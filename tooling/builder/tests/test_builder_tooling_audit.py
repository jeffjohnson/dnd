"""
Independent Builder Validation and Stress Tests for Newly Authored Builder Tooling:
- manifest_gate.py (SourceEntityManifestGate)
- redirects.py (IdentityRedirectResolver)
- rules_retrieval.py (RulesRetrievalEngine)
"""

import sys
from pathlib import Path
import unittest

# Ensure builder src is on sys.path
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

REPO_ROOT = Path(__file__).resolve().parents[3]

from adnd1e_builder.manifest_gate import (
    SourceEntityManifestGate,
    ManifestGateError,
    verify_packet_manifest_completeness,
)
from adnd1e_builder.redirects import (
    IdentityRedirectResolver,
    IdentityRedirectRegistry,
)
from adnd1e_builder.rules_retrieval import RulesRetrievalEngine


class TestSourceEntityManifestGate(unittest.TestCase):
    """Stress tests for SourceEntityManifestGate (SD-015, UNIV-SRC-11, spec:UNIV-COV-05)."""

    def test_gate_passes_when_all_entities_present(self):
        manifest = {
            "packet_id": "PKT-SD-001",
            "required_entities": ["spell_sleep", "spell_magic_missile", "class_wizard"],
            "source_span": "SD p. 23-25",
        }
        gate = SourceEntityManifestGate(manifest)
        extracted = {"spell_sleep", "spell_magic_missile", "class_wizard", "extra_node"}
        self.assertTrue(gate.validate_packet_entities(extracted))

    def test_gate_raises_manifest_gate_error_on_missing_entity(self):
        manifest = {
            "packet_id": "PKT-SD-002",
            "required_entities": ["spell_sleep", "spell_hold_portal", "spell_light"],
            "source_span": "SD p. 44-46",
        }
        gate = SourceEntityManifestGate(manifest)
        extracted = {"spell_sleep", "spell_light"}

        with self.assertRaises(ManifestGateError) as ctx:
            gate.validate_packet_entities(extracted)

        err = ctx.exception
        self.assertIn("spell_hold_portal", err.missing_entities)
        self.assertEqual(err.source_span, "SD p. 44-46")
        self.assertIn("spell_hold_portal", str(err))
        self.assertIn("SD p. 44-46", str(err))

    def test_gate_handles_dict_entities(self):
        manifest = {
            "packet_id": "PKT-SD-003",
            "required_entities": [{"id": "item_longsword"}, {"id": "item_shortbow"}],
            "source_span": "SD p. 38",
        }
        gate = SourceEntityManifestGate(manifest)
        extracted = {"item_longsword"}

        with self.assertRaises(ManifestGateError) as ctx:
            gate.validate_packet_entities(extracted)

        err = ctx.exception
        self.assertEqual(err.missing_entities, ["item_shortbow"])
        self.assertEqual(err.source_span, "SD p. 38")

    def test_verify_packet_manifest_completeness_helper(self):
        res_fail = verify_packet_manifest_completeness(
            packet_id="PKT-004",
            expected_ids=["node_a", "node_b"],
            extracted_ids=["node_a"],
            source_file="span_test.md",
        )
        self.assertFalse(res_fail["valid"])
        self.assertEqual(res_fail["missing_ids"], ["node_b"])
        self.assertEqual(res_fail["source_file"], "span_test.md")

        res_pass = verify_packet_manifest_completeness(
            packet_id="PKT-004",
            expected_ids=["node_a", "node_b"],
            extracted_ids=["node_a", "node_b", "node_c"],
            source_file="span_test.md",
        )
        self.assertTrue(res_pass["valid"])
        self.assertEqual(res_pass["missing_ids"], [])


