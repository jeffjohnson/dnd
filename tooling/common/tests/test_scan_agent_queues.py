from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import yaml


MODULE_PATH = Path(__file__).parents[1] / "scan_agent_queues.py"
SPEC = importlib.util.spec_from_file_location("scan_agent_queues", MODULE_PATH)
assert SPEC and SPEC.loader
scanner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scanner
SPEC.loader.exec_module(scanner)


class DiagnosticsConsoleFormattingTests(unittest.TestCase):
    def test_diagnostics_use_fixed_columns_and_wrapped_continuations(self):
        output = StringIO()
        with redirect_stdout(output):
            scanner._print_diagnostics_table(
                [
                    (
                        "severity-too-long",
                        "c" * 33,
                        "a" * 46,
                        "m" * 78 + " next",
                    )
                ]
            )

        lines = output.getvalue().splitlines()
        widths = (8, 32, 45, 80)
        self.assertEqual(
            lines[0],
            "  ".join(
                header.ljust(width)
                for header, width in zip(("Severity", "Code", "Artifact", "Message"), widths)
            ),
        )
        self.assertEqual(lines[1], "  ".join("-" * width for width in widths))
        self.assertEqual(
            lines[2],
            "  ".join(
                value.ljust(width)
                for value, width in zip(
                    ("severity", "c" * 32, "a" * 45, "m" * 78), widths
                )
            ),
        )
        self.assertEqual(
            lines[3],
            "  ".join(
                value.ljust(width)
                for value, width in zip(("", "c", "a", "next"), widths)
            ),
        )

    def test_message_wraps_only_at_whitespace(self):
        self.assertEqual(
            scanner._wrap_diagnostic_cell("x" * 81, 80, break_long_words=False),
            ["x" * 81],
        )


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


class SupersededApprovedBundleCase(QueueScannerCase):
    """An Approved bundle inherits the standing of the GUP it packages.

    WORK_QUEUES 3 says only the active leaf creates work and 6 says a superseded
    artifact is not ready work. The bundle was routed on its own account, so a
    bundle the Integrator had already rejected kept returning as ready after the
    Builder published a superseding revision -- and that particular batch, by
    the Integrator's own report, would have registered two nodes at degree zero.
    """

    PACKET = "PKT-PHB-001-002-fixture"

    def bundle(self, revision: int, gup_id: str, review_gup_as_mapping=True):
        approved_id = f"APPROVED-{gup_id}-r01"
        review_id = f"REV-{gup_id}-r01"
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/reviews/{review_id}.yaml",
            {
                "id": review_id, "packet_id": self.PACKET, "revision": 1,
                "status": "approved", "overall_disposition": "approved",
                "reviewed_gup": {"id": gup_id} if review_gup_as_mapping else gup_id,
            },
        )
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/approved/{approved_id}.yaml",
            {"id": approved_id, "packet_id": self.PACKET, "review_id": review_id,
             "gup_id": gup_id},
        )
        return approved_id

    def integrator_states(self, result):
        states = {}
        for key in ("Items", "InformationalItems", "BlockedItems"):
            for item in result.get(key, []):
                if item["Role"] == "Integrator":
                    states[item["InputId"]] = (item["State"], item["Queue"])
        return states

    def two_revisions(self, **kwargs):
        gur = self.gur(self.PACKET, 1)
        first = self.gup(self.PACKET, 1, gur)
        second = self.gup(self.PACKET, 2, gur, supersedes=first)
        return (self.bundle(1, first, **kwargs), self.bundle(2, second, **kwargs))

    def test_a_bundle_for_a_superseded_gup_is_not_ready_work(self):
        stale, current = self.two_revisions()
        states = self.integrator_states(self.scan())
        self.assertEqual(states[stale], ("informational", "INTEGRATOR-SUPERSEDED"))
        self.assertEqual(states[current][0], "ready")

    def test_the_reason_names_the_superseded_gup(self):
        stale, _ = self.two_revisions()
        item = next(
            i for i in self.scan()["InformationalItems"] if i["InputId"] == stale
        )
        self.assertIn("supersede", item["Reason"].lower())
        self.assertIn(f"GUP-{self.PACKET}-r01", item["Reason"])

    def test_the_bundle_is_not_deleted_or_moved(self):
        """It is history, and no role may remove an upstream artifact."""
        stale, _ = self.two_revisions()
        path = self.root / "books/adnd1e/phb/artifacts/approved" / f"{stale}.yaml"
        self.scan()
        self.assertTrue(path.is_file())

    def test_a_bundle_for_a_leaf_gup_is_untouched(self):
        gur = self.gur(self.PACKET, 1)
        only = self.gup(self.PACKET, 1, gur)
        approved = self.bundle(1, only)
        self.assertEqual(self.integrator_states(self.scan())[approved][0], "ready")

    def test_a_review_naming_its_gup_as_a_bare_string_is_read_too(self):
        stale, current = self.two_revisions(review_gup_as_mapping=False)
        states = self.integrator_states(self.scan())
        self.assertEqual(states[stale], ("informational", "INTEGRATOR-SUPERSEDED"))
        self.assertEqual(states[current][0], "ready")

    def test_a_bundle_naming_no_gup_at_all_still_routes(self):
        """A check that cannot read the ID must not guess the bundle is stale."""
        gur = self.gur(self.PACKET, 1)
        first = self.gup(self.PACKET, 1, gur)
        self.gup(self.PACKET, 2, gur, supersedes=first)
        approved_id = f"APPROVED-{first}-r01"
        review_id = f"REV-{first}-r01"
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/reviews/{review_id}.yaml",
            {"id": review_id, "packet_id": self.PACKET, "revision": 1,
             "status": "approved", "overall_disposition": "approved"},
        )
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/approved/{approved_id}.yaml",
            {"id": approved_id, "packet_id": self.PACKET, "review_id": review_id},
        )
        self.assertEqual(self.integrator_states(self.scan())[approved_id][0], "ready")


class BlockedGupOwnershipCase(QueueScannerCase):
    """A blocked GUP belongs to the role its handoff names.

    WORK_QUEUES defines `blocked` as "the named role cannot act until every
    blocking_id is resolved". The named role is in the artifact's own handoff.
    Filing every blocked GUP under Builder put patches the Builder is forbidden
    to fix -- an aspect-grain block needs the source reread, which is the
    Analyst's -- into the Builder queue, where they would have waited forever
    for a role that may not act on them.
    """

    PACKET = "PKT-PHB-001-002-fixture"

    def blocked_gup(self, next_role, blocking_ids):
        gur_id = self.gur(self.PACKET, 1)
        artifact_id = f"GUP-{self.PACKET}-r01"
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/gup/{artifact_id}.yaml",
            {
                "id": artifact_id,
                "packet_id": self.PACKET,
                "revision": 1,
                "supersedes": None,
                "status": "blocked",
                "approval_ready": False,
                "provenance": {"gur_id": gur_id},
                "escalations": [],
                "handoff": {
                    "next_role": next_role,
                    "readiness": "blocked",
                    "reason": "fixture",
                    "blocking_ids": blocking_ids,
                },
            },
        )
        (
            self.root / "books/adnd1e/phb/artifacts/gup" / f"{artifact_id}.edges.csv"
        ).write_text("source_id,target_id\n", encoding="utf-8")
        return artifact_id

    def blocked_items(self, result):
        return [i for i in result["BlockedItems"] if i["State"] == "blocked"]

    def test_a_gup_blocked_for_the_analyst_is_the_analysts(self):
        artifact_id = self.blocked_gup("analyst", [f"GUR-{self.PACKET}-r01"])
        items = self.blocked_items(self.scan())
        self.assertEqual([i["InputId"] for i in items], [artifact_id])
        self.assertEqual(items[0]["Role"], "Analyst")
        self.assertNotEqual(items[0]["Queue"], "BUILDER-BLOCKED")

    def test_a_gup_blocked_for_the_architect_is_the_architects(self):
        self.blocked_gup("architect", ["ESC-2026-01-01T00.00.00.000Z"])
        items = self.blocked_items(self.scan())
        self.assertEqual(items[0]["Role"], "Architect")

    def test_a_gup_naming_no_actionable_role_stays_with_the_builder(self):
        """Absent or unroutable, it must not vanish from every queue."""
        for next_role in ("none", "", "nonsense"):
            with self.subTest(next_role=next_role):
                self.setUp()
                self.blocked_gup(next_role, ["something"])
                items = self.blocked_items(self.scan())
                self.assertEqual(items[0]["Role"], "Builder")
                self.assertEqual(items[0]["Queue"], "BUILDER-BLOCKED")

    def test_the_blocked_item_still_names_what_it_waits_on(self):
        gur_id = f"GUR-{self.PACKET}-r01"
        self.blocked_gup("analyst", [gur_id])
        items = self.blocked_items(self.scan())
        self.assertIn(gur_id, items[0]["Reason"])

    def test_reassignment_does_not_turn_a_blocked_item_ready(self):
        self.blocked_gup("analyst", [f"GUR-{self.PACKET}-r01"])
        result = self.scan()
        self.assertEqual(
            [i for i in result["Items"] if i["InputId"] == f"GUP-{self.PACKET}-r01"], []
        )


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

    #: The scanners are compared against the live repository, so the comparison
    #: is only meaningful while the tree holds still. It does not always: an
    #: agent publishing artifacts in another process moved a GUP between the two
    #: invocations here, and the test reported a parity violation for what was
    #: only a fifteen-second gap. Bracketing the PowerShell run with two Python
    #: runs tells the two cases apart -- if the brackets disagree, the tree
    #: moved and this test has nothing to say about parity.
    KEYS = ("Items", "Diagnostics", "ReadyCount", "LineageErrorCount")

    def _scan(self, command):
        import subprocess

        done = subprocess.run(command, capture_output=True, text=True)
        return done.returncode, json.loads(done.stdout)

    def test_powershell_and_python_return_the_same_jobs_and_exit_code(self):
        shell = self._pwsh()
        if shell is None:
            self.skipTest("no PowerShell on PATH")

        python_command = [
            sys.executable, str(MODULE_PATH), "--root", str(self.REPO_ROOT), "--json"
        ]
        powershell_command = [
            shell, "-NoProfile", "-File", str(self.SCRIPT),
            "-Root", str(self.REPO_ROOT), "-Json",
        ]

        before_code, before = self._scan(python_command)
        actual_code, actual = self._scan(powershell_command)
        after_code, after = self._scan(python_command)

        if before_code != after_code or any(before[k] != after[k] for k in self.KEYS):
            self.skipTest(
                "the repository changed between scans; parity is not observable on a moving tree"
            )

        self.assertEqual(actual_code, before_code)
        for key in self.KEYS:
            self.assertEqual(actual[key], before[key], f"{key} differs")

    def test_a_moving_tree_is_reported_as_such_and_not_as_a_parity_violation(self):
        """The guard has to fire, or it is just a slower way to fail."""
        if self._pwsh() is None:
            self.skipTest("no PowerShell on PATH")

        empty = {key: ([] if key in ("Items", "Diagnostics") else 0) for key in self.KEYS}
        scans = [
            (0, dict(empty)),
            (0, dict(empty)),
            (0, dict(empty, ReadyCount=1)),  # the tree moved under the third scan
        ]
        case = TestScannerParity("test_powershell_and_python_return_the_same_jobs_and_exit_code")
        case._scan = lambda command: scans.pop(0)
        with self.assertRaises(unittest.SkipTest):
            case.test_powershell_and_python_return_the_same_jobs_and_exit_code()




class IntegratedMigrationDriftCase(MigrationFixtureMixin, QueueScannerCase):
    """A migration that has been applied is not a migration that needs re-issuing.

    Every decision migration pins the canonical baseline it was planned against,
    and the scanner refuses to route one whose baseline has moved -- applying such
    a plan would edit rows nobody reviewed. But a migration's whole purpose is to
    move that baseline, so the moment it integrates, its own pin is guaranteed
    stale.

    Before this rule the scanner reported every integrated migration as
    "Builder must re-issue it". Three of the five such errors in the live
    repository were finished transactions, including one integrated the same hour,
    which buried the two that were real.
    """

    DECISION = "DEC-2026-9801"
    MIGRATION = "GUP-MIG-DEC-2026-9801-r01"

    def integrate(self, artifact_id: str, *, review_revision=1) -> str:
        """Record an Approved bundle for `artifact_id` as integrated."""
        bundle = f"APPROVED-{artifact_id}-r{review_revision:02d}"
        path = self.root / "rulesets/adnd1e/manifests/INT-20260817-900.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        # Written as real JSON, not YAML under a .json name: the scanner parses a
        # manifest by its suffix, and a mismatch reports the manifest unreadable
        # rather than finding the bundle.
        path.write_text(
            json.dumps(
                {
                    "id": "INT-20260817-900",
                    "integration_id": "INT-20260817-900",
                    "status": "integrated",
                    "ruleset_id": "adnd1e",
                    "approved_bundles": [{"bundle_id": bundle, "gup_id": artifact_id}],
                },
                indent=2,
            ),
            encoding="utf-8",
            newline="\n",
        )
        return bundle

    def move_the_baseline(self) -> None:
        """What integrating the migration does to the file it was planned against."""
        (self.root / self.CANONICAL).write_text(
            "source_id,edge_type,target_id\na_b,GATES,c_d\ne_f,MODIFIES,g_h\n",
            encoding="utf-8",
        )

    def build(self, *, integrated: bool, moved: bool) -> dict:
        self.decision(self.DECISION)
        self.migration(self.MIGRATION, [self.DECISION])
        if integrated:
            self.integrate(self.MIGRATION)
        if moved:
            self.move_the_baseline()
        return self.scan()

    def drift_errors(self, result) -> list[str]:
        return [
            d["ArtifactId"]
            for d in result["Diagnostics"]
            if d["Code"] == "decision_migration_lineage_error"
            and "baseline that has since changed" in d["Message"]
        ]

    def test_an_integrated_migration_with_a_moved_baseline_is_not_an_error(self):
        self.assertEqual(self.drift_errors(self.build(integrated=True, moved=True)), [])

    def test_an_integrated_migration_creates_no_builder_work(self):
        """It is finished: neither the GUP nor its authority Decision is a job."""
        result = self.build(integrated=True, moved=True)
        builder = [i["InputId"] for i in result["Items"] if i["Role"] == "Builder"]
        self.assertNotIn(self.MIGRATION, builder)
        self.assertNotIn(self.DECISION, builder)

    def test_an_unintegrated_migration_with_a_moved_baseline_is_still_an_error(self):
        """The check that matters is untouched: a stale plan must not be routed."""
        self.assertEqual(
            self.drift_errors(self.build(integrated=False, moved=True)), [self.MIGRATION]
        )

    def test_an_integrated_migration_whose_baseline_stands_is_still_clean(self):
        self.assertEqual(self.drift_errors(self.build(integrated=True, moved=False)), [])

    def test_integration_does_not_excuse_any_other_defect(self):
        """Only the baseline reason is dropped, and only because integration moved it."""
        self.decision(self.DECISION)
        self.migration(
            self.MIGRATION,
            [self.DECISION],
            extra_provenance={"gur_id": "GUR-PKT-PHB-001-002-x-r01"},
        )
        self.integrate(self.MIGRATION)
        self.move_the_baseline()
        messages = [
            d["Message"]
            for d in self.scan()["Diagnostics"]
            if d["Code"] == "decision_migration_lineage_error"
        ]
        self.assertTrue(
            any("provenance.gur_id" in message for message in messages), messages
        )
        self.assertFalse(
            any("baseline that has since changed" in message for message in messages),
            messages,
        )

    def test_an_integrated_migration_with_an_unapproved_authority_is_still_reported(self):
        self.decision(self.DECISION, status="proposed")
        self.migration(self.MIGRATION, [self.DECISION])
        self.integrate(self.MIGRATION)
        self.move_the_baseline()
        messages = [
            d["Message"]
            for d in self.scan()["Diagnostics"]
            if d["Code"] == "decision_migration_lineage_error"
        ]
        self.assertTrue(messages, "an unapproved authority is a defect after integration too")
        self.assertFalse(
            any("baseline that has since changed" in message for message in messages),
            messages,
        )

    def test_the_suppressed_reason_is_the_one_named_in_the_module(self):
        """Pins the test to the constant, so rewording it cannot silently unhook this."""
        self.assertIn("baseline that has since changed", scanner.BASELINE_MOVED_REASON)
        self.assertIn("re-issue", scanner.BASELINE_MOVED_REASON)


