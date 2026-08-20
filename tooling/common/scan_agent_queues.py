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
CHECKSUM_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
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


#: The one reason an integrated migration is allowed to carry. A migration's
#: whole purpose is to change the canonical baseline, so once it has been applied
#: the state it was planned against is necessarily gone. Reporting that as work
#: told the Builder to re-issue a transaction the Integrator had already
#: completed, and buried the drift reports that do mean something.
#: DEC-2026-0043: the roles a non-migration Decision may assign its
#: implementation to. Deliberately not every role -- this lifecycle is for
#: tooling, contract, schema and operational work, and it never authorizes
#: canonical or registry mutation, which still requires an Approved GUP.
DIRECT_IMPLEMENTATION_OWNERS = frozenset({"builder", "integrator"})

BASELINE_MOVED_REASON = (
    "was planned against a canonical baseline that has since changed; "
    "Builder must re-issue it"
)


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
            reasons.append(BASELINE_MOVED_REASON)

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
    # WORK_QUEUES 1.7: the Decision that answered the escalation may since have
    # been reissued, and only the leaf of that lineage states the current ruling.
    # The Bards M048 escalation was answered by DEC-2026-0030, reissued as
    # DEC-2026-0031 and then DEC-2026-0037 -- and only the leaf carries the
    # corrected identity. Matching on `escalation_id` alone stopped at the
    # original, whose text says nothing about ordering, so the rebuild looked
    # ready while the instruction set it needed did not exist.
    successors = {
        str(document.get("supersedes") or "").strip(): decision_id
        for decision_id, (_, document) in decisions.items()
        if str(document.get("supersedes") or "").strip()
    }

    prerequisites: list[str] = []
    for decision_id, (_, document) in sorted(decisions.items()):
        if str(document.get("escalation_id") or "") not in blockers:
            continue
        seen = {decision_id}
        while decision_id in successors and successors[decision_id] not in seen:
            decision_id = successors[decision_id]
            seen.add(decision_id)
        document = decisions[decision_id][1]
        disposition = document.get("packet_disposition")
        if isinstance(disposition, dict):
            required = str(disposition.get("required_routing_review") or "").strip()
            # A Decision naming the Review that already exists is describing this
            # one, not asking for a further revision.
            if required and required != review_id:
                if not (artifacts_root / "reviews" / f"{required}.yaml").is_file():
                    prerequisites.append(f"{required} (required by {decision_id})")
        prerequisites.extend(_correction_prerequisites(review_id, decision_id, document))
    return sorted(prerequisites)


def _correction_prerequisites(
    review_id: str, decision_id: str, document: dict[str, Any]
) -> list[str]:
    """A Decision that hands a named Review a correction requires its successor.

    The other shape names a Review that does not exist yet. This one names a
    Review that does -- the current leaf -- and states a correction the Reviewer
    must apply to it, so what is missing is the revision rather than the file.
    DEC-2026-0037 does exactly that: it replaces the Bards M048 row with an
    assertion naming the post-migration identity, and sequences the Reviewer's
    revision ahead of the Builder's rebuild. Reading only the first shape, the
    queue called the rebuild ready while the corrected instruction set did not
    exist, and building against the stale Review would have emitted the retired
    `item_pipes_sewer` that the same Decision exists to remove.

    The trigger is an exact named artifact carrying an exact correction, never
    prose: an `affected_artifacts` entry whose `id` is this leaf and which states
    a `correction_id` or `replacement_assertion`. A Decision merely mentioning a
    Review says nothing about ordering. Because the entry names the *leaf*, the
    correction cannot have been applied yet -- once it is, the leaf is the
    successor and this stops matching on its own.
    """
    affected = document.get("affected_artifacts")
    if not isinstance(affected, dict):
        return []
    found: list[str] = []
    for key, entry in sorted(affected.items()):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("id") or "").strip() != review_id:
            continue
        correction = str(entry.get("correction_id") or "").strip()
        if not correction and not isinstance(entry.get("replacement_assertion"), dict):
            continue
        found.append(
            f"a successor to {review_id} applying "
            f"{correction or 'the replacement assertion'} (required by {decision_id})"
        )
    return found


#: Roles a handoff may name, per WORK_QUEUES "Required Handoff Metadata".
HANDOFF_ROLES = frozenset(
    {"analyst", "builder", "reviewer", "architect", "integrator", "none"}
)


#: Fallback handoff shape, used only when the envelope schema cannot be read.
#: The scanner deliberately depends on nothing but PyYAML, so it degrades to
#: reporting queues rather than failing when the repository is incomplete.
_FALLBACK_HANDOFF_SHAPE = {
    "roles": HANDOFF_ROLES,
    "readiness": frozenset({"ready", "blocked", "terminal"}),
    "required": frozenset({"next_role", "readiness", "reason", "blocking_ids"}),
    "properties": frozenset({"next_role", "readiness", "reason", "blocking_ids"}),
}

_HANDOFF_SHAPE_CACHE: dict[Path, dict[str, frozenset[str]]] = {}


def _handoff_shape(root: Path) -> dict[str, frozenset[str]]:
    """The handoff vocabulary, read from the schema that defines it.

    Restating the enums here would let the scanner and the schema disagree about
    what a valid handoff is -- and the scanner's whole job under WORK_QUEUES
    1.11 is to say which artifacts do not conform. Read with `json` rather than
    validated with `jsonschema` so this stays a dependency-free reporting tool.
    """
    if root in _HANDOFF_SHAPE_CACHE:
        return _HANDOFF_SHAPE_CACHE[root]
    shape = dict(_FALLBACK_HANDOFF_SHAPE)
    path = root / "schemas" / "common" / "artifact-envelope.schema.json"
    try:
        handoff = json.loads(path.read_text(encoding="utf-8"))["$defs"]["handoff"]
        properties = handoff["properties"]
        shape = {
            "roles": frozenset(properties["next_role"]["enum"]),
            "readiness": frozenset(properties["readiness"]["enum"]),
            "required": frozenset(handoff["required"]),
            "properties": frozenset(properties),
        }
    except (OSError, ValueError, KeyError, TypeError):  # pragma: no cover
        pass
    _HANDOFF_SHAPE_CACHE[root] = shape
    return shape


