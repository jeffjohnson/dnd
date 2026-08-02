"""Decision-driven canonical migration — DEC-2026-0015 and DEC-2026-0016.

The acceptance tests of those decisions are implemented here against the real
canonical corpus and registry, because a migration planned against a fixture
proves nothing about the graph it will be applied to.
"""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tooling" / "builder" / "src"))

from adnd1e_builder.decision_migration import (  # noqa: E402
    DecisionMigration,
    plan_from_decisions,
    to_gup,
    validation_report,
)
from adnd1e_builder.duplicates import CanonicalEdges, assertion_key  # noqa: E402
from adnd1e_builder.registry import NodeRegistry  # noqa: E402

DECISIONS = REPO_ROOT / "rulesets" / "adnd1e" / "escalations" / "decisions"
CANONICAL = REPO_ROOT / "rulesets" / "adnd1e" / "canonical" / "edges_master.csv"
REGISTRY = REPO_ROOT / "rulesets" / "adnd1e" / "registries" / "nodes.csv"

DEC_0015 = DECISIONS / "DEC-2026-0015.yaml"
DEC_0016 = DECISIONS / "DEC-2026-0016.yaml"


class MigrationCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = CanonicalEdges.load(CANONICAL)
        cls.registry = NodeRegistry.load(REGISTRY)
        cls.decision = yaml.safe_load(DEC_0015.read_text(encoding="utf-8"))
        cls.plan = plan_from_decisions(cls.canonical, [DEC_0015], cls.registry)
        cls.both = plan_from_decisions(cls.canonical, [DEC_0015, DEC_0016], cls.registry)

    def errors(self, plan: DecisionMigration) -> list[str]:
        return [f["detail"] for f in plan.findings if f["severity"] == "error"]

    def envelope(self, **overrides) -> dict:
        base = {
            "ruleset_id": "adnd1e",
            "book_id": "phb",
            "source_id": "phb-legacy-unspecified",
            "packet_id": "cross-packet",
            "constitution_version": "1.6",
            "lineage_id": "MIG-DEC-2026-0015-0016",
            "revision": 2,
            "supersedes": "GUP-MIG-DEC-2026-0015-0016-r01",
            "canonical_source": str(CANONICAL),
            "canonical_checksum": "sha256:" + hashlib.sha256(CANONICAL.read_bytes()).hexdigest(),
            "canonical_rows_read": len(self.canonical.rows),
            "validation_report": "build/reports/GUP-MIG-TEST-r02.validation.json",
            "validation_report_checksum": "sha256:" + "0" * 64,
        }
        base.update(overrides)
        return base


class TestDec0015AcceptanceTests(MigrationCase):
    """Straight from `DEC-2026-0015.acceptance_tests`."""

    def test_plan_is_clean(self):
        self.assertEqual(self.errors(self.plan), [])
        self.assertFalse(self.plan.blocks_approval)

    def test_seven_authorized_ids_are_unique_and_absent_before_the_migration(self):
        ids = [n["proposed_id"] for n in self.plan.nodes_added]
        self.assertEqual(len(ids), 7)
        self.assertEqual(len(set(ids)), 7)
        for node_id in ids:
            self.assertNotIn(node_id, self.registry, f"{node_id} already canonical")

    def test_nine_retained_ids_take_the_labels_the_decision_lists(self):
        listed = {
            node_id: d["canonical_label"]
            for node_id, d in self.decision["node_dispositions"].items()
            if isinstance(d, dict) and d.get("canonical_label")
        }
        planned = {n["node_id"]: n["to_label"] for n in self.plan.nodes_relabelled}
        self.assertEqual(len(planned), 9)
        for node_id, label in planned.items():
            self.assertEqual(label, listed[node_id])

    def test_spell_imprisonment_and_row_3027_are_untouched(self):
        self.assertNotIn(
            "spell_imprisonment", {n["node_id"] for n in self.plan.nodes_relabelled}
        )
        touched = {c.canonical_row for c in self.plan.row_changes}
        touched |= {r.canonical_row for r in self.plan.removals}
        self.assertNotIn(3027, touched)

    def test_exactly_sixteen_rows_are_repointed_as_the_decision_lists(self):
        listed = {
            int(e["canonical_row"])
            for e in self.decision["canonical_migration"]["endpoint_repoints"]
        }
        planned = {
            c.canonical_row for c in self.plan.row_changes if c.kind == "endpoint_repoint"
        }
        self.assertEqual(len(listed), 16)
        self.assertEqual(planned, listed)

    def test_exactly_ten_endpoints_receive_label_normalizations(self):
        listed = {
            int(e["canonical_row"])
            for e in self.decision["canonical_migration"][
                "endpoint_label_normalizations_without_repoint"
            ]
        }
        planned = {
            c.canonical_row
            for c in self.plan.row_changes
            if c.kind == "label_normalization"
        }
        self.assertEqual(len(listed), 10)
        self.assertEqual(planned, listed)

    def test_row_1765_is_removed_after_its_locus_is_preserved_on_2258(self):
        self.assertEqual(len(self.plan.removals), 1)
        removal = self.plan.removals[0]
        self.assertEqual(removal.canonical_row, 1765)
        self.assertEqual(removal.surviving_row, 2258)
        # The point of the merge is that the citation is not lost.
        self.assertEqual(removal.preserved["book"], "DMG")
        self.assertEqual(removal.preserved["page"], "67")

    def test_the_five_field_key_reports_no_duplicate_created_by_the_migration(self):
        created = [
            f for f in self.plan.findings
            if f["rule"] == "migration_creates_duplicate_assertion"
        ]
        self.assertEqual(created, [])

    def test_net_canonical_row_change_matches_the_decision(self):
        declared = self.decision["canonical_migration"]["counts"]["canonical_row_net_change"]
        self.assertEqual(self.plan.counts["canonical_row_net_change"], declared)

    def test_label_normalizations_never_touch_the_assertion_key(self):
        for change in self.plan.row_changes:
            if change.kind == "label_normalization":
                self.assertFalse(change.touches_identity, f"row {change.canonical_row}")

    def test_rows_3349_and_3350_stay_distinct_after_the_migration(self):
        # The decision reasons explicitly that these two survive as separate
        # assertions once 3350 is repointed. Prove it on the applied copy.
        after = [dict(r) for r in self.canonical.rows]
        for change in self.plan.row_changes:
            for field_name, (_, new_value) in change.changes.items():
                after[change.canonical_index][field_name] = new_value
        self.assertNotEqual(assertion_key(after[3347]), assertion_key(after[3348]))


