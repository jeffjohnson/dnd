#!/usr/bin/env python3
"""One local interface for bounded preparation and owner-specific completion.

This command never supplies a source judgment, approves its own work, starts a
second packet, or waits for another agent. Existing artifacts remain authority.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import uuid

import yaml

CODE_ROOT = Path(__file__).resolve().parents[2]
for relative in ("tooling/common", "tooling/analyst", "tooling/reviewer", "tooling/builder/src", "tooling/integrator/src"):
    sys.path.insert(0, str(CODE_ROOT / relative))

from artifact_io import Output, PublicationError, artifact_schemas, contained, digest, json_bytes, load_mapping, publish, validate_outputs, verify_inputs
import role_context
import scan_agent_queues
from packet_inputs import packet_inputs, plan_claim
from publish_review import plan_review
from adnd1e_builder.registry import normalize_label
from adnd1e_builder.pagemarkers import PandocUnavailable

ROLES = ("analyst", "builder", "reviewer", "integrator", "architect")
NEXT = {"analyst": {"builder", "architect"}, "builder": {"reviewer", "analyst", "architect"},
        "reviewer": {"builder", "integrator", "architect"}, "integrator": {"reviewer", "analyst", "architect"},
        "architect": set(ROLES) - {"architect"}}


def require(condition, message):
    if not condition:
        raise PublicationError(message)


def merge_pins(expected, observed):
    for path, checksum in observed.items():
        require(path not in expected or expected[path] == checksum, f"input changed during preparation/completion: {path}")
    expected.update(observed)


def scoped(root: Path, ruleset: str, book: str | None):
    role_context.validate_scope("analyst", ruleset, book)
    manifest = load_mapping(contained(root, f"rulesets/{ruleset}/ruleset.yaml"))
    require(manifest.get("ruleset_id") == ruleset, "ruleset manifest mismatch")
    if book:
        book_manifest = load_mapping(contained(root, f"books/{ruleset}/{book}/book.yaml"))
        require(book_manifest.get("ruleset_id") == ruleset and book_manifest.get("book_id") == book,
                "book manifest mismatch")
        require(book_manifest.get("status") != "paused", f"{ruleset}/{book} is paused")
    return manifest


def read_input(root: Path, path: Path):
    path = contained(root, path)
    if path.is_dir():
        path /= "packet.yaml"
    require(path.is_file(), f"input does not exist: {path}")
    return path, load_mapping(path) if path.suffix.lower() in {".yaml", ".yml", ".json"} else {}


def context(root: Path, args):
    result = role_context.verify(root, args.role, args.ruleset, args.book, args.session_id)
    receipt = role_context.build_receipt(root, args.role, args.ruleset, args.book, args.session_id)
    token = digest(json.dumps(receipt, sort_keys=True).encode("utf-8"))
    if args.context_read:
        require(args.context_read == token, "context attestation does not match the current role/session/scope/checksums")
        role_context.record(root, args.role, args.ruleset, args.book, args.session_id)
        result["status"] = "cache_hit"
    if result["status"] != "cache_hit":
        return {"outcome": "context_read_required", "context_token": token,
                "reason": "Read every emitted document, then explicitly pass --context-read with this token.",
                "documents": [document_record(root, contained(root, name)) for name in result["stable_authority_paths"]]}
    return None


def document_record(root: Path, path: Path):
    raw = path.read_bytes()
    return {"path": path.relative_to(root).as_posix(), "checksum": digest(raw),
            "content": raw.decode("utf-8-sig")}


def queue(root: Path, role: str, ruleset: str, book: str | None):
    result = scan_agent_queues.scan_repository(root)
    def include(item):
        return (item.get("Role", "").lower() == role and item.get("Ruleset") == ruleset
                and (not book or item.get("Book") in (None, book))
                and (item.get("Ruleset"), item.get("Book")) != ("basicdnd", "rc"))
    projection = {key: [item for item in result[key] if include(item)]
                  for key in ("Items", "ActiveItems", "BlockedItems")}
    projection["Diagnostics"] = [item for item in result["Diagnostics"] if item["Severity"] == "error"]
    projection["GlobalLineageErrorCount"] = result["LineageErrorCount"]
    projection["InformationalDiagnosticCount"] = len(result["Diagnostics"]) - len(projection["Diagnostics"])
    return result, projection


def require_assignment(root, args, path, document, full_queue):
    escalation_ruling = args.role == "architect" and document.get("id", "").startswith("ESC-")
    require(escalation_ruling or not full_queue["LineageErrorCount"], "repository lineage errors prevent a trustworthy assignment")
    identifiers = {document.get("id"), document.get("packet_id") if path.name == "packet.yaml" else None}
    for named in args.review or []:
        identifiers.add(load_mapping(contained(root, named)).get("id"))
    relative = path.relative_to(root).as_posix()
    candidates = []
    pool = full_queue["Items"] + full_queue["ActiveItems"]
    if args.role == "analyst":
        pool += [item for item in full_queue.get("BlockedItems", []) if item.get("Queue") == "ANALYST-BLOCKED-GUP"]
    for item in pool:
        if item.get("Role", "").lower() != args.role or item.get("Ruleset") != args.ruleset:
            continue
        if item.get("Book") not in (None, args.book):
            continue
        if (item.get("InputId") in identifiers - {None}
                or item.get("PacketId") in identifiers - {None}
                or item.get("Path") == relative
                or (path.name == "packet.yaml" and item.get("Path") == path.parent.relative_to(root).as_posix())):
            candidates.append(item)
    require(candidates, "input is not a current ready/active assignment for this role; use prepare --inspect only for an audit")
    handoff = document.get("handoff") or {}
    require(handoff.get("readiness") not in {"blocked", "terminal"}, "blocked/terminal input cannot advance")
    packet = document.get("packet_id")
    if packet:
        for item in full_queue["Items"]:
            if item.get("Role") == "Architect" and item.get("Queue") == "ARCHITECT-ESC" and item.get("PacketId") == packet:
                require(args.role == "architect", f"packet paused by {item['InputId']}")
    return candidates


def resolve_id(root: Path, ruleset: str, book: str | None, identifier: str):
    book_stores = {"GUR-": "gur", "GUP-": "gup", "REV-GUP-": "reviews", "APPROVED-": "approved"}
    for prefix, store in book_stores.items():
        if identifier.startswith(prefix) and book:
            return contained(root, f"books/{ruleset}/{book}/artifacts/{store}/{identifier}.yaml")
    for prefix, store in (("REV-IMP-", "decision-implementation-reviews"), ("IMP-", "decision-implementations"), ("DEC-", "escalations/decisions")):
        if identifier.startswith(prefix):
            return contained(root, f"rulesets/{ruleset}/{store}/{identifier}.yaml")
    if identifier.startswith("ESC-"):
        matches = [contained(root, f"rulesets/{ruleset}/escalations/{state}/{identifier}.yaml")
                   for state in ("pending", "decided", "returned")]
        matches = [path for path in matches if path.exists()]
        require(len(matches) == 1, f"escalation identity is missing or ambiguous: {identifier}")
        return matches[0]
    return None


def collect_inputs(root: Path, path: Path, ruleset: str, book: str | None):
    pending = [path]
    documents = {}
    endpoint_ids = set()
    labels = set()
    def visit(value):
        if isinstance(value, dict):
            ref = value.get("path")
            checksum = value.get("checksum")
            if isinstance(ref, str) and checksum:
                target = contained(root, ref)
                require(target.is_file() and digest(target.read_bytes()) == checksum, f"provenance checksum mismatch: {ref}")
                pending.append(target)
            for key, child in value.items():
                if key in {"source_id", "target_id", "proposed_id"} and isinstance(child, str):
                    endpoint_ids.add(child)
                if key in {"source_label", "target_label", "proposed_label", "submitted_label"} and isinstance(child, str):
                    labels.add(normalize_label(child))
                if key in {"gur_id", "review_id", "gup_id", "supersedes", "escalation_id"} and isinstance(child, str):
                    target = resolve_id(root, ruleset, book, child)
                    if target is not None:
                        require(target.is_file(), f"missing named input: {child}")
                        pending.append(target)
                if key == "validation_report" and isinstance(child, str):
                    pending.append(contained(root, child))
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    while pending:
        current = contained(root, pending.pop())
        key = current.relative_to(root).as_posix()
        if key in documents:
            continue
        require(current.is_file(), f"named input missing: {key}")
        require(len(documents) < 100, "dependency set exceeds 100 documents; split the explicit audit scope, do not silently truncate")
        documents[key] = document_record(root, current)
        if current.suffix in {".yaml", ".yml", ".json"}:
            visit(yaml.safe_load(documents[key]["content"]))
    result = {"documents": list(documents.values()), "input_checksums": {key: value["checksum"] for key, value in documents.items()}}
    for label, relative in (("registry_slice", f"rulesets/{ruleset}/registries/nodes.csv"),
                            ("neighborhood", f"rulesets/{ruleset}/canonical/edges_master.csv")):
        source = contained(root, relative)
        if source.is_file():
            raw = source.read_bytes()
            rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
            result[label] = [row for row in rows if row.get("id") in endpoint_ids
                             or (label == "registry_slice" and normalize_label(row.get("label", "")) in labels)
                             or row.get("source_id") in endpoint_ids or row.get("target_id") in endpoint_ids]
            if label == "registry_slice":
                endpoint_ids.update(row["id"] for row in result[label])
            result["input_checksums"][relative] = digest(raw)
    return result


def include_reviews(root, args, source, result):
    if not args.review:
        return
    require(args.role == "builder", "--review correction inputs belong to Builder")
    documents = {item["path"]: item for item in result["documents"]}
    for named in args.review:
        path = contained(root, named)
        review = load_mapping(path)
        require(review.get("id", "").startswith("REV-GUP-") and all(
            review.get(key) == source.get(key) for key in ("ruleset_id", "book_id", "packet_id")),
            "correction Review scope disagrees with its GUR")
        related = collect_inputs(root, path, args.ruleset, args.book)
        documents.update((item["path"], item) for item in related["documents"])
        merge_pins(result["input_checksums"], related["input_checksums"])
        for label in ("registry_slice", "neighborhood"):
            rows = result.get(label, []) + related.get(label, [])
            result[label] = list({json.dumps(row, sort_keys=True): row for row in rows}.values())
    result["documents"] = list(documents.values())


def prepare(root: Path, args):
    path, document = read_input(root, args.input)
    for key, expected in (("ruleset_id", args.ruleset), ("book_id", args.book)):
        require(key not in document or document[key] == expected, f"input {key} disagrees with requested scope")
    full_queue, projection = queue(root, args.role, args.ruleset, args.book)
    if not args.inspect:
        require_assignment(root, args, path, document, full_queue)
    if args.claim_manifest:
        require(args.role == "analyst" and not args.inspect, "only an assigned Analyst can claim")
        integrated_packets = set()
        manifest_dir = root / "rulesets" / args.ruleset / "manifests"
        if manifest_dir.is_dir():
            for mf in manifest_dir.glob("INT-*.json"):
                try:
                    mdata = json.loads(mf.read_text(encoding="utf-8"))
                    for b in mdata.get("approved_bundles", []):
                        if b.get("packet_id"):
                            integrated_packets.add(b["packet_id"])
                except Exception:
                    pass
        active = {item["PacketId"] for item in full_queue["ActiveItems"] + full_queue["BlockedItems"] + full_queue["Items"]
                  if item.get("PacketId") and item.get("Queue") != "ANALYST-INCOMING"
                  and (item.get("Ruleset"), item.get("Book")) != ("basicdnd", "rc")
                  and item.get("PacketId") not in integrated_packets}
        outputs, expected = plan_claim(root, path, contained(root, args.claim_manifest), active)
        publish(root, outputs, expected_inputs=expected)
        path, document = read_input(root, outputs[0].path)
    result = {"outcome": "inspection_only" if args.inspect else "prepared", "role": args.role, "queue": projection}
    result.update(collect_inputs(root, path, args.ruleset, args.book))
    include_reviews(root, args, document, result)
    packet = document.get("packet_id")
    packet_path = root / "books" / args.ruleset / (args.book or "") / "packets/claimed" / str(packet) / "packet.yaml"
    if path.suffix == ".md" or path.name == "packet.yaml":
        result["packet"] = packet_inputs(root, path)
    elif packet_path.is_file() and args.role in {"analyst", "reviewer", "builder"}:
        result["packet"] = packet_inputs(root, packet_path)
        result["documents"].append(document_record(root, packet_path))
    if "packet" in result:
        packet_data = result["packet"]
        result["documents"] = [item for item in result["documents"] if item["path"] != packet_data["source_path"]]
        result["input_checksums"][packet_data["source_path"]] = packet_data["checksum"]
        for supplied in packet_data["supplied_inputs"]:
            result["input_checksums"][supplied["path"]] = supplied["checksum"]
        if packet_path.is_file():
            result["input_checksums"][packet_path.relative_to(root).as_posix()] = digest(packet_path.read_bytes())
    if args.role == "integrator":
        from adnd1e_integrator.bundles import ready_queue
        local = ready_queue(root, args.ruleset, [args.book] if args.book else [])
        result["integrator_admission"] = {"ready_ids": [bundle.bundle_id for bundle in local["ready"]],
                                           "queue_integrity": local["queue_integrity"], "diagnostics": local["diagnostics"]}
    if not args.inspect:
        snapshot = {"role": args.role, "ruleset": args.ruleset, "book": args.book,
                    "session_id": args.session_id, "input": path.relative_to(root).as_posix(),
                    "input_checksums": result["input_checksums"]}
        target = root / ".local/agent-task/prepared" / f"{uuid.uuid4().hex}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as stream:
            json.dump(snapshot, stream, indent=2)
        result["preparation_file"] = target.relative_to(root).as_posix()
    return result


def validate_lineage(root, destination, document):
    identifier = document.get("id")
    require(identifier == destination.stem, "destination/ID mismatch")
    revision = document.get("revision")
    require(isinstance(revision, int) and not isinstance(revision, bool) and revision > 0, "new output requires an explicit revision")
    if identifier.startswith("REV-GUP-"):
        validate_review_lineage(root, destination, document)
        return
    predecessor = document.get("supersedes")
    family = re.sub(r"-r[0-9]+$", "", identifier)
    relatives = list(destination.parent.glob(f"{family}-r*.yaml"))
    if revision == 1:
        require(predecessor is None, "first revision must not supersede another artifact")
        require(not relatives, "lineage already exists; first revision would fork it")
        return
    require(isinstance(predecessor, str) and predecessor, "successor requires an explicit predecessor")
    prior_path = contained(root, destination.parent / f"{predecessor}.yaml")
    prior = load_mapping(prior_path)
    require(prior.get("id") == predecessor and all(prior.get(key) == document.get(key)
            for key in ("ruleset_id", "book_id", "packet_id")), "predecessor identity/scope mismatch")
    require(isinstance(prior.get("revision"), int) and prior["revision"] < revision, "revision must advance its predecessor")
    require(re.sub(r"-r[0-9]+$", "", predecessor) == family,
            "cross-family supersession requires explicit governance; use the existing specialized workflow")
    for other in relatives:
        value = load_mapping(other)
        require(value.get("supersedes") != predecessor, f"predecessor already has successor: {other.name}")


def validate_review_lineage(root, destination, document):
    """Reuse the scanner's bounded cross-GUP lineage rule, not a second policy."""
    ruleset, book, packet = (document.get(key) for key in ("ruleset_id", "book_id", "packet_id"))
    require(all((ruleset, book, packet)), "Review lineage requires full packet scope")
    base = root / f"books/{ruleset}/{book}/artifacts"
    gups = {}
    diagnostics = []
    for path in (base / "gup").glob(f"GUP-{packet}-r*.yaml"):
        data = load_mapping(path)
        require(all(data.get(key) == document.get(key) for key in ("ruleset_id", "book_id", "packet_id")), "GUP lineage scope mismatch")
        artifact = scan_agent_queues.Artifact(path, "gup", ruleset, book, data)
        gups[artifact.artifact_id] = artifact
    scan_agent_queues._active_leaf(root, list(gups.values()), diagnostics, "publication GUP")
    reviews = {}
    values = [(path, load_mapping(path)) for path in destination.parent.glob(f"REV-GUP-{packet}-r*-r*.yaml")]
    values.append((destination, document))
    for path, data in values:
        require(all(data.get(key) == document.get(key) for key in ("ruleset_id", "book_id", "packet_id")), "Review lineage scope mismatch")
        reviewed = data.get("reviewed_gup")
        gup_id = reviewed.get("id") if isinstance(reviewed, dict) else reviewed
        require(gup_id in gups, "Review must name an existing GUP in this packet")
        reviews.setdefault(gup_id, []).append(scan_agent_queues.Artifact(path, "review", ruleset, book, data))
    leaves = scan_agent_queues._packet_review_leaves(root, gups, reviews, diagnostics)
    require(not [item for item in diagnostics if item["Severity"] == "error"], "invalid Review lineage: " + json.dumps(diagnostics))
    target = document["reviewed_gup"]["id"]
    leaf = leaves.get(target, (None, False))[0]
    require(leaf is not None and leaf.artifact_id == document["id"], "new Review must be the exact active leaf")


