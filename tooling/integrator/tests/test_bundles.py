"""Queue derivation against `contracts/WORK_QUEUES.md`.

Covers the two Integrator acceptance tests the contract requires (7 and 8) plus
the legacy-bundle grouping DEC-2026-0012 flagged in its snapshot.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import unittest

import _bootstrap
from _bootstrap import REPO_ROOT, RULESET_ID

from adnd1e_integrator.bundles import (
    discover, integrated_bundle_ids, ready_queue, rejected_bundle_ids,
    withdrawn_review_ids)
from adnd1e_integrator.cli import cmd_queue


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

    def test_the_cli_accounts_for_every_discovered_bundle(self):
        """The one view an Integrator actually runs must lose nothing.

        `cmd_queue` serialized ready, integrated and superseded but not rejected,
        so a refused bundle appeared in no bucket at all: the CLI reported three
        fewer bundles than it discovered and gave no sign they had been refused,
        while the common scanner listed them as INTEGRATOR-REJECTED. Asserting
        the partition rather than the one missing key is what keeps a future
        bucket from going the same way.
        """
        books = ["phb", "dmg", "mm", "ua"]
        discovered = {b.bundle_id for book in books
                      for b in discover(REPO_ROOT, RULESET_ID, book)[0]}

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            cmd_queue(argparse.Namespace(
                repo_root=str(REPO_ROOT), ruleset_id=RULESET_ID, books=books))
        payload = json.loads(buffer.getvalue())

        buckets = ("ready", "integrated", "superseded", "rejected")
        for name in buckets:
            self.assertIn(name, payload, f"{name} bucket is missing from the payload")

        reported = [entry["bundle_id"] for name in buckets for entry in payload[name]]
        self.assertEqual(len(reported), len(set(reported)),
                         "a bundle appears in more than one bucket")
        self.assertEqual(set(reported), discovered,
                         "the CLI must account for every discovered bundle exactly once")

        for entry in payload["rejected"]:
            self.assertTrue(entry.get("rejection_record_id"),
                            f"{entry['bundle_id']} is refused but names no record")

    def test_a_superseded_rejection_record_stops_suppressing(self):
        """A rejection can be wrong, so it has to be withdrawable.

        Records are immutable, so the only correction is a successor. Without
        honouring `supersedes` an over-broad record would suppress its bundles
        forever: INT-20260819-001 wrongly rejected the psionics bundle on a
        three-field assertion key, and INT-20260819-002 withdrew that claim.
        """
        live = rejected_bundle_ids(REPO_ROOT, RULESET_ID)
        reports = REPO_ROOT / "rulesets" / RULESET_ID / "reports"
        retired = set()
        for path in reports.glob("*.rejected.json"):
            document = json.loads(path.read_text(encoding="utf-8"))
            if document.get("status") == "rejected" and document.get("supersedes"):
                retired.add(str(document["supersedes"]))
        self.assertTrue(retired, "expected at least one superseded rejection record")
        self.assertFalse(set(live.values()) & retired,
                         "a superseded rejection record is still deriving queue state")

    def test_a_bundle_whose_review_lineage_is_withdrawn_is_not_ready(self):
        """Only the active leaf approves anything (WORK_QUEUES 3 and 6).

        The test is the leaf's disposition, not whether the pinned Review was
        superseded. A lineage routinely goes approved -> revision_required ->
        approved, and the re-approving leaf may endorse the same bundle the
        middle revision questioned; treating supersession itself as withdrawal
        would strand that bundle permanently. What must never happen is
        integrating on an approval the lineage has since withdrawn.
        """
        queue = ready_queue(REPO_ROOT, RULESET_ID, ["phb", "dmg", "mm", "ua"])
        stale = set()
        for book in ("phb", "dmg", "mm", "ua"):
            stale |= withdrawn_review_ids(REPO_ROOT, RULESET_ID, book)
        offered = [b.bundle_id for b in queue["ready"] if b.review_id in stale]
        self.assertEqual(offered, [],
                         "a bundle approved by a superseded Review is being offered")

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