class TestIdentityRedirectResolver(unittest.TestCase):
    """Stress tests for IdentityRedirectResolver and Shadowdark redirect registry (SD-002, spec:SD-SPL-03)."""

    def setUp(self):
        self.registry_path = REPO_ROOT / "rulesets" / "shadowdark" / "registries" / "identity_redirects.yaml"
        self.assertTrue(self.registry_path.exists(), f"Registry file not found: {self.registry_path}")
        self.resolver = IdentityRedirectResolver(str(self.registry_path))

    def test_resolve_known_redirect(self):
        # Resolving spell_control_weather -> spell_control_water per DEC-2026-0109
        resolved = self.resolver.resolve("spell_control_weather")
        self.assertEqual(resolved, "spell_control_water")

    def test_resolve_unmapped_id(self):
        # Unmapped IDs resolve to themselves
        self.assertEqual(self.resolver.resolve("spell_cure_wounds"), "spell_cure_wounds")
        self.assertEqual(self.resolver.resolve("class_wizard"), "class_wizard")
        self.assertEqual(self.resolver.resolve("non_existent_node"), "non_existent_node")

    def test_chained_redirects(self):
        resolver = IdentityRedirectResolver()
        resolver.redirects = {
            "legacy_id_1": "legacy_id_2",
            "legacy_id_2": "canonical_id",
        }
        self.assertEqual(resolver.resolve("legacy_id_1"), "canonical_id")
        self.assertEqual(resolver.resolve("legacy_id_2"), "canonical_id")

    def test_cycle_detection(self):
        # 2-step cycle
        resolver = IdentityRedirectResolver()
        resolver.redirects = {
            "node_a": "node_b",
            "node_b": "node_a",
        }
        with self.assertRaises(ValueError) as ctx:
            resolver.resolve("node_a")
        self.assertIn("Circular redirect detected", str(ctx.exception))

        # 3-step cycle
        resolver.redirects = {
            "node_x": "node_y",
            "node_y": "node_z",
            "node_z": "node_x",
        }
        with self.assertRaises(ValueError) as ctx:
            resolver.resolve("node_x")
        self.assertIn("Circular redirect detected", str(ctx.exception))


