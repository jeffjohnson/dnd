"""`decision_migration_v3` — DEC-2026-0050's bounded label-normalization model.

v3 is v1's one-to-one replacement plus one new operation: filling a blank
endpoint label with the endpoint's exact current registry label. That operation
is the reason the model exists and the reason it needs its own guards, because
unlike every other migration operation it writes text into canonical. The bound
that keeps it exact is that the value is *looked up*, never authored: a fill
whose `to` is anything other than the registry's current label for that endpoint
is refused.

Everything else v3 might have been allowed to do -- additions, relabels, merges,
removals, nonblank-label edits -- stays prohibited, and each prohibition is
asserted here rather than assumed.

The Approved bundle is synthesized in the clone. At the time these were written
the reviewed r01 GUP existed but its Review did not, so publishing a bundle in
the live repository would have been the Integrator manufacturing its own input.
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
from adnd1e_integrator.canonical import CanonicalGraph, CanonicalPaths, Registry, read_csv_rows
from adnd1e_integrator.checksums import checksum_file
from adnd1e_integrator.integrate import IntegrationError, integrate, verify_bundle
from adnd1e_integrator.migration import (
    MigrationError, check_declared_counts, check_normalization_labels, read_plan)
from test_transaction import rewind_migrations_in

DECISION = "rulesets/adnd1e/escalations/decisions/DEC-2026-0050.yaml"
GUP_DIR = "books/adnd1e/phb/artifacts/gup"


def _active_plan_id() -> str:
    """The leaf of the DEC-2026-0050 migration lineage.

    Pinning an exact revision made these tests rot the moment Builder reissued:
    r01 was superseded while this suite was being written. The model under test
    is the same at every revision, so resolve the leaf instead of naming it.
    """
    superseded = set()
    found = {}
    for path in sorted((REPO_ROOT / GUP_DIR).glob("GUP-MIG-DEC-2026-0050-*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        found[str(document.get("id") or path.stem)] = path
        if document.get("supersedes"):
            superseded.add(str(document["supersedes"]))
    leaves = sorted(set(found) - superseded)
    if len(leaves) != 1:
        raise AssertionError(f"expected one active DEC-2026-0050 plan, found {leaves}")
    return leaves[0]


def _lineage_gup_ids() -> set[str]:
    """Every revision of this Decision's plan, so the rewind touches only it."""
    return {yaml.safe_load(path.read_text(encoding="utf-8")).get("id")
            for path in (REPO_ROOT / GUP_DIR).glob("GUP-MIG-DEC-2026-0050-*.yaml")}


GUP_ID = _active_plan_id()
PLAN_PATH = f"{GUP_DIR}/{GUP_ID}.yaml"
VALIDATION = f"build/reports/{GUP_ID}.validation.json"
REVIEW_ID = f"REV-{GUP_ID}-r01"
BUNDLE_ID = f"APPROVED-{GUP_ID}-r01"

#: The three legacy identities DEC-2026-0004 and DEC-2026-0014 mapped.
RETIRED = {"comeliness": "abil_comeliness",
           "fatigue": "rule_exhaustion",
           "training": "rule_training"}


def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clone(target: Path) -> Path:
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
    # Once this plan's own migration is integrated the live corpus is the
    # post-migration state, where the retired IDs are gone and the blank labels
    # are filled. Rewind so the clone is again the corpus the plan describes.
    rewind_migrations_in(target, books=("phb", "dmg"), only=_lineage_gup_ids())
    return target


