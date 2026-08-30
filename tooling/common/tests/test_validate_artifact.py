"""The staged preflight: refuse before the write, and read nothing else.

Six malformed YAML artifacts reached durable publication in three days, each
needing its own checksummed Architect exception because a published artifact
cannot be edited or withdrawn. All six failed the same way -- hand-assembled
text where a `: ` inside a value, or a line of continuation prose, silently
changes the document's shape.

These cases drive both halves of DEC-2026-0072's rule: the check catches that
class, and the check does not read the repository while doing it.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tooling" / "common"))

from validate_artifact import main, validate_staged  # noqa: E402

SCHEMAS = REPO_ROOT / "schemas" / "common"


class StagedPreflightCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.schema = self.root / "fixture.schema.json"
        self.schema.write_text(json.dumps({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["id", "status"],
            "properties": {
                "id": {"type": "string"},
                "status": {"enum": ["proposed", "approved"]},
            },
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def stage(self, text):
        path = self.root / "staged.yaml"
        path.write_text(text, encoding="utf-8")
        return path

    # -- what it accepts ------------------------------------------------------

    def test_a_valid_mapping_passes(self):
        staged = self.stage("id: X-1\nstatus: approved\n")
        self.assertEqual(validate_staged(staged, self.schema), [])

    def test_a_quoted_colon_value_passes(self):
        """The safe way to write the thing that keeps breaking."""
        staged = self.stage('id: X-1\nstatus: approved\nnote: "a: colon"\n')
        self.assertEqual(validate_staged(staged, self.schema), [])

    def test_a_block_scalar_passes(self):
        staged = self.stage(
            "id: X-1\nstatus: approved\nnote: >-\n  a: colon and\n  a continuation\n"
        )
        self.assertEqual(validate_staged(staged, self.schema), [])

    # -- the defect class it exists for --------------------------------------

    def test_an_unquoted_colon_space_is_refused(self):
        staged = self.stage("id: X-1\nstatus: approved\nnote: a: colon\n")
        reasons = validate_staged(staged, self.schema)
        self.assertTrue(reasons)
        self.assertIn("not valid YAML", reasons[0])

    def test_continuation_prose_is_refused(self):
        """The exact shape of the Bards and DEC-2026-0065 Review failures."""
        staged = self.stage(
            "id: X-1\nstatus: approved\n"
            "This successor consumes the record\n"
            "and keeps going: without a key\n"
        )
        reasons = validate_staged(staged, self.schema)
        self.assertTrue(reasons)
        self.assertIn("not valid YAML", reasons[0])

    def test_the_reason_names_the_file(self):
        staged = self.stage("id: X-1\nnote: a: colon\n")
        self.assertIn(str(staged), validate_staged(staged, self.schema)[0])

    # -- other refusals -------------------------------------------------------

    def test_a_non_mapping_root_is_refused(self):
        for text, kind in (("- one\n- two\n", "list"), ("just a string\n", "str")):
            with self.subTest(text=text):
                reasons = validate_staged(self.stage(text), self.schema)
                self.assertTrue(reasons)
                self.assertIn("must be a mapping", reasons[0])

    def test_an_empty_document_is_refused(self):
        reasons = validate_staged(self.stage(""), self.schema)
        self.assertTrue(reasons)
        self.assertIn("must be a mapping", reasons[0])

    def test_a_schema_failure_is_refused_and_located(self):
        staged = self.stage("id: X-1\nstatus: withdrawn\n")
        reasons = validate_staged(staged, self.schema)
        self.assertEqual(len(reasons), 1)
        self.assertIn("status", reasons[0])

    def test_every_schema_failure_is_reported(self):
        staged = self.stage("status: withdrawn\n")
        self.assertEqual(len(validate_staged(staged, self.schema)), 2)

    def test_a_missing_staged_file_is_refused(self):
        reasons = validate_staged(self.root / "absent.yaml", self.schema)
        self.assertIn("does not exist", reasons[0])

    def test_a_missing_schema_is_refused(self):
        staged = self.stage("id: X-1\nstatus: approved\n")
        reasons = validate_staged(staged, self.root / "absent.schema.json")
        self.assertTrue(reasons)
        self.assertIn("named explicitly", reasons[0])

    def test_an_unresolved_schema_reference_is_refused(self):
        """A schema whose $ref has no sibling to resolve against."""
        schema = self.root / "dangling.schema.json"
        schema.write_text(json.dumps({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "allOf": [{"$ref": "not-here.schema.json"}],
        }), encoding="utf-8")
        reasons = validate_staged(self.stage("id: X-1\n"), schema)
        self.assertTrue(reasons)

    # -- what it must not do --------------------------------------------------

    def test_it_writes_nothing(self):
        """Deciding to publish is the caller's; this only says whether it may."""
        staged = self.stage("id: X-1\nnote: a: colon\n")
        before = sorted(path.name for path in self.root.iterdir())
        validate_staged(staged, self.schema)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), before)

    def test_it_reads_no_corpus(self):
        """Target-only. A preflight that reads the repository would make every
        publication depend on the repository being healthy -- the coupling that
        turned one bad Review into five broken suites."""
        opened = []
        original = Path.read_text

        def watched(self, *args, **kwargs):
            opened.append(self)
            return original(self, *args, **kwargs)

        staged = self.stage("id: X-1\nstatus: approved\n")
        Path.read_text = watched
        try:
            validate_staged(staged, self.schema)
        finally:
            Path.read_text = original

        for path in opened:
            with self.subTest(path=str(path)):
                self.assertTrue(
                    path == staged or path.parent == self.root,
                    f"the preflight read {path}, which is neither the staged file "
                    f"nor its named schema",
                )

    # -- the command ----------------------------------------------------------

    def test_the_command_exits_zero_on_success(self):
        staged = self.stage("id: X-1\nstatus: approved\n")
        self.assertEqual(
            main([str(staged), "--schema", str(self.schema), "--quiet"]), 0
        )

    def test_the_command_exits_one_on_refusal(self):
        staged = self.stage("id: X-1\nnote: a: colon\n")
        self.assertEqual(main([str(staged), "--schema", str(self.schema)]), 1)

    def test_the_schema_is_required_rather_than_inferred(self):
        """A filename is a claim about what an artifact is; the caller knows."""
        staged = self.stage("id: X-1\nstatus: approved\n")
        with self.assertRaises(SystemExit):
            main([str(staged)])