def authored_plan(root, args, staged, source):
    document = load_mapping(staged)
    require(document.get("ruleset_id") == args.ruleset, "output ruleset mismatch")
    if document.get("book_id"):
        require(document["book_id"] == args.book, "output book mismatch")
    identifier = document.get("id", "")
    require(Path(identifier).name == identifier and identifier, "invalid output ID")
    if identifier.startswith("ESC-"):
        kind, store = "artifact-envelope", f"rulesets/{args.ruleset}/escalations/pending"
        require(re.fullmatch(r"ESC-\d{4}-\d{2}-\d{2}T\d{2}\.\d{2}\.\d{2}\.\d{3}Z", identifier), "ESC requires a UTC timestamp ID")
        require(resolve_id_if_present(root, args.ruleset, identifier) is None, "ESC ID already exists")
        require(document.get("raised_by") == args.role, "ESC must name its actual originating role")
        for field in ("originating_artifacts", "question", "smallest_relevant_source_excerpt", "local_graph_neighborhood",
                      "affected_canonical_ids", "options_considered", "recommended_resolution", "expected_migration_impact"):
            require(field in document, f"ESC requires {field}; schema validation alone is not a complete package")
    elif identifier.startswith("GUR-") and args.role == "analyst":
        kind, store = "gur", f"books/{args.ruleset}/{args.book}/artifacts/gur"
        require(document.get("packet_id") == source.get("packet_id"), "GUR must retain the assigned packet")
    elif identifier.startswith("DEC-") and args.role == "architect":
        kind, store = "architect-decision", f"rulesets/{args.ruleset}/escalations/decisions"
        require(document.get("escalation_id") == source.get("id"), "Decision must name its assigned escalation")
    elif identifier.startswith("IMP-") and args.role in {"builder", "integrator"}:
        kind, store = "decision-implementation", f"rulesets/{args.ruleset}/decision-implementations"
        require(document.get("implemented_by") == args.role, "implementation owner mismatch")
        require(document.get("decision_input", {}).get("id") == source.get("id"), "implementation must name its assigned Decision")
    elif identifier.startswith("REV-IMP-") and args.role == "reviewer":
        kind, store = "decision-implementation-review", f"rulesets/{args.ruleset}/decision-implementation-reviews"
        require(document.get("reviewed_implementation", {}).get("id") == source.get("id"), "Review must name its assigned implementation")
    elif identifier.startswith("INT-") and args.role == "integrator" and document.get("status") == "rejected":
        kind, store = "integration-rejection", f"rulesets/{args.ruleset}/reports"
        rejections = document.get("rejected_bundles") or []
        require(len(rejections) == 1 and rejections[0].get("bundle_id") == source.get("id"),
                "rejection must name only the assigned bundle")
    else:
        raise PublicationError("this role cannot publish that artifact kind")
    path = contained(root, f"{store}/{identifier}.yaml")
    if kind == "integration-rejection":
        path = contained(root, f"{store}/{identifier}.rejected.json")
        require(document.get("revision") == 1 and document.get("supersedes") is None, "rejection records are standalone revision 1")
        return [Output(path, json_bytes(document), artifact_schemas(root, kind, args.ruleset))], document
    if not identifier.startswith("ESC-"):
        validate_lineage(root, path, document)
    return [Output(path, staged.read_bytes(), artifact_schemas(root, kind, args.ruleset))], document


