"""Package an authored Review without supplying or changing its judgments."""
from __future__ import annotations

import copy
import csv
import io
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for relative in ("tooling/common", "tooling/builder/src", "tooling/integrator/src"):
    sys.path.insert(0, str(ROOT / relative))

from artifact_io import Output, PublicationError, artifact_schemas, contained, digest, load_mapping, validate_content, yaml_bytes
from adnd1e_builder.review import ReviewDirectives
from adnd1e_builder.vocab import COLUMNS
from adnd1e_integrator.operations import read_operations
from validate_artifact import _schema_registry


def _require(condition, message):
    if not condition:
        raise PublicationError(message)


def _csv_rows(content: bytes) -> list[dict]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""))
    _require(reader.fieldnames == list(COLUMNS), "edge CSV columns disagree with production columns")
    return list(reader)


def _row(value: dict) -> dict:
    return {column: str(value.get(column) if value.get(column) is not None else "") for column in COLUMNS}


def plan_review(root: Path, staged: Path, *, bundle_revision=1, bundle_supersedes=None):
    """Return staged outputs and pinned inputs; this function publishes nothing."""
    root = root.resolve()
    staged = contained(root, staged)
    review_bytes = staged.read_bytes()
    review = load_mapping(staged)
    problems = validate_content(review_bytes, artifact_schemas(root, "review", review.get("ruleset_id", "")))
    _require(not problems, "invalid staged Review: " + "; ".join(problems))
    _require(review.get("review_contract_version") == "1.3", "new Review must declare contract 1.3")
    scope = {key: review.get(key) for key in ("ruleset_id", "book_id", "source_id", "packet_id")}
    _require(all(scope.values()), "Review requires complete scope")
    base = contained(root, f"books/{scope['ruleset_id']}/{scope['book_id']}/artifacts")
    review_id = review.get("id", "")
    _require(review_id.startswith("REV-GUP-") and Path(review_id).name == review_id, "invalid Review ID")
    destination = base / "reviews" / f"{review_id}.yaml"
    outputs = [Output(destination, review_bytes, artifact_schemas(root, "review", scope["ruleset_id"]))]
    expected = {staged.relative_to(root).as_posix(): digest(review_bytes)}
    reviewed = review.get("reviewed_gup") or {}
    _require(isinstance(reviewed, dict) and all(reviewed.get(key) for key in ("id", "path", "checksum")), "Review must pin GUP ID, path and checksum")
    gup_path = contained(root, reviewed["path"])
    _require(digest(gup_path.read_bytes()) == reviewed["checksum"], "reviewed GUP checksum mismatch")
    expected[reviewed["path"]] = reviewed["checksum"]
    gup = load_mapping(gup_path)
    problems = validate_content(gup_path.read_bytes(), artifact_schemas(root, "gup", scope["ruleset_id"]))
    _require(not problems, "invalid input GUP: " + "; ".join(problems))
    _require(gup.get("id") == reviewed["id"], "reviewed GUP ID mismatch")
    _require(all(gup.get(key) == value for key, value in scope.items()), "Review/GUP scope mismatch")
    _require(review_id.startswith(f"REV-{gup['id']}-r"), "Review ID must name its exact GUP")
    directives = ReviewDirectives.load(staged)
    defects = (directives.unknown_dispositions + directives.unread_decision_keys
               + directives.unreadable_corrections + directives.malformed_policies)
    _require(not defects, "unread Review directives: " + "; ".join(defects))
    disposition = review.get("overall_disposition", review.get("status"))
    if disposition != "approved":
        _require(disposition in {"revision_required", "architect_escalation", "rejected"}, "unrecognized Review disposition")
        _require(review.get("handoff", {}).get("next_role") in {"builder", "architect"}, "correction Review must route to Builder or Architect")
        return outputs, expected, review

    _require(review.get("status") == "approved" and review.get("approval_ready") is True,
             "approved publication requires explicit approved status and approval_ready")
    _require(bool(review.get("independent_validation")), "approved Review must record independent validation")
    _require(review.get("handoff", {}).get("next_role") == "integrator"
             and review["handoff"].get("readiness") == "ready"
             and not review["handoff"].get("blocking_ids"), "approved Review needs an unblocked Integrator handoff")
    _require(gup.get("approval_ready") is True and gup.get("status") == "proposed", "GUP is not approval-ready")
    _require(gup.get("artifact_kind") == "packet_update", "direct migrations retain their existing explicit packaging workflow")
    changes = gup.get("edge_changes") or {}
    _require(not changes.get("removals"), "ordinary publisher cannot invent removal operations")
    rows = []
    index = {"additions": [], "pending_additions": [], "updates": []}
    observed_refs = set()

    def approved(ref, row):
        _require(isinstance(ref, str) and ref and ref not in observed_refs, f"missing/duplicate GUP ref: {ref}")
        observed_refs.add(ref)
        directive = directives.for_ref(ref)
        _require(directive is not None and directive.disposition == "approved", f"{ref}: an explicit approved ruling is required before packaging")
        _require(not directive.corrections and not directive.states_placement, f"{ref}: executable corrections belong in a Builder successor")
        return _row(row)

    for bucket, suffix in (("additions", ".edges.csv"), ("pending_additions", ".pending.csv")):
        declared = changes.get(bucket) or []
        actual_rows = [_row(row) for row in declared]
        component = gup_path.with_suffix(suffix)
        if component.exists() or actual_rows:
            _require(component.is_file(), f"missing GUP component: {component.name}")
            raw = component.read_bytes()
            _require(_csv_rows(raw) == actual_rows, f"{component.name}: CSV/GUP row disagreement")
            expected[component.relative_to(root).as_posix()] = digest(raw)
        for row in declared:
            ref = row.get("ref")
            rows.append(approved(ref, row))
            index[bucket].append({"ref": ref, "csv_row": len(rows)})

    updates = changes.get("updates") or []
    if updates:
        canonical_path = contained(root, f"rulesets/{scope['ruleset_id']}/canonical/edges_master.csv")
        canonical_bytes = canonical_path.read_bytes()
        canonical = _csv_rows(canonical_bytes)
        expected[canonical_path.relative_to(root).as_posix()] = digest(canonical_bytes)
        for update in updates:
            line = update.get("canonical_row")
            _require(isinstance(line, int) and 2 <= line <= len(canonical) + 1, "invalid canonical update locator")
            row = dict(canonical[line - 2])
            for field, change in (update.get("changes") or {}).items():
                _require(field in COLUMNS and row[field] == str(change["canonical"]), f"update baseline mismatch: {update.get('ref')} {field}")
                row[field] = str(change["patch"])
            rows.append(approved(update.get("ref"), row))
            index["updates"].append({key: copy.deepcopy(value) for key, value in update.items()
                                     if key in {"ref", "canonical_row", "changes", "differences_not_applied"}} | {"csv_row": len(rows)})

    blocked = changes.get("blocked_additions") or []
    blocked_refs = set()
    for row in blocked:
        ref = row.get("ref")
        _require(isinstance(ref, str) and ref and ref not in observed_refs and ref not in blocked_refs,
                 f"missing/duplicate blocked ref: {ref}")
        blocked_refs.add(ref)
        directive = directives.for_ref(ref)
        _require(directive is not None, f"blocked row lacks a disposition: {ref}")
    allowed_refs = observed_refs | {row.get("ref") for row in blocked}
    _require(set(directives.rows).issubset(allowed_refs), "Review contains a ref absent from this GUP")
    blocked_component = gup_path.with_suffix(".blocked.csv")
    if blocked or blocked_component.exists():
        _require(blocked_component.is_file(), "blocked component is missing")
        content = blocked_component.read_bytes()
        _require(_csv_rows(content) == [_row(row) for row in blocked], "blocked component/GUP disagreement")
        expected[blocked_component.relative_to(root).as_posix()] = digest(content)

    proposals = {entry["proposed_id"]: entry for entry in (gup.get("node_changes") or {}).get("additions_proposed") or []}
    _require(len(proposals) == len((gup.get("node_changes") or {}).get("additions_proposed") or []), "duplicate proposed node ID")
    decisions = review.get("node_registry_decisions") or []
    seen_nodes = set()
    approved_nodes = 0
    for decision in decisions:
        node = decision.get("proposed_id")
        _require(node in proposals and node not in seen_nodes, f"unknown/duplicate proposed node: {node}")
        seen_nodes.add(node)
        if decision.get("disposition") != "approved":
            continue
        proposal = proposals[node]
        _require(not proposal.get("architect_required"), f"node still requires an Architect ruling: {node}")
        _require(decision.get("submitted_label") == proposal.get("proposed_label")
                 and decision.get("kind") == proposal.get("kind"), f"registration fields disagree: {node}")
        _require(not decision.get("exact_corrections"), f"{node}: unapplied node correction")
        approved_nodes += 1
    _require(seen_nodes == set(proposals), "every proposed node needs an explicit Reviewer disposition")
    edge_validator = _schema_registry(root / "schemas" / scope["ruleset_id"] / "graph" / "edge.schema.json")
    for ordinal, row in enumerate(rows, 1):
        errors = list(edge_validator.iter_errors(row))
        _require(not errors, f"approved row {ordinal} is invalid: " + "; ".join(error.message for error in errors))

    _require(isinstance(bundle_revision, int) and 1 <= bundle_revision <= 99, "bundle revision must be 1..99")
    _require((bundle_revision == 1) == (bundle_supersedes is None), "successor bundle must explicitly name its predecessor")
    bundle_id = f"APPROVED-{gup['id']}-r{bundle_revision:02d}"
    if bundle_supersedes:
        prior_path = contained(root, base / "approved" / f"{bundle_supersedes}.yaml")
        prior = load_mapping(prior_path)
        _require(prior.get("packet_id") == scope["packet_id"] and prior.get("id") == bundle_supersedes,
                 "bundle predecessor scope mismatch")
        expected[prior_path.relative_to(root).as_posix()] = digest(prior_path.read_bytes())
    edge_path = base / "approved" / f"{bundle_id}.edges.csv"
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(COLUMNS), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    edge_bytes = buffer.getvalue().encode("utf-8")
    validation_path = contained(root, gup.get("validation_report") or f"build/reports/{gup['id']}.validation.json")
    validation_bytes = validation_path.read_bytes()
    validation = load_mapping(validation_path)
    _require(validation.get("gup_id") == gup["id"] and validation.get("packet_id") == scope["packet_id"],
             "validation report names another artifact")
    provenance = gup.get("provenance") or {}
    _require(validation.get("gur_id") == provenance.get("gur_id")
             and validation.get("gur_checksum") == provenance.get("gur_checksum"),
             "validation report/GUP provenance disagreement")
    _require(validation.get("status") == "proposed" and validation.get("approval_ready") is True
             and validation.get("summary", {}).get("errors") == 0,
             "validation report is not approval-ready")
    for key, count in (("edge_additions", len(index["additions"])), ("edge_pending_additions", len(index["pending_additions"])),
                       ("edge_updates", len(index["updates"])), ("edge_blocked_additions", len(blocked)),
                       ("node_additions_proposed", len(proposals))):
        _require(validation["summary"].get(key) == count, f"validation report count disagrees: {key}")
    test_result = validation.get("test_result") or {}
    _require(test_result.get("ran") is True and test_result.get("passed") is True
             and test_result.get("failures") == 0 and test_result.get("errors") == 0,
             "validation report has no passing Builder suite gate")
    expected[validation_path.relative_to(root).as_posix()] = digest(validation_bytes)
    manifest = {key: review[key] for key in ("schema_version", "ruleset_id", "book_id", "source_id", "packet_id", "constitution_version")}
    manifest.update({"id": bundle_id, "artifact_kind": "packet_update", "status": "approved",
                     "revision": bundle_revision, "supersedes": bundle_supersedes,
                     "approves": {"review_id": review_id, "review_checksum": digest(review_bytes),
                                  "gup_id": gup["id"], "gup_checksum": reviewed["checksum"],
                                  "gur_id": gup.get("provenance", {}).get("gur_id")},
                     "components": [{"kind": "edges", "path": edge_path.relative_to(root).as_posix(), "checksum": digest(edge_bytes), "rows": len(rows)},
                                    {"kind": "validation", "path": validation_path.relative_to(root).as_posix(), "checksum": digest(validation_bytes)}],
                     "operation_index": index, "node_operations": {"count": approved_nodes},
                     "packaging_evidence": {"inputs": expected, "excluded_blocked_refs": [row["ref"] for row in blocked]},
                     "handoff": dict(review["handoff"])})
    _require(manifest["approves"]["gur_id"], "packet GUP requires GUR provenance")
    read_operations(manifest, review, len(rows))
    outputs.extend([Output(edge_path, edge_bytes), Output(base / "approved" / f"{bundle_id}.yaml", yaml_bytes(manifest), artifact_schemas(root, "approved-bundle", scope["ruleset_id"]))])
    return outputs, expected, review
