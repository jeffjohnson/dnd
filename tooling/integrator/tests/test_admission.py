"""DEC-2026-0065: Decision-governed admission of unreadable Reviews.

One Review in this repository is permanently unreadable YAML. DEC-2026-0064 pins
it as historical evidence; DEC-2026-0065 says the Integrator may omit its bytes
only after re-deriving that record itself, and must otherwise fail closed rather
than skip a parse failure quietly.

The distinction these tests hold is between *trusted history* and *a broken
queue*. Both involve a file that will not parse. Only one of them is safe, and
the difference is an active Decision that still matches the bytes on disk.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap
from _bootstrap import REPO_ROOT, RULESET_ID

from adnd1e_integrator.admission import (
    FATAL_CODE, INFORMATIONAL_CODE, load_admission)
from adnd1e_integrator.bundles import discover, ready_queue

BARDS = "APPROVED-GUP-PKT-PHB-117-119-bards-r04-r01"
BARDS_SUCCESSOR = "APPROVED-GUP-PKT-PHB-117-119-bards-r04-r03"
DIRECT_GOVERNING = "DEC-2026-0068"
#: DEC-2026-0070 supersedes DEC-2026-0069, so it is the active delegator. Naming
#: the superseded one here made every mutation below deny for the wrong reason:
#: the field-level checks never ran, and 0070's untouched pin caught the edit.
DIRECT_DELEGATING = "DEC-2026-0070"
DIRECT_UNREADABLE = ("books/adnd1e/phb/artifacts/reviews/"
                     "REV-GUP-PKT-PHB-117-119-bards-r04-r02.yaml")
GOVERNING = "DEC-2026-0064"
DELEGATING = "DEC-2026-0065"
UNREADABLE = "books/adnd1e/phb/artifacts/reviews/REV-GUP-PKT-PHB-054-064-druid-spells-r01-r04.yaml"
DECISIONS = f"rulesets/{RULESET_ID}/escalations/decisions"
BOOKS = ["phb"]


def clone(target: Path) -> Path:
    for relative in [
        f"rulesets/{RULESET_ID}/canonical",
        f"rulesets/{RULESET_ID}/registries",
        f"rulesets/{RULESET_ID}/profiles",
        f"rulesets/{RULESET_ID}/governance",
        f"rulesets/{RULESET_ID}/escalations",
        f"rulesets/{RULESET_ID}/reports",
        f"rulesets/{RULESET_ID}/manifests",
        f"books/{RULESET_ID}/phb/artifacts",
        "schemas",
        "build/reports",
    ]:
        source = REPO_ROOT / relative
        if source.exists():
            shutil.copytree(source, target / relative, dirs_exist_ok=True)
    return target


def repair_record(root: Path) -> tuple[Path, dict, dict]:
    """The governing Decision document and its single repair record."""
    path = root / DECISIONS / f"{GOVERNING}.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return path, document, document["review_malformed_lineage_repairs"][0]


def rewrite(path: Path, document: dict) -> None:
    path.write_text(yaml.safe_dump(document, sort_keys=False, width=92,
                                   allow_unicode=True), encoding="utf-8")


def repin_direct(root: Path, governing_path: Path) -> None:
    """Re-pin DEC-2026-0069 to an edited DEC-2026-0068.

    Without this every mutation that edits the governing Decision would be caught
    by the delegation checksum alone, and the field-level check actually under
    test would never run.
    """
    from adnd1e_integrator.admission import sha256_of
    path = root / DECISIONS / f"{DIRECT_DELEGATING}.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["governing_direct_predecessor_repair_record"]["decision_input"]["checksum"] =         sha256_of(governing_path)
    rewrite(path, document)


def cli(root: Path, *argv: str) -> subprocess.CompletedProcess:
    # `--books` takes nargs="*", so the space-separated form swallows the
    # subcommand that follows it. The `=` form binds exactly one value and
    # leaves the rest of the command line alone. Without this every CLI
    # assertion below passes on argparse's own exit 2 rather than on the
    # behaviour under test.
    return subprocess.run(
        [sys.executable, "-m", "adnd1e_integrator.cli", "--repo-root", str(root),
         f"--books={BOOKS[0]}", *argv],
        capture_output=True, text=True,
        env={**os.environ,
             "PYTHONPATH": str(REPO_ROOT / "tooling" / "integrator" / "src")},
    )


class TestTheAuthorisedException(unittest.TestCase):
    """Acceptance test 1: the pinned bridge is admitted, and only as history."""

    def test_the_queue_returns_without_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = ready_queue(clone(Path(tmp)), RULESET_ID, BOOKS)
            self.assertEqual(queue["queue_integrity"], [])

    def test_one_informational_notice_names_the_decision_and_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = ready_queue(clone(Path(tmp)), RULESET_ID, BOOKS)
            reviews = {Path(n["path"]).name: n for n in queue["informational"]
                       if n["code"] == INFORMATIONAL_CODE}
            self.assertEqual(set(reviews), {Path(UNREADABLE).name,
                                            Path(DIRECT_UNREADABLE).name})
            notices = reviews
            self.assertEqual(notices[Path(UNREADABLE).name]["authorised_by"], GOVERNING)
            self.assertEqual(notices[Path(DIRECT_UNREADABLE).name]["authorised_by"],
                             DIRECT_GOVERNING)

    def test_no_content_of_the_unreadable_review_is_recovered(self):
        """The notice may name the file. It may not carry what is inside it."""
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            queue = ready_queue(root, RULESET_ID, BOOKS)
            rendered = json.dumps(queue["informational"])
            for fragment in ("Source-supported but omitted", "row_decisions",
                             "rationale", "disposition"):
                self.assertNotIn(fragment, rendered)

    def test_unrelated_bundles_are_still_classified_normally(self):
        """Every discovered bundle still reaches exactly one ordinary bucket.

        Which bucket a given bundle lands in is the corpus's business and moves
        as Reviews and rejections are published. What admission must not do is
        drop a bundle on the floor because some unrelated Review is unreadable.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            queue = ready_queue(root, RULESET_ID, BOOKS)
            classified = [b.bundle_id for b in queue["ready"]]
            classified += [b.bundle_id for b, _ in queue["integrated"]]
            classified += [b.bundle_id for b in queue["superseded"]]
            classified += [b.bundle_id for b, _ in queue["rejected"]]
            # DEC-2026-0070: the withheld historical bundle is accounted for
            # outside the buckets, and must still be accounted for.
            withheld = [n["bundle_id"] for n in queue["informational"]
                        if n["code"] == "historical_unadmitted_bundle"]
            discovered = {b.bundle_id for b in discover(root, RULESET_ID, "phb")[0]}
            self.assertEqual(sorted(classified), sorted(set(classified)),
                             "a bundle reached two buckets")
            self.assertEqual(set(classified) & set(withheld), set())
            self.assertEqual(set(classified) | set(withheld), discovered)
            self.assertIn(BARDS, discovered)

    def test_history_alone_does_not_fail_the_queue(self):
        """Acceptance test 4: a notice is not a diagnostic."""
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            result = cli(root, "queue")
            self.assertNotEqual(result.returncode, 2, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["queue_integrity"], [])
            self.assertEqual(payload["diagnostics"], [])
            codes = sorted(n["code"] for n in payload["informational"])
            self.assertEqual(codes, ["historical_unadmitted_bundle",
                                     "historical_unreadable_review",
                                     "historical_unreadable_review"])


