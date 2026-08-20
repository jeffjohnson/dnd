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

from adnd1e_integrator.bundles import discover, ready_queue
from adnd1e_integrator.canonical import CanonicalPaths
from adnd1e_integrator.checksums import checksum_file
from adnd1e_integrator.integrate import IntegrationError, integrate, verify_bundle
from adnd1e_integrator.snapshot import Snapshot, Transaction


def clone_repo(target: Path, rewind_only: set[str] | None = None) -> Path:
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
        # A direct migration reads its authority Decisions and its Builder
        # validation report, so a clone without them cannot verify one.
        f"rulesets/{RULESET_ID}/escalations",
        # Integration rejection records are queue state under DEC-2026-0043: a
        # clone without them presents bundles as ready that the live repository
        # has already refused.
        f"rulesets/{RULESET_ID}/reports",
        # Without the Integration manifests every historical bundle reads as
        # unintegrated, so the rewind strips registrations that earlier batches
        # legitimately landed.
        f"rulesets/{RULESET_ID}/manifests",
        f"books/{RULESET_ID}/phb/artifacts",
        "build/reports",
    ]:
        source = REPO_ROOT / relative
        if source.exists():
            shutil.copytree(source, target / relative, dirs_exist_ok=True)
    _rewind(target, rewind_only)
    return target


def _rewind_migration(bundle, root: Path, graph, registry) -> bool:
    """Undo a `decision_migration_v1` plan, if canonical shows it was applied.

    Reversal runs in the mirror of the application order: rows come back first,
    so the repoints that follow address the line numbers the plan was measured
    against, and the registry identity swap is undone last.

    Returns whether anything changed, so the caller knows to rederive.
    """
    from adnd1e_integrator.migration import (
        MODEL_V2, MODEL_V3, MigrationError, read_plan)

    manifest = bundle.manifest or {}
    component = next((c for c in manifest.get("components") or []
                      if c.get("kind") == "decision_migration"), None)
    if component is None:
        return False
    plan_path = root / component["path"]
    if not plan_path.exists():
        return False
    try:
        plan = read_plan(yaml.safe_load(plan_path.read_text(encoding="utf-8")))
    except (MigrationError, KeyError, TypeError, ValueError):
        return False

    if plan.model == MODEL_V2:
        return _rewind_merges(plan, graph, registry)

    if plan.model == MODEL_V3:
        # v3 is a v1 replacement plus label fills. The fills must be undone too:
        # leaving them filled would make every enumerated before-image, which
        # pins the label as blank, fail against a corpus that looks migrated.
        if not plan.replacements:
            return False
        if not all(r.canonical_id in registry.ids for r in plan.replacements):
            return False
        for normalization in plan.normalizations:
            edge = graph.edges[normalization.canonical_index]
            for field_name, delta in normalization.changes.items():
                if edge.get(field_name) == delta["to"]:
                    edge[field_name] = delta["from"]
        for repoint in plan.repoints:
            edge = graph.edges[repoint.canonical_index]
            for field_name, delta in repoint.changes.items():
                if edge.get(field_name) == delta["to"]:
                    edge[field_name] = delta["from"]
        for replacement in plan.replacements:
            registry.replace(replacement.canonical_id, {
                "id": replacement.retired_id, "label": replacement.retired_label,
                "kind": replacement.kind, "degree": "0", "roles": ""})
        return True

    # Reverse a plan only when *every* one of its replacement identities is
    # currently registered, which is true exactly when the plan is fully applied
    # and nothing later has superseded part of it.
    #
    # `any` is not sufficient and is not merely loose: DEC-2026-0024-0025
    # replaces two identities, and once DEC-2026-0037 superseded one of them the
    # plan matched on the other and got reversed a second time -- re-inserting
    # its removed row twice and shifting every row below it by one.
    #
    # A plan with no replacements is left alone: there is no identity to test
    # idempotence against, and reversing it twice would be silent corruption.
    if not plan.replacements:
        return False
    if not all(r.canonical_id in registry.ids for r in plan.replacements):
        return False

    for removal in sorted(plan.removals, key=lambda r: r.canonical_row):
        graph.edges.insert(removal.canonical_index, dict(removal.before))
    for repoint in plan.repoints:
        edge = graph.edges[repoint.canonical_index]
        for field_name, delta in repoint.changes.items():
            if edge.get(field_name) == delta["to"]:
                edge[field_name] = delta["from"]
    for replacement in plan.replacements:
        if replacement.canonical_id in registry.ids:
            registry.replace(replacement.canonical_id, {
                "id": replacement.retired_id, "label": replacement.retired_label,
                "kind": replacement.kind, "degree": "0", "roles": ""})
    registry.rows = [r for r in registry.rows
                     if r.values["id"] not in {a.node_id for a in plan.additions}]
    return True


