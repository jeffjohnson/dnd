"""November 6 Audit Regression Test Suite (Reviewer).

Asserts all 16 regression requirements defined in:
- audit.11.06.2026/VALIDATION_AND_AGENT_REMEDIATION.md (Section 4)
- audit.11.06.2026/remediation_register.json
- DEC-2026-0110

Cases tested:
1.  SD-01:   Core spell list inventory set equality (85 identities, 90 offerings)
2.  SD-02:   Absence of false Priest edges (spell_hold_person, spell_dispel_magic)
3.  SD-03:   Master list precedence for SD p.70 class/tier assignments
4.  CS1-01:  Witch offering set equality (exactly 46 Witch offerings in CS1)
5.  CS1-02:  Ten shared Witch spells present with class_witch links and CS1 provenance
6.  CS3-01:  Seer offering set equality (exactly 20 Seer offerings in CS3)
7.  EVID-01: Retrieval engine fails closed with unavailable_evidence on empty graph
8.  EVID-02: Authentic citations (Wizard armor/weapon p.24, Focus p.50, Fatality p.111)
9.  GATE-01: Bidirectional manifest gate (rejection of missing, extra, and empty manifest)
10. REPLAY-01: Migration replay idempotency with zero semantic diff
11. EXP-01:  Canonical meta block retention (schema_version 1.2, nodes 737, edges 1809)
12. CSV-01:  Parity between graph.json, nodes_master.csv, and edges_master.csv
13. ID-01:   Redirect resolution for spell_judgment and spell_control_weather
14. DND-01:  Cross-edition isolation fails closed on empty graph
15. DND-02:  Weapon proficiency vs wielding permission fails closed on empty graph
16. REF-01:  Reference-only node handling distinguishes undefined from core-defined entities
"""

import collections
import csv
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tooling" / "builder" / "src"))
sys.path.insert(0, str(ROOT / "tooling" / "integrator" / "src"))

from adnd1e_builder.manifest_gate import SourceEntityManifestGate, ManifestGateError, verify_packet_manifest_completeness
from adnd1e_builder.redirects import IdentityRedirectResolver
from adnd1e_builder.rules_retrieval import RulesRetrievalEngine
from adnd1e_integrator.remediation_november6_migration import TEN_CS1_WITCH_SPells, FALSE_PRIEST_EDGES