class TestEveryConditionThatDeniesTheException(unittest.TestCase):
    """Acceptance test 2: what invalidates the record invalidates admission.

    Each case leaves the unreadable file exactly as it is and breaks one piece of
    the evidence for it. The record is a claim about the corpus; if any part of
    the claim no longer holds, the exception it buys is withdrawn.
    """

    def _assert_denied(self, mutate, *, expect: str | None = None):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            mutate(root)

            queue = ready_queue(root, RULESET_ID, BOOKS)
            self.assertTrue(queue["queue_integrity"], "expected a fatal diagnostic")
            self.assertEqual([e["code"] for e in queue["queue_integrity"]],
                             [FATAL_CODE] * len(queue["queue_integrity"]))
            self.assertEqual(queue["ready"], [], "no bundle may be offered")
            # The denied file must not also be filed as history. Other lawful
            # exceptions are unaffected: denying one Decision's record says
            # nothing about another's, and asserting an empty list here would
            # quietly require the two to be coupled.
            self.assertNotIn(Path(UNREADABLE).name,
                             {Path(n["path"]).name for n in queue["informational"]},
                             "a denied file is never also history")
            if expect:
                self.assertIn(expect, json.dumps(queue["queue_integrity"]))

            result = cli(root, "queue")
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_an_absent_governing_decision(self):
        def mutate(root):
            (root / DECISIONS / f"{GOVERNING}.yaml").unlink()
        self._assert_denied(mutate)

    def test_an_inactive_governing_decision(self):
        def mutate(root):
            path, document, _ = repair_record(root)
            document["status"] = "superseded"
            rewrite(path, document)
        self._assert_denied(mutate)

    def test_a_changed_governing_decision_checksum(self):
        """The delegating Decision pins the governing one by hash."""
        def mutate(root):
            path, document, _ = repair_record(root)
            document["decision_date"] = "1970-01-01"
            rewrite(path, document)
        self._assert_denied(mutate)

    def test_a_missing_repair_record(self):
        def mutate(root):
            path, document, _ = repair_record(root)
            document["review_malformed_lineage_repairs"] = []
            rewrite(path, document)
            self._repin(root, path)
        self._assert_denied(mutate)

    def test_a_wrong_disposition(self):
        def mutate(root):
            path, document, record = repair_record(root)
            record["disposition"] = "historical_note"
            rewrite(path, document)
            self._repin(root, path)
        self._assert_denied(mutate, expect="disposition")

    def test_a_mismatched_pinned_artifact(self):
        def mutate(root):
            path, document, record = repair_record(root)
            record["bridge_review"]["checksum"] = "sha256:" + "0" * 64
            rewrite(path, document)
            self._repin(root, path)
        self._assert_denied(mutate, expect="bridge_review")

    def test_a_parseable_unreadable_review(self):
        """If the file now parses, the bridge is describing a repair not needed."""
        def mutate(root):
            target = root / UNREADABLE
            text = target.read_text(encoding="utf-8")
            target.write_text(text.replace(
                "rationale: Source-supported but omitted:",
                "rationale: Source-supported but omitted -"), encoding="utf-8")
        self._assert_denied(mutate)

    def test_a_wrong_parser_failure_fragment(self):
        def mutate(root):
            path, document, record = repair_record(root)
            record["unreadable_review"]["parse_failure"]["message_fragment"] = \
                "found undefined alias"
            rewrite(path, document)
            self._repin(root, path)
        self._assert_denied(mutate, expect="expects the parser to fail with")

    def test_a_broken_bridge_link(self):
        def mutate(root):
            path, document, record = repair_record(root)
            record["bridge_review"]["required_supersedes"] = \
                "REV-GUP-PKT-PHB-054-064-druid-spells-r01-r02"
            rewrite(path, document)
            self._repin(root, path)
        self._assert_denied(mutate, expect="supersedes")

    def test_a_wrong_successor_handoff(self):
        def mutate(root):
            path, document, record = repair_record(root)
            record["active_successor_review"]["required_handoff"]["next_role"] = "integrator"
            rewrite(path, document)
            self._repin(root, path)
        self._assert_denied(mutate, expect="handoff")

    def test_a_wrong_reviewed_gup(self):
        def mutate(root):
            path, document, record = repair_record(root)
            record["reviewed_gup"]["id"] = "GUP-PKT-PHB-054-064-druid-spells-r02"
            rewrite(path, document)
            self._repin(root, path)
        self._assert_denied(mutate)

    def test_a_changed_builder_input_set(self):
        def mutate(root):
            path, document, record = repair_record(root)
            record["exact_builder_review_inputs"] = \
                record["exact_builder_review_inputs"][:1]
            rewrite(path, document)
            self._repin(root, path)
        self._assert_denied(mutate, expect="exact_builder_review_inputs")

    @staticmethod
    def _repin(root: Path, governing_path: Path) -> None:
        """Re-pin the delegating Decision to the edited governing Decision.

        Without this every mutation would be caught by the checksum alone, and
        the field-level checks under test would never run.
        """
        from adnd1e_integrator.admission import sha256_of
        path = root / DECISIONS / f"{DELEGATING}.yaml"
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["governing_repair_record"]["decision_input"]["checksum"] = \
            sha256_of(governing_path)
        rewrite(path, document)


