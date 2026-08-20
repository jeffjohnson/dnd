"""`decision_migration_v2` — the bounded many-to-one merge model.

DEC-2026-0044 assigns this capability to the Integrator and DEC-2026-0038 fixes
its shape. Covers WORK_QUEUES 1.9 rules 38-40: a merge rejects fewer than two or
duplicate retired IDs, an existing survivor, a missing retired ID or label
mismatch, an incomplete incident set, a non-paired repoint, or any nonempty
operation array outside `node_changes.merges`; a valid merge replaces every
retired registry identity with exactly one row, repoints every and only its
enumerated endpoints, leaves no retired ID anywhere, and stays transactional;
and a moved advisory `registry_csv_row` is informational, not an error.

The fixtures use the real reviewed plan rather than a hand-made one, so a change
to the published artifact surfaces here instead of being absorbed. The Approved
bundle and its Review are synthesized in the clone only: DEC-2026-0044 reserves
materializing the real bundle for the Reviewer, and this capability work is
explicitly forbidden from touching it.
"""

from __future__ import annotations

import copy
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap
from _bootstrap import REPO_ROOT, RULESET_ID

from adnd1e_integrator.bundles import discover
from adnd1e_integrator.canonical import CanonicalGraph, CanonicalPaths, Registry
from adnd1e_integrator.checksums import checksum_file
from adnd1e_integrator.integrate import IntegrationError, integrate, verify_bundle
from adnd1e_integrator.migration import MigrationError, read_plan
from test_transaction import rewind_migrations_in

PLAN_PATH = "books/adnd1e/dmg/artifacts/gup/GUP-MIG-DEC-2026-0032-r03.yaml"
GUP_ID = "GUP-MIG-DEC-2026-0032-r03"
BUNDLE_ID = "APPROVED-GUP-MIG-DEC-2026-0032-r03-r01"
REVIEW_ID = "REV-GUP-MIG-DEC-2026-0032-r03-r01"
VALIDATION = "build/reports/GUP-MIG-DEC-2026-0032-r03.validation.json"
DECISION = "rulesets/adnd1e/escalations/decisions/DEC-2026-0038.yaml"

SURVIVORS = ("abil_dex_reaction_adjustment", "abil_dex_defensive_adjustment",
             "abil_str_exceptional")
RETIRED = ("dex_reaction_adj", "abil_dexterity_reaction_attacking_adjustment",
           "dex_defensive_adj", "abil_dexterity_defensive_adjustment",
           "str_exceptional", "abil_strength_exceptional")


def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clone(target: Path) -> Path:
    for relative in [
        f"rulesets/{RULESET_ID}/canonical",
        f"rulesets/{RULESET_ID}/registries",
        f"rulesets/{RULESET_ID}/profiles",
        f"rulesets/{RULESET_ID}/governance",
        f"rulesets/{RULESET_ID}/escalations",
        f"books/{RULESET_ID}/dmg/artifacts",
        "build/reports",
    ]:
        source = REPO_ROOT / relative
        if source.exists():
            shutil.copytree(source, target / relative, dirs_exist_ok=True)
    # Once this plan's own migration is integrated, the live corpus is the
    # post-merge state: the survivors are registered and the retired IDs are
    # gone. Rewind so the clone is again the corpus the plan describes.
    rewind_migrations_in(target, books=("phb", "dmg"))
    return target


