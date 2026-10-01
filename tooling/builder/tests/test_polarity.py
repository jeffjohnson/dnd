"""Polarity derivation — constitution 6.1, invariants 13-17."""

from __future__ import annotations

import unittest

import _bootstrap
from _bootstrap import REPO_ROOT

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


class TestRulesetScopedDerivation(unittest.TestCase):
    """DEC-2026-0103: which types are derived, and to what, comes from the
    active ruleset's own vocabulary, not one shared constant.

    Before this Decision `resolve` always consulted the single AD&D
    1e-transcribed `DERIVED_POLARITY` table, and every ruleset -- including
    Basic D&D, whose own constitution never enumerates derived types at all
    -- relied on that sharing. `CLASSIFIED_AS` is the first edge type only
    one ruleset derives, so these tests pin the resulting three-way split
    rather than assuming the change was safe.
    """

    def vocabulary_for(self, ruleset_id):
        from adnd1e_builder.vocab import RulesetVocabulary

        return RulesetVocabulary.load(REPO_ROOT, ruleset_id)

    def test_omitting_vocabulary_keeps_the_prior_shared_behaviour(self):
        """No existing caller passes a vocabulary; none may change behaviour."""
        result = polarity.resolve("GATES", None, None)
        self.assertEqual(result.polarity, "enables")
        self.assertEqual(result.polarity_basis, "derived")

    def test_shadowdark_derives_classified_as_as_neutral(self):
        result = polarity.resolve(
            "CLASSIFIED_AS", None, None, self.vocabulary_for("shadowdark"))
        self.assertEqual(result.polarity, "neutral")
        self.assertEqual(result.polarity_basis, "derived")
        self.assertFalse(result.blocks_approval)

    def test_adnd1e_does_not_derive_classified_as(self):
        """CLASSIFIED_AS is not in AD&D 1e's edge vocabulary at all, but the
        polarity layer is checked independently in case that ever changes."""
        result = polarity.resolve(
            "CLASSIFIED_AS", None, None, self.vocabulary_for("adnd1e"))
        self.assertTrue(result.blocks_approval)
        self.assertIn("polarity_undeterminable", {f["rule"] for f in result.findings})

    def test_basicdnd_does_not_derive_classified_as(self):
        result = polarity.resolve(
            "CLASSIFIED_AS", None, None, self.vocabulary_for("basicdnd"))
        self.assertTrue(result.blocks_approval)

    def test_basicdnd_still_derives_its_ordinary_types(self):
        """Basic D&D's own constitution states no derived-polarity table; it
        must keep falling back to the shared one, not to nothing."""
        for edge_type, expected in (("GATES", "enables"), ("RESOLVED_BY", "governs"),
                                    ("FEEDS_INTO", "neutral")):
            with self.subTest(edge_type=edge_type):
                result = polarity.resolve(
                    edge_type, None, None, self.vocabulary_for("basicdnd"))
                self.assertEqual(result.polarity, expected)
                self.assertFalse(result.blocks_approval)

    def test_adnd1e_vocabulary_matches_the_shared_constant_exactly(self):
        vocabulary = self.vocabulary_for("adnd1e")
        self.assertEqual(dict(vocabulary.derived_polarity), dict(DERIVED_POLARITY))

    def test_shadowdark_still_derives_every_prior_type(self):
        """Gaining CLASSIFIED_AS must not cost Shadowdark any existing one."""
        vocabulary = self.vocabulary_for("shadowdark")
        for edge_type in DERIVED_POLARITY:
            if edge_type == "ALTERNATIVE_TO":
                continue  # symmetric-only; still present, checked separately below
            with self.subTest(edge_type=edge_type):
                self.assertIn(edge_type, vocabulary.derived_polarity)
        self.assertIn("ALTERNATIVE_TO", vocabulary.derived_polarity)

    def test_a_malformed_governed_table_falls_back_rather_than_derives_nothing(self):
        """A constitution with the header but a row the parser cannot read
        must not silently make every edge type undeterminable."""
        import tempfile
        from pathlib import Path as _Path

        from adnd1e_builder.vocab import ruleset_derived_polarity

        with tempfile.TemporaryDirectory() as tmp:
            root = _Path(tmp)
            governance = root / "governance"
            governance.mkdir(parents=True)
            (governance / "constitution.md").write_text(
                "## 5. Polarity and Evidence\n\n"
                "| Edge type | Derived polarity |\n|---|---|\n"
                "not a table row at all\n",
                encoding="utf-8",
            )
            derived = ruleset_derived_polarity("fixture_ruleset", root)
        self.assertEqual(derived, dict(DERIVED_POLARITY))


if __name__ == "__main__":
    unittest.main()
