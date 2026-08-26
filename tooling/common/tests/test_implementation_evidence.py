"""Internal consistency of the evidence an implementation report records.

A report is only worth what its evidence asserts, and the failure mode is not a
wrong verdict but a self-contradictory one: `exit_code: 0` and `result: passed`
beside a summary reading FAILED, or a Builder command carrying the common
suite's totals. Both happened, twice, because a command record was assembled
from three places -- a hardcoded exit code, a hardcoded verdict, and a summary
string captured from a different run. A Reviewer caught it by reading; nothing
in the repository did.

The rule is that one command record describes one execution. Whatever the
verdict, the three fields must agree, and the command must say enough for a
Reviewer to re-run it.

Only active leaves are checked. Superseded revisions are immutable history, and
several were published before these expectations existed.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
STORE = REPO_ROOT / "rulesets" / "adnd1e" / "decision-implementations"

#: The counters `unittest` prints after its verdict, and nothing else.
#: `TextTestResult.printErrors` emits exactly these names, in one parenthesis,
#: comma-separated, each with an integer count.
VERDICT_COUNTERS = (
    "failures",
    "errors",
    "skipped",
    "expected failures",
    "unexpected successes",
)

#: The counters that can appear beside a passing verdict. A skipped or expected
#: failure is compatible with success; the other three are the runner saying the
#: run did not succeed, so `OK` beside one of them is self-contradictory however
#: it got written.
PASSING_COUNTERS = frozenset({"skipped", "expected failures"})

#: A summary ends in the verdict its runner printed, with the runner's own
#: optional counter list and nothing after it. DEC-2026-0061 fixes the grammar
#: to the bounded standard form: an end-anchored bare `OK|FAILED` rejected the
#: literal successful output of every suite that skips a test.
VERDICT = re.compile(
    r"\b(?P<verdict>OK|FAILED)(?:\s*\((?P<counters>[^()]*)\))?\s*$"
)
COUNTER = re.compile(
    r"^(?P<name>" + "|".join(VERDICT_COUNTERS) + r")=(?P<count>\d+)$"
)


def parse_verdict(summary):
    """`(verdict, {counter: count})` for a standard terminal line, else `None`.

    `None` means the text is not something `unittest` printed: a bare prose
    summary, a malformed counter, an unrecognized counter name, or anything
    trailing the verdict. Returning it rather than raising keeps the caller's
    assertion message about the artifact rather than about a regex.
    """
    match = VERDICT.search(str(summary))
    if match is None:
        return None

    text = match.group("counters")
    if text is None:
        return match.group("verdict"), {}
    if not text.strip():
        # `unittest` prints no empty parenthesis; it omits the group entirely.
        return None

    counters = {}
    for field in text.split(","):
        found = COUNTER.match(field.strip())
        if found is None:
            return None
        name = found.group("name")
        if name in counters:
            return None
        counters[name] = int(found.group("count"))
    return match.group("verdict"), counters


def active_leaves():
    """The newest revision of each Decision's report lineage."""
    leaves: dict[str, tuple[int, Path, dict]] = {}
    for path in sorted(STORE.glob("IMP-*.yaml")):
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