def publish(root: Path, plan: dict | None = None) -> None:
    """Re-pin the plan to the clone's baseline and materialize its bundle.

    The published r03 plan was measured against an older canonical, and every
    integration since has moved it. Re-pinning presents a corpus the plan
    genuinely describes; that baseline drift is itself refused is asserted
    separately by `test_baseline_drift_is_refused`.
    """
    paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
    document = plan if plan is not None else yaml.safe_load(
        (root / PLAN_PATH).read_text(encoding="utf-8"))
    provenance = document["provenance"]
    provenance["canonical_checksum"] = sha(paths.edges)
    provenance["canonical_rows_read"] = len(CanonicalGraph.load(paths).edges)
    provenance["registry_checksum"] = sha(paths.registry)
    provenance["registry_rows_read"] = len(Registry.load(paths.registry).rows)
    (root / PLAN_PATH).write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    reviews = root / "books" / RULESET_ID / "dmg" / "artifacts" / "reviews"
    approved = root / "books" / RULESET_ID / "dmg" / "artifacts" / "approved"
    reviews.mkdir(parents=True, exist_ok=True)
    approved.mkdir(parents=True, exist_ok=True)

    review = {
        "schema_version": "1.0", "id": REVIEW_ID, "status": "approved",
        "ruleset_id": RULESET_ID, "book_id": "dmg", "constitution_version": "1.8",
        "overall_disposition": "approved", "approval_ready": True,
        "architectural_escalations": [],
        "reviewed_gup": {"id": GUP_ID, "path": PLAN_PATH,
                         "checksum": sha(root / PLAN_PATH)},
        "summary": {"operations_reviewed": 36},
        "reviewer_checklist": {"canonical_files_modified": False},
        "handoff": {"next_role": "integrator", "readiness": "ready",
                    "blocking_ids": []},
    }
    review_path = reviews / (REVIEW_ID + ".yaml")
    review_path.write_text(yaml.safe_dump(review, sort_keys=False), encoding="utf-8")

    manifest = {
        "schema_version": "1.0", "id": BUNDLE_ID, "status": "approved",
        "ruleset_id": RULESET_ID, "book_id": "dmg", "packet_id": "cross-packet",
        "constitution_version": "1.8", "artifact_kind": "decision_migration",
        "operation_model": "decision_migration_v2", "revision": 1, "supersedes": None,
        "handoff": {"next_role": "integrator", "readiness": "ready",
                    "blocking_ids": []},
        "approves": {"review_id": REVIEW_ID, "review_checksum": sha(review_path),
                     "gup_id": GUP_ID, "gup_checksum": sha(root / PLAN_PATH)},
        "review_id": REVIEW_ID,
        "components": [
            {"kind": "decision_migration", "path": PLAN_PATH,
             "checksum": sha(root / PLAN_PATH)},
            {"kind": "validation", "path": VALIDATION,
             "checksum": sha(root / VALIDATION)},
        ],
        "authority_decisions": [
            {"id": "DEC-2026-0038", "checksum": sha(root / DECISION)}],
    }
    (approved / (BUNDLE_ID + ".yaml")).write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def repin_bundle(root: Path) -> None:
    """Re-pin only the checksums covering the plan, leaving its content alone."""
    digest = sha(root / PLAN_PATH)
    reviews = root / "books" / RULESET_ID / "dmg" / "artifacts" / "reviews"
    approved = root / "books" / RULESET_ID / "dmg" / "artifacts" / "approved"

    review_path = reviews / (REVIEW_ID + ".yaml")
    review = yaml.safe_load(review_path.read_text(encoding="utf-8"))
    review["reviewed_gup"]["checksum"] = digest
    review_path.write_text(yaml.safe_dump(review, sort_keys=False), encoding="utf-8")

    manifest_path = approved / (BUNDLE_ID + ".yaml")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["approves"]["gup_checksum"] = digest
    manifest["approves"]["review_checksum"] = sha(review_path)
    for component in manifest["components"]:
        if component["path"] == PLAN_PATH:
            component["checksum"] = digest
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def bundle_in(root: Path):
    return next(b for b in discover(root, RULESET_ID, "dmg")[0]
                if b.bundle_id == BUNDLE_ID)


def blocking(root: Path) -> list[str]:
    return [c.name for c in verify_bundle(bundle_in(root), root).blocking_failures]


