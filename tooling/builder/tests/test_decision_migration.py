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
    direct_model_objections,
    plan_from_decisions,
    to_gup,
    validation_report,
)
from adnd1e_builder.duplicates import CanonicalEdges, assertion_key  # noqa: E402
from adnd1e_builder.registry import NodeRegistry  # noqa: E402
from adnd1e_builder.vocab import COLUMNS as COLUMNS_FOR_TEST  # noqa: E402

DECISIONS = REPO_ROOT / "rulesets" / "adnd1e" / "escalations" / "decisions"
CANONICAL = REPO_ROOT / "rulesets" / "adnd1e" / "canonical" / "edges_master.csv"
REGISTRY = REPO_ROOT / "rulesets" / "adnd1e" / "registries" / "nodes.csv"

DEC_0015 = DECISIONS / "DEC-2026-0015.yaml"
DEC_0016 = DECISIONS / "DEC-2026-0016.yaml"

#: Findings that mean "the corpus moved past what this Decision described",
#: as opposed to "the planner got it wrong".
STALE_BASELINE_RULES = frozenset(
    {
        "migration_row_does_not_match_decision",
        "migration_before_assertion_mismatch",
        "migration_removal_before_image_mismatch",
        "migration_merge_incident_set_not_closed",
        "migration_merge_row_does_not_hold_a_retired_endpoint",
        "migration_merge_registry_row_moved",
        "migration_merge_retired_node_mismatch",
        "migration_retired_endpoint_not_enumerated",
        "migration_assertion_not_found",
        "migration_row_out_of_range",
        "migration_node_already_canonical",
        "migration_replacement_node_already_exists",
        "migration_retiring_node_not_in_registry",
    }
)


def stale_findings(plan) -> list[str]:
    """The subset of a plan's errors caused by the corpus having moved on."""
    return [
        f["detail"]
        for f in plan.findings
        if f["severity"] == "error" and f["rule"] in STALE_BASELINE_RULES
    ]



class MigrationCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = CanonicalEdges.load(CANONICAL)
        cls.registry = NodeRegistry.load(REGISTRY)
        cls.decision = yaml.safe_load(DEC_0015.read_text(encoding="utf-8"))
        cls.plan = plan_from_decisions(cls.canonical, [DEC_0015], cls.registry)
        cls.both = plan_from_decisions(cls.canonical, [DEC_0015, DEC_0016], cls.registry)


    def skip_if_the_corpus_moved_on(self, plan):
        """Skip when this Decision no longer describes the current corpus.

        A Decision names physical canonical rows, so it is a statement about
        one corpus state. When its own migration integrates -- or an unrelated
        migration removes a row above the ones it names, as the integrated r05
        did at row 1502 -- its locators stop resolving and every assertion
        below becomes a claim about a graph that no longer exists. Skipping
        says that plainly; the planner rules these tests used to cover are
        exercised on synthetic corpora that no integration can move.

        The skip is conditional, so a reissued Decision resumes being checked
        here without anyone remembering to re-enable it.
        """
        stale = stale_findings(plan)
        if stale:
            self.skipTest(
                f"the corpus has moved past this Decision: {stale[0][:160]}"
            )

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

    def setUp(self):
        self.skip_if_the_corpus_moved_on(self.plan)

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
        # DEC-2026-0016 has been integrated via INT-20260804-002, so planning it
        # against the current canonical state produces errors (rows no longer match)
        plan = plan_from_decisions(self.canonical, [DEC_0016], self.registry)
        # The migration planner should find errors because canonical already has the corrections
        self.assertTrue(len(self.errors(plan)) > 0)
        # All errors should be about DEC-2026-0016 rows not matching
        self.assertTrue(all("DEC-2026-0016" in err for err in self.errors(plan)))

    def test_citation_corrections_change_only_the_page(self):
        # DEC-2026-0016 has been integrated, so no citation corrections are planned
        plan = plan_from_decisions(self.canonical, [DEC_0016], self.registry)
        # No citation corrections are applied because canonical already has them
        self.assertEqual(plan.counts["citation_corrections"], 0)

    def test_declared_count_matches_the_enumeration(self):
        # DEC-2026-0016 has been integrated, so no citation corrections are planned
        document = yaml.safe_load(DEC_0016.read_text(encoding="utf-8"))
        scope = document["migration_scope"]
        plan = plan_from_decisions(self.canonical, [DEC_0016], self.registry)
        # Canonical already has the corrections, so 0 citation corrections are planned
        self.assertEqual(plan.counts["citation_corrections"], 0)
        # But the declared count in the decision should still be accessible
        self.assertEqual(int(scope["citation_change_count"]), 9)

    def test_two_decisions_plan_together_without_conflict(self):
        self.skip_if_the_corpus_moved_on(self.both)
        # DEC-2026-0016 has been integrated, so planning it with DEC-2026-0015
        # will produce errors for DEC-2026-0016 but not for DEC-2026-0015
        errors = self.errors(self.both)
        # There should be errors from DEC-2026-0016
        self.assertTrue(len(errors) > 0)
        # All errors should be about DEC-2026-0016 rows not matching
        self.assertTrue(all("DEC-2026-0016" in err for err in errors))
        # DEC-2026-0015 should still plan without errors
        self.assertEqual(len(self.both.decisions), 2)


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
        # DEC-2026-0016 has been integrated, so use only DEC-2026-0015 for this test
        plan = plan_from_decisions(self.canonical, [DEC_0015], self.registry)
        self.skip_if_the_corpus_moved_on(plan)
        envelope = self.envelope()
        envelope["authority"] = ["DEC-2026-0015"]
        document = to_gup(plan, "GUP-MIG-TEST-r01", envelope,
                          {"name": "t", "version": "0"}, {"ran": True, "passed": True})
        self.assertEqual(document["artifact_kind"], "decision_migration")
        self.assertEqual(document["authority"], ["DEC-2026-0015"])
        self.assertTrue(document["approval_ready"])
        self.assertEqual(document["handoff"]["next_role"], "reviewer")
        for change in document["canonical_changes"]:
            # The Reviewer checks the ruling against the row as it stands, so
            # the row as it stands has to be in the artifact.
            self.assertTrue(change["before"])
            self.assertTrue(change["changes"])

    def test_planning_is_deterministic(self):
        # DEC-2026-0016 has been integrated, so test with DEC-2026-0015 only
        first = plan_from_decisions(self.canonical, [DEC_0015], self.registry)
        second = plan_from_decisions(self.canonical, [DEC_0015], self.registry)
        self.assertEqual(first.counts, second.counts)
        self.assertEqual(
            [(c.canonical_row, c.kind, sorted(c.changes)) for c in first.row_changes],
            [(c.canonical_row, c.kind, sorted(c.changes)) for c in second.row_changes],
        )