class TestDec0016CitationCorrections(MigrationCase):
    def test_citation_rows_are_found_by_assertion_not_by_number(self):
        plan = plan_from_decisions(self.canonical, [DEC_0016], self.registry)
        self.assertEqual(self.errors(plan), [])
        self.assertTrue(plan.counts["citation_corrections"] > 0)

    def test_citation_corrections_change_only_the_page(self):
        plan = plan_from_decisions(self.canonical, [DEC_0016], self.registry)
        for change in plan.row_changes:
            if change.kind != "citation_correction":
                continue
            self.assertEqual(set(change.changes), {"page"})
            self.assertFalse(change.touches_identity)

    def test_declared_count_matches_the_enumeration(self):
        document = yaml.safe_load(DEC_0016.read_text(encoding="utf-8"))
        scope = document["migration_scope"]
        plan = plan_from_decisions(self.canonical, [DEC_0016], self.registry)
        self.assertEqual(
            plan.counts["citation_corrections"], int(scope["citation_change_count"])
        )

    def test_two_decisions_plan_together_without_conflict(self):
        self.assertEqual(self.errors(self.both), [])
        rows = [c.canonical_row for c in self.both.row_changes]
        self.assertEqual(len(rows), len(set(rows)), "a row is changed by two decisions")


class TestGuards(MigrationCase):
    """The checks that make the plan refuse rather than guess."""

    def _write(self, tmp: Path, document: dict) -> Path:
        path = tmp / "DEC-TEST.yaml"
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        return path

    def test_unapproved_decision_is_refused(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), {"id": "DEC-TEST", "status": "draft", "ruleset_id": "adnd1e",
                 "migration_required": True})
            plan = plan_from_decisions(self.canonical, [path], self.registry)
            self.assertIn("migration_decision_not_approved", {f["rule"] for f in plan.findings})
            self.assertEqual(plan.decisions, [])

    def test_row_that_no_longer_matches_the_decision_is_refused(self):
        import tempfile

        document = {
            "id": "DEC-TEST",
            "status": "approved",
            "ruleset_id": "adnd1e",
            "migration_required": True,
            "canonical_migration": {
                "endpoint_repoints": [
                    {"canonical_row": 2, "field": "source_id",
                     "from": "not_what_row_2_holds", "to": "rule_anything"}
                ]
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), document)
            plan = plan_from_decisions(self.canonical, [path], self.registry)
            self.assertIn(
                "migration_row_does_not_match_decision", {f["rule"] for f in plan.findings}
            )
            self.assertEqual(plan.row_changes, [])

    def test_out_of_range_row_is_refused(self):
        import tempfile

        document = {
            "id": "DEC-TEST",
            "status": "approved",
            "ruleset_id": "adnd1e",
            "migration_required": True,
            "canonical_migration": {
                "endpoint_repoints": [
                    {"canonical_row": 999999, "field": "source_id", "from": "a_b", "to": "c_d"}
                ]
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), document)
            plan = plan_from_decisions(self.canonical, [path], self.registry)
            self.assertIn("migration_row_out_of_range", {f["rule"] for f in plan.findings})

    def test_a_decision_that_contradicts_its_own_counts_is_refused(self):
        import tempfile

        document = {
            "id": "DEC-TEST",
            "status": "approved",
            "ruleset_id": "adnd1e",
            "migration_required": True,
            "canonical_migration": {
                "endpoint_repoints": [],
                "counts": {"canonical_rows_repointed": 4},
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), document)
            plan = plan_from_decisions(self.canonical, [path], self.registry)
            self.assertIn(
                "migration_declared_count_mismatch", {f["rule"] for f in plan.findings}
            )

    def test_a_migration_that_would_create_a_duplicate_is_an_error(self):
        import tempfile

        # Find two real rows that agree on edge_type, aspect and condition and
        # differ only in source_id. Repointing one onto the other then collapses
        # two distinct assertions into one, which is exactly the damage the
        # audit exists to catch.
        seen: dict[tuple, int] = {}
        pair = None
        for index, row in enumerate(self.canonical.rows):
            key = (row["edge_type"], row["target_id"], row["aspect"], row["condition"])
            if key in seen and self.canonical.rows[seen[key]]["source_id"] != row["source_id"]:
                pair = (seen[key], index)
                break
            seen.setdefault(key, index)
        self.assertIsNotNone(pair, "corpus has no pair to build this case from")
        survivor, victim = pair

        document = {
            "id": "DEC-TEST",
            "status": "approved",
            "ruleset_id": "adnd1e",
            "migration_required": True,
            "canonical_migration": {
                "endpoint_repoints": [
                    {
                        "canonical_row": victim + 2,
                        "field": "source_id",
                        "from": self.canonical.rows[victim]["source_id"],
                        "to": self.canonical.rows[survivor]["source_id"],
                    }
                ]
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), document)
            plan = plan_from_decisions(self.canonical, [path], self.registry)
            self.assertIn(
                "migration_creates_duplicate_assertion", {f["rule"] for f in plan.findings}
            )
            self.assertTrue(plan.blocks_approval)