class TestPlanShape(unittest.TestCase):
    """Rule 38 — every bound on the merge grammar."""

    def setUp(self):
        self.plan = yaml.safe_load((REPO_ROOT / PLAN_PATH).read_text(encoding="utf-8"))

    def test_the_published_plan_parses_as_v2(self):
        plan = read_plan(self.plan)
        self.assertEqual(plan.model, "decision_migration_v2")
        summary = plan.summary()
        self.assertEqual(summary["node_merges"], 3)
        self.assertEqual(summary["retired_identities"], 6)
        self.assertEqual(summary["endpoint_repoints"], 33)

    def test_fewer_than_two_retired_ids_is_refused(self):
        document = copy.deepcopy(self.plan)
        merge = document["node_changes"]["merges"][0]
        merge["retired_nodes"] = [merge["retired_nodes"][0]]
        with self.assertRaises(MigrationError) as caught:
            read_plan(document)
        self.assertIn("at least two", str(caught.exception))

    def test_duplicate_retired_ids_are_refused(self):
        document = copy.deepcopy(self.plan)
        merge = document["node_changes"]["merges"][0]
        merge["retired_nodes"] = [merge["retired_nodes"][0], merge["retired_nodes"][0]]
        with self.assertRaises(MigrationError) as caught:
            read_plan(document)
        self.assertIn("more than once", str(caught.exception))

    def test_a_retired_id_claimed_by_two_merges_is_refused(self):
        document = copy.deepcopy(self.plan)
        merges = document["node_changes"]["merges"]
        merges[1]["retired_nodes"] = list(merges[1]["retired_nodes"]) + [
            merges[0]["retired_nodes"][0]]
        with self.assertRaises(MigrationError) as caught:
            read_plan(document)
        self.assertIn("claimed by two merges", str(caught.exception))

    def test_a_nonempty_v1_array_is_refused(self):
        for key in ("additions_proposed", "relabels", "replacements"):
            document = copy.deepcopy(self.plan)
            document["node_changes"][key] = [{"anything": True}]
            with self.assertRaises(MigrationError) as caught:
                read_plan(document)
            self.assertIn(key, str(caught.exception))

    def test_a_removal_is_refused(self):
        document = copy.deepcopy(self.plan)
        document["canonical_removals"] = [
            {"canonical_row": 1, "replacement_edge": None}]
        with self.assertRaises(MigrationError) as caught:
            read_plan(document)
        self.assertIn("canonical_removals", str(caught.exception))

    def test_the_wrong_registry_action_is_refused(self):
        document = copy.deepcopy(self.plan)
        document["node_changes"]["merges"][0]["registry_action"] = "replace_one_row"
        with self.assertRaises(MigrationError):
            read_plan(document)

    def test_a_non_paired_repoint_is_refused(self):
        document = copy.deepcopy(self.plan)
        changes = document["canonical_changes"][0]["changes"]
        del changes[next(f for f in ("source_label", "target_label") if f in changes)]
        with self.assertRaises(MigrationError) as caught:
            read_plan(document)
        self.assertIn("paired", str(caught.exception))

    def test_v1_cannot_carry_a_merge(self):
        """WORK_QUEUES 1.9: version 1 remains unchanged and cannot merge."""
        document = copy.deepcopy(self.plan)
        document["operation_model"] = "decision_migration_v1"
        with self.assertRaises(MigrationError) as caught:
            read_plan(document)
        self.assertIn("merges", str(caught.exception))