def _handoff_defects(document: dict[str, Any], shape: dict[str, frozenset[str]]) -> list[str]:
    """Why a present handoff does not conform, as field-level phrases.

    Returns `[]` both for a conforming handoff and for an absent one; the caller
    distinguishes those two cases, because a missing block is a legacy artifact
    and a malformed one is a broken workflow.
    """
    handoff = document.get("handoff")
    if not isinstance(handoff, dict):
        return []

    defects: list[str] = []
    for key in sorted(shape["required"] - set(handoff)):
        defects.append(f"{key} is missing")
    for key in sorted(set(handoff) - shape["properties"]):
        defects.append(f"{key} is not a handoff field")

    role = handoff.get("next_role")
    if "next_role" in handoff and role not in shape["roles"]:
        defects.append(f"next_role is {role!r}, not one of {sorted(shape['roles'])}")

    readiness = handoff.get("readiness")
    if "readiness" in handoff and readiness not in shape["readiness"]:
        defects.append(
            f"readiness is {readiness!r}, not one of {sorted(shape['readiness'])}"
        )

    if "reason" in handoff and not str(handoff.get("reason") or "").strip():
        defects.append("reason is empty")

    blocking = handoff.get("blocking_ids")
    if "blocking_ids" in handoff and not isinstance(blocking, list):
        defects.append("blocking_ids is not a list")
        blocking = []
    blocking = blocking or []

    # The schema's three conditional invariants. Expressed here because they are
    # `if`/`then` subschemas rather than enums, and named so a diagnostic can
    # say which one failed.
    if readiness == "terminal" and role != "none":
        defects.append("readiness is terminal but next_role is not none")
    if readiness in ("ready", "terminal") and blocking:
        defects.append(f"readiness is {readiness} but blocking_ids names {len(blocking)}")
    if readiness == "blocked" and not blocking:
        defects.append("readiness is blocked but blocking_ids is empty")
    return defects


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



#: WORK_QUEUES 1.12 rule 14 applies only to Decisions that opt in by declaring
#: this authoring-contract version. Every Decision published before DEC-2026-0045
#: predates the requirement and remains valid immutable history; reading the rule
#: onto them would retroactively invalidate the record rather than govern new work.
DECISION_AUTHORING_CONTRACT_OWNERSHIP = "1.1"

#: The roles a Decision may assign a path to. Any other value is unknown: an
#: exact_diff path assigned to "tooling" or "architect team" names no one who can
#: be handed the work.
DECISION_OWNER_ROLES = frozenset(
    {"architect", "analyst", "builder", "reviewer", "integrator"}
)


def _decision_assigned_roles(document: dict[str, Any]) -> set[str]:
    """The roles this Decision actually schedules work for.

    WORK_QUEUES 1.12 rule 14 names exactly two sources: a sequence step and a
    `follow_up_owners` entry. The older singular `follow_up_owner` is deliberately
    not read here. Accepting it would widen the rule the guard exists to enforce,
    and a role that appears only there has been named as a contact rather than
    scheduled to do anything.
    """

    roles: set[str] = set()
    sequence = document.get("sequence")
    if isinstance(sequence, list):
        for entry in sequence:
            if isinstance(entry, dict):
                owner = str(entry.get("owner") or "").strip().lower()
                if owner:
                    roles.add(owner)
    follow_up = document.get("follow_up_owners")
    if isinstance(follow_up, dict):
        for key in follow_up:
            role = str(key).strip().lower()
            if role:
                roles.add(role)
    elif isinstance(follow_up, list):
        for entry in follow_up:
            if isinstance(entry, str) and entry.strip():
                roles.add(entry.strip().lower())
    return roles


def _sequence_owner_by_step(document: dict[str, Any]) -> dict[int, str]:
    """Step number -> declared owner, for entries that carry both."""

    owners: dict[int, str] = {}
    sequence = document.get("sequence")
    if not isinstance(sequence, list):
        return owners
    for entry in sequence:
        if not isinstance(entry, dict):
            continue
        step = entry.get("step")
        owner = str(entry.get("owner") or "").strip().lower()
        if isinstance(step, int) and not isinstance(step, bool) and owner:
            owners[step] = owner
    return owners


def _exact_diff_ownership_errors(document: dict[str, Any]) -> list[str]:
    """WORK_QUEUES 1.12 rule 14: every changed path has an accountable owner.

    DEC-2026-0043 named four Architect-owned governance files in its `exact_diff`
    and assigned them to no one, so the Decision could not complete: its only
    ready handoff was to Builder, which may not write a contract or a role
    instruction. DEC-2026-0039 had already done the same thing with a test file.
    Both were invisible until a Review failed on the missing work, because
    nothing compared the set of files a Decision changes against the set of roles
    it schedules.

    That comparison is what this function is. It reads the Decision alone -- no
    repository state, no timestamps, no inferred competence -- so an incomplete
    plan is detectable when it is authored rather than when it fails.

    An empty list means the plan is completely owned.
    """

    declared = str(document.get("decision_authoring_contract_version") or "").strip()
    if declared != DECISION_AUTHORING_CONTRACT_OWNERSHIP:
        return []
    exact_diff = document.get("exact_diff")
    if not isinstance(exact_diff, dict) or not exact_diff:
        return []

    ownership = document.get("exact_diff_ownership")
    if ownership is None:
        return [
            f"declares decision_authoring_contract_version "
            f"{DECISION_AUTHORING_CONTRACT_OWNERSHIP} and changes "
            f"{len(exact_diff)} exact_diff path(s) but records no "
            f"exact_diff_ownership"
        ]
    if not isinstance(ownership, list):
        return ["records a non-list exact_diff_ownership"]

    errors: list[str] = []
    assigned_roles = _decision_assigned_roles(document)
    step_owners = _sequence_owner_by_step(document)
    changed_paths = {str(path) for path in exact_diff}

    seen: dict[str, int] = {}
    for index, entry in enumerate(ownership, start=1):
        if not isinstance(entry, dict):
            errors.append(f"exact_diff_ownership entry {index} is not a mapping")
            continue
        path = str(entry.get("path") or "").strip()
        if not path:
            errors.append(f"exact_diff_ownership entry {index} names no path")
            continue
        seen[path] = seen.get(path, 0) + 1

        owner = str(entry.get("owner") or "").strip().lower()
        if not owner:
            errors.append(f"exact_diff_ownership for {path} names no owner")
        elif owner not in DECISION_OWNER_ROLES:
            errors.append(
                f"exact_diff_ownership for {path} names unknown owner {owner!r}; "
                f"expected one of {', '.join(sorted(DECISION_OWNER_ROLES))}"
            )
        elif owner not in assigned_roles:
            # The heart of the rule. An owner the Decision never schedules is a
            # name on a page: DEC-2026-0043 would have failed exactly here.
            errors.append(
                f"exact_diff_ownership assigns {path} to {owner}, which no "
                f"sequence step or follow_up_owners entry names"
            )

        step = entry.get("sequence_step")
        if step is not None:
            if not isinstance(step, int) or isinstance(step, bool):
                errors.append(
                    f"exact_diff_ownership for {path} declares a non-integer "
                    f"sequence_step"
                )
            elif step not in step_owners:
                errors.append(
                    f"exact_diff_ownership for {path} names sequence_step {step}, "
                    f"which the sequence does not define"
                )
            elif owner and step_owners[step] != owner:
                errors.append(
                    f"exact_diff_ownership for {path} names owner {owner} at "
                    f"sequence_step {step}, but that step is owned by "
                    f"{step_owners[step]}"
                )

        if path not in changed_paths:
            errors.append(
                f"exact_diff_ownership names {path}, which is not an exact_diff path"
            )

    for path, count in sorted(seen.items()):
        if count > 1:
            errors.append(
                f"exact_diff_ownership lists {path} {count} times; each path is "
                f"owned exactly once"
            )

    for path in sorted(changed_paths - set(seen)):
        errors.append(f"exact_diff changes {path} but no exact_diff_ownership entry owns it")

    return errors



