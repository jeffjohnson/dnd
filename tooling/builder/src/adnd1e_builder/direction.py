"""Edge direction and type selection — constitution 1.4 section 4.2, DEC-2026-0011.

The ratified rule: an ability, class, race, item, or rule that changes a mechanic
uses `input MODIFIES mechanic`, including when the mechanic is read directly from
a table. `DERIVED_FROM` is reserved for computation or lookup lineage between
separately represented concepts. The same dependency is never recorded as both.

This module classifies a proposed edge that joins the same node pair as a
canonical edge running the other way. The classification is a type-and-direction
signature, not a semantic guess, and only one class is decided mechanically.
"""

from __future__ import annotations

# Types that express an operational input-to-mechanic dependency. A canonical
# edge of one of these types already records "input changes mechanic" in the
# ratified direction.
OPERATIONAL_TYPES: frozenset[str] = frozenset({"MODIFIES", "FEEDS_INTO", "CONSTRAINS"})

# Reject only this. A proposed DERIVED_FROM against a canonical operational edge
# on the reversed pair is the same dependency with the arrow turned around and
# the type changed — the case DEC-2026-0011 rules on directly.
INVERSE_OF_OPERATIONAL = "inverse_of_canonical_operational_edge"

# Everything else that reverses a canonical pair is a genuine reading
# disagreement. DEC-2026-0011 sends those to the Reviewer case by case, so the
# row is carried and flagged rather than dropped.
OPPOSED_DIRECTION = "opposed_direction_vs_canonical"


def classify(edge: dict, reversed_canonical: list[dict]) -> dict | None:
    """Classify a proposed edge against canonical edges on the reversed pair.

    Returns None when there is no reversal to report.
    """
    if not reversed_canonical:
        return None

    edge_type = (edge.get("edge_type") or "").strip()
    operational = [r for r in reversed_canonical if r["edge_type"] in OPERATIONAL_TYPES]

    if edge_type == "DERIVED_FROM" and operational:
        # Warning, not error. DEC-2026-0011 settles this shape: the Analyst
        # yields and the row is dropped. Once the ruled disposition is applied
        # nothing is unresolved, so it must not block the rest of the patch —
        # the same treatment a Reviewer-rejected row already gets.
        return {
            "rule": INVERSE_OF_OPERATIONAL,
            "severity": "warning",
            "disposition": "reject",
            "counterparts": operational,
            "detail": (
                f"{edge.get('source_id')} DERIVED_FROM {edge.get('target_id')} is the inverse of "
                f"canonical "
                + "; ".join(
                    f"{r['source_id']} {r['edge_type']} {r['target_id']}" for r in operational
                )
                + ". Under DEC-2026-0011 an input that changes a mechanic uses "
                f"input MODIFIES mechanic, including direct table lookups, and the same "
                f"dependency is not recorded both ways. The proposal restates an existing "
                f"canonical assertion and is dropped rather than retyped."
            ),
        }

    return {
        "rule": OPPOSED_DIRECTION,
        "severity": "warning",
        "disposition": "carry_for_reviewer",
        "counterparts": reversed_canonical,
        "detail": (
            f"{edge.get('source_id')} {edge_type} {edge.get('target_id')} runs opposite to "
            f"canonical "
            + "; ".join(
                f"{r['source_id']} {r['edge_type']} {r['target_id']}" for r in reversed_canonical
            )
            + ". DEC-2026-0011 does not settle this shape mechanically: the Reviewer decides case "
            f"by case with both sources in hand. Carried unchanged."
        ),
    }