def _rewind_merges(plan, graph, registry) -> bool:
    """Undo an applied `decision_migration_v2` plan.

    A merge is fully applied exactly when every survivor identity is registered.
    Reversing then means putting each retired row back and dropping the survivor,
    after restoring the endpoints the repoints moved. A v2 plan removes no rows,
    so line numbers never shift and the repoints can be reversed in place.

    Idempotent by the same test the v1 branch uses: once the survivors are gone
    from the registry the plan no longer matches, so a second pass is a no-op.
    """
    if not plan.merges:
        return False
    if not all(merge.canonical_id in registry.ids for merge in plan.merges):
        return False

    for repoint in plan.repoints:
        edge = graph.edges[repoint.canonical_index]
        for field_name, delta in repoint.changes.items():
            if edge.get(field_name) == delta["to"]:
                edge[field_name] = delta["from"]

    for merge in plan.merges:
        registry.rows = [r for r in registry.rows
                         if r.values["id"] != merge.canonical_id]
        for retired in merge.retired:
            registry.add({"id": retired.node_id, "label": retired.label,
                          "kind": merge.kind, "degree": "0", "roles": ""})
    return True


def rewind_all_migrations(root: Path, graph, registry, books=("phb",), only=None) -> bool:
    """Undo every applied direct migration, newest first, by repeated passes.

    Migrations compose: DEC-2026-0037 repointed the rows DEC-2026-0031 had
    already repointed, so undoing the older one first would match its
    before-image against a row the newer one has since rewritten -- it silently
    does nothing, and the corpus ends up in a state neither plan describes.

    Application order is not recoverable here -- the clone deliberately omits
    `manifests/`, so nothing records which integration ran first -- so instead of
    sorting, this reverses whatever is currently reversible and repeats until
    nothing moves. `_rewind_migration` is a no-op unless the plan's own
    replacement identity is the one presently in the registry, which is true only
    of the most recently applied migration in a chain. Undoing that one exposes
    its predecessor, so the fixed point is reached in as many passes as there are
    stacked migrations.
    """
    migrations = [b for book_id in books
                  for b in discover(root, RULESET_ID, book_id)[0]
                  if b.is_direct_migration
                  and (only is None or b.gup_id in only)]

    changed = False
    for _ in range(len(migrations) + 1):
        progressed = False
        for bundle in migrations:
            progressed |= _rewind_migration(bundle, root, graph, registry)
        if not progressed:
            return changed
        changed = True
    raise AssertionError("migration rewind did not reach a fixed point")


def resync_registry(graph, registry) -> None:
    """Rebuild the registry's derived columns from the graph.

    `degree` and `roles` are a projection of canonical state, so a restored
    identity comes back at whatever degree its edges now give it. Without this,
    a rewind puts the right IDs back with zeroed derived columns and the file no
    longer matches the checksum a plan pinned against it.
    """
    derived = {n["id"]: n for n in graph.nodes}
    for row in registry.rows:
        node = derived.get(row.values["id"])
        row.values["degree"] = node["degree"] if node else "0"
        row.values["roles"] = node["roles"] if node else ""


def rewind_migrations_in(root: Path, books=("phb",), only=None) -> bool:
    """Return a clone to the state before its direct migrations were applied.

    `test_migration_v2` pins its plan against the corpus the plan describes. Once
    that migration is integrated the live corpus is the *post*-merge state, where
    the survivors are registered and the retired IDs are gone, so a clone of it
    fails every precondition the plan asserts. Rewinding first is what keeps the
    v2 regression suite meaningful after its own migration lands.

    Pass `only` to restrict the rewind to one lineage's GUP ids. A plan is
    measured against a corpus in which *earlier* migrations are already applied,
    and one of those removed a canonical row -- so undoing it too re-inserts that
    row and shifts every locator below it by one, against which no enumerated
    before-image or incident set can match.
    """
    from adnd1e_integrator.canonical import CanonicalGraph, CanonicalPaths, Registry
    from adnd1e_integrator.derive import load_role_profile, rebuild_nodes

    paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
    graph = CanonicalGraph.load(paths)
    registry = Registry.load(paths.registry)
    if not rewind_all_migrations(root, graph, registry, books, only):
        return False

    thresholds = load_role_profile(
        root / "rulesets" / RULESET_ID / "profiles" / "roles.yaml")["thresholds"]
    labels = {n["id"]: n["label"] for n in graph.nodes}
    kinds = {n["id"]: n["kind"] for n in graph.nodes}
    for merge_source in (registry.rows,):
        for row in merge_source:
            labels.setdefault(row.values["id"], row.values["label"])
            kinds.setdefault(row.values["id"], row.values["kind"])
    graph.nodes = rebuild_nodes(graph.edges, labels, kinds, thresholds)
    graph.save(paths)
    resync_registry(graph, registry)
    registry.save(paths.registry)
    return True


