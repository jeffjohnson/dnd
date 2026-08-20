"""Node resolution and the controlled vocabularies."""

from __future__ import annotations

import re
import unittest

import yaml

import _bootstrap
from _bootstrap import REPO_ROOT

import json
import tempfile
from pathlib import Path

from adnd1e_builder.registry import (
    ID_FORMAT,
    NodeRegistry,
    load_applied_retirements,
    normalize_label,
    prefix_of,
)
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
        #
        # The set is asserted by its rule rather than by a literal. Pinning the
        # membership meant a constitution bump failed here with "these two sets
        # differ", which says nothing about what went wrong; and the literal was
        # what a bump was most likely to update carelessly, so it guarded the
        # weakest thing. The rule is: nothing is ever dropped, and every version
        # from the oldest accepted through the current one is contiguous.
        self.assertIn(CONSTITUTION_VERSION, ACCEPTED_GUR_CONSTITUTION_VERSIONS)
        for required in ("1.2", "1.3", "1.4", "1.5", "1.6", "1.7"):
            self.assertIn(
                required,
                ACCEPTED_GUR_CONSTITUTION_VERSIONS,
                f"{required} was accepted before and revalidation never drops a version",
            )

        def as_number(text):
            major, _, minor = text.partition(".")
            return (int(major), int(minor))

        ordered = sorted(ACCEPTED_GUR_CONSTITUTION_VERSIONS, key=as_number)
        self.assertEqual(
            ordered[-1],
            CONSTITUTION_VERSION,
            "the current constitution version must be the newest accepted one",
        )
        numbers = [as_number(v) for v in ordered]
        self.assertEqual(
            numbers,
            [(1, n) for n in range(numbers[0][1], numbers[-1][1] + 1)],
            "accepted versions must be contiguous; a gap would silently reject a GUR",
        )

    def constitution_prefixes(self) -> set[str]:
        """The prefix column of the section 3.1 table, read from governance."""
        import re

        text = (REPO_ROOT / "rulesets" / "adnd1e" / "governance" / "constitution.md").read_text(
            encoding="utf-8"
        )
        section = text.split("| Prefix | Kind | Example |", 1)[1]
        found = set()
        for line in section.splitlines():
            if not line.startswith("|"):
                if found:
                    break
                continue
            cell = line.split("|")[1].strip()
            match = re.fullmatch(r"`([a-z]+_)`", cell)
            if match:
                found.add(match.group(1))
        return found

    def test_the_prefix_set_is_exactly_the_constitution_table(self):
        """The closed set is closed by governance, not by a count in a test.

        This replaces an assertion that the set had 25 members. A count cannot
        distinguish "the Architect added `weapon_` at 1.8" from "someone widened
        the vocabulary to make a row fit", which is the thing worth catching,
        and it failed on every legitimate bump with a message about integers.
        """
        self.assertEqual(NODE_PREFIXES, self.constitution_prefixes())

    def test_1_5_adds_no_prefix(self):
        # DEC-2026-0015 acceptance test: "Builder vocabulary declares
        # Constitution 1.5 without adding a new prefix." The 1.5 change is the
        # meaning of `spell_`, not the size of the closed set.
        self.assertIn("spell_", NODE_PREFIXES)

    def test_1_8_separates_the_mundane_weapon_from_its_statistics(self):
        # DEC-2026-0033: `weapon_` is the mundane weapon identity, `wpn_` stays
        # a weapon property or statistic, and `item_` stays the magic-item
        # namespace. All three coexist; none replaces another.
        for prefix in ("weapon_", "wpn_", "item_"):
            self.assertIn(prefix, NODE_PREFIXES)

    def test_1_8_derived_ability_mechanics_use_the_six_abbreviations(self):
        # DEC-2026-0032: `abil_<abbrev>_<rule>` names a mechanic derived from a
        # score. The full-name score identities are untouched, so no new prefix
        # appears and `abil_` still covers both.
        from adnd1e_builder.vocab import ABILITY_ABBREVIATIONS

        self.assertEqual(
            ABILITY_ABBREVIATIONS, {"str", "dex", "con", "int", "wis", "cha"}
        )
        # DEC-2026-0004 rejected `str_` and `dex_` as prefixes. The abbreviation
        # is a stem *inside* `abil_`, and must not have reintroduced them.
        for rejected in ("str_", "dex_"):
            self.assertNotIn(rejected, NODE_PREFIXES)

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
        # page precedence there. DEC-2026-0025 raises it to 1.2 and adds
        # source-identity authority. DEC-2026-0027 raises it to 1.3 and names the
        # external source steward, which matters to the Builder because it is the
        # rule forbidding a missing locus from being routed back to the Analyst as
        # if it were readable work. That contract is the one `pagemarkers.py`
        # implements, so this is the Builder's dependency rather than the
        # constitution prose, which states the rule by reference.
        # 1.4 adds defining-locus-versus-secondary-mention. The version number
        # is asserted as a floor rather than an equality: the Builder's
        # dependency is that these sections exist, and pinning the exact
        # revision made a legitimate Architect amendment look like a defect.
        text = (REPO_ROOT / "contracts" / "SOURCE_MARKDOWN.md").read_text(encoding="utf-8")
        declared = re.search(r"^\*\*Version (\d+)\.(\d+)\.\*\*$", text, re.MULTILINE)
        self.assertIsNotNone(declared, "SOURCE_MARKDOWN.md declares no version")
        self.assertGreaterEqual(
            (int(declared.group(1)), int(declared.group(2))), (1, 3)
        )
        self.assertIn("Page Authority and Conflicts", text)
        self.assertIn("Source Identity Authority and Conflicts", text)
        self.assertIn("External Source Intake", text)

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



