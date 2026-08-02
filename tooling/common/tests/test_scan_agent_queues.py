from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


MODULE_PATH = Path(__file__).parents[1] / "scan_agent_queues.py"
SPEC = importlib.util.spec_from_file_location("scan_agent_queues", MODULE_PATH)
assert SPEC and SPEC.loader
scanner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scanner
SPEC.loader.exec_module(scanner)


class QueueScannerCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "README.md").write_text("# fixture\n", encoding="utf-8")
        self.book = self.root / "books" / "adnd1e" / "phb"
        for relative in (
            "packets/incoming",
            "packets/claimed",
            "artifacts/gur",
            "artifacts/gup",
            "artifacts/reviews",
            "artifacts/approved",
            "artifacts/integrated",
        ):
            (self.book / relative).mkdir(parents=True, exist_ok=True)
        for relative in (
            "escalations/pending",
            "escalations/decided",
            "escalations/decisions",
            "manifests",
        ):
            (self.root / "rulesets" / "adnd1e" / relative).mkdir(
                parents=True, exist_ok=True
            )

    def tearDown(self):
        self.temp.cleanup()

    def write_yaml(self, relative: str, document: dict) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        return path

    def gur(self, packet: str, revision: int, supersedes=None):
        artifact_id = f"GUR-{packet}-r{revision:02d}"
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/gur/{artifact_id}.yaml",
            {
                "id": artifact_id,
                "packet_id": packet,
                "revision": revision,
                "supersedes": supersedes,
            },
        )
        return artifact_id

    def gup(
        self,
        packet: str,
        revision: int,
        gur_id: str,
        *,
        status="proposed",
        approval_ready=True,
        supersedes=None,
        escalations=None,
    ):
        artifact_id = f"GUP-{packet}-r{revision:02d}"
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/gup/{artifact_id}.yaml",
            {
                "id": artifact_id,
                "packet_id": packet,
                "revision": revision,
                "supersedes": supersedes,
                "status": status,
                "approval_ready": approval_ready,
                "provenance": {"gur_id": gur_id},
                "escalations": escalations or [],
            },
        )
        edge_path = (
            self.root
            / "books"
            / "adnd1e"
            / "phb"
            / "artifacts"
            / "gup"
            / f"{artifact_id}.edges.csv"
        )
        edge_path.write_text("source_id,target_id\n", encoding="utf-8")
        return artifact_id

    def review(self, packet: str, gup_id: str, disposition="approved"):
        artifact_id = f"REV-{gup_id}-r01"
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/reviews/{artifact_id}.yaml",
            {
                "id": artifact_id,
                "packet_id": packet,
                "revision": 1,
                "status": disposition,
                "overall_disposition": disposition,
                "reviewed_gup": {"id": gup_id},
            },
        )
        return artifact_id

    def scan(self):
        return scanner.scan_repository(self.root)

    def test_gur_supersession_and_consumption_produce_no_builder_job(self):
        packet = "PKT-PHB-001-002-fixture"
        r1 = self.gur(packet, 1)
        r2 = self.gur(packet, 2, supersedes=r1)
        self.gup(packet, 1, r2)
        result = self.scan()
        builder = [item for item in result["Items"] if item["Role"] == "Builder"]
        self.assertEqual(builder, [])

    def test_gup_components_are_one_reviewer_job(self):
        packet = "PKT-PHB-001-002-fixture"
        gur_id = self.gur(packet, 1)
        gup_id = self.gup(packet, 1, gur_id)
        result = self.scan()
        reviewer = [item for item in result["Items"] if item["Role"] == "Reviewer"]
        self.assertEqual([item["InputId"] for item in reviewer], [gup_id])
        self.assertEqual(len(reviewer[0]["Components"]), 2)

    def test_reviewed_gup_is_not_reviewer_ready(self):
        packet = "PKT-PHB-001-002-fixture"
        gur_id = self.gur(packet, 1)
        gup_id = self.gup(packet, 1, gur_id)
        self.review(packet, gup_id)
        result = self.scan()
        self.assertFalse(any(item["Role"] == "Reviewer" for item in result["Items"]))

    def test_decided_blocker_returns_gup_to_builder(self):
        packet = "PKT-PHB-001-002-fixture"
        escalation_id = "ESC-2026-07-30T01.02.03.004Z"
        gur_id = self.gur(packet, 1)
        gup_id = self.gup(
            packet,
            1,
            gur_id,
            status="blocked",
            approval_ready=False,
            escalations=[{"id": escalation_id}],
        )
        self.write_yaml(
            f"rulesets/adnd1e/escalations/decided/{escalation_id}.yaml",
            {"id": escalation_id, "status": "decided"},
        )
        result = self.scan()
        builder = [item for item in result["Items"] if item["Role"] == "Builder"]
        self.assertEqual([item["InputId"] for item in builder], [gup_id])
        # WORK_QUEUES acceptance 4: a blocked GUP produces no Reviewer job. The
        # blocker being decided returns it to Builder; it never makes the GUP
        # reviewable, because `status: blocked` and `approval_ready: false`
        # disqualify it on their own.
        self.assertFalse(
            any(item["Role"] == "Reviewer" for item in result["Items"]),
            "a blocked GUP must never be Reviewer-ready",
        )
        self.assertNotIn(
            gup_id,
            [
                item["InputId"]
                for item in result["Items"]
                if item["Role"] == "Reviewer"
            ],
        )

    def test_stale_gup_is_diagnostic_not_reviewer_ready(self):
        packet = "PKT-PHB-001-002-fixture"
        r1 = self.gur(packet, 1)
        self.gur(packet, 2, supersedes=r1)
        gup_id = self.gup(packet, 1, r1)
        result = self.scan()
        self.assertFalse(any(item["Role"] == "Reviewer" for item in result["Items"]))
        self.assertIn(
            gup_id,
            [
                item["ArtifactId"]
                for item in result["Diagnostics"]
                if item["Code"] == "stale_gup_input"
            ],
        )

    def test_claimed_packet_with_gur_is_informational(self):
        packet = "PKT-PHB-001-002-fixture"
        packet_dir = self.book / "packets" / "claimed" / packet
        packet_dir.mkdir()
        self.write_yaml(
            f"books/adnd1e/phb/packets/claimed/{packet}/packet.yaml",
            {"id": packet, "status": "claimed"},
        )
        self.gur(packet, 1)
        result = self.scan()
        self.assertEqual(result["ActiveCount"], 0)
        self.assertEqual(result["InformationalCount"], 1)

    def approved_bundle(self, packet: str) -> str:
        gur_id = self.gur(packet, 1)
        gup_id = self.gup(packet, 1, gur_id)
        review_id = self.review(packet, gup_id)
        approved_id = "APPROVED-" + review_id[len("REV-") :]
        approved_dir = self.book / "artifacts" / "approved"
        (approved_dir / f"{approved_id}.edges.csv").write_text(
            "source_id,target_id\n", encoding="utf-8"
        )
        (approved_dir / f"{approved_id}.nodes.csv").write_text(
            "id,label\n", encoding="utf-8"
        )
        return approved_id

    def test_approved_components_are_one_integrator_job(self):
        """WORK_QUEUES acceptance 7: several components, one job."""
        approved_id = self.approved_bundle("PKT-PHB-001-002-fixture")
        result = self.scan()
        integrator = [
            item for item in result["Items"] if item["Role"] == "Integrator"
        ]
        self.assertEqual([item["InputId"] for item in integrator], [approved_id])
        self.assertEqual(len(integrator[0]["Components"]), 2)

    def test_integrated_approved_bundle_produces_no_integrator_job(self):
        """WORK_QUEUES acceptance 8: an integrated bundle is consumed."""
        approved_id = self.approved_bundle("PKT-PHB-001-002-fixture")
        self.assertTrue(
            any(item["Role"] == "Integrator" for item in self.scan()["Items"]),
            "the bundle must be Integrator work before it is integrated",
        )

        manifest = self.root / "rulesets" / "adnd1e" / "manifests" / "INT-20260730-001.json"
        manifest.write_text(
            json.dumps({"approved_bundles": [approved_id]}), encoding="utf-8"
        )
        result = self.scan()
        self.assertFalse(any(item["Role"] == "Integrator" for item in result["Items"]))

    def test_file_timestamps_do_not_change_queue_result(self):
        packet = "PKT-PHB-001-002-fixture"
        gur_id = self.gur(packet, 1)
        first = self.scan()["Items"]
        path = (
            self.book
            / "artifacts"
            / "gur"
            / f"{gur_id}.yaml"
        )
        os.utime(path, (1, 1))
        second = self.scan()["Items"]
        self.assertEqual(first, second)

    def test_forked_lineage_is_fatal(self):
        """WORK_QUEUES acceptance 10: invalid lineage returns the lineage-error code."""
        packet = "PKT-PHB-001-002-fixture"
        r1 = self.gur(packet, 1)
        self.gur(packet, 2, supersedes=r1)
        self.gur(packet, 3, supersedes=r1)
        result = self.scan()
        self.assertGreater(result["LineageErrorCount"], 0)
        self.assertIn(
            "forked_revision_lineage",
            [item["Code"] for item in result["Diagnostics"]],
        )
        # Assert the process contract directly, not just the counter: a
        # trustworthy result is impossible, so exit 2 must win over the exit 1
        # that ready work would otherwise produce.
        exit_code = scanner.main(["--root", str(self.root), "--json"])
        self.assertEqual(exit_code, 2)


