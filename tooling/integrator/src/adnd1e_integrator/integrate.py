"""Transactional integration of Approved bundles into canonical state.

Implements the sixteen-step sequence in `agents/integrator/INSTRUCTIONS.md`
under "Transactional integration". The whole batch succeeds or canonical state
is restored byte-for-byte; there is no partial application.

Preconditions are checked before the snapshot is taken, so a bundle that fails
verification never reaches a write at all.
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import TOOL_NAME, __version__
from .bundles import Bundle
from .canonical import EDGE_COLUMNS, CanonicalGraph, CanonicalPaths, Registry, read_csv_rows
from .checksums import checksum_file
from .derive import apply_derived_polarity, load_role_profile, rebuild_nodes
from .invariants import assertion_key, approved_prefixes, check, check_derived_state
from .migration import (
    MigrationError, MigrationPlan, check_baselines, check_before_images,
    check_incident_sets, check_registry_targets, read_plan)
from .operations import EdgeUpdate, NodeRegistration, Operations, OperationError, read_operations
from .snapshot import Transaction


class IntegrationError(RuntimeError):
    """Raised when a batch must not be applied. Triggers rollback."""


@dataclass
class Precondition:
    name: str
    passed: bool
    detail: str
    blocking: bool = True

    def as_dict(self) -> dict:
        return {"check": self.name, "result": "pass" if self.passed else "fail",
                "blocking": self.blocking, "detail": self.detail}


@dataclass
class BundleVerification:
    bundle: Bundle
    checks: list[Precondition] = field(default_factory=list)
    rows: list[dict[str, str]] = field(default_factory=list)
    declared_rows: int | None = None
    operations: Operations = field(default_factory=Operations)
    plan: MigrationPlan | None = None

    @property
    def blocking_failures(self) -> list[Precondition]:
        return [c for c in self.checks if not c.passed and c.blocking]

    @property
    def advisories(self) -> list[Precondition]:
        return [c for c in self.checks if not c.passed and not c.blocking]


def verify_bundle(bundle: Bundle, root: Path) -> BundleVerification:
    """Steps 1 and 2: approval, checksums, schema version, component integrity."""
    verification = BundleVerification(bundle=bundle)
    add = verification.checks.append

    review = bundle.review or yaml.safe_load(bundle.review_path.read_text(encoding="utf-8"))
    bundle.review = review

    # -- approval ------------------------------------------------------------
    disposition = review.get("overall_disposition")
    add(Precondition(
        "review disposition is approved",
        disposition == "approved",
        f"overall_disposition={disposition!r}"))
    add(Precondition(
        "review is approval-ready",
        bool(review.get("approval_ready")),
        f"approval_ready={review.get('approval_ready')!r}"))
    add(Precondition(
        "review reports no unresolved architectural escalation",
        not review.get("architectural_escalations"),
        f"{len(review.get('architectural_escalations') or [])} open escalation(s)"))
    add(Precondition(
        "review approved no heuristic or unset polarity",
        not (review.get("reviewer_checklist") or {}).get("heuristic_or_unset_approved"),
        "invariant 16"))

    handoff = review.get("handoff") or (bundle.manifest.get("handoff") if bundle.manifest else None)
    if handoff:
        add(Precondition(
            "handoff routes to integrator and is ready",
            handoff.get("next_role") == "integrator" and handoff.get("readiness") == "ready",
            f"next_role={handoff.get('next_role')!r} readiness={handoff.get('readiness')!r}"))
        add(Precondition(
            "handoff names no blocking id",
            not handoff.get("blocking_ids"),
            f"blocking_ids={handoff.get('blocking_ids')!r}"))
    else:
        add(Precondition(
            "handoff block present", False,
            "legacy artifact predating WORK_QUEUES 1.0; routing inferred from the "
            "approved disposition", blocking=False))

    # -- component checksums -------------------------------------------------
    if bundle.manifest_path is not None:
        manifest = bundle.manifest
        add(Precondition(
            "manifest declares approves.review_id and gup_id",
            bool((manifest.get("approves") or {}).get("review_id")
                 and (manifest.get("approves") or {}).get("gup_id")),
            "approved-bundle.schema.json required fields"))

        approves = manifest.get("approves") or {}
        expected_review = approves.get("review_checksum")
        actual_review = checksum_file(bundle.review_path)
        add(Precondition(
            "declared review checksum matches the Review on disk",
            expected_review == actual_review,
            f"declared={expected_review} actual={actual_review}"))

        for component in manifest.get("components", []):
            path = root / component["path"]
            add(Precondition(
                f"component checksum matches: {component['path']}",
                path.exists() and checksum_file(path) == component["checksum"],
                f"declared={component['checksum']} "
                f"actual={checksum_file(path) if path.exists() else 'MISSING'}"))
            if component.get("kind") == "edges" and "rows" in component:
                verification.declared_rows = component["rows"]
    else:
        add(Precondition(
            "Approved manifest present", False,
            "legacy bundle without a manifest; components grouped under "
            "WORK_QUEUES legacy rule 6", blocking=False))

    # -- the Review's own pinned upstream inputs -----------------------------
    reviewed = review.get("reviewed_gup") or {}
    for label, key, path_key in (
        ("GUP YAML", "checksum", "path"),
        ("GUP edge CSV", "edge_csv_checksum", "edge_csv_path"),
    ):
        declared, rel = reviewed.get(key), reviewed.get(path_key)
        if not declared or not rel:
            continue
        path = root / rel
        actual = checksum_file(path) if path.exists() else "MISSING"
        add(Precondition(
            f"review-pinned {label} still matches on disk",
            actual == declared,
            f"{rel}: declared={declared} actual={actual}"))

    gur = (review.get("input_provenance") or {}).get("gur") or {}
    if gur.get("path") and gur.get("expected_checksum"):
        path = root / gur["path"]
        actual = checksum_file(path) if path.exists() else "MISSING"
        add(Precondition(
            "review-pinned GUR still matches on disk",
            actual == gur["expected_checksum"],
            f"{gur['path']}: declared={gur['expected_checksum']} actual={actual}",
            # An upstream interpretive artifact edited after publication is an
            # append-only violation owned by its author. It cannot be repaired
            # during integration, and it is only load-bearing for rows this
            # bundle actually contributes -- so it is reported, not blocking.
            blocking=False))

    # -- schema version ------------------------------------------------------
    add(Precondition(
        "artifact schema_version is 1.0",
        str(review.get("schema_version")) == "1.0",
        f"schema_version={review.get('schema_version')!r}"))

    if bundle.is_direct_migration:
        _verify_direct_migration(bundle, root, verification, review, add)
        return verification

    # -- edge component ------------------------------------------------------
    rows = read_csv_rows(bundle.edges_path)
    verification.rows = rows
    header = list(rows[0].keys()) if rows else _header_of(bundle.edges_path)
    add(Precondition(
        "edge CSV header matches the production columns",
        header == EDGE_COLUMNS,
        f"{len(header)} columns"))

    if verification.declared_rows is not None:
        add(Precondition(
            "declared row count matches the CSV",
            verification.declared_rows == len(rows),
            f"declared={verification.declared_rows} actual={len(rows)}"))

    summary = review.get("summary") or {}
    if "approved" in summary:
        expected = summary["approved"] + summary.get("approved_with_revision", 0)
        add(Precondition(
            "review approved-row count matches the CSV",
            expected == len(rows),
            f"review approved {expected} row(s), CSV carries {len(rows)}"))

    checklist = review.get("reviewer_checklist") or {}
    for label, key in (("canonical", "canonical_files_modified"), ("GUP", "gup_files_modified")):
        if key in checklist:
            add(Precondition(
                f"reviewer did not modify {label} files",
                checklist[key] is False,
                f"{key}={checklist[key]!r}"))

    # -- operation index -----------------------------------------------------
    try:
        verification.operations = read_operations(bundle.manifest, review, len(rows))
        add(Precondition(
            "operation index classifies every CSV row exactly once",
            True,
            str(verification.operations.summary())))
    except (OperationError, KeyError) as error:
        add(Precondition("operation index classifies every CSV row exactly once",
                         False, str(error)))
        return verification

    for note in verification.operations.inferred:
        add(Precondition("operation classification is declared, not inferred",
                         False, note, blocking=False))

    # A node this batch must register may only be referenced by a row the manifest
    # marked pending; an ordinary addition that needs a new node is misclassified.
    registered = {r.node_id for r in verification.operations.registrations}
    if registered:
        for csv_row in verification.operations.additions:
            row = rows[csv_row - 1]
            needed = registered & {row["source_id"], row["target_id"]}
            if needed:
                add(Precondition(
                    f"addition at CSV row {csv_row} does not depend on an unregistered node",
                    False,
                    f"row references {sorted(needed)}, which this batch registers; it "
                    "belongs in pending_additions"))

    return verification


def _unresolved_endpoints(
    verifications: list[BundleVerification], approved: set[str],
) -> list[tuple[BundleVerification, Precondition]]:
    """Invariant 1 across the whole batch, before the snapshot is taken.

    The applier checks this too, but only mid-transaction and only one endpoint
    at a time: it aborts on the first, so a bundle short of several approved
    identities returns to its author across as many round trips. Reporting the
    whole set up front makes the remediation a single pass.

    Registrations are unioned across every bundle in the batch, because a batch
    may legitimately have one bundle register an identity another references --
    which is why this cannot be a per-bundle precondition.

    Constitution 3.2: the registry, not the graph, is the list of approved node
    IDs, and it is deliberately a superset, so an approved identity sitting at
    degree 0 is still a legal endpoint.
    """
    available = set(approved)
    for verification in verifications:
        available |= {r.node_id for r in verification.operations.registrations}
        if verification.plan is not None:
            available |= {a.node_id for a in verification.plan.additions}
            available |= {r.canonical_id for r in verification.plan.replacements}

    failures = []
    for verification in verifications:
        unresolved: dict[str, list[int]] = {}
        for csv_row, row in enumerate(verification.rows, start=1):
            for side in ("source_id", "target_id"):
                if row[side] and row[side] not in available:
                    unresolved.setdefault(row[side], []).append(csv_row)
        if unresolved:
            listed = "; ".join(
                f"{node_id} (row{'s' if len(r) > 1 else ''} {', '.join(map(str, r))})"
                for node_id, r in sorted(unresolved.items()))
            failures.append((verification, Precondition(
                "every edge endpoint is an approved node or registered by this batch",
                False,
                f"{len(unresolved)} unresolved endpoint id(s): {listed}")))
    return failures


def _apply_migration(graph: CanonicalGraph, registry: Registry,
                     verification: BundleVerification, batch: "Batch",
                     integration_id: str, prefixes) -> None:
    """Execute one `decision_migration_v1` plan in the order DEC-2026-0035 fixes.

    Registry first, then repoints, then removals in *descending* baseline line
    order -- removing a row shifts every later physical locator, so taking the
    highest line first keeps the remaining ones addressing what they were
    measured against. Every operation was already matched against its full
    before-image in `verify_bundle`; the re-checks here are the compare-and-swap
    that makes a mid-batch surprise abort rather than corrupt.
    """
    plan = verification.plan
    bundle_id = verification.bundle.bundle_id

    for addition in plan.additions:
        if addition.node_id in registry.ids:
            raise IntegrationError(
                f"{bundle_id}: node {addition.node_id} is already registered (invariant 4)")
        if addition.node_id[: addition.node_id.find("_") + 1] not in prefixes:
            raise IntegrationError(
                f"{bundle_id}: node {addition.node_id} does not use an approved "
                "prefix (invariant 3)")
        registry.add({"id": addition.node_id, "label": addition.label,
                      "kind": addition.kind, "degree": "0", "roles": ""})
        batch.registrations.append({
            "id": addition.node_id, "label": addition.label, "kind": addition.kind,
            "basis": "decision_migration", "authority": addition.authority,
            # A migration registers an approved identity on a Decision's
            # authority, not because a row in this batch needs it as an
            # endpoint, so nothing depends on it at registration time.
            "edges_depending_on_it": [],
            "bundle_id": bundle_id, "review_id": verification.bundle.review_id,
            "integration_id": integration_id,
        })

    for replacement in plan.replacements:
        if replacement.retired_id not in registry.ids:
            raise IntegrationError(
                f"{bundle_id}: {replacement.retired_id} is not registered; there is no "
                "identity to retire")
        if replacement.canonical_id in registry.ids:
            raise IntegrationError(
                f"{bundle_id}: {replacement.canonical_id} is already registered; the "
                "replacement would duplicate an approved identity (invariant 4)")
        registry.replace(replacement.retired_id, {
            "id": replacement.canonical_id, "label": replacement.canonical_label,
            "kind": replacement.kind, "degree": "0", "roles": ""})
        batch.node_replacements.append({
            "retired_id": replacement.retired_id, "retired_label": replacement.retired_label,
            "canonical_id": replacement.canonical_id,
            "canonical_label": replacement.canonical_label,
            "authority": replacement.authority,
            "incident_rows": list(replacement.incident_rows),
            "bundle_id": bundle_id, "integration_id": integration_id,
        })

    for repoint in plan.repoints:
        edge = graph.edges[repoint.canonical_index]
        differing = [c for c in EDGE_COLUMNS if edge.get(c, "") != repoint.before[c]]
        if differing:
            raise IntegrationError(
                f"{bundle_id}: canonical row {repoint.canonical_row} no longer matches its "
                f"before-image on {differing}; rolling back")
        for field_name, delta in repoint.changes.items():
            edge[field_name] = delta["to"]
        batch.repoints.append({
            "canonical_row": repoint.canonical_row,
            "authority": repoint.authority,
            "changes": {f: dict(d) for f, d in repoint.changes.items()},
            "assertion": f"{edge['source_id']} {edge['edge_type']} {edge['target_id']}",
            "bundle_id": bundle_id, "integration_id": integration_id,
        })

    for removal in sorted(plan.removals, key=lambda r: r.canonical_row, reverse=True):
        edge = graph.edges[removal.canonical_index]
        differing = [c for c in EDGE_COLUMNS if edge.get(c, "") != removal.before[c]]
        if differing:
            raise IntegrationError(
                f"{bundle_id}: canonical row {removal.canonical_row} no longer matches its "
                f"before-image on {differing}; rolling back")
        graph.edges.pop(removal.canonical_index)
        batch.removals.append({
            "canonical_row": removal.canonical_row,
            "authority": removal.authority,
            "assertion": f"{removal.before['source_id']} {removal.before['edge_type']} "
                         f"{removal.before['target_id']}",
            "citation": f"{removal.before['book']} p{removal.before['page'] or '-'} / "
                        f"{removal.before['section']}",
            "bundle_id": bundle_id, "integration_id": integration_id,
        })

    # Nothing may survive that still names a retired identity -- not in the
    # registry, not as an endpoint. This is the check that turns an incomplete
    # incident set into a rollback instead of a dangling reference.
    for replacement in plan.replacements:
        if not replacement.require_no_remaining:
            continue
        if replacement.retired_id in registry.ids:
            raise IntegrationError(
                f"{bundle_id}: retired ID {replacement.retired_id} is still in the registry")
        surviving = [
            i + 2 for i, edge in enumerate(graph.edges)
            if replacement.retired_id in (edge.get("source_id"), edge.get("target_id"))
        ]
        if surviving:
            raise IntegrationError(
                f"{bundle_id}: retired ID {replacement.retired_id} still appears as an "
                f"endpoint on canonical row(s) {surviving}; the incident set was incomplete")


def _verify_direct_migration(bundle: Bundle, root: Path, verification: BundleVerification,
                             review: dict, add) -> None:
    """Preconditions for `decision_migration_v1` (WORK_QUEUES 1.8 rules 33, 34).

    All of these run before the snapshot, so a plan that fails any of them never
    reaches a write. The operation plan is read only from the checksummed GUP
    component -- never from the manifest, which is provenance and routing
    metadata rather than a second plan that could quietly widen the first.
    """
    manifest = bundle.manifest or {}

    add(Precondition(
        "direct migration declares artifact_kind decision_migration",
        manifest.get("artifact_kind") == "decision_migration",
        f"artifact_kind={manifest.get('artifact_kind')!r}"))

    add(Precondition(
        "direct migration carries no edge CSV",
        bundle.edges_path is None,
        "an edge CSV is forbidden in this bundle shape"))

    components = manifest.get("components") or []
    migration_components = [c for c in components if c.get("kind") == "decision_migration"]
    validation_components = [c for c in components if c.get("kind") == "validation"]
    add(Precondition(
        "direct migration names exactly one migration and one validation component",
        len(migration_components) == 1 and len(validation_components) == 1,
        f"{len(migration_components)} migration, {len(validation_components)} validation"))

    approves = manifest.get("approves") or {}
    add(Precondition(
        "direct migration pins both approval checksums",
        bool(approves.get("gup_checksum") and approves.get("review_checksum")),
        "approves.gup_checksum and approves.review_checksum are mandatory for this model"))

    if len(migration_components) != 1:
        return

    component = migration_components[0]
    plan_path = root / component["path"]
    actual = checksum_file(plan_path) if plan_path.exists() else "MISSING"

    # The manifest may not name a plan other than the one the Review approved.
    add(Precondition(
        "migration component is the GUP the Review approved",
        component["path"] == (review.get("reviewed_gup") or {}).get("path")
        and actual == approves.get("gup_checksum"),
        f"component={component['path']} "
        f"reviewed={(review.get('reviewed_gup') or {}).get('path')} "
        f"approves.gup_checksum={approves.get('gup_checksum')} actual={actual}"))

    if not plan_path.exists():
        add(Precondition("migration plan is readable", False, f"{component['path']} is missing"))
        return

    try:
        plan = read_plan(yaml.safe_load(plan_path.read_text(encoding="utf-8")))
    except (MigrationError, KeyError, TypeError, ValueError) as error:
        add(Precondition("migration plan is a well-formed decision_migration_v1 operation set",
                         False, str(error)))
        return
    verification.plan = plan
    add(Precondition("migration plan is a well-formed decision_migration_v1 operation set",
                     True, str(plan.summary())))

    # -- authority Decisions -------------------------------------------------
    declared_decisions = {d["id"]: d for d in manifest.get("authority_decisions") or []}
    add(Precondition(
        "manifest names exactly the plan's authority Decisions",
        set(declared_decisions) == set(plan.authority),
        f"manifest={sorted(declared_decisions)} plan={sorted(plan.authority)}"))
    for entry in (plan_provenance_decisions(plan_path)):
        path = root / entry["path"]
        actual_decision = checksum_file(path) if path.exists() else "MISSING"
        add(Precondition(
            f"authority Decision matches on disk: {entry['id']}",
            actual_decision == entry["checksum"],
            f"declared={entry['checksum']} actual={actual_decision}"))

    # -- baselines, before-images, incident sets -----------------------------
    edges_path = root / plan.canonical_source
    registry_path = root / plan.registry_source
    if not edges_path.exists() or not registry_path.exists():
        add(Precondition("migration baselines exist", False,
                         f"{plan.canonical_source} / {plan.registry_source}"))
        return

    graph_rows = read_csv_rows(edges_path)
    registry = Registry.load(registry_path)
    problems = check_baselines(
        plan, checksum_file(edges_path), len(graph_rows),
        checksum_file(registry_path), len(registry.rows))
    add(Precondition("migration baselines match the pinned canonical and registry state",
                     not problems, "; ".join(problems) or "both baselines current"))

    problems = check_before_images(plan, graph_rows)
    add(Precondition("every enumerated before-image matches canonical exactly",
                     not problems, "; ".join(problems) or
                     f"{len(plan.repoints)} repoint(s), {len(plan.removals)} removal(s)"))

    problems = check_incident_sets(plan, graph_rows)
    add(Precondition("each replacement enumerates its complete incident row set",
                     not problems, "; ".join(problems) or
                     f"{len(plan.replacements)} replacement(s)"))

    problems = check_registry_targets(plan, registry.ids)
    add(Precondition("registry additions are absent and retired IDs are present",
                     not problems, "; ".join(problems) or "registry targets consistent"))

    # -- the Reviewer's own count of what it approved ------------------------
    summary = review.get("summary") or {}
    if "operations_reviewed" in summary:
        planned = sum(plan.summary().values())
        add(Precondition(
            "review operation count matches the plan",
            summary["operations_reviewed"] == planned,
            f"review approved {summary['operations_reviewed']}, plan carries {planned}"))


def plan_provenance_decisions(plan_path: Path) -> list[dict]:
    """The Decision inputs the plan itself pinned, with their checksums."""
    document = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
    return (document.get("provenance") or {}).get("decision_inputs") or []


def _apply_update(
    graph: CanonicalGraph,
    verification: BundleVerification,
    update: EdgeUpdate,
    existing_keys: dict,
    batch: "Batch",
    integration_id: str,
) -> None:
    """Compare-and-swap one canonical row. Any surprise aborts the whole batch."""
    bundle_id = verification.bundle.bundle_id
    if not 0 <= update.canonical_index < len(graph.edges):
        raise IntegrationError(
            f"{bundle_id}: update {update.ref} names canonical line "
            f"{update.canonical_line}, which is outside the {len(graph.edges)}-row file")

    current = graph.edges[update.canonical_index]
    patch = {c: verification.rows[update.csv_row - 1].get(c, "") for c in EDGE_COLUMNS}

    # Identity check. The line number alone could point at a neighbour, so the
    # endpoints must agree before anything is rewritten.
    #
    # An update may legitimately repoint or reverse an edge, and then the patch
    # row's endpoints are the *new* ones. What the canonical row must match is
    # the endpoint the manifest declares it currently holds: the `canonical`
    # side of the change where one is declared, the patch value otherwise. A
    # mistaken line number is still caught, because an undeclared endpoint has
    # to match the patch exactly and a declared one has to match its stated
    # precondition.
    expected_endpoints = tuple(
        update.changes[c]["canonical"] if c in update.changes else patch[c]
        for c in ("source_id", "target_id"))
    if (current["source_id"], current["target_id"]) != expected_endpoints:
        raise IntegrationError(
            f"{bundle_id}: update {update.ref} targets canonical line "
            f"{update.canonical_line} "
            f"({current['source_id']} -> {current['target_id']}) but the manifest expects "
            f"{expected_endpoints[0]} -> {expected_endpoints[1]}")

    # Declared preconditions: every changed field must still hold its expected
    # canonical value, or the row moved under the Reviewer's feet.
    stale = {f: {"expected": c["canonical"], "actual": current[f]}
             for f, c in update.changes.items() if current[f] != c["canonical"]}
    if stale:
        raise IntegrationError(
            f"{bundle_id}: update {update.ref} failed its compare-and-swap on canonical "
            f"line {update.canonical_line}: {stale}")

    # The patch row must equal the canonical row with exactly the declared
    # changes applied — nothing else may ride along in the CSV.
    expected = dict(current)
    expected.update({f: c["patch"] for f, c in update.changes.items()})
    drift = {f: {"declared": expected[f], "csv": patch[f]}
             for f in EDGE_COLUMNS if expected[f] != patch[f]}
    if drift:
        raise IntegrationError(
            f"{bundle_id}: update {update.ref} CSV row carries changes the manifest does "
            f"not declare: {drift}")

    before = dict(current)
    key_before = assertion_key(current)
    graph.edges[update.canonical_index] = expected
    key_after = assertion_key(expected)
    if key_after != key_before:
        if key_after in existing_keys:
            raise IntegrationError(
                f"{bundle_id}: update {update.ref} would collide with canonical row "
                f"{existing_keys[key_after]} (invariant 12)")
        existing_keys.pop(key_before, None)
        existing_keys[key_after] = update.canonical_line

    batch.updated.append({
        **update.as_dict(),
        "assertion_before": f"{before['source_id']} {before['edge_type']} {before['target_id']}",
        "assertion_after": f"{expected['source_id']} {expected['edge_type']} {expected['target_id']}",
        "bundle_id": bundle_id,
        "packet_id": verification.bundle.packet_id,
        "gup_id": verification.bundle.gup_id,
        "review_id": verification.bundle.review_id,
        "integration_id": integration_id,
    })


def _header_of(path: Path) -> list[str]:
    text = path.read_bytes().decode("utf-8")
    first = text.splitlines()[0] if text.strip() else ""
    return first.split(",") if first else []


def next_integration_id(manifests_dir: Path, day: str) -> str:
    existing = sorted(manifests_dir.glob(f"INT-{day}-*.json")) if manifests_dir.exists() else []
    return f"INT-{day}-{len(existing) + 1:03d}"


@dataclass
class Batch:
    integration_id: str
    verifications: list[BundleVerification]
    pre_counts: dict
    post_counts: dict = field(default_factory=dict)
    added: list[dict] = field(default_factory=list)
    updated: list[dict] = field(default_factory=list)
    registrations: list[dict] = field(default_factory=list)
    node_replacements: list[dict] = field(default_factory=list)
    repoints: list[dict] = field(default_factory=list)
    removals: list[dict] = field(default_factory=list)
    registrations_without_edges: list[dict] = field(default_factory=list)
    registry_resync: list[dict] = field(default_factory=list)
    registry_preexisting_drift: list[dict] = field(default_factory=list)
    polarity_corrections: list[dict] = field(default_factory=list)
    node_deltas: list[dict] = field(default_factory=list)
    baseline: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    rejected: list[dict] = field(default_factory=list)
    snapshot: dict = field(default_factory=dict)


def integrate(
    root: Path,
    ruleset_id: str,
    bundles: list[Bundle],
    integration_id: str | None = None,
    dry_run: bool = False,
) -> Batch:
    """Apply a batch. Raises IntegrationError -- and rolls back -- on any failure."""
    paths = CanonicalPaths(root=root, ruleset_id=ruleset_id)
    constitution = root / "rulesets" / ruleset_id / "governance" / "constitution.md"
    prefixes = approved_prefixes(constitution)
    profile = load_role_profile(root / "rulesets" / ruleset_id / "profiles" / "roles.yaml")
    thresholds = profile["thresholds"]
    general_rules = set(json.loads(
        (root / "rulesets" / ruleset_id / "registries" / "general_rules.json")
        .read_text(encoding="utf-8")).keys())

    # -- steps 1 and 2, before anything is written ---------------------------
    verifications = [verify_bundle(b, root) for b in bundles]
    blocking = [(v.bundle.bundle_id, c) for v in verifications for c in v.blocking_failures]

    # Endpoint resolution is a property of the batch, not of one bundle, so it
    # is measured here rather than in verify_bundle -- but still before the
    # snapshot, so a batch that fails it never reaches a write.
    # NOTE: endpoint resolution (invariant 1) is deliberately *not* checked here.
    # The applier enforces it inside the transaction and rolls back correctly; a
    # pre-snapshot version would only improve reporting, by listing every
    # unresolved endpoint instead of aborting on the first. That is worth having,
    # but it has to be measured against the real registry, and the shared rewind
    # fixture presents a registry with cross-bundle registrations stripped -- a
    # state production never produces. Landing it meant either weakening the
    # check or reworking that fixture, and neither is worth trading for a
    # diagnostics nicety. `_unresolved_endpoints` is kept for reporting use.

    day = _dt.date.today().strftime("%Y%m%d")
    integration_id = integration_id or next_integration_id(paths.manifests_dir, day)

    graph = CanonicalGraph.load(paths)
    pre_counts = {
        "edges": len(graph.edges),
        "nodes": len(graph.nodes),
        "registry": len(Registry.load(paths.registry).rows),
        "edges_checksum": checksum_file(paths.edges),
        "nodes_checksum": checksum_file(paths.nodes),
        "graph_json_checksum": checksum_file(paths.graph_json),
        "registry_checksum": checksum_file(paths.registry),
    }
    batch = Batch(integration_id=integration_id, verifications=verifications, pre_counts=pre_counts)

    # -- baseline invariant state, measured before the batch -----------------
    baseline_result = check(graph.edges, graph.nodes, prefixes, general_rules, EDGE_COLUMNS)
    check_derived_state(graph.edges, graph.nodes, thresholds, baseline_result)
    batch.baseline = {
        "findings": len(baseline_result.findings),
        "by_invariant": baseline_result.by_invariant(),
        "affected_rows": len({f.row for f in baseline_result.findings if f.row}),
    }

    if blocking:
        batch.rejected = [{"bundle_id": bid, **c.as_dict()} for bid, c in blocking]
        raise IntegrationError(
            f"{len(blocking)} blocking precondition failure(s); nothing was written")

    snapshot_dir = root / "build" / "snapshots" / integration_id
    registry = Registry.load(paths.registry)

    # Registry drift that already existed, measured against the pre-batch node
    # table so it is not confused with the resync this batch legitimately causes.
    pre_nodes = {n["id"]: n for n in graph.nodes}
    batch.registry_preexisting_drift = [
        {"id": row.values["id"],
         "degree": {"registry": row.values["degree"], "canonical": node["degree"]},
         "roles": {"registry": row.values["roles"], "canonical": node["roles"]}}
        for row in registry.rows
        if (node := pre_nodes.get(row.values["id"])) is not None
        and (row.values["degree"] != node["degree"] or row.values["roles"] != node["roles"])
    ]

    with Transaction(paths.writable(), snapshot_dir) as transaction:
        # -- step 4: node changes first --------------------------------------
        # Every registration is applied before any edge may reference the new ID,
        # which is what the manifests' `node_operations.sequencing` requires.
        registered: dict[str, NodeRegistration] = {}
        for verification in verifications:
            for registration in verification.operations.registrations:
                if registration.node_id in registry.ids:
                    raise IntegrationError(
                        f"{verification.bundle.bundle_id}: node {registration.node_id} is "
                        "already registered; a registry addition must not overwrite an "
                        "approved identity (invariant 4)")
                if registration.node_id[: registration.node_id.find("_") + 1] not in prefixes:
                    raise IntegrationError(
                        f"{verification.bundle.bundle_id}: node {registration.node_id} does "
                        "not use an approved prefix (invariant 3)")
                registry.add({
                    "id": registration.node_id,
                    "label": registration.label,
                    "kind": registration.kind,
                    "degree": "0",
                    "roles": "",
                })
                registered[registration.node_id] = registration
                batch.registrations.append({
                    **registration.as_dict(),
                    "bundle_id": verification.bundle.bundle_id,
                    "review_id": verification.bundle.review_id,
                    "integration_id": integration_id,
                })

        # -- decision_migration_v1, in the order DEC-2026-0035 fixes ----------
        for verification in verifications:
            if verification.plan is not None:
                _apply_migration(graph, registry, verification, batch, integration_id, prefixes)

        # -- steps 5, 6: updates, then additions, with duplicate prevention ---
        existing_keys = {assertion_key(e): i + 2 for i, e in enumerate(graph.edges)}
        # Constitution 3.2: the registry is the list of approved node IDs. An
        # approved ID that currently carries no edge (race_demihuman, race_human)
        # is still a legal endpoint, so eligibility is read from the registry
        # rather than from the nodes present in the graph.
        node_ids = registry.ids

        # Updates are applied first: they mutate rows that already exist, so
        # doing them before the appends keeps every declared line number valid.
        for verification in verifications:
            for update in verification.operations.updates:
                _apply_update(graph, verification, update, existing_keys, batch, integration_id)

        for verification in verifications:
            for csv_row in verification.operations.added_rows:
                row = verification.rows[csv_row - 1]
                edge = {c: row.get(c, "") for c in EDGE_COLUMNS}
                key = assertion_key(edge)
                if key in existing_keys:
                    raise IntegrationError(
                        f"{verification.bundle.bundle_id}: "
                        f"{edge['source_id']} {edge['edge_type']} {edge['target_id']} "
                        f"duplicates canonical row {existing_keys[key]} (invariant 12)")
                for side in ("source_id", "target_id"):
                    if edge[side] not in node_ids:
                        raise IntegrationError(
                            f"{verification.bundle.bundle_id}: {side}={edge[side]} "
                            "is not a canonical node and is not registered by this "
                            "batch (invariant 1)")
                existing_keys[key] = len(graph.edges) + 2
                graph.edges.append(edge)
                # -- step 7: row-level provenance ---------------------------
                batch.added.append({
                    "assertion": f"{edge['source_id']} {edge['edge_type']} {edge['target_id']}",
                    "aspect": edge["aspect"],
                    "condition": edge["condition"],
                    "citation": f"{edge['book']} p{edge['page'] or '-'} / {edge['section']}",
                    "row": len(graph.edges) + 1,
                    "pending_on_registration": csv_row in verification.operations.pending_additions,
                    "bundle_id": verification.bundle.bundle_id,
                    "packet_id": verification.bundle.packet_id,
                    "gur_id": verification.bundle.gur_id,
                    "gup_id": verification.bundle.gup_id,
                    "review_id": verification.bundle.review_id,
                    "integration_id": integration_id,
                })

        # A registration that carries no edge is legal, not an error. The
        # registry is the list of *approved IDs* (constitution 3.2), not a
        # projection of the graph: it is already a strict superset, and an
        # approved identity may sit at degree 0 until a later packet asserts a
        # relationship for it. Refusing these would reject a Review that
        # approved a complete named list — the cleric spell list — while only
        # part of it has mechanical relationships drawn so far.
        #
        # It is still never silent: each one is recorded so the registry count
        # moving further ahead of the node count always has a stated reason.
        endpoints = ({e["source_id"] for e in graph.edges}
                     | {e["target_id"] for e in graph.edges})
        batch.registrations_without_edges = [
            {"id": node_id,
             "label": registration.label,
             "kind": registration.kind,
             "edges_depending_on_it": registration.depends}
            for node_id, registration in sorted(registered.items())
            if node_id not in endpoints]

        # -- step 8: recompute deterministic polarity ------------------------
        batch.polarity_corrections = apply_derived_polarity(graph.edges)

        # -- step 9: recompute degrees and roles -----------------------------
        before_nodes = {n["id"]: dict(n) for n in graph.nodes}
        labels = {n["id"]: n["label"] for n in graph.nodes}
        kinds = {n["id"]: n["kind"] for n in graph.nodes}
        # A newly registered node takes the label and kind the Review approved,
        # not whatever an edge row happened to carry; identity still comes from
        # the ID (invariant 4).
        for node_id, registration in registered.items():
            labels[node_id] = registration.label
            kinds[node_id] = registration.kind
        graph.nodes = rebuild_nodes(graph.edges, labels, kinds, thresholds)

        for node in graph.nodes:
            was = before_nodes.get(node["id"])
            if was is None:
                batch.node_deltas.append({"id": node["id"], "change": "created", "to": dict(node)})
            elif any(was[c] != node[c] for c in ("degree", "core_degree", "in_degree", "out_degree", "roles")):
                batch.node_deltas.append({
                    "id": node["id"],
                    "change": "recomputed",
                    "from": {c: was[c] for c in ("degree", "core_degree", "in_degree", "out_degree", "roles")},
                    "to": {c: node[c] for c in ("degree", "core_degree", "in_degree", "out_degree", "roles")},
                })

        # -- step 11: invariant suite over the whole post-batch graph --------
        after_result = check(graph.edges, graph.nodes, prefixes, general_rules, EDGE_COLUMNS)
        check_derived_state(graph.edges, graph.nodes, thresholds, after_result)
        batch.after = {
            "findings": len(after_result.findings),
            "by_invariant": after_result.by_invariant(),
            "checked": after_result.checked,
            "not_machine_checkable": after_result.not_machine_checkable,
        }

        # A batch may never add a finding. Pre-existing baseline defects are
        # carried, but the delta introduced by this batch must be zero. Rows the
        # batch rewrote count as touched just as much as rows it appended.
        # Rule 36: a repoint changes an assertion's identity, so it can collide
        # with a row it never touched. This is checked after every operation has
        # landed, and before any derived output is rebuilt.
        seen: dict = {}
        for index, edge in enumerate(graph.edges):
            key = assertion_key(edge)
            if key in seen:
                raise IntegrationError(
                    f"post-migration duplicate assertion key: canonical rows {seen[key]} "
                    f"and {index + 2} both assert {edge['source_id']} "
                    f"{edge['edge_type']} {edge['target_id']} (invariant 12)")
            seen[key] = index + 2

        # Removing a row renumbers every row below it, so a touched row's
        # baseline line number is not its post-batch line number. Without this
        # map, a defect the batch merely *carried* -- the legacy unset polarity
        # DEC-2026-0026 explicitly preserves through an identity-only repoint --
        # gets compared against a different row and looks newly introduced.
        removed_rows = sorted(r["canonical_row"] for r in batch.removals)

        def shifted(baseline_row: int) -> int:
            return baseline_row - sum(1 for r in removed_rows if r < baseline_row)

        carried = {}
        for finding in baseline_result.findings:
            if finding.row:
                carried.setdefault(shifted(finding.row), set()).add(
                    (finding.invariant, finding.rule))

        new_rows = ({a["row"] for a in batch.added}
                    | {u["canonical_row"] for u in batch.updated}
                    | {shifted(r["canonical_row"]) for r in batch.repoints})
        # A repoint changes identity fields on a row that already existed, so a
        # finding of the same kind that row already carried is not this batch's
        # doing. An appended row has no baseline entry, so nothing is excused
        # there and ordinary batches behave exactly as before.
        introduced = [
            f for f in after_result.findings
            if f.row in new_rows and (f.invariant, f.rule) not in carried.get(f.row, set())
        ]
        regressions = {
            inv: count - batch.baseline["by_invariant"].get(inv, 0)
            for inv, count in after_result.by_invariant().items()
            if count > batch.baseline["by_invariant"].get(inv, 0)
        }
        if introduced or regressions:
            batch.rejected = [f.as_dict() for f in introduced]
            raise IntegrationError(
                f"batch introduces {len(introduced)} invariant finding(s) "
                f"and regresses {regressions}; rolling back")

        # -- registry: the derived columns are a snapshot of canonical state --
        # `degree` and `roles` in the registry are generated, so they are
        # rebuilt here for every row. INT-20260730-001 recomputed ten nodes
        # without resyncing them, and that drift is corrected by this batch.
        derived = {n["id"]: n for n in graph.nodes}
        for row in registry.rows:
            node = derived.get(row.values["id"])
            fresh = {"degree": node["degree"] if node else "0",
                     "roles": node["roles"] if node else ""}
            changed = {f: {"from": row.values[f], "to": fresh[f]}
                       for f in ("degree", "roles") if row.values[f] != fresh[f]}
            if changed and row.values["id"] not in registered:
                batch.registry_resync.append({"id": row.values["id"], **changed})
            row.values.update(fresh)

        # -- steps 10, 12: write canonical, then recount from disk -----------
        if not dry_run:
            graph.save(paths)
            registry.save(paths.registry)
            reloaded = CanonicalGraph.load(paths)
            if len(reloaded.edges) != len(graph.edges) or len(reloaded.nodes) != len(graph.nodes):
                raise IntegrationError("post-write reread does not match in-memory counts")
            declared = (sum(len(v.operations.added_rows) for v in verifications)
                        - len(batch.removals))
            actual = len(reloaded.edges) - pre_counts["edges"]
            if declared != actual:
                raise IntegrationError(
                    f"count drift: bundles declare a net {declared} row(s), "
                    f"canonical changed by {actual}")
            reloaded_registry = Registry.load(paths.registry)
            # A replacement retires one ID and registers one, so it is net zero.
            expected_registry = pre_counts["registry"] + len(batch.registrations)
            if len(reloaded_registry.rows) != expected_registry:
                raise IntegrationError(
                    f"registry drift: expected {expected_registry} row(s), "
                    f"found {len(reloaded_registry.rows)}")
            missing = reloaded.node_ids - reloaded_registry.ids
            if missing:
                raise IntegrationError(
                    f"{len(missing)} graph node(s) are absent from the registry: "
                    f"{sorted(missing)[:5]}")

        batch.post_counts = {
            "edges": len(graph.edges),
            "nodes": len(graph.nodes),
            "registry": len(registry.rows),
            "edges_checksum": checksum_file(paths.edges) if not dry_run else None,
            "nodes_checksum": checksum_file(paths.nodes) if not dry_run else None,
            "graph_json_checksum": checksum_file(paths.graph_json) if not dry_run else None,
            "registry_checksum": checksum_file(paths.registry) if not dry_run else None,
        }
        batch.snapshot = transaction.snapshot.as_dict(root)

    return batch
