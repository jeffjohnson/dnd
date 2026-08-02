"""Polarity derivation — constitution 6.1, invariants 13-17."""

from __future__ import annotations

import unittest

import _bootstrap  # noqa: F401

from adnd1e_builder import polarity
from adnd1e_builder.vocab import (
    AUTHORED_POLARITY_TYPES,
    DERIVED_POLARITY,
    EDGE_TYPES,
    POLARITY_VALUES,
)


class TestDerivationTable(unittest.TestCase):
    def test_every_edge_type_is_either_derived_or_authored(self):
        covered = set(DERIVED_POLARITY) | set(AUTHORED_POLARITY_TYPES)
        self.assertEqual(covered, set(EDGE_TYPES))

    def test_ten_derived_three_authored(self):
        self.assertEqual(len(DERIVED_POLARITY), 10)
        self.assertEqual(len(AUTHORED_POLARITY_TYPES), 3)

    def test_derived_values_are_in_the_vocabulary(self):
        for value in DERIVED_POLARITY.values():
            self.assertIn(value, POLARITY_VALUES)

    def test_constitution_table_values(self):
        self.assertEqual(DERIVED_POLARITY["GATES"], "enables")
        self.assertEqual(DERIVED_POLARITY["RESOLVED_BY"], "governs")
        self.assertEqual(DERIVED_POLARITY["EXCLUDES"], "negates")
        self.assertEqual(DERIVED_POLARITY["EXCLUDED_FROM"], "negates")
        self.assertEqual(DERIVED_POLARITY["CONSUMES"], "neutral")


class TestDerivedTypes(unittest.TestCase):
    def test_build_assigns_polarity_and_basis(self):
        result = polarity.resolve("GATES", None, None)
        self.assertEqual(result.polarity, "enables")
        self.assertEqual(result.polarity_basis, "derived")
        self.assertFalse(result.blocks_approval)
        self.assertEqual(result.findings, ())

    def test_authored_polarity_on_derived_type_is_an_error_and_is_overridden(self):
        result = polarity.resolve("GATES", "improves", "read")
        self.assertEqual(result.polarity, "enables", "build value wins")
        self.assertEqual(result.polarity_basis, "derived")
        rules = {f["rule"] for f in result.findings}
        self.assertIn("polarity_authored_on_derived_type", rules)
        self.assertIn("polarity_basis_authored_on_derived_type", rules)

    def test_restating_the_correct_derived_value_is_only_a_warning(self):
        result = polarity.resolve("GATES", "enables", "derived")
        self.assertEqual(result.polarity, "enables")
        self.assertTrue(all(f["severity"] == "warning" for f in result.findings))
        self.assertFalse(result.blocks_approval)


class TestAuthoredTypes(unittest.TestCase):
    def test_authored_polarity_is_preserved(self):
        result = polarity.resolve("MODIFIES", "improves", "read")
        self.assertEqual(result.polarity, "improves")
        self.assertEqual(result.polarity_basis, "read")
        self.assertFalse(result.blocks_approval)
        self.assertEqual(result.findings, ())

    def test_missing_authored_polarity_blocks_approval(self):
        result = polarity.resolve("CONSTRAINS", None, None)
        self.assertEqual(result.polarity_basis, "unset")
        self.assertTrue(result.blocks_approval)
        self.assertIn(
            "polarity_missing_on_authored_type", {f["rule"] for f in result.findings}
        )

    def test_heuristic_basis_blocks_approval(self):
        result = polarity.resolve("TRIGGERS", "inflicts", "heuristic")
        self.assertTrue(result.blocks_approval)
        self.assertIn("polarity_basis_blocks_approval", {f["rule"] for f in result.findings})

    def test_unset_basis_blocks_approval(self):
        result = polarity.resolve("MODIFIES", "worsens", "unset")
        self.assertTrue(result.blocks_approval)

    def test_derived_basis_is_illegal_on_an_authored_type(self):
        result = polarity.resolve("MODIFIES", "improves", "derived")
        self.assertTrue(result.blocks_approval)
        self.assertIn(
            "polarity_basis_derived_on_authored_type", {f["rule"] for f in result.findings}
        )

    def test_polarity_outside_vocabulary_blocks_approval(self):
        result = polarity.resolve("MODIFIES", "helps", "read")
        self.assertTrue(result.blocks_approval)
        self.assertIn("polarity_value_illegal", {f["rule"] for f in result.findings})


class TestUnknownType(unittest.TestCase):
    def test_unknown_edge_type_cannot_derive(self):
        result = polarity.resolve("RELATED_TO", None, None)
        self.assertTrue(result.blocks_approval)


if __name__ == "__main__":
    unittest.main()
