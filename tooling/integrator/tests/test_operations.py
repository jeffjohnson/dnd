"""Operation classification, compare-and-swap updates, and registry additions.

These cover the capabilities WORK_QUEUES 1.2-era Approved bundles introduced:
a bundle no longer carries a flat list of additions, and the Integrator now
rewrites existing canonical rows and registers approved node identities.

The dangerous case is the update: it names its target by file line number, so an
off-by-one reading silently rewrites a neighbouring assertion. Every test that
touches an update therefore asserts on the row's identity, not just on a count.
"""

from __future__ import annotations

import copy
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap
from _bootstrap import REPO_ROOT, RULESET_ID

from adnd1e_integrator.bundles import discover
from adnd1e_integrator.canonical import (
    CanonicalGraph, CanonicalPaths, Registry, read_csv_rows)
from adnd1e_integrator.checksums import checksum_file
from adnd1e_integrator.integrate import IntegrationError, integrate
from adnd1e_integrator.operations import OperationError, read_operations

from test_transaction import clone_repo

ABILITY = "APPROVED-GUP-PKT-PHB-009-013-ability-scores-r06-r01"
SPELLS = "APPROVED-GUP-PKT-PHB-040-042-spells-intro-r04-r01"


def bundle_by_id(root: Path, bundle_id: str):
    bundles, _ = discover(root, RULESET_ID, "phb")
    return next(b for b in bundles if b.bundle_id == bundle_id)


def load_review(bundle) -> dict:
    return bundle.review or yaml.safe_load(bundle.review_path.read_text(encoding="utf-8"))


class TestOperationIndex(unittest.TestCase):
    def test_every_csv_row_is_classified_exactly_once(self):
        for bundle in discover(REPO_ROOT, RULESET_ID, "phb")[0]:
            rows = read_csv_rows(bundle.edges_path)
            operations = read_operations(bundle.manifest, load_review(bundle), len(rows))
            claimed = sorted(operations.added_rows + [u.csv_row for u in operations.updates])
            self.assertEqual(claimed, list(range(1, len(rows) + 1)), bundle.bundle_id)

    def test_unclassified_row_is_rejected(self):
        bundle = bundle_by_id(REPO_ROOT, ABILITY)
        manifest = copy.deepcopy(bundle.manifest)
        manifest["operation_index"]["additions"].pop()
        with self.assertRaises(OperationError) as caught:
            read_operations(manifest, load_review(bundle), 33)
        self.assertIn("unclassified", str(caught.exception))

    def test_row_claimed_twice_is_rejected(self):
        bundle = bundle_by_id(REPO_ROOT, ABILITY)
        manifest = copy.deepcopy(bundle.manifest)
        manifest["operation_index"]["additions"].append({"csv_row": 1, "ref": "dup"})
        with self.assertRaises(OperationError):
            read_operations(manifest, load_review(bundle), 33)

    def test_missing_index_is_read_as_additions_and_reported(self):
        """Pre-1.2 bundles carry no operation_index; the inference must surface."""
        bundle = bundle_by_id(REPO_ROOT, SPELLS)
        operations = read_operations(None, load_review(bundle), 4)
        self.assertEqual(operations.additions, [1, 2, 3, 4])
        self.assertEqual(operations.updates, [])
        self.assertTrue(operations.inferred)

    def test_node_operation_count_must_match_the_review(self):
        bundle = bundle_by_id(REPO_ROOT, ABILITY)
        manifest = copy.deepcopy(bundle.manifest)
        manifest["node_operations"]["count"] = 99
        with self.assertRaises(OperationError):
            read_operations(manifest, load_review(bundle), 33)

    def test_canonical_row_is_a_file_line_number(self):
        """Line 1 is the header, so line N addresses edge index N-2."""
        bundle = bundle_by_id(REPO_ROOT, ABILITY)
        rows = read_csv_rows(bundle.edges_path)
        operations = read_operations(bundle.manifest, load_review(bundle), len(rows))
        graph = CanonicalGraph.load(CanonicalPaths(root=REPO_ROOT, ruleset_id=RULESET_ID))
        for update in operations.updates:
            target = graph.edges[update.canonical_index]
            patch = rows[update.csv_row - 1]
            self.assertEqual(
                (target["source_id"], target["target_id"]),
                (patch["source_id"], patch["target_id"]),
                f"{update.ref} at line {update.canonical_line} addresses the wrong row")