class TestDiscoveryAndPreconditions(unittest.TestCase):
    def test_a_v2_bundle_discovers_as_one_job_with_no_edge_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            publish(root)
            found = [b for b in discover(root, RULESET_ID, "dmg")[0]
                     if b.bundle_id == BUNDLE_ID]
            self.assertEqual(len(found), 1)
            self.assertIsNone(found[0].edges_path)
            self.assertTrue(found[0].is_direct_migration)

    def test_a_clean_v2_bundle_passes_every_blocking_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            publish(root)
            self.assertEqual(blocking(root), [])

    def test_a_forbidden_edge_csv_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            publish(root)
            approved = root / "books" / RULESET_ID / "dmg" / "artifacts" / "approved"
            (approved / (BUNDLE_ID + ".edges.csv")).write_text("x", encoding="utf-8")
            found, diagnostics = discover(root, RULESET_ID, "dmg")
            self.assertNotIn(BUNDLE_ID, {b.bundle_id for b in found})
            self.assertTrue(any("forbidden edge CSV" in d for d in diagnostics))

    def test_an_extra_component_is_refused(self):
        """Rule 33: exactly one migration and one validation component.

        The extra component is deliberately well formed -- correct path, correct
        checksum -- because that is the case counting only the two required
        kinds let through. REV-IMP-DEC-2026-0044-r02-r01 reproduced it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            publish(root)
            approved = root / "books" / RULESET_ID / "dmg" / "artifacts" / "approved"
            manifest_path = approved / (BUNDLE_ID + ".yaml")
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest["components"].append(
                {"kind": "report", "path": VALIDATION, "checksum": sha(root / VALIDATION)})
            manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False),
                                     encoding="utf-8")
            self.assertIn(
                "direct migration names exactly one migration and one validation component",
                blocking(root))

    def test_a_forged_manifest_decision_checksum_is_refused(self):
        """The manifest's own Decision checksum is a precondition, not decoration.

        Verifying only the plan's copy left the manifest's copy unread, so a
        forged one passed while the bundle still looked internally consistent.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            publish(root)
            approved = root / "books" / RULESET_ID / "dmg" / "artifacts" / "approved"
            manifest_path = approved / (BUNDLE_ID + ".yaml")
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest["authority_decisions"][0]["checksum"] = "sha256:" + "0" * 64
            manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False),
                                     encoding="utf-8")
            self.assertIn(
                "manifest authority Decision checksum matches the reviewed plan: "
                "DEC-2026-0038",
                blocking(root))

    def test_a_review_that_is_not_approved_is_refused(self):
        """A Review still `proposed` has approved nothing.

        `overall_disposition` is the body's verdict; `status` is the document's
        lifecycle state. Checking only the former accepted a Review that had
        been moved back out of approval.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            publish(root)
            reviews = root / "books" / RULESET_ID / "dmg" / "artifacts" / "reviews"
            review_path = reviews / (REVIEW_ID + ".yaml")
            review = yaml.safe_load(review_path.read_text(encoding="utf-8"))
            review["status"] = "proposed"
            review_path.write_text(yaml.safe_dump(review, sort_keys=False),
                                   encoding="utf-8")
            # Re-pin so this exercises the approval check rather than stopping at
            # the earlier review-checksum precondition.
            repin_bundle(root)
            self.assertIn("review status is approved and agrees with the disposition",
                          blocking(root))

    def test_the_reviewer_reproduction_is_refused(self):
        """REV-IMP-DEC-2026-0044-r02-r01, exactly as the Reviewer built it.

        All three mutations at once, each individually well formed: a valid extra
        component, a forged manifest Decision checksum, and a re-pinned Review
        moved back to `proposed`. The r02 verifier returned no blocking failures
        for this bundle.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            publish(root)
            approved = root / "books" / RULESET_ID / "dmg" / "artifacts" / "approved"
            reviews = root / "books" / RULESET_ID / "dmg" / "artifacts" / "reviews"

            review_path = reviews / (REVIEW_ID + ".yaml")
            review = yaml.safe_load(review_path.read_text(encoding="utf-8"))
            review["status"] = "proposed"
            review_path.write_text(yaml.safe_dump(review, sort_keys=False),
                                   encoding="utf-8")
            repin_bundle(root)

            manifest_path = approved / (BUNDLE_ID + ".yaml")
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest["components"].append(
                {"kind": "report", "path": VALIDATION, "checksum": sha(root / VALIDATION)})
            manifest["authority_decisions"][0]["checksum"] = "sha256:" + "0" * 64
            manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False),
                                     encoding="utf-8")

            failures = blocking(root)
            for expected in (
                "direct migration names exactly one migration and one validation component",
                "manifest authority Decision checksum matches the reviewed plan: DEC-2026-0038",
                "review status is approved and agrees with the disposition",
            ):
                self.assertIn(expected, failures)

    def test_baseline_drift_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            publish(root)
            # Written directly, not through publish(), which re-pins provenance.
            document = yaml.safe_load((root / PLAN_PATH).read_text(encoding="utf-8"))
            document["provenance"]["registry_rows_read"] = 999
            plan_path = root / PLAN_PATH
            plan_path.write_text(yaml.safe_dump(document, sort_keys=False),
                                 encoding="utf-8")
            repin_bundle(root)
            self.assertIn(
                "migration baselines match the pinned canonical and registry state",
                blocking(root))

    def test_an_existing_survivor_identity_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
            registry = Registry.load(paths.registry)
            registry.add({"id": SURVIVORS[0], "label": "Squatter", "kind": "abil",
                          "degree": "0", "roles": ""})
            registry.save(paths.registry)
            publish(root)
            self.assertIn(
                "every retired identity exists and no survivor identity does",
                blocking(root))

    def test_a_retired_label_mismatch_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            document = yaml.safe_load((REPO_ROOT / PLAN_PATH).read_text(encoding="utf-8"))
            document["node_changes"]["merges"][0]["retired_nodes"][0]["label"] = "Wrong"
            publish(root, document)
            self.assertIn(
                "every retired identity exists and no survivor identity does",
                blocking(root))

    def test_an_incomplete_incident_set_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            document = yaml.safe_load((REPO_ROOT / PLAN_PATH).read_text(encoding="utf-8"))
            merge = document["node_changes"]["merges"][0]
            merge["incident_canonical_rows"] = merge["incident_canonical_rows"][:-1]
            publish(root, document)
            self.assertIn("each merge enumerates its complete incident row set",
                          blocking(root))

    def test_a_moved_advisory_locator_is_informational_only(self):
        """Rule 40: ID and label still match, so the row is an observation."""
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            document = yaml.safe_load((REPO_ROOT / PLAN_PATH).read_text(encoding="utf-8"))
            merge = document["node_changes"]["merges"][0]
            merge["retired_nodes"][0]["registry_csv_row"] = 99999
            publish(root, document)
            verification = verify_bundle(bundle_in(root), root)
            self.assertEqual(verification.blocking_failures, [])
            self.assertTrue(any("advisory registry_csv_row" in c.name
                                for c in verification.advisories))


