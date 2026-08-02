"""Handoff metadata and revision lineage — contracts/WORK_QUEUES.md 1.0."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap
from _bootstrap import REPO_ROOT

from adnd1e_builder.cli import previous_revision
from adnd1e_builder.compiler import Compiler
from adnd1e_builder.duplicates import CanonicalEdges
from adnd1e_builder.emit import gup_document
from adnd1e_builder.governance import Governance
from adnd1e_builder.queues import active_leaf
from adnd1e_builder.registry import NodeRegistry

RULESET_ROOT = REPO_ROOT / "rulesets" / "adnd1e"

VALID_ROLES = {"analyst", "builder", "reviewer", "architect", "integrator", "none"}
VALID_READINESS = {"ready", "blocked", "terminal"}

ENVELOPE = {
    "schema_version": "1.0", "id": "GUR-PKT-PHB-950-951-fixture-r01",
    "status": "proposed", "ruleset_id": "adnd1e", "book_id": "phb",
    "source_id": "phb-legacy-unspecified", "packet_id": "PKT-PHB-950-951-fixture",
    "constitution_version": "1.4", "revision": 1, "page_start": 9, "page_end": 13,
}
EDGE = {
    "ref": "T1", "source_id": "abil_strength", "source_label": "Strength",
    "edge_type": "GATES", "target_id": "class_fighter", "target_label": "Fighter",
    "aspect": "class eligibility", "condition": "", "book": "PHB", "page": 9,
    "section": "STRENGTH TABLE I", "evidence": "explicit_rule", "pass": "page-sweep",
    "status": "core", "general_rule_id": "", "supersession_basis": "", "review_flag": "",
}


class HandoffCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = Compiler(
            NodeRegistry.load(RULESET_ROOT / "registries" / "nodes.csv"),
            CanonicalEdges.load(RULESET_ROOT / "canonical" / "edges_master.csv"),
            None,
            Governance.load(RULESET_ROOT),
        )

    def compile_gur(self, revision=None, supersedes=None, **overrides):
        document = {**ENVELOPE, **overrides}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gur.yaml"
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            return self.compiler.compile(path, revision=revision, supersedes=supersedes)


class TestHandoffBlock(HandoffCase):
    def test_clean_patch_hands_off_to_reviewer(self):
        result = self.compile_gur(candidate_edges=[dict(EDGE)])
        handoff = result.handoff
        self.assertEqual(handoff["next_role"], "reviewer")
        self.assertEqual(handoff["readiness"], "ready")
        self.assertEqual(handoff["blocking_ids"], [])

    def test_escalation_hands_off_to_architect_with_blocking_ids(self):
        result = self.compile_gur(
            candidate_nodes=[{"proposed_id": "magic_new_thing", "proposed_label": "New Thing"}]
        )
        handoff = result.handoff
        self.assertEqual(handoff["next_role"], "architect")
        self.assertEqual(handoff["readiness"], "blocked")
        self.assertTrue(handoff["blocking_ids"])

    def test_validation_errors_hand_back_to_analyst(self):
        result = self.compile_gur(
            candidate_edges=[dict(EDGE, target_id="class_nonexistent",
                                  target_label="Nonexistent")]
        )
        handoff = result.handoff
        self.assertEqual(handoff["next_role"], "analyst")
        self.assertEqual(handoff["readiness"], "blocked")
        self.assertTrue(handoff["blocking_ids"])

    def test_vocabulary_is_respected(self):
        for result in (
            self.compile_gur(candidate_edges=[dict(EDGE)]),
            self.compile_gur(candidate_edges=[dict(EDGE, evidence="nonsense")]),
            self.compile_gur(candidate_nodes=[{"proposed_id": "magic_x", "proposed_label": "X"}]),
        ):
            with self.subTest(status=result.status):
                self.assertIn(result.handoff["next_role"], VALID_ROLES)
                self.assertIn(result.handoff["readiness"], VALID_READINESS)

    def test_blocked_patch_is_never_ready(self):
        result = self.compile_gur(candidate_edges=[dict(EDGE, book="OA")])
        self.assertEqual(result.status, "blocked")
        self.assertNotEqual(result.handoff["readiness"], "ready")


class TestRevisionLineage(HandoffCase):
    def test_revision_one_supersedes_nothing(self):
        result = self.compile_gur(revision=1, candidate_edges=[dict(EDGE)])
        document = gup_document(result, {"ran": False})
        self.assertEqual(document["revision"], 1)
        self.assertIsNone(document["supersedes"])

    def test_later_revision_records_its_predecessor(self):
        result = self.compile_gur(
            revision=5, supersedes="GUP-PKT-PHB-950-951-fixture-r04",
            candidate_edges=[dict(EDGE)],
        )
        document = gup_document(result, {"ran": False})
        self.assertEqual(document["revision"], 5)
        self.assertEqual(document["supersedes"], "GUP-PKT-PHB-950-951-fixture-r04")

    def test_document_carries_the_handoff_block(self):
        result = self.compile_gur(candidate_edges=[dict(EDGE)])
        document = gup_document(result, {"ran": False})
        for key in ("next_role", "readiness", "reason", "blocking_ids"):
            self.assertIn(key, document["handoff"])


class TestPreviousRevisionDetection(unittest.TestCase):
    def _gur(self, tmp: Path, packet_id: str) -> Path:
        path = tmp / "gur.yaml"
        path.write_text(
            yaml.safe_dump({"packet_id": packet_id, "revision": 1}, sort_keys=False),
            encoding="utf-8",
        )
        return path

    def test_none_for_first_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gur = self._gur(root, "PKT-X")
            self.assertIsNone(previous_revision(root, gur, 1))

    def test_finds_the_highest_lower_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gur = self._gur(root, "PKT-X")
            for revision in (2, 3, 4):
                (root / f"GUP-PKT-X-r{revision:02d}.yaml").write_text("{}", encoding="utf-8")
            self.assertEqual(previous_revision(root, gur, 5), "GUP-PKT-X-r04")

    def test_skipped_revision_numbers_do_not_break_the_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gur = self._gur(root, "PKT-X")
            (root / "GUP-PKT-X-r02.yaml").write_text("{}", encoding="utf-8")
            # r03 and r04 were never published; r05 must name r02, not r04.
            self.assertEqual(previous_revision(root, gur, 5), "GUP-PKT-X-r02")

    def test_other_packets_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gur = self._gur(root, "PKT-X")
            (root / "GUP-PKT-Y-r09.yaml").write_text("{}", encoding="utf-8")
            self.assertIsNone(previous_revision(root, gur, 2))


class TestPublishedIntroBundle(unittest.TestCase):
    """The intro packet's active leaf must satisfy the Reviewer-readiness rules."""

    GUP_DIR = REPO_ROOT / "books" / "adnd1e" / "phb" / "artifacts" / "gup"

    def documents(self) -> dict:
        return {
            (d := yaml.safe_load(p.read_text(encoding="utf-8")))["id"]: d
            for p in self.GUP_DIR.glob("GUP-PKT-PHB-007-008-intro-r*.yaml")
        }

    def leaf(self) -> dict:
        documents = self.documents()
        result = active_leaf(documents)
        self.assertTrue(result.ok, f"lineage diagnostics: {result.diagnostics}")
        return documents[result.leaf_id]

    def test_exactly_one_active_leaf(self):
        result = active_leaf(self.documents())
        self.assertEqual(result.leaf_id, "GUP-PKT-PHB-007-008-intro-r05")
        self.assertFalse(
            any(d["severity"] == "error" for d in result.diagnostics),
            "no forked or broken lineage",
        )

    def test_legacy_revisions_are_resolved_by_documented_inference(self):
        """r02-r04 predate WORK_QUEUES and carry no `supersedes`."""
        result = active_leaf(self.documents())
        self.assertTrue(result.legacy_inference)
        self.assertIn(
            "legacy_revision_inference", {d["rule"] for d in result.diagnostics}
        )

    def test_leaf_is_reviewer_ready(self):
        leaf = self.leaf()
        self.assertEqual(leaf["status"], "proposed")
        self.assertTrue(leaf["approval_ready"])
        self.assertEqual(leaf["handoff"]["next_role"], "reviewer")
        self.assertEqual(leaf["handoff"]["readiness"], "ready")

    def test_leaf_is_built_from_the_active_leaf_gur(self):
        gur_dir = REPO_ROOT / "books" / "adnd1e" / "phb" / "artifacts" / "gur"
        superseded = set()
        ids = set()
        for path in gur_dir.glob("GUR-PKT-PHB-007-008-intro-r*.yaml"):
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            ids.add(document["id"])
            if document.get("supersedes"):
                superseded.add(document["supersedes"])
        leaf_gur = (ids - superseded).pop()
        self.assertEqual(self.leaf()["provenance"]["gur_id"], leaf_gur)


