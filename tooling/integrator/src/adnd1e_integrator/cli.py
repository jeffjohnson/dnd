"""Command line entry point for the AD&D 1e Integrator.

    python -m adnd1e_integrator queue    [--repo-root PATH]
    python -m adnd1e_integrator validate [--repo-root PATH]
    python -m adnd1e_integrator integrate [BUNDLE_ID ...] [--dry-run]

`queue` derives ready work from artifact lineage (contracts/WORK_QUEUES.md).
`validate` runs the invariant suite over canonical state and writes nothing.
`integrate` applies a batch transactionally and records it.

Exit codes follow the WORK_QUEUES scanner convention where they apply:
`0` clean, `1` work remains or a batch was rejected, `2` lineage or tooling error.
"""

from __future__ import annotations

import argparse
import json
import sys
import unittest
from pathlib import Path

from .bundles import ready_queue
from .canonical import EDGE_COLUMNS, CanonicalGraph, CanonicalPaths
from .derive import load_role_profile
from .integrate import IntegrationError, integrate
from .invariants import approved_prefixes, check, check_derived_state
from .records import write_records

DEFAULT_BOOKS = ["phb", "dmg", "mm", "ua"]


def _constitution_version(root: Path, ruleset_id: str) -> str:
    text = (root / "rulesets" / ruleset_id / "governance" / "constitution.md").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("**Version "):
            return line.split("**Version ", 1)[1].split(".**", 1)[0]
    return "unknown"


def cmd_queue(args) -> int:
    root = Path(args.repo_root).resolve()
    queue = ready_queue(root, args.ruleset_id, args.books)
    payload = {
        "ruleset_id": args.ruleset_id,
        "ready_count": len(queue["ready"]),
        "ready": [
            {
                "bundle_id": b.bundle_id,
                "book_id": b.book_id,
                "packet_id": b.packet_id,
                "review_id": b.review_id,
                "gup_id": b.gup_id,
                "components": [c["path"] for c in b.component_records(root)],
                "legacy_inference": b.legacy_inferences,
            }
            for b in queue["ready"]
        ],
        "integrated": [{"bundle_id": b.bundle_id, "integration_id": i}
                       for b, i in queue["integrated"]],
        "diagnostics": queue["diagnostics"],
    }
    print(json.dumps(payload, indent=2))
    if queue["diagnostics"]:
        return 2
    return 1 if queue["ready"] else 0


def cmd_validate(args) -> int:
    root = Path(args.repo_root).resolve()
    paths = CanonicalPaths(root=root, ruleset_id=args.ruleset_id)
    graph = CanonicalGraph.load(paths)
    prefixes = approved_prefixes(root / "rulesets" / args.ruleset_id / "governance" / "constitution.md")
    profile = load_role_profile(root / "rulesets" / args.ruleset_id / "profiles" / "roles.yaml")
    general_rules = set(json.loads(
        (root / "rulesets" / args.ruleset_id / "registries" / "general_rules.json")
        .read_text(encoding="utf-8")).keys())

    result = check(graph.edges, graph.nodes, prefixes, general_rules, EDGE_COLUMNS)
    check_derived_state(graph.edges, graph.nodes, profile["thresholds"], result)

    print(json.dumps({
        "edges": len(graph.edges),
        "nodes": len(graph.nodes),
        "findings": len(result.findings),
        "by_invariant": {str(k): v for k, v in result.by_invariant().items()},
        "affected_rows": len({f.row for f in result.findings if f.row}),
        "checked": result.checked,
        "not_machine_checkable": result.not_machine_checkable,
        "sample": [f.as_dict() for f in result.findings[:20]],
    }, indent=2))
    return 0 if result.ok else 1


def cmd_integrate(args) -> int:
    root = Path(args.repo_root).resolve()
    queue = ready_queue(root, args.ruleset_id, args.books)
    ready = queue["ready"]

    if args.bundle_ids:
        wanted = set(args.bundle_ids)
        selected = [b for b in ready if b.bundle_id in wanted]
        missing = wanted - {b.bundle_id for b in selected}
        if missing:
            print(f"not ready or not found: {sorted(missing)}", file=sys.stderr)
            return 2
    else:
        selected = ready

    if not selected:
        print("no ready Approved bundle; nothing to integrate")
        return 0

    try:
        batch = integrate(root, args.ruleset_id, selected,
                          integration_id=args.integration_id, dry_run=args.dry_run)
    except IntegrationError as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(json.dumps({
            "dry_run": True,
            "integration_id": batch.integration_id,
            "edges_added": len(batch.added),
            "nodes_changed": len(batch.node_deltas),
            "baseline_findings": batch.baseline["findings"],
            "post_batch_findings": batch.after["findings"],
        }, indent=2))
        return 0

    written = write_records(batch, root, args.ruleset_id,
                            _constitution_version(root, args.ruleset_id))
    print(json.dumps({
        "integration_id": batch.integration_id,
        "bundles": [v.bundle.bundle_id for v in batch.verifications],
        "edges": {"before": batch.pre_counts["edges"], "after": batch.post_counts["edges"]},
        "nodes_changed": len(batch.node_deltas),
        "records": {k: str(v.relative_to(root)) for k, v in written.items()},
    }, indent=2))
    return 0


def cmd_test(args) -> int:
    test_dir = Path(args.repo_root).resolve() / "tooling" / "integrator" / "tests"
    loader = unittest.TestLoader()
    suite = loader.discover(str(test_dir), pattern="test_*.py", top_level_dir=str(test_dir))
    outcome = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if outcome.wasSuccessful() else 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="adnd1e_integrator")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--ruleset-id", default="adnd1e")
    parser.add_argument("--books", nargs="*", default=DEFAULT_BOOKS)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("queue").set_defaults(func=cmd_queue)
    sub.add_parser("validate").set_defaults(func=cmd_validate)
    sub.add_parser("test").set_defaults(func=cmd_test)

    run = sub.add_parser("integrate")
    run.add_argument("bundle_ids", nargs="*")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--integration-id")
    run.set_defaults(func=cmd_integrate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
