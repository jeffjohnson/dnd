"""Replay real approved inputs without touching their immutable outputs."""
import copy
import csv
import io
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tooling/reviewer"))
from publish_review import plan_review
from adnd1e_builder.vocab import COLUMNS
from artifact_io import PublicationError, digest, load_mapping, validate_outputs, yaml_bytes


class ReviewPublisherCase(unittest.TestCase):
    REVIEW = "REV-GUP-PKT-SD-204-205-monster-family-demons-r02-r01"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "schemas", self.root / "schemas")
        review_path = ROOT / f"books/shadowdark/sd/artifacts/reviews/{self.REVIEW}.yaml"
        self.review = load_mapping(review_path)
        gup_path = ROOT / self.review["reviewed_gup"]["path"]
        self.gup = load_mapping(gup_path)
        paths = list(gup_path.parent.glob(gup_path.stem + ".*"))
        paths.append(ROOT / self.gup["validation_report"])
        for path in paths:
            target = self.root / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        self.staged = self.root / "staged.yaml"
        self.staged.write_bytes(review_path.read_bytes())

    def write_review(self):
        self.staged.write_bytes(yaml_bytes(self.review))

    def test_zero_edge_node_only_bundle_replays_existing_judgments(self):
        outputs, inputs, _ = plan_review(self.root, self.staged)
        self.assertEqual(validate_outputs(self.root, outputs), [])
        self.assertEqual(len(outputs), 3)
        manifest = __import__("yaml").safe_load(outputs[-1].content)
        self.assertEqual(manifest["node_operations"]["count"], 5)
        self.assertEqual(manifest["operation_index"], {"additions": [], "pending_additions": [], "updates": []})
        self.assertEqual(manifest["approves"]["review_id"], self.REVIEW)
        self.assertIn(self.gup["validation_report"], inputs)
        self.assertFalse(any(output.path.exists() for output in outputs))

    def test_stale_gup_pin_refuses(self):
        self.review["reviewed_gup"]["checksum"] = "sha256:" + "0" * 64
        self.write_review()
        with self.assertRaisesRegex(PublicationError, "GUP checksum mismatch"):
            plan_review(self.root, self.staged)

    def test_unverified_approval_refuses(self):
        self.review.pop("independent_validation", None)
        self.write_review()
        with self.assertRaisesRegex(PublicationError, "independent validation"):
            plan_review(self.root, self.staged)

    def test_unknown_or_mismatched_node_refuses(self):
        self.review["node_registry_decisions"][0]["submitted_label"] = "invented label"
        self.write_review()
        with self.assertRaisesRegex(PublicationError, "registration fields disagree"):
            plan_review(self.root, self.staged)

    def test_missing_node_disposition_refuses(self):
        self.review["node_registry_decisions"].pop()
        self.write_review()
        with self.assertRaisesRegex(PublicationError, "every proposed node"):
            plan_review(self.root, self.staged)

    def test_false_suite_result_refuses(self):
        report = self.root / self.gup["validation_report"]
        value = load_mapping(report)
        value["test_result"]["passed"] = False
        report.write_bytes(yaml_bytes(value))
        with self.assertRaisesRegex(PublicationError, "passing Builder suite"):
            plan_review(self.root, self.staged)

    def test_wrong_report_identity_refuses(self):
        report = self.root / self.gup["validation_report"]
        value = load_mapping(report)
        value["gup_id"] = "GUP-another"
        report.write_bytes(yaml_bytes(value))
        with self.assertRaisesRegex(PublicationError, "another artifact"):
            plan_review(self.root, self.staged)

    def test_report_count_disagreement_refuses(self):
        report = self.root / self.gup["validation_report"]
        value = load_mapping(report)
        value["summary"]["node_additions_proposed"] = 99
        report.write_bytes(yaml_bytes(value))
        with self.assertRaisesRegex(PublicationError, "count disagrees"):
            plan_review(self.root, self.staged)

    def test_blocked_gup_is_not_silently_promoted_by_the_publisher(self):
        path = self.root / self.review["reviewed_gup"]["path"]
        self.gup["status"] = "blocked"
        self.gup["approval_ready"] = False
        path.write_bytes(yaml_bytes(self.gup))
        self.review["reviewed_gup"]["checksum"] = digest(path.read_bytes())
        self.write_review()
        with self.assertRaisesRegex(PublicationError, "GUP is not approval-ready"):
            plan_review(self.root, self.staged)

    def make_update(self):
        source_gup = load_mapping(ROOT / "books/shadowdark/sd/artifacts/gup/GUP-PKT-SD-015-015-stats-and-stat-modifiers-r05.yaml")
        row = copy.deepcopy(source_gup["edge_changes"]["pending_additions"][0])
        row.pop("ref", None)
        canonical = self.root / "rulesets/shadowdark/canonical/edges_master.csv"
        canonical.parent.mkdir(parents=True)
        with canonical.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerow(row)
        self.gup["edge_changes"]["updates"] = [{"ref": "U1", "canonical_row": 2,
            "changes": {"page": {"canonical": row["page"], "patch": "16"}}}]
        self.review["edge_decisions"] = {"approved_refs": ["U1"], "disposition": "approved"}
        path = self.root / self.review["reviewed_gup"]["path"]
        path.write_bytes(yaml_bytes(self.gup))
        self.review["reviewed_gup"]["checksum"] = digest(path.read_bytes())
        self.write_review()
        report_path = self.root / self.gup["validation_report"]
        report = load_mapping(report_path)
        report["summary"]["edge_updates"] = 1
        report_path.write_bytes(yaml_bytes(report))
        return canonical, row

    def test_update_uses_full_current_before_image_and_explicit_delta(self):
        canonical, row = self.make_update()
        outputs, pins, _ = plan_review(self.root, self.staged)
        generated = list(csv.DictReader(io.StringIO(outputs[1].content.decode())))
        self.assertEqual(generated, [dict(row, page="16")])
        self.assertIn(canonical.relative_to(self.root).as_posix(), pins)
        self.assertEqual(validate_outputs(self.root, outputs), [])

    def test_moved_update_baseline_refuses(self):
        canonical, row = self.make_update()
        with canonical.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerow(dict(row, page="999"))
        with self.assertRaisesRegex(PublicationError, "baseline mismatch"):
            plan_review(self.root, self.staged)

    def test_csv_disagreement_refuses(self):
        edges = (self.root / self.review["reviewed_gup"]["path"]).with_suffix(".edges.csv")
        edges.write_bytes(b"not,the,columns\n")
        with self.assertRaisesRegex(PublicationError, "CSV columns"):
            plan_review(self.root, self.staged)

    def test_ref_keyed_unread_ruling_refuses(self):
        self.review["edge_decisions"] = {"invented": {"disposition": "approved"}}
        self.write_review()
        with self.assertRaises(PublicationError):
            plan_review(self.root, self.staged)

    def test_existing_registration_heavy_approved_packets_replay(self):
        # Planning only: never republish or rewrite the historical bundles.
        names = ["011-014-character-overview-and-starting-level", "015-015-stats-and-stat-modifiers",
                 "016-017-ancestries", "189-189-monster-attributes"]
        successful = []
        for name in names:
            candidates = sorted((ROOT / "books/shadowdark/sd/artifacts/reviews").glob(f"REV-GUP-PKT-SD-{name}-r*-r*.yaml"))
            for path in reversed(candidates):
                value = load_mapping(path)
                if value.get("status") == "approved" and value.get("review_contract_version") == "1.3":
                    with self.subTest(review=path.stem):
                        outputs, _, _ = plan_review(ROOT, path)
                        self.assertEqual(validate_outputs(ROOT, outputs), [])
                        rows = list(csv.DictReader(io.StringIO(outputs[1].content.decode())))
                        self.assertEqual(len(rows), sum(len(group) for group in __import__("yaml").safe_load(outputs[2].content)["operation_index"].values()))
                        successful.append(path.stem)
                    break
        self.assertEqual(len(successful), len(names))


if __name__ == "__main__":
    unittest.main()
