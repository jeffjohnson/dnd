"""Derivation must reproduce the shipped canonical state exactly.

Degrees and roles in `nodes_master.csv` were produced by an earlier build. If
this package cannot reproduce them from the edge list alone, then either the
stored values are stale or the derivation is wrong -- and an integration would
silently rewrite 1,094 node rows either way.
"""

from __future__ import annotations

import unittest

import _bootstrap
from _bootstrap import REPO_ROOT, RULESET_ID

from adnd1e_integrator.canonical import CanonicalGraph, CanonicalPaths
from adnd1e_integrator.derive import (
    AUTHORED_TYPES,
    DERIVED_POLARITY,
    Degrees,
    derive_polarity,
    load_role_profile,
    rebuild_nodes,
)


class TestDerivation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = CanonicalPaths(root=REPO_ROOT, ruleset_id=RULESET_ID)
        cls.graph = CanonicalGraph.load(cls.paths)
        cls.profile = load_role_profile(
            REPO_ROOT / "rulesets" / RULESET_ID / "profiles" / "roles.yaml")
        cls.thresholds = cls.profile["thresholds"]

    def test_thirteen_edge_types(self):
        self.assertEqual(len(DERIVED_POLARITY) + len(AUTHORED_TYPES), 13)

    def test_ten_types_are_build_owned(self):
        self.assertEqual(len(DERIVED_POLARITY), 10)
        for edge_type in AUTHORED_TYPES:
            self.assertIsNone(derive_polarity({"edge_type": edge_type}))

    def test_degrees_reproduce_canonical(self):
        degrees = Degrees(self.graph.edges)
        for node in self.graph.nodes:
            node_id = node["id"]
            self.assertEqual(int(node["in_degree"]), degrees.inbound[node_id], node_id)
            self.assertEqual(int(node["out_degree"]), degrees.outbound[node_id], node_id)
            self.assertEqual(int(node["degree"]), degrees.degree(node_id), node_id)
            self.assertEqual(int(node["core_degree"]), degrees.core[node_id], node_id)

    def test_roles_reproduce_canonical(self):
        degrees = Degrees(self.graph.edges)
        for node in self.graph.nodes:
            expected = "|".join(sorted(degrees.roles(node["id"], self.thresholds)))
            self.assertEqual(node["roles"], expected, node["id"])

    def test_rebuild_reproduces_the_whole_node_table(self):
        labels = {n["id"]: n["label"] for n in self.graph.nodes}
        kinds = {n["id"]: n["kind"] for n in self.graph.nodes}
        rebuilt = rebuild_nodes(self.graph.edges, labels, kinds, self.thresholds)
        self.assertEqual(rebuilt, self.graph.nodes)

    def test_node_order_is_deterministic(self):
        """Degree descending, ties broken by first appearance in the edge list."""
        labels = {n["id"]: n["label"] for n in self.graph.nodes}
        kinds = {n["id"]: n["kind"] for n in self.graph.nodes}
        once = rebuild_nodes(self.graph.edges, labels, kinds, self.thresholds)
        twice = rebuild_nodes(self.graph.edges, labels, kinds, self.thresholds)
        self.assertEqual(once, twice)
        degrees = [int(n["degree"]) for n in once]
        self.assertEqual(degrees, sorted(degrees, reverse=True))


class TestAnEmptyBootstrapProfileDerivesNoRole(unittest.TestCase):
    """DEC-2026-0092. `thresholds: {}` is configuration, not a missing file.

    Shadowdark's profile records that no corpus-based thresholds exist yet. The
    ruling is explicit that this means no derived roles, and that inventing
    thresholds or importing AD&D's would be an unsupported graph conclusion.
    Before this change `roles()` indexed `thresholds[role][key]` directly and
    raised `KeyError` on the first node.
    """

    EDGES = [
        {"source_id": "abil_strength", "target_id": "tbl_stat_modifiers",
         "edge_type": "FEEDS_INTO", "status": "core", "polarity": "neutral"},
        {"source_id": "abil_strength", "target_id": "rule_stat_generation",
         "edge_type": "DERIVED_FROM", "status": "core", "polarity": "neutral"},
    ]

    def test_an_empty_threshold_mapping_yields_no_role(self):
        degrees = Degrees(self.EDGES, tier2_enabled=False)
        for node in ("abil_strength", "tbl_stat_modifiers", "rule_stat_generation"):
            self.assertEqual(degrees.roles(node, {}), set(), node)

    def test_degrees_are_still_derived_when_roles_are_not(self):
        """An empty profile silences roles only. Degrees are topology, not policy."""
        degrees = Degrees(self.EDGES, tier2_enabled=False)
        self.assertEqual(degrees.outbound["abil_strength"], 2)
        self.assertEqual(degrees.inbound["rule_stat_generation"], 1)
        self.assertEqual(degrees.degree("abil_strength"), 2)

    def test_rebuilt_rows_carry_blank_roles(self):
        rows = rebuild_nodes(self.EDGES, {}, {}, {}, tier2_enabled=False)
        self.assertEqual({r["roles"] for r in rows}, {""})

    def test_tier2_rules_are_not_applied_to_a_ruleset_that_declares_none(self):
        """The tier-2 rules name AD&D identities directly.

        A ruleset whose profile declares no tier-2 mapping must not receive them
        because an ID happens to be spelled the same way.
        """
        edges = [{"source_id": "rule_x", "target_id": "xp_treasure",
                  "edge_type": "FEEDS_INTO", "status": "core", "polarity": "neutral"}]
        self.assertEqual(Degrees(edges, tier2_enabled=False).roles("rule_x", {}), set())
        self.assertEqual(Degrees(edges, tier2_enabled=True).roles("rule_x", {}),
                         {"advancement_currency"})


class TestAPopulatedProfileIsUnchanged(unittest.TestCase):
    """The AD&D corpus must derive exactly what it derived before."""

    @classmethod
    def setUpClass(cls):
        cls.paths = CanonicalPaths(root=REPO_ROOT, ruleset_id=RULESET_ID)
        cls.graph = CanonicalGraph.load(cls.paths)
        cls.thresholds = load_role_profile(
            REPO_ROOT / "rulesets" / RULESET_ID / "profiles" / "roles.yaml")["thresholds"]

    def test_the_default_still_reproduces_the_canonical_node_table(self):
        labels = {n["id"]: n["label"] for n in self.graph.nodes}
        kinds = {n["id"]: n["kind"] for n in self.graph.nodes}
        self.assertEqual(rebuild_nodes(self.graph.edges, labels, kinds, self.thresholds),
                         self.graph.nodes)

    def test_some_canonical_node_actually_carries_a_role(self):
        """Otherwise the empty-profile tests above would pass vacuously."""
        self.assertTrue(any(n["roles"] for n in self.graph.nodes))


if __name__ == "__main__":
    unittest.main()
