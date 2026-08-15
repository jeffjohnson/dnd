"""The grain rule — constitution section 2, invariant 11."""

from __future__ import annotations

import unittest

import _bootstrap  # noqa: F401

from adnd1e_builder import grain


def rules(findings):
    return {f["rule"] for f in findings}


class TestMagnitudes(unittest.TestCase):
    def test_clean_aspect_passes(self):
        self.assertEqual(grain.check_edge("hit probability", ""), [])

    def test_digit_in_condition_is_an_error(self):
        findings = grain.check_field("condition", "at level 9")
        self.assertIn("grain_magnitude", rules(findings))
        self.assertEqual(findings[0]["severity"], "error")

    def test_die_expression_is_an_error(self):
        self.assertIn("grain_die_expression", rules(grain.check_field("aspect", "1d6 damage")))
        self.assertIn("grain_die_expression", rules(grain.check_field("aspect", "d% roll")))

    def test_signed_bonus_is_an_error(self):
        self.assertIn("grain_numeric_bonus", rules(grain.check_field("aspect", "+3 to hit")))

    def test_percentage_is_an_error(self):
        self.assertIn("grain_percentage", rules(grain.check_field("condition", "on a 40% roll")))

    def test_spelled_out_number_is_a_warning(self):
        findings = grain.check_field("condition", "at ninth level")
        self.assertIn("grain_spelled_magnitude", rules(findings))
        self.assertEqual(
            [f["severity"] for f in findings if f["rule"] == "grain_spelled_magnitude"], ["warning"]
        )

    def test_common_idiom_is_not_flagged(self):
        # "first" and "second" are allowlisted; they are idiom far more often
        # than magnitude in this corpus.
        self.assertEqual(rules(grain.check_field("condition", "first attack only")), set())

    def test_empty_fields_are_clean(self):
        self.assertEqual(grain.check_field("condition", ""), [])
        self.assertEqual(grain.check_field("condition", "   "), [])


class TestAspectLength(unittest.TestCase):
    def test_four_words_is_allowed(self):
        self.assertEqual(grain.check_aspect_length("one two three four"), [])

    def test_five_words_is_an_error(self):
        """Raised from warning: invariant 11 and the assertion key both bind.

        As a warning this let eight packets reach the Reviewer carrying 466
        overlong aspects, and the Reviewer blocked them by hand.
        """
        findings = grain.check_aspect_length("one two three four five")
        self.assertEqual(findings[0]["severity"], "error")
        self.assertEqual(findings[0]["rule"], "aspect_word_count")

    def test_the_detail_names_what_is_wrong_and_why_it_matters(self):
        detail = grain.check_aspect_length("one two three four five")[0]["detail"]
        self.assertIn("invariant 11", detail)
        self.assertIn("assertion key", detail)

    def test_the_constitution_boundary_is_exactly_four(self):
        self.assertEqual(grain.check_aspect_length("one two three four"), [])
        self.assertEqual(len(grain.check_aspect_length("one two three four five")), 1)

    def test_an_overlong_aspect_blocks_approval_rather_than_only_annotating(self):
        errors = [
            f for f in grain.check_edge("the lawful to chaotic component", "")
            if f["severity"] == "error"
        ]
        self.assertEqual([f["rule"] for f in errors], ["aspect_word_count"])


class TestConstitutionExamples(unittest.TestCase):
    """The constitution's own correct/incorrect worked examples."""

    def test_correct_examples_are_clean(self):
        for aspect, condition in [
            ("hit probability", ""),
            ("save bonus by constitution", ""),
            ("class prerequisite", ""),
            ("score determination", ""),
        ]:
            with self.subTest(aspect=aspect):
                errors = [f for f in grain.check_edge(aspect, condition) if f["severity"] == "error"]
                self.assertEqual(errors, [])

    def test_incorrect_example_is_caught(self):
        # "Strength 18/00 gives +3 to hit" is the constitution's headline wrong case.
        findings = grain.check_field("aspect", "gives +3 to hit")
        self.assertTrue(any(f["severity"] == "error" for f in findings))


if __name__ == "__main__":
    unittest.main()
