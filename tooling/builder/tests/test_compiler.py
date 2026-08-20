"""End-to-end compiler behaviour on synthetic GURs.

Fixtures are written inline so the tests do not depend on the state of any
particular packet.
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
from adnd1e_builder.emit import edges_csv, gup_document, validation_report
import json

from adnd1e_builder.registry import NodeRegistry, normalize_label
from adnd1e_builder.vocab import AUTHORED_POLARITY_TYPES, COLUMNS

REGISTRY_PATH = REPO_ROOT / "rulesets" / "adnd1e" / "registries" / "nodes.csv"
EDGES_PATH = REPO_ROOT / "rulesets" / "adnd1e" / "canonical" / "edges_master.csv"

BASE_ENVELOPE = {
    "schema_version": "1.0",
    "id": "GUR-PKT-PHB-999-999-fixture-r01",
    "status": "proposed",
    "ruleset_id": "adnd1e",
    "book_id": "phb",
    "source_id": "phb-legacy-unspecified",
    "packet_id": "PKT-PHB-999-999-fixture",
    "constitution_version": "1.2",
    "revision": 1,
    "page_start": 9,
    "page_end": 13,
}

BASE_EDGE = {
    "ref": "T1",
    "source_id": "abil_strength",
    "source_label": "Strength",
    "edge_type": "GATES",
    "target_id": "class_fighter",
    "target_label": "Fighter",
    "aspect": "class eligibility",
    "condition": "",
    "book": "PHB",
    "page": 9,
    "section": "STRENGTH TABLE I",
    "evidence": "explicit_rule",
    "pass": "page-sweep",
    "status": "core",
    "general_rule_id": "",
    "supersession_basis": "",
    "review_flag": "",
}


class CompilerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = NodeRegistry.load(REGISTRY_PATH)
        cls.canonical = CanonicalEdges.load(EDGES_PATH)
        # Governance is loaded from the repository, as in real use: Architect
        # decisions change how node proposals route.
        cls.governance = Governance.load(REPO_ROOT / "rulesets" / "adnd1e")
        cls.compiler = Compiler(cls.registry, cls.canonical, None, cls.governance)

    def compile_gur(self, **overrides):
        document = dict(BASE_ENVELOPE)
        document.update(overrides)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gur.yaml"
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            return self.compiler.compile(path)

    def rules(self, result):
        return {f.rule for f in result.findings}


class TestHappyPath(CompilerCase):
    def test_clean_edge_compiles(self):
        result = self.compile_gur(candidate_edges=[dict(BASE_EDGE)])
        self.assertEqual(len(result.rows), 1)
        self.assertEqual([f.detail for f in result.errors], [])

    def test_polarity_is_derived_for_gates(self):
        result = self.compile_gur(candidate_edges=[dict(BASE_EDGE)])
        self.assertEqual(result.rows[0]["polarity"], "enables")
        self.assertEqual(result.rows[0]["polarity_basis"], "derived")

    def test_authored_polarity_is_preserved(self):
        modifies = dict(BASE_EDGE, ref="T2", edge_type="MODIFIES",
                        target_id="save_poison", target_label="Saving Throw vs Poison",
                        aspect="save bonus", polarity="improves", polarity_basis="read")
        result = self.compile_gur(candidate_edges=[modifies])
        self.assertEqual(result.rows[0]["polarity"], "improves")
        self.assertEqual(result.rows[0]["polarity_basis"], "read")

    def test_empty_gur_compiles_to_empty_patch(self):
        result = self.compile_gur(candidate_edges=[])
        self.assertEqual(result.rows, [])
        self.assertEqual(result.status, "proposed")
        self.assertTrue(result.gur_checksum.startswith("sha256:"))


class TestConditionalFields(CompilerCase):
    def test_overrides_without_supersession_basis_errors(self):
        bad = dict(BASE_EDGE, edge_type="OVERRIDES", target_id="class_paladin",
                   target_label="Paladin")
        result = self.compile_gur(candidate_edges=[bad])
        self.assertIn("supersession_basis_required", self.rules(result))

    def test_supersession_basis_on_non_overrides_errors(self):
        bad = dict(BASE_EDGE, supersession_basis="later_publication")
        result = self.compile_gur(candidate_edges=[bad])
        self.assertIn("supersession_basis_forbidden", self.rules(result))

    def test_general_rule_id_requires_general_rule_pass(self):
        bad = dict(BASE_EDGE, general_rule_id="GR_SOMETHING")
        result = self.compile_gur(candidate_edges=[bad])
        self.assertIn("general_rule_id_forbidden", self.rules(result))

    def test_general_rule_pass_requires_an_id(self):
        bad = dict(BASE_EDGE, **{"pass": "general-rule"})
        result = self.compile_gur(candidate_edges=[bad])
        self.assertIn("general_rule_id_required", self.rules(result))

    def test_ua_must_be_optional(self):
        bad = dict(BASE_EDGE, book="UA", status="core", page=9)
        result = self.compile_gur(candidate_edges=[bad])
        self.assertIn("ua_must_be_optional", self.rules(result))


class TestVocabularyEnforcement(CompilerCase):
    def test_illegal_edge_type_escalates(self):
        bad = dict(BASE_EDGE, edge_type="RELATED_TO")
        result = self.compile_gur(candidate_edges=[bad])
        self.assertIn("edge_type_illegal", self.rules(result))
        self.assertEqual(result.rows, [], "an illegal edge type yields no row")
        self.assertTrue(any(e["kind"] == "edge_vocabulary" for e in result.escalations))

    def test_illegal_evidence_class(self):
        result = self.compile_gur(candidate_edges=[dict(BASE_EDGE, evidence="probably")])
        self.assertIn("evidence_illegal", self.rules(result))

    def test_illegal_review_flag(self):
        result = self.compile_gur(candidate_edges=[dict(BASE_EDGE, review_flag="looks_wrong")])
        self.assertIn("review_flag_illegal", self.rules(result))

    def test_illegal_book(self):
        result = self.compile_gur(candidate_edges=[dict(BASE_EDGE, book="OA")])
        self.assertIn("book_illegal", self.rules(result))


class TestIdentity(CompilerCase):
    def test_unknown_node_is_an_error_not_a_guess(self):
        bad = dict(BASE_EDGE, target_id="class_nonexistent", target_label="Nonexistent Class")
        result = self.compile_gur(candidate_edges=[bad])
        self.assertIn("endpoint_unresolved", self.rules(result))
        self.assertEqual(result.rows, [])

    def test_label_match_escalates_rather_than_merging(self):
        bad = dict(BASE_EDGE, target_id="class_fighters", target_label="Fighter")
        result = self.compile_gur(candidate_edges=[bad])
        self.assertIn("identity_ambiguous", self.rules(result))
        self.assertTrue(any(e["kind"] == "identity_resolution" for e in result.escalations))
        self.assertEqual(result.rows, [], "Builder never merges identity by label")

    def test_label_case_difference_is_normalized_silently(self):
        # Case alone is not a label change worth reporting; identity is the ID.
        result = self.compile_gur(candidate_edges=[dict(BASE_EDGE, source_label="STRENGTH")])
        self.assertEqual(result.rows[0]["source_label"], "Strength")
        self.assertNotIn("label_normalized", self.rules(result))

    def test_differing_label_is_normalized_and_reported(self):
        result = self.compile_gur(
            candidate_edges=[dict(BASE_EDGE, source_label="Str Score")]
        )
        self.assertEqual(result.rows[0]["source_label"], "Strength")
        self.assertIn("label_normalized", self.rules(result))
        # Reported as info: the label changed, the identity did not.
        self.assertEqual([f.severity for f in result.findings if f.rule == "label_normalized"],
                         ["info"])

    def test_proposed_node_holds_its_dependent_edge_without_blocking(self):
        """DEC-2026-0003: a clean proposal is not an Architect matter.

        Before that decision this case was an error and blocked the patch. It is
        now normal Builder/Reviewer work, so the edge is held out of the
        integrable set but nothing is blocked.
        """
        result = self.compile_gur(
            candidate_nodes=[{
                "proposed_id": "rule_brand_new_mechanic",
                "proposed_label": "Brand New Mechanic",
                "why_needed": "fixture",
                "edges_depending_on_it": ["T1"],
            }],
            candidate_edges=[dict(BASE_EDGE, target_id="rule_brand_new_mechanic",
                                  target_label="Brand New Mechanic")],
        )
        self.assertIn("endpoint_pending_registry_addition", self.rules(result))
        self.assertEqual(result.status, "proposed")
        self.assertEqual(result.escalations, [])
        self.assertEqual(result.node_additions[0]["disposition"], "reviewer_may_approve")
        self.assertEqual(len(result.pending_additions), 1)

    def test_pending_edge_is_held_out_of_the_integrable_set(self):
        """Invariant 1: the CSV must never carry an edge to a node that does not exist."""
        result = self.compile_gur(
            candidate_nodes=[{"proposed_id": "rule_brand_new_mechanic",
                              "proposed_label": "Brand New Mechanic"}],
            candidate_edges=[
                dict(BASE_EDGE, ref="P1", target_id="rule_brand_new_mechanic",
                     target_label="Brand New Mechanic"),
                dict(BASE_EDGE, ref="P2", target_id="class_paladin", target_label="Paladin"),
            ],
        )
        self.assertEqual([r["ref"] for r in result.pending_additions], ["P1"])
        self.assertEqual([r["ref"] for r in result.additions], ["P2"])
        csv_text = edges_csv(result)
        self.assertNotIn("rule_brand_new_mechanic", csv_text)
        self.assertIn("class_paladin", csv_text)

    def test_every_csv_row_has_canonical_endpoints(self):
        result = self.compile_gur(
            candidate_nodes=[{"proposed_id": "rule_brand_new_mechanic",
                              "proposed_label": "Brand New Mechanic"}],
            candidate_edges=[
                dict(BASE_EDGE, ref="P1", target_id="rule_brand_new_mechanic",
                     target_label="Brand New Mechanic"),
                dict(BASE_EDGE, ref="P2"),
            ],
        )
        import csv as _csv
        for row in _csv.DictReader(edges_csv(result).splitlines()):
            self.assertIn(row["source_id"], self.registry)
            self.assertIn(row["target_id"], self.registry)

    def test_node_additions_are_isolated_from_edges(self):
        result = self.compile_gur(
            candidate_nodes=[{"proposed_id": "rule_new_thing", "proposed_label": "New Thing"}],
            candidate_edges=[dict(BASE_EDGE)],
        )
        self.assertEqual(len(result.node_additions), 1)
        self.assertEqual(len(result.rows), 1)
        self.assertNotIn("rule_new_thing", {r["target_id"] for r in result.rows})

    def test_proposing_an_existing_id_under_another_label_is_an_error(self):
        """Narrowed from "proposing an existing node is an error".

        Same ID under the *same* label is a duplicate proposal, not a defect:
        the Analyst reads the source, so a node an earlier packet proposed and
        the Integrator has since registered gets proposed again, and reuse is
        what constitution 3.2 asks for. Same ID under a different label is the
        case this rule was for, and it still errors. See
        `TestProposalAlreadyCanonical` for both sides.
        """
        result = self.compile_gur(
            candidate_nodes=[{"proposed_id": "race_dwarf", "proposed_label": "Hill Dwarf"}]
        )
        self.assertIn("node_addition_already_canonical", self.rules(result))

    def test_unapproved_prefix_on_a_proposal_is_an_error(self):
        # turn_ was rejected by DEC-2026-0004 and must stay unapproved.
        result = self.compile_gur(
            candidate_nodes=[{"proposed_id": "turn_something", "proposed_label": "Turn Something"}]
        )
        self.assertIn("node_prefix_unapproved", self.rules(result))
        self.assertTrue(result.node_additions[0]["architect_required"])


class TestCanonicalDuplicates(CompilerCase):
    """An assertion already in the canonical graph.

    The fixture is derived from a live canonical row rather than named, because
    naming one makes the test a hostage to integration: the moment a bundle
    repairs that row's polarity the whole class fails on facts about the corpus
    instead of facts about the compiler.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # A row whose polarity is still unset, on a type where polarity is a
        # reading rather than a derivation -- that is the case these tests are
        # about, and there is no point asserting on any other.
        cls.canonical_row, cls.canonical_line = _bootstrap.canonical_row_where(
            cls.canonical,
            lambda row: row["polarity_basis"] == "unset"
            and row["edge_type"] in AUTHORED_POLARITY_TYPES
            and row["source_id"] in cls.registry
            and row["target_id"] in cls.registry
            and row["book"] == "PHB"
            and (row["page"] or "").isdigit(),
        )
        source = cls.canonical_row
        cls.CANON = dict(
            BASE_EDGE,
            ref="X1",
            source_id=source["source_id"],
            source_label=source["source_label"],
            edge_type=source["edge_type"],
            target_id=source["target_id"],
            target_label=source["target_label"],
            aspect=source["aspect"],
            condition=source["condition"],
            book=source["book"],
            page=int(source["page"]),
            section=source["section"],
            evidence=source["evidence"] or "explicit_rule",
            status=source["status"] or "core",
            **{"pass": source["pass"] or "page-sweep"},
        )

    def test_identical_restatement_is_a_duplicate_error(self):
        row = dict(self.CANON, polarity="neutral", polarity_basis="unset")
        result = self.compile_gur(candidate_edges=[row])
        self.assertIn("duplicate_assertion", self.rules(result))
        self.assertEqual(result.updates, [])

    def test_polarity_only_difference_becomes_an_update(self):
        row = dict(self.CANON, polarity="improves", polarity_basis="read")
        result = self.compile_gur(candidate_edges=[row])
        self.assertEqual(len(result.updates), 1)
        self.assertEqual(result.updates[0]["reason"], "polarity_repair")
        self.assertEqual(set(result.updates[0]["changes"]), {"polarity", "polarity_basis"})
        self.assertNotIn("duplicate_assertion", self.rules(result))
        self.assertIn("duplicate_resolved_as_update", self.rules(result))

    def test_update_is_not_also_an_addition(self):
        row = dict(self.CANON, polarity="improves", polarity_basis="read")
        result = self.compile_gur(candidate_edges=[row])
        self.assertEqual(result.additions, [], "an update must not be emitted as a new row")
        self.assertNotIn("X1", edges_csv(result))

    def test_other_differing_fields_are_reported_not_applied(self):
        row = dict(self.CANON, polarity="improves", polarity_basis="read",
                   **{"pass": "page-sweep"})
        result = self.compile_gur(candidate_edges=[row])
        self.assertEqual(len(result.updates), 1)
        update = result.updates[0]
        self.assertEqual(set(update["changes"]), {"polarity", "polarity_basis"})
        self.assertIn("pass", update["differences_not_applied"])
        self.assertEqual(update["differences_not_applied"]["pass"]["canonical"], "prose-sweep")

    def test_any_authored_reading_repairs_an_unset_canonical_row(self):
        row = dict(self.CANON, polarity="worsens", polarity_basis="read")
        result = self.compile_gur(candidate_edges=[row])
        self.assertEqual(len(result.updates), 1)
        self.assertEqual(result.updates[0]["changes"]["polarity"]["patch"], "worsens")

    def test_conflicting_read_polarity_is_an_error_not_an_update(self):
        """Two different read polarities on one assertion is not the Builder's to settle."""
        # Build a compiler over a canonical corpus whose matching row already
        # carries an authored reading, so the repair path must not apply.
        import copy

        canonical = copy.deepcopy(self.canonical)
        # Locate the row by assertion key rather than by position.
        probe = {k: self.CANON[k] for k in
                 ("source_id", "edge_type", "target_id", "aspect", "condition")}
        [match] = canonical.exact_matches(probe)
        target = canonical.rows[match["canonical_index"]]
        self.assertEqual(target["polarity_basis"], "unset")
        target["polarity"], target["polarity_basis"] = "improves", "read"

        compiler = Compiler(self.registry, canonical)
        with tempfile.TemporaryDirectory() as tmp:
            document = dict(BASE_ENVELOPE)
            document["candidate_edges"] = [
                dict(self.CANON, polarity="worsens", polarity_basis="read")
            ]
            path = Path(tmp) / "gur.yaml"
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            result = compiler.compile(path)

        self.assertEqual(result.updates, [], "the Builder must not pick a winner")
        self.assertIn("polarity_conflict_with_canonical", {f.rule for f in result.findings})
        self.assertTrue(result.blocks_approval)