class DecisionMigrationCase(QueueScannerCase):
    """WORK_QUEUES 1.2 acceptance tests 12-20, ruled by DEC-2026-0018.

    A decision migration has no GUR by design. Everything here turns on whether
    the alternate auditable root -- checksummed Decisions plus a pinned canonical
    baseline -- is intact, because that is what earns Reviewer routing in place
    of packet lineage.
    """

    CANONICAL = "rulesets/adnd1e/canonical/edges_master.csv"

    def setUp(self):
        super().setUp()
        canonical = self.root / self.CANONICAL
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text("source_id,edge_type,target_id\na_b,GATES,c_d\n", encoding="utf-8")

    def sha256(self, relative: str) -> str:
        path = self.root / relative
        if not path.is_file():
            # A GUP can record a checksum for a file that is not there: that is
            # the case where authority has gone missing, and the fixture has to
            # be able to build it.
            return "sha256:" + "0" * 64
        return scanner._sha256_of(path)

    def decision(
        self,
        decision_id: str,
        *,
        status="approved",
        migration_required=True,
        next_role="builder",
        readiness="ready",
        ruleset="adnd1e",
    ) -> str:
        relative = f"rulesets/adnd1e/escalations/decisions/{decision_id}.yaml"
        self.write_yaml(
            relative,
            {
                "id": decision_id,
                "status": status,
                "ruleset_id": ruleset,
                "book_id": "phb",
                "migration_required": migration_required,
                "handoff": {
                    "next_role": next_role,
                    "readiness": readiness,
                    "reason": "migrate",
                    "blocking_ids": [],
                },
            },
        )
        return relative

    def migration(
        self,
        artifact_id: str,
        decision_ids,
        *,
        lineage_id="MIG-FIXTURE",
        revision=1,
        supersedes=None,
        store="books/adnd1e/phb/artifacts/gup",
        status="proposed",
        approval_ready=True,
        artifact_kind="decision_migration",
        omit=(),
        extra_provenance=None,
    ) -> str:
        report_relative = f"build/reports/{artifact_id}.validation.json"
        report_path = self.root / report_relative
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps({"gup_id": artifact_id, "approval_ready": approval_ready}),
            encoding="utf-8",
        )

        provenance = {
            "decision_inputs": [
                {
                    "id": decision_id,
                    "path": f"rulesets/adnd1e/escalations/decisions/{decision_id}.yaml",
                    "checksum": self.sha256(
                        f"rulesets/adnd1e/escalations/decisions/{decision_id}.yaml"
                    ),
                }
                for decision_id in decision_ids
            ],
            "canonical_source": self.CANONICAL,
            "canonical_checksum": self.sha256(self.CANONICAL),
            "canonical_rows_read": 1,
        }
        provenance.update(extra_provenance or {})

        document = {
            "id": artifact_id,
            "status": status,
            "ruleset_id": "adnd1e",
            "constitution_version": "1.6",
            "packet_id": "cross-packet",
            "artifact_kind": artifact_kind,
            "lineage_id": lineage_id,
            "revision": revision,
            "supersedes": supersedes,
            "authority": list(decision_ids),
            "validation_report": report_relative,
            "validation_report_checksum": self.sha256(report_relative),
            "approval_ready": approval_ready,
            "handoff": {
                "next_role": "reviewer",
                "readiness": "ready",
                "reason": "migration ready",
                "blocking_ids": [],
            },
            "provenance": provenance,
        }
        for key in omit:
            document.pop(key, None)
        self.write_yaml(f"{store}/{artifact_id}.yaml", document)
        return artifact_id

    def items(self, result, queue: str) -> list[str]:
        return [i["InputId"] for i in result["Items"] if i["Queue"] == queue]

    def codes(self, result) -> list[str]:
        return [d["Code"] for d in result["Diagnostics"]]

    # -- 12 -----------------------------------------------------------------
    def test_valid_migration_is_one_reviewer_job_and_never_stale_gup_input(self):
        self.decision("DEC-2026-0015")
        gup_id = self.migration("GUP-MIG-FIXTURE-r01", ["DEC-2026-0015"])
        result = self.scan()
        self.assertEqual(self.items(result, "REVIEWER-DECISION-MIGRATION"), [gup_id])
        self.assertNotIn("stale_gup_input", self.codes(result))
        self.assertEqual(result["LineageErrorCount"], 0)

    # -- 13 -----------------------------------------------------------------
    def test_missing_decision_prevents_review(self):
        gup_id = self.migration("GUP-MIG-FIXTURE-r01", ["DEC-2026-9999"])
        result = self.scan()
        self.assertEqual(self.items(result, "REVIEWER-DECISION-MIGRATION"), [])
        self.assertIn("decision_migration_lineage_error", self.codes(result))
        self.assertEqual(scanner.main(["--root", str(self.root), "--json"]), 2)
        self.assertTrue(gup_id)

    def test_non_approved_decision_prevents_review(self):
        self.decision("DEC-2026-0015", status="draft")
        self.migration("GUP-MIG-FIXTURE-r01", ["DEC-2026-0015"])
        result = self.scan()
        self.assertEqual(self.items(result, "REVIEWER-DECISION-MIGRATION"), [])
        self.assertIn("decision_migration_lineage_error", self.codes(result))

    def test_wrong_ruleset_decision_prevents_review(self):
        self.decision("DEC-2026-0015", ruleset="adnd2e")
        self.migration("GUP-MIG-FIXTURE-r01", ["DEC-2026-0015"])
        result = self.scan()
        self.assertEqual(self.items(result, "REVIEWER-DECISION-MIGRATION"), [])

    def test_decision_not_requiring_migration_prevents_review(self):
        self.decision("DEC-2026-0015", migration_required=False)
        self.migration("GUP-MIG-FIXTURE-r01", ["DEC-2026-0015"])
        result = self.scan()
        self.assertEqual(self.items(result, "REVIEWER-DECISION-MIGRATION"), [])

    def test_checksum_mismatch_prevents_review(self):
        relative = self.decision("DEC-2026-0015")
        self.migration("GUP-MIG-FIXTURE-r01", ["DEC-2026-0015"])
        # The Decision is edited after the plan was made. The plan now describes
        # authority that no longer says what it said.
        (self.root / relative).write_text(
            (self.root / relative).read_text(encoding="utf-8") + "\nnote: amended\n",
            encoding="utf-8",
        )
        result = self.scan()
        self.assertEqual(self.items(result, "REVIEWER-DECISION-MIGRATION"), [])
        self.assertIn("decision_migration_lineage_error", self.codes(result))

    def test_drifted_canonical_baseline_prevents_review(self):
        self.decision("DEC-2026-0015")
        self.migration("GUP-MIG-FIXTURE-r01", ["DEC-2026-0015"])
        (self.root / self.CANONICAL).write_text(
            "source_id,edge_type,target_id\na_b,GATES,c_d\ne_f,GATES,g_h\n", encoding="utf-8"
        )
        result = self.scan()
        self.assertEqual(self.items(result, "REVIEWER-DECISION-MIGRATION"), [])
        self.assertIn("decision_migration_lineage_error", self.codes(result))

    # -- 14 -----------------------------------------------------------------
    def test_each_missing_envelope_field_prevents_review(self):
        for field in (
            "lineage_id",
            "revision",
            "validation_report",
            "validation_report_checksum",
        ):
            with self.subTest(field=field):
                self.setUp()
                self.decision("DEC-2026-0015")
                self.migration("GUP-MIG-FIXTURE-r01", ["DEC-2026-0015"], omit=(field,))
                result = self.scan()
                self.assertEqual(self.items(result, "REVIEWER-DECISION-MIGRATION"), [])
                self.assertIn("decision_migration_lineage_error", self.codes(result))

    def test_missing_canonical_checksum_prevents_review(self):
        self.decision("DEC-2026-0015")
        self.migration(
            "GUP-MIG-FIXTURE-r01", ["DEC-2026-0015"],
            extra_provenance={"canonical_checksum": ""},
        )
        result = self.scan()
        self.assertEqual(self.items(result, "REVIEWER-DECISION-MIGRATION"), [])

    def test_a_gur_reference_disqualifies_a_decision_migration(self):
        """A decision migration that claims packet lineage is not one."""
        self.decision("DEC-2026-0015")
        self.migration(
            "GUP-MIG-FIXTURE-r01", ["DEC-2026-0015"],
            extra_provenance={"gur_id": "GUR-PKT-PHB-001-002-fixture-r01"},
        )
        result = self.scan()
        self.assertEqual(self.items(result, "REVIEWER-DECISION-MIGRATION"), [])
        self.assertIn("decision_migration_lineage_error", self.codes(result))

    # -- 15 -----------------------------------------------------------------
    def test_invalid_migration_does_not_consume_its_decisions(self):
        self.decision("DEC-2026-0015")
        self.migration("GUP-MIG-FIXTURE-r01", ["DEC-2026-0015"], omit=("lineage_id",))
        result = self.scan()
        self.assertIn("DEC-2026-0015", self.items(result, "BUILDER-DECISION-MIGRATION"))

    def test_valid_migration_consumes_its_decisions(self):
        self.decision("DEC-2026-0015")
        self.decision("DEC-2026-0016")
        self.migration("GUP-MIG-FIXTURE-r01", ["DEC-2026-0015", "DEC-2026-0016"])
        result = self.scan()
        self.assertEqual(self.items(result, "BUILDER-DECISION-MIGRATION"), [])

    def test_an_unconsumed_decision_is_builder_work(self):
        self.decision("DEC-2026-0015")
        self.decision("DEC-2026-0016")
        self.migration("GUP-MIG-FIXTURE-r01", ["DEC-2026-0015"])
        result = self.scan()
        self.assertEqual(self.items(result, "BUILDER-DECISION-MIGRATION"), ["DEC-2026-0016"])

    # -- 16 -----------------------------------------------------------------
    def test_two_cross_packet_migrations_with_distinct_lineage_ids_are_independent(self):
        self.decision("DEC-2026-0015")
        self.decision("DEC-2026-0016")
        a = self.migration("GUP-MIG-ALPHA-r01", ["DEC-2026-0015"], lineage_id="MIG-ALPHA")
        b = self.migration("GUP-MIG-BETA-r01", ["DEC-2026-0016"], lineage_id="MIG-BETA")
        result = self.scan()
        self.assertEqual(
            sorted(self.items(result, "REVIEWER-DECISION-MIGRATION")), sorted([a, b])
        )

    # -- 17 -----------------------------------------------------------------
    def test_only_the_active_leaf_of_a_lineage_is_reviewer_ready(self):
        self.decision("DEC-2026-0015")
        first = self.migration("GUP-MIG-FIXTURE-r01", ["DEC-2026-0015"], revision=1)
        second = self.migration(
            "GUP-MIG-FIXTURE-r02", ["DEC-2026-0015"], revision=2, supersedes=first
        )
        result = self.scan()
        self.assertEqual(self.items(result, "REVIEWER-DECISION-MIGRATION"), [second])

    def test_a_conforming_revision_supersedes_an_unkeyed_predecessor(self):
        """`lineage_id` postdates the first migrations, so r01 may lack it."""
        self.decision("DEC-2026-0015")
        first = self.migration("GUP-MIG-FIXTURE-r01", ["DEC-2026-0015"], omit=("lineage_id",))
        second = self.migration(
            "GUP-MIG-FIXTURE-r02", ["DEC-2026-0015"], revision=2, supersedes=first
        )
        result = self.scan()
        self.assertEqual(self.items(result, "REVIEWER-DECISION-MIGRATION"), [second])
        self.assertNotIn("missing_supersedes_target", self.codes(result))

    # -- 18 -----------------------------------------------------------------
    def test_a_reviewed_decision_migration_is_not_reviewer_ready(self):
        self.decision("DEC-2026-0015")
        gup_id = self.migration("GUP-MIG-FIXTURE-r01", ["DEC-2026-0015"])
        self.review("cross-packet", gup_id)
        result = self.scan()
        self.assertEqual(self.items(result, "REVIEWER-DECISION-MIGRATION"), [])

    # -- 19 -----------------------------------------------------------------
    def test_legacy_spelling_is_not_reviewer_ready_and_is_not_a_lineage_error(self):
        self.decision("DEC-2026-0007")
        self.migration(
            "GUP-MIG-DEC-2026-0007-r01", ["DEC-2026-0007"],
            artifact_kind="identity_merge_migration",
        )
        result = self.scan()
        self.assertEqual(self.items(result, "REVIEWER-DECISION-MIGRATION"), [])
        self.assertIn("legacy_migration_spelling", self.codes(result))
        # Known debt, not broken lineage: it must not poison the exit code, and
        # it must not consume its Decision either.
        self.assertEqual(result["LineageErrorCount"], 0)
        self.assertIn("DEC-2026-0007", self.items(result, "BUILDER-DECISION-MIGRATION"))

    def test_a_packet_gup_is_never_routed_as_a_decision_migration(self):
        packet = "PKT-PHB-001-002-fixture"
        gur_id = self.gur(packet, 1)
        gup_id = self.gup(packet, 1, gur_id)
        result = self.scan()
        self.assertEqual(self.items(result, "REVIEWER-GUP"), [gup_id])
        self.assertEqual(self.items(result, "REVIEWER-DECISION-MIGRATION"), [])

    # -- 20 -----------------------------------------------------------------
    def test_cross_book_store_produces_the_same_job_as_a_book_store(self):
        self.decision("DEC-2026-0015")
        self.migration(
            "GUP-MIG-FIXTURE-r01", ["DEC-2026-0015"],
            store="rulesets/adnd1e/cross-book/identity-resolution",
        )
        result = self.scan()
        self.assertEqual(
            self.items(result, "REVIEWER-DECISION-MIGRATION"), ["GUP-MIG-FIXTURE-r01"]
        )

    def test_components_include_the_validation_report(self):
        self.decision("DEC-2026-0015")
        gup_id = self.migration("GUP-MIG-FIXTURE-r01", ["DEC-2026-0015"])
        result = self.scan()
        item = next(
            i for i in result["Items"] if i["Queue"] == "REVIEWER-DECISION-MIGRATION"
        )
        self.assertIn(f"build/reports/{gup_id}.validation.json", item["Components"])

    def test_timestamps_do_not_change_the_result(self):
        self.decision("DEC-2026-0015")
        self.migration("GUP-MIG-FIXTURE-r01", ["DEC-2026-0015"])
        first = self.scan()["Items"]
        for path in self.root.rglob("*"):
            if path.is_file():
                os.utime(path, (1, 1))
        self.assertEqual(self.scan()["Items"], first)


