"""Universal artifact-envelope and Approved-bundle schemas.

Covers the WORK_QUEUES 1.0 handoff block added to `artifact-envelope.schema.json`
and the new `approved-bundle.schema.json`, including the requirement that
artifacts published before the contract remain valid without those fields.
"""

from __future__ import annotations

import functools
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


PUBLISHED_PATTERNS = (
    "books/*/*/artifacts/gur/GUR-*.yaml",
    "books/*/*/artifacts/gup/GUP-*.yaml",
    "books/*/*/artifacts/reviews/REV-*.yaml",
)


@functools.lru_cache(maxsize=1)
def _published_artifacts() -> dict[Path, dict]:
    """Every published packet-workflow artifact, by path.

    Cached because several tests need the whole set: parsing ~150 YAML files per
    test made the suite noticeably slower than the work it was doing.
    """
    found: dict[Path, dict] = {}
    for pattern in PUBLISHED_PATTERNS:
        for path in sorted(REPO_ROOT.glob(pattern)):
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(document, dict):
                found[path] = document
    return found


def _repaired_by_successor(
    path: Path, document: dict, published: dict[Path, dict]
) -> bool:
    """Whether a published artifact's invalidity has been superseded away.

    DEC-2026-0039 and ARTIFACT_LIFECYCLE 1.9 forbid editing, moving or deleting a
    published artifact: a mis-authored one is repaired only by an immutable
    successor revision. That leaves the predecessor permanently invalid on disk,
    so a repository-wide validation has to distinguish an artifact that is
    *currently wrong* from one that has already been corrected.

    Three conditions, all required, and each denied by a test in
    `TestSupersededExemptionIsNarrow`:

    1. every error is inside `handoff` -- queue-derivation metadata, which
       WORK_QUEUES already does not read from a superseded revision. An error in
       identity, provenance or proposals is never excused;
    2. some published artifact names this one in `supersedes`; and
    3. that successor validates completely.

    Nothing here is inferred from status, name or position in a lineage.
    """
    locations = [
        list(e.absolute_path)
        for e in Draft202012Validator(ENVELOPE, registry=REGISTRY).iter_errors(document)
    ]
    if not locations:
        return False
    if any(not location or location[0] != "handoff" for location in locations):
        return False

    artifact_id = str(document.get("id") or path.stem)
    for successor_path, successor in published.items():
        if successor_path == path:
            continue
        if str(successor.get("supersedes") or "") != artifact_id:
            continue
        if not errors(ENVELOPE, successor):
            return True
    return False


class TestLegacyArtifactsStayValid(unittest.TestCase):
    """`revision`, `supersedes` and `handoff` are optional by design."""

    def test_envelope_without_the_work_queue_block_is_valid(self):
        self.assertEqual(errors(ENVELOPE, dict(BASE)), [])

    def test_none_of_the_three_fields_is_required(self):
        for field in ("revision", "supersedes", "handoff"):
            self.assertNotIn(field, ENVELOPE.get("required", []))

    def test_every_published_artifact_still_validates(self):
        """No artifact in the repository is invalidated by the new fields.

        One exemption, defined by `repaired_by_successor` below: a superseded
        revision whose only invalidity is in its `handoff` block and whose
        successor validates. Governance forbids editing a published artifact, so
        without it a single mis-authored handoff would fail this suite forever --
        and because an approval-ready Decision implementation report requires
        passing validation evidence, forever would have meant seven approved
        Decisions permanently unimplementable.
        """
        published = _published_artifacts()
        self.assertTrue(published, "expected published artifacts to check")
        for path, document in published.items():
            found = errors(ENVELOPE, document)
            if found and _repaired_by_successor(path, document, published):
                continue
            with self.subTest(artifact=path.name):
                self.assertEqual(found, [], path.name)

    def test_the_exemption_is_reported_rather_than_silent(self):
        """An exemption that accumulates unnoticed is a hole, not an allowance."""
        published = _published_artifacts()
        exempt = sorted(
            path.name
            for path, document in published.items()
            if errors(ENVELOPE, document)
            and _repaired_by_successor(path, document, published)
        )
        self.assertEqual(
            exempt,
            ["GUR-PKT-UA-015-015-cavaliers-r02.yaml"],
            "the exempt set changed; a new invalid artifact needs a ruling, not a pass",
        )

    def test_the_exempt_artifact_is_invalid_only_in_its_handoff(self):
        published = _published_artifacts()
        path = next(
            p for p in published if p.name == "GUR-PKT-UA-015-015-cavaliers-r02.yaml"
        )
        found = [
            list(e.absolute_path)
            for e in Draft202012Validator(ENVELOPE, registry=REGISTRY).iter_errors(
                published[path]
            )
        ]
        self.assertTrue(found)
        for location in found:
            self.assertEqual(location[0], "handoff", location)

    def test_the_exempt_artifact_has_a_valid_successor(self):
        published = _published_artifacts()
        successor = next(
            document
            for path, document in published.items()
            if path.name == "GUR-PKT-UA-015-015-cavaliers-r03.yaml"
        )
        self.assertEqual(errors(ENVELOPE, successor), [])
        self.assertEqual(successor["supersedes"], "GUR-PKT-UA-015-015-cavaliers-r02")


