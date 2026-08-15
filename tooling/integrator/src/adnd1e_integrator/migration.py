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
    authority: tuple[str, ...] = ()
    additions: list[NodeAddition] = field(default_factory=list)
    replacements: list[NodeReplacement] = field(default_factory=list)
    repoints: list[EndpointRepoint] = field(default_factory=list)
    removals: list[RowRemoval] = field(default_factory=list)
    canonical_source: str = ""
    canonical_checksum: str = ""
    canonical_rows_read: int = 0
    registry_source: str = ""
    registry_checksum: str = ""
    registry_rows_read: int = 0

    def summary(self) -> dict:
        return {
            "node_additions": len(self.additions),
            "node_replacements": len(self.replacements),
            "endpoint_repoints": len(self.repoints),
            "row_removals": len(self.removals),
        }


#: The only endpoint fields a repoint may change, each paired with its label.
PAIRED_ENDPOINTS = {"source_id": "source_label", "target_id": "target_label"}


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
    """Parse a reviewed decision-migration GUP into an executable plan."""
    if gup.get("operation_model") != "decision_migration_v1":
        raise MigrationError(
            f"operation_model={gup.get('operation_model')!r}, not decision_migration_v1")

    authority = tuple(gup.get("authority") or ())
    if not authority:
        raise MigrationError("plan names no authority Decision")

    provenance = gup.get("provenance") or {}
    plan = MigrationPlan(
        gup_id=gup.get("id", ""),
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
    unknown = sorted(set(node_changes) - {"additions_proposed", "relabels", "replacements"})
    if unknown:
        raise MigrationError(
            f"node_changes declares {unknown}, which decision_migration_v1 does not "
            "authorize; the plan needs an operation model that covers it")

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

    for raw in node_changes.get("replacements") or []:
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

    for raw in gup.get("canonical_changes") or []:
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

    touched = [r.canonical_row for r in plan.repoints] + [r.canonical_row for r in plan.removals]
    duplicated = sorted({r for r in touched if touched.count(r) > 1})
    if duplicated:
        raise MigrationError(f"canonical row(s) {duplicated} touched by more than one operation")

    return plan


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
    for repoint in plan.repoints:
        for field_name, delta in repoint.changes.items():
            if repoint.before[field_name] != delta["from"]:
                problems.append(
                    f"repoint at canonical row {repoint.canonical_row}: {field_name} declares "
                    f"from={delta['from']!r} but its before-image carries "
                    f"{repoint.before[field_name]!r}")
    return problems


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