class TestCarriedForwardCandidates(CompilerCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pending_node, cls.governance = _bootstrap.unregistered_returned_to_workflow(
            cls.governance, cls.registry
        )
        cls.compiler = Compiler(cls.registry, cls.canonical, None, cls.governance)

    def test_carried_candidate_is_pending_not_unresolved(self):
        result = self.compile_gur(
            # Whichever DEC-2026-0003 proposal is still unregistered. Naming a
            # particular one made the test expire the moment it was registered.
            carried_forward_candidates=[
                {"id": self.pending_node,
                 "first_proposed_in": "GUR-EARLIER-r01", "edges_here": ["T1"]}
            ],
            candidate_edges=[dict(BASE_EDGE, target_id=self.pending_node,
                                  target_label="Fixture Carried Candidate")],
        )
        self.assertIn("endpoint_pending_registry_addition", self.rules(result))
        self.assertNotIn("endpoint_unresolved", self.rules(result))
        addition = result.node_additions[0]
        self.assertTrue(addition["carried_forward"])
        self.assertEqual(addition["first_proposed_in"], "GUR-EARLIER-r01")
        # DEC-2026-0003 returned rule_prime_requisite to normal workflow, so a
        # carried-forward candidate is no longer escalated for being unruled.
        self.assertEqual(addition["disposition"], "reviewer_may_approve")
        self.assertEqual(addition["returned_to_workflow_by"], "DEC-2026-0003")
        # Every node proposal states why it routed the way it did.
        self.assertIn("DEC-2026-0003", addition["routing_basis"])
        self.assertEqual(result.escalations, [])

    def test_carried_candidate_with_an_unapproved_prefix_still_escalates(self):
        result = self.compile_gur(
            carried_forward_candidates=[
                {"id": "magic_carried_thing", "first_proposed_in": "GUR-EARLIER-r01",
                 "edges_here": ["T1"]}
            ],
            candidate_edges=[dict(BASE_EDGE, target_id="magic_carried_thing",
                                  target_label="Carried Thing")],
        )
        self.assertTrue(result.node_additions[0]["architect_required"])
        self.assertTrue(
            any(e["kind"] == "node_registration_carried_forward" for e in result.escalations)
        )

    def test_carried_candidate_already_canonical_is_ignored(self):
        result = self.compile_gur(
            carried_forward_candidates=[{"id": "race_dwarf"}],
            candidate_edges=[],
        )
        self.assertEqual(result.node_additions, [])


class TestPendingRowsAreLegibleOnDisk(CompilerCase):
    """A held-back row must be readable from a file, not only from the GUP.

    `GUP-PKT-PHB-119-119-alignment-graph-r02` emitted a header-only
    `.edges.csv`, correctly: all four of its rows depended on nodes the same
    patch proposed, and a row pointing at an unregistered node breaches
    invariant 1. But that file hashed byte-identical to the preamble packet's
    genuinely empty one, an Approved bundle was assembled whose operation index
    asserted four edges the CSV did not contain, and the Integrator rejected the
    batch at the precondition gate.

    The rows were never missing. What was missing was somewhere to read them
    from, so the difference between "nothing to emit" and "everything is
    pending" is now visible on disk.
    """

    #: Absent from the registry, approved prefix, so it is proposable.
    NODE = "rule_fixture_pending_endpoint"

    def compile_with_pending(self):
        return self.compile_gur(
            candidate_nodes=[{
                "proposed_id": self.NODE, "proposed_label": "Fixture Pending Endpoint",
                "why_needed": "The packet names it.", "edges_depending_on_it": ["T1"],
            }],
            candidate_edges=[dict(BASE_EDGE, target_id=self.NODE,
                                  target_label="Fixture Pending Endpoint")],
        )

    def test_a_wholly_pending_patch_still_emits_an_empty_edges_csv(self):
        """The invariant 1 guarantee is unchanged, and that is the point."""
        import csv as _csv

        result = self.compile_with_pending()
        self.assertEqual(result.additions, [])
        self.assertEqual(len(result.pending_additions), 1)
        rows = list(_csv.DictReader(edges_csv(result).splitlines()))
        self.assertEqual(rows, [], "a pending row must never reach the integration input")

    def test_the_pending_rows_are_emitted_in_the_same_eighteen_columns(self):
        import csv as _csv

        from adnd1e_builder.emit import pending_csv

        result = self.compile_with_pending()
        text = pending_csv(result)
        self.assertEqual(text.splitlines()[0].split(","), list(COLUMNS))
        rows = list(_csv.DictReader(text.splitlines()))
        self.assertEqual([r["target_id"] for r in rows], [self.NODE])
        self.assertEqual(set(rows[0]), set(COLUMNS))

    def test_the_two_files_partition_the_compiled_rows(self):
        """Every row lands in exactly one of them, and never in both."""
        import csv as _csv

        from adnd1e_builder.emit import pending_csv

        result = self.compile_with_pending()
        integrable = {r["target_id"] for r in _csv.DictReader(edges_csv(result).splitlines())}
        held = {r["target_id"] for r in _csv.DictReader(pending_csv(result).splitlines())}
        self.assertEqual(integrable & held, set())
        self.assertEqual(len(integrable) + len(held), len(result.rows))

    def test_the_file_exists_only_when_something_is_held(self):
        """Its presence is the signal; an empty one beside a full edges CSV would not be."""
        from adnd1e_builder.emit import write_all

        with tempfile.TemporaryDirectory() as tmp:
            gup_dir, reports = Path(tmp) / "gup", Path(tmp) / "reports"
            clean = self.compile_gur(candidate_edges=[dict(BASE_EDGE)])
            written = write_all(clean, gup_dir, reports, {"ran": False})
            self.assertEqual([p.name for p in written if p.name.endswith(".pending.csv")], [])

            # Same fixture GUR, so the same GUP ID. Publication is create-only
            # with no override (DEC-2026-0053), so the second case gets its own
            # directories rather than rewriting the first.
            second, second_reports = Path(tmp) / "gup2", Path(tmp) / "reports2"
            pending = self.compile_with_pending()
            written = write_all(pending, second, second_reports, {"ran": False})
            self.assertEqual(
                [p.name for p in written if p.name.endswith(".pending.csv")],
                [f"{pending.gup_id}.pending.csv"],
            )

    def test_a_header_only_edges_csv_no_longer_hides_which_case_it_is(self):
        """The collision that caused the rejection: two states, one hash."""
        from adnd1e_builder.emit import pending_csv

        nothing = self.compile_gur(candidate_edges=[])
        everything_pending = self.compile_with_pending()
        self.assertEqual(edges_csv(nothing), edges_csv(everything_pending))
        self.assertNotEqual(pending_csv(nothing), pending_csv(everything_pending))


class TestAPublishedRevisionIsImmutable(CompilerCase):
    """Recompiling at an existing revision must not rewrite it.

    INT-20260812-002 rejected four bundles because the checksum each Review
    pinned for its GUP matched no file on disk: the revision had been recompiled
    in place while the Review was open, so the reviewed content was gone. The
    CLI already told the operator that "FILE_NAMING forbids overwriting a prior
    revision" on the --review path, but nothing enforced it at the write.
    """

    def publish(self, gup_dir, reports, **kwargs):
        from adnd1e_builder.emit import write_all

        return write_all(
            self.compile_gur(candidate_edges=[dict(BASE_EDGE)]),
            gup_dir, reports, {"ran": False}, **kwargs,
        )

    def test_republishing_the_same_revision_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            gup_dir, reports = Path(tmp) / "gup", Path(tmp) / "reports"
            self.publish(gup_dir, reports)
            with self.assertRaises(FileExistsError):
                self.publish(gup_dir, reports)

    def test_the_refusal_leaves_the_published_bytes_untouched(self):
        """The point of the guard: what a Review hashed still hashes the same."""
        import hashlib

        with tempfile.TemporaryDirectory() as tmp:
            gup_dir, reports = Path(tmp) / "gup", Path(tmp) / "reports"
            written = self.publish(gup_dir, reports)
            before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in written}
            with self.assertRaises(FileExistsError):
                self.publish(gup_dir, reports)
            after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in written}
            self.assertEqual(before, after)

    def test_the_refusal_names_the_revision_and_says_to_advance(self):
        with tempfile.TemporaryDirectory() as tmp:
            gup_dir, reports = Path(tmp) / "gup", Path(tmp) / "reports"
            result = self.compile_gur(candidate_edges=[dict(BASE_EDGE)])
            self.publish(gup_dir, reports)
            with self.assertRaises(FileExistsError) as raised:
                self.publish(gup_dir, reports)
            message = str(raised.exception)
            self.assertIn(result.gup_id, message)
            self.assertIn("next revision", message)

    def test_there_is_no_override(self):
        """DEC-2026-0053 removed it: an override that exists is one that gets used.

        It was added for "a revision nothing has consumed", which is a fact the
        writer cannot check -- a Review may already have hashed the file. That is
        how GUP-MIG-DEC-2026-0050-r01 was destroyed, with the flag set.
        """
        with tempfile.TemporaryDirectory() as tmp:
            gup_dir, reports = Path(tmp) / "gup", Path(tmp) / "reports"
            self.publish(gup_dir, reports)
            with self.assertRaises(TypeError):
                self.publish(gup_dir, reports, allow_overwrite=True)
            with self.assertRaises(FileExistsError):
                self.publish(gup_dir, reports)

    def test_a_fresh_revision_never_trips_the_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            gup_dir, reports = Path(tmp) / "gup", Path(tmp) / "reports"
            self.publish(gup_dir, reports)
            other = self.compile_gur(candidate_edges=[dict(BASE_EDGE)], revision=2)
            from adnd1e_builder.emit import write_all

            written = write_all(other, gup_dir, reports, {"ran": False})
            self.assertTrue(any(p.name.endswith(".yaml") for p in written))

    def test_the_cli_offers_no_overwrite_flag(self):
        """The operator cannot ask for it, because it is not on offer."""
        import contextlib
        import io

        from adnd1e_builder.cli import main

        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), self.assertRaises(SystemExit):
            main(["compile", "--help"])
        self.assertNotIn("--allow-overwrite", captured.getvalue())