class RealSchemaCase(unittest.TestCase):
    """The preflight against the repository's own schemas and artifacts."""

    def test_a_published_review_passes_its_own_schema(self):
        staged = (
            REPO_ROOT / "books/adnd1e/phb/artifacts/reviews"
            / "REV-GUP-PKT-PHB-117-119-bards-r04-r03.yaml"
        )
        self.assertEqual(
            validate_staged(staged, SCHEMAS / "review.schema.json"), []
        )

    def test_the_bards_r02_would_have_been_refused(self):
        """The check that would have prevented DEC-2026-0068 from being needed."""
        staged = (
            REPO_ROOT / "books/adnd1e/phb/artifacts/reviews"
            / "REV-GUP-PKT-PHB-117-119-bards-r04-r02.yaml"
        )
        reasons = validate_staged(staged, SCHEMAS / "review.schema.json")
        self.assertTrue(reasons)
        self.assertIn("not valid YAML", reasons[0])

    def test_the_0065_review_would_have_been_refused(self):
        """And the one that made DEC-2026-0072 necessary."""
        staged = (
            REPO_ROOT / "rulesets/adnd1e/decision-implementation-reviews"
            / "REV-IMP-DEC-2026-0065-r01-r01.yaml"
        )
        reasons = validate_staged(
            staged, SCHEMAS / "decision-implementation-review.schema.json"
        )
        self.assertTrue(reasons)
        self.assertIn("not valid YAML", reasons[0])

    def test_every_schema_in_the_repository_can_be_applied(self):
        """A schema that cannot load makes the preflight unusable for its kind."""
        staged = REPO_ROOT / "rulesets/adnd1e/escalations/decisions/DEC-2026-0072.yaml"
        for schema in sorted(SCHEMAS.glob("*.json")):
            with self.subTest(schema=schema.name):
                reasons = validate_staged(staged, schema)
                for reason in reasons:
                    self.assertNotIn("could not be applied", reason)
                    self.assertNotIn("could not be loaded", reason)


if __name__ == "__main__":
    unittest.main()
