"""Duplicate detection and the assertion key — invariant 12."""

from __future__ import annotations

import csv
import unittest

import _bootstrap
from _bootstrap import REPO_ROOT

from adnd1e_builder.duplicates import (
    CanonicalEdges,
    assertion_key,
    endpoint_type_key,
    intra_patch_duplicates,
    self_edges,
)
from adnd1e_builder.vocab import ASSERTION_KEY


def edge(ref, source, edge_type, target, aspect="", condition=""):
    return {
        "ref": ref,
        "source_id": source,
        "edge_type": edge_type,
        "target_id": target,
        "aspect": aspect,
        "condition": condition,
    }


class TestAssertionKey(unittest.TestCase):
    def test_key_is_the_constitution_tuple(self):
        self.assertEqual(
            ASSERTION_KEY, ("source_id", "edge_type", "target_id", "aspect", "condition")
        )

    def test_key_is_case_and_punctuation_insensitive(self):
        a = edge("A", "abil_strength", "MODIFIES", "cbt_tohit", "Hit Probability")
        b = edge("B", "abil_strength", "MODIFIES", "cbt_tohit", "hit  probability")
        self.assertEqual(assertion_key(a), assertion_key(b))

    def test_different_aspect_is_a_different_assertion(self):
        a = edge("A", "abil_strength", "MODIFIES", "cbt_tohit", "hit probability")
        b = edge("B", "abil_strength", "MODIFIES", "cbt_tohit", "damage bonus")
        self.assertNotEqual(assertion_key(a), assertion_key(b))

    def test_symmetric_type_canonicalises_endpoints(self):
        a = edge("A", "rule_x", "ALTERNATIVE_TO", "rule_y")
        b = edge("B", "rule_y", "ALTERNATIVE_TO", "rule_x")
        self.assertEqual(assertion_key(a), assertion_key(b))
        self.assertEqual(endpoint_type_key(a), endpoint_type_key(b))

    def test_asymmetric_type_does_not_canonicalise(self):
        a = edge("A", "rule_x", "GATES", "rule_y")
        b = edge("B", "rule_y", "GATES", "rule_x")
        self.assertNotEqual(assertion_key(a), assertion_key(b))


class TestIntraPatch(unittest.TestCase):
    def test_exact_duplicate_is_reported(self):
        rows = [
            edge("A", "abil_strength", "GATES", "class_fighter", "class eligibility"),
            edge("B", "abil_strength", "GATES", "class_fighter", "class eligibility"),
        ]
        findings = intra_patch_duplicates(rows)
        exact = [f for f in findings if f["grade"] == "exact"]
        self.assertEqual(len(exact), 1)
        self.assertEqual(exact[0]["ref"], "B")

    def test_near_duplicate_is_reported_separately(self):
        rows = [
            edge("A", "abil_strength", "MODIFIES", "cbt_tohit", "hit probability"),
            edge("B", "abil_strength", "MODIFIES", "cbt_tohit", "damage bonus"),
        ]
        findings = intra_patch_duplicates(rows)
        self.assertEqual([f["grade"] for f in findings], ["near"])

    def test_distinct_edges_produce_nothing(self):
        rows = [
            edge("A", "abil_strength", "GATES", "class_fighter"),
            edge("B", "abil_strength", "GATES", "class_paladin"),
        ]
        self.assertEqual(intra_patch_duplicates(rows), [])


class TestSelfEdges(unittest.TestCase):
    def test_self_edge_detected(self):
        rows = [edge("A", "rule_x", "OVERRIDES", "rule_x")]
        self.assertEqual(len(self_edges(rows)), 1)

    def test_normal_edge_not_flagged(self):
        self.assertEqual(self_edges([edge("A", "rule_x", "GATES", "rule_y")]), [])


class TestAgainstCanonicalCorpus(unittest.TestCase):
    """The assertion key must keep the real canonical file duplicate-free."""

    @classmethod
    def setUpClass(cls):
        cls.path = REPO_ROOT / "rulesets" / "adnd1e" / "canonical" / "edges_master.csv"

    def test_canonical_corpus_has_no_duplicate_assertions(self):
        with self.path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        keys = [assertion_key(r) for r in rows]
        self.assertEqual(
            len(set(keys)),
            len(keys),
            "the assertion key must not collapse two distinct canonical edges",
        )

    def test_loader_indexes_every_row(self):
        canonical = CanonicalEdges.load(self.path)
        self.assertEqual(sum(len(v) for v in canonical.by_assertion.values()), len(canonical.rows))

    def test_exact_match_finds_a_known_canonical_edge(self):
        canonical = CanonicalEdges.load(self.path)
        row = canonical.rows[0]
        probe = {
            "source_id": row["source_id"],
            "edge_type": row["edge_type"],
            "target_id": row["target_id"],
            "aspect": row["aspect"],
            "condition": row["condition"],
        }
        self.assertTrue(canonical.exact_matches(probe))


if __name__ == "__main__":
    unittest.main()
