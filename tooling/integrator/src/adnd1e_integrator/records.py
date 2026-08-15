"""Integration records: manifest, validation report, and human-readable diff.

The completion condition in the role instructions is that "another fresh
Integrator agent can reconstruct exactly what changed from the manifest alone".
Everything needed for that reconstruction is written here -- inputs and their
checksums, pre/post counts and file checksums, every added row with its full
provenance chain, every recomputed node, tool and schema versions, the invariant
outcome, and the rollback snapshot.

The Approved bundles themselves are never touched. Consumption is recorded by
naming their IDs and checksums in `approved_bundles` (role instructions, step 16
and the Outputs section).
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from . import TOOL_NAME, __version__
from .canonical import GRAPH_SCHEMA_VERSION, CanonicalPaths
from .checksums import checksum_file
from .integrate import Batch


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{_dt.datetime.now(_dt.timezone.utc).microsecond // 1000:03d}Z"


def build_manifest(batch: Batch, root: Path, ruleset_id: str, constitution_version: str) -> dict:
    paths = CanonicalPaths(root=root, ruleset_id=ruleset_id)
    return {
        "schema_version": "1.0",
        "id": batch.integration_id,
        "integration_id": batch.integration_id,
        "status": "integrated",
        "ruleset_id": ruleset_id,
        "constitution_version": constitution_version,
        "revision": 1,
        "supersedes": None,
        "handoff": {
            "next_role": "none",
            "readiness": "terminal",
            "reason": "canonical state updated, derived artifacts rebuilt, invariants run",
            "blocking_ids": [],
        },
        "integrated_at_utc": _utc_now(),
        "tool": {"name": TOOL_NAME, "version": __version__},
        "schema_versions": {
            "artifact": "1.0",
            "graph_json": GRAPH_SCHEMA_VERSION,
            "edge_columns": 18,
        },
        "approved_bundles": [
            {
                "bundle_id": v.bundle.bundle_id,
                "book_id": v.bundle.book_id,
                "packet_id": v.bundle.packet_id,
                "review_id": v.bundle.review_id,
                "gup_id": v.bundle.gup_id,
                "gur_id": v.bundle.gur_id,
                "constitution_version": v.bundle.constitution_version,
                "rows_applied": len(v.rows),
                "operations": v.operations.summary(),
                "components": v.bundle.component_records(root),
                "review_checksum": checksum_file(v.bundle.review_path),
                "legacy_inferences": v.bundle.legacy_inferences,
                "advisories": [c.as_dict() for c in v.advisories],
            }
            for v in batch.verifications
        ],
        "architect_decisions": sorted({
            d
            for v in batch.verifications
            for d in ((v.bundle.review.get("input_provenance") or {})
                      .get("architect_decisions_consulted") or [])
        }),
        "counts": {
            "before": {"edges": batch.pre_counts["edges"], "nodes": batch.pre_counts["nodes"],
                       "registry": batch.pre_counts["registry"]},
            "after": {"edges": batch.post_counts["edges"], "nodes": batch.post_counts["nodes"],
                      "registry": batch.post_counts["registry"]},
            "edges_added": batch.post_counts["edges"] - batch.pre_counts["edges"],
            "edges_updated": len(batch.updated),
            "nodes_added": batch.post_counts["nodes"] - batch.pre_counts["nodes"],
            "registry_rows_added": batch.post_counts["registry"] - batch.pre_counts["registry"],
            "declared_by_bundles": sum(
                len(v.operations.added_rows) for v in batch.verifications),
        },
        "canonical_files": {
            "edges_master.csv": {
                "before": batch.pre_counts["edges_checksum"],
                "after": batch.post_counts["edges_checksum"],
            },
            "nodes_master.csv": {
                "before": batch.pre_counts["nodes_checksum"],
                "after": batch.post_counts["nodes_checksum"],
            },
            "graph.json": {
                "before": batch.pre_counts["graph_json_checksum"],
                "after": batch.post_counts["graph_json_checksum"],
            },
            "registries/nodes.csv": {
                "before": batch.pre_counts["registry_checksum"],
                "after": batch.post_counts["registry_checksum"],
            },
        },
        "registry_changes": {
            "nodes_added": batch.registrations,
            "nodes_added_without_edges": batch.registrations_without_edges,
            "nodes_retired": [],
            "derived_columns_resynced": len(batch.registry_resync),
            "preexisting_drift_corrected": batch.registry_preexisting_drift,
            "note": (
                "`degree` and `roles` in registries/nodes.csv are a derived snapshot of "
                "canonical state. INT-20260730-001 recomputed node rows without "
                "resyncing them; that drift is corrected here and the resync is now "
                "part of every batch."
            ),
        },
        "edges_added": batch.added,
        "edges_updated": batch.updated,
        "derived_rebuild": {
            "polarity_recomputed": True,
            "polarity_corrections": batch.polarity_corrections,
            "degrees_and_roles_recomputed": True,
            "nodes_changed": len(batch.node_deltas),
            "graph_json_rebuilt_from": "edges_master.csv + nodes_master.csv",
            "role_profile": "roles-v1",
        },
        "node_deltas": batch.node_deltas,
        "validation": {
            "baseline_findings": batch.baseline["findings"],
            "post_batch_findings": batch.after["findings"],
            "introduced_by_this_batch": 0,
            "report": f"rulesets/{ruleset_id}/reports/{batch.integration_id}.validation.json",
        },
        "rollback_snapshot": batch.snapshot,
        "commit_hash": None,
    }


def build_validation_report(batch: Batch, ruleset_id: str) -> dict:
    return {
        "schema_version": "1.0",
        "integration_id": batch.integration_id,
        "ruleset_id": ruleset_id,
        "tool": {"name": TOOL_NAME, "version": __version__},
        "generated_at_utc": _utc_now(),
        "preconditions": [
            {
                "bundle_id": v.bundle.bundle_id,
                "checks": [c.as_dict() for c in v.checks],
                "blocking_failures": len(v.blocking_failures),
                "advisories": len(v.advisories),
            }
            for v in batch.verifications
        ],
        "invariants": {
            "checked": batch.after["checked"],
            "not_machine_checkable": batch.after["not_machine_checkable"],
            "baseline": {
                "findings": batch.baseline["findings"],
                "by_invariant": {str(k): v for k, v in batch.baseline["by_invariant"].items()},
                "affected_rows": batch.baseline["affected_rows"],
                "note": (
                    "Defects already present in canonical state before this batch. "
                    "They are carried forward, not accepted. DEC-2026-0004 owns the "
                    "prefix findings; the polarity_basis findings await the legacy "
                    "migration recorded in canonical/BASELINE.md."
                ),
            },
            "after_batch": {
                "findings": batch.after["findings"],
                "by_invariant": {str(k): v for k, v in batch.after["by_invariant"].items()},
            },
            "introduced_by_this_batch": 0,
            "regressions": {},
            "result": "pass",
        },
        "counts": {
            "edges_before": batch.pre_counts["edges"],
            "edges_after": batch.post_counts["edges"],
            "edges_updated_in_place": len(batch.updated),
            "nodes_before": batch.pre_counts["nodes"],
            "nodes_after": batch.post_counts["nodes"],
            "registry_before": batch.pre_counts["registry"],
            "registry_after": batch.post_counts["registry"],
            "declared_vs_actual": "match",
        },
        "operations": {
            "compare_and_swap_updates": batch.updated,
            "node_registrations": batch.registrations,
            "registry_derived_resync": len(batch.registry_resync),
            "registry_preexisting_drift": batch.registry_preexisting_drift,
        },
        "derived_artifacts": {
            "graph_json": "rebuilt from canonical tabular data",
            "node_degrees": "recomputed for every node",
            "node_roles": "recomputed for every node under roles-v1",
            "reproducible": True,
        },
    }


def render_diff(batch: Batch, ruleset_id: str) -> str:
    lines: list[str] = []
    add = lines.append

    add(f"# Integration {batch.integration_id}")
    add("")
    add(f"- ruleset: `{ruleset_id}`")
    add(f"- tool: `{TOOL_NAME} {__version__}`")
    add(f"- bundles applied: {len(batch.verifications)}")
    add("")

    add("## Approved bundles consumed")
    add("")
    add("| Bundle | Packet | Review | Add | Pending | Update | Nodes |")
    add("|---|---|---|---|---|---|---|")
    for v in batch.verifications:
        o = v.operations
        add(f"| `{v.bundle.bundle_id}` | `{v.bundle.packet_id}` | "
            f"`{v.bundle.review_id}` | {len(o.additions)} | {len(o.pending_additions)} | "
            f"{len(o.updates)} | {len(o.registrations)} |")
    add("")

    add("## Counts")
    add("")
    add("| | Before | After | Delta |")
    add("|---|---|---|---|")
    for label, key in (("Edges", "edges"), ("Nodes", "nodes"), ("Registry", "registry")):
        before, after = batch.pre_counts[key], batch.post_counts[key]
        add(f"| {label} | {before:,} | {after:,} | {after - before:+d} |")
    add("")

    if batch.registrations:
        add("## Node registry additions")
        add("")
        if any(r.get("basis") == "decision_migration" for r in batch.registrations):
            add("Registered on the authority of the Decision named against each row. A")
            add("packet registration is instead sequenced before the edges depending on it,")
            add("per that manifest's `node_operations.sequencing`.")
        else:
            add("Registered before the edges that depend on them, per each manifest's")
            add("`node_operations.sequencing`.")
        add("")
        add("| Node | Label | Kind | Approved by | Depends |")
        add("|---|---|---|---|---|")
        for r in batch.registrations:
            # Rendering runs after the transaction has committed, so a missing
            # optional field must not be able to abort the record write.
            add(f"| `{r['id']}` | {r['label']} | {r['kind']} | `{r['review_id']}` | "
                f"{', '.join(r.get('edges_depending_on_it') or []) or '-'} |")
        add("")

    if batch.node_replacements:
        add("## Node identity replacements")
        add("")
        add("`decision_migration_v1`: each retires one approved ID and registers its")
        add("replacement. No alias is retained, so a replacement is net zero in the registry.")
        add("")
        add("| Retired | Replacement | Authority | Incident rows |")
        add("|---|---|---|---|")
        for r in batch.node_replacements:
            add(f"| `{r['retired_id']}` ({r['retired_label']}) | "
                f"`{r['canonical_id']}` ({r['canonical_label']}) | `{r['authority']}` | "
                f"{', '.join(str(x) for x in r['incident_rows']) or '-'} |")
        add("")

    if batch.repoints:
        add("## Endpoint repoints")
        add("")
        add("Each changes one endpoint ID and its paired label by compare-and-swap against")
        add("a complete 18-field before-image. No other field is touched.")
        add("")
        add("| Row | Field | From | To | Authority |")
        add("|---|---|---|---|---|")
        for r in batch.repoints:
            for name, delta in sorted(r["changes"].items()):
                add(f"| {r['canonical_row']} | `{name}` | {delta['from']} | {delta['to']} | "
                    f"`{r['authority']}` |")
        add("")

    if batch.removals:
        add("## Canonical rows removed")
        add("")
        add("Exact no-replacement removals, applied after the repoints in descending row")
        add("order so earlier physical locators cannot shift.")
        add("")
        for r in batch.removals:
            add(f"- row {r['canonical_row']} — {r['assertion']} ({r['citation']}), "
                f"authority `{r['authority']}`")
        add("")

    if batch.registrations_without_edges:
        add(f"{len(batch.registrations_without_edges)} of those carry no edge yet. The "
            "registry is the list of approved node IDs (constitution 3.2) and is already")
        add("a superset of the graph's nodes, so an approved identity may sit at degree 0 "
            "until a later packet asserts a relationship for it:")
        add("")
        for r in batch.registrations_without_edges:
            add(f"- `{r['id']}` — {r['label']}")
        add("")

    if batch.updated:
        add("## Edges updated in place")
        add("")
        add("Each row was compare-and-swapped: the manifest's declared canonical")
        add("values had to still hold, and the endpoints had to match, before any")
        add("field was written.")
        add("")
        for u in batch.updated:
            add(f"**Row {u['canonical_row']}** — `{u['ref']}` from `{u['bundle_id']}`")
            add("")
            if u["assertion_before"] != u["assertion_after"]:
                add(f"- assertion: `{u['assertion_before']}` -> `{u['assertion_after']}`")
            else:
                add(f"- assertion: `{u['assertion_before']}` (unchanged)")
            for f, c in sorted(u["changes"].items()):
                add(f"- `{f}`: {c['from']!r} -> {c['to']!r}")
            if u["differences_not_applied"]:
                add(f"- left at the canonical value on purpose: "
                    f"{', '.join('`%s`' % f for f in u['differences_not_applied'])}")
            add("")

    if batch.added:
        add("## Edges added")
        add("")
        add("| Row | Assertion | Aspect | Citation | Bundle |")
        add("|---|---|---|---|---|")
        for a in batch.added:
            add(f"| {a['row']} | `{a['assertion']}` | {a['aspect']} | "
                f"{a['citation']} | `{a['bundle_id']}` |")
        add("")
    else:
        add("## Edges added")
        add("")
        add("None. Every bundle in this batch carried a null yield.")
        add("")

    if batch.polarity_corrections:
        add("## Deterministic polarity corrected by the build")
        add("")
        for c in batch.polarity_corrections:
            add(f"- row {c['row']} `{c['source_id']} {c['edge_type']} {c['target_id']}`: "
                f"{c['from']['polarity']}/{c['from']['polarity_basis']} -> "
                f"{c['to']['polarity']}/{c['to']['polarity_basis']}")
        add("")

    add("## Nodes recomputed")
    add("")
    if batch.node_deltas:
        add("| Node | degree | core | in | out | roles |")
        add("|---|---|---|---|---|---|")
        for d in batch.node_deltas:
            if d["change"] == "created":
                add(f"| `{d['id']}` | new | | | | {d['to']['roles'] or '-'} |")
                continue
            f, t = d["from"], d["to"]
            def cell(k):
                return f"{f[k]} -> {t[k]}" if f[k] != t[k] else f[k]
            roles = f"{f['roles'] or '-'} -> {t['roles'] or '-'}" if f["roles"] != t["roles"] else "unchanged"
            add(f"| `{d['id']}` | {cell('degree')} | {cell('core_degree')} | "
                f"{cell('in_degree')} | {cell('out_degree')} | {roles} |")
    else:
        add("No node degree or role changed.")
    add("")

    if batch.registry_resync:
        add("## Registry derived columns")
        add("")
        add(f"`degree` and `roles` were resynced for {len(batch.registry_resync):,} "
            "registry row(s) from the post-batch node table.")
        if batch.registry_preexisting_drift:
            add("")
            add(f"Of these, **{len(batch.registry_preexisting_drift)}** were already "
                "stale before this batch — INT-20260730-001 recomputed those node rows "
                "but did not resync the registry. The resync is now part of every batch.")
            add("")
            add("| Node | degree | roles |")
            add("|---|---|---|")
            for d in batch.registry_preexisting_drift:
                deg = (f"{d['degree']['registry']} -> {d['degree']['canonical']}"
                       if d["degree"]["registry"] != d["degree"]["canonical"] else "unchanged")
                roles = (f"{d['roles']['registry'] or '-'} -> {d['roles']['canonical'] or '-'}"
                         if d["roles"]["registry"] != d["roles"]["canonical"] else "unchanged")
                add(f"| `{d['id']}` | {deg} | {roles} |")
        add("")

    add("## Invariants")
    add("")
    add(f"- baseline findings before this batch: **{batch.baseline['findings']:,}** "
        f"across {batch.baseline['affected_rows']:,} row(s)")
    add(f"- findings after this batch: **{batch.after['findings']:,}**")
    add("- introduced by this batch: **0**")
    resolved = batch.baseline["findings"] - batch.after["findings"]
    if resolved > 0:
        add(f"- pre-existing findings resolved by this batch: **{resolved}**")
    add("")
    add("Baseline findings by invariant:")
    add("")
    add("| Invariant | Before | After | Delta |")
    add("|---|---|---|---|")
    keys = sorted(set(batch.baseline["by_invariant"]) | set(batch.after["by_invariant"]))
    for k in keys:
        before = batch.baseline["by_invariant"].get(k, 0)
        after = batch.after["by_invariant"].get(k, 0)
        add(f"| {k} | {before:,} | {after:,} | {after - before:+d} |")
    add("")

    return "\n".join(lines) + "\n"


def write_records(batch: Batch, root: Path, ruleset_id: str, constitution_version: str) -> dict[str, Path]:
    paths = CanonicalPaths(root=root, ruleset_id=ruleset_id)
    paths.manifests_dir.mkdir(parents=True, exist_ok=True)
    paths.reports_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = paths.manifests_dir / f"{batch.integration_id}.json"
    validation_path = paths.reports_dir / f"{batch.integration_id}.validation.json"
    diff_path = paths.reports_dir / f"{batch.integration_id}.diff.md"

    manifest = build_manifest(batch, root, ruleset_id, constitution_version)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    validation_path.write_text(
        json.dumps(build_validation_report(batch, ruleset_id), indent=2) + "\n", encoding="utf-8")
    diff_path.write_text(render_diff(batch, ruleset_id), encoding="utf-8")

    written = {"manifest": manifest_path, "validation": validation_path, "diff": diff_path}

    # Book-scoped integration copies (contracts/FILE_NAMING.md).
    for v in batch.verifications:
        book_dir = root / "books" / ruleset_id / v.bundle.book_id / "artifacts" / "integrated"
        if not book_dir.exists():
            continue
        record = {
            "schema_version": "1.0",
            "id": f"{batch.integration_id}-{v.bundle.bundle_id}",
            "status": "integrated",
            "ruleset_id": ruleset_id,
            "book_id": v.bundle.book_id,
            "packet_id": v.bundle.packet_id,
            "constitution_version": v.bundle.constitution_version or constitution_version,
            "revision": 1,
            "supersedes": None,
            "handoff": {
                "next_role": "none",
                "readiness": "terminal",
                "reason": "bundle consumed by an integration manifest",
                "blocking_ids": [],
            },
            "integration_id": batch.integration_id,
            "integration_manifest": manifest_path.relative_to(root).as_posix(),
            "bundle_id": v.bundle.bundle_id,
            "review_id": v.bundle.review_id,
            "gup_id": v.bundle.gup_id,
            "gur_id": v.bundle.gur_id,
            "rows_applied": len(v.rows),
            "components": v.bundle.component_records(root),
        }
        path = book_dir / f"{batch.integration_id}-{v.bundle.bundle_id}.json"
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        written[f"integrated:{v.bundle.bundle_id}"] = path

    return written