def resolve_id_if_present(root, ruleset, identifier):
    for state in ("pending", "decided", "returned"):
        path = contained(root, f"rulesets/{ruleset}/escalations/{state}/{identifier}.yaml")
        if path.exists():
            return path
    return None


def prepared_inputs(root, args, path):
    require(args.prepared, "finish requires --prepared from a successful prepare in this actor session")
    snapshot = load_mapping(contained(root, args.prepared))
    for key, expected in (("role", args.role), ("ruleset", args.ruleset), ("book", args.book),
                          ("session_id", args.session_id), ("input", path.relative_to(root).as_posix())):
        require(snapshot.get(key) == expected, f"preparation {key} mismatch")
    pins = snapshot.get("input_checksums")
    require(isinstance(pins, dict) and path.relative_to(root).as_posix() in pins, "preparation lacks exact input checksums")
    verify_inputs(root, pins)
    return pins


def run_role_command(root, role, arguments, expected_inputs=None):
    if role == "builder":
        from adnd1e_builder.cli import main
    else:
        from adnd1e_integrator.cli import main
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
        code = main(arguments, expected_inputs=expected_inputs) if role == "builder" else main(arguments)
    log = root / ".local/agent-task/logs" / f"{role}-{uuid.uuid4().hex}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(capture.getvalue(), encoding="utf-8")
    return code, capture.getvalue(), log.relative_to(root).as_posix()