class IntegrationRejectionCase(QueueScannerCase):
    """DEC-2026-0043: an Integrator rejection is a queue signal, not a report.

    Before this rule a rejected bundle stayed in the Integrator queue and was
    offered again unchanged. `illusionist-spells-r04-r01` was refused four times
    on identical bytes across five days, because nothing in the repository turned
    "this was refused" into work for the role that could repair it.

    The load-bearing half is refusal. A rejection retires an approved bundle, so
    evidence that cannot be trusted -- unreadable, wrong ruleset, superseded,
    ambiguous, or pinned to checksums that have moved -- must leave the bundle
    exactly where it was. A malformed rejection that could suppress integration
    would be a way to silently cancel approved work.
    """

    PACKET = "PKT-PHB-001-002-fixture"

    #: Built on first use rather than in setUp. This case subclasses
    #: QueueScannerCase for its fixture helpers and therefore inherits its tests
    #: too, and those assert against an empty repository -- creating a bundle for
    #: every test would fail them for reasons unrelated to what they check.
    _built = False

    def build(self):
        if self._built:
            return
        self._built = True
        (self.root / "rulesets" / "adnd1e" / "reports").mkdir(parents=True, exist_ok=True)
        self.gur_id = self.gur(self.PACKET, 1)
        self.gup_id = self.gup(self.PACKET, 1, self.gur_id)
        self.review_id = self.review(self.PACKET, self.gup_id)
        self.bundle_id = f"APPROVED-{self.gup_id}-r01"
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/approved/{self.bundle_id}.yaml",
            {
                "id": self.bundle_id,
                "packet_id": self.PACKET,
                "review_id": self.review_id,
                "gup_id": self.gup_id,
            },
        )
        (self.root / "books/adnd1e/phb/artifacts/approved" / f"{self.bundle_id}.edges.csv").write_text(
            "source_id,target_id\n", encoding="utf-8"
        )

    def checksum(self, relative: str) -> str:
        return scanner._sha256_of(self.root / relative)

    def rejection(self, record_id="INT-20260817-900", **overrides) -> Path:
        self.build()
        entry = {
            "bundle_id": self.bundle_id,
            "bundle_checksum": self.checksum(
                f"books/adnd1e/phb/artifacts/approved/{self.bundle_id}.yaml"
            ),
            "review_id": self.review_id,
            "review_checksum": self.checksum(
                f"books/adnd1e/phb/artifacts/reviews/{self.review_id}.yaml"
            ),
            "gup_id": self.gup_id,
            "gup_checksum": self.checksum(
                f"books/adnd1e/phb/artifacts/gup/{self.gup_id}.yaml"
            ),
            "blocking_failures": [
                {
                    "check": "operation index classifies every CSV row exactly once",
                    "result": "fail",
                    "blocking": True,
                    "detail": "csv_row missing on 126 entries",
                }
            ],
        }
        entry.update(overrides.pop("entry", {}))
        document = {
            "schema_version": "1.0",
            "id": record_id,
            "status": "rejected",
            "ruleset_id": "adnd1e",
            "book_id": "phb",
            "revision": 1,
            "supersedes": None,
            "rejected_bundles": [entry],
        }
        document.update(overrides)
        path = self.root / "rulesets" / "adnd1e" / "reports" / f"{record_id}.rejected.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2), encoding="utf-8", newline="\n")
        return path

    def queued(self, result, queue):
        return [i["InputId"] for i in result["Items"] if i["Queue"] == queue]

    def coded(self, result, code):
        return [d for d in result["Diagnostics"] if d["Code"] == code]

    # -- acceptance test 1 --------------------------------------------------

    def test_a_valid_rejection_suppresses_only_that_bundle(self):
        self.rejection()
        result = self.scan()
        self.assertEqual(self.queued(result, "INTEGRATOR-APPROVED"), [])
        self.assertEqual(
            self.queued(result, "REVIEWER-INTEGRATION-REJECTION"), [self.bundle_id]
        )

    def test_a_second_unrejected_bundle_is_untouched(self):
        """Suppression is per bundle, never per book or per queue."""
        self.build()
        other_gur = self.gur("PKT-PHB-003-004-other", 1)
        other_gup = self.gup("PKT-PHB-003-004-other", 1, other_gur)
        other_review = self.review("PKT-PHB-003-004-other", other_gup)
        other_bundle = f"APPROVED-{other_gup}-r01"
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/approved/{other_bundle}.yaml",
            {"id": other_bundle, "packet_id": "PKT-PHB-003-004-other",
             "review_id": other_review, "gup_id": other_gup},
        )
        self.rejection()
        result = self.scan()
        self.assertEqual(self.queued(result, "INTEGRATOR-APPROVED"), [other_bundle])

    def test_the_remediation_item_names_the_failing_check(self):
        self.rejection()
        item = next(
            i for i in self.scan()["Items"] if i["Queue"] == "REVIEWER-INTEGRATION-REJECTION"
        )
        self.assertEqual(item["Role"], "Reviewer")
        self.assertIn("operation index classifies every CSV row exactly once", item["Reason"])
        self.assertIn("INT-20260817-900", item["Reason"])

    def test_exactly_one_remediation_item_is_created(self):
        self.rejection()
        self.assertEqual(
            len(self.queued(self.scan(), "REVIEWER-INTEGRATION-REJECTION")), 1
        )

    # -- acceptance test 2: untrustworthy evidence suppresses nothing --------

    def assert_suppresses_nothing(self, result, code="integration_rejection_invalid"):
        self.build()
        self.assertEqual(self.queued(result, "INTEGRATOR-APPROVED"), [self.bundle_id])
        self.assertEqual(self.queued(result, "REVIEWER-INTEGRATION-REJECTION"), [])
        self.assertTrue(self.coded(result, code))

    def test_a_missing_checksum_suppresses_nothing(self):
        self.rejection(entry={"bundle_checksum": None})
        self.assert_suppresses_nothing(self.scan())

    def test_a_stale_checksum_suppresses_nothing(self):
        self.rejection(entry={"gup_checksum": "sha256:" + "0" * 64})
        self.assert_suppresses_nothing(self.scan())

    def test_a_missing_blocking_failure_suppresses_nothing(self):
        """A rejection stating no failing check directs no repair."""
        self.rejection(entry={"blocking_failures": []})
        self.assert_suppresses_nothing(self.scan())

    def test_a_wrong_ruleset_record_suppresses_nothing(self):
        self.rejection(ruleset_id="other")
        self.assert_suppresses_nothing(self.scan())

    def test_a_record_that_is_not_a_rejection_suppresses_nothing(self):
        self.rejection(status="integrated")
        self.assert_suppresses_nothing(self.scan())

    def test_unreadable_json_suppresses_nothing(self):
        path = self.rejection()
        path.write_text("{not json", encoding="utf-8")
        self.assert_suppresses_nothing(self.scan(), "integration_rejection_unreadable")

    def test_a_superseded_record_suppresses_nothing(self):
        """A later record is the current word; the earlier one is history."""
        self.rejection(record_id="INT-20260817-900")
        self.write_yaml_json = None
        path = self.root / "rulesets/adnd1e/reports/INT-20260817-901.rejected.json"
        document = json.loads(
            (self.root / "rulesets/adnd1e/reports/INT-20260817-900.rejected.json").read_text(
                encoding="utf-8"
            )
        )
        document["id"] = "INT-20260817-901"
        document["supersedes"] = "INT-20260817-900"
        document["rejected_bundles"] = []
        path.write_text(json.dumps(document, indent=2), encoding="utf-8", newline="\n")
        result = self.scan()
        self.assertEqual(self.queued(result, "INTEGRATOR-APPROVED"), [self.bundle_id])
        self.assertEqual(self.queued(result, "REVIEWER-INTEGRATION-REJECTION"), [])

    def test_two_disagreeing_records_suppress_nothing(self):
        """Choosing between two live rejections is not a queue decision."""
        self.rejection(record_id="INT-20260817-900")
        self.rejection(record_id="INT-20260817-901")
        result = self.scan()
        self.assertEqual(self.queued(result, "INTEGRATOR-APPROVED"), [self.bundle_id])
        self.assertEqual(self.queued(result, "REVIEWER-INTEGRATION-REJECTION"), [])
        self.assertTrue(self.coded(result, "integration_rejection_ambiguous"))

    def test_a_rejection_of_a_superseded_bundle_is_silent(self):
        """History needs no report: that bundle produces no Integrator item."""
        self.build()
        self.gup(self.PACKET, 2, self.gur_id, supersedes=self.gup_id)
        self.rejection()
        result = self.scan()
        self.assertEqual(self.coded(result, "integration_rejection_invalid"), [])
        self.assertEqual(self.queued(result, "REVIEWER-INTEGRATION-REJECTION"), [])

    # -- acceptance test 3: a Review successor consumes the item -------------

    def test_a_review_successor_recording_the_rejection_consumes_the_item(self):
        self.rejection()
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/reviews/REV-{self.gup_id}-r02.yaml",
            {
                "id": f"REV-{self.gup_id}-r02",
                "packet_id": self.PACKET,
                "revision": 2,
                "supersedes": self.review_id,
                "status": "revision_required",
                "overall_disposition": "revision_required",
                "reviewed_gup": {"id": self.gup_id},
                "integration_rejection": {"id": "INT-20260817-900"},
            },
        )
        result = self.scan()
        self.assertEqual(self.queued(result, "REVIEWER-INTEGRATION-REJECTION"), [])

    def test_a_successor_naming_another_rejection_does_not_consume_it(self):
        """Matching is on the exact record: postdating it is not reading it."""
        self.rejection()
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/reviews/REV-{self.gup_id}-r02.yaml",
            {
                "id": f"REV-{self.gup_id}-r02",
                "packet_id": self.PACKET,
                "revision": 2,
                "supersedes": self.review_id,
                "status": "revision_required",
                "overall_disposition": "revision_required",
                "reviewed_gup": {"id": self.gup_id},
                "integration_rejection": {"id": "INT-20260101-001"},
            },
        )
        self.assertEqual(
            self.queued(self.scan(), "REVIEWER-INTEGRATION-REJECTION"), [self.bundle_id]
        )

    # -- the bounded legacy authorization -----------------------------------

    def test_the_legacy_allowance_is_pinned_to_one_record_and_bundle(self):
        """DEC-2026-0043 names an exact pair; it must not spread."""
        self.assertEqual(
            scanner.LEGACY_AUTHORIZED_REJECTIONS,
            {
                (
                    "INT-20260815-002",
                    "APPROVED-GUP-PKT-PHB-094-100-illusionist-spells-r04-r01",
                )
            },
        )

    def test_an_unchecksummed_record_outside_the_allowance_suppresses_nothing(self):
        self.rejection(
            record_id="INT-20260815-002",
            entry={"bundle_checksum": None, "review_checksum": None, "gup_checksum": None},
        )
        self.assert_suppresses_nothing(self.scan())


class DirectImplementationOwnerCase(QueueScannerCase):
    """DEC-2026-0043: a non-migration Decision may be owned by Builder or Integrator.

    The owner is whichever role the ready handoff names, and exactly one role owns
    a Decision. A report claiming the other role is diagnostic rather than a
    silent reassignment: who implemented a Decision is part of what the
    independent Review verifies.
    """

    DECISION = "DEC-2026-9901"

    def decision(self, *, next_role="integrator"):
        self.write_yaml(
            f"rulesets/adnd1e/escalations/decisions/{self.DECISION}.yaml",
            {
                "id": self.DECISION,
                "status": "approved",
                "ruleset_id": "adnd1e",
                "book_id": "phb",
                "migration_required": False,
                "acceptance_tests": ["the tool behaves as ruled"],
                "handoff": {
                    "next_role": next_role,
                    "readiness": "ready",
                    "reason": "implement it",
                    "blocking_ids": [],
                },
            },
        )

    def report(self, *, implemented_by="integrator", revision=1):
        report_id = f"IMP-{self.DECISION}-r{revision:02d}"
        target = "tooling/common/scan_agent_queues.py"
        self.write_yaml(
            f"rulesets/adnd1e/decision-implementations/{report_id}.yaml",
            {
                "id": report_id,
                "artifact_kind": "decision_implementation",
                "status": "proposed",
                "ruleset_id": "adnd1e",
                "revision": revision,
                "supersedes": None,
                "approval_ready": True,
                "implemented_by": implemented_by,
                "decision_input": {
                    "id": self.DECISION,
                    "path": f"rulesets/adnd1e/escalations/decisions/{self.DECISION}.yaml",
                    "checksum": scanner._sha256_of(
                        self.root
                        / f"rulesets/adnd1e/escalations/decisions/{self.DECISION}.yaml"
                    ),
                },
                "implementation_files": [
                    {"path": target, "checksum": scanner._sha256_of(self.root / target)}
                ],
                "acceptance_results": [
                    {"acceptance_test_index": 1, "result": "passed", "evidence": "verified"}
                ],
                "handoff": {
                    "next_role": "reviewer",
                    "readiness": "ready",
                    "reason": "ready for review",
                    "blocking_ids": [],
                },
                "validation": {
                    "passed": True,
                    "commands": [
                        {"command": "suite", "exit_code": 0, "result": "passed",
                         "summary": "Ran 1 test OK"}
                    ],
                },
            },
        )
        return report_id

    def setUp(self):
        super().setUp()
        target = self.root / "tooling/common/scan_agent_queues.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# fixture\n", encoding="utf-8")

    def queued(self, result, queue):
        return [i["InputId"] for i in result["Items"] if i["Queue"] == queue]

    def test_an_integrator_decision_creates_an_integrator_item(self):
        self.decision(next_role="integrator")
        result = self.scan()
        self.assertEqual(self.queued(result, "INTEGRATOR-DECISION"), [self.DECISION])
        self.assertEqual(self.queued(result, "BUILDER-DECISION"), [])

    def test_a_builder_decision_still_creates_a_builder_item(self):
        self.decision(next_role="builder")
        result = self.scan()
        self.assertEqual(self.queued(result, "BUILDER-DECISION"), [self.DECISION])
        self.assertEqual(self.queued(result, "INTEGRATOR-DECISION"), [])

    def test_a_valid_integrator_report_routes_to_reviewer(self):
        self.decision(next_role="integrator")
        report_id = self.report(implemented_by="integrator")
        result = self.scan()
        self.assertEqual(
            self.queued(result, "REVIEWER-DECISION-IMPLEMENTATION"), [report_id]
        )
        self.assertEqual(self.queued(result, "INTEGRATOR-DECISION"), [])

    def test_a_builder_report_for_an_integrator_decision_is_diagnostic(self):
        self.decision(next_role="integrator")
        self.report(implemented_by="builder")
        result = self.scan()
        codes = [d["Code"] for d in result["Diagnostics"]]
        self.assertIn("decision_implementation_invalid", codes)
        message = next(
            d["Message"]
            for d in result["Diagnostics"]
            if d["Code"] == "decision_implementation_invalid"
        )
        self.assertIn("implemented_by", message)
        # The Decision is not consumed by a report that misstates its owner.
        self.assertEqual(self.queued(result, "INTEGRATOR-DECISION"), [self.DECISION])
        self.assertEqual(self.queued(result, "REVIEWER-DECISION-IMPLEMENTATION"), [])

    def test_an_integrator_report_for_a_builder_decision_is_diagnostic(self):
        self.decision(next_role="builder")
        self.report(implemented_by="integrator")
        result = self.scan()
        self.assertIn(
            "decision_implementation_invalid",
            [d["Code"] for d in result["Diagnostics"]],
        )
        self.assertEqual(self.queued(result, "BUILDER-DECISION"), [self.DECISION])

    def test_an_approved_review_consumes_the_decision_and_makes_no_batch(self):
        self.decision(next_role="integrator")
        report_id = self.report(implemented_by="integrator")
        report_relative = f"rulesets/adnd1e/decision-implementations/{report_id}.yaml"
        decision_relative = (
            f"rulesets/adnd1e/escalations/decisions/{self.DECISION}.yaml"
        )
        self.write_yaml(
            f"rulesets/adnd1e/decision-implementation-reviews/REV-{report_id}-r01.yaml",
            {
                "id": f"REV-{report_id}-r01",
                "artifact_kind": "decision_implementation_review",
                "status": "approved",
                "ruleset_id": "adnd1e",
                "revision": 1,
                "supersedes": None,
                "reviewed_by": "reviewer",
                "reviewed_implementation": {
                    "id": report_id,
                    "path": report_relative,
                    "checksum": scanner._sha256_of(self.root / report_relative),
                },
                "decision_input": {
                    "id": self.DECISION,
                    "path": decision_relative,
                    "checksum": scanner._sha256_of(self.root / decision_relative),
                },
                "overall_disposition": "approved",
                "acceptance_dispositions": [
                    {"acceptance_test_index": 1, "disposition": "verified",
                     "evidence": "independently reproduced"}
                ],
                "independent_validation": {
                    "passed": True,
                    "commands": [
                        {"command": "suite", "exit_code": 0, "result": "passed",
                         "summary": "Ran 1 test OK"}
                    ],
                },
                "handoff": {
                    "next_role": "none",
                    "readiness": "terminal",
                    "reason": "verified",
                    "blocking_ids": [],
                },
            },
        )
        result = self.scan()
        self.assertEqual(self.queued(result, "INTEGRATOR-DECISION"), [])
        self.assertEqual(self.queued(result, "REVIEWER-DECISION-IMPLEMENTATION"), [])
        self.assertEqual(self.queued(result, "INTEGRATOR-APPROVED"), [])

    def test_the_owner_set_is_exactly_builder_and_integrator(self):
        """Never Analyst, Reviewer or Architect: this lifecycle is bounded."""
        self.assertEqual(
            scanner.DIRECT_IMPLEMENTATION_OWNERS, frozenset({"builder", "integrator"})
        )


class CorrectionSequencedRebuildCase(QueueScannerCase):
    """A Decision that hands a Review a correction orders that revision first.

    The sibling rule reads a Decision naming a routing Review that does not exist
    yet. This one names a Review that does -- the current leaf -- and states the
    exact correction the Reviewer must apply to it, so what is missing is the
    revision rather than the file.

    DEC-2026-0037 is that shape: it replaces the Bards M048 row with an assertion
    naming `item_pipes_of_sewers`, the identity its own migration created, and
    sequences the Reviewer revision ahead of the Builder rebuild. Both halves of
    this case were invisible to the queue. The correction shape was not read at
    all, and the governing Decision could not even be reached: the escalation was
    answered by DEC-2026-0030 and reissued twice, and only the leaf carries the
    corrected identity. So the rebuild showed ready while the instruction set it
    needed did not exist, and compiling against the stale Review would have
    emitted the exact retired ID the migration existed to remove.
    """

    PACKET = "PKT-PHB-001-002-fixture"
    ESCALATION = "ESC-2026-01-01T00.00.00.000Z"
    CORRECTION = "M048"

    def build(self, *, chain=(), correction=True, publish_successor=False):
        """`chain` is the reissue lineage following the answering Decision."""
        gur_id = self.gur(self.PACKET, 1)
        gup_id = self.gup(self.PACKET, 1, gur_id)
        review_id = f"REV-{gup_id}-r01"
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/reviews/{review_id}.yaml",
            {
                "id": review_id,
                "packet_id": self.PACKET,
                "revision": 1,
                "status": "architect_escalation",
                "overall_disposition": "architect_escalation",
                "reviewed_gup": {"id": gup_id},
                "architectural_escalations": [{"id": self.ESCALATION}],
                "handoff": {
                    "next_role": "architect",
                    "readiness": "ready",
                    "blocking_ids": [],
                },
            },
        )

        lineage = ["DEC-2026-9101", *chain]
        for index, decision_id in enumerate(lineage):
            is_leaf = index == len(lineage) - 1
            document = {
                "id": decision_id,
                "status": "approved",
                "ruleset_id": "adnd1e",
                "book_id": "phb",
                "packet_id": self.PACKET,
                "migration_required": False,
                "revision": index + 1,
                "supersedes": lineage[index - 1] if index else None,
                # Only the first Decision answers the Review escalation. A reissue
                # answers its own, which is exactly why the chain must be followed.
                "escalation_id": (
                    self.ESCALATION
                    if index == 0
                    else f"ESC-2026-02-0{index}T00.00.00.000Z"
                ),
                "handoff": {
                    "next_role": "builder",
                    "readiness": "ready",
                    "reason": "the Architect has ruled",
                    "blocking_ids": [],
                },
            }
            if is_leaf and correction:
                document["affected_artifacts"] = {
                    "review_to_revise_after_integration": {
                        "id": review_id,
                        "path": f"books/adnd1e/phb/artifacts/reviews/{review_id}.yaml",
                        "correction_id": self.CORRECTION,
                        "replacement_assertion": {
                            "source_id": "class_bard",
                            "target_id": "item_pipes_of_sewers",
                        },
                    }
                }
            self.write_yaml(
                f"rulesets/adnd1e/escalations/decisions/{decision_id}.yaml", document
            )

        if publish_successor:
            self.write_yaml(
                f"books/adnd1e/phb/artifacts/reviews/REV-{gup_id}-r02.yaml",
                {
                    "id": f"REV-{gup_id}-r02",
                    "packet_id": self.PACKET,
                    "revision": 2,
                    "supersedes": review_id,
                    "status": "revision_required",
                    "overall_disposition": "revision_required",
                    "reviewed_gup": {"id": gup_id},
                    "row_decisions": [
                        {
                            "ref": self.CORRECTION,
                            "disposition": "approved_with_revision",
                            "exact_corrections": {"target_id": "item_pipes_of_sewers"},
                        }
                    ],
                    "handoff": {
                        "next_role": "builder",
                        "readiness": "ready",
                        "blocking_ids": [],
                    },
                },
            )
        return review_id, self.scan()

    def builder(self, result, state):
        key = "BlockedItems" if state == "blocked" else "Items"
        return {
            (item["Queue"], item["InputId"])
            for item in result[key]
            if item["State"] == state and item["Role"] == "Builder"
        }

    def reason(self, result):
        return next(
            item["Reason"]
            for item in result["BlockedItems"]
            if item["Queue"] == "BUILDER-REVISION-BLOCKED"
        )

    def test_a_named_correction_blocks_the_rebuild(self):
        review_id, result = self.build()
        self.assertIn(
            ("BUILDER-REVISION-BLOCKED", review_id), self.builder(result, "blocked")
        )
        # The Decision itself is still ordinary Builder work -- it has no
        # implementation report here. Only the rebuild is held.
        self.assertNotIn(
            ("BUILDER-REVISION", review_id), self.builder(result, "ready")
        )

    def test_the_block_names_the_correction_and_the_decision(self):
        _, result = self.build()
        reason = self.reason(result)
        self.assertIn(self.CORRECTION, reason)
        self.assertIn("DEC-2026-9101", reason)
        self.assertIn("successor", reason)

    def test_a_reissued_decision_is_followed_to_its_leaf(self):
        """The correction sits on the leaf, which answers a different escalation."""
        review_id, result = self.build(chain=("DEC-2026-9102", "DEC-2026-9103"))
        self.assertIn(
            ("BUILDER-REVISION-BLOCKED", review_id), self.builder(result, "blocked")
        )
        self.assertIn("DEC-2026-9103", self.reason(result))

    def test_publishing_the_successor_review_unblocks_the_rebuild(self):
        """Once the leaf Review is the successor, the entry stops matching."""
        _, result = self.build(publish_successor=True)
        self.assertEqual(self.builder(result, "blocked"), set())
        self.assertTrue(
            any(
                queue == "BUILDER-REVISION"
                for queue, _ in self.builder(result, "ready")
            )
        )

    def test_a_decision_naming_the_review_without_a_correction_does_not_block(self):
        """Merely mentioning a Review says nothing about ordering."""
        _, result = self.build(correction=False)
        self.assertEqual(self.builder(result, "blocked"), set())

    def test_a_correction_for_another_artifact_does_not_block(self):
        self.build(correction=False)
        relative = "rulesets/adnd1e/escalations/decisions/DEC-2026-9101.yaml"
        document = yaml.safe_load((self.root / relative).read_text(encoding="utf-8"))
        document["affected_artifacts"] = {
            "other": {"id": "REV-SOMETHING-ELSE-r01", "correction_id": "M001"}
        }
        self.write_yaml(relative, document)
        self.assertEqual(self.builder(self.scan(), "blocked"), set())

