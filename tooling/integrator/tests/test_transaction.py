"""Transactional guarantees: no partial mutation, complete rollback.

The failure-handling rule the Integrator role is held to is "do not partially
mutate canonical state". These tests prove the applier honours it against copies
of the real canonical files.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap
from _bootstrap import REPO_ROOT, RULESET_ID

from adnd1e_integrator.bundles import discover
from adnd1e_integrator.canonical import CanonicalPaths
from adnd1e_integrator.checksums import checksum_file
from adnd1e_integrator.integrate import IntegrationError, integrate, verify_bundle
from adnd1e_integrator.snapshot import Snapshot, Transaction


def clone_repo(target: Path) -> Path:
    """Copy just enough of the repository for an integration to run.

    The clone is rewound to the state *before* the ready bundles were applied,
    so these tests behave identically whether or not the live repository has
    already integrated them. Without this the fixture would silently start
    testing a duplicate-rejection path once the real batch landed.
    """
    for relative in [
        f"rulesets/{RULESET_ID}/canonical",
        f"rulesets/{RULESET_ID}/registries",
        f"rulesets/{RULESET_ID}/profiles",
        f"rulesets/{RULESET_ID}/governance",
        f"books/{RULESET_ID}/phb/artifacts",
    ]:
        source = REPO_ROOT / relative
        if source.exists():
            shutil.copytree(source, target / relative, dirs_exist_ok=True)
    _rewind(target)
    return target


def _rewind(root: Path) -> None:
    """Undo every operation a queued bundle would perform, then rederive.

    Each operation class is reversed the way it was applied. Updates are undone
    first, using the `changes.*.canonical` values the manifest declares, because
    removing rows afterwards is what shifts line numbers. Additions are then
    dropped by assertion key, and registry rows are removed.

    Reversing only the additions -- as this fixture did when bundles could only
    append -- deletes the canonical rows the updates target and corrupts every
    later line number.
    """
    from adnd1e_integrator.canonical import (
        CanonicalGraph, CanonicalPaths, EDGE_COLUMNS, Registry, read_csv_rows)
    from adnd1e_integrator.derive import load_role_profile, rebuild_nodes
    from adnd1e_integrator.invariants import assertion_key
    from adnd1e_integrator.operations import read_operations

    paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
    graph = CanonicalGraph.load(paths)
    registry = Registry.load(paths.registry)
    before = len(graph.edges)
    added_keys, registered = set(), set()
    touched = False

    for bundle in discover(root, RULESET_ID, "phb")[0]:
        rows = read_csv_rows(bundle.edges_path)
        review = bundle.review or yaml.safe_load(
            bundle.review_path.read_text(encoding="utf-8"))
        operations = read_operations(bundle.manifest, review, len(rows))

        for update in operations.updates:
            index = update.canonical_index
            if not 0 <= index < len(graph.edges):
                continue
            current = graph.edges[index]
            patched = {f: c["patch"] for f, c in update.changes.items()}
            if all(current[f] == v for f, v in patched.items()):
                current.update({f: c["canonical"] for f, c in update.changes.items()})
                touched = True

        added_keys |= {assertion_key(rows[r - 1]) for r in operations.added_rows}
        registered |= {r.node_id for r in operations.registrations}

    kept = [e for e in graph.edges if assertion_key(e) not in added_keys]
    registry.rows = [r for r in registry.rows if r.values["id"] not in registered]
    if len(kept) == before and not touched and not registered:
        return

    thresholds = load_role_profile(
        root / "rulesets" / RULESET_ID / "profiles" / "roles.yaml")["thresholds"]
    labels = {n["id"]: n["label"] for n in graph.nodes}
    kinds = {n["id"]: n["kind"] for n in graph.nodes}
    graph.edges = kept
    graph.nodes = rebuild_nodes(kept, labels, kinds, thresholds)
    graph.save(paths)

    derived = {n["id"]: n for n in graph.nodes}
    for row in registry.rows:
        node = derived.get(row.values["id"])
        row.values["degree"] = node["degree"] if node else "0"
        row.values["roles"] = node["roles"] if node else ""
    registry.save(paths.registry)


class TestSnapshot(unittest.TestCase):
    def test_restore_returns_exact_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            target = tmp / "file.csv"
            target.write_bytes(b"a,b\r\n1,2\r\n")
            before = checksum_file(target)

            snapshot = Snapshot.take([target], tmp / "snap")
            target.write_bytes(b"CORRUPTED")
            self.assertEqual(snapshot.verify_unchanged(), [target])

            snapshot.restore()
            self.assertEqual(checksum_file(target), before)
            self.assertEqual(snapshot.verify_unchanged(), [])

    def test_transaction_rolls_back_on_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            target = tmp / "file.csv"
            target.write_bytes(b"original")
            with self.assertRaises(ValueError):
                with Transaction([target], tmp / "snap"):
                    target.write_bytes(b"half-written")
                    raise ValueError("boom")
            self.assertEqual(target.read_bytes(), b"original")


class TestIntegrationIsAtomic(unittest.TestCase):
    def test_duplicate_row_aborts_and_leaves_canonical_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone_repo(Path(tmp))
            paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
            before = {p: checksum_file(p) for p in paths.writable()}

            bundles, _ = discover(root, RULESET_ID, "phb")
            target = next(b for b in bundles if b.bundle_id.endswith("intro-r05-r01"))

            # Integrate once, cleanly.
            integrate(root, RULESET_ID, [target], integration_id="INT-19700101-001")
            after_first = {p: checksum_file(p) for p in paths.writable()}
            self.assertNotEqual(before, after_first)

            # Integrating the same bundle again must be refused by invariant 12
            # and must not move canonical state a single byte.
            with self.assertRaises(IntegrationError):
                integrate(root, RULESET_ID, [target], integration_id="INT-19700101-002")
            self.assertEqual({p: checksum_file(p) for p in paths.writable()}, after_first)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone_repo(Path(tmp))
            paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
            before = {p: checksum_file(p) for p in paths.writable()}

            bundles, _ = discover(root, RULESET_ID, "phb")
            integrate(root, RULESET_ID, bundles, integration_id="INT-19700101-003", dry_run=True)

            self.assertEqual({p: checksum_file(p) for p in paths.writable()}, before)

    def test_result_is_deterministic(self):
        """Identical inputs must produce byte-identical canonical outputs."""
        digests = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmp:
                root = clone_repo(Path(tmp))
                paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
                bundles, _ = discover(root, RULESET_ID, "phb")
                integrate(root, RULESET_ID, bundles, integration_id="INT-19700101-004")
                digests.append(tuple(checksum_file(p) for p in paths.writable()))
        self.assertEqual(digests[0], digests[1])


class TestPreconditions(unittest.TestCase):
    def test_every_ready_bundle_passes_its_blocking_checks(self):
        bundles, _ = discover(REPO_ROOT, RULESET_ID, "phb")
        for bundle in bundles:
            verification = verify_bundle(bundle, REPO_ROOT)
            self.assertEqual(
                verification.blocking_failures, [],
                f"{bundle.bundle_id}: "
                f"{[c.name for c in verification.blocking_failures]}")


if __name__ == "__main__":
    unittest.main()
