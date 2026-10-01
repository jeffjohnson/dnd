"""Each ruleset's vocabulary comes from its own Constitution. DEC-2026-0092.

Two defects are pinned here, one that fired and one that had not yet.

The first fired: `approved_prefixes` located the node-prefix table by splitting
on the literal heading `### 3.1 Format` and then rejected any parse of fewer
than twenty prefixes. Both facts are AD&D's. Shadowdark declares its prefixes
under `## 2. Node Identity` and fewer than twenty of them, so a correct
constitution failed twice --
once on the heading, and again on the count had the heading been patched alone.

The second had not fired: the edge-type and derived-polarity tables were
transcribed into `derive.py` from AD&D constitution section 6.1. Shadowdark
happens to declare the same ten derived types, so the transcription agreed by
coincidence and nothing would have detected divergence. The tests below read
both rulesets from disk rather than asserting a hardcoded list, so a future
ruleset that differs is caught by the same check.
"""

from __future__ import annotations

import re
import unittest

import _bootstrap
from _bootstrap import REPO_ROOT, RULESET_ID

from adnd1e_integrator.invariants import approved_prefixes
from adnd1e_integrator.vocabulary import (
    VocabularyError,
    load_vocabulary,
    read_derived_polarity,
    read_edge_types,
    read_prefixes,
)


def declared_prefixes(ruleset_id: str) -> set[str]:
    """Read the Prefix table independently of the code under test.

    DEC-2026-0093 added `alignment_` and `deity_` to Shadowdark, and the
    original form of this test asserted a hardcoded set of thirteen. That is a
    snapshot of the corpus rather than an invariant, so a lawful constitution
    amendment failed a test about the *loader*. Repaired as ordinary test-only
    maintenance under DEC-2026-0078.

    The reader below is deliberately a different implementation from
    `vocabulary.read_prefixes`: it finds the header line and walks the table by
    hand. Comparing the loader against itself would pass no matter what it
    returned; comparing it against a second, simpler reading is what keeps a
    dropped or invented prefix detectable.
    """
    text = (REPO_ROOT / "rulesets" / ruleset_id / "governance"
            / "constitution.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    found: set[str] = set()
    for index, line in enumerate(lines):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0].lower() != "prefix" or "kind" not in cells[1].lower():
            continue
        for row in lines[index + 2:]:
            if not row.strip().startswith("|"):
                break
            first = row.strip().strip("|").split("|")[0].strip().strip("`")
            if re.fullmatch(r"[a-z][a-z0-9]*_", first):
                found.add(first)
        break
    return found


MINIMAL = """
# A ruleset

| Prefix | Kind | Example |
|---|---|---|
| `foo_` | a thing | `foo_example` |

| Type | Meaning | Direction |
|---|---|---|
| `GATES` | is a precondition for | gate to gated |
| `MODIFIES` | changes a value | modifier to modified |

| Edge type | Derived polarity |
|---|---|
| GATES | enables |
"""