class GurHandoffRoutingCase(QueueScannerCase):
    """DEC-2026-0039 / WORK_QUEUES 1.11: where a GUR's handoff sends its work.

    A handoff that is *present but malformed* is positive evidence of a broken
    workflow, not the missing metadata a legacy artifact has. The distinction is
    load-bearing: routing a malformed GUR under the legacy rules produced an
    ordinary Builder job, and Builder is the one role forbidden to repair a
    published GUR. `GUR-PKT-UA-015-015-cavaliers-r02` sat in that queue while its
    invalidity held the common schema suite red and, through it, blocked seven
    Decision implementation lineages.
    """

    PACKET = "PKT-PHB-001-002-fixture"

    #: The exact defect the UA artifact carried: a readiness value outside the
    #: envelope enum, and a null where the enum wants the string `none`.
    CAVALIERS_HANDOFF = {
        "next_role": None,
        "readiness": "withdrawn",
        "reason": "Superseded by PKT-UA-014-016-cavalier; produces no Builder job.",
        "blocking_ids": [],
    }
    TERMINAL_HANDOFF = {
        "next_role": "none",
        "readiness": "terminal",
        "reason": "Superseded by PKT-PHB-001-003-replacement.",
        "blocking_ids": [],
    }
    READY_HANDOFF = {
        "next_role": "builder",
        "readiness": "ready",
        "reason": "analysis complete",
        "blocking_ids": [],
    }

    def gur_with_handoff(self, revision, handoff, *, supersedes=None, packet=None):
        packet = packet or self.PACKET
        artifact_id = f"GUR-{packet}-r{revision:02d}"
        document = {
            "id": artifact_id,
            "packet_id": packet,
            "revision": revision,
            "supersedes": supersedes,
        }
        if handoff is not None:
            document["handoff"] = handoff
        self.write_yaml(f"books/adnd1e/phb/artifacts/gur/{artifact_id}.yaml", document)
        return artifact_id

    def routed(self, result, queue):
        return [item["InputId"] for item in result["Items"] if item["Queue"] == queue]

    def coded(self, result, code):
        return [d for d in result["Diagnostics"] if d["Code"] == code]

    # -- acceptance test 1: the current r02 fixture -------------------------

    def test_a_malformed_leaf_routes_only_as_an_analyst_repair(self):
        first = self.gur_with_handoff(1, self.READY_HANDOFF)
        leaf = self.gur_with_handoff(2, self.CAVALIERS_HANDOFF, supersedes=first)
        result = self.scan()
        self.assertEqual(self.routed(result, "ANALYST-GUR-REPAIR"), [leaf])
        self.assertEqual(self.routed(result, "BUILDER-GUR"), [])

    def test_the_repair_item_is_ready_analyst_work(self):
        self.gur_with_handoff(1, self.CAVALIERS_HANDOFF)
        item = next(
            i for i in self.scan()["Items"] if i["Queue"] == "ANALYST-GUR-REPAIR"
        )
        self.assertEqual(item["Role"], "Analyst")
        self.assertEqual(item["State"], "ready")
        self.assertIn("successor", item["Reason"])

    def test_exactly_one_error_diagnostic_names_the_invalid_fields(self):
        leaf = self.gur_with_handoff(1, self.CAVALIERS_HANDOFF)
        found = self.coded(self.scan(), "gur_invalid_handoff")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["Severity"], "error")
        self.assertEqual(found[0]["ArtifactId"], leaf)
        self.assertIn("readiness is 'withdrawn'", found[0]["Message"])
        self.assertIn("next_role is None", found[0]["Message"])
        self.assertIn("Analyst", found[0]["Message"])

    def test_a_malformed_leaf_gets_no_legacy_inference(self):
        """A present handoff is never a legacy omission."""
        self.gur_with_handoff(1, self.CAVALIERS_HANDOFF)
        result = self.scan()
        self.assertEqual(self.coded(result, "legacy_handoff_inference"), [])
        self.assertFalse(any(i["LegacyInference"] for i in result["Items"]))

    # -- acceptance test 2: a conforming terminal withdrawal ----------------

    def test_a_terminal_leaf_creates_no_work_at_all(self):
        self.gur_with_handoff(1, self.TERMINAL_HANDOFF)
        result = self.scan()
        self.assertEqual(self.routed(result, "BUILDER-GUR"), [])
        self.assertEqual(self.routed(result, "ANALYST-GUR-REPAIR"), [])
        self.assertEqual(self.coded(result, "gur_invalid_handoff"), [])

    def test_a_terminal_leaf_needs_no_gup_to_retire_it(self):
        """The withdrawal is complete on its own; an empty GUP would be noise."""
        self.gur_with_handoff(1, self.TERMINAL_HANDOFF)
        self.assertEqual([i for i in self.scan()["Items"] if i["Role"] == "Builder"], [])

    # -- acceptance test 3: legacy and ordinary routing are unchanged -------

    def test_a_gur_with_no_handoff_keeps_builder_routing(self):
        leaf = self.gur_with_handoff(1, None)
        result = self.scan()
        self.assertEqual(self.routed(result, "BUILDER-GUR"), [leaf])
        self.assertEqual(self.routed(result, "ANALYST-GUR-REPAIR"), [])

    def test_a_gur_with_no_handoff_reports_the_inference(self):
        leaf = self.gur_with_handoff(1, None)
        result = self.scan()
        found = self.coded(result, "legacy_handoff_inference")
        self.assertEqual([d["ArtifactId"] for d in found], [leaf])
        item = next(i for i in result["Items"] if i["Queue"] == "BUILDER-GUR")
        self.assertTrue(item["LegacyInference"])

    def test_a_valid_ready_gur_routes_to_builder_without_a_diagnostic(self):
        leaf = self.gur_with_handoff(1, self.READY_HANDOFF)
        result = self.scan()
        self.assertEqual(self.routed(result, "BUILDER-GUR"), [leaf])
        self.assertEqual(self.coded(result, "gur_invalid_handoff"), [])
        self.assertEqual(self.coded(result, "legacy_handoff_inference"), [])
        item = next(i for i in result["Items"] if i["Queue"] == "BUILDER-GUR")
        self.assertFalse(item["LegacyInference"])

    # -- acceptance test 4: only the leaf is repairable work ----------------

    def test_a_malformed_non_leaf_is_diagnosed_but_creates_no_repair_item(self):
        stale = self.gur_with_handoff(1, self.CAVALIERS_HANDOFF)
        self.gur_with_handoff(2, self.TERMINAL_HANDOFF, supersedes=stale)
        result = self.scan()
        self.assertEqual(
            [d["ArtifactId"] for d in self.coded(result, "gur_invalid_handoff")], [stale]
        )
        self.assertEqual(self.routed(result, "ANALYST-GUR-REPAIR"), [])
        self.assertEqual(self.routed(result, "BUILDER-GUR"), [])

    def test_the_repair_follows_the_leaf_when_the_successor_is_also_malformed(self):
        stale = self.gur_with_handoff(1, self.CAVALIERS_HANDOFF)
        leaf = self.gur_with_handoff(2, self.CAVALIERS_HANDOFF, supersedes=stale)
        result = self.scan()
        self.assertEqual(
            sorted(d["ArtifactId"] for d in self.coded(result, "gur_invalid_handoff")),
            sorted([stale, leaf]),
        )
        self.assertEqual(self.routed(result, "ANALYST-GUR-REPAIR"), [leaf])

    def test_a_consumed_malformed_leaf_is_still_diagnosed(self):
        """An invalid artifact is invalid whether or not a GUP consumed it."""
        leaf = self.gur_with_handoff(1, self.CAVALIERS_HANDOFF)
        self.gup(self.PACKET, 1, leaf)
        result = self.scan()
        self.assertEqual(
            [d["ArtifactId"] for d in self.coded(result, "gur_invalid_handoff")], [leaf]
        )

    # -- the malformed shapes, one per envelope invariant -------------------

    def test_each_nonconforming_shape_is_refused(self):
        cases = {
            "unknown readiness": dict(self.READY_HANDOFF, readiness="withdrawn"),
            "null role": dict(self.READY_HANDOFF, next_role=None),
            "unknown role": dict(self.READY_HANDOFF, next_role="steward"),
            "empty reason": dict(self.READY_HANDOFF, reason="  "),
            "terminal with a role": dict(self.TERMINAL_HANDOFF, next_role="builder"),
            "ready with blockers": dict(self.READY_HANDOFF, blocking_ids=["ESC-1"]),
            "blocked with none": dict(
                self.READY_HANDOFF, readiness="blocked", blocking_ids=[]
            ),
            "extra field": dict(self.READY_HANDOFF, owner="analyst"),
            "blocking_ids not a list": dict(self.READY_HANDOFF, blocking_ids="ESC-1"),
            "missing field": {"next_role": "builder", "readiness": "ready"},
        }
        for label, handoff in cases.items():
            with self.subTest(shape=label):
                self.assertTrue(
                    scanner._handoff_defects(
                        {"handoff": handoff}, scanner._FALLBACK_HANDOFF_SHAPE
                    ),
                    label,
                )

    def test_each_conforming_shape_is_accepted(self):
        for label, handoff in (
            ("ready", self.READY_HANDOFF),
            ("terminal", self.TERMINAL_HANDOFF),
            (
                "blocked",
                dict(self.READY_HANDOFF, readiness="blocked", blocking_ids=["ESC-1"]),
            ),
        ):
            with self.subTest(shape=label):
                self.assertEqual(
                    scanner._handoff_defects(
                        {"handoff": handoff}, scanner._FALLBACK_HANDOFF_SHAPE
                    ),
                    [],
                    label,
                )

    def test_an_absent_handoff_reports_no_defects(self):
        """Absent and malformed must stay distinguishable to the caller."""
        self.assertEqual(scanner._handoff_defects({}, scanner._FALLBACK_HANDOFF_SHAPE), [])
        self.assertEqual(
            scanner._handoff_defects(
                {"handoff": "ready"}, scanner._FALLBACK_HANDOFF_SHAPE
            ),
            [],
        )