class TestMergeExecution(unittest.TestCase):
    """Rule 39 — a valid merge does exactly what it declared, and no more."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = clone(Path(cls._tmp.name))
        publish(cls.root)
        paths = CanonicalPaths(root=cls.root, ruleset_id=RULESET_ID)
        cls.before_edges = [dict(e) for e in CanonicalGraph.load(paths).edges]
        cls.before_registry = Registry.load(paths.registry)
        cls.batch = integrate(cls.root, RULESET_ID, [bundle_in(cls.root)],
                              integration_id="INT-19700101-300")
        cls.after = CanonicalGraph.load(paths)
        cls.after_registry = Registry.load(paths.registry)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_each_survivor_has_exactly_one_registry_row(self):
        for survivor in SURVIVORS:
            rows = [r for r in self.after_registry.rows if r.values["id"] == survivor]
            self.assertEqual(len(rows), 1, f"{survivor} has {len(rows)} rows")

    def test_no_retired_identity_survives_anywhere(self):
        endpoints = ({e["source_id"] for e in self.after.edges}
                     | {e["target_id"] for e in self.after.edges})
        node_ids = {n["id"] for n in self.after.nodes}
        for retired in RETIRED:
            self.assertNotIn(retired, self.after_registry.ids, f"{retired} in registry")
            self.assertNotIn(retired, endpoints, f"{retired} still an endpoint")
            self.assertNotIn(retired, node_ids, f"{retired} in nodes master")

    def test_the_registry_shrinks_by_exactly_three(self):
        """Six retired identities become three survivors."""
        self.assertEqual(len(self.after_registry.rows),
                         len(self.before_registry.rows) - 3)

    def test_no_row_outside_the_incident_sets_changed(self):
        declared = {r["canonical_row"] for r in self.batch.repoints}
        self.assertEqual(len(self.after.edges), len(self.before_edges))
        for index, before in enumerate(self.before_edges):
            if index + 2 in declared:
                continue
            self.assertEqual(self.after.edges[index], before,
                             f"canonical row {index + 2} changed but was not declared")

    def test_every_repoint_changed_only_its_endpoint_and_label(self):
        for repoint in self.batch.repoints:
            before = self.before_edges[repoint["canonical_row"] - 2]
            current = self.after.edges[repoint["canonical_row"] - 2]
            changed = {c for c in before if before[c] != current[c]}
            # A declared change may be a no-op: two of these merges keep the
            # retired label verbatim, so the paired label field is declared
            # from X to X. What must hold is that nothing outside the declared
            # fields moved, and every declared field now reads its `to` value.
            extra = changed - set(repoint["changes"])
            self.assertEqual(extra, set(),
                             f"row {repoint['canonical_row']} also changed {extra}")
            for field, delta in repoint["changes"].items():
                self.assertEqual(current[field], delta["to"])

    def test_the_batch_introduces_no_finding_and_clears_three(self):
        """The merge may not add a finding, and here it removes three.

        `dex_reaction_adj`, `dex_defensive_adj` and `str_exceptional` use the
        `dex_`/`str_` prefixes constitution 3.1 does not approve, so each is an
        invariant 3 finding while it exists. Consolidating them into the
        approved `abil_` identities is exactly what DEC-2026-0038 is for.
        """
        self.assertLessEqual(self.batch.after["findings"],
                             self.batch.baseline["findings"])
        self.assertEqual(
            self.batch.baseline["findings"] - self.batch.after["findings"], 3)
        before_three = self.batch.baseline["by_invariant"].get(3, 0)
        self.assertEqual(self.batch.after["by_invariant"].get(3, 0), before_three - 3)

    def test_provenance_records_the_merge_and_its_authority(self):
        self.assertEqual(len(self.batch.node_merges), 3)
        for merge in self.batch.node_merges:
            self.assertEqual(merge["authority"], "DEC-2026-0038")
            self.assertEqual(merge["bundle_id"], BUNDLE_ID)
            self.assertEqual(len(merge["retired"]), 2)


class TestTransactional(unittest.TestCase):
    """Rule 37 — a late failure restores every file byte-for-byte."""

    def test_a_duplicate_assertion_key_rolls_everything_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)

            # Give another row the identity a repoint is about to create, so the
            # collision is only discoverable after every merge has landed.
            graph = CanonicalGraph.load(paths)
            document = yaml.safe_load((REPO_ROOT / PLAN_PATH).read_text(encoding="utf-8"))
            first = document["canonical_changes"][0]
            victim = dict(graph.edges[first["canonical_row"] - 2])
            id_field = next(f for f in ("source_id", "target_id") if f in first["changes"])
            label_field = id_field.replace("_id", "_label")
            victim[id_field] = first["changes"][id_field]["to"]
            victim[label_field] = first["changes"][label_field]["to"]
            graph.edges.append(victim)
            graph.save(paths)
            publish(root)

            before = {p: checksum_file(p) for p in paths.writable()}
            with self.assertRaises(IntegrationError) as caught:
                integrate(root, RULESET_ID, [bundle_in(root)],
                          integration_id="INT-19700101-301")
            self.assertIn("duplicate assertion key", str(caught.exception))
            self.assertEqual({p: checksum_file(p) for p in paths.writable()}, before)


if __name__ == "__main__":
    unittest.main()
