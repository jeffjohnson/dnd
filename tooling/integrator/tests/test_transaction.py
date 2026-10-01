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
    if plan.replacements:
        if not all(r.canonical_id in registry.ids for r in plan.replacements):
            return False
    elif plan.additions:
        # A plan that registers rather than replaces has no replacement identity
        # to test idempotence against, but its additions answer the same
        # question: it is applied exactly while every ID it registered is in the
        # registry, and once those rows are dropped below a second pass matches
        # nothing. Treating such a plan as unreversible is not conservative --
        # DEC-2026-0077 adds `monster_giant` and repoints one row, and leaving
        # that repoint in place put a later value under the DEC-2026-0032 v2
        # plan's pinned before-image for the same row, so four v2 tests failed
        # on a corpus no fixture could rewind.
        if not all(addition.node_id in registry.ids for addition in plan.additions):
            return False
    else:
        # Nothing to test applied-ness against, and reversing twice would be
        # silent corruption.
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


def _books_in(root: Path) -> tuple[str, ...]:
    """Which books this clone actually carries artifacts for.

    Derived rather than defaulted. Hard-coding `phb` was invisible while every
    packet lived there, and then DEC-2026-0077 registered `monster_giant` in a
    dmg migration and the dmg packet that anchors on it was never a candidate
    for rewinding, so the clone stranded the node. A fixture that reads whatever
    the clone contains cannot fall behind the corpus that way.
    """
    directory = root / "books" / RULESET_ID
    if not directory.is_dir():
        return ()
    return tuple(sorted(child.name for child in directory.iterdir()
                        if (child / "artifacts").is_dir()))


