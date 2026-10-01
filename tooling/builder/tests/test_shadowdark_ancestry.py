"""Shadowdark's `ancestry_` identities and 1.0 revalidation, per DEC-2026-0087.

The Decision's shape matters to how this file is written. `ancestry_` is a
Shadowdark-only prefix: `RulesetVocabulary` already read it from that ruleset's
own constitution, but the compiler's node-proposal checks and governance's
identity discovery still consulted the global AD&D list, so a perfectly valid
`ancestry_dwarf` proposal came back as an unapproved prefix and escalated.
Adding it to the global constants would have fixed that by authorizing the
prefix in two rulesets that never approved it, so the tests below check both
halves: Shadowdark gains it, and adnd1e and basicdnd do not.

Row-level assertions use synthetic fixtures. The two live Shadowdark GURs are
immutable Analyst artifacts and are only ever read, never written, and their
unrelated defects are asserted to remain visible rather than suppressed.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap
from _bootstrap import REPO_ROOT

from adnd1e_builder.compiler import Compiler
from adnd1e_builder.duplicates import CanonicalEdges
from adnd1e_builder.governance import Governance
from adnd1e_builder.registry import NodeRegistry, prefix_of
from adnd1e_builder.vocab import (
    MalformedHistoricalVersionList,
    NODE_PREFIXES,
    RulesetVocabulary,
    constitution_prefixes,
)

DECISION_PATH = (
    REPO_ROOT / "rulesets" / "shadowdark" / "escalations" / "decisions"
    / "DEC-2026-0087.yaml"
)
SHADOWDARK_ROOT = REPO_ROOT / "rulesets" / "shadowdark"


def decision() -> dict:
    return yaml.safe_load(DECISION_PATH.read_text(encoding="utf-8"))


def approved_identities() -> list[dict]:
    """The six identities, read from the Decision rather than transcribed."""
    return decision()["approved_identities"]


def current_constitution_version() -> str:
    """Shadowdark's current constitution version, read from its manifest.

    Transcribing the version these tests were written against turned a
    governance amendment into seven false failures the moment DEC-2026-0089
    raised the constitution to 1.2. What DEC-2026-0087 actually requires is
    that the historical 1.0 inputs stay admissible and that new output
    declares whatever the current version is, so that is what is asserted.
    """
    manifest = yaml.safe_load(
        (SHADOWDARK_ROOT / "ruleset.yaml").read_text(encoding="utf-8"))
    return str(manifest["constitution_version"])


def version_above(version: str) -> str:
    """The next minor version above `version`, which no schema may admit."""
    major, _, minor = version.partition(".")
    return f"{major}.{int(minor) + 1}"


class ShadowdarkCase(unittest.TestCase):
    """A compiler scoped to Shadowdark, with no canonical baseline.

    Shadowdark has no canonical directory and its registry is header-only, which
    is the state DEC-2026-0087 records at ruling. An empty store is constructed
    rather than read so the test cannot create one.
    """

    @classmethod
    def setUpClass(cls):
        cls.vocabulary = RulesetVocabulary.load(REPO_ROOT, "shadowdark")
        cls.registry = NodeRegistry.load(SHADOWDARK_ROOT / "registries" / "nodes.csv")
        cls.canonical = CanonicalEdges(
            path=SHADOWDARK_ROOT / "canonical" / "edges_master.csv")
        cls.governance = Governance.load(SHADOWDARK_ROOT)
        cls.compiler = Compiler(
            cls.registry, cls.canonical, None, cls.governance, cls.vocabulary)

    ENVELOPE = {
        "schema_version": "1.0",
        "id": "GUR-PKT-SD-016-017-ancestries-r01",
        "status": "proposed",
        "ruleset_id": "shadowdark",
        "book_id": "sd",
        "source_id": "sd-steward-intake",
        "packet_id": "PKT-SD-016-017-ancestries",
        "constitution_version": "1.1",
        "revision": 1,
        "page_start": 16,
        "page_end": 17,
    }

    EDGE = {
        "ref": "A1",
        "source_id": "ancestry_dwarf",
        "source_label": "Dwarf",
        "edge_type": "GATES",
        "target_id": "abil_stout",
        "target_label": "Stout",
        "aspect": _bootstrap.FIXTURE_ASPECT,
        "condition": "",
        "book": "SD",
        "page": 16,
        "section": "ANCESTRIES",
        "evidence": "explicit_rule",
        "pass": "page-sweep",
        "status": "core",
        "general_rule_id": "",
        "supersession_basis": "",
        "review_flag": "",
    }

    def compile_gur(self, **overrides):
        document = dict(self.ENVELOPE)
        document.update(overrides)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gur.yaml"
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            return self.compiler.compile(path)

    def node(self, identity, ref="A1"):
        return {
            "proposed_id": identity["id"],
            "proposed_label": identity["label"],
            "why_needed": "fixture",
            "edges_depending_on_it": [ref],
        }

    def benefit(self, identity, ref="A1"):
        return {
            "proposed_id": identity["benefit_id"],
            "proposed_label": identity["benefit_label"],
            "why_needed": "fixture",
            "edges_depending_on_it": [ref],
        }

    def rules(self, result):
        return {f.rule for f in result.findings}

    def proposal(self, result, node_id):
        found = [n for n in result.node_additions if n["proposed_id"] == node_id]
        self.assertEqual(len(found), 1, f"{node_id} was not proposed exactly once")
        return found[0]


class IsolatedShadowdarkCase(ShadowdarkCase):
    """A pre-integration baseline, constructed rather than read.

    DEC-2026-0097. The six ancestry identities were unregistered when
    DEC-2026-0087 was implemented, so proving that `ancestry_` yields an
    ordinary proposal could be done against the live registry. Integration then
    registered all six and those tests began failing -- not because anything
    regressed, but because they asserted that a production identity is
    permanently unregistered, which stops being true precisely when the normal
    lifecycle works. The fresh-proposal path still needs covering, so it is
    covered here against a registry that holds nothing and is never read from
    disk. Canonical reuse of the same identities is a different property and is
    asserted separately, against the real registry, in
    TestRegisteredAncestriesAreReusedNotProposed.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Constructed, not loaded: no file backs this path, so no later
        # integration can change what these tests mean.
        cls.registry = NodeRegistry(
            path=SHADOWDARK_ROOT / "registries" / "isolated-fixture-nodes.csv")
        cls.compiler = Compiler(
            cls.registry, cls.canonical, None, cls.governance, cls.vocabulary)

    def test_the_isolated_baseline_really_is_empty(self):
        """If this ever fails, every fresh-proposal assertion below is vacuous."""
        self.assertEqual(self.registry.nodes, {})
        for identity in approved_identities():
            self.assertNotIn(identity["id"], self.registry)


# ---------------------------------------------------------------------------
# Acceptance test 1 -- governance, verified as an Architect-owned input.
# ---------------------------------------------------------------------------


