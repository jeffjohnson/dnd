"""Universal artifact-envelope and Approved-bundle schemas.

Covers the WORK_QUEUES 1.0 handoff block added to `artifact-envelope.schema.json`
and the new `approved-bundle.schema.json`, including the requirement that
artifacts published before the contract remain valid without those fields.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMON = REPO_ROOT / "schemas" / "common"

ENVELOPE = json.loads((COMMON / "artifact-envelope.schema.json").read_text(encoding="utf-8"))
APPROVED = json.loads((COMMON / "approved-bundle.schema.json").read_text(encoding="utf-8"))

REGISTRY = Registry().with_resource(
    "artifact-envelope.schema.json",
    Resource(contents=ENVELOPE, specification=DRAFT202012),
)

BASE = {
    "schema_version": "1.0",
    "id": "GUP-PKT-PHB-001-002-fixture-r01",
    "status": "proposed",
    "ruleset_id": "adnd1e",
    "constitution_version": "1.4",
}

CHECKSUM = "sha256:" + "0" * 64


def errors(schema: dict, document: dict) -> list[str]:
    return [e.message for e in Draft202012Validator(schema, registry=REGISTRY).iter_errors(document)]


class TestLegacyArtifactsStayValid(unittest.TestCase):
    """`revision`, `supersedes` and `handoff` are optional by design."""

    def test_envelope_without_the_work_queue_block_is_valid(self):
        self.assertEqual(errors(ENVELOPE, dict(BASE)), [])

    def test_none_of_the_three_fields_is_required(self):
        for field in ("revision", "supersedes", "handoff"):
            self.assertNotIn(field, ENVELOPE.get("required", []))

    def test_every_published_artifact_still_validates(self):
        """No artifact in the repository is invalidated by the new fields."""
        patterns = (
            "books/*/*/artifacts/gur/GUR-*.yaml",
            "books/*/*/artifacts/gup/GUP-*.yaml",
            "books/*/*/artifacts/reviews/REV-*.yaml",
        )
        checked = 0
        for pattern in patterns:
            for path in REPO_ROOT.glob(pattern):
                document = yaml.safe_load(path.read_text(encoding="utf-8"))
                if not isinstance(document, dict):
                    continue
                checked += 1
                with self.subTest(artifact=path.name):
                    self.assertEqual(errors(ENVELOPE, document), [], path.name)
        self.assertGreater(checked, 0, "expected published artifacts to check")


class TestRevisionAndSupersedes(unittest.TestCase):
    def test_first_revision_supersedes_nothing(self):
        self.assertEqual(errors(ENVELOPE, dict(BASE, revision=1, supersedes=None)), [])

    def test_first_revision_may_not_name_a_predecessor(self):
        self.assertTrue(errors(ENVELOPE, dict(BASE, revision=1, supersedes="GUP-x-r00")))

    def test_later_revision_requires_supersedes(self):
        self.assertTrue(errors(ENVELOPE, dict(BASE, revision=2)))
        self.assertTrue(errors(ENVELOPE, dict(BASE, revision=2, supersedes=None)))

    def test_later_revision_with_supersedes_is_valid(self):
        self.assertEqual(
            errors(ENVELOPE, dict(BASE, revision=5, supersedes="GUP-x-r04")), []
        )

    def test_revision_is_a_positive_integer(self):
        self.assertTrue(errors(ENVELOPE, dict(BASE, revision=0, supersedes=None)))
        self.assertTrue(errors(ENVELOPE, dict(BASE, revision="2", supersedes="GUP-x-r01")))


class TestHandoff(unittest.TestCase):
    def ready(self, **overrides):
        block = {
            "next_role": "reviewer",
            "readiness": "ready",
            "reason": "compiled clean",
            "blocking_ids": [],
        }
        block.update(overrides)
        return dict(BASE, handoff=block)

    def test_ready_handoff_is_valid(self):
        self.assertEqual(errors(ENVELOPE, self.ready()), [])

    def test_all_four_fields_are_required(self):
        for field in ("next_role", "readiness", "reason", "blocking_ids"):
            document = self.ready()
            del document["handoff"][field]
            with self.subTest(missing=field):
                self.assertTrue(errors(ENVELOPE, document))

    def test_role_vocabulary_is_closed(self):
        self.assertTrue(errors(ENVELOPE, self.ready(next_role="operator")))
        for role in ("analyst", "builder", "reviewer", "architect", "integrator", "none"):
            with self.subTest(role=role):
                document = self.ready(next_role=role)
                if role == "none":
                    continue
                self.assertEqual(errors(ENVELOPE, document), [])

    def test_readiness_vocabulary_is_closed(self):
        self.assertTrue(errors(ENVELOPE, self.ready(readiness="pending")))

    def test_blocked_must_name_a_blocker(self):
        self.assertTrue(
            errors(ENVELOPE, self.ready(next_role="architect", readiness="blocked",
                                        blocking_ids=[]))
        )
        self.assertEqual(
            errors(ENVELOPE, self.ready(next_role="architect", readiness="blocked",
                                        blocking_ids=["ESC-2026-07-30T01.02.03.004Z"])),
            [],
        )

    def test_ready_work_has_nothing_outstanding(self):
        self.assertTrue(errors(ENVELOPE, self.ready(blocking_ids=["ESC-x"])))

    def test_terminal_means_no_downstream_role(self):
        self.assertEqual(
            errors(ENVELOPE, self.ready(next_role="none", readiness="terminal")), []
        )
        self.assertTrue(
            errors(ENVELOPE, self.ready(next_role="reviewer", readiness="terminal"))
        )

    def test_unknown_handoff_fields_are_rejected(self):
        document = self.ready()
        document["handoff"]["owner"] = "someone"
        self.assertTrue(errors(ENVELOPE, document))


class TestApprovedBundle(unittest.TestCase):
    def bundle(self, **overrides):
        document = {
            "schema_version": "1.0",
            "id": "APPROVED-GUP-PKT-PHB-001-006-preamble-r02-r01",
            "status": "approved",
            "ruleset_id": "adnd1e",
            "constitution_version": "1.4",
            "approves": {
                "review_id": "REV-GUP-PKT-PHB-001-006-preamble-r02-r01",
                "review_checksum": CHECKSUM,
                "gup_id": "GUP-PKT-PHB-001-006-preamble-r02",
                "gup_checksum": CHECKSUM,
            },
            "components": [
                {
                    "kind": "edges",
                    "path": "books/adnd1e/phb/artifacts/approved/x.edges.csv",
                    "checksum": CHECKSUM,
                    "rows": 0,
                }
            ],
        }
        document.update(overrides)
        return document

    def test_minimal_bundle_is_valid(self):
        self.assertEqual(errors(APPROVED, self.bundle()), [])

    def test_envelope_fields_are_inherited(self):
        document = self.bundle()
        del document["ruleset_id"]
        self.assertTrue(errors(APPROVED, document))

    def test_id_follows_the_work_queues_form(self):
        self.assertTrue(errors(APPROVED, self.bundle(id="APPROVED-something")))
        self.assertTrue(
            errors(APPROVED, self.bundle(id="APPROVED-GUP-PKT-PHB-001-006-preamble-r02"))
        )

    def test_provenance_names_both_review_and_gup(self):
        for field in ("review_id", "gup_id"):
            document = self.bundle()
            del document["approves"][field]
            with self.subTest(missing=field):
                self.assertTrue(errors(APPROVED, document))

    def test_provenance_ids_are_shaped(self):
        self.assertTrue(
            errors(APPROVED, self.bundle(approves={"review_id": "nope",
                                                   "gup_id": "GUP-x-r01"}))
        )

    def test_gur_lineage_may_be_carried_through(self):
        document = self.bundle()
        document["approves"]["gur_id"] = "GUR-PKT-PHB-001-006-preamble-r02"
        self.assertEqual(errors(APPROVED, document), [])

    def test_components_are_required_and_non_empty(self):
        self.assertTrue(errors(APPROVED, self.bundle(components=[])))
        document = self.bundle()
        del document["components"]
        self.assertTrue(errors(APPROVED, document))

    def test_component_kind_is_closed(self):
        self.assertTrue(
            errors(APPROVED, self.bundle(components=[
                {"kind": "manifest", "path": "x", "checksum": CHECKSUM}
            ]))
        )

    def test_every_component_is_checksummed(self):
        self.assertTrue(
            errors(APPROVED, self.bundle(components=[{"kind": "edges", "path": "x"}]))
        )

    def test_checksum_form_is_enforced(self):
        for bad in ("deadbeef", "sha256:xyz", "sha256:" + "0" * 63, "SHA256:" + "0" * 64):
            with self.subTest(checksum=bad):
                self.assertTrue(
                    errors(APPROVED, self.bundle(components=[
                        {"kind": "edges", "path": "x", "checksum": bad}
                    ]))
                )

    def test_duplicate_components_are_rejected(self):
        component = {"kind": "edges", "path": "x", "checksum": CHECKSUM}
        self.assertTrue(errors(APPROVED, self.bundle(components=[component, dict(component)])))

    def test_integration_link_marks_the_bundle_consumed(self):
        document = self.bundle()
        document["integration"] = {"integration_id": "INT-20260730-001"}
        self.assertEqual(errors(APPROVED, document), [])
        document["integration"] = {"integration_id": "20260730-1"}
        self.assertTrue(errors(APPROVED, document))


class TestSchemasAreWellFormed(unittest.TestCase):
    def test_every_common_schema_is_a_valid_draft_2020_12_schema(self):
        for path in sorted(COMMON.glob("*.schema.json")):
            with self.subTest(schema=path.name):
                Draft202012Validator.check_schema(
                    json.loads(path.read_text(encoding="utf-8"))
                )


if __name__ == "__main__":
    unittest.main()


class TestImplementationArtifactsValidate(unittest.TestCase):
    """Every published implementation report and Review, against its own schema.

    The envelope sweep above never covered these two kinds, so nothing checked
    them automatically and a shape the schema forbids -- `validation_report`
    nested inside `validation`, a `cwd` key on a command -- survived across
    several revisions until a Reviewer read one by hand. A schema is only worth
    what is validated against it.
    """

    KINDS = (
        ("rulesets/*/decision-implementations/IMP-*.yaml",
         "decision-implementation.schema.json"),
        ("rulesets/*/decision-implementation-reviews/REV-IMP-*.yaml",
         "decision-implementation-review.schema.json"),
    )

    def full_registry(self):
        resources = []
        for path in sorted(COMMON.glob("*.json")):
            contents = json.loads(path.read_text(encoding="utf-8"))
            resources.append((path.name, Resource(contents=contents, specification=DRAFT202012)))
        return Registry().with_resources(resources)

    @staticmethod
    def active_leaves(paths):
        """The newest revision of each lineage.

        Superseded revisions are immutable history. Several were published
        before the schema was tightened and cannot be corrected -- a Decision
        that governs one of them says so explicitly -- so requiring the whole
        archive to satisfy today's schema would make the rule unenforceable and
        the test permanently red. The active leaf is what routes work, so that
        is what must be clean.
        """
        leaves: dict[str, tuple[int, Path, dict]] = {}
        for path in sorted(paths):
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                continue
            identifier = str(document.get("id") or path.stem)
            lineage, _, revision = identifier.rpartition("-r")
            try:
                number = int(revision)
            except ValueError:
                lineage, number = identifier, 0
            if number >= leaves.get(lineage, (-1,))[0]:
                leaves[lineage] = (number, path, document)
        return [(path, document) for _, path, document in leaves.values()]

    def test_every_active_implementation_artifact_validates(self):
        registry = self.full_registry()
        checked = 0
        for pattern, schema_name in self.KINDS:
            schema = json.loads((COMMON / schema_name).read_text(encoding="utf-8"))
            validator = Draft202012Validator(schema, registry=registry)
            for path, document in self.active_leaves(REPO_ROOT.glob(pattern)):
                checked += 1
                with self.subTest(artifact=path.name):
                    found = [
                        f"{list(e.path)}: {e.message}"
                        for e in validator.iter_errors(document)
                    ]
                    self.assertEqual(found, [], path.name)
        self.assertGreater(checked, 0, "expected published implementation artifacts")
