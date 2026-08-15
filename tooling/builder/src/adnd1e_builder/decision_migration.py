"""Decision-driven canonical migration.

`migration.py` plans an identity *merge*: every row incident on a retired ID
moves to a survivor. DEC-2026-0015 and DEC-2026-0016 are a different shape. They
name individual canonical rows and say what changes on each one, because the
Architect decided row by row which assertion is about a specific spell and which
is about a family. Deriving that set from a rule would be the Builder guessing at
identity, which is precisely what those decisions removed.

So this module plans exactly what a decision enumerates and nothing more, then
audits the result against the five-field assertion key. The audit is the reason
the module exists: a repoint can silently turn two distinct assertions into one,
and only a dry run over the whole corpus shows it.

Nothing here writes canonical data. The Integrator does that after Review.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .duplicates import CanonicalEdges, assertion_key

#: Fields of the five-field assertion key. Changing one changes what the row
#: asserts; changing anything else is a correction to how it is described.
_IDENTITY_FIELDS = ("source_id", "edge_type", "target_id", "aspect", "condition")

#: Keys inside `canonical_migration` this planner acts on.
UNDERSTOOD_MIGRATION_KEYS = frozenset(
    {
        "endpoint_repoints",
        "endpoint_label_normalizations_without_repoint",
        "node_id_replacements",
        "node_id_merges",
        "merged_assertion",
        "counts",
    }
)

#: Keys that carry provenance, numbering conventions, or Reviewer constraints
#: rather than operations. Not reading one changes nothing about what the
#: migration does, so they are declared here instead of being reported.
DOCUMENTARY_MIGRATION_KEYS = frozenset(
    {
        "row_locator",
        "canonical_source",
        "registry_source",
        "required_no_change_fields",
    }
)

#: Keys `_plan_endpoint_repoints` reads on a single repoint entry.
UNDERSTOOD_REPOINT_KEYS = frozenset(
    {"canonical_row", "field", "from", "to", "label", "before_assertion", "note"}
)


@dataclass
class RowChange:
    """One canonical row and the exact columns a decision changes on it."""

    canonical_row: int
    canonical_index: int
    kind: str  # endpoint_repoint | label_normalization | citation_correction
    changes: dict[str, tuple[str, str]]  # field -> (before, after)
    authority: str
    before: dict
    note: str = ""

    @property
    def touches_identity(self) -> bool:
        return any(f in _IDENTITY_FIELDS for f in self.changes)


@dataclass
class Removal:
    """A row a decision retires after its provenance is preserved elsewhere."""

    canonical_row: int
    canonical_index: int
    #: The row whose locus justifies retiring this one, or None when the
    #: authorizing Decision retires the row outright with no replacement.
    surviving_row: int | None
    identity: str
    preserved: dict
    authority: str
    #: The exact 18-column row as it stands in canonical, verified equal to the
    #: before-image the Decision states. A removal is a compare-and-swap: the
    #: Reviewer confirms this image, and the Integrator refuses the removal if
    #: the row has moved underneath it.
    before: dict = field(default_factory=dict)
    action: str = "remove_after_the_surviving_row_carries_the_preserved_locus"


@dataclass
class NodeIDReplacement:
    """One retired node ID to be replaced by a canonical node ID."""

    retired_id: str
    retired_label: str
    canonical_id: str
    canonical_label: str
    kind: str
    registry_action: str
    require_no_remaining_retired_endpoints: bool = True


@dataclass
class DecisionMigration:
    decisions: list[str] = field(default_factory=list)
    #: One entry per authority Decision: id, repository path, sha256. This is
    #: the alternate auditable root that stands in for GUR provenance.
    decision_inputs: list[dict] = field(default_factory=list)
    nodes_added: list[dict] = field(default_factory=list)
    nodes_relabelled: list[dict] = field(default_factory=list)
    nodes_replaced: list[dict] = field(default_factory=list)
    #: DEC-2026-0032: two or more retired IDs consolidated into one new
    #: identity. Kept apart from `nodes_replaced` because a merge is not a
    #: sequence of one-to-one replacements -- two retirements landing on one
    #: registry row have to be planned, reviewed and applied as one operation.
    nodes_merged: list[dict] = field(default_factory=list)
    row_changes: list[RowChange] = field(default_factory=list)
    removals: list[Removal] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    #: Bounded exceptions a Decision grants to this migration only, carried into
    #: the GUP so the Reviewer sees the exact scope it is approving.
    exceptions: list[dict] = field(default_factory=list)

    @property
    def blocks_approval(self) -> bool:
        return any(f["severity"] == "error" for f in self.findings)

    def finding(self, rule: str, severity: str, detail: str, **extra) -> None:
        self.findings.append({"rule": rule, "severity": severity, "detail": detail, **extra})


def _index_of(canonical_row, total: int) -> int | None:
    """`canonical_row` is the 1-based CSV line including the header."""
    try:
        index = int(str(canonical_row).strip()) - 2
    except (TypeError, ValueError):
        return None
    return index if 0 <= index < total else None


def _superseding_siblings(decision_paths: list) -> dict[str, str]:
    """Map each superseded Decision ID to the approved Decision replacing it.

    WORK_QUEUES 1.7: a migration cites the active reissue only, never both it
    and a superseded predecessor. The whole Decision store is read rather than
    only the named paths, because the predecessor is exactly what a caller
    naming the wrong file would not have passed.
    """
    replaced: dict[str, str] = {}
    for directory in sorted({Path(path).resolve().parent for path in decision_paths}):
        for candidate in sorted(directory.glob("DEC-*.yaml")):
            document = yaml.safe_load(candidate.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                continue
            if (document.get("status") or "").strip() != "approved":
                continue
            predecessor = str(document.get("supersedes") or "").strip()
            if predecessor:
                replaced[predecessor] = str(document.get("id") or candidate.stem)
    return replaced


def _check_understood_shape(block: dict, decision_id: str, plan: DecisionMigration) -> None:
    """Report migration instructions this planner cannot read.

    A Decision states its operations in a shape the planner parses by key name.
    When a Decision uses a different vocabulary the unread keys are operations
    that silently do not happen: the plan comes out *short* rather than wrong,
    which is far harder to notice than a bad value. DEC-2026-0030 enumerated a
    registry row replacement, a canonical node row replacement, and two repoints
    spelled `physical_csv_row`/`from_id`/`to_id`; the planner produced a
    migration missing all four and said so only because a row number came back
    None. Deciding that an unread key means the same as one it reads is the
    Architect's call to authorize, not the Builder's to guess.
    """
    for key in sorted(block):
        if key in UNDERSTOOD_MIGRATION_KEYS or key in DOCUMENTARY_MIGRATION_KEYS:
            continue
        plan.finding(
            "migration_instruction_not_understood",
            "error",
            f"{decision_id} carries canonical_migration.{key}, which this planner does not "
            f"read. Any operation it enumerates would be dropped without a trace.",
        )
    for position, entry in enumerate(block.get("endpoint_repoints") or [], start=1):
        if not isinstance(entry, dict):
            continue
        unknown = sorted(set(entry) - UNDERSTOOD_REPOINT_KEYS)
        if unknown:
            plan.finding(
                "migration_repoint_key_not_understood",
                "error",
                f"{decision_id} endpoint_repoints[{position}] carries "
                f"{', '.join(unknown)}, which this planner does not read. It reads "
                f"canonical_row, field, from, to, label.",
            )


def _plan_endpoint_repoints(
    canonical: CanonicalEdges, block: dict, decision_id: str, plan: DecisionMigration
) -> None:
    for entry in block.get("endpoint_repoints") or []:
        index = _index_of(entry.get("canonical_row"), len(canonical.rows))
        if index is None:
            plan.finding(
                "migration_row_out_of_range",
                "error",
                f"{decision_id} names canonical row {entry.get('canonical_row')}, which the "
                f"canonical graph does not have ({len(canonical.rows)} rows)",
            )
            continue

        row = canonical.rows[index]
        field_name = str(entry.get("field") or "").strip()
        expected = str(entry.get("from") or "").strip()
        actual = row.get(field_name, "")
        if actual != expected:
            # The decision was written against a corpus state. If the row no
            # longer holds what it named, applying the change blind would edit
            # something nobody ruled on.
            plan.finding(
                "migration_row_does_not_match_decision",
                "error",
                f"{decision_id} expects canonical row {entry.get('canonical_row')} to carry "
                f"{field_name}={expected!r}, but it carries {actual!r}. The decision was written "
                f"against a different corpus state; it needs re-issuing, not reinterpreting.",
                canonical_row=entry.get("canonical_row"),
            )
            continue

        # Validate before_assertion if present (DEC-2026-0025 style)
        before_assertion = entry.get("before_assertion") or {}
        if before_assertion:
            for field, expected_value in before_assertion.items():
                actual_value = row.get(field, "")
                if actual_value != expected_value:
                    plan.finding(
                        "migration_before_assertion_mismatch",
                        "error",
                        f"{decision_id} expects canonical row {entry.get('canonical_row')} to have "
                        f"{field}={expected_value!r} in before_assertion, but it carries {actual_value!r}",
                        canonical_row=entry.get("canonical_row"),
                    )
                    break
            else:
                # Only continue if we didn't break (i.e., all fields matched)
                pass
            # If any field mismatched, skip this entry
            if any(
                row.get(field, "") != expected_value
                for field, expected_value in before_assertion.items()
            ):
                continue

        changes = {field_name: (expected, str(entry.get("to") or "").strip())}
        label_field = field_name.replace("_id", "_label")
        new_label = str(entry.get("label") or "").strip()
        if new_label and row.get(label_field, "") != new_label:
            changes[label_field] = (row.get(label_field, ""), new_label)

        plan.row_changes.append(
            RowChange(
                canonical_row=index + 2,
                canonical_index=index,
                kind="endpoint_repoint",
                changes=changes,
                authority=decision_id,
                before=dict(row),
            )
        )


def _plan_label_normalizations(
    canonical: CanonicalEdges, block: dict, decision_id: str, plan: DecisionMigration
) -> None:
    key = "endpoint_label_normalizations_without_repoint"
    for entry in block.get(key) or []:
        index = _index_of(entry.get("canonical_row"), len(canonical.rows))
        if index is None:
            plan.finding(
                "migration_row_out_of_range",
                "error",
                f"{decision_id} names canonical row {entry.get('canonical_row')} for a label "
                f"normalization, which the canonical graph does not have",
            )
            continue
        row = canonical.rows[index]
        field_name = str(entry.get("field") or "").strip()
        value = str(entry.get("value") or "").strip()
        before = row.get(field_name, "")
        if before == value:
            plan.finding(
                "migration_label_already_correct",
                "info",
                f"canonical row {index + 2} already carries {field_name}={value!r}; "
                f"{decision_id} asks for no change here.",
                canonical_row=index + 2,
            )
            continue
        plan.row_changes.append(
            RowChange(
                canonical_row=index + 2,
                canonical_index=index,
                kind="label_normalization",
                changes={field_name: (before, value)},
                authority=decision_id,
                before=dict(row),
                note="label only; the endpoint ID and the assertion are unchanged",
            )
        )


def _plan_citation_revisions(
    canonical: CanonicalEdges, entries: list, decision_id: str, plan: DecisionMigration
) -> None:
    """DEC-2026-0016 names its rows by assertion, not by row number.

    That is the safer form -- an assertion key survives renumbering -- but it
    means the row has to be found, and finding none or several is a defect
    rather than something to resolve by picking one.
    """
    for entry in entries:
        spec = entry.get("assertion") or {}
        wanted = tuple(str(spec.get(f) or "") for f in _IDENTITY_FIELDS)
        matches = [
            i
            for i, row in enumerate(canonical.rows)
            if tuple(row.get(f, "") for f in _IDENTITY_FIELDS) == wanted
        ]
        described = f"{wanted[0]} {wanted[1]} {wanted[2]} aspect={wanted[3]!r}"
        if not matches:
            plan.finding(
                "migration_assertion_not_found",
                "error",
                f"{decision_id} corrects the page of {described}, which is not in the canonical "
                f"graph",
            )
            continue
        if len(matches) > 1:
            plan.finding(
                "migration_assertion_ambiguous",
                "error",
                f"{decision_id} corrects the page of {described}, which matches "
                f"{len(matches)} canonical rows: {[i + 2 for i in matches]}",
            )
            continue

        index = matches[0]
        row = canonical.rows[index]
        expected = str(entry.get("from_page") or "").strip()
        if row.get("page", "") != expected:
            plan.finding(
                "migration_row_does_not_match_decision",
                "error",
                f"{decision_id} expects {described} to cite page {expected!r}, but canonical row "
                f"{index + 2} cites {row.get('page', '')!r}",
                canonical_row=index + 2,
            )
            continue
        plan.row_changes.append(
            RowChange(
                canonical_row=index + 2,
                canonical_index=index,
                kind="citation_correction",
                changes={"page": (expected, str(entry.get("to_page") or "").strip())},
                authority=decision_id,
                before=dict(row),
                note="packet marker governs the printed page (SOURCE_MARKDOWN 1.1)",
            )
        )


def _plan_merged_assertion(
    canonical: CanonicalEdges, block: dict, decision_id: str, plan: DecisionMigration
) -> None:
    merged = block.get("merged_assertion")
    if not merged:
        return
    removed = _index_of(merged.get("removed_canonical_row"), len(canonical.rows))
    surviving = _index_of(merged.get("surviving_canonical_row"), len(canonical.rows))
    if removed is None or surviving is None:
        plan.finding(
            "migration_row_out_of_range",
            "error",
            f"{decision_id} merges canonical rows "
            f"{merged.get('removed_canonical_row')} and {merged.get('surviving_canonical_row')}, "
            f"at least one of which the canonical graph does not have",
        )
        return

    losing = canonical.rows[removed]
    plan.removals.append(
        Removal(
            canonical_row=removed + 2,
            canonical_index=removed,
            surviving_row=surviving + 2,
            identity=str(merged.get("identity") or ""),
            preserved={
                "book": losing.get("book", ""),
                "page": losing.get("page", ""),
                "section": losing.get("section", ""),
            },
            authority=decision_id,
        )
    )


def _audit(canonical: CanonicalEdges, plan: DecisionMigration) -> None:
    """Apply the plan to a copy and look for identity the migration destroys."""
    after = [dict(row) for row in canonical.rows]
    for change in plan.row_changes:
        for field_name, (_, new_value) in change.changes.items():
            after[change.canonical_index][field_name] = new_value

    removed_indices = {r.canonical_index for r in plan.removals}
    seen: dict[tuple, int] = {}
    for index, row in enumerate(after):
        if index in removed_indices:
            continue
        key = assertion_key(row)
        first = seen.get(key)
        if first is None:
            seen[key] = index
            continue
        # A duplicate that already existed is not this migration's doing.
        was_duplicate = assertion_key(canonical.rows[first]) == assertion_key(
            canonical.rows[index]
        )
        plan.finding(
            "migration_creates_duplicate_assertion" if not was_duplicate
            else "migration_preserves_existing_duplicate",
            "error" if not was_duplicate else "warning",
            f"after this migration canonical rows {first + 2} and {index + 2} share the "
            f"five-field assertion key {key}"
            + ("" if not was_duplicate else "; they already did before it"),
            canonical_row=index + 2,
        )

    for change in plan.row_changes:
        if change.kind == "label_normalization" and change.touches_identity:
            plan.finding(
                "migration_label_change_touches_identity",
                "error",
                f"canonical row {change.canonical_row} is listed as a label normalization but "
                f"the change set includes an assertion-key field",
                canonical_row=change.canonical_row,
            )
        if change.kind == "citation_correction" and change.touches_identity:
            plan.finding(
                "migration_citation_change_touches_identity",
                "error",
                f"canonical row {change.canonical_row} is listed as a citation correction but "
                f"the change set includes an assertion-key field",
                canonical_row=change.canonical_row,
            )

    # Check that no retired node ID remains in any canonical endpoint after migration
    for replacement in plan.nodes_replaced:
        if not replacement.get("require_no_remaining_retired_endpoints", True):
            continue
        retired_id = replacement["retired_id"]
        # Check the after state for any remaining usage
        for index, row in enumerate(after):
            if index in removed_indices:
                continue
            if row.get("source_id") == retired_id or row.get("target_id") == retired_id:
                plan.finding(
                    "migration_retired_id_still_present",
                    "error",
                    f"After migration, retired ID {retired_id!r} still appears in canonical row {index + 2} "
                    f"(source_id: {row.get('source_id')}, target_id: {row.get('target_id')})",
                    canonical_row=index + 2,
                )
                break


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def plan_from_decisions(
    canonical: CanonicalEdges,
    decision_paths: list[Path],
    registry=None,
    repo_root: Path | None = None,
    ruleset_id: str = "",
) -> DecisionMigration:
    """Plan every canonical change the named approved decisions enumerate."""
    plan = DecisionMigration()
    #: Decisions that revise another Decision's proposals, or bound this
    #: migration. Deferred to a second pass: a revision must see every earlier
    #: proposal regardless of the order the Decisions were named.
    revising: list[tuple[str, dict]] = []
    prohibited_identities: dict[str, str] = {}
    replaced_by = _superseding_siblings(decision_paths)

    for path in decision_paths:
        path = Path(path)
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            continue
        decision_id = document.get("id") or path.stem
        if (document.get("status") or "").strip() != "approved":
            plan.finding(
                "migration_decision_not_approved",
                "error",
                f"{decision_id} has status {document.get('status')!r}; only an approved decision "
                f"authorizes a migration",
            )
            continue
        # WORK_QUEUES 1.2 condition 4. A Decision from another ruleset, or one
        # that does not claim to require a migration, is not authority for this
        # artifact however approved it is.
        decision_ruleset = str(document.get("ruleset_id") or "").strip()
        if ruleset_id and decision_ruleset and decision_ruleset != ruleset_id:
            plan.finding(
                "migration_decision_wrong_ruleset",
                "error",
                f"{decision_id} belongs to ruleset {decision_ruleset!r}, not {ruleset_id!r}",
            )
            continue
        if document.get("migration_required") is not True:
            plan.finding(
                "migration_decision_requires_no_migration",
                "error",
                f"{decision_id} declares migration_required="
                f"{document.get('migration_required')!r}; it does not authorize canonical work",
            )
            continue
        if decision_id in plan.decisions:
            plan.finding(
                "migration_decision_listed_twice",
                "error",
                f"{decision_id} is named more than once; authority must be unique",
            )
            continue
        if decision_id in replaced_by:
            plan.finding(
                "migration_decision_superseded",
                "error",
                f"{decision_id} is superseded by {replaced_by[decision_id]}; WORK_QUEUES 1.7 "
                f"makes only the leaf of a Decision reissue lineage usable as migration "
                f"authority. Cite {replaced_by[decision_id]} instead.",
            )
            continue

        plan.decisions.append(decision_id)
        try:
            relative = str(path.resolve().relative_to(Path(repo_root).resolve()))
        except (ValueError, TypeError):
            relative = str(path)
        # Normalize path separators to forward slashes
        relative = relative.replace("\\", "/")
        plan.decision_inputs.append(
            {
                "id": decision_id,
                "path": relative,
                "checksum": _sha256(path),
            }
        )

        for node in document.get("new_nodes_authorized") or []:
            node_id = str(node.get("id") or "").strip()
            entry = {
                "proposed_id": node_id,
                "proposed_label": str(node.get("label") or "").strip(),
                "kind": str(node.get("kind") or "").strip(),
                "basis": str(node.get("basis") or "").strip(),
                "authority": decision_id,
                "action": "add_to_nodes_csv_after_approval",
            }
            if registry is not None and node_id in registry:
                plan.finding(
                    "migration_node_already_canonical",
                    "error",
                    f"{decision_id} authorizes {node_id!r} as a new node, but the registry "
                    f"already has it",
                )
                entry["already_canonical"] = True
            plan.nodes_added.append(entry)

        for node_id, disposition in (document.get("node_dispositions") or {}).items():
            if not isinstance(disposition, dict):
                continue
            label = str(disposition.get("canonical_label") or "").strip()
            if not label:
                continue
            current = ""
            if registry is not None and node_id in registry:
                current = registry.nodes[node_id].label
            if current == label:
                continue
            plan.nodes_relabelled.append(
                {
                    "node_id": str(node_id),
                    "from_label": current,
                    "to_label": label,
                    "disposition": str(disposition.get("disposition") or "").strip(),
                    "authority": decision_id,
                    "action": "update_label_in_nodes_csv_after_approval",
                }
            )

        # Handle identity_disposition (DEC-2026-0024 style)
        _plan_identity_disposition(document, decision_id, plan, registry)

        # Handle legacy_row_disposition (DEC-2026-0024 style)
        _plan_legacy_row_removal(canonical, document, decision_id, plan)

        block = document.get("canonical_migration") or {}
        _check_understood_shape(block, decision_id, plan)
        _plan_endpoint_repoints(canonical, block, decision_id, plan)
        _plan_label_normalizations(canonical, block, decision_id, plan)
        _plan_merged_assertion(canonical, block, decision_id, plan)
        _plan_node_id_replacements(canonical, block, decision_id, plan, registry)
        _plan_node_id_merges(canonical, block, decision_id, plan, registry)

        scope = document.get("migration_scope") or {}
        _plan_citation_revisions(
            canonical, scope.get("canonical_citation_revisions") or [], decision_id, plan
        )

        _check_declared_counts(document, block, decision_id, plan)

        if document.get("migration_revision") or document.get("legacy_polarity_exception"):
            revising.append((decision_id, document))
        banned = str(
            (document.get("default_and_exception_mapping") or {}).get(
                "prohibited_generic_identity"
            )
            or ""
        ).strip()
        if banned:
            prohibited_identities[banned] = decision_id

    for decision_id, document in revising:
        _apply_migration_revision(document, decision_id, plan, registry)
        _apply_polarity_exception(document, decision_id, plan)

    _check_prohibited_identities(plan, prohibited_identities)

    _audit(canonical, plan)

    plan.counts = {
        "decisions": len(plan.decisions),
        "nodes_added": len(plan.nodes_added),
        "nodes_relabelled": len(plan.nodes_relabelled),
        "nodes_replaced": len(plan.nodes_replaced),
        "nodes_merged": len(plan.nodes_merged),
        "retired_by_merge": sum(len(m["retired_nodes"]) for m in plan.nodes_merged),
        "endpoint_repoints": sum(
            1 for c in plan.row_changes if c.kind == "endpoint_repoint"
        ),
        "label_normalizations": sum(
            1 for c in plan.row_changes if c.kind == "label_normalization"
        ),
        "citation_corrections": sum(
            1 for c in plan.row_changes if c.kind == "citation_correction"
        ),
        "rows_removed": len(plan.removals),
        "canonical_row_net_change": -len(plan.removals),
    }
    return plan


def validation_report(
    plan: DecisionMigration,
    gup_id: str,
    envelope: dict,
    tool: dict,
    test_result: dict,
    operation_model: str | None = None,
) -> dict:
    """The external validation component of the bundle.

    Written before the GUP, because the GUP names it by checksum. It repeats the
    baseline identifiers rather than referring back to the GUP so that it can be
    verified on its own -- under the direct model it is one of only two
    components the Approved manifest carries, so standing alone matters more,
    not less.
    """
    report = {
        "gup_id": gup_id,
        "artifact_kind": "decision_migration",
        "lineage_id": envelope["lineage_id"],
        "revision": envelope["revision"],
        "authority": list(plan.decisions),
        "decision_inputs": plan.decision_inputs,
        "canonical_source": envelope["canonical_source"],
        "canonical_checksum": envelope["canonical_checksum"],
        "canonical_rows_read": envelope["canonical_rows_read"],
        "tool": {"name": tool["name"], "version": tool["version"]},
        "test_result": test_result,
        "status": "blocked" if plan.blocks_approval else "proposed",
        "approval_ready": not plan.blocks_approval,
        "counts": plan.counts,
        "summary": {
            "errors": sum(1 for f in plan.findings if f["severity"] == "error"),
            "warnings": sum(1 for f in plan.findings if f["severity"] == "warning"),
            "info": sum(1 for f in plan.findings if f["severity"] == "info"),
        },
        "findings": plan.findings,
        "rows_changed": sorted(c.canonical_row for c in plan.row_changes),
        "rows_removed": sorted(r.canonical_row for r in plan.removals),
        "nodes_replaced": len(plan.nodes_replaced),
    }
    if operation_model in DIRECT_MODELS:
        report["operation_model"] = operation_model
        report["registry_source"] = envelope["registry_source"]
        report["registry_checksum"] = envelope["registry_checksum"]
        report["registry_rows_read"] = envelope["registry_rows_read"]
        report["direct_operations"] = {
            "registry_additions": len(plan.nodes_added),
            "registry_replacements": len(plan.nodes_replaced),
            "registry_merges": len(plan.nodes_merged),
            "registry_rows_retired_by_merge": sum(
                len(m["retired_nodes"]) for m in plan.nodes_merged
            ),
            "canonical_endpoint_repoints": len(plan.row_changes),
            "canonical_row_removals": len(plan.removals),
            "aliases_created": 0,
            "semantic_reinterpretations": 0,
        }
    return report


def _removal_document(removal: Removal) -> dict:
    """One removal, in the shape its authorizing Decision permits.

    A merge (DEC-2026-0015) retires a row *because* a surviving row carries its
    locus, so naming that row and the preserved provenance is the justification.
    A legacy-row removal (DEC-2026-0024) has no replacement at all, and that
    Decision expressly rejects a replacement or surviving-row provenance claim.
    Emitting one shape for both meant every no-replacement removal asserted a
    survivor it did not have, which is what blocked r02 and r03 of this lineage.

    Both shapes carry `before`: the exact image the removal was verified
    against, without which a Reviewer cannot tell an approved removal from a
    row number.
    """
    if removal.surviving_row is None:
        return {
            "canonical_row": removal.canonical_row,
            "replacement_edge": None,
            "authority": removal.authority,
            "action": removal.action,
            "before": removal.before,
        }
    return {
        "canonical_row": removal.canonical_row,
        "surviving_row": removal.surviving_row,
        "identity": removal.identity,
        "provenance_preserved_on_surviving_row": removal.preserved,
        "authority": removal.authority,
        "action": removal.action,
        "before": removal.before,
    }


#: WORK_QUEUES 1.8 / DEC-2026-0035. Registry addition, one-to-one identity
#: replacement, paired endpoint compare-and-swap, exact no-replacement removal.
DIRECT_MODEL = "decision_migration_v1"

#: WORK_QUEUES 1.9 / DEC-2026-0036. Two-or-more-to-one registry merges and
#: their paired endpoint repoints, and nothing else. A merge is not a sequence
#: of v1 replacements, which is why it needs a model of its own rather than a
#: widened v1.
DIRECT_MODEL_V2 = "decision_migration_v2"

DIRECT_MODELS = (DIRECT_MODEL, DIRECT_MODEL_V2)


def _repoint_objections(plan: DecisionMigration) -> list[str]:
    """Row changes neither direct model can execute. Shared by both."""
    objections: list[str] = []
    for change in plan.row_changes:
        if change.kind != "endpoint_repoint":
            objections.append(
                f"canonical row {change.canonical_row} is a {change.kind}; the model "
                f"executes only endpoint_repoint"
            )
            continue
        fields = set(change.changes)
        if fields not in ({"source_id", "source_label"}, {"target_id", "target_label"}):
            objections.append(
                f"canonical row {change.canonical_row} changes {sorted(fields)}; the model "
                f"requires exactly one endpoint ID paired with its own label"
            )
    return objections


def direct_model_objections(
    plan: DecisionMigration, model: str = DIRECT_MODEL
) -> list[str]:
    """Why this plan cannot be published under the named direct model.

    Both models are deliberately narrow. v1 authorizes a registry addition, a
    one-to-one identity replacement with retirement, a paired endpoint
    compare-and-swap and an exact no-replacement removal; v2 authorizes closed
    two-or-more-to-one merges and their paired repoints, and nothing else.
    Each Decision expressly forbids widening its model. An empty list means the
    plan is inside the one named.

    Declaring a model on a plan that does not fit would tell the Integrator it
    may execute operations nobody authorized, so the answer is a refusal rather
    than a silently narrower artifact.
    """
    objections = _repoint_objections(plan)

    if model == DIRECT_MODEL_V2:
        if not plan.nodes_merged:
            objections.append(
                "no node merge; v2 exists to execute merges and has nothing else to do"
            )
        for name, entries in (
            ("addition", plan.nodes_added),
            ("relabel", plan.nodes_relabelled),
            ("one-to-one replacement", plan.nodes_replaced),
        ):
            if entries:
                objections.append(
                    f"{len(entries)} node {name}(s); v2 executes merges only"
                )
        if plan.removals:
            objections.append(
                f"{len(plan.removals)} canonical removal(s); v2 executes no removals"
            )
        return objections

    if plan.nodes_relabelled:
        objections.append(
            f"{len(plan.nodes_relabelled)} relabel(s); the model has no relabel operation"
        )
    if plan.nodes_merged:
        objections.append(
            f"{len(plan.nodes_merged)} node merge(s); v1 executes one-to-one "
            f"replacements only. A merge is {DIRECT_MODEL_V2} work."
        )
    for removal in plan.removals:
        if removal.surviving_row is not None:
            objections.append(
                f"canonical row {removal.canonical_row} is removed against surviving row "
                f"{removal.surviving_row}; the model executes only no-replacement removals"
            )
    return objections


def to_gup(
    plan: DecisionMigration,
    gup_id: str,
    envelope: dict,
    tool: dict,
    test_result: dict,
    operation_model: str | None = None,
) -> dict:
    """Render the plan as a GUP-shaped artifact for Review.

    Every row change carries the full before-state, not just the delta, so the
    Reviewer can check the ruling against the row as it stands without opening
    the canonical file alongside. WORK_QUEUES 1.2 condition 6 requires exactly
    that: a Decision ID never substitutes for the rows to be reviewed.

    The lineage envelope is what makes this artifact routable without a GUR. A
    decision migration is planned against mutable repository state, so the
    Decision files and the canonical baseline are pinned by checksum: a plan
    reviewed against one before-state must not be applied to another.
    """
    direct = operation_model in DIRECT_MODELS
    if direct:
        objections = direct_model_objections(plan, operation_model)
        if objections:
            raise ValueError(
                f"{gup_id} cannot declare {operation_model}: " + "; ".join(objections)
            )

    document = {
        "schema_version": "1.0",
        "id": gup_id,
        "status": "blocked" if plan.blocks_approval else "proposed",
        "ruleset_id": envelope["ruleset_id"],
        "book_id": envelope["book_id"],
        "source_id": envelope["source_id"],
        "packet_id": envelope["packet_id"],
        "constitution_version": envelope["constitution_version"],
        "artifact_kind": "decision_migration",
        # Stable across every revision. `packet_id` cannot group these: several
        # independent migrations all carry `cross-packet`.
        "lineage_id": envelope["lineage_id"],
        "revision": envelope["revision"],
        "supersedes": envelope.get("supersedes"),
        "authority": list(plan.decisions),
        "validation_report": envelope["validation_report"],
        "validation_report_checksum": envelope["validation_report_checksum"],
        "handoff": {
            "next_role": "reviewer",
            "readiness": "blocked" if plan.blocks_approval else "ready",
            "reason": (
                f"{len(plan.row_changes)} canonical row change(s), {len(plan.nodes_added)} node "
                f"addition(s), {len(plan.nodes_relabelled)} relabel(s), "
                f"{len(plan.removals)} removal(s) enumerated by "
                f"{', '.join(plan.decisions)}"
            ),
            "blocking_ids": sorted(
                {str(f.get("canonical_row")) for f in plan.findings
                 if f["severity"] == "error" and f.get("canonical_row")}
            ),
        },
        "provenance": {
            "builder_tool": tool["name"],
            "builder_version": tool["version"],
            "test_result": test_result,
            # No `gur_id` or `gur_checksum`. Their absence is the point: this
            # artifact's root is the Decision record, and carrying either would
            # claim a packet lineage it does not have.
            "decision_inputs": plan.decision_inputs,
            "canonical_source": envelope["canonical_source"],
            "canonical_checksum": envelope["canonical_checksum"],
            "canonical_rows_read": envelope["canonical_rows_read"],
        },
        "approval_ready": not plan.blocks_approval,
        "node_changes": {
            "additions_proposed": plan.nodes_added,
            "relabels": plan.nodes_relabelled,
            "replacements": plan.nodes_replaced,
        },
        "canonical_changes": [
            {
                "canonical_row": c.canonical_row,
                "kind": c.kind,
                "authority": c.authority,
                "changes": {f: {"from": b, "to": a} for f, (b, a) in sorted(c.changes.items())},
                "touches_assertion_identity": c.touches_identity,
                "before": c.before,
            }
            for c in sorted(plan.row_changes, key=lambda c: (c.kind, c.canonical_row))
        ],
        "canonical_removals": [_removal_document(r) for r in plan.removals],
        "bounded_exceptions": plan.exceptions,
        "counts": plan.counts,
        "findings": plan.findings,
        "validation_summary": {
            "errors": sum(1 for f in plan.findings if f["severity"] == "error"),
            "warnings": sum(1 for f in plan.findings if f["severity"] == "warning"),
        },
    }

    if direct:
        document["operation_model"] = operation_model
        if operation_model == DIRECT_MODEL_V2:
            # v1 declares `additionalProperties: false` on node_changes, so the
            # merge array belongs only to the model that executes merges.
            document["node_changes"]["merges"] = plan.nodes_merged
        # The registry is the second mutable baseline this model writes to, so
        # a plan reviewed against one registry state must not be applied to
        # another. The canonical baseline was already pinned above.
        for field_name in ("registry_source", "registry_checksum", "registry_rows_read"):
            document["provenance"][field_name] = envelope[field_name]
    else:
        # Prose the direct schema forbids, because a note is not an operation
        # and the Integrator must not have to decide which is which.
        document["node_changes"]["note"] = (
            "Registry writes belong to the Integrator. These are proposals the "
            "Reviewer confirms against source and local neighbourhood."
        )
        if plan.nodes_merged:
            document["node_changes"]["merges"] = plan.nodes_merged
        for rendered, change in zip(
            document["canonical_changes"],
            sorted(plan.row_changes, key=lambda c: (c.kind, c.canonical_row)),
        ):
            rendered["note"] = change.note

    return document


def _plan_node_id_replacements(
    canonical: CanonicalEdges, block: dict, decision_id: str, plan: DecisionMigration, registry=None
) -> None:
    """Plan node ID replacements from canonical_migration.node_id_replacements.
    
    Each replacement retires one node ID and replaces it with another. This validates:
    - The retiring node exists in the registry
    - The replacement node does NOT exist in the registry (it's being added)
    - Every canonical edge endpoint using the retiring ID is explicitly enumerated
      in endpoint_repoints
    - No endpoint remains with the retiring ID after all repoints are applied
    - No duplicate assertion key is created
    """
    replacements = block.get("node_id_replacements") or []
    if not replacements:
        return

    for entry in replacements:
        retired_id = str(entry.get("retired_id") or "").strip()
        retired_label = str(entry.get("retired_label") or "").strip()
        canonical_id = str(entry.get("canonical_id") or "").strip()
        canonical_label = str(entry.get("canonical_label") or "").strip()
        kind = str(entry.get("kind") or "").strip()
        registry_action = str(entry.get("registry_action") or "").strip()
        require_no_remaining = entry.get("require_no_remaining_retired_endpoints", True)

        if not retired_id or not canonical_id:
            plan.finding(
                "migration_node_replacement_missing_id",
                "error",
                f"{decision_id} node_id_replacements entry missing retired_id or canonical_id",
            )
            continue

        # Validate the retiring node exists in registry
        if registry is not None and retired_id not in registry:
            plan.finding(
                "migration_retiring_node_not_in_registry",
                "error",
                f"{decision_id} retires {retired_id!r} but it is not in the canonical registry",
            )
            continue

        # Validate the replacement node does NOT exist in registry
        if registry is not None and canonical_id in registry:
            plan.finding(
                "migration_replacement_node_already_exists",
                "error",
                f"{decision_id} adds {canonical_id!r} but it already exists in the canonical registry",
            )
            continue

        # Collect all canonical rows that use the retiring ID
        retired_as_source = [
            i for i, row in enumerate(canonical.rows)
            if row.get("source_id") == retired_id
        ]
        retired_as_target = [
            i for i, row in enumerate(canonical.rows)
            if row.get("target_id") == retired_id
        ]
        all_retired_endpoints = retired_as_source + retired_as_target

        if require_no_remaining and all_retired_endpoints:
            # Check that all these endpoints are explicitly enumerated in endpoint_repoints
            enumerated_rows = set()
            for repoint in block.get("endpoint_repoints") or []:
                row_num = repoint.get("canonical_row")
                if row_num is not None:
                    try:
                        enumerated_rows.add(int(row_num) - 2)  # Convert to 0-based index
                    except (TypeError, ValueError):
                        pass

            missing = [i + 2 for i in all_retired_endpoints if i not in enumerated_rows]
            if missing:
                plan.finding(
                    "migration_retired_endpoint_not_enumerated",
                    "error",
                    f"{decision_id} retires {retired_id!r} which is used in canonical rows {missing}, "
                    f"but these rows are not enumerated in endpoint_repoints",
                )
                continue

        plan.nodes_replaced.append({
            "retired_id": retired_id,
            "retired_label": retired_label,
            "canonical_id": canonical_id,
            "canonical_label": canonical_label,
            "kind": kind,
            "registry_action": registry_action,
            "require_no_remaining_retired_endpoints": require_no_remaining,
            "authority": decision_id,
            "incident_canonical_rows": [i + 2 for i in all_retired_endpoints],
        })


def _plan_node_id_merges(
    canonical: CanonicalEdges,
    block: dict,
    decision_id: str,
    plan: DecisionMigration,
    registry=None,
) -> None:
    """DEC-2026-0032: two or more retired IDs consolidate into one new identity.

    Distinct from `node_id_replacements`, which retires exactly one ID for one
    successor. The Decision is explicit about why: a merge is not a sequence of
    ordinary replacements, and accepting a second retirement silently would
    invite duplicated registry or canonical state. So the whole merge is one
    operation, validated against the Decision's own closed incident set.

    Every check here is a refusal, never a repair. The Decision forbids
    discovering identities by label or prefix, so a set that does not match
    exactly is reported for reissue rather than reconciled.
    """
    merges = block.get("node_id_merges") or []
    if not merges:
        return

    for position, entry in enumerate(merges, start=1):
        if not isinstance(entry, dict):
            plan.finding(
                "migration_node_merge_malformed",
                "error",
                f"{decision_id} node_id_merges[{position}] is not a mapping",
            )
            continue

        canonical_id = str(entry.get("canonical_id") or "").strip()
        canonical_label = str(entry.get("canonical_label") or "").strip()
        kind = str(entry.get("kind") or "").strip()
        retired = entry.get("retired_nodes") or []
        label = f"{decision_id} node_id_merges[{position}]"

        if not canonical_id or not canonical_label or not kind:
            plan.finding(
                "migration_node_merge_malformed",
                "error",
                f"{label} omits canonical_id, canonical_label or kind",
            )
            continue

        retired_ids = [str(n.get("id") or "").strip() for n in retired if isinstance(n, dict)]
        if len(retired) < 2 or len(set(retired_ids)) < 2 or "" in retired_ids:
            plan.finding(
                "migration_node_merge_needs_two_retired_ids",
                "error",
                f"{label} names {len(set(retired_ids))} distinct retired ID(s); a merge "
                f"consolidates at least two. One retirement is a node_id_replacement.",
            )
            continue

        if registry is not None and canonical_id in registry:
            plan.finding(
                "migration_merge_canonical_id_already_exists",
                "error",
                f"{label} merges into {canonical_id!r}, which is already in the registry",
            )
            continue

        # Each retired node must be exactly where and what the Decision says.
        mismatched = False
        for node in retired:
            node_id = str(node.get("id") or "").strip()
            if registry is not None and node_id not in registry:
                plan.finding(
                    "migration_merge_retired_node_not_in_registry",
                    "error",
                    f"{label} retires {node_id!r}, which is not in the canonical registry",
                )
                mismatched = True
                continue
            if registry is None:
                continue
            current = registry.nodes[node_id]
            declared_label = str(node.get("label") or "").strip()
            if declared_label and current.label != declared_label:
                plan.finding(
                    "migration_merge_retired_node_mismatch",
                    "error",
                    f"{label} expects {node_id!r} to carry label {declared_label!r}, but the "
                    f"registry has {current.label!r}. The Decision was written against a "
                    f"different registry state; it needs re-issuing, not reinterpreting.",
                )
                mismatched = True
            row_number = node.get("registry_csv_row")
            actual_row = registry.row_of(node_id) if hasattr(registry, "row_of") else None
            if row_number is not None and actual_row is not None and int(row_number) != actual_row:
                plan.finding(
                    "migration_merge_registry_row_moved",
                    "error",
                    f"{label} names registry row {row_number} for {node_id!r}, which now sits "
                    f"at row {actual_row}. The Decision was written against a different "
                    f"registry state; it needs re-issuing, not reinterpreting.",
                )
                mismatched = True
        if mismatched:
            continue

        # The closed incident set. Every declared row must resolve and name
        # exactly one retired endpoint, and the discovered set must match it
        # exactly -- a missing row would leave a retired ID in canonical, and an
        # extra one would repoint an assertion nobody ruled on.
        declared_rows = entry.get("incident_canonical_rows") or []
        expected_count = entry.get("expected_incident_row_count")
        if expected_count is not None and int(expected_count) != len(declared_rows):
            plan.finding(
                "migration_merge_incident_count_mismatch",
                "error",
                f"{label} declares expected_incident_row_count={expected_count} but "
                f"enumerates {len(declared_rows)} row(s); the Decision contradicts itself",
            )
            continue

        resolved: dict[int, int] = {}
        broken = False
        for row_number in declared_rows:
            index = _index_of(row_number, len(canonical.rows))
            if index is None:
                plan.finding(
                    "migration_row_out_of_range",
                    "error",
                    f"{label} names canonical row {row_number}, which the canonical graph "
                    f"does not have ({len(canonical.rows)} rows)",
                    canonical_row=row_number,
                )
                broken = True
                continue
            row = canonical.rows[index]
            hits = [f for f in ("source_id", "target_id") if row.get(f) in retired_ids]
            if len(hits) != 1:
                plan.finding(
                    "migration_merge_row_does_not_hold_a_retired_endpoint",
                    "error",
                    f"{label} names canonical row {row_number}, but it references "
                    f"{len(hits)} of the retired IDs rather than exactly one. The Decision "
                    f"was written against a different corpus state; it needs re-issuing, "
                    f"not reinterpreting.",
                    canonical_row=row_number,
                )
                broken = True
                continue
            resolved[int(row_number)] = index

        discovered = sorted(
            i + 2
            for i, row in enumerate(canonical.rows)
            if row.get("source_id") in retired_ids or row.get("target_id") in retired_ids
        )
        if discovered != sorted(int(r) for r in declared_rows):
            missing = sorted(set(discovered) - {int(r) for r in declared_rows})
            extra = sorted({int(r) for r in declared_rows} - set(discovered))
            plan.finding(
                "migration_merge_incident_set_not_closed",
                "error",
                f"{label} enumerates an incident set that does not match the corpus. "
                f"Rows holding a retired ID but not enumerated: {missing or 'none'}; rows "
                f"enumerated but not holding one: {extra or 'none'}. Leaving the first "
                f"behind would strand a retired identity in canonical.",
            )
            broken = True
        if broken:
            continue

        for row_number, index in sorted(resolved.items()):
            row = canonical.rows[index]
            role = "source" if row.get("source_id") in retired_ids else "target"
            plan.row_changes.append(
                RowChange(
                    canonical_row=row_number,
                    canonical_index=index,
                    kind="endpoint_repoint",
                    changes={
                        f"{role}_id": (row.get(f"{role}_id", ""), canonical_id),
                        f"{role}_label": (row.get(f"{role}_label", ""), canonical_label),
                    },
                    authority=decision_id,
                    before=dict(row),
                )
            )

        plan.nodes_merged.append(
            {
                "canonical_id": canonical_id,
                "canonical_label": canonical_label,
                "kind": kind,
                "retired_nodes": [
                    {
                        "id": str(n.get("id") or "").strip(),
                        "label": str(n.get("label") or "").strip(),
                        "registry_csv_row": n.get("registry_csv_row"),
                    }
                    for n in retired
                ],
                "registry_action": str(entry.get("registry_action") or "").strip(),
                "require_no_remaining_retired_endpoints": bool(
                    entry.get("require_no_remaining_retired_endpoints", True)
                ),
                "authority": decision_id,
                "incident_canonical_rows": sorted(resolved),
            }
        )


def _plan_identity_disposition(
    document: dict, decision_id: str, plan: DecisionMigration, registry=None
) -> None:
    """Plan node additions from identity_disposition (DEC-2026-0024 style)."""
    identity = document.get("identity_disposition") or {}
    canonical_id = str(identity.get("canonical_id") or "").strip()
    if not canonical_id:
        return

    canonical_label = str(identity.get("canonical_label") or "").strip()
    kind = str(identity.get("kind") or "").strip()
    prefix = str(identity.get("prefix") or "").strip()
    registry_action = str(identity.get("registry_action") or "").strip()

    if registry_action != "add":
        plan.finding(
            "migration_identity_disposition_unexpected_action",
            "error",
            f"{decision_id} identity_disposition has action {registry_action!r}, expected 'add'",
        )
        return

    entry = {
        "proposed_id": canonical_id,
        "proposed_label": canonical_label,
        "kind": kind,
        "basis": "decision_identity_disposition",
        "authority": decision_id,
        "action": "add_to_nodes_csv_after_approval",
    }
    if registry is not None and canonical_id in registry:
        plan.finding(
            "migration_identity_disposition_node_already_exists",
            "error",
            f"{decision_id} authorizes {canonical_id!r} via identity_disposition, but the registry "
            f"already has it",
        )
        entry["already_canonical"] = True
    plan.nodes_added.append(entry)


def _plan_legacy_row_removal(
    canonical: CanonicalEdges, document: dict, decision_id: str, plan: DecisionMigration
) -> None:
    """Plan row removals from legacy_row_disposition (DEC-2026-0024 style).

    `remove_exact_before_image` is a compare-and-swap, not a row-number delete.
    The Decision states the full 18 columns it ruled on; if canonical no longer
    carries exactly those, the row number now points at something nobody ruled
    on and the plan is stale. Deleting by index alone would silently retire the
    wrong assertion, which is unrecoverable once the bundle is integrated.
    """
    legacy = document.get("legacy_row_disposition") or {}
    action = str(legacy.get("action") or "").strip()
    if action != "remove_exact_before_image":
        return

    canonical_row = legacy.get("physical_csv_row")
    if canonical_row is None:
        plan.finding(
            "migration_legacy_row_disposition_missing_row",
            "error",
            f"{decision_id} legacy_row_disposition missing physical_csv_row",
        )
        return

    try:
        row_num = int(canonical_row)
    except (TypeError, ValueError):
        plan.finding(
            "migration_legacy_row_disposition_invalid_row",
            "error",
            f"{decision_id} legacy_row_disposition has invalid physical_csv_row: {canonical_row!r}",
        )
        return

    declared = legacy.get("before") or {}
    index = _index_of(row_num, len(canonical.rows))
    if index is None:
        plan.finding(
            "migration_row_out_of_range",
            "error",
            f"{decision_id} names canonical row {row_num} for removal, which the canonical "
            f"graph does not have ({len(canonical.rows)} rows)",
            canonical_row=row_num,
        )
        return

    row = canonical.rows[index]
    mismatched = sorted(
        name
        for name, expected in declared.items()
        if str(row.get(name, "")) != str(expected if expected is not None else "")
    )
    if mismatched:
        plan.finding(
            "migration_removal_before_image_mismatch",
            "error",
            f"{decision_id} names canonical row {row_num} for removal under "
            f"{action}, but the row differs from the stated before-image on "
            f"{', '.join(mismatched)}. The decision was written against a different corpus "
            f"state; it needs re-issuing, not reinterpreting.",
            canonical_row=row_num,
        )
        return

    plan.removals.append(
        Removal(
            canonical_row=row_num,
            canonical_index=index,
            surviving_row=None,
            # Deliberately empty. DEC-2026-0024 retires this row outright and
            # expressly rejects a replacement or surviving-row provenance claim,
            # so synthesizing an identity and a preserved locus from the row
            # being removed would manufacture exactly the claim it refused --
            # which is what REV-GUP-MIG-DEC-2026-0024-0025-r03-r01 blocked.
            identity="",
            preserved={},
            authority=decision_id,
            before=dict(row),
            action=action,
        )
    )


def _apply_migration_revision(
    document: dict, decision_id: str, plan: DecisionMigration, registry=None
) -> None:
    """Let a later Decision revise an earlier Decision's node proposal.

    DEC-2026-0026 supersedes the identity DEC-2026-0024 chose while leaving the
    rest of that Decision's operations intact. Expressing that as a fresh
    single-Decision migration would drop the retained operations; expressing it
    by editing DEC-2026-0024 would rewrite the decision record. So the revising
    Decision names the proposal to withdraw and the one to substitute, and this
    runs after every Decision is read so the result does not depend on the order
    the Decisions are passed on the command line.
    """
    revision = document.get("migration_revision") or {}
    change = revision.get("required_node_change") or {}
    if not change:
        return

    withdrawn = str(change.get("remove_proposal") or "").strip()
    if withdrawn:
        kept = [n for n in plan.nodes_added if n.get("proposed_id") != withdrawn]
        if len(kept) == len(plan.nodes_added):
            plan.finding(
                "migration_revision_withdraws_absent_proposal",
                "warning",
                f"{decision_id} withdraws the node proposal {withdrawn!r}, but no authority "
                f"Decision proposed it. Either the superseded Decision is missing from this "
                f"plan or the revision is already applied.",
            )
        plan.nodes_added = kept

    substitute = change.get("add_proposal") or {}
    node_id = str(substitute.get("id") or "").strip()
    if not node_id:
        return

    entry = {
        "proposed_id": node_id,
        "proposed_label": str(substitute.get("label") or "").strip(),
        "kind": str(substitute.get("kind") or "").strip(),
        "basis": "decision_migration_revision",
        "authority": decision_id,
        "action": "add_to_nodes_csv_after_approval",
    }
    if registry is not None and node_id in registry:
        plan.finding(
            "migration_revision_node_already_exists",
            "error",
            f"{decision_id} substitutes {node_id!r} as the canonical identity, but the "
            f"registry already has it",
        )
        entry["already_canonical"] = True
    plan.nodes_added.append(entry)


def _check_prohibited_identities(plan: DecisionMigration, prohibited: dict[str, str]) -> None:
    """Fail the plan if a Decision-prohibited node ID survives anywhere in it.

    A withdrawn proposal is only half the job. The prohibited ID must also not
    reach canonical as an endpoint, which is the part a hand-check misses.
    """
    for node_id, decision_id in sorted(prohibited.items()):
        sites: list[str] = []
        sites += [
            f"node proposal {n['proposed_id']}"
            for n in plan.nodes_added
            if n.get("proposed_id") == node_id
        ]
        sites += [
            f"node replacement {r.get('canonical_id')}"
            for r in plan.nodes_replaced
            if node_id in (r.get("canonical_id"), r.get("retired_id"))
        ]
        for change in plan.row_changes:
            for name, (before, after) in sorted(change.changes.items()):
                if node_id in (before, after):
                    sites.append(f"row {change.canonical_row} {name}")
        for removal in plan.removals:
            for name in ("source_id", "target_id"):
                if removal.before.get(name) == node_id:
                    sites.append(f"removed row {removal.canonical_row} {name}")
        if sites:
            plan.finding(
                "migration_prohibited_identity_present",
                "error",
                f"{decision_id} prohibits the identity {node_id!r}, but this plan still "
                f"carries it at: {', '.join(sites)}",
            )


def _apply_polarity_exception(
    document: dict, decision_id: str, plan: DecisionMigration
) -> None:
    """Record a Decision's bounded legacy-polarity exception and enforce its limits.

    DEC-2026-0026 permits two legacy rows to keep an unread polarity through an
    identity-only migration. The exception is worth nothing unless its stated
    bounds are checked, so every planned change on those rows is tested against
    the permitted field list, and the preserved values are re-read from the
    before-image rather than copied from the Decision.
    """
    exception = document.get("legacy_polarity_exception") or {}
    entries = exception.get("applies_only_to") or []
    if not entries:
        return

    permitted = {str(f) for f in exception.get("permitted_change_fields") or []}
    prohibited = {str(f) for f in exception.get("prohibited_change_fields") or []}
    by_row = {c.canonical_row: c for c in plan.row_changes}

    recorded: list[dict] = []
    for entry in entries:
        try:
            row_num = int(str(entry.get("canonical_row")).strip())
        except (TypeError, ValueError):
            plan.finding(
                "migration_exception_invalid_row",
                "error",
                f"{decision_id} grants a polarity exception for an unreadable canonical_row "
                f"{entry.get('canonical_row')!r}",
            )
            continue

        change = by_row.get(row_num)
        if change is None:
            plan.finding(
                "migration_exception_row_not_planned",
                "warning",
                f"{decision_id} grants a polarity exception for canonical row {row_num}, but "
                f"this plan changes nothing on that row",
                canonical_row=row_num,
            )
            continue

        overstepped = sorted(
            name
            for name in change.changes
            if (permitted and name not in permitted) or name in prohibited
        )
        if overstepped:
            plan.finding(
                "migration_exception_exceeded",
                "error",
                f"{decision_id} permits only {', '.join(sorted(permitted))} to change on "
                f"canonical row {row_num}, but this plan changes {', '.join(overstepped)}. The "
                f"exception is identity-only; it does not license a semantic edit.",
                canonical_row=row_num,
            )
            continue

        preserve = entry.get("preserve") or {}
        drifted = sorted(
            name
            for name, expected in preserve.items()
            if str(change.before.get(name, "")) != str(expected if expected is not None else "")
        )
        if drifted:
            plan.finding(
                "migration_exception_preserved_value_mismatch",
                "error",
                f"{decision_id} preserves {preserve} on canonical row {row_num}, but the row "
                f"carries a different value for {', '.join(drifted)}",
                canonical_row=row_num,
            )
            continue

        recorded.append(
            {
                "canonical_row": row_num,
                "authority": decision_id,
                "scope": "identity_only",
                "changed_fields": sorted(change.changes),
                # Re-read from the verified before-image, not copied from the
                # Decision: the GUP must state what canonical actually holds.
                "preserved": {
                    name: change.before.get(name, "") for name in sorted(preserve)
                },
            }
        )

    if recorded:
        plan.exceptions.append(
            {
                "kind": "legacy_polarity_exception",
                "authority": decision_id,
                "review_meaning": str(exception.get("review_meaning") or "").strip(),
                "later_source_audit": str(exception.get("later_source_audit") or "").strip(),
                "rows": recorded,
            }
        )


def _check_declared_counts(
    document: dict, block: dict, decision_id: str, plan: DecisionMigration
) -> None:
    """Compare what the decision says it does against what it enumerates.

    A decision states its own scope in `counts`. If the enumeration disagrees
    with the stated total, one of the two is wrong and the Builder should not
    pick. This is the check that would have caught a truncated list.
    """
    declared = block.get("counts") or {}
    # A merge enumerates its repoints inside `incident_canonical_rows` rather
    # than in `endpoint_repoints`, so both have to be counted or a Decision
    # that only merges looks like it contradicts itself.
    merge_repoints = sum(
        len(entry.get("incident_canonical_rows") or [])
        for entry in (block.get("node_id_merges") or [])
        if isinstance(entry, dict)
    )
    pairs = (
        (
            "canonical_rows_repointed",
            len(block.get("endpoint_repoints") or []) + merge_repoints,
        ),
        (
            "canonical_rows_label_normalized_without_repoint",
            len(block.get("endpoint_label_normalizations_without_repoint") or []),
        ),
        ("new_registry_rows", len(document.get("new_nodes_authorized") or [])),
    )
    for key, actual in pairs:
        if key not in declared:
            continue
        if int(declared[key]) != actual:
            plan.finding(
                "migration_declared_count_mismatch",
                "error",
                f"{decision_id} declares {key}={declared[key]} but enumerates {actual}. The "
                f"decision contradicts itself; it needs re-issuing.",
            )

    scope = document.get("migration_scope") or {}
    declared_citations = scope.get("citation_change_count")
    if declared_citations is not None:
        actual = len(scope.get("canonical_citation_revisions") or [])
        if int(declared_citations) != actual:
            plan.finding(
                "migration_declared_count_mismatch",
                "error",
                f"{decision_id} declares citation_change_count={declared_citations} but "
                f"enumerates {actual}",
            )
