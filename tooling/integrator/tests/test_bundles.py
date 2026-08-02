"""Queue derivation against `contracts/WORK_QUEUES.md`.

Covers the two Integrator acceptance tests the contract requires (7 and 8) plus
the legacy-bundle grouping DEC-2026-0012 flagged in its snapshot.
"""

from __future__ import annotations

import json
import unittest

import _bootstrap
from _bootstrap import REPO_ROOT, RULESET_ID

from adnd1e_integrator.bundles import discover, integrated_bundle_ids, ready_queue


class TestQueue(unittest.TestCase):
    def test_a_bundle_with_several_components_is_one_job(self):
        """WORK_QUEUES acceptance test 7."""
        bundles, _ = discover(REPO_ROOT, RULESET_ID, "phb")
        by_id = {b.bundle_id: b for b in bundles}
        target = "APPROVED-GUP-PKT-PHB-007-008-intro-r05-r01"
        self.assertIn(target, by_id)
        # manifest + edge CSV on disk, but exactly one queue entry
        self.assertEqual(sum(1 for b in bundles if b.bundle_id == target), 1)
        self.assertEqual(len(by_id[target].component_records(REPO_ROOT)), 2)

    def test_legacy_bundle_without_a_manifest_is_grouped_by_its_review(self):
        """WORK_QUEUES legacy rule 6."""
        bundles, _ = discover(REPO_ROOT, RULESET_ID, "phb")
        by_id = {b.bundle_id: b for b in bundles}
        legacy = by_id.get("APPROVED-GUP-PKT-PHB-001-006-preamble-r02-r01")
        self.assertIsNotNone(legacy)
        self.assertTrue(legacy.is_legacy)
        self.assertEqual(legacy.review_id, "REV-GUP-PKT-PHB-001-006-preamble-r02-r01")
        self.assertTrue(legacy.legacy_inferences, "legacy inference must be reported")

    def test_integrated_bundles_leave_the_queue(self):
        """WORK_QUEUES acceptance test 8. Consumption is read from manifests only."""
        consumed = integrated_bundle_ids(REPO_ROOT, RULESET_ID)
        queue = ready_queue(REPO_ROOT, RULESET_ID, ["phb", "dmg", "mm", "ua"])
        ready_ids = {b.bundle_id for b in queue["ready"]}
        self.assertFalse(ready_ids & set(consumed),
                         "an already-integrated bundle is still being offered as ready")

    def test_modification_time_does_not_affect_the_queue(self):
        """WORK_QUEUES rule 7 and acceptance test 9."""
        first = [b.bundle_id for b in ready_queue(REPO_ROOT, RULESET_ID, ["phb"])["ready"]]
        second = [b.bundle_id for b in ready_queue(REPO_ROOT, RULESET_ID, ["phb"])["ready"]]
        self.assertEqual(first, second)
        self.assertEqual(first, sorted(first), "queue order must be by ID, not mtime")

    def test_consumption_does_not_rewrite_the_bundle(self):
        """Integrator prohibition: never rewrite an Approved bundle to show state."""
        approved = REPO_ROOT / "books" / RULESET_ID / "phb" / "artifacts" / "approved"
        for path in approved.glob("APPROVED-*.yaml"):
            import yaml
            manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertNotIn(
                "integration", manifest,
                f"{path.name} carries integration state; consumption belongs in the "
                "Integration manifest, not in the published bundle")


if __name__ == "__main__":
    unittest.main()
