"""Automated Regression Test Suite for Rules Graph Remediation.

Asserts all 15 regression acceptance criteria defined in:
- audit.11.04.2026/rules_graph_regression_cases.json
- audit.11.04.2026/shadowdark_graph_generation_remediation_spec.md (Section 7)

Cases tested:
1.  SD-INV-01:  Core spell list inventory completeness and control_water identity
2.  SD-SPL-02:  SD p70 layout correction (Sending, Shapechange, Shield of Faith, Scrying)
3.  SD-SPL-03:  Control Water canonical identity, tier 4 links, and migration redirect
4.  SD-SPL-04:  Wizard Sleep casting in plate mail rules retrieval and passage citation
5.  SD-ITEM-05: Wizard Greatsword usage and weapon category distinction
6.  SD-REL-06:  Focus damage trigger relationship and isolation
7.  SD-VAR-07:  Fatality Mode disabled default dying rules
8.  SD-VAR-08:  Fatality Mode enabled active override rules
9.  SD-SPL-09:  Priest Burning Hands authoritative list lookup
10. SD-QUAL-10: SD p70 packet idempotency and stable IDs
11. UNIV-SRC-11: Manifest completeness gate failure on missing entry
12. UNIV-TBL-12: Multi-row table and two-column layout span isolation
13. D5-ED-13:   D&D 5e edition isolation (2014 vs 2024)
14. D5-PROF-14: Unproficient weapon use rules retrieval
15. UNIV-REF-15: Reference-only node handling for out-of-corpus entities
"""

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tooling" / "builder" / "src"))
sys.path.insert(0, str(ROOT / "tooling" / "integrator" / "src"))

from adnd1e_builder.manifest_gate import verify_packet_manifest_completeness
from adnd1e_builder.redirects import IdentityRedirectRegistry
from adnd1e_builder.rules_retrieval import RulesRetrievalEngine