class TestGovernanceInputs(ShadowdarkCase):
    """The Architect's step-1 files are verified here, never edited."""

    def constitution(self):
        return (SHADOWDARK_ROOT / "governance" / "constitution.md").read_text(
            encoding="utf-8")

    def test_the_constitution_is_at_least_1_1(self):
        line = next(l for l in self.constitution().splitlines()
                    if l.startswith("**Version"))
        version = line.split()[1].strip("*.")
        self.assertGreaterEqual(
            tuple(int(p) for p in version.split(".")), (1, 1), line)

    def test_the_ruleset_manifest_declares_the_same_version(self):
        manifest = yaml.safe_load(
            (SHADOWDARK_ROOT / "ruleset.yaml").read_text(encoding="utf-8"))
        line = next(l for l in self.constitution().splitlines()
                    if l.startswith("**Version"))
        self.assertEqual(str(manifest["constitution_version"]),
                         line.split()[1].strip("*."))

    def test_the_constitution_declares_the_ancestry_prefix(self):
        self.assertIn("ancestry_", self.vocabulary.node_prefixes)
        self.assertIn("`ancestry_`", self.constitution())

    def test_it_distinguishes_ancestry_from_class_creature_and_subsystem(self):
        """The whole point of a dedicated prefix is that these stay separate."""
        text = self.constitution()
        for other in ("class_", "monster_", "sys_"):
            self.assertIn(other, self.vocabulary.node_prefixes)
        self.assertIn("sys_ancestry", text)

    def test_every_approved_identity_and_benefit_appears_in_governance(self):
        text = self.constitution()
        for identity in approved_identities():
            with self.subTest(identity=identity["id"]):
                self.assertIn(identity["id"], text)
                self.assertIn(identity["benefit_id"], text)

    def test_half_orc_is_the_snake_case_identity_with_a_hyphenated_label(self):
        half_orc = next(i for i in approved_identities() if "orc" in i["id"])
        self.assertEqual(half_orc["id"], "ancestry_half_orc")
        self.assertEqual(half_orc["label"], "Half-Orc")

    def test_the_race_registry_stays_inactive(self):
        """The six identities enter through the graph registry, not this one.

        Its prose mentions ancestry to say that nothing has been registered, so
        the check is on its state: empty, inactive, and pointing identity
        authority at nodes.csv.
        """
        registry = yaml.safe_load(
            (SHADOWDARK_ROOT / "registries" / "character_races.yaml").read_text(
                encoding="utf-8"))
        self.assertEqual(registry["status"], "inactive")
        self.assertEqual(registry["members"], [])
        self.assertEqual(registry["membership_policy"]["identity_authority"],
                         "rulesets/shadowdark/registries/nodes.csv")

    def test_historical_1_0_is_admitted_and_the_current_version_is_authored(self):
        current = current_constitution_version()
        self.assertEqual(self.vocabulary.constitution_version, current)
        self.assertIn("1.0", self.vocabulary.accepted_gur_constitution_versions)
        self.assertIn(current, self.vocabulary.accepted_gur_constitution_versions)


# ---------------------------------------------------------------------------
# Acceptance test 2 -- schemas, also Architect-owned inputs.
# ---------------------------------------------------------------------------


