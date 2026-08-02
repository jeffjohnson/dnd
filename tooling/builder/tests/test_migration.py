"""Canonical identity-merge migration — DEC-2026-0007."""

from __future__ import annotations

import unittest

import _bootstrap
from _bootstrap import REPO_ROOT

from adnd1e_builder.duplicates import CanonicalEdges
from adnd1e_builder.governance import Governance
from adnd1e_builder.migration import plan, to_gup
from adnd1e_builder.vocab import ASSERTION_KEY

RULESET_ROOT = REPO_ROOT / "rulesets" / "adnd1e"


class TestGovernanceLoad(unittest.TestCase):
    def test_identity_merges_are_loaded_from_the_decision(self):
        gov = Governance.load(RULESET_ROOT)
        merges = {m["retired_id"]: m["survivor_id"] for m in gov.identity_merges}
        self.assertEqual(
            merges,
            {
                "abil_cha_loyalty_base": "hench_loyalty",
                "hench_max_number": "abil_cha_max_henchmen",
            },
        )
        for merge in gov.identity_merges:
            self.assertEqual(merge["decision_id"], "DEC-2026-0007")


class TestPlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = CanonicalEdges.load(RULESET_ROOT / "canonical" / "edges_master.csv")
        cls.gov = Governance.load(RULESET_ROOT)
        cls.result = plan(cls.canonical, cls.gov.identity_merges)

    def test_two_rows_are_repointed(self):
        # DEC-2026-0007 migration_scope: retired_incident_rows_to_repoint: 2
        self.assertEqual(len(self.result.repoints), 2)

    def test_each_retired_id_has_one_incident_row(self):
        by_retired: dict[str, int] = {}
        for repoint in self.result.repoints:
            by_retired[repoint.retired_id] = by_retired.get(repoint.retired_id, 0) + 1
        self.assertEqual(
            by_retired, {"abil_cha_loyalty_base": 1, "hench_max_number": 1}
        )

    def test_repoints_move_to_the_ruled_survivor(self):
        mapping = {r.retired_id: r.survivor_id for r in self.result.repoints}
        self.assertEqual(mapping["abil_cha_loyalty_base"], "hench_loyalty")
        self.assertEqual(mapping["hench_max_number"], "abil_cha_max_henchmen")

    def test_no_repoint_changes_anything_but_the_endpoint(self):
        for repoint in self.result.repoints:
            before, after = dict(repoint.before), dict(repoint.after)
            self.assertEqual(before.pop(repoint.field_name) is not None, True)
            after.pop(repoint.field_name)
            before.pop(repoint.field_name, None)
            self.assertEqual(before, after, "aspect, condition and type must not move")

    def test_audit_uses_all_five_assertion_key_fields(self):
        document = to_gup(
            self.result, "GUP-MIG-TEST-r01",
            {
                "ruleset_id": "adnd1e", "book_id": "phb",
                "source_id": "phb-legacy-unspecified",
                "packet_id": "PKT-PHB-009-013-ability-scores",
                "constitution_version": "1.4",
                "canonical_source": "x", "canonical_rows_read": len(self.canonical.rows),
            },
            {"name": "t", "version": "0"}, {"ran": False},
        )
        self.assertEqual(document["assertion_key_audit"]["fields"], list(ASSERTION_KEY))

    def test_triple_collisions_are_not_collapsed(self):
        """DEC-2026-0007 prohibited_actions: do not collapse on the triple alone."""
        self.assertEqual(len(self.result.collisions), 2)
        self.assertEqual(len(self.result.exact_duplicates), 0)
        self.assertEqual(len(self.result.distinct_assertions), 2)
        for collision in self.result.distinct_assertions:
            self.assertEqual(collision.differing_fields, ["aspect"])

    def test_provenance_is_preserved_per_row(self):
        pages = {r.provenance["page"] for r in self.result.repoints}
        self.assertEqual(pages, {"13"})
        for repoint in self.result.repoints:
            self.assertTrue(repoint.provenance["section"])
            self.assertTrue(repoint.provenance["pass"])

    def test_the_two_citations_are_never_merged_into_one_field(self):
        """Do not place PHB p13 and p39 together in one page field."""
        for repoint in self.result.repoints:
            self.assertNotIn(",", repoint.provenance["page"])
            self.assertNotIn(";", repoint.provenance["page"])

    def test_survivor_self_loop_is_recorded_untouched(self):
        loops = [e for e in self.result.excluded if e["reason"] == "survivor_self_loop_untouched"]
        self.assertTrue(loops, "the hench_loyalty self-loop must be accounted for")
        for loop in loops:
            self.assertTrue(loop["verified_untouched"])

    def test_plan_is_approval_ready(self):
        self.assertFalse(self.result.blocks_approval)

    def test_plan_does_not_mutate_canonical(self):
        before = [dict(r) for r in self.canonical.rows]
        plan(self.canonical, self.gov.identity_merges)
        self.assertEqual([dict(r) for r in self.canonical.rows], before)

    def test_plan_is_deterministic(self):
        a = plan(self.canonical, self.gov.identity_merges)
        b = plan(self.canonical, self.gov.identity_merges)
        self.assertEqual(
            [(r.canonical_row, r.field_name, r.survivor_id) for r in a.repoints],
            [(r.canonical_row, r.field_name, r.survivor_id) for r in b.repoints],
        )
        self.assertEqual(
            [(c.repointed_row, c.other_row, c.grade) for c in a.collisions],
            [(c.repointed_row, c.other_row, c.grade) for c in b.collisions],
        )


class TestSyntheticExactDuplicate(unittest.TestCase):
    """A repoint that does create a true five-field duplicate must be reported."""

    def test_exact_duplicate_is_flagged_as_a_warning(self):
        import copy

        canonical = copy.deepcopy(
            CanonicalEdges.load(RULESET_ROOT / "canonical" / "edges_master.csv")
        )
        # Make row 685's aspect match the existing abil_charisma -> hench_loyalty
        # row so the repoint collides on all five fields.
        target = canonical.rows[685 - 2]
        self.assertEqual(target["target_id"], "abil_cha_loyalty_base")
        other = [r for r in canonical.rows
                 if r["source_id"] == "abil_charisma" and r["target_id"] == "hench_loyalty"
                 and r["edge_type"] == "MODIFIES"][0]
        target["aspect"], target["condition"] = other["aspect"], other["condition"]

        result = plan(canonical, [{
            "decision_id": "DEC-2026-0007", "label": "Loyalty Base",
            "survivor_id": "hench_loyalty", "retired_id": "abil_cha_loyalty_base",
        }])
        self.assertEqual(len(result.exact_duplicates), 1)
        self.assertIn(
            "merge_creates_exact_duplicate", {f["rule"] for f in result.findings}
        )
        # A duplicate is a Reviewer decision, not an automatic collapse.
        self.assertFalse(result.blocks_approval)


if __name__ == "__main__":
    unittest.main()