def publish(root: Path, plan: dict | None = None) -> None:
    """Re-pin the plan to the clone's baseline, then approve it.

    The rewind restores the corpus the plan describes but not byte-for-byte:
    rebuilding the node table and the registry's derived columns moves both
    checksums. Re-pinning presents a baseline the plan genuinely measures; that
    real drift is still refused is asserted by `test_a_stale_before_image_is_blocking`
    and by the baseline case in `test_baseline_drift_is_refused`.
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
    digest = sha(root / PLAN_PATH)

    reviews = root / "books" / RULESET_ID / "phb" / "artifacts" / "reviews"
    approved = root / "books" / RULESET_ID / "phb" / "artifacts" / "approved"
    reviews.mkdir(parents=True, exist_ok=True)
    approved.mkdir(parents=True, exist_ok=True)

    review = {
        "schema_version": "1.0", "id": REVIEW_ID, "status": "approved",
        "ruleset_id": RULESET_ID, "book_id": "phb", "constitution_version": "1.8",
        "overall_disposition": "approved", "approval_ready": True,
        "architectural_escalations": [],
        "reviewed_gup": {"id": GUP_ID, "path": PLAN_PATH, "checksum": digest},
        "summary": {"operations_reviewed": 60},
        "reviewer_checklist": {"canonical_files_modified": False},
        "handoff": {"next_role": "integrator", "readiness": "ready", "blocking_ids": []},
    }
    review_path = reviews / (REVIEW_ID + ".yaml")
    review_path.write_text(yaml.safe_dump(review, sort_keys=False), encoding="utf-8")

    manifest = {
        "schema_version": "1.0", "id": BUNDLE_ID, "status": "approved",
        "ruleset_id": RULESET_ID, "book_id": "phb", "packet_id": "cross-packet",
        "constitution_version": "1.8", "artifact_kind": "decision_migration",
        "operation_model": "decision_migration_v3", "revision": 1, "supersedes": None,
        "handoff": {"next_role": "integrator", "readiness": "ready", "blocking_ids": []},
        "approves": {"review_id": REVIEW_ID, "review_checksum": sha(review_path),
                     "gup_id": GUP_ID, "gup_checksum": digest},
        "review_id": REVIEW_ID,
        "components": [
            {"kind": "decision_migration", "path": PLAN_PATH, "checksum": digest},
            {"kind": "validation", "path": VALIDATION, "checksum": sha(root / VALIDATION)},
        ],
        "authority_decisions": [{"id": "DEC-2026-0050", "checksum": sha(root / DECISION)}],
    }
    (approved / (BUNDLE_ID + ".yaml")).write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def bundle_in(root: Path):
    return next(b for b in discover(root, RULESET_ID, "phb")[0] if b.bundle_id == BUNDLE_ID)


def blocking(root: Path) -> list[str]:
    return [c.name for c in verify_bundle(bundle_in(root), root).blocking_failures]


def load_plan() -> dict:
    return yaml.safe_load((REPO_ROOT / PLAN_PATH).read_text(encoding="utf-8"))


def normalization(document: dict) -> dict:
    return next(c for c in document["canonical_changes"]
                if c["kind"] == "endpoint_label_normalization")


class TestPlanShape(unittest.TestCase):
    """Every bound DEC-2026-0050 places on the model."""

    def setUp(self):
        self.document = load_plan()

    def test_the_published_plan_parses_as_v3(self):
        plan = read_plan(self.document)
        self.assertEqual(plan.model, "decision_migration_v3")
        self.assertEqual(plan.summary(), {
            "node_additions": 0, "node_replacements": 3, "endpoint_repoints": 50,
            "row_removals": 0, "label_normalizations": 7, "normalized_label_fields": 14})

    def test_the_plan_matches_the_decision_scope(self):
        """DEC-2026-0050 migration_scope, verified against the plan itself."""
        plan = read_plan(self.document)
        self.assertEqual(len(plan.replacements), 3)
        self.assertEqual({r.retired_id for r in plan.replacements}, set(RETIRED))
        self.assertEqual({r.canonical_id for r in plan.replacements}, set(RETIRED.values()))
        self.assertEqual(len(plan.repoints), 50)
        self.assertEqual(len(plan.normalizations), 7)
        self.assertEqual(sum(len(n.changes) for n in plan.normalizations), 14)
        self.assertEqual(len(plan.removals), 0)

    def test_a_nonblank_from_is_refused(self):
        """The one edit a normalization may never make."""
        document = copy.deepcopy(self.document)
        normalization(document)["changes"]["source_label"]["from"] = "Fighter"
        with self.assertRaises(MigrationError) as caught:
            read_plan(document)
        self.assertIn("may never edit a nonblank one", str(caught.exception))

    def test_a_blank_to_is_refused(self):
        document = copy.deepcopy(self.document)
        normalization(document)["changes"]["source_label"]["to"] = "  "
        with self.assertRaises(MigrationError) as caught:
            read_plan(document)
        self.assertIn("blank to", str(caught.exception))

    def test_a_non_label_field_is_refused(self):
        document = copy.deepcopy(self.document)
        normalization(document)["changes"]["polarity"] = {"from": "neutral", "to": "positive"}
        with self.assertRaises(MigrationError) as caught:
            read_plan(document)
        self.assertIn("may change only", str(caught.exception))

    def test_changing_an_endpoint_id_under_a_normalization_is_refused(self):
        document = copy.deepcopy(self.document)
        normalization(document)["changes"]["source_id"] = {"from": "class_fighter",
                                                           "to": "class_paladin"}
        with self.assertRaises(MigrationError):
            read_plan(document)

    def test_claiming_assertion_identity_is_refused(self):
        document = copy.deepcopy(self.document)
        normalization(document)["touches_assertion_identity"] = True
        with self.assertRaises(MigrationError) as caught:
            read_plan(document)
        self.assertIn("touches_assertion_identity", str(caught.exception))

    def test_an_unknown_canonical_change_kind_is_refused(self):
        document = copy.deepcopy(self.document)
        normalization(document)["kind"] = "citation_correction"
        with self.assertRaises(MigrationError) as caught:
            read_plan(document)
        self.assertIn("citation_correction", str(caught.exception))

    def test_two_operations_may_not_claim_one_row(self):
        document = copy.deepcopy(self.document)
        extra = copy.deepcopy(normalization(document))
        document["canonical_changes"].append(extra)
        with self.assertRaises(MigrationError) as caught:
            read_plan(document)
        self.assertIn("more than one operation", str(caught.exception))

    def test_v3_refuses_the_operations_it_does_not_authorize(self):
        for container, value in (
            ("additions_proposed", [{"proposed_id": "x", "proposed_label": "X",
                                     "kind": "rule", "authority": "DEC-2026-0050"}]),
            ("relabels", [{"node_id": "x"}]),
            ("merges", [{"canonical_id": "x"}]),
        ):
            with self.subTest(container=container):
                document = copy.deepcopy(self.document)
                document["node_changes"][container] = value
                with self.assertRaises(MigrationError) as caught:
                    read_plan(document)
                self.assertIn(container, str(caught.exception))

    def test_v3_refuses_a_row_removal(self):
        document = copy.deepcopy(self.document)
        document["canonical_removals"] = [{"canonical_row": 601, "authority": "DEC-2026-0050"}]
        with self.assertRaises(MigrationError) as caught:
            read_plan(document)
        self.assertIn("canonical_removals", str(caught.exception))

    def test_v3_requires_at_least_one_replacement(self):
        document = copy.deepcopy(self.document)
        document["node_changes"]["replacements"] = []
        with self.assertRaises(MigrationError) as caught:
            read_plan(document)
        self.assertIn("no replacements", str(caught.exception))

    def test_an_earlier_model_may_not_carry_a_normalization(self):
        """v1 and v2 remain unchanged (DEC-2026-0050 acceptance test 1)."""
        for model in ("decision_migration_v1", "decision_migration_v2"):
            with self.subTest(model=model):
                document = copy.deepcopy(self.document)
                document["operation_model"] = model
                with self.assertRaises(MigrationError):
                    read_plan(document)


class TestLookupNotAuthorship(unittest.TestCase):
    """A filled label is looked up in the registry, never written by the plan."""

    def setUp(self):
        self.plan = read_plan(load_plan())
        self.registry = Registry.load(
            CanonicalPaths(root=REPO_ROOT, ruleset_id=RULESET_ID).registry)

    def test_the_published_fills_match_the_registry(self):
        self.assertEqual(check_normalization_labels(self.plan, self.registry.rows), [])

    def test_an_invented_label_is_refused(self):
        document = load_plan()
        normalization(document)["changes"]["source_label"]["to"] = "Fightre"
        plan = read_plan(document)
        problems = check_normalization_labels(plan, self.registry.rows)
        self.assertTrue(problems)
        self.assertIn("Fightre", problems[0])

    def test_a_label_for_an_unregistered_endpoint_is_refused(self):
        rows = [r for r in self.registry.rows if r.values["id"] != "class_fighter"]
        problems = check_normalization_labels(self.plan, rows)
        self.assertTrue(any("class_fighter" in p for p in problems))


class TestDeclaredCounts(unittest.TestCase):
    def test_the_published_plan_counts_agree(self):
        """The active plan must count what it carries.

        This check found a real defect: r01 declared
        `counts.label_normalizations: 0` while carrying seven. Every operation in
        it was well formed, so nothing else would have caught it -- the Reviewer
        would have approved one number and the Integrator applied another.
        """
        document = load_plan()
        self.assertEqual(check_declared_counts(read_plan(document), document["counts"]), [])

    def test_a_miscounted_normalization_is_caught(self):
        document = load_plan()
        document["counts"]["label_normalizations"] = 0
        problems = check_declared_counts(read_plan(document), document["counts"])
        self.assertEqual(problems,
                         ["counts.label_normalizations declares 0 but the plan carries 7"])

    def test_a_miscounted_repoint_is_caught(self):
        document = load_plan()
        document["counts"]["endpoint_repoints"] = 49
        problems = check_declared_counts(read_plan(document), document["counts"])
        self.assertIn("counts.endpoint_repoints declares 49 but the plan carries 50", problems)


class TestDiscoveryAndPreconditions(unittest.TestCase):
    def test_a_v3_bundle_discovers_as_one_job_with_no_edge_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            publish(root)
            found = [b for b in discover(root, RULESET_ID, "phb")[0]
                     if b.bundle_id == BUNDLE_ID]
            self.assertEqual(len(found), 1)
            self.assertIsNone(found[0].edges_path)
            self.assertTrue(found[0].is_direct_migration)

    def test_a_clean_v3_bundle_passes_every_blocking_check(self):
        """The active plan is exact against the current corpus."""
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            publish(root)
            self.assertEqual(blocking(root), [])

    def test_a_miscounted_plan_is_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            document = load_plan()
            document["counts"]["label_normalizations"] = 0
            publish(root, document)
            self.assertIn("the plan's declared counts match the operations it carries",
                          blocking(root))

    def test_an_invented_label_is_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            document = load_plan()
            normalization(document)["changes"]["source_label"]["to"] = "Not The Label"
            publish(root, document)
            self.assertIn(
                "every normalized label is the endpoint's current registry label",
                blocking(root))

    def test_a_stale_before_image_is_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            document = load_plan()
            normalization(document)["before"]["aspect"] = "drifted"
            publish(root, document)
            self.assertIn("every enumerated before-image matches canonical exactly",
                          blocking(root))

    def test_an_incomplete_incident_set_is_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            document = load_plan()
            replacement = next(r for r in document["node_changes"]["replacements"]
                               if r["retired_id"] == "training")
            replacement["incident_canonical_rows"] = replacement["incident_canonical_rows"][:-1]
            publish(root, document)
            self.assertIn("each replacement enumerates its complete incident row set",
                          blocking(root))


class TestTransaction(unittest.TestCase):
    """The whole migration, applied against a real corpus."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = clone(Path(cls.tmp.name))
        publish(cls.root)
        cls.paths = CanonicalPaths(root=cls.root, ruleset_id=RULESET_ID)
        cls.before = CanonicalGraph.load(cls.paths)
        cls.batch = integrate(cls.root, RULESET_ID, [bundle_in(cls.root)],
                              integration_id="INT-19700101-030")
        cls.after = CanonicalGraph.load(cls.paths)
        cls.registry = Registry.load(cls.paths.registry)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_no_row_is_added_or_removed(self):
        self.assertEqual(len(self.after.edges), len(self.before.edges))

    def test_every_retired_identity_is_gone(self):
        endpoints = ({e["source_id"] for e in self.after.edges}
                     | {e["target_id"] for e in self.after.edges})
        for retired in RETIRED:
            self.assertNotIn(retired, endpoints, retired)
            self.assertNotIn(retired, self.registry.ids, retired)

    def test_every_replacement_identity_is_registered(self):
        for canonical in RETIRED.values():
            self.assertIn(canonical, self.registry.ids, canonical)

    def test_the_registry_is_net_zero(self):
        """Three one-to-one replacements retire and register one row each."""
        self.assertEqual(self.batch.post_counts["registry"],
                         self.batch.pre_counts["registry"])

    def test_the_blank_labels_are_filled_from_the_registry(self):
        labels = {r.values["id"]: r.values["label"] for r in self.registry.rows}
        filled = 0
        for entry in self.batch.normalizations:
            row = self.after.edges[entry["canonical_row"] - 2]
            for field_name, delta in entry["changes"].items():
                self.assertEqual(row[field_name], delta["to"])
                self.assertEqual(row[field_name], labels[entry["endpoints"][field_name]])
                self.assertTrue(row[field_name].strip())
                filled += 1
        self.assertEqual(filled, 14)

    def test_no_blank_endpoint_label_remains_on_a_normalized_row(self):
        for entry in self.batch.normalizations:
            row = self.after.edges[entry["canonical_row"] - 2]
            self.assertTrue(row["source_label"].strip())
            self.assertTrue(row["target_label"].strip())

    def test_a_normalization_does_not_change_assertion_identity(self):
        for entry in self.batch.normalizations:
            index = entry["canonical_row"] - 2
            before, after = self.before.edges[index], self.after.edges[index]
            for field_name in ("source_id", "edge_type", "target_id", "aspect", "condition"):
                self.assertEqual(before[field_name], after[field_name], field_name)

    def test_only_the_enumerated_rows_changed(self):
        touched = ({e["canonical_row"] for e in self.batch.repoints}
                   | {e["canonical_row"] for e in self.batch.normalizations})
        for index, (before, after) in enumerate(zip(self.before.edges, self.after.edges)):
            if index + 2 in touched:
                continue
            self.assertEqual(before, after, f"canonical row {index + 2} changed unbidden")

    def test_the_batch_records_its_operations(self):
        self.assertEqual(len(self.batch.repoints), 50)
        self.assertEqual(len(self.batch.normalizations), 7)
        self.assertEqual(len(self.batch.node_replacements), 3)


class TestRollback(unittest.TestCase):
    def test_a_late_failure_restores_every_file(self):
        """A before-image that drifts after verification must abort cleanly."""
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            document = load_plan()
            publish(root, document)
            paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
            before = {p: checksum_file(p) for p in paths.writable()}

            # Drift canonical after the bundle was pinned, so the applier's own
            # compare-and-swap is what fails rather than a precondition.
            rows = read_csv_rows(paths.edges)
            target = next(r for r in document["canonical_changes"]
                          if r["kind"] == "endpoint_repoint")
            graph = CanonicalGraph.load(paths)
            graph.edges[target["canonical_row"] - 2]["aspect"] = "drifted after review"
            graph.save(paths)
            drifted = {p: checksum_file(p) for p in paths.writable()}

            with self.assertRaises(IntegrationError):
                integrate(root, RULESET_ID, [bundle_in(root)],
                          integration_id="INT-19700101-031")

            self.assertEqual({p: checksum_file(p) for p in paths.writable()}, drifted)
            self.assertNotEqual(drifted, before)


if __name__ == "__main__":
    unittest.main()
