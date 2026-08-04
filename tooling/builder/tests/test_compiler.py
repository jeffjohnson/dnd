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
from adnd1e_builder.registry import NodeRegistry
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

    def test_proposing_an_existing_node_is_an_error(self):
        result = self.compile_gur(
            candidate_nodes=[{"proposed_id": "race_dwarf", "proposed_label": "Dwarf"}]
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


class TestEnvelope(CompilerCase):
    def test_wrong_ruleset_is_rejected(self):
        result = self.compile_gur(ruleset_id="adnd2e")
        self.assertIn("gur_wrong_ruleset", self.rules(result))

    def test_constitution_version_mismatch_is_rejected(self):
        result = self.compile_gur(constitution_version="1.1")
        self.assertIn("constitution_version_mismatch", self.rules(result))


if __name__ == "__main__":
    unittest.main()