class TestRetiredIdentityResolution(unittest.TestCase):
    """A GUR authored before a merge integrates must still compile.

    A GUR is immutable and names the node IDs that were canonical the day the
    Analyst wrote it. When the merge it anticipated integrates first, those IDs
    leave the registry and the survivors arrive in their place --
    `GUR-PKT-UA-014-016-cavalier-r02` names `str_exceptional` for M048, and
    INT-20260818-001 retired it into `abil_str_exceptional` under DEC-2026-0038
    hours before the GUP was compiled.

    Before this, the retired ID resolved to nothing, the normalized-label
    fallback then found the survivor by its label, and the Builder correctly
    refused to trust that under invariant 4 -- so a whole packet stopped at an
    identity escalation the repository had already answered in writing.
    ESCALATION_CONTRACT is explicit that a known canonical ID is not an
    escalation, so escalating there was the wrong outcome, not merely a slow one.

    The two evidence sources are not interchangeable and this is the whole point
    of the ordering: a label match is a guess, while an Integration manifest's
    `nodes_retired` row is the Integrator's record of a transaction it committed
    under an approved Decision.
    """

    MANIFEST = {
        "integration_id": "INT-19700101-001",
        "registry_changes": {
            "nodes_retired": [
                {
                    "id": "str_exceptional",
                    "label": "Exceptional Strength",
                    "replaced_by": "abil_str_exceptional",
                    "authority": "DEC-2026-9999",
                    "operation": "merge",
                },
                # A retirement with no successor: a removal, nothing to repoint to.
                {"id": "gone_entirely", "label": "Gone", "authority": "DEC-2026-9999"},
                # A successor that never made it into the registry.
                {
                    "id": "points_nowhere",
                    "replaced_by": "abil_not_registered",
                    "authority": "DEC-2026-9999",
                },
            ]
        },
    }

    ROWS = [
        "id,label,kind,degree,roles",
        "abil_str_exceptional,Exceptional Strength,abil,9,",
        "abil_strength,Strength,abil,68,",
    ]

    #: Distinct from None, which would be ambiguous with "write no manifest".
    DEFAULT = object()

    def build(self, *, manifest=DEFAULT, rows=None):
        """A ruleset tree shaped like the real one: registries/ beside manifests/."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "registries").mkdir(parents=True)
        (root / "manifests").mkdir(parents=True)
        registry = root / "registries" / "nodes.csv"
        registry.write_text(
            "\n".join(self.ROWS if rows is None else rows) + "\n", encoding="utf-8"
        )
        document = self.MANIFEST if manifest is self.DEFAULT else manifest
        if document is not None:
            (root / "manifests" / "INT-19700101-001.json").write_text(
                json.dumps(document), encoding="utf-8"
            )
        return NodeRegistry.load(registry)

    def test_a_retired_id_resolves_to_its_recorded_survivor(self):
        resolution = self.build().resolve("str_exceptional", "Exceptional Strength")
        self.assertEqual(resolution.method, "retired_replacement")
        self.assertEqual(resolution.resolved_id, "abil_str_exceptional")
        self.assertTrue(resolution.canonical)

    def test_the_resolution_carries_the_record_that_justifies_it(self):
        """A Reviewer must be able to audit the substitution to its source."""
        resolution = self.build().resolve("str_exceptional", "Exceptional Strength")
        self.assertEqual(resolution.retirement_authority, "DEC-2026-9999")
        self.assertEqual(resolution.retirement_integration_id, "INT-19700101-001")
        self.assertIn("abil_str_exceptional", resolution.detail)
        self.assertIn("DEC-2026-9999", resolution.detail)

    def test_the_record_wins_over_the_label_fallback(self):
        """Both would answer here; only one of them is evidence.

        The label points at the same node, so the outcome looks identical -- but
        the method must show the retirement record, because that is what makes
        the answer checkable rather than lucky.
        """
        resolution = self.build().resolve("str_exceptional", "Exceptional Strength")
        self.assertEqual(resolution.method, "retired_replacement")
        self.assertNotEqual(resolution.method, "normalized_label")

    def test_a_retirement_with_no_successor_does_not_resolve(self):
        resolution = self.build().resolve("gone_entirely", "Gone")
        self.assertEqual(resolution.method, "unresolved")
        self.assertIsNone(resolution.resolved_id)

    def test_a_successor_absent_from_the_registry_does_not_resolve(self):
        """Repointing at an unregistered ID would breach invariant 1."""
        resolution = self.build().resolve("points_nowhere", "Whatever")
        self.assertEqual(resolution.method, "unresolved")

    def test_an_unrelated_unknown_id_is_untouched(self):
        self.assertEqual(self.build().resolve("no_such_node", "").method, "unresolved")

    def test_a_live_id_still_resolves_exactly(self):
        resolution = self.build().resolve("abil_strength", "Strength")
        self.assertEqual(resolution.method, "exact")

    def test_no_manifests_means_no_retirements_and_no_behaviour_change(self):
        registry = self.build(manifest=None)
        self.assertEqual(registry.retirements, {})
        # With nothing recorded, the label fallback is reached exactly as before.
        self.assertEqual(
            registry.resolve("str_exceptional", "Exceptional Strength").method,
            "normalized_label",
        )

    def test_an_unreadable_manifest_is_skipped_rather_than_fatal(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "registries").mkdir(parents=True)
        (root / "manifests").mkdir(parents=True)
        registry = root / "registries" / "nodes.csv"
        registry.write_text("\n".join(self.ROWS) + "\n", encoding="utf-8")
        (root / "manifests" / "broken.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(NodeRegistry.load(registry).retirements, {})


class TestLiveRetirementCorpus(unittest.TestCase):
    """The real registry and the real integration records."""

    def registry(self):
        return NodeRegistry.load(REGISTRY_PATH)

    def test_every_recorded_retirement_left_the_registry(self):
        registry = self.registry()
        if not registry.retirements:
            self.skipTest("no integration has retired a node yet")
        for retired in sorted(registry.retirements):
            self.assertNotIn(retired, registry, f"{retired} is retired but still registered")

    def test_every_recorded_survivor_is_registered_and_reachable(self):
        registry = self.registry()
        if not registry.retirements:
            self.skipTest("no integration has retired a node yet")
        for retired, row in sorted(registry.retirements.items()):
            self.assertIn(row["replaced_by"], registry)
            resolution = registry.resolve(retired, "")
            self.assertEqual(resolution.method, "retired_replacement")
            self.assertEqual(resolution.resolved_id, row["replaced_by"])

    def test_every_retirement_names_its_authority_decision(self):
        """An unattributed retirement could not be audited back to a ruling."""
        registry = self.registry()
        if not registry.retirements:
            self.skipTest("no integration has retired a node yet")
        for retired, row in sorted(registry.retirements.items()):
            self.assertRegex(row["authority"], r"^DEC-\d{4}-\d{4}$", retired)


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
        # 1.1 (DEC-2026-0029) scoped the grain requirements by provenance. The
        # delegation this test guards is untouched by that, and the version is
        # pinned so a future edit to either has to move both.
        self.assertIn("**Version 1.1.**", self.invariants)
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


class TestLegacyGrainConformanceScope(unittest.TestCase):
    """DEC-2026-0029: the grain cap binds new work, not the migrated corpus.

    46 percent of canonical breaches the four-word `aspect` cap. Every one of
    those rows arrived through the pre-Review 13-field import; work authored
    under Review conforms at 341 of 342 rows. The Architect scoped the rule
    rather than authorising a 1,919-row rewrite, because choosing a shorter
    phrase decides what a row asserts and that is source reading.

    The scope is **provenance-bound**. That is the part worth guarding: it is
    tempting to treat a long aspect, or a legacy-looking `pass` value, as proof
    a row is exempt, and the Decision prohibits exactly that. Builder's own
    escalation used `pass` as the proxy, which is why the rule says what it
    says.
    """

    @classmethod
    def setUpClass(cls):
        cls.invariants = (
            REPO_ROOT / "contracts" / "GRAPH_INVARIANTS.md"
        ).read_text(encoding="utf-8")

    def scope_section(self) -> str:
        start = self.invariants.index("## Legacy Migration Conformance Scope")
        return self.invariants[start : self.invariants.index("## Version History", start)]

    def test_the_exception_names_the_import_it_is_rooted_in(self):
        """An exception without a locus is an exception anyone can claim."""
        self.assertIn(
            "migrations/adnd1e/legacy-import/original/edges_master.csv", self.scope_section()
        )

    def test_eligibility_is_provenance_and_never_inferred(self):
        body = self.scope_section()
        self.assertIn("determined by provenance", body)
        for proxy in ("extraction pass", "row location", "word count"):
            self.assertIn(
                proxy, body,
                f"the scope must name {proxy!r} as something that does not establish eligibility",
            )

    def test_new_and_revised_rows_are_still_bound(self):
        body = self.scope_section()
        self.assertIn("every proposed\nGUP row and every revision", body)
        self.assertIn("must reject", body)

    def test_the_numeric_prohibitions_are_never_excepted(self):
        body = self.scope_section()
        for universal in ("magnitudes", "die expressions", "numeric bonuses", "threshold values"):
            self.assertIn(universal, body)

    def test_the_validator_still_rejects_a_long_aspect(self):
        """The contract scoped the rule; it did not soften the enforcement.

        A proposed row is new work whatever it resembles, so nothing about the
        historical exception may reach the validator.
        """
        from adnd1e_builder import grain

        findings = grain.check_aspect_length("different dice if entering via the ranks")
        self.assertEqual([f["severity"] for f in findings], ["error"])

    def test_the_validator_rejects_it_even_when_it_copies_an_excepted_row(self):
        """Verbatim from canonical, and still not admissible as new work.

        This is the exact aspect DEC-2026-0029 leaves standing in canonical. A
        row proposing it today is a revision, and the Decision says a revision
        of an excepted row must conform.
        """
        from adnd1e_builder import grain

        excepted = "acquisition cost at DM adjudication"
        self.assertTrue(
            any(f["severity"] == "error" for f in grain.check_aspect_length(excepted)),
            "an excepted legacy aspect must not become admissible by being legacy",
        )

    def test_the_validator_has_no_provenance_input_at_all(self):
        """The strongest guarantee available: it cannot grant the exception.

        `check_aspect_length` takes one string. There is no argument through
        which a caller could pass provenance, so no future edit can quietly
        teach the entry check to exempt a row.
        """
        import inspect

        from adnd1e_builder import grain

        parameters = list(inspect.signature(grain.check_aspect_length).parameters)
        self.assertEqual(parameters, ["value"])
        for name in ("pass", "provenance", "legacy", "row", "index"):
            self.assertNotIn(name, parameters)

    def test_grain_still_rejects_magnitudes_in_a_short_aspect(self):
        """Never-exempt requirements are independent of the word count."""
        from adnd1e_builder import grain

        rules = {f["rule"] for f in grain.check_field("aspect", "2d6 damage")}
        self.assertIn("grain_die_expression", rules)


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