class TestCrossPacketCandidateTargets(CompilerCase):
    """Endpoints another packet minted and this one reuses.

    A book is not a partition: the illusionist list points at magic-user spells,
    the magic-user list points at druid spells, and three packets reach the same
    death rule. The Analyst declares each of these in the GUR and tells the
    Builder not to mint a second identity for it. Before this was honoured, four
    packets blocked on `endpoint_unresolved` for endpoints the GUR had already
    accounted for.
    """

    #: Absent from the registry and carrying an approved prefix.
    ELSEWHERE = "spell_fixture_minted_elsewhere"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        assert cls.ELSEWHERE not in cls.registry, "fixture ID must be unregistered"
        # A node whose label is unique in the registry, so a fixture ID carrying
        # that label resolves by normalized label to exactly this node. That is
        # the shape of the rule_death / death_character case.
        counts: dict[str, int] = {}
        for node in cls.registry.nodes.values():
            counts[normalize_label(node.label)] = counts.get(normalize_label(node.label), 0) + 1
        cls.collides_with = next(
            node for node in cls.registry.nodes.values()
            if counts[normalize_label(node.label)] == 1 and node.label
        )

    def declare(self, node_id, **extra):
        return [{
            "id": node_id,
            "label": extra.get("label", "Minted Elsewhere"),
            "origin": "candidate minted by GUR-PKT-PHB-000-000-other-r01, not yet canonical",
            "used_by": ["T1"],
            "builder_instruction": "Do not mint a second identity.",
        }]

    def edge_to(self, node_id, label="Minted Elsewhere"):
        return [dict(BASE_EDGE, target_id=node_id, target_label=label)]

    def test_a_declared_target_is_pending_rather_than_unresolved(self):
        result = self.compile_gur(
            cross_packet_candidate_targets=self.declare(self.ELSEWHERE),
            candidate_edges=self.edge_to(self.ELSEWHERE),
        )
        self.assertIn("endpoint_pending_cross_packet_candidate", self.rules(result))
        self.assertNotIn("endpoint_unresolved", self.rules(result))
        self.assertEqual([f.detail for f in result.errors], [])
        self.assertEqual(result.escalations, [])
        # Held out of the integrable set, exactly like a row depending on a node
        # this patch proposes: the origin packet's registration comes first.
        self.assertEqual(result.additions, [])
        self.assertEqual([r["ref"] for r in result.pending_additions], ["T1"])

    def test_a_declared_target_is_not_re_proposed_here(self):
        """The packet that minted the identity owns the registration.

        Proposing it again would ask the Integrator to register one node from
        two GUPs, which is the duplication the declaration exists to prevent.
        """
        result = self.compile_gur(
            cross_packet_candidate_targets=self.declare(self.ELSEWHERE),
            candidate_edges=self.edge_to(self.ELSEWHERE),
        )
        self.assertEqual(result.node_additions, [])
        self.assertEqual(
            [(d["node_id"], d["state"]) for d in result.cross_packet_dependencies],
            [(self.ELSEWHERE, "awaiting_origin_packet")],
        )

    def test_the_declared_label_reaches_the_row(self):
        """An empty label makes the row schema-invalid, and two reached a bundle.

        The Analyst carries the label on the declaration rather than repeating
        it on every edge that reaches the identity, so a row whose endpoint is
        minted elsewhere legitimately arrives with `target_label` unset.
        """
        result = self.compile_gur(
            cross_packet_candidate_targets=self.declare(self.ELSEWHERE),
            candidate_edges=[dict(BASE_EDGE, target_id=self.ELSEWHERE, target_label=None)],
        )
        self.assertEqual(result.rows[0]["target_label"], "Minted Elsewhere")
        self.assertIn("endpoint_label_from_cross_packet_declaration", self.rules(result))

    def test_a_label_on_the_row_is_not_overwritten_by_the_declaration(self):
        result = self.compile_gur(
            cross_packet_candidate_targets=self.declare(self.ELSEWHERE),
            candidate_edges=self.edge_to(self.ELSEWHERE, "Row's Own Label"),
        )
        self.assertEqual(result.rows[0]["target_label"], "Row's Own Label")

    def test_every_emitted_row_carries_both_labels(self):
        """The schema requires them non-empty, so the compiler must guarantee it."""
        result = self.compile_gur(
            cross_packet_candidate_targets=self.declare(self.ELSEWHERE),
            candidate_edges=[dict(BASE_EDGE, target_id=self.ELSEWHERE, target_label=None)],
        )
        for row in result.rows:
            self.assertTrue(row["source_label"].strip(), row)
            self.assertTrue(row["target_label"].strip(), row)

    def test_an_undeclared_missing_endpoint_still_errors(self):
        """The guard has to be the declaration, not the mere absence of a node."""
        result = self.compile_gur(candidate_edges=self.edge_to(self.ELSEWHERE))
        self.assertIn("endpoint_unresolved", self.rules(result))
        self.assertTrue(result.blocks_approval)

    def test_a_declared_target_whose_label_collides_is_neither_merged_nor_escalated(self):
        label = self.collides_with.label
        result = self.compile_gur(
            cross_packet_candidate_targets=self.declare("rule_fixture_collision", label=label),
            candidate_edges=self.edge_to("rule_fixture_collision", label=label),
        )
        self.assertNotIn("identity_ambiguous", self.rules(result))
        self.assertEqual(result.escalations, [])
        # The requested identity is kept. Invariant 4 bars resolving it to the
        # canonical node the label matches, and the declaration does not license
        # that either -- it only says where the identity comes from.
        self.assertEqual(result.rows[0]["target_id"], "rule_fixture_collision")
        detail = next(
            f.detail for f in result.findings
            if f.rule == "endpoint_pending_cross_packet_candidate"
        )
        self.assertIn(self.collides_with.id, detail, "the collision stays visible to the Reviewer")

    def test_an_undeclared_label_collision_still_escalates(self):
        label = self.collides_with.label
        result = self.compile_gur(candidate_edges=self.edge_to("rule_fixture_collision", label=label))
        self.assertIn("identity_ambiguous", self.rules(result))
        self.assertTrue(any(e["kind"] == "identity_resolution" for e in result.escalations))

    def test_a_target_this_packet_also_proposes_is_proposed_once(self):
        result = self.compile_gur(
            cross_packet_candidate_targets=self.declare(self.ELSEWHERE),
            candidate_nodes=[{
                "proposed_id": self.ELSEWHERE,
                "proposed_label": "Minted Elsewhere",
                "why_needed": "Also proposed by the origin packet.",
                "edges_depending_on_it": ["T1"],
            }],
            candidate_edges=self.edge_to(self.ELSEWHERE),
        )
        self.assertEqual([n["proposed_id"] for n in result.node_additions], [self.ELSEWHERE])
        self.assertEqual(result.cross_packet_dependencies[0]["state"], "proposed_by_this_packet")
        self.assertIn("endpoint_pending_registry_addition", self.rules(result))

    def test_a_target_already_registered_needs_no_holding(self):
        node = self.registry.nodes["race_dwarf"]
        result = self.compile_gur(
            cross_packet_candidate_targets=self.declare("race_dwarf", label=node.label),
            candidate_edges=self.edge_to("race_dwarf", node.label),
        )
        self.assertEqual(result.cross_packet_dependencies[0]["state"], "already_canonical")
        self.assertEqual([r["ref"] for r in result.additions], ["T1"])
        self.assertEqual(result.pending_additions, [])

    def test_the_declaration_order_does_not_change_the_output(self):
        pair = self.declare(self.ELSEWHERE) + self.declare("race_dwarf", label="Dwarf")
        forward = self.compile_gur(
            cross_packet_candidate_targets=pair,
            candidate_edges=self.edge_to(self.ELSEWHERE),
        )
        reverse = self.compile_gur(
            cross_packet_candidate_targets=list(reversed(pair)),
            candidate_edges=self.edge_to(self.ELSEWHERE),
        )
        self.assertEqual(forward.cross_packet_dependencies, reverse.cross_packet_dependencies)