class TestAnyOtherUnreadableReview(unittest.TestCase):
    """Acceptance test 3: one exception, pinned by bytes, and no other."""

    def _break(self, root: Path, name: str) -> None:
        target = (root / "books" / RULESET_ID / "phb" / "artifacts" / "reviews" / name)
        text = target.read_text(encoding="utf-8")
        target.write_text(text + "\nbroken: [unclosed\n", encoding="utf-8")

    def test_an_unrelated_packets_review_is_never_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            self._break(root, "REV-GUP-PKT-PHB-110-117-psionics-r06-r05.yaml")
            queue = ready_queue(root, RULESET_ID, BOOKS)
            self.assertTrue(queue["queue_integrity"])
            self.assertEqual(queue["ready"], [])
            self.assertEqual([e["code"] for e in queue["queue_integrity"]], [FATAL_CODE])

    def test_an_approving_review_is_never_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            self._break(root, "REV-GUP-PKT-PHB-117-119-bards-r04-r01.yaml")
            queue = ready_queue(root, RULESET_ID, BOOKS)
            self.assertTrue(queue["queue_integrity"])
            self.assertNotIn(BARDS, [b.bundle_id for b in queue["ready"]])

    def test_integrate_refuses_and_touches_nothing(self):
        from adnd1e_integrator.canonical import CanonicalPaths
        from adnd1e_integrator.checksums import checksum_file
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            self._break(root, "REV-GUP-PKT-PHB-110-117-psionics-r06-r05.yaml")
            paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
            before = {p: checksum_file(p) for p in paths.writable()}

            for argv in (("integrate",), ("integrate", "--dry-run"),
                         ("integrate", BARDS), ("integrate", "--dry-run", BARDS)):
                result = cli(root, *argv)
                self.assertEqual(result.returncode, 2, f"{argv}: {result.stderr}")
                self.assertNotIn("Traceback", result.stderr)
                self.assertIn(FATAL_CODE, result.stderr)

            self.assertEqual({p: checksum_file(p) for p in paths.writable()}, before)
            manifests = root / "rulesets" / RULESET_ID / "manifests"
            self.assertFalse([p for p in manifests.glob("*.json")
                              if p.stat().st_mtime > 0 and "19700101" in p.name])

    def test_restoring_valid_yaml_restores_the_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            name = "REV-GUP-PKT-PHB-110-117-psionics-r06-r05.yaml"
            target = root / "books" / RULESET_ID / "phb" / "artifacts" / "reviews" / name
            original = target.read_text(encoding="utf-8")
            before = ready_queue(root, RULESET_ID, BOOKS)
            self.assertEqual(before["queue_integrity"], [])

            self._break(root, name)
            self.assertTrue(ready_queue(root, RULESET_ID, BOOKS)["queue_integrity"])

            target.write_text(original, encoding="utf-8")
            after = ready_queue(root, RULESET_ID, BOOKS)
            self.assertEqual(after["queue_integrity"], [])
            self.assertEqual([b.bundle_id for b in after["ready"]],
                             [b.bundle_id for b in before["ready"]])
            self.assertEqual(len(after["informational"]), len(before["informational"]))