def all_revisions():
    """Every published report, leaf or not.

    Evidence about a superseded revision has to be checkable against that
    revision's own state, which means reading the ones that are not leaves.
    """
    documents = []
    for path in sorted(STORE.glob("IMP-*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(document, dict):
            documents.append((path, document))
    return documents


class TestValidationEvidenceIsSelfConsistent(unittest.TestCase):
    def setUp(self):
        self.leaves = active_leaves()
        self.assertTrue(self.leaves, "expected published implementation reports")

    def all_revisions(self):
        return all_revisions()

    def test_exit_code_result_and_summary_agree(self):
        for path, document in self.leaves:
            for command in document.get("validation", {}).get("commands", []):
                with self.subTest(artifact=path.name, command=command.get("command")):
                    passed = command.get("result") == "passed"
                    self.assertEqual(
                        command.get("exit_code") == 0, passed,
                        f"{path.name}: exit_code contradicts result",
                    )
                    parsed = parse_verdict(command.get("summary", ""))
                    self.assertIsNotNone(
                        parsed,
                        f"{path.name}: summary records no standard unittest verdict",
                    )
                    verdict, counters = parsed
                    self.assertEqual(
                        verdict == "OK", passed,
                        f"{path.name}: summary verdict contradicts result",
                    )
                    if verdict == "OK":
                        contradicting = sorted(set(counters) - PASSING_COUNTERS)
                        self.assertEqual(
                            contradicting, [],
                            f"{path.name}: summary says OK but records "
                            f"{', '.join(contradicting)}",
                        )

    def test_a_passing_validation_has_no_failing_command(self):
        for path, document in self.leaves:
            validation = document.get("validation", {})
            if validation.get("passed") is not True:
                continue
            with self.subTest(artifact=path.name):
                self.assertEqual(
                    [c for c in validation.get("commands", []) if c.get("result") != "passed"],
                    [], f"{path.name}: validation.passed but a command failed",
                )

    def test_an_approval_ready_report_records_a_passing_validation(self):
        for path, document in self.leaves:
            if document.get("approval_ready") is not True:
                continue
            with self.subTest(artifact=path.name):
                self.assertIs(document.get("validation", {}).get("passed"), True, path.name)

    def test_each_command_says_where_it_ran(self):
        """A Reviewer has to be able to reproduce it.

        `python -m unittest discover -s . -t .` with no working directory names
        no suite at all: two of those appeared in one report, and there was no
        way to tell which was which, or which summary belonged to which.
        """
        for path, document in self.leaves:
            for command in document.get("validation", {}).get("commands", []):
                text = str(command.get("command", ""))
                with self.subTest(artifact=path.name, command=text):
                    self.assertTrue(
                        "cwd" in text or re.search(r"-s\s+\S*tooling\S*", text),
                        f"{path.name}: command names neither a directory nor a suite path",
                    )

    def test_evidence_citing_unit_tests_says_what_they_did(self):
        """A named test with no outcome is a claim, not evidence.

        A reissue script stripped the trailing `-> Ran N tests in Xs OK` from
        every evidence line and only restored it where the citation matched the
        shape it expected, so three acceptance results ended up naming tests
        with no record of running them. A Reviewer caught it.
        """
        for path, document in self.leaves:
            for result in document.get("acceptance_results", []):
                evidence = str(result.get("evidence", ""))
                if not re.search(r"\bunit tests?\b", evidence):
                    continue
                with self.subTest(artifact=path.name, index=result.get("acceptance_test_index")):
                    self.assertRegex(
                        evidence, r"Ran \d+ tests? in [\d.]+s (?:OK|FAILED)",
                        f"{path.name}: evidence names unit tests but records no outcome",
                    )

    def test_no_evidence_calls_an_active_leaf_a_blocked_historical_report(self):
        """The two revisions an evidence line names are not interchangeable.

        Evidence about retirement deliberately names both the current leaf and
        an older revision the work had to leave alone. A blanket
        `IMP-...-rNN -> current leaf` substitution collapsed the two, and the
        sentence came out asserting that the report it had just routed to the
        Reviewer was a blocked historical one. Both halves were individually
        plausible; only together were they false.
        """
        blocked = {
            str(document.get("id"))
            for _, document in self.all_revisions()
            if document.get("status") == "blocked" or document.get("approval_ready") is False
        }
        leaves = {str(document.get("id")) for _, document in self.leaves}
        for path, document in self.leaves:
            for result in document.get("acceptance_results", []):
                evidence = str(result.get("evidence", ""))
                for sentence in re.split(r"(?<=[.;])\s+", evidence):
                    if not re.search(r"\bblocked\b|\bhistorical\b|\bsuperseded\b", sentence):
                        continue
                    cited = set(re.findall(r"IMP-DEC-\d{4}-\d{4}-r\d+", sentence)) - blocked
                    with self.subTest(
                        artifact=path.name, index=result.get("acceptance_test_index")
                    ):
                        self.assertEqual(
                            sorted(cited & leaves), [],
                            f"{path.name}: calls an active leaf blocked or historical",
                        )

    def test_a_claim_that_something_is_the_active_leaf_is_still_true(self):
        """Evidence that names a moving target rots when the target moves.

        One report described another lineage's leaf by revision number. Every
        later revision of *that* lineage silently falsified it, and carrying the
        sentence verbatim through a reissue -- the safe-looking choice, after a
        substitution had corrupted it -- preserved the claim past the point it
        was true. A statement about a specific revision keeps forever; a
        statement about which revision is current does not, so it has to be
        checked rather than trusted.
        """
        leaves = {str(document.get("id")) for _, document in self.leaves}
        superseded = {
            str(document.get("supersedes"))
            for _, document in self.all_revisions()
            if document.get("supersedes")
        }
        for path, document in self.leaves:
            for result in document.get("acceptance_results", []):
                evidence = str(result.get("evidence", ""))
                for cited in re.findall(
                    r"(IMP-DEC-\d{4}-\d{4}-r\d+),?\s+the active leaf", evidence
                ):
                    with self.subTest(
                        artifact=path.name, index=result.get("acceptance_test_index")
                    ):
                        self.assertNotIn(
                            cited, superseded,
                            f"{path.name}: calls {cited} the active leaf, but it is superseded",
                        )
                        self.assertIn(
                            cited, leaves,
                            f"{path.name}: calls {cited} the active leaf, but it is not one",
                        )

    def test_commands_within_one_report_are_distinguishable(self):
        for path, document in self.leaves:
            commands = [
                str(c.get("command", ""))
                for c in document.get("validation", {}).get("commands", [])
            ]
            with self.subTest(artifact=path.name):
                self.assertEqual(
                    len(commands), len(set(commands)),
                    f"{path.name}: two command records are textually identical, so their "
                    f"summaries cannot be attributed",
                )

class TestVerdictGrammar(unittest.TestCase):
    """The bounded grammar DEC-2026-0061 fixes, driven directly.

    The guard reads immutable evidence, so what it accepts has to be settled by
    cases rather than by whichever summaries happen to be in the store today.
    """

    def parse(self, summary):
        return parse_verdict(summary)

    def test_the_form_that_broke_the_old_matcher(self):
        """The literal reason this Decision exists."""
        self.assertEqual(
            self.parse("Ran 655 tests in 103.582s OK (skipped=38)"),
            ("OK", {"skipped": 38}),
        )

    def test_a_bare_verdict(self):
        self.assertEqual(self.parse("Ran 800 tests in 163.074s OK"), ("OK", {}))

    def test_a_failing_verdict_with_counters(self):
        self.assertEqual(
            self.parse("Ran 800 tests in 159.226s FAILED (failures=3)"),
            ("FAILED", {"failures": 3}),
        )

    def test_several_counters(self):
        self.assertEqual(
            self.parse("Ran 12 tests in 1.0s FAILED (failures=2, errors=1, skipped=3)"),
            ("FAILED", {"failures": 2, "errors": 1, "skipped": 3}),
        )

    def test_the_two_word_counter_names(self):
        self.assertEqual(
            self.parse("Ran 9 tests in 0.5s OK (expected failures=2)"),
            ("OK", {"expected failures": 2}),
        )
        self.assertEqual(
            self.parse("Ran 9 tests in 0.5s FAILED (unexpected successes=1)"),
            ("FAILED", {"unexpected successes": 1}),
        )

    def test_prose_after_the_verdict_is_not_a_verdict(self):
        """The whole point of anchoring: a summary must end where the run did."""
        for summary in (
            "Ran 655 tests in 103.582s OK (skipped=38) and everything looks fine",
            "Ran 655 tests OK, then I fixed the rest",
            "OK (skipped=38) FAILED later",
        ):
            with self.subTest(summary=summary):
                parsed = self.parse(summary)
                if parsed is not None:
                    # A trailing `FAILED` is itself a terminal verdict, so the
                    # only reading that survives is the one at the end.
                    self.assertEqual(parsed[0], "FAILED")

    def test_no_verdict_at_all(self):
        for summary in ("Ran 129 focused lifecycle and queue tests; all passed.", "", "passed"):
            with self.subTest(summary=summary):
                self.assertIsNone(self.parse(summary))

    def test_a_malformed_counter_is_not_a_verdict(self):
        for summary in (
            "Ran 1 test in 0.1s OK (skipped=)",
            "Ran 1 test in 0.1s OK (skipped=many)",
            "Ran 1 test in 0.1s OK (skipped)",
            "Ran 1 test in 0.1s OK ()",
            "Ran 1 test in 0.1s OK (skipped=1;errors=2)",
        ):
            with self.subTest(summary=summary):
                self.assertIsNone(self.parse(summary))

    def test_an_unrecognized_counter_name_is_not_a_verdict(self):
        """`unittest` prints a closed set. Anything else was written by hand."""
        for summary in (
            "Ran 1 test in 0.1s OK (flaky=1)",
            "Ran 1 test in 0.1s OK (skipped=1, flaky=1)",
        ):
            with self.subTest(summary=summary):
                self.assertIsNone(self.parse(summary))

    def test_a_repeated_counter_is_not_a_verdict(self):
        self.assertIsNone(self.parse("Ran 1 test in 0.1s OK (skipped=1, skipped=2)"))

    def test_counters_that_contradict_a_passing_verdict_are_still_parsed(self):
        """Parsing and judging are separate.

        `OK (failures=1)` is well-formed text and a false claim. The parser
        reports what it says; the guard below is what rejects it. Collapsing the
        two would make the failure message say `no verdict`, which is not the
        problem.
        """
        self.assertEqual(
            self.parse("Ran 3 tests in 0.2s OK (failures=1)"), ("OK", {"failures": 1})
        )
        self.assertFalse(PASSING_COUNTERS & {"failures", "errors", "unexpected successes"})


class TestPassingVerdictRejectsFailureCounters(unittest.TestCase):
    """`OK` beside a failure counter must not read as a passing record.

    Driven through the guard rather than the parser, because this is the
    assertion a report would trip.
    """

    def check(self, summary):
        document = {
            "id": "IMP-DEC-2026-9999-r01",
            "validation": {
                "passed": True,
                "commands": [{
                    "command": "[cwd tooling/common] python -m unittest discover -s tests",
                    "exit_code": 0,
                    "result": "passed",
                    "summary": summary,
                }],
            },
        }
        case = TestValidationEvidenceIsSelfConsistent("test_exit_code_result_and_summary_agree")
        case.leaves = [(Path("IMP-DEC-2026-9999-r01.yaml"), document)]
        return case

    def test_a_clean_ok_passes(self):
        self.check("Ran 3 tests in 0.2s OK (skipped=1)").test_exit_code_result_and_summary_agree()

    def test_ok_with_failures_is_rejected(self):
        for summary in (
            "Ran 3 tests in 0.2s OK (failures=1)",
            "Ran 3 tests in 0.2s OK (errors=1)",
            "Ran 3 tests in 0.2s OK (unexpected successes=1)",
            "Ran 3 tests in 0.2s OK (skipped=1, errors=2)",
        ):
            with self.subTest(summary=summary):
                case = self.check(summary)
                with self.assertRaises(AssertionError):
                    case.test_exit_code_result_and_summary_agree()

    def test_prose_is_rejected(self):
        case = self.check("Ran 3 tests in 0.2s OK and the rest is fine")
        with self.assertRaises(AssertionError):
            case.test_exit_code_result_and_summary_agree()


class TestTheRetainedReportsPass(unittest.TestCase):
    """DEC-2026-0061 AT2, pinned to the two reports the ruling names.

    The Decision retains IMP-DEC-2026-0053-r03 and IMP-DEC-2026-0060-r01
    unchanged and authorizes no successor for either. If the corrected grammar
    did not accept their existing summaries, the only remaining remedy would be
    a reissue the Decision forbids -- so this is checked by name, not left to
    the corpus sweep above.
    """

    RETAINED = ("IMP-DEC-2026-0053-r03", "IMP-DEC-2026-0060-r01")

    def test_each_retained_report_is_still_the_active_leaf(self):
        leaves = {str(document.get("id")) for _, document in active_leaves()}
        for identifier in self.RETAINED:
            with self.subTest(artifact=identifier):
                self.assertIn(identifier, leaves)

    def test_every_summary_in_them_parses_and_agrees(self):
        for identifier in self.RETAINED:
            document = yaml.safe_load(
                (STORE / f"{identifier}.yaml").read_text(encoding="utf-8")
            )
            for command in document.get("validation", {}).get("commands", []):
                with self.subTest(artifact=identifier, command=command.get("command")):
                    parsed = parse_verdict(command.get("summary", ""))
                    self.assertIsNotNone(parsed, command.get("summary"))
                    verdict, counters = parsed
                    self.assertEqual(verdict == "OK", command.get("result") == "passed")
                    if verdict == "OK":
                        self.assertEqual(sorted(set(counters) - PASSING_COUNTERS), [])

    def test_no_successor_was_published_for_either(self):
        """The Decision says no Builder reissue is authorized. Prove none exists."""
        for identifier in self.RETAINED:
            lineage, _, revision = identifier.rpartition("-r")
            later = sorted(
                path.name
                for path in STORE.glob(f"{lineage}-r*.yaml")
                if path.stem.rpartition("-r")[2].isdigit()
                and int(path.stem.rpartition("-r")[2]) > int(revision)
            )
            with self.subTest(artifact=identifier):
                self.assertEqual(later, [])



if __name__ == "__main__":
    unittest.main()