class TestProposalAlreadyCanonical(CompilerCase):
    """A candidate the registry already carries under the same name.

    The Analyst reads the source, not the registry, so a node an earlier packet
    proposed and the Integrator has since registered gets proposed again. That
    is not an architectural question: constitution 3.2 says reuse it, and the
    edges already resolve. Escalating it blocked three packets on a question
    with one answer.
    """

    def canonical_node(self):
        return self.registry.nodes["race_dwarf"]

    def propose(self, label):
        node = self.canonical_node()
        return dict(
            candidate_nodes=[{
                "proposed_id": node.id,
                "proposed_label": label,
                "why_needed": "The packet names it.",
                "edges_depending_on_it": ["T1"],
            }],
            candidate_edges=[dict(BASE_EDGE, target_id=node.id, target_label=node.label)],
        )

    def test_same_id_and_label_is_reused_not_escalated(self):
        node = self.canonical_node()
        result = self.compile_gur(**self.propose(node.label))
        self.assertIn("node_proposal_resolved_to_canonical", self.rules(result))
        self.assertNotIn("node_addition_already_canonical", self.rules(result))
        self.assertEqual(result.node_additions, [])
        self.assertEqual(result.escalations, [])
        self.assertEqual([f.detail for f in result.errors], [])
        self.assertEqual([r["ref"] for r in result.additions], ["T1"])

    def test_the_label_comparison_is_normalized(self):
        result = self.compile_gur(**self.propose(self.canonical_node().label.upper()))
        self.assertIn("node_proposal_resolved_to_canonical", self.rules(result))
        self.assertEqual(result.escalations, [])

    def test_same_id_under_a_different_label_still_errors(self):
        """Reuse is licensed by the two agreeing, not by the ID being present."""
        result = self.compile_gur(**self.propose("Something Else Entirely"))
        self.assertIn("node_addition_already_canonical", self.rules(result))
        self.assertTrue(any(e["kind"] == "node_registration" for e in result.escalations))
        self.assertTrue(result.blocks_approval)


class TestCitations(CompilerCase):
    def test_page_outside_packet_range_errors(self):
        result = self.compile_gur(candidate_edges=[dict(BASE_EDGE, page=70)])
        self.assertIn("page_outside_packet", self.rules(result))

    def test_missing_citation_errors(self):
        result = self.compile_gur(candidate_edges=[dict(BASE_EDGE, page="", section="")])
        self.assertIn("citation_missing", self.rules(result))

    def test_section_alone_is_a_valid_citation(self):
        result = self.compile_gur(candidate_edges=[dict(BASE_EDGE, page="")])
        self.assertNotIn("citation_missing", self.rules(result))


class TestDeterminism(CompilerCase):
    def test_row_order_is_independent_of_input_order(self):
        a = dict(BASE_EDGE, ref="A", target_id="class_fighter", target_label="Fighter")
        b = dict(BASE_EDGE, ref="B", target_id="class_paladin", target_label="Paladin")
        forward = self.compile_gur(candidate_edges=[a, b])
        reverse = self.compile_gur(candidate_edges=[b, a])
        self.assertEqual(
            [r["ref"] for r in forward.rows], [r["ref"] for r in reverse.rows]
        )

    def test_serialization_is_byte_stable(self):
        edges = [dict(BASE_EDGE, ref="A"),
                 dict(BASE_EDGE, ref="B", target_id="class_paladin", target_label="Paladin")]
        first = self.compile_gur(candidate_edges=edges)
        second = self.compile_gur(candidate_edges=edges)
        stub = {"ran": False}
        self.assertEqual(edges_csv(first), edges_csv(second))
        self.assertEqual(gup_document(first, stub), gup_document(second, stub))

    def test_csv_carries_exactly_the_production_columns(self):
        result = self.compile_gur(candidate_edges=[dict(BASE_EDGE)])
        header = edges_csv(result).splitlines()[0]
        self.assertEqual(header.split(","), list(COLUMNS))

    def test_every_row_has_eighteen_fields(self):
        result = self.compile_gur(candidate_edges=[dict(BASE_EDGE)])
        for line in edges_csv(result).splitlines()[1:]:
            self.assertEqual(len(next(__import__("csv").reader([line]))), 18)


class TestGrainIntegration(CompilerCase):
    def test_magnitude_in_aspect_is_caught(self):
        result = self.compile_gur(candidate_edges=[dict(BASE_EDGE, aspect="+3 to hit")])
        self.assertIn("grain_numeric_bonus", self.rules(result))


class TestStatusAndReport(CompilerCase):
    def test_blocked_when_escalations_exist(self):
        # An unapproved prefix is still architectural, so it still blocks.
        result = self.compile_gur(
            candidate_nodes=[{"proposed_id": "magic_x_new", "proposed_label": "X New"}]
        )
        self.assertEqual(result.status, "blocked")
        self.assertTrue(result.blocks_approval)

    def test_not_blocked_by_an_ordinary_node_proposal(self):
        result = self.compile_gur(
            candidate_nodes=[{"proposed_id": "rule_x_new", "proposed_label": "X New"}]
        )
        self.assertEqual(result.status, "proposed")
        self.assertFalse(result.blocks_approval)

    def test_report_shape(self):
        result = self.compile_gur(candidate_edges=[dict(BASE_EDGE)])
        report = validation_report(result, {"ran": True, "passed": True})
        for key in ("gup_id", "gur_checksum", "tool", "test_result", "status", "summary",
                    "derivations", "findings", "duplicates", "escalations"):
            self.assertIn(key, report)

    def test_gup_document_declares_provenance(self):
        result = self.compile_gur(candidate_edges=[dict(BASE_EDGE)])
        document = gup_document(result, {"ran": True, "passed": True})
        self.assertEqual(document["provenance"]["gur_id"], BASE_ENVELOPE["id"])
        self.assertTrue(document["provenance"]["gur_checksum"].startswith("sha256:"))

    def test_gup_declares_the_constitution_it_was_compiled_under(self):
        # The GUR here is authored under 1.2 and revalidated, so the patch was
        # never checked against 1.2 rules. Echoing the GUR's version onto the
        # GUP would misreport that to the Reviewer; the input's own version
        # belongs in provenance, where it describes the input.
        from adnd1e_builder.vocab import CONSTITUTION_VERSION

        result = self.compile_gur(candidate_edges=[dict(BASE_EDGE)])
        document = gup_document(result, {"ran": True, "passed": True})
        self.assertEqual(document["constitution_version"], CONSTITUTION_VERSION)
        self.assertEqual(document["provenance"]["gur_constitution_version"], "1.2")