class TestSchemaInputs(ShadowdarkCase):
    def validator(self, name):
        from jsonschema import Draft202012Validator

        schema = json.loads(
            (REPO_ROOT / "schemas" / "shadowdark" / "graph" / name).read_text(
                encoding="utf-8"))
        return Draft202012Validator(schema)

    def endpoint_ok(self, node_id, field="source_id"):
        """Whether the edge schema admits one endpoint ID."""
        from jsonschema import Draft202012Validator

        schema = json.loads(
            (REPO_ROOT / "schemas" / "shadowdark" / "graph" / "edge.schema.json")
            .read_text(encoding="utf-8"))
        pattern = schema["properties"][field].get("pattern")
        self.assertIsNotNone(pattern, f"{field} has no closed pattern")
        import re

        return re.match(pattern, node_id) is not None

    def test_both_endpoints_accept_every_approved_ancestry_id(self):
        for identity in approved_identities():
            for field in ("source_id", "target_id"):
                with self.subTest(identity=identity["id"], field=field):
                    self.assertTrue(self.endpoint_ok(identity["id"], field))

    def test_the_hyphenated_form_is_rejected(self):
        """`ancestry_half-orc` is not an alternate ID for the same identity."""
        for field in ("source_id", "target_id"):
            with self.subTest(field=field):
                self.assertFalse(self.endpoint_ok("ancestry_half-orc", field))

    def test_an_unsupported_prefix_is_rejected(self):
        for bad in ("race_dwarf", "ancestor_dwarf", "Ancestry_dwarf"):
            with self.subTest(node_id=bad):
                self.assertFalse(self.endpoint_ok(bad))

    def test_the_open_stem_grammar_is_preserved(self):
        """A misspelling is an identity-review error, not a reason to close the
        stem to six constants: further source-defined ancestries use this kind
        through ordinary workflow."""
        self.assertTrue(self.endpoint_ok("ancestry_halforc"))
        self.assertTrue(self.endpoint_ok("ancestry_some_future_ancestry"))

    def test_artifact_schemas_admit_historical_and_current_versions(self):
        for name in ("gur.schema.json", "gup.schema.json"):
            with self.subTest(schema=name):
                schema = json.loads(
                    (REPO_ROOT / "schemas" / "shadowdark" / "graph" / name)
                    .read_text(encoding="utf-8"))
                versions = schema["properties"]["constitution_version"]["enum"]
                current = current_constitution_version()
                self.assertIn("1.0", versions)
                self.assertIn(current, versions)
                self.assertNotIn(version_above(current), versions)
                # Artifact schema version and constitution version are distinct
                # properties; widening one must not have widened the other.
                self.assertNotIn(
                    "enum", schema["properties"]["schema_version"])

    def test_an_unknown_version_is_still_rejected(self):
        for name in ("gur.schema.json", "gup.schema.json"):
            with self.subTest(schema=name):
                schema = json.loads(
                    (REPO_ROOT / "schemas" / "shadowdark" / "graph" / name)
                    .read_text(encoding="utf-8"))
                enum = schema["properties"]["constitution_version"]["enum"]
                self.assertNotIn(version_above(current_constitution_version()), enum)
                self.assertNotIn("2.0", enum)

    def test_no_other_ruleset_schema_gained_ancestry(self):
        import re

        for ruleset in ("adnd1e", "basicdnd"):
            path = REPO_ROOT / "schemas" / ruleset / "graph" / "edge.schema.json"
            if not path.is_file():
                continue
            with self.subTest(ruleset=ruleset):
                self.assertNotIn("ancestry", path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Acceptance test 3 -- the six node proposals, on synthetic fixtures.
# ---------------------------------------------------------------------------


class TestAncestryNodeProposals(IsolatedShadowdarkCase):
    def test_each_identity_is_proposed_as_an_ordinary_ancestry_node(self):
        for identity in approved_identities():
            with self.subTest(identity=identity["id"]):
                result = self.compile_gur(
                    candidate_nodes=[self.node(identity), self.benefit(identity)],
                    candidate_edges=[dict(
                        self.EDGE,
                        source_id=identity["id"], source_label=identity["label"],
                        target_id=identity["benefit_id"],
                        target_label=identity["benefit_label"],
                        page=identity["page"])],
                )
                proposal = self.proposal(result, identity["id"])
                self.assertEqual(proposal["kind"], "ancestry")
                self.assertTrue(proposal["prefix_approved"])
                self.assertEqual(proposal["proposed_label"], identity["label"])

    def test_an_ancestry_proposal_is_reviewer_approvable_not_an_escalation(self):
        """Before DEC-2026-0087 this raised an unapproved-prefix escalation."""
        identity = approved_identities()[0]
        result = self.compile_gur(
            candidate_nodes=[self.node(identity), self.benefit(identity)],
            candidate_edges=[dict(
                self.EDGE, source_id=identity["id"], source_label=identity["label"],
                target_id=identity["benefit_id"],
                target_label=identity["benefit_label"])],
        )
        self.assertEqual(
            self.proposal(result, identity["id"])["disposition"],
            "reviewer_may_approve")
        self.assertEqual(
            [e for e in result.escalations if e.get("kind") == "node_identity"], [])

    def test_the_named_benefit_is_an_ordinary_ability(self):
        """Benefits are abil_ mechanics, not ancestry properties or copied prose."""
        for identity in approved_identities():
            with self.subTest(benefit=identity["benefit_id"]):
                result = self.compile_gur(
                    candidate_nodes=[self.node(identity), self.benefit(identity)],
                    candidate_edges=[dict(
                        self.EDGE, source_id=identity["id"],
                        source_label=identity["label"],
                        target_id=identity["benefit_id"],
                        target_label=identity["benefit_label"])],
                )
                proposal = self.proposal(result, identity["benefit_id"])
                self.assertEqual(proposal["kind"], "abil")
                self.assertTrue(proposal["prefix_approved"])

    def test_an_ancestry_is_accepted_in_either_endpoint(self):
        identity = approved_identities()[1]
        other = approved_identities()[2]
        result = self.compile_gur(
            candidate_nodes=[self.node(identity), self.node(other)],
            candidate_edges=[dict(
                self.EDGE, source_id=other["id"], source_label=other["label"],
                target_id=identity["id"], target_label=identity["label"],
                edge_type="ALTERNATIVE_TO")],
        )
        for node_id in (identity["id"], other["id"]):
            self.assertTrue(self.proposal(result, node_id)["prefix_approved"])

    def test_the_source_page_and_spelling_are_retained(self):
        for identity in approved_identities():
            with self.subTest(identity=identity["id"]):
                result = self.compile_gur(
                    candidate_nodes=[self.node(identity), self.benefit(identity)],
                    candidate_edges=[dict(
                        self.EDGE, source_id=identity["id"],
                        source_label=identity["label"],
                        target_id=identity["benefit_id"],
                        target_label=identity["benefit_label"],
                        page=identity["page"])],
                )
                self.assertEqual(result.rows[0]["page"], str(identity["page"]))
                self.assertEqual(result.rows[0]["source_label"], identity["label"])

    def test_a_carried_forward_proposal_keeps_its_approved_prefix(self):
        """The carried-forward path consulted the global list too."""
        identity = approved_identities()[3]
        result = self.compile_gur(
            candidate_nodes=[self.node(identity), self.benefit(identity)],
            candidate_edges=[dict(
                self.EDGE, source_id=identity["id"], source_label=identity["label"],
                target_id=identity["benefit_id"],
                target_label=identity["benefit_label"])],
            carried_forward_nodes=[self.node(identity)],
        )
        self.assertTrue(self.proposal(result, identity["id"])["prefix_approved"])


# ---------------------------------------------------------------------------
# Acceptance test 4 -- the scoping itself.
# ---------------------------------------------------------------------------


class TestPrefixScopeIsPerRuleset(unittest.TestCase):
    def test_ancestry_is_approved_only_in_shadowdark(self):
        self.assertIn(
            "ancestry_",
            RulesetVocabulary.load(REPO_ROOT, "shadowdark").node_prefixes)
        for ruleset in ("adnd1e", "basicdnd"):
            with self.subTest(ruleset=ruleset):
                self.assertNotIn(
                    "ancestry_",
                    RulesetVocabulary.load(REPO_ROOT, ruleset).node_prefixes)

    def test_the_global_vocabulary_is_untouched(self):
        """Adding it here would have authorized the prefix everywhere."""
        self.assertNotIn("ancestry_", NODE_PREFIXES)

    def test_prefix_of_defaults_to_the_adnd1e_constants(self):
        self.assertIsNone(prefix_of("ancestry_dwarf"))
        self.assertEqual(prefix_of("class_fighter"), "class_")

    def test_prefix_of_accepts_an_explicit_scope(self):
        shadowdark = RulesetVocabulary.load(REPO_ROOT, "shadowdark").node_prefixes
        self.assertEqual(prefix_of("ancestry_dwarf", shadowdark), "ancestry_")
        self.assertIsNone(prefix_of("bogus_thing", shadowdark))

    def test_the_longest_matching_prefix_wins_deterministically(self):
        """The approved set is a frozenset; iteration order is not guaranteed."""
        scope = frozenset({"ex_", "exp_"})
        for _ in range(8):
            self.assertEqual(prefix_of("exp_level", scope), "exp_")

    def test_governance_discovery_is_scoped_by_ruleset_root(self):
        self.assertIn("ancestry_", constitution_prefixes(SHADOWDARK_ROOT))
        self.assertNotIn(
            "ancestry_", constitution_prefixes(REPO_ROOT / "rulesets" / "adnd1e"))

    def test_governance_falls_back_when_a_ruleset_has_no_constitution(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(constitution_prefixes(Path(tmp)), NODE_PREFIXES)

    def test_a_default_governance_keeps_the_adnd1e_prefixes(self):
        self.assertEqual(Governance().node_prefixes, NODE_PREFIXES)

    def test_each_ruleset_governance_carries_its_own_prefixes(self):
        for ruleset, expected in (("shadowdark", True), ("adnd1e", False),
                                  ("basicdnd", False)):
            with self.subTest(ruleset=ruleset):
                loaded = Governance.load(REPO_ROOT / "rulesets" / ruleset)
                self.assertEqual("ancestry_" in loaded.node_prefixes, expected)


class TestAHeldAncestryIdentityStillBlocks(IsolatedShadowdarkCase):
    """Scoping must not quietly unblock work an open escalation holds.

    Identity discovery reads escalation subjects for node IDs. While it used the
    global AD&D list, an `ancestry_` ID in an open Shadowdark escalation looked
    like ordinary prose: nothing was held, and a proposal the Architect still
    owned would have been offered to the Reviewer as routine. The escalation
    here is synthetic and lives in a temporary tree, so no real package is
    filed, altered or resolved.
    """

    ESCALATION = {
        "schema_version": "1.0",
        "id": "ESC-SD-FIXTURE-0001",
        "status": "pending",
        "ruleset_id": "shadowdark",
        "raised_by": "builder",
        "assigned_by": "architect",
        "topic": "fixture hold on ancestry_dwarf",
        "question": "Is ancestry_dwarf one identity or two?",
        "affected_proposed_ids": ["ancestry_dwarf"],
    }

    def synthetic_root(self, tmp: str, ruleset: str):
        """A ruleset tree holding one pending escalation over an ancestry ID."""
        root = Path(tmp) / ruleset
        (root / "governance").mkdir(parents=True)
        (root / "escalations" / "pending").mkdir(parents=True)
        (root / "escalations" / "decisions").mkdir(parents=True)
        source = REPO_ROOT / "rulesets" / ruleset / "governance" / "constitution.md"
        (root / "governance" / "constitution.md").write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8")
        (root / "escalations" / "pending" / "ESC-SD-FIXTURE-0001.yaml").write_text(
            yaml.safe_dump(self.ESCALATION, sort_keys=False), encoding="utf-8")
        return Governance.load(root)

    def test_the_held_ancestry_identity_is_recognised_in_shadowdark(self):
        with tempfile.TemporaryDirectory() as tmp:
            governance = self.synthetic_root(tmp, "shadowdark")
            held = governance.held_by_package("ancestry_dwarf")
            self.assertIsNotNone(held, "the open escalation did not hold its subject")
            self.assertEqual(held["reserved_escalation_id"], "ESC-SD-FIXTURE-0001")

    def test_the_same_escalation_holds_nothing_under_adnd1e_prefixes(self):
        """Proof the recognition above comes from Shadowdark's own table."""
        with tempfile.TemporaryDirectory() as tmp:
            governance = self.synthetic_root(tmp, "adnd1e")
            self.assertIsNone(governance.held_by_package("ancestry_dwarf"))

    def test_a_held_identity_blocks_its_dependent_registration(self):
        identity = approved_identities()[0]
        with tempfile.TemporaryDirectory() as tmp:
            compiler = Compiler(
                self.registry, self.canonical, None,
                self.synthetic_root(tmp, "shadowdark"), self.vocabulary)
            document = dict(self.ENVELOPE)
            document["candidate_nodes"] = [self.node(identity), self.benefit(identity)]
            document["candidate_edges"] = [dict(
                self.EDGE, source_id=identity["id"], source_label=identity["label"],
                target_id=identity["benefit_id"],
                target_label=identity["benefit_label"])]
            path = Path(tmp) / "gur.yaml"
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            result = compiler.compile(path)

        proposal = self.proposal(result, identity["id"])
        self.assertTrue(proposal["architect_required"])
        self.assertEqual(proposal["disposition"], "requires_architect_decision")
        self.assertIn(
            "node_registration_held_by_package",
            {e.get("kind") for e in result.escalations})
        # The unheld benefit alongside it is unaffected.
        self.assertEqual(
            self.proposal(result, identity["benefit_id"])["disposition"],
            "reviewer_may_approve")


class TestUnsupportedIdentitiesStillFail(IsolatedShadowdarkCase):
    def test_an_unsupported_prefix_is_still_refused(self):
        bogus = {"id": "race_dwarf", "label": "Dwarf",
                 "benefit_id": "abil_stout", "benefit_label": "Stout", "page": 16}
        result = self.compile_gur(
            candidate_nodes=[self.node(bogus), self.benefit(bogus)],
            candidate_edges=[dict(
                self.EDGE, source_id="race_dwarf", target_id="abil_stout")],
        )
        self.assertFalse(self.proposal(result, "race_dwarf")["prefix_approved"])

    def test_a_creature_sharing_a_label_is_not_merged_into_an_ancestry(self):
        """Name similarity must not resolve one identity to the other."""
        result = self.compile_gur(
            candidate_nodes=[
                {"proposed_id": "ancestry_dwarf", "proposed_label": "Dwarf",
                 "why_needed": "fixture", "edges_depending_on_it": ["A1"]},
                {"proposed_id": "monster_dwarf", "proposed_label": "Dwarf",
                 "why_needed": "fixture", "edges_depending_on_it": ["A1"]},
            ],
            candidate_edges=[dict(
                self.EDGE, source_id="ancestry_dwarf", source_label="Dwarf",
                target_id="monster_dwarf", target_label="Dwarf",
                edge_type="CROSS_REFERENCES")],
        )
        proposed = {n["proposed_id"] for n in result.node_additions}
        self.assertEqual(proposed, {"ancestry_dwarf", "monster_dwarf"})
        self.assertEqual(
            self.proposal(result, "ancestry_dwarf")["kind"], "ancestry")
        self.assertEqual(
            self.proposal(result, "monster_dwarf")["kind"], "monster")


# ---------------------------------------------------------------------------
# Acceptance test 5 -- the two immutable 1.0 GURs, read only.
# ---------------------------------------------------------------------------


class TestHistoricalGursRevalidate(ShadowdarkCase):
    """Read-only dry compilation. Nothing is published and nothing is edited."""

    NAMED = (
        "GUR-PKT-SD-011-014-character-overview-and-starting-level-r01",
        "GUR-PKT-SD-015-015-stats-and-stat-modifiers-r01",
    )

    def gur_paths(self):
        directory = REPO_ROOT / "books" / "shadowdark" / "sd" / "artifacts" / "gur"
        return [directory / f"{name}.yaml" for name in self.NAMED]

    def test_the_named_gurs_are_the_decision_s_unaffected_inputs(self):
        self.assertEqual(sorted(self.NAMED),
                         sorted(decision()["compatibility"]["unaffected_inputs"]))

    def test_they_declare_the_historical_version(self):
        for path in self.gur_paths():
            with self.subTest(gur=path.name):
                document = yaml.safe_load(path.read_text(encoding="utf-8"))
                self.assertEqual(str(document["constitution_version"]), "1.0")

    def test_they_dry_compile_without_a_version_mismatch(self):
        for path in self.gur_paths():
            with self.subTest(gur=path.name):
                result = self.compiler.compile(path)
                self.assertNotIn("constitution_version_mismatch", self.rules(result))

    def test_the_older_input_version_is_reported_not_silently_accepted(self):
        for path in self.gur_paths():
            with self.subTest(gur=path.name):
                result = self.compiler.compile(path)
                self.assertIn("constitution_version_older_than_compiler",
                              self.rules(result))

    def test_output_records_the_current_version_and_the_input_version(self):
        for path in self.gur_paths():
            with self.subTest(gur=path.name):
                envelope = self.compiler.compile(path).envelope
                self.assertEqual(envelope["constitution_version"],
                                 current_constitution_version())
                self.assertEqual(envelope["gur_constitution_version"], "1.0")

    def test_unrelated_findings_remain_visible(self):
        """These GURs omit `evidence` on every edge. That defect belongs to the
        Analyst's ordinary lifecycle and must not be suppressed here."""
        result = self.compiler.compile(self.gur_paths()[1])
        self.assertIn("edge_fields_missing", {f.rule for f in result.errors})

    def test_an_unknown_future_version_still_fails(self):
        result = self.compile_gur(constitution_version="9.9")
        self.assertIn("constitution_version_mismatch", self.rules(result))

    def test_the_gurs_and_their_source_are_not_modified(self):
        """The compile above is read-only; these bytes must be untouched."""
        import hashlib

        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.gur_paths()}
        for path in self.gur_paths():
            self.compiler.compile(path)
        for path, digest in before.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_no_canonical_state_is_written(self):
        """Compiling writes no canonical state and disturbs none that exists.

        This asserted that rulesets/shadowdark/canonical was absent, which was
        true when DEC-2026-0087 was implemented and stopped being true when
        INT-20260922-002 created the first Shadowdark canonical files. The
        property the Decision actually requires is that a read-only dry compile
        creates nothing and changes nothing, which holds either way.
        """
        import hashlib

        canonical = SHADOWDARK_ROOT / "canonical"

        def state():
            if not canonical.exists():
                return None
            return {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(canonical.iterdir())
                if path.is_file()
            }

        before = state()
        for path in self.gur_paths():
            self.compiler.compile(path)
        self.assertEqual(state(), before,
                         "compilation must not create or modify canonical state")


class TestOpenScalarFieldsDoNotCrashTheCompiler(ShadowdarkCase):
    """`pass` is open-ended by the constitution, so a GUR may write an integer.

    Both live Shadowdark GURs do. The compiler assumed a string and raised
    AttributeError, which made the Decision's required dry compilation
    impossible on an input it also forbids editing.
    """

    def test_an_integer_pass_compiles(self):
        identity = approved_identities()[0]
        result = self.compile_gur(
            candidate_nodes=[self.node(identity), self.benefit(identity)],
            candidate_edges=[dict(
                self.EDGE, source_id=identity["id"], source_label=identity["label"],
                target_id=identity["benefit_id"],
                target_label=identity["benefit_label"], **{"pass": 1})],
        )
        self.assertEqual(result.rows[0]["pass"], "1")

    def test_coercion_does_not_weaken_a_controlled_vocabulary(self):
        """An integer in a closed field is still illegal, not quietly accepted."""
        identity = approved_identities()[0]
        result = self.compile_gur(
            candidate_nodes=[self.node(identity), self.benefit(identity)],
            candidate_edges=[dict(
                self.EDGE, source_id=identity["id"], source_label=identity["label"],
                target_id=identity["benefit_id"],
                target_label=identity["benefit_label"], evidence=1)],
        )
        self.assertIn("evidence_illegal", self.rules(result))


# ---------------------------------------------------------------------------
# DEC-2026-0090 -- historical 1.1 Shadowdark GUR compatibility.
# ---------------------------------------------------------------------------


class TestHistoricalVersionCompatibility(ShadowdarkCase):
    """DEC-2026-0100: historical GUR-version compatibility is governed, not
    transcribed into Builder code.

    DEC-2026-0087 and DEC-2026-0090 each hand-extended a Shadowdark-specific
    constant in vocab.py, once for 1.0 and once for 1.1 -- and the extension
    was then missed on the next two amendments, stranding every GUR published
    under 1.2 or 1.3 the moment 1.4 became current. DEC-2026-0100 moved the
    set into `rulesets/shadowdark/ruleset.yaml`'s own
    `historical_gur_constitution_versions`, so these tests read that governed
    list rather than transcribing it a second time here -- the same lesson
    `current_constitution_version()` already applies to the current version,
    now applied to the historical set as well.
    """

    def accepted(self):
        return self.vocabulary.accepted_gur_constitution_versions

    def governed_historical_versions(self) -> list[str]:
        manifest = yaml.safe_load(
            (SHADOWDARK_ROOT / "ruleset.yaml").read_text(encoding="utf-8"))
        return [str(v) for v in manifest["historical_gur_constitution_versions"]]

    def test_exactly_the_governed_and_current_versions_are_accepted(self):
        expected = sorted(
            set(self.governed_historical_versions())
            | {current_constitution_version()})
        self.assertEqual(sorted(self.accepted()), expected)

    def test_the_constitution_points_at_the_governed_list_not_a_transcription(self):
        """The accepted set is governed metadata, so this checks that the
        constitution defers to it rather than re-naming specific versions."""
        constitution = " ".join(
            (SHADOWDARK_ROOT / "governance" / "constitution.md")
            .read_text(encoding="utf-8").split())
        self.assertIn("historical_gur_constitution_versions", constitution)
        self.assertIn(
            "remain admissible only with full", constitution)
        self.assertIn("revalidation under the current", constitution)

    def test_every_governed_historical_version_is_admitted(self):
        for version in self.governed_historical_versions():
            with self.subTest(constitution_version=version):
                result = self.compile_gur(constitution_version=version)
                self.assertNotIn(
                    "constitution_version_mismatch", self.rules(result))

    def test_1_2_and_1_3_are_specifically_admitted(self):
        """The exact two versions DEC-2026-0100 exists to unstrand."""
        for version in ("1.2", "1.3"):
            self.assertIn(version, self.governed_historical_versions())
            with self.subTest(constitution_version=version):
                result = self.compile_gur(constitution_version=version)
                self.assertNotIn(
                    "constitution_version_mismatch", self.rules(result))

    def test_a_1_1_gur_compiles_without_a_version_mismatch(self):
        result = self.compile_gur(constitution_version="1.1")
        self.assertNotIn("constitution_version_mismatch", self.rules(result))

    def test_a_1_1_gur_is_still_reported_as_older_than_the_compiler(self):
        """Admitted is not trusted: the older input version stays visible."""
        result = self.compile_gur(constitution_version="1.1")
        self.assertIn("constitution_version_older_than_compiler", self.rules(result))

    def test_a_1_1_gur_stamps_current_output_and_keeps_its_input_version(self):
        envelope = self.compile_gur(constitution_version="1.1").envelope
        self.assertEqual(envelope["constitution_version"],
                         current_constitution_version())
        self.assertEqual(envelope["gur_constitution_version"], "1.1")

    def test_the_current_version_is_not_reported_as_older(self):
        result = self.compile_gur(
            constitution_version=current_constitution_version())
        self.assertNotIn("constitution_version_older_than_compiler",
                         self.rules(result))
        self.assertNotIn("constitution_version_mismatch", self.rules(result))

    def test_an_unknown_version_between_the_historical_ones_still_fails(self):
        """1.0 and 1.1 are admitted because governance names them, not because
        anything below the current version is waved through."""
        for version in ("0.9", version_above(current_constitution_version()), "9.9"):
            with self.subTest(constitution_version=version):
                result = self.compile_gur(constitution_version=version)
                self.assertIn("constitution_version_mismatch", self.rules(result))

    def test_no_other_ruleset_gained_a_historical_version(self):
        from adnd1e_builder.vocab import (
            ACCEPTED_GUR_CONSTITUTION_VERSIONS,
            HISTORICAL_ACCEPTED_GUR_CONSTITUTION_VERSIONS,
        )

        self.assertEqual(
            HISTORICAL_ACCEPTED_GUR_CONSTITUTION_VERSIONS["adnd1e"],
            ACCEPTED_GUR_CONSTITUTION_VERSIONS)
        self.assertNotIn(
            "basicdnd", HISTORICAL_ACCEPTED_GUR_CONSTITUTION_VERSIONS)

    def test_the_immutable_1_0_gurs_are_unaffected(self):
        """The two published 1.0 GURs keep compiling exactly as before."""
        directory = REPO_ROOT / "books" / "shadowdark" / "sd" / "artifacts" / "gur"
        for name in TestHistoricalGursRevalidate.NAMED:
            with self.subTest(gur=name):
                result = self.compiler.compile(directory / f"{name}.yaml")
                self.assertNotIn("constitution_version_mismatch", self.rules(result))
                self.assertEqual(
                    result.envelope["gur_constitution_version"], "1.0")


# ---------------------------------------------------------------------------
# DEC-2026-0100 -- a malformed governed list is a configuration error.
# ---------------------------------------------------------------------------


class TestMalformedGovernedHistoricalVersions(unittest.TestCase):
    """A present-but-invalid `historical_gur_constitution_versions` refuses.

    Constructed synthetic ruleset roots, not the real repository: the point is
    to prove the validator's shape, not to exercise Shadowdark's actual
    manifest, which is asserted well-formed elsewhere.
    """

    def load(self, tmp: str, governed):
        """A minimal registered ruleset declaring the given governed value."""
        root = Path(tmp)
        ruleset_root = root / "rulesets" / "shadowdark"
        ruleset_root.mkdir(parents=True)
        manifest = {
            "ruleset_id": "shadowdark",
            "constitution_version": "1.5",
            "historical_gur_constitution_versions": governed,
        }
        (ruleset_root / "ruleset.yaml").write_text(
            yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
        return RulesetVocabulary.load(root, "shadowdark")

    def test_a_present_valid_list_loads_normally(self):
        with tempfile.TemporaryDirectory() as tmp:
            vocabulary = self.load(tmp, ["1.0", "1.2"])
        self.assertEqual(
            vocabulary.accepted_gur_constitution_versions,
            frozenset({"1.0", "1.2", "1.5"}))

    def test_a_non_dotted_numeric_entry_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(MalformedHistoricalVersionList):
                self.load(tmp, ["1.0", "not-a-version"])

    def test_a_duplicate_entry_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(MalformedHistoricalVersionList):
                self.load(tmp, ["1.0", "1.1", "1.0"])

    def test_an_empty_list_is_refused(self):
        """DEC-2026-0100: a malformed governed list is a configuration error,
        never a silent fallback to the retired hardcoded history."""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(MalformedHistoricalVersionList):
                self.load(tmp, [])

    def test_a_non_list_value_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(MalformedHistoricalVersionList):
                self.load(tmp, "1.0")

    def test_a_malformed_list_does_not_fall_back_to_the_retired_constant(self):
        """The old hardcoded {'1.0', '1.1'} must not reappear as a rescue path
        when the governed field is present but broken."""
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self.load(tmp, ["bad"])
            except MalformedHistoricalVersionList:
                pass
            else:  # pragma: no cover - the assertRaises above already covers this
                self.fail("a malformed list must raise, not silently resolve")

    def test_an_absent_field_falls_back_to_no_shadowdark_entry(self):
        """DEC-2026-0100 retired the hardcoded Shadowdark entry entirely, so a
        manifest declaring no governed list at all has no historical
        compatibility -- the correct default for a newly registered ruleset,
        matching what a brand-new ruleset with no history gets today."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ruleset_root = root / "rulesets" / "shadowdark"
            ruleset_root.mkdir(parents=True)
            (ruleset_root / "ruleset.yaml").write_text(
                yaml.safe_dump({"ruleset_id": "shadowdark",
                               "constitution_version": "1.5"}, sort_keys=False),
                encoding="utf-8")
            vocabulary = RulesetVocabulary.load(root, "shadowdark")
        self.assertEqual(
            vocabulary.accepted_gur_constitution_versions, frozenset({"1.5"}))

    def test_adnd1e_is_unaffected_by_a_missing_governed_list(self):
        """adnd1e has no ruleset.yaml field for this; it must keep using its
        own transcribed constant exactly as before."""
        vocabulary = RulesetVocabulary.load(REPO_ROOT, "adnd1e")
        from adnd1e_builder.vocab import ACCEPTED_GUR_CONSTITUTION_VERSIONS

        self.assertTrue(
            ACCEPTED_GUR_CONSTITUTION_VERSIONS.issubset(
                vocabulary.accepted_gur_constitution_versions))


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# DEC-2026-0091 -- the common candidate-node input shape.
# ---------------------------------------------------------------------------


class TestCandidateNodeSchemaContract(IsolatedShadowdarkCase):
    """The schema and the compiler must agree on what a candidate node is.

    The compiler's fail-closed check and the common schema's required set are
    two statements of one rule. When they drifted apart -- the schema silent,
    the compiler reading fields Shadowdark did not write -- 49 node proposals
    across three packets serialized blank and a Reviewer corrected ten of them
    by hand before anyone noticed the cause.
    """

    def candidate_node_schema(self):
        schema = json.loads(
            (REPO_ROOT / "schemas" / "common" / "gur.schema.json").read_text(
                encoding="utf-8"))
        return schema["$defs"]["candidateNode"]

    def validator(self):
        from jsonschema import Draft202012Validator

        return Draft202012Validator(self.candidate_node_schema())

    COMPLETE = {
        "proposed_id": "ancestry_dwarf",
        "proposed_label": "Dwarf",
        "kind": "ancestry",
        "why_needed": "The packet names it as a playable ancestry.",
    }

    def test_the_schema_requires_all_four_executable_fields(self):
        self.assertEqual(sorted(self.candidate_node_schema()["required"]),
                         ["kind", "proposed_id", "proposed_label", "why_needed"])

    def test_a_complete_candidate_node_validates(self):
        self.assertTrue(self.validator().is_valid(self.COMPLETE))

    def test_omitting_either_registration_field_is_rejected(self):
        for field in ("proposed_label", "why_needed"):
            with self.subTest(omitted=field):
                candidate = {k: v for k, v in self.COMPLETE.items() if k != field}
                self.assertFalse(self.validator().is_valid(candidate))

    def test_a_blank_registration_field_is_rejected(self):
        for field in ("proposed_label", "why_needed"):
            with self.subTest(blank=field):
                self.assertFalse(
                    self.validator().is_valid({**self.COMPLETE, field: ""}))

    def test_the_legacy_spellings_are_rejected_not_accepted_as_aliases(self):
        for spelling in ("label", "evidence"):
            with self.subTest(legacy=spelling):
                self.assertFalse(
                    self.validator().is_valid({**self.COMPLETE, spelling: "anything"}))

    def test_the_compiler_and_the_schema_agree(self):
        """A candidate the schema rejects must not compile to a proposal."""
        identity = approved_identities()[0]
        result = self.compile_gur(
            candidate_nodes=[{"proposed_id": identity["id"],
                              "label": identity["label"]},
                             self.benefit(identity)],
            candidate_edges=[dict(
                self.EDGE, source_id=identity["id"],
                source_label=identity["label"],
                target_id=identity["benefit_id"],
                target_label=identity["benefit_label"])],
        )
        self.assertIn("candidate_node_fields_missing", self.rules(result))
        self.assertNotIn(identity["id"],
                         {n["proposed_id"] for n in result.node_additions})

    def test_the_six_ancestries_still_propose_from_canonical_fields(self):
        """DEC-2026-0087's behaviour is retained under the stricter input."""
        for identity in approved_identities():
            with self.subTest(identity=identity["id"]):
                result = self.compile_gur(
                    candidate_nodes=[self.node(identity), self.benefit(identity)],
                    candidate_edges=[dict(
                        self.EDGE, source_id=identity["id"],
                        source_label=identity["label"],
                        target_id=identity["benefit_id"],
                        target_label=identity["benefit_label"])],
                )
                self.assertNotIn("candidate_node_fields_missing", self.rules(result))
                proposal = self.proposal(result, identity["id"])
                self.assertEqual(proposal["kind"], "ancestry")
                self.assertEqual(proposal["proposed_label"], identity["label"])
                self.assertTrue(proposal["why_needed"])


# ---------------------------------------------------------------------------
# DEC-2026-0097 -- the same identities after integration registered them.
# ---------------------------------------------------------------------------


class TestRegisteredAncestriesAreReusedNotProposed(ShadowdarkCase):
    """Against the real registry, a registered ancestry is reused, not proposed.

    The counterpart to IsolatedShadowdarkCase. DEC-2026-0087 authorized the six
    identities; INT-20260922-002 and the integrations after it registered them.
    Constitution 3.2 says reuse a canonical identity rather than propose it
    again, and the compiler reports node_proposal_resolved_to_canonical for an
    Analyst who read the source rather than the registry. Neither state stands
    in for the other, so both are asserted, and this class reads the live
    registry on purpose: if an identity here is ever absent, these tests should
    fail rather than quietly assert nothing.
    """

    def registered(self):
        """The approved identities the live registry actually holds."""
        return [identity for identity in approved_identities()
                if identity["id"] in self.registry]

    def test_every_approved_ancestry_is_registered_by_now(self):
        """The premise of this class, checked rather than assumed."""
        missing = [identity["id"] for identity in approved_identities()
                   if identity["id"] not in self.registry]
        self.assertEqual(missing, [], "unregistered identities belong in the "
                                      "isolated case, not this one")

    def test_a_registered_ancestry_is_not_proposed_again(self):
        for identity in self.registered():
            with self.subTest(identity=identity["id"]):
                result = self.compile_gur(
                    candidate_nodes=[self.node(identity)],
                    candidate_edges=[dict(
                        self.EDGE, source_id=identity["id"],
                        source_label=identity["label"],
                        target_id=identity["benefit_id"],
                        target_label=identity["benefit_label"])],
                )
                proposed = {n["proposed_id"] for n in result.node_additions}
                self.assertNotIn(identity["id"], proposed)

    def test_the_reuse_is_reported_as_resolved_to_canonical(self):
        for identity in self.registered():
            with self.subTest(identity=identity["id"]):
                result = self.compile_gur(
                    candidate_nodes=[self.node(identity)],
                    candidate_edges=[dict(
                        self.EDGE, source_id=identity["id"],
                        source_label=identity["label"],
                        target_id=identity["benefit_id"],
                        target_label=identity["benefit_label"])],
                )
                self.assertIn("node_proposal_resolved_to_canonical",
                              self.rules(result))

    def test_reuse_is_not_an_error_or_an_escalation(self):
        identity = self.registered()[0]
        result = self.compile_gur(
            candidate_nodes=[self.node(identity)],
            candidate_edges=[dict(
                self.EDGE, source_id=identity["id"],
                source_label=identity["label"],
                target_id=identity["benefit_id"],
                target_label=identity["benefit_label"])],
        )
        self.assertEqual(
            [e for e in result.escalations if e.get("kind") == "node_identity"], [])
        self.assertNotIn("identity_ambiguous", self.rules(result))

    def test_the_registry_keeps_the_label_the_decision_authorized(self):
        for identity in self.registered():
            with self.subTest(identity=identity["id"]):
                self.assertEqual(
                    self.registry.nodes[identity["id"]].label, identity["label"])

    def test_the_registered_kind_is_ancestry(self):
        for identity in self.registered():
            with self.subTest(identity=identity["id"]):
                self.assertEqual(
                    self.registry.nodes[identity["id"]].kind, "ancestry")

    def test_an_edge_onto_a_registered_ancestry_needs_no_registration(self):
        """The point of reuse: the row resolves instead of waiting on Review."""
        identity = self.registered()[0]
        result = self.compile_gur(
            candidate_nodes=[self.node(identity)],
            candidate_edges=[dict(
                self.EDGE, source_id=identity["id"],
                source_label=identity["label"],
                target_id=identity["benefit_id"],
                target_label=identity["benefit_label"])],
        )
        self.assertNotIn("endpoint_unresolved", self.rules(result))


class TestSameLabelIdentitiesStayDistinctAgainstTheRegistry(ShadowdarkCase):
    """`monster_dwarf` is still not `ancestry_dwarf`, now that one is canonical.

    The isolated case proves two fresh proposals do not merge. This is the
    harder direction: one identity is registered and the other is not, which is
    exactly when a label-based resolver would collapse them.
    """

    def compile_pair(self):
        return self.compile_gur(
            candidate_nodes=[
                {"proposed_id": "monster_dwarf", "proposed_label": "Dwarf",
                 "why_needed": "fixture", "edges_depending_on_it": ["A1"]},
            ],
            candidate_edges=[dict(
                self.EDGE, source_id="ancestry_dwarf", source_label="Dwarf",
                target_id="monster_dwarf", target_label="Dwarf",
                edge_type="CROSS_REFERENCES")],
        )

    def test_the_registered_ancestry_is_not_proposed(self):
        proposed = {n["proposed_id"] for n in self.compile_pair().node_additions}
        self.assertNotIn("ancestry_dwarf", proposed)

    def test_the_unregistered_creature_remains_an_ordinary_proposal(self):
        result = self.compile_pair()
        proposal = self.proposal(result, "monster_dwarf")
        self.assertEqual(proposal["kind"], "monster")
        self.assertTrue(proposal["prefix_approved"])
        self.assertEqual(proposal["disposition"], "reviewer_may_approve")

    def test_the_shared_label_does_not_merge_them(self):
        result = self.compile_pair()
        self.assertNotIn("identity_ambiguous", self.rules(result))
        self.assertEqual(
            [e for e in result.escalations if e.get("kind") == "identity_resolution"],
            [])

    def test_the_row_keeps_both_endpoints_as_written(self):
        row = self.compile_pair().rows[0]
        self.assertEqual(row["source_id"], "ancestry_dwarf")
        self.assertEqual(row["target_id"], "monster_dwarf")


# ---------------------------------------------------------------------------
# DEC-2026-0103 -- the three bounded CLASSIFIED_AS shapes and their cardinality.
# ---------------------------------------------------------------------------


class TestBoundedClassifications(IsolatedShadowdarkCase):
    """Constitution section 2.4: only three (source, target, aspect) triples
    are a legal `CLASSIFIED_AS` edge, and a spell has exactly one tier.

    Uses the isolated pre-integration registry: whether `class_wizard` or
    `rule_spell_tier_1` happen to be canonical yet must not change whether a
    classification shape is accepted, so every node here is a fresh proposal.
    """

    CLASS_EDGE = {
        "ref": "C1",
        "source_id": "spell_fireball",
        "source_label": "Fireball",
        "edge_type": "CLASSIFIED_AS",
        "target_id": "class_wizard",
        "target_label": "Wizard",
        "aspect": "casting class",
        "condition": "",
        "book": "SD",
        "page": 59,
        "section": "SPELLS",
        "evidence": "explicit_rule",
        "pass": "page-sweep",
        "status": "core",
        "general_rule_id": "",
        "supersession_basis": "",
        "review_flag": "",
    }

    def tier_edge(self, ref, source_id, target_id, aspect):
        return {**self.CLASS_EDGE, "ref": ref, "source_id": source_id,
                "target_id": target_id, "aspect": aspect}

    def node(self, node_id, label, ref):
        return {"proposed_id": node_id, "proposed_label": label,
                "why_needed": "fixture", "edges_depending_on_it": [ref]}

    # -- the three accepted shapes --------------------------------------------

    def test_spell_to_wizard_casting_class_is_accepted(self):
        result = self.compile_gur(
            candidate_nodes=[self.node("spell_fireball", "Fireball", "C1"),
                             self.node("class_wizard", "Wizard", "C1")],
            candidate_edges=[self.CLASS_EDGE],
        )
        self.assertEqual(self.rules(result) & {
            "classified_as_target_illegal", "classified_as_direction_illegal",
            "classified_as_aspect_illegal"}, set())
        self.assertEqual(len(result.rows), 1)
        self.assertEqual(result.rows[0]["polarity"], "neutral")
        self.assertEqual(result.rows[0]["polarity_basis"], "derived")

    def test_a_spell_may_have_two_casting_classes(self):
        """Cardinality one_or_more: both rows are legal, not a duplicate."""
        edges = [
            self.tier_edge("C1", "spell_fireball", "class_wizard", "casting class"),
            self.tier_edge("C2", "spell_fireball", "class_priest", "casting class"),
        ]
        result = self.compile_gur(
            candidate_nodes=[self.node("spell_fireball", "Fireball", "C1"),
                             self.node("class_wizard", "Wizard", "C1"),
                             self.node("class_priest", "Priest", "C2")],
            candidate_edges=edges,
        )
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(self.rules(result) & {
            "classified_as_duplicate_tier", "classified_as_target_illegal"}, set())

    def test_spell_to_tier_value_is_accepted(self):
        edges = [self.tier_edge("C1", "spell_fireball", "rule_spell_tier_3", "spell tier")]
        result = self.compile_gur(
            candidate_nodes=[self.node("spell_fireball", "Fireball", "C1"),
                             self.node("rule_spell_tier_3", "Tier 3", "C1")],
            candidate_edges=edges,
        )
        self.assertEqual(self.rules(result) & {
            "classified_as_target_illegal", "classified_as_direction_illegal",
            "classified_as_aspect_illegal"}, set())
        self.assertEqual(len(result.rows), 1)

    def test_tier_value_to_aggregate_is_accepted(self):
        edges = [self.tier_edge(
            "C1", "rule_spell_tier_3", "rule_spell_tier", "spell tier category")]
        result = self.compile_gur(
            candidate_nodes=[self.node("rule_spell_tier_3", "Tier 3", "C1"),
                             self.node("rule_spell_tier", "Spell Tier", "C1")],
            candidate_edges=edges,
        )
        self.assertEqual(self.rules(result) & {
            "classified_as_target_illegal", "classified_as_direction_illegal",
            "classified_as_aspect_illegal"}, set())
        self.assertEqual(len(result.rows), 1)

    # -- rejected shapes --------------------------------------------------------

    def test_a_sys_target_is_rejected(self):
        """In production sys_class is already canonical, so the fixture
        proposes it too: the point is that a resolvable, real target is still
        rejected on shape, not that it fails to resolve at all."""
        edges = [self.tier_edge("C1", "spell_fireball", "sys_class", "casting class")]
        result = self.compile_gur(
            candidate_nodes=[self.node("spell_fireball", "Fireball", "C1"),
                             self.node("sys_class", "Class", "C1")],
            candidate_edges=edges,
        )
        self.assertIn("classified_as_target_illegal", self.rules(result))

    def test_a_reversed_edge_is_rejected_as_a_direction_error(self):
        """class_wizard CLASSIFIED_AS spell_fireball, backwards."""
        edges = [self.tier_edge("C1", "class_wizard", "spell_fireball", "casting class")]
        result = self.compile_gur(
            candidate_nodes=[self.node("spell_fireball", "Fireball", "C1"),
                             self.node("class_wizard", "Wizard", "C1")],
            candidate_edges=edges,
        )
        self.assertIn("classified_as_direction_illegal", self.rules(result))
        self.assertNotIn("classified_as_target_illegal", self.rules(result))

    def test_the_wrong_aspect_on_a_legal_pair_is_rejected(self):
        edges = [self.tier_edge("C1", "spell_fireball", "class_wizard", "spell tier")]
        result = self.compile_gur(
            candidate_nodes=[self.node("spell_fireball", "Fireball", "C1"),
                             self.node("class_wizard", "Wizard", "C1")],
            candidate_edges=edges,
        )
        self.assertIn("classified_as_aspect_illegal", self.rules(result))

    def test_an_unsupported_target_kind_is_rejected(self):
        """Nothing whitelists spell-to-item; this must not resolve as any shape."""
        edges = [self.tier_edge("C1", "spell_fireball", "item_wand", "casting class")]
        result = self.compile_gur(
            candidate_nodes=[self.node("spell_fireball", "Fireball", "C1"),
                             self.node("item_wand", "Wand", "C1")],
            candidate_edges=edges,
        )
        self.assertIn("classified_as_target_illegal", self.rules(result))

    def test_a_taxonomy_only_table_target_is_rejected(self):
        edges = [self.tier_edge(
            "C1", "spell_fireball", "tbl_common_languages", "casting class")]
        result = self.compile_gur(
            candidate_nodes=[self.node("spell_fireball", "Fireball", "C1"),
                             self.node("tbl_common_languages", "Common Languages", "C1")],
            candidate_edges=edges,
        )
        self.assertIn("classified_as_target_illegal", self.rules(result))

    # -- cardinality --------------------------------------------------------

    def test_two_tier_classifications_for_one_spell_is_a_duplicate(self):
        edges = [
            self.tier_edge("C1", "spell_fireball", "rule_spell_tier_3", "spell tier"),
            self.tier_edge("C2", "spell_fireball", "rule_spell_tier_4", "spell tier"),
        ]
        result = self.compile_gur(
            candidate_nodes=[self.node("spell_fireball", "Fireball", "C1"),
                             self.node("rule_spell_tier_3", "Tier 3", "C1"),
                             self.node("rule_spell_tier_4", "Tier 4", "C2")],
            candidate_edges=edges,
        )
        self.assertIn("classified_as_duplicate_tier", self.rules(result))

    def test_a_casting_class_with_no_tier_in_the_same_gur_is_missing_tier(self):
        edges = [self.tier_edge("C1", "spell_fireball", "class_wizard", "casting class")]
        result = self.compile_gur(
            candidate_nodes=[self.node("spell_fireball", "Fireball", "C1"),
                             self.node("class_wizard", "Wizard", "C1")],
            candidate_edges=edges,
        )
        self.assertIn("classified_as_tier_missing", self.rules(result))

    def test_casting_class_and_tier_together_has_no_cardinality_finding(self):
        edges = [
            self.tier_edge("C1", "spell_fireball", "class_wizard", "casting class"),
            self.tier_edge("C2", "spell_fireball", "rule_spell_tier_3", "spell tier"),
        ]
        result = self.compile_gur(
            candidate_nodes=[self.node("spell_fireball", "Fireball", "C1"),
                             self.node("class_wizard", "Wizard", "C1"),
                             self.node("rule_spell_tier_3", "Tier 3", "C2")],
            candidate_edges=edges,
        )
        self.assertEqual(self.rules(result) & {
            "classified_as_duplicate_tier", "classified_as_tier_missing"}, set())

    def test_an_unclassified_spell_elsewhere_in_the_gur_is_not_flagged(self):
        """A spell with no CLASSIFIED_AS edge at all needs no tier yet."""
        edges = [
            self.tier_edge("C1", "spell_fireball", "class_wizard", "casting class"),
            self.tier_edge("C2", "spell_fireball", "rule_spell_tier_3", "spell tier"),
            dict(self.EDGE, ref="M1", source_id="spell_magic_missile",
                 source_label="Magic Missile", edge_type="FEEDS_INTO",
                 target_id="cbt_attack_roll", target_label="Attack Roll"),
        ]
        result = self.compile_gur(
            candidate_nodes=[self.node("spell_fireball", "Fireball", "C1"),
                             self.node("class_wizard", "Wizard", "C1"),
                             self.node("rule_spell_tier_3", "Tier 3", "C2"),
                             self.node("spell_magic_missile", "Magic Missile", "M1")],
            candidate_edges=edges,
        )
        self.assertNotIn("classified_as_tier_missing", self.rules(result))

    # -- polarity is not authorable on this type --------------------------------

    def test_authoring_polarity_on_classified_as_is_rejected(self):
        edge = dict(self.CLASS_EDGE, polarity="improves")
        result = self.compile_gur(
            candidate_nodes=[self.node("spell_fireball", "Fireball", "C1"),
                             self.node("class_wizard", "Wizard", "C1")],
            candidate_edges=[edge],
        )
        self.assertIn("polarity_authored_on_derived_type", self.rules(result))
        self.assertEqual(result.rows[0]["polarity"], "neutral")


class TestBoundedItemLightSourceClassification(IsolatedShadowdarkCase):
    """DEC-2026-0104: the one additional bounded shape, `item_` to
    `rule_light_source` with aspect `light source`, at most one per item.

    Isolated registry for the same reason as `TestBoundedClassifications`:
    whether `rule_light_source` happens to be canonical yet must not change
    whether the shape is accepted.
    """

    LIGHT_EDGE = {
        "ref": "L1",
        "source_id": "item_torch",
        "source_label": "Torch",
        "edge_type": "CLASSIFIED_AS",
        "target_id": "rule_light_source",
        "target_label": "Light Source",
        "aspect": "light source",
        "condition": "",
        "book": "SD",
        "page": 85,
        "section": "GEAR",
        "evidence": "explicit_rule",
        "pass": "page-sweep",
        "status": "core",
        "general_rule_id": "",
        "supersession_basis": "",
        "review_flag": "",
    }

    def light_edge(self, ref, source_id, target_id, aspect):
        return {**self.LIGHT_EDGE, "ref": ref, "source_id": source_id,
                "target_id": target_id, "aspect": aspect}

    def node(self, node_id, label, ref):
        return {"proposed_id": node_id, "proposed_label": label,
                "why_needed": "fixture", "edges_depending_on_it": [ref]}

    def test_item_to_light_source_is_accepted(self):
        result = self.compile_gur(
            candidate_nodes=[self.node("item_torch", "Torch", "L1"),
                             self.node("rule_light_source", "Light Source", "L1")],
            candidate_edges=[self.LIGHT_EDGE],
        )
        self.assertEqual(self.rules(result) & {
            "classified_as_target_illegal", "classified_as_direction_illegal",
            "classified_as_aspect_illegal"}, set())
        self.assertEqual(len(result.rows), 1)
        self.assertEqual(result.rows[0]["polarity"], "neutral")
        self.assertEqual(result.rows[0]["polarity_basis"], "derived")

    def test_a_reversed_item_light_source_edge_is_rejected(self):
        edges = [self.light_edge("L1", "rule_light_source", "item_torch", "light source")]
        result = self.compile_gur(
            candidate_nodes=[self.node("item_torch", "Torch", "L1"),
                             self.node("rule_light_source", "Light Source", "L1")],
            candidate_edges=edges,
        )
        self.assertIn("classified_as_direction_illegal", self.rules(result))
        self.assertNotIn("classified_as_target_illegal", self.rules(result))

    def test_a_non_item_source_is_rejected(self):
        """A spell classified as a light source: not an authorized shape."""
        edges = [self.light_edge("L1", "spell_fireball", "rule_light_source", "light source")]
        result = self.compile_gur(
            candidate_nodes=[self.node("spell_fireball", "Fireball", "L1"),
                             self.node("rule_light_source", "Light Source", "L1")],
            candidate_edges=edges,
        )
        self.assertIn("classified_as_target_illegal", self.rules(result))

    def test_a_non_light_target_is_rejected(self):
        """Nothing whitelists item-to-class; this must not resolve as any shape."""
        edges = [self.light_edge("L1", "item_torch", "class_wizard", "light source")]
        result = self.compile_gur(
            candidate_nodes=[self.node("item_torch", "Torch", "L1"),
                             self.node("class_wizard", "Wizard", "L1")],
            candidate_edges=edges,
        )
        self.assertIn("classified_as_target_illegal", self.rules(result))

    def test_the_wrong_aspect_on_a_legal_item_pair_is_rejected(self):
        edges = [self.light_edge("L1", "item_torch", "rule_light_source", "provides light")]
        result = self.compile_gur(
            candidate_nodes=[self.node("item_torch", "Torch", "L1"),
                             self.node("rule_light_source", "Light Source", "L1")],
            candidate_edges=edges,
        )
        self.assertIn("classified_as_aspect_illegal", self.rules(result))

    def test_two_light_source_classifications_for_one_item_is_a_duplicate(self):
        edges = [
            self.light_edge("L1", "item_torch", "rule_light_source", "light source"),
            self.light_edge("L2", "item_torch", "rule_light_source", "light source"),
        ]
        result = self.compile_gur(
            candidate_nodes=[self.node("item_torch", "Torch", "L1"),
                             self.node("rule_light_source", "Light Source", "L1")],
            candidate_edges=edges,
        )
        self.assertIn("classified_as_duplicate_light_source", self.rules(result))

    def test_an_item_needs_no_light_source_classification_at_all(self):
        """DEC-2026-0104: at most one, never a requirement to classify."""
        edges = [
            dict(self.EDGE, ref="M1", source_id="item_rope", source_label="Rope",
                 edge_type="FEEDS_INTO", target_id="rule_climbing",
                 target_label="Climbing"),
        ]
        result = self.compile_gur(
            candidate_nodes=[self.node("item_rope", "Rope", "M1"),
                             self.node("rule_climbing", "Climbing", "M1")],
            candidate_edges=edges,
        )
        self.assertNotIn("classified_as_duplicate_light_source", self.rules(result))

    def test_item_light_source_and_spell_classifications_are_independent(self):
        """DEC-2026-0104 must not disturb DEC-2026-0103 spell cardinality."""
        edges = [
            self.light_edge("L1", "item_torch", "rule_light_source", "light source"),
            self.light_edge("C1", "spell_fireball", "class_wizard", "casting class"),
            self.light_edge("C2", "spell_fireball", "rule_spell_tier_3", "spell tier"),
        ]
        result = self.compile_gur(
            candidate_nodes=[self.node("item_torch", "Torch", "L1"),
                             self.node("rule_light_source", "Light Source", "L1"),
                             self.node("spell_fireball", "Fireball", "C1"),
                             self.node("class_wizard", "Wizard", "C1"),
                             self.node("rule_spell_tier_3", "Tier 3", "C2")],
            candidate_edges=edges,
        )
        self.assertEqual(len(result.rows), 3)
        self.assertEqual(self.rules(result) & {
            "classified_as_target_illegal", "classified_as_direction_illegal",
            "classified_as_aspect_illegal", "classified_as_duplicate_tier",
            "classified_as_tier_missing", "classified_as_duplicate_light_source"},
            set())


class TestClassifiedAsRulesetScoping(unittest.TestCase):
    """DEC-2026-0103: CLASSIFIED_AS is legal only where a ruleset's own
    constitution admits it, and it must not have widened another ruleset's
    vocabulary in code the way an earlier ancestry-style mistake could have.
    """

    def test_classified_as_is_shadowdark_only_in_the_edge_vocabulary(self):
        from adnd1e_builder.vocab import RulesetVocabulary

        shadowdark = RulesetVocabulary.load(REPO_ROOT, "shadowdark")
        adnd1e = RulesetVocabulary.load(REPO_ROOT, "adnd1e")
        basicdnd = RulesetVocabulary.load(REPO_ROOT, "basicdnd")
        self.assertIn("CLASSIFIED_AS", shadowdark.edge_types)
        self.assertNotIn("CLASSIFIED_AS", adnd1e.edge_types)
        self.assertNotIn("CLASSIFIED_AS", basicdnd.edge_types)

    def test_no_other_ruleset_schema_gained_classified_as(self):
        for ruleset in ("adnd1e", "basicdnd"):
            path = REPO_ROOT / "schemas" / ruleset / "graph" / "edge.schema.json"
            if not path.is_file():
                continue
            with self.subTest(ruleset=ruleset):
                self.assertNotIn("CLASSIFIED_AS", path.read_text(encoding="utf-8"))
