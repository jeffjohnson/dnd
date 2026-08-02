"""Node resolution and the controlled vocabularies."""

from __future__ import annotations

import unittest

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

    def test_constitution_version_is_1_6(self):
        from adnd1e_builder.vocab import CONSTITUTION_VERSION

        self.assertEqual(CONSTITUTION_VERSION, "1.6")

    def test_accepts_historical_versions_for_revalidation(self):
        from adnd1e_builder.vocab import ACCEPTED_GUR_CONSTITUTION_VERSIONS

        # DEC-2026-0008: older GURs are revalidated under the current
        # constitution, not rejected. DEC-2026-0017 acceptance test requires
        # 1.5 GURs to be accepted for revalidation under 1.6.
        self.assertEqual(
            ACCEPTED_GUR_CONSTITUTION_VERSIONS, {"1.2", "1.3", "1.4", "1.5", "1.6"}
        )
        self.assertIn("1.5", ACCEPTED_GUR_CONSTITUTION_VERSIONS)

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
