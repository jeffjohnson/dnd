from __future__ import annotations

import importlib.util
import json
import os
import sys
import shutil
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

#: The repository itself, for the live-corpus cases.
REPO_ROOT = Path(__file__).resolve().parents[3]


class DiagnosticsConsoleFormattingTests(unittest.TestCase):
    def test_console_diagnostics_are_enabled_by_default(self):
        self.assertTrue(scanner._parse_args([]).verbose)
        self.assertTrue(scanner._parse_args(["-v"]).verbose)

    def test_console_diagnostics_can_be_disabled(self):
        for arguments in (
            ["-v", "false"],
            ["-v=false"],
            ["--verbose", "false"],
            ["--verbose=false"],
        ):
            with self.subTest(arguments=arguments):
                self.assertFalse(scanner._parse_args(arguments).verbose)

    def test_quiet_console_omits_the_diagnostics_section(self):
        result = {
            "RepositoryRoot": "fixture",
            "Summary": [
                {
                    "Role": role,
                    "Ready": 0,
                    "Active": 0,
                    "Blocked": 0,
                    "Informational": 0,
                }
                for role in scanner.ROLE_ORDER
            ],
            "Items": [],
            "ActiveItems": [],
            "BlockedItems": [],
            "InformationalItems": [],
            "Diagnostics": [
                {
                    "Severity": "info",
                    "Code": "fixture",
                    "ArtifactId": "FIXTURE",
                    "Message": "This must not be printed.",
                }
            ],
            "ReadyCount": 0,
            "ActiveCount": 0,
            "BlockedCount": 0,
            "DiagnosticCount": 1,
        }
        output = StringIO()
        with redirect_stdout(output):
            scanner._print_console(result, include_all=False, show_diagnostics=False)
        self.assertNotIn("Diagnostics", output.getvalue())
        self.assertNotIn("This must not be printed.", output.getvalue())

    def test_default_console_includes_the_diagnostics_section(self):
        result = {
            "RepositoryRoot": "fixture",
            "Summary": [
                {
                    "Role": role,
                    "Ready": 0,
                    "Active": 0,
                    "Blocked": 0,
                    "Informational": 0,
                }
                for role in scanner.ROLE_ORDER
            ],
            "Items": [],
            "ActiveItems": [],
            "BlockedItems": [],
            "InformationalItems": [],
            "Diagnostics": [
                {
                    "Severity": "info",
                    "Code": "fixture",
                    "ArtifactId": "FIXTURE",
                    "Message": "This is printed by default.",
                }
            ],
            "ReadyCount": 0,
            "ActiveCount": 0,
            "BlockedCount": 0,
            "DiagnosticCount": 1,
        }
        output = StringIO()
        with redirect_stdout(output):
            scanner._print_console(result, include_all=False)
        self.assertIn("Diagnostics", output.getvalue())
        self.assertIn("This is printed by default.", output.getvalue())

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


DEFAULT_REVIEW_ID = object()


class QueueScannerCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "README.md").write_text("# fixture\n", encoding="utf-8")
        # The scanner reads the schemas it enforces from the tree it is scanning
        # -- the handoff vocabulary, and under DEC-2026-0061 the exact Decision
        # Implementation Review schema. A fixture without them would exercise
        # fallback paths instead of the real rules.
        schemas = self.root / "schemas" / "common"
        schemas.mkdir(parents=True, exist_ok=True)
        for source in sorted((REPO_ROOT / "schemas" / "common").glob("*.json")):
            shutil.copyfile(source, schemas / source.name)
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
        review_id=DEFAULT_REVIEW_ID,
    ):
        artifact_id = f"GUP-{packet}-r{revision:02d}"
        provenance = {"gur_id": gur_id}
        # Distinguished from None on purpose. A GUP that records no review_id at
        # all is a legacy artifact and reads differently under DEC-2026-0054 from
        # one that carries the field and names something else.
        if review_id is not DEFAULT_REVIEW_ID:
            provenance["review_id"] = review_id
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/gup/{artifact_id}.yaml",
            {
                "id": artifact_id,
                "packet_id": packet,
                "revision": revision,
                "supersedes": supersedes,
                "status": status,
                "approval_ready": approval_ready,
                "provenance": provenance,
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

    def review(
        self,
        packet: str,
        gup_id: str,
        disposition="approved",
        *,
        revision: int = 1,
        supersedes=None,
        handoff_role: str | None = None,
    ):
        artifact_id = f"REV-{gup_id}-r{revision:02d}"
        document = {
            "id": artifact_id,
            "packet_id": packet,
            "revision": revision,
            "supersedes": supersedes,
            "status": disposition,
            "overall_disposition": disposition,
            "reviewed_gup": {"id": gup_id},
        }
        if handoff_role:
            document["handoff"] = {
                "next_role": handoff_role,
                "readiness": "ready",
                "reason": "fixture",
                "blocking_ids": [],
            }
            document["required_builder_revision"] = {
                "successor_gup_id": f"GUP-{packet}-r99",
                "exact_correction": "fixture correction",
            }
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/reviews/{artifact_id}.yaml", document
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
                # Both version fields are required by the Review schema, which
                # DEC-2026-0061 now enforces before a Review can consume.
                "schema_version": "1.0",
                "id": f"REV-{report_id}-r01",
                "artifact_kind": "decision_implementation_review",
                "status": "approved",
                "ruleset_id": "adnd1e",
                "constitution_version": "1.7",
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
    #: DEC-2026-0105's own shape: a conforming blocked GUR routed to Architect,
    #: modelled on the real GUR-PKT-SD-189-189-monster-attributes-r01 blocker.
    BLOCKED_HANDOFF = {
        "next_role": "architect",
        "readiness": "blocked",
        "reason": (
            "monster level has no identity and no approved prefix covers a "
            "creature statistic"
        ),
        "blocking_ids": ["ESC-2026-09-30T06.00.29.086Z"],
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

    # -- acceptance test 5 (DEC-2026-0105): a conforming blocked handoff ----

    def blocked_routed(self, result, queue):
        return [item["InputId"] for item in result["BlockedItems"] if item["Queue"] == queue]

    def test_a_blocked_leaf_produces_exactly_one_blocked_item(self):
        leaf = self.gur_with_handoff(1, self.BLOCKED_HANDOFF)
        result = self.scan()
        items = [i for i in result["BlockedItems"] if i["InputId"] == leaf]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["State"], "blocked")

    def test_a_blocked_leaf_never_appears_among_ready_items(self):
        leaf = self.gur_with_handoff(1, self.BLOCKED_HANDOFF)
        result = self.scan()
        self.assertNotIn(leaf, [i["InputId"] for i in result["Items"]])

    def test_a_blocked_leaf_routes_to_its_declared_next_role(self):
        leaf = self.gur_with_handoff(1, self.BLOCKED_HANDOFF)
        result = self.scan()
        item = next(i for i in result["BlockedItems"] if i["InputId"] == leaf)
        self.assertEqual(item["Role"], "Architect")
        self.assertEqual(item["Queue"], "ARCHITECT-BLOCKED-GUR")

    def test_a_blocked_leaf_preserves_its_blocking_ids(self):
        leaf = self.gur_with_handoff(1, self.BLOCKED_HANDOFF)
        result = self.scan()
        item = next(i for i in result["BlockedItems"] if i["InputId"] == leaf)
        self.assertIn("ESC-2026-09-30T06.00.29.086Z", item["Reason"])

    def test_a_blocked_leaf_preserves_its_authored_reason(self):
        """WORK_QUEUES 1.35 rule 6a: blocking_ids *and* reason are preserved.

        A generated "waiting on: <ids>" string keeps the IDs but discards the
        Analyst's own account of the blocker; both must survive routing.
        """
        leaf = self.gur_with_handoff(1, self.BLOCKED_HANDOFF)
        result = self.scan()
        item = next(i for i in result["BlockedItems"] if i["InputId"] == leaf)
        self.assertIn(self.BLOCKED_HANDOFF["reason"], item["Reason"])
        self.assertIn("ESC-2026-09-30T06.00.29.086Z", item["Reason"])

    def test_a_blocked_leaf_never_produces_a_builder_gur_item(self):
        self.gur_with_handoff(1, self.BLOCKED_HANDOFF)
        result = self.scan()
        self.assertEqual(self.routed(result, "BUILDER-GUR"), [])

    def test_a_blocked_leaf_gets_no_legacy_inference(self):
        self.gur_with_handoff(1, self.BLOCKED_HANDOFF)
        result = self.scan()
        self.assertEqual(self.coded(result, "legacy_handoff_inference"), [])

    def test_a_blocked_leaf_raises_no_invalid_handoff_error(self):
        self.gur_with_handoff(1, self.BLOCKED_HANDOFF)
        result = self.scan()
        self.assertEqual(self.coded(result, "gur_invalid_handoff"), [])

    def test_a_blocked_leaf_does_not_contribute_to_ready_count(self):
        self.gur_with_handoff(1, self.BLOCKED_HANDOFF)
        result = self.scan()
        self.assertEqual(result["ReadyCount"], 0)
        self.assertEqual(result["BlockedCount"], 1)

    def test_a_blocked_leaf_routes_dynamically_by_its_own_role_not_a_constant(self):
        """The routed role follows the handoff; Architect above is not hardcoded."""
        builder_blocked = dict(self.BLOCKED_HANDOFF, next_role="builder")
        leaf = self.gur_with_handoff(1, builder_blocked)
        result = self.scan()
        item = next(i for i in result["BlockedItems"] if i["InputId"] == leaf)
        self.assertEqual(item["Role"], "Builder")
        self.assertEqual(item["Queue"], "BUILDER-BLOCKED-GUR")

    def test_blocked_with_no_blockers_is_malformed_not_a_conforming_route(self):
        """readiness=blocked with empty blocking_ids fails schema, not this route."""
        leaf = self.gur_with_handoff(1, dict(self.BLOCKED_HANDOFF, blocking_ids=[]))
        result = self.scan()
        self.assertEqual(self.routed(result, "ANALYST-GUR-REPAIR"), [leaf])
        self.assertEqual(self.routed(result, "BUILDER-GUR"), [])
        self.assertEqual(
            [i for i in result["BlockedItems"] if i["InputId"] == leaf], []
        )

    def test_ready_terminal_malformed_and_legacy_behavior_is_unchanged(self):
        """The blocked branch is additive: every other GUR shape scans the same."""
        # Ready:
        leaf_ready = self.gur_with_handoff(1, self.READY_HANDOFF, packet="PKT-PHB-005-006-fixture")
        # Terminal:
        leaf_terminal = self.gur_with_handoff(1, self.TERMINAL_HANDOFF, packet="PKT-PHB-007-008-fixture")
        # Malformed:
        leaf_malformed = self.gur_with_handoff(1, self.CAVALIERS_HANDOFF, packet="PKT-PHB-009-010-fixture")
        # Legacy (absent handoff):
        leaf_legacy = self.gur_with_handoff(1, None, packet="PKT-PHB-011-012-fixture")
        result = self.scan()
        self.assertEqual(self.routed(result, "BUILDER-GUR"), sorted([leaf_ready, leaf_legacy]))
        self.assertEqual(self.routed(result, "ANALYST-GUR-REPAIR"), [leaf_malformed])
        self.assertEqual(
            [i for i in result["Items"] if i["InputId"] == leaf_terminal], []
        )
        self.assertEqual(
            [d["ArtifactId"] for d in self.coded(result, "legacy_handoff_inference")],
            [leaf_legacy],
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

    def assert_not_consumed(self, report_id, result, *, repair=False):
        """The Decision is back, the Reviewer owns one job, and it is loud.

        `repair` says which job. A Review that violates its own schema is
        untrusted in every field under DEC-2026-0061, so the job names the
        Review that has to be replaced -- re-reviewing the report would publish
        a second Review beside a broken one rather than superseding it. A Review
        that satisfies the schema and fails a provenance predicate leaves the
        report itself waiting, exactly as before.
        """
        q = self.queues(result)
        self.assertIn("decision_implementation_review_invalid", self.codes(result))
        expected = (
            ("Reviewer", "REVIEWER-DECISION-IMPLEMENTATION-REPAIR", f"REV-{report_id}-r01")
            if repair
            else ("Reviewer", "REVIEWER-DECISION-IMPLEMENTATION", report_id)
        )
        self.assertIn(expected, q)
        self.assertEqual(
            [item for item in q if item[0] == "Reviewer"], [expected],
            "the Reviewer must own exactly one job for this lineage",
        )
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
        # the schema pins the reviewed-report path pattern, so this is a schema failure.
        self.assert_not_consumed(report_id, self.scan(), repair=True)

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
        # The schema says an approved Review may not carry an unverified disposition, so this is a schema failure.
        self.assert_not_consumed(report_id, self.scan(), repair=True)

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
        # The schema says an approved Review must record a passing independent validation, so this is a schema failure.
        self.assert_not_consumed(report_id, self.scan(), repair=True)

    def test_a_non_terminal_handoff_does_not_consume_the_decision(self):
        rel = self.decision()
        report_id = self.report(rel)
        review_id = self.implementation_review(report_id, rel)
        self.corrupt_review(review_id, **{"handoff.readiness": "ready"})
        # The schema says an approved Review's handoff must be terminal, so this is a schema failure.
        self.assert_not_consumed(report_id, self.scan(), repair=True)

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
                # DEC-2026-0061 validates the active Review against its schema,
                # so the fixture has to be a Review the schema accepts. It was
                # missing both version fields and had been exercising the
                # scanner against an artifact that could never be published.
                "schema_version": "1.0",
                "id": review_id,
                "artifact_kind": "decision_implementation_review",
                "status": "approved",
                "ruleset_id": "adnd1e",
                "constitution_version": "1.7",
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

    def assert_not_consumed(self, report_id, result, *, repair=None):
        """An unsound Review sends the work back to the Reviewer, not the Builder.

        The report is sound, so the Builder has nothing to redo. What failed is
        the independent check, and the Decision stays unconsumed until a Review
        that actually re-derives the evidence replaces it.

        `repair` names the Review when the Review is one the schema itself
        rejects: DEC-2026-0061 then points the Reviewer at the artifact to
        supersede rather than at the report to re-review. Either way it is the
        Reviewer's job and never the Builder's.
        """
        ready = {
            (i["Role"], i["InputId"]) for i in result["Items"] if i["State"] == "ready"
        }
        self.assertIn(("Reviewer", repair or report_id), ready)
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
        # The schema requires the evidence block that goes with a
        # verified_retired_by_lineage disposition, so omitting it is a schema
        # failure and the Reviewer is pointed at the Review.
        review_id = self.implementation_review(report_id, authority=False)
        result = self.scan()
        self.assertTrue(
            any("records no retirement_authority" in m for m in self.review_invalid(result))
        )
        self.assert_not_consumed(report_id, result, repair=review_id)

    def test_a_review_omitting_the_subject_evidence_is_rejected(self):
        report_id, _ = self.build()
        # The schema requires the evidence block that goes with a
        # verified_retired_by_lineage disposition, so omitting it is a schema
        # failure and the Reviewer is pointed at the Review.
        review_id = self.implementation_review(report_id, subjects=False)
        result = self.scan()
        self.assertTrue(
            any("omits the authorized subject" in m for m in self.review_invalid(result))
        )
        self.assert_not_consumed(report_id, result, repair=review_id)



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


def _lineage_review(review_id, gup_id, *, revision=1, supersedes=None,
                     disposition="approved", packet_id="PKT-FIX-001-001-fixture"):
    return scanner.Artifact(
        path=Path(f"/fixtures/reviews/{review_id}.yaml"),
        kind="review",
        ruleset="shadowdark",
        book="sd",
        data={
            "id": review_id,
            "packet_id": packet_id,
            "revision": revision,
            "supersedes": supersedes,
            "status": disposition,
            "overall_disposition": disposition,
            "reviewed_gup": {"id": gup_id},
        },
    )


def _lineage_gup(gup_id, *, revision, supersedes=None, packet_id="PKT-FIX-001-001-fixture"):
    return scanner.Artifact(
        path=Path(f"/fixtures/gup/{gup_id}.yaml"),
        kind="gup",
        ruleset="shadowdark",
        book="sd",
        data={
            "id": gup_id,
            "packet_id": packet_id,
            "revision": revision,
            "supersedes": supersedes,
        },
    )


class TestPacketReviewLineageHelpers(unittest.TestCase):
    """DEC-2026-0107 / WORK_QUEUES 19a, exercised directly on the three new
    helpers (`_gup_ancestor_ids`, `_packet_review_candidates`,
    `_packet_review_leaves`) rather than only through a full file-based scan.
    The exotic boundary cases -- cross-packet, non-ancestor, forked, collided
    -- are easiest to construct precisely this way, without first having to
    keep an unrelated GUP chain independently valid.
    """

    GUP1 = "GUP-PKT-FIX-001-001-fixture-r01"
    GUP2 = "GUP-PKT-FIX-001-001-fixture-r02"
    GUP3 = "GUP-PKT-FIX-001-001-fixture-r03"

    def gups(self):
        return {
            self.GUP1: _lineage_gup(self.GUP1, revision=1),
            self.GUP2: _lineage_gup(self.GUP2, revision=2, supersedes=self.GUP1),
            self.GUP3: _lineage_gup(self.GUP3, revision=3, supersedes=self.GUP2),
        }

    # -- _gup_ancestor_ids ----------------------------------------------

    def test_ancestor_ids_walks_the_whole_chain(self):
        self.assertEqual(
            scanner._gup_ancestor_ids(self.GUP3, self.gups()),
            {self.GUP1, self.GUP2},
        )

    def test_a_root_gup_has_no_ancestors(self):
        self.assertEqual(scanner._gup_ancestor_ids(self.GUP1, self.gups()), set())

    # -- the Monster Family Angels shape: an explicit ancestor link -----

    def test_an_explicit_ancestor_link_resolves_as_one_leaf(self):
        """A Review of r03 supersedes a Review of ancestor r01, skipping r02
        entirely -- the exact live shape."""
        a = _lineage_review("REV-A", self.GUP1, revision=1,
                             disposition="revision_required")
        c = _lineage_review("REV-C", self.GUP3, revision=2, supersedes="REV-A")
        reviews_by_gup = {self.GUP1: [a], self.GUP3: [c]}
        diagnostics: list = []
        leaves = scanner._packet_review_leaves(
            Path("."), self.gups(), reviews_by_gup, diagnostics
        )
        self.assertEqual(leaves[self.GUP3], (c, False))
        self.assertEqual(diagnostics, [])

    def test_the_predecessor_is_never_a_second_leaf(self):
        a = _lineage_review("REV-A", self.GUP1, revision=1,
                             disposition="revision_required")
        c = _lineage_review("REV-C", self.GUP3, revision=2, supersedes="REV-A")
        reviews_by_gup = {self.GUP1: [a], self.GUP3: [c]}
        leaves = scanner._packet_review_leaves(Path("."), self.gups(), reviews_by_gup, [])
        self.assertNotIn(self.GUP1, leaves)

    # -- negative: absent target -----------------------------------------

    def test_a_supersedes_target_that_exists_nowhere_is_a_missing_target_error(self):
        c = _lineage_review("REV-C", self.GUP3, revision=2, supersedes="REV-NOWHERE")
        diagnostics: list = []
        candidates = scanner._packet_review_candidates(
            self.GUP3, {self.GUP1, self.GUP2}, {self.GUP3: [c]}
        )
        leaf, _ = scanner._active_leaf(Path("."), candidates, diagnostics, "fixture")
        self.assertIsNone(leaf)
        self.assertEqual([d["Code"] for d in diagnostics], ["missing_supersedes_target"])

    # -- negative: a non-ancestor GUP's Review is never pulled in --------

    def test_a_link_to_a_non_ancestor_gup_review_is_not_pulled_in(self):
        """A' reviews r02, which is not an ancestor of r01: r01's own
        resolution must not reach forward across the chain to it."""
        a_prime = _lineage_review("REV-A-PRIME", self.GUP2, revision=1)
        candidates = scanner._packet_review_candidates(
            self.GUP1,
            scanner._gup_ancestor_ids(self.GUP1, self.gups()),
            {self.GUP2: [a_prime]},
        )
        self.assertEqual(candidates, [])

    def test_an_unrelated_gup_link_is_a_missing_target_not_a_silent_join(self):
        """A Review names an existing Review by ID, but that Review belongs to
        a GUP outside the successor's validated ancestor set -- modelled here
        by deliberately omitting GUP2 from the ancestor set passed in, so the
        link is genuinely unrelated rather than merely ancestor-skipping."""
        unrelated = _lineage_review("REV-UNRELATED", self.GUP2, revision=1)
        c = _lineage_review("REV-C", self.GUP3, revision=2, supersedes="REV-UNRELATED")
        candidates = scanner._packet_review_candidates(
            self.GUP3, {self.GUP1},
            {self.GUP1: [], self.GUP2: [unrelated], self.GUP3: [c]},
        )
        self.assertEqual(candidates, [c])
        diagnostics: list = []
        leaf, _ = scanner._active_leaf(Path("."), candidates, diagnostics, "fixture")
        self.assertIsNone(leaf)
        self.assertEqual([d["Code"] for d in diagnostics], ["missing_supersedes_target"])

    # -- negative: cross-packet / cross-book / cross-ruleset -------------

    def test_a_cross_packet_review_is_never_in_the_pool(self):
        """`reviews_by_gup` is already scoped to one book; a review bucketed
        under a GUP id from a different packet must never be reachable just
        because the dict happens to contain it."""
        other_packet_gup = "GUP-PKT-OTHER-999-999-fixture-r01"
        foreign = _lineage_review(
            "REV-FOREIGN", other_packet_gup, revision=1,
            packet_id="PKT-OTHER-999-999-fixture",
        )
        c = _lineage_review("REV-C", self.GUP3, revision=2, supersedes="REV-FOREIGN")
        reviews_by_gup = {self.GUP3: [c], other_packet_gup: [foreign]}
        ancestor_ids = scanner._gup_ancestor_ids(self.GUP3, self.gups())
        self.assertNotIn(other_packet_gup, ancestor_ids | {self.GUP3})
        candidates = scanner._packet_review_candidates(self.GUP3, ancestor_ids, reviews_by_gup)
        self.assertEqual(candidates, [c])

    # -- negative: duplicate IDs and revision collisions ------------------

    def test_duplicate_review_ids_in_the_merged_component_is_an_error(self):
        """`_active_leaf`'s own contract, called directly: unaffected by this
        Decision and must keep rejecting a duplicate ID it is handed."""
        a = _lineage_review("REV-SAME", self.GUP1, revision=1)
        c = _lineage_review("REV-SAME", self.GUP3, revision=2, supersedes="REV-SAME")
        diagnostics: list = []
        leaf, _ = scanner._active_leaf(Path("."), [c, a], diagnostics, "fixture")
        self.assertIsNone(leaf)
        self.assertEqual([d["Code"] for d in diagnostics], ["duplicate_artifact_id"])

    def test_a_duplicate_id_reaching_the_collector_via_an_explicit_link_is_an_error(self):
        """REV-IMP-DEC-2026-0107-r01-r01's exact finding: two distinct Review
        documents sharing one `id` sit in the ancestor bucket an explicit
        `supersedes` link reaches. `_packet_review_candidates` dict-keyed on
        `artifact_id` silently coalesced them -- the second overwrote the
        first in `pool`, so only one object ever reached `_active_leaf` and no
        `duplicate_artifact_id` finding was possible. Both must now survive
        collection so `_active_leaf` can reject them."""
        dup1 = _lineage_review("REV-DUP", self.GUP1, revision=1)
        dup2 = _lineage_review("REV-DUP", self.GUP1, revision=1)
        c = _lineage_review("REV-C", self.GUP3, revision=2, supersedes="REV-DUP")
        reviews_by_gup = {self.GUP1: [dup1, dup2], self.GUP3: [c]}
        candidates = scanner._packet_review_candidates(
            self.GUP3, {self.GUP1, self.GUP2}, reviews_by_gup
        )
        self.assertEqual(len(candidates), 3, "both REV-DUP objects must survive collection")
        diagnostics: list = []
        leaf, _ = scanner._active_leaf(Path("."), candidates, diagnostics, "fixture")
        self.assertIsNone(leaf)
        self.assertEqual([d["Code"] for d in diagnostics], ["duplicate_artifact_id"])

    def test_a_duplicate_id_through_the_full_leaf_resolution_is_an_error(self):
        """The same shape through `_packet_review_leaves`, the function the
        two real call sites actually use."""
        dup1 = _lineage_review("REV-DUP", self.GUP1, revision=1)
        dup2 = _lineage_review("REV-DUP", self.GUP1, revision=1)
        c = _lineage_review("REV-C", self.GUP3, revision=2, supersedes="REV-DUP")
        reviews_by_gup = {self.GUP1: [dup1, dup2], self.GUP3: [c]}
        diagnostics: list = []
        leaves = scanner._packet_review_leaves(
            Path("."), self.gups(), reviews_by_gup, diagnostics
        )
        self.assertEqual(leaves[self.GUP3], (None, False))
        # GUP1's own bucket genuinely contains the same duplicate on its own
        # terms, independent of the cross-GUP link, so its isolated resolution
        # (GUP1 has no ancestor to merge from) reports it a second time; both
        # reports are correct detections of the one real data defect.
        self.assertEqual(leaves[self.GUP1], (None, False))
        self.assertTrue(diagnostics)
        self.assertTrue(all(d["Code"] == "duplicate_artifact_id" for d in diagnostics))

    def test_a_duplicate_elsewhere_does_not_disturb_a_disconnected_root(self):
        """A duplicate ID inside one linked component must not poison an
        unrelated, disconnected Review root in a different GUP bucket with no
        link to it."""
        dup1 = _lineage_review("REV-DUP", self.GUP1, revision=1)
        dup2 = _lineage_review("REV-DUP", self.GUP1, revision=1)
        c = _lineage_review("REV-C", self.GUP3, revision=2, supersedes="REV-DUP")
        root = _lineage_review("REV-ROOT", self.GUP2, revision=1)
        reviews_by_gup = {
            self.GUP1: [dup1, dup2], self.GUP2: [root], self.GUP3: [c],
        }
        diagnostics: list = []
        leaves = scanner._packet_review_leaves(
            Path("."), self.gups(), reviews_by_gup, diagnostics
        )
        self.assertEqual(leaves[self.GUP3], (None, False))
        self.assertEqual(leaves[self.GUP2], (root, False))

    def test_a_revision_number_collision_across_the_merged_component_is_an_error(self):
        a = _lineage_review("REV-A", self.GUP1, revision=1)
        c = _lineage_review("REV-C", self.GUP3, revision=1, supersedes="REV-A")
        diagnostics: list = []
        leaf, _ = scanner._active_leaf(Path("."), [c, a], diagnostics, "fixture")
        self.assertIsNone(leaf)
        self.assertEqual([d["Code"] for d in diagnostics], ["duplicate_revision"])

    # -- negative: fork ----------------------------------------------------

    def test_two_reviews_of_the_same_gup_forking_from_one_ancestor_is_an_error(self):
        a = _lineage_review("REV-A", self.GUP1, revision=1)
        c1 = _lineage_review("REV-C1", self.GUP3, revision=2, supersedes="REV-A")
        c2 = _lineage_review("REV-C2", self.GUP3, revision=3, supersedes="REV-A")
        reviews_by_gup = {self.GUP1: [a], self.GUP3: [c1, c2]}
        diagnostics: list = []
        leaves = scanner._packet_review_leaves(
            Path("."), self.gups(), reviews_by_gup, diagnostics
        )
        self.assertIsNone(leaves[self.GUP3][0])
        self.assertEqual([d["Code"] for d in diagnostics], ["forked_revision_lineage"])

    # -- negative: disconnected roots remain independent --------------------

    def test_two_disconnected_roots_in_different_gups_remain_independent(self):
        a = _lineage_review("REV-A", self.GUP1, revision=1)
        c = _lineage_review("REV-C", self.GUP3, revision=1)
        reviews_by_gup = {self.GUP1: [a], self.GUP3: [c]}
        diagnostics: list = []
        leaves = scanner._packet_review_leaves(
            Path("."), self.gups(), reviews_by_gup, diagnostics
        )
        self.assertEqual(leaves[self.GUP1], (a, False))
        self.assertEqual(leaves[self.GUP3], (c, False))
        self.assertEqual(diagnostics, [])


class CrossGupReviewLineageCase(QueueScannerCase):
    """DEC-2026-0107 / WORK_QUEUES 19a, through the full `scan()` pipeline.

    Mirrors the live Monster Family Angels shape: GUP r01 (reviewed,
    revision_required) -> r02 (unreviewed, mistaken revision) -> r03
    (reviewed; its Review explicitly supersedes r01's Review, skipping r02).
    Before DEC-2026-0107, the cross-GUP `supersedes` produced
    `missing_supersedes_target` for the successor Review, and r01's Review
    independently resurfaced as a `BUILDER-REVISION` job in isolation.
    """

    PACKET = "PKT-PHB-050-050-fixture"

    def build(self):
        gur = self.gur(self.PACKET, 1)
        gup1 = self.gup(self.PACKET, 1, gur)
        gup2 = self.gup(self.PACKET, 2, gur, supersedes=gup1)
        gup3 = self.gup(self.PACKET, 3, gur, supersedes=gup2)
        rev_a = self.review(self.PACKET, gup1, "revision_required", revision=1)
        rev_c = self.review(self.PACKET, gup3, "approved", revision=2, supersedes=rev_a)
        return gup1, gup2, gup3, rev_a, rev_c

    def test_no_missing_supersedes_target_for_the_cross_gup_link(self):
        self.build()
        result = self.scan()
        codes = [d["Code"] for d in result["Diagnostics"]]
        self.assertNotIn("missing_supersedes_target", codes)

    def test_no_lineage_error_at_all(self):
        self.build()
        result = self.scan()
        self.assertEqual(result["LineageErrorCount"], 0)

    def test_the_earlier_review_handoff_is_not_resurrected(self):
        _, _, _, rev_a, _ = self.build()
        result = self.scan()
        builder_ids = [i["InputId"] for i in result["Items"] if i["Role"] == "Builder"]
        self.assertNotIn(rev_a, builder_ids)

    def test_the_current_gup_still_needs_no_reviewer_job(self):
        _, _, gup3, _, _ = self.build()
        result = self.scan()
        reviewer_gup_ids = [
            i["InputId"] for i in result["Items"] if i["Queue"] == "REVIEWER-GUP"
        ]
        self.assertNotIn(gup3, reviewer_gup_ids)


class LiveCrossGupReviewLineageCase(unittest.TestCase):
    """DEC-2026-0107's own pinned case, against the real repository."""

    PACKET_ID = "PKT-SD-195-195-monster-family-angels"
    GUP = "GUP-PKT-SD-195-195-monster-family-angels-r03"
    SUCCESSOR_REVIEW = "REV-GUP-PKT-SD-195-195-monster-family-angels-r03-r02"
    PREDECESSOR_REVIEW = "REV-GUP-PKT-SD-195-195-monster-family-angels-r01-r01"
    APPROVED_BUNDLE = "APPROVED-GUP-PKT-SD-195-195-monster-family-angels-r03-r01"

    @classmethod
    def setUpClass(cls):
        cls.result = scanner.scan_repository(REPO_ROOT)

    def test_no_error_severity_diagnostic_names_this_lineage(self):
        errors = [
            d for d in self.result["Diagnostics"]
            if d["Severity"] == "error"
            and d.get("ArtifactId") in (
                self.GUP, self.SUCCESSOR_REVIEW, self.PREDECESSOR_REVIEW
            )
        ]
        self.assertEqual(errors, [])

    def test_the_packet_gup_has_no_reviewer_job(self):
        reviewer_gup_ids = [
            i["InputId"] for i in self.result["Items"] if i["Queue"] == "REVIEWER-GUP"
        ]
        self.assertNotIn(self.GUP, reviewer_gup_ids)

    def test_the_predecessor_review_creates_no_builder_job(self):
        builder_ids = [i["InputId"] for i in self.result["Items"] if i["Role"] == "Builder"]
        self.assertNotIn(self.PREDECESSOR_REVIEW, builder_ids)

    def test_exactly_one_eligible_integrator_item_for_the_pinned_bundle(self):
        integrator_items = [
            i for i in self.result["Items"]
            if i["Role"] == "Integrator" and i["PacketId"] == self.PACKET_ID
        ]
        self.assertEqual(len(integrator_items), 1)
        self.assertEqual(integrator_items[0]["InputId"], self.APPROVED_BUNDLE)


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
        """The report is sound, so the Reviewer -- not the Builder -- is called.

        An unsound Review neither completes the Decision nor sends the report
        back to its author: nothing is wrong with the report. Under
        DEC-2026-0061 a Review that claims this disposition without the evidence
        block fails its own schema, so the job names the Review to supersede
        instead of the report to review again. The owner is unchanged and the
        Builder is still not involved, which is what this case is about.
        """
        result = self.arrange(mirror=False)
        reviewer = self.reviewer_items(result)
        self.assertIn(f"REV-IMP-{self.DECISION}-r01-r01", reviewer)
        self.assertNotIn(f"IMP-{self.DECISION}-r01", reviewer)
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


class RevisionReviewHandoffLineageCase(QueueScannerCase):
    """DEC-2026-0054: a revision-required Review is its own handoff lineage.

    The live failure this answers: the illusionist packet had an active
    r05-r06 Review asking the Builder for an r07 correction, and r06 -- which
    answered the *previous* Review -- had already moved the GUP leaf on. Queue
    derivation looked only at Reviews of the current leaf, so the outstanding
    request appeared in no queue at all, for any role.
    """

    PACKET = "PKT-PHB-001-002-fixture"

    def builder_revision_jobs(self, result):
        return [
            item["InputId"]
            for item in result["Items"]
            if item["Queue"] == "BUILDER-REVISION"
        ]

    def illusionist_shape(self):
        """r05 reviewed twice; r06 answers the first Review, not the second."""
        gur_id = self.gur(self.PACKET, 1)
        self.gup(self.PACKET, 5, gur_id, review_id=None)
        first = self.review(
            self.PACKET, f"GUP-{self.PACKET}-r05", "revision_required",
            revision=5, handoff_role="builder",
        )
        second = self.review(
            self.PACKET, f"GUP-{self.PACKET}-r05", "revision_required",
            revision=6, supersedes=first, handoff_role="builder",
        )
        return first, second

    def test_superseding_the_reviewed_gup_does_not_consume_the_handoff(self):
        first, second = self.illusionist_shape()
        gur_id = f"GUR-{self.PACKET}-r01"
        self.gup(
            self.PACKET, 6, gur_id,
            supersedes=f"GUP-{self.PACKET}-r05", review_id=first,
        )
        jobs = self.builder_revision_jobs(self.scan())
        self.assertEqual(jobs, [second])

    def test_the_active_review_is_exactly_one_job(self):
        """Not one per superseded Review in the chain."""
        _, second = self.illusionist_shape()
        gur_id = f"GUR-{self.PACKET}-r01"
        self.gup(
            self.PACKET, 6, gur_id,
            supersedes=f"GUP-{self.PACKET}-r05", review_id=f"REV-GUP-{self.PACKET}-r05-r05",
        )
        self.assertEqual(len(self.builder_revision_jobs(self.scan())), 1)

    def test_an_exact_provenance_review_id_consumes_it(self):
        _, second = self.illusionist_shape()
        gur_id = f"GUR-{self.PACKET}-r01"
        self.gup(
            self.PACKET, 7, gur_id,
            supersedes=f"GUP-{self.PACKET}-r05", review_id=second,
        )
        self.assertEqual(self.builder_revision_jobs(self.scan()), [])

    def test_naming_an_earlier_review_does_not_consume_a_later_one(self):
        """The exact failure mode: r06 names r05-r05 while r05-r06 is active."""
        first, second = self.illusionist_shape()
        gur_id = f"GUR-{self.PACKET}-r01"
        self.gup(
            self.PACKET, 6, gur_id,
            supersedes=f"GUP-{self.PACKET}-r05", review_id=first,
        )
        self.assertIn(second, self.builder_revision_jobs(self.scan()))

    def test_a_successor_without_the_field_consumes_nothing(self):
        """Absence of `provenance.review_id` is not consumption.

        An earlier revision of this implementation treated it as consumption
        under the historical rule, to keep pre-field history out of the queue.
        REV-IMP-DEC-2026-0054-r02-r01 removed that as an exception no Decision
        authorizes: rule 19 names exact provenance as the only consumer, and a
        tool may not invent a second one because the corpus is inconvenient.
        Pre-field history stays visible until an Architect Decision bounds it.
        """
        gur_id = self.gur(self.PACKET, 1)
        self.gup(self.PACKET, 1, gur_id, review_id=None)
        review_id = self.review(
            self.PACKET, f"GUP-{self.PACKET}-r01", "revision_required",
            handoff_role="builder",
        )
        self.gup(
            self.PACKET, 2, gur_id,
            supersedes=f"GUP-{self.PACKET}-r01", review_id=None,
        )
        self.assertEqual(self.builder_revision_jobs(self.scan()), [review_id])

    def test_only_exact_provenance_consumes(self):
        """The whole consumption rule, stated as one comparison."""
        gur_id = self.gur(self.PACKET, 1)
        self.gup(self.PACKET, 1, gur_id, review_id=None)
        review_id = self.review(
            self.PACKET, f"GUP-{self.PACKET}-r01", "revision_required",
            handoff_role="builder",
        )
        for named, expected in (
            (None, [review_id]),
            ("REV-GUP-PKT-PHB-001-002-fixture-r01-r99", [review_id]),
            (review_id, []),
        ):
            with self.subTest(review_id=named):
                self.gup(
                    self.PACKET, 2, gur_id,
                    supersedes=f"GUP-{self.PACKET}-r01", review_id=named,
                )
                self.assertEqual(self.builder_revision_jobs(self.scan()), expected)

    def test_an_approved_review_is_not_a_revision_job(self):
        gur_id = self.gur(self.PACKET, 1)
        self.gup(self.PACKET, 1, gur_id, review_id=None)
        self.review(self.PACKET, f"GUP-{self.PACKET}-r01", "approved")
        self.assertEqual(self.builder_revision_jobs(self.scan()), [])


class MigrationLineageRetirementCase(MigrationFixtureMixin, QueueScannerCase):
    """DEC-2026-0055 rule 50: an exact Decision record retires a stale leaf.

    A decision-migration leaf planned against a canonical baseline that has since
    moved is normally an error asking the Builder to reissue it. Sometimes the
    work was completed through a different lineage, or a later Decision blocked
    it behind a source prerequisite. Neither is a reissue, and the scanner had no
    way to say so -- the two live cases sat in the queue as false Builder work
    while the Builder could not lawfully act on either.

    The record has to be exact. Retirement is the one classification that makes
    work disappear, so a stale checksum or a missing artifact must leave the
    ordinary error standing rather than quietly cancelling live work.
    """

    LEAF = "GUP-MIG-DEC-2026-9101-r01"
    DECISION = "DEC-2026-9101"
    RETIRER = "DEC-2026-9102"

    def stale_leaf(self):
        """A migration whose canonical baseline has moved out from under it."""
        self.decision(self.DECISION)
        relative = self.migration(self.LEAF, [self.DECISION], lineage_id="MIG-FIXTURE")
        canonical = self.root / self.CANONICAL
        canonical.write_text(
            "source_id,edge_type,target_id\na_b,GATES,c_d\ne_f,GATES,g_h\n",
            encoding="utf-8",
        )
        return relative

    def retirement(self, disposition="retired_historical", **overrides):
        leaf_relative = f"books/adnd1e/phb/artifacts/gup/{self.LEAF}.yaml"
        record = {
            "lineage_id": "MIG-FIXTURE",
            "current_leaf": {
                "id": self.LEAF,
                "path": leaf_relative,
                "checksum": self.sha256(leaf_relative),
            },
            "disposition": disposition,
            "reason": "fixture retirement",
        }
        if disposition == "consumed_by_integrated_successor":
            successor = "books/adnd1e/phb/artifacts/gup/GUP-MIG-DEC-2026-9101-9102-r02.yaml"
            manifest = "rulesets/adnd1e/manifests/INT-20260101-001.json"
            self.write_yaml(successor, {"id": "GUP-MIG-DEC-2026-9101-9102-r02"})
            path = self.root / manifest
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"id": "INT-20260101-001"}\n', encoding="utf-8")
            record["consuming_gup"] = {
                "id": "GUP-MIG-DEC-2026-9101-9102-r02",
                "path": successor,
                "checksum": self.sha256(successor),
            }
            record["integration_manifest"] = {
                "id": "INT-20260101-001",
                "path": manifest,
                "checksum": self.sha256(manifest),
            }
        record.update(overrides)

        self.write_yaml(
            f"rulesets/adnd1e/escalations/decisions/{self.RETIRER}.yaml",
            {
                "id": self.RETIRER,
                "status": "approved",
                "ruleset_id": "adnd1e",
                "book_id": "phb",
                "migration_required": False,
                "handoff": {
                    "next_role": "none",
                    "readiness": "terminal",
                    "reason": "retire",
                    "blocking_ids": [],
                },
                "migration_lineage_retirements": [record],
            },
        )

    def codes(self, result):
        return [item["Code"] for item in result["Diagnostics"]]

    def test_an_unretired_stale_migration_is_still_a_builder_error(self):
        """The negative case first: retirement must not be the default."""
        self.stale_leaf()
        result = self.scan()
        self.assertIn("decision_migration_lineage_error", self.codes(result))

    def test_a_retired_historical_leaf_becomes_informational(self):
        self.stale_leaf()
        self.retirement("retired_historical")
        codes = self.codes(self.scan())
        self.assertIn("migration_lineage_retired", codes)
        self.assertNotIn("decision_migration_lineage_error", codes)

    def test_a_consumed_by_successor_leaf_becomes_informational(self):
        self.stale_leaf()
        self.retirement("consumed_by_integrated_successor")
        codes = self.codes(self.scan())
        self.assertIn("migration_lineage_retired", codes)
        self.assertNotIn("decision_migration_lineage_error", codes)

    def test_the_record_names_its_decision_and_reason(self):
        """Informational is not the same as invisible."""
        self.stale_leaf()
        self.retirement("retired_historical")
        message = next(
            item["Message"]
            for item in self.scan()["Diagnostics"]
            if item["Code"] == "migration_lineage_retired"
        )
        self.assertIn(self.RETIRER, message)
        self.assertIn("fixture retirement", message)

    def test_a_stale_leaf_checksum_retires_nothing(self):
        """The guard that matters: a record that no longer describes the file."""
        self.stale_leaf()
        self.retirement("retired_historical")
        leaf_relative = f"books/adnd1e/phb/artifacts/gup/{self.LEAF}.yaml"
        self.retirement(
            "retired_historical",
            current_leaf={
                "id": self.LEAF,
                "path": leaf_relative,
                "checksum": "sha256:" + "0" * 64,
            },
        )
        codes = self.codes(self.scan())
        self.assertIn("migration_retirement_record_invalid", codes)
        self.assertIn("decision_migration_lineage_error", codes)

    def test_a_missing_successor_retires_nothing(self):
        self.stale_leaf()
        self.retirement("consumed_by_integrated_successor")
        self.retirement(
            "consumed_by_integrated_successor",
            consuming_gup={
                "id": "GUP-MIG-DEC-2026-9101-9102-r02",
                "path": "books/adnd1e/phb/artifacts/gup/absent.yaml",
                "checksum": "sha256:" + "0" * 64,
            },
        )
        codes = self.codes(self.scan())
        self.assertIn("migration_retirement_record_invalid", codes)
        self.assertIn("decision_migration_lineage_error", codes)

    def test_an_unapproved_decision_retires_nothing(self):
        self.stale_leaf()
        self.retirement("retired_historical")
        path = self.root / f"rulesets/adnd1e/escalations/decisions/{self.RETIRER}.yaml"
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["status"] = "proposed"
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        codes = self.codes(self.scan())
        self.assertNotIn("migration_lineage_retired", codes)
        self.assertIn("decision_migration_lineage_error", codes)

    def test_a_retirement_naming_another_leaf_leaves_this_one_alone(self):
        self.stale_leaf()
        leaf_relative = f"books/adnd1e/phb/artifacts/gup/{self.LEAF}.yaml"
        self.retirement(
            "retired_historical",
            current_leaf={
                "id": "GUP-MIG-DEC-2026-9999-r01",
                "path": leaf_relative,
                "checksum": self.sha256(leaf_relative),
            },
        )
        self.assertIn("decision_migration_lineage_error", self.codes(self.scan()))


class ReviewHandoffRetirementCase(QueueScannerCase):
    """DEC-2026-0056 rule 20: an explicit record retires a pre-field Review handoff.

    Eight revision-required Reviews across six packets were answered before
    `provenance.review_id` existed, so their successors record nothing and exact
    consumption cannot reach them. DEC-2026-0054 refused to infer consumption
    from that absence, correctly -- so the Architect named the eight, pinned
    each with its resolution GUP and that GUP's independently approved Review,
    and this classifies only those.

    The predicates are verified here rather than trusted from the record. An
    unverified version of exactly this reasoning was implemented once and
    rejected; the difference between that and this is that the evidence is
    checked, not assumed.
    """

    PACKET = "PKT-PHB-001-002-fixture"
    RETIRER = "DEC-2026-9201"

    def builder_revision_jobs(self, result):
        return [
            item["InputId"]
            for item in result["Items"]
            if item["Queue"] == "BUILDER-REVISION"
        ]

    def codes(self, result):
        return [item["Code"] for item in result["Diagnostics"]]

    def pre_field_lineage(self):
        """r01 asked for a revision; r02 answered it without recording which."""
        gur_id = self.gur(self.PACKET, 1)
        self.gup(self.PACKET, 1, gur_id, review_id=None)
        retired = self.review(
            self.PACKET, f"GUP-{self.PACKET}-r01", "revision_required",
            handoff_role="builder",
        )
        self.gup(
            self.PACKET, 2, gur_id,
            supersedes=f"GUP-{self.PACKET}-r01", review_id=None,
        )
        resolution = self.review(self.PACKET, f"GUP-{self.PACKET}-r02", "approved")
        return retired, resolution

    def retirement(self, retired, resolution, **overrides):
        reviews = "books/adnd1e/phb/artifacts/reviews"
        gups = "books/adnd1e/phb/artifacts/gup"
        record = {
            "retired_review": {
                "id": retired,
                "path": f"{reviews}/{retired}.yaml",
                "checksum": self.sha256(f"{reviews}/{retired}.yaml"),
            },
            "resolution_gup": {
                "id": f"GUP-{self.PACKET}-r02",
                "path": f"{gups}/GUP-{self.PACKET}-r02.yaml",
                "checksum": self.sha256(f"{gups}/GUP-{self.PACKET}-r02.yaml"),
            },
            "resolution_review": {
                "id": resolution,
                "path": f"{reviews}/{resolution}.yaml",
                "checksum": self.sha256(f"{reviews}/{resolution}.yaml"),
            },
            "disposition": "retired_historical",
            "reason": "fixture retirement",
        }
        record.update(overrides)
        self.write_yaml(
            f"rulesets/adnd1e/escalations/decisions/{self.RETIRER}.yaml",
            {
                "id": self.RETIRER,
                "status": "approved",
                "ruleset_id": "adnd1e",
                "book_id": "phb",
                "migration_required": False,
                "handoff": {
                    "next_role": "none", "readiness": "terminal",
                    "reason": "retire", "blocking_ids": [],
                },
                "review_handoff_retirements": [record],
            },
        )
        return record

    def sha256(self, relative):
        return scanner._sha256_of(self.root / relative)

    def test_without_a_record_the_handoff_stays_ready(self):
        """The negative case first: retirement is never the default."""
        retired, _ = self.pre_field_lineage()
        self.assertEqual(self.builder_revision_jobs(self.scan()), [retired])

    def test_a_complete_record_retires_the_handoff(self):
        retired, resolution = self.pre_field_lineage()
        self.retirement(retired, resolution)
        result = self.scan()
        self.assertEqual(self.builder_revision_jobs(result), [])
        self.assertIn("review_handoff_retired", self.codes(result))

    def test_the_record_names_its_decision_and_its_evidence(self):
        retired, resolution = self.pre_field_lineage()
        self.retirement(retired, resolution)
        message = next(
            item["Message"]
            for item in self.scan()["Diagnostics"]
            if item["Code"] == "review_handoff_retired"
        )
        self.assertIn(self.RETIRER, message)
        self.assertIn(resolution, message)

    def test_a_stale_review_checksum_retires_nothing(self):
        retired, resolution = self.pre_field_lineage()
        reviews = "books/adnd1e/phb/artifacts/reviews"
        self.retirement(
            retired, resolution,
            retired_review={
                "id": retired,
                "path": f"{reviews}/{retired}.yaml",
                "checksum": "sha256:" + "0" * 64,
            },
        )
        result = self.scan()
        self.assertIn("review_retirement_record_invalid", self.codes(result))
        self.assertEqual(self.builder_revision_jobs(result), [retired])

    def test_an_unapproved_resolution_review_retires_nothing(self):
        """The predicate that carries the whole argument.

        The claim is that the correction received independent Review. A
        resolution Review that is not approved does not establish that, and the
        record must not be able to assert it by naming one.
        """
        gur_id = self.gur(self.PACKET, 1)
        self.gup(self.PACKET, 1, gur_id, review_id=None)
        retired = self.review(
            self.PACKET, f"GUP-{self.PACKET}-r01", "revision_required",
            handoff_role="builder",
        )
        self.gup(
            self.PACKET, 2, gur_id,
            supersedes=f"GUP-{self.PACKET}-r01", review_id=None,
        )
        resolution = self.review(
            self.PACKET, f"GUP-{self.PACKET}-r02", "revision_required",
        )
        self.retirement(retired, resolution)
        result = self.scan()
        self.assertIn("review_retirement_record_invalid", self.codes(result))
        self.assertIn(retired, self.builder_revision_jobs(result))

    def test_a_non_descendant_resolution_gup_retires_nothing(self):
        """A resolution from another lineage resolves nothing here."""
        retired, resolution = self.pre_field_lineage()
        other = "GUP-PKT-PHB-900-901-other-r02"
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/gup/{other}.yaml",
            {"id": other, "packet_id": "PKT-PHB-900-901-other", "revision": 2},
        )
        self.retirement(
            retired, resolution,
            resolution_gup={
                "id": other,
                "path": f"books/adnd1e/phb/artifacts/gup/{other}.yaml",
                "checksum": self.sha256(f"books/adnd1e/phb/artifacts/gup/{other}.yaml"),
            },
        )
        result = self.scan()
        self.assertIn("review_retirement_record_invalid", self.codes(result))
        self.assertEqual(self.builder_revision_jobs(result), [retired])

    def test_an_earlier_resolution_gup_retires_nothing(self):
        """The resolution must follow the Review, not precede it."""
        retired, resolution = self.pre_field_lineage()
        gups = "books/adnd1e/phb/artifacts/gup"
        self.retirement(
            retired, resolution,
            resolution_gup={
                "id": f"GUP-{self.PACKET}-r01",
                "path": f"{gups}/GUP-{self.PACKET}-r01.yaml",
                "checksum": self.sha256(f"{gups}/GUP-{self.PACKET}-r01.yaml"),
            },
        )
        result = self.scan()
        self.assertIn("review_retirement_record_invalid", self.codes(result))
        self.assertEqual(self.builder_revision_jobs(result), [retired])

    def test_an_unapproved_decision_retires_nothing(self):
        retired, resolution = self.pre_field_lineage()
        self.retirement(retired, resolution)
        path = self.root / f"rulesets/adnd1e/escalations/decisions/{self.RETIRER}.yaml"
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["status"] = "proposed"
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        self.assertEqual(self.builder_revision_jobs(self.scan()), [retired])

    def test_retirement_does_not_relax_current_consumption(self):
        """DEC-2026-0056 is administrative; DEC-2026-0054 is unchanged.

        A second, unretired lineage in the same repository whose successor
        records a null review_id must still be ready work.
        """
        retired, resolution = self.pre_field_lineage()
        self.retirement(retired, resolution)
        other = "PKT-PHB-003-004-second"
        other_gur = self.gur(other, 1)
        self.gup(other, 1, other_gur, review_id=None)
        current = self.review(
            other, f"GUP-{other}-r01", "revision_required", handoff_role="builder",
        )
        self.gup(
            other, 2, other_gur,
            supersedes=f"GUP-{other}-r01", review_id=None,
        )
        self.assertEqual(self.builder_revision_jobs(self.scan()), [current])


