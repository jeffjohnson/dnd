"""Command line entry point for the AD&D 1e Builder compiler.

    python -m adnd1e_builder compile <gur.yaml> [...] [--repo-root PATH]

Runs the invariant test suite first (Builder responsibility 15) and records the
outcome in every artifact it writes, so a Reviewer can see the compiler was
green when the patch was produced.
"""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

from .compiler import Compiler, load_general_rules
from .duplicates import CanonicalEdges
from .emit import preflight_create_only, write_all
from .governance import Governance
from .registry import NodeRegistry
from .review import ReviewDirectives
from .vocab import CONSTITUTION_VERSION


def run_tests(test_dir: Path) -> dict:
    """Run the Builder test suite and summarise it for provenance."""
    if not test_dir.exists():
        return {"ran": False, "reason": f"no test directory at {test_dir}"}
    loader = unittest.TestLoader()
    suite = loader.discover(str(test_dir), pattern="test_*.py", top_level_dir=str(test_dir))
    runner = unittest.TextTestRunner(stream=open("nul" if sys.platform == "win32" else "/dev/null", "w"), verbosity=0)
    outcome = runner.run(suite)
    return {
        "ran": True,
        "tests": outcome.testsRun,
        "failures": len(outcome.failures),
        "errors": len(outcome.errors),
        "passed": outcome.wasSuccessful(),
    }


def published_revisions(gup_dir: Path, packet_id: str) -> list[int]:
    """Revision numbers of every published GUP for one packet."""
    import re

    if not packet_id or not gup_dir.is_dir():
        return []
    pattern = re.compile(rf"^GUP-{re.escape(packet_id)}-r(\d+)$")
    found = []
    for path in gup_dir.glob(f"GUP-{packet_id}-r*.yaml"):
        match = pattern.match(path.stem)
        if match:
            found.append(int(match.group(1)))
    return sorted(found)


def next_revision(gup_dir: Path, packet_id: str) -> int:
    """The revision a new GUP should carry.

    A GUP revision counts *GUP* revisions, not GUR revisions. Taking it from the
    GUR would give a packet's first GUP a number above 1 whenever the Analyst
    had revised, and WORK_QUEUES requires revision 2 or later to name the
    revision it supersedes — which a first GUP has none of.
    """
    published = published_revisions(gup_dir, packet_id)
    return published[-1] + 1 if published else 1


def previous_revision(gup_dir: Path, gur_path: Path, revision: int | None) -> str | None:
    """The highest published GUP revision below this one, for `supersedes`.

    WORK_QUEUES requires revision 2 and later to name the immediately prior
    revision. Scanning the directory rather than assuming rNN-1 keeps the link
    valid when a revision number was skipped.
    """
    import re

    import yaml

    document = yaml.safe_load(gur_path.read_text(encoding="utf-8")) or {}
    packet_id = document.get("packet_id") or ""
    target = int(revision if revision is not None else document.get("revision") or 1)
    if target <= 1 or not packet_id:
        return None

    pattern = re.compile(rf"^GUP-{re.escape(packet_id)}-r(\d+)$")
    found = []
    for path in gup_dir.glob(f"GUP-{packet_id}-r*.yaml"):
        match = pattern.match(path.stem)
        if match and int(match.group(1)) < target:
            found.append((int(match.group(1)), path.stem))
    if not found:
        return None
    return max(found)[1]