class TestTheActiveConstitutionSuppliesTheVocabulary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adnd = load_vocabulary(REPO_ROOT, RULESET_ID)
        cls.shadowdark = load_vocabulary(REPO_ROOT, "shadowdark")

    def test_shadowdark_yields_exactly_what_its_constitution_declares(self):
        """Every declared prefix, and nothing the constitution does not declare."""
        declared = declared_prefixes("shadowdark")
        self.assertTrue(declared, "the fixture reader found no Prefix table")
        self.assertEqual(set(self.shadowdark.prefixes), declared)

    def test_shadowdark_keeps_the_identities_its_decisions_established(self):
        """Amendments add; they must not silently drop an approved identity.

        `ancestry_` is DEC-2026-0087 and `alignment_`/`deity_` are DEC-2026-0093.
        Naming them individually keeps a regression attributable to the Decision
        it would break, without pinning the table's total size.
        """
        for prefix in ("abil_", "ancestry_", "alignment_", "deity_", "class_", "rule_"):
            self.assertIn(prefix, self.shadowdark.prefixes, prefix)
        self.assertNotIn("race_", self.shadowdark.prefixes,
                         "Shadowdark must not acquire an AD&D prefix")

    def test_adnd_keeps_its_own_larger_prefix_set(self):
        declared = declared_prefixes(RULESET_ID)
        self.assertEqual(set(self.adnd.prefixes), declared)
        self.assertGreater(len(self.adnd.prefixes), len(self.shadowdark.prefixes))
        self.assertIn("race_", self.adnd.prefixes)
        self.assertNotIn("ancestry_", self.adnd.prefixes,
                         "AD&D must not acquire a Shadowdark prefix")

    def test_the_two_rulesets_do_not_share_a_prefix_set(self):
        """Ancestry and race are distinct identity axes; neither may inherit the other."""
        self.assertNotEqual(set(self.adnd.prefixes), set(self.shadowdark.prefixes))

    def test_a_count_below_twenty_is_no_longer_rejected(self):
        """The old parser raised on any table smaller than AD&D's."""
        self.assertLess(len(self.shadowdark.prefixes), 20)
        self.assertGreaterEqual(len(self.shadowdark.prefixes), 13)

    def test_the_public_helper_reads_the_same_table(self):
        for ruleset, expected in ((RULESET_ID, self.adnd), ("shadowdark", self.shadowdark)):
            constitution = REPO_ROOT / "rulesets" / ruleset / "governance" / "constitution.md"
            self.assertEqual(approved_prefixes(constitution), expected.prefixes)

    def test_each_ruleset_declares_its_own_edge_vocabulary(self):
        for vocabulary in (self.adnd, self.shadowdark):
            self.assertEqual(len(vocabulary.edge_types), 13, vocabulary.ruleset_id)
            self.assertNotIn("RELATED_TO", vocabulary.edge_types)

    def test_derived_and_authored_types_partition_the_vocabulary(self):
        for vocabulary in (self.adnd, self.shadowdark):
            derived = set(vocabulary.derived_polarity)
            authored = set(vocabulary.authored_types)
            self.assertEqual(derived | authored, set(vocabulary.edge_types))
            self.assertEqual(derived & authored, set())
            self.assertEqual(len(derived), 10, vocabulary.ruleset_id)
            self.assertEqual(authored, {"MODIFIES", "TRIGGERS", "CONSTRAINS"})

    def test_the_authored_table_is_not_read_as_a_derivation(self):
        """AD&D states its authored types in a second table of the same shape.

        Its polarity cell reads 'Analyst-authored', which is not a polarity
        value, so it contributes nothing. Reading it would assign a derived
        polarity to the three types the Analyst must read off the page.
        """
        for vocabulary in (self.adnd, self.shadowdark):
            for edge_type in ("MODIFIES", "TRIGGERS", "CONSTRAINS"):
                self.assertIsNone(vocabulary.polarity_for(edge_type))

    def test_citation_books_come_from_the_ruleset_book_registry(self):
        self.assertEqual(self.adnd.citation_books, frozenset({"PHB", "DMG", "MM", "UA"}))
        self.assertIn("SD", self.shadowdark.citation_books)
        self.assertNotIn("PHB", self.shadowdark.citation_books,
                         "a Shadowdark row must not be citable to an AD&D book")


class TestAMalformedConstitutionFailsClosed(unittest.TestCase):
    """Failing closed is the point: the alternative is inheriting AD&D silently."""

    def test_a_minimal_well_formed_constitution_parses(self):
        self.assertEqual(read_prefixes(MINIMAL), frozenset({"foo_"}))
        self.assertEqual(read_edge_types(MINIMAL), ("GATES", "MODIFIES"))

    def test_a_missing_prefix_table_is_an_error(self):
        with self.assertRaises(VocabularyError):
            read_prefixes("# a constitution with no tables at all")

    def test_a_prefix_table_with_no_usable_row_is_an_error(self):
        text = "| Prefix | Kind | Example |\n|---|---|---|\n| not a prefix | x | y |\n"
        with self.assertRaises(VocabularyError):
            read_prefixes(text)

    def test_a_missing_edge_vocabulary_is_an_error(self):
        with self.assertRaises(VocabularyError):
            read_edge_types("# nothing here")

    def test_a_missing_polarity_table_is_an_error(self):
        with self.assertRaises(VocabularyError):
            read_derived_polarity("# nothing here", ("GATES",))

    def test_a_polarity_table_naming_an_undeclared_edge_type_is_an_error(self):
        """The two tables must agree; a derivation for a type that is not in the
        vocabulary means one of them is wrong, and guessing which is not the
        Integrator's call."""
        text = MINIMAL.replace("| GATES | enables |",
                               "| GATES | enables |\n| INVENTED | neutral |")
        with self.assertRaises(VocabularyError) as caught:
            read_derived_polarity(text, read_edge_types(text))
        self.assertIn("INVENTED", str(caught.exception))

    def test_a_polarity_table_with_no_derived_row_is_an_error(self):
        text = MINIMAL.replace("| GATES | enables |", "| GATES | Analyst-authored |")
        with self.assertRaises(VocabularyError):
            read_derived_polarity(text, read_edge_types(text))

    def test_a_contradictory_polarity_table_is_an_error(self):
        text = MINIMAL.replace("| GATES | enables |",
                               "| GATES | enables |\n| GATES | negates |")
        with self.assertRaises(VocabularyError):
            read_derived_polarity(text, read_edge_types(text))

    def test_an_unknown_ruleset_is_an_error(self):
        with self.assertRaises(VocabularyError):
            load_vocabulary(REPO_ROOT, "no-such-ruleset")


if __name__ == "__main__":
    unittest.main()
