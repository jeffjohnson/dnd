"""Architect decisions as compiler input.

DEC-2026-0003 (node registration routing), DEC-2026-0004 (prefix governance and
the migration map), DEC-2026-0005 (escalation package assignment).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap
from _bootstrap import REPO_ROOT

from adnd1e_builder.compiler import Compiler
from adnd1e_builder.duplicates import CanonicalEdges
from adnd1e_builder.governance import Governance
from adnd1e_builder.registry import NodeRegistry

RULESET_ROOT = REPO_ROOT / "rulesets" / "adnd1e"


class TestLoadedFromRepository(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gov = Governance.load(RULESET_ROOT)

    def test_only_approved_decisions_are_loaded(self):
        self.assertTrue(self.gov.decisions_loaded)
        for decision_id in self.gov.decisions_loaded:
            self.assertTrue(decision_id.startswith("DEC-"))

    def test_migration_map_carries_the_sixteen_rejected_ids(self):
        # DEC-2026-0004 migration_scope: 16 nodes require a reviewed replacement.
        self.assertEqual(len(self.gov.migration_map), 16)

    def test_migration_targets_match_the_decision(self):
        self.assertEqual(self.gov.migration_target("turn_undead"), "rule_turn_undead")
        self.assertEqual(self.gov.migration_target("str_bend_bars"), "abil_strength_bend_bars")
        self.assertEqual(self.gov.migration_target("comeliness"), "abil_comeliness")
        self.assertEqual(self.gov.migration_source("turn_undead")
                         if callable(getattr(self.gov, "migration_source", None))
                         else self.gov.migration_source["turn_undead"], "DEC-2026-0004")

    def test_wpn_nodes_are_not_on_the_migration_list(self):
        # DEC-2026-0004: keep the seven wpn_ IDs unchanged.
        for node_id in ("wpn_length", "wpn_range", "wpn_space_required", "wpn_speed_factor",
                        "wpn_stats", "wpn_type_vs_ac", "wpn_weight"):
            with self.subTest(node_id=node_id):
                self.assertIsNone(self.gov.migration_target(node_id))

    def test_four_nodes_returned_to_normal_workflow(self):
        returned = set(self.gov.nodes_returned_to_workflow)
        self.assertEqual(
            returned,
            {"rule_prime_requisite", "rule_revivification_limit", "rule_tracking",
             "rule_dual_class"},
        )
        for node_id in returned:
            self.assertEqual(self.gov.nodes_returned_to_workflow[node_id], "DEC-2026-0003")

    def test_racial_detection_is_now_a_rejected_identity(self):
        """DEC-2026-0009 refused it and named a replacement.

        It was previously held by an open escalation. Now it is decided, so the
        hold is gone and a rejection with a named substitute takes its place.
        """
        self.assertIsNone(self.gov.held_by_package("rule_racial_detection"))
        rejected = self.gov.rejected_identity("rule_racial_detection")
        self.assertIsNotNone(rejected)
        self.assertEqual(rejected["replacement_id"], "rule_detection")
        self.assertEqual(rejected["decision_id"], "DEC-2026-0009")

    def test_a_decided_escalation_holds_nothing(self):
        for node_id, held in self.gov.nodes_held_by_package.items():
            with self.subTest(node_id=node_id):
                self.assertFalse(
                    self.gov.is_decided(held["reserved_escalation_id"]),
                    f"{node_id} is held by an escalation that has already been decided",
                )

    def test_architect_row_dispositions_are_loaded(self):
        e7 = self.gov.row_disposition("PKT-PHB-007-008-intro", "E7")
        self.assertEqual(e7["decision_id"], "DEC-2026-0008")
        self.assertEqual(e7["fields"]["page"], "7")
        self.assertEqual(e7["fields"]["section"], "THE GAME")

        f6 = self.gov.row_disposition("PKT-PHB-013-018-races", "F6")
        self.assertEqual(f6["decision_id"], "DEC-2026-0009")
        self.assertEqual(f6["fields"]["target_id"], "rule_detection")
        self.assertEqual(f6["fields"]["page"], "")
        self.assertEqual(f6["fields"]["section"], "Dwarves")

    def test_architect_may_rule_polarity(self):
        """DEC-2026-0010 rules F33 polarity outright.

        Invariants 13-14 bar workers from authoring polarity; the Architect has
        authority to amend edge semantics, so a decision may set it.
        """
        f33 = self.gov.row_disposition("PKT-PHB-013-018-races", "F33")
        self.assertEqual(f33["decision_id"], "DEC-2026-0010")
        self.assertEqual(f33["fields"]["edge_type"], "MODIFIES")
        self.assertEqual(f33["fields"]["polarity"], "neutral")
        self.assertEqual(f33["fields"]["polarity_basis"], "read")


class TestRoutingInTheCompiler(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = NodeRegistry.load(RULESET_ROOT / "registries" / "nodes.csv")
        cls.canonical = CanonicalEdges.load(RULESET_ROOT / "canonical" / "edges_master.csv")
        cls.gov = Governance.load(RULESET_ROOT)
        # Whichever DEC-2026-0003 proposal is still unregistered. Naming one
        # makes the test expire the moment that node is registered; once they
        # are all registered the helper supplies a stand-in so the routing rule
        # stays covered.
        cls.pending_node, cls.gov = _bootstrap.unregistered_returned_to_workflow(
            cls.gov, cls.registry
        )
        cls.compiler = Compiler(cls.registry, cls.canonical, None, cls.gov)

    ENVELOPE = {
        "schema_version": "1.0", "id": "GUR-PKT-PHB-900-901-fixture-r01",
        "status": "proposed", "ruleset_id": "adnd1e", "book_id": "phb",
        "source_id": "phb-legacy-unspecified", "packet_id": "PKT-PHB-900-901-fixture",
        "constitution_version": "1.3", "revision": 1, "page_start": 9, "page_end": 13,
    }
    EDGE = {
        "ref": "T1", "source_id": "abil_strength", "source_label": "Strength",
        "edge_type": "GATES", "target_id": "class_fighter", "target_label": "Fighter",
        "aspect": "class eligibility", "condition": "", "book": "PHB", "page": 9,
        "section": "STRENGTH TABLE I", "evidence": "explicit_rule", "pass": "page-sweep",
        "status": "core", "general_rule_id": "", "supersession_basis": "", "review_flag": "",
    }

    def compile_gur(self, **overrides):
        document = {**self.ENVELOPE, **overrides}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gur.yaml"
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            return self.compiler.compile(path)

    def rules(self, result):
        return {f.rule for f in result.findings}

    def test_clean_proposal_is_reviewer_approvable_not_escalated(self):
        result = self.compile_gur(
            candidate_nodes=[{"proposed_id": self.pending_node,
                              "proposed_label": "Fixture Ordinary Proposal",
                              "edges_depending_on_it": ["T1"]}],
            candidate_edges=[dict(self.EDGE, target_id=self.pending_node,
                                  target_label="Fixture Ordinary Proposal")],
        )
        addition = result.node_additions[0]
        self.assertFalse(addition["architect_required"])
        self.assertEqual(addition["disposition"], "reviewer_may_approve")
        self.assertEqual(result.escalations, [], "DEC-2026-0003: not an Architect matter")
        self.assertIn("node_addition_normal_workflow", self.rules(result))

    def test_dependent_edge_is_informational_not_an_error(self):
        # An unregistered proposal, derived rather than named: `rule_dual_class`
        # was hardcoded here until the Integrator registered it, at which point
        # the row stopped being pending and the test failed on corpus growth
        # rather than on a defect.
        result = self.compile_gur(
            candidate_nodes=[{"proposed_id": self.pending_node,
                              "proposed_label": "Fixture Pending Proposal"}],
            candidate_edges=[dict(self.EDGE, target_id=self.pending_node,
                                  target_label="Fixture Pending Proposal")],
        )
        pending = [f for f in result.findings if f.rule == "endpoint_pending_registry_addition"]
        self.assertEqual([f.severity for f in pending], ["info"])
        self.assertEqual(result.errors, [])
        self.assertFalse(result.blocks_approval)
        self.assertEqual(result.status, "proposed")

    def test_pending_row_is_still_held_out_of_the_csv(self):
        result = self.compile_gur(
            candidate_nodes=[{"proposed_id": self.pending_node,
                              "proposed_label": "Fixture Pending Proposal"}],
            candidate_edges=[dict(self.EDGE, target_id=self.pending_node,
                                  target_label="Fixture Pending Proposal")],
        )
        self.assertEqual(len(result.pending_additions), 1)
        self.assertEqual(result.additions, [], "invariant 1 until the registry change applies")

    def test_rejected_identity_is_refused_with_its_replacement(self):
        """DEC-2026-0009 acceptance tests."""
        result = self.compile_gur(
            candidate_nodes=[{"proposed_id": "rule_racial_detection",
                              "proposed_label": "Racial Underground Detection"}],
            candidate_edges=[dict(self.EDGE, target_id="rule_racial_detection",
                                  target_label="Racial Underground Detection")],
        )
        # Not carried as a registry addition.
        self.assertEqual(result.node_additions, [])
        self.assertEqual(len(result.rejected_node_proposals), 1)
        rejected = result.rejected_node_proposals[0]
        self.assertEqual(rejected["replacement_id"], "rule_detection")
        self.assertEqual(rejected["rejected_by"], "DEC-2026-0009")
        # The dependent edge cannot enter the GUP.
        self.assertEqual(result.rows, [])
        self.assertIn("endpoint_uses_rejected_identity", self.rules(result))
        self.assertTrue(result.blocks_approval)

    def test_rejection_is_not_an_escalation(self):
        # The question is decided, so it must not be re-raised to the Architect.
        result = self.compile_gur(
            candidate_nodes=[{"proposed_id": "rule_racial_detection",
                              "proposed_label": "Racial Underground Detection"}]
        )
        self.assertEqual(result.escalations, [])

    def test_architect_ruled_polarity_is_carried_and_flagged(self):
        result = self.compile_gur(
            packet_id="PKT-PHB-013-018-races",
            page_start=13,
            page_end=18,
            candidate_edges=[dict(self.EDGE, ref="F33", source_id="race_subrace",
                                  source_label="Sub-Race", edge_type="GATES",
                                  target_id="race_infravision", target_label="Infravision",
                                  aspect="racial vision",
                                  condition="halfling blood determines range",
                                  page=17, section="Halflings")],
        )
        row = result.rows[0]
        self.assertEqual(row["edge_type"], "MODIFIES")
        self.assertEqual(row["polarity"], "neutral")
        self.assertEqual(row["polarity_basis"], "read")
        # F33's assertion has since been integrated, so the row now restates a
        # canonical one. That is a fact about the corpus, not about the ruling.
        # What this test guards is that an Architect-ruled polarity is carried
        # rather than refused as a worker authoring a build-owned field.
        self.assertEqual(
            [f.rule for f in result.errors if f.rule != "duplicate_assertion"], []
        )
        self.assertIn("architect_ruled_build_owned_field", self.rules(result))
        override = [o for o in result.architect_overrides if o["ref"] == "F33"][0]
        self.assertEqual(override["build_owned_fields_ruled"], ["polarity", "polarity_basis"])

    def test_replacement_identity_compiles_cleanly(self):
        result = self.compile_gur(
            candidate_edges=[dict(self.EDGE, ref="F6", source_id="race_dwarf",
                                  source_label="Dwarf", edge_type="GATES",
                                  target_id="rule_detection", target_label="Detection",
                                  aspect="underground detection", page="", section="Dwarves")]
        )
        self.assertEqual(len(result.rows), 1)
        self.assertEqual(result.rows[0]["target_id"], "rule_detection")
        self.assertEqual(result.errors, [])


    def test_unapproved_prefix_still_escalates(self):
        result = self.compile_gur(
            candidate_nodes=[{"proposed_id": "turn_something", "proposed_label": "Turn Something"}]
        )
        self.assertTrue(result.node_additions[0]["architect_required"])
        self.assertIn("node_prefix_unapproved", self.rules(result))

    def test_wpn_prefix_proposal_is_now_accepted(self):
        result = self.compile_gur(
            candidate_nodes=[{"proposed_id": "wpn_reach", "proposed_label": "Weapon Reach"}]
        )
        addition = result.node_additions[0]
        self.assertTrue(addition["prefix_approved"])
        self.assertFalse(addition["architect_required"])
        self.assertNotIn("node_prefix_unapproved", self.rules(result))


class TestMigrationValidation(TestRoutingInTheCompiler):
    """DEC-2026-0004: distinguish unchanged wpn_ nodes from the sixteen to migrate."""

    def test_edge_to_a_rejected_prefix_node_warns_with_its_target(self):
        result = self.compile_gur(
            candidate_edges=[dict(self.EDGE, edge_type="MODIFIES", target_id="str_bend_bars",
                                  target_label="Bend Bars/Lift Gates", aspect="chance",
                                  polarity="improves", polarity_basis="read")]
        )
        findings = [f for f in result.findings if f.rule == "endpoint_pending_migration"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "warning")
        self.assertIn("abil_strength_bend_bars", findings[0].detail)
        self.assertFalse(result.blocks_approval, "resolves today; a warning, not a blocker")

    def test_edge_to_a_wpn_node_does_not_warn(self):
        result = self.compile_gur(
            candidate_edges=[dict(self.EDGE, edge_type="MODIFIES", target_id="wpn_speed_factor",
                                  target_label="Weapon Speed Factor", aspect="initiative",
                                  polarity="improves", polarity_basis="read")]
        )
        self.assertNotIn("endpoint_pending_migration", self.rules(result))


class TestConstitutionVersionTolerance(TestRoutingInTheCompiler):
    def test_gur_authored_under_1_2_compiles_with_a_warning(self):
        result = self.compile_gur(constitution_version="1.2", candidate_edges=[dict(self.EDGE)])
        self.assertIn("constitution_version_older_than_compiler", self.rules(result))
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.rows), 1)

    def test_unknown_version_is_still_an_error(self):
        result = self.compile_gur(constitution_version="0.9")
        self.assertIn("constitution_version_mismatch", self.rules(result))
        self.assertTrue(result.blocks_approval)


if __name__ == "__main__":
    unittest.main()
