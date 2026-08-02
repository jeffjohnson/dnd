"""Everything the build computes rather than reads.

Three derivations live here, all of them forbidden to human authorship:

- **Polarity** on the ten deterministic edge types (constitution section 6.1,
  invariants 13, 14, 17).
- **Node degrees**, including `core_degree`.
- **Node roles**, tier 1 from topology and tier 2 from edge patterns
  (constitution section 11), with thresholds read from the versioned profile
  rather than hard-coded (constitution section 13b).

Re-derivation is total, not incremental: every node is recomputed from the whole
edge list on every integration. An incremental update would let a stale value
survive a batch that should have changed it.
"""

from __future__ import annotations

import collections
from pathlib import Path

import yaml

# Constitution section 6.1. Ten types where polarity follows from edge type.
DERIVED_POLARITY = {
    "GATES": "enables",
    "RESOLVED_BY": "governs",
    "EXCLUDES": "negates",
    "EXCLUDED_FROM": "negates",
    "DERIVED_FROM": "neutral",
    "ALTERNATIVE_TO": "neutral",
    "OVERRIDES": "neutral",
    "FEEDS_INTO": "neutral",
    "CROSS_REFERENCES": "neutral",
    "CONSUMES": "neutral",
}

# The three types that carry Analyst-authored polarity.
AUTHORED_TYPES = ("MODIFIES", "TRIGGERS", "CONSTRAINS")

EDGE_TYPES = tuple(DERIVED_POLARITY) + AUTHORED_TYPES

POLARITY_VALUES = ("inflicts", "improves", "worsens", "negates", "enables", "governs", "neutral")
POLARITY_BASIS_VALUES = ("derived", "read", "heuristic", "unset")