def plan_decision_migration(args) -> int:
    """Propose the canonical changes an approved decision enumerates row by row."""
    import json

    from .compiler import TOOL_NAME, TOOL_VERSION, sha256_of
    from .decision_migration import (
        note_baseline_drift,
        plan_from_decisions,
        to_gup,
        validation_report,
    )
    from .duplicates import CanonicalEdges
    from .emit import _dump
    from .registry import NodeRegistry

    root: Path = args.repo_root.resolve()
    ruleset_root = root / "rulesets" / args.ruleset
    canonical_path = ruleset_root / "canonical" / "edges_master.csv"
    registry_path = ruleset_root / "registries" / "nodes.csv"
    canonical = CanonicalEdges.load(canonical_path)
    registry = NodeRegistry.load(registry_path)

    plan = plan_from_decisions(
        canonical, list(args.decision), registry, repo_root=root, ruleset_id=args.ruleset
    )
    if not plan.decisions:
        print("no approved decision enumerated a canonical migration", file=sys.stderr)
        return 2

    test_result = (
        {"ran": False, "reason": "skipped by flag"}
        if args.skip_tests
        else run_tests(root / "tooling" / "builder" / "tests")
    )
    if test_result.get("ran") and not test_result.get("passed"):
        print(f"builder test suite failed: {test_result}", file=sys.stderr)
        return 2

    gup_id = args.gup_id or f"GUP-MIG-{'-'.join(plan.decisions)}-r01"
    report_path = root / "build" / "reports" / f"{gup_id}.validation.json"
    envelope = {
        "ruleset_id": args.ruleset,
        "book_id": args.book,
        "source_id": args.source_id,
        "packet_id": "cross-packet",
        "constitution_version": CONSTITUTION_VERSION,
        "lineage_id": args.lineage_id or f"MIG-{'-'.join(plan.decisions)}",
        "revision": args.revision,
        "supersedes": args.supersedes or None,
        "canonical_source": str(canonical_path.relative_to(root)).replace("\\", "/"),
        "canonical_checksum": f"sha256:{sha256_of(canonical_path)}",
        "canonical_rows_read": len(canonical.rows),
        "validation_report": str(report_path.relative_to(root)).replace("\\", "/"),
        "validation_report_checksum": "",
        # The registry is the second baseline a direct migration writes to.
        # Recorded unconditionally so the numbers in a report and a GUP always
        # come from the same read, and consumed only by the direct model.
        "registry_source": str(registry_path.relative_to(root)).replace("\\", "/"),
        "registry_checksum": f"sha256:{sha256_of(registry_path)}",
        "registry_rows_read": len(registry.nodes),
    }

    tool = {"name": TOOL_NAME, "version": TOOL_VERSION}
    # Recorded before either artifact is rendered so the note appears in both.
    note_baseline_drift(plan, envelope)
    # The report is written first because the GUP pins it by checksum. Doing it
    # the other way round would mean hashing a file that does not exist yet.
    report = validation_report(
        plan, gup_id, envelope, tool, test_result, operation_model=args.operation_model
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # DEC-2026-0053: both durable outputs are checked before either is written.
    # The report is written first because the GUP pins it by checksum, so a
    # per-file check would have already clobbered the report by the time it
    # noticed the GUP existed.
    try:
        preflight_create_only([report_path, args.out], gup_id)
    except FileExistsError as clash:
        print(str(clash), file=sys.stderr)
        return 2
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    envelope["validation_report_checksum"] = f"sha256:{sha256_of(report_path)}"

    try:
        document = to_gup(
            plan, gup_id, envelope, tool, test_result, operation_model=args.operation_model
        )
    except ValueError as mismatch:
        print(str(mismatch), file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(_dump(document), encoding="utf-8", newline="\n")

    print(
        f"{gup_id}: status={document['status']} "
        f"rows={len(plan.row_changes)} nodes={len(plan.nodes_added)} "
        f"relabels={len(plan.nodes_relabelled)} removals={len(plan.removals)} "
        f"errors={document['validation_summary']['errors']}"
    )
    print(f"  wrote {args.out}")
    print(f"  wrote {report_path}")
    return 1 if plan.blocks_approval else 0


def plan_migration(args) -> int:
    """DEC-2026-0007: propose an approved identity merge with a full-key audit."""
    import yaml

    from .compiler import TOOL_NAME, TOOL_VERSION
    from .duplicates import CanonicalEdges
    from .emit import _dump
    from .governance import Governance
    from .migration import plan, to_gup

    root: Path = args.repo_root.resolve()
    ruleset_root = root / "rulesets" / args.ruleset
    governance = Governance.load(ruleset_root)
    if not governance.identity_merges:
        print("no approved identity merges found in the decision record", file=sys.stderr)
        return 2

    canonical_path = ruleset_root / "canonical" / "edges_master.csv"
    canonical = CanonicalEdges.load(canonical_path)
    result = plan(canonical, governance.identity_merges)

    test_result = (
        {"ran": False, "reason": "skipped by flag"}
        if args.skip_tests
        else run_tests(root / "tooling" / "builder" / "tests")
    )
    if test_result.get("ran") and not test_result.get("passed"):
        print(f"builder test suite failed: {test_result}", file=sys.stderr)
        return 2

    decision_ids = sorted({m["authority"] for m in result.merges if m["authority"]})
    gup_id = f"GUP-MIG-{decision_ids[0]}-r01" if decision_ids else "GUP-MIG-r01"
    envelope = {
        "ruleset_id": args.ruleset,
        "book_id": "phb",
        "source_id": "phb-legacy-unspecified",
        "packet_id": "PKT-PHB-009-013-ability-scores",
        "constitution_version": CONSTITUTION_VERSION,
        "canonical_source": str(canonical_path.relative_to(root)).replace("\\", "/"),
        "canonical_rows_read": len(canonical.rows),
    }

    document = to_gup(
        result, gup_id, envelope,
        {"name": TOOL_NAME, "version": TOOL_VERSION}, test_result,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    try:
        preflight_create_only([args.out], gup_id)
    except FileExistsError as clash:
        print(str(clash), file=sys.stderr)
        return 2
    args.out.write_text(_dump(document), encoding="utf-8", newline="\n")

    summary = document["validation_summary"]
    print(
        f"{gup_id}: status={document['status']} merges={summary['merges']} "
        f"repoints={summary['rows_repointed']} "
        f"triple_matches={summary['triple_matches_examined']} "
        f"exact_duplicates={summary['exact_duplicates']} "
        f"distinct_preserved={summary['distinct_assertions_preserved']}"
    )
    print(f"  wrote {args.out.relative_to(root) if args.out.is_relative_to(root) else args.out}")
    return 0 if document["approval_ready"] else 1


def audit_escalation_ids(ruleset_root: Path) -> int:
    """DEC-2026-0006 validator. Builder owns validator_implementation."""
    from .escalation_ids import audit

    result = audit(ruleset_root)
    print(
        f"{result.checked} escalation file(s): {result.timestamp_form} timestamp-form, "
        f"{result.legacy_form} legacy"
    )
    for finding in result.findings:
        print(f"  [{finding.severity}] {finding.rule}: {finding.detail}")
        if finding.path:
            print(f"        {finding.path}")
    print("  ok" if result.ok else "  FAILED")
    return 0 if result.ok else 1


def lint_source(sources: list[Path]) -> int:
    """Check packet source Markdown against `contracts/SOURCE_MARKDOWN.md`.

    Run this before an Analyst pass. A packet with no resolvable page markers
    cannot produce a citable edge, and that is cheaper to learn now than after
    extraction.
    """
    import re

    from .pagemarkers import MARKER_TEXT, parse_source

    MALFORMED = re.compile(r"\{#\s*[pP][^}]*\}")

    exit_code = 0
    for source in sources:
        if not source.exists():
            print(f"FAIL {source}: does not exist", file=sys.stderr)
            exit_code = max(exit_code, 1)
            continue

        problems: list[str] = []
        notes: list[str] = []

        parsed = parse_source(source)
        pages = parsed.pages

        if not pages:
            problems.append(
                "no page markers at all: every citation from this packet would be unresolvable "
                "(SOURCE_MARKDOWN 'Attribution Rules')"
            )
        else:
            gaps = [p for p in range(pages[0], pages[-1] + 1) if p not in pages]
            if gaps:
                notes.append(f"no marker for page(s) {gaps} inside the range {pages[0]}-{pages[-1]}")

        # Marker-shaped tokens that are not exactly {#pN}.
        text = source.read_text(encoding="utf-8")
        for candidate in set(MALFORMED.findall(text)):
            if not MARKER_TEXT.match(candidate):
                problems.append(f"malformed marker {candidate!r}; the form is exactly {{#pN}}")

        if parsed.unattributed_text:
            preview = parsed.unattributed_text[:70].replace("\n", " ")
            problems.append(
                f"content precedes the first marker and has no resolved page: {preview!r}..."
            )

        problems.extend(parsed.warnings)

        status = "FAIL" if problems else "ok  "
        print(f"{status} {source.name}")
        if pages:
            print(f"       pages resolved: {pages[0]}-{pages[-1]} ({len(pages)} marked)")
        for note in notes:
            print(f"       note: {note}")
        for problem in problems:
            print(f"       PROBLEM: {problem}")
        if problems:
            exit_code = max(exit_code, 1)

    return exit_code


def verify_pages(packet_dirs: list[Path], gup_dir: Path) -> int:
    """Cross-check GUP citations against the packet source's page markers.

    The compiler already checks a cited page against the packet's declared
    range. This is the stronger check: the page must actually be marked in the
    source, per `contracts/SOURCE_MARKDOWN.md`.
    """
    import csv

    from .pagemarkers import parse_source

    exit_code = 0
    for packet_dir in packet_dirs:
        source = packet_dir / "source.md"
        if not source.exists():
            print(f"{packet_dir.name}: no source.md", file=sys.stderr)
            exit_code = max(exit_code, 1)
            continue

        parsed = parse_source(source)
        available = set(parsed.pages)

        # Check the active leaf only. Superseded revisions are immutable
        # history and may legitimately contain values a later contract forbids;
        # re-flagging them would report settled problems forever.
        import yaml

        from .queues import active_leaf

        documents = {}
        for path in gup_dir.glob(f"GUP-{packet_dir.name}-r*.yaml"):
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if document.get("id"):
                documents[document["id"]] = document
        leaf = active_leaf(documents).leaf_id if documents else None

        cited: set[int] = set()
        malformed: list[str] = []
        if leaf:
            csv_path = gup_dir / f"{leaf}.edges.csv"
            if csv_path.exists():
                with csv_path.open(newline="", encoding="utf-8") as handle:
                    for row in csv.DictReader(handle):
                        page = (row.get("page") or "").strip()
                        if not page:
                            continue
                        if page.isdigit():
                            cited.add(int(page))
                        else:
                            malformed.append(page)

        missing = sorted(cited - available)
        gaps = [
            p
            for p in range(min(available), max(available) + 1)
            if available and p not in available
        ] if available else []

        status = "FAIL" if (missing or malformed) else "ok"
        print(f"{status:4s} {packet_dir.name}" + (f"  [leaf {leaf}]" if leaf else "  [no GUP]"))
        for value in sorted(set(malformed)):
            print(f"       non-numeric page value in the leaf bundle: {value!r}")
        print(f"       marked pages: {sorted(available)}")
        print(f"       cited pages : {sorted(cited)}")
        if gaps:
            print(f"       unmarked pages inside the range: {gaps}")
        if missing:
            print(f"       cited but not marked in source: {missing}")
            exit_code = max(exit_code, 1)
        for warning in parsed.warnings:
            print(f"       parser warning: {warning}")

    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="adnd1e_builder")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_cmd = sub.add_parser("compile", help="compile one or more GURs into GUPs")
    compile_cmd.add_argument("gur", nargs="+", type=Path)
    compile_cmd.add_argument("--repo-root", type=Path, default=Path.cwd())
    compile_cmd.add_argument("--ruleset", default="adnd1e")
    compile_cmd.add_argument("--skip-tests", action="store_true")
    compile_cmd.add_argument(
        "--review",
        type=Path,
        action="append",
        help=(
            "apply a Reviewer revision request; requires --revision for the new GUP number. "
            "Repeat in review order to apply a chain: later reviews win on disposition, and "
            "structural instructions from earlier ones are carried unless restated"
        ),
    )
    compile_cmd.add_argument(
        "--supersedes",
        help="prior GUP ID this revision replaces; auto-detected from the gup directory",
    )
    compile_cmd.add_argument(
        "--revision",
        type=int,
        help="GUP revision number; defaults to the GUR's revision",
    )
    pages_cmd = sub.add_parser(
        "verify-pages",
        help="check every page cited by a GUP against the page markers in the packet source",
    )
    pages_cmd.add_argument("packet_dir", nargs="+", type=Path)
    pages_cmd.add_argument("--gup-dir", type=Path, required=True)

    mig_cmd = sub.add_parser(
        "plan-migration",
        help="plan an approved canonical identity merge (DEC-2026-0007) as a migration GUP",
    )
    mig_cmd.add_argument("--repo-root", type=Path, default=Path.cwd())
    mig_cmd.add_argument("--ruleset", default="adnd1e")
    mig_cmd.add_argument("--out", type=Path, required=True,
                         help="path to write the migration GUP")
    mig_cmd.add_argument("--skip-tests", action="store_true")

    dec_cmd = sub.add_parser(
        "plan-decision-migration",
        help="plan the canonical changes an approved decision enumerates row by row",
    )
    dec_cmd.add_argument("decision", nargs="+", type=Path,
                         help="approved decision files, e.g. .../DEC-2026-0015.yaml")
    dec_cmd.add_argument("--repo-root", type=Path, default=Path.cwd())
    dec_cmd.add_argument("--ruleset", default="adnd1e")
    dec_cmd.add_argument("--out", type=Path, required=True)
    dec_cmd.add_argument("--gup-id", default="")
    dec_cmd.add_argument("--lineage-id", default="",
                         help="stable across revisions; defaults to MIG-<decision ids>")
    dec_cmd.add_argument("--revision", type=int, default=1)
    dec_cmd.add_argument(
        "--operation-model",
        choices=["decision_migration_v1", "decision_migration_v2"],
        default=None,
        help="declare the WORK_QUEUES 1.8 direct operation model. Refused when the "
        "plan contains an operation the model does not execute.",
    )
    dec_cmd.add_argument("--supersedes", default="")
    dec_cmd.add_argument("--book", default="phb")
    dec_cmd.add_argument("--source-id", default="phb-legacy-unspecified")
    dec_cmd.add_argument("--skip-tests", action="store_true")

    esc_cmd = sub.add_parser(
        "audit-escalation-ids",
        help="check escalation IDs and filenames against DEC-2026-0006",
    )
    esc_cmd.add_argument("--repo-root", type=Path, default=Path.cwd())
    esc_cmd.add_argument("--ruleset", default="adnd1e")

    lint_cmd = sub.add_parser(
        "lint-source",
        help="check a source markdown file against contracts/SOURCE_MARKDOWN.md",
    )
    lint_cmd.add_argument("source", nargs="+", type=Path)

    args = parser.parse_args(argv)

    if args.command == "verify-pages":
        return verify_pages(args.packet_dir, args.gup_dir)
    if args.command == "lint-source":
        return lint_source(args.source)
    if args.command == "plan-migration":
        return plan_migration(args)
    if args.command == "plan-decision-migration":
        return plan_decision_migration(args)
    if args.command == "audit-escalation-ids":
        return audit_escalation_ids(args.repo_root.resolve() / "rulesets" / args.ruleset)

    root: Path = args.repo_root.resolve()

    registry = NodeRegistry.load(root / "rulesets" / args.ruleset / "registries" / "nodes.csv")
    canonical = CanonicalEdges.load(root / "rulesets" / args.ruleset / "canonical" / "edges_master.csv")
    general_rules = load_general_rules(root / "rulesets" / args.ruleset / "registries" / "general_rules.json")
    governance = Governance.load(root / "rulesets" / args.ruleset)

    test_result = (
        {"ran": False, "reason": "skipped by flag"}
        if args.skip_tests
        else run_tests(root / "tooling" / "builder" / "tests")
    )
    if test_result.get("ran") and not test_result.get("passed"):
        print(f"builder test suite failed: {test_result}", file=sys.stderr)
        return 2

    compiler = Compiler(registry, canonical, general_rules, governance)
    exit_code = 0

    directives = None
    if args.review:
        directives = ReviewDirectives.load_chain(args.review)
        if len(args.gur) != 1:
            print("--review applies to exactly one GUR", file=sys.stderr)
            return 2
        if args.revision is None:
            print(
                "--review requires --revision: a revision request advances the GUP number, and "
                "FILE_NAMING forbids overwriting a prior revision",
                file=sys.stderr,
            )
            return 2

    for gur_path in args.gur:
        import yaml as _yaml

        gup_dir = gur_path.resolve().parent.parent / "gup"
        packet_id = (
            _yaml.safe_load(gur_path.read_text(encoding="utf-8")) or {}
        ).get("packet_id") or ""
        revision = args.revision
        if revision is None:
            revision = next_revision(gup_dir, packet_id)
        supersedes = args.supersedes
        if supersedes is None:
            supersedes = previous_revision(gup_dir, gur_path, revision)
        result = compiler.compile(
            gur_path, directives=directives, revision=revision, supersedes=supersedes
        )
        report_dir = root / "build" / "reports"
        try:
            written = write_all(result, gup_dir, report_dir, test_result)
        except FileExistsError as clash:
            print(str(clash), file=sys.stderr)
            return 2

        print(
            f"{result.gup_id}: status={result.status} "
            f"edges={len(result.rows)} errors={len(result.errors)} "
            f"warnings={len(result.warnings)} escalations={len(result.escalations)} "
            f"duplicates={len(result.duplicate_findings)}"
        )
        for path in written:
            print(f"  wrote {path.relative_to(root) if path.is_relative_to(root) else path}")
        if result.blocks_approval:
            exit_code = max(exit_code, 1)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
