#!/usr/bin/env python3
"""Report logical role queues from immutable repository artifact lineage.

The scanner implements contracts/WORK_QUEUES.md. It never determines workflow
order from filesystem timestamps and never treats companion files as separate
jobs.

Exit codes:
    0: no ready work and no fatal lineage errors
    1: one or more ready jobs
    2: invalid or ambiguous lineage prevents a trustworthy result
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only in an incomplete runtime
    print(
        "PyYAML is required. Install it with: python -m pip install PyYAML",
        file=sys.stderr,
    )
    raise SystemExit(2)


ROLE_ORDER = ("Analyst", "Builder", "Reviewer", "Architect", "Integrator")
DEFAULT_ROOT = Path(__file__).resolve().parents[2]
REVISION_PATTERN = re.compile(r"-r(\d+)$")
APPROVED_ID_PATTERN = re.compile(r"\bAPPROVED-[A-Za-z0-9._-]+")
COMPONENT_SUFFIXES = (
    ".edges.csv",
    ".nodes.csv",
    ".validation.json",
    ".report.json",
    ".yaml",
    ".yml",
    ".json",
    ".csv",
)


@dataclass(frozen=True)
class Artifact:
    path: Path
    kind: str
    ruleset: str
    book: str | None
    data: dict[str, Any]

    @property
    def artifact_id(self) -> str:
        return str(self.data.get("id") or self.path.stem)

    @property
    def packet_id(self) -> str | None:
        value = self.data.get("packet_id")
        return str(value) if value else None

    @property
    def supersedes(self) -> str | None:
        value = self.data.get("supersedes")
        return str(value) if value else None

    @property
    def revision(self) -> int | None:
        value = self.data.get("revision")
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit() and int(value) > 0:
            return int(value)
        match = REVISION_PATTERN.search(self.artifact_id)
        return int(match.group(1)) if match else None


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _diag(
    diagnostics: list[dict[str, Any]],
    severity: str,
    code: str,
    message: str,
    *,
    path: str | None = None,
    artifact_id: str | None = None,
) -> None:
    diagnostics.append(
        {
            "Severity": severity,
            "Code": code,
            "ArtifactId": artifact_id,
            "Path": path,
            "Message": message,
        }
    )


def _load_yaml(
    root: Path,
    path: Path,
    diagnostics: list[dict[str, Any]],
) -> dict[str, Any] | None:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        _diag(
            diagnostics,
            "error",
            "yaml_unreadable",
            str(exc),
            path=_relative(root, path),
        )
        return None
    if not isinstance(document, dict):
        _diag(
            diagnostics,
            "error",
            "yaml_root_not_mapping",
            "Artifact YAML root must be a mapping.",
            path=_relative(root, path),
        )
        return None
    return document


def _load_artifacts(
    root: Path,
    directory: Path,
    kind: str,
    ruleset: str,
    book: str | None,
    diagnostics: list[dict[str, Any]],
) -> list[Artifact]:
    artifacts: list[Artifact] = []
    if not directory.is_dir():
        return artifacts
    for path in sorted(directory.glob("*.yaml")):
        if path.name.startswith("."):
            continue
        document = _load_yaml(root, path, diagnostics)
        if document is None:
            continue
        artifacts.append(Artifact(path, kind, ruleset, book, document))
    return artifacts


PACKET_UPDATE = "packet_update"
DECISION_MIGRATION = "decision_migration"
LEGACY_MIGRATION = "identity_merge_migration"


def _sha256_of(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _lineage_root(artifact: Artifact) -> str:
    """Which of the two GUP lineage roots this artifact declares.

    WORK_QUEUES 1.2: a declared kind is never reinterpreted to make an invalid
    artifact routable. Only a GUP that omits the field is inferred, and only as
    a packet update, and only where its GUR provenance is actually recoverable.
    """
    declared = str(artifact.data.get("artifact_kind") or "").strip()
    if declared:
        return declared
    provenance = artifact.data.get("provenance")
    if isinstance(provenance, dict) and provenance.get("gur_id"):
        return PACKET_UPDATE
    return PACKET_UPDATE


def _decision_migration_errors(
    root: Path,
    artifact: Artifact,
    decisions: dict[str, tuple[Path, dict[str, Any]]],
) -> list[str]:
    """Every mandatory condition of the WORK_QUEUES 1.2 Decision Migration section.

    Returns the reasons this artifact may not be routed to Reviewer. An empty
    list means the alternate auditable root is intact: the Decisions exist, are
    approved, belong to this ruleset, require a migration, and hash to what the
    GUP recorded, and the canonical baseline it was planned against still stands.
    """
    reasons: list[str] = []
    data = artifact.data

    if str(data.get("artifact_kind") or "") == LEGACY_MIGRATION:
        reasons.append(
            "declares the legacy artifact_kind identity_merge_migration, which is not "
            "Reviewer-ready until superseded by a conforming decision_migration revision"
        )
        return reasons

    lineage_id = str(data.get("lineage_id") or "").strip()
    if not lineage_id:
        reasons.append("has no lineage_id")
    if data.get("revision") is None:
        reasons.append("has no revision")
    revision = data.get("revision")
    if isinstance(revision, int) and revision >= 2 and not data.get("supersedes"):
        reasons.append(f"is revision {revision} but names no supersedes")

    provenance = data.get("provenance")
    if not isinstance(provenance, dict):
        reasons.append("has no provenance block")
        provenance = {}

    for forbidden in ("gur_id", "gur_checksum"):
        if provenance.get(forbidden):
            reasons.append(
                f"carries provenance.{forbidden}; a decision migration has no GUR lineage"
            )

    authority = data.get("authority")
    if not isinstance(authority, list) or not authority:
        reasons.append("has an empty or missing authority list")
        authority = []
    if len(set(map(str, authority))) != len(authority):
        reasons.append("repeats a Decision in authority")

    inputs = provenance.get("decision_inputs")
    if not isinstance(inputs, list) or not inputs:
        reasons.append("has no provenance.decision_inputs")
        inputs = []

    input_ids = [str(entry.get("id")) for entry in inputs if isinstance(entry, dict)]
    if sorted(input_ids) != sorted(str(a) for a in authority):
        reasons.append(
            "authority and provenance.decision_inputs name different Decisions "
            f"({sorted(str(a) for a in authority)} vs {sorted(input_ids)})"
        )

    for entry in inputs:
        if not isinstance(entry, dict):
            reasons.append("a decision_inputs entry is not a mapping")
            continue
        decision_id = str(entry.get("id") or "")
        recorded = str(entry.get("checksum") or "")
        relative = str(entry.get("path") or "")
        if not recorded:
            reasons.append(f"{decision_id or 'a decision input'} has no checksum")
        known = decisions.get(decision_id)
        if known is None:
            reasons.append(f"{decision_id or 'a decision input'} is not an approved Decision "
                           f"of ruleset {artifact.ruleset}")
            continue
        path, document = known
        if str(document.get("ruleset_id") or "") != artifact.ruleset:
            reasons.append(f"{decision_id} belongs to another ruleset")
        if document.get("migration_required") is not True:
            reasons.append(f"{decision_id} does not declare migration_required: true")
        if relative and _relative(root, path) != relative:
            reasons.append(
                f"{decision_id} is recorded at {relative}, but the Decision is at "
                f"{_relative(root, path)}"
            )
        if recorded and _sha256_of(path) != recorded:
            reasons.append(
                f"{decision_id} has changed since this GUP was planned; its checksum no "
                f"longer matches"
            )

    canonical_source = str(provenance.get("canonical_source") or "")
    canonical_checksum = str(provenance.get("canonical_checksum") or "")
    if not canonical_source:
        reasons.append("records no canonical_source")
    if not canonical_checksum:
        reasons.append("records no canonical_checksum")
    if provenance.get("canonical_rows_read") is None:
        reasons.append("records no canonical_rows_read")
    if canonical_source and canonical_checksum:
        canonical_path = root / canonical_source
        if not canonical_path.is_file():
            reasons.append(f"names canonical source {canonical_source}, which does not exist")
        elif _sha256_of(canonical_path) != canonical_checksum:
            # The plan describes a before-state that is no longer there. Applying
            # it would edit rows nobody reviewed.
            reasons.append(
                "was planned against a canonical baseline that has since changed; "
                "Builder must re-issue it"
            )

    report = str(data.get("validation_report") or "")
    report_checksum = str(data.get("validation_report_checksum") or "")
    if not report:
        reasons.append("names no validation_report")
    if not report_checksum:
        reasons.append("names no validation_report_checksum")
    if report and report_checksum:
        report_path = root / report
        if not report_path.is_file():
            reasons.append(f"names validation report {report}, which does not exist")
        elif _sha256_of(report_path) != report_checksum:
            reasons.append("validation report checksum does not match the file")

    return reasons


def _migration_components(root: Path, artifact: Artifact) -> list[str]:
    components = [_relative(root, artifact.path)]
    report = str(artifact.data.get("validation_report") or "")
    if report and (root / report).is_file():
        components.append(report)
    return components


def _active_leaf(
    root: Path,
    artifacts: list[Artifact],
    diagnostics: list[dict[str, Any]],
    group_label: str,
) -> tuple[Artifact | None, bool]:
    """Return the active leaf and whether legacy revision inference was used."""
    if not artifacts:
        return None, False

    by_id: dict[str, Artifact] = {}
    revisions: dict[int, Artifact] = {}
    for artifact in artifacts:
        if artifact.artifact_id in by_id:
            _diag(
                diagnostics,
                "error",
                "duplicate_artifact_id",
                f"Duplicate {group_label} ID.",
                path=_relative(root, artifact.path),
                artifact_id=artifact.artifact_id,
            )
            return None, False
        by_id[artifact.artifact_id] = artifact
        revision = artifact.revision
        if revision is not None:
            if revision in revisions:
                _diag(
                    diagnostics,
                    "error",
                    "duplicate_revision",
                    f"{group_label} has more than one r{revision:02d} revision.",
                    path=_relative(root, artifact.path),
                    artifact_id=artifact.artifact_id,
                )
                return None, False
            revisions[revision] = artifact

    successor_count: Counter[str] = Counter()
    superseded: set[str] = set()
    for artifact in artifacts:
        predecessor = artifact.supersedes
        if not predecessor:
            continue
        if predecessor not in by_id:
            _diag(
                diagnostics,
                "error",
                "missing_supersedes_target",
                f"{artifact.artifact_id} supersedes missing ID {predecessor}.",
                path=_relative(root, artifact.path),
                artifact_id=artifact.artifact_id,
            )
            return None, False
        successor_count[predecessor] += 1
        superseded.add(predecessor)

    forks = [predecessor for predecessor, count in successor_count.items() if count > 1]
    if forks:
        _diag(
            diagnostics,
            "error",
            "forked_revision_lineage",
            f"{group_label} forks after {', '.join(sorted(forks))}.",
            artifact_id=forks[0],
        )
        return None, False

    leaves = [artifact for artifact in artifacts if artifact.artifact_id not in superseded]
    if len(leaves) == 1:
        return leaves[0], False

    # Legacy GUPs and Reviews often omit supersedes. Infer only when every
    # revision number is present and unique within this packet and artifact kind.
    if len(revisions) == len(artifacts):
        leaf = revisions[max(revisions)]
        _diag(
            diagnostics,
            "warning",
            "legacy_revision_inference",
            f"{group_label} omits an unambiguous supersedes chain; selected "
            f"{leaf.artifact_id} by rNN within this artifact kind and packet.",
            path=_relative(root, leaf.path),
            artifact_id=leaf.artifact_id,
        )
        return leaf, True

    _diag(
        diagnostics,
        "error",
        "ambiguous_revision_lineage",
        f"{group_label} has {len(leaves)} active leaves and cannot be ordered safely.",
    )
    return None, False


def _component_paths(root: Path, gup: Artifact) -> list[str]:
    components = [_relative(root, gup.path)]
    edge_path = gup.path.with_suffix(".edges.csv")
    if edge_path.is_file():
        components.append(_relative(root, edge_path))
    report = gup.data.get("validation_report")
    if isinstance(report, str):
        report_path = root / report
        if report_path.is_file():
            components.append(_relative(root, report_path))
    return components


def _blocking_ids(document: dict[str, Any]) -> set[str]:
    blockers: set[str] = set()
    handoff = document.get("handoff")
    if isinstance(handoff, dict):
        for value in handoff.get("blocking_ids") or []:
            if isinstance(value, str) and value:
                blockers.add(value)
    for entry in document.get("escalations") or []:
        if isinstance(entry, dict):
            value = entry.get("id") or entry.get("escalation_id")
            if isinstance(value, str) and value:
                blockers.add(value)
    for entry in document.get("architectural_escalations") or []:
        if isinstance(entry, dict):
            value = entry.get("id") or entry.get("escalation_id")
            if isinstance(value, str) and value:
                blockers.add(value)
    return blockers


def _queue_item(
    *,
    state: str,
    queue: str,
    role: str,
    ruleset: str,
    book: str | None,
    packet_id: str | None,
    input_id: str,
    reason: str,
    path: str,
    components: Iterable[str],
    legacy_inference: bool = False,
) -> dict[str, Any]:
    return {
        "State": state,
        "Queue": queue,
        "Role": role,
        "Ruleset": ruleset,
        "Book": book,
        "PacketId": packet_id,
        "InputId": input_id,
        "Reason": reason,
        "Path": path,
        "Components": list(dict.fromkeys(components)),
        "LegacyInference": legacy_inference,
    }


def _approved_base(name: str) -> str:
    for suffix in COMPONENT_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return Path(name).stem


def _collect_approved_ids(value: Any, found: set[str]) -> None:
    if isinstance(value, dict):
        for child in value.values():
            _collect_approved_ids(child, found)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _collect_approved_ids(child, found)
    elif isinstance(value, str):
        for match in APPROVED_ID_PATTERN.findall(value):
            found.add(_approved_base(Path(match).name))


def _integrated_approved_ids(
    root: Path,
    ruleset: str,
    book_root: Path,
    diagnostics: list[dict[str, Any]],
) -> set[str]:
    found: set[str] = set()
    manifest_dir = root / "rulesets" / ruleset / "manifests"
    if manifest_dir.is_dir():
        for path in sorted(manifest_dir.glob("INT-*")):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
                if path.suffix.lower() == ".json":
                    document = json.loads(text)
                elif path.suffix.lower() in {".yaml", ".yml"}:
                    document = yaml.safe_load(text)
                else:
                    document = text
                _collect_approved_ids(document, found)
            except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
                _diag(
                    diagnostics,
                    "error",
                    "integration_manifest_unreadable",
                    str(exc),
                    path=_relative(root, path),
                )
    integrated_dir = book_root / "artifacts" / "integrated"
    if integrated_dir.is_dir():
        for path in integrated_dir.iterdir():
            if path.name.startswith("."):
                continue
            if path.name.startswith("APPROVED-"):
                found.add(_approved_base(path.name))
    return found


def _sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    role_index = {role: index for index, role in enumerate(ROLE_ORDER)}
    return sorted(
        items,
        key=lambda item: (
            role_index.get(item["Role"], len(ROLE_ORDER)),
            item.get("Ruleset") or "",
            item.get("Book") or "",
            item.get("Queue") or "",
            item.get("InputId") or "",
        ),
    )


def scan_repository(root: Path) -> dict[str, Any]:
    root = root.resolve()
    diagnostics: list[dict[str, Any]] = []
    ready: list[dict[str, Any]] = []
    active: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    informational: list[dict[str, Any]] = []

    if not (root / "README.md").is_file() or not (root / "books").is_dir():
        _diag(
            diagnostics,
            "error",
            "not_repository_root",
            "Root must contain README.md and books/.",
            path=str(root),
        )
        return _build_result(root, ready, active, blocked, informational, diagnostics)

    decided_by_ruleset: dict[str, set[str]] = defaultdict(set)
    #: Approved Decisions by ruleset and ID, with the path they were read from so
    #: a decision migration's recorded checksum can be re-verified against it.
    decisions_by_ruleset: dict[str, dict[str, tuple[Path, dict[str, Any]]]] = defaultdict(dict)
    #: Decision migrations found anywhere: book GUP stores and ruleset-scoped
    #: cross-book stores alike. Scope location does not change the lineage checks.
    migrations_by_ruleset: dict[str, list[Artifact]] = defaultdict(list)
    reviewed_gup_ids_global: set[str] = set()
    rulesets_root = root / "rulesets"
    if rulesets_root.is_dir():
        for ruleset_dir in sorted(path for path in rulesets_root.iterdir() if path.is_dir()):
            ruleset = ruleset_dir.name
            decided_dir = ruleset_dir / "escalations" / "decided"
            if decided_dir.is_dir():
                for path in decided_dir.glob("ESC-*.yaml"):
                    document = _load_yaml(root, path, diagnostics)
                    if document:
                        decided_by_ruleset[ruleset].add(str(document.get("id") or path.stem))
            decisions_dir = ruleset_dir / "escalations" / "decisions"
            if decisions_dir.is_dir():
                for path in sorted(decisions_dir.glob("DEC-*.yaml")):
                    document = _load_yaml(root, path, diagnostics)
                    if document and str(document.get("status") or "") == "approved":
                        escalation_id = document.get("escalation_id")
                        if isinstance(escalation_id, str) and escalation_id:
                            decided_by_ruleset[ruleset].add(escalation_id)
                        decisions_by_ruleset[ruleset][
                            str(document.get("id") or path.stem)
                        ] = (path, document)

            pending_dir = ruleset_dir / "escalations" / "pending"
            if pending_dir.is_dir():
                for path in sorted(pending_dir.glob("ESC-*.yaml")):
                    document = _load_yaml(root, path, diagnostics)
                    if not document:
                        continue
                    escalation_id = str(document.get("id") or path.stem)
                    ready.append(
                        _queue_item(
                            state="ready",
                            queue="ARCHITECT-ESC",
                            role="Architect",
                            ruleset=ruleset,
                            book=document.get("book_id"),
                            packet_id=document.get("packet_id"),
                            input_id=escalation_id,
                            reason="Complete escalation package is pending an Architect decision.",
                            path=_relative(root, path),
                            components=[_relative(root, path)],
                        )
                    )

    books_root = root / "books"
    for ruleset_dir in sorted(path for path in books_root.iterdir() if path.is_dir()):
        ruleset = ruleset_dir.name
        for book_root in sorted(path for path in ruleset_dir.iterdir() if path.is_dir()):
            book = book_root.name
            artifacts_root = book_root / "artifacts"
            gurs = _load_artifacts(
                root, artifacts_root / "gur", "gur", ruleset, book, diagnostics
            )
            gups = _load_artifacts(
                root, artifacts_root / "gup", "gup", ruleset, book, diagnostics
            )
            reviews = _load_artifacts(
                root, artifacts_root / "reviews", "review", ruleset, book, diagnostics
            )

            gurs_by_packet: dict[str, list[Artifact]] = defaultdict(list)
            gups_by_packet: dict[str, list[Artifact]] = defaultdict(list)
            reviews_by_gup: dict[str, list[Artifact]] = defaultdict(list)
            for artifact in gurs:
                if artifact.packet_id:
                    gurs_by_packet[artifact.packet_id].append(artifact)
                else:
                    _diag(
                        diagnostics,
                        "error",
                        "gur_missing_packet_id",
                        "GUR has no packet_id.",
                        path=_relative(root, artifact.path),
                        artifact_id=artifact.artifact_id,
                    )
            for artifact in gups:
                # A decision migration is grouped by lineage_id, not packet_id:
                # several independent migrations all carry `cross-packet`, so
                # packet grouping would collapse them into one false chain.
                if _lineage_root(artifact) in (DECISION_MIGRATION, LEGACY_MIGRATION):
                    migrations_by_ruleset[ruleset].append(artifact)
                    continue
                if artifact.packet_id:
                    gups_by_packet[artifact.packet_id].append(artifact)
                else:
                    _diag(
                        diagnostics,
                        "error",
                        "gup_missing_packet_id",
                        "GUP has no packet_id.",
                        path=_relative(root, artifact.path),
                        artifact_id=artifact.artifact_id,
                    )
            for artifact in reviews:
                reviewed = artifact.data.get("reviewed_gup")
                reviewed_id = reviewed.get("id") if isinstance(reviewed, dict) else None
                if reviewed_id:
                    reviews_by_gup[str(reviewed_id)].append(artifact)
                    # A migration is cross-book, so the Review that consumes it
                    # may sit in any book's review store.
                    reviewed_gup_ids_global.add(str(reviewed_id))
                else:
                    _diag(
                        diagnostics,
                        "error",
                        "review_missing_gup_id",
                        "Review has no reviewed_gup.id.",
                        path=_relative(root, artifact.path),
                        artifact_id=artifact.artifact_id,
                    )

            # Analyst ready and active states.
            incoming_dir = book_root / "packets" / "incoming"
            if incoming_dir.is_dir():
                for path in sorted(incoming_dir.iterdir()):
                    if path.name.startswith("."):
                        continue
                    input_id = path.name
                    packet_id = None
                    if path.is_dir() and (path / "packet.yaml").is_file():
                        document = _load_yaml(root, path / "packet.yaml", diagnostics)
                        if document:
                            packet_id = document.get("id") or document.get("packet_id")
                            input_id = str(packet_id or path.name)
                    ready.append(
                        _queue_item(
                            state="ready",
                            queue="ANALYST-INCOMING",
                            role="Analyst",
                            ruleset=ruleset,
                            book=book,
                            packet_id=str(packet_id) if packet_id else None,
                            input_id=input_id,
                            reason="Incoming source or packet is awaiting Analyst claim.",
                            path=_relative(root, path),
                            components=[_relative(root, path)],
                        )
                    )

            claimed_dir = book_root / "packets" / "claimed"
            if claimed_dir.is_dir():
                for path in sorted(item for item in claimed_dir.iterdir() if item.is_dir()):
                    if path.name.startswith("."):
                        continue
                    packet_id = path.name
                    manifest = path / "packet.yaml"
                    if manifest.is_file():
                        document = _load_yaml(root, manifest, diagnostics)
                        if document:
                            packet_id = str(
                                document.get("id")
                                or document.get("packet_id")
                                or packet_id
                            )
                    target = informational if packet_id in gurs_by_packet else active
                    state = "informational" if target is informational else "active"
                    reason = (
                        "Claimed packet is retained for provenance; a GUR already "
                        "completed the Analyst handoff."
                        if target is informational
                        else "Claimed packet has no GUR and remains active Analyst work."
                    )
                    target.append(
                        _queue_item(
                            state=state,
                            queue="ANALYST-CLAIMED",
                            role="Analyst",
                            ruleset=ruleset,
                            book=book,
                            packet_id=packet_id,
                            input_id=packet_id,
                            reason=reason,
                            path=_relative(root, path),
                            components=[_relative(root, path)],
                        )
                    )

            all_packets = sorted(set(gurs_by_packet) | set(gups_by_packet))
            leaf_gur_by_packet: dict[str, tuple[Artifact | None, bool]] = {}
            leaf_gup_by_packet: dict[str, tuple[Artifact | None, bool]] = {}
            for packet_id in all_packets:
                leaf_gur_by_packet[packet_id] = _active_leaf(
                    root,
                    gurs_by_packet.get(packet_id, []),
                    diagnostics,
                    f"{ruleset}/{book}/{packet_id} GUR",
                )
                leaf_gup_by_packet[packet_id] = _active_leaf(
                    root,
                    gups_by_packet.get(packet_id, []),
                    diagnostics,
                    f"{ruleset}/{book}/{packet_id} GUP",
                )

            consumed_gur_ids = {
                str(provenance.get("gur_id"))
                for artifact in gups
                if isinstance((provenance := artifact.data.get("provenance")), dict)
                and provenance.get("gur_id")
            }
            reviewed_gup_ids = set(reviews_by_gup)

            for packet_id in all_packets:
                leaf_gur, gur_inferred = leaf_gur_by_packet[packet_id]
                leaf_gup, gup_inferred = leaf_gup_by_packet[packet_id]

                if leaf_gur and leaf_gur.artifact_id not in consumed_gur_ids:
                    ready.append(
                        _queue_item(
                            state="ready",
                            queue="BUILDER-GUR",
                            role="Builder",
                            ruleset=ruleset,
                            book=book,
                            packet_id=packet_id,
                            input_id=leaf_gur.artifact_id,
                            reason="Active-leaf GUR has no consuming GUP.",
                            path=_relative(root, leaf_gur.path),
                            components=[_relative(root, leaf_gur.path)],
                            legacy_inference=gur_inferred,
                        )
                    )

                if not leaf_gup:
                    continue

                status = str(leaf_gup.data.get("status") or "")
                approval_ready = leaf_gup.data.get("approval_ready") is True
                provenance = leaf_gup.data.get("provenance")
                source_gur_id = (
                    str(provenance.get("gur_id"))
                    if isinstance(provenance, dict) and provenance.get("gur_id")
                    else None
                )
                source_is_leaf = bool(
                    leaf_gur and source_gur_id == leaf_gur.artifact_id
                )

                if status == "proposed" and approval_ready and not source_is_leaf:
                    _diag(
                        diagnostics,
                        "warning",
                        "stale_gup_input",
                        f"{leaf_gup.artifact_id} references {source_gur_id or 'no GUR'}, "
                        f"but the active GUR is "
                        f"{leaf_gur.artifact_id if leaf_gur else 'missing'}. "
                        "It is not Reviewer-ready.",
                        path=_relative(root, leaf_gup.path),
                        artifact_id=leaf_gup.artifact_id,
                    )

                blockers = _blocking_ids(leaf_gup.data)
                unresolved = blockers - decided_by_ruleset[ruleset]
                if status == "blocked":
                    if blockers and not unresolved:
                        ready.append(
                            _queue_item(
                                state="ready",
                                queue="BUILDER-REVISION",
                                role="Builder",
                                ruleset=ruleset,
                                book=book,
                                packet_id=packet_id,
                                input_id=leaf_gup.artifact_id,
                                reason="All architectural blockers are decided; rebuild the GUP.",
                                path=_relative(root, leaf_gup.path),
                                components=_component_paths(root, leaf_gup),
                                legacy_inference=gup_inferred,
                            )
                        )
                    else:
                        reason = (
                            "Blocked GUP is waiting on: " + ", ".join(sorted(unresolved))
                            if unresolved
                            else "Blocked GUP has no resolved downstream handoff."
                        )
                        blocked.append(
                            _queue_item(
                                state="blocked",
                                queue="BUILDER-BLOCKED",
                                role="Builder",
                                ruleset=ruleset,
                                book=book,
                                packet_id=packet_id,
                                input_id=leaf_gup.artifact_id,
                                reason=reason,
                                path=_relative(root, leaf_gup.path),
                                components=_component_paths(root, leaf_gup),
                                legacy_inference=gup_inferred,
                            )
                        )

                review_leaf = None
                review_inferred = False
                if leaf_gup.artifact_id in reviews_by_gup:
                    review_leaf, review_inferred = _active_leaf(
                        root,
                        reviews_by_gup[leaf_gup.artifact_id],
                        diagnostics,
                        f"{leaf_gup.artifact_id} Review",
                    )

                if (
                    status == "proposed"
                    and approval_ready
                    and source_is_leaf
                    and leaf_gup.artifact_id not in reviewed_gup_ids
                ):
                    ready.append(
                        _queue_item(
                            state="ready",
                            queue="REVIEWER-GUP",
                            role="Reviewer",
                            ruleset=ruleset,
                            book=book,
                            packet_id=packet_id,
                            input_id=leaf_gup.artifact_id,
                            reason="Approval-ready active-leaf GUP has no Review.",
                            path=_relative(root, leaf_gup.path),
                            components=_component_paths(root, leaf_gup),
                            legacy_inference=gup_inferred,
                        )
                    )

                if review_leaf:
                    disposition = str(
                        review_leaf.data.get("overall_disposition")
                        or review_leaf.data.get("status")
                        or ""
                    )
                    review_blockers = _blocking_ids(review_leaf.data)
                    review_unresolved = (
                        review_blockers - decided_by_ruleset[ruleset]
                    )
                    if disposition == "revision_required":
                        ready.append(
                            _queue_item(
                                state="ready",
                                queue="BUILDER-REVISION",
                                role="Builder",
                                ruleset=ruleset,
                                book=book,
                                packet_id=packet_id,
                                input_id=review_leaf.artifact_id,
                                reason="Active Review requires a Builder revision.",
                                path=_relative(root, review_leaf.path),
                                components=[_relative(root, review_leaf.path)],
                                legacy_inference=review_inferred,
                            )
                        )
                    elif (
                        disposition == "architect_escalation"
                        and review_blockers
                        and not review_unresolved
                    ):
                        ready.append(
                            _queue_item(
                                state="ready",
                                queue="BUILDER-REVISION",
                                role="Builder",
                                ruleset=ruleset,
                                book=book,
                                packet_id=packet_id,
                                input_id=review_leaf.artifact_id,
                                reason="Review escalations are decided; rebuild the GUP.",
                                path=_relative(root, review_leaf.path),
                                components=[_relative(root, review_leaf.path)],
                                legacy_inference=review_inferred,
                            )
                        )

            # Approved bundles are grouped by base ID.
            approved_dir = artifacts_root / "approved"
            approved_groups: dict[str, list[Path]] = defaultdict(list)
            if approved_dir.is_dir():
                for path in sorted(approved_dir.iterdir()):
                    if path.name.startswith(".") or not path.is_file():
                        continue
                    approved_groups[_approved_base(path.name)].append(path)

            review_by_id = {artifact.artifact_id: artifact for artifact in reviews}
            integrated_ids = _integrated_approved_ids(
                root, ruleset, book_root, diagnostics
            )
            for approved_id, component_paths in sorted(approved_groups.items()):
                manifest_path = next(
                    (
                        path
                        for path in component_paths
                        if path.suffix.lower() in {".yaml", ".yml"}
                    ),
                    None,
                )
                manifest = (
                    _load_yaml(root, manifest_path, diagnostics)
                    if manifest_path
                    else None
                )
                review_id = None
                packet_id = None
                if manifest:
                    review_id = manifest.get("review_id")
                    packet_id = manifest.get("packet_id")
                    if not review_id and isinstance(manifest.get("provenance"), dict):
                        review_id = manifest["provenance"].get("review_id")
                if not review_id and approved_id.startswith("APPROVED-"):
                    review_id = "REV-" + approved_id[len("APPROVED-") :]

                review = review_by_id.get(str(review_id)) if review_id else None
                if review is None:
                    _diag(
                        diagnostics,
                        "warning",
                        "approved_review_inferred_or_missing",
                        f"{approved_id} has no manifest-linked Review. "
                        f"Tried legacy Review ID {review_id or '(none)'}.",
                        path=_relative(root, component_paths[0]),
                        artifact_id=approved_id,
                    )
                    # A legacy filename that maps exactly to an approved Review is
                    # accepted below; otherwise integration would be unsafe.
                    continue
                disposition = str(
                    review.data.get("overall_disposition")
                    or review.data.get("status")
                    or ""
                )
                if disposition != "approved":
                    _diag(
                        diagnostics,
                        "error",
                        "approved_bundle_without_approval",
                        f"{approved_id} maps to non-approved Review {review.artifact_id}.",
                        path=_relative(root, component_paths[0]),
                        artifact_id=approved_id,
                    )
                    continue
                if approved_id in integrated_ids:
                    informational.append(
                        _queue_item(
                            state="informational",
                            queue="INTEGRATOR-CONSUMED",
                            role="Integrator",
                            ruleset=ruleset,
                            book=book,
                            packet_id=str(packet_id or review.packet_id or "") or None,
                            input_id=approved_id,
                            reason="Approved bundle is already named by an Integration record.",
                            path=_relative(root, component_paths[0]),
                            components=[_relative(root, path) for path in component_paths],
                            legacy_inference=manifest is None,
                        )
                    )
                    continue
                ready.append(
                    _queue_item(
                        state="ready",
                        queue="INTEGRATOR-APPROVED",
                        role="Integrator",
                        ruleset=ruleset,
                        book=book,
                        packet_id=str(packet_id or review.packet_id or "") or None,
                        input_id=approved_id,
                        reason="Approved bundle is not named by an Integration record.",
                        path=_relative(root, component_paths[0]),
                        components=[_relative(root, path) for path in component_paths],
                        legacy_inference=manifest is None,
                    )
                )

    # -- decision migrations ---------------------------------------------------
    # Deliberately after the books loop, because a decision migration is
    # cross-book: its GUP may sit in a book store or in the ruleset-scoped
    # cross-book store, and the Review that consumes it may sit in any book.
    if rulesets_root.is_dir():
        for ruleset_dir in sorted(path for path in rulesets_root.iterdir() if path.is_dir()):
            ruleset = ruleset_dir.name
            cross_book = ruleset_dir / "cross-book"
            if cross_book.is_dir():
                for path in sorted(cross_book.rglob("GUP-*.yaml")):
                    if path.name.startswith("."):
                        continue
                    document = _load_yaml(root, path, diagnostics)
                    if document is None:
                        continue
                    migrations_by_ruleset[ruleset].append(
                        Artifact(path, "gup", ruleset, None, document)
                    )

            decisions = decisions_by_ruleset[ruleset]
            migrations = migrations_by_ruleset[ruleset]

            by_lineage: dict[str, list[Artifact]] = defaultdict(list)
            unkeyed: dict[str, Artifact] = {}
            for artifact in migrations:
                lineage_id = str(artifact.data.get("lineage_id") or "").strip()
                if lineage_id:
                    by_lineage[lineage_id].append(artifact)
                else:
                    unkeyed[artifact.artifact_id] = artifact

            # `lineage_id` postdates the first migrations, so a conforming
            # revision often supersedes one that predates the field. Follow the
            # supersedes chain backwards to pull those into the lineage that
            # claims them; anything still unclaimed gets its own group so it is
            # reported rather than silently merged with an unrelated migration.
            for lineage_id in sorted(by_lineage):
                pending = [str(a.data.get("supersedes") or "") for a in by_lineage[lineage_id]]
                while pending:
                    predecessor = unkeyed.pop(pending.pop(), None)
                    if predecessor is None:
                        continue
                    by_lineage[lineage_id].append(predecessor)
                    pending.append(str(predecessor.data.get("supersedes") or ""))
            for artifact_id, artifact in unkeyed.items():
                by_lineage[f"!unkeyed:{artifact_id}"].append(artifact)

            consumed_decision_ids: set[str] = set()
            for lineage_id in sorted(by_lineage):
                group = by_lineage[lineage_id]
                leaf, inferred = _active_leaf(
                    root, group, diagnostics, f"{ruleset} decision migration {lineage_id}"
                )
                if leaf is None:
                    continue

                reasons = _decision_migration_errors(root, leaf, decisions)
                if reasons:
                    # A legacy spelling is known debt, not broken lineage: the
                    # artifact is immutable history awaiting a conforming
                    # revision. Reporting it as an error would make every scan
                    # of the repository exit 2 until that revision exists, which
                    # would hide the errors that do mean something.
                    legacy = str(leaf.data.get("artifact_kind") or "") == LEGACY_MIGRATION
                    _diag(
                        diagnostics,
                        "warning" if legacy else "error",
                        "legacy_migration_spelling" if legacy
                        else "decision_migration_lineage_error",
                        f"{leaf.artifact_id} " + "; ".join(reasons) + ".",
                        path=_relative(root, leaf.path),
                        artifact_id=leaf.artifact_id,
                    )
                    # Either way it does not consume its authority Decisions, so
                    # their Builder jobs stay visible.
                    continue

                consumed_decision_ids.update(str(a) for a in leaf.data.get("authority") or [])

                status = str(leaf.data.get("status") or "")
                approval_ready = leaf.data.get("approval_ready") is True
                handoff = leaf.data.get("handoff")
                handoff_ready = (
                    isinstance(handoff, dict)
                    and str(handoff.get("next_role") or "") == "reviewer"
                    and str(handoff.get("readiness") or "") == "ready"
                    and not (handoff.get("blocking_ids") or [])
                )
                blockers = _blocking_ids(leaf.data)
                unresolved = blockers - decided_by_ruleset[ruleset]

                if status == "blocked" or not approval_ready:
                    blocked.append(
                        _queue_item(
                            state="blocked",
                            queue="BUILDER-DECISION-MIGRATION-BLOCKED",
                            role="Builder",
                            ruleset=ruleset,
                            book=leaf.book,
                            packet_id=leaf.packet_id,
                            input_id=leaf.artifact_id,
                            reason=(
                                "Blocked decision migration is waiting on: "
                                + ", ".join(sorted(unresolved))
                                if unresolved
                                else "Decision migration is not approval-ready."
                            ),
                            path=_relative(root, leaf.path),
                            components=_migration_components(root, leaf),
                            legacy_inference=inferred,
                        )
                    )
                    continue

                if not handoff_ready:
                    _diag(
                        diagnostics,
                        "error",
                        "decision_migration_lineage_error",
                        f"{leaf.artifact_id} has no ready Reviewer handoff.",
                        path=_relative(root, leaf.path),
                        artifact_id=leaf.artifact_id,
                    )
                    continue

                if leaf.artifact_id in reviewed_gup_ids_global:
                    continue

                ready.append(
                    _queue_item(
                        state="ready",
                        queue="REVIEWER-DECISION-MIGRATION",
                        role="Reviewer",
                        ruleset=ruleset,
                        book=leaf.book,
                        packet_id=leaf.packet_id,
                        input_id=leaf.artifact_id,
                        reason=(
                            "Decision-migration lineage validates; absence of a GUR is "
                            "expected for this artifact kind."
                        ),
                        path=_relative(root, leaf.path),
                        components=_migration_components(root, leaf),
                        legacy_inference=inferred,
                    )
                )

            # A Decision with a ready Builder handoff that requires a migration is
            # Builder work until a structurally valid migration consumes it.
            for decision_id in sorted(decisions):
                path, document = decisions[decision_id]
                handoff = document.get("handoff")
                if not isinstance(handoff, dict):
                    continue
                if str(handoff.get("next_role") or "") != "builder":
                    continue
                if str(handoff.get("readiness") or "") != "ready":
                    continue
                if document.get("migration_required") is not True:
                    continue
                if decision_id in consumed_decision_ids:
                    continue
                ready.append(
                    _queue_item(
                        state="ready",
                        queue="BUILDER-DECISION-MIGRATION",
                        role="Builder",
                        ruleset=ruleset,
                        book=str(document.get("book_id") or "") or None,
                        packet_id=str(document.get("packet_id") or "") or None,
                        input_id=decision_id,
                        reason=(
                            "Approved Decision requires a migration and no valid "
                            "decision-migration GUP consumes it."
                        ),
                        path=_relative(root, path),
                        components=[_relative(root, path)],
                    )
                )

    # A job can be discovered through both a blocked GUP and its Review. Keep one
    # deterministic entry per role, queue, and input artifact.
    ready = _dedupe(ready)
    active = _dedupe(active)
    blocked = _dedupe(blocked)
    informational = _dedupe(informational)
    return _build_result(root, ready, active, blocked, informational, diagnostics)


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in items:
        key = (item["Role"], item["Queue"], item["InputId"])
        unique.setdefault(key, item)
    return _sort_items(list(unique.values()))


def _build_result(
    root: Path,
    ready: list[dict[str, Any]],
    active: list[dict[str, Any]],
    blocked: list[dict[str, Any]],
    informational: list[dict[str, Any]],
    diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    ready = _sort_items(ready)
    active = _sort_items(active)
    blocked = _sort_items(blocked)
    informational = _sort_items(informational)
    diagnostics = sorted(
        diagnostics,
        key=lambda item: (
            0 if item["Severity"] == "error" else 1,
            item["Code"],
            item.get("ArtifactId") or "",
            item.get("Path") or "",
        ),
    )
    summary = []
    for role in ROLE_ORDER:
        summary.append(
            {
                "Role": role,
                "Ready": sum(item["Role"] == role for item in ready),
                "Active": sum(item["Role"] == role for item in active),
                "Blocked": sum(item["Role"] == role for item in blocked),
                "Informational": sum(
                    item["Role"] == role for item in informational
                ),
            }
        )
    return {
        "RepositoryRoot": str(root),
        "ScannedAt": datetime.now(timezone.utc).isoformat(),
        "ReadyCount": len(ready),
        "PendingCount": len(ready),
        "ActiveCount": len(active),
        "BlockedCount": len(blocked),
        "InformationalCount": len(informational),
        "DiagnosticCount": len(diagnostics),
        "LineageErrorCount": sum(
            item["Severity"] == "error" for item in diagnostics
        ),
        "Summary": summary,
        "Items": ready,
        "ActiveItems": active,
        "BlockedItems": blocked,
        "InformationalItems": informational,
        "Diagnostics": diagnostics,
    }


def _print_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    if not rows:
        return
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]
    print("  ".join(headers[index].ljust(widths[index]) for index in range(len(headers))))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(row[index].ljust(widths[index]) for index in range(len(headers))))


def _print_items(title: str, items: list[dict[str, Any]]) -> None:
    if not items:
        return
    print(f"\n{title}\n")
    rows = [
        (
            item["Role"],
            item["Queue"],
            item.get("Ruleset") or "",
            item.get("Book") or "",
            item["InputId"],
            item["Path"],
        )
        for item in items
    ]
    _print_table(("Role", "Queue", "Ruleset", "Book", "Input", "Path"), rows)
    for item in items:
        print(f"\n[{item['Role']}] {item['InputId']}")
        print(f"  {item['Reason']}")
        if len(item["Components"]) > 1:
            print("  Components:")
            for component in item["Components"]:
                print(f"    - {component}")
        if item["LegacyInference"]:
            print("  Legacy inference: yes")


def _print_console(result: dict[str, Any], include_all: bool) -> None:
    print("\nAgent Queue Status")
    print(f"Repository: {result['RepositoryRoot']}\n")
    summary_rows = [
        (
            entry["Role"],
            str(entry["Ready"]),
            str(entry["Active"]),
            str(entry["Blocked"]),
            str(entry["Informational"]),
        )
        for entry in result["Summary"]
    ]
    _print_table(
        ("Role", "Ready", "Active", "Blocked", "Informational"),
        summary_rows,
    )
    _print_items("Ready work", result["Items"])
    if include_all:
        _print_items("Active work", result["ActiveItems"])
        _print_items("Blocked work", result["BlockedItems"])
        _print_items("Informational items", result["InformationalItems"])

    if result["Diagnostics"]:
        print("\nDiagnostics\n")
        rows = [
            (
                item["Severity"],
                item["Code"],
                item.get("ArtifactId") or "",
                item["Message"],
            )
            for item in result["Diagnostics"]
        ]
        _print_table(("Severity", "Code", "Artifact", "Message"), rows)

    print(
        f"\n{result['ReadyCount']} ready job(s), "
        f"{result['ActiveCount']} active, "
        f"{result['BlockedCount']} blocked, "
        f"{result['DiagnosticCount']} diagnostic(s)."
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="Repository root. Defaults to the repository containing this script.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of formatted console output.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Print active, blocked, and informational items in console mode.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = scan_repository(args.root)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_console(result, args.all)
    if result["LineageErrorCount"]:
        return 2
    if result["ReadyCount"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