class TestScannerParity(unittest.TestCase):
    """WORK_QUEUES 1.2 acceptance 20: the two scanners must agree.

    They agree by construction rather than by duplication -- the PowerShell
    entry point forwards to the Python implementation -- so this test proves the
    forwarding, which is the only place the two could diverge.
    """

    REPO_ROOT = Path(__file__).resolve().parents[3]
    SCRIPT = REPO_ROOT / "tooling" / "common" / "scan-agent-queues.ps1"

    def _pwsh(self) -> str | None:
        import shutil

        return shutil.which("pwsh") or shutil.which("powershell")

    def test_powershell_and_python_return_the_same_jobs_and_exit_code(self):
        import subprocess

        shell = self._pwsh()
        if shell is None:
            self.skipTest("no PowerShell on PATH")

        python = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--root", str(self.REPO_ROOT), "--json"],
            capture_output=True, text=True,
        )
        powershell = subprocess.run(
            [shell, "-NoProfile", "-File", str(self.SCRIPT),
             "-Root", str(self.REPO_ROOT), "-Json"],
            capture_output=True, text=True,
        )
        self.assertEqual(powershell.returncode, python.returncode)

        expected = json.loads(python.stdout)
        actual = json.loads(powershell.stdout)
        for key in ("Items", "Diagnostics", "ReadyCount", "LineageErrorCount"):
            self.assertEqual(actual[key], expected[key], f"{key} differs")


if __name__ == "__main__":
    unittest.main()