class TestAuthorizedIdentityMigration(CompilerCase):
    """DEC-2026-0004 named a replacement ID for each rejected-prefix node.

    Pointing an edge at one of those replacements is not the label merge
    invariant 4 forbids: the mapping is the Architect's, and the label match is
    only corroboration. The node still does not exist, so the row must be held
    pending rather than shipped into the integrable CSV.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Whichever mapping is still pending. The Integrator retires these one
        # bundle at a time, so naming a particular pair makes the test expire
        # silently the moment that pair lands.
        cls.LEGACY, cls.TARGET = _bootstrap.unregistered_migration_pair(
            cls.governance, cls.registry
        )
        cls.MIGRATED = dict(
            BASE_EDGE,
            ref="M1",
            edge_type="DERIVED_FROM",
            source_id=cls.TARGET,
            source_label=cls.registry.nodes[cls.LEGACY].label,
            target_id="abil_strength",
            target_label="Strength",
            aspect="fixture migration subject",
            condition="",
        )

    def test_migration_target_is_not_an_identity_error(self):
        result = self.compile_gur(candidate_edges=[dict(self.MIGRATED)])
        self.assertNotIn("identity_ambiguous", self.rules(result))
        self.assertIn("endpoint_authorized_migration_target", self.rules(result))

    def test_row_is_held_pending_not_integrable(self):
        result = self.compile_gur(candidate_edges=[dict(self.MIGRATED)])
        self.assertIn("M1", result.rows_pending)
        self.assertEqual([f.detail for f in result.errors], [])

    def test_the_new_node_travels_with_the_patch(self):
        result = self.compile_gur(candidate_edges=[dict(self.MIGRATED)])
        addition = next(
            n for n in result.node_additions if n["proposed_id"] == self.TARGET
        )
        self.assertEqual(addition["replaces_canonical_id"], self.LEGACY)
        self.assertEqual(addition["authority"], "DEC-2026-0004")
        self.assertEqual(addition["disposition"], "authorized_migration")
        self.assertFalse(addition["architect_required"])
        self.assertIn("M1", addition["edges_depending_on_it"])

    def test_two_edges_share_one_node_addition(self):
        second = dict(self.MIGRATED, ref="M2", edge_type="GATES",
                      source_id="class_fighter", source_label="Fighter",
                      target_id=self.TARGET,
                      target_label=self.registry.nodes[self.LEGACY].label,
                      aspect="second fixture migration subject")
        result = self.compile_gur(candidate_edges=[dict(self.MIGRATED), second])
        additions = [n for n in result.node_additions
                     if n["proposed_id"] == self.TARGET]
        self.assertEqual(len(additions), 1)
        self.assertEqual(sorted(additions[0]["edges_depending_on_it"]), ["M1", "M2"])

    def test_an_unmapped_label_match_is_still_an_error(self):
        # The guard is the decision, not the label. An ID the Architect never
        # named stays an identity escalation however well its label matches.
        invented = dict(self.MIGRATED, ref="M3", source_id="abil_strength_mighty",
                        source_label=self.registry.nodes[self.LEGACY].label)
        result = self.compile_gur(candidate_edges=[invented])
        self.assertIn("identity_ambiguous", self.rules(result))
        self.assertNotIn("endpoint_authorized_migration_target", self.rules(result))



class RetiredEndpointRepointCase(CompilerCase):
    """An immutable GUR naming an ID that a later integration retired.

    This is the shape that stopped GUR-PKT-UA-014-016-cavalier-r02 dead. Its
    M048 names `str_exceptional`, and INT-20260818-001 retired that into
    `abil_str_exceptional` under DEC-2026-0038 between the GUR being published
    and the GUP being compiled. The Analyst could not have written the survivor:
    when the GUR was authored the survivor was in no registry, and constitution
    3.2 requires reusing an existing ID over minting a variant.

    The compiler repoints the row and says so on the row. It does not rewrite the
    GUR, which is immutable and correct for the day it was written.
    """

    RETIRED = "str_exceptional"
    SURVIVOR = "abil_str_exceptional"

    def registry_with_retirement(self, *, survivor_registered=True, record=True):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "registries").mkdir(parents=True)
        (root / "manifests").mkdir(parents=True)
        rows = ["id,label,kind,degree,roles", "abil_strength,Strength,abil,68,"]
        if survivor_registered:
            rows.append(f"{self.SURVIVOR},Exceptional Strength,abil,9,")
        (root / "registries" / "nodes.csv").write_text(
            "\n".join(rows) + "\n", encoding="utf-8"
        )
        if record:
            (root / "manifests" / "INT-19700101-001.json").write_text(
                json.dumps(
                    {
                        "integration_id": "INT-19700101-001",
                        "registry_changes": {
                            "nodes_retired": [
                                {
                                    "id": self.RETIRED,
                                    "label": "Exceptional Strength",
                                    "replaced_by": self.SURVIVOR,
                                    "authority": "DEC-2026-9999",
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )
        return NodeRegistry.load(root / "registries" / "nodes.csv")

    def compile_with(self, registry, edge):
        compiler = Compiler(registry, self.canonical, None, self.governance)
        document = dict(BASE_ENVELOPE, candidate_edges=[edge])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gur.yaml"
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            return compiler.compile(path)

    def edge(self):
        return dict(
            BASE_EDGE,
            ref="M048",
            source_id="abil_strength",
            source_label="Strength",
            edge_type="GATES",
            target_id=self.RETIRED,
            target_label="Exceptional Strength",
            aspect="strength grade",
        )

    def test_the_row_is_repointed_to_the_survivor(self):
        result = self.compile_with(self.registry_with_retirement(), self.edge())
        self.assertEqual([f.detail for f in result.errors], [])
        self.assertEqual(len(result.rows), 1)
        self.assertEqual(result.rows[0]["target_id"], self.SURVIVOR)

    def test_the_label_follows_the_surviving_identity(self):
        result = self.compile_with(self.registry_with_retirement(), self.edge())
        self.assertEqual(result.rows[0]["target_label"], "Exceptional Strength")

    def test_the_substitution_is_reported_on_the_row(self):
        """A silent repoint would be an identity change a Reviewer never sees."""
        result = self.compile_with(self.registry_with_retirement(), self.edge())
        findings = [
            f for f in result.findings
            if f.rule == "endpoint_repointed_to_merge_survivor"
        ]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].ref, "M048")
        self.assertIn(self.RETIRED, findings[0].detail)
        self.assertIn(self.SURVIVOR, findings[0].detail)
        self.assertIn("DEC-2026-9999", findings[0].detail)
        self.assertIn("INT-19700101-001", findings[0].detail)

    def test_it_does_not_escalate_an_answered_question(self):
        """ESCALATION_CONTRACT: a known canonical ID is not an escalation."""
        result = self.compile_with(self.registry_with_retirement(), self.edge())
        self.assertNotIn("identity_ambiguous", self.rules(result))
        self.assertEqual(result.escalations, [])

    def test_without_the_record_the_builder_still_refuses_the_label_match(self):
        """The guard this rests beside must stay exactly as strict.

        Same registry, same label, no integration record: the only thing linking
        the two IDs is now the label, and invariant 4 forbids merging on that.
        """
        registry = self.registry_with_retirement(record=False)
        result = self.compile_with(registry, self.edge())
        self.assertIn("identity_ambiguous", self.rules(result))
        self.assertTrue(result.errors)

    def test_a_survivor_absent_from_the_registry_does_not_repoint(self):
        """Repointing at an unregistered ID would breach invariant 1."""
        registry = self.registry_with_retirement(survivor_registered=False)
        result = self.compile_with(registry, self.edge())
        self.assertNotIn("endpoint_repointed_to_merge_survivor", self.rules(result))
        self.assertTrue(result.errors)

    def test_a_live_endpoint_is_untouched(self):
        edge = dict(self.edge(), ref="T9", target_id="abil_strength",
                    target_label="Strength", source_id=self.SURVIVOR,
                    source_label="Exceptional Strength")
        result = self.compile_with(self.registry_with_retirement(), edge)
        self.assertNotIn("endpoint_repointed_to_merge_survivor", self.rules(result))
        self.assertEqual([f.detail for f in result.errors], [])


class LiveCavalierRepointCase(unittest.TestCase):
    """The published packet this behaviour was built for."""

    GUP = (
        REPO_ROOT / "books" / "adnd1e" / "ua" / "artifacts" / "gup"
        / "GUP-PKT-UA-014-016-cavalier-r01.yaml"
    )
    REPORT = (
        REPO_ROOT / "build" / "reports" / "GUP-PKT-UA-014-016-cavalier-r01.validation.json"
    )

    def report(self):
        if not self.REPORT.is_file():  # pragma: no cover - packet may be superseded
            self.skipTest("the cavalier GUP has not been compiled")
        return json.loads(self.REPORT.read_text(encoding="utf-8"))

    def test_m048_was_repointed_rather_than_escalated(self):
        report = self.report()
        repoints = [
            f for f in report["findings"]
            if f["rule"] == "endpoint_repointed_to_merge_survivor"
        ]
        self.assertEqual([f["ref"] for f in repoints], ["M048"])
        self.assertIn("abil_str_exceptional", repoints[0]["detail"])

    def test_the_packet_compiled_without_an_identity_escalation(self):
        report = self.report()
        self.assertEqual(report["summary"]["errors"], 0)
        self.assertEqual(report["summary"]["escalations"], 0)
        self.assertEqual(report["summary"]["edges_rejected"], 0)

    def test_no_emitted_row_names_a_retired_identity(self):
        import csv

        if not self.GUP.is_file():  # pragma: no cover
            self.skipTest("the cavalier GUP has not been compiled")
        registry = NodeRegistry.load(REGISTRY_PATH)
        retired = set(registry.retirements)
        if not retired:
            self.skipTest("no integration has retired a node yet")
        offenders = []
        for suffix in ("edges", "pending", "blocked"):
            path = self.GUP.with_suffix("").with_suffix(f".{suffix}.csv")
            path = self.GUP.parent / f"{self.GUP.stem}.{suffix}.csv"
            if not path.is_file():
                continue
            with path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    for field in ("source_id", "target_id"):
                        if row.get(field) in retired:
                            offenders.append((path.name, row.get("ref"), row.get(field)))
        self.assertEqual(offenders, [])



class ReviewOwnedDefectRoutingCase(CompilerCase):
    """A defect that came from the Review goes back to the Reviewer.

    The blocked-handoff branch routed every validation error to the Analyst with
    the GUR as the blocker. That is right for a source-derived defect -- an
    assertion the packet does not support is repaired by a new GUR. It is wrong
    for a defect the Review itself introduced: no GUR revision can supply a
    disposition a Review omitted, or respell one the Builder does not recognise.

    Sending it to the Analyst is the same failure this repository has hit before
    at a larger scale: routing a defect to a role that is not permitted to fix
    it, so the work stalls with the queue looking busy. The illusionist packet
    hit it live -- REV-...-r05-r04 dispositioned six rows
    `approved_but_excluded_from_bundle`, which is not one of the four
    dispositions ARTIFACT_LIFECYCLE section 4 defines, and the resulting GUP was
    handed to the Analyst blocked on its GUR.
    """

    def review(self, tmp: Path, rows: dict) -> Path:
        path = tmp / "review.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "id": "REV-GUP-PKT-PHB-999-999-fixture-r01-r01",
                    "packet_id": BASE_ENVELOPE["packet_id"],
                    "reviewed_gup": {"id": "GUP-PKT-PHB-999-999-fixture-r01"},
                    "overall_disposition": "revision_required",
                    "row_decisions": [
                        {"ref": ref, "disposition": disposition}
                        for ref, disposition in rows.items()
                    ],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return path

    def compile_with_review(self, rows, edges):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            gur = tmp / "gur.yaml"
            gur.write_text(
                yaml.safe_dump(dict(BASE_ENVELOPE, candidate_edges=edges), sort_keys=False),
                encoding="utf-8",
            )
            from adnd1e_builder.review import ReviewDirectives

            directives = ReviewDirectives.load(self.review(tmp, rows))
            return self.compiler.compile(gur, directives=directives)

    def edges(self):
        return [
            dict(BASE_EDGE, ref="T1"),
            dict(
                BASE_EDGE,
                ref="T2",
                target_id="save_poison",
                target_label="Saving Throw vs Poison",
                aspect="save bonus",
            ),
        ]

    def test_an_unknown_disposition_routes_to_the_reviewer(self):
        result = self.compile_with_review(
            {"T1": "approved", "T2": "approved_but_excluded_from_bundle"}, self.edges()
        )
        handoff = result.handoff
        self.assertEqual(handoff["next_role"], "reviewer")
        self.assertEqual(handoff["readiness"], "blocked")

    def test_the_blocker_is_the_review_not_the_gur(self):
        """Naming the GUR would ask the Analyst for a revision that cannot help."""
        result = self.compile_with_review(
            {"T1": "approved", "T2": "approved_but_excluded_from_bundle"}, self.edges()
        )
        handoff = result.handoff
        self.assertEqual(
            handoff["blocking_ids"], ["REV-GUP-PKT-PHB-999-999-fixture-r01-r01"]
        )
        self.assertNotIn(BASE_ENVELOPE["id"], handoff["blocking_ids"])

    def test_the_reason_names_the_review_owned_rule(self):
        result = self.compile_with_review(
            {"T1": "approved", "T2": "approved_but_excluded_from_bundle"}, self.edges()
        )
        reason = result.handoff["reason"]
        self.assertIn("review_disposition_unknown", reason)
        self.assertIn("Review-owned", reason)

    def test_an_undecided_row_also_routes_to_the_reviewer(self):
        """Review is per row; an omitted disposition is the Review's omission."""
        result = self.compile_with_review({"T1": "approved"}, self.edges())
        handoff = result.handoff
        self.assertEqual(handoff["next_role"], "reviewer")
        self.assertIn("review_row_undecided", handoff["reason"])

    def test_a_source_defect_still_routes_to_the_analyst(self):
        """The default this narrows must keep working for what it was written for."""
        broken = dict(BASE_EDGE, ref="T3", target_id="no_such_canonical_node",
                      target_label="Nothing At All")
        result = self.compile_with_review(
            {"T1": "approved", "T3": "approved"}, [dict(BASE_EDGE, ref="T1"), broken]
        )
        handoff = result.handoff
        self.assertEqual(handoff["next_role"], "analyst")
        self.assertEqual(handoff["blocking_ids"], [BASE_ENVELOPE["id"]])

    def test_a_mixed_batch_stays_with_the_analyst(self):
        """A source defect is present, so the conservative default holds."""
        broken = dict(BASE_EDGE, ref="T3", target_id="no_such_canonical_node",
                      target_label="Nothing At All")
        result = self.compile_with_review(
            {"T1": "approved", "T3": "not_a_real_disposition"},
            [dict(BASE_EDGE, ref="T1"), broken],
        )
        self.assertEqual(result.handoff["next_role"], "analyst")

    def test_a_clean_review_still_reaches_the_reviewer_ready(self):
        result = self.compile_with_review(
            {"T1": "approved", "T2": "approved"}, self.edges()
        )
        handoff = result.handoff
        self.assertEqual(handoff["next_role"], "reviewer")
        self.assertEqual(handoff["readiness"], "ready")
        self.assertEqual(handoff["blocking_ids"], [])