class TestSupersededExemptionIsNarrow(unittest.TestCase):
    """Each condition of the exemption, denied one at a time.

    A guard nobody has tried to break is a guard nobody knows the shape of. Every
    case here is an artifact the suite must still fail.
    """

    BROKEN_HANDOFF = {"next_role": None, "readiness": "withdrawn",
                      "reason": "superseded", "blocking_ids": []}
    GOOD_HANDOFF = {"next_role": "none", "readiness": "terminal",
                    "reason": "superseded by a replacement packet", "blocking_ids": []}

    def lineage(self, *, predecessor_extra=None, successor=True, successor_valid=True,
                successor_names_it=True):
        stale = Path("books/adnd1e/ua/artifacts/gur/GUR-FIXTURE-r01.yaml")
        predecessor = dict(
            BASE,
            id="GUR-FIXTURE-r01",
            revision=1,
            supersedes=None,
            handoff=self.BROKEN_HANDOFF,
        )
        predecessor.update(predecessor_extra or {})
        published = {stale: predecessor}
        if successor:
            document = dict(
                BASE,
                id="GUR-FIXTURE-r02",
                revision=2,
                supersedes="GUR-FIXTURE-r01" if successor_names_it else "GUR-OTHER-r01",
                handoff=self.GOOD_HANDOFF if successor_valid else self.BROKEN_HANDOFF,
            )
            published[Path("books/adnd1e/ua/artifacts/gur/GUR-FIXTURE-r02.yaml")] = document
        return stale, published

    def exempt(self, **kwargs):
        stale, published = self.lineage(**kwargs)
        return _repaired_by_successor(stale, published[stale], published)

    def test_the_intended_case_is_exempt(self):
        self.assertTrue(self.exempt())

    def test_a_leaf_with_no_successor_is_not_exempt(self):
        """Nothing has repaired it, so it is live work, not history."""
        self.assertFalse(self.exempt(successor=False))

    def test_a_successor_that_names_another_predecessor_is_not_exempt(self):
        self.assertFalse(self.exempt(successor_names_it=False))

    def test_a_successor_that_is_itself_invalid_repairs_nothing(self):
        self.assertFalse(self.exempt(successor_valid=False))

    def test_an_error_outside_the_handoff_is_not_exempt(self):
        """Only queue-derivation metadata is excused; semantics never are."""
        self.assertFalse(self.exempt(predecessor_extra={"revision": 0}))
        self.assertFalse(self.exempt(predecessor_extra={"schema_version": 1.0}))

    def test_a_valid_artifact_is_never_routed_through_the_exemption(self):
        stale, published = self.lineage()
        published[stale]["handoff"] = self.GOOD_HANDOFF
        self.assertEqual(errors(ENVELOPE, published[stale]), [])


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


REVIEW = json.loads((COMMON / "review.schema.json").read_text(encoding="utf-8"))

REVIEW_BASE = {
    "schema_version": "1.0",
    "id": "REV-GUP-PKT-PHB-999-999-fixture-r01-r01",
    "status": "revision_required",
    "ruleset_id": "adnd1e",
    "constitution_version": "1.8",
}


