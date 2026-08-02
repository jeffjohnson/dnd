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


if __name__ == "__main__":
    unittest.main()
