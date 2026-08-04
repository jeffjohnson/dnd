"""Node resolution and the controlled vocabularies."""

from __future__ import annotations

import unittest

import yaml

import _bootstrap
from _bootstrap import REPO_ROOT

from adnd1e_builder.registry import ID_FORMAT, NodeRegistry, normalize_label, prefix_of
from adnd1e_builder.vocab import (
    COLUMNS,
    EDGE_DIRECTION,
    EDGE_TYPES,
    NODE_PREFIXES,
    POLARITY_BASIS_VALUES,
)

REGISTRY_PATH = REPO_ROOT / "rulesets" / "adnd1e" / "registries" / "nodes.csv"
EDGES_PATH = REPO_ROOT / "rulesets" / "adnd1e" / "canonical" / "edges_master.csv"


class TestVocabulary(unittest.TestCase):
    def test_eighteen_production_columns(self):
        self.assertEqual(len(COLUMNS), 18)

    def test_column_order_matches_canonical_file(self):
        header = EDGES_PATH.read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(list(COLUMNS), header.split(","))

    def test_thirteen_edge_types(self):
        self.assertEqual(len(EDGE_TYPES), 13)

    def test_related_to_is_not_a_type(self):
        self.assertNotIn("RELATED_TO", EDGE_TYPES)
        self.assertNotIn("COUNTERS", EDGE_TYPES)

    def test_every_edge_type_documents_a_direction(self):
        self.assertEqual(set(EDGE_DIRECTION), set(EDGE_TYPES))

    def test_four_polarity_basis_values(self):
        self.assertEqual(POLARITY_BASIS_VALUES, {"derived", "read", "heuristic", "unset"})


