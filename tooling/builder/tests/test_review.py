"""Reviewer revision requests as compiler input."""

from __future__ import annotations

import tempfile
import hashlib
import unittest
from pathlib import Path

import yaml

import _bootstrap
from _bootstrap import REPO_ROOT

from adnd1e_builder.compiler import Compiler
from adnd1e_builder.duplicates import CanonicalEdges
from adnd1e_builder.governance import Governance
from adnd1e_builder.registry import NodeRegistry
from adnd1e_builder.review import ReviewDirectives

REGISTRY_PATH = REPO_ROOT / "rulesets" / "adnd1e" / "registries" / "nodes.csv"
EDGES_PATH = REPO_ROOT / "rulesets" / "adnd1e" / "canonical" / "edges_master.csv"

ENVELOPE = {
    "schema_version": "1.0",
    "id": "GUR-PKT-PHB-777-778-fixture-r02",
    "status": "proposed",
    "ruleset_id": "adnd1e",
    "book_id": "phb",
    "source_id": "phb-legacy-unspecified",
    "packet_id": "PKT-PHB-777-778-fixture",
    "constitution_version": "1.2",
    "revision": 2,
    "page_start": 7,
    "page_end": 8,
}

# Deliberately not a direction conflict: `rule_languages DERIVED_FROM race_any`
# is the real E1 case that DEC-2026-0011 rejects, so it cannot serve as a
# neutral fixture for review-directive tests.
EDGE_A = {
    "ref": "A1", "source_id": "abil_strength", "source_label": "Strength",
    "edge_type": "GATES", "target_id": "class_fighter", "target_label": "Fighter",
    "aspect": "class eligibility", "condition": "", "book": "PHB", "page": 8,
    "section": "CREATING THE PLAYER CHARACTER", "evidence": "explicit_rule",
    "pass": "page-sweep", "status": "core", "general_rule_id": "",
    "supersession_basis": "", "review_flag": "",
}
EDGE_B = dict(EDGE_A, ref="B1", target_id="class_paladin", target_label="Paladin")

# The real E1 case: DEC-2026-0011 rejects this as the inverse of an existing
# canonical operational edge, so the compiler drops it without any Reviewer
# involvement.
# MODIFIES is one of the three types whose polarity section 6.1 leaves to a
# reading rather than deriving, so the GUR must carry it.
EDGE_AUTHORED = dict(
    EDGE_A, ref="M1", edge_type="MODIFIES", polarity="improves", polarity_basis="read",
)

EDGE_REJECTED_BY_BUILD = dict(
    EDGE_A, ref="R1", source_id="rule_languages", source_label="Languages",
    edge_type="DERIVED_FROM", target_id="race_any", target_label="Race",
    aspect="known languages",
)


class ReviewCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Governance is loaded from the repository, as in real use: several
        # Reviewer directives only mean anything against an Architect ruling,
        # and a default-empty Governance would make those tests vacuous.
        cls.compiler = Compiler(
            NodeRegistry.load(REGISTRY_PATH),
            CanonicalEdges.load(EDGES_PATH),
            None,
            Governance.load(REPO_ROOT / "rulesets" / "adnd1e"),
        )

    def run_with(self, edges, row_decisions, revision=3, input_gur=None):
        with tempfile.TemporaryDirectory() as tmp:
            gur = Path(tmp) / "gur.yaml"
            gur.write_text(
                yaml.safe_dump({**ENVELOPE, "candidate_edges": edges}, sort_keys=False),
                encoding="utf-8",
            )
            document = {
                "id": "REV-GUP-PKT-PHB-777-778-fixture-r02-r01",
                "packet_id": ENVELOPE["packet_id"],
                "reviewed_gup": "GUP-PKT-PHB-777-778-fixture-r02",
                "overall_disposition": "revision_required",
                "row_decisions": row_decisions,
            }
            if input_gur is not None:
                document["input_provenance"] = {"gur": {"id": input_gur}}
            review = Path(tmp) / "rev.yaml"
            review.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            directives = ReviewDirectives.load(review)
            return self.compiler.compile(gur, directives=directives, revision=revision)

    def run_with_chain(self, edges, documents, revision=3):
        """Compile against a chain of Reviews, oldest first.

        Chaining is where rulings get lost: each Review judges a patch built
        from the same GUR, so what an earlier Review corrected is already in the
        patch the later one approves, and a later approval must not compile the
        GUR without it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            gur = Path(tmp) / "gur.yaml"
            gur.write_text(
                yaml.safe_dump({**ENVELOPE, "candidate_edges": edges}, sort_keys=False),
                encoding="utf-8",
            )
            paths = []
            for position, document in enumerate(documents):
                path = Path(tmp) / f"rev{position}.yaml"
                path.write_text(
                    yaml.safe_dump(
                        {
                            "id": f"REV-GUP-PKT-PHB-777-778-fixture-r0{position + 2}-r01",
                            "packet_id": ENVELOPE["packet_id"],
                            "reviewed_gup": f"GUP-PKT-PHB-777-778-fixture-r0{position + 2}",
                            "overall_disposition": "revision_required",
                            **document,
                        },
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )
                paths.append(path)
            directives = ReviewDirectives.load_chain(paths)
            return self.compiler.compile(gur, directives=directives, revision=revision)

    def rules(self, result):
        return {f.rule for f in result.findings}


class TestRevisionNumbering(ReviewCase):
    def test_revision_advances_independently_of_the_gur(self):
        result = self.run_with([EDGE_A], [{"ref": "A1", "disposition": "approved"}], revision=3)
        self.assertEqual(result.gup_id, "GUP-PKT-PHB-777-778-fixture-r03")
        self.assertEqual(result.gur_id, "GUR-PKT-PHB-777-778-fixture-r02")

    def test_review_id_is_recorded_as_provenance(self):
        result = self.run_with([EDGE_A], [{"ref": "A1", "disposition": "approved"}])
        self.assertEqual(result.review_id, "REV-GUP-PKT-PHB-777-778-fixture-r02-r01")


class TestDispositions(ReviewCase):
    def test_approved_row_passes_through(self):
        result = self.run_with([EDGE_A], [{"ref": "A1", "disposition": "approved"}])
        self.assertEqual([r["ref"] for r in result.rows], ["A1"])
        self.assertEqual(result.rejected_rows, [])

    def test_rejected_row_is_omitted_and_recorded(self):
        result = self.run_with(
            [EDGE_A, EDGE_B],
            [
                {"ref": "A1", "disposition": "rejected", "rationale": "duplicate",
                 "integration_action": "omit_duplicate_or_unsupported_row",
                 "canonical_rows": [118, 935]},
                {"ref": "B1", "disposition": "approved"},
            ],
        )
        self.assertEqual([r["ref"] for r in result.rows], ["B1"])
        self.assertEqual(len(result.rejected_rows), 1)
        self.assertEqual(result.rejected_rows[0]["canonical_rows"], [118, 935])
        self.assertIn("reviewer_rejected_row", self.rules(result))

    def test_architect_escalation_holds_the_row(self):
        result = self.run_with(
            [EDGE_A], [{"ref": "A1", "disposition": "architect_escalation",
                        "rationale": "ontology unclear"}]
        )
        self.assertEqual(result.rows, [])
        self.assertTrue(result.blocks_approval)
        self.assertTrue(any(e["kind"] == "carried_from_review" for e in result.escalations))

    def test_undecided_row_is_an_error(self):
        result = self.run_with([EDGE_A, EDGE_B], [{"ref": "A1", "disposition": "approved"}])
        self.assertIn("review_row_undecided", self.rules(result))

    def test_undecided_row_the_build_rejects_itself_is_not_an_error(self):
        # A row this build drops never reached the Reviewer, so the absent
        # disposition is expected rather than an omission by the Reviewer.
        result = self.run_with(
            [EDGE_A, EDGE_REJECTED_BY_BUILD], [{"ref": "A1", "disposition": "approved"}]
        )
        self.assertEqual([r["ref"] for r in result.rows], ["A1"])
        self.assertNotIn("review_row_undecided", self.rules(result))
        self.assertIn("review_row_not_presented", self.rules(result))
        self.assertEqual(
            [f.severity for f in result.findings if f.rule == "review_row_not_presented"],
            ["info"],
        )

    def test_review_ref_absent_from_gur_is_an_error(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved"}, {"ref": "ZZ", "disposition": "approved"}],
        )
        self.assertIn("review_ref_not_in_gur", self.rules(result))

    def test_unknown_disposition_is_an_error(self):
        result = self.run_with([EDGE_A], [{"ref": "A1", "disposition": "looks_fine"}])
        self.assertIn("review_disposition_unknown", self.rules(result))


class TestDirectedCanonicalUpdates(ReviewCase):
    """`operation: canonical_update` is an instruction about the graph, not a
    field value. It must move the row out of additions."""

    # A real canonical assertion, so the diff is against actual data.
    CANONICAL_ROW = 118

    def canonical_at(self, row_number):
        return self.compiler.canonical.rows[row_number - 2]

    def test_a_directed_update_is_not_emitted_as_an_addition(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "integration_action": "apply_exact_corrections",
              "rationale": "already canonical",
              "exact_corrections": {"operation": "canonical_update",
                                    "canonical_row": self.CANONICAL_ROW}}],
        )
        self.assertEqual(result.additions, [])
        self.assertEqual(len(result.updates), 1)
        self.assertEqual(result.updates[0]["canonical_row"], self.CANONICAL_ROW)
        self.assertEqual(result.updates[0]["reason"], "canonical_update")
        self.assertIn("reviewer_directed_canonical_update", self.rules(result))

    def test_structural_keys_never_reach_the_edge(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "exact_corrections": {"operation": "canonical_update",
                                    "canonical_row": self.CANONICAL_ROW,
                                    "aspect": "fighter eligibility"}}],
        )
        row = result.rows[0]
        for key in ("operation", "canonical_row", "obsolete_conflicting_row"):
            self.assertNotIn(key, row)
        # The genuine field correction alongside them is still applied.
        self.assertEqual(row["aspect"], "fighter eligibility")

    def test_the_diff_is_taken_against_the_named_row(self):
        canonical = self.canonical_at(self.CANONICAL_ROW)
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "exact_corrections": {"operation": "canonical_update",
                                    "canonical_row": self.CANONICAL_ROW}}],
        )
        changes = result.updates[0]["changes"]
        for column, values in changes.items():
            self.assertEqual(values["canonical"], (canonical.get(column) or "").strip())

    def test_a_migration_records_the_obsolete_row(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "exact_corrections": {"operation": "canonical_migration",
                                    "canonical_row": self.CANONICAL_ROW,
                                    "obsolete_conflicting_row": 1915}}],
        )
        self.assertEqual(result.updates[0]["obsolete_conflicting_row"], 1915)
        self.assertEqual(result.updates[0]["reason"], "canonical_migration")

    def test_a_row_number_outside_the_graph_is_an_error(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "exact_corrections": {"operation": "canonical_update",
                                    "canonical_row": 999999}}],
        )
        self.assertIn("review_canonical_row_out_of_range", self.rules(result))
        self.assertTrue(result.blocks_approval)
        self.assertEqual(result.updates, [])

    def test_an_ordinary_correction_still_produces_an_addition(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "exact_corrections": {"aspect": "fighter eligibility"}}],
        )
        self.assertEqual([r["ref"] for r in result.additions], ["A1"])
        self.assertEqual(result.updates, [])


class TestReviewAnsweredByANewGur(ReviewCase):
    """A Review that returns a packet to the Analyst is answered by a new GUR.

    That replacement drops what the Review rejected and adds what it demanded,
    so the Review no longer covers the whole population being compiled. Neither
    difference is a defect.
    """

    EARLIER = "GUR-PKT-PHB-777-778-fixture-r01"
    SAME = ENVELOPE["id"]

    def test_a_row_added_since_the_review_is_carried_not_blocked(self):
        result = self.run_with(
            [EDGE_A, EDGE_B],
            [{"ref": "A1", "disposition": "approved"}],
            input_gur=self.EARLIER,
        )
        self.assertNotIn("review_row_undecided", self.rules(result))
        self.assertIn("review_row_new_since_review", self.rules(result))
        self.assertIn("review_answered_by_new_gur", self.rules(result))
        self.assertEqual([r["ref"] for r in result.rows], ["A1", "B1"])
        self.assertFalse(result.blocks_approval)

    def test_a_rejected_row_the_analyst_removed_is_not_an_error(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved"},
             {"ref": "B1", "disposition": "rejected", "rationale": "duplicate"}],
            input_gur=self.EARLIER,
        )
        self.assertNotIn("review_ref_not_in_gur", self.rules(result))
        self.assertIn("review_rejection_applied_at_source", self.rules(result))
        self.assertFalse(result.blocks_approval)

    def test_an_approved_row_the_analyst_dropped_is_still_an_error(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved"},
             {"ref": "B1", "disposition": "approved"}],
            input_gur=self.EARLIER,
        )
        self.assertIn("review_ref_not_in_gur", self.rules(result))

    def test_a_review_of_this_same_gur_is_still_read_strictly(self):
        result = self.run_with(
            [EDGE_A, EDGE_B],
            [{"ref": "A1", "disposition": "approved"}],
            input_gur=self.SAME,
        )
        self.assertIn("review_row_undecided", self.rules(result))
        self.assertNotIn("review_answered_by_new_gur", self.rules(result))

    def test_a_review_without_recorded_input_provenance_is_read_strictly(self):
        result = self.run_with([EDGE_A, EDGE_B], [{"ref": "A1", "disposition": "approved"}])
        self.assertIn("review_row_undecided", self.rules(result))


class TestCorrections(ReviewCase):
    def test_correction_is_applied_and_recorded(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "exact_corrections": {"aspect": "fighter eligibility"},
              "rationale": "narrower facet"}],
        )
        self.assertEqual(result.rows[0]["aspect"], "fighter eligibility")
        self.assertEqual(len(result.corrections_applied), 1)
        self.assertEqual(
            result.corrections_applied[0]["fields"]["aspect"],
            {"from": "class eligibility", "to": "fighter eligibility"},
        )

    def test_corrected_value_is_revalidated(self):
        """A Reviewer correction is not exempt from the grain rule."""
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "exact_corrections": {"aspect": "+3 to hit"}}],
        )
        self.assertIn("grain_numeric_bonus", self.rules(result))
        self.assertTrue(result.blocks_approval)

    def test_reviewer_may_not_correct_a_build_owned_field(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "exact_corrections": {"polarity": "improves"}}],
        )
        self.assertIn("reviewer_correction_on_build_owned_field", self.rules(result))
        # GATES is a deterministic type; the build value must survive.
        self.assertEqual(result.rows[0]["polarity"], "enables")
        self.assertEqual(result.rows[0]["polarity_basis"], "derived")

    def test_reviewer_may_correct_polarity_on_an_authored_type(self):
        """Section 6.1 leaves MODIFIES polarity to a reading, and readings are
        the Reviewer's to own."""
        result = self.run_with(
            [EDGE_AUTHORED],
            [{"ref": "M1", "disposition": "approved_with_revision",
              "exact_corrections": {"polarity": "worsens", "polarity_basis": "read"},
              "rationale": "the source reading is negative"}],
        )
        self.assertNotIn("reviewer_correction_on_build_owned_field", self.rules(result))
        self.assertEqual(result.rows[0]["polarity"], "worsens")
        self.assertEqual(result.rows[0]["polarity_basis"], "read")

    def test_edge_type_correction_decides_which_polarity_regime_applies(self):
        """Retyping to a derived type hands polarity back to the build."""
        result = self.run_with(
            [EDGE_AUTHORED],
            [{"ref": "M1", "disposition": "approved_with_revision",
              "exact_corrections": {"edge_type": "GATES", "polarity": "worsens"}}],
        )
        self.assertIn("reviewer_correction_on_build_owned_field", self.rules(result))
        self.assertEqual(result.rows[0]["polarity"], "enables")
        self.assertEqual(result.rows[0]["polarity_basis"], "derived")

    def test_corrected_polarity_on_an_authored_type_is_still_revalidated(self):
        result = self.run_with(
            [EDGE_AUTHORED],
            [{"ref": "M1", "disposition": "approved_with_revision",
              "exact_corrections": {"polarity": "improves", "polarity_basis": "heuristic"}}],
        )
        self.assertNotIn("reviewer_correction_on_build_owned_field", self.rules(result))
        self.assertTrue(result.blocks_approval)

    def test_multi_page_correction_is_rejected_and_escalated(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "exact_corrections": {"page": "7, 9, 15",
                                    "section": "THE GAME; STRENGTH TABLE I"}}],
        )
        self.assertIn("citation_multi_locus", self.rules(result))
        self.assertIn("page_outside_packet", self.rules(result))
        self.assertTrue(any(e["kind"] == "citation_cardinality" for e in result.escalations))
        self.assertTrue(result.blocks_approval)

    def test_single_page_correction_inside_the_packet_is_clean(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "exact_corrections": {"page": "7", "section": "THE GAME"}}],
        )
        self.assertNotIn("citation_multi_locus", self.rules(result))
        self.assertNotIn("page_outside_packet", self.rules(result))
        self.assertEqual(result.rows[0]["page"], "7")