class TestRulesRetrievalEngine(unittest.TestCase):
    """Stress tests for RulesRetrievalEngine query methods."""

    def setUp(self):
        self.engine = RulesRetrievalEngine()

    def test_wizard_sleep_in_plate_mail(self):
        detailed = self.engine.can_wizard_cast_sleep_in_plate_mail()
        self.assertFalse(detailed["allowed"])
        self.assertEqual(detailed["resolved_entities"]["class"], "class_wizard")
        self.assertEqual(detailed["resolved_entities"]["spell"], "spell_sleep")
        self.assertEqual(detailed["resolved_entities"]["armor"], "item_plate_mail")
        self.assertEqual(len(detailed["citations"]), 2)
        self.assertEqual(detailed["conclusion_basis"], "authoritative_source_passages")

        query = self.engine.query_wizard_sleep_in_plate()
        self.assertFalse(query["can_cast_in_armor"])
        self.assertIn("cannot cast spells while wearing armor", query["citation_text"])
        self.assertFalse(query["concluded_solely_from_edge"])

    def test_wizard_greatsword_usability_vs_category(self):
        detailed = self.engine.can_wizard_use_greatsword()
        self.assertTrue(detailed["is_weapon"])
        self.assertEqual(detailed["weapon_category"], "item_weapon")
        self.assertFalse(detailed["class_permitted"])
        self.assertEqual(detailed["permitted_weapons"], ["item_dagger", "item_staff"])
        self.assertIn("distinction", detailed)

        query = self.engine.query_wizard_greatsword()
        self.assertFalse(query["can_wield_effectively"])
        self.assertEqual(query["weapon_category"], "item_weapon")
        self.assertTrue(query["distinguishes_class_from_category"])

    def test_focus_damage_trigger(self):
        detailed = self.engine.focus_spellcaster_takes_damage()
        self.assertEqual(detailed["trigger"], "damage_taken_while_focusing")
        self.assertEqual(detailed["required_check"], "Constitution")
        self.assertEqual(detailed["dc_formula"], "max(10, damage_taken)")
        self.assertEqual(detailed["failure_effect"], "spell_ends")
        self.assertTrue(detailed["unrelated_spells_excluded"])

        query = self.engine.query_focus_damage()
        self.assertEqual(query["trigger"], "takes_damage")
        self.assertEqual(query["effect"], "spell_ends_immediately")
        self.assertEqual(query["unrelated_spells_included"], [])

    def test_dying_rules_fatality_mode_toggle(self):
        # Default dying (fatality mode disabled)
        detailed_def = self.engine.check_dying_rules(fatality_mode=False)
        self.assertEqual(detailed_def["active_rule"], "standard_dying")
        self.assertFalse(detailed_def["fatality_mode_active"])
        self.assertTrue(detailed_def["fatality_mode_searchable"])

        query_def = self.engine.query_dying_rules(fatality_mode_enabled=False)
        self.assertEqual(query_def["active_rule"], "default_dying")
        self.assertFalse(query_def["fatality_mode_active"])
        self.assertTrue(query_def["fatality_mode_searchable"])
        self.assertEqual(query_def["source_page"], 88)

        # Fatality mode enabled
        detailed_fat = self.engine.check_dying_rules(fatality_mode=True)
        self.assertEqual(detailed_fat["active_rule"], "fatality_mode_override")
        self.assertTrue(detailed_fat["fatality_mode_active"])
        self.assertIn("standard_dying", detailed_fat["override_targets"])

        query_fat = self.engine.query_dying_rules(fatality_mode_enabled=True)
        self.assertEqual(query_fat["active_rule"], "fatality_mode_override")
        self.assertTrue(query_fat["fatality_mode_active"])
        self.assertIn("die instantly", query_fat["override_text"])
        self.assertIn("unconscious and dying", query_fat["general_rule_text"])

    def test_priest_burning_hands_authoritative_list_check(self):
        detailed = self.engine.can_priest_cast_burning_hands()
        self.assertFalse(detailed["allowed"])
        self.assertFalse(detailed["on_priest_list"])
        self.assertTrue(detailed["on_wizard_list"])
        self.assertFalse(detailed["negative_edge_inferred"])
        self.assertEqual(detailed["evidence_basis"], "authoritative_class_spell_lists")

        query = self.engine.query_priest_burning_hands()
        self.assertFalse(query["priest_can_cast"])
        self.assertFalse(query["inferred_from_edge_absence"])
        self.assertEqual(query["authoritative_class"], "wizard")
        self.assertEqual(query["authoritative_tier"], 1)

    def test_dnd5e_edition_isolation(self):
        res_2014 = self.engine.query_cross_edition_rule("spell_cure_wounds", "2014")
        self.assertEqual(res_2014["ruleset_version"], "5e-2014")
        self.assertTrue(res_2014["isolated"])
        self.assertTrue(res_2014["cross_version_merge_prevented"])

        res_2024 = self.engine.query_cross_edition_rule("spell_cure_wounds", "2024")
        self.assertEqual(res_2024["ruleset_version"], "5e-2024")
        self.assertTrue(res_2024["isolated"])
        self.assertTrue(res_2024["cross_version_merge_prevented"])

        with self.assertRaises(ValueError):
            self.engine.query_cross_edition_rule("spell_cure_wounds", "1978")

        iso_query = self.engine.query_dnd5e_edition_isolation("spell_cure_wounds")
        self.assertTrue(iso_query["editions_isolated"])
        self.assertEqual(iso_query["editions"]["2014"]["source_revision"], "5e-2014")
        self.assertEqual(iso_query["editions"]["2024"]["source_revision"], "5e-2024")
        self.assertNotEqual(iso_query["editions"]["2014"]["healing_dice"], iso_query["editions"]["2024"]["healing_dice"])

    def test_dnd5e_weapon_proficiency_vs_wieldability(self):
        prof = self.engine.evaluate_unproficient_weapon_use("greatsword", proficient=True, edition="2024")
        self.assertTrue(prof["usable"])
        self.assertFalse(prof["prohibited"])
        self.assertEqual(prof["proficiency_bonus_applied"], 2)
        self.assertEqual(prof["attack_roll_bonus"], 5)

        unprof = self.engine.evaluate_unproficient_weapon_use("greatsword", proficient=False, edition="2024")
        self.assertTrue(unprof["usable"])
        self.assertFalse(unprof["prohibited"])
        self.assertEqual(unprof["proficiency_bonus_applied"], 0)
        self.assertEqual(unprof["attack_roll_bonus"], 3)

        query = self.engine.query_unproficient_weapon_use(character_class="wizard", weapon="greatsword")
        self.assertTrue(query["allowed_to_wield"])
        self.assertFalse(query["adds_proficiency_bonus"])
        self.assertEqual(query["attack_bonus_formula"], "STR_MOD")

    def test_out_of_corpus_reference_only_node(self):
        detailed = self.engine.get_reference_only_entry("spell_wish")
        self.assertEqual(detailed["entity_role"], "reference_only")
        self.assertEqual(detailed["definition_status"], "undefined_in_corpus")
        self.assertFalse(detailed["fake_definition_invented"])
        self.assertFalse(detailed["fake_tier_assigned"])

        query = self.engine.query_reference_only_node("spell_wish")
        self.assertTrue(query["is_reference_only"])
        self.assertFalse(query["has_invented_definition"])
        self.assertIsNone(query["tier"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