class TestCompareAndSwap(unittest.TestCase):
    def _mutate_manifest(self, root: Path, bundle_id: str, mutate) -> None:
        path = (root / "books" / RULESET_ID / "phb" / "artifacts" / "approved"
                / f"{bundle_id}.yaml")
        manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
        mutate(manifest)
        path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    def test_stale_precondition_aborts_without_writing(self):
        """If canonical no longer holds the declared value, the row moved."""
        with tempfile.TemporaryDirectory() as tmp:
            root = clone_repo(Path(tmp))
            paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
            self._mutate_manifest(
                root, ABILITY,
                lambda m: m["operation_index"]["updates"][0]["changes"]["polarity"]
                .__setitem__("canonical", "worsens"))
            before = {p: checksum_file(p) for p in paths.writable()}

            with self.assertRaises(IntegrationError) as caught:
                integrate(root, RULESET_ID, [bundle_by_id(root, ABILITY)],
                          integration_id="INT-19700101-010")
            self.assertIn("compare-and-swap", str(caught.exception))
            self.assertEqual({p: checksum_file(p) for p in paths.writable()}, before)

    def test_wrong_line_number_is_caught_by_endpoint_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone_repo(Path(tmp))
            paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
            self._mutate_manifest(
                root, ABILITY,
                lambda m: m["operation_index"]["updates"][0].__setitem__("canonical_row", 106))
            before = {p: checksum_file(p) for p in paths.writable()}

            with self.assertRaises(IntegrationError) as caught:
                integrate(root, RULESET_ID, [bundle_by_id(root, ABILITY)],
                          integration_id="INT-19700101-011")
            self.assertIn("but the patch row is", str(caught.exception))
            self.assertEqual({p: checksum_file(p) for p in paths.writable()}, before)

    def test_undeclared_change_in_the_csv_is_refused(self):
        """The CSV may not smuggle a field the manifest does not declare.

        The component checksum is re-pinned after the edit so this exercises the
        update guard rather than stopping at the earlier checksum precondition.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = clone_repo(Path(tmp))
            csv_path = (root / "books" / RULESET_ID / "phb" / "artifacts" / "approved"
                        / f"{ABILITY}.edges.csv")
            lines = csv_path.read_bytes().decode("utf-8").split("\n")
            self.assertIn(",core,", lines[30], "expected update row 30 to be a core row")
            lines[30] = lines[30].replace(",core,", ",optional,")
            csv_path.write_bytes("\n".join(lines).encode("utf-8"))
            self._mutate_manifest(
                root, ABILITY,
                lambda m: m["components"][0].__setitem__(
                    "checksum", checksum_file(csv_path)))

            with self.assertRaises(IntegrationError) as caught:
                integrate(root, RULESET_ID, [bundle_by_id(root, ABILITY)],
                          integration_id="INT-19700101-012")
            self.assertIn("does not declare", str(caught.exception))

    def test_update_rewrites_only_its_own_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone_repo(Path(tmp))
            paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
            before = CanonicalGraph.load(paths).edges
            bundle = bundle_by_id(root, ABILITY)
            rows = read_csv_rows(bundle.edges_path)
            operations = read_operations(bundle.manifest, load_review(bundle), len(rows))
            targets = {u.canonical_index for u in operations.updates}
            snapshot = [dict(e) for e in before]

            integrate(root, RULESET_ID, [bundle], integration_id="INT-19700101-013")
            after = CanonicalGraph.load(paths).edges

            for index in range(len(snapshot)):
                if index in targets:
                    continue
                self.assertEqual(snapshot[index], after[index],
                                 f"row at index {index} changed but was not an update target")
            for update in operations.updates:
                row = after[update.canonical_index]
                for field, change in update.changes.items():
                    self.assertEqual(row[field], change["patch"])
                for field in update.differences_not_applied:
                    self.assertEqual(row[field], snapshot[update.canonical_index][field],
                                     f"{field} was declared not-applied but changed")


class TestRegistryAdditions(unittest.TestCase):
    def test_registry_round_trips_byte_for_byte(self):
        """Mixed CRLF/LF terminators must survive a load/save cycle untouched."""
        path = REPO_ROOT / "rulesets" / RULESET_ID / "registries" / "nodes.csv"
        original = path.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            copy_path = Path(tmp) / "nodes.csv"
            shutil.copy2(path, copy_path)
            Registry.load(copy_path).save(copy_path)
            self.assertEqual(copy_path.read_bytes(), original)

    def test_new_row_is_inserted_in_sorted_position(self):
        path = REPO_ROOT / "rulesets" / RULESET_ID / "registries" / "nodes.csv"
        registry = Registry.load(path)
        registry.add({"id": "rule_zzz_probe", "label": "Probe", "kind": "rule",
                      "degree": "0", "roles": ""})
        ids = [r.values["id"] for r in registry.rows]
        self.assertEqual(ids, sorted(ids))

    def test_registrations_land_and_are_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone_repo(Path(tmp))
            paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
            before = Registry.load(paths.registry).ids

            bundles, _ = discover(root, RULESET_ID, "phb")
            batch = integrate(root, RULESET_ID, bundles, integration_id="INT-19700101-014")

            after = Registry.load(paths.registry)
            added = after.ids - before
            self.assertEqual(added, {r["id"] for r in batch.registrations})
            # Every registered node must carry at least one edge.
            graph = CanonicalGraph.load(paths)
            endpoints = {e["source_id"] for e in graph.edges} | {e["target_id"] for e in graph.edges}
            self.assertTrue(added <= endpoints)
            # And the registry must remain a superset of the graph's nodes.
            self.assertTrue(graph.node_ids <= after.ids)

    def test_duplicate_registration_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone_repo(Path(tmp))
            paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
            registry = Registry.load(paths.registry)
            registry.add({"id": "rule_prime_requisite", "label": "Squatter", "kind": "rule",
                          "degree": "0", "roles": ""})
            registry.save(paths.registry)

            with self.assertRaises(IntegrationError) as caught:
                integrate(root, RULESET_ID, [bundle_by_id(root, ABILITY)],
                          integration_id="INT-19700101-015")
            self.assertIn("already registered", str(caught.exception))

    def test_registry_derived_columns_track_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone_repo(Path(tmp))
            paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
            bundles, _ = discover(root, RULESET_ID, "phb")
            integrate(root, RULESET_ID, bundles, integration_id="INT-19700101-016")

            nodes = {n["id"]: n for n in CanonicalGraph.load(paths).nodes}
            for row in Registry.load(paths.registry).rows:
                node = nodes.get(row.values["id"])
                expected_degree = node["degree"] if node else "0"
                expected_roles = node["roles"] if node else ""
                self.assertEqual(row.values["degree"], expected_degree, row.values["id"])
                self.assertEqual(row.values["roles"], expected_roles, row.values["id"])


if __name__ == "__main__":
    unittest.main()