class TestCanonicalPageShape(unittest.TestCase):
    def test_no_canonical_row_carries_a_multi_page_citation(self):
        """The precedent behind `citation_multi_locus`.

        If this ever fails, multi-locus citation has entered the corpus and the
        rule needs revisiting rather than the data.
        """
        import csv

        with EDGES_PATH.open(encoding="utf-8", newline="") as handle:
            pages = [row["page"] for row in csv.DictReader(handle)]
        self.assertTrue(all(p == "" or p.isdigit() for p in pages))


class TestBucketInstructions(ReviewCase):
    """A Review can rule on which bucket a row belongs in.

    The bucket is not a column, so this cannot be said as a field correction.
    Reading it as one is how the ruling gets lost -- the build writes a field
    literally named `edge_changes` onto the edge and reports success.
    """

    CANONICAL_ROW = 118

    def test_a_bucket_instruction_moves_a_row_from_additions_to_updates(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "rationale": "already canonical",
              "exact_corrections": {
                  "edge_changes.additions": {"remove_ref": "A1"},
                  "edge_changes.updates": {
                      "add": {"ref": "A1", "canonical_row": self.CANONICAL_ROW,
                              "reason": "canonical_update"}},
              }}],
        )
        self.assertEqual(result.additions, [])
        self.assertEqual(len(result.updates), 1)
        self.assertEqual(result.updates[0]["canonical_row"], self.CANONICAL_ROW)
        self.assertEqual([f.detail for f in result.errors], [])

    def test_a_retained_ref_in_updates_is_also_an_update(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "exact_corrections": {
                  "edge_changes.pending_additions": {"remove_ref": "A1"},
                  "edge_changes.updates": {"retain_ref": "A1",
                                           "canonical_row": self.CANONICAL_ROW},
              }}],
        )
        self.assertEqual(result.additions, [])
        self.assertEqual(result.updates[0]["canonical_row"], self.CANONICAL_ROW)

    def test_bucket_keys_never_reach_the_edge(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "exact_corrections": {
                  "edge_changes.updates": {"add": {"ref": "A1",
                                                   "canonical_row": self.CANONICAL_ROW}},
              }}],
        )
        for update in result.updates:
            self.assertNotIn("edge_changes", update.get("changes", {}))
            self.assertNotIn("edge_changes.updates", update.get("changes", {}))
        self.assertNotIn("reviewer_directive_not_understood", self.rules(result))

    def test_a_withheld_field_leaves_the_change_set_and_is_recorded(self):
        """A correction can be source-supported and still deferred.

        DEC-2026-0016 authorizes no page replacement on the Paladin rows until
        separate work resolves them, so the Reviewer keeps the semantic update
        and holds `page` back. Dropping it silently would leave the Integrator
        unable to tell a deferral from an oversight.
        """
        canonical = self.compiler.canonical.rows[self.CANONICAL_ROW - 2]
        edge = dict(EDGE_A, page=str(int(canonical["page"] or 0) + 1) if canonical["page"] else "9")
        result = self.run_with(
            [edge],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "rationale": "page deferred by decision",
              "exact_corrections": {
                  "edge_changes": {"updates": {
                      "ref": "A1", "canonical_row": self.CANONICAL_ROW,
                      "remove_change_fields": ["page"],
                      "set_differences_not_applied": {
                          "page": {"canonical": canonical["page"],
                                   "patch": edge["page"],
                                   "disposition": "deferred"}},
                  }},
              }}],
        )
        self.assertEqual(len(result.updates), 1)
        update = result.updates[0]
        self.assertNotIn("page", update["changes"])
        self.assertIn("page", update["differences_not_applied"])
        self.assertEqual(update["differences_not_applied"]["page"]["disposition"], "deferred")
        self.assertIn("reviewer_withheld_field_from_update", self.rules(result))