#: `**Version 1.15.**` on its own line, as every contract in `contracts/` writes it.
CONTRACT_VERSION_PATTERN = re.compile(r"^\*\*Version ([0-9]+(?:\.[0-9]+)*)\.\*\*", re.M)


def _version_tuple(text: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(part) for part in str(text).strip().split("."))
    except (TypeError, ValueError):
        return None


def _declared_contract_version(root: Path, relative: str) -> str | None:
    """The version a contract declares, read from the file itself.

    Deliberately not taken from the report: the whole point of this evidence is
    that the current file is checked, so the number must come from the file.
    """

    path = root / relative
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - unreadable contract
        return None
    match = CONTRACT_VERSION_PATTERN.search(text)
    return match.group(1) if match else None


def _authorized_contract_sets(
    report_decision_id: str,
    report_decision_checksum: str,
    index: int,
    authority_document: dict[str, Any],
    authority_is_own_decision: bool,
) -> tuple[list[dict[str, Any]] | None, str]:
    """The contract/anchor sets this authority grants for this exact test.

    Returns (sets, reason). `sets` is None when the authority grants nothing for
    this Decision and index, and `reason` says why. Two shapes are legal:
    a Decision declaring its own `versioned_contract_content` semantics, and a
    later Decision pinning a legacy test through
    `contract_version_acceptance_authorizations`.
    """

    if authority_is_own_decision:
        for entry in authority_document.get("acceptance_test_semantics") or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("kind") != "versioned_contract_content":
                continue
            if entry.get("acceptance_test_index") != index:
                continue
            contracts = entry.get("contracts")
            if not isinstance(contracts, list) or not contracts:
                return None, "declares versioned_contract_content semantics with no contracts"
            return contracts, ""

    for entry in authority_document.get("contract_version_acceptance_authorizations") or []:
        if not isinstance(entry, dict):
            continue
        pinned = entry.get("decision_input")
        pinned = pinned if isinstance(pinned, dict) else {}
        if str(pinned.get("id") or "") != report_decision_id:
            continue
        if entry.get("acceptance_test_index") != index:
            continue
        # The authorization pins the Decision it covers by checksum, so a
        # rewritten Decision loses it rather than silently keeping it.
        if str(pinned.get("checksum") or "") != report_decision_checksum:
            return None, (
                f"authorizes {report_decision_id} at a different checksum than the "
                f"report's Decision currently hashes to"
            )
        contracts = entry.get("contracts")
        if not isinstance(contracts, list) or not contracts:
            return None, "carries an authorization with no contracts"
        return contracts, ""

    return None, (
        f"does not authorize {report_decision_id} acceptance test {index}"
    )


def _versioned_content_errors(
    root: Path,
    artifact: Artifact,
    decisions: dict[str, tuple[Path, dict[str, Any]]],
) -> list[str]:
    """WORK_QUEUES 1.15 acceptance test 48, over one implementation report.

    A mutable contract's version in an acceptance test becomes a minimum rather
    than a literal only through explicit, checksummed authority. DEC-2026-0045
    acceptance test 1 named WORK_QUEUES 1.12 and DEC-2026-0046 test 4 named 1.13;
    both were literally false within a day because later approved Decisions
    advanced the same file, while every requirement they actually stated was
    still present. Reading "1.12" as "1.12 or later" by eye would have fixed that
    and quietly widened every other version-pinned test at the same time.

    So the widening is granted per test, by an approved Decision, pinned to a
    checksum -- and this refuses it in every other case. It checks the current
    files, never the report's summary of them.
    """

    data = artifact.data
    decision_input = data.get("decision_input")
    decision_input = decision_input if isinstance(decision_input, dict) else {}
    report_decision_id = str(decision_input.get("id") or "")
    report_decision_checksum = str(decision_input.get("checksum") or "")

    errors: list[str] = []
    for entry in data.get("acceptance_results") or []:
        if not isinstance(entry, dict):
            continue
        block = entry.get("versioned_contract_content")
        if not isinstance(block, dict):
            continue
        errors.extend(
            _versioned_block_errors(
                root,
                report_decision_id,
                report_decision_checksum,
                entry.get("acceptance_test_index"),
                block,
                decisions,
                result_value=str(entry.get("result") or ""),
            )
        )
    return errors


