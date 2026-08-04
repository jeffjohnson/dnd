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


class MigrationFixtureMixin:
    """Decision-migration fixture builders, carrying no tests of their own.

    Kept apart from the test class so a second suite can build the same
    fixtures without re-running the first suite's assertions.
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


class DecisionMigrationCase(MigrationFixtureMixin, QueueScannerCase):
    """WORK_QUEUES 1.2 acceptance tests 12-20, ruled by DEC-2026-0018.

    A decision migration has no GUR by design. Everything here turns on whether
    the alternate auditable root -- checksummed Decisions plus a pinned canonical
    baseline -- is intact, because that is what earns Reviewer routing in place
    of packet lineage.
    """

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


class ReviewRevisionRoutingCase(QueueScannerCase):
    """A `revision_required` Review names whose revision it wants.

    Routing every such Review to Builder regardless is how a packet stalls: a
    Review whose only finding is that the GUR omits source assertions gives the
    Builder nothing to apply. The Builder may not reinterpret source, so its
    only options are to publish a byte-identical no-op leaf or to invent the
    missing rows -- and the Analyst, who can actually answer, never sees the job.
    """

    PACKET = "PKT-PHB-001-002-fixture"

    def revision_review(self, *, handoff_role=None, row_corrections=None,
                        required_revisions=None):
        gur_id = self.gur(self.PACKET, 1)
        gup_id = self.gup(self.PACKET, 1, gur_id)
        document = {
            "id": f"REV-{gup_id}-r01",
            "packet_id": self.PACKET,
            "revision": 1,
            "status": "revision_required",
            "overall_disposition": "revision_required",
            "reviewed_gup": {"id": gup_id},
            "row_decisions": [
                {"ref": "B1", "disposition": "approved"},
                {"ref": "B2", "disposition": "approved_with_revision",
                 "exact_corrections": row_corrections or {}},
            ],
        }
        if handoff_role is not None:
            document["handoff"] = {
                "next_role": handoff_role, "readiness": "ready", "blocking_ids": []
            }
        if required_revisions is not None:
            document["required_gup_revisions"] = required_revisions
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/reviews/REV-{gup_id}-r01.yaml", document
        )
        return self.scan()

    def roles(self, result):
        return sorted(
            item["Role"] for item in result["Items"] if item["State"] == "ready"
        )

    def test_a_review_returned_to_the_analyst_is_not_builder_work(self):
        result = self.revision_review(
            handoff_role="analyst",
            required_revisions=[
                {"finding_id": "F-COMPLETENESS", "next_role": "analyst",
                 "exact_action": "account for the omitted source clauses"}
            ],
        )
        self.assertEqual(self.roles(result), ["Analyst"])
        self.assertNotIn(
            "Builder", [item["Role"] for item in result["Items"] if item["State"] == "ready"]
        )

    def test_a_review_with_an_exact_correction_is_builder_work(self):
        result = self.revision_review(
            handoff_role="builder", row_corrections={"aspect": "corrected aspect"}
        )
        self.assertEqual(self.roles(result), ["Builder"])

    def test_a_review_may_give_work_to_both_roles(self):
        """The real money-equipment r03 case.

        One exact correction for the Builder to apply, alongside a completeness
        finding only the Analyst can answer. Reading `handoff.next_role` alone
        would hide the correction; reading the corrections alone would hide the
        packet's return to the Analyst.
        """
        result = self.revision_review(
            handoff_role="analyst",
            row_corrections={"polarity": "neutral"},
            required_revisions=[
                {"finding_id": "F-POLARITY", "exact_action": "retain B2 as neutral"},
                {"finding_id": "F-COMPLETENESS", "next_role": "analyst",
                 "exact_action": "account for the omitted clauses"},
            ],
        )
        self.assertEqual(self.roles(result), ["Analyst", "Builder"])

    def test_an_unqualified_revision_request_belongs_to_the_builder(self):
        """A `required_gup_revisions` entry naming no role is the Builder's.

        The Builder emits the GUP, so an unqualified request to revise it is a
        request to the Builder even where the packet also returns to the Analyst.
        """
        result = self.revision_review(
            handoff_role="analyst",
            required_revisions=[
                {"finding_id": "F-UNQUALIFIED", "exact_action": "drop the duplicate"}
            ],
        )
        self.assertEqual(self.roles(result), ["Analyst", "Builder"])

    def test_a_legacy_review_with_no_handoff_still_routes_to_builder(self):
        """Legacy artifacts remain valid and the inference is reported."""
        result = self.revision_review()
        self.assertEqual(self.roles(result), ["Builder"])
        builder = [
            item for item in result["Items"]
            if item["Role"] == "Builder" and item["State"] == "ready"
        ]
        self.assertTrue(builder[0]["LegacyInference"])
        self.assertIn(
            "review_handoff_inferred",
            {d["Code"] for d in result["Diagnostics"]},
        )

    def test_an_unrecognised_handoff_role_is_not_trusted(self):
        """Routing to a role that does not exist would hide the work entirely."""
        result = self.revision_review(handoff_role="stakeholder")
        self.assertEqual(self.roles(result), ["Builder"])


class TestReviewRevisionRoles(unittest.TestCase):
    """The routing rule, read directly."""

    def roles(self, document):
        return scanner._review_revision_roles(document)

    def test_no_signal_yields_no_role(self):
        self.assertEqual(self.roles({}), [])

    def test_handoff_none_is_not_a_role(self):
        self.assertEqual(self.roles({"handoff": {"next_role": "none"}}), [])

    def test_builder_is_listed_first_when_both_apply(self):
        document = {
            "handoff": {"next_role": "analyst"},
            "row_decisions": [{"ref": "A1", "exact_corrections": {"aspect": "x"}}],
        }
        self.assertEqual(self.roles(document), ["builder", "analyst"])

    def test_a_role_is_never_listed_twice(self):
        document = {
            "handoff": {"next_role": "builder"},
            "row_decisions": [{"ref": "A1", "exact_corrections": {"aspect": "x"}}],
            "required_gup_revisions": [{"finding_id": "F1"}],
        }
        self.assertEqual(self.roles(document), ["builder"])

    def test_empty_corrections_are_not_actionable(self):
        document = {
            "handoff": {"next_role": "analyst"},
            "row_decisions": [{"ref": "A1", "exact_corrections": {}}],
        }
        self.assertEqual(self.roles(document), ["analyst"])


class MigrationReviewRoutingCase(MigrationFixtureMixin, QueueScannerCase):
    """A Review on a migration leaf names who fixes it; a lineage error does not.

    A drifted canonical baseline says the leaf cannot go to Reviewer as it
    stands. It says nothing about who acts next. Treating it as "nobody has
    consumed these Decisions" republished them as ready Builder work while the
    Review that decided them was still asking the Analyst for a prerequisite --
    and hid the Analyst's job entirely, so the work had no visible owner.
    """

    def stale_migration_with_review(self, *, review_handoff=None,
                                    row_corrections=None, required_revisions=None):
        self.decision("DEC-2026-0015")
        gup_id = self.migration("GUP-MIG-FIXTURE-r01", ["DEC-2026-0015"])
        if review_handoff is not None:
            document = {
                "id": f"REV-{gup_id}-r01",
                "packet_id": "cross-packet",
                "revision": 1,
                "status": "revision_required",
                "overall_disposition": "revision_required",
                "reviewed_gup": {"id": gup_id},
                "handoff": {
                    "next_role": review_handoff, "readiness": "ready",
                    "blocking_ids": [],
                },
                "row_decisions": [
                    {"ref": "R1", "disposition": "approved_with_revision",
                     "exact_corrections": row_corrections or {}}
                ],
            }
            if required_revisions is not None:
                document["required_gup_revisions"] = required_revisions
            self.write_yaml(
                f"books/adnd1e/phb/artifacts/reviews/REV-{gup_id}-r01.yaml", document
            )
        # Drift the baseline the migration was planned against.
        (self.root / self.CANONICAL).write_text(
            "source_id,edge_type,target_id\na_b,GATES,c_d\ne_f,GATES,g_h\n",
            encoding="utf-8",
        )
        return gup_id, self.scan()

    def ready(self, result):
        return [i for i in result["Items"] if i["State"] == "ready"]

    def ready_roles(self, result):
        return sorted(i["Role"] for i in self.ready(result))

    def test_a_stale_migration_returned_to_the_analyst_is_not_builder_work(self):
        _, result = self.stale_migration_with_review(
            review_handoff="analyst",
            required_revisions=[
                {"finding_id": "MIG-PREREQ", "next_role": "analyst",
                 "exact_action": "integrate the prerequisite cleanup first"}
            ],
        )
        self.assertEqual(self.ready_roles(result), ["Analyst"])
        # The authority Decision must not resurface as ready Builder work while
        # its Review is asking someone else for the prerequisite.
        self.assertEqual(self.items(result, "BUILDER-DECISION-MIGRATION"), [])

    def test_the_lineage_error_is_still_reported(self):
        """Routing changes; truth-telling does not."""
        gup_id, result = self.stale_migration_with_review(review_handoff="analyst")
        self.assertIn("decision_migration_lineage_error", self.codes(result))
        self.assertIn(gup_id, {d["ArtifactId"] for d in result["Diagnostics"]})
        self.assertEqual(self.items(result, "REVIEWER-DECISION-MIGRATION"), [])

    def test_a_migration_review_asking_the_builder_is_builder_work(self):
        _, result = self.stale_migration_with_review(
            review_handoff="builder",
            row_corrections={"target_label": "Corrected Label"},
        )
        self.assertEqual(self.ready_roles(result), ["Builder"])
        self.assertEqual(self.items(result, "BUILDER-DECISION-MIGRATION"), [])

    def test_a_migration_review_may_give_work_to_both_roles(self):
        _, result = self.stale_migration_with_review(
            review_handoff="analyst",
            row_corrections={"target_label": "Corrected Label"},
            required_revisions=[
                {"finding_id": "MIG-PREREQ", "next_role": "analyst",
                 "exact_action": "integrate the prerequisite"}
            ],
        )
        self.assertEqual(self.ready_roles(result), ["Analyst", "Builder"])

    def test_an_unreviewed_stale_migration_still_republishes_its_decisions(self):
        """With no Review there is no ruling to defer to.

        The Decisions are genuinely unconsumed and the Builder is genuinely the
        role that re-issues the migration, so they must stay visible.
        """
        _, result = self.stale_migration_with_review(review_handoff=None)
        self.assertEqual(self.ready_roles(result), ["Builder"])
        self.assertEqual(
            self.items(result, "BUILDER-DECISION-MIGRATION"),
            ["DEC-2026-0015"],
        )


class DecisionHandoffReplacementCase(QueueScannerCase):
    """WORK_QUEUES 1.3, ruled by DEC-2026-0022.

    An immutable artifact preserves the evidence a Review was built on, but it
    cannot represent a ruling made after it was written. Where an approved
    Decision resolved the escalation that artifact raised, continuing to report
    the artifact's older handoff assigns obsolete work and double-counts one
    coordination lineage. Replacement is queue-state only: the artifact is never
    rewritten, and the link must be exact rather than inferred.
    """

    PACKET = "PKT-PHB-001-002-fixture"
    ESC = "ESC-2026-08-03T22.35.13.308Z"

    def review_needing_the_analyst(self, artifact_id="REV-GUP-FIXTURE-r01-r01"):
        """A Review whose own handoff makes it ready Analyst work."""
        gur_id = self.gur(self.PACKET, 1)
        gup_id = self.gup(self.PACKET, 1, gur_id)
        relative = f"books/adnd1e/phb/artifacts/reviews/{artifact_id}.yaml"
        self.write_yaml(
            relative,
            {
                "id": artifact_id,
                "packet_id": self.PACKET,
                "revision": 1,
                "status": "revision_required",
                "overall_disposition": "revision_required",
                "reviewed_gup": {"id": gup_id},
                "handoff": {
                    "next_role": "analyst", "readiness": "ready", "blocking_ids": []
                },
                "required_gup_revisions": [
                    {"finding_id": "F-PREREQ", "next_role": "analyst",
                     "exact_action": "produce the prerequisite"}
                ],
            },
        )
        return artifact_id, relative

    def decided_package(self, artifact_id, artifact_path, escalation_id=None):
        escalation_id = escalation_id or self.ESC
        self.write_yaml(
            f"rulesets/adnd1e/escalations/decided/{escalation_id}.yaml",
            {
                "id": escalation_id,
                "question": "who acts next?",
                "originating_artifacts": {
                    "review": artifact_id,
                    "review_path": artifact_path,
                },
            },
        )
        return escalation_id

    def decision(self, decision_id, escalation_id, *, next_role="builder",
                 readiness="ready", blocking_ids=None):
        self.write_yaml(
            f"rulesets/adnd1e/escalations/decisions/{decision_id}.yaml",
            {
                "id": decision_id,
                "status": "approved",
                "ruleset_id": "adnd1e",
                "book_id": "phb",
                "packet_id": self.PACKET,
                "escalation_id": escalation_id,
                "migration_required": False,
                "handoff": {
                    "next_role": next_role,
                    "readiness": readiness,
                    "reason": "the Architect has ruled",
                    "blocking_ids": blocking_ids or [],
                },
            },
        )
        return decision_id

    def ready_ids(self, result):
        return [i["InputId"] for i in result["Items"] if i["State"] == "ready"]

    def blocked_ids(self, result):
        return [i["InputId"] for i in result["BlockedItems"]]

    def codes(self, result):
        return [d["Code"] for d in result["Diagnostics"]]

    # -- the ruling ---------------------------------------------------------
    def test_the_decision_replaces_the_stale_ready_handoff(self):
        artifact_id, path = self.review_needing_the_analyst()
        esc = self.decided_package(artifact_id, path)
        decision_id = self.decision("DEC-2026-0021", esc)
        result = self.scan()
        self.assertNotIn(artifact_id, self.ready_ids(result))
        self.assertIn(decision_id, self.ready_ids(result))

    def test_the_originating_artifact_is_untouched_and_diagnosed(self):
        artifact_id, path = self.review_needing_the_analyst()
        before = (self.root / path).read_bytes()
        esc = self.decided_package(artifact_id, path)
        self.decision("DEC-2026-0021", esc)
        result = self.scan()
        self.assertEqual((self.root / path).read_bytes(), before)
        self.assertIn("handoff_replaced_by_decision", self.codes(result))

    # -- exactness ----------------------------------------------------------
    def test_a_mismatched_escalation_id_does_not_suppress(self):
        artifact_id, path = self.review_needing_the_analyst()
        self.decided_package(artifact_id, path)
        self.decision("DEC-2026-0021", "ESC-2026-01-01T00.00.00.000Z")
        result = self.scan()
        self.assertIn(artifact_id, self.ready_ids(result))

    def test_a_mismatched_originating_path_does_not_suppress(self):
        artifact_id, path = self.review_needing_the_analyst()
        esc = self.decided_package(artifact_id, "books/adnd1e/phb/artifacts/reviews/OTHER.yaml")
        self.decision("DEC-2026-0021", esc)
        result = self.scan()
        self.assertIn(artifact_id, self.ready_ids(result))

    def test_a_superseded_originating_artifact_does_not_suppress_the_leaf(self):
        """Naming an older revision must not silence the active one."""
        artifact_id, path = self.review_needing_the_analyst()
        esc = self.decided_package(
            "REV-GUP-FIXTURE-r00-r01",
            "books/adnd1e/phb/artifacts/reviews/REV-GUP-FIXTURE-r00-r01.yaml",
        )
        self.decision("DEC-2026-0021", esc)
        result = self.scan()
        self.assertIn(artifact_id, self.ready_ids(result))

    def test_free_text_without_a_path_does_not_suppress(self):
        """WORK_QUEUES 1.3 forbids inferring the link from free text."""
        artifact_id, _ = self.review_needing_the_analyst()
        self.write_yaml(
            f"rulesets/adnd1e/escalations/decided/{self.ESC}.yaml",
            {
                "id": self.ESC,
                "originating_artifacts": {
                    "note": f"raised while reviewing {artifact_id}",
                    "reviews": [artifact_id],
                },
            },
        )
        self.decision("DEC-2026-0021", self.ESC)
        result = self.scan()
        self.assertIn(artifact_id, self.ready_ids(result))

    def test_a_decision_without_a_handoff_block_does_not_suppress(self):
        artifact_id, path = self.review_needing_the_analyst()
        esc = self.decided_package(artifact_id, path)
        self.write_yaml(
            "rulesets/adnd1e/escalations/decisions/DEC-2026-0021.yaml",
            {"id": "DEC-2026-0021", "status": "approved", "ruleset_id": "adnd1e",
             "escalation_id": esc, "migration_required": False},
        )
        result = self.scan()
        self.assertIn(artifact_id, self.ready_ids(result))

    # -- readiness routing --------------------------------------------------
    def test_a_blocked_replacement_produces_blocked_state_and_no_ready_item(self):
        artifact_id, path = self.review_needing_the_analyst()
        esc = self.decided_package(artifact_id, path)
        decision_id = self.decision(
            "DEC-2026-0021", esc, readiness="blocked", blocking_ids=["ESC-9999"]
        )
        result = self.scan()
        self.assertNotIn(artifact_id, self.ready_ids(result))
        self.assertNotIn(decision_id, self.ready_ids(result))
        self.assertIn(decision_id, self.blocked_ids(result))
        reason = next(
            i["Reason"] for i in result["BlockedItems"] if i["InputId"] == decision_id
        )
        self.assertIn("ESC-9999", reason)

    def test_a_terminal_replacement_produces_no_downstream_item(self):
        artifact_id, path = self.review_needing_the_analyst()
        esc = self.decided_package(artifact_id, path)
        decision_id = self.decision("DEC-2026-0021", esc, readiness="terminal")
        result = self.scan()
        self.assertNotIn(artifact_id, self.ready_ids(result))
        self.assertNotIn(decision_id, self.ready_ids(result))
        self.assertNotIn(decision_id, self.blocked_ids(result))

    def test_the_decision_is_one_job_not_two(self):
        """A Decision already ready for the role gains no second item."""
        artifact_id, path = self.review_needing_the_analyst()
        esc = self.decided_package(artifact_id, path)
        decision_id = self.decision("DEC-2026-0021", esc, next_role="builder")
        result = self.scan()
        self.assertEqual(self.ready_ids(result).count(decision_id), 1)
        self.assertNotIn(artifact_id, self.ready_ids(result))


class TestOriginatingArtifactRefs(unittest.TestCase):
    """The resolver reads exact pairs only, in either spelling packages use."""

    def refs(self, block):
        return scanner._originating_artifact_refs(block)

    def test_kind_and_kind_path_pair(self):
        self.assertEqual(
            self.refs({"review": "REV-X-r01", "review_path": "books/x/REV-X-r01.yaml"}),
            [("REV-X-r01", "books/x/REV-X-r01.yaml")],
        )

    def test_nested_id_and_path_mapping(self):
        self.assertEqual(
            self.refs({"gup": {"id": "GUP-X-r02", "path": "books/x/GUP-X-r02.yaml"}}),
            [("GUP-X-r02", "books/x/GUP-X-r02.yaml")],
        )

    def test_a_list_of_mappings(self):
        self.assertEqual(
            self.refs({"gups": [{"id": "A", "path": "p/a"}, {"id": "B", "path": "p/b"}]}),
            [("A", "p/a"), ("B", "p/b")],
        )

    def test_an_id_without_a_path_yields_nothing(self):
        self.assertEqual(self.refs({"reviews": ["REV-X-r01", "REV-Y-r01"]}), [])
        self.assertEqual(self.refs({"gur": "GUR-X-r01"}), [])

    def test_a_path_without_an_id_yields_nothing(self):
        self.assertEqual(self.refs({"review_path": "books/x/REV-X-r01.yaml"}), [])

    def test_a_non_mapping_yields_nothing(self):
        self.assertEqual(self.refs(None), [])
        self.assertEqual(self.refs(["REV-X-r01"]), [])