class TestUnknownDirectivesFail(ReviewCase):
    """A ruling the build cannot execute must never be absorbed as a field write."""

    def test_an_unrecognised_correction_key_is_an_error(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "exact_corrections": {"rearrange_the_graph": "somehow"}}],
        )
        self.assertIn("reviewer_directive_not_understood", self.rules(result))
        self.assertTrue(result.errors)

    def test_the_unknown_key_is_not_written_onto_the_edge(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "exact_corrections": {"rearrange_the_graph": "somehow"}}],
        )
        for row in result.rows:
            self.assertNotIn("rearrange_the_graph", row)

    def test_a_real_column_is_still_applied(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "exact_corrections": {"aspect": "fighter eligibility"}}],
        )
        self.assertNotIn("reviewer_directive_not_understood", self.rules(result))
        self.assertEqual(result.rows[0]["aspect"], "fighter eligibility")


class TestReviewerApprovedIdentityMigration(ReviewCase):
    """DEC-2026-0004 fixed the mapping but withheld the repoint per node.

    A `node_registry_decisions` entry naming a migration target and the edges
    that depend on it is the Reviewer confirmation the decision requires. Until
    it exists the edge keeps the legacy ID.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Whichever DEC-2026-0004 mapping is still pending. Naming one made this
        # class fail the moment the Integrator registered that target.
        cls.LEGACY, cls.TARGET = _bootstrap.unregistered_migration_pair(
            cls.compiler.governance, cls.compiler.registry
        )
        cls.EDGE = dict(
            EDGE_A, ref="C11", source_id=cls.LEGACY,
            source_label=cls.compiler.registry.nodes[cls.LEGACY].label,
            edge_type="GATES", target_id="cbt_initiative", target_label="Initiative",
            aspect="reviewer migration fixture", condition="",
        )

    def run_nodes(self, node_decisions, row_decisions=None):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            gur = Path(tmp) / "gur.yaml"
            gur.write_text(
                yaml.safe_dump({**ENVELOPE, "candidate_edges": [self.EDGE]}, sort_keys=False),
                encoding="utf-8",
            )
            review = Path(tmp) / "rev.yaml"
            review.write_text(
                yaml.safe_dump({
                    "id": "REV-GUP-PKT-PHB-777-778-fixture-r02-r01",
                    "packet_id": ENVELOPE["packet_id"],
                    "reviewed_gup": "GUP-PKT-PHB-777-778-fixture-r02",
                    "overall_disposition": "revision_required",
                    "row_decisions": row_decisions or [
                        {"ref": "C11", "disposition": "approved"}],
                    "node_registry_decisions": node_decisions,
                }, sort_keys=False),
                encoding="utf-8",
            )
            return self.compiler.compile(
                gur, directives=ReviewDirectives.load(review), revision=3
            )

    def test_without_reviewer_confirmation_the_legacy_id_stands(self):
        result = self.run_nodes([])
        self.assertEqual(result.rows[0]["source_id"], self.LEGACY)
        self.assertIn("endpoint_pending_migration", self.rules(result))

    def test_a_confirmed_mapping_repoints_the_named_edges(self):
        result = self.run_nodes([{
            "proposed_id": self.TARGET,
            "disposition": "approved_with_revision",
            "edges_depending_on_it": ["C11"],
        }])
        self.assertEqual(result.rows[0]["source_id"], self.TARGET)
        self.assertIn("endpoint_repointed_by_review", self.rules(result))
        self.assertIn("reviewer_approved_identity_migration", self.rules(result))

    def test_the_repointed_row_waits_on_the_registry(self):
        result = self.run_nodes([{
            "proposed_id": self.TARGET, "disposition": "approved_with_revision",
            "edges_depending_on_it": ["C11"],
        }])
        self.assertIn("C11", result.rows_pending)

    def test_the_node_carries_the_reviewers_label_not_the_legacy_one(self):
        result = self.run_nodes([{
            "proposed_id": self.TARGET,
            "disposition": "approved_with_revision",
            "edges_depending_on_it": ["C11"],
            "submitted_label": self.compiler.registry.nodes[self.LEGACY].label,
            "exact_corrections": {"proposed_label": "Corrected Fixture Label"},
        }])
        addition = next(
            n for n in result.node_additions if n["proposed_id"] == self.TARGET
        )
        self.assertEqual(addition["proposed_label"], "Corrected Fixture Label")
        self.assertEqual(addition["authority"], "DEC-2026-0004")

    def test_the_edge_label_agrees_with_the_node_it_depends_on(self):
        """A bundle must not disagree with itself about what a node is called."""
        result = self.run_nodes([{
            "proposed_id": self.TARGET,
            "disposition": "approved_with_revision",
            "edges_depending_on_it": ["C11"],
            "exact_corrections": {"proposed_label": "Corrected Fixture Label"},
        }])
        self.assertEqual(result.rows[0]["source_label"], "Corrected Fixture Label")

    def test_a_rejected_node_decision_repoints_nothing(self):
        result = self.run_nodes([{
            "proposed_id": self.TARGET, "disposition": "rejected",
            "edges_depending_on_it": ["C11"],
        }])
        self.assertEqual(result.rows[0]["source_id"], self.LEGACY)



class ReviewDecisionKeyCase(unittest.TestCase):
    """A Review states its rulings under one of two key names.

    The loader read `row_decisions` only. Seventeen published Reviews use
    `edge_decisions`, and every one of them loaded zero row rulings -- so a
    revision built from one would silently keep the rows the Reviewer rejected
    and look perfectly clean doing it. Both spellings carry the same entry
    shape; only the vintage differs.
    """

    ENTRY = {
        "ref": "M001",
        "disposition": "rejected",
        "rationale": "not supported by the source",
    }

    def write(self, document):
        import tempfile

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "REV-GUP-PKT-TEST-r01-r01.yaml"
        base = {
            "id": "REV-GUP-PKT-TEST-r01-r01",
            "packet_id": "PKT-TEST",
            "reviewed_gup": {"id": "GUP-PKT-TEST-r01"},
            "overall_disposition": "revision_required",
        }
        base.update(document)
        path.write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")
        return path

    def test_row_decisions_are_read(self):
        directives = ReviewDirectives.load(self.write({"row_decisions": [self.ENTRY]}))
        self.assertEqual(directives.rows["M001"].disposition, "rejected")

    def test_edge_decisions_are_read(self):
        """The spelling that silently loaded nothing."""
        directives = ReviewDirectives.load(self.write({"edge_decisions": [self.ENTRY]}))
        self.assertEqual(directives.rows["M001"].disposition, "rejected")

    def test_both_spellings_carry_exact_corrections(self):
        for key in ("row_decisions", "edge_decisions"):
            with self.subTest(key=key):
                entry = dict(self.ENTRY, disposition="approved_with_revision",
                             exact_corrections={"page": "115"})
                directives = ReviewDirectives.load(self.write({key: [entry]}))
                self.assertEqual(directives.rows["M001"].corrections, {"page": "115"})

    def test_a_review_using_both_keys_reads_every_ruling(self):
        directives = ReviewDirectives.load(
            self.write(
                {
                    "row_decisions": [self.ENTRY],
                    "edge_decisions": [dict(self.ENTRY, ref="M002")],
                }
            )
        )
        self.assertEqual(sorted(directives.rows), ["M001", "M002"])

    def test_an_unread_decision_key_is_reported(self):
        directives = ReviewDirectives.load(
            self.write({"assertion_decisions": [self.ENTRY]})
        )
        self.assertEqual(directives.unread_decision_keys, ["assertion_decisions"])
        self.assertEqual(directives.rows, {})

    def test_a_known_decision_key_is_not_reported(self):
        directives = ReviewDirectives.load(
            self.write(
                {
                    "edge_decisions": [self.ENTRY],
                    "node_registry_decisions": [
                        {"proposed_id": "rule_x", "disposition": "approved"}
                    ],
                }
            )
        )
        self.assertEqual(directives.unread_decision_keys, [])

    def test_an_unread_key_survives_a_review_chain(self):
        first = self.write({"edge_decisions": [self.ENTRY]})
        second = self.write({"assertion_decisions": [self.ENTRY]})
        merged = ReviewDirectives.load_chain([first, second])
        self.assertIn("assertion_decisions", merged.unread_decision_keys)


class LiveReviewSpellingCase(unittest.TestCase):
    """Every published Review must load the rulings it states."""

    @staticmethod
    def reviews():
        root = Path(__file__).resolve().parents[3]
        return sorted((root / "books" / "adnd1e" / "phb" / "artifacts" / "reviews").glob("REV-*.yaml"))

    def test_both_spellings_are_present_in_the_corpus(self):
        """If this stops being true the compatibility is still required."""
        spellings = set()
        for path in self.reviews():
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for key in ("row_decisions", "edge_decisions"):
                if document.get(key):
                    spellings.add(key)
        self.assertEqual(spellings, {"row_decisions", "edge_decisions"})

    def test_no_published_review_states_rulings_the_loader_cannot_read(self):
        offenders = {}
        for path in self.reviews():
            directives = ReviewDirectives.load(path)
            if directives.unread_decision_keys:
                offenders[path.name] = directives.unread_decision_keys
        self.assertEqual(offenders, {})

    def test_every_review_that_states_rulings_loads_them(self):
        """The defect in one assertion: rulings on disk, none in the directives."""
        empty = []
        for path in self.reviews():
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            stated = sum(
                len(document.get(key) or []) for key in ("row_decisions", "edge_decisions")
            )
            if not stated:
                continue
            if not ReviewDirectives.load(path).rows:
                empty.append(path.name)
        self.assertEqual(empty, [])

if __name__ == "__main__":
    unittest.main()


class TestReplaceRefFields(ReviewCase):
    """`replace_ref` with a `fields` block is a field correction.

    Three separate Reviews wrote a correction this way -- a polarity ruling and
    two endpoint repoints -- and the build read the bucket, ignored `fields`,
    and reported the row as correctly compiled. A correction the build silently
    declines to apply is the failure this whole path exists to prevent.
    """

    def test_a_fields_block_corrects_the_row(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "exact_corrections": {
                  "edge_changes": {"additions": {
                      "replace_ref": "A1",
                      "fields": {"target_id": "class_ranger", "target_label": "Ranger"},
                  }},
              }}],
        )
        self.assertEqual(result.rows[0]["target_id"], "class_ranger")
        self.assertEqual(result.rows[0]["target_label"], "Ranger")
        self.assertNotIn("reviewer_directive_not_understood", self.rules(result))

    def test_an_authored_polarity_may_be_corrected_through_fields(self):
        """MODIFIES leaves polarity to a reading, and the Reviewer owns readings."""
        result = self.run_with(
            [EDGE_AUTHORED],
            [{"ref": "M1", "disposition": "approved_with_revision",
              "exact_corrections": {
                  "edge_changes": {"additions": {
                      "replace_ref": "M1", "fields": {"polarity": "neutral"}}},
              }}],
        )
        self.assertEqual(result.rows[0]["polarity"], "neutral")
        self.assertNotIn("reviewer_correction_on_build_owned_field", self.rules(result))

    def test_a_derived_polarity_is_still_refused_through_fields(self):
        """The ownership check must not be bypassed by the bucket spelling.

        `GATES` polarity is derived from the edge type, so a Review cannot
        author it -- whichever syntax the correction arrives in.
        """
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "exact_corrections": {
                  "edge_changes": {"additions": {
                      "replace_ref": "A1", "fields": {"polarity": "worsens"}}},
              }}],
        )
        self.assertIn("reviewer_correction_on_build_owned_field", self.rules(result))
        self.assertNotEqual(result.rows[0]["polarity"], "worsens")

    def test_an_unknown_key_inside_a_bucket_instruction_is_an_error(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "exact_corrections": {
                  "edge_changes": {"additions": {"rearrange_the_rows": "somehow"}},
              }}],
        )
        self.assertIn("reviewer_directive_not_understood", self.rules(result))


class TestChainedReviewsKeepEarlierRulings(ReviewCase):
    """A later Review approves a patch the earlier Review already corrected.

    The build recompiles from the GUR, not from the reviewed patch, so anything
    the earlier Review fixed has to be re-applied. Letting the later row
    decision replace the earlier one wholesale means an approval silently undoes
    the corrections it is approving.
    """

    CANONICAL_ROW = 118

    def test_an_earlier_field_correction_survives_a_later_approval(self):
        result = self.run_with_chain(
            [EDGE_A],
            [
                {"row_decisions": [{"ref": "A1", "disposition": "approved_with_revision",
                                    "exact_corrections": {"aspect": "fighter eligibility"}}]},
                {"row_decisions": [{"ref": "A1", "disposition": "approved",
                                    "submitted_operations": ["additions"]}]},
            ],
        )
        self.assertEqual(result.rows[0]["aspect"], "fighter eligibility")

    def test_a_later_correction_wins_on_the_same_field(self):
        result = self.run_with_chain(
            [EDGE_A],
            [
                {"row_decisions": [{"ref": "A1", "disposition": "approved_with_revision",
                                    "exact_corrections": {"aspect": "fighter eligibility"}}]},
                {"row_decisions": [{"ref": "A1", "disposition": "approved_with_revision",
                                    "submitted_operations": ["additions"],
                                    "exact_corrections": {"aspect": "class eligibility"}}]},
            ],
        )
        self.assertEqual(result.rows[0]["aspect"], "class eligibility")

    def test_a_restated_operation_record_keeps_the_row_an_update(self):
        """The later Review restates the placement it approves, and that governs."""
        result = self.run_with_chain(
            [EDGE_A],
            [
                {"row_decisions": [{"ref": "A1", "disposition": "approved_with_revision",
                                    "exact_corrections": {
                                        "edge_changes.additions": {"remove_ref": "A1"},
                                        "edge_changes.updates": {
                                            "retain_ref": "A1",
                                            "canonical_row": self.CANONICAL_ROW}}}]},
                {"row_decisions": [{"ref": "A1", "disposition": "approved",
                                    "submitted_operations": ["updates"],
                                    "submitted_operation_records": [
                                        {"ref": "A1", "canonical_row": self.CANONICAL_ROW,
                                         "reason": "reviewer_canonical_update",
                                         "detail": "already canonical"}]}]},
            ],
        )
        self.assertEqual(result.additions, [])
        self.assertEqual(len(result.updates), 1)
        self.assertEqual(result.updates[0]["canonical_row"], self.CANONICAL_ROW)
        self.assertEqual(result.updates[0]["detail"], "already canonical")

    def test_a_later_review_may_return_a_row_to_additions(self):
        """Placement is not inherited where the later Review states its own.

        Merging placement instead would resurrect a canonical row number the
        later Review deliberately dropped.
        """
        result = self.run_with_chain(
            [EDGE_A],
            [
                {"row_decisions": [{"ref": "A1", "disposition": "approved_with_revision",
                                    "exact_corrections": {
                                        "edge_changes.updates": {
                                            "retain_ref": "A1",
                                            "canonical_row": self.CANONICAL_ROW}}}]},
                {"row_decisions": [{"ref": "A1", "disposition": "approved",
                                    "submitted_operations": ["additions"]}]},
            ],
        )
        self.assertEqual(result.updates, [])
        self.assertEqual(len(result.additions), 1)


class TestRowsRemovedFromABucket(ReviewCase):
    """One GUR candidate must not become two operations."""

    CANONICAL_ROW = 118

    def test_a_removed_bucket_is_reported(self):
        result = self.run_with(
            [EDGE_A],
            [{"ref": "A1", "disposition": "approved_with_revision",
              "submitted_operations": ["pending_additions", "updates"],
              "exact_corrections": {
                  "edge_changes": {
                      "pending_additions": {"remove_ref": "A1"},
                      "updates": {"retain_ref": "A1",
                                  "canonical_row": self.CANONICAL_ROW}}}}],
        )
        self.assertIn("reviewer_removed_row_from_bucket", self.rules(result))
        self.assertEqual(result.pending_additions, [])

    def test_a_superseded_row_is_never_also_pending(self):
        """A repair to an existing canonical row is not an insertion.

        The row's endpoint may still be a node this patch proposes, which is
        what puts it in `rows_pending`. That does not make it a second
        operation: the assertion is already in the graph.
        """
        from adnd1e_builder.compiler import CompileResult

        result = CompileResult(
            gur_id="GUR-fixture-r01", gup_id="GUP-fixture-r01", packet_id="PKT-fixture"
        )
        result.rows.append(dict(EDGE_A))
        result.rows_pending.add("A1")
        self.assertEqual([r["ref"] for r in result.pending_additions], ["A1"])
        result.rows_superseded.add("A1")
        self.assertEqual(result.pending_additions, [])
        self.assertEqual(result.additions, [])


class TestPresentedOperations(ReviewCase):
    """`submitted_operations` is how Reviews actually record placement.

    The build read only the singular `operation` key, so the check that a
    Reviewer-approved update never degrades into an insertion was inert against
    every Review in the repository.
    """

    def test_submitted_operations_is_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rev.yaml"
            path.write_text(
                yaml.safe_dump({
                    "id": "REV-fixture-r01",
                    "packet_id": ENVELOPE["packet_id"],
                    "reviewed_gup": "GUP-fixture-r01",
                    "overall_disposition": "revision_required",
                    "row_decisions": [
                        {"ref": "A1", "disposition": "approved",
                         "submitted_operations": ["updates"]},
                        {"ref": "B1", "disposition": "approved",
                         "submitted_operations": ["pending_additions", "updates"]},
                    ],
                }, sort_keys=False),
                encoding="utf-8",
            )
            directives = ReviewDirectives.load(path)

        self.assertEqual(directives.rows["A1"].presented_operation, "updates")
        self.assertEqual(directives.rows["A1"].presented_operations, ("updates",))
        # A row in two buckets has no single presented operation, and the
        # checks that read one must not pick between them.
        self.assertEqual(directives.rows["B1"].presented_operation, "")
        self.assertEqual(
            directives.rows["B1"].presented_operations, ("pending_additions", "updates")
        )
        self.assertTrue(directives.rows["B1"].states_placement)


class TestCarriedEscalationWithoutAnId(ReviewCase):
    """ESCALATION_CONTRACT requires an escalation ID on every escalation.

    Without one the build cannot tell an open question from one the Architect
    has already ruled on, so it carries the entry forward and blocks. That is
    correct -- the Builder never guesses which escalation an entry means -- but
    it has to say why, or the artifact owner sees only an unexplained
    `status: blocked`.
    """

    def test_an_id_less_escalation_is_reported_and_still_blocks(self):
        result = self.run_with(
            [EDGE_A], [{"ref": "A1", "disposition": "approved"}],
        )
        self.assertNotIn("gur_escalation_omits_id", self.rules(result))

    def test_the_missing_id_is_named_as_the_reason(self):
        import tempfile as _t
        with _t.TemporaryDirectory() as tmp:
            gur = Path(tmp) / "gur.yaml"
            gur.write_text(
                yaml.safe_dump(
                    {
                        **ENVELOPE,
                        "candidate_edges": [EDGE_A],
                        "architectural_escalations": [
                            {"topic": "an unresolved ontology question",
                             "question": "which node represents this?"}
                        ],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            result = self.compiler.compile(gur, revision=3)
        self.assertIn("gur_escalation_omits_id", self.rules(result))
        self.assertTrue(result.blocks_approval, "an unmatched escalation still blocks")
        detail = next(
            f.detail for f in result.findings if f.rule == "gur_escalation_omits_id"
        )
        self.assertIn("an unresolved ontology question", detail)

    def test_an_escalation_with_a_decided_id_does_not_block(self):
        """The existing path: a decided ID resolves and the patch proceeds."""
        decided = sorted(self.compiler.governance.decided_escalations)
        if not decided:
            self.skipTest("no decided escalation in the repository to exercise")
        import tempfile as _t
        with _t.TemporaryDirectory() as tmp:
            gur = Path(tmp) / "gur.yaml"
            gur.write_text(
                yaml.safe_dump(
                    {
                        **ENVELOPE,
                        "candidate_edges": [EDGE_A],
                        "architectural_escalations": [
                            {"id": decided[0], "question": "settled long ago"}
                        ],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            result = self.compiler.compile(gur, revision=3)
        self.assertIn("gur_escalation_since_decided", self.rules(result))
        self.assertNotIn("gur_escalation_omits_id", self.rules(result))


class FieldDecisionCase(unittest.TestCase):
    """A ruling on a GUP-level field, which names no row to attach to.

    Every other ruling shape keys on a `ref` or a proposed node ID, so the
    compiler can find the thing it edits. `field_decisions` keys on a field of
    the patch itself: the illusionist Review rules on `operation_index`, which
    describes the whole patch, and no edit to any single row satisfies it.

    Reading it matters because the alternative is silence. Before this, the key
    was unknown, and an unknown ruling key is a correction that quietly does not
    apply -- the revision comes out looking clean while ignoring what the
    Reviewer asked for. That is the same defect that once made the loader read
    one of four ruling shapes.
    """

    REVIEW = {
        "id": "REV-GUP-PKT-PHB-000-000-fixture-r01-r01",
        "packet_id": "PKT-PHB-000-000-fixture",
        "reviewed_gup": {"id": "GUP-PKT-PHB-000-000-fixture-r01"},
        "overall_disposition": "revision_required",
        "field_decisions": {
            "operation_index": {
                "disposition": "approved_with_revision",
                "exact_correction": "Add a valid csv_row locator to every declared operation.",
                "evidence": "126 declared operations over 14 CSV rows.",
            }
        },
    }

    def load(self, document=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.yaml"
            path.write_text(
                yaml.safe_dump(document or self.REVIEW, sort_keys=False), encoding="utf-8"
            )
            return ReviewDirectives.load(path)

    def test_the_key_is_read_rather_than_reported_unread(self):
        directives = self.load()
        self.assertEqual(directives.unread_decision_keys, [])

    def test_the_ruling_is_carried_with_its_correction(self):
        directive = self.load().field_directives[0]
        self.assertEqual(directive.field_name, "operation_index")
        self.assertEqual(directive.disposition, "approved_with_revision")
        self.assertIn("csv_row", directive.correction)
        self.assertIn("126", directive.evidence)

    def test_it_creates_no_row_or_node_directive(self):
        """It names no row, so inventing one would be the Builder guessing."""
        directives = self.load()
        self.assertEqual(directives.rows, {})
        self.assertEqual(directives.nodes, {})

    def test_a_review_without_the_key_carries_no_field_directive(self):
        document = dict(self.REVIEW)
        document.pop("field_decisions")
        self.assertEqual(self.load(document).field_directives, [])

    def test_a_malformed_entry_is_skipped_not_guessed(self):
        document = dict(self.REVIEW, field_decisions={"operation_index": "fix it"})
        self.assertEqual(self.load(document).field_directives, [])

    def test_the_known_key_set_names_it(self):
        from adnd1e_builder.review import FIELD_DECISION_KEY, KNOWN_DECISION_KEYS

        self.assertIn(FIELD_DECISION_KEY, KNOWN_DECISION_KEYS)


class LiveFieldDecisionCase(unittest.TestCase):
    """The published Review that produced this shape."""

    PATH = (
        REPO_ROOT / "books" / "adnd1e" / "phb" / "artifacts" / "reviews"
        / "REV-GUP-PKT-PHB-094-100-illusionist-spells-r04-r04.yaml"
    )

    def directives(self):
        if not self.PATH.is_file():  # pragma: no cover - the Review may be superseded
            self.skipTest("the illusionist remediation Review is not present")
        return ReviewDirectives.load(self.PATH)

    def test_the_illusionist_remediation_is_fully_read(self):
        directives = self.directives()
        self.assertEqual(directives.unread_decision_keys, [])
        self.assertEqual(
            [d.field_name for d in directives.field_directives], ["operation_index"]
        )

    def test_the_correction_names_the_csv_row_locator(self):
        directive = self.directives().field_directives[0]
        self.assertEqual(directive.disposition, "approved_with_revision")
        self.assertIn("csv_row", directive.correction)


class InheritedRejectionCase(unittest.TestCase):
    """A successor Review may carry forward rejections instead of restating them.

    DEC-2026-0051 produced the first one. r06 had to restate six rows as
    `approved` and keep the nine rejections its predecessor established; writing
    all fifteen again would have invited a transcription error in exactly the
    rows a superseded Review had already settled. So it names the source Review
    by ID and SHA-256 and lists the refs it preserves.

    The source is read and hashed rather than believed. A Review that claims an
    inheritance its source does not support inherits nothing and is reported as
    not fully understood, because applying nine unverified rejections silently is
    worse than refusing to compile.
    """

    SOURCE = "REV-GUP-PKT-PHB-999-999-fixture-r01-r01"
    REFS = ["M082", "M085"]

    def build(self, *, checksum=None, source_dispositions=None, refs=None,
              restate=None, omit_source=False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)

        dispositions = source_dispositions or {ref: "rejected" for ref in self.REFS}
        source_path = root / f"{self.SOURCE}.yaml"
        if not omit_source:
            source_path.write_text(
                yaml.safe_dump({
                    "id": self.SOURCE,
                    "packet_id": "PKT-PHB-999-999-fixture",
                    "overall_disposition": "revision_required",
                    "edge_decisions": [
                        {"ref": ref, "disposition": d,
                         "rationale": f"source rationale for {ref}"}
                        for ref, d in dispositions.items()
                    ],
                }, sort_keys=False),
                encoding="utf-8",
            )

        actual = (
            "sha256:" + hashlib.sha256(source_path.read_bytes()).hexdigest()
            if source_path.exists() else "sha256:" + "0" * 64
        )
        successor = {
            "id": "REV-GUP-PKT-PHB-999-999-fixture-r01-r02",
            "packet_id": "PKT-PHB-999-999-fixture",
            "supersedes": self.SOURCE,
            "overall_disposition": "revision_required",
            "review_contract_version": "1.1",
            "edge_decisions": restate or [],
            "inherited_edge_decisions": {
                "from_review": self.SOURCE,
                "checksum": checksum or actual,
                "preserved_rejected_refs": list(self.REFS if refs is None else refs),
                "rationale": "settled in the superseded review",
            },
        }
        path = root / "REV-GUP-PKT-PHB-999-999-fixture-r01-r02.yaml"
        path.write_text(yaml.safe_dump(successor, sort_keys=False), encoding="utf-8")
        return ReviewDirectives.load(path)

    # -- a sound inheritance -------------------------------------------------

    def test_the_preserved_rejections_are_applied(self):
        directives = self.build()
        self.assertEqual(
            {ref: directives.rows[ref].disposition for ref in self.REFS},
            {ref: "rejected" for ref in self.REFS},
        )

    def test_a_sound_inheritance_reports_no_unread_key(self):
        self.assertEqual(self.build().unread_decision_keys, [])

    def test_the_source_rationale_is_carried_not_invented(self):
        directives = self.build()
        self.assertIn("source rationale for M082", directives.rows["M082"].rationale)

    def test_a_restatement_in_the_successor_wins(self):
        """The successor is the active ruling; inheritance fills the gaps."""
        directives = self.build(
            restate=[{"ref": "M082", "disposition": "approved",
                      "rationale": "the successor reversed this"}]
        )
        self.assertEqual(directives.rows["M082"].disposition, "approved")
        self.assertEqual(directives.rows["M085"].disposition, "rejected")

    # -- and every way it can be unsound -------------------------------------

    def assert_refused(self, directives, fragment):
        self.assertEqual(directives.rows, {})
        self.assertTrue(directives.unread_decision_keys)
        self.assertIn(fragment, " ".join(directives.unread_decision_keys))

    def test_a_stale_source_checksum_inherits_nothing(self):
        self.assert_refused(
            self.build(checksum="sha256:" + "1" * 64), "now hashes to"
        )

    def test_an_absent_source_inherits_nothing(self):
        self.assert_refused(self.build(omit_source=True), "is not present")

    def test_a_ref_the_source_does_not_reject_inherits_nothing(self):
        """Claiming an inheritance the source will not support refuses all of it."""
        self.assert_refused(
            self.build(source_dispositions={"M082": "rejected", "M085": "approved"}),
            "does not reject M085",
        )

    def test_a_ref_absent_from_the_source_inherits_nothing(self):
        self.assert_refused(
            self.build(refs=["M082", "M999"]), "does not reject M999"
        )

    def test_an_empty_preserved_list_is_reported(self):
        self.assert_refused(self.build(refs=[]), "no preserved refs")


class LiveIllusionistR06Case(unittest.TestCase):
    """The published Review this reading was written for."""

    PATH = (
        REPO_ROOT / "books" / "adnd1e" / "phb" / "artifacts" / "reviews"
        / "REV-GUP-PKT-PHB-094-100-illusionist-spells-r05-r06.yaml"
    )
    APPROVED = ("M025", "M026", "M058", "M072", "M073", "M074")
    REJECTED = ("M082", "M085", "M086", "M090", "M095", "M096", "M100", "M102", "M112")

    def directives(self):
        if not self.PATH.is_file():  # pragma: no cover - superseded
            self.skipTest("the r06 Review is not present")
        return ReviewDirectives.load(self.PATH)

    def test_it_is_fully_read(self):
        self.assertEqual(self.directives().unread_decision_keys, [])

    def test_the_six_are_approved_and_the_nine_inherited_rejections_hold(self):
        rows = self.directives().rows
        self.assertEqual(
            {ref: rows[ref].disposition for ref in self.APPROVED},
            {ref: "approved" for ref in self.APPROVED},
        )
        self.assertEqual(
            {ref: rows[ref].disposition for ref in self.REJECTED},
            {ref: "rejected" for ref in self.REJECTED},
        )

    def test_it_introduces_no_disposition_outside_the_legal_four(self):
        """DEC-2026-0051: the invalid fifth term must not reappear."""
        rows = self.directives().rows
        self.assertEqual(
            {r.disposition for r in rows.values()}, {"approved", "rejected"}
        )


class ChainSupersedesUnknownDispositionCase(unittest.TestCase):
    """A later legal ruling settles a ref an earlier Review got wrong.

    DEC-2026-0051 declared `approved_but_excluded_from_bundle` invalid. r05-r04
    had used it on six rows and r06 restates those exact six as `approved`, so
    the merged chain applies a legal ruling to every one of them. Carrying the
    earlier complaint forward would block the build on a disposition the merged
    result never uses.

    The drop is per ref and only where a later Review actually restates it: an
    unknown disposition nobody revisited still stops the build, because nothing
    has replaced it.
    """

    def chain(self, later_disposition="approved", later_ref="M1"):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)

        def write(name, decisions):
            path = root / f"{name}.yaml"
            path.write_text(
                yaml.safe_dump({
                    "id": name,
                    "packet_id": "PKT-PHB-999-999-fixture",
                    "overall_disposition": "revision_required",
                    "edge_decisions": decisions,
                }, sort_keys=False),
                encoding="utf-8",
            )
            return path

        first = write("REV-GUP-PKT-PHB-999-999-fixture-r01-r01", [
            {"ref": "M1", "disposition": "approved_but_excluded_from_bundle"},
            {"ref": "M2", "disposition": "approved_but_excluded_from_bundle"},
        ])
        second = write("REV-GUP-PKT-PHB-999-999-fixture-r01-r02", [
            {"ref": later_ref, "disposition": later_disposition},
        ])
        return ReviewDirectives.load_chain([first, second])

    def test_a_restated_ref_drops_its_earlier_complaint(self):
        merged = self.chain()
        self.assertEqual(merged.rows["M1"].disposition, "approved")
        self.assertFalse(
            [e for e in merged.unknown_dispositions if e.startswith("M1: ")]
        )

    def test_a_ref_nobody_revisited_still_stops_the_build(self):
        merged = self.chain()
        self.assertTrue(
            [e for e in merged.unknown_dispositions if e.startswith("M2: ")],
            "M2 was never restated, so its unknown disposition must survive",
        )

    def test_a_later_illegal_ruling_does_not_clear_anything(self):
        """Replacing one invalid term with another settles nothing."""
        merged = self.chain(later_disposition="approved_pending_packaging")
        self.assertTrue(
            [e for e in merged.unknown_dispositions if e.startswith("M1: ")]
        )

    def test_the_live_illusionist_chain_merges_clean(self):
        base = REPO_ROOT / "books" / "adnd1e" / "phb" / "artifacts" / "reviews"
        paths = [
            base / "REV-GUP-PKT-PHB-094-100-illusionist-spells-r05-r04.yaml",
            base / "REV-GUP-PKT-PHB-094-100-illusionist-spells-r05-r06.yaml",
        ]
        if not all(p.is_file() for p in paths):  # pragma: no cover
            self.skipTest("the illusionist review chain is not present")
        merged = ReviewDirectives.load_chain(paths)
        self.assertEqual(merged.unknown_dispositions, [])
        self.assertEqual(merged.unread_decision_keys, [])
        self.assertEqual(len(merged.rows), 126)
        self.assertEqual(
            sum(1 for r in merged.rows.values() if r.disposition == "rejected"), 9
        )