def notify(root, role, next_role, message):
    if next_role == "none":
        return {"status": "not_applicable"}
    require(next_role in NEXT[role], "notification route is not permitted for this role")
    command = ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(root / "tooling/common/Send-HerdrPrompt.ps1"),
               "-Role", next_role.title(), "-Message", message, "-Repository", str(root)]
    try:
        process = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
        return {"status": "submitted" if process.returncode == 0 else "failed", "exit_code": process.returncode,
                "detail": (process.stdout + process.stderr).strip()}
    except subprocess.TimeoutExpired:
        return {"status": "unknown", "detail": "notification timed out; do not automatically resend or republish"}
    except OSError as exc:
        return {"status": "failed", "detail": str(exc)}


def finish(root, args):
    require(not args.inspect and not args.claim_manifest, "finish does not accept inspection or claim modes")
    path, source = read_input(root, args.input)
    prepared = prepared_inputs(root, args, path)
    require(source.get("ruleset_id") == args.ruleset, "input ruleset mismatch")
    require(source.get("book_id") in (None, args.book), "input book mismatch")
    full_queue, _ = queue(root, args.role, args.ruleset, args.book)
    require_assignment(root, args, path, source, full_queue)
    evidence = collect_inputs(root, path, args.ruleset, args.book)
    include_reviews(root, args, source, evidence)
    require(set(evidence["input_checksums"]).issubset(prepared),
            "input dependencies changed since preparation; prepare again with every correction Review")
    expected = dict(prepared)
    merge_pins(expected, evidence["input_checksums"])
    if args.staged:
        staged = contained(root, args.staged)
        staged_checksum = digest(staged.read_bytes())
        document = load_mapping(staged)
        if args.role == "reviewer" and document.get("id", "").startswith("REV-GUP-"):
            outputs, pinned, document = plan_review(root, staged, bundle_revision=args.bundle_revision, bundle_supersedes=args.bundle_supersedes)
            require(document.get("reviewed_gup", {}).get("id") == source.get("id"), "Review must consume the assigned GUP")
            merge_pins(expected, pinned)
            for output in outputs:
                if output.path.suffix == ".yaml":
                    validate_lineage(root, output.path, yaml.safe_load(output.content))
        else:
            outputs, document = authored_plan(root, args, staged, source)
            # Authored provenance is checked mechanically, not accepted as prose.
            staged_evidence = collect_inputs(root, staged, args.ruleset, args.book)
            merge_pins(expected, staged_evidence["input_checksums"])
        next_role = "architect" if document["id"].startswith("ESC-") else document.get("handoff", {}).get("next_role")
        require(next_role == "none" or next_role in NEXT[args.role], "output declares an illegal next-role route")
        merge_pins(expected, {staged.relative_to(root).as_posix(): staged_checksum})
        problems = validate_outputs(root, outputs)
        require(not problems, "staged validation failed: " + "; ".join(problems))
        lifecycle_target = None
        if args.role == "architect" and document["id"].startswith("DEC-"):
            require(next_role == source.get("raised_by"), "Decision must return control to the escalation originator")
            require(path.parent == root / f"rulesets/{args.ruleset}/escalations/pending", "Architect input must be in pending")
            target_state = "returned" if document.get("status") == "returned" else "decided"
            lifecycle_target = contained(root, path.parent.parent / target_state / path.name)
            require(not lifecycle_target.exists(), "escalation lifecycle destination already exists")
        result = {"outcome": "validated_preview" if args.preview else "published", "next_role": next_role,
                  "artifacts": [{"path": output.path.relative_to(root).as_posix(), "checksum": digest(output.content)} for output in outputs]}
        if not args.preview:
            result["artifacts"] = publish(root, outputs, expected_inputs=expected)
            if lifecycle_target is not None:
                lifecycle_target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    path.rename(lifecycle_target)
                except OSError as exc:
                    return dict(result, outcome="published_lifecycle_incomplete", next_role="none",
                                error=str(exc), notification={"status": "not_sent"})
        else:
            result["notification"] = {"status": "disabled_in_preview"}
            return result
    elif args.role == "builder":
        require(source.get("id", "").startswith("GUR-"), "compile input must be the exact assigned GUR; pass --review for a correction")
        require(not args.preview, "Builder preview is prepare; finish retains the full suite and publishes create-only")
        from adnd1e_builder.cli import next_revision
        revision = args.revision or next_revision(root / f"books/{args.ruleset}/{args.book}/artifacts/gup", source["packet_id"])
        arguments = ["compile", str(path), "--repo-root", str(root), "--ruleset", args.ruleset, "--revision", str(revision)]
        if args.supersedes:
            arguments += ["--supersedes", args.supersedes]
        for review in args.review or []:
            arguments += ["--review", str(contained(root, review))]
        code, text, log = run_role_command(root, args.role, arguments, expected_inputs=expected)
        if code not in (0, 1):
            return {"outcome": "failed", "phase": "compile", "exit_code": code, "log": log, "detail": text, "next_role": "none"}
        identifier = f"GUP-{source['packet_id']}-r{revision:02d}"
        output = contained(root, f"books/{args.ruleset}/{args.book}/artifacts/gup/{identifier}.yaml")
        require(output.is_file(), "compiler did not produce its declared output")
        built = load_mapping(output)
        next_role = built["handoff"]["next_role"]
        result = {"outcome": "blocked" if code == 1 else "published", "next_role": next_role,
                  "artifacts": [{"path": output.relative_to(root).as_posix(), "checksum": digest(output.read_bytes())}], "log": log, "detail": text}
    elif args.role == "integrator":
        require(source.get("id", "").startswith("APPROVED-"), "integration requires an exact Approved bundle")
        arguments = ["--repo-root", str(root), "--ruleset-id", args.ruleset, f"--books={args.book}", "integrate", source["id"]]
        if args.preview:
            arguments.append("--dry-run")
        code, text, log = run_role_command(root, args.role, arguments)
        if code:
            return {"outcome": "rejected", "phase": "integration", "exit_code": code, "log": log, "detail": text,
                    "next_role": "reviewer", "notification": {"status": "not_sent_without_a_published_rejection"}}
        details = json.loads(text)
        if args.preview:
            return {"outcome": "validated_preview", "detail": details, "next_role": "none"}
        require(details.get("records", {}).get("manifest"), "integration has no terminal manifest")
        for record in details["records"].values():
            require(contained(root, record).is_file(), f"missing terminal record: {record}")
        next_role = "analyst"
        result = {"outcome": "integrated", "next_role": next_role, "integration": details, "log": log}
    else:
        raise PublicationError("this role requires an authored --staged artifact")
    if args.notify:
        if next_role == "architect" and not args.staged:
            result["notification"] = {"status": "not_sent_without_a_published_escalation"}
            return result
        result["notification"] = notify(root, args.role, next_role,
            f"Completed {result['outcome']}: {json.dumps(result.get('artifacts') or result.get('integration'))}. "
            + ("Select the next eligible packet. " if result["outcome"] == "integrated" else "Recheck exact inputs and prerequisites. ")
            + "NO RC. Notification only; no reply or relay.")
    else:
        result["notification"] = {"status": "not_requested"}
    return result


