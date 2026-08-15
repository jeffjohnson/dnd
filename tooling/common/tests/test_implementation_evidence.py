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

#: A summary ends in the verdict its runner printed.
VERDICT = re.compile(r"\b(OK|FAILED)\s*$")


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
                    verdict = VERDICT.search(str(command.get("summary", "")))
                    self.assertIsNotNone(
                        verdict, f"{path.name}: summary records no verdict",
                    )
                    self.assertEqual(
                        verdict.group(1) == "OK", passed,
                        f"{path.name}: summary verdict contradicts result",
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


if __name__ == "__main__":
    unittest.main()