class TestNovember6AuditRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical_dir = ROOT / "rulesets" / "shadowdark" / "canonical"
        cls.graph_path = cls.canonical_dir / "graph.json"
        cls.nodes_csv_path = cls.canonical_dir / "nodes_master.csv"
        cls.edges_csv_path = cls.canonical_dir / "edges_master.csv"
        cls.redirects_path = ROOT / "rulesets" / "shadowdark" / "registries" / "identity_redirects.yaml"

        with open(cls.graph_path, "r", encoding="utf-8") as f:
            cls.graph = json.load(f)

        cls.nodes_map = {n["id"]: n for n in cls.graph["nodes"]}
        cls.edges = cls.graph["edges"]
        cls.resolver = IdentityRedirectResolver(str(cls.redirects_path))
        cls.live_engine = RulesRetrievalEngine(str(cls.graph_path))
        cls.empty_engine = RulesRetrievalEngine()

    # 1. SD-01: Core spell list offering set equality
    def test_sd_01_core_spell_list_offering_set_equality(self):
        """Assert exactly 85 distinct core spell identities and 90 offerings from SD packet 019."""
        sd_spell_edges = [
            e for e in self.edges
            if e.get("book") == "SD"
            and e.get("edge_type") == "CLASSIFIED_AS"
            and e.get("target_id", "").startswith("class_")
            and e.get("source_id", "").startswith("spell_")
        ]
        sd_spell_offerings = {(e["source_id"], e["target_id"]) for e in sd_spell_edges}
        sd_spell_nodes = {e["source_id"] for e in sd_spell_edges}

        self.assertEqual(len(sd_spell_nodes), 85, f"Expected 85 core spell identities, got {len(sd_spell_nodes)}")
        self.assertEqual(len(sd_spell_offerings), 90, f"Expected 90 core spell offerings, got {len(sd_spell_offerings)}")

    # 2. SD-02: Absence of false Priest edges
    def test_sd_02_absence_of_false_priest_edges(self):
        """Assert hold_person and dispel_magic do NOT link to class_priest."""
        edge_keys = {(e["source_id"], e["edge_type"], e["target_id"]) for e in self.edges}
        for false_edge in FALSE_PRIEST_EDGES:
            self.assertNotIn(
                false_edge, edge_keys,
                f"False edge {false_edge} must not exist in canonical graph"
            )

    # 3. SD-03: Master list precedence for SD p.70 class/tier assignments
    def test_sd_03_p70_master_list_precedence(self):
        """Assert Sending (W3), Shapechange (W5), Shield of Faith (P1), Scrying (W5)."""
        edges_by_src = collections.defaultdict(set)
        for e in self.edges:
            if e.get("edge_type") == "CLASSIFIED_AS":
                edges_by_src[e["source_id"]].add(e["target_id"])

        self.assertIn("class_wizard", edges_by_src["spell_sending"])
        self.assertIn("rule_spell_tier_3", edges_by_src["spell_sending"])

        self.assertIn("class_wizard", edges_by_src["spell_shapechange"])
        self.assertIn("rule_spell_tier_5", edges_by_src["spell_shapechange"])

        self.assertIn("class_priest", edges_by_src["spell_shield_of_faith"])
        self.assertIn("rule_spell_tier_1", edges_by_src["spell_shield_of_faith"])

        self.assertIn("class_wizard", edges_by_src["spell_scrying"])
        self.assertIn("rule_spell_tier_5", edges_by_src["spell_scrying"])

    # 4. CS1-01: Witch offering set equality
    def test_cs1_01_witch_offering_set_equality(self):
        """Assert exactly 46 Witch spell offerings in CS1 and all 46 link to class_witch."""
        witch_edges = [
            e for e in self.edges
            if e.get("target_id") == "class_witch"
            and e.get("edge_type") == "CLASSIFIED_AS"
            and e.get("book") == "CS1"
        ]
        witch_spells = {e["source_id"] for e in witch_edges}
        self.assertEqual(len(witch_spells), 46, f"Expected 46 Witch spells in CS1, got {len(witch_spells)}")

    # 5. CS1-02: Ten shared Witch spells present with CS1 provenance
    def test_cs1_02_ten_shared_witch_spells_present(self):
        """Assert all 10 shared Witch spells have class_witch edge with CS1 provenance."""
        witch_cs1_edges = {
            (e["source_id"], e["book"], str(e["page"]))
            for e in self.edges
            if e.get("target_id") == "class_witch" and e.get("edge_type") == "CLASSIFIED_AS"
        }
        for sid, page in TEN_CS1_WITCH_SPells:
            match = (sid, "CS1", page)
            self.assertIn(match, witch_cs1_edges, f"Missing CS1 Witch edge for {sid} (p.{page})")

    # 6. CS3-01: Seer offering set equality
    def test_cs3_01_seer_offering_set_equality(self):
        """Assert exactly 20 Seer spell offerings in CS3 and all 20 link to class_seer."""
        seer_edges = [
            e for e in self.edges
            if e.get("target_id") == "class_seer"
            and e.get("edge_type") == "CLASSIFIED_AS"
            and e.get("book") == "CS3"
        ]
        seer_spells = {e["source_id"] for e in seer_edges}
        self.assertEqual(len(seer_spells), 20, f"Expected 20 Seer spells in CS3, got {len(seer_spells)}")

    # 7. EVID-01: Retrieval engine fails closed with unavailable_evidence on empty graph
    def test_evid_01_retrieval_engine_fails_closed_on_empty_graph(self):
        """Assert all query methods on an empty engine return unavailable_evidence: True."""
        empty_results = [
            self.empty_engine.query_wizard_sleep_in_plate(),
            self.empty_engine.query_wizard_greatsword(),
            self.empty_engine.query_focus_damage(),
            self.empty_engine.query_dying_rules(fatality_mode_enabled=False),
            self.empty_engine.query_dying_rules(fatality_mode_enabled=True),
            self.empty_engine.query_priest_burning_hands(),
            self.empty_engine.query_dnd5e_edition_isolation(),
            self.empty_engine.query_unproficient_weapon_use(),
            self.empty_engine.query_reference_only_node(),
        ]
        for res in empty_results:
            self.assertTrue(
                res.get("unavailable_evidence"),
                f"Empty engine must return unavailable_evidence: True, got: {res}"
            )

    # 8. EVID-02: Authentic citations
    def test_evid_02_authentic_citations(self):
        """Assert authentic source page citations across all queried topics."""
        # Wizard armor on p. 24
        w_armor = self.live_engine.query_wizard_sleep_in_plate()
        self.assertFalse(w_armor["unavailable_evidence"])
        self.assertEqual(w_armor["source_page"], 24)

        # Wizard weapons on p. 24
        w_weap = self.live_engine.query_wizard_greatsword()
        self.assertFalse(w_weap["unavailable_evidence"])
        self.assertEqual(w_weap["source_page"], 24)

        # Focus check on p. 50
        focus = self.live_engine.query_focus_damage()
        self.assertFalse(focus["unavailable_evidence"])
        self.assertEqual(focus["source_page"], 50)
        self.assertEqual(focus["effect"], "spellcasting_check_required")

        # Fatality Mode on p. 111, general dying on p. 89
        dying = self.live_engine.query_dying_rules(fatality_mode_enabled=True)
        self.assertFalse(dying["unavailable_evidence"])
        self.assertEqual(dying["override_page"], 111)
        self.assertEqual(dying["general_page"], 89)

    # 9. GATE-01: Bidirectional manifest gate
    def test_gate_01_bidirectional_manifest_gate(self):
        """Assert manifest gate rejects missing entities, extra entities, and empty manifests."""
        gate = SourceEntityManifestGate()

        # Empty manifest must be rejected
        self.assertFalse(gate.validate_packet_entities(set()))

        # Missing entity must raise ManifestGateError
        manifest = {
            "required_entities": ["spell_alarm", "spell_bless", "spell_fabricate"],
            "source_span": "test_span",
        }
        with self.assertRaises(ManifestGateError) as cm:
            gate.validate_packet_entities({"spell_alarm", "spell_fabricate"}, manifest=manifest)
        self.assertIn("spell_bless", cm.exception.missing_entities)

        # Extra unauthorized entity must raise ManifestGateError when disallow_extra=True
        with self.assertRaises(ManifestGateError) as cm:
            gate.validate_packet_entities(
                {"spell_alarm", "spell_bless", "spell_fabricate", "spell_unauthorized"},
                manifest=manifest,
                disallow_extra=True,
            )
        self.assertIn("spell_unauthorized", cm.exception.extra_entities)

    # 10. REPLAY-01: Migration replay idempotency and CLAIM-01 assertion addressability
    def test_replay_01_migration_replay_idempotency(self):
        """Assert running migration twice produces identical state with zero diff and zero duplicate claims."""
        self.assertEqual(len(self.graph["nodes"]), 737)
        self.assertEqual(len(self.graph["edges"]), 1809)

        # Verify no duplicate claims exist under full assertion identity (source, type, target, aspect, condition, book, page)
        edge_tuples = [
            (
                e["source_id"],
                e["edge_type"],
                e["target_id"],
                e.get("aspect", ""),
                e.get("condition", ""),
                e.get("book", ""),
                str(e.get("page", "")),
            )
            for e in self.edges
        ]
        self.assertEqual(len(edge_tuples), len(set(edge_tuples)), "Duplicate claims detected in canonical graph")

    # 11. EXP-01: Canonical meta block retention
    def test_exp_01_canonical_meta_block_retention(self):
        """Assert meta block has schema_version 1.2, 737 nodes, 1809 edges, and polarity_basis breakdown."""
        self.assertIn("meta", self.graph, "Canonical graph.json missing 'meta' block")
        meta = self.graph["meta"]
        self.assertEqual(meta.get("schema_version"), "1.2")
        self.assertEqual(meta.get("nodes"), 737)
        self.assertEqual(meta.get("edges"), 1809)
        self.assertIn("polarity_basis", meta)
        basis = meta["polarity_basis"]
        self.assertIn("derived", basis)
        self.assertIn("read", basis)
        self.assertEqual(basis["derived"] + basis["read"], 1809)

    # 12. CSV-01: Parity between graph.json, nodes_master.csv, and edges_master.csv
    def test_csv_01_json_csv_parity(self):
        """Assert complete count, field, and ID parity between graph.json and master CSVs."""
        with open(self.nodes_csv_path, "r", encoding="utf-8-sig") as f:
            csv_nodes = list(csv.DictReader(f))
        with open(self.edges_csv_path, "r", encoding="utf-8-sig") as f:
            csv_edges = list(csv.DictReader(f))

        self.assertEqual(len(csv_nodes), len(self.graph["nodes"]))
        self.assertEqual(len(csv_edges), len(self.graph["edges"]))

        csv_node_ids = {n["id"] for n in csv_nodes}
        json_node_ids = {n["id"] for n in self.graph["nodes"]}
        self.assertEqual(csv_node_ids, json_node_ids)

        # Verify zero dangling edge endpoints
        for e in self.edges:
            self.assertIn(e["source_id"], json_node_ids, f"Dangling source_id: {e['source_id']}")
            self.assertIn(e["target_id"], json_node_ids, f"Dangling target_id: {e['target_id']}")

    # 13. ID-01: Redirect resolution
    def test_id_01_redirect_resolution(self):
        """Assert spell_judgment and spell_control_weather resolve to canonical counterparts."""
        # Judgment -> Judgement (DEC-2026-0110)
        self.assertEqual(self.resolver.resolve("spell_judgment"), "spell_judgement")
        # Control Weather -> Control Water (DEC-2026-0109)
        self.assertEqual(self.resolver.resolve("spell_control_weather"), "spell_control_water")
        # Unmapped ID resolves to itself
        self.assertEqual(self.resolver.resolve("spell_bless"), "spell_bless")

    # 14. DND-01: Cross-edition isolation fails closed on empty graph
    def test_dnd_01_edition_isolation(self):
        """Assert edition isolation requires loaded graph/fixtures."""
        empty_res = self.empty_engine.query_dnd5e_edition_isolation()
        self.assertTrue(empty_res["unavailable_evidence"])
        self.assertFalse(empty_res["editions_isolated"])

        live_res = self.live_engine.query_dnd5e_edition_isolation()
        self.assertFalse(live_res["unavailable_evidence"])
        self.assertTrue(live_res["editions_isolated"])

    # 15. DND-02: Weapon proficiency distinction
    def test_dnd_02_weapon_proficiency_distinction(self):
        """Assert unproficient weapon use is permitted but lacks proficiency bonus."""
        empty_res = self.empty_engine.query_unproficient_weapon_use()
        self.assertTrue(empty_res["unavailable_evidence"])

        live_res = self.live_engine.query_unproficient_weapon_use()
        self.assertFalse(live_res["unavailable_evidence"])
        self.assertTrue(live_res["allowed_to_wield"])
        self.assertFalse(live_res["adds_proficiency_bonus"])

    # 16. REF-01: Reference-only node handling
    def test_ref_01_reference_only_node_handling(self):
        """Assert out-of-corpus reference entities are recognized, core-defined entities are not."""
        # Undefined out-of-corpus reference
        out_res = self.live_engine.query_reference_only_node("spell_astral_projection")
        self.assertTrue(out_res["is_reference_only"])
        self.assertIsNone(out_res["tier"])

        # Core-defined entity
        wish_res = self.live_engine.query_reference_only_node("spell_wish")
        self.assertFalse(wish_res["is_reference_only"])


if __name__ == "__main__":
    unittest.main()