def test_suites(root, names):
    results = []
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(str(root / "tooling" / role / "src") for role in ("builder", "integrator"))
    environment["PYTHONUTF8"] = "1"
    for key in tuple(environment):
        if key.startswith("HERDR_"):
            environment.pop(key)
    for name in names:
        directory = contained(root, f"tooling/{name}/tests")
        command = [sys.executable, "-m", "unittest", "discover", "-s", str(directory), "-t", str(directory), "-p", "test_*.py"]
        log = root / ".local/agent-task/logs" / f"tests-{name}-{uuid.uuid4().hex}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        try:
            with log.open("w", encoding="utf-8") as output:
                process = subprocess.run(command, cwd=root, stdout=output, stderr=subprocess.STDOUT, env=environment, timeout=5400)
            code = process.returncode
        except subprocess.TimeoutExpired:
            code = 124
        results.append({"suite": name, "exit_code": code, "seconds": round(time.monotonic() - started, 3),
                        "log": log.relative_to(root).as_posix(), "summary": "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-12:])})
    return {"outcome": "failed" if any(item["exit_code"] for item in results) else "passed", "suites": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "finish", "test"))
    parser.add_argument("--root", type=Path, default=CODE_ROOT)
    parser.add_argument("--role", choices=ROLES)
    parser.add_argument("--ruleset")
    parser.add_argument("--book")
    parser.add_argument("--session-id")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--staged", type=Path)
    parser.add_argument("--context-read")
    parser.add_argument("--prepared", type=Path, help="same-session preparation snapshot returned by prepare")
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--notify", action="store_true")
    parser.add_argument("--claim-manifest", type=Path)
    parser.add_argument("--review", type=Path, action="append")
    parser.add_argument("--revision", type=int)
    parser.add_argument("--supersedes")
    parser.add_argument("--bundle-revision", type=int, default=1)
    parser.add_argument("--bundle-supersedes")
    parser.add_argument("--suites", nargs="+", choices=("builder", "common", "integrator", "reviewer"), default=["builder", "common", "integrator", "reviewer"])
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "test":
            result = test_suites(root, args.suites)
        else:
            require(args.role and args.ruleset and args.session_id and args.input, "role, ruleset, session-id and exact input are required")
            scoped(root, args.ruleset, args.book)
            result = context(root, args)
            if result is None:
                result = prepare(root, args) if args.command == "prepare" else finish(root, args)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["outcome"] in {"prepared", "inspection_only", "validated_preview", "published", "integrated", "passed"} else 1
    except (PublicationError, role_context.ContextError, PandocUnavailable, OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
        print(json.dumps({"outcome": "failed", "error": str(exc), "next_role": "none"}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