def _versioned_block_errors(
    root: Path,
    report_decision_id: str,
    report_decision_checksum: str,
    index: Any,
    block: dict[str, Any],
    decisions: dict[str, tuple[Path, dict[str, Any]]],
    *,
    result_value: str,
) -> list[str]:
    """Validate one versioned contract-content evidence block.

    Shared deliberately between an implementation report and its independent
    Review. WORK_QUEUES 1.15 requires the Reviewer to re-derive the same
    authority, versions and anchors; running a second, similar implementation for
    the Review is how two checks drift until one quietly accepts what the other
    rejects.
    """

    errors: list[str] = []
    label = f"acceptance test {index}"

    if result_value != "passed":
        errors.append(
            f"carries versioned contract-content evidence on {label}, whose result is "
            f"{result_value!r}; this outcome is reported as passed"
        )

    if block.get("authorized_acceptance_test_index") != index:
        errors.append(
            f"{label} records versioned contract-content authority for index "
            f"{block.get('authorized_acceptance_test_index')!r}"
        )

    authority = block.get("authority")
    authority = authority if isinstance(authority, dict) else {}
    authority_id = str(authority.get("id") or "")
    if authority_id not in decisions:
        errors.append(
            f"{label} names authority {authority_id or '(absent)'}, which is not an "
            f"approved Decision of this ruleset"
        )
        return errors
    authority_path, authority_document = decisions[authority_id]

    actual = _sha256_of(authority_path)
    if str(authority.get("checksum") or "") != actual:
        errors.append(
            f"{label} records a stale checksum for authority {authority_id}, which now "
            f"hashes to {actual}"
        )
        return errors
    declared_path = str(authority.get("path") or "")
    if declared_path and declared_path != _relative(root, authority_path):
        errors.append(f"{label} records the wrong path for authority {authority_id}")

    contracts, reason = _authorized_contract_sets(
        report_decision_id,
        report_decision_checksum,
        index,
        authority_document,
        authority_is_own_decision=authority_id == report_decision_id,
    )
    if contracts is None:
        errors.append(f"{label} authority {authority_id} {reason}")
        return errors

    observed: dict[str, list[dict[str, Any]]] = {}
    for record in block.get("contracts") or []:
        if isinstance(record, dict) and record.get("path"):
            observed.setdefault(str(record["path"]), []).append(record)

    authorized_paths = set()
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        relative = str(contract.get("path") or "")
        authorized_paths.add(relative)
        minimum = str(contract.get("minimum_version") or "")
        anchors = [str(a) for a in (contract.get("substantive_anchors") or [])]

        records = observed.get(relative) or []
        if not records:
            errors.append(f"{label} records no current evidence for {relative}")
            continue
        if len(records) > 1:
            errors.append(f"{label} records {relative} {len(records)} times")
        record = records[0]

        current_sum = _sha256_of(root / relative) if (root / relative).is_file() else None
        if current_sum is None:
            errors.append(f"{label} names {relative}, which does not exist")
            continue
        if str(record.get("checksum") or "") != current_sum:
            errors.append(
                f"{label} records a stale checksum for {relative}, which now hashes to "
                f"{current_sum}"
            )
        if str(record.get("minimum_version") or "") != minimum:
            errors.append(
                f"{label} records minimum version {record.get('minimum_version')!r} for "
                f"{relative}, but its authority grants {minimum!r}"
            )

        live_version = _declared_contract_version(root, relative)
        if live_version is None:
            errors.append(f"{label} names {relative}, which declares no version")
            continue
        if str(record.get("observed_version") or "") != live_version:
            errors.append(
                f"{label} reports {relative} at version "
                f"{record.get('observed_version')!r} but the file declares {live_version!r}"
            )
        live_tuple, minimum_tuple = _version_tuple(live_version), _version_tuple(minimum)
        if live_tuple is None or minimum_tuple is None:
            errors.append(f"{label} cannot compare versions for {relative}")
        elif live_tuple < minimum_tuple:
            errors.append(
                f"{label} requires {relative} at {minimum} or later, but it is {live_version}"
            )

        present = {str(a) for a in (record.get("anchors_present") or [])}
        missing = [a for a in anchors if a not in present]
        if missing:
            errors.append(
                f"{label} does not evidence {len(missing)} authorized anchor(s) for "
                f"{relative}: {'; '.join(missing)}"
            )

    for relative in sorted(set(observed) - authorized_paths):
        errors.append(f"{label} evidences {relative}, which its authority does not name")

    return errors