class TestVerifyPagesUsesTheLeafBundle(unittest.TestCase):
    """verify-pages must read the active leaf, not every published revision.

    A superseded revision may legitimately hold a value a later contract forbids
    — intro r03 carries the multi-locus page DEC-2026-0008 later banned. Reading
    it crashed the command and would have re-reported a settled problem forever.
    """

    def test_superseded_revisions_are_not_read(self):
        import io
        from contextlib import redirect_stdout

        from adnd1e_builder.cli import verify_pages

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet = root / "packets" / "PKT-X"
            packet.mkdir(parents=True)
            (packet / "source.md").write_text(
                "# H {#p7}\n\nbody\n", encoding="utf-8", newline="\n"
            )
            gup_dir = root / "gup"
            gup_dir.mkdir()
            # r01 holds a value the current contract forbids; r02 supersedes it.
            (gup_dir / "GUP-PKT-X-r01.yaml").write_text(
                yaml.safe_dump({"id": "GUP-PKT-X-r01", "supersedes": None}), encoding="utf-8")
            (gup_dir / "GUP-PKT-X-r01.edges.csv").write_text(
                'page\n"7, 9, 15"\n', encoding="utf-8", newline="\n")
            (gup_dir / "GUP-PKT-X-r02.yaml").write_text(
                yaml.safe_dump({"id": "GUP-PKT-X-r02", "supersedes": "GUP-PKT-X-r01"}),
                encoding="utf-8")
            (gup_dir / "GUP-PKT-X-r02.edges.csv").write_text(
                "page\n7\n", encoding="utf-8", newline="\n")

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = verify_pages([packet], gup_dir)

        output = buffer.getvalue()
        self.assertEqual(code, 0, output)
        self.assertIn("GUP-PKT-X-r02", output)
        self.assertNotIn("7, 9, 15", output)


if __name__ == "__main__":
    unittest.main()
