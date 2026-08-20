"""Direction and type selection — constitution 1.4 section 4.2, DEC-2026-0011."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from test_decision_migration import applied_retirements  # noqa: E402

import _bootstrap
from _bootstrap import REPO_ROOT

from adnd1e_builder import direction
from adnd1e_builder.compiler import Compiler
from adnd1e_builder.duplicates import CanonicalEdges
from adnd1e_builder.governance import Governance
from adnd1e_builder.registry import NodeRegistry

RULESET_ROOT = REPO_ROOT / "rulesets" / "adnd1e"


class TestClassification(unittest.TestCase):
    def test_no_reversal_reports_nothing(self):
        self.assertIsNone(direction.classify({"edge_type": "GATES"}, []))

    def test_derived_from_against_operational_canonical_is_rejected(self):
        result = direction.classify(
            {"source_id": "a_x", "edge_type": "DERIVED_FROM", "target_id": "b_y"},
            [{"source_id": "b_y", "edge_type": "MODIFIES", "target_id": "a_x",
              "canonical_row": 42}],
        )
        self.assertEqual(result["rule"], direction.INVERSE_OF_OPERATIONAL)
        self.assertEqual(result["disposition"], "reject")
        # The disposition is decided, so dropping the row resolves it. A
        # rejection under an approved decision must not block the patch.
        self.assertEqual(result["severity"], "warning")

    def test_feeds_into_and_constrains_also_count_as_operational(self):
        for canonical_type in ("FEEDS_INTO", "CONSTRAINS"):
            with self.subTest(canonical_type=canonical_type):
                result = direction.classify(
                    {"source_id": "a_x", "edge_type": "DERIVED_FROM", "target_id": "b_y"},
                    [{"source_id": "b_y", "edge_type": canonical_type, "target_id": "a_x",
                      "canonical_row": 7}],
                )
                self.assertEqual(result["disposition"], "reject")

    def test_proposed_feeds_into_is_never_retyped_by_this_rule(self):
        """DEC-2026-0011 do_not: retype FEEDS_INTO rows under this decision."""
        result = direction.classify(
            {"source_id": "a_x", "edge_type": "FEEDS_INTO", "target_id": "b_y"},
            [{"source_id": "b_y", "edge_type": "GATES", "target_id": "a_x", "canonical_row": 9}],
        )
        self.assertEqual(result["disposition"], "carry_for_reviewer")
        self.assertEqual(result["severity"], "warning")

    def test_opposed_same_type_goes_to_the_reviewer(self):
        result = direction.classify(
            {"source_id": "race_x", "edge_type": "CONSTRAINS", "target_id": "abil_y"},
            [{"source_id": "abil_y", "edge_type": "CONSTRAINS", "target_id": "race_x",
              "canonical_row": 11}],
        )
        self.assertEqual(result["disposition"], "carry_for_reviewer")

    def test_gates_against_operational_is_not_auto_rejected(self):
        """Class B in the dedupe report: a minimum gating vs an adjustment."""
        result = direction.classify(
            {"source_id": "abil_strength", "edge_type": "GATES", "target_id": "race_halfling"},
            [{"source_id": "race_halfling", "edge_type": "MODIFIES",
              "target_id": "abil_strength", "canonical_row": 3}],
        )
        self.assertEqual(result["disposition"], "carry_for_reviewer")

    def test_derived_from_against_non_operational_canonical_is_not_rejected(self):
        result = direction.classify(
            {"source_id": "a_x", "edge_type": "DERIVED_FROM", "target_id": "b_y"},
            [{"source_id": "b_y", "edge_type": "GATES", "target_id": "a_x", "canonical_row": 5}],
        )
        self.assertEqual(result["disposition"], "carry_for_reviewer")


class TestInTheCompiler(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = Compiler(
            NodeRegistry.load(RULESET_ROOT / "registries" / "nodes.csv"),
            CanonicalEdges.load(RULESET_ROOT / "canonical" / "edges_master.csv"),
            None,
            Governance.load(RULESET_ROOT),
        )

    ENVELOPE = {
        "schema_version": "1.0", "id": "GUR-PKT-PHB-800-801-fixture-r01",
        "status": "proposed", "ruleset_id": "adnd1e", "book_id": "phb",
        "source_id": "phb-legacy-unspecified", "packet_id": "PKT-PHB-800-801-fixture",
        "constitution_version": "1.4", "revision": 1, "page_start": 8, "page_end": 13,
    }
    BASE = {
        "ref": "X1", "aspect": "known languages", "condition": "", "book": "PHB", "page": 8,
        "section": "CREATING THE PLAYER CHARACTER", "evidence": "explicit_rule",
        "pass": "page-sweep", "status": "core", "general_rule_id": "",
        "supersession_basis": "", "review_flag": "",
    }

    def compile_edges(self, edges):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gur.yaml"
            path.write_text(
                yaml.safe_dump({**self.ENVELOPE, "candidate_edges": edges}, sort_keys=False),
                encoding="utf-8",
            )
            return self.compiler.compile(path)

    def rules(self, result):
        return {f.rule for f in result.findings}

    def test_e1_is_dropped_not_retyped(self):
        """The real E1: rule_languages DERIVED_FROM race_any."""
        result = self.compile_edges([
            dict(self.BASE, ref="E1", source_id="rule_languages", source_label="Languages",
                 edge_type="DERIVED_FROM", target_id="race_any", target_label="Race")
        ])
        self.assertEqual(result.rows, [], "dropped as a restatement of the canonical row")
        self.assertIn(direction.INVERSE_OF_OPERATIONAL, self.rules(result))
        self.assertFalse(result.blocks_approval, "a ruled rejection is not an unresolved defect")
        rejected = [r for r in result.rejected_rows if r["ref"] == "E1"]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["authority"], "DEC-2026-0011")
        self.assertTrue(rejected[0]["canonical_rows"])
        # Not retyped: no MODIFIES row appears in its place.
        self.assertNotIn("MODIFIES", [r["edge_type"] for r in result.rows])

    def test_ratified_direction_compiles_cleanly(self):
        result = self.compile_edges([
            dict(self.BASE, ref="OK1", source_id="abil_dexterity", source_label="Dexterity",
                 edge_type="MODIFIES", target_id="dex_reaction_adj",
                 target_label="Dexterity Reaction Adjustment", aspect="tabulated adjustment",
                 page=11, section="DEXTERITY", polarity="improves", polarity_basis="read")
        ])
        self.assertNotIn(direction.INVERSE_OF_OPERATIONAL, self.rules(result))

    def test_opposed_direction_is_carried_with_a_warning(self):
        """E6-shaped: race CONSTRAINS ability vs canonical ability CONSTRAINS race."""
        result = self.compile_edges([
            dict(self.BASE, ref="E6", source_id="race_half_orc", source_label="Half-Orc",
                 edge_type="CONSTRAINS", target_id="abil_intelligence",
                 target_label="Intelligence", aspect="maximum score", page=13,
                 section="CHARACTER RACE TABLE III", polarity="worsens",
                 polarity_basis="read")
        ])
        self.assertEqual(len(result.rows), 1, "carried, not dropped")
        self.assertIn(direction.OPPOSED_DIRECTION, self.rules(result))
        self.assertEqual(
            [f.severity for f in result.findings if f.rule == direction.OPPOSED_DIRECTION],
            ["warning"],
        )

    def test_direction_findings_are_reported(self):
        result = self.compile_edges([
            dict(self.BASE, ref="E1", source_id="rule_languages", source_label="Languages",
                 edge_type="DERIVED_FROM", target_id="race_any", target_label="Race")
        ])
        self.assertEqual(len(result.direction_findings), 1)
        finding = result.direction_findings[0]
        self.assertEqual(finding["proposed"], "rule_languages DERIVED_FROM race_any")
        self.assertTrue(finding["canonical_counterparts"])


class TestAgainstTheRealGurs(unittest.TestCase):
    """DEC-2026-0011 acceptance: Builder deduplicates the eight direct cases.

    Two of the eight (B1, B10) were already normalized by the Analyst in
    money-equipment r04, so six remain in the latest revisions.

    These six must always be detected. The set is not asserted to be exhaustive:
    a reversal is a relationship between a proposed row and the canonical graph,
    so every integration can create new ones, and DEC-2026-0011 leaves those to
    the Reviewer case by case. Requiring equality would turn ordinary growth of
    the graph into a Builder test failure.
    """

    EXPECTED = {
        ("PKT-PHB-007-008-intro", "E1"),
        ("PKT-PHB-009-013-ability-scores", "G1"),
        ("PKT-PHB-009-013-ability-scores", "D1"),
        ("PKT-PHB-009-013-ability-scores", "D2"),
        ("PKT-PHB-009-013-ability-scores", "H1"),
        ("PKT-PHB-009-013-ability-scores", "H2"),
    }

    def test_class_a_cases_in_the_latest_revisions(self):
        canonical = CanonicalEdges.load(RULESET_ROOT / "canonical" / "edges_master.csv")
        gur_dir = REPO_ROOT / "books" / "adnd1e" / "phb" / "artifacts" / "gur"

        latest: dict[str, Path] = {}
        for path in sorted(gur_dir.glob("GUR-PKT-PHB-*.yaml")):
            packet = path.stem[4:].rsplit("-r", 1)[0]
            latest[packet] = path  # sorted order leaves the highest revision

        # A GUR is immutable, so an old one keeps naming the node IDs that were
        # current when the Analyst wrote it. DEC-2026-0038 merged six of those
        # into three survivors, which silently cost this test the two ability
        # cases D1 and D2: their reversed canonical counterparts still exist,
        # under the surviving IDs. Resolving each endpoint through the
        # retirements the Integrator actually recorded restores the comparison
        # without editing the GUR or weakening EXPECTED. An unretired ID maps to
        # itself, so this is a no-op until a merge lands.
        retirements = applied_retirements()

        def survivor(node_id):
            row = retirements.get(node_id)
            return row["replaced_by"] if row else node_id

        found = set()
        for packet, path in latest.items():
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            for edge in document.get("candidate_edges") or []:
                probe = {
                    "source_id": survivor(edge.get("source_id")),
                    "target_id": survivor(edge.get("target_id")),
                    "edge_type": edge.get("edge_type"),
                }
                verdict = direction.classify(probe, canonical.reversed_edges(probe))
                if verdict and verdict["disposition"] == "reject":
                    found.add((packet, edge["ref"]))

        missing = self.EXPECTED - found
        self.assertEqual(missing, set(), "a ratified DEC-2026-0011 case stopped being detected")

    def test_money_equipment_r04_already_uses_the_ratified_direction(self):
        path = (
            REPO_ROOT / "books" / "adnd1e" / "phb" / "artifacts" / "gur"
            / "GUR-PKT-PHB-035-038-money-equipment-r04.yaml"
        )
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        by_ref = {e["ref"]: e for e in document["candidate_edges"]}
        for ref in ("B1", "B10"):
            with self.subTest(ref=ref):
                self.assertEqual(by_ref[ref]["edge_type"], "MODIFIES")
                self.assertEqual(by_ref[ref]["source_id"], "sys_classes")


if __name__ == "__main__":
    unittest.main()