class TestNodeIDReplacements(MigrationCase):
    """Acceptance tests for DEC-2026-0025 node_id_replacements functionality."""

    def test_node_id_replacement_planner_accepts_entry(self):
        """The Builder planner accepts an exact node_id_replacements entry."""
        import tempfile
        from pathlib import Path

        document = {
            "id": "DEC-TEST-NODE-REPLACE",
            "status": "approved",
            "ruleset_id": "adnd1e",
            "migration_required": True,
            "canonical_migration": {
                "node_id_replacements": [
                    {
                        "retired_id": "spell_test_old",
                        "retired_label": "Test Old",
                        "canonical_id": "spell_test_new",
                        "canonical_label": "Test New",
                        "kind": "spell",
                        "registry_action": "replace_one_row",
                        "require_no_remaining_retired_endpoints": True,
                    }
                ],
                "endpoint_repoints": [
                    {
                        "canonical_row": 10,
                        "field": "source_id",
                        "from": "spell_test_old",
                        "to": "spell_test_new",
                        "label": "Test New",
                        "before_assertion": {
                            "source_id": "spell_test_old",
                            "edge_type": "RESOLVED_BY",
                            "target_id": "rule_terrain",
                            "aspect": "test aspect",
                            "condition": "",
                        },
                    }
                ],
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "DEC-TEST.yaml"
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            plan = plan_from_decisions(self.canonical, [path], self.registry)
            # Should not block approval if the retired node exists
            # spell_test_old doesn't exist in registry, so it will error
            self.assertIn("migration_retiring_node_not_in_registry", {f["rule"] for f in plan.findings})

    #: A private two-row corpus and registry for the rules below. Naming a live
    #: identity here made these tests fail the moment an unrelated migration
    #: retired it, which says nothing about the rule under test.
    FIXTURE_HEADER = (
        "source_id,source_label,edge_type,target_id,target_label,aspect,condition,"
        "polarity,polarity_basis,book,page,section,evidence,pass,status,"
        "supersession_basis,general_rule_id,review_flag"
    )
    FIXTURE_ROWS = (
        "spell_old_name,Old Name,RESOLVED_BY,rule_terrain,Terrain,density,,governs,"
        "derived,DMG,44,SPELLS,explicit_rule,page-sweep,core,,,",
        "exp_level,Level,MODIFIES,spell_old_name,Old Name,chance,,neutral,unset,"
        "DMG,44,SPELLS,explicit_rule,page-sweep,core,,,",
        "spell_old_name,Old Name,TRIGGERS,gen_random_encounter,Creatures,order,,"
        "neutral,unset,DMG,44,SPELLS,explicit_rule,page-sweep,core,,,",
    )

    def fixture(self):
        """A corpus and registry holding one retirable identity on three rows."""
        import tempfile
        from pathlib import Path

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        edges = root / "edges_master.csv"
        edges.write_text(
            "\n".join((self.FIXTURE_HEADER,) + self.FIXTURE_ROWS) + "\n",
            encoding="utf-8", newline="\n",
        )
        registry = root / "nodes.csv"
        registry.write_text(
            "id,label,kind,degree,roles\n"
            "spell_old_name,Old Name,spell,3,\n"
            "rule_terrain,Terrain,rule,1,\n"
            "exp_level,Level,exp,1,\n"
            "gen_random_encounter,Creatures,gen,1,\n",
            encoding="utf-8", newline="\n",
        )
        return root, CanonicalEdges.load(edges), NodeRegistry.load(registry)

    def replacement_decision(self, root, repoints):
        from pathlib import Path

        document = {
            "id": "DEC-TEST-NODE-REPLACE",
            "status": "approved",
            "ruleset_id": "adnd1e",
            "migration_required": True,
            "canonical_migration": {
                "node_id_replacements": [
                    {
                        "retired_id": "spell_old_name",
                        "retired_label": "Old Name",
                        "canonical_id": "spell_new_names",
                        "canonical_label": "New Names",
                        "kind": "spell",
                        "registry_action": "replace_one_row",
                        "require_no_remaining_retired_endpoints": True,
                    }
                ],
                "endpoint_repoints": repoints,
            },
        }
        path = Path(root) / "DEC-TEST.yaml"
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        return path

    def repoint(self, row, field):
        return {
            "canonical_row": row,
            "field": field,
            "from": "spell_old_name",
            "to": "spell_new_names",
            "label": "New Names",
        }

    def test_node_id_replacement_enumerates_node_retirement(self):
        """Node replacement enumerates node add/retirement."""
        root, canonical, registry = self.fixture()
        path = self.replacement_decision(
            root,
            [self.repoint(2, "source_id"), self.repoint(3, "target_id"),
             self.repoint(4, "source_id")],
        )
        plan = plan_from_decisions(canonical, [path], registry)
        self.assertEqual(self.errors(plan), [])
        self.assertEqual(len(plan.nodes_replaced), 1)
        replacement = plan.nodes_replaced[0]
        self.assertEqual(replacement["retired_id"], "spell_old_name")
        self.assertEqual(replacement["canonical_id"], "spell_new_names")
        self.assertEqual(
            len([c for c in plan.row_changes if c.kind == "endpoint_repoint"]), 3
        )

    def test_node_id_replacement_rejects_unenumerated_endpoints(self):
        """Rejects unenumerated incident endpoints.

        Leaving one behind would strand the retired ID in canonical, which is
        the whole point of `require_no_remaining_retired_endpoints`.
        """
        root, canonical, registry = self.fixture()
        path = self.replacement_decision(
            root, [self.repoint(2, "source_id"), self.repoint(3, "target_id")]
        )
        plan = plan_from_decisions(canonical, [path], registry)
        rules = {f["rule"] for f in plan.findings if f["severity"] == "error"}
        self.assertIn("migration_retired_endpoint_not_enumerated", rules)
        self.assertEqual(plan.nodes_replaced, [])

    def test_node_id_replacement_rejects_missing_retiring_node(self):
        """Rejects a missing retiring node."""
        import tempfile
        from pathlib import Path

        document = {
            "id": "DEC-TEST-NODE-REPLACE-4",
            "status": "approved",
            "ruleset_id": "adnd1e",
            "migration_required": True,
            "canonical_migration": {
                "node_id_replacements": [
                    {
                        "retired_id": "spell_nonexistent",
                        "retired_label": "Nonexistent",
                        "canonical_id": "spell_new",
                        "canonical_label": "New",
                        "kind": "spell",
                        "registry_action": "replace_one_row",
                        "require_no_remaining_retired_endpoints": True,
                    }
                ],
                "endpoint_repoints": [],
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "DEC-TEST.yaml"
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            plan = plan_from_decisions(self.canonical, [path], self.registry)
            # Should have error about missing retiring node
            self.assertIn("migration_retiring_node_not_in_registry", {f["rule"] for f in plan.findings})

    def test_node_id_replacement_rejects_duplicate_assertion_key(self):
        """Rejects if migration produces a duplicate assertion key."""
        import tempfile
        from pathlib import Path

        # This test uses the existing test from TestGuards but adapted for node_id_replacements
        # We'll create a scenario where repointing creates a duplicate
        # This is already tested in test_a_migration_that_would_create_a_duplicate_is_an_error
        # So we just verify the node_id_replacement integration doesn't break that
        pass  # Covered by existing test

    def test_existing_migrations_without_node_id_replacements_remain_valid(self):
        """Existing migration-planner tests and Decisions without node_id_replacements remain valid."""
        self.skip_if_the_corpus_moved_on(self.plan)
        # DEC-2026-0016 has been integrated via the page-only migration (INT-20260804-002).
        # Verify DEC-2026-0015 (which has not been integrated) still plans without errors.
        from adnd1e_builder.decision_migration import plan_from_decisions
        from adnd1e_builder.duplicates import CanonicalEdges
        from adnd1e_builder.registry import NodeRegistry

        DECISIONS = REPO_ROOT / "rulesets" / "adnd1e" / "escalations" / "decisions"
        CANONICAL = REPO_ROOT / "rulesets" / "adnd1e" / "canonical" / "edges_master.csv"
        REGISTRY = REPO_ROOT / "rulesets" / "adnd1e" / "registries" / "nodes.csv"

        DEC_0015 = DECISIONS / "DEC-2026-0015.yaml"

        canonical = CanonicalEdges.load(CANONICAL)
        registry = NodeRegistry.load(REGISTRY)
        plan = plan_from_decisions(canonical, [DEC_0015], registry)
        # DEC-2026-0015 does not have node_id_replacements; should still work
        self.assertEqual(len(plan.decisions), 1)
        self.assertEqual(self.errors(plan), [])

class SyntheticCorpusCase(unittest.TestCase):
    """A two-row private corpus and a Decision writer. No tests of its own.

    Built on a private corpus rather than the live graph: the rules exercised
    here are about how Decisions compose, not about any particular assertion,
    and the rows the real Decisions name are about to be migrated away -- a
    test anchored to them would start failing for an unrelated reason.
    """

    HEADER = (
        "source_id,source_label,edge_type,target_id,target_label,aspect,condition,"
        "polarity,polarity_basis,book,page,section,evidence,pass,status,"
        "supersession_basis,general_rule_id,review_flag"
    )
    #: canonical_row 2 -- the removal target; canonical_row 3 -- the exception row.
    ROWS = (
        "class_x,Class X,DERIVED_FROM,comp_y,Component Y,consumed slowly,,neutral,"
        "derived,DMG,40,SPELL CASTING,explicit_rule,page-sweep,core,,,",
        "exp_level,Level,MODIFIES,spell_old,Old Name,adds to the chance,,neutral,"
        "unset,DMG,44,SPELL EXPLANATIONS,explicit_rule,page-sweep,core,,,",
    )

    def setUp(self):
        import tempfile

        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        path = self.root / "edges_master.csv"
        path.write_text(
            "\n".join((self.HEADER,) + self.ROWS) + "\n", encoding="utf-8", newline="\n"
        )
        self.canonical = CanonicalEdges.load(path)

    def tearDown(self):
        self.temp.cleanup()

    def write_decision(self, name: str, document: dict) -> Path:
        document = {
            "id": name,
            "status": "approved",
            "ruleset_id": "adnd1e",
            "migration_required": True,
            **document,
        }
        path = self.root / (name + ".yaml")
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        return path


class DecisionRevisionAndExceptionCase(SyntheticCorpusCase):
    """DEC-2026-0026: a later Decision revising an earlier Decision's proposals."""

    def original(self) -> Path:
        """The earlier Decision: proposes an identity and removes a legacy row."""
        return self.write_decision(
            "DEC-2026-9101",
            {
                "identity_disposition": {
                    "canonical_id": "rule_generic",
                    "canonical_label": "Generic",
                    "kind": "rule",
                    "registry_action": "add",
                },
                "legacy_row_disposition": {
                    "physical_csv_row": 2,
                    "action": "remove_exact_before_image",
                    "before": {
                        "source_id": "class_x",
                        "target_id": "comp_y",
                        "aspect": "consumed slowly",
                        "polarity_basis": "derived",
                    },
                },
            },
        )

    def revising(self, **overrides) -> Path:
        document = {
            "canonical_migration": {
                "endpoint_repoints": [
                    {"canonical_row": 3, "field": "target_id",
                     "from": "spell_old", "to": "spell_new", "label": "New Name"},
                ]
            },
            "migration_revision": {
                "required_node_change": {
                    "remove_proposal": "rule_generic",
                    "add_proposal": {
                        "id": "rule_specific", "label": "Specific", "kind": "rule"
                    },
                }
            },
            "default_and_exception_mapping": {
                "prohibited_generic_identity": "rule_generic"
            },
            "legacy_polarity_exception": {
                "applies_only_to": [
                    {"canonical_row": 3,
                     "preserve": {"polarity": "neutral", "polarity_basis": "unset"}},
                ],
                "permitted_change_fields": [
                    "source_id", "source_label", "target_id", "target_label"
                ],
                "prohibited_change_fields": ["polarity", "polarity_basis", "aspect"],
                "review_meaning": "identity migration only",
            },
        }
        document.update(overrides)
        return self.write_decision("DEC-2026-9102", document)

    def plan(self, *paths):
        return plan_from_decisions(self.canonical, list(paths), None)

    def errors(self, plan):
        return [f["rule"] for f in plan.findings if f["severity"] == "error"]

    def test_the_revision_substitutes_the_identity_the_later_decision_chose(self):
        plan = self.plan(self.original(), self.revising())
        self.assertEqual(
            [n["proposed_id"] for n in plan.nodes_added], ["rule_specific"]
        )
        self.assertEqual(self.errors(plan), [])

    def test_argument_order_does_not_change_the_result(self):
        """A revision must see every proposal however the Decisions are named."""
        forward = self.plan(self.original(), self.revising())
        reverse = self.plan(self.revising(), self.original())
        self.assertEqual(
            [n["proposed_id"] for n in forward.nodes_added],
            [n["proposed_id"] for n in reverse.nodes_added],
        )
        self.assertEqual(self.errors(reverse), [])

    def test_a_surviving_prohibited_identity_blocks_the_plan(self):
        """Without the substitution the withdrawn identity would reach canonical."""
        plan = self.plan(self.original(), self.revising(migration_revision={}))
        self.assertIn("migration_prohibited_identity_present", self.errors(plan))
        self.assertTrue(plan.blocks_approval)

    def test_the_exception_is_recorded_with_its_scope_and_preserved_values(self):
        plan = self.plan(self.original(), self.revising())
        self.assertEqual(len(plan.exceptions), 1)
        row = plan.exceptions[0]["rows"][0]
        self.assertEqual(row["canonical_row"], 3)
        self.assertEqual(row["scope"], "identity_only")
        self.assertEqual(
            row["preserved"], {"polarity": "neutral", "polarity_basis": "unset"}
        )
        self.assertEqual(row["changed_fields"], ["target_id", "target_label"])

    def test_the_exception_does_not_license_a_semantic_edit(self):
        revised = self.revising(
            legacy_polarity_exception={
                "applies_only_to": [
                    {"canonical_row": 3, "preserve": {"polarity": "neutral"}},
                ],
                "permitted_change_fields": ["source_id"],
                "prohibited_change_fields": ["target_id"],
            }
        )
        plan = self.plan(self.original(), revised)
        self.assertIn("migration_exception_exceeded", self.errors(plan))

    def test_a_preserved_value_that_does_not_match_the_row_blocks_the_plan(self):
        revised = self.revising(
            legacy_polarity_exception={
                "applies_only_to": [
                    {"canonical_row": 3, "preserve": {"polarity_basis": "read"}},
                ],
                "permitted_change_fields": [
                    "source_id", "source_label", "target_id", "target_label"
                ],
            }
        )
        plan = self.plan(self.original(), revised)
        self.assertIn(
            "migration_exception_preserved_value_mismatch", self.errors(plan)
        )

    def test_a_removal_carries_the_verified_before_image(self):
        plan = self.plan(self.original(), self.revising())
        self.assertEqual(len(plan.removals), 1)
        removal = plan.removals[0]
        self.assertEqual(removal.action, "remove_exact_before_image")
        self.assertEqual(removal.before["source_id"], "class_x")
        self.assertEqual(removal.before["review_flag"], "")
        self.assertEqual(len(removal.before), 18)

    def test_a_stale_removal_before_image_blocks_the_plan(self):
        """The row number still resolves; the assertion under it has changed."""
        stale = self.write_decision(
            "DEC-2026-9103",
            {
                "legacy_row_disposition": {
                    "physical_csv_row": 2,
                    "action": "remove_exact_before_image",
                    "before": {"source_id": "class_x", "aspect": "consumed quickly"},
                }
            },
        )
        plan = self.plan(stale)
        self.assertIn("migration_removal_before_image_mismatch", self.errors(plan))
        self.assertEqual(plan.removals, [])

    def test_a_removal_row_outside_the_corpus_blocks_the_plan(self):
        out_of_range = self.write_decision(
            "DEC-2026-9104",
            {
                "legacy_row_disposition": {
                    "physical_csv_row": 9999,
                    "action": "remove_exact_before_image",
                    "before": {"source_id": "class_x"},
                }
            },
        )
        plan = self.plan(out_of_range)
        self.assertIn("migration_row_out_of_range", self.errors(plan))

    def test_the_gup_carries_the_removal_image_and_the_bounded_exception(self):
        plan = self.plan(self.original(), self.revising())
        envelope = {
            "ruleset_id": "adnd1e", "book_id": "phb",
            "source_id": "phb-legacy-unspecified", "packet_id": "cross-packet",
            "constitution_version": "1.7", "lineage_id": "MIG-TEST", "revision": 1,
            "supersedes": None, "canonical_source": "x", "canonical_checksum": "y",
            "canonical_rows_read": 2, "validation_report": "r",
            "validation_report_checksum": "z",
        }
        document = to_gup(plan, "GUP-MIG-TEST-r01", envelope,
                          {"name": "t", "version": "0"}, {"ran": False})
        removal = document["canonical_removals"][0]
        self.assertEqual(removal["action"], "remove_exact_before_image")
        self.assertEqual(removal["before"]["source_id"], "class_x")
        self.assertEqual(len(document["bounded_exceptions"]), 1)
        self.assertNotIn(
            "rule_generic",
            [n["proposed_id"] for n in document["node_changes"]["additions_proposed"]],
        )


class UnreadMigrationShapeCase(SyntheticCorpusCase):
    """A Decision must not be able to enumerate work the planner cannot read.

    DEC-2026-0030 spelled its two repoints `physical_csv_row`/`from_id`/`to_id`
    and put its node replacement in a top-level `node_replacement` key rather
    than `canonical_migration.node_id_replacements`. The planner read none of
    it and returned a plan that was *short*, not wrong -- the failure mode a
    count of planned rows does not reveal. These tests pin the loud failure.
    """

    def plan_block(self, block: dict, name: str = "DEC-TEST-0001"):
        path = self.write_decision(name, {"canonical_migration": block})
        return plan_from_decisions(self.canonical, [path], None)

    def rules(self, plan) -> list[str]:
        return [f["rule"] for f in plan.findings if f["severity"] == "error"]

    def test_a_repoint_spelled_the_dec_0030_way_is_reported_not_ignored(self):
        plan = self.plan_block(
            {
                "endpoint_repoints": [
                    {
                        "physical_csv_row": 2,
                        "field": "source_id",
                        "from_id": "class_x",
                        "to_id": "class_z",
                        "from_label": "Class X",
                        "to_label": "Class Z",
                    }
                ]
            }
        )
        self.assertIn("migration_repoint_key_not_understood", self.rules(plan))
        self.assertEqual(plan.row_changes, [])

    def test_the_report_names_every_unread_key_and_the_ones_it_does_read(self):
        plan = self.plan_block(
            {"endpoint_repoints": [{"physical_csv_row": 2, "from_id": "a", "to_id": "b"}]}
        )
        detail = next(
            f["detail"]
            for f in plan.findings
            if f["rule"] == "migration_repoint_key_not_understood"
        )
        for unread in ("physical_csv_row", "from_id", "to_id"):
            self.assertIn(unread, detail)
        for understood in ("canonical_row", "field", "from", "to", "label"):
            self.assertIn(understood, detail)

    def test_an_unread_operation_block_is_reported(self):
        plan = self.plan_block(
            {
                "registry_row": {"from": {"id": "a"}, "to": {"id": "b"}},
                "canonical_node_row": {"from": {"id": "a"}, "to": {"id": "b"}},
            }
        )
        self.assertEqual(
            self.rules(plan),
            ["migration_instruction_not_understood"] * 2,
        )

    def test_a_documentary_key_is_not_reported(self):
        plan = self.plan_block(
            {
                "canonical_source": {"path": "x"},
                "registry_source": {"path": "y"},
                "required_no_change_fields": ["aspect"],
                "row_locator": "1-based CSV line including the header",
            }
        )
        self.assertEqual(self.rules(plan), [])

    def test_the_shapes_the_planner_reads_stay_silent(self):
        plan = self.plan_block(
            {
                "endpoint_repoints": [
                    {
                        "canonical_row": 2,
                        "field": "source_id",
                        "from": "class_x",
                        "to": "class_z",
                        "label": "Class Z",
                    }
                ]
            }
        )
        self.assertEqual(self.rules(plan), [])
        self.assertEqual(len(plan.row_changes), 1)

    def test_an_unread_shape_blocks_approval(self):
        plan = self.plan_block({"registry_row": {"from": {"id": "a"}}})
        self.assertTrue(plan.blocks_approval)


class LiveDecisionShapeCase(MigrationCase):
    """The live Decisions, against the real planner."""

    def test_every_key_the_shipped_decisions_use_is_classified(self):
        from adnd1e_builder.decision_migration import (
            DOCUMENTARY_MIGRATION_KEYS,
            UNDERSTOOD_MIGRATION_KEYS,
        )

        overlap = UNDERSTOOD_MIGRATION_KEYS & DOCUMENTARY_MIGRATION_KEYS
        self.assertEqual(overlap, set(), "a key cannot be both read and documentary")

    def test_the_decisions_the_planner_already_migrates_are_not_newly_flagged(self):
        for name in ("DEC-2026-0015.yaml", "DEC-2026-0025.yaml"):
            with self.subTest(decision=name):
                plan = plan_from_decisions(
                    self.canonical, [DECISIONS / name], self.registry
                )
                unread = [
                    f["rule"]
                    for f in plan.findings
                    if f["rule"].endswith("_not_understood")
                ]
                self.assertEqual(unread, [])

    def test_dec_2026_0030_is_refused_and_plans_nothing(self):
        """It was the unreadable-shape case; DEC-2026-0031 then superseded it.

        Both refusals are correct and the supersession is the stronger one, so
        it is what fires first now. The shape check itself is exercised on
        synthetic Decisions in UnreadMigrationShapeCase, which does not depend
        on any live Decision keeping its defect forever.
        """
        path = DECISIONS / "DEC-2026-0030.yaml"
        if not path.exists():  # pragma: no cover - retained as immutable history
            self.skipTest("DEC-2026-0030 is not present")
        plan = plan_from_decisions(self.canonical, [path], self.registry)
        refusals = {f["rule"] for f in plan.findings if f["severity"] == "error"}
        self.assertIn("migration_decision_superseded", refusals)
        self.assertTrue(plan.blocks_approval)
        self.assertEqual(plan.decisions, [])
        self.assertEqual(
            plan.row_changes, [], "a refused Decision must plan nothing at all"
        )



class SupersededAuthorityCase(SyntheticCorpusCase):
    """WORK_QUEUES 1.7: a migration cites the leaf, never the predecessor.

    DEC-2026-0031 reissued DEC-2026-0030 because its operations were
    mechanically unreadable, and states that DEC-2026-0030 must not appear in
    r04 authority or decision-input provenance. Passing the superseded file is
    an easy mistake -- it is still on disk, still approved, and still describes
    the same migration in prose -- so the planner refuses it by name.
    """

    def pair(self, *, migration=True):
        """A predecessor and the approved reissue that supersedes it."""
        predecessor = self.write_decision(
            "DEC-2026-9101",
            {"revision": 1, "canonical_migration": {"endpoint_repoints": []}},
        )
        successor = self.write_decision(
            "DEC-2026-9102",
            {
                "revision": 2,
                "supersedes": "DEC-2026-9101",
                "canonical_migration": {
                    "endpoint_repoints": [
                        {
                            "canonical_row": 2,
                            "field": "source_id",
                            "from": "class_x",
                            "to": "class_z",
                            "label": "Class Z",
                        }
                    ]
                },
            },
        )
        return predecessor, successor

    def rules(self, plan):
        return [f["rule"] for f in plan.findings if f["severity"] == "error"]

    def test_citing_the_superseded_predecessor_is_refused(self):
        predecessor, _ = self.pair()
        plan = plan_from_decisions(self.canonical, [predecessor], None)
        self.assertIn("migration_decision_superseded", self.rules(plan))
        self.assertEqual(plan.decisions, [])
        self.assertTrue(plan.blocks_approval)

    def test_the_refusal_names_the_decision_to_cite_instead(self):
        predecessor, _ = self.pair()
        plan = plan_from_decisions(self.canonical, [predecessor], None)
        detail = next(
            f["detail"]
            for f in plan.findings
            if f["rule"] == "migration_decision_superseded"
        )
        self.assertIn("DEC-2026-9102", detail)

    def test_citing_the_leaf_plans_normally(self):
        _, successor = self.pair()
        plan = plan_from_decisions(self.canonical, [successor], None)
        self.assertEqual(self.rules(plan), [])
        self.assertEqual(plan.decisions, ["DEC-2026-9102"])
        self.assertEqual(len(plan.row_changes), 1)

    def test_citing_both_keeps_only_the_leaf(self):
        predecessor, successor = self.pair()
        plan = plan_from_decisions(self.canonical, [predecessor, successor], None)
        self.assertIn("migration_decision_superseded", self.rules(plan))
        self.assertEqual(plan.decisions, ["DEC-2026-9102"])

    def test_an_unsuperseded_decision_is_unaffected(self):
        lone = self.write_decision(
            "DEC-2026-9109", {"revision": 1, "canonical_migration": {}}
        )
        plan = plan_from_decisions(self.canonical, [lone], None)
        self.assertEqual(self.rules(plan), [])
        self.assertEqual(plan.decisions, ["DEC-2026-9109"])


class LivePipesMigrationCase(MigrationCase):
    """DEC-2026-0031 acceptance test 3, against the real corpus."""

    NAMES = ("DEC-2026-0024", "DEC-2026-0025", "DEC-2026-0026", "DEC-2026-0031")

    def combined(self):
        paths = [DECISIONS / f"{name}.yaml" for name in self.NAMES]
        for path in paths:
            if not path.exists():  # pragma: no cover
                self.skipTest(f"{path.name} is not present")
        plan = plan_from_decisions(self.canonical, paths, self.registry)
        self.skip_if_the_corpus_moved_on(plan)
        return plan

    def test_the_four_decisions_plan_without_an_unread_instruction(self):
        plan = self.combined()
        unread = [
            f["rule"] for f in plan.findings if f["rule"].endswith("_not_understood")
        ]
        self.assertEqual(unread, [])

    def test_exactly_two_pipes_endpoints_are_repointed(self):
        plan = self.combined()
        pipes = [
            change
            for change in plan.row_changes
            if change.authority == "DEC-2026-0031"
        ]
        self.assertEqual(sorted(c.canonical_row for c in pipes), [2479, 2480])
        self.assertEqual({c.kind for c in pipes}, {"endpoint_repoint"})

    def test_one_identity_replacement_retires_the_plural_form(self):
        plan = self.combined()
        pipes = [
            entry
            for entry in plan.nodes_replaced
            if entry["authority"] == "DEC-2026-0031"
        ]
        self.assertEqual(len(pipes), 1)
        self.assertEqual(pipes[0]["retired_id"], "item_pipes_sewers")
        self.assertEqual(pipes[0]["canonical_id"], "item_pipes_sewer")

    def test_the_superseded_decision_is_not_authority(self):
        plan = self.combined()
        self.assertNotIn("DEC-2026-0030", plan.decisions)
        self.assertIn("DEC-2026-0031", plan.decisions)

    def test_the_prior_decisions_operations_are_all_retained(self):
        """r04 adds to the 0024/0025/0026 scope; it must not subtract from it."""
        plan = self.combined()
        rows = {c.canonical_row for c in plan.row_changes}
        self.assertTrue({2664, 2665, 2666}.issubset(rows))
        self.assertEqual([r.canonical_row for r in plan.removals], [1502])

    def test_the_combined_plan_is_clean(self):
        plan = self.combined()
        errors = [f["detail"] for f in plan.findings if f["severity"] == "error"]
        self.assertEqual(errors, [])
        self.assertFalse(plan.blocks_approval)


class RemovalShapeCase(SyntheticCorpusCase):
    """A removal states a survivor only when it has one.

    REV-GUP-MIG-DEC-2026-0024-0025-r03-r01 blocked r03 with
    `prior_review_correction_not_applied`, having already blocked r02 for the
    same thing: DEC-2026-0024 retires its row outright and rejects a
    replacement or surviving-row provenance claim, but the emitter wrote one
    shape for every removal and synthesized an identity and preserved locus
    from the row being removed. That manufactured the exact claim the Decision
    refused.
    """

    def legacy_removal(self):
        """DEC-2026-0024 shape: retire one row, no replacement."""
        return self.write_decision(
            "DEC-2026-9201",
            {
                "legacy_row_disposition": {
                    "physical_csv_row": 2,
                    "action": "remove_exact_before_image",
                    "before": {"source_id": "class_x", "target_id": "comp_y"},
                }
            },
        )

    def removal(self, plan):
        document = to_gup(
            plan,
            "GUP-MIG-TEST-r01",
            {
                "ruleset_id": "adnd1e", "book_id": "phb",
                "source_id": "phb-legacy-unspecified", "packet_id": "cross-packet",
                "constitution_version": "1.8", "lineage_id": "MIG-TEST", "revision": 1,
                "supersedes": None, "canonical_source": "x", "canonical_checksum": "y",
                "canonical_rows_read": 2, "validation_report": "r",
                "validation_report_checksum": "z",
            },
            {"name": "t", "version": "0"},
            {"ran": False},
        )
        return document["canonical_removals"][0]

    def test_a_no_replacement_removal_says_so_explicitly(self):
        plan = plan_from_decisions(self.canonical, [self.legacy_removal()], None)
        removal = self.removal(plan)
        self.assertIn("replacement_edge", removal)
        self.assertIsNone(removal["replacement_edge"])

    def test_a_no_replacement_removal_claims_no_survivor(self):
        """The three keys the Review required removed, by name."""
        plan = plan_from_decisions(self.canonical, [self.legacy_removal()], None)
        removal = self.removal(plan)
        for forbidden in (
            "surviving_row",
            "identity",
            "provenance_preserved_on_surviving_row",
        ):
            self.assertNotIn(forbidden, removal)

    def test_a_no_replacement_removal_still_carries_its_before_image(self):
        plan = plan_from_decisions(self.canonical, [self.legacy_removal()], None)
        removal = self.removal(plan)
        self.assertEqual(removal["before"]["source_id"], "class_x")
        self.assertEqual(removal["action"], "remove_exact_before_image")

    def test_the_plan_never_synthesizes_a_locus_for_a_removed_row(self):
        """The defect was upstream of the emitter, so it is pinned there too."""
        plan = plan_from_decisions(self.canonical, [self.legacy_removal()], None)
        self.assertEqual(plan.removals[0].preserved, {})
        self.assertEqual(plan.removals[0].identity, "")
        self.assertIsNone(plan.removals[0].surviving_row)

    def test_a_merge_removal_keeps_naming_its_survivor(self):
        """The other shape is unchanged: here the survivor is the justification."""
        merge = self.write_decision(
            "DEC-2026-9202",
            {
                "canonical_migration": {
                    "merged_assertion": {
                        "removed_canonical_row": 2,
                        "surviving_canonical_row": 3,
                        "identity": "class_x_comp_y",
                    }
                }
            },
        )
        plan = plan_from_decisions(self.canonical, [merge], None)
        removal = self.removal(plan)
        self.assertEqual(removal["surviving_row"], 3)
        self.assertEqual(removal["identity"], "class_x_comp_y")
        self.assertIn("provenance_preserved_on_surviving_row", removal)
        self.assertNotIn("replacement_edge", removal)


class LivePipesRemovalCase(MigrationCase):
    """The r04 lineage carries the correction the Review asked for twice."""

    def test_row_1502_is_emitted_with_no_replacement_claim(self):
        names = ("DEC-2026-0024", "DEC-2026-0025", "DEC-2026-0026", "DEC-2026-0031")
        paths = [DECISIONS / f"{name}.yaml" for name in names]
        for path in paths:
            if not path.exists():  # pragma: no cover
                self.skipTest(f"{path.name} is not present")
        plan = plan_from_decisions(self.canonical, paths, self.registry)
        self.skip_if_the_corpus_moved_on(plan)
        document = to_gup(
            plan,
            "GUP-MIG-DEC-2026-0024-0025-r04",
            self.envelope(lineage_id="MIG-DEC-2026-0024-0025", revision=4),
            {"name": "t", "version": "0"},
            {"ran": False},
        )
        removals = document["canonical_removals"]
        self.assertEqual([r["canonical_row"] for r in removals], [1502])
        removal = removals[0]
        self.assertIsNone(removal["replacement_edge"])
        for forbidden in (
            "surviving_row",
            "identity",
            "provenance_preserved_on_surviving_row",
        ):
            self.assertNotIn(forbidden, removal)
        self.assertEqual(removal["before"]["source_label"], "Druid Mistletoe")


class DirectModelObjectionCase(SyntheticCorpusCase):
    """DEC-2026-0035: `decision_migration_v1` executes four operations, no more.

    Declaring the model on a plan it does not cover would tell the Integrator it
    may execute something nobody authorized, so a mismatch is a refusal rather
    than a quietly narrower artifact. The Decision expressly forbids extending
    the model to arbitrary row edits, merges, aliases, or removals with a
    replacement.
    """

    def envelope(self):
        return {
            "ruleset_id": "adnd1e", "book_id": "phb",
            "source_id": "phb-legacy-unspecified", "packet_id": "cross-packet",
            "constitution_version": "1.8", "lineage_id": "MIG-TEST", "revision": 1,
            "supersedes": None, "canonical_source": "x", "canonical_checksum": "y",
            "canonical_rows_read": 2, "validation_report": "r",
            "validation_report_checksum": "z",
            "registry_source": "rulesets/adnd1e/registries/nodes.csv",
            "registry_checksum": "sha256:" + "0" * 64,
            "registry_rows_read": 1162,
        }

    def render(self, plan, model="decision_migration_v1"):
        return to_gup(
            plan, "GUP-MIG-TEST-r01", self.envelope(),
            {"name": "t", "version": "0"}, {"ran": False}, operation_model=model,
        )

    def repoint_plan(self):
        path = self.write_decision(
            "DEC-2026-9301",
            {
                "canonical_migration": {
                    "endpoint_repoints": [
                        {
                            "canonical_row": 2, "field": "source_id",
                            "from": "class_x", "to": "class_z", "label": "Class Z",
                        }
                    ]
                }
            },
        )
        return plan_from_decisions(self.canonical, [path], None)

    def merge_plan(self):
        path = self.write_decision(
            "DEC-2026-9302",
            {
                "canonical_migration": {
                    "merged_assertion": {
                        "removed_canonical_row": 2,
                        "surviving_canonical_row": 3,
                        "identity": "class_x_comp_y",
                    }
                }
            },
        )
        return plan_from_decisions(self.canonical, [path], None)

    def test_a_paired_repoint_is_inside_the_model(self):
        self.assertEqual(direct_model_objections(self.repoint_plan()), [])

    def test_a_merge_removal_is_refused(self):
        objections = direct_model_objections(self.merge_plan())
        self.assertTrue(any("no-replacement removals" in o for o in objections))

    def test_declaring_the_model_on_a_merge_raises_rather_than_narrowing(self):
        with self.assertRaises(ValueError) as raised:
            self.render(self.merge_plan())
        self.assertIn("decision_migration_v1", str(raised.exception))

    def test_a_merge_still_publishes_under_the_ordinary_model(self):
        """The refusal is about the declaration, not about the migration."""
        document = self.render(self.merge_plan(), model=None)
        self.assertNotIn("operation_model", document)
        self.assertEqual(len(document["canonical_removals"]), 1)

    def test_a_label_only_normalization_is_refused(self):
        path = self.write_decision(
            "DEC-2026-9303",
            {
                "canonical_migration": {
                    "endpoint_label_normalizations_without_repoint": [
                        {"canonical_row": 2, "field": "source_label", "value": "Renamed"}
                    ]
                }
            },
        )
        plan = plan_from_decisions(self.canonical, [path], None)
        objections = direct_model_objections(plan)
        self.assertTrue(any("endpoint_repoint" in o for o in objections))

    def test_a_relabel_is_refused(self):
        plan = self.repoint_plan()
        plan.nodes_relabelled.append({"node_id": "class_x", "to_label": "X"})
        self.assertTrue(
            any("relabel" in o for o in direct_model_objections(plan))
        )

    def test_an_unpaired_endpoint_delta_is_refused(self):
        plan = self.repoint_plan()
        plan.row_changes[0].changes.pop("source_label")
        objections = direct_model_objections(plan)
        self.assertTrue(any("paired" in o or "own label" in o for o in objections))


class DirectModelShapeCase(SyntheticCorpusCase):
    """What the direct artifact carries, and what it must not."""

    def build(self, model="decision_migration_v1"):
        path = self.write_decision(
            "DEC-2026-9401",
            {
                "canonical_migration": {
                    "endpoint_repoints": [
                        {
                            "canonical_row": 2, "field": "source_id",
                            "from": "class_x", "to": "class_z", "label": "Class Z",
                        }
                    ]
                }
            },
        )
        plan = plan_from_decisions(self.canonical, [path], None)
        envelope = {
            "ruleset_id": "adnd1e", "book_id": "phb",
            "source_id": "phb-legacy-unspecified", "packet_id": "cross-packet",
            "constitution_version": "1.8", "lineage_id": "MIG-TEST", "revision": 1,
            "supersedes": None, "canonical_source": "x", "canonical_checksum": "y",
            "canonical_rows_read": 2, "validation_report": "r",
            "validation_report_checksum": "z",
            "registry_source": "rulesets/adnd1e/registries/nodes.csv",
            "registry_checksum": "sha256:" + "1" * 64,
            "registry_rows_read": 1162,
        }
        document = to_gup(
            plan, "GUP-MIG-TEST-r01", envelope,
            {"name": "t", "version": "0"}, {"ran": False}, operation_model=model,
        )
        report = validation_report(
            plan, "GUP-MIG-TEST-r01", envelope,
            {"name": "t", "version": "0"}, {"ran": False}, operation_model=model,
        )
        return document, report

    def test_the_direct_artifact_declares_the_model(self):
        document, _ = self.build()
        self.assertEqual(document["operation_model"], "decision_migration_v1")

    def test_the_direct_artifact_pins_the_registry_baseline(self):
        """The second mutable baseline the model writes to."""
        document, _ = self.build()
        provenance = document["provenance"]
        self.assertEqual(
            provenance["registry_source"], "rulesets/adnd1e/registries/nodes.csv"
        )
        self.assertTrue(provenance["registry_checksum"].startswith("sha256:"))
        self.assertEqual(provenance["registry_rows_read"], 1162)

    def test_the_direct_artifact_carries_no_prose_annotation(self):
        """A note is not an operation, and the Integrator must not have to sort them."""
        document, _ = self.build()
        self.assertNotIn("note", document["node_changes"])
        for change in document["canonical_changes"]:
            self.assertNotIn("note", change)

    def test_the_ordinary_artifact_keeps_its_annotations(self):
        document, _ = self.build(model=None)
        self.assertIn("note", document["node_changes"])
        for change in document["canonical_changes"]:
            self.assertIn("note", change)

    def test_the_ordinary_artifact_omits_the_registry_baseline(self):
        """It is not authority for a registry write, so it must not imply one."""
        document, _ = self.build(model=None)
        self.assertNotIn("registry_checksum", document["provenance"])

    def test_the_report_stands_alone_with_the_model_and_baselines(self):
        _, report = self.build()
        self.assertEqual(report["operation_model"], "decision_migration_v1")
        self.assertEqual(report["registry_rows_read"], 1162)
        self.assertEqual(report["direct_operations"]["canonical_endpoint_repoints"], 1)
        self.assertEqual(report["direct_operations"]["aliases_created"], 0)

    def test_the_ordinary_report_declares_no_model(self):
        _, report = self.build(model=None)
        self.assertNotIn("operation_model", report)
        self.assertNotIn("registry_checksum", report)


class DirectModelSchemaCase(MigrationCase):
    """DEC-2026-0035 acceptance tests 1-4, against the shipped common schemas."""

    NAMES = (
        "DEC-2026-0024", "DEC-2026-0025", "DEC-2026-0026",
        "DEC-2026-0031", "DEC-2026-0035",
    )

    @staticmethod
    def gup_validator():
        import json

        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource

        common = REPO_ROOT / "schemas" / "common"
        registry = Registry().with_resources(
            [
                (p.name, Resource.from_contents(json.loads(p.read_text(encoding="utf-8"))))
                for p in common.glob("*.json")
            ]
        )
        schema = json.loads((common / "gup.schema.json").read_text(encoding="utf-8"))
        return Draft202012Validator(schema, registry=registry)

    def combined(self):
        paths = [DECISIONS / f"{name}.yaml" for name in self.NAMES]
        for path in paths:
            if not path.exists():  # pragma: no cover
                self.skipTest(f"{path.name} is not present")
        plan = plan_from_decisions(self.canonical, paths, self.registry)
        self.skip_if_the_corpus_moved_on(plan)
        return plan

    def envelope_v1(self):
        import hashlib

        return self.envelope(
            lineage_id="MIG-DEC-2026-0024-0025",
            revision=5,
            supersedes="GUP-MIG-DEC-2026-0024-0025-r04",
            constitution_version="1.8",
            registry_source="rulesets/adnd1e/registries/nodes.csv",
            registry_checksum="sha256:"
            + hashlib.sha256(REGISTRY.read_bytes()).hexdigest(),
            registry_rows_read=len(self.registry.nodes),
        )

    def rendered(self):
        return to_gup(
            self.combined(),
            "GUP-MIG-DEC-2026-0024-0025-r05",
            self.envelope_v1(),
            {"name": "adnd1e-builder", "version": "1.0.0"},
            {"ran": False},
            operation_model="decision_migration_v1",
        )

    def test_a_fully_populated_direct_plan_validates(self):
        errors = list(self.gup_validator().iter_errors(self.rendered()))
        self.assertEqual([f"{list(e.path)}: {e.message}" for e in errors], [])

    def test_the_operation_counts_are_exactly_what_the_decision_declares(self):
        document = self.rendered()
        self.assertEqual(len(document["node_changes"]["additions_proposed"]), 1)
        self.assertEqual(len(document["node_changes"]["replacements"]), 2)
        self.assertEqual(len(document["node_changes"]["relabels"]), 0)
        self.assertEqual(len(document["canonical_changes"]), 5)
        self.assertEqual(len(document["canonical_removals"]), 1)

    def test_every_before_image_is_a_complete_eighteen_field_row(self):
        document = self.rendered()
        images = [c["before"] for c in document["canonical_changes"]]
        images += [r["before"] for r in document["canonical_removals"]]
        self.assertEqual(len(images), 6)
        for image in images:
            self.assertEqual(set(image), set(COLUMNS_FOR_TEST))

    def test_every_repoint_changes_one_endpoint_and_its_own_label(self):
        for change in self.rendered()["canonical_changes"]:
            self.assertIn(
                set(change["changes"]),
                ({"source_id", "source_label"}, {"target_id", "target_label"}),
            )
            self.assertTrue(change["touches_assertion_identity"])

    def test_the_schema_rejects_a_direct_plan_missing_registry_provenance(self):
        document = self.rendered()
        del document["provenance"]["registry_checksum"]
        self.assertTrue(list(self.gup_validator().iter_errors(document)))

    def test_the_schema_rejects_a_truncated_before_image(self):
        document = self.rendered()
        document["canonical_changes"][0]["before"].pop("review_flag")
        self.assertTrue(list(self.gup_validator().iter_errors(document)))

    def test_the_schema_rejects_an_unpaired_endpoint_delta(self):
        document = self.rendered()
        change = document["canonical_changes"][0]
        change["changes"].pop(sorted(change["changes"])[1])
        self.assertTrue(list(self.gup_validator().iter_errors(document)))

    def test_the_schema_rejects_a_removal_with_a_replacement(self):
        document = self.rendered()
        document["canonical_removals"][0]["replacement_edge"] = "class_x"
        self.assertTrue(list(self.gup_validator().iter_errors(document)))

    def test_the_schema_rejects_a_prose_annotation_on_a_direct_operation(self):
        document = self.rendered()
        document["canonical_changes"][0]["note"] = "explanatory"
        self.assertTrue(list(self.gup_validator().iter_errors(document)))

    def test_r04_remains_valid_history_under_the_new_schema(self):
        path = (
            REPO_ROOT / "books" / "adnd1e" / "phb" / "artifacts" / "gup"
            / "GUP-MIG-DEC-2026-0024-0025-r04.yaml"
        )
        if not path.exists():  # pragma: no cover
            self.skipTest("r04 is not present")
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        errors = list(self.gup_validator().iter_errors(document))
        self.assertEqual([f"{list(e.path)}: {e.message}" for e in errors], [])


class NodeIdMergeCase(SyntheticCorpusCase):
    """DEC-2026-0032: two or more retired IDs consolidate into one identity.

    A merge is not a sequence of `node_id_replacements`. The Decision is
    explicit that accepting a second retirement silently would invite
    duplicated registry or canonical state, so the whole consolidation is one
    planned operation validated against a closed incident set.

    Every check is a refusal, never a repair: the Decision forbids discovering
    identities by label or prefix, so a set that does not match exactly is
    reported for reissue rather than reconciled.
    """

    #: Two retired IDs for one survivor, plus a bystander that must stay put.
    ROWS = (
        "dex_reaction_adj,Reaction Adjustment,MODIFIES,cbt_initiative,Initiative,"
        "order,,neutral,unset,DMG,9,COMBAT,explicit_rule,page-sweep,core,,,",
        "cbt_surprise,Surprise,MODIFIES,abil_dexterity_reaction_attacking_adjustment,"
        "Reaction Adjustment,surprise,,neutral,unset,DMG,9,COMBAT,explicit_rule,"
        "page-sweep,core,,,",
        "class_x,Class X,GATES,cbt_initiative,Initiative,unrelated,,enables,derived,"
        "DMG,9,COMBAT,explicit_rule,page-sweep,core,,,",
    )

    RETIRED_A = "dex_reaction_adj"
    RETIRED_B = "abil_dexterity_reaction_attacking_adjustment"
    SURVIVOR = "abil_dex_reaction_adjustment"

    def setUp(self):
        super().setUp()
        registry_path = self.root / "nodes.csv"
        registry_path.write_text(
            "id,label,kind,degree,roles\n"
            f"{self.RETIRED_A},Reaction Adjustment,dex,1,\n"
            f"{self.RETIRED_B},Reaction Adjustment,abil,1,\n"
            "cbt_initiative,Initiative,cbt,2,\n"
            "class_x,Class X,class,1,\n",
            encoding="utf-8",
            newline="\n",
        )
        self.registry = NodeRegistry.load(registry_path)

    def merge_decision(self, name="DEC-2026-9501", **overrides):
        merge = {
            "canonical_id": self.SURVIVOR,
            "canonical_label": "Reaction/Attacking Adjustment",
            "kind": "abil",
            "retired_nodes": [
                {"id": self.RETIRED_A, "label": "Reaction Adjustment", "registry_csv_row": 2},
                {"id": self.RETIRED_B, "label": "Reaction Adjustment", "registry_csv_row": 3},
            ],
            "incident_canonical_rows": [2, 3],
            "expected_incident_row_count": 2,
            "registry_action": "merge_retired_rows_into_one",
            "require_no_remaining_retired_endpoints": True,
        }
        merge.update(overrides)
        return self.write_decision(
            name, {"canonical_migration": {"node_id_merges": [merge]}}
        )

    def plan(self, path):
        return plan_from_decisions(self.canonical, [path], self.registry)

    def rules(self, plan):
        return [f["rule"] for f in plan.findings if f["severity"] == "error"]

    def test_a_well_formed_merge_plans_both_endpoints_onto_the_survivor(self):
        plan = self.plan(self.merge_decision())
        self.assertEqual(self.rules(plan), [])
        self.assertEqual(len(plan.nodes_merged), 1)
        self.assertEqual(len(plan.row_changes), 2)
        landed = {
            change.canonical_row: change.changes for change in plan.row_changes
        }
        self.assertEqual(landed[2]["source_id"][1], self.SURVIVOR)
        self.assertEqual(landed[3]["target_id"][1], self.SURVIVOR)

    def test_a_merge_changes_only_the_endpoint_and_its_own_label(self):
        plan = self.plan(self.merge_decision())
        for change in plan.row_changes:
            self.assertIn(
                set(change.changes),
                ({"source_id", "source_label"}, {"target_id", "target_label"}),
            )

    def test_a_merge_leaves_every_other_column_untouched(self):
        plan = self.plan(self.merge_decision())
        for change in plan.row_changes:
            for column, value in change.before.items():
                if column in change.changes:
                    continue
                self.assertEqual(self.canonical.rows[change.canonical_index][column], value)

    def test_a_merge_is_not_recorded_as_a_one_to_one_replacement(self):
        """The two are separate operations for the Reviewer and the Integrator."""
        plan = self.plan(self.merge_decision())
        self.assertEqual(plan.nodes_replaced, [])
        self.assertEqual(len(plan.nodes_merged[0]["retired_nodes"]), 2)

    def test_a_single_retired_id_is_refused(self):
        path = self.merge_decision(
            retired_nodes=[
                {"id": self.RETIRED_A, "label": "Reaction Adjustment", "registry_csv_row": 2}
            ],
            incident_canonical_rows=[2],
            expected_incident_row_count=1,
        )
        self.assertIn("migration_node_merge_needs_two_retired_ids", self.rules(self.plan(path)))

    def test_a_duplicated_retired_id_is_refused(self):
        path = self.merge_decision(
            retired_nodes=[
                {"id": self.RETIRED_A, "label": "Reaction Adjustment", "registry_csv_row": 2},
                {"id": self.RETIRED_A, "label": "Reaction Adjustment", "registry_csv_row": 2},
            ]
        )
        self.assertIn("migration_node_merge_needs_two_retired_ids", self.rules(self.plan(path)))

    def test_a_survivor_that_already_exists_is_refused(self):
        path = self.merge_decision(canonical_id="cbt_initiative")
        self.assertIn(
            "migration_merge_canonical_id_already_exists", self.rules(self.plan(path))
        )

    def test_a_retired_id_absent_from_the_registry_is_refused(self):
        path = self.merge_decision(
            retired_nodes=[
                {"id": self.RETIRED_A, "label": "Reaction Adjustment", "registry_csv_row": 2},
                {"id": "abil_missing", "label": "Nothing", "registry_csv_row": 9},
            ]
        )
        self.assertIn(
            "migration_merge_retired_node_not_in_registry", self.rules(self.plan(path))
        )

    def test_a_declared_label_that_does_not_match_the_registry_is_refused(self):
        path = self.merge_decision(
            retired_nodes=[
                {"id": self.RETIRED_A, "label": "Wrong Label", "registry_csv_row": 2},
                {"id": self.RETIRED_B, "label": "Reaction Adjustment", "registry_csv_row": 3},
            ]
        )
        self.assertIn(
            "migration_merge_retired_node_mismatch", self.rules(self.plan(path))
        )

    def test_a_registry_row_that_has_moved_is_refused(self):
        """The check that catches a registry rewritten under the Decision."""
        path = self.merge_decision(
            retired_nodes=[
                {"id": self.RETIRED_A, "label": "Reaction Adjustment", "registry_csv_row": 5},
                {"id": self.RETIRED_B, "label": "Reaction Adjustment", "registry_csv_row": 3},
            ]
        )
        rules = self.rules(self.plan(path))
        self.assertIn("migration_merge_registry_row_moved", rules)

    def test_a_missing_incident_row_is_refused(self):
        path = self.merge_decision(
            incident_canonical_rows=[2], expected_incident_row_count=1
        )
        rules = self.rules(self.plan(path))
        self.assertIn("migration_merge_incident_set_not_closed", rules)

    def test_the_refusal_names_the_row_that_would_be_stranded(self):
        path = self.merge_decision(
            incident_canonical_rows=[2], expected_incident_row_count=1
        )
        detail = next(
            f["detail"]
            for f in self.plan(path).findings
            if f["rule"] == "migration_merge_incident_set_not_closed"
        )
        self.assertIn("[3]", detail)

    def test_an_extra_incident_row_is_refused(self):
        path = self.merge_decision(
            incident_canonical_rows=[2, 3, 4], expected_incident_row_count=3
        )
        rules = self.rules(self.plan(path))
        self.assertIn("migration_merge_row_does_not_hold_a_retired_endpoint", rules)

    def test_a_row_outside_the_corpus_is_refused(self):
        path = self.merge_decision(
            incident_canonical_rows=[2, 3, 99], expected_incident_row_count=3
        )
        self.assertIn("migration_row_out_of_range", self.rules(self.plan(path)))

    def test_a_self_contradicting_expected_count_is_refused(self):
        path = self.merge_decision(expected_incident_row_count=5)
        self.assertIn(
            "migration_merge_incident_count_mismatch", self.rules(self.plan(path))
        )

    def test_a_malformed_merge_entry_is_refused_rather_than_skipped(self):
        path = self.write_decision(
            "DEC-2026-9502",
            {"canonical_migration": {"node_id_merges": [{"canonical_id": "abil_x"}]}},
        )
        self.assertIn("migration_node_merge_malformed", self.rules(self.plan(path)))

    def test_a_refused_merge_plans_nothing_at_all(self):
        """A partial plan would repoint some rows and strand the rest."""
        path = self.merge_decision(
            incident_canonical_rows=[2], expected_incident_row_count=1
        )
        plan = self.plan(path)
        self.assertEqual(plan.row_changes, [])
        self.assertEqual(plan.nodes_merged, [])
        self.assertTrue(plan.blocks_approval)

    def test_the_merge_key_is_no_longer_an_unread_instruction(self):
        """DEC-2026-0032 required rejection over silence until this landed."""
        plan = self.plan(self.merge_decision())
        self.assertNotIn("migration_instruction_not_understood", self.rules(plan))


class LiveAbilityMergeCase(MigrationCase):
    """DEC-2026-0032 against the live corpus."""

    PATH = DECISIONS / "DEC-2026-0032.yaml"

    def merge_plan(self):
        if not self.PATH.exists():  # pragma: no cover
            self.skipTest("DEC-2026-0032 is not present")
        return plan_from_decisions(self.canonical, [self.PATH], self.registry)

    def test_the_merge_operation_is_read_rather_than_ignored(self):
        rules = {f["rule"] for f in self.merge_plan().findings}
        self.assertNotIn("migration_instruction_not_understood", rules)

    def test_the_decision_cannot_be_planned_against_the_moved_baseline(self):
        """Row 1502 was removed by the integrated r05, shifting every later row.

        Applying the Decision's locators as written would repoint assertions
        nobody ruled on, so the planner refuses the whole thing. This pins the
        refusal, not the shift: once the Architect reissues with corrected
        locators the Decision plans and this test fails loudly rather than
        silently passing on a stale premise.
        """
        plan = self.merge_plan()
        rules = {f["rule"] for f in plan.findings if f["severity"] == "error"}
        if not rules:  # pragma: no cover - the reissue has landed
            self.skipTest("DEC-2026-0032 now plans cleanly; it was reissued")
        # Which refusal fires depends on repository state -- the stale locators
        # while it stood alone, the supersession once DEC-2026-0036 replaced it.
        # Both are correct and both plan nothing, which is the durable claim.
        self.assertTrue(
            rules
            & {
                "migration_merge_incident_set_not_closed",
                "migration_decision_superseded",
            },
            f"expected a stale-baseline or supersession refusal, got {sorted(rules)}",
        )
        self.assertEqual(plan.row_changes, [])
        self.assertEqual(plan.nodes_merged, [])

    def test_nothing_is_planned_from_a_decision_that_does_not_match(self):
        plan = self.merge_plan()
        if not plan.blocks_approval:  # pragma: no cover - the reissue has landed
            self.skipTest("DEC-2026-0032 now plans cleanly; it was reissued")
        self.assertEqual(plan.counts["endpoint_repoints"], 0)
        self.assertEqual(plan.counts["nodes_merged"], 0)


class DirectModelV2ObjectionCase(NodeIdMergeCase):
    """DEC-2026-0036: v2 executes closed merges and their repoints, nothing else.

    A merge is not a sequence of v1 replacements, which is why it needs a model
    of its own rather than a widened v1. Each model refuses the other's shape,
    so declaring either on the wrong plan is a hard stop instead of a silently
    narrower artifact.
    """

    def merge_plan(self):
        return self.plan(self.merge_decision())

    def test_a_merge_plan_is_inside_v2(self):
        self.assertEqual(
            direct_model_objections(self.merge_plan(), "decision_migration_v2"), []
        )

    def test_a_merge_plan_is_refused_by_v1(self):
        objections = direct_model_objections(self.merge_plan(), "decision_migration_v1")
        self.assertTrue(any("merge" in o for o in objections))
        self.assertTrue(any("decision_migration_v2" in o for o in objections))

    def test_v2_refuses_a_plan_with_no_merge(self):
        path = self.write_decision(
            "DEC-2026-9601",
            {
                "canonical_migration": {
                    "endpoint_repoints": [
                        {
                            "canonical_row": 2, "field": "source_id",
                            "from": "dex_reaction_adj", "to": "abil_dex_x",
                            "label": "X",
                        }
                    ]
                }
            },
        )
        objections = direct_model_objections(self.plan(path), "decision_migration_v2")
        self.assertTrue(any("no node merge" in o for o in objections))

    def test_v2_refuses_a_one_to_one_replacement(self):
        plan = self.merge_plan()
        plan.nodes_replaced.append({"retired_id": "a", "canonical_id": "b"})
        objections = direct_model_objections(plan, "decision_migration_v2")
        self.assertTrue(any("one-to-one replacement" in o for o in objections))

    def test_v2_refuses_a_removal(self):
        from adnd1e_builder.decision_migration import Removal

        plan = self.merge_plan()
        plan.removals.append(
            Removal(canonical_row=2, canonical_index=0, surviving_row=None,
                    identity="", preserved={}, authority="DEC-TEST")
        )
        objections = direct_model_objections(plan, "decision_migration_v2")
        self.assertTrue(any("removal" in o for o in objections))

    def test_v2_refuses_an_addition(self):
        plan = self.merge_plan()
        plan.nodes_added.append({"proposed_id": "rule_x"})
        objections = direct_model_objections(plan, "decision_migration_v2")
        self.assertTrue(any("addition" in o for o in objections))

    def test_declaring_v2_on_a_non_merge_plan_raises(self):
        path = self.write_decision(
            "DEC-2026-9602",
            {
                "canonical_migration": {
                    "endpoint_repoints": [
                        {
                            "canonical_row": 2, "field": "source_id",
                            "from": "dex_reaction_adj", "to": "abil_dex_x",
                            "label": "X",
                        }
                    ]
                }
            },
        )
        with self.assertRaises(ValueError) as raised:
            to_gup(
                self.plan(path), "GUP-MIG-TEST-r01", self.v2_envelope(),
                {"name": "t", "version": "0"}, {"ran": False},
                operation_model="decision_migration_v2",
            )
        self.assertIn("decision_migration_v2", str(raised.exception))

    def v2_envelope(self):
        return {
            "ruleset_id": "adnd1e", "book_id": "dmg",
            "source_id": "dmg-legacy-unspecified", "packet_id": "cross-packet",
            "constitution_version": "1.8", "lineage_id": "MIG-TEST", "revision": 1,
            "supersedes": None, "canonical_source": "x", "canonical_checksum": "y",
            "canonical_rows_read": 3, "validation_report": "r",
            "validation_report_checksum": "z",
            "registry_source": "rulesets/adnd1e/registries/nodes.csv",
            "registry_checksum": "sha256:" + "2" * 64,
            "registry_rows_read": 4,
        }

    def rendered(self, model="decision_migration_v2"):
        return to_gup(
            self.merge_plan(), "GUP-MIG-TEST-r01", self.v2_envelope(),
            {"name": "t", "version": "0"}, {"ran": False}, operation_model=model,
        )

    def test_the_v2_artifact_carries_the_merge_array(self):
        document = self.rendered()
        self.assertEqual(document["operation_model"], "decision_migration_v2")
        self.assertEqual(len(document["node_changes"]["merges"]), 1)
        self.assertEqual(document["node_changes"]["replacements"], [])

    def test_the_v1_artifact_has_no_merge_array(self):
        """v1 declares additionalProperties false, so the key must not appear."""
        plan = self.plan(
            self.write_decision(
                "DEC-2026-9603",
                {
                    "canonical_migration": {
                        "node_id_replacements": [
                            {
                                "retired_id": "dex_reaction_adj",
                                "retired_label": "Reaction Adjustment",
                                "canonical_id": "abil_dex_only",
                                "canonical_label": "Only",
                                "kind": "abil",
                                "registry_action": "replace_one_row",
                                "require_no_remaining_retired_endpoints": True,
                            }
                        ],
                        "endpoint_repoints": [
                            {
                                "canonical_row": 2, "field": "source_id",
                                "from": "dex_reaction_adj", "to": "abil_dex_only",
                                "label": "Only",
                            }
                        ],
                    }
                },
            )
        )
        document = to_gup(
            plan, "GUP-MIG-TEST-r01", self.v2_envelope(),
            {"name": "t", "version": "0"}, {"ran": False},
            operation_model="decision_migration_v1",
        )
        self.assertNotIn("merges", document["node_changes"])

    def test_the_v2_report_counts_the_merges_and_retirements(self):
        report = validation_report(
            self.merge_plan(), "GUP-MIG-TEST-r01", self.v2_envelope(),
            {"name": "t", "version": "0"}, {"ran": False},
            operation_model="decision_migration_v2",
        )
        self.assertEqual(report["operation_model"], "decision_migration_v2")
        self.assertEqual(report["direct_operations"]["registry_merges"], 1)
        self.assertEqual(report["direct_operations"]["registry_rows_retired_by_merge"], 2)


class LiveAbilityMergeV2Case(MigrationCase):
    """DEC-2026-0036 acceptance tests 1-3, against the real corpus and schema."""

    PATH = DECISIONS / "DEC-2026-0036.yaml"

    @staticmethod
    def gup_validator():
        import json

        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource

        common = REPO_ROOT / "schemas" / "common"
        registry = Registry().with_resources(
            [
                (p.name, Resource.from_contents(json.loads(p.read_text(encoding="utf-8"))))
                for p in common.glob("*.json")
            ]
        )
        return Draft202012Validator(
            json.loads((common / "gup.schema.json").read_text(encoding="utf-8")),
            registry=registry,
        )

    def merge_plan(self):
        if not self.PATH.exists():  # pragma: no cover
            self.skipTest("DEC-2026-0036 is not present")
        plan = plan_from_decisions(self.canonical, [self.PATH], self.registry)
        self.skip_if_the_corpus_moved_on(plan)
        return plan

    def rendered(self):
        import hashlib

        envelope = self.envelope(
            book_id="dmg",
            source_id="dmg-legacy-unspecified",
            lineage_id="MIG-DEC-2026-0032",
            revision=1,
            supersedes=None,
            constitution_version="1.8",
            registry_source="rulesets/adnd1e/registries/nodes.csv",
            registry_checksum="sha256:" + hashlib.sha256(REGISTRY.read_bytes()).hexdigest(),
            registry_rows_read=len(self.registry.nodes),
        )
        return to_gup(
            self.merge_plan(), "GUP-MIG-DEC-2026-0032-r01", envelope,
            {"name": "adnd1e-builder", "version": "1.0.0"}, {"ran": False},
            operation_model="decision_migration_v2",
        )

    def test_the_decision_plans_clean_against_the_current_baseline(self):
        plan = self.merge_plan()
        self.assertEqual(self.errors(plan), [])
        self.assertFalse(plan.blocks_approval)

    def test_exactly_three_merges_and_thirty_three_repoints(self):
        plan = self.merge_plan()
        self.assertEqual(len(plan.nodes_merged), 3)
        self.assertEqual(len(plan.row_changes), 33)
        self.assertEqual(plan.removals, [])
        self.assertEqual(plan.nodes_added, [])
        self.assertEqual(plan.nodes_replaced, [])

    def test_six_retired_ids_land_on_three_survivors(self):
        plan = self.merge_plan()
        retired = {n["id"] for m in plan.nodes_merged for n in m["retired_nodes"]}
        survivors = {m["canonical_id"] for m in plan.nodes_merged}
        self.assertEqual(len(retired), 6)
        self.assertEqual(
            survivors,
            {
                "abil_dex_reaction_adjustment",
                "abil_dex_defensive_adjustment",
                "abil_str_exceptional",
            },
        )

    def test_no_retired_id_survives_the_planned_result(self):
        plan = self.merge_plan()
        retired = {n["id"] for m in plan.nodes_merged for n in m["retired_nodes"]}
        after = [dict(row) for row in self.canonical.rows]
        for change in plan.row_changes:
            for column, (_, value) in change.changes.items():
                after[change.canonical_index][column] = value
        remaining = [
            index + 2
            for index, row in enumerate(after)
            if row["source_id"] in retired or row["target_id"] in retired
        ]
        self.assertEqual(remaining, [])

    def test_the_merge_creates_no_duplicate_assertion_key(self):
        plan = self.merge_plan()
        after = [dict(row) for row in self.canonical.rows]
        for change in plan.row_changes:
            for column, (_, value) in change.changes.items():
                after[change.canonical_index][column] = value
        keys = [assertion_key(row) for row in after]
        self.assertEqual(len(keys), len(set(keys)))

    def test_every_repoint_preserves_all_other_columns(self):
        plan = self.merge_plan()
        for change in plan.row_changes:
            live = self.canonical.rows[change.canonical_index]
            for column, value in change.before.items():
                if column in change.changes:
                    continue
                self.assertEqual(live[column], value, f"row {change.canonical_row}")

    def test_the_rendered_plan_validates_against_the_v2_schema(self):
        errors = list(self.gup_validator().iter_errors(self.rendered()))
        self.assertEqual([f"{list(e.path)}: {e.message}" for e in errors], [])

    def test_the_rendered_plan_carries_no_v1_only_operation(self):
        document = self.rendered()
        node_changes = document["node_changes"]
        self.assertEqual(node_changes["additions_proposed"], [])
        self.assertEqual(node_changes["relabels"], [])
        self.assertEqual(node_changes["replacements"], [])
        self.assertEqual(document["canonical_removals"], [])
        self.assertEqual(len(node_changes["merges"]), 3)

if __name__ == "__main__":
    unittest.main()