class RejectedRowLeavesNodeDependentsCase(CompilerCase):
    """A node proposal must not keep advertising rows the Review rejected.

    `edges_depending_on_it` is how a proposal argues it earns registration, and a
    Reviewer reads it to decide. When a Review rejects a row but keeps the node
    because other rows still need it, leaving the rejected ref in that list makes
    the proposal claim support the Reviewer has just withdrawn.

    The existing rejected-node handling computed the surviving rows already, but
    returned early unless a *node* was rejected, so a row-only rejection never
    reached it. The cavalier packet is the live case: the Review rejected M067
    and kept `rule_chivalric_code`, whose list still named M067.
    """

    NODE = "rule_fixture_code"

    def gur(self, refs=("T1", "T2")):
        edges = []
        for index, ref in enumerate(refs):
            edges.append(dict(
                BASE_EDGE, ref=ref, source_id=self.NODE, source_label="Fixture Code",
                edge_type="GATES", target_id="class_fighter", target_label="Fighter",
                aspect=f"facet {index}",
            ))
        return dict(
            BASE_ENVELOPE,
            candidate_edges=edges,
            candidate_nodes=[{
                "proposed_id": self.NODE,
                "proposed_label": "Fixture Code",
                "kind": "rule",
                "why_needed": "the fixture needs it",
                "edges_depending_on_it": list(refs),
            }],
        )

    def compile_with(self, rows, refs=("T1", "T2")):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            gur = tmp / "gur.yaml"
            gur.write_text(yaml.safe_dump(self.gur(refs), sort_keys=False), encoding="utf-8")
            review = tmp / "review.yaml"
            review.write_text(
                yaml.safe_dump({
                    "id": "REV-GUP-PKT-PHB-999-999-fixture-r01-r01",
                    "packet_id": BASE_ENVELOPE["packet_id"],
                    "reviewed_gup": {"id": "GUP-PKT-PHB-999-999-fixture-r01"},
                    "overall_disposition": "revision_required",
                    "row_decisions": [
                        {"ref": ref, "disposition": disposition}
                        for ref, disposition in rows.items()
                    ],
                    "node_decisions": [
                        {"proposed_id": self.NODE, "disposition": "approved"}
                    ],
                }, sort_keys=False),
                encoding="utf-8",
            )
            from adnd1e_builder.review import ReviewDirectives

            return self.compiler.compile(
                gur, directives=ReviewDirectives.load(review)
            )

    def proposal(self, result):
        return next(
            n for n in result.node_additions if n["proposed_id"] == self.NODE
        )

    def test_a_rejected_row_leaves_the_dependent_list(self):
        result = self.compile_with({"T1": "approved", "T2": "rejected"})
        self.assertEqual(self.proposal(result)["edges_depending_on_it"], ["T1"])

    def test_the_surviving_rows_are_kept(self):
        result = self.compile_with(
            {"T1": "approved", "T2": "rejected", "T3": "approved"},
            refs=("T1", "T2", "T3"),
        )
        self.assertEqual(self.proposal(result)["edges_depending_on_it"], ["T1", "T3"])

    def test_the_removal_is_reported(self):
        """A silent edit to the proposal's own argument would be invisible."""
        result = self.compile_with({"T1": "approved", "T2": "rejected"})
        findings = [f for f in result.findings if f.rule == "node_dependent_row_rejected"]
        self.assertEqual(len(findings), 1)
        self.assertIn("T2", findings[0].detail)
        self.assertIn(self.NODE, findings[0].detail)

    def test_nothing_changes_when_no_row_is_rejected(self):
        result = self.compile_with({"T1": "approved", "T2": "approved"})
        self.assertEqual(self.proposal(result)["edges_depending_on_it"], ["T1", "T2"])
        self.assertEqual(
            [f for f in result.findings if f.rule == "node_dependent_row_rejected"], []
        )

    def test_the_node_survives_while_any_row_needs_it(self):
        result = self.compile_with({"T1": "approved", "T2": "rejected"})
        self.assertIn(
            self.NODE, {n["proposed_id"] for n in result.node_additions}
        )


class LiveCavalierDependentsCase(unittest.TestCase):
    """The published packet the prune was written for."""

    GUP = (
        REPO_ROOT / "books" / "adnd1e" / "ua" / "artifacts" / "gup"
        / "GUP-PKT-UA-014-016-cavalier-r03.yaml"
    )

    def proposal(self):
        if not self.GUP.is_file():  # pragma: no cover - superseded or not yet built
            self.skipTest("the cavalier r03 GUP is not present")
        document = yaml.safe_load(self.GUP.read_text(encoding="utf-8"))
        for node in (document.get("node_changes") or {}).get("additions_proposed") or []:
            if node.get("proposed_id") == "rule_chivalric_code":
                return node
        self.fail("rule_chivalric_code is not proposed by this GUP")

    def test_the_rejected_row_is_gone_from_the_dependent_list(self):
        self.assertNotIn("M067", self.proposal()["edges_depending_on_it"])

    def test_the_rows_that_still_need_it_remain(self):
        depending = self.proposal()["edges_depending_on_it"]
        for ref in ("M003", "M009", "M065", "M066", "M068"):
            self.assertIn(ref, depending)