def load_role_profile(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def derive_polarity(edge: dict[str, str]) -> tuple[str, str] | None:
    """The (polarity, polarity_basis) the build owns, or None if authored.

    Returning None means the edge type is one of the three where the Analyst
    reads polarity off the page. The build validates those but never assigns
    them.
    """
    edge_type = edge["edge_type"]
    if edge_type in DERIVED_POLARITY:
        return DERIVED_POLARITY[edge_type], "derived"
    return None


def apply_derived_polarity(edges: list[dict[str, str]]) -> list[dict]:
    """Recompute deterministic polarity in place; report every correction."""
    corrections = []
    for index, edge in enumerate(edges):
        derived = derive_polarity(edge)
        if derived is None:
            continue
        polarity, basis = derived
        if edge["polarity"] != polarity or edge["polarity_basis"] != basis:
            corrections.append({
                "row": index + 2,  # 1-based with header
                "source_id": edge["source_id"],
                "edge_type": edge["edge_type"],
                "target_id": edge["target_id"],
                "from": {"polarity": edge["polarity"], "polarity_basis": edge["polarity_basis"]},
                "to": {"polarity": polarity, "polarity_basis": basis},
            })
            edge["polarity"] = polarity
            edge["polarity_basis"] = basis
    return corrections


class Degrees:
    """Per-node counters computed from the full edge list."""

    def __init__(self, edges: list[dict[str, str]]):
        self.inbound = collections.Counter()
        self.outbound = collections.Counter()
        self.core = collections.Counter()
        self.in_by_type = collections.defaultdict(collections.Counter)
        self.out_by_type = collections.defaultdict(collections.Counter)
        self.tier2 = collections.defaultdict(set)
        # Introduction order: scan the edge list once, visiting each edge's source
        # before its target. Two nodes introduced by the same edge therefore get
        # distinct ordinals, which makes the node sort total rather than merely
        # stable. `first_seen` keyed on edge position alone would tie here.
        self.first_seen: dict[str, int] = {}

        for edge in edges:
            source, target, edge_type = edge["source_id"], edge["target_id"], edge["edge_type"]
            for node in (source, target):
                if node not in self.first_seen:
                    self.first_seen[node] = len(self.first_seen)
            self.outbound[source] += 1
            self.inbound[target] += 1
            self.out_by_type[source][edge_type] += 1
            self.in_by_type[target][edge_type] += 1
            if edge["status"] == "core":
                self.core[source] += 1
                self.core[target] += 1
            self._tier2(edge, source, target, edge_type)

    def _tier2(self, edge, source, target, edge_type) -> None:
        """Constitution section 11 tier 2. Direction matters and was wrong in v1.0."""
        if edge_type == "FEEDS_INTO" and target.startswith("xp_"):
            self.tier2[source].add("advancement_currency")
        if edge_type == "FEEDS_INTO" and target == "enc_encumbrance":
            self.tier2[source].add("logistical_burden")
        if edge_type == "CONSUMES" and target == "money_gp":
            self.tier2[source].add("wealth_sink")
        if edge_type == "CONSUMES" and target == "rule_time":
            self.tier2[source].add("time_sink")
        if edge_type == "MODIFIES" and target == "rule_hit_points" and edge["polarity"] == "worsens":
            self.tier2[source].add("attrition_pressure")

    def degree(self, node: str) -> int:
        return self.inbound[node] + self.outbound[node]

    def roles(self, node: str, thresholds: dict) -> set[str]:
        """Tier 1 structural roles plus any tier 2 role already collected."""
        found = set(self.tier2.get(node, ()))
        out, inn = self.out_by_type[node], self.in_by_type[node]
        t = thresholds

        def th(role: str, key: str) -> int:
            return t[role][key]

        if inn["CONSUMES"] >= th("resource", "inbound_CONSUMES"):
            found.add("resource")
        if out["CONSUMES"] >= th("consumer", "outbound_CONSUMES"):
            found.add("consumer")
        if (inn["CONSUMES"] >= th("sink", "inbound_CONSUMES")
                and out["CONSUMES"] <= th("sink", "outbound_CONSUMES_max")):
            found.add("sink")
        if out["GATES"] >= th("gatekeeper", "outbound_GATES"):
            found.add("gatekeeper")
        if inn["GATES"] >= th("gated_privilege", "inbound_GATES"):
            found.add("gated_privilege")
        if inn["MODIFIES"] >= th("tuning_point", "inbound_MODIFIES"):
            found.add("tuning_point")
        if out["MODIFIES"] >= th("modifier_source", "outbound_MODIFIES"):
            found.add("modifier_source")
        if out["TRIGGERS"] >= th("trigger_source", "outbound_TRIGGERS"):
            found.add("trigger_source")
        if inn["TRIGGERS"] >= th("triggered_procedure", "inbound_TRIGGERS"):
            found.add("triggered_procedure")
        if inn["RESOLVED_BY"] >= th("resolution_machinery", "inbound_RESOLVED_BY"):
            found.add("resolution_machinery")
        if inn["FEEDS_INTO"] >= th("aggregator", "inbound_FEEDS_INTO"):
            found.add("aggregator")
        if out["OVERRIDES"] >= th("override_source", "outbound_OVERRIDES"):
            found.add("override_source")
        if (out["EXCLUDES"] + inn["EXCLUDED_FROM"]
                >= th("boundary_marker", "outbound_EXCLUDES_plus_inbound_EXCLUDED_FROM")):
            found.add("boundary_marker")
        if (self.outbound[node] >= th("index", "outbound_min")
                and self.inbound[node] <= th("index", "inbound_max")):
            found.add("index")
        if (self.inbound[node] >= th("accumulator", "inbound_min")
                and self.outbound[node] <= th("accumulator", "outbound_max")):
            found.add("accumulator")
        return found


def rebuild_nodes(
    edges: list[dict[str, str]],
    labels: dict[str, str],
    kinds: dict[str, str],
    thresholds: dict,
) -> list[dict[str, str]]:
    """Recompute every node row and return them in canonical order.

    Canonical order is degree descending, ties broken by order of first
    appearance in the edge list. That rule reproduces the existing corpus
    exactly and stays stable as edges are added, so an integration diff shows
    only nodes whose numbers actually moved.
    """
    degrees = Degrees(edges)
    node_ids = set(degrees.inbound) | set(degrees.outbound)

    rows = []
    for node in node_ids:
        rows.append({
            "id": node,
            "label": labels.get(node, node),
            "kind": kinds.get(node, node.split("_", 1)[0]),
            "degree": degrees.degree(node),
            "core_degree": degrees.core[node],
            "in_degree": degrees.inbound[node],
            "out_degree": degrees.outbound[node],
            "roles": "|".join(sorted(degrees.roles(node, thresholds))),
        })

    rows.sort(key=lambda r: (-r["degree"], degrees.first_seen[r["id"]]))
    return [{k: str(v) for k, v in row.items()} for row in rows]
