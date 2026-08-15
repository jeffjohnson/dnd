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
