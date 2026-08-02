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
    surviving_row: int
    identity: str
    preserved: dict
    authority: str


@dataclass
class DecisionMigration:
    decisions: list[str] = field(default_factory=list)
    #: One entry per authority Decision: id, repository path, sha256. This is
    #: the alternate auditable root that stands in for GUR provenance.
    decision_inputs: list[dict] = field(default_factory=list)
    nodes_added: list[dict] = field(default_factory=list)
    nodes_relabelled: list[dict] = field(default_factory=list)
    row_changes: list[RowChange] = field(default_factory=list)
    removals: list[Removal] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    counts: dict = field(default_factory=dict)

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

        plan.decisions.append(decision_id)
        try:
            relative = str(path.resolve().relative_to(Path(repo_root).resolve()))
        except (ValueError, TypeError):
            relative = str(path)
        plan.decision_inputs.append(
            {
                "id": decision_id,
                "path": relative.replace("\\", "/"),
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

        block = document.get("canonical_migration") or {}
        _plan_endpoint_repoints(canonical, block, decision_id, plan)
        _plan_label_normalizations(canonical, block, decision_id, plan)
        _plan_merged_assertion(canonical, block, decision_id, plan)

        scope = document.get("migration_scope") or {}
        _plan_citation_revisions(
            canonical, scope.get("canonical_citation_revisions") or [], decision_id, plan
        )

        _check_declared_counts(document, block, decision_id, plan)

    _audit(canonical, plan)

    plan.counts = {
        "decisions": len(plan.decisions),
        "nodes_added": len(plan.nodes_added),
        "nodes_relabelled": len(plan.nodes_relabelled),
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
    plan: DecisionMigration, gup_id: str, envelope: dict, tool: dict, test_result: dict
) -> dict:
    """The external validation component of the bundle.

    Written before the GUP, because the GUP names it by checksum. It repeats the
    baseline identifiers rather than referring back to the GUP so that it can be
    verified on its own.
    """
    return {
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
    }


def to_gup(plan: DecisionMigration, gup_id: str, envelope: dict, tool: dict, test_result: dict) -> dict:
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
    return {
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
            "note": (
                "Registry writes belong to the Integrator. These are proposals the "
                "Reviewer confirms against source and local neighbourhood."
            ),
        },
        "canonical_changes": [
            {
                "canonical_row": c.canonical_row,
                "kind": c.kind,
                "authority": c.authority,
                "changes": {f: {"from": b, "to": a} for f, (b, a) in sorted(c.changes.items())},
                "touches_assertion_identity": c.touches_identity,
                "before": c.before,
                "note": c.note,
            }
            for c in sorted(plan.row_changes, key=lambda c: (c.kind, c.canonical_row))
        ],
        "canonical_removals": [
            {
                "canonical_row": r.canonical_row,
                "surviving_row": r.surviving_row,
                "identity": r.identity,
                "provenance_preserved_on_surviving_row": r.preserved,
                "authority": r.authority,
                "action": "remove_after_the_surviving_row_carries_the_preserved_locus",
            }
            for r in plan.removals
        ],
        "counts": plan.counts,
        "findings": plan.findings,
        "validation_summary": {
            "errors": sum(1 for f in plan.findings if f["severity"] == "error"),
            "warnings": sum(1 for f in plan.findings if f["severity"] == "warning"),
        },
    }


def _check_declared_counts(
    document: dict, block: dict, decision_id: str, plan: DecisionMigration
) -> None:
    """Compare what the decision says it does against what it enumerates.

    A decision states its own scope in `counts`. If the enumeration disagrees
    with the stated total, one of the two is wrong and the Builder should not
    pick. This is the check that would have caught a truncated list.
    """
    declared = block.get("counts") or {}
    pairs = (
        ("canonical_rows_repointed", len(block.get("endpoint_repoints") or [])),
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