def _rewind(root: Path, only: set[str] | None = None,
            books: tuple[str, ...] | None = None) -> None:
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

    if books is None:
        books = _books_in(root)

    paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
    graph = CanonicalGraph.load(paths)
    registry = Registry.load(paths.registry)
    before = len(graph.edges)
    added_keys, registered = set(), set()
    touched = False

    # Migrations first, in reverse application order, so their before-images are
    # matched against the corpus each was measured against.
    registered_before_migrations = set(registry.ids)
    touched |= rewind_all_migrations(root, graph, registry, books)
    #: Identities a migration reversal took back out of the registry. A packet
    #: bundle integrated later may legitimately anchor on one of them -- the
    #: Bards r04 batch reuses `item_pipes_of_sewers`, which DEC-2026-0037
    #: registered -- and such a bundle has to come out too, whatever `only`
    #: says, or the clone ends holding a graph node no registry row covers.
    stranded = registered_before_migrations - set(registry.ids)

    discovered = [bundle for book in books for bundle in discover(root, RULESET_ID, book)[0]]
    for bundle in discovered:
        if bundle.is_direct_migration:
            continue
        rows = read_csv_rows(bundle.edges_path)
        # A test that re-applies one bundle needs only that bundle rewound. The
        # registry is shared, so rewinding a sibling as well retires identities
        # the target depends on but does not itself register, and the re-apply
        # then fails invariant 1 on a node an earlier batch legitimately landed.
        #
        # The exception is a bundle stranded by the migration rewind above: a
        # partial rewind still has to be closed under registry dependency.
        if only is not None and bundle.bundle_id not in only:
            if not any(row["source_id"] in stranded or row["target_id"] in stranded
                       for row in rows):
                continue
        try:
            review = bundle.review or yaml.safe_load(
                bundle.review_path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            # DEC-2026-0065/0070: a bundle whose approving Review is unreadable
            # is never integrated, so there is nothing to rewind. Parsing it here
            # would crash the fixture on a file the queue deliberately withholds.
            continue
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


#: The bundles the atomicity and determinism tests re-apply.
#:
#: These tests need a batch that verifies, not whatever happens to be ready.
#: Reading the live queue coupled them to the corpus: the day the only ready
#: bundle was one the Integrator refuses, atomicity and determinism started
#: failing on a defect in someone else's packaging rather than on anything they
#: test. Pinning a set that is rewound and re-applied together keeps them honest;
#: whether a *given* bundle verifies is asserted by TestPreconditions.
PINNED = {
    "APPROVED-GUP-PKT-PHB-009-013-ability-scores-r06-r01",
    "APPROVED-GUP-PKT-PHB-040-042-spells-intro-r04-r01",
    "APPROVED-GUP-PKT-PHB-018-033-classes-r09-r01",
    "APPROVED-GUP-PKT-PHB-043-054-cleric-spells-r04-r01",
}


def applicable_batch(root: Path) -> list:
    """Exactly the bundles `clone_repo(rewind_only=PINNED)` rewound.

    Direct migrations are excluded on purpose. `_rewind` returns canonical to a
    state before those bundles were applied, which is far below the exact
    baseline a migration plan pins, so no migration can verify against this
    fixture by construction. Their transaction, rollback and determinism are
    covered against their own pinned baselines in `test_migration` and
    `test_migration_v2`.
    """
    found = {b.bundle_id: b for b in discover(root, RULESET_ID, "phb")[0]}
    return [found[bundle_id] for bundle_id in sorted(PINNED)]


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
            root = clone_repo(Path(tmp), rewind_only=PINNED)
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
                root = clone_repo(Path(tmp), rewind_only=PINNED)
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


class TestAPartialRewindClosesOverRetiredIdentities(unittest.TestCase):
    """DEC-2026-0075: a fixture may not strand a node it has just unregistered.

    Reversing a `decision_migration_v1` replacement takes the identity it
    registered back out of the registry. That was self-contained until a later
    packet bundle reused one -- the Bards batch anchors an edge on
    `item_pipes_of_sewers`, which DEC-2026-0037 registered -- and then a rewind
    that reversed the migration without also rewinding the dependent bundle left
    canonical referencing a node no registry row covered. Nine tests failed on a
    corpus their own fixture had broken, and the integration that exposed it was
    correct.

    So the property is closure, not a count: whatever identities the migration
    rewind retires, every integrated row that anchors on one of them has to come
    out too. Everything below is derived from the clone and from live canonical
    at the time the test runs. Nothing here names a revision, an edge total or a
    registry total, because each of those moves on the next integration and a
    guard that moves with the corpus is the defect this test exists to catch.
    """

    @classmethod
    def setUpClass(cls):
        from adnd1e_integrator.canonical import CanonicalGraph, Registry

        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        # The migration fixture's own clone, which is the partial rewind under
        # test: it reverses migrations and, through `_rewind`, only whatever
        # else that reversal makes necessary.
        from test_migration import clone as migration_clone
        migration_clone(cls.root)

        cls.paths = CanonicalPaths(root=cls.root, ruleset_id=RULESET_ID)
        cls.graph = CanonicalGraph.load(cls.paths)
        cls.registry = Registry.load(cls.paths.registry)

        live_paths = CanonicalPaths(root=REPO_ROOT, ruleset_id=RULESET_ID)
        cls.live_graph = CanonicalGraph.load(live_paths)
        cls.live_registry = Registry.load(live_paths.registry)
        #: Identities the rewind took out, read by comparing the two registries
        #: rather than by naming one.
        cls.retired = set(cls.live_registry.ids) - set(cls.registry.ids)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_rewind_actually_retired_a_registered_identity(self):
        """Without this the closure tests below would pass vacuously."""
        self.assertNotEqual(
            self.retired, set(),
            "the fixture reversed no registration, so it proves no closure")

    def test_every_integrated_row_anchored_on_a_retired_identity_came_out(self):
        """The closure property itself, derived from the clone's own bundles.

        A row only proves anything if the live repository actually integrated
        it, so live canonical is the filter: a row that is in live canonical and
        anchors on a retired identity must be absent from the clone.
        """
        from adnd1e_integrator.canonical import read_csv_rows
        from adnd1e_integrator.invariants import assertion_key

        live_keys = {assertion_key(e) for e in self.live_graph.edges}
        clone_keys = {assertion_key(e) for e in self.graph.edges}

        dependents, checked = set(), 0
        for bundle in discover(self.root, RULESET_ID, "phb")[0]:
            if bundle.is_direct_migration:
                continue
            for row in read_csv_rows(bundle.edges_path):
                if row["source_id"] not in self.retired and row["target_id"] not in self.retired:
                    continue
                key = assertion_key(row)
                if key not in live_keys:
                    continue
                dependents.add(bundle.bundle_id)
                checked += 1
                self.assertNotIn(
                    key, clone_keys,
                    f"{bundle.bundle_id} anchors an integrated row on a retired "
                    f"identity, so the rewind had to take that row out too")

        self.assertNotEqual(
            dependents, set(),
            "no integrated bundle depends on a retired identity, so this "
            "fixture cannot demonstrate closure and the guard is not being run")
        self.assertGreater(checked, 0)

    def test_the_dependent_belongs_to_the_packet_that_reused_the_identity(self):
        """Derived from the manifests, not from a pinned revision.

        The Bards packet is what reuses `item_pipes_of_sewers`; which revision
        of it is current is exactly the kind of fact that rots, so the packet is
        named and the revision is read.
        """
        from adnd1e_integrator.canonical import read_csv_rows
        from adnd1e_integrator.invariants import assertion_key

        live_keys = {assertion_key(e) for e in self.live_graph.edges}
        packets = set()
        for bundle in discover(self.root, RULESET_ID, "phb")[0]:
            if bundle.is_direct_migration:
                continue
            rows = read_csv_rows(bundle.edges_path)
            if any(assertion_key(row) in live_keys
                   and (row["source_id"] in self.retired or row["target_id"] in self.retired)
                   for row in rows):
                packets.add((bundle.manifest or {}).get("packet_id"))
        self.assertIn("PKT-PHB-117-119-bards", packets)

    def test_the_clone_has_no_endpoint_without_a_registry_identity(self):
        """Invariant 1 stated against the fixture rather than the applier."""
        endpoints = ({e["source_id"] for e in self.graph.edges}
                     | {e["target_id"] for e in self.graph.edges})
        self.assertEqual(
            sorted(endpoints - set(self.registry.ids)), [],
            "the clone carries an edge endpoint no registry row covers")

    def test_the_migration_fixture_still_verifies_and_applies(self):
        """The clone is not merely self-consistent; it is usable.

        Asserted rather than skipped on purpose. A guard that steps aside when
        the clone looks wrong would go green on exactly the corpus that broke
        it.
        """
        from test_migration import bundle_in

        bundle = bundle_in(self.root)
        verification = verify_bundle(bundle, self.root)
        self.assertEqual(
            [c.name for c in verification.blocking_failures], [],
            "the migration fixture's own bundle no longer verifies on its clone")

        before = {p: checksum_file(p) for p in self.paths.writable()}
        integrate(self.root, RULESET_ID, [bundle],
                  integration_id="INT-19700101-200", dry_run=True)
        self.assertEqual({p: checksum_file(p) for p in self.paths.writable()}, before,
                         "a dry run wrote to the clone")


class TestEveryIntegratedMigrationStaysRewindable(unittest.TestCase):
    """DEC-2026-0075's standing rule, applied to the migration rewind itself.

    A direct migration's plan pins an exact before-image for every row it
    touches, and the fixtures reproduce that corpus by reversing the migrations
    the repository has since applied. That only works while every applied
    migration is reversible. DEC-2026-0077 was not: its plan registers a node
    and repoints a row but replaces no identity, and the v1 rewind tested
    applied-ness solely by looking for a replacement identity, so it declined to
    reverse the plan at all. Its repoint then sat on canonical row 1747
    underneath the DEC-2026-0032 v2 plan's pinned before-image for that same
    row, and four v2 tests failed on a corpus no fixture could rewind.

    The invariant is stated over whatever the repository has integrated rather
    than over a list, so the next migration in any book is covered the day it
    lands.
    """

    #: Every book the repository actually carries artifacts for. Naming two of
    #: them was the same mistake one level up: the clone then held a UA row
    #: anchored on a DEC-2026-0032 merge survivor whose bundle it had not copied
    #: and could not rewind.
    BOOKS = tuple(sorted(
        child.name for child in (REPO_ROOT / "books" / RULESET_ID).iterdir()
        if (child / "artifacts").is_dir()))

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        for relative in [
            f"rulesets/{RULESET_ID}/canonical",
            f"rulesets/{RULESET_ID}/registries",
            f"rulesets/{RULESET_ID}/profiles",
            f"rulesets/{RULESET_ID}/governance",
            f"rulesets/{RULESET_ID}/escalations",
            f"rulesets/{RULESET_ID}/reports",
            "build/reports",
        ] + [f"books/{RULESET_ID}/{book}/artifacts" for book in cls.BOOKS]:
            source = REPO_ROOT / relative
            if source.exists():
                shutil.copytree(source, cls.root / relative, dirs_exist_ok=True)
        # `_rewind` with an empty set, so the clone spans both books and closes
        # over whatever the migration reversal strands. `rewind_migrations_in`
        # alone does not: it reverses migrations and stops, which is how the DMG
        # 64 packet came to anchor M014 on a `monster_giant` the rewind had just
        # unregistered.
        _rewind(cls.root, only=set(), books=cls.BOOKS)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _integrated_migrations(self):
        """Every direct-migration bundle the live repository has consumed."""
        found = []
        for book in self.BOOKS:
            for bundle in ready_queue(REPO_ROOT, RULESET_ID, [book])["integrated"]:
                bundle = bundle[0] if isinstance(bundle, tuple) else bundle
                if bundle.is_direct_migration:
                    found.append(bundle)
        return found

    def test_the_rewind_actually_moved_the_registry(self):
        """Non-vacuity: the checks below mean nothing on an unchanged clone."""
        from adnd1e_integrator.canonical import CanonicalPaths, Registry

        live = Registry.load(CanonicalPaths(root=REPO_ROOT, ruleset_id=RULESET_ID).registry)
        clone = Registry.load(CanonicalPaths(root=self.root, ruleset_id=RULESET_ID).registry)
        self.assertNotEqual(
            set(live.ids) - set(clone.ids), set(),
            "no migration was reversed, so this class compares the live corpus "
            "with itself")

    def test_the_rewound_clone_strands_no_endpoint_in_any_book(self):
        """Closure across every book the clone carries, not a named subset.

        `_rewind` looked for dependent bundles in `phb` alone. That was
        invisible while every packet lived there, and then a dmg migration
        registered `monster_giant` and the dmg packet that anchors M014 on it
        was never a candidate for rewinding, so the clone kept a graph node no
        registry row covered and the v2 merge fixture died in setUpClass.
        """
        from adnd1e_integrator.canonical import CanonicalGraph, CanonicalPaths, Registry

        paths = CanonicalPaths(root=self.root, ruleset_id=RULESET_ID)
        graph = CanonicalGraph.load(paths)
        registry = Registry.load(paths.registry)
        endpoints = ({e["source_id"] for e in graph.edges}
                     | {e["target_id"] for e in graph.edges})
        self.assertEqual(
            sorted(endpoints - set(registry.ids)), [],
            "the rewound clone carries an edge endpoint no registry row covers")

    def test_no_identity_an_integrated_migration_registered_survives_the_rewind(self):
        """Reversibility stated where composition cannot confuse it.

        Row locators deliberately do not survive a full rewind: a plan is
        measured against a corpus in which earlier migrations are applied, and
        undoing one that removed a row shifts every locator below it, which is
        why `rewind_migrations_in` takes an `only` argument at all. The registry
        carries no such ordering. Every identity a migration registers must be
        gone once the rewind reaches its fixed point, and every identity one
        retired must be back -- and that is exactly what DEC-2026-0077 broke,
        because a plan the rewind refused to reverse left `monster_giant`
        registered and its repoint standing.
        """
        from adnd1e_integrator.canonical import CanonicalPaths, Registry
        from adnd1e_integrator.migration import MigrationError, read_plan

        registry = Registry.load(CanonicalPaths(root=self.root, ruleset_id=RULESET_ID).registry)
        checked = 0
        for bundle in self._integrated_migrations():
            component = next((c for c in (bundle.manifest or {}).get("components") or []
                              if c.get("kind") == "decision_migration"), None)
            self.assertIsNotNone(
                component, f"{bundle.bundle_id} declares no decision_migration component")
            try:
                plan = read_plan(yaml.safe_load(
                    (self.root / component["path"]).read_text(encoding="utf-8")))
            except MigrationError as exc:  # pragma: no cover - a malformed plan
                self.fail(f"{bundle.bundle_id}: {exc}")

            for addition in plan.additions:
                with self.subTest(bundle=bundle.bundle_id, added=addition.node_id):
                    self.assertNotIn(
                        addition.node_id, registry.ids,
                        f"{bundle.bundle_id} registered {addition.node_id} and the rewind "
                        f"left it there, so this migration was never reversed")
                    checked += 1
            for replacement in plan.replacements:
                # Only the forward direction is asserted. Migrations chain:
                # DEC-2026-0024-0025 renamed `item_pipes_sewers` to
                # `item_pipes_sewer` and DEC-2026-0037 then renamed that to
                # `item_pipes_of_sewers`, so at the fixed point the ID restored
                # is the *first* plan's retired one, not each plan's own.
                # Requiring every retired_id back would assert a history that
                # never existed.
                with self.subTest(bundle=bundle.bundle_id, replaced=replacement.canonical_id):
                    self.assertNotIn(
                        replacement.canonical_id, registry.ids,
                        f"{bundle.bundle_id} registered {replacement.canonical_id} and the "
                        f"rewind left it there, so this migration was never reversed")
                    checked += 1
        self.assertGreater(
            checked, 0, "no integrated migration changed the registry, so nothing was proved")


class TestASnapshotRestoresAbsenceNotJustContent(unittest.TestCase):
    """DEC-2026-0092, at the unit that had the hole.

    `Snapshot.take` skipped any path that did not exist. That is harmless when
    every canonical file is already there and silently fatal when none of them
    is: a genesis rollback had nothing recorded, so it restored nothing and left
    behind every file the transaction had written. "Restore the pre-state" has
    to mean absence when the pre-state was absence.

    `test_genesis.py` proves this through a whole transaction; these prove the
    mechanism directly, so a regression here is attributable without reading a
    transaction log.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.existing = self.root / "already-here.csv"
        self.existing.write_bytes(b"id,label\r\n")
        self.created_dir = self.root / "canonical"
        self.new_file = self.created_dir / "edges_master.csv"
        self.snapshot_dir = self.root / "build" / "snapshots" / "INT-TEST-001"

    def test_a_file_that_did_not_exist_is_removed_on_restore(self):
        snapshot = Snapshot.take([self.existing, self.new_file], self.snapshot_dir,
                                 genesis_dirs=(self.created_dir,))
        self.created_dir.mkdir(parents=True)
        self.new_file.write_bytes(b"written by the transaction")
        snapshot.restore()
        self.assertFalse(self.new_file.exists(), "a created file survived rollback")
        self.assertFalse(self.created_dir.exists(), "a created directory survived rollback")

    def test_a_file_that_did_exist_is_restored_byte_for_byte(self):
        before = checksum_file(self.existing)
        snapshot = Snapshot.take([self.existing, self.new_file], self.snapshot_dir,
                                 genesis_dirs=(self.created_dir,))
        self.existing.write_bytes(b"id,label\r\nclobbered,x\r\n")
        snapshot.restore()
        self.assertEqual(checksum_file(self.existing), before)

    def test_a_directory_holding_anything_else_is_left_alone(self):
        """Only an empty directory is removed.

        A non-empty one holds something this transaction did not put there, and
        deleting it would destroy state the transaction never owned.
        """
        snapshot = Snapshot.take([self.new_file], self.snapshot_dir,
                                 genesis_dirs=(self.created_dir,))
        self.created_dir.mkdir(parents=True)
        (self.created_dir / "someone-elses-file").write_bytes(b"not ours")
        snapshot.restore()
        self.assertTrue(self.created_dir.exists())

    def test_the_transaction_rolls_a_genesis_back_and_discards_its_snapshot(self):
        with self.assertRaises(RuntimeError):
            with Transaction([self.existing, self.new_file], self.snapshot_dir,
                             genesis_dirs=(self.created_dir,),
                             discard_snapshot_on_rollback=True):
                self.created_dir.mkdir(parents=True)
                self.new_file.write_bytes(b"partial write")
                raise RuntimeError("a late failure")
        self.assertFalse(self.new_file.exists())
        self.assertFalse(self.created_dir.exists())
        self.assertFalse(self.snapshot_dir.exists(),
                         "a rolled-back genesis left a snapshot behind")

    def test_an_ordinary_rollback_keeps_its_snapshot(self):
        """An established ruleset has a real pre-state worth retaining."""
        with self.assertRaises(RuntimeError):
            with Transaction([self.existing], self.snapshot_dir):
                self.existing.write_bytes(b"clobbered")
                raise RuntimeError("a late failure")
        self.assertTrue(self.snapshot_dir.exists())
        self.assertEqual(self.existing.read_bytes(), b"id,label\r\n")


if __name__ == "__main__":
    unittest.main()