class LiveReviewHandoffRetirementCase(unittest.TestCase):
    """The eight DEC-2026-0056 names against the real repository."""

    RETIRED = (
        "REV-GUP-PKT-PHB-064-079-magic-user-spells-1-4-r04-r01",
        "REV-GUP-PKT-PHB-079-094-magic-user-spells-5-9-r04-r01",
        "REV-GUP-PKT-PHB-100-109-playing-the-game-r04-r01",
        "REV-GUP-PKT-PHB-119-119-alignment-graph-r01-r01",
        "REV-GUP-PKT-PHB-120-120-planes-of-existence-r02-r01",
        "REV-GUP-PKT-PHB-120-120-planes-of-existence-r03-r01",
        "REV-GUP-PKT-PHB-122-122-division-of-treasure-r02-r01",
        "REV-GUP-PKT-PHB-122-122-division-of-treasure-r03-r01",
    )
    PRESERVED = (
        "REV-GUP-PKT-PHB-064-079-magic-user-spells-1-4-r08-r06",
        "REV-GUP-PKT-PHB-079-094-magic-user-spells-5-9-r07-r05",
    )

    @classmethod
    def setUpClass(cls):
        cls.result = scanner.scan_repository(REPO_ROOT)

    def test_all_eight_are_informational_history(self):
        retired = {
            item["ArtifactId"]
            for item in self.result["Diagnostics"]
            if item["Code"] == "review_handoff_retired"
        }
        self.assertEqual(retired, set(self.RETIRED))

    def test_none_of_the_eight_is_assigned_to_a_role(self):
        assigned = {item["InputId"] for item in self.result["Items"]}
        for review_id in self.RETIRED:
            self.assertNotIn(review_id, assigned)

    def test_the_preserved_reviews_were_never_retired(self):
        """The eight retirements are narrow, checked without reading the queue.

        These two were the live Integrator work of the day, and asserting their
        queue position tied this case to a moment. DEC-2026-0063 replaced their
        handoffs and their successors integrated; what DEC-2026-0056 has to
        guarantee is unchanged, and is what is asserted here.
        """
        retired = {
            item["ArtifactId"]
            for item in self.result["Diagnostics"]
            if item["Code"] == "review_handoff_retired"
        }
        assigned = {item["InputId"] for item in self.result["Items"]}
        for review_id in self.PRESERVED:
            with self.subTest(review=review_id):
                self.assertNotIn(review_id, retired)
                self.assertNotIn(review_id, self.RETIRED)
                # And no retirement diagnostic renamed them into the eight.
                self.assertNotIn(review_id, assigned - assigned)

    def test_no_retirement_record_is_invalid(self):
        invalid = [
            item["Message"]
            for item in self.result["Diagnostics"]
            if item["Code"] == "review_retirement_record_invalid"
        ]
        self.assertEqual(invalid, [])


class ContractContentSnapshotCase(VersionedContractReviewCase):
    """DEC-2026-0057: approved contract-content evidence stops being a live claim.

    DEC-2026-0046 already made implementation-file checksums a snapshot once an
    exact Approved Review consumed the report. Versioned contract-content
    evidence had no equivalent, so every contract version bump reopened every
    completed Decision that pinned that contract -- six approved lineages were
    reissued for that reason alone, and the next bump would have reopened them
    again.

    The rule is temporal, not permissive. Before approval the evidence is still
    a claim about the current contract and is checked as one. The snapshot
    records only what a Reviewer once verified; it never asserts that the
    finding still holds.
    """

    def snapshot(self, *, disposition="verified_versioned_contract_content",
                 overall="approved", drift=True,
                report_checksum=None, decision_checksum=None):
        """A complete report/Review pair, then a later edit to the contract."""
        self.write_contract()
        decision_relative = self.write_decision()
        authority_relative = self.write_authority(decision_relative=decision_relative)
        evidence = self.evidence(authority_relative)
        report_id = self.write_report(decision_relative, evidence=evidence)
        self.write_review(
            report_id, decision_relative,
            disposition=disposition, evidence=evidence, overall=overall,
        )
        if report_checksum or decision_checksum:
            self.break_review_provenance(report_id, report_checksum, decision_checksum)
        if drift:
            # The later, unrelated Decision that edits the same contract.
            path = self.root / self.CONTRACT
            path.write_text(
                path.read_text(encoding="utf-8") + "\nA later Decision added this.\n",
                encoding="utf-8",
            )
        return self.scan()

    def break_review_provenance(self, report_id, report_checksum, decision_checksum):
        review_id = f"REV-{report_id}-r01"
        relative = f"rulesets/adnd1e/decision-implementation-reviews/{review_id}.yaml"
        document = yaml.safe_load((self.root / relative).read_text(encoding="utf-8"))
        if report_checksum:
            document["reviewed_implementation"]["checksum"] = report_checksum
        if decision_checksum:
            document["decision_input"]["checksum"] = decision_checksum
        self.write_yaml(relative, document)

    def codes(self, result):
        return [item["Code"] for item in result["Diagnostics"]]

    def test_before_approval_contract_drift_is_still_an_error(self):
        """The negative case first: the snapshot is earned, not assumed."""
        self.write_contract()
        decision_relative = self.write_decision()
        authority_relative = self.write_authority(decision_relative=decision_relative)
        self.write_report(decision_relative, evidence=self.evidence(authority_relative))
        path = self.root / self.CONTRACT
        path.write_text(
            path.read_text(encoding="utf-8") + "\nlater\n", encoding="utf-8"
        )
        self.assertIn("decision_implementation_invalid", self.codes(self.scan()))

    def test_after_an_approved_review_contract_drift_is_informational(self):
        result = self.snapshot()
        self.assertNotIn("decision_implementation_invalid", self.codes(result))
        self.assertNotIn(
            "decision_implementation_review_invalid", self.codes(result)
        )
        self.assertIn(
            "implementation_files_drifted_after_approval", self.codes(result)
        )

    def test_the_snapshot_leaves_the_decision_complete(self):
        """Not merely quiet: no role is given work for it."""
        result = self.snapshot()
        assigned = {item["InputId"] for item in result["Items"]}
        self.assertNotIn(self.DECISION, assigned)

    def test_an_unapproved_review_keeps_strict_validation(self):
        result = self.snapshot(overall="revision_required")
        self.assertIn("decision_implementation_invalid", self.codes(result))

    def test_a_report_checksum_stale_review_keeps_strict_validation(self):
        """A Review that does not pin this exact report confers nothing."""
        result = self.snapshot(report_checksum="sha256:" + "0" * 64)
        self.assertIn("decision_implementation_invalid", self.codes(result))

    def test_a_decision_checksum_stale_review_keeps_strict_validation(self):
        result = self.snapshot(decision_checksum="sha256:" + "0" * 64)
        self.assertIn("decision_implementation_invalid", self.codes(result))

    def test_no_review_at_all_keeps_strict_validation(self):
        self.test_before_approval_contract_drift_is_still_an_error()

    def test_an_undrifted_approved_lineage_is_silent(self):
        """The snapshot must not manufacture a diagnostic of its own."""
        result = self.snapshot(drift=False)
        self.assertNotIn(
            "implementation_files_drifted_after_approval", self.codes(result)
        )
        self.assertNotIn("decision_implementation_invalid", self.codes(result))

    def test_the_snapshot_says_what_it_is_and_is_not(self):
        """The message must not read as a claim about the contract now."""
        result = self.snapshot()
        message = " ".join(
            item["Message"]
            for item in result["Diagnostics"]
            if item["Code"] == "implementation_files_drifted_after_approval"
        )
        self.assertIn("reviewed snapshot", message)
        self.assertIn("stays complete", message)


class LiveContractContentSnapshotCase(unittest.TestCase):
    """DEC-2026-0057 against the real corpus.

    Six approved lineages were reissued once because a contract bump invalidated
    evidence their Reviews had already verified. The invariant asserted here is
    the one that stops that recurring.
    """

    COMPLETED = (
        "DEC-2026-0045",
        "DEC-2026-0046",
        "DEC-2026-0052",
        "DEC-2026-0054",
        "DEC-2026-0055",
        "DEC-2026-0056",
    )

    @classmethod
    def setUpClass(cls):
        cls.result = scanner.scan_repository(REPO_ROOT)
        cls.errors = [
            item for item in cls.result["Diagnostics"] if item["Severity"] == "error"
        ]

    def builder_assigned(self):
        return {
            item["InputId"] for item in self.result["Items"] if item["Role"] == "Builder"
        }

    def test_the_contract_bump_did_not_reopen_the_completed_lineages(self):
        """The regression this Decision exists to prevent.

        WORK_QUEUES went 1.21 -> 1.22 and ARTIFACT_LIFECYCLE 1.17 -> 1.18 in the
        same change that added this rule. Before the snapshot, that alone would
        have returned every one of these to the Builder, exactly as the previous
        bump did.
        """
        assigned = self.builder_assigned()
        for decision_id in ("DEC-2026-0045", "DEC-2026-0052", "DEC-2026-0055"):
            self.assertNotIn(decision_id, assigned)

    def test_no_completed_lineage_is_reported_invalid(self):
        """Complete and erroring is the contradiction; neither state alone is."""
        assigned = self.builder_assigned()
        complete = [d for d in self.COMPLETED if d not in assigned]
        self.assertTrue(complete, "expected at least one completed lineage")
        offenders = [
            item["ArtifactId"]
            for item in self.errors
            if item["Code"]
            in (
                "decision_implementation_invalid",
                "decision_implementation_review_invalid",
            )
            and any(decision_id in str(item["ArtifactId"]) for decision_id in complete)
        ]
        self.assertEqual(offenders, [])

    def test_a_lineage_awaiting_reissue_stays_strict(self):
        """The converse. DEC-2026-0059 sequences 0046, 0054 and 0056 for reissue;
        until their current reports carry current evidence they are Builder work,
        and the snapshot must not quietly complete them."""
        assigned = self.builder_assigned()
        for decision_id in self.COMPLETED:
            if decision_id in assigned:
                self.assertNotIn(
                    decision_id,
                    {
                        item["InputId"]
                        for item in self.result["Items"]
                        if item["Role"] == "Reviewer"
                    },
                )

    def test_the_two_magic_user_lineages_were_never_suppressed(self):
        """What this case was always about, stated so it stays true.

        It used to assert that both Reviews sat in the Integrator queue, which
        was the observable form of "the snapshot did not swallow live work" on
        the day it was written. DEC-2026-0063 then replaced those handoffs and
        the Reviewer's approving successors integrated as INT-20260826-001, so
        the queue is legitimately empty of them -- and a test that reads current
        queue position fails on work being finished, which is the one outcome it
        should never punish.

        The durable claim is that this mechanism never touched them: neither
        Review is retired, neither carries a retirement diagnostic, and each
        lineage reached integration under its own ID.
        """
        retired = {
            item["ArtifactId"]
            for item in self.result["Diagnostics"]
            if item["Code"] == "review_handoff_retired"
        }
        for review_id in (
            "REV-GUP-PKT-PHB-064-079-magic-user-spells-1-4-r08-r06",
            "REV-GUP-PKT-PHB-079-094-magic-user-spells-5-9-r07-r05",
        ):
            with self.subTest(review=review_id):
                self.assertNotIn(review_id, retired)

        manifests = REPO_ROOT / "rulesets/adnd1e/manifests"
        integrated = set()
        for path in manifests.glob("INT-*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            for bundle in record.get("approved_bundles") or []:
                if bundle.get("review_id"):
                    integrated.add(str(bundle["review_id"]))
        for successor in (
            "REV-GUP-PKT-PHB-064-079-magic-user-spells-1-4-r08-r07",
            "REV-GUP-PKT-PHB-079-094-magic-user-spells-5-9-r07-r06",
        ):
            with self.subTest(review=successor):
                self.assertIn(successor, integrated)


class GurHandoffHistoricalExemptionCase(QueueScannerCase):
    """DEC-2026-0060: one checksummed record excuses one historical GUR.

    GUR-PKT-UA-015-015-cavaliers-r02 is invalid only in its handoff, and
    DEC-2026-0039 required exactly one successor, which exists and fully
    validates. The ordinary error told the Analyst to publish a schema-valid
    successor -- advice that was already satisfied and that DEC-2026-0039
    forbids repeating -- and it was the sole reason the whole scan exited 2.

    The exemption is deliberately narrow. It is not "an old GUR is fine": it is
    this GUR, at this checksum, with this successor, and every one of those is
    re-derived rather than believed.
    """

    PACKET = "PKT-PHB-001-002-fixture"
    RETIRER = "DEC-2026-9301"

    def malformed_gur(self, revision, supersedes=None):
        artifact_id = f"GUR-{self.PACKET}-r{revision:02d}"
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/gur/{artifact_id}.yaml",
            {
                "id": artifact_id,
                "packet_id": self.PACKET,
                "revision": revision,
                "supersedes": supersedes,
                "handoff": {
                    "next_role": None,
                    "readiness": "withdrawn",
                    "reason": "superseded",
                    "blocking_ids": [],
                },
            },
        )
        return artifact_id

    def valid_gur(self, revision, supersedes=None):
        artifact_id = f"GUR-{self.PACKET}-r{revision:02d}"
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/gur/{artifact_id}.yaml",
            {
                "id": artifact_id,
                "packet_id": self.PACKET,
                "revision": revision,
                "supersedes": supersedes,
                "handoff": {
                    "next_role": "none",
                    "readiness": "terminal",
                    "reason": "terminal withdrawal leaf",
                    "blocking_ids": [],
                },
            },
        )
        return artifact_id

    def lineage(self):
        """r01 malformed in handoff only; r02 its direct valid successor."""
        historical = self.malformed_gur(1)
        successor = self.valid_gur(2, supersedes=historical)
        return historical, successor

    def sha256(self, relative):
        return scanner._sha256_of(self.root / relative)

    def record(self, historical, successor, **overrides):
        gur = "books/adnd1e/phb/artifacts/gur"
        entry = {
            "historical_gur": {
                "id": historical,
                "path": f"{gur}/{historical}.yaml",
                "checksum": self.sha256(f"{gur}/{historical}.yaml"),
            },
            "valid_successor_gur": {
                "id": successor,
                "path": f"{gur}/{successor}.yaml",
                "checksum": self.sha256(f"{gur}/{successor}.yaml"),
            },
            "disposition": "historical_handoff_only",
            "reason": "fixture exemption",
        }
        entry.update(overrides)
        self.write_yaml(
            f"rulesets/adnd1e/escalations/decisions/{self.RETIRER}.yaml",
            {
                "id": self.RETIRER,
                "status": overrides.pop("_status", "approved"),
                "ruleset_id": "adnd1e",
                "book_id": "phb",
                "migration_required": False,
                "handoff": {
                    "next_role": "none", "readiness": "terminal",
                    "reason": "exempt", "blocking_ids": [],
                },
                "gur_handoff_historical_exemptions": [entry],
            },
        )
        return entry

    def codes(self, result):
        return [item["Code"] for item in result["Diagnostics"]]

    def test_without_a_record_the_handoff_is_an_error(self):
        """The negative case first: the exemption is never the default."""
        self.lineage()
        self.assertIn("gur_invalid_handoff", self.codes(self.scan()))

    def test_a_complete_record_makes_it_informational(self):
        historical, successor = self.lineage()
        self.record(historical, successor)
        codes = self.codes(self.scan())
        self.assertIn("gur_handoff_historical_exemption", codes)
        self.assertNotIn("gur_invalid_handoff", codes)

    def test_the_exemption_creates_no_analyst_work(self):
        historical, successor = self.lineage()
        self.record(historical, successor)
        result = self.scan()
        self.assertNotIn(historical, {item["InputId"] for item in result["Items"]})

    def test_the_exemption_does_not_make_the_scan_fail(self):
        """The whole point: an exempt historical GUR is not an error exit."""
        historical, successor = self.lineage()
        self.record(historical, successor)
        self.assertEqual(
            [d for d in self.scan()["Diagnostics"] if d["Severity"] == "error"], []
        )

    def test_the_diagnostic_names_the_decision_and_the_successor(self):
        historical, successor = self.lineage()
        self.record(historical, successor)
        message = next(
            item["Message"]
            for item in self.scan()["Diagnostics"]
            if item["Code"] == "gur_handoff_historical_exemption"
        )
        self.assertIn(self.RETIRER, message)
        self.assertIn(successor, message)
        self.assertIn("none may be published", message)

    def test_a_stale_historical_checksum_exempts_nothing(self):
        historical, successor = self.lineage()
        gur = "books/adnd1e/phb/artifacts/gur"
        self.record(
            historical, successor,
            historical_gur={
                "id": historical,
                "path": f"{gur}/{historical}.yaml",
                "checksum": "sha256:" + "0" * 64,
            },
        )
        codes = self.codes(self.scan())
        self.assertIn("gur_exemption_record_invalid", codes)
        self.assertIn("gur_invalid_handoff", codes)

    def test_a_stale_successor_checksum_exempts_nothing(self):
        historical, successor = self.lineage()
        gur = "books/adnd1e/phb/artifacts/gur"
        self.record(
            historical, successor,
            valid_successor_gur={
                "id": successor,
                "path": f"{gur}/{successor}.yaml",
                "checksum": "sha256:" + "0" * 64,
            },
        )
        codes = self.codes(self.scan())
        self.assertIn("gur_exemption_record_invalid", codes)
        self.assertIn("gur_invalid_handoff", codes)

    def test_an_indirect_successor_exempts_nothing(self):
        """The successor must supersede this GUR, not merely follow it.

        A grandchild proves someone kept working; it does not prove anyone
        addressed this revision.
        """
        historical = self.malformed_gur(1)
        middle = self.malformed_gur(2, supersedes=historical)
        successor = self.valid_gur(3, supersedes=middle)
        self.record(historical, successor)
        codes = self.codes(self.scan())
        self.assertIn("gur_exemption_record_invalid", codes)
        self.assertIn("gur_invalid_handoff", codes)

    def test_an_invalid_successor_exempts_nothing(self):
        historical = self.malformed_gur(1)
        successor = self.malformed_gur(2, supersedes=historical)
        self.record(historical, successor)
        codes = self.codes(self.scan())
        self.assertIn("gur_exemption_record_invalid", codes)
        self.assertIn("gur_invalid_handoff", codes)

    def test_a_conforming_predecessor_has_nothing_to_exempt(self):
        historical = self.valid_gur(1)
        successor = self.valid_gur(2, supersedes=historical)
        self.record(historical, successor)
        self.assertIn("gur_exemption_record_invalid", self.codes(self.scan()))

    def test_an_unapproved_decision_exempts_nothing(self):
        historical, successor = self.lineage()
        self.record(historical, successor)
        path = self.root / f"rulesets/adnd1e/escalations/decisions/{self.RETIRER}.yaml"
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["status"] = "proposed"
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        self.assertIn("gur_invalid_handoff", self.codes(self.scan()))

    def test_an_unrecorded_malformed_gur_is_untouched(self):
        """One record exempts one GUR, not a class of them."""
        historical, successor = self.lineage()
        self.record(historical, successor)
        other = "PKT-PHB-003-004-second"
        self.write_yaml(
            f"books/adnd1e/phb/artifacts/gur/GUR-{other}-r01.yaml",
            {
                "id": f"GUR-{other}-r01",
                "packet_id": other,
                "revision": 1,
                "supersedes": None,
                "handoff": {
                    "next_role": None, "readiness": "withdrawn",
                    "reason": "x", "blocking_ids": [],
                },
            },
        )
        self.assertIn("gur_invalid_handoff", self.codes(self.scan()))


class LiveGurHandoffExemptionCase(unittest.TestCase):
    """DEC-2026-0060's single authorized instance, against the real repository."""

    HISTORICAL = "GUR-PKT-UA-015-015-cavaliers-r02"
    SUCCESSOR = "GUR-PKT-UA-015-015-cavaliers-r03"

    @classmethod
    def setUpClass(cls):
        cls.result = scanner.scan_repository(REPO_ROOT)

    def test_r02_is_informational_history(self):
        exempt = [
            item["ArtifactId"]
            for item in self.result["Diagnostics"]
            if item["Code"] == "gur_handoff_historical_exemption"
        ]
        self.assertEqual(exempt, [self.HISTORICAL])

    def test_r02_raises_no_invalid_handoff_error(self):
        codes = [
            item["ArtifactId"]
            for item in self.result["Diagnostics"]
            if item["Code"] == "gur_invalid_handoff"
        ]
        self.assertNotIn(self.HISTORICAL, codes)

    def test_r02_produces_no_analyst_repair_item(self):
        assigned = {item["InputId"] for item in self.result["Items"]}
        self.assertNotIn(self.HISTORICAL, assigned)

    def test_no_exemption_record_is_invalid(self):
        invalid = [
            item["Message"]
            for item in self.result["Diagnostics"]
            if item["Code"] == "gur_exemption_record_invalid"
        ]
        self.assertEqual(invalid, [])

    def test_no_fourth_revision_exists(self):
        gur = REPO_ROOT / "books/adnd1e/ua/artifacts/gur"
        self.assertFalse((gur / "GUR-PKT-UA-015-015-cavaliers-r04.yaml").exists())