def _implementation_report_errors(
    root: Path,
    artifact: Artifact,
    decisions: dict[str, tuple[Path, dict[str, Any]]],
    *,
    drift_sink: list[str] | None = None,
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

    # 2: the Decision must actually be a ready non-migration assignment, and the
    # report must claim the role the Decision assigned. DEC-2026-0043 opened this
    # to the Integrator for tooling and contract work; the owner is whichever role
    # the ready handoff names, and exactly one role owns a Decision. A report
    # claiming the other role is a diagnostic rather than a silent reassignment,
    # because who implemented a Decision is part of what the Review verifies.
    handoff = decision_doc.get("handoff")
    handoff = handoff if isinstance(handoff, dict) else {}
    if str(decision_doc.get("ruleset_id") or "") != artifact.ruleset:
        reasons.append(f"{decision_id} belongs to another ruleset")
    owner = str(handoff.get("next_role") or "").strip().lower()
    if owner not in DIRECT_IMPLEMENTATION_OWNERS:
        reasons.append(
            f"{decision_id} hands off to {owner or 'no role'}, not to "
            f"{' or '.join(sorted(DIRECT_IMPLEMENTATION_OWNERS))}"
        )
    else:
        declared = str(data.get("implemented_by") or "").strip().lower()
        if declared != owner:
            reasons.append(
                f"declares implemented_by {declared!r} but {decision_id} assigns its "
                f"implementation to {owner!r}"
            )
    if str(handoff.get("readiness") or "") != "ready":
        reasons.append(f"{decision_id} has no ready implementation handoff")
    if decision_doc.get("migration_required") is not False:
        reasons.append(f"{decision_id} is not a non-migration Decision")

    acceptance = decision_doc.get("acceptance_tests")
    if not isinstance(acceptance, list) or not acceptance:
        reasons.append(f"{decision_id} declares no acceptance_tests")
        acceptance = []

    # 4: every implementation file exists and hashes to what is recorded.
    #
    # WORK_QUEUES 1.13 rule 15 makes the meaning of a drifted file depend on
    # something this function cannot see: whether an exact Approved Review has
    # already consumed this report. So drift is collected separately when the
    # caller asks for it, and the caller decides whether it is an error or a
    # historical observation. A missing or malformed list is not drift -- it is
    # a defect in the report itself either way.
    drift = drift_sink if drift_sink is not None else reasons
    files = data.get("implementation_files")
    if not isinstance(files, list) or not files:
        reasons.append("has an empty or missing implementation_files list")
        files = []
    for item in files:
        if not isinstance(item, dict):
            reasons.append("has an implementation_files entry that is not a mapping")
            continue
        relative = str(item.get("path") or "").strip()
        if not relative:
            reasons.append("has an implementation_files entry naming no path")
            continue
        candidate = root / relative
        if not candidate.is_file():
            drift.append(f"names implementation file {relative!r}, which does not exist")
            continue
        if str(item.get("checksum") or "").strip() != _sha256_of(candidate):
            drift.append(f"records a stale checksum for {relative}")

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

    # WORK_QUEUES 1.15: current-state contract evidence is validated against the
    # current files, so an authorization that has gone stale or a contract that
    # has fallen below its floor stops the report here rather than at Review.
    reasons.extend(_versioned_content_errors(root, artifact, decisions))

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
    report_versioned = {
        r.get("acceptance_test_index")
        for r in report.data.get("acceptance_results") or []
        if isinstance(r, dict) and isinstance(r.get("versioned_contract_content"), dict)
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
        elif disposition_value == "verified_versioned_contract_content":
            # WORK_QUEUES 1.15. The Reviewer re-derives the authority, the current
            # contract versions and every anchor for itself, through exactly the
            # validation the report went through -- a second implementation here
            # would drift from that one until the two disagreed.
            if reported != "passed":
                reasons.append(
                    f"disposes acceptance_test_index {index} as "
                    f"verified_versioned_contract_content, but the report records it as "
                    f"{reported!r}"
                )
                continue
            if index not in report_versioned:
                reasons.append(
                    f"disposes acceptance_test_index {index} as "
                    f"verified_versioned_contract_content, but the report claims no "
                    f"versioned contract-content evidence for it"
                )
                continue
            mirrored = item.get("verified_versioned_contract_content")
            if not isinstance(mirrored, dict):
                reasons.append(
                    f"disposes acceptance_test_index {index} as "
                    f"verified_versioned_contract_content without recording its own "
                    f"verification"
                )
                continue
            reasons.extend(
                f"independent verification: {reason}"
                for reason in _versioned_block_errors(
                    root,
                    decision_id,
                    report_checksum,
                    index,
                    mirrored,
                    decisions,
                    result_value=reported,
                )
            )
        elif disposition_value == "verified":
            if reported == "retired_by_lineage":
                reasons.append(
                    f"is approved but disposes the retired acceptance_test_index {index} as "
                    f"plain verified; a retired result needs verified_retired_by_lineage"
                )
            elif index in report_versioned:
                # The converse guard, matching the retired one above: approving
                # this evidence as plain `verified` would make the Reviewer's
                # independent re-derivation optional.
                reasons.append(
                    f"is approved but disposes the versioned contract-content "
                    f"acceptance_test_index {index} as plain verified; it needs "
                    f"verified_versioned_contract_content"
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


def _diagnose_gur_handoffs(
    root: Path,
    gurs: list[Artifact],
    diagnostics: list[dict[str, Any]],
) -> None:
    """Report every GUR whose present handoff does not conform.

    Emitted for leaf and non-leaf revisions alike, because an invalid artifact is
    invalid wherever it sits in a lineage and the repository-wide schema suite
    will fail on it either way. Only the active leaf becomes repair *work*: a
    superseded revision's successor has already resolved queue ownership, so
    asking for a repair of history would be asking to rewrite it.
    """
    shape = _handoff_shape(root)
    for artifact in gurs:
        defects = _handoff_defects(artifact.data, shape)
        if not defects:
            continue
        _diag(
            diagnostics,
            "error",
            "gur_invalid_handoff",
            f"{artifact.artifact_id} declares a handoff that does not conform: "
            f"{'; '.join(defects)}. Analyst owns the repair and must publish a "
            f"schema-valid successor revision; the published artifact is immutable.",
            path=_relative(root, artifact.path),
            artifact_id=artifact.artifact_id,
        )


def _route_leaf_gur(
    root: Path,
    ruleset: str,
    book: str,
    packet_id: str,
    leaf_gur: Artifact,
    gur_inferred: bool,
    ready: list[dict[str, Any]],
    diagnostics: list[dict[str, Any]],
) -> None:
    """WORK_QUEUES 1.11: where an unconsumed active-leaf GUR's work belongs.

    Three shapes, three destinations:

    * a **malformed** handoff is a broken workflow the Analyst owns. It routes to
      `ANALYST-GUR-REPAIR` and never to Builder -- the role that cannot legally
      repair a published GUR. Before this rule, an unreadable handoff fell
      through to legacy inference and produced an ordinary Builder job, so a UA
      GUR sat in the wrong queue for days while its invalidity held the common
      suite red and, through it, seven Decision implementation reports.
    * a conforming **terminal** handoff is finished work. A withdrawn GUR needs
      no empty GUP to consume it.
    * an **absent** handoff is a legacy artifact: ordinary Builder routing, with
      the inference reported rather than silent.
    """
    defects = _handoff_defects(leaf_gur.data, _handoff_shape(root))
    handoff = leaf_gur.data.get("handoff")
    path = _relative(root, leaf_gur.path)

    if defects:
        ready.append(
            _queue_item(
                state="ready",
                queue="ANALYST-GUR-REPAIR",
                role="Analyst",
                ruleset=ruleset,
                book=book,
                packet_id=packet_id,
                input_id=leaf_gur.artifact_id,
                reason=(
                    "Active-leaf GUR has a malformed handoff; Analyst must publish a "
                    "schema-valid successor revision."
                ),
                path=path,
                components=[path],
            )
        )
        return

    if isinstance(handoff, dict):
        if str(handoff.get("readiness") or "").strip() == "terminal":
            return
    else:
        _diag(
            diagnostics,
            "info",
            "legacy_handoff_inference",
            f"{leaf_gur.artifact_id} carries no handoff block; ordinary Builder "
            f"routing was inferred under the WORK_QUEUES legacy rules.",
            path=path,
            artifact_id=leaf_gur.artifact_id,
        )

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
            path=path,
            components=[path],
            legacy_inference=gur_inferred or not isinstance(handoff, dict),
        )
    )


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



#: DEC-2026-0043 authorizes exactly one already-published rejection record to act
#: as a queue signal without the checksums the schema now requires. It is named by
#: record ID *and* bundle ID together, so the allowance cannot spread to another
#: bundle in the same file or to a later record reusing the ID.
LEGACY_AUTHORIZED_REJECTIONS = {
    ("INT-20260815-002", "APPROVED-GUP-PKT-PHB-094-100-illusionist-spells-r04-r01"),
}

REJECTION_CHECKSUM_FIELDS = (
    ("bundle_id", "bundle_checksum", "bundle"),
    ("review_id", "review_checksum", "approving Review"),
    ("gup_id", "gup_checksum", "reviewed GUP"),
)


def _rejection_entry_errors(
    root: Path,
    record_id: str,
    entry: dict[str, Any],
    artifact_paths: dict[str, Path],
) -> list[str]:
    """Why one rejected-bundle entry may not act as a queue signal.

    A rejection retires an Integrator job, so it has to be at least as
    well-evidenced as the approval it overrides: the exact bundle, the Review
    that approved it, and the GUP it carries, each pinned to the bytes on disk.
    Without the pins a record would keep suppressing integration after the
    artifacts it describes were re-issued -- the bundle would sit unqueued and
    unrejected, which is the failure mode this whole rule exists to end.
    """
    reasons: list[str] = []
    bundle_id = str(entry.get("bundle_id") or "").strip()
    if not bundle_id:
        return ["names no bundle_id"]

    if (record_id, bundle_id) in LEGACY_AUTHORIZED_REJECTIONS:
        # Authorized by exact ID pair. Still must name a failure: a rejection
        # with no stated failing check directs no repair.
        if not (entry.get("blocking_failures") or []):
            reasons.append(f"{bundle_id} names no blocking_failures")
        return reasons

    failures = entry.get("blocking_failures")
    if not isinstance(failures, list) or not failures:
        reasons.append(f"{bundle_id} names no blocking_failures")
    else:
        for failure in failures:
            if not isinstance(failure, dict):
                reasons.append(f"{bundle_id} has a blocking_failures entry that is not a mapping")
                continue
            if not str(failure.get("check") or "").strip():
                reasons.append(f"{bundle_id} has a blocking failure naming no check")
            if not str(failure.get("detail") or "").strip():
                reasons.append(f"{bundle_id} has a blocking failure with no detail")

    for id_field, checksum_field, label in REJECTION_CHECKSUM_FIELDS:
        declared_id = str(entry.get(id_field) or "").strip()
        declared_sum = str(entry.get(checksum_field) or "").strip()
        if not declared_id:
            reasons.append(f"{bundle_id} names no {id_field}")
            continue
        if not CHECKSUM_PATTERN.match(declared_sum):
            reasons.append(f"{bundle_id} records no valid {checksum_field}")
            continue
        path = artifact_paths.get(declared_id)
        if path is None:
            reasons.append(f"{bundle_id} names {label} {declared_id}, which is not on disk")
            continue
        actual = _sha256_of(path)
        if actual != declared_sum:
            reasons.append(
                f"{bundle_id} records a stale {label} checksum for {declared_id}; "
                f"it now hashes to {actual}"
            )
    return reasons


def _rejected_bundle_ids(
    root: Path,
    ruleset: str,
    artifact_paths: dict[str, Path],
    live_bundle_ids: set[str],
    diagnostics: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Bundles a current, valid rejection record blocks, by bundle ID.

    DEC-2026-0043 makes an Integration rejection a first-class queue signal: it
    suppresses that exact bundle's Integrator item and creates one Reviewer
    remediation item. Everything that could make the signal untrustworthy --
    unreadable, wrong ruleset, superseded by a later record, ambiguous between two
    records, or pinned to checksums that have moved -- is reported and suppresses
    nothing. A rejection that cannot be trusted must leave the bundle exactly where
    it was rather than quietly removing it from the queue.
    """
    directory = root / "rulesets" / ruleset / "reports"
    if not directory.is_dir():
        return {}

    records: dict[str, tuple[Path, dict[str, Any]]] = {}
    superseded: set[str] = set()
    for path in sorted(directory.glob("*.rejected.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            _diag(
                diagnostics,
                "error",
                "integration_rejection_unreadable",
                f"{path.name} is not readable JSON: {exc}",
                path=_relative(root, path),
            )
            continue
        if not isinstance(document, dict):
            _diag(
                diagnostics,
                "error",
                "integration_rejection_invalid",
                f"{path.name} does not contain a mapping.",
                path=_relative(root, path),
            )
            continue
        record_id = str(document.get("id") or path.name).strip()
        if str(document.get("status") or "").strip() != "rejected":
            _diag(
                diagnostics,
                "error",
                "integration_rejection_invalid",
                f"{record_id} declares status "
                f"{document.get('status')!r} rather than 'rejected'.",
                path=_relative(root, path),
                artifact_id=record_id,
            )
            continue
        declared_ruleset = str(document.get("ruleset_id") or "").strip()
        if declared_ruleset != ruleset:
            _diag(
                diagnostics,
                "error",
                "integration_rejection_invalid",
                f"{record_id} belongs to ruleset {declared_ruleset!r}, not {ruleset!r}; "
                f"it suppresses nothing here.",
                path=_relative(root, path),
                artifact_id=record_id,
            )
            continue
        records[record_id] = (path, document)
        predecessor = str(document.get("supersedes") or "").strip()
        if predecessor:
            superseded.add(predecessor)

    blocked_by_bundle: dict[str, dict[str, Any]] = {}
    claimed_by: dict[str, str] = {}
    for record_id in sorted(records):
        path, document = records[record_id]
        if record_id in superseded:
            # A later record describes the current state of this integration.
            continue
        entries = document.get("rejected_bundles")
        if not isinstance(entries, list) or not entries:
            _diag(
                diagnostics,
                "error",
                "integration_rejection_invalid",
                f"{record_id} names no rejected_bundles.",
                path=_relative(root, path),
                artifact_id=record_id,
            )
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            bundle_id = str(entry.get("bundle_id") or "").strip()
            if bundle_id not in live_bundle_ids:
                # Superseded, integrated, or gone. The bundle produces no
                # Integrator item, so this entry can neither suppress one nor
                # describe repairable work.
                continue
            reasons = _rejection_entry_errors(root, record_id, entry, artifact_paths)
            if reasons:
                _diag(
                    diagnostics,
                    "error",
                    "integration_rejection_invalid",
                    f"{record_id} " + "; ".join(reasons) + ". It suppresses no integration.",
                    path=_relative(root, path),
                    artifact_id=record_id,
                )
                continue
            previous = claimed_by.get(bundle_id)
            if previous is not None and previous != record_id:
                # Two live records disagreeing about one bundle is not a signal
                # anyone can act on, and choosing between them is not a queue
                # decision. Both are reported and neither suppresses.
                _diag(
                    diagnostics,
                    "error",
                    "integration_rejection_ambiguous",
                    f"{bundle_id} is rejected by both {previous} and {record_id} with "
                    f"neither superseding the other; neither suppresses integration.",
                    path=_relative(root, path),
                    artifact_id=bundle_id,
                )
                blocked_by_bundle.pop(bundle_id, None)
                continue
            claimed_by[bundle_id] = record_id
            blocked_by_bundle[bundle_id] = {
                "record_id": record_id,
                "record_path": _relative(root, path),
                "bundle_id": bundle_id,
                "review_id": str(entry.get("review_id") or "").strip(),
                "gup_id": str(entry.get("gup_id") or "").strip(),
                "failures": [
                    str(f.get("check") or "")
                    for f in (entry.get("blocking_failures") or [])
                    if isinstance(f, dict)
                ],
            }
    return blocked_by_bundle


def _rejection_remediated(rejection: dict[str, Any], reviews: list[Artifact]) -> bool:
    """Whether a Review successor already records this exact rejection.

    The successor is what turns a rejection into repairable work, so the
    remediation item exists only until one names the record. Matching is on the
    exact record ID: a Review that merely postdates the rejection has not
    necessarily read it.
    """
    for artifact in reviews:
        for key in ("integration_rejection", "rejection_input", "rejected_by"):
            block = artifact.data.get(key)
            if isinstance(block, dict):
                if str(block.get("id") or "").strip() == rejection["record_id"]:
                    return True
            elif isinstance(block, str) and block.strip() == rejection["record_id"]:
                return True
    return False

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
    #: WORK_QUEUES 1.7: per ruleset, the Decision IDs a valid reissue superseded.
    reissued_by_ruleset: dict[str, set[str]] = defaultdict(set)
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
                _diagnose_gur_handoffs(
                    root, gurs_by_packet.get(packet_id, []), diagnostics
                )
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
                    _route_leaf_gur(
                        root,
                        ruleset,
                        book,
                        packet_id,
                        leaf_gur,
                        gur_inferred,
                        ready,
                        diagnostics,
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
            # DEC-2026-0043: a rejection pins the bundle, its approving Review and
            # its GUP by checksum, so every one of those has to be resolvable to a
            # path before the record can be trusted.
            rejection_artifact_paths: dict[str, Path] = {}
            for base, paths in approved_groups.items():
                manifest_path = next(
                    (candidate for candidate in paths if candidate.suffix == ".yaml"), None
                )
                if manifest_path is not None:
                    rejection_artifact_paths[base] = manifest_path
            for artifact in reviews:
                rejection_artifact_paths[artifact.artifact_id] = artifact.path
            for artifact in gups:
                rejection_artifact_paths[artifact.artifact_id] = artifact.path
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
            # Only a bundle that could otherwise be offered for integration is
            # worth judging a rejection against. Every rejection in this
            # repository's history names bundles that have since been superseded
            # or integrated, and reporting each pre-contract record as defective
            # produced 56 errors that buried the 5 live ones. A rejection of a
            # bundle nobody is queuing suppresses nothing either way.
            live_bundle_ids: set[str] = set()
            for base, paths in approved_groups.items():
                if base in integrated_ids:
                    continue
                manifest_candidate = next(
                    (c for c in paths if c.suffix.lower() in {".yaml", ".yml"}), None
                )
                bundle_manifest = (
                    _load_yaml(root, manifest_candidate, diagnostics)
                    if manifest_candidate
                    else None
                )
                legacy_review_id = (
                    "REV-" + base[len("APPROVED-"):] if base.startswith("APPROVED-") else ""
                )
                packaged = _packaged_gup_id(
                    bundle_manifest, review_by_id.get(legacy_review_id)
                )
                if packaged and packaged in superseded_gup_ids:
                    continue
                live_bundle_ids.add(base)
            rejected_bundles = _rejected_bundle_ids(
                root, ruleset, rejection_artifact_paths, live_bundle_ids, diagnostics
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

                rejection = rejected_bundles.get(approved_id)
                if rejection is not None:
                    # DEC-2026-0043: the rejection is the current word on this
                    # bundle. Re-offering it would hand the Integrator the same
                    # batch it just refused -- which is what kept the illusionist
                    # bundle in the ready queue across three rejections of the
                    # same bytes. The repairable work belongs to the Reviewer,
                    # who publishes an immutable successor Review recording the
                    # rejection and routing the fix to its responsible role.
                    successors = [
                        artifact
                        for artifact in reviews_by_gup.get(rejection["gup_id"], [])
                        if artifact.artifact_id != rejection["review_id"]
                    ]
                    if _rejection_remediated(rejection, successors):
                        informational.append(
                            _queue_item(
                                state="informational",
                                queue="INTEGRATOR-REJECTED",
                                role="Integrator",
                                ruleset=ruleset,
                                book=book,
                                packet_id=str(packet_id or review.packet_id or "") or None,
                                input_id=approved_id,
                                reason=(
                                    f"{rejection['record_id']} rejected this bundle and a "
                                    f"Review successor already records it. The bundle is "
                                    f"unchanged and remains available as history."
                                ),
                                path=_relative(root, component_paths[0]),
                                components=[
                                    _relative(root, path) for path in component_paths
                                ],
                            )
                        )
                        continue
                    ready.append(
                        _queue_item(
                            state="ready",
                            queue="REVIEWER-INTEGRATION-REJECTION",
                            role="Reviewer",
                            ruleset=ruleset,
                            book=book,
                            packet_id=str(packet_id or review.packet_id or "") or None,
                            input_id=approved_id,
                            reason=(
                                f"{rejection['record_id']} rejected this bundle: "
                                + "; ".join(rejection["failures"])
                                + ". Publish a Review successor recording the rejection "
                                "and routing the repair."
                            ),
                            path=rejection["record_path"],
                            components=sorted(
                                {rejection["record_path"]}
                                | {_relative(root, path) for path in component_paths}
                            ),
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
            # Kept per ruleset because the handoff-replacement pass at the end of
            # the scan runs in its own loop and needs the same answer -- and
            # recomputing it there would emit every lineage diagnostic twice.
            reissued_decision_ids = _decision_reissue_leaves(
                root, ruleset, decisions, decisions_by_ruleset, diagnostics
            )
            reissued_by_ruleset[ruleset] = reissued_decision_ids

            # WORK_QUEUES 1.12 rule 14. Checked here, before either Decision loop
            # below derives work, because an unowned exact_diff path is a defect
            # in the plan itself rather than in anything downstream of it.
            unowned_decision_ids: set[str] = set()
            for decision_id in sorted(decisions):
                decision_path, decision_document = decisions[decision_id]
                ownership_errors = _exact_diff_ownership_errors(decision_document)
                if not ownership_errors:
                    continue
                unowned_decision_ids.add(decision_id)
                _diag(
                    diagnostics,
                    "error",
                    "decision_exact_diff_unowned",
                    f"{decision_id} " + "; ".join(ownership_errors) + ".",
                    path=_relative(root, decision_path),
                    artifact_id=decision_id,
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
                if lineage_integrated and BASELINE_MOVED_REASON in reasons:
                    # Applying the migration is what moved the baseline. Any other
                    # reason still stands: an integrated artifact with a forbidden
                    # GUR lineage or an unapproved authority is a real defect.
                    reasons = [r for r in reasons if r != BASELINE_MOVED_REASON]
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
                owner = str(handoff.get("next_role") or "").strip().lower()
                if owner not in DIRECT_IMPLEMENTATION_OWNERS:
                    continue
                if str(handoff.get("readiness") or "") != "ready":
                    continue
                if document.get("migration_required") is not False:
                    continue
                if decision_id in reissued_decision_ids:
                    continue
                if decision_id in unowned_decision_ids:
                    # WORK_QUEUES 1.12 rule 14: an incompletely owned plan cannot
                    # become approval-ready, so it is not ready implementation
                    # work. It is reported blocked rather than dropped: the work
                    # is real, and silently withholding it is how DEC-2026-0043
                    # reached a failed acceptance test with an empty Architect
                    # queue. Decisions are immutable, so only a successor
                    # Decision can supply the missing assignment.
                    blocked.append(
                        _queue_item(
                            state="blocked",
                            queue="ARCHITECT-DECISION-OWNERSHIP",
                            role="Architect",
                            ruleset=ruleset,
                            book=str(document.get("book_id") or "") or None,
                            packet_id=str(document.get("packet_id") or "") or None,
                            input_id=decision_id,
                            reason=(
                                f"{decision_id} changes exact_diff paths that its own "
                                f"sequence and follow_up_owners assign to no role, so "
                                f"{owner.capitalize()} cannot complete it. A successor "
                                f"Decision must record the missing ownership."
                            ),
                            path=_relative(root, path),
                            components=[_relative(root, path)],
                        )
                    )
                    continue

                group = reports_by_decision.get(decision_id) or []
                leaf, report_inferred = _active_leaf(
                    root, group, diagnostics, f"{ruleset} implementation {decision_id}"
                )

                # WORK_QUEUES 1.13 rule 15. The candidate Review is resolved and
                # validated before implementation-file drift is classified,
                # because drift means opposite things on either side of an
                # Approved Review. After one, the recorded checksums are a
                # snapshot of the state that was reviewed, and a later Decision
                # editing the same shared file says nothing about this one.
                # Before one, drift is still a live defect and still returns the
                # Decision to its implementation owner.
                report_errors: list[str] = []
                file_drift: list[str] = []
                review_leaf = None
                if leaf is not None:
                    report_errors = _implementation_report_errors(
                        root, leaf, decisions, drift_sink=file_drift
                    )
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
                        # It also cannot confer the post-approval drift exception:
                        # a Review that does not pin this exact report and
                        # Decision has not established any completed state.
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

                consumed_by_approved_review = review_leaf is not None and str(
                    review_leaf.data.get("overall_disposition")
                    or review_leaf.data.get("status")
                    or ""
                ) == "approved"

                if file_drift and leaf is not None:
                    if consumed_by_approved_review:
                        _diag(
                            diagnostics,
                            "info",
                            "implementation_files_drifted_after_approval",
                            f"{leaf.artifact_id} " + "; ".join(file_drift) + ". "
                            f"{review_leaf.artifact_id} already approved this exact "
                            f"report, so these checksums are the reviewed snapshot "
                            f"and {decision_id} stays complete. Validating the "
                            f"current file belongs to whatever changed it.",
                            path=_relative(root, leaf.path),
                            artifact_id=leaf.artifact_id,
                        )
                    else:
                        report_errors = report_errors + file_drift

                if report_errors:
                    _diag(
                        diagnostics,
                        "error",
                        "decision_implementation_invalid",
                        f"{leaf.artifact_id} " + "; ".join(report_errors) + ".",
                        path=_relative(root, leaf.path),
                        artifact_id=leaf.artifact_id,
                    )
                    # A report that is broken on its own terms is consumed by no
                    # Review. Discarding the leaf here keeps every pre-approval
                    # case behaving exactly as it did before rule 15.
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
                            queue=f"{owner.upper()}-DECISION-IMPLEMENTATION-REVISION",
                            role=owner.capitalize(),
                            ruleset=ruleset,
                            book=str(document.get("book_id") or "") or None,
                            packet_id=str(document.get("packet_id") or "") or None,
                            input_id=review_leaf.artifact_id,
                            reason=(
                                f"Implementation Review requires a "
                                f"{owner.capitalize()} revision of {decision_id}."
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
                # Decision remains its assigned owner's work.
                ready.append(
                    _queue_item(
                        state="ready",
                        queue=f"{owner.upper()}-DECISION",
                        role=owner.capitalize(),
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

            # WORK_QUEUES 1.7: a superseded Decision states a ruling its leaf has
            # replaced, so it must not create work here either. The suppression
            # above still stands -- the escalation really was resolved by this
            # lineage -- but the job belongs to the leaf, which raises its own
            # item. Without this, DEC-2026-0033 kept producing a ready Builder
            # item beside DEC-2026-0042, the very reissue that corrected it, and
            # the two Decision loops' 1.7 guards could not see it because this
            # pass runs in a separate loop.
            if decision_id in reissued_by_ruleset.get(ruleset, set()):
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
