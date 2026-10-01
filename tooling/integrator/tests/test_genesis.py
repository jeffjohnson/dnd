"""A ruleset's first integration: DEC-2026-0092.

Shadowdark reached its first Integrator-ready Approved bundle with no
`rulesets/shadowdark/canonical/` directory at all, and the transaction could not
run. Constitution 1.2 section 8 and DEC-2026-0083 both allow the Integrator to
create that directory, and both forbid preparing it beforehand: the canonical
files must be a *consequence* of a verified bundle, never a baseline laid down
so a transaction has something to write into.

These fixtures are isolated. They take Shadowdark's real, Architect-owned
governance -- its constitution, role profile, and registries -- because that is
what makes them a Shadowdark genesis rather than a generic one. They synthesize
their own Approved bundle instead of copying whichever bundle the Reviewer has
currently published, so the evidence a Reviewer re-runs does not change meaning
when an unrelated packet is re-approved.

What each test is trying to catch is stated with it. The rollback test is the
one that matters most: before this change `Snapshot.take` skipped a path that
did not exist, so a failed genesis restored nothing and therefore left behind
every canonical file it had just written -- a partially mutated canonical state,
which is the one outcome the Integrator's failure-handling rule forbids.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

import _bootstrap
from _bootstrap import REPO_ROOT

from adnd1e_integrator.bundles import discover
from adnd1e_integrator.canonical import CanonicalGraph, CanonicalPaths, read_csv_rows
from adnd1e_integrator.checksums import checksum_file
from adnd1e_integrator.integrate import IntegrationError, integrate, verify_bundle

GENESIS_RULESET = "shadowdark"
GENESIS_BOOK = "sd"

EDGE_HEADER = (
    "source_id,source_label,edge_type,target_id,target_label,aspect,condition,"
    "polarity,polarity_basis,book,page,section,evidence,pass,status,"
    "supersession_basis,general_rule_id,review_flag"
)

# Four rows over three identities, using only vocabulary the Shadowdark
# constitution actually declares: `abil_`, `rule_` and `tbl_` prefixes, the
# DERIVED_FROM/FEEDS_INTO/OVERRIDES edge types, and the SD citation code from
# the Shadowdark book registry. Nothing here is copied from AD&D.
EDGE_ROWS = [
    "abil_strength,Strength,DERIVED_FROM,rule_stat_generation,Stat Generation,"
    "initial score,,neutral,derived,SD,15,STATS,explicit_rule,1,core,,,",
    "abil_strength,Strength,FEEDS_INTO,tbl_stat_modifiers,Stat Modifiers Table,"
    "score input,,neutral,derived,SD,15,STAT MODIFIERS TABLE,explicit_rule,1,core,,,",
    "abil_dexterity,Dexterity,DERIVED_FROM,rule_stat_generation,Stat Generation,"
    "initial score,,neutral,derived,SD,15,STATS,explicit_rule,1,core,,,",
    "rule_stat_reroll,Stat Reroll,OVERRIDES,rule_stat_generation,Stat Generation,"
    "generated set,when no stat qualifies,neutral,derived,SD,15,STATS,"
    "explicit_rule,1,optional,optional_variant,,",
]

REGISTERED = [
    ("abil_strength", "Strength", "abil"),
    ("abil_dexterity", "Dexterity", "abil"),
    ("rule_stat_generation", "Stat Generation", "rule"),
    ("rule_stat_reroll", "Stat Reroll", "rule"),
    ("tbl_stat_modifiers", "Stat Modifiers Table", "tbl"),
]

GUP_ID = "GUP-PKT-SD-TEST-genesis-r01"
REVIEW_ID = f"REV-{GUP_ID}-r01"
BUNDLE_ID = f"APPROVED-{GUP_ID}-r01"


def build_genesis_root(target: Path) -> Path:
    """A repository with real Shadowdark governance and no canonical state."""
    for relative in (
        f"rulesets/{GENESIS_RULESET}/governance",
        f"rulesets/{GENESIS_RULESET}/profiles",
        f"rulesets/{GENESIS_RULESET}/registries",
    ):
        shutil.copytree(REPO_ROOT / relative, target / relative, dirs_exist_ok=True)

    # The node registry is authored here rather than copied, because a genesis is
    # defined by an empty one. The first version of this fixture copied the live
    # registry, which was header-only at the time and stopped being so the moment
    # INT-20260922-002 registered ten identities -- so the fixture asserted a fact
    # about the corpus rather than about genesis, and began failing on a
    # successful authorized integration. DEC-2026-0075 states the standing rule
    # this broke: an Integrator fixture that reads live corpus state must assert
    # an invariant that survives integration. Governance above is still copied,
    # because the Constitution and role profile are what make this a *Shadowdark*
    # genesis and neither is changed by integrating a bundle.
    registry_path = target / "rulesets" / GENESIS_RULESET / "registries" / "nodes.csv"
    registry_path.write_bytes(b"id,label,kind,degree,roles\r\n")

    artifacts = target / "books" / GENESIS_RULESET / GENESIS_BOOK / "artifacts"
    (artifacts / "approved").mkdir(parents=True, exist_ok=True)
    (artifacts / "reviews").mkdir(parents=True, exist_ok=True)

    edges_path = artifacts / "approved" / f"{BUNDLE_ID}.edges.csv"
    edges_path.write_bytes(
        ("\r\n".join([EDGE_HEADER, *EDGE_ROWS]) + "\r\n").encode("utf-8"))

    review_path = artifacts / "reviews" / f"{REVIEW_ID}.yaml"
    review_path.write_text(yaml.safe_dump({
        "schema_version": "1.0",
        "id": REVIEW_ID,
        "status": "approved",
        "ruleset_id": GENESIS_RULESET,
        "book_id": GENESIS_BOOK,
        "constitution_version": "1.2",
        "overall_disposition": "approved",
        "approval_ready": True,
        "reviewed_gup": {"id": GUP_ID},
        "summary": {"approved": len(EDGE_ROWS)},
        "reviewer_checklist": {
            "canonical_files_modified": False,
            "gup_files_modified": False,
            "heuristic_or_unset_approved": False,
        },
        "node_registry_decisions": [
            {"proposed_id": node_id, "submitted_label": label, "kind": kind,
             "disposition": "approved"}
            for node_id, label, kind in REGISTERED
        ],
        "handoff": {"next_role": "integrator", "readiness": "ready",
                    "reason": "approved", "blocking_ids": []},
    }, sort_keys=False), encoding="utf-8")

    manifest_path = artifacts / "approved" / f"{BUNDLE_ID}.yaml"
    manifest_path.write_text(yaml.safe_dump({
        "schema_version": "1.0",
        "id": BUNDLE_ID,
        "artifact_kind": "packet_update",
        "status": "approved",
        "ruleset_id": GENESIS_RULESET,
        "book_id": GENESIS_BOOK,
        "constitution_version": "1.2",
        "approves": {
            "review_id": REVIEW_ID,
            "review_checksum": checksum_file(review_path),
            "gup_id": GUP_ID,
        },
        # In a genesis *every* row depends on an identity this same batch
        # registers, because nothing was registered before it. That is what
        # `pending_additions` means, so a genesis manifest legitimately has an
        # empty `additions` list -- and the applier's existing dependency check
        # is what proves the distinction is being honoured rather than bypassed.
        "operation_index": {
            "additions": [],
            "pending_additions": [{"csv_row": n} for n in range(1, len(EDGE_ROWS) + 1)],
        },
        "node_operations": {"count": len(REGISTERED)},
        "components": [{
            "kind": "edges",
            "path": f"books/{GENESIS_RULESET}/{GENESIS_BOOK}/artifacts/approved/"
                    f"{BUNDLE_ID}.edges.csv",
            "checksum": checksum_file(edges_path),
            "rows": len(EDGE_ROWS),
        }],
    }, sort_keys=False), encoding="utf-8")
    return target


def genesis_bundle(root: Path):
    bundles, diagnostics = discover(root, GENESIS_RULESET, GENESIS_BOOK)
    assert not diagnostics, diagnostics
    return next(b for b in bundles if b.bundle_id == BUNDLE_ID)


class GenesisCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = build_genesis_root(Path(self.tmp.name))
        self.paths = CanonicalPaths(root=self.root, ruleset_id=GENESIS_RULESET)
        self.registry_before = checksum_file(self.paths.registry)

    def assertNoCanonicalState(self):
        self.assertFalse(self.paths.canonical_dir.exists(),
                         "a canonical directory exists that nothing authorized")
        for path in (self.paths.edges, self.paths.nodes, self.paths.graph_json):
            self.assertFalse(path.exists(), f"{path.name} exists")


class TestAGenesisFixtureStartsWithNothing(GenesisCase):
    def test_the_fixture_has_no_canonical_state(self):
        self.assertNoCanonicalState()
        self.assertTrue(self.paths.is_genesis)

    def test_the_node_registry_exists_and_is_empty(self):
        """Header-only is the *bootstrap* state, and is not a canonical baseline."""
        rows = [r for r in self.paths.registry.read_text(encoding="utf-8").splitlines() if r]
        self.assertEqual(len(rows), 1, "the bootstrap registry should be header-only")

    def test_the_bundle_passes_every_blocking_precondition(self):
        verification = verify_bundle(genesis_bundle(self.root), self.root)
        self.assertEqual([c.name for c in verification.blocking_failures], [])


class TestReadOnlyPathsCreateNoCanonicalState(GenesisCase):
    """Acceptance test 4. Nothing short of a real transaction may create a file."""

    def test_discovery_creates_nothing(self):
        genesis_bundle(self.root)
        self.assertNoCanonicalState()

    def test_verification_creates_nothing(self):
        verify_bundle(genesis_bundle(self.root), self.root)
        self.assertNoCanonicalState()

    def test_loading_a_genesis_graph_creates_nothing(self):
        graph = CanonicalGraph.load(self.paths, allow_genesis=True)
        self.assertEqual(graph.edges, [])
        self.assertEqual(graph.nodes, [])
        self.assertNoCanonicalState()

    def test_a_dry_run_creates_nothing(self):
        batch = integrate(self.root, GENESIS_RULESET, [genesis_bundle(self.root)],
                          dry_run=True)
        self.assertEqual(len(batch.added), len(EDGE_ROWS))
        self.assertNoCanonicalState()
        self.assertEqual(checksum_file(self.paths.registry), self.registry_before,
                         "a dry run rewrote the node registry")

    def test_loading_without_the_genesis_flag_still_refuses(self):
        """The permissive read is opt-in, so no existing caller starts from empty."""
        with self.assertRaises(FileNotFoundError):
            CanonicalGraph.load(self.paths)


class TestASuccessfulGenesisWritesOnlyWhatWasApproved(GenesisCase):
    """Acceptance test 6: exactly the declared rows, and nothing invented."""

    def setUp(self):
        super().setUp()
        self.batch = integrate(self.root, GENESIS_RULESET, [genesis_bundle(self.root)])

    def test_canonical_state_now_exists(self):
        for path in (self.paths.edges, self.paths.nodes, self.paths.graph_json):
            self.assertTrue(path.exists(), f"{path.name} was not written")

    def test_it_wrote_exactly_the_declared_rows(self):
        rows = read_csv_rows(self.paths.edges)
        self.assertEqual(len(rows), len(EDGE_ROWS))
        self.assertEqual(self.batch.pre_counts["edges"], 0)
        self.assertEqual(self.batch.post_counts["edges"], len(EDGE_ROWS))

    def test_no_row_was_seeded_sampled_or_inferred(self):
        approved = {tuple(line.split(",")[:5]) for line in EDGE_ROWS}
        found = {(r["source_id"], r["source_label"], r["edge_type"],
                  r["target_id"], r["target_label"])
                 for r in read_csv_rows(self.paths.edges)}
        self.assertEqual(found, approved)

    def test_the_registry_holds_exactly_the_approved_registrations(self):
        from adnd1e_integrator.canonical import Registry
        self.assertEqual(Registry.load(self.paths.registry).ids,
                         {node_id for node_id, _, _ in REGISTERED})

    def test_every_node_and_registry_row_has_blank_roles(self):
        """Acceptance test 3: an empty bootstrap profile derives no role.

        Shadowdark's `roles.yaml` declares `thresholds: {}` and `tier2: {}`,
        recording that no corpus-based thresholds exist yet. Empty role fields
        preserve that fact. This fails if the profile is ignored and AD&D's
        thresholds or tier-2 rules are applied by default.
        """
        from adnd1e_integrator.canonical import Registry
        for node in read_csv_rows(self.paths.nodes):
            self.assertEqual(node["roles"], "", f"{node['id']} derived a role")
        for row in Registry.load(self.paths.registry).rows:
            self.assertEqual(row.values["roles"], "", f"{row.values['id']} derived a role")

    def test_the_graph_json_is_reproducible_from_the_rows(self):
        import json
        payload = json.loads(self.paths.graph_json.read_text(encoding="utf-8"))
        self.assertEqual(payload["meta"]["edges"], len(EDGE_ROWS))
        self.assertEqual(payload["meta"]["nodes"], len(read_csv_rows(self.paths.nodes)))
        rebuilt = CanonicalGraph.load(self.paths).to_graph_json()
        self.assertEqual(payload, rebuilt)


class TestALateGenesisFailureRestoresAbsence(GenesisCase):
    """Acceptance test 5, and the defect this change exists to remove.

    The failure is injected *after* the canonical files have been written, at
    the post-write reread, so the rollback has real files to undo rather than a
    transaction that never started.
    """

    def _integrate_with_a_late_failure(self):
        real_load = CanonicalGraph.load
        calls = {"n": 0}

        def flaky(paths, allow_genesis=False):
            calls["n"] += 1
            graph = real_load(paths, allow_genesis=allow_genesis)
            if calls["n"] == 2:  # the post-write reread
                graph.edges = graph.edges + [dict(graph.edges[0])]
            return graph

        with mock.patch.object(CanonicalGraph, "load", staticmethod(flaky)):
            with self.assertRaises(IntegrationError):
                integrate(self.root, GENESIS_RULESET, [genesis_bundle(self.root)])
        self.assertEqual(calls["n"], 2, "the late failure was never reached")

    def test_the_canonical_directory_and_files_are_absent_again(self):
        self._integrate_with_a_late_failure()
        self.assertNoCanonicalState()

    def test_the_registry_is_byte_identical(self):
        self._integrate_with_a_late_failure()
        self.assertEqual(checksum_file(self.paths.registry), self.registry_before)

    def test_no_manifest_report_or_integrated_record_remains(self):
        self._integrate_with_a_late_failure()
        for directory in (self.paths.manifests_dir, self.paths.reports_dir,
                          self.root / "books" / GENESIS_RULESET / GENESIS_BOOK
                          / "artifacts" / "integrated"):
            if directory.exists():
                self.assertEqual(list(directory.iterdir()), [],
                                 f"{directory} retained a generated record")

    def test_no_transaction_snapshot_remains(self):
        self._integrate_with_a_late_failure()
        snapshots = self.root / "build" / "snapshots"
        if snapshots.exists():
            self.assertEqual(list(snapshots.iterdir()), [],
                             "a rolled-back genesis left a snapshot behind")


if __name__ == "__main__":
    unittest.main()