class InvalidImplementationReviewCase(DecisionImplementationCase):
    """DEC-2026-0061: a Review must be a Review before it can decide anything.

    REV-IMP-DEC-2026-0046-r11-r01 was published with its evidence sentence
    written as an unquoted YAML flow mapping. The commas split it into keys, the
    schema suite rejected the file, and the scanner -- which checked provenance
    but never validity -- read `overall_disposition: approved` off it and closed
    DEC-2026-0046. The repository simultaneously held that the Decision was
    complete and that the artifact completing it was invalid, and no role owned
    the contradiction.

    So validity is now a precondition of consumption, and an invalid Review is
    untrusted in every field: not its disposition, not its handoff, not the
    report it claims to review.
    """

    def review_path(self, review_id):
        return (
            self.root
            / "rulesets/adnd1e/decision-implementation-reviews"
            / f"{review_id}.yaml"
        )

    def mutate_review(self, review_id, change):
        path = self.review_path(review_id)
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        change(document)
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        return review_id

    def broken(self, *, disposition="approved"):
        """A lineage whose active Review omits a field the schema requires."""
        relative = self.decision()
        report_id = self.report(relative)
        review_id = self.implementation_review(report_id, relative, disposition=disposition)
        self.mutate_review(review_id, lambda d: d.pop("constitution_version"))
        return relative, report_id, review_id

    def successor(self, report_id, relative, review_id, *, disposition="approved"):
        """A schema-valid r02 that directly supersedes the broken r01."""
        second = self.implementation_review(
            report_id, relative, disposition=disposition, revision=2
        )
        self.mutate_review(second, lambda d: d.__setitem__("supersedes", review_id))
        return second

    def errors(self, result, code="decision_implementation_review_invalid"):
        return [d for d in result["Diagnostics"] if d["Code"] == code]

    def items(self, result, role):
        return [i for i in result["Items"] if i["Role"] == role]

    # -- the invalid Review ---------------------------------------------------

    def test_one_error_names_the_review_and_the_cause(self):
        _, _, review_id = self.broken()
        found = self.errors(self.scan())
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["ArtifactId"], review_id)
        self.assertIn("decision-implementation-review.schema.json", found[0]["Message"])
        self.assertIn("constitution_version", found[0]["Message"])

    def test_one_reviewer_repair_item_names_the_review(self):
        _, _, review_id = self.broken()
        items = self.items(self.scan(), "Reviewer")
        self.assertEqual([i["InputId"] for i in items], [review_id])
        self.assertEqual(items[0]["Queue"], "REVIEWER-DECISION-IMPLEMENTATION-REPAIR")

    def test_a_claimed_approval_does_not_complete_the_decision(self):
        """The field the old scanner trusted is the field it may no longer read."""
        relative, report_id, _ = self.broken(disposition="approved")
        result = self.scan()
        self.assertNotEqual(self.errors(result), [])
        self.assertEqual(self.items(result, "Builder"), [])
        # Nor is the report quietly treated as reviewed.
        self.assertNotIn(
            report_id, [i["InputId"] for i in self.items(result, "Reviewer")]
        )

    def test_a_claimed_revision_request_creates_no_builder_work(self):
        self.broken(disposition="revision_required")
        self.assertEqual(self.items(self.scan(), "Builder"), [])

    def test_the_real_defect_shape_is_rejected(self):
        """The exact YAML that caused this: comma-split evidence in a flow map.

        Reconstructed rather than described, because the point is that a file
        can look like a Review, parse, and still not be one.
        """
        relative = self.decision()
        report_id = self.report(relative)
        review_id = self.implementation_review(report_id, relative)
        self.mutate_review(
            review_id,
            lambda d: d["acceptance_dispositions"][0].update(
                {
                    "evidence": "Missing",
                    "revision-required": None,
                    "malformed": None,
                    "and stale-checksum Reviews retain strict handling.": None,
                }
            ),
        )
        found = self.errors(self.scan())
        self.assertEqual(len(found), 1)
        self.assertIn("acceptance_dispositions", found[0]["Message"])

    def test_the_report_itself_is_not_blamed(self):
        """A sound report must not be sent back for someone else's broken Review."""
        _, report_id, _ = self.broken()
        result = self.scan()
        self.assertEqual(
            [d for d in result["Diagnostics"]
             if d["Code"] == "decision_implementation_invalid"],
            [],
        )
        self.assertEqual(self.items(result, "Builder"), [])

    # -- recovery -------------------------------------------------------------

    def test_a_valid_successor_restores_approved_consumption(self):
        relative, report_id, review_id = self.broken()
        self.successor(report_id, relative, review_id)
        result = self.scan()
        self.assertEqual(self.errors(result), [])
        self.assertEqual(self.items(result, "Reviewer"), [])
        self.assertEqual(self.items(result, "Builder"), [])

    def test_a_valid_successor_restores_revision_routing(self):
        relative, report_id, review_id = self.broken()
        second = self.successor(
            report_id, relative, review_id, disposition="revision_required"
        )
        result = self.scan()
        self.assertEqual(self.errors(result), [])
        self.assertEqual(
            [(i["Queue"], i["InputId"]) for i in self.items(result, "Builder")],
            [("BUILDER-DECISION-IMPLEMENTATION-REVISION", second)],
        )

    def test_a_broken_predecessor_under_a_valid_leaf_is_not_repair_work(self):
        """Only the active leaf is judged; the superseded revision is history."""
        relative, report_id, review_id = self.broken()
        self.successor(report_id, relative, review_id)
        result = self.scan()
        self.assertNotIn(
            review_id, [i["InputId"] for i in self.items(result, "Reviewer")]
        )

    # -- the path this must not disturb ---------------------------------------

    def test_a_valid_approved_review_still_consumes(self):
        relative = self.decision()
        report_id = self.report(relative)
        self.implementation_review(report_id, relative)
        result = self.scan()
        self.assertEqual(self.errors(result), [])
        self.assertEqual(self.items(result, "Builder"), [])
        self.assertEqual(self.items(result, "Reviewer"), [])

    def test_a_valid_revision_required_review_still_routes_to_builder(self):
        relative = self.decision()
        report_id = self.report(relative)
        review_id = self.implementation_review(
            report_id, relative, disposition="revision_required"
        )
        result = self.scan()
        self.assertEqual(self.errors(result), [])
        self.assertEqual(
            [i["InputId"] for i in self.items(result, "Builder")], [review_id]
        )

    def test_a_report_with_no_review_at_all_is_unchanged(self):
        relative = self.decision()
        report_id = self.report(relative)
        result = self.scan()
        self.assertEqual(self.errors(result), [])
        self.assertEqual(
            [(i["Queue"], i["InputId"]) for i in self.items(result, "Reviewer")],
            [("REVIEWER-DECISION-IMPLEMENTATION", report_id)],
        )


class LiveInvalidImplementationReviewCase(unittest.TestCase):
    """DEC-2026-0061 AT5, against the repository itself."""

    HISTORICAL = "REV-IMP-DEC-2026-0046-r11-r01"
    SUCCESSOR = "REV-IMP-DEC-2026-0046-r11-r02"
    STORE = REPO_ROOT / "rulesets" / "adnd1e" / "decision-implementation-reviews"

    @classmethod
    def setUpClass(cls):
        cls.result = scanner.scan_repository(REPO_ROOT)

    def document(self, artifact_id):
        return yaml.safe_load(
            (self.STORE / f"{artifact_id}.yaml").read_text(encoding="utf-8")
        )

    def test_the_successor_supersedes_the_invalid_revision_directly(self):
        document = self.document(self.SUCCESSOR)
        self.assertEqual(document["supersedes"], self.HISTORICAL)

    def test_the_successor_preserves_the_exact_report_and_decision_provenance(self):
        historical, successor = self.document(self.HISTORICAL), self.document(self.SUCCESSOR)
        for field in ("reviewed_implementation", "decision_input"):
            with self.subTest(field=field):
                self.assertEqual(historical[field]["id"], successor[field]["id"])
                self.assertEqual(
                    historical[field]["checksum"], successor[field]["checksum"]
                )

    def test_the_predecessor_really_was_invalid(self):
        """Without this the case below could pass because nothing was wrong."""
        path = self.STORE / f"{self.HISTORICAL}.yaml"
        artifact = scanner.Artifact(
            path=path,
            kind="decision_implementation_review",
            ruleset="adnd1e",
            book=None,
            data=self.document(self.HISTORICAL),
        )
        self.assertNotEqual(scanner._review_schema_errors(REPO_ROOT, artifact), [])

    def test_the_successor_is_valid(self):
        path = self.STORE / f"{self.SUCCESSOR}.yaml"
        artifact = scanner.Artifact(
            path=path,
            kind="decision_implementation_review",
            ruleset="adnd1e",
            book=None,
            data=self.document(self.SUCCESSOR),
        )
        self.assertEqual(scanner._review_schema_errors(REPO_ROOT, artifact), [])

    def test_no_active_review_in_the_repository_is_invalid(self):
        found = [
            d["ArtifactId"]
            for d in self.result["Diagnostics"]
            if d["Code"] == "decision_implementation_review_invalid"
        ]
        self.assertEqual(found, [])

    def test_no_repair_item_is_outstanding(self):
        found = [
            i["InputId"]
            for i in self.result["Items"]
            if i["Queue"] == "REVIEWER-DECISION-IMPLEMENTATION-REPAIR"
        ]
        self.assertEqual(found, [])


class BlockedReviewReadinessCase(QueueScannerCase):
    """DEC-2026-0063: a Review says whether its revision can start yet.

    The pending-revision pass emitted `state: ready` for every role a
    revision-required Review named, whatever its handoff said. A Reviewer who
    wrote `readiness: blocked` -- because the revision cannot begin until
    something else lands -- had that answer discarded and the work reported as
    available. Readiness is a contract state, not prose: reporting blocked work
    as ready does not remove the prerequisite, it sends a role to an attempt
    that cannot succeed and inflates the count the user coordinates from.
    """

    PACKET = "PKT-PHB-001-002-fixture"

    def lineage(self, *, readiness="ready", role="builder", reason="fix M001",
                blocking=(), builder_work=False, disposition="revision_required"):
        """One reviewed GUP and one Review, built through the shared fixtures.

        `builder_work` decides whether the Review also gives the Builder a
        row-level correction, which is what makes a Review name two roles.
        """
        gur_id = self.gur(self.PACKET, 1)
        gup_id = self.gup(self.PACKET, 1, gur_id, approval_ready=True)
        review_id = self.review(
            self.PACKET, gup_id, disposition, handoff_role=role
        )
        path = (
            self.root / "books/adnd1e/phb/artifacts/reviews" / f"{review_id}.yaml"
        )
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["handoff"].update({
            "readiness": readiness,
            "reason": reason,
            "blocking_ids": list(blocking),
        })
        if builder_work:
            document["row_decisions"] = [{
                "ref": "M001",
                "disposition": "approved_with_revision",
                "exact_corrections": {"aspect": "to-hit rolls"},
            }]
        else:
            document.pop("required_builder_revision", None)
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        return gup_id, review_id

    def items(self, result, state):
        key = "Items" if state == "ready" else "BlockedItems"
        return [i for i in result[key] if i["InputId"].startswith("REV-")]

    # -- blocked stays blocked ------------------------------------------------

    def test_a_blocked_handoff_is_one_blocked_item(self):
        _, review_id = self.lineage(readiness="blocked")
        result = self.scan()
        blocked = self.items(result, "blocked")
        self.assertEqual([i["InputId"] for i in blocked], [review_id])
        self.assertEqual(blocked[0]["Role"], "Builder")

    def test_a_blocked_handoff_creates_no_ready_duplicate(self):
        """The failure was a false positive, so the absence is the assertion."""
        _, review_id = self.lineage(readiness="blocked")
        result = self.scan()
        self.assertEqual(self.items(result, "ready"), [])
        self.assertNotIn(review_id, {i["InputId"] for i in result["Items"]})

    def test_the_blocked_item_keeps_the_reviewers_reason(self):
        _, _ = self.lineage(
            readiness="blocked", reason="waiting on the registry migration",
        )
        blocked = self.items(self.scan(), "blocked")[0]
        self.assertIn("waiting on the registry migration", blocked["Reason"])
        self.assertIn("blocked", blocked["Reason"].lower())

    def test_the_blocked_item_names_its_unresolved_blockers(self):
        _, _ = self.lineage(
            readiness="blocked", blocking=("ESC-2026-01-01T00.00.00.000Z",),
        )
        blocked = self.items(self.scan(), "blocked")[0]
        self.assertIn("ESC-2026-01-01T00.00.00.000Z", blocked["Reason"])

    def test_a_decided_blocker_is_not_reported_as_unresolved(self):
        """Blocked is the Reviewer's statement; the blocker list is derived."""
        escalation = "ESC-2026-01-01T00.00.00.000Z"
        self.write_yaml(
            f"rulesets/adnd1e/escalations/decided/{escalation}.yaml",
            {"id": escalation, "status": "decided"},
        )
        self.lineage(readiness="blocked", blocking=(escalation,))
        blocked = self.items(self.scan(), "blocked")[0]
        self.assertNotIn(escalation, blocked["Reason"])

    def test_the_named_role_is_preserved_when_blocked(self):
        for role in ("builder", "analyst"):
            with self.subTest(role=role):
                self.setUp()
                self.lineage(readiness="blocked", role=role)
                blocked = self.items(self.scan(), "blocked")[0]
                self.assertEqual(blocked["Role"], role.capitalize())
                self.assertEqual(blocked["Queue"], f"{role.upper()}-REVISION-BLOCKED")

    def test_every_role_a_review_gives_work_to_is_blocked_together(self):
        """A Review can name two roles. Blocking one and readying the other
        would report half a job as available."""
        self.lineage(readiness="blocked", role="analyst", builder_work=True)
        result = self.scan()
        blocked = {i["Role"] for i in self.items(result, "blocked")}
        self.assertEqual(blocked, {"Builder", "Analyst"})
        self.assertEqual(self.items(result, "ready"), [])

    # -- ready still works ----------------------------------------------------

    def test_a_ready_handoff_produces_its_ordinary_item(self):
        _, review_id = self.lineage(readiness="ready")
        result = self.scan()
        ready = self.items(result, "ready")
        self.assertEqual([i["InputId"] for i in ready], [review_id])
        self.assertEqual(ready[0]["Queue"], "BUILDER-REVISION")
        self.assertEqual(self.items(result, "blocked"), [])

    def test_only_blocked_is_treated_as_blocked(self):
        """`terminal` and an unrecognised value are not a licence to hide work."""
        for readiness in ("ready", "terminal", "pending", ""):
            with self.subTest(readiness=readiness):
                self.setUp()
                self.lineage(readiness=readiness)
                self.assertEqual(self.items(self.scan(), "blocked"), [])

    def test_an_approved_bundle_still_reaches_integrator(self):
        """AT2 explicitly requires this route to be unchanged.

        The readiness rule is scoped to revision-required Reviews, and an
        approved bundle is a different path entirely. Asserting it here is what
        keeps the scoping honest rather than assumed.
        """
        approved_id = self.approved_bundle("PKT-PHB-003-004-second")
        result = self.scan()
        self.assertIn(
            approved_id,
            {i["InputId"] for i in result["Items"] if i["Role"] == "Integrator"},
        )

    def test_a_blocked_revision_elsewhere_does_not_hide_integrator_work(self):
        """Both in one scan: the blocked Review is blocked, the bundle is not."""
        approved_id = self.approved_bundle("PKT-PHB-003-004-second")
        self.lineage(readiness="blocked")
        result = self.scan()
        self.assertIn(
            approved_id,
            {i["InputId"] for i in result["Items"] if i["Role"] == "Integrator"},
        )
        self.assertEqual(len(self.items(result, "blocked")), 1)

    def test_the_same_review_flips_with_its_readiness(self):
        """One artifact, one field, both outcomes -- nothing else differs."""
        self.lineage(readiness="blocked")
        self.assertEqual(len(self.items(self.scan(), "blocked")), 1)

        path = (
            self.root
            / "books/adnd1e/phb/artifacts/reviews"
            / f"REV-GUP-{self.PACKET}-r01-r01.yaml"
        )
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["handoff"]["readiness"] = "ready"
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

        result = self.scan()
        self.assertEqual(self.items(result, "blocked"), [])
        self.assertEqual(len(self.items(result, "ready")), 1)