class HandoffShapeSourceCase(unittest.TestCase):
    """The vocabulary comes from the schema, not from a copy of it.

    Restating the enums in the scanner would let the two disagree about what
    conforms, and reporting exactly that disagreement is the scanner's job under
    WORK_QUEUES 1.11.
    """

    @staticmethod
    def repo_root():
        return Path(__file__).resolve().parents[3]

    def test_the_shape_is_read_from_the_envelope_schema(self):
        root = self.repo_root()
        schema = json.loads(
            (root / "schemas" / "common" / "artifact-envelope.schema.json").read_text(
                encoding="utf-8"
            )
        )
        handoff = schema["$defs"]["handoff"]
        shape = scanner._handoff_shape(root)
        self.assertEqual(
            shape["roles"], frozenset(handoff["properties"]["next_role"]["enum"])
        )
        self.assertEqual(
            shape["readiness"], frozenset(handoff["properties"]["readiness"]["enum"])
        )
        self.assertEqual(shape["required"], frozenset(handoff["required"]))
        self.assertEqual(shape["properties"], frozenset(handoff["properties"]))

    def test_the_fallback_matches_the_schema_today(self):
        """If these diverge, the schema moved and the fallback is stale."""
        self.assertEqual(
            scanner._handoff_shape(self.repo_root()), scanner._FALLBACK_HANDOFF_SHAPE
        )

    def test_an_unreadable_schema_falls_back_rather_than_crashing(self):
        """The scanner reports queues on an incomplete tree; it must not raise."""
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                scanner._handoff_shape(Path(tmp)), scanner._FALLBACK_HANDOFF_SHAPE
            )

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
                 readiness="ready", blocking_ids=None, migration_required=False):
        self.write_yaml(
            f"rulesets/adnd1e/escalations/decisions/{decision_id}.yaml",
            {
                "id": decision_id,
                "status": "approved",
                "ruleset_id": "adnd1e",
                "book_id": "phb",
                "packet_id": self.PACKET,
                "escalation_id": escalation_id,
                "migration_required": migration_required,
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
    def test_a_migration_decision_still_replaces_the_stale_handoff(self):
        """The real DEC-2026-0021 shape, and the one the guard used to swallow.

        A migration-required Decision with a ready Builder handoff gets its
        Builder item from the decision-migration rule, so this stage must not
        emit a second one. That is a reason to skip the emission, not the
        suppression -- and skipping both left the originating Review sitting in
        the Analyst queue as ready work the Architect had already reassigned.
        """
        artifact_id, path = self.review_needing_the_analyst()
        esc = self.decided_package(artifact_id, path)
        self.decision("DEC-2026-0021", esc, migration_required=True)
        result = self.scan()
        self.assertNotIn(artifact_id, self.ready_ids(result))
        self.assertIn("handoff_replaced_by_decision", self.codes(result))

    def test_a_migration_decision_does_not_double_count_its_builder_job(self):
        """Suppressing must not bring back the duplicate the guard prevents."""
        artifact_id, path = self.review_needing_the_analyst()
        esc = self.decided_package(artifact_id, path)
        decision_id = self.decision("DEC-2026-0021", esc, migration_required=True)
        result = self.scan()
        emitted = [
            item for item in result["Items"]
            if item["InputId"] == decision_id and item["Role"] == "Builder"
        ]
        self.assertLessEqual(len(emitted), 1)
        self.assertNotIn(
            "BUILDER-DECISION", [item["Queue"] for item in emitted]
        )

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

    def test_later_decision_wins_when_two_decisions_replace_one_handoff(self):
        artifact_id, path = self.review_needing_the_analyst()
        old_escalation = self.decided_package(
            artifact_id, path, "ESC-2026-08-03T22.35.13.308Z"
        )
        new_escalation = self.decided_package(
            artifact_id, path, "ESC-2026-08-06T02.36.49.284Z"
        )
        self.decision("DEC-2026-0021", old_escalation, migration_required=True)
        self.decision(
            "DEC-2026-0027", new_escalation, next_role="none", readiness="terminal"
        )

        result = self.scan()
        replacement = next(
            diagnostic
            for diagnostic in result["Diagnostics"]
            if diagnostic["Code"] == "handoff_replaced_by_decision"
        )
        self.assertNotIn(artifact_id, self.ready_ids(result))
        self.assertTrue(replacement["Message"].startswith("DEC-2026-0027 resolved"))

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

    def test_kind_id_and_kind_path_pair(self):
        self.assertEqual(
            self.refs({"gur_id": "GUR-X-r01", "gur_path": "books/x/GUR-X-r01.yaml"}),
            [("GUR-X-r01", "books/x/GUR-X-r01.yaml")],
        )

    def test_kind_ids_and_kind_paths_pair(self):
        self.assertEqual(
            self.refs(
                {
                    "gur_ids": ["GUR-X-r01", "GUR-Y-r01"],
                    "gur_paths": ["books/x/GUR-X-r01.yaml", "books/y/GUR-Y-r01.yaml"],
                }
            ),
            [
                ("GUR-X-r01", "books/x/GUR-X-r01.yaml"),
                ("GUR-Y-r01", "books/y/GUR-Y-r01.yaml"),
            ],
        )

    def test_mismatched_parallel_lists_yield_nothing(self):
        self.assertEqual(
            self.refs({"gur_ids": ["GUR-X-r01"], "gur_paths": []}),
            [],
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


class DecisionImplementationCase(QueueScannerCase):
    """WORK_QUEUES 1.4, ruled by DEC-2026-0023.

    A non-migration Decision changes schemas, documentation, tests or tooling
    and produces no GUP, so nothing in the graph lineage can retire it. Its
    completion lineage is one Builder report plus one independent Review, and
    only the Approved Review consumes it. File existence, version strings,
    passing tests and Builder's own claim are all insufficient by ruling.
    """

    DECISION = "DEC-2026-0099"
    ACCEPTANCE = ["first criterion", "second criterion", "third criterion"]

    def sha256(self, relative: str) -> str:
        return scanner._sha256_of(self.root / relative)

    def decision(self, *, migration_required=False, next_role="builder",
                 readiness="ready", acceptance=None):
        relative = f"rulesets/adnd1e/escalations/decisions/{self.DECISION}.yaml"
        self.write_yaml(
            relative,
            {
                "id": self.DECISION,
                "status": "approved",
                "ruleset_id": "adnd1e",
                "book_id": "phb",
                "packet_id": "cross-packet",
                "migration_required": migration_required,
                "acceptance_tests": self.ACCEPTANCE if acceptance is None else acceptance,
                "handoff": {
                    "next_role": next_role, "readiness": readiness,
                    "reason": "implement it", "blocking_ids": [],
                },
            },
        )
        return relative

    def implementation_file(self, relative="tooling/common/fixture_impl.py"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixture implementation\n", encoding="utf-8")
        return relative

    def report(self, decision_relative, *, revision=1, approval_ready=True,
               indices=None, results=None, files=None, supersedes=None,
               decision_checksum=None, decision_path=None,
               handoff_role="reviewer", handoff_readiness="ready"):
        artifact_id = f"IMP-{self.DECISION}-r{revision:02d}"
        impl = files if files is not None else [self.implementation_file()]
        indices = list(range(1, len(self.ACCEPTANCE) + 1)) if indices is None else indices
        results = results or {}
        self.write_yaml(
            f"rulesets/adnd1e/decision-implementations/{artifact_id}.yaml",
            {
                "schema_version": "1.0",
                "id": artifact_id,
                "artifact_kind": "decision_implementation",
                "status": "proposed",
                "ruleset_id": "adnd1e",
                "constitution_version": "1.7",
                "revision": revision,
                "supersedes": supersedes,
                "approval_ready": approval_ready,
                "implemented_by": "builder",
                "decision_input": {
                    "id": self.DECISION,
                    "path": decision_path or decision_relative,
                    "checksum": decision_checksum or self.sha256(decision_relative),
                },
                "implementation_files": [
                    {"path": p, "checksum": self.sha256(p)} for p in impl
                ],
                "acceptance_results": [
                    {"acceptance_test_index": i,
                     "result": results.get(i, "passed"),
                     "evidence": f"evidence for {i}"}
                    for i in indices
                ],
                "validation": {
                    "passed": True,
                    "commands": [
                        {"command": "python -m unittest discover",
                         "exit_code": 0, "result": "passed", "summary": "all green"}
                    ],
                },
                "handoff": {
                    "next_role": handoff_role, "readiness": handoff_readiness,
                    "reason": "implemented", "blocking_ids": [],
                },
            },
        )
        return artifact_id

    def implementation_review(self, report_id, decision_relative, *,
                              disposition="approved", revision=1):
        artifact_id = f"REV-{report_id}-r{revision:02d}"
        report_relative = f"rulesets/adnd1e/decision-implementations/{report_id}.yaml"
        self.write_yaml(
            f"rulesets/adnd1e/decision-implementation-reviews/{artifact_id}.yaml",
            {
                "schema_version": "1.0",
                "id": artifact_id,
                "artifact_kind": "decision_implementation_review",
                "status": disposition,
                "ruleset_id": "adnd1e",
                "constitution_version": "1.7",
                "revision": revision,
                "supersedes": None,
                "reviewed_by": "reviewer",
                "reviewed_implementation": {
                    "id": report_id,
                    "path": report_relative,
                    "checksum": self.sha256(report_relative),
                },
                "decision_input": {
                    "id": self.DECISION,
                    "path": decision_relative,
                    "checksum": self.sha256(decision_relative),
                },
                "acceptance_dispositions": [
                    {"acceptance_test_index": i, "disposition": "verified",
                     "evidence": "independently checked"}
                    for i in range(1, len(self.ACCEPTANCE) + 1)
                ],
                "independent_validation": {
                    "passed": True,
                    "commands": [
                        {"command": "python -m unittest discover",
                         "exit_code": 0, "result": "passed", "summary": "reproduced"}
                    ],
                },
                "overall_disposition": disposition,
                "handoff": {
                    "next_role": "none" if disposition == "approved" else "builder",
                    "readiness": "terminal" if disposition == "approved" else "ready",
                    "reason": "reviewed", "blocking_ids": [],
                },
            },
        )
        return artifact_id

    def queues(self, result):
        return {(i["Role"], i["Queue"], i["InputId"]) for i in result["Items"]}

    def codes(self, result):
        return [d["Code"] for d in result["Diagnostics"]]

    # -- discovery ----------------------------------------------------------
    def test_an_unconsumed_non_migration_decision_is_one_builder_job(self):
        self.decision()
        result = self.scan()
        self.assertIn(("Builder", "BUILDER-DECISION", self.DECISION), self.queues(result))

    def test_a_migration_decision_is_not_routed_by_this_rule(self):
        self.decision(migration_required=True)
        result = self.scan()
        self.assertNotIn(("Builder", "BUILDER-DECISION", self.DECISION), self.queues(result))

    # -- report validity ----------------------------------------------------
    def test_a_valid_report_is_one_reviewer_job_and_suppresses_the_decision_job(self):
        rel = self.decision()
        report_id = self.report(rel)
        result = self.scan()
        q = self.queues(result)
        self.assertIn(("Reviewer", "REVIEWER-DECISION-IMPLEMENTATION", report_id), q)
        self.assertNotIn(("Builder", "BUILDER-DECISION", self.DECISION), q)

    def test_a_partial_report_is_not_reviewer_ready(self):
        """The six-of-thirteen spot-check case, in miniature."""
        rel = self.decision()
        self.report(rel, indices=[1, 2])
        result = self.scan()
        q = self.queues(result)
        self.assertIn(("Builder", "BUILDER-DECISION", self.DECISION), q)
        self.assertFalse(any(r == "Reviewer" for r, _, _ in q))
        self.assertIn("decision_implementation_invalid", self.codes(result))

    def test_a_repeated_acceptance_index_is_invalid(self):
        rel = self.decision()
        self.report(rel, indices=[1, 2, 3, 3])
        result = self.scan()
        self.assertIn("decision_implementation_invalid", self.codes(result))
        self.assertIn(("Builder", "BUILDER-DECISION", self.DECISION), self.queues(result))

    def test_an_out_of_range_acceptance_index_is_invalid(self):
        rel = self.decision()
        self.report(rel, indices=[1, 2, 3, 4])
        result = self.scan()
        self.assertIn("decision_implementation_invalid", self.codes(result))

    def test_a_failed_acceptance_result_cannot_be_approval_ready(self):
        rel = self.decision()
        self.report(rel, results={2: "failed"})
        result = self.scan()
        self.assertIn("decision_implementation_invalid", self.codes(result))
        self.assertIn(("Builder", "BUILDER-DECISION", self.DECISION), self.queues(result))

    def test_a_stale_decision_checksum_is_invalid(self):
        rel = self.decision()
        self.report(rel, decision_checksum="sha256:" + "0" * 64)
        result = self.scan()
        self.assertIn("decision_implementation_invalid", self.codes(result))
        self.assertIn(("Builder", "BUILDER-DECISION", self.DECISION), self.queues(result))

    def test_a_mismatched_decision_path_is_invalid(self):
        rel = self.decision()
        self.report(rel, decision_path="rulesets/adnd1e/escalations/decisions/DEC-2026-0001.yaml")
        result = self.scan()
        self.assertIn("decision_implementation_invalid", self.codes(result))

    def test_a_missing_implementation_file_is_invalid(self):
        rel = self.decision()
        report_id = self.report(rel)
        # Remove the file the report vouches for.
        (self.root / "tooling/common/fixture_impl.py").unlink()
        result = self.scan()
        self.assertIn("decision_implementation_invalid", self.codes(result))
        self.assertNotIn(
            ("Reviewer", "REVIEWER-DECISION-IMPLEMENTATION", report_id),
            self.queues(result),
        )

    def test_a_stale_implementation_file_checksum_is_invalid(self):
        rel = self.decision()
        self.report(rel)
        (self.root / "tooling/common/fixture_impl.py").write_text("# changed\n", encoding="utf-8")
        result = self.scan()
        self.assertIn("decision_implementation_invalid", self.codes(result))

    def test_a_non_ready_report_leaves_the_decision_as_builder_work(self):
        rel = self.decision()
        self.report(rel, approval_ready=False)
        result = self.scan()
        self.assertIn(("Builder", "BUILDER-DECISION", self.DECISION), self.queues(result))

    # -- Review routing -----------------------------------------------------
    def test_an_approved_review_consumes_the_decision(self):
        rel = self.decision()
        report_id = self.report(rel)
        self.implementation_review(report_id, rel, disposition="approved")
        result = self.scan()
        q = self.queues(result)
        self.assertNotIn(("Builder", "BUILDER-DECISION", self.DECISION), q)
        self.assertNotIn(("Reviewer", "REVIEWER-DECISION-IMPLEMENTATION", report_id), q)
        self.assertFalse(
            any(role == "Integrator" for role, _, _ in q),
            "this lineage creates no Integrator job",
        )

    def test_a_revision_required_review_is_one_builder_job_and_no_duplicate(self):
        rel = self.decision()
        report_id = self.report(rel)
        review_id = self.implementation_review(report_id, rel, disposition="revision_required")
        result = self.scan()
        q = self.queues(result)
        self.assertIn(
            ("Builder", "BUILDER-DECISION-IMPLEMENTATION-REVISION", review_id), q
        )
        self.assertNotIn(("Builder", "BUILDER-DECISION", self.DECISION), q)
        self.assertNotIn(("Reviewer", "REVIEWER-DECISION-IMPLEMENTATION", report_id), q)

    def test_a_superseding_revision_leaves_only_the_active_leaf(self):
        rel = self.decision()
        first = self.report(rel, revision=1, approval_ready=False)
        second = self.report(rel, revision=2, supersedes=first)
        result = self.scan()
        q = self.queues(result)
        self.assertIn(("Reviewer", "REVIEWER-DECISION-IMPLEMENTATION", second), q)
        self.assertNotIn(("Reviewer", "REVIEWER-DECISION-IMPLEMENTATION", first), q)


class TestImplementationReportValidation(unittest.TestCase):
    """The report validator, read directly against WORK_QUEUES 1.4."""

    def test_a_wrong_artifact_kind_is_rejected_immediately(self):
        artifact = scanner.Artifact(
            Path("x.yaml"), "decision-implementation", "adnd1e", None,
            {"artifact_kind": "packet_update"},
        )
        reasons = scanner._implementation_report_errors(Path("."), artifact, {})
        self.assertEqual(len(reasons), 1)
        self.assertIn("artifact_kind", reasons[0])

    def test_an_unknown_decision_is_rejected(self):
        artifact = scanner.Artifact(
            Path("x.yaml"), "decision-implementation", "adnd1e", None,
            {"artifact_kind": "decision_implementation",
             "decision_input": {"id": "DEC-2026-9999"}},
        )
        reasons = scanner._implementation_report_errors(Path("."), artifact, {})
        self.assertTrue(any("not an approved Decision" in r for r in reasons))


class ImplementationReviewProvenanceCase(DecisionImplementationCase):
    """WORK_QUEUES 1.4: the Review is what consumes a Decision, so it is checked.

    Validating the report but not the Review left the consuming half of the
    lineage unguarded. An approved Review carrying a checksum of all zeroes
    retired its Decision, produced no Reviewer job, and emitted no diagnostic --
    the exact failure REV-IMP-DEC-2026-0023-r01-r01 reported at acceptance test
    11. An unsound Review must consume nothing and must not hide the report that
    is still waiting for a sound one.
    """

    def corrupt_review(self, review_id, **overrides):
        path = (
            self.root
            / "rulesets/adnd1e/decision-implementation-reviews"
            / f"{review_id}.yaml"
        )
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        for dotted, value in overrides.items():
            block, _, field = dotted.partition(".")
            if field:
                doc[block][field] = value
            else:
                doc[block] = value
        path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    def assert_not_consumed(self, report_id, result):
        """The Decision is back, the report is still Reviewer-ready, and it is loud."""
        q = self.queues(result)
        self.assertIn("decision_implementation_review_invalid", self.codes(result))
        self.assertIn(("Reviewer", "REVIEWER-DECISION-IMPLEMENTATION", report_id), q)
        self.assertNotIn(
            ("Builder", "BUILDER-DECISION-IMPLEMENTATION-REVISION", f"REV-{report_id}-r01"), q
        )

    def test_a_stale_report_checksum_does_not_consume_the_decision(self):
        rel = self.decision()
        report_id = self.report(rel)
        review_id = self.implementation_review(report_id, rel)
        self.corrupt_review(review_id, **{"reviewed_implementation.checksum": "sha256:" + "0" * 64})
        self.assert_not_consumed(report_id, self.scan())

    def test_a_mismatched_report_path_does_not_consume_the_decision(self):
        rel = self.decision()
        report_id = self.report(rel)
        review_id = self.implementation_review(report_id, rel)
        self.corrupt_review(
            review_id,
            **{"reviewed_implementation.path": "rulesets/adnd1e/decision-implementations/OTHER.yaml"},
        )
        self.assert_not_consumed(report_id, self.scan())

    def test_a_stale_decision_checksum_does_not_consume_the_decision(self):
        rel = self.decision()
        report_id = self.report(rel)
        review_id = self.implementation_review(report_id, rel)
        self.corrupt_review(review_id, **{"decision_input.checksum": "sha256:" + "0" * 64})
        self.assert_not_consumed(report_id, self.scan())

    def test_a_mismatched_decision_path_does_not_consume_the_decision(self):
        rel = self.decision()
        report_id = self.report(rel)
        review_id = self.implementation_review(report_id, rel)
        self.corrupt_review(
            review_id,
            **{"decision_input.path": "rulesets/adnd1e/escalations/decisions/DEC-2026-0001.yaml"},
        )
        self.assert_not_consumed(report_id, self.scan())

    def test_a_review_of_a_superseded_report_does_not_consume_the_decision(self):
        """A Review must target the active report leaf, not an earlier revision."""
        rel = self.decision()
        first = self.report(rel, revision=1)
        self.implementation_review(first, rel)
        second = self.report(rel, revision=2, supersedes=first)
        result = self.scan()
        q = self.queues(result)
        # The Review named r01; r02 is the leaf, so it is still awaiting Review.
        self.assertIn(("Reviewer", "REVIEWER-DECISION-IMPLEMENTATION", second), q)
        self.assertNotIn(("Builder", "BUILDER-DECISION", self.DECISION), q)

    def test_an_unverified_disposition_does_not_consume_the_decision(self):
        rel = self.decision()
        report_id = self.report(rel)
        review_id = self.implementation_review(report_id, rel)
        path = (
            self.root
            / "rulesets/adnd1e/decision-implementation-reviews"
            / f"{review_id}.yaml"
        )
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        doc["acceptance_dispositions"][1]["disposition"] = "failed"
        path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
        self.assert_not_consumed(report_id, self.scan())

    def test_a_missing_disposition_does_not_consume_the_decision(self):
        rel = self.decision()
        report_id = self.report(rel)
        review_id = self.implementation_review(report_id, rel)
        path = (
            self.root
            / "rulesets/adnd1e/decision-implementation-reviews"
            / f"{review_id}.yaml"
        )
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        doc["acceptance_dispositions"] = doc["acceptance_dispositions"][:1]
        path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
        self.assert_not_consumed(report_id, self.scan())

    def test_a_failed_independent_validation_does_not_consume_the_decision(self):
        rel = self.decision()
        report_id = self.report(rel)
        review_id = self.implementation_review(report_id, rel)
        self.corrupt_review(review_id, **{"independent_validation.passed": False})
        self.assert_not_consumed(report_id, self.scan())

    def test_a_non_terminal_handoff_does_not_consume_the_decision(self):
        rel = self.decision()
        report_id = self.report(rel)
        review_id = self.implementation_review(report_id, rel)
        self.corrupt_review(review_id, **{"handoff.readiness": "ready"})
        self.assert_not_consumed(report_id, self.scan())

    def test_a_sound_approved_review_still_consumes_the_decision(self):
        """The guard must not break the path it protects."""
        rel = self.decision()
        report_id = self.report(rel)
        self.implementation_review(report_id, rel)
        result = self.scan()
        q = self.queues(result)
        self.assertNotIn(("Builder", "BUILDER-DECISION", self.DECISION), q)
        self.assertNotIn(("Reviewer", "REVIEWER-DECISION-IMPLEMENTATION", report_id), q)
        self.assertNotIn("decision_implementation_review_invalid", self.codes(result))

    def test_a_sound_revision_required_review_still_returns_builder_work(self):
        rel = self.decision()
        report_id = self.report(rel)
        review_id = self.implementation_review(report_id, rel, disposition="revision_required")
        result = self.scan()
        self.assertIn(
            ("Builder", "BUILDER-DECISION-IMPLEMENTATION-REVISION", review_id),
            self.queues(result),
        )
        self.assertNotIn("decision_implementation_review_invalid", self.codes(result))



class PostApprovalFileDriftCase(DecisionImplementationCase):
    """DEC-2026-0046: a consumed report's file checksums are a reviewed snapshot.

    `implementation_files` proves which repository state an independent Review
    actually verified. It was also being read as a permanent dependency on every
    future edit to that file, so a completed Decision reopened whenever a later,
    unrelated Decision touched the same shared scanner, schema or test module.
    Five Decisions -- 0018, 0022, 0023, 0028 and 0039 -- were re-opened at once by
    a single edit that DEC-2026-0045 had itself ordered, and their report
    revisions had already reached 15, 13, 15, 9 and 4 largely on that treadmill.
    The cycle has no fixed point: a re-issued report pins the newest bytes, and
    the next Decision touching the file voids it again.

    Rule 15 makes the exception exactly as wide as the evidence supports. An
    exact Approved Review is what completes a Decision, and it pins both the
    report and the Decision by checksum, so later drift cannot alter what it
    verified. Everywhere short of that -- no Review, a revision-required one, or
    an Approved one that does not pin this exact report and Decision -- drift
    keeps its old strict meaning, because no completed state has been
    established to snapshot.
    """

    SHARED = "tooling/common/shared_tool.py"

    def drift(self):
        """Edit the shared file after the report pinned it."""
        path = self.root / self.SHARED
        path.write_text("# edited by a later, unrelated Decision\n", encoding="utf-8")

    def lineage(self, *, disposition="approved", review=True, drift=True):
        decision_relative = self.decision()
        self.implementation_file(self.SHARED)
        report_id = self.report(decision_relative, files=[self.SHARED])
        review_id = None
        if review:
            review_id = self.implementation_review(
                report_id, decision_relative, disposition=disposition
            )
        if drift:
            self.drift()
        return decision_relative, report_id, review_id

    def diagnostics(self, result, code):
        return [d for d in result["Diagnostics"] if d["Code"] == code]

    def builder_items(self, result):
        return {
            (item["Queue"], item["InputId"])
            for item in result["Items"]
            if item["Role"] == "Builder"
        }

    # -- acceptance test 1: the completed lineage stays completed ------------

    def test_post_approval_drift_does_not_reopen_the_decision(self):
        self.lineage()
        result = self.scan()
        self.assertEqual(self.builder_items(result), set())

    def test_post_approval_drift_is_informational_not_an_error(self):
        self.lineage()
        result = self.scan()
        self.assertEqual(
            self.diagnostics(result, "decision_implementation_invalid"), []
        )
        drift = self.diagnostics(result, "implementation_files_drifted_after_approval")
        self.assertEqual(len(drift), 1)
        self.assertEqual(drift[0]["Severity"], "info")

    def test_the_observation_names_the_file_the_report_and_the_review(self):
        _, report_id, review_id = self.lineage()
        message = self.diagnostics(
            self.scan(), "implementation_files_drifted_after_approval"
        )[0]["Message"]
        self.assertIn(self.SHARED, message)
        self.assertIn(report_id, message)
        self.assertIn(review_id, message)

    def test_a_deleted_implementation_file_is_also_only_informational(self):
        """Absence after approval is drift too; the Review still verified it."""
        self.lineage(drift=False)
        (self.root / self.SHARED).unlink()
        result = self.scan()
        self.assertEqual(self.builder_items(result), set())
        self.assertEqual(
            len(self.diagnostics(result, "implementation_files_drifted_after_approval")), 1
        )

    def test_the_report_and_review_remain_untouched(self):
        """Queue derivation changed; the immutable artifacts did not."""
        _, report_id, review_id = self.lineage()
        report = self.root / f"rulesets/adnd1e/decision-implementations/{report_id}.yaml"
        review = (
            self.root
            / f"rulesets/adnd1e/decision-implementation-reviews/{review_id}.yaml"
        )
        before = (report.read_bytes(), review.read_bytes())
        self.scan()
        self.assertEqual((report.read_bytes(), review.read_bytes()), before)

    def test_a_completed_lineage_without_drift_is_still_silent(self):
        self.lineage(drift=False)
        result = self.scan()
        self.assertEqual(self.builder_items(result), set())
        self.assertEqual(
            self.diagnostics(result, "implementation_files_drifted_after_approval"), []
        )

    # -- acceptance test 2: everything short of approval stays strict --------

    def assert_strict(self, result):
        self.assertEqual(
            len(self.diagnostics(result, "decision_implementation_invalid")), 1
        )
        self.assertEqual(
            self.diagnostics(result, "implementation_files_drifted_after_approval"), []
        )
        self.assertTrue(
            self.builder_items(result),
            "drift before approval must return ready work to the implementation owner",
        )

    def test_drift_without_any_review_remains_an_error(self):
        self.lineage(review=False)
        self.assert_strict(self.scan())

    def test_drift_under_a_revision_required_review_remains_an_error(self):
        self.lineage(disposition="revision_required")
        self.assert_strict(self.scan())

    def test_drift_under_a_review_pinning_a_stale_report_checksum_remains_an_error(self):
        """An Approved Review that does not pin this exact report proves nothing."""
        decision_relative, report_id, review_id = self.lineage()
        relative = (
            f"rulesets/adnd1e/decision-implementation-reviews/{review_id}.yaml"
        )
        document = yaml.safe_load((self.root / relative).read_text(encoding="utf-8"))
        document["reviewed_implementation"]["checksum"] = "sha256:" + "0" * 64
        self.write_yaml(relative, document)
        self.assert_strict(self.scan())

    def test_drift_under_a_review_pinning_a_stale_decision_checksum_remains_an_error(self):
        decision_relative, report_id, review_id = self.lineage()
        relative = (
            f"rulesets/adnd1e/decision-implementation-reviews/{review_id}.yaml"
        )
        document = yaml.safe_load((self.root / relative).read_text(encoding="utf-8"))
        document["decision_input"]["checksum"] = "sha256:" + "1" * 64
        self.write_yaml(relative, document)
        self.assert_strict(self.scan())

    def test_drift_under_a_malformed_review_remains_an_error(self):
        decision_relative, report_id, review_id = self.lineage()
        relative = (
            f"rulesets/adnd1e/decision-implementation-reviews/{review_id}.yaml"
        )
        document = yaml.safe_load((self.root / relative).read_text(encoding="utf-8"))
        document["independent_validation"] = {"passed": False, "commands": []}
        self.write_yaml(relative, document)
        self.assert_strict(self.scan())

    def test_a_defect_other_than_drift_is_still_an_error_after_approval(self):
        """The exception covers drifted files, not a report broken on its own terms."""
        decision_relative = self.decision()
        self.implementation_file(self.SHARED)
        report_id = self.report(
            decision_relative, files=[self.SHARED], indices=[1, 2]
        )  # one acceptance test unaccounted for
        self.implementation_review(report_id, decision_relative)
        self.drift()
        result = self.scan()
        self.assertEqual(
            len(self.diagnostics(result, "decision_implementation_invalid")), 1
        )
        self.assertTrue(self.builder_items(result))

    # -- acceptance test 3: the later Decision keeps its own lifecycle -------

    def test_the_decision_that_changed_the_file_is_independently_discoverable(self):
        """Suppressing the completed Decision must not suppress the new one.

        The exception is about the queue state of the Decision already reviewed.
        Whatever edited the shared file answers for that edit through its own
        report and Review, which is exactly what the ruling assigns.
        """
        self.lineage()
        later = "DEC-2026-0098"
        self.write_yaml(
            f"rulesets/adnd1e/escalations/decisions/{later}.yaml",
            {
                "id": later,
                "status": "approved",
                "ruleset_id": "adnd1e",
                "book_id": "phb",
                "migration_required": False,
                "acceptance_tests": ["the later change is evidenced"],
                "handoff": {
                    "next_role": "builder",
                    "readiness": "ready",
                    "reason": "implement the later change",
                    "blocking_ids": [],
                },
            },
        )
        result = self.scan()
        self.assertEqual(
            self.builder_items(result), {("BUILDER-DECISION", later)}
        )


class TestImplementationDriftSink(unittest.TestCase):
    """The drift/defect split the caller depends on, read directly."""

    def test_drift_goes_to_the_sink_and_other_defects_do_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            decision_relative = "rulesets/adnd1e/escalations/decisions/DEC-2026-0097.yaml"
            (root / decision_relative).parent.mkdir(parents=True, exist_ok=True)
            (root / decision_relative).write_text(
                yaml.safe_dump(
                    {
                        "id": "DEC-2026-0097",
                        "status": "approved",
                        "ruleset_id": "adnd1e",
                        "migration_required": False,
                        "acceptance_tests": ["only criterion"],
                        "handoff": {
                            "next_role": "builder",
                            "readiness": "ready",
                            "reason": "go",
                            "blocking_ids": [],
                        },
                    }
                ),
                encoding="utf-8",
            )
            target = root / "tooling/common/thing.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# real\n", encoding="utf-8")

            report_relative = (
                "rulesets/adnd1e/decision-implementations/IMP-DEC-2026-0097-r01.yaml"
            )
            document = {
                "id": "IMP-DEC-2026-0097-r01",
                "artifact_kind": "decision_implementation",
                "status": "proposed",
                "ruleset_id": "adnd1e",
                "revision": 1,
                "supersedes": None,
                "approval_ready": True,
                "implemented_by": "builder",
                "decision_input": {
                    "id": "DEC-2026-0097",
                    "path": decision_relative,
                    "checksum": scanner._sha256_of(root / decision_relative),
                },
                # One drifted file and one absent file, plus a duplicated
                # acceptance index that is not drift at all.
                "implementation_files": [
                    {"path": "tooling/common/thing.py", "checksum": "sha256:" + "0" * 64},
                    {"path": "tooling/common/gone.py", "checksum": "sha256:" + "0" * 64},
                ],
                "acceptance_results": [
                    {"acceptance_test_index": 1, "result": "passed", "evidence": "e"},
                    {"acceptance_test_index": 1, "result": "passed", "evidence": "e"},
                ],
                "validation": {
                    "passed": True,
                    "commands": [
                        {"command": "c", "exit_code": 0, "result": "passed", "summary": "OK"}
                    ],
                },
                "handoff": {
                    "next_role": "reviewer",
                    "readiness": "ready",
                    "reason": "done",
                    "blocking_ids": [],
                },
            }
            (root / report_relative).parent.mkdir(parents=True, exist_ok=True)
            (root / report_relative).write_text(
                yaml.safe_dump(document), encoding="utf-8"
            )

            artifact = scanner.Artifact(
                path=root / report_relative,
                kind="decision_implementation",
                ruleset="adnd1e",
                book=None,
                data=yaml.safe_load((root / report_relative).read_text(encoding="utf-8")),
            )
            decisions = {
                "DEC-2026-0097": (
                    root / decision_relative,
                    yaml.safe_load((root / decision_relative).read_text(encoding="utf-8")),
                )
            }

            sink: list[str] = []
            errors = scanner._implementation_report_errors(
                root, artifact, decisions, drift_sink=sink
            )
            self.assertEqual(len(sink), 2, sink)
            self.assertTrue(any("thing.py" in s for s in sink))
            self.assertTrue(any("gone.py" in s for s in sink))
            self.assertTrue(any("repeats acceptance_test_index" in e for e in errors))
            self.assertFalse(any("thing.py" in e for e in errors))

            # Without a sink the caller sees the old, undivided list.
            combined = scanner._implementation_report_errors(root, artifact, decisions)
            self.assertTrue(any("thing.py" in e for e in combined))


class SequencedRebuildRoutingCase(QueueScannerCase):
    """A decided escalation does not by itself make the Builder next.

    DEC-2026-0024 answered the mistletoe identity escalation and, in the same
    ruling, ordered a routing Review revision ahead of the packet rebuild: the
    Decision settles identities, and the Review carries those identities down
    onto individual rows. Calling the rebuild ready the moment the escalation is
    decided sends the Builder to compile against instructions that do not exist,
    and the only ways out are a no-op leaf or invented rows.
    """

    PACKET = "PKT-PHB-001-002-fixture"
    ESCALATION = "ESC-2026-01-01T00.00.00.000Z"

    def escalated_review(self, *, required_routing_review=None, publish_required=False):
        gur_id = self.gur(self.PACKET, 1)
        gup_id = self.gup(self.PACKET, 1, gur_id)
        review_id = f"REV-{gup_id}-r01"
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/reviews/{review_id}.yaml",
            {
                "id": review_id,
                "packet_id": self.PACKET,
                "revision": 1,
                "status": "architect_escalation",
                "overall_disposition": "architect_escalation",
                "reviewed_gup": {"id": gup_id},
                "architectural_escalations": [{"id": self.ESCALATION}],
                "handoff": {
                    "next_role": "architect",
                    "readiness": "ready",
                    "blocking_ids": [],
                },
            },
        )
        disposition = {"existing_gup": gup_id}
        if required_routing_review is not None:
            disposition["required_routing_review"] = required_routing_review.format(
                gup=gup_id
            )
        self.write_yaml(
            "rulesets/adnd1e/escalations/decisions/DEC-2026-9001.yaml",
            {
                "id": "DEC-2026-9001",
                "status": "approved",
                "ruleset_id": "adnd1e",
                "book_id": "phb",
                "packet_id": self.PACKET,
                "escalation_id": self.ESCALATION,
                "migration_required": False,
                "packet_disposition": disposition,
                "handoff": {
                    "next_role": "builder",
                    "readiness": "ready",
                    "reason": "the Architect has ruled",
                    "blocking_ids": [],
                },
            },
        )
        if publish_required:
            self.write_yaml(
                f"books/adnd1e/phb/artifacts/reviews/REV-{gup_id}-r02.yaml",
                {
                    "id": f"REV-{gup_id}-r02",
                    "packet_id": self.PACKET,
                    "revision": 2,
                    "supersedes": review_id,
                    "status": "revision_required",
                    "overall_disposition": "revision_required",
                    "reviewed_gup": {"id": gup_id},
                    "row_decisions": [
                        {"ref": "B1", "disposition": "approved_with_revision",
                         "exact_corrections": {"aspect": "as the Decision directs"}},
                    ],
                    "handoff": {
                        "next_role": "builder",
                        "readiness": "ready",
                        "blocking_ids": [],
                    },
                },
            )
        return review_id, self.scan()

    def entries(self, result, state):
        key = "BlockedItems" if state == "blocked" else "Items"
        return {
            (item["Queue"], item["InputId"])
            for item in result[key]
            if item["State"] == state and item["Role"] == "Builder"
        }

    def test_a_decision_naming_an_unpublished_routing_review_blocks_the_rebuild(self):
        review_id, result = self.escalated_review(
            required_routing_review="REV-{gup}-r02"
        )
        self.assertIn(
            ("BUILDER-REVISION-BLOCKED", review_id), self.entries(result, "blocked")
        )
        self.assertNotIn(
            ("BUILDER-REVISION", review_id), self.entries(result, "ready")
        )

    def test_the_blocked_item_names_the_artifact_and_the_decision(self):
        _, result = self.escalated_review(required_routing_review="REV-{gup}-r02")
        reason = next(
            item["Reason"]
            for item in result["BlockedItems"]
            if item["Role"] == "Builder"
        )
        self.assertIn("r02", reason)
        self.assertIn("DEC-2026-9001", reason)

    def test_publishing_the_routing_review_releases_the_rebuild(self):
        """The block must clear on its own, without a Builder edit."""
        _, result = self.escalated_review(
            required_routing_review="REV-{gup}-r02", publish_required=True
        )
        self.assertEqual(self.entries(result, "blocked"), set())
        self.assertTrue(
            any(item["Role"] == "Builder" and item["State"] == "ready"
                for item in result["Items"])
        )

    def test_a_decision_ordering_nothing_leaves_the_rebuild_ready(self):
        """The guard must not block every decided escalation."""
        review_id, result = self.escalated_review()
        self.assertEqual(self.entries(result, "blocked"), set())
        self.assertIn(("BUILDER-REVISION", review_id), self.entries(result, "ready"))

    def test_a_decision_naming_this_review_is_not_its_own_prerequisite(self):
        """`required_routing_review` pointing at the active leaf describes it."""
        review_id, result = self.escalated_review(
            required_routing_review="REV-{gup}-r01"
        )
        self.assertEqual(self.entries(result, "blocked"), set())
        self.assertIn(("BUILDER-REVISION", review_id), self.entries(result, "ready"))


class RetiredLineageFixtureMixin:
    """Fixtures shared by the report and Review halves of DEC-2026-0028.

    Deliberately not a TestCase. Subclassing one case from another would
    re-run every one of its tests under the second name, which inflates the
    suite without testing anything new.
    """

    DECISION = "DEC-2026-9201"
    AUTHORITY = "DEC-2026-9202"
    SUBJECT = "GUP-PKT-PHB-001-002-fixture-r01"
    SUBJECT_PATH = "books/adnd1e/phb/artifacts/gup/GUP-PKT-PHB-001-002-fixture-r01.yaml"
    RECORD = (
        "books/adnd1e/phb/artifacts/integrated/"
        "INT-20260804-001-APPROVED-GUP-PKT-PHB-001-002-fixture-r01-r01.json"
    )

    def setUp(self):
        super().setUp()
        (self.root / "books/adnd1e/phb/artifacts/integrated").mkdir(
            parents=True, exist_ok=True
        )
        (self.root / "rulesets/adnd1e/decision-implementations").mkdir(
            parents=True, exist_ok=True
        )
        (self.root / "rulesets/adnd1e/decision-implementation-reviews").mkdir(
            parents=True, exist_ok=True
        )

    def sha256(self, relative):
        import hashlib

        path = self.root / relative
        if not path.is_file():
            # Deliberate in the missing-authority case: the report still has to
            # record some checksum, and the scanner must reject it on the file's
            # absence rather than on a malformed field.
            return "sha256:" + "0" * 64
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    def integration_record(self):
        path = self.root / self.RECORD
        path.write_text(
            json.dumps({"id": "INT-20260804-001", "approved_bundle": "APPROVED"}, indent=2)
            + "\n",
            encoding="utf-8", newline="\n",
        )
        return self.RECORD

    def decision(self, *, semantics=None):
        """The Decision under implementation. Two acceptance tests."""
        document = {
            "id": self.DECISION,
            "status": "approved",
            "ruleset_id": "adnd1e",
            "book_id": "phb",
            "migration_required": False,
            "acceptance_tests": ["a behavior test", "a live queue snapshot"],
            "handoff": {
                "next_role": "builder", "readiness": "ready",
                "reason": "implement", "blocking_ids": [],
            },
        }
        if semantics is not None:
            document["acceptance_test_semantics"] = semantics
        self.write_yaml(
            f"rulesets/adnd1e/escalations/decisions/{self.DECISION}.yaml", document
        )
        return f"rulesets/adnd1e/escalations/decisions/{self.DECISION}.yaml"

    def authority(self, *, index=2, subjects=None, checksum=None, kind="live_queue_snapshot",
                  allowed=True, target=None):
        """A later Decision authorizing retirement of the legacy Decision's test."""
        decision_path = f"rulesets/adnd1e/escalations/decisions/{self.DECISION}.yaml"
        if subjects is None:
            subjects = [{
                "id": self.SUBJECT,
                "path": self.SUBJECT_PATH,
                "permitted_retirement_state": "consumed_by_integrated_bundle",
                "integration_record_path": self.RECORD,
            }]
        self.write_yaml(
            f"rulesets/adnd1e/escalations/decisions/{self.AUTHORITY}.yaml",
            {
                "id": self.AUTHORITY,
                "status": "approved",
                "ruleset_id": "adnd1e",
                "book_id": "phb",
                "migration_required": False,
                "acceptance_tests": ["authorize the retirement"],
                "handoff": {
                    "next_role": "builder", "readiness": "ready",
                    "reason": "authorize", "blocking_ids": [],
                },
                "retired_acceptance_authorizations": [{
                    "decision_input": {
                        "id": target or self.DECISION,
                        "path": decision_path,
                        "checksum": checksum or self.sha256(decision_path),
                    },
                    "acceptance_test_index": index,
                    "kind": kind,
                    "retirement_allowed": allowed,
                    "subjects": subjects,
                }],
            },
        )
        return f"rulesets/adnd1e/escalations/decisions/{self.AUTHORITY}.yaml"

    def report(self, *, retired=None, authority_id=None, result="retired_by_lineage",
               approval_ready=True, index=2):
        decision_path = f"rulesets/adnd1e/escalations/decisions/{self.DECISION}.yaml"
        authority_id = authority_id or self.AUTHORITY
        authority_path = f"rulesets/adnd1e/escalations/decisions/{authority_id}.yaml"
        if retired is None:
            retired = [{
                "id": self.SUBJECT,
                "path": self.SUBJECT_PATH,
                "retirement_state": "consumed_by_integrated_bundle",
                "integration_record_path": self.RECORD,
                "integration_record_checksum": self.sha256(self.RECORD),
            }]
        snapshot = {
            "acceptance_test_index": index,
            "result": result,
            "evidence": "the subject completed its lineage",
        }
        if result == "retired_by_lineage":
            snapshot["retirement_authority"] = {
                "id": authority_id,
                "path": authority_path,
                "checksum": self.sha256(authority_path),
                "authorized_acceptance_test_index": index,
            }
            snapshot["retired_subjects"] = retired
        report_id = f"IMP-{self.DECISION}-r01"
        self.write_yaml(
            f"rulesets/adnd1e/decision-implementations/{report_id}.yaml",
            {
                "id": report_id,
                "artifact_kind": "decision_implementation",
                "status": "proposed",
                "ruleset_id": "adnd1e",
                "revision": 1,
                "supersedes": None,
                "approval_ready": approval_ready,
                "implemented_by": "builder",
                "decision_input": {
                    "id": self.DECISION,
                    "path": decision_path,
                    "checksum": self.sha256(decision_path),
                },
                "implementation_files": [
                    {"path": "README.md", "checksum": self.sha256("README.md")}
                ],
                "acceptance_results": [
                    {"acceptance_test_index": 1, "result": "passed", "evidence": "unit test"},
                    snapshot,
                ],
                "validation": {
                    "passed": True,
                    "commands": [{
                        "command": "python -m unittest", "exit_code": 0,
                        "result": "passed", "summary": "OK",
                    }],
                },
                "handoff": {
                    "next_role": "reviewer", "readiness": "ready",
                    "reason": "ready for review", "blocking_ids": [],
                },
            },
        )
        return report_id

    def build(self, **kwargs):
        """The whole sound arrangement, with named parts overridable."""
        self.integration_record()
        self.decision(semantics=kwargs.pop("semantics", None))
        if kwargs.pop("with_authority", True):
            self.authority(**kwargs.pop("authority", {}))
        report_id = self.report(**kwargs.pop("report", {}))
        return report_id, self.scan()

    def invalid(self, result):
        return [
            d["Message"] for d in result["Diagnostics"]
            if d["Code"] == "decision_implementation_invalid"
        ]

    def reviewer_ready(self, result):
        return [
            i["InputId"] for i in result["Items"]
            if i["Role"] == "Reviewer" and i["State"] == "ready"
        ]


class RetiredByLineageCase(RetiredLineageFixtureMixin, QueueScannerCase):
    """WORK_QUEUES 1.6, ruled by DEC-2026-0028.

    An acceptance test naming a live queue position goes false when its subject
    completes Approval and Integration -- not because the implementation
    regressed, but because the pipeline worked. Calling that `passed` falsifies
    repository state; leaving it unresolved makes the Decision permanently
    undischargeable. `retired_by_lineage` is the narrow third answer, and it is
    worth nothing unless every part of its evidence is checked against the
    repository rather than against the report's own account of it.
    """

    # -- the outcome works ---------------------------------------------------
    def test_a_sound_retirement_is_reviewer_ready(self):
        report_id, result = self.build()
        self.assertEqual(self.invalid(result), [])
        self.assertIn(report_id, self.reviewer_ready(result))

    def test_the_decision_may_classify_its_own_snapshot_test(self):
        """A future Decision needs no later authorization."""
        self.integration_record()
        self.decision(semantics=[{
            "acceptance_test_index": 2,
            "kind": "live_queue_snapshot",
            "retirement_allowed": True,
            "subjects": [{"id": self.SUBJECT, "path": self.SUBJECT_PATH}],
        }])
        report_id = self.report(authority_id=self.DECISION)
        result = self.scan()
        self.assertEqual(self.invalid(result), [])
        self.assertIn(report_id, self.reviewer_ready(result))

    # -- and cannot be asserted on weaker facts ------------------------------
    def test_a_decision_without_semantics_cannot_retire_its_own_test(self):
        """"A report cannot authorize itself" -- WORK_QUEUES 1.6 condition 2."""
        self.integration_record()
        self.decision()
        report_id = self.report(authority_id=self.DECISION)
        result = self.scan()
        self.assertTrue(any("cannot authorize its own" in m for m in self.invalid(result)))
        self.assertNotIn(report_id, self.reviewer_ready(result))

    def test_a_missing_authority_does_not_retire(self):
        report_id, result = self.build(with_authority=False)
        self.assertTrue(
            any("not an approved Decision" in m for m in self.invalid(result))
        )
        self.assertNotIn(report_id, self.reviewer_ready(result))

    def test_a_stale_authority_checksum_does_not_retire(self):
        """The authority pinned a Decision that has since been re-issued."""
        report_id, result = self.build(
            authority={"checksum": "sha256:" + "0" * 64}
        )
        self.assertTrue(any("at checksum" in m for m in self.invalid(result)))
        self.assertNotIn(report_id, self.reviewer_ready(result))

    def test_an_authority_for_another_index_does_not_retire(self):
        report_id, result = self.build(authority={"index": 1})
        self.assertTrue(
            any("does not authorize retiring" in m for m in self.invalid(result))
        )
        self.assertNotIn(report_id, self.reviewer_ready(result))

    def test_an_authority_for_another_decision_does_not_retire(self):
        report_id, result = self.build(authority={"target": "DEC-2026-9999"})
        self.assertTrue(
            any("does not authorize retiring" in m for m in self.invalid(result))
        )
        self.assertNotIn(report_id, self.reviewer_ready(result))

    def test_a_non_snapshot_test_cannot_be_retired(self):
        report_id, result = self.build(authority={"kind": "behavior"})
        self.assertTrue(
            any("not a live queue snapshot" in m for m in self.invalid(result))
        )
        self.assertNotIn(report_id, self.reviewer_ready(result))

    def test_an_authority_withholding_retirement_does_not_retire(self):
        report_id, result = self.build(authority={"allowed": False})
        self.assertTrue(
            any("does not allow retirement" in m for m in self.invalid(result))
        )
        self.assertNotIn(report_id, self.reviewer_ready(result))

    def test_partial_subject_coverage_does_not_retire(self):
        """Two authorized subjects, one accounted for."""
        report_id, result = self.build(authority={"subjects": [
            {"id": self.SUBJECT, "path": self.SUBJECT_PATH,
             "permitted_retirement_state": "consumed_by_integrated_bundle",
             "integration_record_path": self.RECORD},
            {"id": "GUR-PKT-PHB-001-002-fixture-r01",
             "path": "books/adnd1e/phb/artifacts/gur/GUR-PKT-PHB-001-002-fixture-r01.yaml",
             "permitted_retirement_state": "consumed_by_integrated_bundle",
             "integration_record_path": self.RECORD},
        ]})
        self.assertTrue(any("omits the authorized subject" in m for m in self.invalid(result)))
        self.assertNotIn(report_id, self.reviewer_ready(result))

    def test_an_unauthorized_subject_does_not_retire(self):
        report_id, result = self.build(report={"retired": [
            {"id": "GUP-SOMETHING-ELSE-r01", "path": "books/x.yaml",
             "retirement_state": "consumed_by_integrated_bundle",
             "integration_record_path": self.RECORD,
             "integration_record_checksum": "sha256:" + "0" * 64},
        ]})
        self.assertTrue(any("which its authority does not name" in m for m in self.invalid(result)))

    def test_a_state_the_authority_does_not_permit_does_not_retire(self):
        report_id, result = self.build(report={"retired": [
            {"id": self.SUBJECT, "path": self.SUBJECT_PATH,
             "retirement_state": "superseded_by_integrated_revision",
             "integrated_successor_id": "GUP-PKT-PHB-001-002-fixture-r02",
             "integration_record_path": self.RECORD,
             "integration_record_checksum": "sha256:" + "0" * 64},
        ]})
        self.assertTrue(any("authority permits only" in m for m in self.invalid(result)))

    def test_a_supersession_without_an_integrated_successor_does_not_retire(self):
        """A merely superseded artifact is not retired -- condition 4."""
        self.integration_record()
        self.decision()
        self.authority(subjects=[{
            "id": self.SUBJECT, "path": self.SUBJECT_PATH,
            "permitted_retirement_state": "superseded_by_integrated_revision",
            "integrated_successor_id": "GUP-PKT-PHB-001-002-fixture-r02",
            "integration_record_path": self.RECORD,
        }])
        report_id = self.report(retired=[{
            "id": self.SUBJECT, "path": self.SUBJECT_PATH,
            "retirement_state": "superseded_by_integrated_revision",
            "integration_record_path": self.RECORD,
            "integration_record_checksum": self.sha256(self.RECORD),
        }])
        result = self.scan()
        self.assertTrue(any("no integrated successor" in m for m in self.invalid(result)))
        self.assertNotIn(report_id, self.reviewer_ready(result))

    def test_a_missing_integration_record_does_not_retire(self):
        self.decision()
        self.authority()
        report_id = self.report(retired=[{
            "id": self.SUBJECT, "path": self.SUBJECT_PATH,
            "retirement_state": "consumed_by_integrated_bundle",
            "integration_record_path": self.RECORD,
            "integration_record_checksum": "sha256:" + "0" * 64,
        }])
        result = self.scan()
        self.assertTrue(any("does not exist" in m for m in self.invalid(result)))
        self.assertNotIn(report_id, self.reviewer_ready(result))

    def test_a_stale_integration_record_checksum_does_not_retire(self):
        report_id, result = self.build(report={"retired": [
            {"id": self.SUBJECT, "path": self.SUBJECT_PATH,
             "retirement_state": "consumed_by_integrated_bundle",
             "integration_record_path": self.RECORD,
             "integration_record_checksum": "sha256:" + "0" * 64},
        ]})
        self.assertTrue(
            any("stale integration-record checksum" in m for m in self.invalid(result))
        )
        self.assertNotIn(report_id, self.reviewer_ready(result))

    def test_an_unrelated_integration_record_does_not_retire(self):
        other = (
            "books/adnd1e/phb/artifacts/integrated/"
            "INT-20260101-001-APPROVED-GUP-UNRELATED-r01-r01.json"
        )
        self.integration_record()
        (self.root / other).write_text("{}\n", encoding="utf-8", newline="\n")
        self.decision()
        self.authority()
        report_id = self.report(retired=[{
            "id": self.SUBJECT, "path": self.SUBJECT_PATH,
            "retirement_state": "consumed_by_integrated_bundle",
            "integration_record_path": other,
            "integration_record_checksum": self.sha256(other),
        }])
        result = self.scan()
        self.assertTrue(any("but its authority cites" in m for m in self.invalid(result)))
        self.assertNotIn(report_id, self.reviewer_ready(result))

    def test_an_unapproved_authority_does_not_retire(self):
        self.integration_record()
        self.decision()
        path = self.authority()
        document = yaml.safe_load((self.root / path).read_text(encoding="utf-8"))
        document["status"] = "proposed"
        self.write_yaml(path, document)
        report_id = self.report()
        result = self.scan()
        self.assertTrue(any("not an approved Decision" in m for m in self.invalid(result)))
        self.assertNotIn(report_id, self.reviewer_ready(result))

    def test_an_ordinary_result_may_not_carry_retirement_evidence(self):
        """Guarded in the schema; asserted here so the two cannot drift."""
        import json as _json
        from jsonschema import Draft202012Validator

        repo_root = Path(__file__).resolve().parents[3]
        schema = _json.loads(
            (repo_root / "schemas" / "common" / "decision-implementation.schema.json")
            .read_text(encoding="utf-8")
        )
        result = {
            "acceptance_test_index": 1,
            "result": "passed",
            "evidence": "unit test",
            "retirement_authority": {
                "id": self.AUTHORITY,
                "path": f"rulesets/adnd1e/escalations/decisions/{self.AUTHORITY}.yaml",
                "checksum": "sha256:" + "0" * 64,
                "authorized_acceptance_test_index": 1,
            },
        }
        # Validated through the whole schema so the internal $ref targets resolve.
        subschema = dict(schema["$defs"]["acceptanceResult"])
        subschema["$defs"] = schema["$defs"]
        validator = Draft202012Validator(subschema)
        self.assertTrue(list(validator.iter_errors(result)))
        result.pop("retirement_authority")
        self.assertEqual(list(validator.iter_errors(result)), [])


class RetiredReviewDispositionCase(RetiredLineageFixtureMixin, QueueScannerCase):
    """The Reviewer half of DEC-2026-0028.

    Approving a retired result is the point at which the retirement becomes
    real, so the Review has to re-derive the same evidence rather than take the
    report's word. Allowing a plain `verified` here would make the independent
    check optional exactly where it matters most.
    """

    def implementation_review(self, report_id, *, disposition="verified_retired_by_lineage",
               authority=True, subjects=True, index=2):
        report_path = f"rulesets/adnd1e/decision-implementations/{report_id}.yaml"
        decision_path = f"rulesets/adnd1e/escalations/decisions/{self.DECISION}.yaml"
        authority_path = f"rulesets/adnd1e/escalations/decisions/{self.AUTHORITY}.yaml"
        snapshot = {
            "acceptance_test_index": index,
            "disposition": disposition,
            "evidence": "re-derived from repository state",
        }
        if disposition == "verified_retired_by_lineage":
            if authority:
                snapshot["verified_retirement_authority"] = {
                    "id": self.AUTHORITY,
                    "path": authority_path,
                    "checksum": self.sha256(authority_path),
                    "authorized_acceptance_test_index": index,
                }
            if subjects:
                snapshot["verified_retired_subjects"] = [{
                    "id": self.SUBJECT,
                    "path": self.SUBJECT_PATH,
                    "retirement_state": "consumed_by_integrated_bundle",
                    "integration_record_path": self.RECORD,
                    "integration_record_checksum": self.sha256(self.RECORD),
                }]
        review_id = f"REV-{report_id}-r01"
        self.write_yaml(
            f"rulesets/adnd1e/decision-implementation-reviews/{review_id}.yaml",
            {
                "id": review_id,
                "artifact_kind": "decision_implementation_review",
                "status": "approved",
                "ruleset_id": "adnd1e",
                "revision": 1,
                "supersedes": None,
                "reviewed_by": "reviewer",
                "overall_disposition": "approved",
                "reviewed_implementation": {
                    "id": report_id,
                    "path": report_path,
                    "checksum": self.sha256(report_path),
                },
                "decision_input": {
                    "id": self.DECISION,
                    "path": decision_path,
                    "checksum": self.sha256(decision_path),
                },
                "acceptance_dispositions": [
                    {"acceptance_test_index": 1, "disposition": "verified",
                     "evidence": "re-ran the unit test"},
                    snapshot,
                ],
                "independent_validation": {
                    "passed": True,
                    "commands": [{
                        "command": "python -m unittest", "exit_code": 0,
                        "result": "passed", "summary": "OK",
                    }],
                },
                "handoff": {
                    "next_role": "none", "readiness": "terminal",
                    "reason": "decision complete", "blocking_ids": [],
                },
            },
        )
        return review_id

    def review_invalid(self, result):
        return [
            d["Message"] for d in result["Diagnostics"]
            if d["Code"] == "decision_implementation_review_invalid"
        ]

    def assert_not_consumed(self, report_id, result):
        """An unsound Review sends the work back to the Reviewer, not the Builder.

        The report is sound, so the Builder has nothing to redo. What failed is
        the independent check, and the Decision stays unconsumed until a Review
        that actually re-derives the evidence replaces it.
        """
        ready = {
            (i["Role"], i["InputId"]) for i in result["Items"] if i["State"] == "ready"
        }
        self.assertIn(("Reviewer", report_id), ready)
        self.assertNotIn(("Builder", self.DECISION), ready)

    def test_a_sound_retired_review_consumes_the_decision(self):
        report_id, _ = self.build()
        self.implementation_review(report_id)
        result = self.scan()
        self.assertEqual(self.review_invalid(result), [])
        ready = {
            (i["Role"], i["InputId"]) for i in result["Items"] if i["State"] == "ready"
        }
        self.assertNotIn(("Reviewer", report_id), ready)
        self.assertNotIn(("Builder", self.DECISION), ready)

    def test_plain_verified_cannot_approve_a_retired_result(self):
        report_id, _ = self.build()
        self.implementation_review(report_id, disposition="verified")
        result = self.scan()
        self.assertTrue(
            any("needs verified_retired_by_lineage" in m for m in self.review_invalid(result))
        )
        self.assert_not_consumed(report_id, result)

    def test_a_retired_disposition_on_an_ordinary_result_is_rejected(self):
        report_id, _ = self.build()
        self.implementation_review(report_id, index=1)
        result = self.scan()
        self.assertTrue(
            any("the report records it as 'passed'" in m for m in self.review_invalid(result))
        )
        self.assert_not_consumed(report_id, result)

    def test_a_review_omitting_its_own_authority_is_rejected(self):
        report_id, _ = self.build()
        self.implementation_review(report_id, authority=False)
        result = self.scan()
        self.assertTrue(
            any("records no retirement_authority" in m for m in self.review_invalid(result))
        )
        self.assert_not_consumed(report_id, result)

    def test_a_review_omitting_the_subject_evidence_is_rejected(self):
        report_id, _ = self.build()
        self.implementation_review(report_id, subjects=False)
        result = self.scan()
        self.assertTrue(
            any("omits the authorized subject" in m for m in self.review_invalid(result))
        )
        self.assert_not_consumed(report_id, result)



class ExactDiffOwnershipCase(QueueScannerCase):
    """DEC-2026-0045: every path a Decision changes has an accountable owner.

    DEC-2026-0043 listed four Architect-owned governance files in `exact_diff`
    and assigned them to nobody. Its sequence named builder, reviewer, reviewer;
    its follow_up_owners named builder, reviewer, integrator. The only ready
    handoff was to Builder, which may not write a contract or a role instruction,
    so the Decision could not complete by any action of the role it routed to --
    and nothing noticed until a Review failed acceptance test 5 against an empty
    Architect queue. DEC-2026-0039 had already done the same thing with a test
    file; that gap happened to fall inside Builder competence, so it was closed
    under protest and authorized retroactively by DEC-2026-0041.

    The check compares two sets already inside the Decision: the paths it changes
    and the roles it schedules. It needs no repository state, no timestamps, and
    no judgment about which role looks capable, which is why it can run when the
    Decision is authored instead of when its implementation fails.
    """

    DECISION = "DEC-2026-9801"
    PATHS = ("contracts/WORK_QUEUES.md", "tooling/common/scan_agent_queues.py")

    def decision(
        self,
        *,
        version="1.1",
        ownership="complete",
        sequence=None,
        follow_up=None,
        next_role="builder",
    ):
        """Publish one non-migration Decision whose ownership plan varies."""

        if sequence is None:
            sequence = [
                {"step": 1, "owner": "architect", "action": "publish the contract"},
                {"step": 2, "owner": "builder", "action": "implement the scanner"},
            ]
        if follow_up is None:
            follow_up = {"builder": ["implement it"], "reviewer": ["verify it"]}

        complete = [
            {"path": self.PATHS[0], "owner": "architect", "sequence_step": 1},
            {"path": self.PATHS[1], "owner": "builder", "sequence_step": 2},
        ]
        plans = {
            "complete": complete,
            # The exact DEC-2026-0043 shape: a governance file nobody owns.
            "missing": complete[1:],
            "duplicate": complete + [dict(complete[0])],
            "unowned": [{"path": self.PATHS[0]}, complete[1]],
            "unknown_owner": [
                {"path": self.PATHS[0], "owner": "tooling"},
                complete[1],
            ],
            "unscheduled_owner": [
                {"path": self.PATHS[0], "owner": "analyst"},
                complete[1],
            ],
            "sequence_mismatch": [
                {"path": self.PATHS[0], "owner": "architect", "sequence_step": 2},
                complete[1],
            ],
            "absent_step": [
                {"path": self.PATHS[0], "owner": "architect", "sequence_step": 9},
                complete[1],
            ],
            "stray_path": complete + [
                {"path": "contracts/UNTOUCHED.md", "owner": "builder", "sequence_step": 2}
            ],
            "none": None,
        }

        document = {
            "id": self.DECISION,
            "status": "approved",
            "ruleset_id": "adnd1e",
            "book_id": "phb",
            "migration_required": False,
            "acceptance_tests": ["the guard behaves as ruled"],
            "sequence": sequence,
            "follow_up_owners": follow_up,
            "exact_diff": {path: ["change it"] for path in self.PATHS},
            "handoff": {
                "next_role": next_role,
                "readiness": "ready",
                "reason": "implement it",
                "blocking_ids": [],
            },
        }
        if version is not None:
            document["decision_authoring_contract_version"] = version
        plan = plans[ownership]
        if plan is not None:
            document["exact_diff_ownership"] = plan
        self.write_yaml(
            f"rulesets/adnd1e/escalations/decisions/{self.DECISION}.yaml", document
        )
        return self.scan()

    def ownership_diagnostics(self, result):
        return [
            item
            for item in result["Diagnostics"]
            if item["Code"] == "decision_exact_diff_unowned"
        ]

    def message(self, result):
        found = self.ownership_diagnostics(result)
        self.assertEqual(len(found), 1, f"expected one diagnostic, got {found}")
        return found[0]["Message"]

    def builder_items(self, result):
        return {
            (item["Queue"], item["InputId"])
            for item in result["Items"]
            if item["Role"] == "Builder"
        }

    # -- the fully owned plan is silent ------------------------------------

    def test_a_complete_plan_produces_no_ownership_diagnostic(self):
        result = self.decision(ownership="complete")
        self.assertEqual(self.ownership_diagnostics(result), [])

    def test_a_complete_plan_is_ordinary_implementation_work(self):
        result = self.decision(ownership="complete")
        self.assertIn(("BUILDER-DECISION", self.DECISION), self.builder_items(result))

    # -- each defect the Decision names ------------------------------------

    def test_an_unassigned_path_is_diagnostic(self):
        message = self.message(self.decision(ownership="missing"))
        self.assertIn(self.PATHS[0], message)
        self.assertIn("no exact_diff_ownership entry owns it", message)

    def test_a_duplicate_entry_is_diagnostic(self):
        message = self.message(self.decision(ownership="duplicate"))
        self.assertIn("2 times", message)

    def test_an_entry_without_an_owner_is_diagnostic(self):
        message = self.message(self.decision(ownership="unowned"))
        self.assertIn("names no owner", message)

    def test_an_unknown_owner_is_diagnostic(self):
        message = self.message(self.decision(ownership="unknown_owner"))
        self.assertIn("unknown owner", message)
        self.assertIn("tooling", message)

    def test_an_owner_the_decision_never_schedules_is_diagnostic(self):
        """The DEC-2026-0043 defect stated exactly: a name, but no assignment."""
        message = self.message(self.decision(ownership="unscheduled_owner"))
        self.assertIn("analyst", message)
        self.assertIn("no sequence step or follow_up_owners entry names", message)

    def test_a_sequence_step_owned_by_another_role_is_diagnostic(self):
        message = self.message(self.decision(ownership="sequence_mismatch"))
        self.assertIn("sequence_step 2", message)
        self.assertIn("owned by builder", message)

    def test_a_sequence_step_the_sequence_does_not_define_is_diagnostic(self):
        message = self.message(self.decision(ownership="absent_step"))
        self.assertIn("sequence does not define", message)

    def test_owning_a_path_the_decision_does_not_change_is_diagnostic(self):
        message = self.message(self.decision(ownership="stray_path"))
        self.assertIn("not an exact_diff path", message)

    def test_declaring_the_version_without_any_ownership_is_diagnostic(self):
        message = self.message(self.decision(ownership="none"))
        self.assertIn("records no exact_diff_ownership", message)

    # -- what an invalid plan does to the queue -----------------------------

    def test_an_unowned_plan_is_not_ready_implementation_work(self):
        """WORK_QUEUES 1.12 rule 14: it cannot become approval-ready."""
        result = self.decision(ownership="missing")
        self.assertEqual(self.builder_items(result), set())

    def test_an_unowned_plan_is_reported_blocked_rather_than_dropped(self):
        """Silence is the failure this guard exists to prevent, not its remedy.

        Dropping the item would leave the queue looking clean while a Decision
        no one can complete sits unimplemented -- which is what the repository
        actually did before this rule.
        """
        result = self.decision(ownership="missing")
        blocked = [
            item
            for item in result["BlockedItems"]
            if item["InputId"] == self.DECISION
        ]
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["Role"], "Architect")
        self.assertIn("assign to no role", blocked[0]["Reason"])

    def test_an_integrator_owned_decision_is_guarded_the_same_way(self):
        """Ownership is a property of the plan, not of who was handed it."""
        result = self.decision(ownership="missing", next_role="integrator")
        self.assertEqual(len(self.ownership_diagnostics(result)), 1)
        self.assertEqual(
            [item for item in result["Items"] if item["Role"] == "Integrator"], []
        )

    # -- the rule is opt-in, so history stays valid -------------------------

    def test_a_decision_without_the_version_declaration_is_untouched(self):
        """Every Decision before DEC-2026-0045 omits it and remains valid history."""
        result = self.decision(version=None, ownership="none")
        self.assertEqual(self.ownership_diagnostics(result), [])
        self.assertIn(("BUILDER-DECISION", self.DECISION), self.builder_items(result))

    def test_an_older_authoring_version_is_untouched(self):
        result = self.decision(version="1.0", ownership="none")
        self.assertEqual(self.ownership_diagnostics(result), [])

    def test_every_published_decision_satisfies_the_guard(self):
        """The live corpus, not just fixtures: 45 Decisions, none unowned."""
        repo_root = Path(__file__).resolve().parents[3]
        decisions = sorted(
            (repo_root / "rulesets/adnd1e/escalations/decisions").glob("DEC-*.yaml")
        )
        self.assertGreater(len(decisions), 0)
        offenders = {}
        for path in decisions:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            errors = scanner._exact_diff_ownership_errors(document)
            if errors:
                offenders[path.name] = errors
        self.assertEqual(offenders, {})


class TestExactDiffOwnershipHelpers(unittest.TestCase):
    """The two set-valued helpers the guard rests on, read directly."""

    def test_only_scheduled_sources_count_as_an_assignment(self):
        """`follow_up_owner` singular is deliberately not an assignment.

        WORK_QUEUES 1.12 rule 14 names a sequence step and a `follow_up_owners`
        entry. Reading the older singular field too would widen the rule this
        guard enforces: a role named only there has been recorded as a contact,
        not scheduled to publish anything.
        """
        document = {
            "sequence": [{"step": 1, "owner": "Architect"}],
            "follow_up_owners": {"builder": ["do it"]},
            "follow_up_owner": "integrator",
        }
        self.assertEqual(
            scanner._decision_assigned_roles(document), {"architect", "builder"}
        )

    def test_a_list_shaped_follow_up_owners_is_read(self):
        document = {"follow_up_owners": ["builder", "reviewer"]}
        self.assertEqual(
            scanner._decision_assigned_roles(document), {"builder", "reviewer"}
        )

    def test_sequence_steps_map_to_their_owners(self):
        document = {
            "sequence": [
                {"step": 1, "owner": "architect"},
                {"step": 2, "owner": "builder"},
                {"owner": "reviewer"},
            ]
        }
        self.assertEqual(
            scanner._sequence_owner_by_step(document),
            {1: "architect", 2: "builder"},
        )

    def test_a_decision_with_no_exact_diff_has_nothing_to_own(self):
        document = {"decision_authoring_contract_version": "1.1"}
        self.assertEqual(scanner._exact_diff_ownership_errors(document), [])



class VersionedContractContentCase(QueueScannerCase):
    """DEC-2026-0048: a mutable contract's version as a floor, not a literal.

    DEC-2026-0045 acceptance test 1 named WORK_QUEUES 1.12 and DEC-2026-0046 test
    4 named 1.13. Both were literally false inside a day, not because anything
    regressed but because later approved Decisions advanced the same file while
    every requirement the tests actually stated stayed put. Read literally they
    were permanently undischargeable; read generously by eye, every other
    version-pinned test would have been widened at the same time.

    The ruling makes the widening explicit, per test, and checksummed. These
    tests hold that line from both sides: valid authority passes and reaches
    Review, and absent, stale, mismatched, incomplete or below-minimum authority
    is diagnostic and never approval-ready.
    """

    DECISION = "DEC-2026-9701"
    AUTHORITY = "DEC-2026-9702"
    CONTRACT = "contracts/FIXTURE_CONTRACT.md"
    OTHER = "contracts/FIXTURE_OTHER.md"
    ANCHORS = ["the first required rule", "the second required rule"]

    def write_contract(self, relative=None, version="1.15", anchors=None):
        relative = relative or self.CONTRACT
        anchors = self.ANCHORS if anchors is None else anchors
        body = "\n".join(f"- {a}" for a in anchors)
        (self.root / relative).parent.mkdir(parents=True, exist_ok=True)
        (self.root / relative).write_text(
            f"# Fixture Contract\n\n**Version {version}.**\n\n{body}\n",
            encoding="utf-8",
        )
        return relative

    def sha(self, relative):
        return scanner._sha256_of(self.root / relative)

    def write_decision(self, semantics=None):
        relative = f"rulesets/adnd1e/escalations/decisions/{self.DECISION}.yaml"
        document = {
            "id": self.DECISION,
            "status": "approved",
            "ruleset_id": "adnd1e",
            "book_id": "phb",
            "migration_required": False,
            "acceptance_tests": ["the contract still carries what this Decision needs"],
            "handoff": {
                "next_role": "builder", "readiness": "ready",
                "reason": "implement it", "blocking_ids": [],
            },
        }
        if semantics is not None:
            document["acceptance_test_semantics"] = semantics
        self.write_yaml(relative, document)
        return relative

    def write_authority(self, *, decision_relative, index=1, minimum="1.12",
                        anchors=None, checksum=None, paths=None):
        relative = f"rulesets/adnd1e/escalations/decisions/{self.AUTHORITY}.yaml"
        contracts = [
            {
                "path": path,
                "minimum_version": minimum,
                "substantive_anchors": list(self.ANCHORS if anchors is None else anchors),
            }
            for path in (paths or [self.CONTRACT])
        ]
        self.write_yaml(
            relative,
            {
                "id": self.AUTHORITY,
                "status": "approved",
                "ruleset_id": "adnd1e",
                "book_id": "phb",
                "migration_required": False,
                "acceptance_tests": ["authorize the legacy test"],
                "contract_version_acceptance_authorizations": [
                    {
                        "decision_input": {
                            "id": self.DECISION,
                            "path": decision_relative,
                            "checksum": checksum or self.sha(decision_relative),
                        },
                        "acceptance_test_index": index,
                        "contracts": contracts,
                    }
                ],
                "handoff": {
                    "next_role": "none", "readiness": "terminal",
                    "reason": "ruled", "blocking_ids": [],
                },
            },
        )
        return relative

    def write_report(self, decision_relative, *, evidence=None, index=1,
                     result="passed", authority_relative=None, authority_id=None):
        report_id = f"IMP-{self.DECISION}-r01"
        entry = {"acceptance_test_index": index, "result": result,
                 "evidence": "verified against the current contract"}
        if evidence is not None:
            entry["versioned_contract_content"] = evidence
        self.write_yaml(
            f"rulesets/adnd1e/decision-implementations/{report_id}.yaml",
            {
                "schema_version": "1.0",
                "id": report_id,
                "artifact_kind": "decision_implementation",
                "status": "proposed",
                "ruleset_id": "adnd1e",
                "constitution_version": "1.8",
                "revision": 1,
                "supersedes": None,
                "approval_ready": True,
                "implemented_by": "builder",
                "decision_input": {
                    "id": self.DECISION,
                    "path": decision_relative,
                    "checksum": self.sha(decision_relative),
                },
                "implementation_files": [
                    {"path": self.CONTRACT, "checksum": self.sha(self.CONTRACT)}
                ],
                "acceptance_results": [entry],
                "validation": {
                    "passed": True,
                    "commands": [{"command": "suite", "exit_code": 0,
                                  "result": "passed", "summary": "Ran 1 test OK"}],
                },
                "handoff": {"next_role": "reviewer", "readiness": "ready",
                            "reason": "done", "blocking_ids": []},
            },
        )
        return report_id

    def evidence(self, authority_relative, *, index=1, minimum="1.12",
                 observed=None, anchors=None, checksum=None, paths=None,
                 authority_id=None, authority_checksum=None):
        return {
            "authority": {
                "id": authority_id or self.AUTHORITY,
                "path": authority_relative,
                "checksum": authority_checksum or self.sha(authority_relative),
                "authorized_acceptance_test_index": index,
            },
            "authorized_acceptance_test_index": index,
            "contracts": [
                {
                    "path": path,
                    "checksum": checksum or self.sha(path),
                    "observed_version": observed or "1.15",
                    "minimum_version": minimum,
                    "anchors_present": list(self.ANCHORS if anchors is None else anchors),
                }
                for path in (paths or [self.CONTRACT])
            ],
        }

    def build(self, **overrides):
        """The whole valid arrangement; overrides bend exactly one piece."""
        self.write_contract()
        decision_relative = self.write_decision()
        authority_relative = self.write_authority(
            decision_relative=decision_relative,
            index=overrides.pop("authorized_index", 1),
            minimum=overrides.pop("authorized_minimum", "1.12"),
            anchors=overrides.pop("authorized_anchors", None),
            checksum=overrides.pop("pinned_decision_checksum", None),
            paths=overrides.pop("authorized_paths", None),
        )
        evidence = self.evidence(authority_relative, **overrides)
        self.write_report(decision_relative, evidence=evidence)
        return self.scan()

    def diagnostics(self, result):
        return [
            d for d in result["Diagnostics"]
            if d["Code"] == "decision_implementation_invalid"
        ]

    def message(self, result):
        found = self.diagnostics(result)
        self.assertTrue(found, "expected the report to be diagnostic")
        return " ".join(d["Message"] for d in found)

    def reviewer_items(self, result):
        return {i["InputId"] for i in result["Items"] if i["Role"] == "Reviewer"}

    def builder_items(self, result):
        return {i["InputId"] for i in result["Items"] if i["Role"] == "Builder"}

    # -- valid authority -----------------------------------------------------

    def test_valid_evidence_is_not_diagnostic(self):
        result = self.build()
        self.assertEqual(self.diagnostics(result), [])

    def test_valid_evidence_reaches_the_reviewer(self):
        """Current-state evidence is still reviewed; it is not self-approving."""
        result = self.build()
        self.assertIn(f"IMP-{self.DECISION}-r01", self.reviewer_items(result))

    def test_a_version_above_the_floor_satisfies_it(self):
        """1.15 against a 1.12 floor: the case the whole ruling exists for."""
        result = self.build(minimum="1.12", observed="1.15")
        self.assertEqual(self.diagnostics(result), [])

    def test_the_floor_compares_numerically_not_as_text(self):
        """1.9 must not read as above 1.12 merely because '9' sorts after '1'."""
        self.write_contract(version="1.9")
        decision_relative = self.write_decision()
        authority_relative = self.write_authority(decision_relative=decision_relative)
        self.write_report(
            decision_relative,
            evidence=self.evidence(authority_relative, observed="1.9"),
        )
        self.assertIn("1.12 or later", self.message(self.scan()))

    def test_a_decision_declaring_its_own_semantics_needs_no_authorization(self):
        self.write_contract()
        decision_relative = self.write_decision(
            semantics=[
                {
                    "acceptance_test_index": 1,
                    "kind": "versioned_contract_content",
                    "contracts": [
                        {
                            "path": self.CONTRACT,
                            "minimum_version": "1.12",
                            "substantive_anchors": list(self.ANCHORS),
                        }
                    ],
                }
            ]
        )
        evidence = self.evidence(decision_relative, authority_id=self.DECISION)
        self.write_report(decision_relative, evidence=evidence)
        self.assertEqual(self.diagnostics(self.scan()), [])

    # -- everything the ruling says must be rejected -------------------------

    def test_evidence_with_no_authorization_is_diagnostic(self):
        self.write_contract()
        decision_relative = self.write_decision()
        authority_relative = self.write_authority(decision_relative=decision_relative)
        # The authority covers index 1; the report claims index 2.
        self.write_report(
            decision_relative,
            evidence=self.evidence(authority_relative, index=2),
            index=2,
        )
        self.assertIn("does not authorize", self.message(self.scan()))

    def test_an_absent_authority_is_diagnostic(self):
        self.write_contract()
        decision_relative = self.write_decision()
        evidence = self.evidence(
            f"rulesets/adnd1e/escalations/decisions/{self.AUTHORITY}.yaml",
            authority_checksum="sha256:" + "0" * 64,
        )
        self.write_report(decision_relative, evidence=evidence)
        self.assertIn("not an approved Decision", self.message(self.scan()))

    def test_a_stale_authority_checksum_is_diagnostic(self):
        result = self.build(authority_checksum="sha256:" + "1" * 64)
        self.assertIn("stale checksum for authority", self.message(result))

    def test_an_authorization_pinned_to_another_decision_checksum_is_diagnostic(self):
        """A rewritten Decision loses its authorization rather than keeping it."""
        result = self.build(pinned_decision_checksum="sha256:" + "2" * 64)
        self.assertIn("different checksum", self.message(result))

    def test_a_mismatched_authorized_index_is_diagnostic(self):
        result = self.build(index=1, authorized_index=1)
        self.assertEqual(self.diagnostics(result), [])
        self.tearDown(); self.setUp()
        self.write_contract()
        decision_relative = self.write_decision()
        authority_relative = self.write_authority(decision_relative=decision_relative)
        evidence = self.evidence(authority_relative)
        evidence["authorized_acceptance_test_index"] = 7
        self.write_report(decision_relative, evidence=evidence)
        self.assertIn("authority for index", self.message(self.scan()))

    def test_a_below_minimum_contract_is_diagnostic(self):
        self.write_contract(version="1.11")
        decision_relative = self.write_decision()
        authority_relative = self.write_authority(decision_relative=decision_relative)
        self.write_report(
            decision_relative,
            evidence=self.evidence(authority_relative, observed="1.11"),
        )
        self.assertIn("or later", self.message(self.scan()))

    def test_incomplete_anchor_evidence_is_diagnostic(self):
        result = self.build(anchors=[self.ANCHORS[0]])
        message = self.message(result)
        self.assertIn("authorized anchor", message)
        self.assertIn(self.ANCHORS[1], message)

    def test_a_stale_contract_checksum_is_diagnostic(self):
        result = self.build(checksum="sha256:" + "3" * 64)
        self.assertIn("stale checksum", self.message(result))

    def test_an_observed_version_disagreeing_with_the_file_is_diagnostic(self):
        """The report may not simply assert a version the file does not carry."""
        result = self.build(observed="9.99")
        self.assertIn("but the file declares", self.message(result))

    def test_a_declared_minimum_below_the_authorized_one_is_diagnostic(self):
        result = self.build(minimum="1.00", authorized_minimum="1.12")
        self.assertIn("its authority grants", self.message(result))

    def test_evidence_for_an_unauthorized_contract_is_diagnostic(self):
        self.write_contract()
        self.write_contract(relative=self.OTHER)
        decision_relative = self.write_decision()
        authority_relative = self.write_authority(decision_relative=decision_relative)
        evidence = self.evidence(authority_relative)
        evidence["contracts"].append(
            {
                "path": self.OTHER,
                "checksum": self.sha(self.OTHER),
                "observed_version": "1.15",
                "minimum_version": "1.12",
                "anchors_present": list(self.ANCHORS),
            }
        )
        self.write_report(decision_relative, evidence=evidence)
        self.assertIn("which its authority does not name", self.message(self.scan()))

    def test_missing_evidence_for_an_authorized_contract_is_diagnostic(self):
        self.write_contract()
        self.write_contract(relative=self.OTHER)
        decision_relative = self.write_decision()
        authority_relative = self.write_authority(
            decision_relative=decision_relative, paths=[self.CONTRACT, self.OTHER]
        )
        self.write_report(
            decision_relative, evidence=self.evidence(authority_relative)
        )
        self.assertIn("records no current evidence", self.message(self.scan()))

    def test_this_outcome_may_not_be_carried_on_a_failed_result(self):
        self.write_contract()
        decision_relative = self.write_decision()
        authority_relative = self.write_authority(decision_relative=decision_relative)
        self.write_report(
            decision_relative,
            evidence=self.evidence(authority_relative),
            result="failed",
        )
        self.assertIn("reported as passed", self.message(self.scan()))

    # -- the queue consequence the ruling requires ---------------------------

    def test_an_invalid_report_is_not_approval_ready(self):
        """It must not reach Reviewer, and the Decision returns to its owner."""
        result = self.build(anchors=[self.ANCHORS[0]])
        self.assertNotIn(f"IMP-{self.DECISION}-r01", self.reviewer_items(result))
        self.assertIn(self.DECISION, self.builder_items(result))

    def test_a_report_without_this_evidence_is_untouched(self):
        """The check applies only where the evidence is claimed."""
        self.write_contract()
        decision_relative = self.write_decision()
        self.write_report(decision_relative, evidence=None)
        self.assertEqual(self.diagnostics(self.scan()), [])



class VersionedContractReviewCase(VersionedContractContentCase):
    """The Review half of DEC-2026-0048, which the first implementation missed.

    The schema gained `verified_versioned_contract_content` but the queue's
    approved-review validator still fell through to "rather than verified", so a
    Reviewer using the disposition the ruling requires had its Review rejected.
    REV-IMP-DEC-2026-0048-r01-r02 caught it, and the two authorized reports
    demonstrated it: both were validly structured and both stalled solely on the
    disposition value.

    The Reviewer re-derives the evidence through exactly the validation the
    report went through, so the two cannot drift apart.
    """

    def write_review(self, report_id, decision_relative, *, disposition,
                     evidence=None, overall="approved"):
        review_id = f"REV-{report_id}-r01"
        report_relative = f"rulesets/adnd1e/decision-implementations/{report_id}.yaml"
        entry = {
            "acceptance_test_index": 1,
            "disposition": disposition,
            "evidence": "independently re-derived",
        }
        if evidence is not None:
            entry["verified_versioned_contract_content"] = evidence
        self.write_yaml(
            f"rulesets/adnd1e/decision-implementation-reviews/{review_id}.yaml",
            {
                "schema_version": "1.0",
                "id": review_id,
                "artifact_kind": "decision_implementation_review",
                "status": overall,
                "ruleset_id": "adnd1e",
                "constitution_version": "1.8",
                "revision": 1,
                "supersedes": None,
                "reviewed_by": "reviewer",
                "reviewed_implementation": {
                    "id": report_id,
                    "path": report_relative,
                    "checksum": self.sha(report_relative),
                },
                "decision_input": {
                    "id": self.DECISION,
                    "path": decision_relative,
                    "checksum": self.sha(decision_relative),
                },
                "acceptance_dispositions": [entry],
                "independent_validation": {
                    "passed": True,
                    "commands": [{"command": "suite", "exit_code": 0,
                                  "result": "passed", "summary": "Ran 1 test OK"}],
                },
                "overall_disposition": overall,
                "handoff": {
                    "next_role": "none" if overall == "approved" else "builder",
                    "readiness": "terminal" if overall == "approved" else "ready",
                    "reason": "reviewed", "blocking_ids": [],
                },
            },
        )
        return review_id

    def arrange(self, *, disposition="verified_versioned_contract_content",
                mirror=True, mutate=None):
        self.write_contract()
        decision_relative = self.write_decision()
        authority_relative = self.write_authority(decision_relative=decision_relative)
        evidence = self.evidence(authority_relative)
        report_id = self.write_report(decision_relative, evidence=evidence)
        mirrored = None
        if mirror:
            mirrored = json.loads(json.dumps(evidence))
            if mutate:
                mutate(mirrored)
        self.write_review(
            report_id, decision_relative, disposition=disposition, evidence=mirrored
        )
        return self.scan()

    def review_diagnostics(self, result):
        return [
            d for d in result["Diagnostics"]
            if d["Code"] == "decision_implementation_review_invalid"
        ]

    # -- the branch that was missing ----------------------------------------

    def test_a_valid_versioned_review_is_accepted(self):
        result = self.arrange()
        self.assertEqual(self.review_diagnostics(result), [])

    def test_a_valid_versioned_review_consumes_the_decision(self):
        """An Approved Review completes the Decision; no work should remain."""
        result = self.arrange()
        self.assertEqual(self.builder_items(result), set())
        self.assertEqual(self.reviewer_items(result), set())

    # -- and the ways it must still be refused -------------------------------

    def test_the_disposition_requires_its_own_verification(self):
        result = self.arrange(mirror=False)
        self.assertIn(
            "without recording its own verification",
            " ".join(d["Message"] for d in self.review_diagnostics(result)),
        )

    def test_the_reviewer_evidence_is_re_derived_not_trusted(self):
        """A Review asserting a version the file does not carry is rejected."""
        result = self.arrange(
            mutate=lambda block: block["contracts"][0].__setitem__("observed_version", "9.99")
        )
        self.assertIn(
            "independent verification:",
            " ".join(d["Message"] for d in self.review_diagnostics(result)),
        )

    def test_a_reviewer_dropping_an_anchor_is_rejected(self):
        result = self.arrange(
            mutate=lambda block: block["contracts"][0].__setitem__(
                "anchors_present", [self.ANCHORS[0]]
            )
        )
        self.assertIn(
            "authorized anchor",
            " ".join(d["Message"] for d in self.review_diagnostics(result)),
        )

    def test_plain_verified_cannot_approve_this_evidence(self):
        """The converse guard: it would make the re-derivation optional."""
        result = self.arrange(disposition="verified", mirror=False)
        self.assertIn(
            "needs verified_versioned_contract_content",
            " ".join(d["Message"] for d in self.review_diagnostics(result)),
        )

    def test_the_disposition_needs_the_report_to_claim_the_evidence(self):
        """A Reviewer may not invent this outcome for an ordinary result."""
        self.write_contract()
        decision_relative = self.write_decision()
        authority_relative = self.write_authority(decision_relative=decision_relative)
        report_id = self.write_report(decision_relative, evidence=None)
        self.write_review(
            report_id, decision_relative,
            disposition="verified_versioned_contract_content",
            evidence=self.evidence(authority_relative),
        )
        self.assertIn(
            "claims no versioned contract-content evidence",
            " ".join(d["Message"] for d in self.review_diagnostics(self.scan())),
        )

    def test_an_invalid_versioned_review_does_not_consume_the_decision(self):
        """The report is sound, so it waits for a sound Review.

        An unsound Review neither completes the Decision nor sends the report
        back to its author: nothing is wrong with the report. It stays in the
        Reviewer queue until a Review that re-derives the evidence arrives.
        """
        result = self.arrange(mirror=False)
        self.assertIn(f"IMP-{self.DECISION}-r01", self.reviewer_items(result))
        self.assertEqual(self.builder_items(result), set())


class TestVersionedContractHelpers(unittest.TestCase):
    """The version reading the guard rests on."""

    def test_a_contract_version_is_read_from_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contracts").mkdir()
            (root / "contracts/X.md").write_text(
                "# X\n\n**Version 1.15.**\n\nbody\n", encoding="utf-8"
            )
            self.assertEqual(
                scanner._declared_contract_version(root, "contracts/X.md"), "1.15"
            )

    def test_a_file_without_a_version_reads_as_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contracts").mkdir()
            (root / "contracts/X.md").write_text("# X\n\nno version\n", encoding="utf-8")
            self.assertIsNone(scanner._declared_contract_version(root, "contracts/X.md"))

    def test_an_absent_file_reads_as_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(
                scanner._declared_contract_version(Path(tmp), "contracts/missing.md")
            )

    def test_versions_compare_numerically(self):
        self.assertGreater(scanner._version_tuple("1.15"), scanner._version_tuple("1.12"))
        self.assertLess(scanner._version_tuple("1.9"), scanner._version_tuple("1.12"))
        self.assertGreaterEqual(scanner._version_tuple("1.12"), scanner._version_tuple("1.12"))

    def test_a_malformed_version_is_none(self):
        self.assertIsNone(scanner._version_tuple("one point five"))


class DecisionReissueLineageCase(QueueScannerCase):
    """WORK_QUEUES 1.7 Decision reissue, per DEC-2026-0031 acceptance test 2.

    Architect Decisions are immutable, so a correction is a new Decision naming
    the old one in `supersedes`. Both files stay on disk. Before this rule the
    predecessor kept producing a ready Builder job beside its own replacement,
    which is exactly what DEC-2026-0030 and DEC-2026-0031 did.

    The load-bearing half is what happens when a reissue is *malformed*: it must
    be reported and suppress nothing, so a broken correction can never quietly
    cancel the job it was meant to fix.
    """

    def decision(
        self,
        decision_id,
        *,
        ruleset="adnd1e",
        migration=True,
        revision=1,
        supersedes=None,
        status="approved",
    ):
        self.write_yaml(
            f"rulesets/{ruleset}/escalations/decisions/{decision_id}.yaml",
            {
                "id": decision_id,
                "status": status,
                "ruleset_id": ruleset,
                "book_id": "phb",
                "revision": revision,
                "supersedes": supersedes,
                "migration_required": migration,
                "acceptance_tests": ["fixture"],
                "handoff": {
                    "next_role": "builder",
                    "readiness": "ready",
                    "reason": "fixture",
                    "blocking_ids": [],
                },
            },
        )
        return decision_id

    def builder_decision_ids(self, result):
        return sorted(
            item["InputId"]
            for item in result["Items"]
            if item["Role"] == "Builder" and item["Queue"].startswith("BUILDER-DECISION")
        )

    def lineage_errors(self, result):
        return [
            d["Message"]
            for d in result["Diagnostics"]
            if d["Code"] == "decision_reissue_lineage_error"
        ]

    def test_a_valid_reissue_leaves_only_the_leaf_job(self):
        self.decision("DEC-2026-9001", revision=1)
        self.decision("DEC-2026-9002", revision=2, supersedes="DEC-2026-9001")
        result = self.scan()
        self.assertEqual(self.builder_decision_ids(result), ["DEC-2026-9002"])
        self.assertEqual(self.lineage_errors(result), [])

    def test_a_valid_reissue_leaves_the_predecessor_file_alone(self):
        path = self.root / "rulesets/adnd1e/escalations/decisions/DEC-2026-9001.yaml"
        self.decision("DEC-2026-9001", revision=1)
        before = path.read_bytes()
        self.decision("DEC-2026-9002", revision=2, supersedes="DEC-2026-9001")
        self.scan()
        self.assertEqual(path.read_bytes(), before)

    def test_an_unrelated_decision_is_untouched_by_a_reissue_elsewhere(self):
        self.decision("DEC-2026-9001", revision=1)
        self.decision("DEC-2026-9002", revision=2, supersedes="DEC-2026-9001")
        self.decision("DEC-2026-9009", revision=1)
        result = self.scan()
        self.assertEqual(
            self.builder_decision_ids(result), ["DEC-2026-9002", "DEC-2026-9009"]
        )

    def test_a_missing_predecessor_is_an_error_and_suppresses_nothing(self):
        self.decision("DEC-2026-9002", revision=2, supersedes="DEC-2026-9001")
        result = self.scan()
        self.assertEqual(self.builder_decision_ids(result), ["DEC-2026-9002"])
        self.assertTrue(
            any("is not an approved Decision" in m for m in self.lineage_errors(result))
        )

    def test_an_unapproved_predecessor_is_an_error_and_suppresses_nothing(self):
        self.decision("DEC-2026-9001", revision=1, status="proposed")
        self.decision("DEC-2026-9002", revision=2, supersedes="DEC-2026-9001")
        result = self.scan()
        # The predecessor was never approved, so it produced no job of its own;
        # what matters is that the reissue did not silently inherit authority.
        self.assertEqual(self.builder_decision_ids(result), ["DEC-2026-9002"])
        self.assertTrue(
            any("is not an approved Decision" in m for m in self.lineage_errors(result))
        )

    def test_a_cross_ruleset_reissue_is_an_error_and_says_so(self):
        (self.root / "rulesets" / "osric" / "escalations" / "decisions").mkdir(
            parents=True, exist_ok=True
        )
        self.decision("DEC-2026-9001", ruleset="osric", revision=1)
        self.decision("DEC-2026-9002", revision=2, supersedes="DEC-2026-9001")
        result = self.scan()
        self.assertIn("DEC-2026-9002", self.builder_decision_ids(result))
        self.assertIn("DEC-2026-9001", self.builder_decision_ids(result))
        self.assertTrue(
            any("does not cross rulesets" in m for m in self.lineage_errors(result))
        )

    def test_a_changed_migration_flag_is_an_error_and_suppresses_nothing(self):
        self.decision("DEC-2026-9001", revision=1, migration=True)
        self.decision(
            "DEC-2026-9002", revision=2, supersedes="DEC-2026-9001", migration=False
        )
        result = self.scan()
        self.assertEqual(
            self.builder_decision_ids(result), ["DEC-2026-9001", "DEC-2026-9002"]
        )
        self.assertTrue(
            any(
                "preserves the predecessor" in m
                for m in self.lineage_errors(result)
            )
        )

    def test_a_forked_reissue_is_an_error_and_suppresses_nothing(self):
        self.decision("DEC-2026-9001", revision=1)
        self.decision("DEC-2026-9002", revision=2, supersedes="DEC-2026-9001")
        self.decision("DEC-2026-9003", revision=2, supersedes="DEC-2026-9001")
        result = self.scan()
        self.assertEqual(
            self.builder_decision_ids(result),
            ["DEC-2026-9001", "DEC-2026-9002", "DEC-2026-9003"],
        )
        self.assertTrue(
            any("at most one direct successor" in m for m in self.lineage_errors(result))
        )

    def test_a_reissue_that_does_not_advance_the_revision_is_an_error(self):
        self.decision("DEC-2026-9001", revision=2)
        self.decision("DEC-2026-9002", revision=2, supersedes="DEC-2026-9001")
        result = self.scan()
        self.assertEqual(
            self.builder_decision_ids(result), ["DEC-2026-9001", "DEC-2026-9002"]
        )
        self.assertTrue(any("not later than" in m for m in self.lineage_errors(result)))

    def test_a_non_migration_reissue_also_derives_from_the_leaf(self):
        """The rule is about Decision lineage, not about the migration flag."""
        self.decision("DEC-2026-9001", revision=1, migration=False)
        self.decision(
            "DEC-2026-9002", revision=2, supersedes="DEC-2026-9001", migration=False
        )
        result = self.scan()
        self.assertEqual(self.builder_decision_ids(result), ["DEC-2026-9002"])

    def test_a_three_step_lineage_leaves_only_the_last(self):
        self.decision("DEC-2026-9001", revision=1)
        self.decision("DEC-2026-9002", revision=2, supersedes="DEC-2026-9001")
        self.decision("DEC-2026-9003", revision=3, supersedes="DEC-2026-9002")
        result = self.scan()
        self.assertEqual(self.builder_decision_ids(result), ["DEC-2026-9003"])
        self.assertEqual(self.lineage_errors(result), [])

    def test_the_live_superseded_pipes_decision_creates_no_builder_job(self):
        """The case that motivated the rule, against the real repository.

        Only the superseded half is asserted. Whether DEC-2026-0031 is itself
        ready depends on whether a migration has consumed it yet, and pinning
        that would make this test a claim about which artifact is current --
        true today and false the next time the lineage advances.
        """
        repo_root = Path(__file__).resolve().parents[3]
        decisions = repo_root / "rulesets" / "adnd1e" / "escalations" / "decisions"
        if not (decisions / "DEC-2026-0031.yaml").exists():  # pragma: no cover
            self.skipTest("DEC-2026-0031 is not present")
        result = scanner.scan_repository(repo_root)
        ready = {
            item["InputId"]
            for item in result["Items"]
            if item["Role"] == "Builder" and item["Queue"].startswith("BUILDER-DECISION")
        }
        self.assertNotIn("DEC-2026-0030", ready)
        self.assertTrue(
            (decisions / "DEC-2026-0030.yaml").exists(),
            "the superseded Decision stays on disk as history",
        )
        self.assertEqual(
            [
                d["Message"]
                for d in result["Diagnostics"]
                if d["Code"] == "decision_reissue_lineage_error"
            ],
            [],
            "the live reissue lineage is valid",
        )
