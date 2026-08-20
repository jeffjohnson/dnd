"""`decision_migration_v1` — the direct operation model of WORK_QUEUES 1.8.

Covers the acceptance rules DEC-2026-0035 requires (WORK_QUEUES 31-37): the
bundle shape discovers as one job, every way a plan can be malformed or stale is
refused *before* the snapshot, a valid plan changes exactly what it declared and
nothing else, and any failure — including one raised after canonical rows have
already been rewritten in memory — leaves every file byte-for-byte intact.

The fixtures work on a clone, and edit copies of the real reviewed plan rather
than inventing one, so a change to the published artifact shows up here as a
test failure instead of passing against a hand-made stand-in.
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

from adnd1e_integrator.bundles import discover, ready_queue
from adnd1e_integrator.canonical import CanonicalGraph, CanonicalPaths, Registry
from adnd1e_integrator.checksums import checksum_file
from adnd1e_integrator.derive import load_role_profile, rebuild_nodes
from adnd1e_integrator.integrate import IntegrationError, integrate, verify_bundle
from adnd1e_integrator.migration import MigrationError, read_plan
from test_transaction import resync_registry, rewind_all_migrations

BUNDLE_ID = "APPROVED-GUP-MIG-DEC-2026-0024-0025-r05-r01"
PLAN_PATH = "books/adnd1e/phb/artifacts/gup/GUP-MIG-DEC-2026-0024-0025-r05.yaml"
MANIFEST_PATH = f"books/adnd1e/phb/artifacts/approved/{BUNDLE_ID}.yaml"

#: What the published plan declares, restated here so a silent change to the
#: artifact is caught rather than absorbed.
RETIRED_IDS = ("spell_call_woodland_being", "item_pipes_sewers")
CANONICAL_IDS = ("spell_call_woodland_beings", "item_pipes_sewer")
ADDED_ID = "rule_greater_mistletoe"
REMOVED_ROW = 1502
REPOINTED_ROWS = (2479, 2480, 2664, 2665, 2666)


def clone(target: Path) -> Path:
    """Copy every tree a direct migration reads or writes, rewind it, re-pin it.

    Deliberately not `clone_repo`: that rewinds *every* bundle, including ones
    integrated before this plan was measured, so it cannot reproduce this
    baseline either.

    Once the migration is consumed, its pinned baseline is historical by
    definition -- every later integration moves canonical further from it, and
    no rewind of this bundle alone can recover it. So the fixture rewinds the
    migration and then re-pins the plan to the corpus that results, which is a
    state the plan genuinely describes. Nothing is lost by doing so: that the
    applier *rejects* a drifted baseline is asserted directly by
    `test_canonical_baseline_drift_is_rejected` and its registry counterpart,
    which pin deliberately wrong values and require the refusal.
    """
    for relative in [
        f"rulesets/{RULESET_ID}/canonical",
        f"rulesets/{RULESET_ID}/registries",
        f"rulesets/{RULESET_ID}/profiles",
        f"rulesets/{RULESET_ID}/governance",
        f"rulesets/{RULESET_ID}/escalations",
        f"books/{RULESET_ID}/phb/artifacts",
        "build/reports",
    ]:
        source = REPO_ROOT / relative
        if source.exists():
            shutil.copytree(source, target / relative, dirs_exist_ok=True)

    paths = CanonicalPaths(root=target, ruleset_id=RULESET_ID)
    graph = CanonicalGraph.load(paths)
    registry = Registry.load(paths.registry)
    if rewind_all_migrations(target, graph, registry):
        thresholds = load_role_profile(
            target / "rulesets" / RULESET_ID / "profiles" / "roles.yaml")["thresholds"]
        labels = {n["id"]: n["label"] for n in graph.nodes}
        kinds = {n["id"]: n["kind"] for n in graph.nodes}
        graph.nodes = rebuild_nodes(graph.edges, labels, kinds, thresholds)
        resync_registry(graph, registry)
        graph.save(paths)
        registry.save(paths.registry)

        document = load(target, PLAN_PATH)
        document["provenance"]["canonical_checksum"] = checksum_file(paths.edges)
        document["provenance"]["canonical_rows_read"] = len(graph.edges)
        document["provenance"]["registry_checksum"] = checksum_file(paths.registry)
        document["provenance"]["registry_rows_read"] = len(registry.rows)
        rewrite(target, PLAN_PATH, document)
    return target


def bundle_in(root: Path):
    return next(b for b in discover(root, RULESET_ID, "phb")[0] if b.bundle_id == BUNDLE_ID)


def load(root: Path, relative: str) -> dict:
    return yaml.safe_load((root / relative).read_text(encoding="utf-8"))


def rewrite(root: Path, relative: str, document: dict) -> None:
    """Write a plan back and re-pin every checksum that covers it.

    A test that mutated the plan without re-pinning would trip the checksum
    check first and never reach the condition it meant to exercise.
    """
    path = root / relative
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    digest = checksum_file(path)

    manifest = load(root, MANIFEST_PATH)
    manifest["approves"]["gup_checksum"] = digest
    for component in manifest["components"]:
        if component["path"] == relative:
            component["checksum"] = digest
    (root / MANIFEST_PATH).write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    review_path = f"books/{RULESET_ID}/phb/artifacts/reviews/{manifest['review_id']}.yaml"
    review = load(root, review_path)
    review["reviewed_gup"]["checksum"] = digest
    (root / review_path).write_text(
        yaml.safe_dump(review, sort_keys=False), encoding="utf-8")
    manifest["approves"]["review_checksum"] = checksum_file(root / review_path)
    (root / MANIFEST_PATH).write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def blocking_names(root: Path) -> list[str]:
    return [c.name for c in verify_bundle(bundle_in(root), root).blocking_failures]


class TestDiscovery(unittest.TestCase):
    """WORK_QUEUES 31 and 32."""

    def test_no_edge_csv_bundle_is_one_integrator_job(self):
        found, diagnostics = discover(REPO_ROOT, RULESET_ID, "phb")
        matching = [b for b in found if b.bundle_id == BUNDLE_ID]
        self.assertEqual(len(matching), 1)
        self.assertIsNone(matching[0].edges_path)
        self.assertTrue(matching[0].is_direct_migration)
        self.assertNotIn(f"{BUNDLE_ID}: manifest present with no .edges.csv component",
                         diagnostics)

    def test_direct_migration_is_ready_work(self):
        """Measured on a clone: once integrated, the live bundle is consumed.

        The claim under test is that this bundle *shape* produces one Integrator
        job -- not that this particular bundle is forever pending.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            ready = {b.bundle_id for b in ready_queue(root, RULESET_ID, ["phb"])["ready"]}
            self.assertIn(BUNDLE_ID, ready)

    def test_packet_manifest_without_its_edge_csv_stays_a_diagnostic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            manifest = load(root, MANIFEST_PATH)
            del manifest["operation_model"]
            (root / MANIFEST_PATH).write_text(
                yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

            found, diagnostics = discover(root, RULESET_ID, "phb")
            self.assertNotIn(BUNDLE_ID, {b.bundle_id for b in found})
            self.assertTrue(any("no .edges.csv component" in d for d in diagnostics))


class TestPlanParsing(unittest.TestCase):
    """The plan grammar itself: anything unrecognised is refused, not guessed."""

    def setUp(self):
        self.plan = yaml.safe_load((REPO_ROOT / PLAN_PATH).read_text(encoding="utf-8"))

    def test_published_plan_parses(self):
        plan = read_plan(self.plan)
        self.assertEqual(plan.summary(), {
            "node_additions": 1, "node_replacements": 2,
            "endpoint_repoints": 5, "row_removals": 1})

    def test_unpaired_endpoint_change_is_refused(self):
        document = copy.deepcopy(self.plan)
        del document["canonical_changes"][0]["changes"]["source_label"]
        with self.assertRaises(MigrationError) as caught:
            read_plan(document)
        self.assertIn("paired", str(caught.exception))

    def test_non_endpoint_field_change_is_refused(self):
        document = copy.deepcopy(self.plan)
        document["canonical_changes"][0]["changes"]["polarity"] = {
            "from": "neutral", "to": "governs"}
        with self.assertRaises(MigrationError):
            read_plan(document)

    def test_incomplete_before_image_is_refused(self):
        document = copy.deepcopy(self.plan)
        del document["canonical_changes"][0]["before"]["evidence"]
        with self.assertRaises(MigrationError) as caught:
            read_plan(document)
        self.assertIn("before-image", str(caught.exception))

    def test_removal_with_a_replacement_edge_is_refused(self):
        document = copy.deepcopy(self.plan)
        document["canonical_removals"][0]["replacement_edge"] = {"source_id": "x"}
        with self.assertRaises(MigrationError):
            read_plan(document)

    def test_operation_citing_an_unlisted_decision_is_refused(self):
        document = copy.deepcopy(self.plan)
        document["canonical_changes"][0]["authority"] = "DEC-2026-9999"
        with self.assertRaises(MigrationError) as caught:
            read_plan(document)
        self.assertIn("not listed", str(caught.exception))

    def test_an_unknown_operation_container_aborts_the_plan(self):
        """DEC-2026-0032's two-into-one merge has no execution path in this model.

        Skipping what we do not recognise would apply part of a reviewed
        migration and drop the rest, which is worse than refusing it.
        """
        document = copy.deepcopy(self.plan)
        document["node_changes"]["merges"] = [
            {"retired_ids": ["dex_reaction_adjustment", "abil_dex_reaction"],
             "canonical_id": "abil_dex_reaction_adjustment"}]
        with self.assertRaises(MigrationError) as caught:
            read_plan(document)
        self.assertIn("merges", str(caught.exception))

    def test_relabel_is_not_an_authorized_operation(self):
        document = copy.deepcopy(self.plan)
        document["node_changes"]["relabels"] = [{"id": "rule_terrain", "label": "Terrain"}]
        with self.assertRaises(MigrationError):
            read_plan(document)


class TestPreconditionsRejectBeforeWriting(unittest.TestCase):
    """WORK_QUEUES 33 and 34 — every one of these must fail before the snapshot."""

    def assert_rejected(self, root: Path, expected: str):
        names = blocking_names(root)
        self.assertTrue(any(expected in n for n in names),
                        f"expected a failure matching {expected!r}, got {names}")

    def test_clean_bundle_passes_every_blocking_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(blocking_names(clone(Path(tmp))), [])

    def test_forbidden_edge_csv_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            approved = root / "books" / RULESET_ID / "phb" / "artifacts" / "approved"
            (approved / f"{BUNDLE_ID}.edges.csv").write_text("x", encoding="utf-8")
            found, diagnostics = discover(root, RULESET_ID, "phb")
            self.assertNotIn(BUNDLE_ID, {b.bundle_id for b in found})
            self.assertTrue(any("forbidden edge CSV" in d for d in diagnostics))

    def test_mismatched_gup_checksum_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            manifest = load(root, MANIFEST_PATH)
            manifest["approves"]["gup_checksum"] = "sha256:" + "0" * 64
            (root / MANIFEST_PATH).write_text(
                yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
            self.assert_rejected(root, "the GUP the Review approved")

    def test_plan_other_than_the_reviewed_one_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            other = "books/adnd1e/phb/artifacts/gup/GUP-MIG-DEC-2026-0024-0025-r04.yaml"
            manifest = load(root, MANIFEST_PATH)
            for component in manifest["components"]:
                if component["kind"] == "decision_migration":
                    component["path"] = other
                    component["checksum"] = checksum_file(root / other)
            manifest["approves"]["gup_checksum"] = checksum_file(root / other)
            (root / MANIFEST_PATH).write_text(
                yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
            self.assert_rejected(root, "the GUP the Review approved")

    def test_missing_migration_component_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            manifest = load(root, MANIFEST_PATH)
            manifest["components"] = [c for c in manifest["components"]
                                      if c["kind"] != "decision_migration"]
            (root / MANIFEST_PATH).write_text(
                yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
            self.assert_rejected(root, "exactly one migration and one validation component")

    def test_canonical_baseline_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            document = load(root, PLAN_PATH)
            document["provenance"]["canonical_checksum"] = "sha256:" + "0" * 64
            rewrite(root, PLAN_PATH, document)
            self.assert_rejected(root, "baselines match the pinned canonical")

    def test_registry_baseline_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            document = load(root, PLAN_PATH)
            document["provenance"]["registry_rows_read"] = 999
            rewrite(root, PLAN_PATH, document)
            self.assert_rejected(root, "baselines match the pinned canonical")

    def test_stale_before_image_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            document = load(root, PLAN_PATH)
            document["canonical_changes"][0]["before"]["aspect"] = "something else entirely"
            rewrite(root, PLAN_PATH, document)
            self.assert_rejected(root, "before-image matches canonical")

    def test_incomplete_incident_set_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            document = load(root, PLAN_PATH)
            replacement = document["node_changes"]["replacements"][0]
            replacement["incident_canonical_rows"] = replacement["incident_canonical_rows"][:-1]
            rewrite(root, PLAN_PATH, document)
            self.assert_rejected(root, "complete incident row set")

    def test_authority_decision_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            decision = root / "rulesets" / RULESET_ID / "escalations" / "decisions" / "DEC-2026-0025.yaml"
            decision.write_text(decision.read_text(encoding="utf-8") + "\n# edited\n",
                                encoding="utf-8")
            self.assert_rejected(root, "authority Decision matches on disk: DEC-2026-0025")

    def test_a_rejected_plan_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
            before = {p: checksum_file(p) for p in paths.writable()}

            document = load(root, PLAN_PATH)
            document["canonical_changes"][0]["before"]["aspect"] = "drifted"
            rewrite(root, PLAN_PATH, document)

            with self.assertRaises(IntegrationError):
                integrate(root, RULESET_ID, [bundle_in(root)],
                          integration_id="INT-19700101-101")
            self.assertEqual({p: checksum_file(p) for p in paths.writable()}, before)


class TestValidMigrationChangesExactlyWhatItDeclared(unittest.TestCase):
    """WORK_QUEUES 35 and 36."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = clone(Path(cls._tmp.name))
        paths = CanonicalPaths(root=cls.root, ruleset_id=RULESET_ID)
        cls.before_graph = CanonicalGraph.load(paths)
        cls.before_edges = [dict(e) for e in cls.before_graph.edges]
        cls.before_registry = Registry.load(paths.registry)
        cls.batch = integrate(cls.root, RULESET_ID, [bundle_in(cls.root)],
                              integration_id="INT-19700101-100")
        cls.after_graph = CanonicalGraph.load(paths)
        cls.after_registry = Registry.load(paths.registry)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_exactly_one_row_was_removed(self):
        self.assertEqual(len(self.after_graph.edges), len(self.before_edges) - 1)
        self.assertEqual([r["canonical_row"] for r in self.batch.removals], [REMOVED_ROW])

    def test_no_retired_id_survives_anywhere(self):
        endpoints = ({e["source_id"] for e in self.after_graph.edges}
                     | {e["target_id"] for e in self.after_graph.edges})
        node_ids = {n["id"] for n in self.after_graph.nodes}
        for retired in RETIRED_IDS:
            self.assertNotIn(retired, endpoints, f"{retired} survives as an endpoint")
            self.assertNotIn(retired, self.after_registry.ids, f"{retired} survives in registry")
            self.assertNotIn(retired, node_ids, f"{retired} survives in nodes master")

    def test_no_alias_row_is_left_behind(self):
        """A replacement is net zero: one identity retired, one registered."""
        self.assertEqual(len(self.after_registry.rows),
                         len(self.before_registry.rows) + 1)  # the one addition
        for canonical_id in CANONICAL_IDS:
            self.assertIn(canonical_id, self.after_registry.ids)
        self.assertIn(ADDED_ID, self.after_registry.ids)

    def test_untouched_rows_are_byte_identical(self):
        touched = set(REPOINTED_ROWS)
        after = self.after_graph.edges
        for index, before_row in enumerate(self.before_edges):
            baseline_row = index + 2
            if baseline_row in touched or baseline_row == REMOVED_ROW:
                continue
            shifted = baseline_row - (1 if baseline_row > REMOVED_ROW else 0)
            self.assertEqual(after[shifted - 2], before_row,
                             f"canonical row {baseline_row} was mutated but not declared")

    def test_repoints_changed_only_their_endpoint_and_label(self):
        for repoint in self.batch.repoints:
            baseline = self.before_edges[repoint["canonical_row"] - 2]
            shifted = repoint["canonical_row"] - (1 if repoint["canonical_row"] > REMOVED_ROW else 0)
            current = self.after_graph.edges[shifted - 2]
            changed = {c for c in baseline if baseline[c] != current[c]}
            self.assertEqual(changed, set(repoint["changes"]),
                             f"row {repoint['canonical_row']} changed {changed}")

    def test_the_batch_introduced_no_finding(self):
        self.assertEqual(self.batch.after["findings"], self.batch.baseline["findings"])

    def test_derived_outputs_were_rebuilt(self):
        for canonical_id in CANONICAL_IDS:
            self.assertIn(canonical_id, {n["id"] for n in self.after_graph.nodes})


class TestRollback(unittest.TestCase):
    """WORK_QUEUES 37 — including a failure raised after rows were rewritten."""

    def test_late_invariant_failure_restores_every_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)

            # Make the migration collide: give another row the assertion identity
            # the repoint is about to create, so the duplicate-key check fires
            # only *after* every operation has already been applied in memory.
            graph = CanonicalGraph.load(paths)
            victim = dict(graph.edges[REPOINTED_ROWS[0] - 2])
            victim["source_id"] = "item_pipes_sewer"
            victim["source_label"] = "Pipes of the Sewer"
            graph.edges.append(victim)
            graph.save(paths)

            document = load(root, PLAN_PATH)
            document["provenance"]["canonical_checksum"] = checksum_file(paths.edges)
            document["provenance"]["canonical_rows_read"] = len(graph.edges)
            rewrite(root, PLAN_PATH, document)

            before = {p: checksum_file(p) for p in paths.writable()}
            with self.assertRaises(IntegrationError) as caught:
                integrate(root, RULESET_ID, [bundle_in(root)],
                          integration_id="INT-19700101-102")
            self.assertIn("duplicate assertion key", str(caught.exception))
            self.assertEqual({p: checksum_file(p) for p in paths.writable()}, before)


if __name__ == "__main__":
    unittest.main()
