"""Canonical identity-merge migration — DEC-2026-0007.

An approved merge retires one node ID into another. The Builder proposes the
work; only the Integrator writes canonical files.

The audit is the point of this module. The escalation that prompted the merge
counted `(source, type, target)` collisions, but the production assertion key is
five fields, so a triple collision is a *review candidate*, not a duplicate.
Every repointed row is normalized in a dry-run copy of the graph and then
classified on all five fields, so two rows that differ only in `aspect` or
`condition` survive as distinct assertions.

Nothing here mutates canonical data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .duplicates import CanonicalEdges, assertion_key
from .vocab import ASSERTION_KEY


@dataclass
class Repoint:
    """One canonical row whose endpoint moves from a retired ID to a survivor."""

    canonical_row: int
    canonical_index: int
    field_name: str  # source_id | target_id
    retired_id: str
    survivor_id: str
    before: dict
    after: dict
    provenance: dict


@dataclass
class Collision:
    """A repointed row whose new assertion key meets an existing canonical row."""

    ref: str
    repointed_row: int
    other_row: int
    grade: str  # exact_duplicate | distinct_assertion
    differing_fields: list[str]
    repointed: dict
    other: dict


@dataclass
class MigrationResult:
    merges: list[dict] = field(default_factory=list)
    repoints: list[Repoint] = field(default_factory=list)
    collisions: list[Collision] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)

    @property
    def exact_duplicates(self) -> list[Collision]:
        return [c for c in self.collisions if c.grade == "exact_duplicate"]

    @property
    def distinct_assertions(self) -> list[Collision]:
        return [c for c in self.collisions if c.grade == "distinct_assertion"]

    @property
    def blocks_approval(self) -> bool:
        return any(f["severity"] == "error" for f in self.findings)


def _row_view(row: dict) -> dict:
    return {
        "source_id": row["source_id"],
        "edge_type": row["edge_type"],
        "target_id": row["target_id"],
        "aspect": row["aspect"],
        "condition": row["condition"],
    }


def _provenance(row: dict) -> dict:
    return {
        "book": row["book"],
        "page": row["page"],
        "section": row["section"],
        "evidence": row["evidence"],
        "pass": row["pass"],
        "status": row["status"],
    }


def plan(canonical: CanonicalEdges, merges: list[dict]) -> MigrationResult:
    """Plan an approved identity merge and audit it on the full assertion key."""
    result = MigrationResult()
    mapping = {m["retired_id"]: m["survivor_id"] for m in merges}
    result.merges = [
        {
            "label": m.get("label"),
            "survivor_id": m["survivor_id"],
            "retired_id": m["retired_id"],
            "authority": m.get("decision_id"),
        }
        for m in merges
    ]

    # -- 1. locate incident rows and plan the repoints ------------------------
    for index, row in enumerate(canonical.rows):
        for field_name in ("source_id", "target_id"):
            retired = row[field_name]
            if retired not in mapping:
                continue
            survivor = mapping[retired]

            if row["source_id"] == row["target_id"]:
                # A self-loop on a retired ID would need its own reasoning.
                result.excluded.append(
                    {
                        "canonical_row": index + 2,
                        "reason": "self_loop_out_of_scope",
                        "detail": f"{retired} self-loop is not repointed by this migration",
                    }
                )
                continue

            after = dict(row)
            after[field_name] = survivor
            result.repoints.append(
                Repoint(
                    canonical_row=index + 2,
                    canonical_index=index,
                    field_name=field_name,
                    retired_id=retired,
                    survivor_id=survivor,
                    before=_row_view(row),
                    after=_row_view(after),
                    provenance=_provenance(row),
                )
            )

    # -- 2. dry-run graph with the retired IDs normalized --------------------
    dry_run = [dict(r) for r in canonical.rows]
    repointed_indexes = {r.canonical_index for r in result.repoints}
    for repoint in result.repoints:
        dry_run[repoint.canonical_index][repoint.field_name] = repoint.survivor_id

    # -- 3. classify every resulting full-key match --------------------------
    for repoint in result.repoints:
        moved = dry_run[repoint.canonical_index]
        moved_key = assertion_key(moved)
        for index, other in enumerate(dry_run):
            if index == repoint.canonical_index or index in repointed_indexes:
                continue
            if not (
                other["source_id"] == moved["source_id"]
                and other["edge_type"] == moved["edge_type"]
                and other["target_id"] == moved["target_id"]
            ):
                continue

            # Triple match. Only the full five-field key decides duplication.
            if assertion_key(other) == moved_key:
                grade, differing = "exact_duplicate", []
            else:
                grade = "distinct_assertion"
                differing = [
                    f
                    for f in ASSERTION_KEY
                    if (moved.get(f) or "").strip() != (other.get(f) or "").strip()
                ]

            result.collisions.append(
                Collision(
                    ref=f"MIG-{repoint.canonical_row}",
                    repointed_row=repoint.canonical_row,
                    other_row=index + 2,
                    grade=grade,
                    differing_fields=differing,
                    repointed=_row_view(moved) | {"provenance": repoint.provenance},
                    other=_row_view(other) | {"provenance": _provenance(other)},
                )
            )

    # -- 4. verify the survivors' own rows are untouched ----------------------
    # DEC-2026-0007 prohibits modifying the unrelated hench_loyalty self-loop.
    # Assert it rather than assume it: a self-loop on a *survivor* is never a
    # repoint target, and saying so makes the acceptance test checkable.
    survivors = {m["survivor_id"] for m in merges}
    for index, row in enumerate(canonical.rows):
        if row["source_id"] == row["target_id"] and row["source_id"] in survivors:
            touched = index in {r.canonical_index for r in result.repoints}
            result.excluded.append(
                {
                    "canonical_row": index + 2,
                    "reason": "survivor_self_loop_untouched",
                    "detail": (
                        f"{row['source_id']} self-loop ({row['book']} p{row['page']}) is outside "
                        f"this migration and is not modified"
                    ),
                    "verified_untouched": not touched,
                }
            )
            if touched:
                result.findings.append(
                    {
                        "severity": "error",
                        "rule": "survivor_self_loop_modified",
                        "detail": (
                            f"canonical row {index + 2} is a {row['source_id']} self-loop and this "
                            f"plan would modify it, which DEC-2026-0007 prohibits"
                        ),
                    }
                )

    # -- 5. findings ---------------------------------------------------------
    for merge in merges:
        retired = merge["retired_id"]
        planned = [r for r in result.repoints if r.retired_id == retired]
        result.findings.append(
            {
                "severity": "info",
                "rule": "merge_planned",
                "detail": (
                    f"{retired} -> {merge['survivor_id']}: {len(planned)} incident row(s) "
                    f"repointed, per {merge.get('decision_id')}"
                ),
            }
        )

    for collision in result.exact_duplicates:
        result.findings.append(
            {
                "severity": "warning",
                "rule": "merge_creates_exact_duplicate",
                "detail": (
                    f"repointed row {collision.repointed_row} matches canonical row "
                    f"{collision.other_row} on all five assertion-key fields. One row must be "
                    f"withdrawn and both citations preserved in provenance; the Reviewer decides "
                    f"which survives."
                ),
            }
        )

    for collision in result.distinct_assertions:
        result.findings.append(
            {
                "severity": "info",
                "rule": "merge_preserves_distinct_assertion",
                "detail": (
                    f"repointed row {collision.repointed_row} shares endpoints and type with "
                    f"canonical row {collision.other_row} but differs in "
                    f"{', '.join(collision.differing_fields)}. Preserved as distinct; a triple "
                    f"collision is not a duplicate."
                ),
            }
        )

    return result


def to_gup(
    result: MigrationResult,
    gup_id: str,
    envelope: dict,
    tool: dict,
    test_result: dict,
) -> dict:
    """Render a migration plan as a GUP-shaped artifact for Review."""
    return {
        "schema_version": "1.0",
        "id": gup_id,
        "status": "blocked" if result.blocks_approval else "proposed",
        "ruleset_id": envelope["ruleset_id"],
        "book_id": envelope["book_id"],
        "source_id": envelope["source_id"],
        "packet_id": envelope["packet_id"],
        "constitution_version": envelope["constitution_version"],
        # `identity_merge_migration` was the earlier spelling. DEC-2026-0018
        # rules it a legacy name for this same lineage root, not a third one:
        # already-published artifacts keep it as immutable history, and every
        # new one declares the current kind.
        "artifact_kind": "decision_migration",
        "authority": sorted({m["authority"] for m in result.merges if m["authority"]}),
        "provenance": {
            "builder_tool": tool["name"],
            "builder_version": tool["version"],
            "test_result": test_result,
            "canonical_source": envelope["canonical_source"],
            "canonical_rows_read": envelope["canonical_rows_read"],
        },
        "approval_ready": not result.blocks_approval,
        "node_changes": {
            "retirements": [
                {
                    "retired_id": m["retired_id"],
                    "survivor_id": m["survivor_id"],
                    "label": m["label"],
                    "authority": m["authority"],
                    "action": "remove_from_nodes_csv_after_approval",
                }
                for m in result.merges
            ],
            "additions_proposed": [],
            "note": (
                "Only the Integrator removes a registry row. Retirement is proposed here and "
                "applied from an approved migration artifact."
            ),
        },
        "edge_changes": {
            "additions": [],
            "updates": [
                {
                    "canonical_row": r.canonical_row,
                    "change": "repoint_endpoint",
                    "field": r.field_name,
                    "from": r.retired_id,
                    "to": r.survivor_id,
                    "before": r.before,
                    "after": r.after,
                    "provenance_preserved": r.provenance,
                }
                for r in result.repoints
            ],
            "removals": [],
        },
        "assertion_key_audit": {
            "fields": list(ASSERTION_KEY),
            "method": (
                "Retired IDs were normalized in a dry-run copy of the canonical graph, then every "
                "resulting source/type/target match was classified on all five fields."
            ),
            "triple_matches_examined": len(result.collisions),
            "exact_duplicates": [
                {
                    "repointed_row": c.repointed_row,
                    "other_row": c.other_row,
                    "repointed": c.repointed,
                    "other": c.other,
                }
                for c in result.exact_duplicates
            ],
            "distinct_assertions_preserved": [
                {
                    "repointed_row": c.repointed_row,
                    "other_row": c.other_row,
                    "differing_fields": c.differing_fields,
                    "repointed": c.repointed,
                    "other": c.other,
                }
                for c in result.distinct_assertions
            ],
        },
        "excluded_from_migration": result.excluded,
        "findings": result.findings,
        "validation_summary": {
            "merges": len(result.merges),
            "rows_repointed": len(result.repoints),
            "triple_matches_examined": len(result.collisions),
            "exact_duplicates": len(result.exact_duplicates),
            "distinct_assertions_preserved": len(result.distinct_assertions),
            "excluded": len(result.excluded),
        },
    }
