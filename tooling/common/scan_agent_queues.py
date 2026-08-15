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
import textwrap
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

#: Lowercase handoff role name -> the reporting role it belongs to. `none` and
#: any unrecognised value are deliberately absent: a blocked artifact naming no
#: actionable role stays with the Builder that produced it rather than vanishing.
ROLE_BY_NAME = {role.lower(): role for role in ROLE_ORDER}
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


def _packaged_gup_id(manifest: dict[str, Any] | None, review: "Artifact") -> str:
    """The GUP an Approved bundle packages.

    Three spellings are in use across the corpus: the bundle manifest may name
    it directly or under `provenance`, and the Review names it as either a
    mapping with an `id` or a bare string. The bundle's own manifest wins when
    it has one -- it is the artifact being routed -- and the Review is the
    fallback for bundles that predate the field.

    Returns `""` when none of them says, which routes the bundle normally
    rather than suppressing it: a supersession check that cannot read the ID
    must not guess that the bundle is stale.
    """
    for source in (manifest or {}), ((manifest or {}).get("provenance") or {}):
        if isinstance(source, dict) and source.get("gup_id"):
            return str(source["gup_id"])
    reviewed = review.data.get("reviewed_gup")
    if isinstance(reviewed, dict):
        return str(reviewed.get("id") or "")
    return str(reviewed or "")


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


def _sequenced_prerequisites(
    review_id: str,
    blockers: set[str],
    decisions: dict[str, tuple[Path, dict[str, Any]]],
    artifacts_root: Path,
) -> list[str]:
    """Artifacts a resolving Decision puts ahead of the Builder's rebuild.

    A Decision that answers a Review's escalation may also rule on the order the
    remaining work happens in. Where it names a routing Review revision the
    Builder must build against, that Review is a prerequisite, not a suggestion:
    it carries the Decision's dispositions down onto the individual rows. Until
    it exists the Builder has decided identities but no instruction set, so the
    rebuild is blocked however thoroughly the escalation was answered.

    Only an exact named artifact counts. Prose sequencing is left alone, because
    guessing an order out of prose is how a queue starts inventing governance.
    """
    prerequisites: list[str] = []
    for decision_id, (_, document) in sorted(decisions.items()):
        if str(document.get("escalation_id") or "") not in blockers:
            continue
        disposition = document.get("packet_disposition")
        if not isinstance(disposition, dict):
            continue
        required = str(disposition.get("required_routing_review") or "").strip()
        # A Decision naming the Review that already exists is describing this
        # one, not asking for a further revision.
        if not required or required == review_id:
            continue
        if not (artifacts_root / "reviews" / f"{required}.yaml").is_file():
            prerequisites.append(f"{required} (required by {decision_id})")
    return sorted(prerequisites)


#: Roles a handoff may name, per WORK_QUEUES "Required Handoff Metadata".
HANDOFF_ROLES = frozenset(
    {"analyst", "builder", "reviewer", "architect", "integrator", "none"}
)


def _handoff_role(document: dict[str, Any]) -> str:
    """The role a document hands work to, or `""` when it names none.

    An unrecognised role is treated as absent rather than trusted: routing work
    to a role that does not exist would hide it from every queue.
    """
    handoff = document.get("handoff")
    if not isinstance(handoff, dict):
        return ""
    role = str(handoff.get("next_role") or "").strip().lower()
    return role if role in HANDOFF_ROLES else ""


def _originating_artifact_refs(block: Any) -> list[tuple[str, str]]:
    """Exact `(artifact id, repository path)` pairs a decided package names.

    WORK_QUEUES 1.3 requires both halves before a handoff may be replaced, and
    forbids inferring the link from free text, packet association or timestamps.
    So only shapes that state an ID *and* a path together are read, and anything
    naming one without the other yields nothing rather than a guess.

    Escalation packages write the pair two ways, both supported here:

        review: REV-...-r01              # `<kind>` plus `<kind>_path`
        review_path: books/.../REV-...yaml

        gur_id: GUR-...-r01              # `<kind>_id` plus `<kind>_path`
        gur_path: books/.../GUR-...yaml

        gup: {id: GUP-...-r02, path: books/.../GUP-...yaml}
    """
    refs: list[tuple[str, str]] = []
    if not isinstance(block, dict):
        return refs

    def add(identifier: Any, path: Any) -> None:
        identifier = str(identifier or "").strip()
        path = str(path or "").strip()
        if identifier and path:
            refs.append((identifier, path))

    for key, value in block.items():
        if isinstance(value, dict):
            add(value.get("id"), value.get("path"))
        elif isinstance(value, list):
            if str(key).endswith("_ids"):
                stem = str(key)[:-4]
                paths = block.get(f"{stem}_paths")
                if isinstance(paths, list) and len(value) == len(paths):
                    for identifier, path in zip(value, paths):
                        add(identifier, path)
            else:
                for entry in value:
                    if isinstance(entry, dict):
                        add(entry.get("id"), entry.get("path"))
        elif isinstance(value, str) and not str(key).endswith("_path"):
            stem = str(key)[:-3] if str(key).endswith("_id") else str(key)
            add(value, block.get(f"{stem}_path"))
    return refs


