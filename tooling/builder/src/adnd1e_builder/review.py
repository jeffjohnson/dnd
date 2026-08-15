"""Reviewer decisions as compiler input.

A Review artifact is already machine-readable: every row carries a disposition,
optional `exact_corrections`, and an `integration_action`. That is a revision
directive, so the Builder consumes it directly rather than inventing a second
format for the same information.

Applying a directive does not make its result valid. Corrections are pushed back
through the normal validators, and a correction that violates the constitution is
reported like any other defect. The Reviewer owns what an edge asserts; the
Builder still owns whether the row is well formed.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from .vocab import BUILD_OWNED_FIELDS, COLUMNS

#: Correction keys that are not edge columns but are understood elsewhere and
#: must not be reported as unknown.
#:
#: `submitted_assertion` and `corrected_assertion` are the Reviewer's record of
#: what the row asserted before and after. They are documentation for a human
#: comparing the two, not instructions -- the instruction lives in the bucket
#: block -- so they are read past rather than executed.
_TOLERATED_CORRECTION_KEYS = frozenset(
    {
        "integration_action",
        "proposed_label",
        "ref",
        "submitted_assertion",
        "corrected_assertion",
    }
)

APPROVED = "approved"
APPROVED_WITH_REVISION = "approved_with_revision"
REJECTED = "rejected"
ARCHITECT_ESCALATION = "architect_escalation"

DISPOSITIONS = frozenset({APPROVED, APPROVED_WITH_REVISION, REJECTED, ARCHITECT_ESCALATION})

#: The two spellings a Review uses for its per-row rulings. The entry shape is
#: identical; which one appears depends on when the Review was written.
ROW_DECISION_KEYS = ("row_decisions", "edge_decisions")

#: The same for rulings on proposed nodes.
NODE_DECISION_KEYS = ("node_registry_decisions", "node_decisions")

#: Bulk rulings. A Review that approves most of a large packet says so once
#: under a policy block listing every ref it covers, rather than repeating an
#: entry per row, and then states only the exceptions individually. Eleven
#: published Reviews do this -- the psionics Review covers 216 of its 218 rows
#: this way -- so not reading them made almost every row look undecided.
ROW_POLICY_KEY = "field_decision_policy"
NODE_POLICY_KEY = "node_registry_policy"

#: Every top-level `*_policy` key this loader accounts for.
KNOWN_POLICY_KEYS = frozenset({ROW_POLICY_KEY, NODE_POLICY_KEY})

#: Every top-level `*_decisions` key this loader accounts for. Anything else is
#: reported rather than ignored: an unread ruling is one that silently does not
#: apply, which looks exactly like a clean revision.
KNOWN_DECISION_KEYS = frozenset(
    set(ROW_DECISION_KEYS)
    | set(NODE_DECISION_KEYS)
    | {
        "node_addition_decisions",
        "node_replacement_decisions",
        "canonical_change_decisions",
        "canonical_removal_decisions",
        # Migration-review rulings. A decision_migration is planned from the
        # Decision record, not compiled through these directives, so the packet
        # compiler is not their consumer and not reading them here hides
        # nothing from anyone.
        "node_relabel_decisions",
        "component_decisions",
    }
)

CANONICAL_UPDATE = "canonical_update"
CANONICAL_MIGRATION = "canonical_migration"
CANONICAL_OPERATIONS = frozenset({CANONICAL_UPDATE, CANONICAL_MIGRATION})

#: Keys inside `exact_corrections` that address the shape of the operation
#: rather than the value of an edge field. `operation` says the row repairs an
#: existing canonical assertion instead of inserting a new one, and the row
#: numbers say which. They are not columns and must never reach an edge.
STRUCTURAL_KEYS = frozenset({"operation", "canonical_row", "obsolete_conflicting_row"})

#: The bucket a compiled row lands in. A Reviewer may rule that a row belongs in
#: a different one -- typically that an insertion is really a repair to an
#: existing canonical assertion -- and says so by naming the bucket.
BUCKETS = ("additions", "updates", "pending_additions")

#: Keys inside `exact_corrections` that address which bucket a row belongs in
#: rather than any field of it. `edge_changes` alone carries an instruction for
#: whichever bucket the row is already in.
BUCKET_KEYS = frozenset({"edge_changes"} | {f"edge_changes.{bucket}" for bucket in BUCKETS})

#: Where a Review supplies a complete node-addition entry for the patch to carry.
NODE_CHANGE_KEY = "node_changes"


@dataclass(frozen=True)
class BucketInstruction:
    """A Reviewer ruling on which bucket a row belongs in and what it changes.

    Whether a compiled row is a new assertion or a repair to one the graph
    already holds is a judgement about the neighbourhood, and the Reviewer makes
    it with the canonical row in front of them. Expressing it as a field
    correction is not possible -- the bucket is not a column -- so a Review says
    it by naming the bucket, and this is the parsed form of that.
    """

    #: Buckets this row must be removed from.
    remove_from: frozenset[str] = frozenset()
    #: The bucket it must end up in, when the Review names one.
    target_bucket: str = ""
    canonical_row: int | None = None
    reason: str = ""
    #: Explicit per-field change set, when the Review supplies one.
    changes: dict[str, dict[str, str]] = field(default_factory=dict)
    #: Fields to drop from the change set the build computes. Used where a
    #: correction is source-supported but a decision defers the canonical write.
    remove_change_fields: frozenset[str] = frozenset()
    #: Fields recorded for the Integrator as knowingly not applied, with the
    #: Reviewer's disposition for each.
    differences_not_applied: dict[str, dict] = field(default_factory=dict)
    #: Edge column values supplied inside the bucket payload. A Review that
    #: restates the whole corrected row is correcting those fields, and reading
    #: only the bucket would drop every one of them.
    field_values: dict[str, str] = field(default_factory=dict)
    #: Complete node-addition entries the Review supplies for the patch to carry.
    node_additions: tuple[dict, ...] = ()
    #: Explicit column corrections from a `replace_ref`/`fields` instruction.
    #: Unlike `field_values` these are authored rulings, not an echo of the row,
    #: so they must reach the build-ownership check rather than bypass it.
    field_corrections: dict[str, str] = field(default_factory=dict)
    #: Keys inside a bucket instruction this parser does not implement.
    unknown_keys: tuple[str, ...] = ()
    #: Row the ruling supersedes, when the Review names one on the operation.
    obsolete_row: int | None = None
    #: The Reviewer's own account of why this row is an update. A later Review
    #: that approves the operation carries a rationale about the row's contents,
    #: not about its placement, so the account travels with the ruling.
    detail: str = ""

    @property
    def states_placement(self) -> bool:
        """The instruction decides which bucket this row lands in."""
        return bool(
            self.remove_from or self.target_bucket or self.canonical_row is not None
        )

    @property
    def is_empty(self) -> bool:
        return not (
            self.remove_from
            or self.target_bucket
            or self.canonical_row is not None
            or self.changes
            or self.remove_change_fields
            or self.differences_not_applied
            or self.field_values
            or self.node_additions
            or self.field_corrections
            or self.obsolete_row is not None
        )


#: Keys a bucket instruction may carry that are not edge columns. Anything else
#: is a Reviewer instruction this build does not implement, and it is reported
#: rather than ignored -- an unread `fields:` block silently discards a ruling.
_KNOWN_INSTRUCTION_KEYS = frozenset(
    {
        "add",
        "canonical_row",
        "changes",
        "detail",
        "differences_not_applied",
        "fields",
        "obsolete_conflicting_row",
        "reason",
        "ref",
        "remove_change_fields",
        "remove_ref",
        "replace_ref",
        "retain_ref",
        "set_differences_not_applied",
    }
)


def _normalized_change(delta: dict) -> dict[str, str] | None:
    """One field's change set, from either spelling a Review uses.

    Reviews write the pair as `canonical`/`patch` in some places and `from`/`to`
    in others. Both name the same two values. The emitted spelling is
    `canonical`/`patch`, matching the diff the build computes itself, so a
    Reviewer-supplied change set and a computed one read the same downstream.
    """
    if "patch" in delta or "canonical" in delta:
        return {
            "canonical": str(delta.get("canonical", "")),
            "patch": str(delta.get("patch", "")),
        }
    if "from" in delta or "to" in delta:
        return {"canonical": str(delta.get("from", "")), "patch": str(delta.get("to", ""))}
    return None


def _parse_operation_records(records) -> BucketInstruction:
    """Read the operation ruling a Review restates in `submitted_operation_records`.

    A later Review in a chain approves the operations an earlier one directed,
    and `load_chain` lets the later disposition win wholesale. Without this the
    approval would erase the ruling it approves: rows the Reviewer placed as
    canonical updates would come back as insertions, which is the one outcome
    every party has already rejected.

    Only records naming a `canonical_row` are rulings. A record that restates
    the submitted edge row is the patch's own content, not an instruction.
    """
    canonical_row = None
    reason = ""
    changes: dict[str, dict[str, str]] = {}
    differences: dict[str, dict] = {}
    obsolete_row = None
    detail = ""

    for record in records or ():
        if not isinstance(record, dict):
            continue
        row_number = _as_row_number(record.get("canonical_row"))
        if row_number is None:
            continue
        canonical_row = row_number
        reason = reason or str(record.get("reason") or "").strip()
        obsolete_row = _as_row_number(record.get("obsolete_conflicting_row")) or obsolete_row
        detail = detail or str(record.get("detail") or "").strip()
        for field_name, delta in (record.get("changes") or {}).items():
            if isinstance(delta, dict):
                normalized = _normalized_change(delta)
                if normalized is not None:
                    changes[str(field_name)] = normalized
        for field_name, body in (record.get("differences_not_applied") or {}).items():
            if isinstance(body, dict):
                differences[str(field_name)] = dict(body)

    if canonical_row is None:
        return BucketInstruction()
    return BucketInstruction(
        target_bucket="updates",
        canonical_row=canonical_row,
        reason=reason,
        changes=changes,
        differences_not_applied=differences,
        obsolete_row=obsolete_row,
        detail=detail,
    )


def _parse_bucket_instruction(corrections: dict, records=None) -> BucketInstruction:
    """Read the `edge_changes[.bucket]` instructions out of `exact_corrections`.

    `submitted_operation_records` supplies the same ruling in restated form and
    is read first, so an explicit `exact_corrections` instruction still wins.
    """
    prior = _parse_operation_records(records)
    remove_from: set[str] = set()
    target_bucket = prior.target_bucket
    canonical_row = prior.canonical_row
    reason = prior.reason
    changes: dict[str, dict[str, str]] = dict(prior.changes)
    remove_change_fields: set[str] = set()
    differences: dict[str, dict] = dict(prior.differences_not_applied)
    field_values: dict[str, str] = {}
    node_additions: list[dict] = []
    field_corrections: dict[str, str] = {}
    unknown_instruction_keys: set[str] = set()
    obsolete_row = prior.obsolete_row
    detail = prior.detail

    # `node_changes.additions_proposed.add` supplies a whole proposal entry.
    node_block = corrections.get(NODE_CHANGE_KEY)
    if isinstance(node_block, dict):
        proposed = node_block.get("additions_proposed")
        if isinstance(proposed, dict):
            entry = proposed.get("add")
            if isinstance(entry, dict):
                node_additions.append(dict(entry))
            elif isinstance(proposed.get("add"), list):
                node_additions.extend(dict(e) for e in proposed["add"] if isinstance(e, dict))

    for key in sorted(BUCKET_KEYS & set(corrections)):
        body = corrections[key]
        if not isinstance(body, dict):
            continue
        named_bucket = key.split(".", 1)[1] if "." in key else ""

        # `edge_changes: {updates: {...}}` nests the bucket one level down.
        nested = {b: body[b] for b in BUCKETS if isinstance(body.get(b), dict)}
        entries = nested or ({named_bucket: body} if named_bucket else {})
        for bucket, instruction in entries.items():
            if not isinstance(instruction, dict):
                continue
            if instruction.get("remove_ref"):
                remove_from.add(bucket)
                continue

            payload = instruction.get("add")
            payload = payload if isinstance(payload, dict) else instruction

            # `replace_ref` names the row and `fields` carries the corrected
            # columns. This is the Reviewer authoring values, so it is kept
            # apart from the whole-row echo and handed to the ownership check.
            for source in (instruction, payload):
                block = source.get("fields")
                if isinstance(block, dict):
                    for field_name, value in block.items():
                        field_corrections[str(field_name)] = (
                            "" if value is None else str(value)
                        )
            for source in (instruction, payload):
                unknown_instruction_keys.update(
                    str(key)
                    for key in source
                    if key not in _KNOWN_INSTRUCTION_KEYS and key not in COLUMNS
                )

            if instruction.get("retain_ref") or payload is not instruction or bucket == "updates":
                target_bucket = target_bucket or bucket
            row_number = _as_row_number(payload.get("canonical_row"))
            if row_number is not None:
                canonical_row = row_number
            reason = reason or str(payload.get("reason") or "").strip()
            for field_name, delta in (payload.get("changes") or {}).items():
                if isinstance(delta, dict):
                    normalized = _normalized_change(delta)
                    if normalized is not None:
                        changes[str(field_name)] = normalized
            for field_name in payload.get("remove_change_fields") or ():
                remove_change_fields.add(str(field_name))
            for field_name, body_ in (payload.get("set_differences_not_applied") or {}).items():
                if isinstance(body_, dict):
                    differences[str(field_name)] = dict(body_)
            for field_name, body_ in (payload.get("differences_not_applied") or {}).items():
                if isinstance(body_, dict):
                    differences[str(field_name)] = dict(body_)
            # A payload that restates the corrected row carries edge columns
            # alongside the instruction. Those are corrections -- except for the
            # build-owned ones. Restating a derived polarity is an echo of the
            # row, not a Reviewer authoring it, and treating it as authorship
            # would report invariants 13-14 against a Review that did nothing
            # wrong. A genuine polarity ruling arrives as an explicit
            # `exact_corrections` entry or in the `changes` set, both of which
            # still go through the ownership check.
            for field_name in COLUMNS:
                if field_name in BUILD_OWNED_FIELDS:
                    continue
                if field_name in payload and not isinstance(payload[field_name], (dict, list)):
                    value = payload[field_name]
                    field_values[field_name] = "" if value is None else str(value)

    return BucketInstruction(
        remove_from=frozenset(remove_from),
        target_bucket=target_bucket,
        canonical_row=canonical_row,
        reason=reason,
        changes=changes,
        remove_change_fields=frozenset(remove_change_fields),
        differences_not_applied=differences,
        field_values=field_values,
        node_additions=tuple(node_additions),
        field_corrections=field_corrections,
        unknown_keys=tuple(sorted(unknown_instruction_keys)),
        obsolete_row=obsolete_row,
        detail=detail,
    )


def _as_row_number(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class RowDirective:
    ref: str
    disposition: str
    corrections: dict[str, str]
    rationale: str
    integration_action: str
    canonical_rows: tuple[int, ...] = ()
    operation: str = ""
    canonical_row: int | None = None
    obsolete_row: int | None = None
    #: The bucket the reviewed patch presented this row in -- `additions` or
    #: `updates`. An `approved` disposition affirms that bucket, so a build that
    #: later demotes an approved update to an insertion has lost the ruling.
    presented_operation: str = ""
    #: Every bucket the reviewed patch presented this row in. A row can occupy
    #: two, which is itself the defect a Review sometimes rules on.
    presented_operations: tuple[str, ...] = ()
    #: The Review that decided this row, and the GUR that Review's patch was
    #: built from. In a chain these differ per row: an early Review judged a
    #: population the Analyst has since revised, so whether a missing row is a
    #: defect depends on which Review is asking, not on the newest one.
    review_id: str = ""
    review_input_gur: str = ""
    #: Bucket-level ruling, parsed out of `exact_corrections`.
    bucket: BucketInstruction = field(default_factory=lambda: BucketInstruction())
    #: Correction keys that are neither an edge column nor an instruction this
    #: build knows how to carry out. Silently absorbing one as a field write is
    #: how a Reviewer ruling gets lost, so the compiler fails on these.
    unknown_keys: tuple[str, ...] = ()

    @property
    def omits_row(self) -> bool:
        return self.disposition == REJECTED

    @property
    def holds_row(self) -> bool:
        return self.disposition == ARCHITECT_ESCALATION

    @property
    def targets_canonical_row(self) -> bool:
        """The Reviewer ruled this a repair to a named canonical row.

        Two spellings say the same thing: the flat `operation`/`canonical_row`
        pair, and a bucket instruction placing the row in `updates` against a
        named canonical row. Both are the Reviewer deciding the graph already
        holds this assertion.
        """
        if self.operation in CANONICAL_OPERATIONS and self.canonical_row is not None:
            return True
        return self.bucket.target_bucket == "updates" and self.bucket.canonical_row is not None

    @property
    def effective_canonical_row(self) -> int | None:
        if self.bucket.canonical_row is not None:
            return self.bucket.canonical_row
        return self.canonical_row

    @property
    def effective_operation(self) -> str:
        return self.operation or self.bucket.reason or CANONICAL_UPDATE

    @property
    def states_placement(self) -> bool:
        """This Review decides which bucket the row belongs in.

        Naming the buckets it was submitted in counts: a Review that lists a
        row's operations has considered its placement, even where it approves
        that placement without changing anything.
        """
        return bool(
            self.presented_operation
            or self.presented_operations
            or self.operation
            or self.canonical_row is not None
            or self.bucket.states_placement
        )

    @property
    def effective_obsolete_row(self) -> int | None:
        if self.obsolete_row is not None:
            return self.obsolete_row
        return self.bucket.obsolete_row


@dataclass(frozen=True)
class NodeDirective:
    """A Reviewer ruling on a node this patch proposes.

    `node_registry_decisions` is the node-level counterpart of `row_decisions`.
    It is where a Reviewer supplies the label a blank proposal is missing, and
    where an ordinary addition is confirmed under DEC-2026-0003. Ignoring it
    means re-shipping a defect the Reviewer already wrote the fix for.
    """

    proposed_id: str
    disposition: str
    corrections: dict[str, str]
    basis: str
    review_id: str = ""
    #: Refs the Review says depend on this identity. When the node is an
    #: Architect migration target, this is the Reviewer confirming the mapping
    #: per row, which DEC-2026-0004 requires before any repoint.
    edges: tuple[str, ...] = ()
    #: The ID the reviewed patch submitted, when the Review renames it.
    submitted_label: str = ""

    @property
    def corrected_label(self) -> str:
        return str(self.corrections.get("proposed_label") or "").strip()


def _presented_operations(row: dict) -> tuple[str, ...]:
    """The buckets the reviewed patch put this row in, as the Review records them.

    Reviews name this `submitted_operations` and write a list; the singular
    `operation` key is the older spelling. Reading only one of the two loses the
    Reviewer's account of where the row was, which is what the
    `reviewer_operation_not_preserved` check compares against.
    """
    submitted = row.get("submitted_operations")
    if isinstance(submitted, str):
        submitted = [submitted]
    operations = [str(op).strip() for op in (submitted or ()) if str(op).strip()]
    single = str(row.get("operation") or "").strip()
    if single and single not in operations:
        operations.append(single)
    return tuple(operations)


def _presented_operation(row: dict) -> str:
    """The single bucket the row was presented in, where there is exactly one.

    A row in two buckets has no single presented operation, and the checks that
    read this must not pick one of the two arbitrarily.
    """
    single = str(row.get("operation") or "").strip()
    if single:
        return single
    operations = _presented_operations(row)
    return operations[0] if len(operations) == 1 else ""


def _carry_forward(earlier: RowDirective | None, later: RowDirective) -> RowDirective:
    """Fold an earlier Review's ruling into the later one that supersedes it.

    Corrections and placement carry forward on different rules, because the two
    Reviews say different kinds of thing about them.

    *Corrections merge.* Each Review in a chain judges a patch compiled from the
    same GUR, so an earlier Review's field corrections are already in the patch
    the later Review approves. Dropping them would recompile the GUR without
    them and hand back the very defects that Review fixed -- an approval would
    undo the corrections it approves. Later wins field by field.

    *Placement does not.* A Review states which bucket every row belongs in, so
    where the later Review states a placement it is complete and replaces the
    earlier one outright. Merging instead would resurrect a canonical row number
    or a withheld field the later Review deliberately dropped. Only when the
    later Review is silent about placement does the earlier one stand.
    """
    if earlier is None:
        return later

    corrections = {**earlier.corrections, **later.corrections}
    unknown_keys = tuple(sorted(set(earlier.unknown_keys) | set(later.unknown_keys)))
    placement = later if later.states_placement else earlier
    bucket = replace(
        placement.bucket,
        field_values={**earlier.bucket.field_values, **later.bucket.field_values},
        field_corrections={
            **earlier.bucket.field_corrections,
            **later.bucket.field_corrections,
        },
        node_additions=later.bucket.node_additions or earlier.bucket.node_additions,
        unknown_keys=tuple(
            sorted(set(earlier.bucket.unknown_keys) | set(later.bucket.unknown_keys))
        ),
    )
    return replace(
        later,
        operation=placement.operation,
        canonical_row=placement.canonical_row,
        obsolete_row=placement.obsolete_row,
        corrections=corrections,
        bucket=bucket,
        unknown_keys=unknown_keys,
    )


def _policy_disposition(block: dict, directives=None, key: str = "") -> str:
    """The disposition a bulk policy block carries, normalized.

    Reviews phrase these in prose -- "approved as submitted", "approved as
    submitted except where an explicit row decision overrides it" -- so the
    text is read only far enough to confirm it is an approval. Anything that
    does not begin that way is reported rather than guessed at, because a bulk
    block covers hundreds of rows and mistaking its meaning is expensive.
    """
    text = str(block.get("disposition") or "").strip().lower()
    if text.startswith(APPROVED):
        return APPROVED
    if directives is not None:
        directives.unknown_dispositions.append(f"{key}: {block.get('disposition')!r}")
    return ""


def _policy_entries(document: dict, directives=None) -> list[dict]:
    """Per-ref rulings expanded from the row policy block, if there is one."""
    block = document.get(ROW_POLICY_KEY)
    if not isinstance(block, dict):
        return []
    disposition = _policy_disposition(block, directives, ROW_POLICY_KEY)
    if not disposition:
        return []
    return [
        {"ref": str(ref), "disposition": disposition, "rationale": block.get("rationale") or ""}
        for ref in block.get("applies_to") or []
    ]


def _ruling_entries(document: dict, directives=None) -> list[dict]:
    """Per-row rulings, from every shape a Review uses to state them.

    Three shapes are on disk. `row_decisions` and `edge_decisions` both hold a
    list of entries -- same shape, different vintage -- and six Reviews instead
    put a single mapping under `edge_decisions` that applies one disposition to
    an `approved_refs` list. Expanding the bulk form here means every consumer
    works on one shape.

    Reading only `row_decisions` meant seventeen Reviews loaded no rulings at
    all, so a revision built from one silently kept the rows the Reviewer had
    rejected while looking perfectly clean.
    """
    # Policy first: an explicit per-row ruling later in the list overwrites
    # it, which is exactly what the 'except where an explicit row decision
    # overrides it' wording asks for.
    entries: list[dict] = list(_policy_entries(document, directives))
    for key in ROW_DECISION_KEYS:
        block = document.get(key)
        if isinstance(block, dict):
            refs = block.get("approved_refs") or block.get("refs") or []
            if not refs and directives is not None:
                directives.unread_decision_keys.append(key)
                continue
            shared = {
                name: value
                for name, value in block.items()
                if name not in ("approved_refs", "refs")
            }
            entries.extend({**shared, "ref": str(ref)} for ref in refs)
            continue
        for entry in block or []:
            if isinstance(entry, dict):
                entries.append(entry)
            elif directives is not None:
                directives.unread_decision_keys.append(key)
    return entries


@dataclass
class ReviewDirectives:
    review_id: str
    reviewed_gup: str
    packet_id: str
    overall_disposition: str
    #: The GUR the reviewed patch was built from. When a Review returns a packet
    #: to the Analyst, the replacement GUR is a different revision, and the
    #: Review then covers only part of the row population being compiled.
    input_gur: str = ""
    rows: dict[str, RowDirective] = field(default_factory=dict)
    #: Reviewer rulings on proposed nodes, keyed by proposed ID.
    nodes: dict[str, NodeDirective] = field(default_factory=dict)
    unknown_dispositions: list[str] = field(default_factory=list)
    #: Top-level `*_decisions` keys this loader does not read. A Review states
    #: its rulings under a key name, so an unread key is a ruling that silently
    #: does not apply -- the revision comes out looking clean while ignoring
    #: what the Reviewer asked for.
    unread_decision_keys: list[str] = field(default_factory=list)
    #: Earlier Reviews in the chain, oldest first, whose rulings are folded in.
    superseded_reviews: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "ReviewDirectives":
        path = Path(path)
        document = yaml.safe_load(path.read_text(encoding="utf-8"))

        reviewed = document.get("reviewed_gup")
        if isinstance(reviewed, dict):
            reviewed = reviewed.get("id") or reviewed.get("gup_id") or ""

        provenance = document.get("input_provenance") or {}
        input_gur = provenance.get("gur") or {}
        if isinstance(input_gur, dict):
            input_gur = input_gur.get("id") or ""

        directives = cls(
            review_id=document.get("id") or path.stem,
            reviewed_gup=reviewed or "",
            packet_id=document.get("packet_id") or "",
            overall_disposition=document.get("overall_disposition")
            or document.get("status")
            or "",
            input_gur=str(input_gur or ""),
        )

        for key in sorted(document):
            if key.endswith("_decisions") and key not in KNOWN_DECISION_KEYS:
                directives.unread_decision_keys.append(key)
            if key.endswith("_policy") and key not in KNOWN_POLICY_KEYS:
                directives.unread_decision_keys.append(key)

        for row in _ruling_entries(document, directives):
            ref = row.get("ref")
            if not ref:
                continue
            disposition = (row.get("disposition") or "").strip()
            if disposition not in DISPOSITIONS:
                directives.unknown_dispositions.append(f"{ref}: {disposition!r}")
            raw = row.get("exact_corrections") or {}
            corrections = {
                str(k): ("" if v is None else str(v))
                for k, v in raw.items()
                if k not in STRUCTURAL_KEYS
                and k not in BUCKET_KEYS
                and k != NODE_CHANGE_KEY
            }
            bucket = _parse_bucket_instruction(
                raw, row.get("submitted_operation_records")
            )
            unknown = tuple(
                sorted(
                    {
                        key
                        for key in corrections
                        if key not in COLUMNS and key not in _TOLERATED_CORRECTION_KEYS
                    }
                    | {
                        key
                        for key in bucket.unknown_keys
                        if key not in _TOLERATED_CORRECTION_KEYS
                    }
                )
            )
            directives.rows[ref] = RowDirective(
                ref=ref,
                disposition=disposition,
                corrections=corrections,
                rationale=(row.get("rationale") or "").strip(),
                integration_action=(row.get("integration_action") or "").strip(),
                canonical_rows=tuple(row.get("canonical_rows") or ()),
                operation=str(raw.get("operation") or "").strip(),
                canonical_row=_as_row_number(raw.get("canonical_row")),
                obsolete_row=_as_row_number(raw.get("obsolete_conflicting_row")),
                presented_operation=_presented_operation(row),
                presented_operations=_presented_operations(row),
                review_id=directives.review_id,
                review_input_gur=directives.input_gur,
                bucket=bucket,
                unknown_keys=unknown,
            )

        node_policy = document.get(NODE_POLICY_KEY)
        node_rulings: list[dict] = []
        if isinstance(node_policy, dict):
            disposition = _policy_disposition(node_policy, directives, NODE_POLICY_KEY)
            if disposition:
                node_rulings.extend(
                    {"proposed_id": str(node_id), "disposition": disposition}
                    for node_id in node_policy.get("applies_to") or []
                )
        node_rulings.extend(
            entry
            for key in NODE_DECISION_KEYS
            for entry in (document.get(key) or [])
            if isinstance(entry, dict)
        )
        for node in node_rulings:
            # A decision may rule on one proposal or on a group of them, as the
            # DEC-2026-0004 identity block does. Both shapes carry the same
            # instruction, so both are indexed by every ID they name.
            ids = node.get("proposed_ids") or (
                [node["proposed_id"]] if node.get("proposed_id") else []
            )
            raw = node.get("exact_corrections") or {}
            corrections = {str(k): ("" if v is None else str(v)) for k, v in raw.items()}
            for proposed_id in ids:
                directives.nodes[str(proposed_id)] = NodeDirective(
                    proposed_id=str(proposed_id),
                    disposition=(node.get("disposition") or "").strip(),
                    corrections=corrections,
                    basis=(node.get("basis") or "").strip(),
                    review_id=directives.review_id,
                    edges=tuple(str(r) for r in (node.get("edges_depending_on_it") or ())),
                    submitted_label=str(node.get("submitted_label") or "").strip(),
                )

        return directives

    @classmethod
    def load_chain(cls, paths) -> "ReviewDirectives":
        """Fold a sequence of Reviews, oldest first, into one set of directives.

        A packet can be reviewed several times. The newest Review is
        authoritative on disposition, but it states a ruling only once: having
        told the Builder in round one that a row repairs canonical row 463, the
        Reviewer writes `approved` in round two rather than repeating the row
        number. Dropping the earlier instruction would silently turn that repair
        back into an insertion, so structural instructions carry forward until a
        later Review restates them.
        """
        paths = list(paths)
        if not paths:
            raise ValueError("load_chain requires at least one Review")

        merged = cls.load(paths[0])
        for path in paths[1:]:
            later = cls.load(path)
            merged.review_id = later.review_id
            merged.reviewed_gup = later.reviewed_gup
            merged.overall_disposition = later.overall_disposition
            merged.packet_id = later.packet_id or merged.packet_id
            merged.input_gur = later.input_gur or merged.input_gur
            merged.unknown_dispositions.extend(later.unknown_dispositions)
            merged.unread_decision_keys.extend(later.unread_decision_keys)
            merged.superseded_reviews.append(merged.review_id)
            for ref, directive in later.rows.items():
                merged.rows[ref] = _carry_forward(merged.rows.get(ref), directive)
            # A node ruling is a plain override: unlike a row, it carries no
            # structural instruction that a later silence should preserve.
            merged.nodes.update(later.nodes)
        merged.superseded_reviews = [r for r in merged.superseded_reviews if r != merged.review_id]
        return merged

    def for_ref(self, ref: str) -> RowDirective | None:
        return self.rows.get(ref)
