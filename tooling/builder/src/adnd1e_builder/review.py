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
        )


def _parse_bucket_instruction(corrections: dict) -> BucketInstruction:
    """Read the `edge_changes[.bucket]` instructions out of `exact_corrections`."""
    remove_from: set[str] = set()
    target_bucket = ""
    canonical_row = None
    reason = ""
    changes: dict[str, dict[str, str]] = {}
    remove_change_fields: set[str] = set()
    differences: dict[str, dict] = {}
    field_values: dict[str, str] = {}
    node_additions: list[dict] = []

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
            if instruction.get("retain_ref") or payload is not instruction or bucket == "updates":
                target_bucket = target_bucket or bucket
            row_number = _as_row_number(payload.get("canonical_row"))
            if row_number is not None:
                canonical_row = row_number
            reason = reason or str(payload.get("reason") or "").strip()
            for field_name, delta in (payload.get("changes") or {}).items():
                if isinstance(delta, dict):
                    changes[str(field_name)] = {
                        "from": str(delta.get("canonical", "")),
                        "to": str(delta.get("patch", "")),
                    }
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


def _carry_forward(earlier: RowDirective | None, later: RowDirective) -> RowDirective:
    """Later disposition wins; earlier structural instructions survive silence.

    Only the instructions the later Review does not restate are inherited. A
    later Review that names its own operation or canonical row replaces the
    earlier one outright.
    """
    if earlier is None or later.operation or later.canonical_row is not None:
        return later
    return replace(
        later,
        operation=earlier.operation,
        canonical_row=earlier.canonical_row,
        obsolete_row=earlier.obsolete_row,
    )


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

        for row in document.get("row_decisions") or []:
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
            bucket = _parse_bucket_instruction(raw)
            unknown = tuple(
                sorted(
                    key
                    for key in corrections
                    if key not in COLUMNS and key not in _TOLERATED_CORRECTION_KEYS
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
                presented_operation=str(row.get("operation") or "").strip(),
                review_id=directives.review_id,
                review_input_gur=directives.input_gur,
                bucket=bucket,
                unknown_keys=unknown,
            )

        for node in document.get("node_registry_decisions") or []:
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
