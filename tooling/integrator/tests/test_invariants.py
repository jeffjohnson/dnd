"""The invariant suite, including its behaviour on the real corpus.

Canonical state currently carries known baseline defects (see
`rulesets/adnd1e/reports/`). These tests pin the *shape* of what the suite
detects rather than asserting the corpus is clean, so a future repair shows up
as a deliberate test change rather than a silent pass.
"""

from __future__ import annotations

import json
import unittest

import _bootstrap
from _bootstrap import REPO_ROOT, RULESET_ID

from adnd1e_integrator.canonical import EDGE_COLUMNS, CanonicalGraph, CanonicalPaths
from adnd1e_integrator.derive import load_role_profile
from adnd1e_integrator.invariants import (
    approved_prefixes,
    assertion_key,
    check,
    check_derived_state,
)

BASE_EDGE = {
    "source_id": "class_cleric", "source_label": "Cleric", "edge_type": "GATES",
    "target_id": "rule_turn_undead", "target_label": "Turning Undead",
    "aspect": "class prerequisite", "condition": "",
    "polarity": "enables", "polarity_basis": "derived",
    "book": "PHB", "page": "", "section": "CLERICS", "evidence": "explicit_rule",
    "pass": "page-sweep", "status": "core",
    "supersession_basis": "", "general_rule_id": "", "review_flag": "",
}
NODES = [
    {"id": "class_cleric", "label": "Cleric", "kind": "class",
     "degree": "1", "core_degree": "1", "in_degree": "0", "out_degree": "1", "roles": ""},
    {"id": "rule_turn_undead", "label": "Turning Undead", "kind": "rule",
     "degree": "1", "core_degree": "1", "in_degree": "1", "out_degree": "0", "roles": ""},
]


def run(edges, nodes=None, prefixes=None, rules=None):
    return check(edges, nodes or NODES, prefixes or frozenset({"class_", "rule_", "abil_"}),
                 rules or set(), EDGE_COLUMNS)


def edge(**overrides):
    row = dict(BASE_EDGE)
    row.update(overrides)
    return row


class TestSyntheticInvariants(unittest.TestCase):
    def test_clean_edge_passes(self):
        self.assertTrue(run([edge()]).ok)

    def test_dangling_endpoint(self):
        result = run([edge(target_id="rule_absent")])
        self.assertIn(1, result.by_invariant())

    def test_unapproved_prefix(self):
        result = run([edge()], nodes=NODES + [
            {"id": "turn_undead", "label": "x", "kind": "turn", "degree": "0",
             "core_degree": "0", "in_degree": "0", "out_degree": "0", "roles": ""}])
        self.assertIn(3, result.by_invariant())

    def test_illegal_edge_type(self):
        self.assertIn(7, run([edge(edge_type="RELATED_TO")]).by_invariant())

    def test_missing_citation(self):
        self.assertIn(9, run([edge(page="", section="")]).by_invariant())

    def test_magnitude_in_aspect(self):
        self.assertIn(11, run([edge(aspect="gives +3 to hit")]).by_invariant())

    def test_duplicate_assertion_identity(self):
        self.assertIn(12, run([edge(), edge()]).by_invariant())

    def test_alternative_to_is_symmetric_for_duplicates(self):
        a = edge(edge_type="ALTERNATIVE_TO", polarity="neutral")
        b = edge(edge_type="ALTERNATIVE_TO", polarity="neutral",
                 source_id="rule_turn_undead", target_id="class_cleric")
        self.assertEqual(assertion_key(a), assertion_key(b))

    def test_derived_polarity_must_match_the_table(self):
        self.assertIn(17, run([edge(polarity="improves")]).by_invariant())

    def test_authored_polarity_may_not_be_unset(self):
        result = run([edge(edge_type="MODIFIES", polarity="neutral", polarity_basis="unset")])
        self.assertIn(16, result.by_invariant())

    def test_authored_polarity_may_not_be_heuristic(self):
        result = run([edge(edge_type="MODIFIES", polarity="improves", polarity_basis="heuristic")])
        self.assertIn(16, result.by_invariant())

    def test_overrides_requires_supersession_basis(self):
        result = run([edge(edge_type="OVERRIDES", polarity="neutral")])
        self.assertIn(20, result.by_invariant())

    def test_supersession_basis_forbidden_elsewhere(self):
        self.assertIn(20, run([edge(supersession_basis="later_publication")]).by_invariant())

    def test_general_rule_id_required_on_general_rule_pass(self):
        self.assertIn(18, run([edge(**{"pass": "general-rule"})]).by_invariant())

    def test_general_rule_id_must_resolve(self):
        result = run([edge(**{"pass": "general-rule", "general_rule_id": "GR_NOPE"})])
        self.assertIn(18, result.by_invariant())

    def test_general_rule_id_forbidden_on_establishing_edge(self):
        self.assertIn(19, run([edge(general_rule_id="GR_X")]).by_invariant())


class TestAgainstRealCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = CanonicalPaths(root=REPO_ROOT, ruleset_id=RULESET_ID)
        cls.graph = CanonicalGraph.load(cls.paths)
        cls.prefixes = approved_prefixes(
            REPO_ROOT / "rulesets" / RULESET_ID / "governance" / "constitution.md")
        cls.rules = set(json.loads(
            (REPO_ROOT / "rulesets" / RULESET_ID / "registries" / "general_rules.json")
            .read_text(encoding="utf-8")).keys())
        cls.thresholds = load_role_profile(
            REPO_ROOT / "rulesets" / RULESET_ID / "profiles" / "roles.yaml")["thresholds"]

    def test_prefixes_parse_from_the_constitution(self):
        self.assertGreaterEqual(len(self.prefixes), 24)
        for expected in ("abil_", "class_", "race_", "rule_", "sys_", "exp_", "wpn_", "thief_"):
            self.assertIn(expected, self.prefixes)

    def test_prefix_list_agrees_with_builder_tooling(self):
        """Two roles must not hold different ideas of the approved prefix set."""
        import sys
        builder_src = REPO_ROOT / "tooling" / "builder" / "src"
        if not builder_src.exists():
            self.skipTest("builder tooling not present")
        sys.path.insert(0, str(builder_src))
        try:
            from adnd1e_builder.vocab import NODE_PREFIXES
        finally:
            sys.path.remove(str(builder_src))
        self.assertEqual(set(NODE_PREFIXES), set(self.prefixes))

    def test_corpus_has_no_duplicate_assertion_identity(self):
        keys = {assertion_key(e) for e in self.graph.edges}
        self.assertEqual(len(keys), len(self.graph.edges))

    def test_corpus_has_no_dangling_endpoint(self):
        result = check(self.graph.edges, self.graph.nodes, self.prefixes,
                       self.rules, EDGE_COLUMNS)
        self.assertNotIn(1, result.by_invariant())

    def test_stored_derived_state_is_current(self):
        result = check(self.graph.edges, self.graph.nodes, self.prefixes,
                       self.rules, EDGE_COLUMNS)
        check_derived_state(self.graph.edges, self.graph.nodes, self.thresholds, result)
        self.assertNotIn(22, result.by_invariant(),
                         "graph.json / nodes_master degrees or roles are stale")

    def test_every_edge_carries_a_citation(self):
        result = check(self.graph.edges, self.graph.nodes, self.prefixes,
                       self.rules, EDGE_COLUMNS)
        self.assertNotIn(9, result.by_invariant())


if __name__ == "__main__":
    unittest.main()
