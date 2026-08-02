"""Escalation identifier contract — DEC-2026-0006."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import yaml

import _bootstrap
from _bootstrap import REPO_ROOT

from adnd1e_builder import escalation_ids

RULESET_ROOT = REPO_ROOT / "rulesets" / "adnd1e"


class TestPattern(unittest.TestCase):
    def test_accepts_the_decision_example(self):
        self.assertTrue(escalation_ids.is_timestamp_form("ESC-2026-07-30T00.57.31.482Z"))

    def test_accepts_the_collision_example(self):
        self.assertTrue(escalation_ids.is_timestamp_form("ESC-2026-07-30T00.57.31.482Z-02"))

    def test_rejects_a_colon(self):
        self.assertFalse(escalation_ids.is_timestamp_form("ESC-2026-07-30T00:57:31.482Z"))

    def test_requires_three_millisecond_digits(self):
        self.assertFalse(escalation_ids.is_timestamp_form("ESC-2026-07-30T00.57.31.48Z"))
        self.assertFalse(escalation_ids.is_timestamp_form("ESC-2026-07-30T00.57.31.4821Z"))

    def test_requires_the_utc_marker(self):
        self.assertFalse(escalation_ids.is_timestamp_form("ESC-2026-07-30T00.57.31.482"))

    def test_rejects_occurrence_suffix_01(self):
        # The first occurrence carries no suffix, so -01 is never allocated.
        self.assertFalse(escalation_ids.is_timestamp_form("ESC-2026-07-30T00.57.31.482Z-01"))

    def test_legacy_ids_remain_valid(self):
        self.assertTrue(escalation_ids.is_legacy("ESC-2026-0001"))
        self.assertTrue(escalation_ids.is_valid("ESC-2026-0001"))
        self.assertFalse(escalation_ids.is_timestamp_form("ESC-2026-0001"))

    def test_garbage_is_rejected(self):
        for bad in ("ESC-nope", "esc-2026-0001", "ESC-2026-1", "2026-07-30T00.57.31.482Z"):
            with self.subTest(bad=bad):
                self.assertFalse(escalation_ids.is_valid(bad))


class TestAllocation(unittest.TestCase):
    def test_allocates_a_valid_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = escalation_ids.allocate(Path(tmp))
            self.assertTrue(escalation_ids.is_timestamp_form(path.stem))
            self.assertTrue(path.exists())
            self.assertEqual(path.parent.name, "pending")

    def test_same_millisecond_collision_appends_02_then_03(self):
        moment = datetime(2026, 7, 30, 5, 6, 7, 890_000, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            first = escalation_ids.allocate(Path(tmp), now=moment)
            second = escalation_ids.allocate(Path(tmp), now=moment)
            third = escalation_ids.allocate(Path(tmp), now=moment)
        self.assertEqual(first.stem, "ESC-2026-07-30T05.06.07.890Z")
        self.assertEqual(second.stem, "ESC-2026-07-30T05.06.07.890Z-02")
        self.assertEqual(third.stem, "ESC-2026-07-30T05.06.07.890Z-03")

    def test_allocation_is_exclusive(self):
        moment = datetime(2026, 7, 30, 5, 6, 7, 890_000, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            a = escalation_ids.allocate(Path(tmp), now=moment)
            b = escalation_ids.allocate(Path(tmp), now=moment)
            self.assertNotEqual(a, b, "two filings must never claim one ID")


class TestAudit(unittest.TestCase):
    def _write(self, directory: Path, name: str, document: dict) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(yaml.safe_dump(document), encoding="utf-8")

    def test_clean_repository_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root / "escalations" / "pending",
                        "ESC-2026-07-30T00.57.31.482Z.yaml",
                        {"id": "ESC-2026-07-30T00.57.31.482Z"})
            self._write(root / "escalations" / "decided",
                        "ESC-2026-0001.yaml", {"id": "ESC-2026-0001"})
            result = escalation_ids.audit(root)
        self.assertTrue(result.ok)
        self.assertEqual(result.checked, 2)
        self.assertEqual(result.timestamp_form, 1)
        self.assertEqual(result.legacy_form, 1)

    def test_filename_stem_mismatch_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root / "escalations" / "pending",
                        "ESC-2026-07-30T00.57.31.482Z.yaml",
                        {"id": "ESC-2026-07-30T99.99.99.999Z"})
            result = escalation_ids.audit(root)
        self.assertFalse(result.ok)
        self.assertIn("escalation_filename_mismatch", {f.rule for f in result.findings})

    def test_duplicate_across_state_folders_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder in ("pending", "decided"):
                self._write(root / "escalations" / folder,
                            "ESC-2026-0001.yaml", {"id": "ESC-2026-0001"})
            result = escalation_ids.audit(root)
        self.assertFalse(result.ok)
        self.assertIn("escalation_id_duplicated", {f.rule for f in result.findings})

    def test_malformed_id_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root / "escalations" / "pending", "ESC-nonsense.yaml",
                        {"id": "ESC-nonsense"})
            result = escalation_ids.audit(root)
        self.assertFalse(result.ok)
        self.assertIn("escalation_id_malformed", {f.rule for f in result.findings})


class TestRealRepository(unittest.TestCase):
    def test_every_escalation_in_the_repository_conforms(self):
        result = escalation_ids.audit(RULESET_ROOT)
        self.assertTrue(
            result.ok,
            "escalation ID contract violations: "
            + "; ".join(f"{f.rule} {f.path}" for f in result.findings),
        )
        self.assertGreater(result.checked, 0)

    def test_no_escalation_filename_contains_a_colon(self):
        for folder in escalation_ids.STATE_FOLDERS:
            directory = RULESET_ROOT / "escalations" / folder
            if not directory.is_dir():
                continue
            for path in directory.glob("*.yaml"):
                with self.subTest(path=path.name):
                    self.assertNotIn(":", path.name)


if __name__ == "__main__":
    unittest.main()