class TestOrdinarySemanticsAreUnchanged(unittest.TestCase):
    """Acceptance test 4: admission adds a gate; it moves nothing else."""

    def test_the_buckets_still_agree_with_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            queue = ready_queue(root, RULESET_ID, BOOKS)
            self.assertTrue(queue["integrated"])
            self.assertTrue(queue["rejected"])
            self.assertTrue(queue["superseded"])

    def test_admission_permits_exactly_the_pinned_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            admission = load_admission(root, RULESET_ID)
            self.assertEqual(
                {Path(p).name for p in admission.permitted},
                {Path(UNREADABLE).name, Path(DIRECT_UNREADABLE).name})
            self.assertEqual(set(admission.permitted.values()),
                             {GOVERNING, DIRECT_GOVERNING})
            self.assertFalse(admission.fails_closed)

    def test_history_alone_does_not_prevent_a_transaction(self):
        """The gate must not stand in for bundle verification.

        A permitted historical file lets the run proceed to ordinary
        preconditions; whether *this* bundle then passes them is a separate
        question this Decision explicitly leaves to the normal lifecycle. What
        matters here is that the refusal, if any, comes from verification and
        not from admission.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            result = cli(root, "integrate", "--dry-run")
            self.assertNotEqual(result.returncode, 2, result.stderr)
            self.assertNotIn(FATAL_CODE, result.stderr)
            self.assertNotIn("queue integrity failed", result.stderr)


def direct_record(root: Path) -> tuple[Path, dict, dict]:
    """The DEC-2026-0068 document and its single direct-predecessor record."""
    path = root / DECISIONS / f"{DIRECT_GOVERNING}.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return path, document, document["review_direct_predecessor_repairs"][0]


class TestTheDirectPredecessorException(unittest.TestCase):
    """DEC-2026-0069: a one-step lineage, admitted on its own evidence.

    The Druid record bridges three artifacts. This one has two, so it cannot
    corroborate the successor through an intermediate revision. It compensates
    with the rejection it consumes, the component it re-packages unchanged, and
    the operation partition it declares -- which is precisely what the rejected
    bundle got wrong, and therefore what has to be proved right.
    """

    def _repin(self, root: Path, governing_path: Path) -> None:
        from adnd1e_integrator.admission import sha256_of
        path = root / DECISIONS / f"{DIRECT_DELEGATING}.yaml"
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        document["governing_direct_predecessor_repair_record"]["decision_input"]["checksum"] = \
            sha256_of(governing_path)
        rewrite(path, document)

    def _assert_denied(self, mutate, *, expect: str | None = None):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            mutate(root)
            queue = ready_queue(root, RULESET_ID, BOOKS)
            self.assertTrue(queue["queue_integrity"], "expected a fatal diagnostic")
            self.assertEqual([e["code"] for e in queue["queue_integrity"]],
                             [FATAL_CODE] * len(queue["queue_integrity"]))
            self.assertEqual(queue["ready"], [])
            if expect:
                self.assertIn(expect, json.dumps(queue["queue_integrity"]))
            result = cli(root, "queue")
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_the_bards_notice_names_its_own_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = ready_queue(clone(Path(tmp)), RULESET_ID, BOOKS)
            notice = next(n for n in queue["informational"]
                          if Path(n["path"]).name == Path(DIRECT_UNREADABLE).name)
            self.assertEqual(notice["authorised_by"], DIRECT_GOVERNING)
            self.assertEqual(queue["queue_integrity"], [])

    def test_no_content_of_the_unreadable_bards_review_is_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = ready_queue(clone(Path(tmp)), RULESET_ID, BOOKS)
            rendered = json.dumps(queue["informational"])
            for fragment in ("This successor consumes", "completeness_statement",
                             "packaging_only_successor"):
                self.assertNotIn(fragment, rendered)

    def test_a_changed_governing_checksum(self):
        def mutate(root):
            path, document, _ = direct_record(root)
            document["decision_date"] = "1970-01-01"
            rewrite(path, document)
        self._assert_denied(mutate)

    def test_an_inactive_governing_decision(self):
        def mutate(root):
            path, document, _ = direct_record(root)
            document["status"] = "superseded"
            rewrite(path, document)
            self._repin(root, path)
        self._assert_denied(mutate)

    def test_a_delegation_naming_another_field(self):
        """A delegation may not nominate a list of its own choosing."""
        def mutate(root):
            path = root / DECISIONS / f"{DIRECT_DELEGATING}.yaml"
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            document["governing_direct_predecessor_repair_record"]["field"] = "rationale"
            rewrite(path, document)
        self._assert_denied(mutate, expect="admits only")

    def test_a_self_delegating_decision(self):
        def mutate(root):
            from adnd1e_integrator.admission import sha256_of
            path = root / DECISIONS / f"{DIRECT_DELEGATING}.yaml"
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            block = document["governing_direct_predecessor_repair_record"]["decision_input"]
            block["id"] = DIRECT_DELEGATING
            block["path"] = f"{DECISIONS}/{DIRECT_DELEGATING}.yaml"
            rewrite(path, document)
            block["checksum"] = sha256_of(path)
            rewrite(path, document)
            block["checksum"] = sha256_of(path)
            rewrite(path, document)
        self._assert_denied(mutate)

    def test_a_parseable_unreadable_review(self):
        def mutate(root):
            target = root / DIRECT_UNREADABLE
            text = target.read_text(encoding="utf-8")
            target.write_text(text.replace("completeness_statement: >-",
                                           "completeness_statement: packaging successor"),
                              encoding="utf-8")
        self._assert_denied(mutate)

    def test_a_wrong_parser_fragment(self):
        def mutate(root):
            path, document, record = direct_record(root)
            record["unreadable_review"]["parse_failure"]["message_fragment"] = \
                "found undefined alias"
            rewrite(path, document)
            self._repin(root, path)
        self._assert_denied(mutate, expect="expects the parser to fail with")

    def test_a_broken_bundle_supersession(self):
        def mutate(root):
            path, document, record = direct_record(root)
            record["active_successor_bundle"]["required_supersedes"] = \
                "APPROVED-GUP-PKT-PHB-117-119-bards-r04-r01"
            rewrite(path, document)
            self._repin(root, path)
        self._assert_denied(mutate, expect="active_successor_bundle")

    def test_a_changed_component_row_count(self):
        def mutate(root):
            path, document, record = direct_record(root)
            record["edge_component"]["rows"] = 56
            rewrite(path, document)
            self._repin(root, path)
        self._assert_denied(mutate, expect="edge_component declares")

    def test_a_changed_operation_partition(self):
        def mutate(root):
            path, document, record = direct_record(root)
            record["required_operations"]["pending_additions"]["count"] = 27
            rewrite(path, document)
            self._repin(root, path)
        self._assert_denied(mutate, expect="pending_additions")

    def test_a_changed_registered_node_count(self):
        def mutate(root):
            path, document, record = direct_record(root)
            record["required_operations"]["registered_node_count"] = 10
            rewrite(path, document)
            self._repin(root, path)
        self._assert_denied(mutate, expect="registered_node_count")

    def test_a_mismatched_rejection_pin(self):
        def mutate(root):
            path, document, record = direct_record(root)
            record["integration_rejection"]["checksum"] = "sha256:" + "0" * 64
            rewrite(path, document)
            self._repin(root, path)
        self._assert_denied(mutate, expect="integration_rejection")

    def test_the_druid_form_still_works_alongside_it(self):
        """Acceptance test 3: neither exception absorbs the other."""
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            path, document, _ = direct_record(root)
            document["status"] = "superseded"
            rewrite(path, document)
            self._repin(root, path)
            queue = ready_queue(root, RULESET_ID, BOOKS)
            self.assertTrue(queue["queue_integrity"], "the Bards exception must be denied")
            names = {Path(n["path"]).name for n in queue["informational"]}
            self.assertEqual(names, {Path(UNREADABLE).name},
                             "the Druid exception is independent and still stands")


class TestTheExclusionIsBoundedByItsRecord(unittest.TestCase):
    """DEC-2026-0070: invalidating the record restores fail-closed, never r02.

    The failure mode worth guarding is not that r02 becomes ready -- it is that
    a broken record silently downgrades to "admit everything". Each case here
    breaks one pin and asserts the queue refuses rather than relaxes.
    """

    HISTORICAL = "APPROVED-GUP-PKT-PHB-117-119-bards-r04-r02"

    def _assert_fails_closed(self, mutate):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            mutate(root)
            queue = ready_queue(root, RULESET_ID, BOOKS)

            self.assertTrue(queue["queue_integrity"], "expected fail-closed")
            self.assertEqual(queue["ready"], [])
            # `superseded` is deliberately not checked here. r03's own manifest
            # names r02 in `supersedes`, which is a readable fact about a
            # readable file and holds whether or not the record validates -- so
            # classifying r02 as repackaged history costs the denial nothing.
            # What a denial must never do is offer it as work or claim the
            # exclusion authority it was just refused.
            offered = set()
            for name in ("ready", "integrated", "rejected"):
                for entry in queue[name]:
                    item = entry[0] if isinstance(entry, tuple) else entry
                    offered.add(item.bundle_id)
            self.assertNotIn(self.HISTORICAL, offered,
                             "a denied record must not admit the historical bundle")
            self.assertNotIn(self.HISTORICAL,
                             [n.get("bundle_id") for n in queue["informational"]],
                             "a denied record excludes nothing")
            result = cli(root, "queue")
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_an_altered_historical_bundle_id(self):
        def mutate(root):
            path, document, record = direct_record(root)
            record["historical_bundle"]["id"] = \
                "APPROVED-GUP-PKT-PHB-117-119-bards-r04-r01"
            rewrite(path, document)
            repin_direct(root, path)
        self._assert_fails_closed(mutate)

    def test_an_altered_historical_bundle_checksum(self):
        def mutate(root):
            path, document, record = direct_record(root)
            record["historical_bundle"]["checksum"] = "sha256:" + "0" * 64
            rewrite(path, document)
            repin_direct(root, path)
        self._assert_fails_closed(mutate)

    def test_a_historical_bundle_approved_by_a_readable_review(self):
        """If a readable Review approved it, it is an ordinary bundle."""
        def mutate(root):
            approved = (root / "books" / RULESET_ID / "phb" / "artifacts" / "approved"
                        / "APPROVED-GUP-PKT-PHB-117-119-bards-r04-r02.yaml")
            manifest = yaml.safe_load(approved.read_text(encoding="utf-8"))
            manifest["approves"]["review_id"] = \
                "REV-GUP-PKT-PHB-117-119-bards-r04-r03"
            manifest["review_id"] = "REV-GUP-PKT-PHB-117-119-bards-r04-r03"
            rewrite(approved, manifest)
            path, document, record = direct_record(root)
            from adnd1e_integrator.admission import sha256_of
            record["historical_bundle"]["checksum"] = sha256_of(approved)
            rewrite(path, document)
            repin_direct(root, path)
        self._assert_fails_closed(mutate)

    def test_a_parseable_unreadable_review_removes_the_exclusion(self):
        def mutate(root):
            target = root / DIRECT_UNREADABLE
            text = target.read_text(encoding="utf-8")
            target.write_text(text.replace("completeness_statement: >-",
                                           "completeness_statement: packaging successor"),
                              encoding="utf-8")
        self._assert_fails_closed(mutate)


if __name__ == "__main__":
    unittest.main()