class TestReviewDispositionVocabulary(unittest.TestCase):
    """DEC-2026-0051: four legal per-row dispositions, checked at publication.

    `approved_but_excluded_from_bundle` conflated two independent facts. Whether
    a row is correct is the Reviewer's judgment; whether it lands in an Approved
    edge component is packaging, derived from the GUP's approved/pending/blocked
    components under DEC-2026-0047. The illusionist lineage is what happens
    without this check: the term validated at publication, travelled through the
    Review, and was first read as unknown when the Builder tried to compile
    against it several artifacts later.

    The check is opt-in on `review_contract_version: '1.1'` so the 111 Reviews
    published before the ruling stay valid history rather than retroactively
    becoming defects.
    """

    LEGAL = ["approved", "approved_with_revision", "rejected", "architect_escalation"]
    ILLEGAL = "approved_but_excluded_from_bundle"

    def review(self, **overrides):
        return dict(REVIEW_BASE, **overrides)

    # -- the opt-in boundary -------------------------------------------------

    def test_a_legacy_review_without_the_field_is_untouched(self):
        """Immutable history must not become invalid because a rule arrived."""
        document = self.review(
            edge_decisions=[{"ref": "M1", "disposition": self.ILLEGAL}]
        )
        self.assertEqual(errors(REVIEW, document), [])

    def test_a_legacy_review_is_untouched_in_the_mapping_shape_too(self):
        document = self.review(row_decisions={"M1": {"disposition": self.ILLEGAL}})
        self.assertEqual(errors(REVIEW, document), [])

    def test_another_declared_version_does_not_opt_in(self):
        document = self.review(
            review_contract_version="1.0",
            edge_decisions=[{"ref": "M1", "disposition": self.ILLEGAL}],
        )
        self.assertEqual(errors(REVIEW, document), [])

    # -- enforcement under 1.1 ----------------------------------------------

    def test_every_legal_disposition_is_accepted(self):
        for disposition in self.LEGAL:
            with self.subTest(disposition=disposition):
                document = self.review(
                    review_contract_version="1.1",
                    edge_decisions=[{"ref": "M1", "disposition": disposition}],
                )
                self.assertEqual(errors(REVIEW, document), [])

    def test_the_invalid_disposition_is_rejected_in_edge_decisions(self):
        document = self.review(
            review_contract_version="1.1",
            edge_decisions=[{"ref": "M1", "disposition": self.ILLEGAL}],
        )
        self.assertTrue(errors(REVIEW, document))

    def test_the_invalid_disposition_is_rejected_in_row_decisions(self):
        document = self.review(
            review_contract_version="1.1",
            row_decisions=[{"ref": "M1", "disposition": self.ILLEGAL}],
        )
        self.assertTrue(errors(REVIEW, document))

    def test_both_published_shapes_are_checked(self):
        """A list of decisions and a mapping of them are both in use.

        Checking one and silently passing the other is exactly how an invalid
        value survives a validator, so the mapping form is pinned here too.
        """
        document = self.review(
            review_contract_version="1.1",
            edge_decisions={"M1": {"disposition": self.ILLEGAL}},
        )
        self.assertTrue(errors(REVIEW, document))

    def test_any_unknown_disposition_is_rejected_not_just_the_named_one(self):
        document = self.review(
            review_contract_version="1.1",
            row_decisions=[{"ref": "M1", "disposition": "approved_pending_packaging"}],
        )
        self.assertTrue(errors(REVIEW, document))

    def test_one_bad_row_among_good_ones_is_still_rejected(self):
        document = self.review(
            review_contract_version="1.1",
            edge_decisions=[
                {"ref": "M1", "disposition": "approved"},
                {"ref": "M2", "disposition": "rejected"},
                {"ref": "M3", "disposition": self.ILLEGAL},
            ],
        )
        self.assertTrue(errors(REVIEW, document))

    # -- what the check must not touch --------------------------------------

    def test_a_grouped_summary_is_not_a_per_row_disposition(self):
        """`edge_decisions: {approved_refs: [...]}` states no row judgment.

        The migration Reviews use these keys for grouped summaries. Requiring a
        disposition there would fail artifacts that never claimed to carry one.
        """
        document = self.review(
            review_contract_version="1.1",
            edge_decisions={"approved_refs": ["canonical_row_27", "canonical_row_102"]},
        )
        self.assertEqual(errors(REVIEW, document), [])

    def test_a_row_carrying_no_disposition_is_left_alone(self):
        document = self.review(
            review_contract_version="1.1",
            edge_decisions=[{"ref": "M1", "rationale": "still being written"}],
        )
        self.assertEqual(errors(REVIEW, document), [])

    def test_other_review_fields_are_unconstrained(self):
        document = self.review(
            review_contract_version="1.1",
            edge_decisions=[{
                "ref": "M1",
                "disposition": "approved",
                "source_locus": "PHB p94",
                "rationale": "verified against the page",
            }],
            packaging_evidence={"blocked_component": "x.blocked.csv"},
        )
        self.assertEqual(errors(REVIEW, document), [])


class TestPublishedReviewsStillValidate(unittest.TestCase):
    """The live corpus, which is what the opt-in exists to protect."""

    def reviews(self):
        return sorted(
            (REPO_ROOT / "books" / "adnd1e").glob("*/artifacts/reviews/*.yaml")
        )

    def test_every_published_review_validates(self):
        offenders = {}
        for path in self.reviews():
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            found = errors(REVIEW, document)
            if found:
                offenders[path.name] = found[0]
        self.assertEqual(offenders, {})

    def test_the_corpus_is_not_empty(self):
        self.assertGreater(len(self.reviews()), 50)
