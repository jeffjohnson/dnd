"""The `decision_migration_v1` direct operation model (WORK_QUEUES 1.8).

DEC-2026-0035 introduced this model for a Decision migration that has no edge-CSV
representation: an edge CSV can express additions and ordinary compare-and-swap
updates, but it cannot encode registry identity replacement, retirement, or an
exact deletion. Rather than let a prose note stand in for an executable
instruction -- which would make the Integrator invent operations after Review --
the reviewed GUP YAML *is* the plan, pinned by checksum from the Approved
manifest.

Four operations are permitted, and nothing else:

1. `node_changes.additions_proposed` -- register a previously absent approved node;
2. `node_changes.replacements`      -- replace one registry identity and retire
                                       the old ID, with no alias left behind;
3. `canonical_changes`              -- repoint one enumerated endpoint ID and its
                                       paired label by exact compare-and-swap; and
4. `canonical_removals`             -- remove one exact 18-field before-image.

The parsing here is deliberately literal. Every operation must name the canonical
row it touches, carry a complete before-image, and be authorized by a Decision the
GUP lists. Anything this module cannot match exactly is a rejection, never a
best-effort application: the prohibited actions in DEC-2026-0035 are all forms of
guessing, and the way not to guess is to refuse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .canonical import EDGE_COLUMNS


class MigrationError(ValueError):
    """The plan is not a well-formed decision_migration_v1 operation set."""


@dataclass(frozen=True)
class NodeAddition:
    node_id: str
    label: str
    kind: str
    authority: str


@dataclass(frozen=True)
class RetiredNode:
    node_id: str
    label: str
    #: One-based advisory locator in the plan's pinned registry baseline. Under
    #: DEC-2026-0038 a moved row is informational; the retired ID, its label and
    #: the pinned registry checksum are what the transaction actually relies on.
    registry_csv_row: int | None = None


@dataclass(frozen=True)
class NodeMerge:
    """`decision_migration_v2`: many retired registry IDs into one absent ID."""

    canonical_id: str
    canonical_label: str
    kind: str
    authority: str
    retired: tuple[RetiredNode, ...]
    incident_rows: tuple[int, ...]
    require_no_remaining: bool = True


@dataclass(frozen=True)
class NodeReplacement:
    retired_id: str
    retired_label: str
    canonical_id: str
    canonical_label: str
    kind: str
    authority: str
    incident_rows: tuple[int, ...]
    require_no_remaining: bool = True


@dataclass(frozen=True)
class EndpointRepoint:
    canonical_row: int
    authority: str
    changes: dict[str, dict[str, str]]
    before: dict[str, str]

    @property
    def canonical_index(self) -> int:
        """`canonical_row` is a file line number; the header occupies line 1."""
        return self.canonical_row - 2


@dataclass(frozen=True)
class LabelNormalization:
    """A `decision_migration_v3` blank-endpoint-label fill.

    DEC-2026-0050 bounds this tightly: it changes only `source_label`,
    `target_label`, or both, on one explicitly enumerated row. Each changed label
    must be blank in the pinned before-image and become the exact current
    registry label for its endpoint ID, whose ID is not touched. It never changes
    assertion identity, which is why it is a separate operation from a repoint
    rather than a repoint that happens to leave the ID alone.
    """
    canonical_row: int
    authority: str
    changes: dict[str, dict[str, str]]
    before: dict[str, str]

    @property
    def canonical_index(self) -> int:
        return self.canonical_row - 2

    @property
    def endpoint_ids(self) -> dict[str, str]:
        """The endpoint ID each changed label belongs to."""
        return {f: self.before[LABEL_ENDPOINTS[f]] for f in self.changes}


@dataclass(frozen=True)
class RowRemoval:
    canonical_row: int
    authority: str
    before: dict[str, str]

    @property
    def canonical_index(self) -> int:
        return self.canonical_row - 2


@dataclass
class MigrationPlan:
    gup_id: str = ""
    model: str = "decision_migration_v1"
    authority: tuple[str, ...] = ()
    additions: list[NodeAddition] = field(default_factory=list)
    merges: list[NodeMerge] = field(default_factory=list)
    replacements: list[NodeReplacement] = field(default_factory=list)
    repoints: list[EndpointRepoint] = field(default_factory=list)
    normalizations: list[LabelNormalization] = field(default_factory=list)
    removals: list[RowRemoval] = field(default_factory=list)
    canonical_source: str = ""
    canonical_checksum: str = ""
    canonical_rows_read: int = 0
    registry_source: str = ""
    registry_checksum: str = ""
    registry_rows_read: int = 0

    @property
    def operation_count(self) -> int:
        """Operations the Reviewer counts. Retired identities are not operations:
        one merge consolidating six IDs is three operations, not nine."""
        return (len(self.additions) + len(self.replacements) + len(self.merges)
                + len(self.repoints) + len(self.normalizations) + len(self.removals))

    def summary(self) -> dict:
        summary = {
            "node_additions": len(self.additions),
            "node_replacements": len(self.replacements),
            "endpoint_repoints": len(self.repoints),
            "row_removals": len(self.removals),
        }
        if self.model == MODEL_V2:
            summary["node_merges"] = len(self.merges)
            summary["retired_identities"] = sum(len(m.retired) for m in self.merges)
        if self.model == MODEL_V3:
            summary["label_normalizations"] = len(self.normalizations)
            summary["normalized_label_fields"] = sum(
                len(n.changes) for n in self.normalizations)
        return summary


#: The only endpoint fields a repoint may change, each paired with its label.
PAIRED_ENDPOINTS = {"source_id": "source_label", "target_id": "target_label"}

#: The label field carried by each endpoint, and the endpoint each label belongs
#: to. A normalization is keyed by the label; a repoint is keyed by the ID.
LABEL_ENDPOINTS = {"source_label": "source_id", "target_label": "target_id"}

MODEL_V1 = "decision_migration_v1"
MODEL_V2 = "decision_migration_v2"
MODEL_V3 = "decision_migration_v3"
MODELS = (MODEL_V1, MODEL_V2, MODEL_V3)


def _before_image(raw: dict, where: str) -> dict[str, str]:
    """A before-image must be complete across all 18 canonical fields.

    A partial image would let a repoint match a row it was never measured
    against, which is exactly the "broadened to another row" failure the model
    prohibits.
    """
    if not isinstance(raw, dict):
        raise MigrationError(f"{where}: before-image is missing")
    missing = [c for c in EDGE_COLUMNS if c not in raw]
    if missing:
        raise MigrationError(
            f"{where}: before-image omits {len(missing)} of 18 canonical field(s): "
            f"{missing[:5]}")
    extra = [k for k in raw if k not in EDGE_COLUMNS]
    if extra:
        raise MigrationError(f"{where}: before-image carries unknown field(s) {extra}")
    return {c: "" if raw[c] is None else str(raw[c]) for c in EDGE_COLUMNS}


def read_plan(gup: dict) -> MigrationPlan:
    """Parse a reviewed decision-migration GUP into an executable plan.

    Handles both narrow models. v1 is one-to-one registry replacement with
    optional additions and exact removals; v2 is a bounded many-to-one merge and
    nothing else. WORK_QUEUES 1.9: "Version 1 remains unchanged and cannot be
    used for a merge", so the two shapes are parsed apart rather than blended.
    """
    model = gup.get("operation_model")
    if model not in MODELS:
        raise MigrationError(
            f"operation_model={model!r}, not one of {list(MODELS)}")

    authority = tuple(gup.get("authority") or ())
    if not authority:
        raise MigrationError("plan names no authority Decision")

    provenance = gup.get("provenance") or {}
    plan = MigrationPlan(
        gup_id=gup.get("id", ""),
        model=model,
        authority=authority,
        canonical_source=provenance.get("canonical_source", ""),
        canonical_checksum=provenance.get("canonical_checksum", ""),
        canonical_rows_read=provenance.get("canonical_rows_read", 0),
        registry_source=provenance.get("registry_source", ""),
        registry_checksum=provenance.get("registry_checksum", ""),
        registry_rows_read=provenance.get("registry_rows_read", 0),
    )

    def authorized(value: str, where: str) -> str:
        if value not in authority:
            raise MigrationError(
                f"{where}: authority {value!r} is not listed by the plan {list(authority)}")
        return value

    node_changes = gup.get("node_changes") or {}

    # DEC-2026-0035 authorizes four operations and says so exhaustively. An
    # operation container this model does not know must abort the plan rather
    # than be skipped: silently applying the parts we recognise and dropping the
    # rest is a partial application of a reviewed migration, which is worse than
    # refusing it. DEC-2026-0032's two-into-one `merges`, for instance, is not a
    # one-row `replacements` swap and has no execution path here at all.
    known = {"additions_proposed", "relabels", "replacements"}
    if model == MODEL_V2:
        known.add("merges")
    unknown = sorted(set(node_changes) - known)
    if unknown:
        raise MigrationError(
            f"node_changes declares {unknown}, which {model} does not "
            "authorize; the plan needs an operation model that covers it")

    if model == MODEL_V3:
        # DEC-2026-0050: v3 is one-or-more one-to-one replacements, the closed
        # paired repoints incident to them, and explicit blank-label
        # normalization. Everything else stays prohibited, so a v3 plan that
        # also added, relabelled, merged or removed would be widening the model
        # rather than using it.
        for name, present in (("additions_proposed", node_changes.get("additions_proposed")),
                              ("relabels", node_changes.get("relabels")),
                              ("merges", node_changes.get("merges")),
                              ("canonical_removals", gup.get("canonical_removals"))):
            if present:
                raise MigrationError(
                    f"{model} requires an empty {name}; {len(present)} declared")
        _read_replacements(node_changes.get("replacements") or [], plan, authorized)
        if not plan.replacements:
            raise MigrationError(f"{model} declares no replacements")
        _read_canonical_changes(gup.get("canonical_changes") or [], plan, authorized)
        _check_touched_once(plan)
        return plan

    if model == MODEL_V2:
        # WORK_QUEUES 1.9: v2 carries merges and their paired repoints, and
        # every other operation array must be empty. A v2 plan that also
        # replaced or removed would be a merge model doing v1's work unreviewed.
        for name, present in (("additions_proposed", node_changes.get("additions_proposed")),
                              ("relabels", node_changes.get("relabels")),
                              ("replacements", node_changes.get("replacements")),
                              ("canonical_removals", gup.get("canonical_removals"))):
            if present:
                raise MigrationError(
                    f"{model} requires an empty {name}; {len(present)} declared")
        _read_merges(node_changes.get("merges") or [], plan, authorized)
        _read_repoints(gup.get("canonical_changes") or [], plan, authorized)
        if not plan.merges:
            raise MigrationError(f"{model} declares no merges")
        _check_touched_once(plan)
        return plan

    if node_changes.get("relabels"):
        # A relabel is not one of the four permitted operations. Applying one
        # would be a non-enumerated field change.
        raise MigrationError(
            "plan declares node_changes.relabels, which decision_migration_v1 "
            "does not authorize")

    for raw in node_changes.get("additions_proposed") or []:
        plan.additions.append(NodeAddition(
            node_id=raw["proposed_id"],
            label=raw["proposed_label"],
            kind=raw["kind"],
            authority=authorized(raw["authority"], f"addition {raw['proposed_id']}"),
        ))

    _read_replacements(node_changes.get("replacements") or [], plan, authorized)

    _read_repoints(gup.get("canonical_changes") or [], plan, authorized)

    for raw in gup.get("canonical_removals") or []:
        where = f"canonical_removals row {raw.get('canonical_row')}"
        if raw.get("replacement_edge") is not None:
            raise MigrationError(
                f"{where}: replacement_edge must be null; this model removes without "
                "substituting")
        plan.removals.append(RowRemoval(
            canonical_row=int(raw["canonical_row"]),
            authority=authorized(raw["authority"], where),
            before=_before_image(raw.get("before"), where),
        ))

    if not (plan.additions or plan.replacements or plan.repoints or plan.removals):
        raise MigrationError("plan declares no operations")

    _check_touched_once(plan)
    return plan


def _read_replacements(raws: list, plan: MigrationPlan, authorized) -> None:
    """Parse one-to-one registry replacements. Identical in v1 and v3."""
    for raw in raws:
        where = f"replacement {raw.get('retired_id')}"
        if raw.get("registry_action") != "replace_one_row":
            raise MigrationError(
                f"{where}: registry_action={raw.get('registry_action')!r} is not "
                "replace_one_row")
        plan.replacements.append(NodeReplacement(
            retired_id=raw["retired_id"],
            retired_label=raw["retired_label"],
            canonical_id=raw["canonical_id"],
            canonical_label=raw["canonical_label"],
            kind=raw["kind"],
            authority=authorized(raw["authority"], where),
            incident_rows=tuple(sorted(raw.get("incident_canonical_rows") or ())),
            require_no_remaining=bool(raw.get("require_no_remaining_retired_endpoints", True)),
        ))


def _read_canonical_changes(raws: list, plan: MigrationPlan, authorized) -> None:
    """Split a v3 `canonical_changes` list by declared kind.

    The two kinds are parsed apart rather than blended because they have
    different bounds: a repoint must change an endpoint ID paired with its label,
    a normalization must change *only* labels and must not touch identity.
    """
    for raw in raws:
        kind = raw.get("kind")
        if kind == "endpoint_repoint":
            _read_repoints([raw], plan, authorized)
        elif kind == "endpoint_label_normalization":
            _read_normalization(raw, plan, authorized)
        else:
            raise MigrationError(
                f"canonical_changes row {raw.get('canonical_row')}: kind={kind!r} is not "
                "endpoint_repoint or endpoint_label_normalization")


def _read_normalization(raw: dict, plan: MigrationPlan, authorized) -> None:
    """Every bound DEC-2026-0050 places on a blank-label normalization."""
    where = f"canonical_changes row {raw.get('canonical_row')}"
    changes = raw.get("changes") or {}
    if not changes:
        raise MigrationError(f"{where}: a normalization changes at least one label")
    illegal = sorted(set(changes) - set(LABEL_ENDPOINTS))
    if illegal:
        raise MigrationError(
            f"{where}: a normalization may change only "
            f"{sorted(LABEL_ENDPOINTS)}; declared {illegal}")
    if raw.get("touches_assertion_identity"):
        raise MigrationError(
            f"{where}: touches_assertion_identity must be false; a label fill never "
            "changes assertion identity")
    for field_name, delta in changes.items():
        if set(delta) != {"from", "to"}:
            raise MigrationError(f"{where}: {field_name} must declare both from and to")
        if str(delta["from"]).strip():
            raise MigrationError(
                f"{where}: {field_name} declares from={delta['from']!r}; a normalization "
                "fills a blank label and may never edit a nonblank one")
        if not str(delta["to"]).strip():
            raise MigrationError(
                f"{where}: {field_name} declares a blank to; the fill must supply the "
                "registry label")
    plan.normalizations.append(LabelNormalization(
        canonical_row=int(raw["canonical_row"]),
        authority=authorized(raw["authority"], where),
        changes={f: {"from": str(d["from"]), "to": str(d["to"])}
                 for f, d in changes.items()},
        before=_before_image(raw.get("before"), where),
    ))


def _check_touched_once(plan: MigrationPlan) -> None:
    touched = ([r.canonical_row for r in plan.repoints]
               + [r.canonical_row for r in plan.normalizations]
               + [r.canonical_row for r in plan.removals])
    duplicated = sorted({r for r in touched if touched.count(r) > 1})
    if duplicated:
        raise MigrationError(f"canonical row(s) {duplicated} touched by more than one operation")


def _read_repoints(raws: list, plan: MigrationPlan, authorized) -> None:
    """Parse paired endpoint repoints. Identical in both models."""
    for raw in raws:
        where = f"canonical_changes row {raw.get('canonical_row')}"
        if raw.get("kind") != "endpoint_repoint":
            raise MigrationError(f"{where}: kind={raw.get('kind')!r} is not endpoint_repoint")
        changes = raw.get("changes") or {}
        endpoints = [f for f in changes if f in PAIRED_ENDPOINTS]
        if len(endpoints) != 1:
            raise MigrationError(
                f"{where}: a repoint changes exactly one endpoint ID, not {sorted(changes)}")
        endpoint = endpoints[0]
        label_field = PAIRED_ENDPOINTS[endpoint]
        if set(changes) != {endpoint, label_field}:
            raise MigrationError(
                f"{where}: {endpoint} must be paired with {label_field}; "
                f"declared {sorted(changes)}")
        for field_name, delta in changes.items():
            if set(delta) != {"from", "to"}:
                raise MigrationError(
                    f"{where}: {field_name} must declare both from and to")
        plan.repoints.append(EndpointRepoint(
            canonical_row=int(raw["canonical_row"]),
            authority=authorized(raw["authority"], where),
            changes={f: {"from": str(d["from"]), "to": str(d["to"])}
                     for f, d in changes.items()},
            before=_before_image(raw.get("before"), where),
        ))


def _read_merges(raws: list, plan: MigrationPlan, authorized) -> None:
    """Parse v2 merges. Every bound in WORK_QUEUES 1.9 is enforced here."""
    for raw in raws:
        canonical_id = raw.get("canonical_id")
        where = f"merge into {canonical_id}"
        if raw.get("registry_action") != "merge_retired_rows_into_one":
            raise MigrationError(
                f"{where}: registry_action={raw.get('registry_action')!r} is not "
                "merge_retired_rows_into_one")
        if not raw.get("require_no_remaining_retired_endpoints"):
            raise MigrationError(
                f"{where}: require_no_remaining_retired_endpoints must be true")
        if not canonical_id or not raw.get("canonical_label") or not raw.get("kind"):
            raise MigrationError(f"{where}: canonical_id, canonical_label and kind are required")

        retired_raw = raw.get("retired_nodes") or []
        if len(retired_raw) < 2:
            raise MigrationError(
                f"{where}: a merge consolidates at least two retired IDs, "
                f"{len(retired_raw)} declared; a one-to-one change is v1's replacement")
        retired = []
        for entry in retired_raw:
            if not entry.get("id") or not entry.get("label"):
                raise MigrationError(f"{where}: every retired node needs an id and a label")
            row = entry.get("registry_csv_row")
            retired.append(RetiredNode(
                node_id=entry["id"], label=entry["label"],
                registry_csv_row=int(row) if row is not None else None))

        ids = [r.node_id for r in retired]
        duplicated = sorted({i for i in ids if ids.count(i) > 1})
        if duplicated:
            raise MigrationError(f"{where}: retired ID(s) {duplicated} declared more than once")
        if canonical_id in ids:
            raise MigrationError(
                f"{where}: the canonical ID is also listed as retired")

        plan.merges.append(NodeMerge(
            canonical_id=canonical_id,
            canonical_label=raw["canonical_label"],
            kind=raw["kind"],
            authority=authorized(raw["authority"], where),
            retired=tuple(retired),
            incident_rows=tuple(sorted(raw.get("incident_canonical_rows") or ())),
        ))

    surviving = [m.canonical_id for m in plan.merges]
    duplicated = sorted({i for i in surviving if surviving.count(i) > 1})
    if duplicated:
        raise MigrationError(f"canonical ID(s) {duplicated} are the target of two merges")

    claimed: dict[str, str] = {}
    for merge in plan.merges:
        for retired in merge.retired:
            if retired.node_id in claimed:
                raise MigrationError(
                    f"retired ID {retired.node_id} is claimed by two merges "
                    f"({claimed[retired.node_id]} and {merge.canonical_id})")
            claimed[retired.node_id] = merge.canonical_id


def check_baselines(plan: MigrationPlan, edges_checksum: str, edge_rows: int,
                    registry_checksum: str, registry_rows: int) -> list[str]:
    """Both pinned baselines must match before a snapshot is taken."""
    problems = []
    if plan.canonical_checksum != edges_checksum:
        problems.append(
            f"canonical baseline drift: plan pinned {plan.canonical_checksum}, "
            f"found {edges_checksum}")
    if plan.canonical_rows_read != edge_rows:
        problems.append(
            f"canonical row count drift: plan read {plan.canonical_rows_read}, "
            f"found {edge_rows}")
    if plan.registry_checksum != registry_checksum:
        problems.append(
            f"registry baseline drift: plan pinned {plan.registry_checksum}, "
            f"found {registry_checksum}")
    if plan.registry_rows_read != registry_rows:
        problems.append(
            f"registry row count drift: plan read {plan.registry_rows_read}, "
            f"found {registry_rows}")
    return problems


def check_before_images(plan: MigrationPlan, edges: list[dict]) -> list[str]:
    """Every enumerated row must still be exactly what the Reviewer measured."""
    problems = []
    for operation, label in ([(r, "repoint") for r in plan.repoints]
                             + [(r, "normalization") for r in plan.normalizations]
                             + [(r, "removal") for r in plan.removals]):
        index = operation.canonical_index
        if not 0 <= index < len(edges):
            problems.append(
                f"{label} names canonical row {operation.canonical_row}, which is outside "
                f"the {len(edges)}-row baseline")
            continue
        current = edges[index]
        differing = [c for c in EDGE_COLUMNS if current.get(c, "") != operation.before[c]]
        if differing:
            problems.append(
                f"{label} at canonical row {operation.canonical_row}: before-image differs "
                f"on {differing}")
    for operation, label in ([(r, "repoint") for r in plan.repoints]
                             + [(r, "normalization") for r in plan.normalizations]):
        for field_name, delta in operation.changes.items():
            if operation.before[field_name] != delta["from"]:
                problems.append(
                    f"{label} at canonical row {operation.canonical_row}: {field_name} "
                    f"declares from={delta['from']!r} but its before-image carries "
                    f"{operation.before[field_name]!r}")
    return problems


def check_normalization_labels(plan: MigrationPlan, registry_rows: list) -> list[str]:
    """Each filled label must be the endpoint's exact current registry label.

    DEC-2026-0050 does not let a normalization invent text: the value is looked
    up, not authored. Checking it against the registry is what keeps this an
    exact migration rather than a licence to write labels into canonical.

    The endpoint ID itself must be untouched, so a normalization and a repoint
    can never both claim the same row -- `_check_touched_once` enforces that -- and
    a row whose ID this plan is repointing is verified against the *post*-
    replacement identity, since the registry row for a retired ID is gone by the
    time labels are read.
    """
    labels = {row.values["id"]: row.values["label"] for row in registry_rows}
    replaced = {r.retired_id: (r.canonical_id, r.canonical_label)
                for r in plan.replacements}

    problems = []
    for normalization in plan.normalizations:
        for field_name, delta in normalization.changes.items():
            endpoint_id = normalization.before[LABEL_ENDPOINTS[field_name]]
            if endpoint_id in replaced:
                canonical_id, expected = replaced[endpoint_id]
                source = f"the replacement identity {canonical_id}"
            else:
                expected = labels.get(endpoint_id)
                source = "the registry"
            if expected is None:
                problems.append(
                    f"normalization at canonical row {normalization.canonical_row}: "
                    f"{field_name} names endpoint {endpoint_id!r}, which the registry "
                    "does not carry")
            elif delta["to"] != expected:
                problems.append(
                    f"normalization at canonical row {normalization.canonical_row}: "
                    f"{field_name} fills {delta['to']!r} but {source} carries "
                    f"{expected!r} for {endpoint_id}")
    return problems


def check_declared_counts(plan: MigrationPlan, declared: dict) -> list[str]:
    """The plan's own `counts` block must match the operations it carries.

    A count that disagrees with the enumerated operations means the Reviewer
    approved one number while the Integrator would apply another, so it is drift
    even when every individual operation is well formed.
    """
    if not declared:
        return []
    actual = {
        "nodes_replaced": len(plan.replacements),
        "endpoint_repoints": len(plan.repoints),
        "label_normalizations": len(plan.normalizations),
        "rows_removed": len(plan.removals),
        "nodes_added": len(plan.additions),
        "nodes_merged": len(plan.merges),
    }
    return [
        f"counts.{name} declares {declared[name]} but the plan carries {value}"
        for name, value in sorted(actual.items())
        if name in declared and int(declared[name]) != value
    ]


def check_incident_sets(plan: MigrationPlan, edges: list[dict]) -> list[str]:
    """A replacement must enumerate *every* row still using the retired ID.

    An unenumerated incident row is the failure mode the model most needs to
    catch: applying the enumerated ones and inferring the rest is precisely the
    "infer an unlisted endpoint repoint from a retired ID" prohibition, and it
    would leave a retired endpoint behind in canonical state.
    """
    problems = []
    repointed = {r.canonical_row for r in plan.repoints}
    removed = {r.canonical_row for r in plan.removals}
    for replacement in plan.replacements:
        actual = {
            i + 2 for i, edge in enumerate(edges)
            if replacement.retired_id in (edge.get("source_id"), edge.get("target_id"))
        }
        declared = set(replacement.incident_rows)
        if actual != declared:
            problems.append(
                f"replacement {replacement.retired_id}: incident set is incomplete; "
                f"declared {sorted(declared)}, canonical carries {sorted(actual)}")
        unhandled = declared - repointed - removed
        if unhandled:
            problems.append(
                f"replacement {replacement.retired_id}: incident row(s) {sorted(unhandled)} "
                "are not enumerated as a repoint or removal")
    return problems


def check_merge_incident_sets(plan: MigrationPlan, edges: list[dict]) -> list[str]:
    """Every row using any retired ID must be an enumerated repoint of that merge.

    The failure this exists to stop is a retired identity surviving in canonical
    because a row referencing it was never enumerated. Inferring the missing row
    is explicitly prohibited, so an incomplete set is a rejection.
    """
    problems = []
    repointed = {r.canonical_row for r in plan.repoints}
    for merge in plan.merges:
        retired_ids = {r.node_id for r in merge.retired}
        actual = {
            i + 2 for i, edge in enumerate(edges)
            if edge.get("source_id") in retired_ids or edge.get("target_id") in retired_ids
        }
        declared = set(merge.incident_rows)
        if actual != declared:
            missing = sorted(actual - declared)
            extra = sorted(declared - actual)
            problems.append(
                f"merge into {merge.canonical_id}: incident set does not match canonical; "
                f"unenumerated={missing} not-incident={extra}")
        unhandled = declared - repointed
        if unhandled:
            problems.append(
                f"merge into {merge.canonical_id}: incident row(s) {sorted(unhandled)} are "
                "not enumerated as a paired endpoint repoint")
    return problems


def check_merge_registry(plan: MigrationPlan, registry_rows: list) -> list[str]:
    """Retired IDs must exist with the declared label; survivors must not exist.

    DEC-2026-0038: a retired node's `registry_csv_row` is advisory. A moved row
    whose ID and label still match is an observation, not an error -- the pinned
    registry checksum is what makes the transaction safe, and an advisory locator
    never substitutes for it.
    """
    problems = []
    by_id = {r.values["id"]: (index + 2, r.values) for index, r in enumerate(registry_rows)}
    for merge in plan.merges:
        if merge.canonical_id in by_id:
            problems.append(
                f"merge into {merge.canonical_id}: the canonical ID is already registered; "
                "v2 merges into a previously absent identity")
        for retired in merge.retired:
            found = by_id.get(retired.node_id)
            if found is None:
                problems.append(
                    f"merge into {merge.canonical_id}: retired ID {retired.node_id} is not "
                    "in the registry")
                continue
            _, values = found
            if values["label"] != retired.label:
                problems.append(
                    f"merge into {merge.canonical_id}: retired ID {retired.node_id} is "
                    f"labelled {values['label']!r} but the plan declares {retired.label!r}")
    return problems


def merge_locator_observations(plan: MigrationPlan, registry_rows: list) -> list[str]:
    """Advisory `registry_csv_row` values that no longer point at their row.

    Informational by DEC-2026-0038, and reported rather than dropped so the audit
    trail still shows the plan was measured against a different registry layout.
    """
    observations = []
    positions = {r.values["id"]: index + 2 for index, r in enumerate(registry_rows)}
    for merge in plan.merges:
        for retired in merge.retired:
            if retired.registry_csv_row is None:
                continue
            actual = positions.get(retired.node_id)
            if actual is not None and actual != retired.registry_csv_row:
                observations.append(
                    f"{retired.node_id}: advisory registry_csv_row "
                    f"{retired.registry_csv_row} now reads {actual}; ID and label still match")
    return observations


def check_registry_targets(plan: MigrationPlan, registry_ids: set[str]) -> list[str]:
    """Additions must be absent, retired IDs present, and new IDs unclaimed."""
    problems = []
    for addition in plan.additions:
        if addition.node_id in registry_ids:
            problems.append(
                f"addition {addition.node_id} is already registered; a migration must not "
                "overwrite an approved identity")
    for replacement in plan.replacements:
        if replacement.retired_id not in registry_ids:
            problems.append(
                f"replacement {replacement.retired_id} is not in the registry, so there is "
                "no row to replace")
        if replacement.canonical_id in registry_ids:
            problems.append(
                f"replacement target {replacement.canonical_id} is already registered; "
                "replacing would create a duplicate identity")
    return problems