class LiveBlockedReviewReadinessCase(unittest.TestCase):
    """DEC-2026-0063 against the repository, including what must not have moved."""

    @classmethod
    def setUpClass(cls):
        cls.result = scanner.scan_repository(REPO_ROOT)

    def test_no_blocked_review_is_also_reported_ready(self):
        blocked = {i["InputId"] for i in self.result["BlockedItems"]}
        ready = {i["InputId"] for i in self.result["Items"]}
        self.assertEqual(blocked & ready, set())

    def test_every_ready_revision_item_comes_from_a_non_blocked_handoff(self):
        reviews = REPO_ROOT / "books" / "adnd1e"
        for item in self.result["Items"]:
            if not item["Queue"].endswith("-REVISION"):
                continue
            path = REPO_ROOT / item["Path"]
            if not path.is_file():
                continue
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            readiness = str(
                (document.get("handoff") or {}).get("readiness") or ""
            ).strip().lower()
            with self.subTest(item=item["InputId"]):
                self.assertNotEqual(readiness, "blocked")

    def test_the_two_named_successor_bundles_reached_integration(self):
        """AT2's other half, on the two lineages this Decision actually moved.

        Today's Integrator queue is empty only because INT-20260826-001 finished
        the work, so queue position proves nothing. What must hold is that the
        approving successors' bundles were integrated rather than lost.
        """
        integrated = set()
        for path in (REPO_ROOT / "rulesets/adnd1e/manifests").glob("INT-*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            for bundle in record.get("approved_bundles") or []:
                if bundle.get("review_id"):
                    integrated.add(str(bundle["review_id"]))
        for successor in (
            "REV-GUP-PKT-PHB-064-079-magic-user-spells-1-4-r08-r07",
            "REV-GUP-PKT-PHB-079-094-magic-user-spells-5-9-r07-r06",
        ):
            with self.subTest(review=successor):
                self.assertIn(successor, integrated)


class DecisionHandoffReplacementLiveCase(unittest.TestCase):
    """DEC-2026-0063 acceptance test 3, on the exact records that produced it."""

    ORIGINATING = (
        "REV-GUP-PKT-PHB-064-079-magic-user-spells-1-4-r08-r06",
        "REV-GUP-PKT-PHB-079-094-magic-user-spells-5-9-r07-r05",
    )
    ESCALATION = "ESC-2026-08-26T11.24.32.014Z"

    def test_the_decided_escalation_names_both_reviews_with_paths(self):
        """WORK_QUEUES 1.3 replaces a handoff only on an exact id-and-path pair."""
        document = yaml.safe_load(
            (REPO_ROOT / "rulesets/adnd1e/escalations/decided" / f"{self.ESCALATION}.yaml")
            .read_text(encoding="utf-8")
        )
        refs = dict(scanner._originating_artifact_refs(document.get("originating_artifacts")))
        for review_id in self.ORIGINATING:
            with self.subTest(review=review_id):
                self.assertIn(review_id, refs)
                self.assertTrue((REPO_ROOT / refs[review_id]).is_file())

    def test_the_decision_resolves_that_escalation(self):
        decision = yaml.safe_load(
            (REPO_ROOT / "rulesets/adnd1e/escalations/decisions/DEC-2026-0063.yaml")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(decision["escalation_id"], self.ESCALATION)
        self.assertEqual(decision["handoff"]["next_role"], "builder")

    def test_the_named_successors_exist_and_supersede_them(self):
        base = REPO_ROOT / "books/adnd1e/phb/artifacts/reviews"
        for original, successor in zip(
            self.ORIGINATING,
            (
                "REV-GUP-PKT-PHB-064-079-magic-user-spells-1-4-r08-r07",
                "REV-GUP-PKT-PHB-079-094-magic-user-spells-5-9-r07-r06",
            ),
        ):
            with self.subTest(review=successor):
                document = yaml.safe_load(
                    (base / f"{successor}.yaml").read_text(encoding="utf-8")
                )
                self.assertEqual(document["supersedes"], original)
                self.assertEqual(document["review_contract_version"], "1.3")
                self.assertEqual(document["overall_disposition"], "approved")
                self.assertTrue(document["approved_bundle_emitted"])

    def test_no_synthetic_integrator_record_was_written_for_the_preflight(self):
        """The ruling's central prohibition, checked against the manifests.

        A passing standalone check must not become an Integration or a rejection.
        Every integration record in the repository names at least one approved
        bundle; one asserting a transaction with no bundle would be the
        fabricated pass this Decision forbids.
        """
        for path in sorted((REPO_ROOT / "rulesets/adnd1e/manifests").glob("INT-*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if str(record.get("status")) != "integrated":
                continue
            with self.subTest(record=path.name):
                self.assertTrue(
                    record.get("approved_bundles"),
                    f"{path.name} claims an integration with no approved bundle",
                )


class MalformedReviewLineageRepairCase(QueueScannerCase):
    """DEC-2026-0064: one checksummed bridge across one unreadable Review.

    A published Review that will not parse cannot be edited, deleted, or read,
    and no ordinary successor makes a parser open it -- so a correction set
    living past it has no route to the Builder. The repair is not "skip
    unreadable Reviews": it is this file, at this checksum, failing this way,
    bridged by this successor, carrying this exact input pair. Every one of
    those is re-derived from the files, because a record that is believed rather
    than checked is how an exception outlives the thing it excused.
    """

    PACKET = "PKT-PHB-001-002-fixture"
    DECISION = "DEC-2026-9401"
    REVIEW_DIR = "books/adnd1e/phb/artifacts/reviews"

    def setUp(self):
        super().setUp()
        self.gur_id = self.gur(self.PACKET, 1)
        self.gup_id = self.gup(self.PACKET, 1, self.gur_id, approval_ready=True)

    # -- the fixture lineage --------------------------------------------------

    def review_path(self, revision):
        return self.root / self.REVIEW_DIR / f"REV-{self.gup_id}-r{revision:02d}.yaml"

    def write_review(self, revision, *, supersedes=None, disposition="revision_required",
                     handoff_role="builder", readiness="ready", reviewed=None):
        artifact_id = f"REV-{self.gup_id}-r{revision:02d}"
        self.write_yaml(
            f"{self.REVIEW_DIR}/{artifact_id}.yaml",
            {
                "schema_version": "1.0",
                "id": artifact_id,
                "artifact_kind": "review",
                "status": disposition,
                "ruleset_id": "adnd1e",
                "constitution_version": "1.8",
                "packet_id": self.PACKET,
                "revision": revision,
                "supersedes": supersedes,
                "reviewed_gup": {"id": reviewed or self.gup_id},
                "overall_disposition": disposition,
                "row_decisions": [{
                    "ref": "M001",
                    "disposition": "approved_with_revision",
                    "exact_corrections": {"aspect": "to-hit rolls"},
                }],
                "handoff": {
                    "next_role": handoff_role,
                    "readiness": readiness,
                    "reason": "fixture",
                    "blocking_ids": [],
                },
            },
        )
        return artifact_id

    def write_unreadable(self, revision):
        artifact_id = f"REV-{self.gup_id}-r{revision:02d}"
        path = self.root / self.REVIEW_DIR / f"{artifact_id}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        # A real YAML failure, not a truncated file: the record pins the parser's
        # message, so the fixture has to fail the same way the live artifact does.
        path.write_text(
            "id: " + artifact_id + "\n"
            "note: Source-supported but omitted: its key is already canonical\n",
            encoding="utf-8",
        )
        return artifact_id

    def lineage(self):
        original = self.write_review(1)
        unreadable = self.write_unreadable(2)
        bridge = self.write_review(3, supersedes=unreadable)
        successor = self.write_review(4, supersedes=bridge)
        return original, unreadable, bridge, successor

    def sha256(self, relative):
        return scanner._sha256_of(self.root / relative)

    def pinned(self, artifact_id, **extra):
        relative = f"{self.REVIEW_DIR}/{artifact_id}.yaml"
        block = {
            "id": artifact_id,
            "path": relative,
            "checksum": self.sha256(relative),
        }
        block.update(extra)
        return block

    def record(self, original, unreadable, bridge, successor, *, status="approved",
               **overrides):
        gup_relative = f"books/adnd1e/phb/artifacts/gup/{self.gup_id}.yaml"
        entry = {
            "disposition": "historical_unreadable_bridge",
            "reason": "fixture bridge",
            "original_review": self.pinned(original),
            "unreadable_review": self.pinned(
                unreadable,
                parse_failure={
                    "diagnostic_code": "yaml_unreadable",
                    "message_fragment": "mapping values are not allowed here",
                },
            ),
            "bridge_review": self.pinned(bridge, required_supersedes=unreadable),
            "active_successor_review": self.pinned(
                successor,
                required_supersedes=bridge,
                required_disposition="revision_required",
                required_handoff={"next_role": "builder", "readiness": "ready"},
            ),
            "reviewed_gup": {
                "id": self.gup_id,
                "path": gup_relative,
                "checksum": self.sha256(gup_relative),
            },
            "exact_builder_review_inputs": [
                self.pinned(original), self.pinned(successor)
            ],
        }
        entry.update(overrides)
        self.write_yaml(
            f"rulesets/adnd1e/escalations/decisions/{self.DECISION}.yaml",
            {
                "id": self.DECISION,
                "status": status,
                "ruleset_id": "adnd1e",
                "book_id": "phb",
                "migration_required": False,
                "handoff": {
                    "next_role": "none", "readiness": "terminal",
                    "reason": "repaired", "blocking_ids": [],
                },
                "review_malformed_lineage_repairs": [entry],
            },
        )
        return entry

    def codes(self, result):
        return [item["Code"] for item in result["Diagnostics"]]

    def builder_items(self, result):
        return [i for i in result["Items"] if i["Role"] == "Builder"]

    # -- without a record -----------------------------------------------------

    def test_without_a_record_the_lineage_is_broken(self):
        """The negative case first: the repair is never the default."""
        self.lineage()
        codes = self.codes(self.scan())
        self.assertIn("yaml_unreadable", codes)
        self.assertNotIn("review_malformed_lineage_repaired", codes)

    def test_without_a_record_no_builder_item_is_derived(self):
        self.lineage()
        self.assertEqual(self.builder_items(self.scan()), [])

    # -- with a valid record --------------------------------------------------

    def test_a_complete_record_reports_one_informational_finding(self):
        original, unreadable, bridge, successor = self.lineage()
        self.record(original, unreadable, bridge, successor)
        result = self.scan()
        found = [
            d for d in result["Diagnostics"]
            if d["Code"] == "review_malformed_lineage_repaired"
        ]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["ArtifactId"], unreadable)
        self.assertEqual(found[0]["Severity"], "info")

    def test_the_parse_error_and_missing_target_errors_are_gone(self):
        original, unreadable, bridge, successor = self.lineage()
        self.record(original, unreadable, bridge, successor)
        codes = self.codes(self.scan())
        self.assertNotIn("yaml_unreadable", codes)
        self.assertNotIn("missing_supersedes_target", codes)

    def test_the_repair_produces_no_error_at_all(self):
        original, unreadable, bridge, successor = self.lineage()
        self.record(original, unreadable, bridge, successor)
        self.assertEqual(
            [d for d in self.scan()["Diagnostics"] if d["Severity"] == "error"], []
        )

    def test_exactly_one_builder_item_for_the_successor(self):
        original, unreadable, bridge, successor = self.lineage()
        self.record(original, unreadable, bridge, successor)
        items = self.builder_items(self.scan())
        self.assertEqual([i["InputId"] for i in items], [successor])
        self.assertEqual(items[0]["Queue"], "BUILDER-REVISION")
        self.assertEqual(items[0]["State"], "ready")

    def test_the_item_components_are_exactly_the_two_named_inputs(self):
        original, unreadable, bridge, successor = self.lineage()
        self.record(original, unreadable, bridge, successor)
        components = self.builder_items(self.scan())[0]["Components"]
        self.assertEqual(
            components,
            [f"{self.REVIEW_DIR}/{original}.yaml", f"{self.REVIEW_DIR}/{successor}.yaml"],
        )

    def test_neither_the_unreadable_review_nor_the_bridge_is_an_input(self):
        """The Decision forbids passing them to the compiler; prove they are absent."""
        original, unreadable, bridge, successor = self.lineage()
        self.record(original, unreadable, bridge, successor)
        components = " ".join(self.builder_items(self.scan())[0]["Components"])
        self.assertNotIn(unreadable, components)
        self.assertNotIn(bridge, components)

    def test_the_gup_is_not_also_reported_as_unreviewed(self):
        original, unreadable, bridge, successor = self.lineage()
        self.record(original, unreadable, bridge, successor)
        reviewer = {i["InputId"] for i in self.scan()["Items"] if i["Role"] == "Reviewer"}
        self.assertNotIn(self.gup_id, reviewer)

    # -- denial cases ---------------------------------------------------------

    def assert_denied(self, result):
        """The repaired route did not apply, and the record's failure is loud.

        Deliberately not "no Builder item exists". Two denial cases leave a
        perfectly walkable chain -- if the pinned file actually parses, the
        ordinary lineage routes its leaf, and that work is real. What must never
        appear is an item carrying the repair's two-file input set, because that
        is the thing the record would have granted.
        """
        codes = self.codes(result)
        self.assertIn("review_lineage_repair_record_invalid", codes)
        self.assertNotIn("review_malformed_lineage_repaired", codes)
        for item in self.builder_items(result):
            with self.subTest(item=item["InputId"]):
                self.assertEqual(
                    len(item["Components"]), 1,
                    "a denied record must not supply the repaired input set",
                )

    def test_an_inactive_decision_repairs_nothing(self):
        original, unreadable, bridge, successor = self.lineage()
        self.record(original, unreadable, bridge, successor, status="proposed")
        codes = self.codes(self.scan())
        self.assertIn("yaml_unreadable", codes)
        self.assertNotIn("review_malformed_lineage_repaired", codes)

    def test_a_stale_checksum_on_any_pinned_file_denies_the_repair(self):
        for field in ("original_review", "unreadable_review", "bridge_review",
                      "active_successor_review", "reviewed_gup"):
            with self.subTest(field=field):
                self.setUp()
                original, unreadable, bridge, successor = self.lineage()
                entry = self.record(original, unreadable, bridge, successor)
                block = dict(entry[field])
                block["checksum"] = "sha256:" + "0" * 64
                self.record(original, unreadable, bridge, successor, **{field: block})
                self.assert_denied(self.scan())

    def test_a_parseable_unreadable_review_denies_the_repair(self):
        """If the file starts parsing, there is nothing left to bridge."""
        original = self.write_review(1)
        unreadable = self.write_review(2)
        bridge = self.write_review(3, supersedes=unreadable)
        successor = self.write_review(4, supersedes=bridge)
        self.record(original, unreadable, bridge, successor)
        result = self.scan()
        self.assert_denied(result)
        # The chain is intact here, so ordinary routing still owns the leaf.
        self.assertEqual(
            [i["InputId"] for i in self.builder_items(result)], [successor]
        )

    def test_a_wrong_parse_failure_fragment_denies_the_repair(self):
        original, unreadable, bridge, successor = self.lineage()
        entry = self.record(original, unreadable, bridge, successor)
        block = dict(entry["unreadable_review"])
        block["parse_failure"] = {
            "diagnostic_code": "yaml_unreadable",
            "message_fragment": "found undefined alias",
        }
        self.record(original, unreadable, bridge, successor, unreadable_review=block)
        self.assert_denied(self.scan())

    def test_a_wrong_diagnostic_code_denies_the_repair(self):
        original, unreadable, bridge, successor = self.lineage()
        entry = self.record(original, unreadable, bridge, successor)
        block = dict(entry["unreadable_review"])
        block["parse_failure"] = {
            "diagnostic_code": "yaml_root_not_mapping",
            "message_fragment": "mapping values are not allowed here",
        }
        self.record(original, unreadable, bridge, successor, unreadable_review=block)
        self.assert_denied(self.scan())

    def test_a_broken_bridge_link_denies_the_repair(self):
        """The bridge must supersede the unreadable file, not merely follow it."""
        original = self.write_review(1)
        unreadable = self.write_unreadable(2)
        bridge = self.write_review(3, supersedes=original)
        successor = self.write_review(4, supersedes=bridge)
        self.record(original, unreadable, bridge, successor)
        self.assert_denied(self.scan())

    def test_a_broken_successor_link_denies_the_repair(self):
        original = self.write_review(1)
        unreadable = self.write_unreadable(2)
        bridge = self.write_review(3, supersedes=unreadable)
        successor = self.write_review(4, supersedes=original)
        self.record(original, unreadable, bridge, successor)
        self.assert_denied(self.scan())

    def test_a_successor_reviewing_another_gup_denies_the_repair(self):
        original = self.write_review(1)
        unreadable = self.write_unreadable(2)
        bridge = self.write_review(3, supersedes=unreadable)
        successor = self.write_review(4, supersedes=bridge, reviewed="GUP-OTHER-r01")
        self.record(original, unreadable, bridge, successor)
        self.assert_denied(self.scan())

    def test_a_non_ready_successor_handoff_denies_the_repair(self):
        original = self.write_review(1)
        unreadable = self.write_unreadable(2)
        bridge = self.write_review(3, supersedes=unreadable)
        successor = self.write_review(4, supersedes=bridge, readiness="blocked")
        self.record(original, unreadable, bridge, successor)
        self.assert_denied(self.scan())

    def test_a_non_builder_successor_handoff_denies_the_repair(self):
        original = self.write_review(1)
        unreadable = self.write_unreadable(2)
        bridge = self.write_review(3, supersedes=unreadable)
        successor = self.write_review(4, supersedes=bridge, handoff_role="analyst")
        self.record(original, unreadable, bridge, successor)
        self.assert_denied(self.scan())

    def test_a_wrong_successor_disposition_denies_the_repair(self):
        original = self.write_review(1)
        unreadable = self.write_unreadable(2)
        bridge = self.write_review(3, supersedes=unreadable)
        successor = self.write_review(4, supersedes=bridge, disposition="approved")
        self.record(original, unreadable, bridge, successor)
        self.assert_denied(self.scan())

    def test_a_schema_invalid_successor_denies_the_repair(self):
        original, unreadable, bridge, successor = self.lineage()
        path = self.review_path(4)
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["review_contract_version"] = "1.2"
        document["row_decisions"][0].pop("exact_corrections")
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        self.record(original, unreadable, bridge, successor)
        self.assert_denied(self.scan())

    def test_a_changed_input_set_denies_the_repair(self):
        for inputs in (
            "drop_one", "add_one", "wrong_member",
        ):
            with self.subTest(case=inputs):
                self.setUp()
                original, unreadable, bridge, successor = self.lineage()
                entry = self.record(original, unreadable, bridge, successor)
                if inputs == "drop_one":
                    changed = [entry["exact_builder_review_inputs"][0]]
                elif inputs == "add_one":
                    changed = entry["exact_builder_review_inputs"] + [self.pinned(bridge)]
                else:
                    changed = [self.pinned(original), self.pinned(bridge)]
                self.record(
                    original, unreadable, bridge, successor,
                    exact_builder_review_inputs=changed,
                )
                self.assert_denied(self.scan())

    def test_a_wrong_disposition_on_the_record_denies_the_repair(self):
        original, unreadable, bridge, successor = self.lineage()
        self.record(
            original, unreadable, bridge, successor,
            disposition="historical_handoff_only",
        )
        self.assert_denied(self.scan())

    def test_a_record_without_a_reason_denies_the_repair(self):
        original, unreadable, bridge, successor = self.lineage()
        self.record(original, unreadable, bridge, successor, reason="")
        self.assert_denied(self.scan())

    def test_another_unreadable_review_is_untouched(self):
        """One record repairs one lineage, not a class of them."""
        original, unreadable, bridge, successor = self.lineage()
        self.record(original, unreadable, bridge, successor)
        other = "PKT-PHB-003-004-second"
        other_gur = self.gur(other, 1)
        other_gup = self.gup(other, 1, other_gur, approval_ready=True)
        path = self.root / self.REVIEW_DIR / f"REV-{other_gup}-r01.yaml"
        path.write_text(
            "id: REV-" + other_gup + "-r01\n"
            "note: broken: like the other one\n",
            encoding="utf-8",
        )
        self.assertIn("yaml_unreadable", self.codes(self.scan()))


class LiveMalformedReviewLineageRepairCase(unittest.TestCase):
    """DEC-2026-0064's single authorized instance, against the repository."""

    UNREADABLE = "REV-GUP-PKT-PHB-054-064-druid-spells-r01-r04"
    BRIDGE = "REV-GUP-PKT-PHB-054-064-druid-spells-r01-r05"
    SUCCESSOR = "REV-GUP-PKT-PHB-054-064-druid-spells-r01-r06"
    ORIGINAL = "REV-GUP-PKT-PHB-054-064-druid-spells-r01-r01"

    @classmethod
    def setUpClass(cls):
        cls.result = scanner.scan_repository(REPO_ROOT)

    def test_the_unreadable_review_is_informational_history(self):
        found = [
            d for d in self.result["Diagnostics"]
            if d["Code"] == "review_malformed_lineage_repaired"
        ]
        self.assertEqual([d["ArtifactId"] for d in found], [self.UNREADABLE])

    def test_it_raises_no_parse_error(self):
        """Scoped to the bridged lineage, which is what the record covers.

        This asserted that the whole repository was free of parse errors, which
        was true on the day it was written and is not a property this Decision
        governs. Other roles have since published their own malformed files, and
        those must fail loudly somewhere -- just not here, where the claim is
        that DEC-2026-0064's exemption works.
        """
        offenders = [
            d for d in self.result["Diagnostics"]
            if d["Code"] in ("yaml_unreadable", "missing_supersedes_target")
            and (
                self.UNREADABLE in str(d.get("ArtifactId") or "")
                or self.UNREADABLE in str(d.get("Path") or "")
                or self.BRIDGE in str(d.get("ArtifactId") or "")
            )
        ]
        self.assertEqual(offenders, [])

    def test_the_exemption_did_not_spread_to_other_unreadable_files(self):
        """Fail-closed, stated as a property rather than assumed.

        Every parse failure the scan reports must be for some file other than
        the one DEC-2026-0064 pins -- the pinned one is skipped, and nothing
        else is.
        """
        for diagnostic in self.result["Diagnostics"]:
            if diagnostic["Code"] != "yaml_unreadable":
                continue
            with self.subTest(path=diagnostic.get("Path")):
                self.assertNotIn(self.UNREADABLE, str(diagnostic.get("Path") or ""))

    def test_no_repair_record_is_invalid(self):
        invalid = [
            d["Message"] for d in self.result["Diagnostics"]
            if d["Code"] == "review_lineage_repair_record_invalid"
        ]
        self.assertEqual(invalid, [])

    def test_the_repaired_route_produced_the_revision(self):
        """The durable form of "the item existed and named both inputs".

        Asserting the item's presence tied this case to the moment before
        GUP-PKT-PHB-054-064-druid-spells-r02 was published. Once the revision
        exists the record stops routing work -- the leaf has moved on -- and a
        test that reads queue position fails on the work being done. What
        remains true is which Review the revision was built from.
        """
        gup = yaml.safe_load(
            (REPO_ROOT / "books/adnd1e/phb/artifacts/gup"
             / "GUP-PKT-PHB-054-064-druid-spells-r02.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(gup["provenance"]["review_id"], self.SUCCESSOR)
        self.assertEqual(gup["supersedes"], "GUP-PKT-PHB-054-064-druid-spells-r01")

    def test_the_bridge_and_unreadable_reviews_are_not_builder_inputs(self):
        components = " ".join(
            component
            for item in self.result["Items"]
            for component in item["Components"]
        )
        self.assertNotIn(self.UNREADABLE, components)
        self.assertNotIn(self.BRIDGE, components)

    def test_the_decision_never_suppressed_its_own_routed_item(self):
        """WORK_QUEUES 1.3 replaces an originating artifact's stale handoff.

        DEC-2026-0064's escalation names r06, so without an exemption the rule
        removed the very item the Decision exists to expose -- and would have
        kept removing it after the Decision was consumed, because the
        replacement is computed from the Decision's handoff rather than from
        whether its work is still outstanding. The revision below is the proof
        that it did not: r06's directives reached a published GUP, which could
        not have happened had the item stayed suppressed.
        """
        replaced = [
            d["ArtifactId"] for d in self.result["Diagnostics"]
            if d["Code"] == "handoff_replaced_by_decision"
        ]
        self.assertNotIn(self.SUCCESSOR, replaced)
        self.assertTrue(
            (REPO_ROOT / "books/adnd1e/phb/artifacts/gup"
             / "GUP-PKT-PHB-054-064-druid-spells-r02.yaml").is_file()
        )


class MalformedArtifactNeverCrashesTheScanCase(QueueScannerCase):
    """One unreadable file must cost one diagnostic, not the whole queue.

    `_packaged_gup_id` documents itself as returning "" when nothing names the
    packaged GUP, then dereferenced its Review argument unconditionally. That
    argument is looked up by a name derived from the bundle, so it is None
    whenever the Review is absent *or does not parse* -- and when
    REV-GUP-PKT-PHB-117-119-bards-r04-r02 was published unparseable, the scan
    raised AttributeError instead of reporting it. Every role reads its work
    from this scan, so a single malformed artifact took the queue away from all
    five at once.

    Failing closed means reporting the file, not falling over.
    """

    PACKET = "PKT-PHB-001-002-fixture"

    def malformed_review(self, name):
        path = self.root / "books/adnd1e/phb/artifacts/reviews" / f"{name}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"id: {name}\nnote: broken\n"
            "This successor: is not valid YAML: at all\n",
            encoding="utf-8",
        )
        return path

    def bundle_without_a_readable_review(self):
        """An Approved bundle whose derived Review name will not parse."""
        gur_id = self.gur(self.PACKET, 1)
        gup_id = self.gup(self.PACKET, 1, gur_id)
        review_id = f"REV-{gup_id}-r01"
        self.malformed_review(review_id)
        approved_id = "APPROVED-" + review_id[len("REV-"):]
        approved_dir = self.book / "artifacts" / "approved"
        approved_dir.mkdir(parents=True, exist_ok=True)
        (approved_dir / f"{approved_id}.edges.csv").write_text(
            "source_id,target_id\n", encoding="utf-8"
        )
        return approved_id, review_id

    def test_the_scan_completes(self):
        self.bundle_without_a_readable_review()
        result = self.scan()  # must not raise
        self.assertIn("Items", result)

    def test_the_unreadable_file_is_reported(self):
        _, review_id = self.bundle_without_a_readable_review()
        codes = [d["Code"] for d in self.scan()["Diagnostics"]]
        self.assertIn("yaml_unreadable", codes)

    def test_it_is_an_error_not_a_silent_skip(self):
        """Fail closed: an unrecognised parse failure is never informational."""
        self.bundle_without_a_readable_review()
        unreadable = [
            d for d in self.scan()["Diagnostics"] if d["Code"] == "yaml_unreadable"
        ]
        self.assertTrue(unreadable)
        for diagnostic in unreadable:
            self.assertEqual(diagnostic["Severity"], "error")

    def test_other_roles_still_get_their_work(self):
        """The point of not crashing: everyone else's queue survives it."""
        self.bundle_without_a_readable_review()
        other = "PKT-PHB-003-004-second"
        other_gur = self.gur(other, 1)
        self.gup(other, 1, other_gur, approval_ready=True)
        result = self.scan()
        self.assertIn(
            f"GUP-{other}-r01", {i["InputId"] for i in result["Items"]}
        )


class DirectPredecessorRepairCase(QueueScannerCase):
    """DEC-2026-0068: the shape DEC-2026-0064's bridge cannot express.

    A two-hop bridge needs a middle artifact. The Bards lineage has none -- r03
    directly supersedes the unreadable r02 -- so fitting it to the bridge record
    would make one Review occupy both the bridge and successor slots, which is
    a claim that it supersedes itself.

    Being a different shape does not make it a looser one. This successor exists
    to repackage a rejected bundle, so the bundle, the rejection it answers, the
    component it packages and the exact row partition are all pinned too, and
    all re-derived here. Nothing is read from the unreadable file.
    """

    PACKET = "PKT-PHB-001-002-fixture"
    DECISION = "DEC-2026-9501"
    REVIEWS = "books/adnd1e/phb/artifacts/reviews"
    APPROVED = "books/adnd1e/phb/artifacts/approved"

    def setUp(self):
        super().setUp()
        self.gur_id = self.gur(self.PACKET, 1)
        self.gup_id = self.gup(self.PACKET, 1, self.gur_id, approval_ready=True)
        self.component = f"{self.APPROVED}/APPROVED-{self.gup_id}-r01.edges.csv"
        path = self.root / self.component
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "source_id,target_id\n" + "".join(
                f"a{i},b{i}\n" for i in range(1, 6)
            ),
            encoding="utf-8",
        )
        self.rejection = "rulesets/adnd1e/reports/INT-29990101-001.rejected.json"
        rejection = self.root / self.rejection
        rejection.parent.mkdir(parents=True, exist_ok=True)
        # Written by `write_rejection` once the bundles exist, so every pinned
        # checksum in it is real. A rejection the scanner's ordinary validator
        # would reject is a state the repository could never hold, and testing
        # the repair against one would prove nothing.
        self.rejection_path = rejection

    # -- the fixture lineage --------------------------------------------------

    def write_review(self, revision, *, supersedes=None, disposition="approved",
                     handoff_role="architect", readiness="ready", reviewed=None,
                     bundle=None):
        artifact_id = f"REV-{self.gup_id}-r{revision:02d}"
        document = {
            "schema_version": "1.0",
            "id": artifact_id,
            "artifact_kind": "review",
            "status": disposition,
            "ruleset_id": "adnd1e",
            "constitution_version": "1.8",
            "packet_id": self.PACKET,
            "revision": revision,
            "supersedes": supersedes,
            "reviewed_gup": {"id": reviewed or self.gup_id},
            "overall_disposition": disposition,
            "handoff": {
                "next_role": handoff_role, "readiness": readiness,
                "reason": "fixture", "blocking_ids": [],
            },
        }
        if bundle:
            document["approved_bundle_emitted"] = bundle
        self.write_yaml(f"{self.REVIEWS}/{artifact_id}.yaml", document)
        return artifact_id

    def write_unreadable_review(self, revision):
        artifact_id = f"REV-{self.gup_id}-r{revision:02d}"
        path = self.root / self.REVIEWS / f"{artifact_id}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"id: {artifact_id}\nnote: broken\n"
            "This successor consumes the rejection\n"
            "and keeps going: without a colon\n",
            encoding="utf-8",
        )
        return artifact_id

    def write_bundle(self, revision, *, supersedes=None, approves=None,
                     additions=29, pending=28, updates=0, nodes=11,
                     first_pending=None):
        artifact_id = f"APPROVED-{self.gup_id}-r{revision:02d}"
        start_pending = first_pending or additions + 1
        self.write_yaml(
            f"{self.APPROVED}/{artifact_id}.yaml",
            {
                "schema_version": "1.0",
                "id": artifact_id,
                "artifact_kind": "packet_update",
                "status": "approved",
                "ruleset_id": "adnd1e",
                "constitution_version": "1.8",
                "packet_id": self.PACKET,
                "revision": revision,
                "supersedes": supersedes,
                "approves": {
                    "review_id": approves or f"REV-{self.gup_id}-r{revision:02d}",
                    "gup_id": self.gup_id,
                },
                "components": [{
                    "kind": "edges",
                    "path": self.component,
                    "checksum": self.sha256(self.component),
                }],
                "operation_index": {
                    "additions": [{"csv_row": i} for i in range(1, additions + 1)],
                    "pending_additions": [
                        {"csv_row": i}
                        for i in range(start_pending, start_pending + pending)
                    ],
                    "updates": [{"csv_row": 0}] * updates,
                },
                "node_operations": {"count": nodes},
                "handoff": {
                    "next_role": "integrator", "readiness": "ready",
                    "reason": "fixture", "blocking_ids": [],
                },
            },
        )
        if revision == 1:
            # The rejection refused the first bundle, which a readable Review
            # approved -- exactly the live Bards shape, where INT-20260827-001
            # refused the r01 bundle and the unreadable r02 Review came after.
            self.write_rejection(artifact_id)
        return artifact_id

    def write_rejection(self, bundle_id):
        """A rejection record the scanner's own validator accepts."""
        manifest = f"{self.APPROVED}/{bundle_id}.yaml"
        gup_relative = f"books/adnd1e/phb/artifacts/gup/{self.gup_id}.yaml"
        review_relative = f"{self.REVIEWS}/REV-{self.gup_id}-r01.yaml"
        self.rejection_path.write_text(
            json.dumps({
                "id": "INT-29990101-001",
                "ruleset_id": "adnd1e",
                "status": "rejected",
                "rejected_bundles": [{
                    "bundle_id": bundle_id,
                    "bundle_checksum": self.sha256(manifest),
                    "review_id": f"REV-{self.gup_id}-r01",
                    "review_checksum": self.sha256(review_relative),
                    "gup_id": self.gup_id,
                    "gup_checksum": self.sha256(gup_relative),
                    "packet_id": self.PACKET,
                    "manifest_path": manifest,
                    "blocking_failures": [
                        {"check": "fixture_failure", "detail": "fixture blocking detail"}
                    ],
                    "blocking_failure_count": 1,
                    "advisory_failure_count": 0,
                    "checks_evaluated": 1,
                }],
            }, indent=1) + "\n",
            encoding="utf-8",
        )

    def lineage(self):
        original = self.write_review(1)
        self.write_bundle(1, approves=original)
        unreadable = self.write_unreadable_review(2)
        historical = self.write_bundle(2, approves=unreadable)
        successor = self.write_review(3, supersedes=unreadable,
                                      bundle=f"APPROVED-{self.gup_id}-r03")
        bundle = self.write_bundle(3, supersedes=historical, approves=successor)
        return original, unreadable, historical, successor, bundle

    def sha256(self, relative):
        return scanner._sha256_of(self.root / relative)

    def pinned(self, artifact_id, directory, **extra):
        relative = f"{directory}/{artifact_id}.yaml"
        block = {"id": artifact_id, "path": relative,
                 "checksum": self.sha256(relative)}
        block.update(extra)
        return block

    def record(self, original, unreadable, historical, successor, bundle, *,
               status="approved", **overrides):
        gup_relative = f"books/adnd1e/phb/artifacts/gup/{self.gup_id}.yaml"
        entry = {
            "disposition": "historical_unreadable_direct_predecessor",
            "reason": "fixture direct predecessor",
            "original_review": self.pinned(original, self.REVIEWS),
            "unreadable_review": self.pinned(
                unreadable, self.REVIEWS,
                parse_failure={
                    "diagnostic_code": "yaml_unreadable",
                    "message_fragment": "could not find expected ':'",
                },
            ),
            "historical_bundle": self.pinned(historical, self.APPROVED),
            "active_successor_review": self.pinned(
                successor, self.REVIEWS,
                required_supersedes=unreadable,
                required_disposition="approved",
                required_handoff={"next_role": "architect", "readiness": "ready"},
            ),
            "active_successor_bundle": self.pinned(
                bundle, self.APPROVED, required_supersedes=historical,
            ),
            "reviewed_gup": {
                "id": self.gup_id, "path": gup_relative,
                "checksum": self.sha256(gup_relative),
            },
            "integration_rejection": {
                "id": "INT-29990101-001", "path": self.rejection,
                "checksum": self.sha256(self.rejection),
            },
            "edge_component": {
                "path": self.component,
                "checksum": self.sha256(self.component),
                "rows": 5,
            },
            "required_operations": {
                "additions": {"first_csv_row": 1, "last_csv_row": 29, "count": 29},
                "pending_additions": {"first_csv_row": 30, "last_csv_row": 57,
                                      "count": 28},
                "updates_count": 0,
                "registered_node_count": 11,
            },
        }
        entry.update(overrides)
        self.write_yaml(
            f"rulesets/adnd1e/escalations/decisions/{self.DECISION}.yaml",
            {
                "id": self.DECISION, "status": status, "ruleset_id": "adnd1e",
                "book_id": "phb", "migration_required": False,
                "handoff": {"next_role": "none", "readiness": "terminal",
                            "reason": "repaired", "blocking_ids": []},
                "review_direct_predecessor_repairs": [entry],
            },
        )
        return entry

    def codes(self, result):
        return [item["Code"] for item in result["Diagnostics"]]

    def errors(self, result):
        return [d for d in result["Diagnostics"] if d["Severity"] == "error"]

    # -- without a record -----------------------------------------------------

    def test_without_a_record_the_file_is_an_error(self):
        self.lineage()
        self.assertIn("yaml_unreadable", self.codes(self.scan()))

    # -- with a valid record --------------------------------------------------

    def test_a_complete_record_reports_one_informational_finding(self):
        _, unreadable, *_ = self.lineage()
        self.record(*self.lineage_args())
        found = [
            d for d in self.scan()["Diagnostics"]
            if d["Code"] == "review_unreadable_direct_predecessor_repaired"
        ]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["ArtifactId"], unreadable)
        self.assertEqual(found[0]["Severity"], "info")

    def lineage_args(self):
        """Rebuild the same lineage IDs without rewriting the files."""
        return (
            f"REV-{self.gup_id}-r01", f"REV-{self.gup_id}-r02",
            f"APPROVED-{self.gup_id}-r02", f"REV-{self.gup_id}-r03",
            f"APPROVED-{self.gup_id}-r03",
        )

    def test_the_parse_error_is_gone(self):
        self.lineage()
        self.record(*self.lineage_args())
        self.assertNotIn("yaml_unreadable", self.codes(self.scan()))

    def test_the_successor_does_not_dangle(self):
        """Skipping the file must not turn its successor into a broken link."""
        self.lineage()
        self.record(*self.lineage_args())
        self.assertNotIn("missing_supersedes_target", self.codes(self.scan()))

    def test_the_parent_is_not_left_as_a_second_leaf(self):
        """The other half: r01 is superseded through the file nobody can read."""
        self.lineage()
        self.record(*self.lineage_args())
        codes = self.codes(self.scan())
        self.assertNotIn("ambiguous_revision_lineage", codes)
        self.assertNotIn("legacy_revision_inference", codes)

    def test_the_repair_produces_no_error(self):
        self.lineage()
        self.record(*self.lineage_args())
        self.assertEqual(self.errors(self.scan()), [])

    # -- denial cases ---------------------------------------------------------

    def assert_denied(self, result):
        codes = self.codes(result)
        self.assertIn("review_direct_predecessor_repair_record_invalid", codes)
        self.assertNotIn("review_unreadable_direct_predecessor_repaired", codes)
        self.assertIn("yaml_unreadable", codes)

    def test_an_inactive_decision_repairs_nothing(self):
        self.lineage()
        self.record(*self.lineage_args(), status="proposed")
        codes = self.codes(self.scan())
        self.assertIn("yaml_unreadable", codes)
        self.assertNotIn("review_unreadable_direct_predecessor_repaired", codes)

    def test_a_stale_checksum_on_any_pinned_artifact_denies_it(self):
        for field in ("original_review", "unreadable_review", "historical_bundle",
                      "active_successor_review", "active_successor_bundle",
                      "reviewed_gup", "integration_rejection", "edge_component"):
            with self.subTest(field=field):
                self.setUp()
                self.lineage()
                entry = self.record(*self.lineage_args())
                block = dict(entry[field])
                block["checksum"] = "sha256:" + "0" * 64
                self.record(*self.lineage_args(), **{field: block})
                self.assert_denied(self.scan())

    def test_a_parseable_predecessor_denies_it(self):
        self.write_bundle(1, approves=self.write_review(1))
        self.write_review(2)
        self.write_bundle(2, approves=f"REV-{self.gup_id}-r02")
        self.write_review(3, supersedes=f"REV-{self.gup_id}-r02",
                          bundle=f"APPROVED-{self.gup_id}-r03")
        self.write_bundle(3, supersedes=f"APPROVED-{self.gup_id}-r02",
                          approves=f"REV-{self.gup_id}-r03")
        self.record(*self.lineage_args())
        codes = self.codes(self.scan())
        self.assertIn("review_direct_predecessor_repair_record_invalid", codes)
        self.assertNotIn("review_unreadable_direct_predecessor_repaired", codes)

    def test_a_wrong_parse_fragment_denies_it(self):
        self.lineage()
        entry = self.record(*self.lineage_args())
        block = dict(entry["unreadable_review"])
        block["parse_failure"] = {"diagnostic_code": "yaml_unreadable",
                                  "message_fragment": "found undefined alias"}
        self.record(*self.lineage_args(), unreadable_review=block)
        self.assert_denied(self.scan())

    def test_a_wrong_review_link_denies_it(self):
        self.write_bundle(1, approves=self.write_review(1))
        unreadable = self.write_unreadable_review(2)
        historical = self.write_bundle(2, approves=unreadable)
        self.write_review(3, supersedes=f"REV-{self.gup_id}-r01",
                          bundle=f"APPROVED-{self.gup_id}-r03")
        self.write_bundle(3, supersedes=historical, approves=f"REV-{self.gup_id}-r03")
        self.record(*self.lineage_args())
        self.assert_denied(self.scan())

    def test_a_wrong_bundle_link_denies_it(self):
        self.write_bundle(1, approves=self.write_review(1))
        unreadable = self.write_unreadable_review(2)
        self.write_bundle(2, approves=unreadable)
        self.write_review(3, supersedes=unreadable,
                          bundle=f"APPROVED-{self.gup_id}-r03")
        self.write_bundle(3, supersedes=None, approves=f"REV-{self.gup_id}-r03")
        self.record(*self.lineage_args())
        self.assert_denied(self.scan())

    def test_a_non_approved_successor_denies_it(self):
        self.write_bundle(1, approves=self.write_review(1))
        unreadable = self.write_unreadable_review(2)
        historical = self.write_bundle(2, approves=unreadable)
        self.write_review(3, supersedes=unreadable, disposition="revision_required",
                          bundle=f"APPROVED-{self.gup_id}-r03")
        self.write_bundle(3, supersedes=historical, approves=f"REV-{self.gup_id}-r03")
        self.record(*self.lineage_args())
        self.assert_denied(self.scan())

    def test_a_wrong_successor_handoff_denies_it(self):
        for role, readiness in (("integrator", "ready"), ("architect", "blocked")):
            with self.subTest(role=role, readiness=readiness):
                self.setUp()
                self.write_bundle(1, approves=self.write_review(1))
                unreadable = self.write_unreadable_review(2)
                historical = self.write_bundle(2, approves=unreadable)
                self.write_review(3, supersedes=unreadable, handoff_role=role,
                                  readiness=readiness,
                                  bundle=f"APPROVED-{self.gup_id}-r03")
                self.write_bundle(3, supersedes=historical,
                                  approves=f"REV-{self.gup_id}-r03")
                self.record(*self.lineage_args())
                self.assert_denied(self.scan())

    def test_a_successor_reviewing_another_gup_denies_it(self):
        self.write_bundle(1, approves=self.write_review(1))
        unreadable = self.write_unreadable_review(2)
        historical = self.write_bundle(2, approves=unreadable)
        self.write_review(3, supersedes=unreadable, reviewed="GUP-OTHER-r01",
                          bundle=f"APPROVED-{self.gup_id}-r03")
        self.write_bundle(3, supersedes=historical, approves=f"REV-{self.gup_id}-r03")
        self.record(*self.lineage_args())
        self.assert_denied(self.scan())

    def test_a_bundle_approving_another_review_denies_it(self):
        self.write_bundle(1, approves=self.write_review(1))
        unreadable = self.write_unreadable_review(2)
        historical = self.write_bundle(2, approves=unreadable)
        self.write_review(3, supersedes=unreadable,
                          bundle=f"APPROVED-{self.gup_id}-r03")
        self.write_bundle(3, supersedes=historical, approves=f"REV-{self.gup_id}-r01")
        self.record(*self.lineage_args())
        self.assert_denied(self.scan())

    def test_a_non_contiguous_partition_denies_it(self):
        """A gap between the buckets is a different transaction."""
        self.write_bundle(1, approves=self.write_review(1))
        unreadable = self.write_unreadable_review(2)
        historical = self.write_bundle(2, approves=unreadable)
        self.write_review(3, supersedes=unreadable,
                          bundle=f"APPROVED-{self.gup_id}-r03")
        self.write_bundle(3, supersedes=historical, approves=f"REV-{self.gup_id}-r03",
                          first_pending=31)
        self.record(*self.lineage_args())
        self.assert_denied(self.scan())

    def test_a_wrong_row_count_denies_it(self):
        self.write_bundle(1, approves=self.write_review(1))
        unreadable = self.write_unreadable_review(2)
        historical = self.write_bundle(2, approves=unreadable)
        self.write_review(3, supersedes=unreadable,
                          bundle=f"APPROVED-{self.gup_id}-r03")
        self.write_bundle(3, supersedes=historical, approves=f"REV-{self.gup_id}-r03",
                          additions=28, pending=28)
        self.record(*self.lineage_args())
        self.assert_denied(self.scan())

    def test_a_nonzero_update_count_denies_it(self):
        self.write_bundle(1, approves=self.write_review(1))
        unreadable = self.write_unreadable_review(2)
        historical = self.write_bundle(2, approves=unreadable)
        self.write_review(3, supersedes=unreadable,
                          bundle=f"APPROVED-{self.gup_id}-r03")
        self.write_bundle(3, supersedes=historical, approves=f"REV-{self.gup_id}-r03",
                          updates=1)
        self.record(*self.lineage_args())
        self.assert_denied(self.scan())

    def test_a_different_node_count_denies_it(self):
        self.write_bundle(1, approves=self.write_review(1))
        unreadable = self.write_unreadable_review(2)
        historical = self.write_bundle(2, approves=unreadable)
        self.write_review(3, supersedes=unreadable,
                          bundle=f"APPROVED-{self.gup_id}-r03")
        self.write_bundle(3, supersedes=historical, approves=f"REV-{self.gup_id}-r03",
                          nodes=10)
        self.record(*self.lineage_args())
        self.assert_denied(self.scan())

    def test_a_wrong_disposition_denies_it(self):
        self.lineage()
        self.record(*self.lineage_args(),
                    disposition="historical_unreadable_bridge")
        self.assert_denied(self.scan())

    def test_a_record_without_a_reason_denies_it(self):
        self.lineage()
        self.record(*self.lineage_args(), reason="")
        self.assert_denied(self.scan())

    def test_another_unreadable_review_is_untouched(self):
        """One record admits one file, never a class of them."""
        self.lineage()
        self.record(*self.lineage_args())
        other = "PKT-PHB-003-004-second"
        other_gur = self.gur(other, 1)
        other_gup = self.gup(other, 1, other_gur, approval_ready=True)
        path = self.root / self.REVIEWS / f"REV-{other_gup}-r01.yaml"
        path.write_text("id: x\nbroken: like: the other one\n", encoding="utf-8")
        self.assertIn("yaml_unreadable", self.codes(self.scan()))


class LiveDirectPredecessorRepairCase(unittest.TestCase):
    """DEC-2026-0068's single authorized instance, against the repository."""

    UNREADABLE = "REV-GUP-PKT-PHB-117-119-bards-r04-r02"
    SUCCESSOR = "REV-GUP-PKT-PHB-117-119-bards-r04-r03"
    ORIGINAL = "REV-GUP-PKT-PHB-117-119-bards-r04-r01"

    @classmethod
    def setUpClass(cls):
        cls.result = scanner.scan_repository(REPO_ROOT)

    def test_the_predecessor_is_informational_history(self):
        found = [
            d["ArtifactId"] for d in self.result["Diagnostics"]
            if d["Code"] == "review_unreadable_direct_predecessor_repaired"
        ]
        self.assertEqual(found, [self.UNREADABLE])

    def test_it_raises_no_parse_or_link_error_of_its_own(self):
        for diagnostic in self.result["Diagnostics"]:
            if diagnostic["Code"] not in ("yaml_unreadable", "missing_supersedes_target"):
                continue
            with self.subTest(code=diagnostic["Code"]):
                self.assertNotIn(self.UNREADABLE, str(diagnostic.get("Path") or ""))
                self.assertNotIn(self.SUCCESSOR, str(diagnostic.get("ArtifactId") or ""))

    def test_no_record_is_invalid(self):
        invalid = [
            d["Message"] for d in self.result["Diagnostics"]
            if d["Code"] == "review_direct_predecessor_repair_record_invalid"
        ]
        self.assertEqual(invalid, [])

    def test_the_record_is_distinct_from_the_druid_bridge(self):
        """The two exceptions are separate records with separate shapes.

        DEC-2026-0064 bridges across a middle artifact; this one admits a direct
        pair. Neither may be used to justify the other's file, which is why they
        are validated by different predicates rather than one relaxed rule.
        """
        decisions = REPO_ROOT / "rulesets/adnd1e/escalations/decisions"
        bridge = yaml.safe_load(
            (decisions / "DEC-2026-0064.yaml").read_text(encoding="utf-8")
        )
        direct = yaml.safe_load(
            (decisions / "DEC-2026-0068.yaml").read_text(encoding="utf-8")
        )
        self.assertIn("review_malformed_lineage_repairs", bridge)
        self.assertNotIn("review_direct_predecessor_repairs", bridge)
        self.assertIn("review_direct_predecessor_repairs", direct)
        self.assertNotIn("review_malformed_lineage_repairs", direct)

    def test_the_successor_directly_supersedes_the_unreadable_file(self):
        document = yaml.safe_load(
            (REPO_ROOT / "books/adnd1e/phb/artifacts/reviews"
             / f"{self.SUCCESSOR}.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(document["supersedes"], self.UNREADABLE)


class ImplementationReviewRepairCase(QueueScannerCase):
    """DEC-2026-0072: the unreadable-predecessor shape, one artifact kind over.

    Structurally this is DEC-2026-0068's record applied to a Decision
    Implementation Review instead of a packet Review. They are kept separate
    because the predicates differ in substance: what makes a packet Review's
    successor trustworthy is its bundle and row partition, and what makes an
    implementation Review's successor trustworthy is that it pins the same
    report and the same Decision its unreadable predecessor was published to
    review. A rule loose enough to cover both would check neither.
    """

    DECISION = "DEC-2026-9601"
    SUBJECT = "DEC-2026-9602"
    STORE = "rulesets/adnd1e/decision-implementation-reviews"
    REPORTS = "rulesets/adnd1e/decision-implementations"

    def setUp(self):
        super().setUp()
        self.subject_path = (
            f"rulesets/adnd1e/escalations/decisions/{self.SUBJECT}.yaml"
        )
        # Deliberately not approved. The record pins this Decision by ID and
        # checksum and requires the successor Review to name the same one; its
        # lifecycle state is no part of the rule. Leaving it approved would add
        # a BUILDER-DECISION item to every scan in this case and break the
        # shared fixtures' own tests, which this class inherits.
        self.write_yaml(self.subject_path, {
            "id": self.SUBJECT, "status": "proposed", "ruleset_id": "adnd1e",
            "book_id": "phb", "migration_required": False,
            "acceptance_tests": ["only criterion"],
            "handoff": {"next_role": "builder", "readiness": "ready",
                        "reason": "implement", "blocking_ids": []},
        })
        self.report_id = f"IMP-{self.SUBJECT}-r01"
        self.report_path = f"{self.REPORTS}/{self.report_id}.yaml"
        self.write_yaml(self.report_path, {
            "schema_version": "1.0", "id": self.report_id,
            "artifact_kind": "decision_implementation", "status": "proposed",
            "ruleset_id": "adnd1e", "constitution_version": "1.8",
            "revision": 1, "supersedes": None, "approval_ready": True,
            "implemented_by": "builder",
            "decision_input": {"id": self.SUBJECT, "path": self.subject_path,
                               "checksum": self.sha256(self.subject_path)},
            "implementation_files": [],
            "acceptance_results": [{"acceptance_test_index": 1,
                                    "result": "passed", "evidence": "fixture"}],
            "validation": {"passed": True, "commands": [{
                "command": "[cwd tooling/common] python -m unittest discover",
                "exit_code": 0, "result": "passed", "summary": "Ran 1 test OK"}]},
            "handoff": {"next_role": "reviewer", "readiness": "ready",
                        "reason": "implemented", "blocking_ids": []},
        })

    def sha256(self, relative):
        return scanner._sha256_of(self.root / relative)

    def write_review(self, revision, *, supersedes=None,
                     disposition="revision_required", reviewed=None,
                     decision=None):
        artifact_id = f"REV-{self.report_id}-r{revision:02d}"
        self.write_yaml(f"{self.STORE}/{artifact_id}.yaml", {
            "schema_version": "1.0", "id": artifact_id,
            "artifact_kind": "decision_implementation_review",
            "status": disposition, "ruleset_id": "adnd1e",
            "constitution_version": "1.8", "revision": revision,
            "supersedes": supersedes, "reviewed_by": "reviewer",
            "reviewed_implementation": {
                "id": reviewed or self.report_id,
                "path": self.report_path if not reviewed else self.report_path,
                "checksum": self.sha256(self.report_path),
            },
            "decision_input": {
                "id": decision or self.SUBJECT, "path": self.subject_path,
                "checksum": self.sha256(self.subject_path),
            },
            "acceptance_dispositions": [{
                "acceptance_test_index": 1,
                "disposition": "verified" if disposition == "approved" else "failed",
                "evidence": "fixture",
            }],
            "independent_validation": {
                "passed": disposition == "approved",
                "commands": [{
                    "command": "[cwd tooling/common] python -m unittest discover",
                    "exit_code": 0 if disposition == "approved" else 1,
                    "result": "passed" if disposition == "approved" else "failed",
                    "summary": "Ran 1 test OK" if disposition == "approved"
                               else "Ran 1 test FAILED (failures=1)",
                }],
            },
            "overall_disposition": disposition,
            "handoff": {
                "next_role": "none" if disposition == "approved" else "builder",
                "readiness": "terminal" if disposition == "approved" else "ready",
                "reason": "reviewed", "blocking_ids": [],
            },
        })
        return artifact_id

    def write_unreadable(self, revision):
        artifact_id = f"REV-{self.report_id}-r{revision:02d}"
        path = self.root / self.STORE / f"{artifact_id}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"id: {artifact_id}\nnote: broken\n"
            "evidence: the record says: this and that\n",
            encoding="utf-8",
        )
        return artifact_id

    def lineage(self):
        unreadable = self.write_unreadable(1)
        successor = self.write_review(2, supersedes=unreadable)
        return unreadable, successor

    def pinned(self, artifact_id, directory, **extra):
        relative = f"{directory}/{artifact_id}.yaml"
        block = {"id": artifact_id, "path": relative,
                 "checksum": self.sha256(relative)}
        block.update(extra)
        return block

    def record(self, unreadable, successor, *, status="approved", **overrides):
        entry = {
            "disposition": "historical_unreadable_direct_predecessor",
            "reason": "fixture unreadable implementation Review",
            "unreadable_review": self.pinned(
                unreadable, self.STORE,
                parse_failure={"diagnostic_code": "yaml_unreadable",
                               "message_fragment": "mapping values are not allowed here"},
            ),
            "successor_review": self.pinned(
                successor, self.STORE,
                required_supersedes=unreadable,
                required_disposition="revision_required",
            ),
            "reviewed_implementation": {
                "id": self.report_id, "path": self.report_path,
                "checksum": self.sha256(self.report_path),
            },
            "decision_input": {
                "id": self.SUBJECT, "path": self.subject_path,
                "checksum": self.sha256(self.subject_path),
            },
        }
        entry.update(overrides)
        self.write_yaml(
            f"rulesets/adnd1e/escalations/decisions/{self.DECISION}.yaml",
            {
                "id": self.DECISION, "status": status, "ruleset_id": "adnd1e",
                "book_id": "phb", "migration_required": False,
                "handoff": {"next_role": "none", "readiness": "terminal",
                            "reason": "repaired", "blocking_ids": []},
                "decision_implementation_review_unreadable_predecessor_repairs": [entry],
            },
        )
        return entry

    def codes(self, result):
        return [item["Code"] for item in result["Diagnostics"]]

    # -- without a record -----------------------------------------------------

    def test_without_a_record_it_is_an_error(self):
        self.lineage()
        self.assertIn("yaml_unreadable", self.codes(self.scan()))

    # -- with a valid record --------------------------------------------------

    def test_a_complete_record_reports_one_informational_finding(self):
        unreadable, successor = self.lineage()
        self.record(unreadable, successor)
        found = [
            d for d in self.scan()["Diagnostics"]
            if d["Code"] == "implementation_review_unreadable_predecessor_repaired"
        ]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["ArtifactId"], unreadable)
        self.assertEqual(found[0]["Severity"], "info")

    def test_the_parse_error_is_gone(self):
        unreadable, successor = self.lineage()
        self.record(unreadable, successor)
        self.assertNotIn("yaml_unreadable", self.codes(self.scan()))

    def test_the_repaired_predecessor_routes_no_work_of_its_own(self):
        """It is history, not an artifact anyone acts on.

        The classification says why the file is skipped and stops there: it
        approves nothing, requests nothing, and appears in nobody's queue.
        """
        unreadable, successor = self.lineage()
        self.record(unreadable, successor)
        result = self.scan()
        assigned = {i["InputId"] for i in result["Items"]}
        self.assertNotIn(unreadable, assigned)
        for item in result["Items"]:
            with self.subTest(item=item["InputId"]):
                self.assertNotIn(unreadable, " ".join(item["Components"]))

    # -- denial cases ---------------------------------------------------------

    def assert_denied(self, result):
        codes = self.codes(result)
        self.assertIn("implementation_review_repair_record_invalid", codes)
        self.assertNotIn(
            "implementation_review_unreadable_predecessor_repaired", codes
        )
        self.assertIn("yaml_unreadable", codes)

    def test_an_inactive_decision_repairs_nothing(self):
        unreadable, successor = self.lineage()
        self.record(unreadable, successor, status="proposed")
        codes = self.codes(self.scan())
        self.assertIn("yaml_unreadable", codes)
        self.assertNotIn(
            "implementation_review_unreadable_predecessor_repaired", codes
        )

    def test_a_stale_checksum_on_any_pinned_artifact_denies_it(self):
        for field in ("unreadable_review", "successor_review",
                      "reviewed_implementation", "decision_input"):
            with self.subTest(field=field):
                self.setUp()
                unreadable, successor = self.lineage()
                entry = self.record(unreadable, successor)
                block = dict(entry[field])
                block["checksum"] = "sha256:" + "0" * 64
                self.record(unreadable, successor, **{field: block})
                self.assert_denied(self.scan())

    def test_a_parseable_predecessor_denies_it(self):
        unreadable = self.write_review(1)
        successor = self.write_review(2, supersedes=unreadable)
        self.record(unreadable, successor)
        codes = self.codes(self.scan())
        self.assertIn("implementation_review_repair_record_invalid", codes)
        self.assertNotIn(
            "implementation_review_unreadable_predecessor_repaired", codes
        )

    def test_a_wrong_parse_fragment_denies_it(self):
        unreadable, successor = self.lineage()
        entry = self.record(unreadable, successor)
        block = dict(entry["unreadable_review"])
        block["parse_failure"] = {"diagnostic_code": "yaml_unreadable",
                                  "message_fragment": "found undefined alias"}
        self.record(unreadable, successor, unreadable_review=block)
        self.assert_denied(self.scan())

    def test_a_broken_supersedes_link_denies_it(self):
        unreadable = self.write_unreadable(1)
        successor = self.write_review(2, supersedes=None)
        self.record(unreadable, successor)
        self.assert_denied(self.scan())

    def test_a_wrong_disposition_on_the_successor_denies_it(self):
        unreadable = self.write_unreadable(1)
        successor = self.write_review(2, supersedes=unreadable,
                                      disposition="approved")
        self.record(unreadable, successor)
        self.assert_denied(self.scan())

    def test_a_successor_reviewing_another_report_denies_it(self):
        """The one thing an unreadable predecessor cannot contradict."""
        unreadable = self.write_unreadable(1)
        successor = self.write_review(2, supersedes=unreadable,
                                      reviewed="IMP-DEC-2026-9999-r01")
        self.record(unreadable, successor)
        self.assert_denied(self.scan())

    def test_a_successor_under_another_decision_denies_it(self):
        unreadable = self.write_unreadable(1)
        successor = self.write_review(2, supersedes=unreadable,
                                      decision="DEC-2026-9999")
        self.record(unreadable, successor)
        self.assert_denied(self.scan())

    def test_a_schema_invalid_successor_denies_it(self):
        unreadable, successor = self.lineage()
        path = self.root / self.STORE / f"{successor}.yaml"
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document.pop("constitution_version")
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        self.record(unreadable, successor)
        self.assert_denied(self.scan())

    def test_a_wrong_record_disposition_denies_it(self):
        unreadable, successor = self.lineage()
        self.record(unreadable, successor,
                    disposition="historical_unreadable_bridge")
        self.assert_denied(self.scan())

    def test_a_record_without_a_reason_denies_it(self):
        unreadable, successor = self.lineage()
        self.record(unreadable, successor, reason="")
        self.assert_denied(self.scan())

    def test_another_unreadable_implementation_review_is_untouched(self):
        unreadable, successor = self.lineage()
        self.record(unreadable, successor)
        other = self.root / self.STORE / "REV-IMP-DEC-2026-9998-r01-r01.yaml"
        other.write_text("id: x\nbroken: like: the other\n", encoding="utf-8")
        self.assertIn("yaml_unreadable", self.codes(self.scan()))


class LiveImplementationReviewRepairCase(unittest.TestCase):
    """DEC-2026-0072's single authorized instance, against the repository."""

    UNREADABLE = "REV-IMP-DEC-2026-0065-r01-r01"
    SUCCESSOR = "REV-IMP-DEC-2026-0065-r01-r02"

    @classmethod
    def setUpClass(cls):
        cls.result = scanner.scan_repository(REPO_ROOT)

    def test_the_predecessor_is_informational_history(self):
        found = [
            d["ArtifactId"] for d in self.result["Diagnostics"]
            if d["Code"] == "implementation_review_unreadable_predecessor_repaired"
        ]
        self.assertEqual(found, [self.UNREADABLE])

    def test_it_raises_no_parse_error(self):
        for diagnostic in self.result["Diagnostics"]:
            if diagnostic["Code"] != "yaml_unreadable":
                continue
            with self.subTest(path=diagnostic.get("Path")):
                self.assertNotIn(self.UNREADABLE, str(diagnostic.get("Path") or ""))

    def test_no_record_is_invalid(self):
        invalid = [
            d["Message"] for d in self.result["Diagnostics"]
            if d["Code"] == "implementation_review_repair_record_invalid"
        ]
        self.assertEqual(invalid, [])

    def test_the_successor_pins_the_same_report_and_decision(self):
        document = yaml.safe_load(
            (REPO_ROOT / "rulesets/adnd1e/decision-implementation-reviews"
             / f"{self.SUCCESSOR}.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(document["supersedes"], self.UNREADABLE)
        self.assertEqual(
            document["reviewed_implementation"]["id"], "IMP-DEC-2026-0065-r01"
        )
        self.assertEqual(document["decision_input"]["id"], "DEC-2026-0065")

    def test_three_repair_kinds_coexist_without_overlapping(self):
        """Each record admits its own file and no other.

        Three exceptions now exist across two shapes. What keeps them from
        becoming a general bypass is that each names one file by checksum, and
        no record's predicates can be satisfied by another's artifact.
        """
        repaired = {
            d["Code"]: d["ArtifactId"]
            for d in self.result["Diagnostics"]
            if d["Code"].endswith("_repaired")
        }
        self.assertEqual(
            repaired,
            {
                "review_malformed_lineage_repaired":
                    "GUR-PKT-UA-015-015-cavaliers-r02"
                    if "GUR" in repaired.get("review_malformed_lineage_repaired", "")
                    else "REV-GUP-PKT-PHB-054-064-druid-spells-r01-r04",
                "review_unreadable_direct_predecessor_repaired":
                    "REV-GUP-PKT-PHB-117-119-bards-r04-r02",
                "implementation_review_unreadable_predecessor_repaired":
                    self.UNREADABLE,
            },
        )


class RejectionRemediationRecordCase(QueueScannerCase):
    """DEC-2026-0073: one Review's rejection reference, under an unread name.

    `_rejection_remediated` reads `integration_rejection`, `rejection_input` and
    `rejected_by`. Bards r03 wrote `integration_rejection_input` -- a fourth
    spelling, in an immutable file -- so the scan kept asking the Reviewer to
    remediate a rejection r03 had already remediated and whose successor was
    sitting ready for the Integrator.

    Adding the spelling as a general alias would silently change how every
    published Review is read on the strength of one artifact's word choice. This
    admits that one Review's mapping, and only after the rejection it names, the
    bundle that rejection refused, the GUP under review, and both successors all
    check out.
    """

    PACKET = "PKT-PHB-001-002-fixture"
    DECISION = "DEC-2026-9701"
    REVIEWS = "books/adnd1e/phb/artifacts/reviews"
    APPROVED = "books/adnd1e/phb/artifacts/approved"
    REJECTION = "rulesets/adnd1e/reports/INT-29990202-001.rejected.json"

    def setUp(self):
        super().setUp()
        self.gur_id = self.gur(self.PACKET, 1)
        self.gup_id = self.gup(self.PACKET, 1, self.gur_id, approval_ready=True)
        self.gup_relative = f"books/adnd1e/phb/artifacts/gup/{self.gup_id}.yaml"

    def sha256(self, relative):
        return scanner._sha256_of(self.root / relative)

    def write_review(self, revision, *, supersedes=None, handoff_role="integrator",
                     readiness="ready", rejection_field=None, rejection_id=None):
        artifact_id = f"REV-{self.gup_id}-r{revision:02d}"
        document = {
            "schema_version": "1.0", "id": artifact_id, "artifact_kind": "review",
            "status": "approved", "ruleset_id": "adnd1e",
            "constitution_version": "1.8", "packet_id": self.PACKET,
            "revision": revision, "supersedes": supersedes,
            "reviewed_gup": {"id": self.gup_id},
            "overall_disposition": "approved",
            "approved_bundle_emitted": f"APPROVED-{self.gup_id}-r{revision:02d}",
            "handoff": {"next_role": handoff_role, "readiness": readiness,
                        "reason": "fixture", "blocking_ids": []},
        }
        if rejection_field:
            document[rejection_field] = {
                "id": rejection_id or "INT-29990202-001",
                "path": self.REJECTION,
                "checksum": self.sha256(self.REJECTION),
            }
        self.write_yaml(f"{self.REVIEWS}/{artifact_id}.yaml", document)
        return artifact_id

    def write_bundle(self, revision, *, supersedes=None, approves=None,
                     handoff_role="integrator", readiness="ready"):
        artifact_id = f"APPROVED-{self.gup_id}-r{revision:02d}"
        component = f"{self.APPROVED}/{artifact_id}.edges.csv"
        path = self.root / component
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("source_id,target_id\na,b\n", encoding="utf-8")
        self.write_yaml(f"{self.APPROVED}/{artifact_id}.yaml", {
            "schema_version": "1.0", "id": artifact_id,
            "artifact_kind": "packet_update", "status": "approved",
            "ruleset_id": "adnd1e", "constitution_version": "1.8",
            "packet_id": self.PACKET, "revision": revision,
            "supersedes": supersedes,
            "review_id": approves or f"REV-{self.gup_id}-r{revision:02d}",
            "approves": {
                "review_id": approves or f"REV-{self.gup_id}-r{revision:02d}",
                "gup_id": self.gup_id,
            },
            "components": [{"kind": "edges", "path": component,
                            "checksum": self.sha256(component)}],
            "handoff": {"next_role": handoff_role, "readiness": readiness,
                        "reason": "fixture", "blocking_ids": []},
        })
        return artifact_id

    def write_rejection(self, bundle_id, review_id, *, gup_id=None):
        path = self.root / self.REJECTION
        path.parent.mkdir(parents=True, exist_ok=True)
        manifest = f"{self.APPROVED}/{bundle_id}.yaml"
        path.write_text(json.dumps({
            "id": "INT-29990202-001", "ruleset_id": "adnd1e", "status": "rejected",
            "rejected_bundles": [{
                "bundle_id": bundle_id,
                "bundle_checksum": self.sha256(manifest),
                "review_id": review_id,
                "review_checksum": self.sha256(f"{self.REVIEWS}/{review_id}.yaml"),
                "gup_id": gup_id or self.gup_id,
                "gup_checksum": self.sha256(self.gup_relative),
                "packet_id": self.PACKET,
                "manifest_path": manifest,
                "blocking_failures": [{"check": "fixture", "detail": "fixture detail"}],
                "blocking_failure_count": 1, "advisory_failure_count": 0,
                "checks_evaluated": 1,
            }],
        }, indent=1) + "\n", encoding="utf-8")

    def lineage(self, *, field="integration_rejection_input"):
        """r01 rejected, r02 recording it under an unread name, r03 the successor."""
        first_review = self.write_review(1)
        first_bundle = self.write_bundle(1)
        self.write_rejection(first_bundle, first_review)
        recording = self.write_review(2, supersedes=first_review,
                                      rejection_field=field)
        self.write_bundle(2, supersedes=first_bundle, approves=recording)
        successor = self.write_review(3, supersedes=recording)
        successor_bundle = self.write_bundle(3, supersedes=f"APPROVED-{self.gup_id}-r02",
                                             approves=successor)
        return first_bundle, recording, successor, successor_bundle

    def pinned(self, artifact_id, directory, **extra):
        relative = f"{directory}/{artifact_id}.yaml"
        block = {"id": artifact_id, "path": relative,
                 "checksum": self.sha256(relative)}
        block.update(extra)
        return block

    def record(self, first_bundle, recording, successor, successor_bundle, *,
               status="approved", **overrides):
        entry = {
            "disposition": "historical_rejection_remediation",
            "reason": "fixture historical remediation",
            "rejection_recording_review": self.pinned(
                recording, self.REVIEWS,
                required_field="integration_rejection_input",
            ),
            "integration_rejection": {
                "id": "INT-29990202-001", "path": self.REJECTION,
                "checksum": self.sha256(self.REJECTION),
            },
            "rejected_bundle": self.pinned(first_bundle, self.APPROVED),
            "active_successor_review": self.pinned(
                successor, self.REVIEWS,
                required_supersedes=recording,
                required_handoff={"next_role": "integrator", "readiness": "ready"},
            ),
            "active_successor_bundle": self.pinned(
                successor_bundle, self.APPROVED,
                required_supersedes=f"APPROVED-{self.gup_id}-r02",
                required_review_id=successor,
                required_handoff={"next_role": "integrator", "readiness": "ready"},
            ),
            "reviewed_gup": {
                "id": self.gup_id, "path": self.gup_relative,
                "checksum": self.sha256(self.gup_relative),
            },
            "governing_decision": self.pinned(
                "DEC-2026-9702", "rulesets/adnd1e/escalations/decisions",
            ) if (self.root / "rulesets/adnd1e/escalations/decisions/DEC-2026-9702.yaml").is_file() else None,
        }
        entry.update(overrides)
        self.write_yaml(
            f"rulesets/adnd1e/escalations/decisions/{self.DECISION}.yaml",
            {
                "id": self.DECISION, "status": status, "ruleset_id": "adnd1e",
                "book_id": "phb", "migration_required": False,
                "handoff": {"next_role": "none", "readiness": "terminal",
                            "reason": "remediated", "blocking_ids": []},
                "integration_rejection_historical_remediations": [entry],
            },
        )
        return entry

    def governing(self):
        self.write_yaml(
            "rulesets/adnd1e/escalations/decisions/DEC-2026-9702.yaml",
            {"id": "DEC-2026-9702", "status": "proposed", "ruleset_id": "adnd1e",
             "book_id": "phb", "migration_required": False,
             "handoff": {"next_role": "none", "readiness": "terminal",
                         "reason": "governs", "blocking_ids": []}},
        )

    def codes(self, result):
        return [item["Code"] for item in result["Diagnostics"]]

    def queues(self, result):
        rows = []
        for key in ("Items", "InformationalItems"):
            rows.extend((i["Queue"], i["InputId"]) for i in result.get(key) or [])
        return rows

    def build(self, **kwargs):
        self.governing()
        args = self.lineage()
        self.record(*args, **kwargs)
        return args

    # -- without a record -----------------------------------------------------

    def test_without_a_record_the_reviewer_is_asked_to_remediate(self):
        """The negative case: an unread field really does leave work behind."""
        self.governing()
        first_bundle, *_ = self.lineage()
        queues = self.queues(self.scan())
        self.assertIn(("REVIEWER-INTEGRATION-REJECTION", first_bundle), queues)

    # -- with a valid record --------------------------------------------------

    def test_the_remedied_rejection_creates_no_reviewer_work(self):
        first_bundle, *_ = self.build()
        queues = self.queues(self.scan())
        self.assertNotIn(("REVIEWER-INTEGRATION-REJECTION", first_bundle), queues)
        self.assertIn(("INTEGRATOR-REJECTED", first_bundle), queues)

    def test_the_successor_bundle_keeps_its_integrator_work(self):
        """The other half of the ruling: the r04 path must survive."""
        *_, successor_bundle = self.build()
        queues = self.queues(self.scan())
        self.assertIn(("INTEGRATOR-APPROVED", successor_bundle), queues)

    def test_one_informational_finding_explains_it(self):
        _, recording, *_ = self.build()
        found = [
            d for d in self.scan()["Diagnostics"]
            if d["Code"] == "integration_rejection_remediation_recognised"
        ]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["ArtifactId"], recording)
        self.assertEqual(found[0]["Severity"], "info")

    def test_it_produces_no_error(self):
        self.build()
        self.assertEqual(
            [d for d in self.scan()["Diagnostics"] if d["Severity"] == "error"], []
        )

    # -- the alias that is not an alias ---------------------------------------

    def test_the_field_has_no_effect_for_an_unnamed_review(self):
        """AT3. Another Review writing the same key is simply not in the map.

        This is the whole reason the record names a Review instead of adding a
        spelling: one artifact's word choice must not change how every other
        published Review is read.
        """
        self.governing()
        first_review = self.write_review(1)
        first_bundle = self.write_bundle(1)
        self.write_rejection(first_bundle, first_review)
        recording = self.write_review(2, supersedes=first_review,
                                      rejection_field="integration_rejection_input")
        self.write_bundle(2, supersedes=first_bundle, approves=recording)
        successor = self.write_review(3, supersedes=recording)
        successor_bundle = self.write_bundle(
            3, supersedes=f"APPROVED-{self.gup_id}-r02", approves=successor)
        # A record for a *different* Review id than the one that carries the field.
        self.record(first_bundle, recording, successor, successor_bundle,
                    rejection_recording_review=self.pinned(
                        successor, self.REVIEWS,
                        required_field="integration_rejection_input"))
        queues = self.queues(self.scan())
        self.assertIn(("REVIEWER-INTEGRATION-REJECTION", first_bundle), queues)

    def test_the_recognised_keys_still_work(self):
        """The ordinary spellings are untouched by any of this."""
        for field in ("integration_rejection", "rejection_input", "rejected_by"):
            with self.subTest(field=field):
                self.setUp()
                self.governing()
                first_review = self.write_review(1)
                first_bundle = self.write_bundle(1)
                self.write_rejection(first_bundle, first_review)
                self.write_review(2, supersedes=first_review, rejection_field=field)
                queues = self.queues(self.scan())
                self.assertNotIn(
                    ("REVIEWER-INTEGRATION-REJECTION", first_bundle), queues
                )

    # -- denial cases ---------------------------------------------------------

    def assert_denied(self, result, first_bundle):
        codes = self.codes(result)
        self.assertIn("rejection_remediation_record_invalid", codes)
        self.assertNotIn("integration_rejection_remediation_recognised", codes)
        self.assertIn(
            ("REVIEWER-INTEGRATION-REJECTION", first_bundle), self.queues(result)
        )

    def test_an_inactive_decision_remedies_nothing(self):
        first_bundle, *_ = self.build(status="proposed")
        self.assertIn(
            ("REVIEWER-INTEGRATION-REJECTION", first_bundle), self.queues(self.scan())
        )

    def test_a_stale_checksum_on_any_pinned_artifact_denies_it(self):
        for field in ("rejection_recording_review", "integration_rejection",
                      "rejected_bundle", "active_successor_review",
                      "active_successor_bundle", "reviewed_gup"):
            with self.subTest(field=field):
                self.setUp()
                args = self.build()
                entry = self.record(*args)
                block = dict(entry[field])
                block["checksum"] = "sha256:" + "0" * 64
                self.record(*args, **{field: block})
                self.assert_denied(self.scan(), args[0])

    def test_a_wrong_required_field_denies_it(self):
        args = self.build()
        entry = self.record(*args)
        block = dict(entry["rejection_recording_review"])
        block["required_field"] = "rejected_by"
        self.record(*args, rejection_recording_review=block)
        self.assert_denied(self.scan(), args[0])

    def test_a_rejection_naming_another_bundle_denies_it(self):
        self.governing()
        first_review = self.write_review(1)
        first_bundle = self.write_bundle(1)
        # The rejection refuses a bundle the record does not name. Written before
        # the recording Review, which pins it by checksum.
        second_bundle = self.write_bundle(2, supersedes=first_bundle,
                                          approves=f"REV-{self.gup_id}-r02")
        self.write_rejection(second_bundle, first_review)
        recording = self.write_review(2, supersedes=first_review,
                                      rejection_field="integration_rejection_input")
        successor = self.write_review(3, supersedes=recording)
        successor_bundle = self.write_bundle(
            3, supersedes=second_bundle, approves=successor)
        self.record(first_bundle, recording, successor, successor_bundle)
        self.assertIn(
            "rejection_remediation_record_invalid", self.codes(self.scan())
        )

    def test_a_rejection_naming_another_gup_denies_it(self):
        args = self.build()
        self.write_rejection(args[0], f"REV-{self.gup_id}-r01",
                             gup_id="GUP-OTHER-r01")
        self.record(*args)
        self.assertIn(
            "rejection_remediation_record_invalid", self.codes(self.scan())
        )

    def test_a_wrong_successor_link_denies_it(self):
        args = self.build()
        entry = self.record(*args)
        block = dict(entry["active_successor_review"])
        block["required_supersedes"] = f"REV-{self.gup_id}-r01"
        self.record(*args, active_successor_review=block)
        self.assert_denied(self.scan(), args[0])

    def test_a_wrong_successor_handoff_denies_it(self):
        args = self.build()
        entry = self.record(*args)
        block = dict(entry["active_successor_review"])
        block["required_handoff"] = {"next_role": "reviewer", "readiness": "ready"}
        self.record(*args, active_successor_review=block)
        self.assert_denied(self.scan(), args[0])

    def test_a_bundle_approving_another_review_denies_it(self):
        args = self.build()
        entry = self.record(*args)
        block = dict(entry["active_successor_bundle"])
        block["required_review_id"] = f"REV-{self.gup_id}-r01"
        self.record(*args, active_successor_bundle=block)
        self.assert_denied(self.scan(), args[0])

    def test_a_wrong_disposition_denies_it(self):
        args = self.build()
        self.record(*args, disposition="historical_unreadable_bridge")
        self.assert_denied(self.scan(), args[0])

    def test_a_record_without_a_reason_denies_it(self):
        args = self.build()
        self.record(*args, reason="")
        self.assert_denied(self.scan(), args[0])


class LiveRejectionRemediationCase(unittest.TestCase):
    """DEC-2026-0073's single authorized instance, against the repository."""

    RECORDING = "REV-GUP-PKT-PHB-117-119-bards-r04-r03"
    REJECTED = "APPROVED-GUP-PKT-PHB-117-119-bards-r04-r01"
    SUCCESSOR_BUNDLE = "APPROVED-GUP-PKT-PHB-117-119-bards-r04-r04"

    @classmethod
    def setUpClass(cls):
        cls.result = scanner.scan_repository(REPO_ROOT)

    def queues(self):
        rows = []
        for key in ("Items", "InformationalItems"):
            rows.extend((i["Queue"], i["InputId"]) for i in self.result.get(key) or [])
        return rows

    def test_the_reviewer_is_no_longer_asked_to_remediate(self):
        self.assertNotIn(
            ("REVIEWER-INTEGRATION-REJECTION", self.REJECTED), self.queues()
        )

    def test_the_rejected_bundle_is_never_ready_work_again(self):
        """It is history either way -- informational while it waited, consumed now.

        This asserted the INTEGRATOR-REJECTED position, which held until the
        Integrator applied the successor and both bundles became consumed. What
        must stay true is that the rejected bundle is never re-offered as work.
        """
        queues = {input_id: queue for queue, input_id in self.queues()}
        self.assertIn(self.REJECTED, queues)
        self.assertNotEqual(queues[self.REJECTED], "INTEGRATOR-APPROVED")
        self.assertNotIn(
            ("REVIEWER-INTEGRATION-REJECTION", self.REJECTED), self.queues()
        )

    def test_the_r04_integrator_path_was_preserved_through_to_integration(self):
        """The ruling's second requirement, stated so completing it cannot break it.

        Asserting INTEGRATOR-APPROVED tied this to the window between the record
        landing and the Integrator acting. The durable claim is that the path
        survived: the successor bundle reached an integration record, which it
        could not have done had the handoff replacement kept deleting its item.
        """
        integrated = set()
        for path in (REPO_ROOT / "rulesets/adnd1e/manifests").glob("INT-*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            for bundle in record.get("approved_bundles") or []:
                if bundle.get("bundle_id"):
                    integrated.add(str(bundle["bundle_id"]))
        self.assertIn(self.SUCCESSOR_BUNDLE, integrated)

    def test_one_finding_names_the_recording_review(self):
        found = [
            d["ArtifactId"] for d in self.result["Diagnostics"]
            if d["Code"] == "integration_rejection_remediation_recognised"
        ]
        self.assertEqual(found, [self.RECORDING])

    def test_no_record_is_invalid(self):
        invalid = [
            d["Message"] for d in self.result["Diagnostics"]
            if d["Code"] == "rejection_remediation_record_invalid"
        ]
        self.assertEqual(invalid, [])

    def test_no_further_bards_review_was_published(self):
        """The ruling authorizes no r05; the repair is the record, not a successor."""
        base = REPO_ROOT / "books/adnd1e/phb/artifacts/reviews"
        self.assertFalse(
            (base / "REV-GUP-PKT-PHB-117-119-bards-r04-r05.yaml").is_file()
        )


class ReplacementConsumptionGateCase(DecisionImplementationCase):
    """DEC-2026-0074: replacement speaks only while the Decision still owes work.

    WORK_QUEUES 1.3 replacement is computed from a Decision's authored handoff.
    That handoff never changes, so the rule kept asserting it after the work was
    finished: DEC-2026-0068 sat in the Builder queue with its report approved and
    its Review terminal, and nothing could retire it.

    The ordinary Decision lifecycle already decides what happens next. This makes
    replacement consult the same answer rather than contradict it.
    """

    ESCALATION = "ESC-2026-01-01T00.00.00.000Z"

    def escalated_decision(self, *, next_role="builder", readiness="ready"):
        """A Decision whose escalation names an artifact that would route."""
        gur_id = self.gur("PKT-PHB-001-002-fixture", 1)
        gup_id = self.gup("PKT-PHB-001-002-fixture", 1, gur_id, approval_ready=True)
        review_id = f"REV-{gup_id}-r01"
        origin = f"books/adnd1e/phb/artifacts/reviews/{review_id}.yaml"
        self.write_yaml(origin, {
            "id": review_id, "packet_id": "PKT-PHB-001-002-fixture",
            "revision": 1, "supersedes": None,
            "reviewed_gup": {"id": gup_id},
            "overall_disposition": "revision_required",
            "row_decisions": [{
                "ref": "M001", "disposition": "approved_with_revision",
                "exact_corrections": {"aspect": "to-hit rolls"},
            }],
            "handoff": {"next_role": "builder", "readiness": "ready",
                        "reason": "fixture", "blocking_ids": []},
        })
        self.write_yaml(
            f"rulesets/adnd1e/escalations/decided/{self.ESCALATION}.yaml",
            {
                "id": self.ESCALATION, "status": "decided", "ruleset_id": "adnd1e",
                "originating_artifacts": {
                    "review": {"id": review_id, "path": origin},
                },
            },
        )
        relative = self.decision(next_role=next_role, readiness=readiness)
        path = self.root / relative
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["escalation_id"] = self.ESCALATION
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        return relative, review_id

    def decision_items(self, result):
        return [
            i for i in result["Items"] + (result.get("BlockedItems") or [])
            if i["InputId"] == self.DECISION
        ]

    def replaced(self, result):
        return [
            d["ArtifactId"] for d in result["Diagnostics"]
            if d["Code"] == "handoff_replaced_by_decision"
        ]

    # -- the gate ------------------------------------------------------------

    def test_a_consumed_decision_raises_no_item(self):
        """AT1. The Decision is complete; nothing about it is work."""
        relative, _ = self.escalated_decision()
        report_id = self.report(relative)
        self.implementation_review(report_id, relative)
        self.assertEqual(self.decision_items(self.scan()), [])

    def test_a_consumed_decision_still_suppresses_the_origin(self):
        """AT4. Suppression is untouched: the ruling really did supersede it."""
        relative, review_id = self.escalated_decision()
        report_id = self.report(relative)
        self.implementation_review(report_id, relative)
        result = self.scan()
        self.assertIn(review_id, self.replaced(result))
        self.assertNotIn(review_id, {i["InputId"] for i in result["Items"]})

    def test_an_approval_ready_report_yields_only_the_reviewer_job(self):
        """AT3. One job, owned by the Reviewer, with no Decision item beside it."""
        relative, _ = self.escalated_decision()
        report_id = self.report(relative)
        result = self.scan()
        self.assertEqual(self.decision_items(result), [])
        self.assertIn(
            ("Reviewer", report_id),
            {(i["Role"], i["InputId"]) for i in result["Items"]},
        )

    def test_a_revision_required_review_yields_only_the_owner_job(self):
        """AT3, the other half."""
        relative, _ = self.escalated_decision()
        report_id = self.report(relative)
        review_id = self.implementation_review(
            report_id, relative, disposition="revision_required"
        )
        result = self.scan()
        self.assertEqual(self.decision_items(result), [])
        self.assertIn(
            ("Builder", review_id),
            {(i["Role"], i["InputId"]) for i in result["Items"]},
        )

    # -- what must not change ------------------------------------------------

    def test_an_unconsumed_decision_still_raises_its_item(self):
        """AT2. The rule keeps doing its job where the work is outstanding."""
        relative, review_id = self.escalated_decision()
        result = self.scan()
        items = self.decision_items(result)
        self.assertEqual([i["Role"] for i in items], ["Builder"])
        self.assertIn(review_id, self.replaced(result))

    def test_a_blocked_decision_handoff_is_still_blocked_work(self):
        self.escalated_decision(readiness="blocked")
        items = self.decision_items(self.scan())
        self.assertEqual([i["State"] for i in items], ["blocked"])

    def test_the_origin_is_never_suppressed_without_the_exact_conditions(self):
        """AT4. No escalation link means no replacement, gate or no gate."""
        gur_id = self.gur("PKT-PHB-003-004-second", 1)
        gup_id = self.gup("PKT-PHB-003-004-second", 1, gur_id, approval_ready=True)
        review_id = f"REV-{gup_id}-r01"
        self.write_yaml(f"books/adnd1e/phb/artifacts/reviews/{review_id}.yaml", {
            "id": review_id, "packet_id": "PKT-PHB-003-004-second",
            "revision": 1, "supersedes": None,
            "reviewed_gup": {"id": gup_id},
            "overall_disposition": "revision_required",
            "row_decisions": [{
                "ref": "M001", "disposition": "approved_with_revision",
                "exact_corrections": {"aspect": "to-hit rolls"},
            }],
            "handoff": {"next_role": "builder", "readiness": "ready",
                        "reason": "fixture", "blocking_ids": []},
        })
        result = self.scan()
        self.assertNotIn(review_id, self.replaced(result))
        self.assertIn(review_id, {i["InputId"] for i in result["Items"]})

    def test_a_migration_decision_keeps_its_ordinary_route(self):
        """AT2. The migration path is a separate rule and is not double-counted."""
        relative, _ = self.escalated_decision()
        path = self.root / relative
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["migration_required"] = True
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        items = self.decision_items(self.scan())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["Role"], "Builder")


class LiveReplacementConsumptionGateCase(unittest.TestCase):
    """DEC-2026-0074 against the repository, on the Decision that caused it."""

    COMPLETED = "DEC-2026-0068"

    @classmethod
    def setUpClass(cls):
        cls.result = scanner.scan_repository(REPO_ROOT)

    def test_the_completed_decision_raises_no_item(self):
        assigned = {
            i["InputId"]
            for i in self.result["Items"] + (self.result.get("BlockedItems") or [])
        }
        self.assertNotIn(self.COMPLETED, assigned)

    def test_it_really_is_complete(self):
        """Guards the guard: absence must mean consumed, not merely missing."""
        review = yaml.safe_load(
            (REPO_ROOT / "rulesets/adnd1e/decision-implementation-reviews"
             / "REV-IMP-DEC-2026-0068-r03-r01.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(review["overall_disposition"], "approved")
        self.assertEqual(review["reviewed_implementation"]["id"], "IMP-DEC-2026-0068-r03")
        self.assertEqual(review["handoff"]["readiness"], "terminal")

    def test_no_decision_with_an_approved_implementation_is_queued(self):
        """The class, not the instance: this is what the gate is for."""
        store = REPO_ROOT / "rulesets/adnd1e/decision-implementation-reviews"
        consumed = set()
        for path in sorted(store.glob("REV-IMP-*.yaml")):
            try:
                document = yaml.safe_load(path.read_text(encoding="utf-8"))
            except yaml.YAMLError:
                continue
            if not isinstance(document, dict):
                continue
            if str(document.get("overall_disposition") or "") != "approved":
                continue
            reviewed = document.get("reviewed_implementation") or {}
            report = str(reviewed.get("id") or "")
            if report.startswith("IMP-"):
                consumed.add(report[len("IMP-"):].rsplit("-r", 1)[0])
        self.assertTrue(consumed)
        assigned = {
            i["InputId"]
            for i in self.result["Items"] + (self.result.get("BlockedItems") or [])
        }
        self.assertEqual(sorted(consumed & assigned), [])


class ApprovedBundleDerivationCase(QueueScannerCase):
    """DEC-2026-0095: declared Review, own active leaf, declared consumption.

    Three defects met on the Stats lineage. The scanner guessed the approving
    Review from the APPROVED- filename stem, so publishing an unrelated
    REV-...-r03 silently changed which Review a byte-identical bundle was
    validated against. It asked only whether the packaged GUP was superseded,
    never whether a later manifest replaced this one, so five manifests for one
    GUP were all offered. And it regex-harvested any APPROVED- substring from an
    Integration manifest, so a shared component path recorded a bundle nobody
    integrated as integrated.
    """

    PACKET = "PKT-PHB-001-002-fixture"
    APPROVED = "books/adnd1e/phb/artifacts/approved"

    def setUp(self):
        super().setUp()
        self.gur_id = self.gur(self.PACKET, 1)
        self.gup_id = self.gup(self.PACKET, 1, self.gur_id, approval_ready=True)

    def write_review(self, revision):
        return self.review(self.PACKET, self.gup_id, revision=revision)

    def write_bundle(self, revision, *, approves, supersedes=None,
                     declare_revision=True, review_checksum=None,
                     component=None, top_level_review_id=None):
        artifact_id = f"APPROVED-{self.gup_id}-r{revision:02d}"
        component = component or f"{self.APPROVED}/{artifact_id}.edges.csv"
        path = self.root / component
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("source_id,target_id\na,b\n", encoding="utf-8")
        approves_block = {"review_id": approves, "gup_id": self.gup_id}
        if review_checksum:
            approves_block["review_checksum"] = review_checksum
        document = {
            "schema_version": "1.0", "id": artifact_id,
            "artifact_kind": "packet_update", "status": "approved",
            "ruleset_id": "adnd1e", "packet_id": self.PACKET,
            "supersedes": supersedes,
            "approves": approves_block,
            "components": [{"kind": "edges", "path": component}],
        }
        if declare_revision:
            document["revision"] = revision
        if top_level_review_id:
            document["review_id"] = top_level_review_id
        self.write_yaml(f"{self.APPROVED}/{artifact_id}.yaml", document)
        return artifact_id

    def integrate(self, bundle_id, *, as_record=True, extra_strings=()):
        body = {
            "schema_version": "1.0",
            "id": f"INT-29990303-001-{bundle_id}",
            "integration_id": "INT-29990303-001",
            "status": "integrated",
            "ruleset_id": "adnd1e",
            "bundle_id": bundle_id,
            "components": list(extra_strings),
        }
        directory = (
            self.book / "artifacts" / "integrated" if as_record
            else self.root / "rulesets" / "adnd1e" / "manifests"
        )
        directory.mkdir(parents=True, exist_ok=True)
        name = (f"INT-29990303-001-{bundle_id}.json" if as_record
                else "INT-29990303-001.json")
        (directory / name).write_text(json.dumps(body), encoding="utf-8")

    def rows(self, result=None):
        result = result or self.scan()
        rows = {}
        for key in ("Items", "InformationalItems"):
            for item in result.get(key) or []:
                if item["InputId"].startswith("APPROVED-"):
                    rows[item["InputId"]] = (item["Queue"], item.get("LegacyInference"))
        return rows

    def codes(self, result=None):
        result = result or self.scan()
        return [d["Code"] for d in result["Diagnostics"]]

    # -- the declared Review is the only Review ------------------------------

    def test_a_declared_review_resolves_without_a_filename_match(self):
        review = self.write_review(1)
        bundle = self.write_bundle(7, approves=review)
        self.assertEqual(self.rows()[bundle][0], "INTEGRATOR-APPROVED")
        self.assertNotIn("approved_review_inferred_or_missing", self.codes())

    def test_a_conflicting_stem_cannot_select_another_review(self):
        """The Stats case exactly: the bundle declares r01, its stem says r03."""
        declared = self.write_review(1)
        self.write_review(3)
        bundle = self.write_bundle(3, approves=declared)
        self.assertEqual(self.rows()[bundle][0], "INTEGRATOR-APPROVED")
        self.assertNotIn("approved_review_inferred_or_missing", self.codes())

    def test_publishing_an_unrelated_review_does_not_move_a_bundle(self):
        """A byte-identical bundle must not change state because of another file."""
        declared = self.write_review(1)
        self.write_bundle(3, approves=declared)
        before = self.rows()
        self.write_review(3)
        self.assertEqual(self.rows(), before)

    def test_a_top_level_field_cannot_override_the_declared_review(self):
        declared = self.write_review(1)
        self.write_review(2)
        bundle = self.write_bundle(
            9, approves=declared,
            top_level_review_id=f"REV-{self.gup_id}-r02")
        self.assertEqual(self.rows()[bundle][0], "INTEGRATOR-APPROVED")

    def test_a_manifest_declaring_no_review_is_not_guessed_for(self):
        self.write_review(1)
        artifact_id = f"APPROVED-{self.gup_id}-r01"
        self.write_yaml(f"{self.APPROVED}/{artifact_id}.yaml", {
            "id": artifact_id, "packet_id": self.PACKET, "components": [],
        })
        self.assertNotIn(artifact_id, self.rows())
        self.assertIn("approved_review_inferred_or_missing", self.codes())

    def test_a_manifestless_bundle_keeps_its_filename_fallback(self):
        self.write_review(1)
        path = self.root / self.APPROVED / f"APPROVED-{self.gup_id}-r01.edges.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("source_id,target_id\na,b\n", encoding="utf-8")
        self.assertEqual(
            self.rows()[f"APPROVED-{self.gup_id}-r01"][0], "INTEGRATOR-APPROVED")

    def test_a_declared_review_checksum_must_match(self):
        review = self.write_review(1)
        bundle = self.write_bundle(
            1, approves=review, review_checksum="sha256:" + "0" * 64)
        self.assertNotIn(bundle, self.rows())
        self.assertIn("approved_review_checksum_mismatch", self.codes())

    def test_a_correct_declared_review_checksum_is_accepted(self):
        review = self.write_review(1)
        checksum = scanner._sha256_of(
            self.root / f"books/adnd1e/phb/artifacts/reviews/{review}.yaml")
        bundle = self.write_bundle(1, approves=review, review_checksum=checksum)
        self.assertEqual(self.rows()[bundle][0], "INTEGRATOR-APPROVED")

    def test_a_superseded_manifests_stale_checksum_is_not_a_lineage_error(self):
        """The exact live case: a corrective successor makes a predecessor's
        pinned checksum stale, and the predecessor is already retired history.

        This first implementation validated the checksum before resolving
        manifest supersession, so publishing APPROVED-...-r03 with the correct
        checksum -- to fix APPROVED-...-r02's own stale pin -- made the
        superseded r02 a fatal repo-wide lineage error, exit code 2, on an
        artifact nothing live depends on.
        """
        review = self.write_review(1)
        first = self.write_bundle(
            1, approves=review, review_checksum="sha256:" + "0" * 64)
        second = self.write_bundle(2, approves=review, supersedes=first)
        result = self.scan()
        rows = self.rows(result)
        self.assertEqual(rows[first][0], "INTEGRATOR-SUPERSEDED")
        self.assertEqual(rows[second][0], "INTEGRATOR-APPROVED")
        errors = [d for d in result["Diagnostics"] if d["Severity"] == "error"]
        self.assertEqual(errors, [])

    def test_a_live_leafs_bad_checksum_is_still_an_error(self):
        """The narrowing must not swallow a real defect on live work."""
        review = self.write_review(1)
        bundle = self.write_bundle(
            1, approves=review, review_checksum="sha256:" + "0" * 64)
        result = self.scan()
        self.assertNotIn(bundle, self.rows(result))
        errors = [d for d in result["Diagnostics"] if d["Severity"] == "error"]
        self.assertTrue(
            any(d["Code"] == "approved_review_checksum_mismatch" for d in errors))

    # -- the manifest's own active leaf ---------------------------------------

    def test_an_explicit_chain_leaves_one_active_manifest(self):
        review = self.write_review(1)
        first = self.write_bundle(1, approves=review)
        second = self.write_bundle(2, approves=review, supersedes=first)
        rows = self.rows()
        self.assertEqual(rows[first][0], "INTEGRATOR-SUPERSEDED")
        self.assertEqual(rows[second][0], "INTEGRATOR-APPROVED")

    def test_a_legacy_member_without_revision_metadata_is_placed_by_rnn(self):
        """The Stats shape: r01 declares neither revision nor supersedes."""
        review = self.write_review(1)
        first = self.write_bundle(1, approves=review, declare_revision=False)
        second = self.write_bundle(2, approves=review, declare_revision=False)
        third = self.write_bundle(3, approves=review, supersedes=second)
        rows = self.rows()
        self.assertEqual(rows[first][0], "INTEGRATOR-SUPERSEDED")
        self.assertEqual(rows[second][0], "INTEGRATOR-SUPERSEDED")
        self.assertEqual(rows[third][0], "INTEGRATOR-APPROVED")
        self.assertTrue(rows[first][1], "the inferred placement is reported")
        self.assertIn("legacy_revision_inference", self.codes())

    def test_a_single_manifest_lineage_is_untouched(self):
        review = self.write_review(1)
        only = self.write_bundle(1, approves=review)
        self.assertEqual(self.rows()[only][0], "INTEGRATOR-APPROVED")
        self.assertNotIn("legacy_revision_inference", self.codes())

    def test_a_fork_whose_members_all_declare_revisions_is_left_alone(self):
        """Clause 2 covers a legacy omission, not a declared fork. Inferring a
        leaf here would retire a bundle on the strength of its filename."""
        review = self.write_review(1)
        first = self.write_bundle(1, approves=review)
        second = self.write_bundle(2, approves=review)
        rows = self.rows()
        self.assertEqual(rows[first][0], "INTEGRATOR-APPROVED")
        self.assertEqual(rows[second][0], "INTEGRATOR-APPROVED")
        self.assertNotIn("legacy_revision_inference", self.codes())

    def test_modification_time_never_places_a_manifest(self):
        review = self.write_review(1)
        first = self.write_bundle(1, approves=review, declare_revision=False)
        second = self.write_bundle(2, approves=review, declare_revision=False)
        third = self.write_bundle(3, approves=review, supersedes=second)
        os.utime(self.root / self.APPROVED / f"{first}.yaml",
                 (2 ** 31 - 1, 2 ** 31 - 1))
        rows = self.rows()
        self.assertEqual(rows[first][0], "INTEGRATOR-SUPERSEDED")
        self.assertEqual(rows[third][0], "INTEGRATOR-APPROVED")

    # -- integration consumption is declared, never inferred -------------------

    def test_a_component_path_does_not_consume_another_bundle(self):
        """The Stats case: every manifest declares the same shared edges CSV,
        stem-named after r05-r01, and integrating r05-r05 marked r01 consumed."""
        review = self.write_review(1)
        shared = f"{self.APPROVED}/APPROVED-{self.gup_id}-r01.edges.csv"
        first = self.write_bundle(1, approves=review, component=shared)
        second = self.write_bundle(2, approves=review, supersedes=first,
                                   component=shared)
        self.integrate(second, extra_strings=[shared])
        rows = self.rows()
        self.assertEqual(rows[second][0], "INTEGRATOR-CONSUMED")
        self.assertEqual(rows[first][0], "INTEGRATOR-SUPERSEDED")

    def test_an_int_prefixed_record_is_recognised(self):
        review = self.write_review(1)
        bundle = self.write_bundle(1, approves=review)
        self.integrate(bundle, as_record=True)
        self.assertEqual(self.rows()[bundle][0], "INTEGRATOR-CONSUMED")

    def test_an_integration_manifest_is_recognised(self):
        review = self.write_review(1)
        bundle = self.write_bundle(1, approves=review)
        self.integrate(bundle, as_record=False)
        self.assertEqual(self.rows()[bundle][0], "INTEGRATOR-CONSUMED")

    def test_a_non_integrated_record_consumes_nothing(self):
        review = self.write_review(1)
        bundle = self.write_bundle(1, approves=review)
        directory = self.book / "artifacts" / "integrated"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "INT-29990303-002-rejected.json").write_text(
            json.dumps({"id": "INT-29990303-002", "status": "rejected",
                        "ruleset_id": "adnd1e", "bundle_id": bundle}),
            encoding="utf-8")
        self.assertEqual(self.rows()[bundle][0], "INTEGRATOR-APPROVED")


class LiveStatsApprovedLineageCase(unittest.TestCase):
    """DEC-2026-0095 acceptance tests 3 and 4, on the exact named artifacts."""

    LINEAGE = "APPROVED-GUP-PKT-SD-015-015-stats-and-stat-modifiers-r05-r0"

    @classmethod
    def setUpClass(cls):
        directory = (REPO_ROOT / "books" / "shadowdark" / "sd" / "artifacts"
                     / "approved")
        if not (directory / f"{cls.LINEAGE}5.yaml").is_file():  # pragma: no cover
            raise unittest.SkipTest("the Stats r05 lineage is no longer present")
        cls.result = scanner.scan_repository(REPO_ROOT)
        cls.rows = {}
        for key in ("Items", "InformationalItems", "BlockedItems"):
            for item in cls.result.get(key) or []:
                cls.rows[item["InputId"]] = item

    def test_only_r05_is_consumed(self):
        self.assertEqual(
            self.rows[f"{self.LINEAGE}5"]["Queue"], "INTEGRATOR-CONSUMED")

    def test_the_shared_r01_component_did_not_consume_r01(self):
        self.assertNotEqual(
            self.rows[f"{self.LINEAGE}1"]["Queue"], "INTEGRATOR-CONSUMED")

    def test_no_stats_manifest_is_a_ready_integrator_item(self):
        ready = [i["InputId"] for i in self.result["Items"]
                 if i["InputId"].startswith(self.LINEAGE)]
        self.assertEqual(ready, [])

    def test_r01_through_r04_are_informational_history(self):
        for suffix in ("1", "2", "3", "4"):
            with self.subTest(manifest=f"{self.LINEAGE}{suffix}"):
                self.assertEqual(
                    self.rows[f"{self.LINEAGE}{suffix}"]["State"], "informational")

    def test_the_legacy_placement_of_r01_is_reported(self):
        self.assertTrue(self.rows[f"{self.LINEAGE}1"]["LegacyInference"])
        codes = [(d["Code"], d.get("ArtifactId")) for d in self.result["Diagnostics"]]
        self.assertIn(("legacy_revision_inference", f"{self.LINEAGE}5"), codes)

    def test_the_r04_rejection_creates_no_reviewer_work(self):
        remediation = [i for i in self.result["Items"]
                       if i["Queue"] == "REVIEWER-INTEGRATION-REJECTION"]
        self.assertEqual(remediation, [])

    def test_no_stats_manifest_raises_a_review_linkage_warning(self):
        for diagnostic in self.result["Diagnostics"]:
            if str(diagnostic.get("ArtifactId") or "").startswith(self.LINEAGE):
                self.assertNotEqual(
                    diagnostic["Code"], "approved_review_inferred_or_missing")