def _rewind(root: Path, only: set[str] | None = None) -> None:
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

    # Migrations first, in reverse application order, so their before-images are
    # matched against the corpus each was measured against.
    touched |= rewind_all_migrations(root, graph, registry)

    for bundle in discover(root, RULESET_ID, "phb")[0]:
        if bundle.is_direct_migration:
            continue
        # A test that re-applies one bundle needs only that bundle rewound. The
        # registry is shared, so rewinding a sibling as well retires identities
        # the target depends on but does not itself register, and the re-apply
        # then fails invariant 1 on a node an earlier batch legitimately landed.
        if only is not None and bundle.bundle_id not in only:
            continue
        rows = read_csv_rows(bundle.edges_path)
        review = bundle.review or yaml.safe_load(
            bundle.review_path.read_text(encoding="utf-8"))
        try:
            operations = read_operations(bundle.manifest, review, len(rows))
        except (KeyError, ValueError):
            # A bundle whose operation index cannot be read is one the applier
            # rejects at precondition time, so it never reached canonical state
            # and there is nothing here to undo. Skipping keeps the fixture
            # measuring the transaction rather than dying on a malformed input
            # that happens to be sitting in the queue.
            #
            # The defect itself is not swallowed: TestPreconditions asserts that
            # every ready bundle passes its blocking checks, and that is the test
            # that must fail while such a bundle is published.
            continue

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
    # The registry is shared across bundles. A registration whose node still
    # anchors a surviving edge is one a bundle this rewind did not undo depends
    # on, so retiring it would leave canonical referencing an unregistered node
    # and fail the re-apply on a defect the fixture invented.
    surviving = {e["source_id"] for e in kept} | {e["target_id"] for e in kept}
    registered -= surviving
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


def applicable_batch(root: Path) -> list:
    """The edge-CSV bundles these transaction tests are about.

    Direct migrations are excluded on purpose. `_rewind` returns canonical to a
    state before *every* queued bundle was applied, which is far below the exact
    baseline a migration plan pins, so no migration can verify against this
    fixture by construction. Their transaction, rollback and determinism are
    covered against their own pinned baselines in `test_migration` and
    `test_migration_v2`.
    """
    return [b for b in ready_queue(root, RULESET_ID, ["phb"])["ready"]
            if not b.is_direct_migration]


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

            bundles = applicable_batch(root)
            integrate(root, RULESET_ID, bundles, integration_id="INT-19700101-003", dry_run=True)

            self.assertEqual({p: checksum_file(p) for p in paths.writable()}, before)

    def test_result_is_deterministic(self):
        """Identical inputs must produce byte-identical canonical outputs."""
        digests = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmp:
                root = clone_repo(Path(tmp))
                paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
                bundles = applicable_batch(root)
                integrate(root, RULESET_ID, bundles, integration_id="INT-19700101-004")
                digests.append(tuple(checksum_file(p) for p in paths.writable()))
        self.assertEqual(digests[0], digests[1])


class TestPreconditions(unittest.TestCase):
    def test_every_ready_bundle_passes_its_blocking_checks(self):
        """Ready means the active leaf, not everything `discover` returns.

        `discover` deliberately yields every Approved bundle, history included.
        A superseded bundle will never be integrated, so holding its provenance
        to a blocking check asserts a contract the repository does not make --
        and it fails on exactly the bundles whose successors already shipped.
        """
        for bundle in ready_queue(REPO_ROOT, RULESET_ID, ["phb"])["ready"]:
            verification = verify_bundle(bundle, REPO_ROOT)
            self.assertEqual(
                verification.blocking_failures, [],
                f"{bundle.bundle_id}: "
                f"{[c.name for c in verification.blocking_failures]}")

    def test_superseded_bundle_is_not_offered_as_ready(self):
        """A bundle whose GUP a later revision supersedes is history, not a job."""
        queue = ready_queue(REPO_ROOT, RULESET_ID, ["phb"])
        retired = {b.bundle_id for b in queue["superseded"]}
        self.assertNotEqual(retired, set(), "fixture expects at least one retired bundle")
        self.assertEqual(retired & {b.bundle_id for b in queue["ready"]}, set())


if __name__ == "__main__":
    unittest.main()