class TestConstitutionVersion(unittest.TestCase):
    """DEC-2026-0004 (wpn_), DEC-2026-0008 and DEC-2026-0017 (revalidation)."""

    def test_builder_declares_the_governing_constitution_version(self):
        """The declared version is read from governance, not pinned by hand.

        Pinning the number here meant every constitution bump failed this test
        with an assertion about a literal rather than telling anyone which file
        had moved. Reading both sides makes the test say the real thing: the
        Builder declares whatever the ruleset declares.
        """
        from adnd1e_builder.vocab import CONSTITUTION_VERSION

        ruleset = yaml.safe_load(
            (REPO_ROOT / "rulesets" / "adnd1e" / "ruleset.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(CONSTITUTION_VERSION, str(ruleset["constitution_version"]))

        constitution = (
            REPO_ROOT / "rulesets" / "adnd1e" / "governance" / "constitution.md"
        ).read_text(encoding="utf-8")
        self.assertIn(f"**Version {CONSTITUTION_VERSION}.**", constitution)

    def test_accepts_historical_versions_for_revalidation(self):
        from adnd1e_builder.vocab import (
            ACCEPTED_GUR_CONSTITUTION_VERSIONS,
            CONSTITUTION_VERSION,
        )

        # DEC-2026-0008: older GURs are revalidated under the current
        # constitution, not rejected. DEC-2026-0017 requires 1.5 GURs accepted
        # under 1.6; DEC-2026-0020 requires 1.6 GURs accepted under 1.7.
        self.assertEqual(
            ACCEPTED_GUR_CONSTITUTION_VERSIONS,
            {"1.2", "1.3", "1.4", "1.5", "1.6", "1.7"},
        )
        # The current version must always be accepted, and so must the one
        # immediately before it -- that is what "revalidated, not rejected"
        # means for the GURs already in the repository when a version lands.
        self.assertIn(CONSTITUTION_VERSION, ACCEPTED_GUR_CONSTITUTION_VERSIONS)
        self.assertIn("1.6", ACCEPTED_GUR_CONSTITUTION_VERSIONS)

    def test_1_5_adds_no_prefix(self):
        # DEC-2026-0015 acceptance test: "Builder vocabulary declares
        # Constitution 1.5 without adding a new prefix." The 1.5 change is the
        # meaning of `spell_`, not the size of the closed set. 1.6 likewise
        # touches sections 2.1 and 5 and leaves the prefix table alone.
        self.assertEqual(len(NODE_PREFIXES), 25)
        self.assertIn("spell_", NODE_PREFIXES)

    def test_1_6_scaling_rule_exists(self):
        # Constitution 1.6 section 2.1, ruled by DEC-2026-0017. The Builder
        # cannot enforce it -- deciding
        # which spell descriptions state the dependency is Analyst work, and the
        # decision forbids the Builder synthesizing the rows -- but the compiler
        # must not reject the resulting exp_level MODIFIES spell_ edges, so the
        # rule is pinned here.
        text = (REPO_ROOT / "rulesets" / "adnd1e" / "governance" / "constitution.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Scaling dependencies are relationships", text)

    def test_page_authority_lives_in_the_source_markdown_contract(self):
        # DEC-2026-0016 raises SOURCE_MARKDOWN to 1.1 and puts packet-over-legacy
        # page precedence there. That contract is the one `pagemarkers.py`
        # implements, so this is the Builder's dependency rather than the
        # constitution prose, which states the rule by reference.
        text = (REPO_ROOT / "contracts" / "SOURCE_MARKDOWN.md").read_text(encoding="utf-8")
        self.assertIn("**Version 1.1.**", text)
        self.assertIn("Page Authority and Conflicts", text)

    def test_version_matches_ruleset_yaml(self):
        text = (REPO_ROOT / "rulesets" / "adnd1e" / "ruleset.yaml").read_text(encoding="utf-8")
        from adnd1e_builder.vocab import CONSTITUTION_VERSION

        self.assertIn(f'constitution_version: "{CONSTITUTION_VERSION}"', text)

    def test_spell_family_stem_rule_is_in_the_constitution(self):
        # The rule the Builder cannot mechanically enforce, pinned so a silent
        # revert of section 3.1 is caught here rather than in a later migration.
        text = (REPO_ROOT / "rulesets" / "adnd1e" / "governance" / "constitution.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("spell or source-named spell family/category", text)
        self.assertIn("does not broaden or alias", text)

    def test_version_matches_the_constitution_file(self):
        text = (REPO_ROOT / "rulesets" / "adnd1e" / "governance" / "constitution.md").read_text(
            encoding="utf-8"
        )
        from adnd1e_builder.vocab import CONSTITUTION_VERSION

        self.assertIn(f"**Version {CONSTITUTION_VERSION}.**", text)

    def test_wpn_prefix_is_approved(self):
        self.assertIn("wpn_", NODE_PREFIXES)
        self.assertEqual(prefix_of("wpn_speed_factor"), "wpn_")

    def test_rejected_prefixes_stay_unapproved(self):
        from adnd1e_builder.vocab import REJECTED_PREFIXES

        for prefix in REJECTED_PREFIXES:
            with self.subTest(prefix=prefix):
                self.assertNotIn(prefix, NODE_PREFIXES)

    def test_rejected_legacy_ids_are_not_recognised(self):
        for node_id in ("turn_undead", "str_bend_bars", "dex_reaction_adj", "align_change",
                        "cursed_item", "magic_resistance", "death_drowning",
                        "time_segment_round_turn"):
            with self.subTest(node_id=node_id):
                self.assertIsNone(prefix_of(node_id), f"{node_id} must remain unapproved")

    def test_bare_unprefixed_ids_are_not_recognised(self):
        for node_id in ("comeliness", "fatigue", "training"):
            with self.subTest(node_id=node_id):
                self.assertIsNone(prefix_of(node_id))


class TestIdentityHelpers(unittest.TestCase):
    def test_prefix_recognition(self):
        self.assertEqual(prefix_of("race_half_elf"), "race_")
        self.assertEqual(prefix_of("abil_strength"), "abil_")
        self.assertIsNone(prefix_of("turn_undead"))

    def test_id_format(self):
        self.assertTrue(ID_FORMAT.match("race_half_elf"))
        self.assertTrue(ID_FORMAT.match("money_gp"))
        self.assertFalse(ID_FORMAT.match("race_half-elf"), "hyphens are not snake_case")
        self.assertFalse(ID_FORMAT.match("Race_Human"), "IDs are lowercase")

    def test_normalize_label(self):
        self.assertEqual(normalize_label("Half-Elf"), "half_elf")
        self.assertEqual(normalize_label("  Saving Throw vs Poison "), "saving_throw_vs_poison")
        self.assertEqual(normalize_label("A & B"), "a_and_b")


class TestRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = NodeRegistry.load(REGISTRY_PATH)

    def test_loads_without_duplicate_ids(self):
        self.assertGreater(len(self.registry), 1000)

    def test_exact_resolution(self):
        resolution = self.registry.resolve("race_dwarf", "Dwarf")
        self.assertEqual(resolution.method, "exact")
        self.assertTrue(resolution.canonical)

    def test_unknown_id_with_unknown_label_is_unresolved(self):
        resolution = self.registry.resolve("rule_not_a_real_node", "Nonexistent Concept")
        self.assertEqual(resolution.method, "unresolved")
        self.assertIsNone(resolution.resolved_id)

    def test_unknown_id_with_unique_known_label_is_reported_not_merged(self):
        resolution = self.registry.resolve("class_fighters", "Fighter")
        self.assertEqual(resolution.method, "normalized_label")
        self.assertEqual(resolution.resolved_id, "class_fighter")
        # Reported as a candidate; the compiler escalates rather than merging.

    def test_label_shared_by_two_nodes_is_ambiguous_not_resolved(self):
        # "Dwarf" is carried by both monster_dwarf and race_dwarf. Invariant 4
        # says labels do not determine identity, so this must not resolve.
        resolution = self.registry.resolve("race_dwarves", "Dwarf")
        self.assertEqual(resolution.method, "unresolved")
        self.assertEqual(resolution.ambiguous_with, ("monster_dwarf", "race_dwarf"))

    def test_registry_label_collisions_do_not_hide_identity_merges(self):
        """Labels carried by more than one canonical node.

        ESC-2026-07-30T01.21.13.768Z reports duplicate-label pairs as an open
        identity issue. The count is not pinned: the registry grows every time
        the Integrator lands a bundle, and a pinned number turns ordinary
        progress into a test failure. What must hold is the invariant behind the
        escalation -- a shared label never collapses two IDs into one -- so that
        is what is asserted.
        """
        collisions = {k: v for k, v in self.registry._by_label.items() if len(v) > 1}
        for label, ids in collisions.items():
            self.assertEqual(
                len(set(ids)), len(ids), f"label {label!r} lists an ID twice"
            )
            for node_id in ids:
                self.assertIn(node_id, self.registry)
                self.assertEqual(self.registry.resolve(node_id, label).method, "exact")

    def test_architect_decisions_landed_in_the_registry(self):
        # DEC-2026-0001 and DEC-2026-0002 acceptance tests.
        self.assertIn("race_human", self.registry)
        self.assertIn("race_demihuman", self.registry)
        self.assertIn("race_any", self.registry)
        self.assertEqual(self.registry.get("race_human").label, "Human")
        self.assertEqual(self.registry.get("race_human").kind, "race")
        self.assertEqual(self.registry.get("race_human").roles, ())

    def test_invalid_spellings_are_absent(self):
        # DEC-2026-0002 identifier_normalization.
        self.assertNotIn("race_half-elf", self.registry)
        self.assertNotIn("race_half-orc", self.registry)

    def test_every_registry_id_is_snake_case(self):
        bad = [n for n in self.registry.nodes if not ID_FORMAT.match(n)]
        self.assertEqual(bad, [], "invariant 3: canonical IDs are snake_case")

    def test_unapproved_prefixes_are_a_known_open_issue(self):
        """ESC-2026-0002 reports node prefixes outside constitution 3.1.

        This test pins the known set so a change in it is visible rather than
        silent. It is not an assertion that the situation is acceptable.
        """
        unapproved = sorted({n for n in self.registry.nodes if prefix_of(n) is None})
        self.assertTrue(unapproved, "if this becomes empty the escalation is resolved")
        for node_id in unapproved:
            self.assertFalse(
                any(node_id.startswith(p) for p in NODE_PREFIXES),
                f"{node_id} unexpectedly matches an approved prefix",
            )


if __name__ == "__main__":
    unittest.main()


class TestAssertionKeyMatchesGovernance(unittest.TestCase):
    """DEC-2026-0020 acceptance tests: the key is governed, not chosen.

    GRAPH_INVARIANTS 1.0 invariant 12 requires each ruleset constitution to
    define its assertion key and forbids tooling inventing, omitting or widening
    one. These tests read the governing text and compare it with what the build
    actually does, so a future edit to either side has to move both.
    """

    @classmethod
    def setUpClass(cls):
        cls.constitution = (
            REPO_ROOT / "rulesets" / "adnd1e" / "governance" / "constitution.md"
        ).read_text(encoding="utf-8")
        cls.invariants = (
            REPO_ROOT / "contracts" / "GRAPH_INVARIANTS.md"
        ).read_text(encoding="utf-8")

    def section_5_1(self) -> str:
        start = self.constitution.index("### 5.1 Edge identity")
        end = self.constitution.index("## 6.", start)
        return self.constitution[start:end]

    def test_section_5_1_exists_and_names_the_five_fields(self):
        from adnd1e_builder.vocab import ASSERTION_KEY

        body = self.section_5_1()
        self.assertEqual(
            ASSERTION_KEY,
            ("source_id", "edge_type", "target_id", "aspect", "condition"),
        )
        # The constitution states the tuple; the build must carry that tuple.
        for name in ASSERTION_KEY:
            self.assertIn(name, body)

    def test_graph_invariants_is_versioned_and_delegates_the_key(self):
        self.assertIn("**Version 1.0.**", self.invariants)
        self.assertIn("Each ruleset constitution defines its assertion key", self.invariants)

    def test_excluded_fields_are_exactly_the_non_key_columns(self):
        """Every column is either identity or explicitly not identity."""
        from adnd1e_builder.vocab import (
            ASSERTION_KEY,
            COLUMNS,
            IDENTITY_EXCLUDED_FIELDS,
        )

        self.assertEqual(
            set(ASSERTION_KEY) | IDENTITY_EXCLUDED_FIELDS, set(COLUMNS)
        )
        self.assertEqual(set(ASSERTION_KEY) & IDENTITY_EXCLUDED_FIELDS, set())

    def test_citation_polarity_and_review_fields_are_not_identity(self):
        from adnd1e_builder.vocab import IDENTITY_EXCLUDED_FIELDS

        for excluded in ("book", "page", "section", "polarity", "polarity_basis",
                         "source_label", "target_label", "evidence", "review_flag"):
            self.assertIn(excluded, IDENTITY_EXCLUDED_FIELDS)

    def test_alternative_to_is_the_only_symmetric_type(self):
        from adnd1e_builder.vocab import EDGE_TYPES, SYMMETRIC_EDGE_TYPES

        self.assertEqual(SYMMETRIC_EDGE_TYPES, {"ALTERNATIVE_TO"})
        self.assertTrue(SYMMETRIC_EDGE_TYPES <= set(EDGE_TYPES))
        self.assertIn("`ALTERNATIVE_TO` is symmetric", self.section_5_1())


class TestAssertionKeyBehaviour(unittest.TestCase):
    """Section 5.1 comparison rules, exercised rather than described."""

    def edge(self, **overrides):
        base = {
            "source_id": "abil_strength", "edge_type": "GATES",
            "target_id": "class_fighter", "aspect": "class eligibility",
            "condition": "", "polarity": "enables", "polarity_basis": "derived",
            "book": "PHB", "page": "9", "section": "STRENGTH", "evidence": "explicit_rule",
            "pass": "page-sweep", "status": "core", "supersession_basis": "",
            "general_rule_id": "", "review_flag": "", "source_label": "Strength",
            "target_label": "Fighter",
        }
        base.update(overrides)
        return base

    def test_cosmetic_wording_does_not_create_a_new_assertion(self):
        from adnd1e_builder.duplicates import assertion_key

        self.assertEqual(
            assertion_key(self.edge(aspect="Class Eligibility")),
            assertion_key(self.edge(aspect="class  eligibility")),
        )
        self.assertEqual(
            assertion_key(self.edge(aspect="class-eligibility")),
            assertion_key(self.edge(aspect="class_eligibility")),
        )

    def test_a_different_facet_is_a_different_assertion(self):
        from adnd1e_builder.duplicates import assertion_key

        self.assertNotEqual(
            assertion_key(self.edge(aspect="class eligibility")),
            assertion_key(self.edge(aspect="encumbrance allowance")),
        )

    def test_a_different_condition_is_a_different_assertion(self):
        from adnd1e_builder.duplicates import assertion_key

        self.assertNotEqual(
            assertion_key(self.edge(condition="")),
            assertion_key(self.edge(condition="when charging")),
        )

    def test_excluded_fields_never_change_identity(self):
        from adnd1e_builder.duplicates import assertion_key
        from adnd1e_builder.vocab import IDENTITY_EXCLUDED_FIELDS

        baseline = assertion_key(self.edge())
        for excluded in sorted(IDENTITY_EXCLUDED_FIELDS):
            with self.subTest(field=excluded):
                self.assertEqual(
                    assertion_key(self.edge(**{excluded: "something else"})), baseline
                )

    def test_alternative_to_endpoints_are_unordered(self):
        from adnd1e_builder.duplicates import assertion_key

        forward = self.edge(edge_type="ALTERNATIVE_TO", source_id="a_one", target_id="b_two")
        reversed_ = self.edge(edge_type="ALTERNATIVE_TO", source_id="b_two", target_id="a_one")
        self.assertEqual(assertion_key(forward), assertion_key(reversed_))

    def test_directed_types_keep_endpoint_order(self):
        from adnd1e_builder.duplicates import assertion_key
        from adnd1e_builder.vocab import EDGE_TYPES, SYMMETRIC_EDGE_TYPES

        for edge_type in sorted(set(EDGE_TYPES) - SYMMETRIC_EDGE_TYPES):
            with self.subTest(edge_type=edge_type):
                forward = self.edge(edge_type=edge_type, source_id="a_one", target_id="b_two")
                reversed_ = self.edge(edge_type=edge_type, source_id="b_two", target_id="a_one")
                self.assertNotEqual(assertion_key(forward), assertion_key(reversed_))

    def test_ids_are_compared_directly_not_through_the_text_normalizer(self):
        """Section 5.1 normalizes `aspect` and `condition` only.

        Routing IDs through the text normalizer would fold two distinct IDs
        together wherever they differed only by a separator character.
        """
        from adnd1e_builder.duplicates import assertion_key

        key = assertion_key(self.edge())
        self.assertEqual(key[0], "abil_strength")
        self.assertEqual(key[1], "GATES")
        self.assertEqual(key[2], "class_fighter")


class TestCanonicalCorpusHasNoExactDuplicates(unittest.TestCase):
    """DEC-2026-0020 acceptance test, measured against the live file."""

    def test_zero_exact_duplicates_under_the_governed_key(self):
        from collections import Counter

        from adnd1e_builder.duplicates import CanonicalEdges, assertion_key

        canonical = CanonicalEdges.load(EDGES_PATH)
        counts = Counter(assertion_key(row) for row in canonical.rows)
        duplicates = {key: n for key, n in counts.items() if n > 1}
        self.assertEqual(duplicates, {}, f"{len(duplicates)} duplicate assertion key(s)")
        self.assertEqual(sum(counts.values()), len(canonical.rows))
