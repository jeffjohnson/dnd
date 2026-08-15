"""Canonical serialization of a compiled patch.

Serialization is byte-deterministic: fixed key order, fixed row order, LF
endings, no timestamps inside the artifacts. Two runs over the same GUR and the
same registry produce identical files.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import yaml

from .compiler import TOOL_NAME, TOOL_VERSION, CompileResult, edge_row
from .vocab import COLUMNS


class _Dumper(yaml.SafeDumper):
    """Block-style YAML with stable indentation."""

    def increase_indent(self, flow=False, indentless=False):  # noqa: ARG002
        return super().increase_indent(flow, False)


def _str_presenter(dumper: yaml.Dumper, data: str):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_Dumper.add_representer(str, _str_presenter)


def _dump(payload: dict) -> str:
    return yaml.dump(payload, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100)


def validation_report(result: CompileResult, test_result: dict) -> dict:
    """The machine-readable validation report."""
    by_rule: dict[str, int] = {}
    for finding in result.findings:
        by_rule[finding.rule] = by_rule.get(finding.rule, 0) + 1

    polarity_basis: dict[str, int] = {}
    for row in result.additions:
        basis = row["polarity_basis"]
        polarity_basis[basis] = polarity_basis.get(basis, 0) + 1

    edge_types: dict[str, int] = {}
    for row in result.additions:
        edge_types[row["edge_type"]] = edge_types.get(row["edge_type"], 0) + 1

    return {
        "gup_id": result.gup_id,
        "gur_id": result.gur_id,
        "packet_id": result.packet_id,
        "gur_checksum": result.gur_checksum,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "test_result": test_result,
        "status": result.status,
        "approval_ready": not result.blocks_approval,
        "summary": {
            "edges_in": result.edges_in,
            "edges_compiled": len(result.rows),
            "edges_rejected": result.edges_in - len(result.rows),
            "edge_additions": len(result.additions),
            "edge_pending_additions": len(result.batch_satisfiable_additions),
            "edge_blocked_additions": len(result.blocked_additions),
            "edge_updates": len(result.updates),
            "errors": len(result.errors),
            "warnings": len(result.warnings),
            "escalations": len(result.escalations),
            "escalations_since_decided": len(result.resolved_escalations),
            "architect_overrides": len(result.architect_overrides),
            "node_proposals_rejected": len(result.rejected_node_proposals),
            "direction_findings": len(result.direction_findings),
            "node_additions_proposed": len(result.node_additions),
            "cross_packet_dependencies": len(result.cross_packet_dependencies),
            "duplicate_findings": len(result.duplicate_findings),
            "neighbourhood_conflicts": len(result.conflict_findings),
        },
        "derivations": {
            "polarity_basis": dict(sorted(polarity_basis.items())),
            "edge_types": dict(sorted(edge_types.items())),
        },
        "findings_by_rule": dict(sorted(by_rule.items())),
        "findings": [f.as_dict() for f in result.findings],
        "duplicates": result.duplicate_findings,
        "cross_packet_dependencies": result.cross_packet_dependencies,
        "neighbourhood_conflicts": result.conflict_findings,
        "escalations": result.escalations,
        "escalations_since_decided": result.resolved_escalations,
        "architect_dispositions_applied": result.architect_overrides,
        "direction_findings": result.direction_findings,
    }


def gup_document(result: CompileResult, test_result: dict) -> dict:
    envelope = result.envelope
    document = {
        "schema_version": envelope.get("schema_version", "1.0"),
        "id": result.gup_id,
        "status": result.status,
        "ruleset_id": envelope.get("ruleset_id"),
        "book_id": envelope.get("book_id"),
        "source_id": envelope.get("source_id"),
        "packet_id": result.packet_id,
        "constitution_version": envelope.get("constitution_version"),
        # WORK_QUEUES 1.2: a GUP declares which of the two lineage roots it has.
        # A packet update consumes one active-leaf GUR; the alternative is a
        # decision migration, which has no GUR at all. Legacy GUPs that predate
        # the contract omit this and are read as packet updates only where their
        # GUR provenance is unambiguous.
        "artifact_kind": "packet_update",
        "revision": result.revision,
        "supersedes": result.supersedes,
        "handoff": result.handoff,
        "provenance": {
            "gur_id": result.gur_id,
            "gur_checksum": result.gur_checksum,
            "gur_constitution_version": envelope.get("gur_constitution_version", ""),
            "review_id": result.review_id,
            "builder_tool": TOOL_NAME,
            "builder_version": TOOL_VERSION,
            "test_result": test_result,
        },
        "approval_ready": not result.blocks_approval,
        "blocking_reason": (
            None
            if not result.blocks_approval
            else (
                f"{len(result.errors)} validation error(s) and {len(result.escalations)} "
                f"unresolved escalation(s); a schema-valid patch is not an approvable one"
            )
        ),
        "node_changes": {
            "additions_proposed": result.node_additions,
            "proposals_rejected_by_decision": result.rejected_node_proposals,
            "cross_packet_dependencies": result.cross_packet_dependencies,
            "cross_packet_note": (
                "Identities another packet minted and this one reuses, as the GUR declares them. "
                "They are not proposals: the originating packet owns the registration, and rows "
                "reaching them are held pending until it is applied."
            ),
            "note": (
                "Registry changes are isolated from edge insertions (Builder instruction 13). "
                "Builder may not mint node identity; each addition requires an Architect decision."
            ),
        },
        "edge_changes": {
            "additions": [edge_row(row) | {"ref": row["ref"]} for row in result.additions],
            "pending_additions": [
                edge_row(row) | {"ref": row["ref"]}
                for row in result.batch_satisfiable_additions
            ],
            # Held for a node another packet mints. Named apart so the Approved
            # bundle cannot merge them in with the rows this batch can satisfy.
            "blocked_additions": [
                edge_row(row) | {"ref": row["ref"]} for row in result.blocked_additions
            ],
            "pending_note": (
                "These rows reference a node this patch only proposes. They satisfy every other "
                "check but violate invariant 1 until the node is registered, so they are held out "
                "of the additions set and out of the edges CSV. They are not rejected."
            ),
            "updates": result.updates,
            "removals": [],
        },
        "derivations": {
            "note": (
                "polarity and polarity_basis on the ten deterministic edge types are assigned by "
                "the build (constitution 6.1, invariants 13-14). Authored polarity on MODIFIES, "
                "TRIGGERS and CONSTRAINS is carried through unchanged and validated only."
            ),
            "polarity_basis_counts": validation_report(result, test_result)["derivations"][
                "polarity_basis"
            ],
        },
        "duplicate_findings": result.duplicate_findings,
        "neighbourhood_conflicts": result.conflict_findings,
        "escalations": result.escalations,
        "escalations_since_decided": result.resolved_escalations,
        "architect_dispositions_applied": result.architect_overrides,
        "direction_findings": result.direction_findings,
        "validation_summary": validation_report(result, test_result)["summary"],
        "validation_report": f"build/reports/{result.gup_id}.validation.json",
    }

    if result.review_id:
        document["reviewer_directives_applied"] = {
            "review_id": result.review_id,
            "corrections": result.corrections_applied,
            "rejected_rows": result.rejected_rows,
            "note": (
                "Reviewer decisions are applied as given; the Reviewer owns what an edge asserts. "
                "Corrected values are then revalidated, and a correction that violates the "
                "constitution is reported like any other defect rather than passed through."
            ),
        }

    return document


def edges_csv(result: CompileResult) -> str:
    """The 18-column edge additions, in canonical order.

    Updates are deliberately absent: they are not new rows, and emitting them
    here would read as 5 extra insertions to anyone diffing the file.
    """
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(COLUMNS), lineterminator="\n")
    writer.writeheader()
    for row in result.additions:
        writer.writerow(edge_row(row))
    return buffer.getvalue()


def pending_csv(result: CompileResult) -> str:
    """The rows held out of `.edges.csv`, in the same 18 columns.

    A patch whose every row depends on a node it also proposes emits a
    header-only `.edges.csv`, because a row pointing at an unregistered node
    would breach invariant 1. That is correct and it is also indistinguishable,
    on disk, from a patch with nothing to say: the alignment-graph GUP's empty
    edge CSV hashed byte-identical to the preamble GUP's, and an Approved bundle
    was assembled from it whose operation index asserted four edges the CSV did
    not contain. The Integrator caught it at the precondition gate.

    The rows were never missing -- they are in the GUP under
    `edge_changes.pending_additions`, complete and cited. What was missing was a
    file to read them from. This is that file. It is not an integration input:
    the Integrator applies `.edges.csv`, and these rows enter canonical only
    once the registry change they depend on is applied and the Reviewer carries
    them into the Approved bundle.
    """
    return _rows_csv(result.batch_satisfiable_additions)


def blocked_csv(result: CompileResult) -> str:
    """Pending rows another packet has to land before these can integrate.

    Split out from `.pending.csv` because the two are not interchangeable and
    the Approved bundle has to treat them differently. A row waiting on a node
    this patch proposes travels with the patch; a row waiting on a node another
    packet mints cannot integrate until that packet does.

    INT-20260814-003 refused the psionics bundle over exactly this: nine
    endpoints minted by the magic-user and druid packets, correctly held and
    correctly declared under `cross_packet_dependencies`, but merged into one
    undifferentiated CSV where nothing downstream could separate the 190 rows
    the batch could satisfy from the 13 it could not.
    """
    return _rows_csv(result.blocked_additions)


def _rows_csv(rows) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(COLUMNS), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(edge_row(row))
    return buffer.getvalue()


def write_all(
    result: CompileResult,
    gup_dir: Path,
    report_dir: Path,
    test_result: dict,
    allow_overwrite: bool = False,
) -> list[Path]:
    """Publish a GUP. A revision that already exists is never rewritten.

    A published revision is immutable. A Reviewer may already have hashed it,
    and rewriting it in place leaves that Review pinning content that no longer
    exists anywhere -- INT-20260812-002 rejected four bundles for exactly that,
    with the declared checksums matching no file on disk. Recompiling at an
    existing `--revision` used to clobber silently, so the damage was invisible
    until the Integrator refused the bundle.
    """
    gup_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    gup_path = gup_dir / f"{result.gup_id}.yaml"
    csv_path = gup_dir / f"{result.gup_id}.edges.csv"

    if gup_path.exists() and not allow_overwrite:
        raise FileExistsError(
            f"{result.gup_id} is already published at {gup_path}. A published revision is "
            f"immutable -- a Review may already pin its checksum. Publish the next revision "
            f"instead, or pass allow_overwrite only for a revision nothing has consumed."
        )
    report_path = report_dir / f"{result.gup_id}.validation.json"

    gup_path.write_text(_dump(gup_document(result, test_result)), encoding="utf-8", newline="\n")
    csv_path.write_text(edges_csv(result), encoding="utf-8", newline="\n")
    report_path.write_text(
        json.dumps(validation_report(result, test_result), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    written = [gup_path, csv_path, report_path]

    # Written only when there is something to hold, so its presence is itself
    # the signal that `.edges.csv` is short by design rather than by accident.
    if result.batch_satisfiable_additions:
        pending_path = gup_dir / f"{result.gup_id}.pending.csv"
        pending_path.write_text(pending_csv(result), encoding="utf-8", newline="\n")
        written.append(pending_path)
    # Its presence is the signal that this patch cannot integrate on its own,
    # however complete it otherwise looks.
    if result.blocked_additions:
        blocked_path = gup_dir / f"{result.gup_id}.blocked.csv"
        blocked_path.write_text(blocked_csv(result), encoding="utf-8", newline="\n")
        written.append(blocked_path)
    return written
