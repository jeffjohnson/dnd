"""Queue derivation against `contracts/WORK_QUEUES.md`.

Covers the two Integrator acceptance tests the contract requires (7 and 8) plus
the legacy-bundle grouping DEC-2026-0012 flagged in its snapshot.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap
from _bootstrap import REPO_ROOT, RULESET_ID

from adnd1e_integrator.admission import load_admission
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

        # DEC-2026-0070 adds a fifth outcome: a bundle a validated
        # direct-predecessor record names as history is withheld from every
        # bucket, because its approving Review is unreadable and there is no
        # readable approval to classify it against. It is still accounted for --
        # withholding it silently is exactly what this test exists to catch --
        # so it must appear as an informational historical_unadmitted_bundle.
        withheld = [entry["bundle_id"] for entry in payload["informational"]
                    if entry["code"] == "historical_unadmitted_bundle"]
        self.assertEqual(len(withheld), len(set(withheld)),
                         "a withheld bundle is reported more than once")
        self.assertEqual(set(reported) & set(withheld), set(),
                         "a bundle is both bucketed and withheld")

        accounted = reported + withheld
        self.assertEqual(len(accounted), len(set(accounted)),
                         "a bundle appears in more than one bucket")
        self.assertEqual(set(accounted), discovered,
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
        # DEC-2026-0065: a direct caller must supply admission, or an unreadable
        # Review raises rather than being silently skipped. Resolving it here is
        # what lets this walk reach the same lineage state the queue saw.
        admission = load_admission(REPO_ROOT, RULESET_ID)
        stale = set()
        for book in ("phb", "dmg", "mm", "ua"):
            stale |= withdrawn_review_ids(REPO_ROOT, RULESET_ID, book, admission)
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


class TestManifestComponentAuthority(unittest.TestCase):
    """WORK_QUEUES 1.25 / DEC-2026-0070: the manifest declares its own components.

    Filename inference and the manifest agreed for as long as every bundle
    shipped a CSV named after itself. The Bards r03 bundle re-packages the r01
    component deliberately, which is the first artifact to separate them, and a
    derived convention must not override an explicit declaration.
    """

    BARDS_R03 = "APPROVED-GUP-PKT-PHB-117-119-bards-r04-r03"
    DECLARED = ("books/adnd1e/phb/artifacts/approved/"
                "APPROVED-GUP-PKT-PHB-117-119-bards-r04-r01.edges.csv")

    def _clone(self, target: Path) -> Path:
        for relative in [
            f"rulesets/{RULESET_ID}/canonical", f"rulesets/{RULESET_ID}/registries",
            f"rulesets/{RULESET_ID}/profiles", f"rulesets/{RULESET_ID}/governance",
            f"rulesets/{RULESET_ID}/escalations", f"rulesets/{RULESET_ID}/reports",
            f"rulesets/{RULESET_ID}/manifests", f"books/{RULESET_ID}/phb/artifacts",
            "build/reports",
        ]:
            source = REPO_ROOT / relative
            if source.exists():
                shutil.copytree(source, target / relative, dirs_exist_ok=True)
        return target

    def _manifest(self, root: Path):
        path = (root / "books" / RULESET_ID / "phb" / "artifacts" / "approved"
                / f"{self.BARDS_R03}.yaml")
        return path, yaml.safe_load(path.read_text(encoding="utf-8"))

    def _rewrite(self, path: Path, document: dict) -> None:
        path.write_text(yaml.safe_dump(document, sort_keys=False, width=92,
                                       allow_unicode=True), encoding="utf-8")

    def _found(self, root: Path):
        bundles, diagnostics = discover(root, RULESET_ID, "phb")
        return {b.bundle_id: b for b in bundles}, diagnostics

    def test_the_declared_component_is_used_though_the_stem_differs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._clone(Path(tmp))
            found, _ = self._found(root)
            self.assertIn(self.BARDS_R03, found)
            self.assertEqual(found[self.BARDS_R03].edges_path, (root / self.DECLARED).resolve())

    def test_a_colocated_stem_csv_does_not_change_the_result(self):
        """Acceptance test 2: adding or removing a stem CSV is inert."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._clone(Path(tmp))
            before = self._found(root)[0][self.BARDS_R03].edges_path

            approved = root / "books" / RULESET_ID / "phb" / "artifacts" / "approved"
            decoy = approved / f"{self.BARDS_R03}.edges.csv"
            decoy.write_text("source_id,edge_type,target_id\ndecoy,MODIFIES,decoy\n",
                             encoding="utf-8")
            self.assertEqual(self._found(root)[0][self.BARDS_R03].edges_path, before)

            decoy.unlink()
            self.assertEqual(self._found(root)[0][self.BARDS_R03].edges_path, before)

    def test_a_missing_declared_component_is_diagnostic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._clone(Path(tmp))
            path, manifest = self._manifest(root)
            manifest["components"][0]["path"] = ("books/adnd1e/phb/artifacts/approved/"
                                                "APPROVED-does-not-exist.edges.csv")
            self._rewrite(path, manifest)
            found, diagnostics = self._found(root)
            self.assertNotIn(self.BARDS_R03, found)
            self.assertTrue(any("does not exist" in d for d in diagnostics))

    def test_a_component_outside_the_repository_is_diagnostic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._clone(Path(tmp))
            path, manifest = self._manifest(root)
            manifest["components"][0]["path"] = "../outside.edges.csv"
            self._rewrite(path, manifest)
            found, diagnostics = self._found(root)
            self.assertNotIn(self.BARDS_R03, found)
            self.assertTrue(any("outside the repository" in d for d in diagnostics))

    def test_a_checksum_invalid_component_is_diagnostic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._clone(Path(tmp))
            path, manifest = self._manifest(root)
            manifest["components"][0]["checksum"] = "sha256:" + "0" * 64
            self._rewrite(path, manifest)
            found, diagnostics = self._found(root)
            self.assertNotIn(self.BARDS_R03, found)
            self.assertTrue(any("hashes to" in d for d in diagnostics))

    def test_a_wrong_kind_leaves_no_edges_component(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._clone(Path(tmp))
            path, manifest = self._manifest(root)
            manifest["components"][0]["kind"] = "pending"
            self._rewrite(path, manifest)
            found, diagnostics = self._found(root)
            self.assertNotIn(self.BARDS_R03, found)
            self.assertTrue(any("components of kind 'edges'" in d for d in diagnostics))

    def test_a_manifestless_legacy_bundle_still_uses_its_filename(self):
        """WORK_QUEUES 1.25 keeps inference for the case with no declaration."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._clone(Path(tmp))
            found, _ = self._found(root)
            legacy = found["APPROVED-GUP-PKT-PHB-001-006-preamble-r02-r01"]
            self.assertTrue(legacy.is_legacy)
            self.assertIsNotNone(legacy.edges_path)
            self.assertTrue(legacy.edges_path.name.startswith(legacy.bundle_id))

    def test_a_direct_migration_still_carries_no_edge_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._clone(Path(tmp))
            found, _ = self._found(root)
            migrations = [b for b in found.values() if b.is_direct_migration]
            self.assertTrue(migrations, "fixture expects at least one direct migration")
            for bundle in migrations:
                self.assertIsNone(bundle.edges_path)


class TestTheHistoricalBundleIsWithheld(unittest.TestCase):
    """DEC-2026-0070: named by a validated record, offered by no bucket."""

    HISTORICAL = "APPROVED-GUP-PKT-PHB-117-119-bards-r04-r02"
    # The direct successor DEC-2026-0068 pins. DEC-2026-0071 authorised r04 to
    # supersede it, so it is now the repackaged predecessor, not the leaf.
    SUCCESSOR = "APPROVED-GUP-PKT-PHB-117-119-bards-r04-r03"

    def _queue(self):
        return ready_queue(REPO_ROOT, RULESET_ID, ["phb"])

    def test_it_is_discovered_but_reaches_no_bucket(self):
        queue = self._queue()
        for name in ("ready", "integrated", "superseded", "rejected"):
            entries = queue[name]
            ids = {(e[0] if isinstance(e, tuple) else e).bundle_id for e in entries}
            self.assertNotIn(self.HISTORICAL, ids, f"withheld bundle reached {name}")

    def test_it_is_reported_rather_than_dropped(self):
        notices = [n for n in self._queue()["informational"]
                   if n["code"] == "historical_unadmitted_bundle"]
        self.assertEqual([n["bundle_id"] for n in notices], [self.HISTORICAL])
        self.assertEqual(notices[0]["authorised_by"], "DEC-2026-0068")

    def _bards_leaf(self):
        """The Bards bundle no other approved manifest supersedes.

        Read straight from the manifests rather than from the queue, so this
        stays independent of the code under test and does not need editing
        every time the packet is repackaged -- r03 became r04 under
        DEC-2026-0071 and pinned a revision here would have rotted again.
        """
        approved = REPO_ROOT / "books" / RULESET_ID / "phb" / "artifacts" / "approved"
        manifests = {}
        for path in sorted(approved.glob("APPROVED-GUP-PKT-PHB-117-119-bards-*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            manifests[str(data.get("id") or path.stem)] = data
        superseded = {str(d["supersedes"]) for d in manifests.values() if d.get("supersedes")}
        leaves = sorted(set(manifests) - superseded)
        self.assertEqual(len(leaves), 1, f"expected one Bards leaf, got {leaves}")
        return leaves[0]

    def test_the_current_leaf_is_still_offered(self):
        leaf = self._bards_leaf()
        self.assertNotEqual(leaf, self.HISTORICAL,
                            "the withheld bundle must never be the offered leaf")
        self.assertIn(leaf, [b.bundle_id for b in self._queue()["ready"]])

    def test_the_repackaged_predecessor_is_history_not_work(self):
        """WORK_QUEUES 3/4: a bundle a later bundle supersedes is not a job.

        The predecessor keeps the same GUP and an approved Review lineage, so
        neither the GUP nor the Review check retires it; both it and its
        successor were offered as ready until bundle supersession was read.
        """
        queue = self._queue()
        ready = {b.bundle_id for b in queue["ready"]}
        superseded = {b.bundle_id for b in queue["superseded"]}
        self.assertNotIn(self.SUCCESSOR, ready)
        self.assertIn(self.SUCCESSOR, superseded)


if __name__ == "__main__":
    unittest.main()
