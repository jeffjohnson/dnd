"""DEC-2026-0014 acceptance tests for the production edge schema.

The decision corrected `schemas/adnd1e/graph/edge.schema.json` to the
constitutional 18-column row and explicitly refused to migrate production data
to match the defective schema. It names the Builder as owner of
`schema_regression_tests_and_full_corpus_validation`, which is this module.

These tests are read-only. They validate the canonical corpus and the active
GUP bundles; nothing here writes to the graph.

The decision's own figures were taken when the corpus held 3,809 rows. Approved
bundles have integrated since, so the totals are derived rather than asserted.
What the decision actually fixed is the *shape* of the known migration debt --
53 rows, 60 errors, three unprefixed IDs, seven blank labels at each end -- and
that is asserted exactly.
"""

from __future__ import annotations

import csv
import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path

import _bootstrap
from _bootstrap import REPO_ROOT

from jsonschema import Draft202012Validator
from jsonschema.validators import validator_for

from adnd1e_builder.vocab import COLUMNS

SCHEMA_PATH = REPO_ROOT / "schemas" / "adnd1e" / "graph" / "edge.schema.json"
CANONICAL_PATH = REPO_ROOT / "rulesets" / "adnd1e" / "canonical" / "edges_master.csv"
REGISTRY_PATH = REPO_ROOT / "rulesets" / "adnd1e" / "registries" / "nodes.csv"
GUP_DIR = REPO_ROOT / "books" / "adnd1e" / "phb" / "artifacts" / "gup"
APPROVED_DIR = REPO_ROOT / "books" / "adnd1e" / "phb" / "artifacts" / "approved"

# DEC-2026-0014, `migration_required: false` / `known_preexisting_validation_debt`.
# Legacy rows that predate DEC-2026-0004 prefixing and carry blank labels. The
# decision rules these are fixed through ordinary workflow, not by weakening the
# schema, so they are pinned here to keep the debt from growing unnoticed.
DEBT_ROWS = 53
DEBT_ERRORS = 60
DEBT_UNPREFIXED_SOURCE = 18
DEBT_UNPREFIXED_TARGET = 28
DEBT_BLANK_SOURCE_LABELS = 7
DEBT_BLANK_TARGET_LABELS = 7
DEBT_IDS = frozenset({"comeliness", "fatigue", "training"})

VALID_ROW = {
    "source_id": "abil_strength",
    "source_label": "Strength",
    "edge_type": "GATES",
    "target_id": "class_fighter",
    "target_label": "Fighter",
    "aspect": "class eligibility",
    "condition": "",
    "polarity": "enables",
    "polarity_basis": "derived",
    "book": "PHB",
    "page": "9",
    "section": "STRENGTH",
    "evidence": "explicit_rule",
    "pass": "page-sweep",
    "status": "core",
    "supersession_basis": "",
    "general_rule_id": "",
    "review_flag": "",
}


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def canonical_rows() -> list[dict]:
    with CANONICAL_PATH.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def leaf_gup_edge_csvs() -> list[Path]:
    """The highest revision of each packet's edge CSV.

    DEC-2026-0014 validated the six bundles that raised the escalation. Pinning
    those filenames would rot at the next revision, so the active leaf of every
    packet is checked instead -- a superset that stays true as the pipeline
    advances.
    """
    by_packet: dict[str, tuple[int, Path]] = {}
    for path in GUP_DIR.glob("GUP-*.edges.csv"):
        stem = path.name[: -len(".edges.csv")]
        packet, _, revision = stem.rpartition("-r")
        rank = int(revision) if revision.isdigit() else -1
        if packet not in by_packet or rank > by_packet[packet][0]:
            by_packet[packet] = (rank, path)
    return sorted(path for _, path in by_packet.values())


class TestSchemaShape(unittest.TestCase):
    def test_schema_is_a_valid_draft_2020_12_schema(self):
        schema = load_schema()
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        validator_for(schema).check_schema(schema)

    def test_required_is_the_eighteen_column_row_in_canonical_order(self):
        required = load_schema()["required"]
        self.assertEqual(len(required), 18)
        self.assertEqual(len(set(required)), 18, "required repeats a field name")
        self.assertEqual(required, list(COLUMNS))

    def test_required_matches_the_canonical_header_order(self):
        with CANONICAL_PATH.open(encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle))
        self.assertEqual(load_schema()["required"], header)

    def test_artifact_scope_fields_are_not_production_edge_fields(self):
        schema = load_schema()
        for field in ("ruleset_id", "book_id"):
            self.assertNotIn(field, schema["required"])
            self.assertNotIn(field, schema["properties"])

    def test_book_is_a_per_row_field_with_the_closed_citation_vocabulary(self):
        self.assertEqual(
            load_schema()["properties"]["book"]["enum"], ["PHB", "DMG", "MM", "UA"]
        )


class TestRowValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = Draft202012Validator(load_schema())

    def assert_valid(self, row):
        self.assertEqual(list(self.validator.iter_errors(row)), [])

    def assert_invalid(self, row, field=None):
        errors = list(self.validator.iter_errors(row))
        self.assertTrue(errors, "expected the row to be rejected")
        if field is not None:
            paths = {".".join(str(p) for p in e.path) for e in errors}
            self.assertIn(field, paths)

    def test_a_representative_eighteen_field_row_validates(self):
        self.assert_valid(VALID_ROW)

    def test_both_endpoints_reject_an_unprefixed_node_id(self):
        for field in ("source_id", "target_id"):
            with self.subTest(field=field):
                self.assert_invalid({**VALID_ROW, field: "comeliness"}, field=field)

    def test_book_rejects_a_value_outside_the_vocabulary(self):
        self.assert_invalid({**VALID_ROW, "book": "OA"}, field="book")

    def test_artifact_scope_fields_are_rejected_inside_a_row(self):
        for field in ("ruleset_id", "book_id"):
            with self.subTest(field=field):
                self.assert_invalid({**VALID_ROW, field: "adnd1e"})

    def test_a_nineteenth_field_is_rejected(self):
        self.assert_invalid({**VALID_ROW, "confidence": "high"})

    def test_a_missing_field_is_rejected(self):
        row = dict(VALID_ROW)
        del row["book"]
        self.assert_invalid(row)


class TestFullCorpus(unittest.TestCase):
    """The audit DEC-2026-0014 assigns to the Builder."""

    @classmethod
    def setUpClass(cls):
        validator = Draft202012Validator(load_schema())
        cls.rows = canonical_rows()
        cls.failures: list[tuple[int, dict, list]] = []
        for number, row in enumerate(cls.rows, start=2):
            errors = list(validator.iter_errors(row))
            if errors:
                cls.failures.append((number, row, errors))

    def error_fields(self) -> Counter:
        return Counter(
            ".".join(str(p) for p in error.path)
            for _, _, errors in self.failures
            for error in errors
        )

    def test_the_corpus_is_not_empty(self):
        self.assertGreater(len(self.rows), 3800)

    def test_every_row_outside_the_known_debt_validates(self):
        self.assertEqual(len(self.rows) - len(self.failures), len(self.rows) - DEBT_ROWS)

    def test_the_debt_is_exactly_the_rows_and_errors_the_decision_recorded(self):
        self.assertEqual(len(self.failures), DEBT_ROWS)
        self.assertEqual(sum(len(e) for _, _, e in self.failures), DEBT_ERRORS)

    def test_the_debt_is_only_unprefixed_endpoints_and_blank_labels(self):
        self.assertEqual(
            self.error_fields(),
            Counter(
                {
                    "source_id": DEBT_UNPREFIXED_SOURCE,
                    "target_id": DEBT_UNPREFIXED_TARGET,
                    "source_label": DEBT_BLANK_SOURCE_LABELS,
                    "target_label": DEBT_BLANK_TARGET_LABELS,
                }
            ),
        )

    def test_the_unprefixed_ids_are_only_the_three_dec_2026_0004_named(self):
        seen = {
            row[field]
            for _, row, errors in self.failures
            for field in ("source_id", "target_id")
            for error in errors
            if ".".join(str(p) for p in error.path) == field
        }
        self.assertEqual(seen, set(DEBT_IDS))

    def test_the_blank_labels_are_blank_rather_than_malformed(self):
        for _, row, errors in self.failures:
            for error in errors:
                field = ".".join(str(p) for p in error.path)
                if field in ("source_label", "target_label"):
                    self.assertEqual(row[field], "")


class TestGupBundles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = Draft202012Validator(load_schema())
        cls.csvs = leaf_gup_edge_csvs()

    def test_there_are_gup_bundles_to_check(self):
        self.assertGreaterEqual(len(self.csvs), 6)

    def test_every_leaf_gup_header_matches_the_schema_field_set(self):
        for path in self.csvs:
            with self.subTest(bundle=path.name):
                with path.open(encoding="utf-8", newline="") as handle:
                    header = next(csv.reader(handle))
                self.assertEqual(header, list(COLUMNS))

    def test_every_leaf_gup_row_validates(self):
        for path in self.csvs:
            with path.open(encoding="utf-8", newline="") as handle:
                for number, row in enumerate(csv.DictReader(handle), start=2):
                    errors = list(self.validator.iter_errors(row))
                    with self.subTest(bundle=path.name, row=number):
                        self.assertEqual([e.message for e in errors], [])

    def test_every_approved_bundle_row_validates(self):
        for path in sorted(APPROVED_DIR.glob("APPROVED-*.edges.csv")):
            with path.open(encoding="utf-8", newline="") as handle:
                for number, row in enumerate(csv.DictReader(handle), start=2):
                    errors = list(self.validator.iter_errors(row))
                    with self.subTest(bundle=path.name, row=number):
                        self.assertEqual([e.message for e in errors], [])


class TestAuditIsReadOnly(unittest.TestCase):
    """DEC-2026-0014: no canonical, registry, GUP or Approved component is
    modified by this decision. Validation must never be a write path."""

    def test_validating_the_corpus_does_not_change_it(self):
        watched = [CANONICAL_PATH, REGISTRY_PATH, *leaf_gup_edge_csvs()]
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}

        validator = Draft202012Validator(load_schema())
        for row in canonical_rows():
            list(validator.iter_errors(row))

        after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