class TestPlanningIsReadOnly(MigrationCase):
    """Planning must never be a write path to canonical or registry data."""

    def test_no_canonical_or_registry_file_is_changed_by_planning(self):
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (CANONICAL, REGISTRY)}
        plan = plan_from_decisions(self.canonical, [DEC_0015, DEC_0016], self.registry)
        to_gup(plan, "GUP-MIG-TEST-r02", self.envelope(),
               {"name": "t", "version": "0"}, {"ran": False})
        after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (CANONICAL, REGISTRY)}
        self.assertEqual(before, after)

    def test_the_in_memory_corpus_is_not_mutated_either(self):
        before = [dict(r) for r in self.canonical.rows]
        plan_from_decisions(self.canonical, [DEC_0015, DEC_0016], self.registry)
        self.assertEqual(self.canonical.rows, before)


class TestArtifactShape(MigrationCase):
    def test_gup_records_authority_and_carries_the_before_state(self):
        document = to_gup(self.both, "GUP-MIG-TEST-r02", self.envelope(),
                          {"name": "t", "version": "0"}, {"ran": True, "passed": True})
        self.assertEqual(document["artifact_kind"], "decision_migration")
        self.assertEqual(document["authority"], ["DEC-2026-0015", "DEC-2026-0016"])
        self.assertTrue(document["approval_ready"])
        self.assertEqual(document["handoff"]["next_role"], "reviewer")
        for change in document["canonical_changes"]:
            # The Reviewer checks the ruling against the row as it stands, so
            # the row as it stands has to be in the artifact.
            self.assertTrue(change["before"])
            self.assertTrue(change["changes"])

    def test_planning_is_deterministic(self):
        first = plan_from_decisions(self.canonical, [DEC_0015, DEC_0016], self.registry)
        second = plan_from_decisions(self.canonical, [DEC_0015, DEC_0016], self.registry)
        self.assertEqual(first.counts, second.counts)
        self.assertEqual(
            [(c.canonical_row, c.kind, sorted(c.changes)) for c in first.row_changes],
            [(c.canonical_row, c.kind, sorted(c.changes)) for c in second.row_changes],
        )


if __name__ == "__main__":
    unittest.main()
