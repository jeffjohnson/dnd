"""Batched interface guards; no real notifications or live publication."""
from argparse import Namespace
import copy
import json
import shutil
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tooling/common"))
import agent_task as task
from artifact_io import PublicationError, digest, yaml_bytes


class AgentTaskCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.args = Namespace(role="analyst", ruleset="shadowdark", book="sd", session_id="session-a",
                              context_read=None, review=None, prepared=None, inspect=False, claim_manifest=None)
        self.input = self.root / "input.yaml"
        self.document = {"id": "GUR-PKT-SD-001-001-fixture-r01", "ruleset_id": "shadowdark", "book_id": "sd",
                         "packet_id": "PKT-SD-001-001-fixture", "handoff": {"next_role": "builder", "readiness": "ready"}}
        self.input.write_bytes(yaml_bytes(self.document))
        self.queue = {"LineageErrorCount": 0, "Items": [{"Role": "Analyst", "Ruleset": "shadowdark", "Book": "sd",
                      "InputId": self.document["id"], "Path": "input.yaml", "PacketId": self.document["packet_id"]}],
                      "ActiveItems": [], "BlockedItems": [], "Diagnostics": []}

    def snapshot(self, **changes):
        payload = {"role": "analyst", "ruleset": "shadowdark", "book": "sd", "session_id": "session-a",
                   "input": "input.yaml", "input_checksums": {"input.yaml": digest(self.input.read_bytes())}}
        payload.update(changes)
        self.args.prepared = self.root / "prepared.json"
        self.args.prepared.write_text(json.dumps(payload), encoding="utf-8")

    def test_prepared_same_session_unchanged_hits(self):
        self.snapshot()
        self.assertIn("input.yaml", task.prepared_inputs(self.root, self.args, self.input))

    def test_prepared_different_role_scope_session_or_input_refuses(self):
        for field, value in (("role", "reviewer"), ("ruleset", "adnd1e"), ("book", "cs1"),
                             ("session_id", "another"), ("input", "different.yaml")):
            with self.subTest(field=field):
                self.snapshot(**{field: value})
                with self.assertRaisesRegex(PublicationError, "mismatch"):
                    task.prepared_inputs(self.root, self.args, self.input)

    def test_prepared_stale_input_refuses(self):
        self.snapshot()
        self.input.write_bytes(b"different")
        with self.assertRaisesRegex(PublicationError, "changed or disappeared"):
            task.prepared_inputs(self.root, self.args, self.input)

    def test_missing_preparation_refuses(self):
        with self.assertRaisesRegex(PublicationError, "requires --prepared"):
            task.prepared_inputs(self.root, self.args, self.input)

    def test_conflicting_observations_never_replace_an_earlier_checksum(self):
        expected = {"source.md": "sha256:old"}
        with self.assertRaisesRegex(PublicationError, "changed during"):
            task.merge_pins(expected, {"source.md": "sha256:new"})
        self.assertEqual(expected, {"source.md": "sha256:old"})

    def test_context_miss_emits_full_content_without_issuing_receipt(self):
        authority = self.root / "authority.md"
        authority.write_text("complete authority\n" * 200, encoding="utf-8")
        with patch.object(task.role_context, "verify", return_value={"status": "cache_miss", "stable_authority_paths": ["authority.md"]}), \
             patch.object(task.role_context, "build_receipt", return_value={"session": "a"}), \
             patch.object(task.role_context, "record") as record:
            result = task.context(self.root, self.args)
        self.assertEqual(result["documents"][0]["content"], authority.read_bytes().decode())
        record.assert_not_called()

    def test_context_attestation_binds_exact_current_receipt(self):
        receipt = {"session": "session-a", "checksum": "current"}
        self.args.context_read = digest(json.dumps(receipt, sort_keys=True).encode())
        with patch.object(task.role_context, "verify", return_value={"status": "cache_miss"}), \
             patch.object(task.role_context, "build_receipt", return_value=receipt), \
             patch.object(task.role_context, "record") as record:
            self.assertIsNone(task.context(self.root, self.args))
            record.assert_called_once()
            self.args.context_read = "stale"
            with self.assertRaisesRegex(PublicationError, "attestation"):
                task.context(self.root, self.args)

    def test_context_hit_does_not_reload_authorities(self):
        with patch.object(task.role_context, "verify", return_value={"status": "cache_hit"}), \
             patch.object(task.role_context, "build_receipt", return_value={}), \
             patch.object(task, "document_record") as reader:
            self.assertIsNone(task.context(self.root, self.args))
        reader.assert_not_called()

    def test_ready_assignment_exact_role_scope_and_input(self):
        task.require_assignment(self.root, self.args, self.input, self.document, self.queue)
        for role in ("builder", "reviewer", "integrator"):
            self.args.role = role
            with self.assertRaisesRegex(PublicationError, "not a current"):
                task.require_assignment(self.root, self.args, self.input, self.document, self.queue)

    def test_blocked_or_terminal_input_cannot_advance(self):
        for state in ("blocked", "terminal"):
            self.document["handoff"]["readiness"] = state
            with self.assertRaisesRegex(PublicationError, "blocked/terminal"):
                task.require_assignment(self.root, self.args, self.input, self.document, self.queue)

    def test_escalation_pauses_normal_packet(self):
        self.queue["Items"].append({"Role": "Architect", "Queue": "ARCHITECT-ESC", "PacketId": self.document["packet_id"], "InputId": "ESC-fixture"})
        with self.assertRaisesRegex(PublicationError, "packet paused"):
            task.require_assignment(self.root, self.args, self.input, self.document, self.queue)

    def test_lineage_errors_do_not_deadlock_architect_escalation(self):
        self.queue["LineageErrorCount"] = 1
        with self.assertRaisesRegex(PublicationError, "lineage errors"):
            task.require_assignment(self.root, self.args, self.input, self.document, self.queue)
        self.args.role = "architect"
        self.document["id"] = "ESC-fixture"
        self.queue["Items"][0].update(Role="Architect", InputId="ESC-fixture")
        task.require_assignment(self.root, self.args, self.input, self.document, self.queue)

    def test_illegal_notification_route_never_invokes_transport(self):
        with patch.object(task.subprocess, "run") as run:
            with self.assertRaisesRegex(PublicationError, "not permitted"):
                task.notify(self.root, "builder", "integrator", "work")
        run.assert_not_called()

    def test_notification_uses_only_supported_wrapper_without_profile(self):
        with patch.object(task.subprocess, "run") as run:
            run.return_value = Namespace(returncode=0, stdout="sent", stderr="")
            result = task.notify(self.root, "integrator", "analyst", "next packet")
        command = run.call_args.args[0]
        self.assertIn("-NoProfile", command)
        self.assertIn(str(self.root / "tooling/common/Send-HerdrPrompt.ps1"), command)
        self.assertIn("Analyst", command)
        self.assertEqual(result["status"], "submitted")

    def test_unchanged_malformed_unrelated_history_does_not_block_lineage_preflight(self):
        path = self.root / "GUR-PKT-fixture-r02.yaml"
        prior = {"id": "GUR-PKT-fixture-r01", "revision": 1, "supersedes": None, "ruleset_id": "shadowdark"}
        (self.root / f"{prior['id']}.yaml").write_bytes(yaml_bytes(prior))
        (self.root / "unrelated.yaml").write_text("x: [", encoding="utf-8")
        document = dict(prior, id=path.stem, revision=2, supersedes=prior["id"])
        task.validate_lineage(self.root, path, document)
        (self.root / "GUR-PKT-fixture-r03.yaml").write_bytes(yaml_bytes(dict(document, id="GUR-PKT-fixture-r03", revision=3)))
        with self.assertRaisesRegex(PublicationError, "already has successor"):
            task.validate_lineage(self.root, path, document)

    def test_second_lineage_root_refuses(self):
        path = self.root / "GUR-fixture-r01.yaml"
        path.write_bytes(b"existing")
        with self.assertRaisesRegex(PublicationError, "fork"):
            task.validate_lineage(self.root, path, {"id": path.stem, "revision": 1, "supersedes": None})

    def test_input_collection_handles_json_arrays_without_guessing(self):
        values = self.root / "slice.json"
        values.write_text('[{"source_id":"node_a"}]', encoding="utf-8")
        self.input.write_bytes(yaml_bytes({"supplied": {"path": "slice.json", "checksum": digest(values.read_bytes())}}))
        result = task.collect_inputs(self.root, self.input, "shadowdark", "sd")
        self.assertEqual(set(result["input_checksums"]), {"input.yaml", "slice.json"})

    def test_input_collection_refuses_stale_or_escaping_provenance(self):
        for path in ("input.yaml", "../outside.yaml"):
            self.input.write_bytes(yaml_bytes({"pin": {"path": path, "checksum": "sha256:" + "0" * 64}}))
            with self.assertRaises(PublicationError):
                task.collect_inputs(self.root, self.input, "shadowdark", "sd")

    def test_analyst_cannot_publish_builder_artifacts(self):
        staged = self.root / "output.yaml"
        staged.write_bytes(yaml_bytes(dict(self.document, id="GUP-PKT-fixture-r01")))
        with self.assertRaisesRegex(PublicationError, "cannot publish"):
            task.authored_plan(self.root, self.args, staged, self.document)

    def publication_fixture(self):
        shutil.copytree(ROOT / "schemas", self.root / "schemas")
        self.document.update(schema_version="1.0", source_id="sd-steward-intake", constitution_version="1.8",
                             revision=1, supersedes=None, status="proposed", candidate_nodes=[], candidate_edges=[])
        self.document["handoff"].update(reason="fixture authored extraction", blocking_ids=[])
        self.input.write_bytes(yaml_bytes(self.document))
        self.snapshot()
        self.args.input = self.input
        self.args.staged = self.root / "staged.yaml"
        self.args.staged.write_bytes(yaml_bytes(self.document))
        self.args.preview = False
        self.args.notify = False
        return self.root / f"books/shadowdark/sd/artifacts/gur/{self.document['id']}.yaml"

    def test_finish_validates_and_publishes_authored_gur_create_only(self):
        target = self.publication_fixture()
        with patch.object(task, "queue", return_value=(self.queue, {})):
            result = task.finish(self.root, self.args)
            self.assertEqual(result["outcome"], "published")
            self.assertEqual(result["next_role"], "builder")
            self.assertEqual(target.read_bytes(), self.args.staged.read_bytes())
            with self.assertRaisesRegex(PublicationError, "fork"):
                task.finish(self.root, self.args)

    def test_finish_preview_validates_without_outputs_or_notification(self):
        target = self.publication_fixture()
        self.args.preview = True
        self.args.notify = True
        with patch.object(task, "queue", return_value=(self.queue, {})), patch.object(task, "notify") as notify:
            result = task.finish(self.root, self.args)
        self.assertEqual(result["outcome"], "validated_preview")
        self.assertFalse(target.exists())
        notify.assert_not_called()

    def test_finish_schema_failure_leaves_no_outputs(self):
        target = self.publication_fixture()
        self.document["candidate_nodes"] = [{"proposed_id": "monster_test", "label": "not the governed field"}]
        self.args.staged.write_bytes(yaml_bytes(self.document))
        with patch.object(task, "queue", return_value=(self.queue, {})), self.assertRaisesRegex(PublicationError, "staged validation"):
            task.finish(self.root, self.args)
        self.assertFalse(target.exists())

    def test_registry_label_matches_use_the_existing_normalizer(self):
        path = self.root / "rulesets/shadowdark/registries/nodes.csv"
        path.parent.mkdir(parents=True)
        path.write_text("id,label,kind,degree,roles\nrule_a,Rock and Stone,rule,0,\n", encoding="utf-8")
        self.input.write_bytes(yaml_bytes({"proposed_id": "rule_new", "proposed_label": "Rock & Stone"}))
        result = task.collect_inputs(self.root, self.input, "shadowdark", "sd")
        self.assertEqual([row["id"] for row in result["registry_slice"]], ["rule_a"])

    def test_explicit_correction_review_is_read_and_pinned(self):
        self.args.role = "builder"
        review_path = self.root / "review.yaml"
        review = dict(self.document, id="REV-GUP-fixture-r01-r01")
        review_path.write_bytes(yaml_bytes(review))
        self.args.review = [review_path]
        result = task.collect_inputs(self.root, self.input, "shadowdark", "sd")
        task.include_reviews(self.root, self.args, self.document, result)
        self.assertIn("review.yaml", result["input_checksums"])
        self.assertIn("review.yaml", [item["path"] for item in result["documents"]])
        review["packet_id"] = "PKT-another"
        review_path.write_bytes(yaml_bytes(review))
        with self.assertRaisesRegex(PublicationError, "Review scope"):
            task.include_reviews(self.root, self.args, self.document, result)

    def test_cross_gup_review_lineage_uses_existing_scanner_rule(self):
        packet = self.document["packet_id"]
        base = self.root / "books/shadowdark/sd/artifacts"
        (base / "gup").mkdir(parents=True)
        (base / "reviews").mkdir()
        gup1, gup2 = (f"GUP-{packet}-r{revision:02d}" for revision in (1, 2))
        for revision, identifier, previous in ((1, gup1, None), (2, gup2, gup1)):
            data = dict(self.document, id=identifier, revision=revision, supersedes=previous, artifact_kind="packet_update")
            (base / "gup" / f"{identifier}.yaml").write_bytes(yaml_bytes(data))
        predecessor = dict(self.document, id=f"REV-{gup1}-r01", revision=1, supersedes=None, reviewed_gup={"id": gup1})
        (base / "reviews" / f"{predecessor['id']}.yaml").write_bytes(yaml_bytes(predecessor))
        successor = dict(self.document, id=f"REV-{gup2}-r02", revision=2, supersedes=predecessor["id"], reviewed_gup={"id": gup2})
        path = base / "reviews" / f"{successor['id']}.yaml"
        task.validate_lineage(self.root, path, successor)
        successor["supersedes"] = "REV-GUP-unrelated-r01-r01"
        with self.assertRaisesRegex(PublicationError, "invalid Review lineage"):
            task.validate_lineage(self.root, path, successor)

    def test_analyst_backward_relay_blocked_gup_is_accepted(self):
        packet_yaml = self.root / "packet.yaml"
        packet_yaml.write_bytes(yaml_bytes({"id": "PKT-SD-001-001-fixture", "ruleset_id": "shadowdark", "book_id": "sd"}))
        queue = {"LineageErrorCount": 0, "Items": [], "ActiveItems": [],
                 "BlockedItems": [{"Role": "Analyst", "Ruleset": "shadowdark", "Book": "sd",
                                   "PacketId": "PKT-SD-001-001-fixture", "InputId": "GUP-PKT-SD-001-001-fixture-r01",
                                   "Queue": "ANALYST-BLOCKED-GUP", "Path": "gup.yaml"}],
                 "Diagnostics": []}
        candidates = task.require_assignment(self.root, self.args, packet_yaml, {"id": "PKT-SD-001-001-fixture"}, queue)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["InputId"], "GUP-PKT-SD-001-001-fixture-r01")


if __name__ == "__main__":
    unittest.main()