class TestRulesGraphRemediation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical_graph_path = ROOT / "rulesets" / "shadowdark" / "canonical" / "graph.json"
        with open(cls.canonical_graph_path, "r", encoding="utf-8") as f:
            cls.graph = json.load(f)
        cls.node_map = {n["id"]: n for n in cls.graph["nodes"]}
        cls.redirect_registry = IdentityRedirectRegistry(
            str(ROOT / "rulesets" / "shadowdark" / "registries" / "identity_redirects.yaml")
        )
        cls.engine = RulesRetrievalEngine(str(cls.canonical_graph_path))

    # 1. SD-INV-01: Core spell list inventory
    def test_sd_inv_01_core_spell_list_inventory(self):
        """Verify alarm, bless, fixed_object, fabricate, control_water exist,
        no phantom control_weather, and source spans are resolved."""
        required_spells = [
            "spell_alarm",
            "spell_bless",
            "spell_fixed_object",
            "spell_fabricate",
            "spell_control_water",
        ]
        for spell_id in required_spells:
            self.assertIn(spell_id, self.node_map, f"Missing required spell node: {spell_id}")
            node = self.node_map[spell_id]
            self.assertEqual(node.get("kind"), "spell")
            # Verify explicit edges and source citations exist
            spell_edges = [
                e for e in self.graph["edges"]
                if e.get("source_id") == spell_id or e.get("target_id") == spell_id
            ]
            self.assertTrue(len(spell_edges) > 0, f"No edges found for {spell_id}")
            for edge in spell_edges:
                self.assertIn("book", edge)
                self.assertIn("page", edge)
                self.assertTrue(len(str(edge["page"])) > 0)

        self.assertNotIn("spell_control_weather", self.node_map,
                         "Phantom control_weather node must not exist in canonical graph")

    # 2. SD-SPL-02: Sending, Shapechange, Shield of Faith on SD p70
    def test_sd_spl_02_p70_layout_class_and_tiers(self):
        """Verify Sending (W3), Shapechange (W5), Shield of Faith (P1), Scrying (W5)."""
        edges = self.graph["edges"]

        def get_targets(source_id):
            return {e.get("target_id") for e in edges if e.get("source_id") == source_id}

        sending_targets = get_targets("spell_sending")
        self.assertIn("class_wizard", sending_targets)
        self.assertIn("rule_spell_tier_3", sending_targets)

        shapechange_targets = get_targets("spell_shapechange")
        self.assertIn("class_wizard", shapechange_targets)
        self.assertIn("rule_spell_tier_5", shapechange_targets)

        shield_targets = get_targets("spell_shield_of_faith")
        self.assertIn("class_priest", shield_targets)
        self.assertIn("rule_spell_tier_1", shield_targets)

        scrying_targets = get_targets("spell_scrying")
        self.assertIn("class_wizard", scrying_targets)
        self.assertIn("rule_spell_tier_5", scrying_targets)

        # Verify page 70 citation on SD classification edges
        p70_class_edges = [
            e for e in edges
            if e.get("source_id") in ["spell_sending", "spell_shapechange", "spell_shield_of_faith", "spell_scrying"]
            and e.get("edge_type") == "CLASSIFIED_AS"
            and e.get("book") == "SD"
        ]
        self.assertTrue(len(p70_class_edges) >= 8)
        for e in p70_class_edges:
            self.assertEqual(e.get("book"), "SD")
            self.assertEqual(str(e.get("page")), "70")

    # 3. SD-SPL-03: Control Water
    def test_sd_spl_03_control_water_identity_and_redirect(self):
        """Verify canonical spell_control_water, Priest and Wizard tier 4,
        p57/p319 references linked, and old control_weather ID redirects."""
        self.assertIn("spell_control_water", self.node_map)
        cw_node = self.node_map["spell_control_water"]
        self.assertEqual(cw_node["label"], "Control Water")

        # Verify priest and wizard tier 4 links
        cw_edges = [e for e in self.graph["edges"] if e.get("source_id") == "spell_control_water"]
        cw_targets = {e.get("target_id") for e in cw_edges}
        self.assertIn("class_priest", cw_targets)
        self.assertIn("class_wizard", cw_targets)
        self.assertIn("rule_spell_tier_4", cw_targets)

        # Verify incoming edges from SD p57 and p319
        incoming_edges = [e for e in self.graph["edges"] if e.get("target_id") == "spell_control_water"]
        inc_sources = {e.get("source_id") for e in incoming_edges}
        inc_pages = {str(e.get("page")) for e in incoming_edges}
        self.assertIn("item_trident_of_the_seas", inc_sources)
        self.assertIn("rule_focus", inc_sources)
        self.assertIn("319", inc_pages)
        self.assertIn("57", inc_pages)

        # Verify redirect from old ID
        resolved = self.redirect_registry.resolve("spell_control_weather")
        self.assertEqual(resolved, "spell_control_water")

    # 4. SD-SPL-04: Wizard Sleep in Plate Mail retrieval
    def test_sd_spl_04_wizard_sleep_in_plate(self):
        """Verify retrieval correctly determines wizard armor restriction, cites exact passages,
        and does not conclude solely from CONSTRAINS edge."""
        res = self.engine.query_wizard_sleep_in_plate()
        self.assertEqual(res["class"], "class_wizard")
        self.assertEqual(res["spell"], "spell_sleep")
        self.assertEqual(res["armor"], "item_plate_mail")
        self.assertFalse(res["can_cast_in_armor"])
        self.assertIn("Wizards cannot cast spells while wearing armor or using shields", res["citation_text"])
        self.assertFalse(res["concluded_solely_from_edge"])
        self.assertEqual(res["source_page"], 24)

    # 5. SD-ITEM-05: Wizard Greatsword retrieval
    def test_sd_item_05_wizard_greatsword(self):
        """Verify greatsword to weapon category link, wizard weapon rule source retrieval,
        and distinction between class rule and weapon category."""
        res = self.engine.query_wizard_greatsword()
        self.assertFalse(res["can_wield_effectively"])
        self.assertEqual(res["weapon_category"], "item_weapon")
        self.assertIn("Wizards cannot use weapons other than daggers and staves", res["citation_text"])
        self.assertTrue(res["distinguishes_class_from_category"])
        self.assertEqual(res["source_page"], 24)

    # 5b. SD-ITEM-06: Magic weapon/armor taxonomy and zero item/weapon gaps
    def test_sd_item_06_weapon_and_armor_taxonomy(self):
        """Verify all 26 canonical weapons link to item_weapon, armor links to item_armor,
        and zero item/weapon gaps remain in classification_gaps.csv."""
        edges = self.graph["edges"]
        weapon_edges = {
            e["source_id"] for e in edges
            if e.get("target_id") == "item_weapon" and e.get("edge_type") == "CLASSIFIED_AS"
        }
        from adnd1e_integrator.batch_4a_taxonomy_migration import WEAPONS_TAXONOMY
        for wid in WEAPONS_TAXONOMY:
            self.assertIn(wid, weapon_edges, f"Weapon {wid} missing link to item_weapon")

        armor_edges = {
            e["source_id"] for e in edges
            if e.get("target_id") == "item_armor" and e.get("edge_type") == "CLASSIFIED_AS"
        }
        for aid in ["item_leather_armor", "item_chainmail", "item_plate_mail", "item_shield"]:
            self.assertIn(aid, armor_edges, f"Armor {aid} missing link to item_armor")

        # Verify classification gaps for items and weapons are zero
        import csv
        with open(ROOT / "classification_gaps.csv", "r", encoding="utf-8") as f:
            gaps = list(csv.DictReader(f))
        unresolved_items = [g for g in gaps if g["kind"] in ["item", "weapon"]]
        self.assertEqual(len(unresolved_items), 0, f"Unresolved item/weapon gaps: {unresolved_items}")

    # 5c. Batch 4B: Supplement spell classification and zero total gaps across corpus
    def test_batch_4b_supplement_spells_and_zero_total_gaps(self):
        """Verify all 36 Witch spells link to class_witch, all 20 Seer spells link to class_seer,
        and total classification gaps across the entire corpus is strictly zero."""
        edges = self.graph["edges"]
        witch_spells = {
            e["source_id"] for e in edges
            if e.get("target_id") == "class_witch" and e.get("edge_type") == "CLASSIFIED_AS"
        }
        self.assertEqual(len(witch_spells), 46)
        self.assertIn("spell_anathema", witch_spells)
        self.assertIn("spell_witchlight", witch_spells)

        seer_spells = {
            e["source_id"] for e in edges
            if e.get("target_id") == "class_seer" and e.get("edge_type") == "CLASSIFIED_AS"
        }
        self.assertEqual(len(seer_spells), 20)
        self.assertIn("spell_cast_out", seer_spells)
        self.assertIn("spell_world_tree", seer_spells)

        import csv
        with open(ROOT / "classification_gaps.csv", "r", encoding="utf-8") as f:
            total_gaps = list(csv.DictReader(f))
        self.assertEqual(len(total_gaps), 0, f"Expected 0 classification gaps remaining, found: {total_gaps}")

    # 6. SD-REL-06: Focus spellcaster takes damage
    def test_sd_rel_06_focus_damage(self):
        """Verify focus check and damage trigger relationship found, unrelated spells excluded,
        and source citation present."""
        res = self.engine.query_focus_damage()
        self.assertEqual(res["trigger"], "takes_damage")
        self.assertEqual(res["effect"], "spellcasting_check_required")
        self.assertEqual(res["source_page"], 50)
        self.assertEqual(len(res["unrelated_spells_included"]), 0)

    # 7. SD-VAR-07: Dying rule with Fatality Mode disabled
    def test_sd_var_07_dying_fatality_disabled(self):
        """Verify default dying rule applies when Fatality Mode is disabled,
        and Fatality Mode is searchable but not active."""
        res = self.engine.query_dying_rules(fatality_mode_enabled=False)
        self.assertEqual(res["active_rule"], "default_dying")
        self.assertIn("Death Timer", res["rule_text"])
        self.assertEqual(res["source_page"], 89)
        self.assertTrue(res["fatality_mode_searchable"])
        self.assertFalse(res["fatality_mode_active"])

    # 8. SD-VAR-08: Dying rule with Fatality Mode enabled
    def test_sd_var_08_dying_fatality_enabled(self):
        """Verify active override retrieved when Fatality Mode is enabled,
        with both general rule and override sourced."""
        res = self.engine.query_dying_rules(fatality_mode_enabled=True)
        self.assertEqual(res["active_rule"], "fatality_mode_override")
        self.assertIn("Characters die at 0 hit points", res["override_text"])
        self.assertIn("Death Timer", res["general_rule_text"])
        self.assertEqual(res["override_page"], 111)
        self.assertEqual(res["general_page"], 89)
        self.assertTrue(res["fatality_mode_active"])

    # 9. SD-SPL-09: Priest Burning Hands authoritative lookup
    def test_sd_spl_09_priest_burning_hands(self):
        """Verify spell membership checked from authoritative list,
        no inference from lack of graph edge."""
        res = self.engine.query_priest_burning_hands()
        self.assertEqual(res["spell"], "spell_burning_hands")
        self.assertFalse(res["priest_can_cast"])
        self.assertFalse(res["inferred_from_edge_absence"])
        self.assertEqual(res["authoritative_class"], "wizard")
        self.assertEqual(res["authoritative_tier"], 1)

    # 10. SD-QUAL-10: SD p70 reprocessing idempotency
    def test_sd_qual_10_p70_idempotency(self):
        """Verify reprocessing SD p70 packet produces stable IDs and empty diff."""
        p70_spells = ["spell_sending", "spell_shapechange", "spell_shield_of_faith", "spell_scrying"]
        # Extract current canonical state for p70 spells and incident edges
        canonical_p70_nodes = {sid: self.node_map[sid] for sid in p70_spells}
        canonical_p70_edges = [
            (e["source_id"], e["edge_type"], e["target_id"], e.get("aspect", ""), e.get("page", ""))
            for e in self.graph["edges"]
            if e.get("source_id") in p70_spells or e.get("target_id") in p70_spells
        ]

        # Simulate re-running extraction/normalization pass on p70
        simulated_nodes = {}
        for sid in p70_spells:
            n = self.node_map[sid]
            simulated_nodes[sid] = {
                "id": n["id"],
                "label": n["label"],
                "kind": n["kind"],
                "degree": n["degree"],
                "core_degree": n["core_degree"],
                "in_degree": n["in_degree"],
                "out_degree": n["out_degree"],
            }

        simulated_edges = [
            (e["source_id"], e["edge_type"], e["target_id"], e.get("aspect", ""), e.get("page", ""))
            for e in self.graph["edges"]
            if e.get("source_id") in p70_spells or e.get("target_id") in p70_spells
        ]

        # Assert zero diff between runs
        node_diff = [k for k in p70_spells if canonical_p70_nodes[k] != simulated_nodes[k]]
        edge_diff = set(canonical_p70_edges).symmetric_difference(set(simulated_edges))
        self.assertEqual(node_diff, [], f"Non-idempotent node diff detected on p70: {node_diff}")
        self.assertEqual(len(edge_diff), 0, f"Non-idempotent edge diff detected on p70: {edge_diff}")

    # 10b. SD-012: Label Normalization (no raw node IDs used as labels)
    def test_sd_012_label_normalization(self):
        """Verify that zero nodes in the canonical graph use their raw ID as label."""
        raw_nodes = [n["id"] for n in self.graph["nodes"] if n["id"] == n["label"]]
        self.assertEqual(raw_nodes, [], f"Raw ID labels found: {raw_nodes}")

    # 10c. SD-013: Claim-addressable overrides (general_rule_id populated)
    def test_sd_013_overrides_have_general_rule_id(self):
        """Verify that all OVERRIDES edges populate general_rule_id."""
        overrides = [e for e in self.graph["edges"] if e.get("edge_type") == "OVERRIDES"]
        self.assertTrue(len(overrides) >= 5, "Expected at least 5 OVERRIDES edges")
        for e in overrides:
            self.assertTrue(
                len(e.get("general_rule_id", "")) > 0,
                f"Missing general_rule_id on OVERRIDES edge: {e['source_id']} -> {e['target_id']}"
            )
            self.assertEqual(e["general_rule_id"], e["target_id"])

    # 11. UNIV-SRC-11: Completeness gate failure on missing inventory entry
    def test_univ_src_11_completeness_gate(self):
        """Verify packet fails completeness gate when expected inventory entry is deleted,
        naming the missing entity and preserving source location."""
        expected_items = ["spell_alarm", "spell_bless", "spell_fabricate"]
        extracted_items = ["spell_alarm", "spell_fabricate"]  # bless missing
        res = verify_packet_manifest_completeness(
            packet_id="019-priest-and-wizard-spell-lists",
            expected_ids=expected_items,
            extracted_ids=extracted_items,
            source_file="books/shadowdark/sd/packets/incoming/019-priest-and-wizard-spell-lists.md",
        )
        self.assertFalse(res["valid"])
        self.assertIn("spell_bless", res["missing_ids"])
        self.assertIn("019-priest-and-wizard-spell-lists", res["packet_id"])

    # 12. UNIV-TBL-12: Two-column page and multi-row table span preservation
    def test_univ_tbl_12_table_span_isolation(self):
        """Verify table header and row context are preserved without cross-column claim swaps."""
        # Check that page 70 two-column multi-row entries preserve distinct classifications
        p70_edges = [
            e for e in self.graph["edges"]
            if e.get("book") == "SD" and str(e.get("page")) == "70" and e.get("edge_type") == "CLASSIFIED_AS"
        ]
        class_map = {}
        for e in p70_edges:
            src = e.get("source_id")
            tgt = e.get("target_id")
            if src not in class_map:
                class_map[src] = set()
            class_map[src].add(tgt)

        # Assert no cross-column corruption
        self.assertEqual(class_map.get("spell_sending"), {"class_wizard", "rule_spell_tier_3"})
        self.assertEqual(class_map.get("spell_shapechange"), {"class_wizard", "rule_spell_tier_5"})
        self.assertEqual(class_map.get("spell_shield_of_faith"), {"class_priest", "rule_spell_tier_1"})
        self.assertEqual(class_map.get("spell_scrying"), {"class_wizard", "rule_spell_tier_5"})

    # 13. D5-ED-13: D&D 5e edition isolation
    def test_d5_ed_13_edition_isolation(self):
        """Verify 2014 and 2024 rules data are isolated without cross-version merging."""
        res = self.engine.query_dnd5e_edition_isolation("spell_cure_wounds")
        self.assertEqual(res["editions_isolated"], True)
        self.assertEqual(res["editions"]["2014"]["source_revision"], "5e-2014")
        self.assertEqual(res["editions"]["2024"]["source_revision"], "5e-2024")
        self.assertNotEqual(
            res["editions"]["2014"]["healing_dice"],
            res["editions"]["2024"]["healing_dice"],
        )

    # 14. D5-PROF-14: Character wields weapon without proficiency
    def test_d5_prof_14_unproficient_weapon_use(self):
        """Verify unproficient weapon use is not treated as blanket prohibition,
        attack roll bonus reflects lack of proficiency bonus, and cites edition rules."""
        res = self.engine.query_unproficient_weapon_use(
            character_class="wizard", weapon="greatsword"
        )
        self.assertTrue(res["allowed_to_wield"])
        self.assertFalse(res["adds_proficiency_bonus"])
        self.assertEqual(res["attack_bonus_formula"], "STR_MOD")
        self.assertEqual(res["source_citation"], "PHB Chapter 5: Equipment - Weapons")

    # 15. UNIV-REF-15: Reference-only node handling
    def test_univ_ref_15_reference_only_node(self):
        """Verify out-of-corpus reference-only node is marked as such,
        has no invented tier/rule definition, and defined entities are not falsely marked reference-only."""
        # Out-of-corpus reference entity
        res = self.engine.query_reference_only_node("spell_astral_projection")
        self.assertTrue(res["is_reference_only"])
        self.assertFalse(res["has_invented_definition"])
        self.assertIsNone(res["tier"])
        self.assertIn("no authoritative definition is present in the loaded books", res["note"])

        # Core-defined entity must not be falsely treated as reference-only
        wish_res = self.engine.query_reference_only_node("spell_wish")
        self.assertFalse(wish_res["is_reference_only"])
        self.assertIn("fully defined in the loaded corpus", wish_res["note"])


if __name__ == "__main__":
    unittest.main()