class DueMigrationEndpointCase(CompilerCase):
    """DEC-2026-0050: a due legacy endpoint is refused, not warned about.

    `comeliness`, `fatigue` and `training` had their replacements decided long
    ago by DEC-2026-0004 and DEC-2026-0014, and the debt they belong to is meant
    to shrink. Until now the compiler warned and carried on, and that warning was
    read by four gates in a row without stopping anything: the cavalier GUR
    disclosed the tension, this compiler warned on each row, the Reviewer
    approved them, the Integrator applied them, and four rows joined a set an
    approved Decision had pinned at a fixed size. The first thing to notice was a
    test failure after integration.

    So for this exactly-named set the row is refused. It is never rewritten to
    the successor: repointing a source assertion is the reviewed migration's job,
    and doing it here would be the Builder deciding identity on its own.
    """

    def edge_with(self, node_id, *, role="target"):
        edge = dict(BASE_EDGE, ref="M041")
        if role == "target":
            edge.update(target_id=node_id, target_label="Training")
        else:
            edge.update(source_id=node_id, source_label="Training")
        return edge

    def rules_for(self, node_id, **kwargs):
        result = self.compile_gur(candidate_edges=[self.edge_with(node_id, **kwargs)])
        return result, self.rules(result)

    def test_each_due_id_is_refused(self):
        for node_id in ("comeliness", "fatigue", "training"):
            with self.subTest(node_id=node_id):
                result, rules = self.rules_for(node_id)
                self.assertIn("endpoint_migration_due", rules)
                self.assertTrue(result.errors)

    def test_it_is_refused_on_either_endpoint(self):
        for role in ("source", "target"):
            with self.subTest(role=role):
                _, rules = self.rules_for("training", role=role)
                self.assertIn("endpoint_migration_due", rules)

    def test_the_row_is_not_emitted(self):
        result, _ = self.rules_for("training")
        self.assertEqual(result.rows, [])

    def test_the_row_is_not_rewritten_to_the_successor(self):
        """Silently repointing would be the Builder deciding identity."""
        result, _ = self.rules_for("training")
        emitted = {
            node
            for row in result.rows
            for node in (row.get("source_id"), row.get("target_id"))
        }
        self.assertNotIn("rule_training", emitted)

    def test_the_finding_names_the_decision_and_the_successor(self):
        result, _ = self.rules_for("training")
        detail = next(
            f.detail for f in result.findings if f.rule == "endpoint_migration_due"
        )
        self.assertIn("DEC-2026-0050", detail)
        self.assertIn("rule_training", detail)

    def test_the_old_warning_no_longer_fires_for_a_due_id(self):
        """One row must not carry both a refusal and a carry-on warning."""
        _, rules = self.rules_for("training")
        self.assertNotIn("endpoint_pending_migration", rules)

    def test_an_ordinary_endpoint_is_unaffected(self):
        result = self.compile_gur(candidate_edges=[dict(BASE_EDGE)])
        self.assertNotIn("endpoint_migration_due", self.rules(result))
        self.assertEqual([f.detail for f in result.errors], [])

    def test_the_successor_id_itself_is_not_refused(self):
        """Once the migration lands, the surviving ID must compile normally."""
        _, rules = self.rules_for("rule_training")
        self.assertNotIn("endpoint_migration_due", rules)

    def test_the_due_set_is_exactly_the_three_named(self):
        """A closed set: other pending migrations keep their warning."""
        from adnd1e_builder.governance import Governance

        governance = Governance.load(REPO_ROOT / "rulesets" / "adnd1e")
        self.assertEqual(
            set(governance.migration_due_ids), {"comeliness", "fatigue", "training"}
        )
        for retired, (successor, decision_id) in governance.migration_due_ids.items():
            self.assertEqual(decision_id, "DEC-2026-0050", retired)
        self.assertEqual(
            {r: s for r, (s, _) in governance.migration_due_ids.items()},
            {
                "comeliness": "abil_comeliness",
                "fatigue": "rule_exhaustion",
                "training": "rule_training",
            },
        )


class TestEnvelope(CompilerCase):
    def test_wrong_ruleset_is_rejected(self):
        result = self.compile_gur(ruleset_id="adnd2e")
        self.assertIn("gur_wrong_ruleset", self.rules(result))

    def test_constitution_version_mismatch_is_rejected(self):
        result = self.compile_gur(constitution_version="1.1")
        self.assertIn("constitution_version_mismatch", self.rules(result))