def _handoff_replacements(
    root: Path,
    ruleset: str,
    decisions: dict[str, tuple[Path, dict[str, Any]]],
    decided_packages: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Decision handoffs that replace an originating artifact's, per WORK_QUEUES 1.3.

    All four conditions of the section must hold: the Decision's `escalation_id`
    resolves to a decided package in this ruleset, that package names an
    artifact ID and path, and the Decision carries an explicit `handoff` block.
    Whether the named artifact is still the active leaf is settled by the caller,
    which only suppresses an item the scan actually derived for that exact ID and
    path -- a superseded artifact has no such item.
    """
    replacements: list[dict[str, Any]] = []
    # Multiple Decisions can name the same active artifact. WORK_QUEUES 1.5
    # gives the later governance ruling precedence, based on authored Decision
    # metadata rather than filesystem state.
    ordered_decision_ids = sorted(
        decisions,
        key=lambda decision_id: (
            str(decisions[decision_id][1].get("decision_date") or ""),
            decision_id,
        ),
        reverse=True,
    )
    for decision_id in ordered_decision_ids:
        path, document = decisions[decision_id]
        escalation_id = str(document.get("escalation_id") or "").strip()
        if not escalation_id:
            continue
        package = decided_packages.get(escalation_id)
        if package is None:
            continue
        handoff = document.get("handoff")
        if not isinstance(handoff, dict) or not handoff.get("next_role"):
            continue
        refs = _originating_artifact_refs(package.get("originating_artifacts"))
        if not refs:
            continue
        replacements.append(
            {
                "decision_id": decision_id,
                "decision_path": _relative(root, path),
                "document": document,
                "handoff": handoff,
                "ruleset": ruleset,
                "refs": refs,
            }
        )
    return replacements


DECISION_IMPLEMENTATION = "decision_implementation"
DECISION_IMPLEMENTATION_REVIEW = "decision_implementation_review"


#: Retirement states WORK_QUEUES 1.6 recognises. Anything else -- deletion, a
#: replaced handoff, an unapproved revision -- is not a retirement.
RETIREMENT_STATES = frozenset(
    {"consumed_by_integrated_bundle", "superseded_by_integrated_revision"}
)


def _authorized_retirement(
    decision_id: str,
    input_checksum: str,
    index: int,
    authority_id: str,
    authority_doc: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    """The authorization covering one retired result, or why there is none.

    Two shapes authorize a retirement. The Decision under implementation may
    classify its own test with `acceptance_test_semantics`; or a later Decision
    may name that exact Decision, checksum and index in
    `retired_acceptance_authorizations`. The second exists because a Decision
    written before this rule cannot classify anything, and rewriting it to say
    so would edit the decision record after the fact.

    Both are exact. Neither may be widened by matching on packet, role or date.
    """
    if authority_id == decision_id:
        for entry in authority_doc.get("acceptance_test_semantics") or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("acceptance_test_index") != index:
                continue
            if str(entry.get("kind") or "") != "live_queue_snapshot":
                return None, (
                    f"{authority_id} classifies acceptance test {index} as "
                    f"{entry.get('kind')!r}, which is not a live queue snapshot"
                )
            if entry.get("retirement_allowed") is not True:
                return None, (
                    f"{authority_id} does not allow retirement of acceptance test {index}"
                )
            return entry, ""
        return None, (
            f"{authority_id} declares no live-queue-snapshot semantics for acceptance "
            f"test {index}, so it cannot authorize its own retirement"
        )

    for entry in authority_doc.get("retired_acceptance_authorizations") or []:
        if not isinstance(entry, dict):
            continue
        target = entry.get("decision_input")
        target = target if isinstance(target, dict) else {}
        if str(target.get("id") or "") != decision_id:
            continue
        if entry.get("acceptance_test_index") != index:
            continue
        # The authority pins the Decision it authorizes. If that Decision has
        # been re-issued since, the ruling was made about different text.
        if str(target.get("checksum") or "").strip() != input_checksum:
            return None, (
                f"{authority_id} authorizes acceptance test {index} of {decision_id} at "
                f"checksum {target.get('checksum')}, but the report records {input_checksum}"
            )
        if str(entry.get("kind") or "") != "live_queue_snapshot":
            return None, (
                f"{authority_id} classifies acceptance test {index} of {decision_id} as "
                f"{entry.get('kind')!r}, which is not a live queue snapshot"
            )
        if entry.get("retirement_allowed") is not True:
            return None, (
                f"{authority_id} does not allow retirement of acceptance test {index} "
                f"of {decision_id}"
            )
        return entry, ""

    return None, (
        f"{authority_id} does not authorize retiring acceptance test {index} of "
        f"{decision_id}"
    )


def _retired_result_errors(
    root: Path,
    decision_id: str,
    input_checksum: str,
    result: dict[str, Any],
    decisions: dict[str, tuple[Path, dict[str, Any]]],
) -> list[str]:
    """WORK_QUEUES 1.6 conditions 1-5 for one `retired_by_lineage` result.

    The outcome says a subject left the asserted queue by completing its whole
    ordinary lineage. Everything here exists to keep that from being assertable
    on any weaker fact: a superseded artifact whose successor never integrated,
    a subject removed by handoff replacement, or an authority that covers a
    different index. Each is checked against repository state rather than
    against what the report says about repository state.
    """
    reasons: list[str] = []
    index = result.get("acceptance_test_index")
    label = f"acceptance result {index}"

    authority = result.get("retirement_authority")
    if not isinstance(authority, dict):
        return [f"{label} is retired_by_lineage but records no retirement_authority"]

    authority_id = str(authority.get("id") or "").strip()
    entry = decisions.get(authority_id)
    if entry is None:
        return [
            f"{label} names retirement authority {authority_id!r}, which is not an "
            f"approved Decision of this ruleset"
        ]
    authority_path, authority_doc = entry

    declared = str(authority.get("path") or "").strip()
    actual = _relative(root, authority_path)
    if declared != actual:
        reasons.append(
            f"{label} records authority path {declared!r} but {authority_id} is at {actual!r}"
        )
    actual_sum = _sha256_of(authority_path)
    if str(authority.get("checksum") or "").strip() != actual_sum:
        reasons.append(
            f"{label} records a stale checksum for its authority {authority_id}; it now "
            f"hashes to {actual_sum}"
        )
    if authority.get("authorized_acceptance_test_index") != index:
        reasons.append(
            f"{label} records an authority for acceptance test "
            f"{authority.get('authorized_acceptance_test_index')!r}, not {index!r}"
        )

    if not isinstance(index, int):
        reasons.append(f"{label} has a non-integer acceptance_test_index")
        return reasons

    authorization, why = _authorized_retirement(
        decision_id, input_checksum, index, authority_id, authority_doc
    )
    if authorization is None:
        reasons.append(f"{label}: {why}")
        return reasons

    # Condition 3: complete coverage. A partial account would retire a test on
    # the strength of whichever subject happened to be convenient.
    authorized = {
        str(s.get("id") or ""): s
        for s in authorization.get("subjects") or []
        if isinstance(s, dict)
    }
    recorded = {
        str(s.get("id") or ""): s
        for s in result.get("retired_subjects") or []
        if isinstance(s, dict)
    }
    for missing in sorted(set(authorized) - set(recorded)):
        reasons.append(
            f"{label} omits the authorized subject {missing}; partial coverage does not "
            f"retire an acceptance test"
        )
    for extra in sorted(set(recorded) - set(authorized)):
        reasons.append(f"{label} records {extra}, which its authority does not name")

    for subject_id in sorted(set(authorized) & set(recorded)):
        allowed = authorized[subject_id]
        claimed = recorded[subject_id]
        state = str(claimed.get("retirement_state") or "").strip()
        if state not in RETIREMENT_STATES:
            reasons.append(
                f"{label} records retirement state {state!r} for {subject_id}, which is "
                f"not an ordinary integrated completion"
            )
            continue
        permitted = str(allowed.get("permitted_retirement_state") or "").strip()
        if permitted and state != permitted:
            reasons.append(
                f"{label} records {subject_id} as {state}, but its authority permits "
                f"only {permitted}"
            )
            continue

        if state == "superseded_by_integrated_revision":
            successor = str(claimed.get("integrated_successor_id") or "").strip()
            expected = str(allowed.get("integrated_successor_id") or "").strip()
            if not successor:
                reasons.append(
                    f"{label} supersedes {subject_id} but names no integrated successor; a "
                    f"merely superseded artifact is not retired"
                )
                continue
            if expected and successor != expected:
                reasons.append(
                    f"{label} names successor {successor} for {subject_id}, but its "
                    f"authority names {expected}"
                )
                continue

        record_path = str(claimed.get("integration_record_path") or "").strip()
        expected_record = str(allowed.get("integration_record_path") or "").strip()
        if expected_record and record_path != expected_record:
            reasons.append(
                f"{label} cites integration record {record_path!r} for {subject_id}, but "
                f"its authority cites {expected_record!r}"
            )
            continue
        candidate = root / record_path
        if not record_path or not candidate.is_file():
            reasons.append(
                f"{label} cites integration record {record_path!r} for {subject_id}, which "
                f"does not exist"
            )
            continue
        if str(claimed.get("integration_record_checksum") or "").strip() != _sha256_of(
            candidate
        ):
            reasons.append(
                f"{label} records a stale integration-record checksum for {subject_id}"
            )

    return reasons


def _decision_reissue_leaves(
    root: Path,
    ruleset: str,
    decisions: dict[str, tuple[Path, dict[str, Any]]],
    decisions_by_ruleset: dict[str, dict[str, tuple[Path, dict[str, Any]]]],
    diagnostics: list,
) -> set[str]:
    """WORK_QUEUES 1.7: only the leaf of a valid Decision reissue creates work.

    Architect Decisions are immutable, so a Decision whose executable
    instructions need correcting is replaced by a new one that names it in
    `supersedes` rather than being rewritten. Both files stay on disk, so
    without this the predecessor keeps producing a ready Builder job beside its
    own replacement -- which is what DEC-2026-0030 and DEC-2026-0031 did.

    Returns the IDs a *valid* reissue supersedes. An invalid reissue is reported
    and suppresses nothing: the contract is explicit that a lineage error leaves
    both Decisions' otherwise-ready work visible, so a malformed correction can
    never quietly cancel the job it was meant to fix.
    """
    successors: dict[str, list[str]] = defaultdict(list)
    for decision_id in sorted(decisions):
        predecessor = str(decisions[decision_id][1].get("supersedes") or "").strip()
        if predecessor:
            successors[predecessor].append(decision_id)

    superseded: set[str] = set()
    for decision_id in sorted(decisions):
        path, document = decisions[decision_id]
        predecessor = str(document.get("supersedes") or "").strip()
        if not predecessor:
            continue

        reasons: list[str] = []
        entry = decisions.get(predecessor)
        if entry is None:
            # Only this ruleset's approved Decisions are in `decisions`, so a
            # miss is either a cross-ruleset reference or an absent/unapproved
            # predecessor. Saying which one saves the reader the lookup.
            elsewhere = next(
                (
                    other
                    for other, table in sorted(decisions_by_ruleset.items())
                    if other != ruleset and predecessor in table
                ),
                None,
            )
            if elsewhere is not None:
                reasons.append(
                    f"supersedes {predecessor}, which belongs to ruleset {elsewhere!r}; "
                    f"a Decision reissue lineage does not cross rulesets"
                )
            else:
                reasons.append(
                    f"supersedes {predecessor}, which is not an approved Decision of "
                    f"ruleset {ruleset!r}"
                )
        else:
            prior = entry[1]
            if prior.get("migration_required") != document.get("migration_required"):
                reasons.append(
                    f"declares migration_required={document.get('migration_required')!r} "
                    f"but {predecessor} declares {prior.get('migration_required')!r}; a "
                    f"reissue preserves the predecessor's migration flag"
                )
            revision = document.get("revision")
            prior_revision = prior.get("revision")
            if (
                isinstance(revision, int)
                and isinstance(prior_revision, int)
                and revision <= prior_revision
            ):
                reasons.append(
                    f"is revision {revision}, which is not later than {predecessor} at "
                    f"revision {prior_revision}"
                )
            branches = successors.get(predecessor) or []
            if len(branches) > 1:
                reasons.append(
                    f"{predecessor} is superseded by {', '.join(branches)}; a Decision "
                    f"lineage has at most one direct successor"
                )

        if reasons:
            _diag(
                diagnostics,
                "error",
                "decision_reissue_lineage_error",
                f"{decision_id} " + "; ".join(reasons) + ".",
                path=_relative(root, path),
                artifact_id=decision_id,
            )
            continue
        superseded.add(predecessor)
    return superseded


def _implementation_report_errors(
    root: Path,
    artifact: Artifact,
    decisions: dict[str, tuple[Path, dict[str, Any]]],
) -> list[str]:
    """Every mandatory condition of WORK_QUEUES 1.4 "Builder report".

    An empty list means the report may carry its Decision to Reviewer. Anything
    else is a diagnostic: the report neither routes to Reviewer nor consumes the
    Decision, so the Decision stays visible as Builder work rather than being
    silently retired by a report that does not hold up.
    """
    reasons: list[str] = []
    data = artifact.data

    if str(data.get("artifact_kind") or "") != DECISION_IMPLEMENTATION:
        reasons.append(
            f"declares artifact_kind {data.get('artifact_kind')!r} rather than "
            f"{DECISION_IMPLEMENTATION}"
        )
        return reasons

    decision_input = data.get("decision_input")
    if not isinstance(decision_input, dict):
        reasons.append("has no decision_input block")
        return reasons

    decision_id = str(decision_input.get("id") or "").strip()
    if not decision_id:
        reasons.append("names no Decision in decision_input.id")
        return reasons

    entry = decisions.get(decision_id)
    if entry is None:
        reasons.append(f"names {decision_id}, which is not an approved Decision of this ruleset")
        return reasons
    decision_path, decision_doc = entry

    # 3: exact ID, repository path and current checksum.
    declared_path = str(decision_input.get("path") or "").strip()
    actual_path = _relative(root, decision_path)
    if declared_path != actual_path:
        reasons.append(
            f"records decision path {declared_path!r} but the Decision is at {actual_path!r}"
        )
    declared_sum = str(decision_input.get("checksum") or "").strip()
    actual_sum = _sha256_of(decision_path)
    if declared_sum != actual_sum:
        reasons.append(
            f"records a stale decision checksum; {decision_id} now hashes to {actual_sum}"
        )

    # 2: the Decision must actually be a non-migration Builder assignment.
    handoff = decision_doc.get("handoff")
    handoff = handoff if isinstance(handoff, dict) else {}
    if str(decision_doc.get("ruleset_id") or "") != artifact.ruleset:
        reasons.append(f"{decision_id} belongs to another ruleset")
    if str(handoff.get("next_role") or "") != "builder":
        reasons.append(f"{decision_id} does not hand off to Builder")
    if str(handoff.get("readiness") or "") != "ready":
        reasons.append(f"{decision_id} has no ready Builder handoff")
    if decision_doc.get("migration_required") is not False:
        reasons.append(f"{decision_id} is not a non-migration Decision")

    acceptance = decision_doc.get("acceptance_tests")
    if not isinstance(acceptance, list) or not acceptance:
        reasons.append(f"{decision_id} declares no acceptance_tests")
        acceptance = []

    # 4: every implementation file exists and hashes to what is recorded.
    files = data.get("implementation_files")
    if not isinstance(files, list) or not files:
        reasons.append("has an empty or missing implementation_files list")
        files = []
    for item in files:
        if not isinstance(item, dict):
            reasons.append("has an implementation_files entry that is not a mapping")
            continue
        relative = str(item.get("path") or "").strip()
        candidate = root / relative
        if not relative or not candidate.is_file():
            reasons.append(f"names implementation file {relative!r}, which does not exist")
            continue
        if str(item.get("checksum") or "").strip() != _sha256_of(candidate):
            reasons.append(f"records a stale checksum for {relative}")

    # 5: every acceptance test accounted for exactly once, by one-based index.
    results = data.get("acceptance_results")
    if not isinstance(results, list) or not results:
        reasons.append("has an empty or missing acceptance_results list")
        results = []
    indexes = [
        r.get("acceptance_test_index") for r in results if isinstance(r, dict)
    ]
    expected = set(range(1, len(acceptance) + 1))
    seen: set[int] = set()
    for value in indexes:
        if not isinstance(value, int):
            reasons.append(f"has a non-integer acceptance_test_index {value!r}")
            continue
        if value in seen:
            reasons.append(f"repeats acceptance_test_index {value}")
        if acceptance and value not in expected:
            reasons.append(
                f"records acceptance_test_index {value}, outside 1..{len(acceptance)}"
            )
        seen.add(value)
    missing = sorted(expected - seen)
    if missing:
        reasons.append(
            f"omits acceptance_test_index {', '.join(str(m) for m in missing)}; a partial "
            f"account is not Reviewer-ready"
        )

    # WORK_QUEUES 1.6: a retired result carries evidence of its own, and it is
    # checked whether or not the report claims to be approval-ready. A blocked
    # report with an unsound retirement should say so now, not the revision
    # after someone tries to approve it.
    for result in results:
        if not isinstance(result, dict):
            continue
        if str(result.get("result") or "") != "retired_by_lineage":
            continue
        reasons.extend(
            _retired_result_errors(root, decision_id, actual_sum, result, decisions)
        )

    # 6: approval_ready is a claim about every result, not a mood.
    if data.get("approval_ready") is True:
        failed = [
            r.get("acceptance_test_index")
            for r in results
            if isinstance(r, dict)
            and str(r.get("result") or "") not in ("passed", "retired_by_lineage")
        ]
        if failed:
            reasons.append(
                "is approval_ready but acceptance results "
                + ", ".join(str(f) for f in failed)
                + " neither passed nor validly retired by lineage"
            )
        validation = data.get("validation")
        validation = validation if isinstance(validation, dict) else {}
        if validation.get("passed") is not True:
            reasons.append("is approval_ready but its validation did not pass")
        if not validation.get("commands"):
            reasons.append("is approval_ready but records no validation commands")
        report_handoff = data.get("handoff")
        report_handoff = report_handoff if isinstance(report_handoff, dict) else {}
        if str(report_handoff.get("next_role") or "") != "reviewer":
            reasons.append("is approval_ready but does not hand off to Reviewer")
        if str(report_handoff.get("readiness") or "") != "ready":
            reasons.append("is approval_ready but its Reviewer handoff is not ready")
        if report_handoff.get("blocking_ids"):
            reasons.append("is approval_ready but names blocking IDs")

    # 8: one unforked lineage per Decision.
    revision = data.get("revision")
    if isinstance(revision, int) and revision >= 2 and not data.get("supersedes"):
        reasons.append(f"is revision {revision} but names no supersedes")

    return reasons


def _implementation_review_errors(
    root: Path,
    review: Artifact,
    report: Artifact,
    decisions: dict[str, tuple[Path, dict[str, Any]]],
) -> list[str]:
    """Every provenance condition WORK_QUEUES 1.4 puts on an implementation Review.

    Validating the report but not the Review left the consuming half of the
    lineage unguarded: any schema-shaped approved Review grouped by report ID
    retired its Decision, even with a checksum of all zeroes. The Review is what
    completes a Decision, so its provenance has to be checked at least as hard as
    the report's.

    Provenance is checked for every Review. The stricter conditions -- every
    index verified, independent validation passed, terminal handoff -- apply to
    an `approved` Review, because those are what the section requires before
    consumption.
    """
    reasons: list[str] = []
    data = review.data

    if str(data.get("artifact_kind") or "") != DECISION_IMPLEMENTATION_REVIEW:
        reasons.append(
            f"declares artifact_kind {data.get('artifact_kind')!r} rather than "
            f"{DECISION_IMPLEMENTATION_REVIEW}"
        )
        return reasons

    disposition = str(data.get("overall_disposition") or data.get("status") or "").strip()
    if disposition not in ("approved", "revision_required"):
        reasons.append(f"has an unrecognised overall_disposition {disposition!r}")

    # The Review must name the exact report leaf it reviewed.
    reviewed = data.get("reviewed_implementation")
    if not isinstance(reviewed, dict):
        reasons.append("has no reviewed_implementation block")
        return reasons
    report_path = _relative(root, report.path)
    if str(reviewed.get("id") or "") != report.artifact_id:
        reasons.append(
            f"names implementation report {reviewed.get('id')!r} rather than the active "
            f"leaf {report.artifact_id}"
        )
    if str(reviewed.get("path") or "") != report_path:
        reasons.append(
            f"records report path {reviewed.get('path')!r} but the report is at {report_path!r}"
        )
    actual_report_sum = _sha256_of(report.path)
    if str(reviewed.get("checksum") or "") != actual_report_sum:
        reasons.append(
            f"records a stale report checksum; {report.artifact_id} now hashes to "
            f"{actual_report_sum}"
        )

    # It must repeat the same Decision provenance the report carries.
    review_decision = data.get("decision_input")
    report_decision = report.data.get("decision_input")
    if not isinstance(review_decision, dict):
        reasons.append("has no decision_input block")
        return reasons
    if not isinstance(report_decision, dict):
        report_decision = {}
    decision_id = str(review_decision.get("id") or "")
    if decision_id != str(report_decision.get("id") or ""):
        reasons.append(
            f"names Decision {decision_id!r} but the report implements "
            f"{report_decision.get('id')!r}"
        )
    entry = decisions.get(decision_id)
    if entry is None:
        reasons.append(f"names {decision_id!r}, which is not an approved Decision of this ruleset")
    else:
        decision_path, _ = entry
        actual_path = _relative(root, decision_path)
        if str(review_decision.get("path") or "") != actual_path:
            reasons.append(
                f"records decision path {review_decision.get('path')!r} but the Decision is "
                f"at {actual_path!r}"
            )
        actual_sum = _sha256_of(decision_path)
        if str(review_decision.get("checksum") or "") != actual_sum:
            reasons.append(
                f"records a stale decision checksum; {decision_id} now hashes to {actual_sum}"
            )

    if disposition != "approved":
        return reasons

    # Consumption conditions.
    acceptance = []
    if entry is not None:
        acceptance = entry[1].get("acceptance_tests") or []
    dispositions = data.get("acceptance_dispositions")
    if not isinstance(dispositions, list) or not dispositions:
        reasons.append("is approved but has no acceptance_dispositions")
        dispositions = []
    # WORK_QUEUES 1.6: the two dispositions are not interchangeable. A retired
    # result must be met with `verified_retired_by_lineage`, which obliges the
    # Reviewer to re-derive the authority and Integration evidence; letting a
    # plain `verified` approve it would make the independent check optional.
    # The converse matters too: the retired disposition on an ordinary result
    # would approve a retirement nobody claimed.
    report_results = {
        r.get("acceptance_test_index"): str(r.get("result") or "")
        for r in report.data.get("acceptance_results") or []
        if isinstance(r, dict)
    }
    report_checksum = str(report_decision.get("checksum") or "").strip()

    seen: set[int] = set()
    for item in dispositions:
        if not isinstance(item, dict):
            continue
        index = item.get("acceptance_test_index")
        if isinstance(index, int):
            if index in seen:
                reasons.append(f"repeats acceptance_test_index {index}")
            seen.add(index)
        disposition_value = str(item.get("disposition") or "")
        reported = report_results.get(index, "")
        if disposition_value == "verified_retired_by_lineage":
            if reported != "retired_by_lineage":
                reasons.append(
                    f"disposes acceptance_test_index {index} as verified_retired_by_lineage, "
                    f"but the report records it as {reported!r}"
                )
                continue
            mirrored = {
                "acceptance_test_index": index,
                "retirement_authority": item.get("verified_retirement_authority"),
                "retired_subjects": item.get("verified_retired_subjects"),
            }
            reasons.extend(
                f"independent verification: {reason}"
                for reason in _retired_result_errors(
                    root, decision_id, report_checksum, mirrored, decisions
                )
            )
        elif disposition_value == "verified":
            if reported == "retired_by_lineage":
                reasons.append(
                    f"is approved but disposes the retired acceptance_test_index {index} as "
                    f"plain verified; a retired result needs verified_retired_by_lineage"
                )
        else:
            reasons.append(
                f"is approved but acceptance_test_index {index} is "
                f"{item.get('disposition')!r} rather than verified"
            )
    missing = sorted(set(range(1, len(acceptance) + 1)) - seen)
    if missing:
        reasons.append(
            "is approved but does not dispose acceptance_test_index "
            + ", ".join(str(m) for m in missing)
        )

    validation = data.get("independent_validation")
    validation = validation if isinstance(validation, dict) else {}
    if validation.get("passed") is not True:
        reasons.append("is approved but its independent validation did not pass")
    if not validation.get("commands"):
        reasons.append("is approved but records no independent validation commands")

    handoff = data.get("handoff")
    handoff = handoff if isinstance(handoff, dict) else {}
    if str(handoff.get("readiness") or "") != "terminal":
        reasons.append("is approved but its handoff is not terminal")
    if handoff.get("blocking_ids"):
        reasons.append("is approved but names blocking IDs")

    return reasons


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def _review_revision_roles(document: dict[str, Any]) -> list[str]:
    """Roles a `revision_required` Review actually gives work to, in order.

    `handoff.next_role` names one role, but a Review routinely gives work to
    two: an exact correction for the Builder to apply, alongside a completeness
    finding only the Analyst can answer. Reading either signal alone gets one of
    the two cases wrong.

    Builder work is a row-level `exact_corrections`, or a `required_gup_revisions`
    entry that names no other role -- an unqualified revision request is the
    Builder's by default, since the Builder emits the GUP. Where a Review carries
    none of those, there is nothing for the Builder to apply, and compiling a
    fresh leaf from the same GUR would either restate the patch byte for byte or
    require inventing the assertions the Review says are missing.
    """
    roles: list[str] = []

    builder_actionable = any(
        row.get("exact_corrections")
        for row in document.get("row_decisions") or []
        if isinstance(row, dict)
    ) or any(
        str(entry.get("next_role") or "").strip().lower() in ("", "builder")
        for entry in document.get("required_gup_revisions") or []
        if isinstance(entry, dict)
    )
    if builder_actionable:
        roles.append("builder")

    handoff_role = _handoff_role(document)
    if handoff_role and handoff_role != "none" and handoff_role not in roles:
        roles.append(handoff_role)
    return roles


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
    #: Decided escalation packages by ID. WORK_QUEUES 1.3 resolves a Decision's
    #: originating artifacts through the package it decided, so the whole
    #: document is needed and not merely the fact that the ID is decided.
    decided_packages_by_ruleset: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    #: Approved Decisions by ruleset and ID, with the path they were read from so
    #: a decision migration's recorded checksum can be re-verified against it.
    decisions_by_ruleset: dict[str, dict[str, tuple[Path, dict[str, Any]]]] = defaultdict(dict)
    #: Decision migrations found anywhere: book GUP stores and ruleset-scoped
    #: cross-book stores alike. Scope location does not change the lineage checks.
    migrations_by_ruleset: dict[str, list[Artifact]] = defaultdict(list)
    reviewed_gup_ids_global: set[str] = set()
    #: The same Reviews, keyed by the GUP they reviewed. A migration is
    #: cross-book, so its Review may sit in any book's store and the per-book
    #: index cannot see it.
    reviews_by_gup_global: dict[str, list[Artifact]] = defaultdict(list)
    rulesets_root = root / "rulesets"
    if rulesets_root.is_dir():
        for ruleset_dir in sorted(path for path in rulesets_root.iterdir() if path.is_dir()):
            ruleset = ruleset_dir.name
            decided_dir = ruleset_dir / "escalations" / "decided"
            if decided_dir.is_dir():
                for path in decided_dir.glob("ESC-*.yaml"):
                    document = _load_yaml(root, path, diagnostics)
                    if document:
                        escalation_id = str(document.get("id") or path.stem)
                        decided_by_ruleset[ruleset].add(escalation_id)
                        # WORK_QUEUES 1.3 reads `originating_artifacts` off the
                        # decided package, so the document is kept, not just its ID.
                        decided_packages_by_ruleset[ruleset][escalation_id] = document
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
                    reviews_by_gup_global[str(reviewed_id)].append(artifact)
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
                        # WORK_QUEUES: `blocked` means "the named role cannot
                        # act until every blocking_id is resolved". The named
                        # role is the one in the artifact's own handoff, not the
                        # one that produced it. Attributing every blocked GUP to
                        # Builder filed a patch the Builder is forbidden to fix
                        # -- an Analyst revision it may not perform itself,
                        # because that would be reinterpreting source -- as
                        # Builder work, where it would have waited forever.
                        owner = _handoff_role(leaf_gup.data)
                        role = owner.capitalize() if owner in ROLE_BY_NAME else "Builder"
                        blocked.append(
                            _queue_item(
                                state="blocked",
                                queue=f"{role.upper()}-BLOCKED-GUP" if role != "Builder"
                                else "BUILDER-BLOCKED",
                                role=role,
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
                        # WORK_QUEUES makes a Builder job "a Review that requests
                        # Builder revision", and `handoff.next_role` is where a
                        # Review says whose revision it wants. Routing every
                        # revision_required Review to Builder regardless sends
                        # back work no Builder may perform: where the finding is
                        # that the GUR omits source assertions, the only Builder
                        # response is to reinterpret source, which the role
                        # forbids, or to publish a byte-identical no-op leaf.
                        roles = _review_revision_roles(review_leaf.data)
                        # A Review with neither a handoff block nor any
                        # actionable finding is legacy. The contract keeps those
                        # valid under the legacy rules, which is the historical
                        # Builder routing, reported as an inference.
                        inferred = review_inferred or not roles
                        if not roles:
                            roles = ["builder"]
                            _diag(
                                diagnostics,
                                "warning",
                                "review_handoff_inferred",
                                f"{review_leaf.artifact_id} requires revision but names "
                                f"no handoff role and no actionable finding; routed to "
                                f"Builder under the legacy rule.",
                                path=_relative(root, review_leaf.path),
                                artifact_id=review_leaf.artifact_id,
                            )
                        for role in roles:
                            ready.append(
                                _queue_item(
                                    state="ready",
                                    queue=f"{role.upper()}-REVISION",
                                    role=role.capitalize(),
                                    ruleset=ruleset,
                                    book=book,
                                    packet_id=packet_id,
                                    input_id=review_leaf.artifact_id,
                                    reason=(
                                        f"Active Review requires "
                                        f"{_article(role)} {role.capitalize()} revision."
                                    ),
                                    path=_relative(root, review_leaf.path),
                                    components=[_relative(root, review_leaf.path)],
                                    legacy_inference=inferred,
                                )
                            )
                    elif (
                        disposition == "architect_escalation"
                        and review_blockers
                        and not review_unresolved
                    ):
                        # A decided escalation does not by itself make the
                        # Builder next. The resolving Decision may order another
                        # role ahead of the rebuild, and where it does, calling
                        # this ready sends the Builder to compile against state
                        # that is not there yet.
                        prerequisites = _sequenced_prerequisites(
                            review_leaf.artifact_id,
                            review_blockers,
                            decisions_by_ruleset[ruleset],
                            artifacts_root,
                        )
                        if prerequisites:
                            blocked.append(
                                _queue_item(
                                    state="blocked",
                                    queue="BUILDER-REVISION-BLOCKED",
                                    role="Builder",
                                    ruleset=ruleset,
                                    book=book,
                                    packet_id=packet_id,
                                    input_id=review_leaf.artifact_id,
                                    reason=(
                                        "Review escalations are decided, but the deciding "
                                        "Decision orders another artifact first: "
                                        + "; ".join(prerequisites)
                                    ),
                                    path=_relative(root, review_leaf.path),
                                    components=[_relative(root, review_leaf.path)],
                                    legacy_inference=review_inferred,
                                )
                            )
                        else:
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
            # WORK_QUEUES 3 and 6: only the active leaf creates work, and a
            # superseded artifact is not ready work. A bundle inherits that from
            # the GUP it packages. The Integrator rejected
            # APPROVED-GUP-PKT-PHB-119-119-alignment-graph-r02-r01 and the
            # Builder published r03, and the rejected bundle still came back as
            # ready -- offering a batch that had already been refused, and whose
            # own report said applying it would register two nodes at degree 0.
            superseded_gup_ids = {
                str(artifact.data.get("supersedes"))
                for artifact in gups
                if artifact.data.get("supersedes")
            }
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

                packaged_gup = _packaged_gup_id(manifest, review)
                if packaged_gup and packaged_gup in superseded_gup_ids:
                    informational.append(
                        _queue_item(
                            state="informational",
                            queue="INTEGRATOR-SUPERSEDED",
                            role="Integrator",
                            ruleset=ruleset,
                            book=book,
                            packet_id=str(packet_id or review.packet_id or "") or None,
                            input_id=approved_id,
                            reason=(
                                f"Approved bundle packages {packaged_gup}, which a later "
                                f"revision supersedes. Only the active leaf creates work "
                                f"(WORK_QUEUES 3, 6). The bundle is unchanged and remains "
                                f"available as history."
                            ),
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
            # WORK_QUEUES 1.7. Computed once: both the migration and the
            # non-migration Decision loops below derive work from the leaf only.
            reissued_decision_ids = _decision_reissue_leaves(
                root, ruleset, decisions, decisions_by_ruleset, diagnostics
            )

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

            # Collect all integrated APPROVED bundle IDs for this ruleset
            # to check if a decision migration lineage has been integrated
            integrated_approved_for_ruleset = _integrated_approved_ids(
                root, ruleset, rulesets_root / ruleset, diagnostics
            )

            consumed_decision_ids: set[str] = set()
            for lineage_id in sorted(by_lineage):
                group = by_lineage[lineage_id]
                leaf, inferred = _active_leaf(
                    root, group, diagnostics, f"{ruleset} decision migration {lineage_id}"
                )
                if leaf is None:
                    continue

                # Check if ANY artifact in this lineage group has been integrated
                # by checking if there's an integrated APPROVED bundle that
                # corresponds to it. APPROVED bundle IDs are of the form:
                # APPROVED-<gup-id>-r<review-revision>
                # We check if any integrated APPROVED ID contains the GUP artifact ID
                lineage_integrated = False
                for artifact in group:
                    gup_id = artifact.artifact_id
                    # Check if any integrated APPROVED bundle corresponds to this GUP
                    for approved_id in integrated_approved_for_ruleset:
                        if approved_id.startswith(f"APPROVED-{gup_id}-r") or approved_id == f"APPROVED-{gup_id}":
                            lineage_integrated = True
                            break
                    if lineage_integrated:
                        break

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
                    # A lineage error says the leaf cannot go to Reviewer as it
                    # stands. It does not say who fixes it. Where a Review has
                    # already ruled on this leaf and named the role that acts
                    # next, that ruling governs -- exactly as it does for a
                    # packet GUP. Discarding it here republished the authority
                    # Decisions as ready Builder work while the Review that
                    # decided them was still asking the Analyst for the
                    # prerequisite, and hid the Analyst's job entirely.
                    review_leaf, _ = _active_leaf(
                        root,
                        reviews_by_gup_global.get(leaf.artifact_id, []),
                        diagnostics,
                        f"{ruleset} decision migration {lineage_id} review",
                    )
                    review_disposition = str(
                        review_leaf.data.get("overall_disposition")
                        or review_leaf.data.get("status")
                        or ""
                    ) if review_leaf else ""
                    roles = (
                        _review_revision_roles(review_leaf.data)
                        if review_leaf and review_disposition == "revision_required"
                        else []
                    )
                    if roles:
                        # The Review is answering for these Decisions, so they
                        # are spoken for and must not resurface as ready work.
                        consumed_decision_ids.update(
                            str(a) for a in leaf.data.get("authority") or []
                        )
                        for role in roles:
                            ready.append(
                                _queue_item(
                                    state="ready",
                                    queue=f"{role.upper()}-DECISION-MIGRATION-REVISION",
                                    role=role.capitalize(),
                                    ruleset=ruleset,
                                    book=leaf.book,
                                    packet_id=leaf.packet_id,
                                    input_id=review_leaf.artifact_id,
                                    reason=(
                                        f"Active Review on {leaf.artifact_id} requires "
                                        f"{_article(role)} {role.capitalize()} revision."
                                    ),
                                    path=_relative(root, review_leaf.path),
                                    components=[_relative(root, review_leaf.path)],
                                    legacy_inference=inferred,
                                )
                            )
                        continue

                    # If this lineage has been integrated (even if the leaf has errors),
                    # its authority Decisions are consumed
                    if lineage_integrated:
                        for artifact in group:
                            consumed_decision_ids.update(
                                str(a) for a in artifact.data.get("authority") or []
                            )

                    # Otherwise it does not consume its authority Decisions, so
                    # their Builder jobs stay visible.
                    continue

                # If lineage is integrated, add all authority Decisions from all artifacts
                if lineage_integrated:
                    for artifact in group:
                        consumed_decision_ids.update(
                            str(a) for a in artifact.data.get("authority") or []
                        )
                else:
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
                if decision_id in reissued_decision_ids:
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

            # -- WORK_QUEUES 1.4: non-migration Decision implementations -------
            # A non-migration Decision changes schemas, docs, tests or tooling
            # and produces no GUP, so nothing in the graph lineage can retire it.
            # Its completion lineage is one Builder report plus one independent
            # Review, and only the Approved Review consumes the Decision.
            reports = _load_artifacts(
                root,
                ruleset_dir / "decision-implementations",
                "decision-implementation",
                ruleset,
                None,
                diagnostics,
            )
            impl_reviews = _load_artifacts(
                root,
                ruleset_dir / "decision-implementation-reviews",
                "decision-implementation-review",
                ruleset,
                None,
                diagnostics,
            )

            reports_by_decision: dict[str, list[Artifact]] = defaultdict(list)
            for artifact in reports:
                block = artifact.data.get("decision_input")
                target = (
                    str(block.get("id") or "") if isinstance(block, dict) else ""
                )
                if target:
                    reports_by_decision[target].append(artifact)

            reviews_by_report: dict[str, list[Artifact]] = defaultdict(list)
            for artifact in impl_reviews:
                block = artifact.data.get("reviewed_implementation")
                target = (
                    str(block.get("id") or "") if isinstance(block, dict) else ""
                )
                if target:
                    reviews_by_report[target].append(artifact)

            for decision_id in sorted(decisions):
                path, document = decisions[decision_id]
                handoff = document.get("handoff")
                if not isinstance(handoff, dict):
                    continue
                if str(handoff.get("next_role") or "") != "builder":
                    continue
                if str(handoff.get("readiness") or "") != "ready":
                    continue
                if document.get("migration_required") is not False:
                    continue
                if decision_id in reissued_decision_ids:
                    continue

                group = reports_by_decision.get(decision_id) or []
                leaf, report_inferred = _active_leaf(
                    root, group, diagnostics, f"{ruleset} implementation {decision_id}"
                )

                report_errors: list[str] = []
                if leaf is not None:
                    report_errors = _implementation_report_errors(root, leaf, decisions)
                    if report_errors:
                        _diag(
                            diagnostics,
                            "error",
                            "decision_implementation_invalid",
                            f"{leaf.artifact_id} " + "; ".join(report_errors) + ".",
                            path=_relative(root, leaf.path),
                            artifact_id=leaf.artifact_id,
                        )

                review_leaf = None
                if leaf is not None and not report_errors:
                    review_leaf, _ = _active_leaf(
                        root,
                        reviews_by_report.get(leaf.artifact_id) or [],
                        diagnostics,
                        f"{ruleset} implementation review {leaf.artifact_id}",
                    )

                if review_leaf is not None:
                    review_errors = _implementation_review_errors(
                        root, review_leaf, leaf, decisions
                    )
                    if review_errors:
                        # An unsound Review neither consumes the Decision nor
                        # hides the report that is still waiting for a sound one.
                        _diag(
                            diagnostics,
                            "error",
                            "decision_implementation_review_invalid",
                            f"{review_leaf.artifact_id} "
                            + "; ".join(review_errors)
                            + ".",
                            path=_relative(root, review_leaf.path),
                            artifact_id=review_leaf.artifact_id,
                        )
                        review_leaf = None

                if review_leaf is not None:
                    disposition = str(
                        review_leaf.data.get("overall_disposition")
                        or review_leaf.data.get("status")
                        or ""
                    )
                    if disposition == "approved":
                        # The Decision is complete. No Integrator job exists for
                        # this lineage: no canonical or registry state changed.
                        continue
                    ready.append(
                        _queue_item(
                            state="ready",
                            queue="BUILDER-DECISION-IMPLEMENTATION-REVISION",
                            role="Builder",
                            ruleset=ruleset,
                            book=str(document.get("book_id") or "") or None,
                            packet_id=str(document.get("packet_id") or "") or None,
                            input_id=review_leaf.artifact_id,
                            reason=(
                                f"Implementation Review requires a Builder revision of "
                                f"{decision_id}."
                            ),
                            path=_relative(root, review_leaf.path),
                            components=[_relative(root, review_leaf.path)],
                        )
                    )
                    # The revision job replaces the Decision job rather than
                    # standing alongside it.
                    continue

                if leaf is not None and not report_errors and leaf.data.get("approval_ready") is True:
                    ready.append(
                        _queue_item(
                            state="ready",
                            queue="REVIEWER-DECISION-IMPLEMENTATION",
                            role="Reviewer",
                            ruleset=ruleset,
                            book=str(document.get("book_id") or "") or None,
                            packet_id=str(document.get("packet_id") or "") or None,
                            input_id=leaf.artifact_id,
                            reason=(
                                f"Approval-ready implementation report for {decision_id} "
                                f"has no independent Review."
                            ),
                            path=_relative(root, leaf.path),
                            components=[_relative(root, leaf.path)],
                            legacy_inference=report_inferred,
                        )
                    )
                    continue

                # No report, an invalid one, or one still marked partial: the
                # Decision remains Builder work.
                ready.append(
                    _queue_item(
                        state="ready",
                        queue="BUILDER-DECISION",
                        role="Builder",
                        ruleset=ruleset,
                        book=str(document.get("book_id") or "") or None,
                        packet_id=str(document.get("packet_id") or "") or None,
                        input_id=decision_id,
                        reason=(
                            "Approved non-migration Decision has no approval-ready "
                            "implementation report."
                        ),
                        path=_relative(root, path),
                        components=[_relative(root, path)],
                    )
                )

    # -- WORK_QUEUES 1.3: Decision handoff replacement -------------------------
    # An immutable artifact preserves the evidence a Review was built on, but it
    # cannot represent a ruling made after it was written. Where an approved
    # Decision resolved the escalation that artifact raised, the Decision's
    # handoff is the current one and the artifact's earlier ready item is stale
    # work. The artifact itself is untouched; only queue derivation changes.
    for ruleset in sorted(decisions_by_ruleset):
        for replacement in _handoff_replacements(
            root,
            ruleset,
            decisions_by_ruleset[ruleset],
            decided_packages_by_ruleset[ruleset],
        ):
            handoff = replacement["handoff"]
            readiness = str(handoff.get("readiness") or "").strip().lower()
            role = str(handoff.get("next_role") or "").strip().lower()
            document = replacement["document"]
            decision_id = replacement["decision_id"]

            suppressed = False
            for artifact_id, artifact_path in replacement["refs"]:
                if artifact_id in decisions_by_ruleset[ruleset]:
                    # A Decision is authored governance, not a queue artifact
                    # whose handoff was derived from the escalation it raised,
                    # and only the Architect supersedes one. Escalation packages
                    # routinely name Decisions as context -- the package behind
                    # DEC-2026-0023 lists the three Decisions the question was
                    # about, and the one behind DEC-2026-0021 names DEC-2026-0019
                    # the same way. Reading that as replacement would retire
                    # Builder work the replacing Decision expressly reaffirms.
                    continue
                # Condition 3: only an item the scan derived for this exact ID
                # and path is replaced. A Decision naming a superseded artifact
                # matches nothing, so the active leaf keeps its own handoff.
                remaining = [
                    item
                    for item in ready
                    if not (
                        item["InputId"] == artifact_id and item["Path"] == artifact_path
                    )
                ]
                if len(remaining) != len(ready):
                    suppressed = True
                    ready[:] = remaining
                    _diag(
                        diagnostics,
                        "info",
                        "handoff_replaced_by_decision",
                        f"{decision_id} resolved the escalation {artifact_id} raised, so "
                        f"its ready handoff is superseded for queue derivation. The "
                        f"artifact is unchanged and remains available as history.",
                        path=artifact_path,
                        artifact_id=artifact_id,
                    )

            # A migration-required Decision with a ready Builder handoff already
            # gets its Builder item from the decision-migration consumption rule
            # above, so emitting one here would double-count it. That is a reason
            # to skip the *emission* only. Skipping the suppression loop as well
            # left DEC-2026-0021 unable to replace the stale Analyst handoff on
            # REV-GUP-MIG-DEC-2026-0015-0016-r03-r01, which is precisely the case
            # DEC-2026-0022 names -- so this guard sits after the suppression.
            if (document.get("migration_required") is True and
                    role == "builder" and readiness == "ready"):
                continue

            if not suppressed or role in ("", "none") or readiness == "terminal":
                continue

            # Skip if this Decision has already been consumed by an integrated
            # decision-migration GUP
            if decision_id in consumed_decision_ids:
                continue

            already_ready = any(
                item["InputId"] == decision_id and item["Role"] == role.capitalize()
                for item in ready
            )
            if already_ready:
                # One Decision is one logical coordination job.
                continue

            item = _queue_item(
                state="blocked" if readiness == "blocked" else "ready",
                queue=f"{role.upper()}-DECISION",
                role=role.capitalize(),
                ruleset=ruleset,
                book=str(document.get("book_id") or "") or None,
                packet_id=str(document.get("packet_id") or "") or None,
                input_id=decision_id,
                reason=(
                    f"Approved Decision replaces the originating artifact's handoff; "
                    f"{_article(role)} {role.capitalize()} action is required."
                ),
                path=replacement["decision_path"],
                components=[replacement["decision_path"]],
            )
            if readiness == "blocked":
                blocking = [str(b) for b in (handoff.get("blocking_ids") or [])]
                item["Reason"] = (
                    "Decision handoff is blocked on: " + ", ".join(sorted(blocking))
                    if blocking
                    else "Decision handoff is blocked."
                )
                blocked.append(item)
            else:
                ready.append(item)

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


def _wrap_diagnostic_cell(value: str, width: int, *, break_long_words: bool) -> list[str]:
    lines = textwrap.wrap(
        value,
        width=width,
        break_long_words=break_long_words,
        break_on_hyphens=False,
    )
    return lines or [""]


def _print_diagnostics_table(rows: list[tuple[str, str, str, str]]) -> None:
    headers = ("Severity", "Code", "Artifact", "Message")
    widths = (8, 32, 45, 80)
    print("  ".join(headers[index].ljust(widths[index]) for index in range(len(headers))))
    print("  ".join("-" * width for width in widths))
    for severity, code, artifact, message in rows:
        cells = (
            [severity[: widths[0]]],
            _wrap_diagnostic_cell(code, widths[1], break_long_words=True),
            _wrap_diagnostic_cell(artifact, widths[2], break_long_words=True),
            _wrap_diagnostic_cell(message, widths[3], break_long_words=False),
        )
        for line_index in range(max(len(cell) for cell in cells)):
            print(
                "  ".join(
                    (
                        cells[column_index][line_index]
                        if line_index < len(cells[column_index])
                        else ""
                    ).ljust(widths[column_index])
                    for column_index in range(len(headers))
                )
            )


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
        _print_diagnostics_table(rows)

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