class ReviewerRejectedNodeCase(CompilerCase):
    """A node proposal the Review rejected must leave the patch.

    It used to survive carrying only a recorded disposition, so the next
    revision still asked the Integrator to register it. With its only edge
    rejected too that registers a node at degree zero -- the defect the
    Integrator refused the alignment-graph bundle for, and the exact shape of
    REV-GUP-PKT-PHB-120-120-planes-of-existence-r05-r01 rejecting
    `rule_prime_material_plane` because its only edge was rejected.
    """

    NODE = "rule_fixture_rejected_node"

    def compile_with_review(self, node_disposition, row_disposition):
        from adnd1e_builder.review import ReviewDirectives

        document = dict(BASE_ENVELOPE)
        document.update(
            candidate_nodes=[{
                "proposed_id": self.NODE, "proposed_label": "Fixture Rejected Node",
                "why_needed": "The packet names it.", "edges_depending_on_it": ["T1"],
            }],
            candidate_edges=[dict(BASE_EDGE, ref="T1", target_id=self.NODE,
                                  target_label="Fixture Rejected Node")],
        )
        review = {
            "id": "REV-GUP-PKT-TEST-r01-r01",
            "packet_id": document["packet_id"],
            "reviewed_gup": {"id": "GUP-PKT-TEST-r01"},
            "overall_disposition": "revision_required",
            "row_decisions": [
                {"ref": "T1", "disposition": row_disposition, "rationale": "fixture"}
            ],
            "node_registry_decisions": [
                {"proposed_id": self.NODE, "disposition": node_disposition}
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            gur = Path(tmp) / "gur.yaml"
            gur.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            rev = Path(tmp) / "REV.yaml"
            rev.write_text(yaml.safe_dump(review, sort_keys=False), encoding="utf-8")
            return self.compiler.compile(
                gur, directives=ReviewDirectives.load(rev), revision=2,
                supersedes="GUP-PKT-PHB-999-999-fixture-r01",
            )

    def proposed(self, result):
        return [n["proposed_id"] for n in result.node_additions]

    def by_severity(self, result, severity):
        return [f.rule for f in result.findings if f.severity == severity]

    def test_a_rejected_node_with_no_surviving_row_is_dropped(self):
        result = self.compile_with_review("rejected", "rejected")
        self.assertNotIn(self.NODE, self.proposed(result))
        self.assertIn("reviewer_rejected_node_dropped", self.by_severity(result, "info"))

    def test_dropping_it_is_not_an_error(self):
        """The Reviewer asked for this; it must not block the revision."""
        result = self.compile_with_review("rejected", "rejected")
        self.assertNotIn(
            "reviewer_rejected_node_still_needed", self.by_severity(result, "error")
        )

    def test_a_rejected_node_a_surviving_row_needs_is_an_error(self):
        """Dropping it would strand the row against an unregistered endpoint."""
        result = self.compile_with_review("rejected", "approved")
        self.assertIn(
            "reviewer_rejected_node_still_needed", self.by_severity(result, "error")
        )
        self.assertIn(self.NODE, self.proposed(result))

    def test_the_error_names_the_row_that_still_depends_on_it(self):
        result = self.compile_with_review("rejected", "approved")
        detail = next(
            f.detail for f in result.findings
            if f.rule == "reviewer_rejected_node_still_needed"
        )
        self.assertIn("T1", detail)

    def test_an_approved_node_survives(self):
        result = self.compile_with_review("approved", "approved")
        self.assertIn(self.NODE, self.proposed(result))

    def test_the_guard_stays_quiet_when_nothing_is_rejected(self):
        result = self.compile_with_review("approved", "approved")
        self.assertNotIn(
            "reviewer_rejected_node_dropped", self.by_severity(result, "info")
        )


class BlockedRowsAreSeparableCase(CompilerCase):
    """Two things hold a row back, and they are not interchangeable.

    A row waiting on a node *this* patch proposes travels with the patch: the
    batch that registers the node integrates the row. A row waiting on a node
    another packet mints cannot integrate at all until that packet does.

    INT-20260814-003 refused the psionics bundle over nine endpoints of the
    second kind. They were correctly held and correctly declared under
    `cross_packet_dependencies`, but all 203 pending rows went into one
    undifferentiated CSV, so nothing downstream could separate the 190 rows the
    batch could satisfy from the 13 it could not.
    """

    OWN = "rule_fixture_own_proposal"
    OTHER = "rule_fixture_other_packet"

    def compile_mixed(self):
        return self.compile_gur(
            candidate_nodes=[{
                "proposed_id": self.OWN, "proposed_label": "Fixture Own Proposal",
                "why_needed": "The packet names it.", "edges_depending_on_it": ["T1"],
            }],
            cross_packet_candidate_targets=[{
                "id": self.OTHER, "label": "Fixture Other Packet",
                "origin": "candidate minted by GUR-PKT-PHB-998-998-other-r01, not yet canonical",
                "used_by": ["T2"],
                "builder_instruction": "Do not mint a second identity.",
            }],
            candidate_edges=[
                dict(BASE_EDGE, ref="T1", target_id=self.OWN,
                     target_label="Fixture Own Proposal"),
                dict(BASE_EDGE, ref="T2", target_id=self.OTHER,
                     target_label="Fixture Other Packet"),
            ],
        )

    def test_both_kinds_are_held_out_of_the_integration_input(self):
        """The invariant 1 guarantee is unchanged; only the reporting splits."""
        result = self.compile_mixed()
        self.assertEqual(result.additions, [])
        self.assertEqual(len(result.pending_additions), 2)

    def test_the_two_kinds_are_separated(self):
        result = self.compile_mixed()
        self.assertEqual(
            [r["ref"] for r in result.batch_satisfiable_additions], ["T1"]
        )
        self.assertEqual([r["ref"] for r in result.blocked_additions], ["T2"])

    def test_the_split_partitions_the_pending_set(self):
        result = self.compile_mixed()
        satisfiable = {r["ref"] for r in result.batch_satisfiable_additions}
        blocked = {r["ref"] for r in result.blocked_additions}
        self.assertEqual(satisfiable & blocked, set())
        self.assertEqual(
            satisfiable | blocked, {r["ref"] for r in result.pending_additions}
        )

    def test_a_patch_waiting_only_on_itself_has_nothing_blocked(self):
        result = self.compile_gur(
            candidate_nodes=[{
                "proposed_id": self.OWN, "proposed_label": "Fixture Own Proposal",
                "why_needed": "The packet names it.", "edges_depending_on_it": ["T1"],
            }],
            candidate_edges=[dict(BASE_EDGE, ref="T1", target_id=self.OWN,
                                  target_label="Fixture Own Proposal")],
        )
        self.assertEqual(result.blocked_additions, [])
        self.assertEqual(len(result.batch_satisfiable_additions), 1)

    def test_the_two_csvs_carry_the_two_kinds(self):
        from adnd1e_builder.emit import blocked_csv, pending_csv

        import csv as _csv

        result = self.compile_mixed()
        pending = list(_csv.DictReader(pending_csv(result).splitlines()))
        blocked = list(_csv.DictReader(blocked_csv(result).splitlines()))
        self.assertEqual([r["target_id"] for r in pending], [self.OWN])
        self.assertEqual([r["target_id"] for r in blocked], [self.OTHER])

    def test_the_blocked_file_exists_only_when_something_is_blocked(self):
        """Its presence is the signal that this patch cannot integrate alone."""
        from adnd1e_builder.emit import write_all

        with tempfile.TemporaryDirectory() as tmp:
            gup_dir, reports = Path(tmp) / "gup", Path(tmp) / "reports"
            mixed = self.compile_mixed()
            written = write_all(mixed, gup_dir, reports, {"ran": False})
            self.assertEqual(
                [p.name for p in written if p.name.endswith(".blocked.csv")],
                [f"{mixed.gup_id}.blocked.csv"],
            )

            second, second_reports = Path(tmp) / "gup2", Path(tmp) / "reports2"
            clean = self.compile_gur(candidate_edges=[dict(BASE_EDGE)])
            written = write_all(clean, second, second_reports, {"ran": False})
            self.assertEqual(
                [p.name for p in written if p.name.endswith(".blocked.csv")], []
            )

    def test_the_gup_names_the_two_buckets_apart(self):
        from adnd1e_builder.emit import gup_document

        document = gup_document(self.compile_mixed(), {"ran": False})
        changes = document["edge_changes"]
        self.assertEqual([r["ref"] for r in changes["pending_additions"]], ["T1"])
        self.assertEqual([r["ref"] for r in changes["blocked_additions"]], ["T2"])

    def test_the_validation_summary_counts_them_apart(self):
        from adnd1e_builder.emit import validation_report

        summary = validation_report(self.compile_mixed(), {"ran": False})["summary"]
        self.assertEqual(summary["edge_pending_additions"], 1)
        self.assertEqual(summary["edge_blocked_additions"], 1)


class EndpointSatisfiabilityCase(CompilerCase):
    """An endpoint reaches integration only if something in the batch mints it.

    There are exactly three fates for an unregistered endpoint, and each has to
    be distinguishable from the others by looking at what was written to disk:
    this packet proposes it (held, travels with the batch), another packet
    mints it and the GUR says so (held, blocked until that packet lands), or
    nothing accounts for it at all (refused outright).

    Both bundle rejections in this lineage came from the middle case being
    indistinguishable from the first once the CSVs were merged.
    """

    OWN = "rule_fixture_own_proposal"
    FOREIGN = "spell_fixture_another_packet_mints_it"
    UNKNOWN = "spell_fixture_nobody_accounts_for_it"

    def compile_mixed(self, declare=True):
        overrides = {
            "candidate_nodes": [{
                "proposed_id": self.OWN, "proposed_label": "Fixture Own Proposal",
                "why_needed": "The packet names it.", "edges_depending_on_it": ["T1"],
            }],
            "candidate_edges": [
                dict(BASE_EDGE, ref="T1", target_id=self.OWN,
                     target_label="Fixture Own Proposal"),
                dict(BASE_EDGE, ref="T2", target_id=self.FOREIGN,
                     target_label="Fixture Foreign Spell"),
            ],
        }
        if declare:
            overrides["cross_packet_candidate_targets"] = [{
                "id": self.FOREIGN, "label": "Fixture Foreign Spell",
                "origin": "candidate minted by GUR-PKT-PHB-998-998-other-r01, not yet canonical",
                "used_by": ["T2"],
                "builder_instruction": "Do not mint a second identity.",
            }]
        return self.compile_gur(**overrides)

    def test_the_three_fates_are_separable(self):
        result = self.compile_mixed()
        self.assertEqual(
            [r["ref"] for r in result.batch_satisfiable_additions], ["T1"]
        )
        self.assertEqual([r["ref"] for r in result.blocked_additions], ["T2"])
        self.assertEqual(result.unsatisfiable_endpoints, {self.FOREIGN})

    def test_an_endpoint_nobody_accounts_for_is_refused_not_held(self):
        """Not a bucket question: an undeclared unknown endpoint is an error."""
        result = self.compile_gur(
            candidate_edges=[
                dict(BASE_EDGE, ref="T3", target_id=self.UNKNOWN,
                     target_label="Fixture Unknown"),
            ],
        )
        self.assertIn("endpoint_unresolved", self.rules(result))
        self.assertEqual([r["ref"] for r in result.rows], [])

    def test_every_shipped_row_resolves_against_the_batch(self):
        """The exact property both Integrator rejections tested and found false."""
        result = self.compile_mixed()
        known = result.canonical_node_ids | {
            n["proposed_id"] for n in result.node_additions
        }
        for row in result.additions + result.batch_satisfiable_additions:
            self.assertIn(row["source_id"], known, row["ref"])
            self.assertIn(row["target_id"], known, row["ref"])

    def test_satisfiability_is_read_from_the_corpus_not_the_declaration(self):
        """The declaration names the origin; it does not create the blockage.

        Keying the split on `cross_packet_dependencies` made the bucket a
        restatement of what the GUR said rather than of what is true, so a
        declaration that was absent, misspelled, or later contradicted would
        have silently reclassified the row as safe to integrate.
        """
        result = self.compile_mixed()
        result.cross_packet_dependencies = []
        self.assertEqual([r["ref"] for r in result.blocked_additions], ["T2"])

    def test_a_registered_endpoint_is_never_blocked(self):
        result = self.compile_gur(candidate_edges=[dict(BASE_EDGE)])
        self.assertEqual(result.blocked_additions, [])
        self.assertEqual(result.unsatisfiable_endpoints, set())


class LivePsionicsBlockedCase(CompilerCase):
    """The rejection, reproduced against the published GUR."""

    GUR = (
        REPO_ROOT / "books" / "adnd1e" / "phb" / "artifacts" / "gur"
        / "GUR-PKT-PHB-110-117-psionics-r03.yaml"
    )

    #: The nine endpoints INT-20260814-003 named, verbatim.
    REJECTED = (
        "spell_clairaudience", "spell_clairvoyance", "spell_dimension_door",
        "spell_fear", "spell_feather_fall", "spell_geas", "spell_heat_metal",
        "spell_telekinesis", "spell_teleport",
    )

    def result(self):
        if not self.GUR.exists():  # pragma: no cover
            self.skipTest("the psionics GUR is not present")
        return self.compiler.compile(self.GUR)

    def test_every_rejected_endpoint_lands_in_the_blocked_bucket(self):
        result = self.result()
        blocked = {
            node
            for row in result.blocked_additions
            for node in (row["source_id"], row["target_id"])
        }
        for endpoint in self.REJECTED:
            if endpoint in self.registry:  # pragma: no cover - origin has landed
                continue
            self.assertIn(endpoint, blocked, endpoint)

    def test_no_rejected_endpoint_reaches_the_integration_input(self):
        """The guarantee the Integrator checks: additions resolve or are held."""
        result = self.result()
        integrable = {
            node
            for row in result.additions
            for node in (row["source_id"], row["target_id"])
        }
        self.assertEqual(integrable & set(self.REJECTED), set())

    def test_the_blocked_set_is_a_small_remainder_of_the_packet(self):
        """Only a remainder blocks the batch; the bulk of the packet is safe.

        This compared `blocked_additions` against `batch_satisfiable_additions`,
        which was 13 against 190 when the rejection was first reproduced. That
        comparison decays to false as the corpus completes, and not because
        anything regressed: `batch_satisfiable_additions` is pending rows minus
        blocked ones, so every node that lands canonically moves a row out of
        pending and into plain additions. With the psionics dependencies now
        registered, pending holds only the 9 rows blocked on the unpublished
        druid-spells packet, batch_satisfiable is 0, and `9 < 0` fails.

        The claim worth keeping is the one the rejection was about: the blocked
        rows are a small remainder rather than the bulk of the packet. Measuring
        that against the total emitted row set says it directly and stays true
        whether the dependencies have landed or not.
        """
        result = self.result()
        self.assertTrue(result.blocked_additions)
        emitted = (
            len(result.additions)
            + len(result.pending_additions)
            + len(result.updates)
        )
        self.assertGreater(emitted, 0)
        self.assertLess(len(result.blocked_additions), emitted // 4)

    def test_blocked_rows_are_a_subset_of_the_pending_rows(self):
        """Blocked is a narrowing of pending, not a fourth independent bucket.

        `batch_satisfiable_additions` is defined as the difference of the two, so
        if a blocked row ever escaped the pending set that property would report
        a nonsense count rather than fail outright.
        """
        result = self.result()
        pending = {id(row) for row in result.pending_additions}
        for row in result.blocked_additions:
            self.assertIn(
                id(row), pending,
                f"{row['source_id']} -> {row['target_id']} is blocked but not pending",
            )
        self.assertEqual(
            len(result.batch_satisfiable_additions),
            len(result.pending_additions) - len(result.blocked_additions),
        )

if __name__ == "__main__":
    unittest.main()
