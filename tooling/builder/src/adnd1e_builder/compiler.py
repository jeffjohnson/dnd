"""GUR -> GUP compilation.

The compiler is deterministic: identical inputs produce byte-identical outputs,
and nothing depends on conversation history. Every judgement it makes is either
a lookup in a controlled vocabulary or a rule transcribed from the constitution.

Where it cannot decide, it does not guess. Unresolved identity and ontology
questions are emitted as escalations and the patch is marked `blocked`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import direction, grain, polarity as polarity_mod
from .duplicates import CanonicalEdges, intra_patch_duplicates, self_edges
from .registry import ID_FORMAT, NodeRegistry, normalize_label, prefix_of
from .review import ReviewDirectives, RowDirective
from .governance import Governance
from .vocab import (
    ACCEPTED_GUR_CONSTITUTION_VERSIONS,
    AUTHORED_POLARITY_TYPES,
    BOOKS,
    BUILD_OWNED_FIELDS,
    COLUMNS,
    CONSTITUTION_VERSION,
    EDGE_TYPES,
    EVIDENCE_CLASSES,
    NODE_PREFIXES,
    PASS_GENERAL_RULE,
    REVIEW_FLAG_VALUES,
    STATUS_VALUES,
    SUPERSESSION_BASIS_VALUES,
)

TOOL_NAME = "adnd1e-builder"
TOOL_VERSION = "1.0.0"

REQUIRED_GUR_FIELDS = (
    "schema_version",
    "id",
    "status",
    "ruleset_id",
    "book_id",
    "source_id",
    "packet_id",
    "constitution_version",
)

REQUIRED_EDGE_FIELDS = (
    "ref",
    "source_id",
    "source_label",
    "edge_type",
    "target_id",
    "target_label",
    "aspect",
    "condition",
    "book",
    "page",
    "section",
    "evidence",
    "pass",
    "status",
    "general_rule_id",
    "supersession_basis",
    "review_flag",
)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class Finding:
    rule: str
    severity: str  # error | warning | info
    detail: str
    ref: str | None = None
    field_name: str | None = None

    def as_dict(self) -> dict:
        out = {"rule": self.rule, "severity": self.severity, "detail": self.detail}
        if self.ref:
            out["ref"] = self.ref
        if self.field_name:
            out["field"] = self.field_name
        return out


@dataclass
class CompileResult:
    gur_id: str
    gup_id: str
    packet_id: str
    rows: list[dict] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    node_additions: list[dict] = field(default_factory=list)
    updates: list[dict] = field(default_factory=list)
    rows_superseded: set[str] = field(default_factory=set)
    rows_pending: set[str] = field(default_factory=set)
    #: `(ref, bucket)` pairs a Review directed out of a bucket by name.
    rows_removed_from: set[tuple[str, str]] = field(default_factory=set)
    rejected_rows: list[dict] = field(default_factory=list)
    rejected_node_proposals: list[dict] = field(default_factory=list)
    #: Node IDs another packet minted that this packet reuses, as the GUR
    #: declares them. Not proposals: the originating packet owns the identity.
    cross_packet_dependencies: list[dict] = field(default_factory=list)
    #: Every node ID the registry held when this packet was compiled.
    canonical_node_ids: set[str] = field(default_factory=set)
    architect_overrides: list[dict] = field(default_factory=list)
    direction_findings: list[dict] = field(default_factory=list)
    resolved_escalations: list[dict] = field(default_factory=list)
    corrections_applied: list[dict] = field(default_factory=list)
    review_id: str | None = None
    duplicate_findings: list[dict] = field(default_factory=list)
    conflict_findings: list[dict] = field(default_factory=list)
    escalations: list[dict] = field(default_factory=list)
    envelope: dict = field(default_factory=dict)
    gur_checksum: str = ""
    edges_in: int = 0
    revision: int = 1
    supersedes: str | None = None

    @property
    def additions(self) -> list[dict]:
        """Rows that could be integrated as-is.

        Excludes rows emitted as updates, and rows whose endpoints depend on a
        node this patch only proposes. Every row here satisfies invariant 1, so
        the emitted CSV never contains an edge pointing at a node that does not
        exist.
        """
        held = self.rows_superseded | self.rows_pending
        return [
            r
            for r in self.rows
            if r["ref"] not in held
            and (r["ref"], "additions") not in self.rows_removed_from
        ]

    @property
    def pending_additions(self) -> list[dict]:
        """Rows blocked on an Architect ruling for a proposed node.

        A row the Reviewer placed as a repair to a named canonical row is not
        also an insertion waiting on that node: the assertion is already in the
        graph, and the proposed node only renames one of its endpoints. Emitting
        both makes one GUR candidate into two operations, which is the duplicate
        two Reviews have had to report by hand.
        """
        return [
            r
            for r in self.rows
            if r["ref"] in self.rows_pending
            and r["ref"] not in self.rows_superseded
            and (r["ref"], "pending_additions") not in self.rows_removed_from
        ]

    @property
    def _declared_awaiting_origin_ids(self) -> set[str]:
        """Cross-packet identities the GUR named, with their origin packet."""
        return {
            dependency["node_id"]
            for dependency in self.cross_packet_dependencies
            if dependency.get("state") == "awaiting_origin_packet"
        }

    @property
    def unsatisfiable_endpoints(self) -> set[str]:
        """Endpoints in pending rows that nothing in this batch will register.

        The question is answered from the corpus, not from the GUR's
        declarations. `cross_packet_candidate_targets` is how a careful Analyst
        announces this situation, and when it is present it also names the
        origin packet -- but an endpoint that is neither canonical nor proposed
        here is unsatisfiable whether or not anyone wrote that down. Keying the
        split on the declaration meant an undeclared one reached the Integrator
        as a rejection instead of a held row.
        """
        proposed = {n["proposed_id"] for n in self.node_additions}
        known = self.canonical_node_ids | proposed
        unsatisfiable = {
            endpoint
            for row in self.pending_additions
            for endpoint in (row.get("source_id"), row.get("target_id"))
            if endpoint and endpoint not in known
        }
        # A declared dependency counts even if the registry has since gained
        # the ID: the GUR says another packet owns minting it.
        return unsatisfiable | (self._declared_awaiting_origin_ids - self.canonical_node_ids)

    @property
    def blocked_additions(self) -> list[dict]:
        """Pending rows another packet has to land before these can integrate.

        Two things hold a row back and they are not interchangeable. A row
        waiting on a node *this* patch proposes travels with it: the batch that
        registers the node integrates the row. A row waiting on a node another
        packet mints cannot integrate at all until that packet does.

        INT-20260814-003 refused the psionics bundle for nine endpoints of the
        second kind. They were correctly held and correctly declared, but the
        Approved bundle merged all 203 pending rows into one CSV, so nothing
        downstream could tell the 190 safe ones from the 13 that were not.
        INT-20260815-002 then refused both magic-user bundles for three
        endpoints of the same kind that no GUR had declared at all.
        """
        blocked = self.unsatisfiable_endpoints
        if not blocked:
            return []
        return [
            row
            for row in self.pending_additions
            if {row.get("source_id"), row.get("target_id")} & blocked
        ]

    @property
    def batch_satisfiable_additions(self) -> list[dict]:
        """Pending rows the same batch registers a node for."""
        blocked = {id(row) for row in self.blocked_additions}
        return [row for row in self.pending_additions if id(row) not in blocked]

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def blocks_approval(self) -> bool:
        return bool(self.errors) or bool(self.escalations)

    @property
    def status(self) -> str:
        return "blocked" if self.blocks_approval else "proposed"

    @property
    def handoff(self) -> dict:
        """Explicit downstream handoff — contracts/WORK_QUEUES.md.

        A GUP is only Reviewer work when it is genuinely actionable. Naming the
        blocker, and the role that owns it, is what keeps a blocked patch out of
        the Reviewer queue instead of relying on a directory name.
        """
        if self.escalations:
            blocking = sorted(
                {
                    str(
                        e.get("reserved_escalation_id")
                        or e.get("id")
                        or e.get("proposed_id")
                        or e.get("kind")
                    )
                    for e in self.escalations
                }
            )
            return {
                "next_role": "architect",
                "readiness": "blocked",
                "reason": (
                    f"{len(self.escalations)} unresolved architectural question(s); "
                    f"a schema-valid patch is not an approvable one"
                ),
                "blocking_ids": blocking,
            }

        if self.errors:
            rules = sorted({f.rule for f in self.errors})
            refs = sorted({f.ref for f in self.errors if f.ref})

            # A defect that originates in the Review is the Reviewer's to repair,
            # and routing it to the Analyst sends the work to a role that cannot
            # do it: no GUR revision can supply a disposition the Review omitted
            # or spell one the Builder does not recognise. The Analyst default
            # below is right for a source-derived defect and only that.
            if rules and all(rule.startswith("review_") for rule in rules):
                return {
                    "next_role": "reviewer",
                    "readiness": "blocked",
                    "reason": (
                        f"{len(self.errors)} Review-owned defect(s) the Builder will not "
                        f"silently rewrite: {', '.join(rules)}"
                        + (f"; affected rows {', '.join(refs)}" if refs else "")
                    ),
                    "blocking_ids": [self.review_id] if self.review_id else [],
                }

            return {
                "next_role": "analyst",
                "readiness": "blocked",
                "reason": (
                    f"{len(self.errors)} validation error(s) the Builder will not silently "
                    f"rewrite: {', '.join(rules)}"
                    + (f"; affected rows {', '.join(refs)}" if refs else "")
                ),
                # The artifact whose revision unblocks this, which is the GUR.
                # Candidate-edge refs went here once, and they are neither an
                # escalation nor an artifact: no Decision can ever resolve an
                # `M003`, so the queue scanner had a permanently unresolvable
                # blocker and the packet sat waiting on nothing nameable. The
                # refs are not lost -- every finding carries its own, and they
                # are listed in the reason.
                "blocking_ids": [self.gur_id] if self.gur_id else [],
            }

        return {
            "next_role": "reviewer",
            "readiness": "ready",
            "reason": (
                f"compiled clean: {len(self.additions)} edge addition(s), "
                f"{len(self.updates)} update(s), {len(self.pending_additions)} pending a "
                f"registry addition"
            ),
            "blocking_ids": [],
        }


class Compiler:
    def __init__(
        self,
        registry: NodeRegistry,
        canonical: CanonicalEdges,
        general_rules: dict | None = None,
        governance: Governance | None = None,
    ) -> None:
        self.registry = registry
        self.canonical = canonical
        self.general_rules = general_rules or {}
        self.governance = governance or Governance()

    # -- envelope ------------------------------------------------------------
    def _check_envelope(self, gur: dict, result: CompileResult) -> None:
        for field_name in REQUIRED_GUR_FIELDS:
            if not gur.get(field_name):
                result.findings.append(
                    Finding(
                        "gur_envelope_incomplete",
                        "error",
                        f"GUR is missing required envelope field {field_name!r}",
                        field_name=field_name,
                    )
                )
        if gur.get("ruleset_id") not in (None, "adnd1e"):
            result.findings.append(
                Finding(
                    "gur_wrong_ruleset",
                    "error",
                    f"ruleset_id {gur.get('ruleset_id')!r} is not adnd1e; "
                    f"SCOPE_AND_IDENTITY forbids silently moving artifacts between rulesets",
                )
            )
        declared = str(gur.get("constitution_version") or "")
        if declared and declared != CONSTITUTION_VERSION:
            if declared in ACCEPTED_GUR_CONSTITUTION_VERSIONS:
                result.findings.append(
                    Finding(
                        "constitution_version_older_than_compiler",
                        "warning",
                        f"GUR was authored under constitution {declared} and is revalidated under "
                        f"{CONSTITUTION_VERSION}, not trusted on its declared version. "
                        f"{CONSTITUTION_VERSION} is not purely permissive over {declared}: it fixes "
                        f"citation cardinality at one locus per edge (DEC-2026-0008) and settles "
                        f"MODIFIES vs DERIVED_FROM for table lookups (DEC-2026-0011). Rows that "
                        f"were valid under {declared} may fail here.",
                    )
                )
            else:
                result.findings.append(
                    Finding(
                        "constitution_version_mismatch",
                        "error",
                        f"GUR declares constitution {declared}; compiler implements "
                        f"{CONSTITUTION_VERSION} and accepts "
                        f"{sorted(ACCEPTED_GUR_CONSTITUTION_VERSIONS)}",
                    )
                )

    # -- nodes ---------------------------------------------------------------
    def _register_migration_node(
        self, node_id: str, replaces_id: str, ref: str, result: CompileResult
    ) -> None:
        """Record the registry addition an authorized identity migration needs.

        The Architect fixed the mapping and the Reviewer confirms it per row, but
        neither writes `nodes.csv`. The new ID therefore has to travel with the
        patch as a proposed addition so the Integrator has something to apply,
        and so the edge depending on it is visibly pending rather than silently
        pointing at a node that does not exist.
        """
        existing = next(
            (n for n in result.node_additions if n["proposed_id"] == node_id), None
        )
        if existing is not None:
            if ref not in existing["edges_depending_on_it"]:
                existing["edges_depending_on_it"].append(ref)
            return

        old = self.registry.nodes.get(replaces_id)
        decision_id = self.governance.migration_source.get(replaces_id, "")
        result.node_additions.append(
            {
                "proposed_id": node_id,
                "proposed_label": old.label if old else "",
                "kind": (prefix_of(node_id) or "").rstrip("_"),
                "why_needed": (
                    f"{decision_id or 'An Architect decision'} rejects the prefix of "
                    f"{replaces_id!r} and names {node_id!r} as its replacement."
                ),
                "edges_depending_on_it": [ref],
                "prefix_approved": prefix_of(node_id) is not None,
                "id_format_valid": bool(ID_FORMAT.match(node_id)),
                "already_canonical": False,
                "label_collides_with": [],
                "architect_required": False,
                "disposition": "authorized_migration",
                "carried_forward": False,
                "first_proposed_in": None,
                "replaces_canonical_id": replaces_id,
                "authority": decision_id,
            }
        )

    def _endpoint_label(
        self, node_id: str, edge: dict, role: str, result: CompileResult | None = None
    ) -> str:
        """The label to write for an endpoint.

        The registry is the normal authority, which is what keeps one node from
        appearing under several spellings. It is not the authority when the
        Architect has relabelled the node and the Integrator has not applied it
        yet: the registry is then simply out of date, and normalizing to it
        would reintroduce the label the decision replaced on every row that
        touches the node. A node this patch only proposes has no registry entry,
        so the edge's own label stands.
        """
        ruled = self.governance.approved_label(node_id)
        if ruled:
            return ruled[0]
        if node_id in self.registry:
            return self.registry.nodes[node_id].label
        if result is not None:
            # A node this patch proposes has no registry entry yet, so the
            # proposal is its label -- including any correction the Reviewer
            # made to it. Falling through to the edge's own value would let a
            # row disagree with the node it depends on inside one bundle.
            proposed = next(
                (n for n in result.node_additions if n["proposed_id"] == node_id), None
            )
            if proposed and proposed.get("proposed_label"):
                return str(proposed["proposed_label"])
        return (edge.get(f"{role}_label") or "").strip()

    def _prune_rejected_dependents(
        self,
        directives: "ReviewDirectives",
        candidate_edges: list[dict],
        result: CompileResult,
    ) -> None:
        """Drop rejected rows from the `edges_depending_on_it` of surviving nodes.

        A node proposal lists the rows that need it, and a Reviewer reads that
        list to judge whether the node earns its registration. When the Review
        rejects a row but keeps the node -- because other rows still need it --
        the list kept advertising the rejected row, so the proposal overstated
        its own support by exactly the rows the Reviewer had just removed.

        `_drop_reviewer_rejected_nodes` already computed a surviving set, but it
        returns early unless some *node* was rejected, so a row-only rejection
        never reached it. That is how M067 survived in `rule_chivalric_code` on
        the cavalier packet after the Review rejected it.
        """

        rejected_refs = {
            ref
            for ref, ruling in directives.rows.items()
            if ruling.disposition == "rejected"
        }
        if not rejected_refs:
            return

        for addition in result.node_additions:
            depending = addition.get("edges_depending_on_it") or []
            kept = [ref for ref in depending if ref not in rejected_refs]
            if len(kept) == len(depending):
                continue
            dropped = [ref for ref in depending if ref in rejected_refs]
            addition["edges_depending_on_it"] = kept
            result.findings.append(
                Finding(
                    "node_dependent_row_rejected",
                    "info",
                    f"{', '.join(dropped)} removed from the rows depending on proposed node "
                    f"{addition['proposed_id']!r}: "
                    f"{directives.review_id or 'the Review'} rejected "
                    f"{'them' if len(dropped) > 1 else 'it'}. "
                    f"{len(kept)} row(s) still require this node.",
                )
            )

    def _drop_reviewer_rejected_nodes(
        self, directives: ReviewDirectives, candidate_edges: list, result: CompileResult
    ) -> None:
        """Remove proposals the Review rejected.

        A rejected proposal used to stay in the patch carrying only a recorded
        disposition, so the next revision still asked the Integrator to register
        it. With its only edge rejected too, that registers a node at degree
        zero -- the defect the Integrator refused the alignment-graph bundle
        for. REV-GUP-PKT-PHB-120-120-planes-of-existence-r05-r01 is the same
        shape: `rule_prime_material_plane` is rejected because its only edge is.

        A rejected proposal that some surviving row still points at is a
        different situation and an error: dropping it would strand that row
        against an unregistered endpoint, so the Reviewer is told rather than
        the conflict being resolved here.
        """
        rejected = {
            proposed_id
            for proposed_id, directive in directives.nodes.items()
            if directive.disposition == "rejected"
        }
        if not rejected:
            return

        surviving = {
            edge.get("ref")
            for edge in candidate_edges
            if (ruling := directives.rows.get(edge.get("ref"))) is None
            or ruling.disposition != "rejected"
        }
        kept = []
        for addition in result.node_additions:
            proposed_id = addition["proposed_id"]
            if proposed_id not in rejected:
                kept.append(addition)
                continue
            depending = sorted(
                ref for ref in addition.get("edges_depending_on_it") or [] if ref in surviving
            )
            if depending:
                kept.append(addition)
                result.findings.append(
                    Finding(
                        "reviewer_rejected_node_still_needed",
                        "error",
                        f"{directives.review_id or 'the Review'} rejects proposed node "
                        f"{proposed_id!r}, but {', '.join(depending)} still depend(s) on it. "
                        f"Dropping it would leave those rows pointing at an unregistered "
                        f"endpoint.",
                    )
                )
                continue
            result.findings.append(
                Finding(
                    "reviewer_rejected_node_dropped",
                    "info",
                    f"proposed node {proposed_id!r} is withdrawn: "
                    f"{directives.review_id or 'the Review'} rejected it and no surviving row "
                    f"depends on it.",
                )
            )
        result.node_additions[:] = kept

    def _apply_node_directives(
        self, directives: ReviewDirectives, result: CompileResult
    ) -> None:
        """Apply Reviewer rulings on proposed nodes.

        The label of a proposed node is a reading of the source, so the Reviewer
        owns it exactly as they own an edge's aspect. A blank label that a
        Review has already corrected must not survive into the next revision --
        that is the defect two Reviews reported by hand for
        `rule_prime_requisite`.
        """
        for addition in result.node_additions:
            directive = directives.nodes.get(addition["proposed_id"])
            if directive is None:
                continue
            addition["reviewer_disposition"] = directive.disposition
            addition["reviewer_basis"] = directive.basis
            integration_action = directive.corrections.get("integration_action", "").strip()
            if integration_action:
                addition["integration_action"] = integration_action

            label = directive.corrected_label
            if not label or label == addition.get("proposed_label"):
                continue
            previous = addition.get("proposed_label") or ""
            addition["proposed_label"] = label
            result.findings.append(
                Finding(
                    "reviewer_corrected_node_label",
                    "info",
                    f"proposed node {addition['proposed_id']!r} takes label {label!r} from "
                    f"{directive.review_id}"
                    + (f", replacing {previous!r}" if previous else ", which the proposal left blank")
                    + ".",
                )
            )

        # A label the Reviewer supplied is only applied if the proposal is still
        # in the patch. One that is not tells the Reviewer their correction went
        # nowhere, rather than silently doing nothing.
        proposed = {n["proposed_id"] for n in result.node_additions}
        for proposed_id, directive in sorted(directives.nodes.items()):
            if proposed_id in proposed or not directive.corrected_label:
                continue
            result.findings.append(
                Finding(
                    "reviewer_node_correction_unused",
                    "info",
                    f"{directive.review_id} corrects the label of proposed node "
                    f"{proposed_id!r}, which this revision no longer proposes.",
                )
            )

    def _reviewer_approved_repoints(
        self, directives: ReviewDirectives, candidate_edges: list, result: CompileResult
    ) -> dict[str, str]:
        """Legacy endpoint IDs the Review has cleared for their migration target.

        DEC-2026-0004 fixed the mapping but withheld the repoint until a Reviewer
        confirms identity, label and neighbourhood *per node*. A
        `node_registry_decisions` entry naming a migration target, with the edges
        that depend on it, is that confirmation. Until it exists the edge keeps
        the legacy ID and only carries a pending-migration warning.

        Returns legacy ID -> approved replacement.
        """
        approved: dict[str, str] = {}
        live_refs = {e.get("ref") for e in candidate_edges}
        for proposed_id, node_directive in sorted(directives.nodes.items()):
            origin = self.governance.migration_origin(proposed_id)
            if origin is None or origin not in self.registry:
                continue
            if node_directive.disposition == "rejected":
                continue
            confirmed = [ref for ref in node_directive.edges if ref in live_refs]
            if not confirmed:
                continue
            approved[origin] = proposed_id
            self._register_migration_node(proposed_id, origin, confirmed[0], result)
            for ref in confirmed[1:]:
                entry = next(
                    n for n in result.node_additions if n["proposed_id"] == proposed_id
                )
                if ref not in entry["edges_depending_on_it"]:
                    entry["edges_depending_on_it"].append(ref)
            result.findings.append(
                Finding(
                    "reviewer_approved_identity_migration",
                    "info",
                    f"{node_directive.review_id or 'the Review'} confirms "
                    f"{origin!r} becomes {proposed_id!r} for {', '.join(confirmed)} "
                    f"({self.governance.migration_source.get(origin, 'an Architect decision')}). "
                    f"Those endpoints are repointed and held pending registration.",
                )
            )
        return approved

    def _register_reviewer_directed_nodes(
        self, directives: ReviewDirectives, candidate_edges: list, result: CompileResult
    ) -> None:
        """Register nodes a Review introduces by repointing an endpoint.

        Deciding that a source names a spell family rather than one spell is an
        identity judgement, and the Reviewer is the role that makes it against
        the source. When that judgement lands as an exact correction the target
        ID may not exist yet, and the row would otherwise fail invariant 1 as an
        unresolved endpoint -- reporting the Reviewer's own ruling as a defect.

        The node is proposed rather than assumed: it travels in the patch, the
        row waits on it, and the Integrator writes the registry. Format and
        prefix are still checked here, because a Reviewer may not widen the
        ontology any more than an Analyst may.
        """
        live_refs = {e.get("ref") for e in candidate_edges}
        for ref in sorted(live_refs & set(directives.rows)):
            directive = directives.rows[ref]
            if directive.omits_row or directive.holds_row:
                continue

            # A Review may supply a complete node-addition entry rather than
            # just an ID -- typically restoring a proposal an earlier revision
            # dropped. The entry is the Reviewer's, so it is carried as
            # authored; only its identity fields are re-checked below.
            for entry in directive.bucket.node_additions:
                node_id = str(entry.get("proposed_id") or "").strip()
                if not node_id or node_id in self.registry:
                    continue
                existing = next(
                    (n for n in result.node_additions if n["proposed_id"] == node_id), None
                )
                if existing is not None:
                    if ref not in existing["edges_depending_on_it"]:
                        existing["edges_depending_on_it"].append(ref)
                    continue
                carried = dict(entry)
                carried.setdefault("edges_depending_on_it", [])
                if ref not in carried["edges_depending_on_it"]:
                    carried["edges_depending_on_it"].append(ref)
                carried["prefix_approved"] = prefix_of(node_id) is not None
                carried["id_format_valid"] = bool(ID_FORMAT.match(node_id))
                carried["already_canonical"] = False
                result.node_additions.append(carried)
                result.findings.append(
                    Finding(
                        "reviewer_supplied_node_addition",
                        "info",
                        f"{ref}: {directives.review_id} supplies the node proposal "
                        f"{node_id!r} for this patch to carry"
                        + (f": {directive.rationale}" if directive.rationale else "")
                        + ".",
                        ref=ref,
                    )
                )
                if not carried["prefix_approved"] or not carried["id_format_valid"]:
                    result.findings.append(
                        Finding(
                            "node_prefix_unapproved",
                            "error",
                            f"{directives.review_id} supplies node {node_id!r}, which is not a "
                            f"valid ID under an approved prefix (constitution 3.1). A Review may "
                            f"rule on identity, not widen the ontology.",
                            ref=ref,
                        )
                    )

            for field_name in ("source_id", "target_id"):
                node_id = str(directive.corrections.get(field_name) or "").strip()
                if not node_id or node_id in self.registry:
                    continue
                existing = next(
                    (n for n in result.node_additions if n["proposed_id"] == node_id), None
                )
                if existing is not None:
                    if ref not in existing["edges_depending_on_it"]:
                        existing["edges_depending_on_it"].append(ref)
                    continue

                # An Architect decision may already have named this ID as the
                # replacement for a rejected-prefix node. Then the Reviewer is
                # applying a ruling rather than minting anything, and the label
                # and provenance belong to the legacy node -- which is where a
                # blank `proposed_label` would otherwise come from.
                origin = self.governance.migration_origin(node_id)
                if origin and origin in self.registry:
                    self._register_migration_node(node_id, origin, ref, result)
                    continue

                label_field = field_name.replace("_id", "_label")
                prefix_ok = prefix_of(node_id) is not None
                format_ok = bool(ID_FORMAT.match(node_id))
                result.node_additions.append(
                    {
                        "proposed_id": node_id,
                        "proposed_label": str(
                            directive.corrections.get(label_field) or ""
                        ).strip(),
                        "kind": (prefix_of(node_id) or "").rstrip("_"),
                        "why_needed": (
                            f"{directive.review_id or directives.review_id} repointed {ref} here"
                            + (f": {directive.rationale}" if directive.rationale else "")
                        ),
                        "edges_depending_on_it": [ref],
                        "prefix_approved": prefix_ok,
                        "id_format_valid": format_ok,
                        "already_canonical": False,
                        "label_collides_with": sorted(
                            self.registry.label_collisions(
                                node_id, str(directive.corrections.get(label_field) or "")
                            )
                        ),
                        "architect_required": False,
                        "disposition": "reviewer_directed",
                        "carried_forward": False,
                        "first_proposed_in": None,
                        "authority": directive.review_id or directives.review_id,
                    }
                )
                if not prefix_ok:
                    result.findings.append(
                        Finding(
                            "node_prefix_unapproved",
                            "error",
                            f"{directives.review_id} repoints {ref} at {node_id!r}, which uses no "
                            f"approved prefix (constitution 3.1). A Review may rule on identity, "
                            f"not widen the ontology.",
                            ref=ref,
                            field_name=field_name,
                        )
                    )
                if not format_ok:
                    result.findings.append(
                        Finding(
                            "node_id_format_invalid",
                            "error",
                            f"{directives.review_id} repoints {ref} at {node_id!r}, which is not a "
                            f"valid node ID (constitution 3.1)",
                            ref=ref,
                            field_name=field_name,
                        )
                    )
                if prefix_ok and format_ok:
                    result.findings.append(
                        Finding(
                            "reviewer_directed_node_addition",
                            "info",
                            f"{directives.review_id} repoints {ref} at {node_id!r}, which is not yet "
                            f"canonical. Proposed as a node addition; the row waits on it and the "
                            f"Integrator applies the registry change first (DEC-2026-0003).",
                            ref=ref,
                            field_name=field_name,
                        )
                    )

    def _resolve_endpoint(self, edge: dict, role: str, result: CompileResult) -> str | None:
        node_id = (edge.get(f"{role}_id") or "").strip()
        label = (edge.get(f"{role}_label") or "").strip()
        ref = edge.get("ref")
        proposed = {n["proposed_id"] for n in result.node_additions}

        rejected = self.governance.rejected_identity(node_id)
        if rejected:
            # The Architect refused this identity and named the ID to use
            # instead. The edge may not enter the patch until it is repointed.
            result.findings.append(
                Finding(
                    "endpoint_uses_rejected_identity",
                    "error",
                    f"{role}_id {node_id!r} was rejected by {rejected['decision_id']}"
                    + (f" ({rejected['disposition']})" if rejected.get("disposition") else "")
                    + f". Use {rejected['replacement_id']!r}. The edge cannot enter a GUP until it "
                    f"is repointed.",
                    ref=ref,
                    field_name=f"{role}_id",
                )
            )
            return None

        # DEC-2026-0004 rejected some prefixes and slated those IDs for a
        # reviewed migration. Such a node still resolves, so this must be checked
        # before the exact-match path returns.
        # DEC-2026-0050. Three legacy IDs are due, not merely proposed: their
        # replacements were already decided by DEC-2026-0004 and DEC-2026-0014,
        # and the debt they belong to is meant to shrink. Warning was not enough.
        # The cavalier packet disclosed the tension, this compiler warned on every
        # affected row, the Reviewer approved them and the Integrator applied
        # them -- and four rows joined a set an approved Decision had pinned. A
        # warning that four gates read and none acted on is a warning in the
        # wrong severity, so for this exactly-named set the row is refused.
        #
        # The row is never rewritten to the successor. Repointing a source
        # assertion is the migration's job, under review; doing it silently here
        # would be the Builder deciding identity.
        due = self.governance.migration_due(node_id)
        if due:
            successor, decision_id = due
            result.findings.append(
                Finding(
                    "endpoint_migration_due",
                    "error",
                    f"{role}_id {node_id!r} has a due identity migration: {decision_id} "
                    f"replaces it with {successor!r}. New ordinary work may not use it, and "
                    f"the Builder will not rewrite the row -- that repoint belongs to the "
                    f"reviewed migration. Re-raise this assertion against {successor!r} once "
                    f"the migration integrates, or escalate if the source means something "
                    f"other than {successor!r}.",
                    ref=ref,
                    field_name=f"{role}_id",
                )
            )
            return None

        migration_target = self.governance.migration_target(node_id)
        if migration_target and node_id in self.registry:
            result.findings.append(
                Finding(
                    "endpoint_pending_migration",
                    "warning",
                    f"{role}_id {node_id!r} uses a prefix rejected by "
                    f"{self.governance.migration_source.get(node_id, 'an Architect decision')} and "
                    f"is slated to become {migration_target!r}. The edge resolves today; it will "
                    f"need repointing when the migration is approved.",
                    ref=ref,
                    field_name=f"{role}_id",
                )
            )

        resolution = self.registry.resolve(node_id, label)

        # An ID the Integrator has recorded as retired into a surviving one is
        # repointed here, before any other handling. This is not the label
        # merge invariant 4 forbids: the mapping comes from the Integration
        # manifest that applied the migration, named by authority Decision and
        # integration ID, and it is reported on every row it touches so a
        # Reviewer sees the substitution rather than discovering it in a diff.
        #
        # A GUR is immutable and is authored against the registry of its day. If
        # the merge it anticipated integrates before the GUP is compiled -- which
        # is exactly what DEC-2026-0038 and INT-20260818-001 did to this
        # packet's `str_exceptional` -- then without this the row cannot compile
        # at all, and the Builder would escalate a question the repository has
        # already answered in writing.
        if resolution.method == "retired_replacement":
            survivor = resolution.resolved_id
            edge[f"{role}_id"] = survivor
            canonical_label = self.registry.nodes[survivor].label
            if canonical_label:
                edge[f"{role}_label"] = canonical_label
            result.findings.append(
                Finding(
                    "endpoint_repointed_to_merge_survivor",
                    "info",
                    f"{role}_id {node_id!r} was retired into {survivor!r} by "
                    f"{resolution.retirement_integration_id or 'an integration'} under "
                    f"{resolution.retirement_authority or 'an approved Decision'}; the row is "
                    f"repointed to the surviving identity. The GUR predates that integration "
                    f"and remains immutable.",
                    ref=ref,
                    field_name=f"{role}_id",
                )
            )
            return survivor

        if resolution.method == "exact":
            canonical_label = self.registry.nodes[node_id].label
            ruled = self.governance.approved_label(node_id)
            if ruled and ruled[0] != canonical_label:
                # The Architect relabelled this node and the Integrator has not
                # applied it yet. Normalizing to the registry here would undo
                # the ruling on every row that touches the node.
                canonical_label = ruled[0]
                edge[f"{role}_label"] = canonical_label
                result.findings.append(
                    Finding(
                        "endpoint_label_from_decision",
                        "info",
                        f"{role}_label for {node_id} set to {canonical_label!r} by {ruled[1]}, "
                        f"which the registry has not yet been updated to carry.",
                        ref=ref,
                        field_name=f"{role}_label",
                    )
                )
                return node_id
            if label and canonical_label and label.strip().lower() != canonical_label.lower():
                result.findings.append(
                    Finding(
                        "label_normalized",
                        "info",
                        f"{role}_label {label!r} normalized to registry label {canonical_label!r} "
                        f"for {node_id}; identity is unchanged",
                        ref=ref,
                        field_name=f"{role}_label",
                    )
                )
            return node_id

        if node_id in proposed:
            # Depends on a node this patch proposes. Held out of the integrable
            # set because invariant 1 is not satisfied until the registry change
            # is applied, but not a defect: the addition rides in this same GUP.
            result.rows_pending.add(ref)
            addition = next(
                (n for n in result.node_additions if n["proposed_id"] == node_id), None
            )
            # The proposal lists what depends on it so the Reviewer and
            # Integrator can see the blast radius of approving the node. A
            # second edge reaching the same proposal has to be recorded there
            # too, or the list understates the dependency.
            if addition is not None and ref not in addition.setdefault(
                "edges_depending_on_it", []
            ):
                addition["edges_depending_on_it"].append(ref)
            architect_required = bool(addition and addition.get("architect_required"))
            result.findings.append(
                Finding(
                    "endpoint_pending_registry_addition",
                    "error" if architect_required else "info",
                    f"{role}_id {node_id!r} is not yet canonical; it is proposed by this patch. "
                    + (
                        "The proposal needs an Architect decision, so this edge cannot proceed."
                        if architect_required
                        else "The Reviewer may approve the node change and this edge together "
                        "(DEC-2026-0003); the Integrator applies the registry change first."
                    ),
                    ref=ref,
                    field_name=f"{role}_id",
                )
            )
            return node_id

        if self.governance.migration_target(resolution.resolved_id or "") == node_id:
            # Not a label merge. The Architect named this exact ID as the
            # replacement for the canonical node the label matched, so the
            # mapping comes from the decision and the label agreement is only
            # corroboration that the right node is being repointed. Invariant 4
            # bars the Builder from *inventing* an identity, not from applying
            # one already ruled. The node still does not exist yet, so the row
            # is held out of the integrable set exactly like any other pending
            # addition: the Integrator writes nodes.csv first.
            self._register_migration_node(node_id, resolution.resolved_id, ref, result)
            result.rows_pending.add(ref)
            result.findings.append(
                Finding(
                    "endpoint_authorized_migration_target",
                    "info",
                    f"{role}_id {node_id!r} is the migration target "
                    f"{self.governance.migration_source.get(resolution.resolved_id, 'an Architect decision')} "
                    f"names for canonical {resolution.resolved_id!r}. Carried as a pending addition "
                    f"until the Integrator registers the node.",
                    ref=ref,
                    field_name=f"{role}_id",
                )
            )
            return node_id

        dependency = next(
            (
                d
                for d in result.cross_packet_dependencies
                if d["node_id"] == node_id and d["state"] == "awaiting_origin_packet"
            ),
            None,
        )
        if dependency is not None:
            # The GUR named the packet this identity comes from. The row is held
            # exactly like one depending on a node this patch proposes: it is
            # not integrable until the origin packet's node is registered, and
            # it is not a defect. Where the label also matches an existing
            # canonical node, that stays visible here -- the question of whether
            # the two are the same concept belongs to the packet that minted the
            # identity, and is not answered by silently merging them (invariant 4).
            result.rows_pending.add(ref)
            # The Analyst puts the label on the declaration rather than on each
            # edge, because the identity is minted elsewhere and one declaration
            # serves every row that reaches it. Carrying it onto the row is not
            # inventing a label: it is the label declared for this exact ID. Not
            # carrying it emitted `target_label` empty, which fails the edge
            # schema -- two such rows reached an Approved bundle.
            if not label and dependency["label"]:
                edge[f"{role}_label"] = dependency["label"]
                result.findings.append(
                    Finding(
                        "endpoint_label_from_cross_packet_declaration",
                        "info",
                        f"{role}_label for {node_id} taken from the GUR's cross-packet "
                        f"declaration, which carries {dependency['label']!r}. The edge left it "
                        f"empty because the identity is minted in another packet.",
                        ref=ref,
                        field_name=f"{role}_label",
                    )
                )
            collision = (
                f" Label {label!r} also matches canonical {resolution.resolved_id!r}; that "
                f"identity question belongs to the proposal in the origin packet, so this "
                f"patch neither merges nor re-proposes it."
                if resolution.method == "normalized_label"
                else ""
            )
            result.findings.append(
                Finding(
                    "endpoint_pending_cross_packet_candidate",
                    "info",
                    f"{role}_id {node_id!r} is a candidate minted elsewhere and declared by the "
                    f"GUR as a cross-packet target ({dependency['origin'] or 'origin unrecorded'}). "
                    f"The row is held pending until that node is registered." + collision,
                    ref=ref,
                    field_name=f"{role}_id",
                )
            )
            return node_id

        if resolution.method == "normalized_label":
            result.findings.append(
                Finding(
                    "identity_ambiguous",
                    "error",
                    f"{role}_id {node_id!r} is not in the registry, but label {label!r} matches "
                    f"canonical {resolution.resolved_id!r}. Builder does not merge identity by "
                    f"label (invariant 4); escalated.",
                    ref=ref,
                    field_name=f"{role}_id",
                )
            )
            result.escalations.append(
                {
                    "kind": "identity_resolution",
                    "ref": ref,
                    "requested_id": node_id,
                    "label": label,
                    "candidate_canonical_id": resolution.resolved_id,
                    "question": (
                        f"Is {node_id!r} the same concept as canonical {resolution.resolved_id!r}, "
                        f"or a distinct node requiring registration?"
                    ),
                }
            )
            return None

        if resolution.ambiguous_with:
            result.escalations.append(
                {
                    "kind": "identity_ambiguous",
                    "ref": ref,
                    "requested_id": node_id,
                    "label": label,
                    "candidates": list(resolution.ambiguous_with),
                    "question": f"Label {label!r} matches several canonical nodes; which is meant?",
                }
            )

        result.findings.append(
            Finding(
                "endpoint_unresolved",
                "error",
                f"{role}_id {node_id!r} does not resolve to a canonical node and is not "
                f"proposed by this patch (invariant 1)",
                ref=ref,
                field_name=f"{role}_id",
            )
        )
        return None

    def _record_cross_packet_targets(self, gur: dict, result: CompileResult) -> None:
        """Node identities another packet minted that this packet reuses.

        A book is not a partition. The illusionist list points at magic-user
        spells, the magic-user list points at druid spells, and three packets
        reach the same death rule. The Analyst declares each such endpoint in
        `cross_packet_candidate_targets`, naming the GUR that minted it and
        instructing the Builder not to mint a second identity for it.

        Builder honours that by holding the dependent row out of the integrable
        set until the originating packet's node is registered -- the same
        treatment a row gets when it depends on a node *this* patch proposes.
        What it must not do is either of the alternatives: minting a duplicate
        identity, or rejecting the edge as unresolvable when the Analyst has
        already said where the identity comes from.

        These are recorded as dependencies, not as node additions. The packet
        that minted the identity owns the proposal, and asking the Integrator
        to register the same node from two GUPs would be the double
        registration the declaration exists to prevent.
        """
        also_proposed_here = {
            (c.get("proposed_id") or "").strip() for c in (gur.get("candidate_nodes") or [])
        }
        for target in gur.get("cross_packet_candidate_targets") or []:
            node_id = (target.get("id") or "").strip()
            if not node_id:
                continue
            if node_id in self.registry:
                state = "already_canonical"
            elif node_id in also_proposed_here:
                state = "proposed_by_this_packet"
            else:
                state = "awaiting_origin_packet"
            result.cross_packet_dependencies.append(
                {
                    "node_id": node_id,
                    "label": (target.get("label") or "").strip(),
                    "origin": (target.get("origin") or "").strip(),
                    "used_by": list(target.get("used_by") or []),
                    "state": state,
                    "builder_instruction": (target.get("builder_instruction") or "").strip(),
                }
            )
        result.cross_packet_dependencies.sort(key=lambda d: d["node_id"])

    def _compile_node_additions(self, gur: dict, result: CompileResult) -> None:
        """Proposed registry changes, isolated from edge insertions (instruction 13)."""
        self._record_cross_packet_targets(gur, result)

        # A candidate first proposed by an earlier packet and still awaiting a
        # ruling is carried forward rather than re-proposed. It is pending, not
        # unknown, and its dependent edges must say so.
        for carried in gur.get("carried_forward_candidates") or []:
            node_id = (carried.get("id") or "").strip()
            if not node_id or node_id in self.registry:
                continue
            held = self.governance.held_by_package(node_id)
            architect_required = (
                prefix_of(node_id) is None or not ID_FORMAT.match(node_id) or held is not None
            )
            result.node_additions.append(
                {
                    "proposed_id": node_id,
                    "proposed_label": "",
                    "kind": (prefix_of(node_id) or "").rstrip("_"),
                    "why_needed": (carried.get("note") or "").strip(),
                    "edges_depending_on_it": list(carried.get("edges_here") or []),
                    "prefix_approved": prefix_of(node_id) is not None,
                    "id_format_valid": bool(ID_FORMAT.match(node_id)),
                    "already_canonical": False,
                    "label_collides_with": [],
                    "architect_required": architect_required,
                    "disposition": (
                        "requires_architect_decision"
                        if architect_required
                        else "reviewer_may_approve"
                    ),
                    "carried_forward": True,
                    "first_proposed_in": carried.get("first_proposed_in"),
                    "returned_to_workflow_by": self.governance.nodes_returned_to_workflow.get(
                        node_id
                    ),
                    "routing_basis": (
                        f"held by {held['reserved_escalation_id']} ({held.get('topic')}), owner "
                        f"{held.get('package_owner')}"
                        if held
                        else f"returned to normal workflow by "
                        f"{self.governance.nodes_returned_to_workflow[node_id]}"
                        if self.governance.is_returned_to_workflow(node_id)
                        else "DEC-2026-0003: approved prefix and kind, valid ID, no duplicate"
                        if not architect_required
                        else "fails an identity or ontology precondition"
                    ),
                }
            )
            if not architect_required:
                result.findings.append(
                    Finding(
                        "node_addition_normal_workflow",
                        "info",
                        f"proposed node {node_id!r}, carried forward from "
                        f"{carried.get('first_proposed_in')}, is isolated in node_changes for "
                        f"Reviewer approval per DEC-2026-0003.",
                    )
                )
                continue
            result.escalations.append(
                {
                    "kind": "node_registration_carried_forward",
                    "proposed_id": node_id,
                    "first_proposed_in": carried.get("first_proposed_in"),
                    "question": (
                        f"{node_id!r} was proposed by an earlier packet and remains an open "
                        f"architectural question; edges in this packet depend on it."
                    ),
                    "edges_depending_on_it": list(carried.get("edges_here") or []),
                }
            )

        for candidate in gur.get("candidate_nodes") or []:
            proposed_id = (candidate.get("proposed_id") or "").strip()
            label = (candidate.get("proposed_label") or "").strip()

            rejected = self.governance.rejected_identity(proposed_id)
            if rejected:
                # Already decided: the Architect refused this identity. It is not
                # a pending proposal and not an open escalation.
                result.rejected_node_proposals.append(
                    {
                        "proposed_id": proposed_id,
                        "proposed_label": label,
                        "rejected_by": rejected["decision_id"],
                        "disposition": rejected.get("disposition"),
                        "replacement_id": rejected["replacement_id"],
                        "edges_depending_on_it": list(candidate.get("edges_depending_on_it") or []),
                    }
                )
                result.findings.append(
                    Finding(
                        "node_proposal_rejected_by_decision",
                        "warning",
                        f"proposed node {proposed_id!r} was rejected by "
                        f"{rejected['decision_id']}; {rejected['replacement_id']!r} is the "
                        f"replacement identity. Not carried as a registry addition.",
                    )
                )
                continue

            if proposed_id in self.registry:
                canonical_label = self.registry.nodes[proposed_id].label
                if not label or normalize_label(label) == normalize_label(canonical_label):
                    # Same ID, same label. An earlier packet proposed this node
                    # and it has since been registered; the Analyst, reading the
                    # source rather than the registry, proposed it again. There
                    # is nothing to add and nothing to decide -- constitution 3.2
                    # says reuse it, and the ID is the identity (invariant 4), so
                    # the endpoints already resolve against the registry. Asking
                    # the Architect whether to add a node that is present, under
                    # the name it is present under, would block the packet on a
                    # question with one answer.
                    result.findings.append(
                        Finding(
                            "node_proposal_resolved_to_canonical",
                            "info",
                            f"proposed node {proposed_id!r} is already canonical under the same "
                            f"label {canonical_label!r}. Reused rather than proposed again "
                            f"(constitution 3.2); its edges resolve against the registry.",
                        )
                    )
                    continue
                # Same ID, different label. That is a real conflict rather than a
                # duplicate proposal, and it falls through to the error below.

            entry = {
                "proposed_id": proposed_id,
                "proposed_label": label,
                "kind": (prefix_of(proposed_id) or "").rstrip("_"),
                "why_needed": (candidate.get("why_needed") or "").strip(),
                "edges_depending_on_it": list(candidate.get("edges_depending_on_it") or []),
                "prefix_approved": prefix_of(proposed_id) is not None,
                "id_format_valid": bool(ID_FORMAT.match(proposed_id)),
                "already_canonical": proposed_id in self.registry,
                "label_collides_with": list(self.registry.label_collisions(proposed_id, label)),
                "disposition": "requires_architect_decision",
            }
            # DEC-2026-0003 and ESCALATION_CONTRACT 1.1: absence from the
            # registry is not by itself architectural. A proposal under an
            # approved prefix and kind, with a valid ID and clear duplicate and
            # neighbourhood checks, is normal Builder/Reviewer work.
            held = self.governance.held_by_package(proposed_id)
            architect_required = (
                entry["already_canonical"]
                or not entry["prefix_approved"]
                or not entry["id_format_valid"]
                or held is not None
            )
            entry["architect_required"] = architect_required
            entry["disposition"] = (
                "requires_architect_decision" if architect_required else "reviewer_may_approve"
            )
            entry["routing_basis"] = (
                f"held by {held['reserved_escalation_id']} ({held['topic']}), owner "
                f"{held['package_owner']}, per {held['decision_id']}"
                if held
                else "DEC-2026-0003: approved prefix and kind, valid ID, no duplicate"
                if not architect_required
                else "fails an identity or ontology precondition"
            )
            if self.governance.is_returned_to_workflow(proposed_id):
                entry["returned_to_workflow_by"] = self.governance.nodes_returned_to_workflow[
                    proposed_id
                ]
            result.node_additions.append(entry)

            if entry["already_canonical"]:
                result.findings.append(
                    Finding(
                        "node_addition_already_canonical",
                        "error",
                        f"proposed node {proposed_id!r} already exists in the registry; "
                        f"reuse it rather than minting a variant (constitution 3.2)",
                    )
                )
            if not entry["prefix_approved"]:
                result.findings.append(
                    Finding(
                        "node_prefix_unapproved",
                        "error",
                        f"proposed node {proposed_id!r} uses no approved prefix "
                        f"(constitution 3.1); Builder may not create ontology",
                    )
                )
            if not entry["id_format_valid"]:
                result.findings.append(
                    Finding(
                        "node_id_format",
                        "error",
                        f"proposed node {proposed_id!r} is not prefixed snake_case (invariant 3)",
                    )
                )
            if entry["label_collides_with"]:
                result.findings.append(
                    Finding(
                        "node_label_collision",
                        "warning",
                        f"proposed label {label!r} already used by canonical "
                        f"{', '.join(entry['label_collides_with'])}; labels do not determine "
                        f"identity (invariant 4) but this is the shape of a duplicate",
                    )
                )

            if not architect_required:
                result.findings.append(
                    Finding(
                        "node_addition_normal_workflow",
                        "info",
                        f"proposed node {proposed_id!r} is isolated in node_changes for Reviewer "
                        f"approval. Prefix and kind are approved and identity checks are clear, so "
                        f"per DEC-2026-0003 this is not an Architect escalation.",
                    )
                )
                continue

            if held is not None:
                result.escalations.append(
                    {
                        "kind": "node_registration_held_by_package",
                        "proposed_id": proposed_id,
                        "reserved_escalation_id": held["reserved_escalation_id"],
                        "topic": held["topic"],
                        "package_owner": held["package_owner"],
                        "assigned_by": held["decision_id"],
                        "question": (
                            f"{proposed_id!r} is the subject of {held['reserved_escalation_id']} "
                            f"({held.get('state')}), owner {held['package_owner']}. It may not be "
                            f"approved as an ordinary registry addition until that is decided."
                        ),
                        "edges_depending_on_it": entry["edges_depending_on_it"],
                    }
                )
                continue

            result.escalations.append(
                {
                    "kind": "node_registration",
                    "proposed_id": proposed_id,
                    "proposed_label": label,
                    "question": (
                        f"Should {proposed_id!r} be added to the canonical node registry? "
                        f"It fails an identity or ontology precondition, so it is not an "
                        f"ordinary registry addition under DEC-2026-0003."
                    ),
                    "edges_depending_on_it": entry["edges_depending_on_it"],
                    "why_needed": entry["why_needed"],
                }
            )

    # -- edges ---------------------------------------------------------------
    def _apply_directive(
        self, edge: dict, directive: "RowDirective", result: CompileResult
    ) -> dict | None:
        """Apply one Reviewer decision to a candidate edge.

        Returns the edge to compile, or None if the Reviewer removed it.
        """
        ref = directive.ref

        # A Review can rule a row out of one bucket while keeping it in another.
        # That is how a candidate occupying two buckets at once gets resolved,
        # so the removal has to reach the emitted patch rather than stop here.
        for bucket in sorted(directive.bucket.remove_from):
            result.rows_removed_from.add((ref, bucket))
            result.findings.append(
                Finding(
                    "reviewer_removed_row_from_bucket",
                    "info",
                    f"{ref}: {directive.review_id or 'the Review'} removed this row from "
                    f"{bucket}; its other operation stands.",
                    ref=ref,
                )
            )

        if directive.omits_row:
            result.rejected_rows.append(
                {
                    "ref": ref,
                    "reason": "reviewer_rejected",
                    "rationale": directive.rationale,
                    "integration_action": directive.integration_action,
                    "canonical_rows": list(directive.canonical_rows),
                }
            )
            result.findings.append(
                Finding(
                    "reviewer_rejected_row",
                    "info",
                    f"{ref} omitted on Reviewer disposition: {directive.rationale}",
                    ref=ref,
                )
            )
            return None

        if directive.holds_row:
            result.findings.append(
                Finding(
                    "reviewer_escalated_row",
                    "error",
                    f"{ref} carries a Reviewer architect_escalation and may not be compiled "
                    f"until it is decided: {directive.rationale}",
                    ref=ref,
                )
            )
            result.escalations.append(
                {
                    "kind": "carried_from_review",
                    "ref": ref,
                    "question": directive.rationale,
                }
            )
            return None

        # A Reviewer instruction this build cannot carry out must never be
        # absorbed as a write to a field of that name, and must never pass
        # unremarked because the same directive happens to carry no corrections.
        # Losing a ruling silently is the failure mode; failing the build is the
        # only honest alternative.
        for field_name in directive.unknown_keys:
            result.findings.append(
                Finding(
                    "reviewer_directive_not_understood",
                    "error",
                    f"{ref}: {directive.review_id or 'the Review'} gives an instruction "
                    f"{field_name!r} that is neither an edge column nor an operation this "
                    f"build implements. It has not been applied.",
                    ref=ref,
                    field_name=field_name,
                )
            )

        # Field values can arrive either as flat `exact_corrections` entries or
        # inside a bucket payload that restates the corrected row. A Review that
        # uses only the second form still corrects fields.
        if directive.corrections or directive.bucket.field_values or directive.bucket.field_corrections:
            revised = dict(edge)
            applied: dict[str, dict[str, str]] = {}
            # Polarity is build-owned only on the ten types section 6.1 derives
            # from the edge type. On MODIFIES, TRIGGERS and CONSTRAINS it is a
            # reading of the source, and the Reviewer owns readings. A correction
            # to edge_type in the same directive decides which regime applies.
            effective_type = str(
                directive.corrections.get(
                    "edge_type",
                    directive.bucket.field_corrections.get(
                        "edge_type", edge.get("edge_type") or ""
                    ),
                )
            ).strip()
            polarity_is_authored = effective_type in AUTHORED_POLARITY_TYPES

            # A Review that restates the whole corrected row inside its bucket
            # instruction is correcting those columns. They are applied first so
            # an explicit `exact_corrections` entry still wins. A `replace_ref`
            # `fields` block sits between the two: more deliberate than an echo
            # of the row, less specific than a flat correction.
            corrections = {
                **directive.bucket.field_values,
                **directive.bucket.field_corrections,
                **directive.corrections,
            }
            for field_name, new_value in corrections.items():
                if field_name in directive.unknown_keys:
                    continue
                if field_name in BUILD_OWNED_FIELDS and not polarity_is_authored:
                    result.findings.append(
                        Finding(
                            "reviewer_correction_on_build_owned_field",
                            "error",
                            f"{ref}: Reviewer corrected {field_name!r}, which the build derives "
                            f"from edge_type {effective_type!r}. Correction not applied "
                            f"(invariants 13-14).",
                            ref=ref,
                            field_name=field_name,
                        )
                    )
                    continue
                applied[field_name] = {
                    "from": str(revised.get(field_name, "")),
                    "to": new_value,
                }
                revised[field_name] = new_value

            if applied:
                result.corrections_applied.append(
                    {
                        "ref": ref,
                        "rationale": directive.rationale,
                        "fields": applied,
                    }
                )
                result.findings.append(
                    Finding(
                        "reviewer_correction_applied",
                        "info",
                        f"{ref}: applied Reviewer correction to "
                        f"{', '.join(sorted(applied))}. The corrected value is revalidated below.",
                        ref=ref,
                    )
                )
            return revised

        return edge

    def _apply_architect_disposition(
        self, edge: dict, disposition: dict, result: CompileResult
    ) -> dict:
        """Apply an Architect decision's ruled field values to one row.

        Highest authority in the pipeline. Where a Reviewer correction and a
        decision disagree, the decision wins and the displacement is recorded so
        the override is visible rather than silent.
        """
        ref = edge.get("ref")
        revised = dict(edge)
        applied: dict[str, dict[str, str]] = {}

        for field_name, ruled in disposition["fields"].items():
            before = "" if edge.get(field_name) is None else str(edge.get(field_name))
            after = "" if ruled is None else str(ruled)
            if before == after:
                continue
            applied[field_name] = {"from": before, "to": after}
            revised[field_name] = ruled

        if applied:
            build_owned = sorted(set(applied) & BUILD_OWNED_FIELDS)
            result.architect_overrides.append(
                {
                    "ref": ref,
                    "decision_id": disposition["decision_id"],
                    "fields": applied,
                    "build_owned_fields_ruled": build_owned,
                }
            )
            result.findings.append(
                Finding(
                    "architect_disposition_applied",
                    "info",
                    f"{ref}: {disposition['decision_id']} rules "
                    f"{', '.join(sorted(applied))}. Applied over the GUR and any Reviewer "
                    f"correction to the same field.",
                    ref=ref,
                )
            )
            if build_owned:
                result.findings.append(
                    Finding(
                        "architect_ruled_build_owned_field",
                        "warning",
                        f"{ref}: {disposition['decision_id']} rules "
                        f"{', '.join(build_owned)}, which the build normally owns. Carried as "
                        f"decision-sourced, not derived; the Reviewer must still verify the "
                        f"reading against source.",
                        ref=ref,
                    )
                )
        return revised

    def _compile_edge(self, edge: dict, gur: dict, result: CompileResult) -> dict | None:
        ref = edge.get("ref") or "<no ref>"

        missing = [f for f in REQUIRED_EDGE_FIELDS if f not in edge]
        if missing:
            result.findings.append(
                Finding(
                    "edge_fields_missing",
                    "error",
                    f"edge is missing required field(s): {', '.join(missing)}",
                    ref=ref,
                )
            )

        edge_type = (edge.get("edge_type") or "").strip()
        if edge_type not in EDGE_TYPES:
            result.findings.append(
                Finding(
                    "edge_type_illegal",
                    "error",
                    f"edge_type {edge_type!r} is outside the thirteen-type closed vocabulary "
                    f"(invariant 7). Builder does not extend the ontology.",
                    ref=ref,
                    field_name="edge_type",
                )
            )
            result.escalations.append(
                {
                    "kind": "edge_vocabulary",
                    "ref": ref,
                    "edge_type": edge_type,
                    "question": "An edge does not fit the closed vocabulary; Architect ruling required.",
                }
            )
            return None

        source_id = self._resolve_endpoint(edge, "source", result)
        target_id = self._resolve_endpoint(edge, "target", result)

        pol = polarity_mod.resolve(edge_type, edge.get("polarity"), edge.get("polarity_basis"))
        for item in pol.findings:
            result.findings.append(
                Finding(item["rule"], item["severity"], item["detail"], ref=ref, field_name="polarity")
            )

        for item in grain.check_edge(edge.get("aspect") or "", edge.get("condition") or ""):
            result.findings.append(
                Finding(item["rule"], item["severity"], item["detail"], ref=ref, field_name=item["field"])
            )

        # -- controlled vocabularies -----------------------------------------
        book = (edge.get("book") or "").strip()
        if book not in BOOKS:
            result.findings.append(
                Finding("book_illegal", "error", f"book {book!r} is not one of PHB, DMG, UA, MM",
                        ref=ref, field_name="book")
            )

        evidence = (edge.get("evidence") or "").strip()
        if evidence not in EVIDENCE_CLASSES:
            result.findings.append(
                Finding("evidence_illegal", "error",
                        f"evidence {evidence!r} is outside the section 7 classes",
                        ref=ref, field_name="evidence")
            )

        status = (edge.get("status") or "").strip()
        if status not in STATUS_VALUES:
            result.findings.append(
                Finding("status_illegal", "error", f"status {status!r} is not core or optional",
                        ref=ref, field_name="status")
            )
        if book == "UA" and status != "optional":
            result.findings.append(
                Finding("ua_must_be_optional", "error",
                        "Unearthed Arcana is optional in its entirety (constitution section 8)",
                        ref=ref, field_name="status")
            )

        review_flag = (edge.get("review_flag") or "").strip()
        if review_flag and review_flag not in REVIEW_FLAG_VALUES:
            result.findings.append(
                Finding("review_flag_illegal", "error",
                        f"review_flag {review_flag!r} is outside the controlled vocabulary",
                        ref=ref, field_name="review_flag")
            )

        # -- conditional fields ----------------------------------------------
        supersession = (edge.get("supersession_basis") or "").strip()
        if edge_type == "OVERRIDES":
            if not supersession:
                result.findings.append(
                    Finding("supersession_basis_required", "error",
                            "supersession_basis is required on every OVERRIDES edge (invariant 20)",
                            ref=ref, field_name="supersession_basis")
                )
            elif supersession not in SUPERSESSION_BASIS_VALUES:
                result.findings.append(
                    Finding("supersession_basis_illegal", "error",
                            f"supersession_basis {supersession!r} is outside the controlled vocabulary",
                            ref=ref, field_name="supersession_basis")
                )
        elif supersession:
            result.findings.append(
                Finding("supersession_basis_forbidden", "error",
                        f"supersession_basis is populated only for OVERRIDES; found on {edge_type} "
                        f"(invariant 20)",
                        ref=ref, field_name="supersession_basis")
            )

        general_rule_id = (edge.get("general_rule_id") or "").strip()
        pass_value = (edge.get("pass") or "").strip()
        if pass_value == PASS_GENERAL_RULE:
            if not general_rule_id:
                result.findings.append(
                    Finding("general_rule_id_required", "error",
                            "general_rule_id is required when pass=general-rule (invariant 18)",
                            ref=ref, field_name="general_rule_id")
                )
            elif self.general_rules and general_rule_id not in self.general_rules:
                result.findings.append(
                    Finding("general_rule_id_unknown", "error",
                            f"general_rule_id {general_rule_id!r} does not resolve in the "
                            f"general-rule register",
                            ref=ref, field_name="general_rule_id")
                )
        elif general_rule_id:
            result.findings.append(
                Finding("general_rule_id_forbidden", "error",
                        f"general_rule_id is populated only for inherited general-rule edges; "
                        f"found with pass={pass_value!r} (invariant 19)",
                        ref=ref, field_name="general_rule_id")
            )

        # -- citation ---------------------------------------------------------
        page = str(edge.get("page") or "").strip()
        section = (edge.get("section") or "").strip()
        if ";" in section:
            # Constitution 1.4: `section` never contains a list of headings.
            result.findings.append(
                Finding(
                    "citation_multi_locus", "error",
                    f"section {section!r} joins several headings. Constitution "
                    f"{CONSTITUTION_VERSION} allows one section heading or blank; where evidence "
                    f"spans pages within one section, cite that section and leave page blank.",
                    ref=ref, field_name="section",
                )
            )
        if not page and not section:
            result.findings.append(
                Finding("citation_missing", "error",
                        "every edge needs a citation: book plus section and/or page (invariant 9)",
                        ref=ref, field_name="page")
            )
        if page:
            parts = [p.strip() for p in page.split(",") if p.strip()]
            if len(parts) > 1:
                # Constitution section 5 defines `page` as "printed page number
                # from the source's own footer", singular. No canonical row
                # carries a list. Admitting one is a data-model change.
                result.findings.append(
                    Finding(
                        "citation_multi_locus", "error",
                        f"page {page!r} names {len(parts)} printed pages. Constitution section 5 "
                        f"defines `page` as a single printed page number and no canonical row "
                        f"carries a list; Builder will not widen the field's meaning.",
                        ref=ref, field_name="page",
                    )
                )
                result.escalations.append(
                    {
                        "kind": "citation_cardinality",
                        "ref": ref,
                        "page_value": page,
                        "section_value": section,
                        "question": (
                            "May one edge carry several printed-page loci? Constitution section 5 "
                            "reads `page` as singular and 3,804 of 3,809 canonical rows are a "
                            "single number, the rest empty. If multi-locus citation is correct, "
                            "the field definition, the CSV contract and the Reviewer's citation "
                            "checks all need amending together."
                        ),
                    }
                )

            if any(sep in page for sep in (";", "-", "–")) and len(parts) == 1:
                result.findings.append(
                    Finding(
                        "citation_multi_locus", "error",
                        f"page {page!r} is a range or delimiter-joined value. Constitution "
                        f"{CONSTITUTION_VERSION} section 5 allows one printed page number or blank.",
                        ref=ref, field_name="page",
                    )
                )

            if not all(p.isdigit() for p in parts):
                result.findings.append(
                    Finding("page_not_numeric", "error",
                            f"page {page!r} is not a printed page number",
                            ref=ref, field_name="page")
                )

            start, end = gur.get("page_start"), gur.get("page_end")
            if isinstance(start, int) and isinstance(end, int):
                outside = [p for p in parts if p.isdigit() and not (start <= int(p) <= end)]
                if outside:
                    result.findings.append(
                        Finding("page_outside_packet", "error",
                                f"page(s) {', '.join(outside)} lie outside the packet range "
                                f"{start}-{end}; a packet may not cite pages it does not cover, "
                                f"and this packet's source carries no marker for them",
                                ref=ref, field_name="page")
                    )

        if source_id is None or target_id is None:
            return None

        # Direction and type selection (constitution 1.4 section 4.2, DEC-2026-0011).
        probe = {"source_id": source_id, "target_id": target_id, "edge_type": edge_type}
        reversal = direction.classify(probe, self.canonical.reversed_edges(probe))
        if reversal is not None:
            result.findings.append(
                Finding(reversal["rule"], reversal["severity"], reversal["detail"], ref=ref)
            )
            result.direction_findings.append(
                {
                    "ref": ref,
                    "rule": reversal["rule"],
                    "disposition": reversal["disposition"],
                    "proposed": f"{source_id} {edge_type} {target_id}",
                    "canonical_counterparts": reversal["counterparts"],
                }
            )
            if reversal["disposition"] == "reject":
                result.rejected_rows.append(
                    {
                        "ref": ref,
                        "reason": reversal["rule"],
                        "rationale": reversal["detail"],
                        "authority": "DEC-2026-0011",
                        "canonical_rows": [c["canonical_row"] for c in reversal["counterparts"]],
                    }
                )
                return None

        return {
            "ref": ref,
            "source_id": source_id,
            "source_label": self._endpoint_label(source_id, edge, "source", result),
            "edge_type": edge_type,
            "target_id": target_id,
            "target_label": self._endpoint_label(target_id, edge, "target", result),
            "aspect": (edge.get("aspect") or "").strip(),
            "condition": (edge.get("condition") or "").strip(),
            "polarity": pol.polarity,
            "polarity_basis": pol.polarity_basis,
            "book": book,
            "page": page,
            "section": section,
            "evidence": evidence,
            "pass": pass_value,
            "status": status,
            "supersession_basis": supersession,
            "general_rule_id": general_rule_id,
            "review_flag": review_flag,
        }

    def _field_diff(self, row: dict, canonical_index: int) -> dict[str, dict[str, str]]:
        """Per-column difference between a compiled row and a canonical row."""
        canonical = self.canonical.rows[canonical_index]
        diff: dict[str, dict[str, str]] = {}
        for column in COLUMNS:
            ours = (row.get(column) or "").strip()
            theirs = (canonical.get(column) or "").strip()
            if ours != theirs:
                diff[column] = {"patch": ours, "canonical": theirs}
        return diff

    def _emit_directed_update(self, row: dict, directive, result: CompileResult) -> None:
        """Emit a row as a repair to the canonical row the Reviewer named.

        Whether an assertion is already in the graph under a different wording is
        a judgement about the neighbourhood, and the Reviewer is the role that
        makes it. Where a directive names the row, the build honours it instead
        of inserting a second copy of the assertion. Unlike a polarity repair,
        every differing column is offered for change: the Reviewer authored the
        corrected values deliberately.
        """
        ref = row["ref"]
        canonical_row = directive.effective_canonical_row
        operation = directive.effective_operation
        index = canonical_row - 2  # header occupies line 1
        if not 0 <= index < len(self.canonical.rows):
            result.findings.append(
                Finding(
                    "review_canonical_row_out_of_range",
                    "error",
                    f"{ref}: the Review names canonical row {canonical_row}, which the "
                    f"canonical graph does not have ({len(self.canonical.rows)} rows)",
                    ref=ref,
                )
            )
            return

        # Where the Review supplies the change set explicitly, that is the
        # authored one and it governs: it records what the Reviewer compared
        # against canonical, which may differ from what this build recomputes if
        # the row has moved on since.
        diff = (
            dict(directive.bucket.changes)
            if directive.bucket.changes
            else self._field_diff(row, index)
        )

        # A field can be source-supported and still not writable yet: an
        # Architect decision may defer the canonical change until separate work
        # resolves it. The Reviewer names those fields, and they move out of the
        # change set into the record of what was knowingly left alone -- so the
        # Integrator sees the deferral rather than a silently missing column.
        withheld: dict[str, Any] = {}
        for field_name in sorted(directive.bucket.remove_change_fields):
            if field_name in diff:
                withheld[field_name] = diff.pop(field_name)
                result.findings.append(
                    Finding(
                        "reviewer_withheld_field_from_update",
                        "info",
                        f"{ref}: {directive.review_id or 'the Review'} holds {field_name!r} out "
                        f"of the update to canonical row {canonical_row}"
                        + (f": {directive.rationale}" if directive.rationale else "")
                        + ".",
                        ref=ref,
                        field_name=field_name,
                    )
                )
            else:
                result.findings.append(
                    Finding(
                        "reviewer_withheld_field_not_in_change_set",
                        "warning",
                        f"{ref}: the Review holds {field_name!r} out of the update to canonical "
                        f"row {canonical_row}, but this build does not change that field.",
                        ref=ref,
                        field_name=field_name,
                    )
                )
        for field_name, body in directive.bucket.differences_not_applied.items():
            withheld[field_name] = dict(body)

        entry = {
            "ref": ref,
            "canonical_row": canonical_row,
            "reason": operation,
            "changes": diff,
            "differences_not_applied": withheld,
            # A later Review in a chain approves the placement rather than
            # restating why the row belongs at this canonical row, and its
            # rationale speaks to the row's contents. Where the Review carries
            # the placement account, it is the one the Integrator needs.
            "detail": directive.bucket.detail
            or (
                f"Reviewer ruled this a {operation.replace('_', ' ')} of canonical row "
                f"{canonical_row} rather than an insertion"
                + (f": {directive.rationale}" if directive.rationale else "")
            ),
        }
        obsolete_row = directive.effective_obsolete_row
        if obsolete_row is not None:
            entry["obsolete_conflicting_row"] = obsolete_row

        result.updates.append(entry)
        result.rows_superseded.add(ref)

        if not diff:
            result.findings.append(
                Finding(
                    "reviewer_directed_update_is_a_no_op",
                    "info",
                    f"{ref} matches canonical row {canonical_row} in every column. "
                    f"Recorded as an update so the row is not inserted twice; nothing changes.",
                    ref=ref,
                )
            )
            return

        result.findings.append(
            Finding(
                "reviewer_directed_canonical_update",
                "info",
                f"{ref} emitted as a {operation} of canonical row "
                f"{canonical_row}, changing {', '.join(sorted(diff))}"
                + (
                    f"; canonical row {obsolete_row} is superseded"
                    if obsolete_row is not None
                    else ""
                )
                + ".",
                ref=ref,
            )
        )

    # -- driver --------------------------------------------------------------
    def compile(
        self,
        gur_path: str | Path,
        directives: "ReviewDirectives | None" = None,
        revision: int | None = None,
        supersedes: str | None = None,
    ) -> CompileResult:
        gur_path = Path(gur_path)
        gur = yaml.safe_load(gur_path.read_text(encoding="utf-8"))

        gur_id = gur.get("id") or gur_path.stem
        packet_id = gur.get("packet_id") or ""
        # A GUP revision tracks the GUR by default, but a Reviewer revision
        # request advances the GUP without a new GUR, so it may be set
        # explicitly. FILE_NAMING forbids overwriting a prior revision.
        gup_revision = revision if revision is not None else gur.get("revision") or 1
        gup_id = f"GUP-{packet_id}-r{int(gup_revision):02d}"

        result = CompileResult(
            gur_id=gur_id,
            gup_id=gup_id,
            packet_id=packet_id,
            gur_checksum=f"sha256:{sha256_of(gur_path)}",
        )
        # Snapshotted so a result can answer "is this endpoint registered?"
        # without holding the registry, which is what separates a pending row
        # the batch can satisfy from one it cannot.
        result.canonical_node_ids = set(self.registry.nodes)
        result.revision = int(gup_revision)
        result.supersedes = supersedes
        result.envelope = {
            "schema_version": "1.0",
            "id": gup_id,
            "ruleset_id": gur.get("ruleset_id"),
            "book_id": gur.get("book_id"),
            "source_id": gur.get("source_id"),
            "packet_id": packet_id,
            # The constitution this patch was *compiled and validated* under,
            # which is the compiler's, not the GUR's. A GUR authored under 1.2 is
            # revalidated here rather than trusted, so echoing 1.2 onto the GUP
            # would tell the Reviewer the patch was checked against rules that
            # were never applied to it. What the GUR declared is preserved in
            # provenance, where it describes the input instead of the output.
            "constitution_version": CONSTITUTION_VERSION,
            "gur_constitution_version": str(gur.get("constitution_version") or ""),
        }

        self._check_envelope(gur, result)
        self._compile_node_additions(gur, result)

        candidate_edges = gur.get("candidate_edges") or []
        result.edges_in = len(candidate_edges)
        seen_refs: set[str] = set()
        answers_earlier_gur = False
        approved_repoints: dict[str, str] = {}
        if directives is not None:
            result.review_id = directives.review_id
            if directives.reviewed_gup and directives.reviewed_gup.startswith("GUP-"):
                expected_packet = directives.packet_id
                if expected_packet and expected_packet != packet_id:
                    result.findings.append(
                        Finding(
                            "review_packet_mismatch",
                            "error",
                            f"review {directives.review_id} is for packet {expected_packet!r} but "
                            f"the GUR is for {packet_id!r}",
                        )
                    )
            for name in directives.unknown_dispositions:
                result.findings.append(
                    Finding(
                        "review_disposition_unknown",
                        "error",
                        f"review carries an unrecognised disposition for {name}",
                    )
                )
            for key in sorted(set(directives.unread_decision_keys)):
                result.findings.append(
                    Finding(
                        "review_decision_key_not_read",
                        "error",
                        f"review {directives.review_id} states rulings under {key!r}, which "
                        f"this compiler does not read. Applying the revision would silently "
                        f"ignore them.",
                    )
                )
            # A ruling on a GUP-level field names no row, so nothing in the
            # compile loop can consume it. It is reported on every compile so the
            # Builder answers it deliberately in how the patch is emitted --
            # reading the key without surfacing it would be the same silent drop
            # as not reading it at all.
            for directive in directives.field_directives:
                result.findings.append(
                    Finding(
                        "review_field_directive_outstanding",
                        "warning",
                        f"review {directives.review_id} rules "
                        f"{directive.disposition or 'no disposition'} on the GUP field "
                        f"{directive.field_name!r}: {directive.correction or 'no correction stated'} "
                        f"This constrains how the patch is emitted rather than any single "
                        f"row; confirm the emitted patch satisfies it before approval.",
                    )
                )

            # A Review that returned the packet to the Analyst is answered by a
            # new GUR revision. That replacement legitimately drops rows the
            # Review rejected and adds rows it demanded, so the Review covers
            # only part of the population being compiled. Comparing the Review's
            # own input GUR against the GUR in hand distinguishes the two cases.
            # A Review with no recorded input GUR is read strictly.
            answers_earlier_gur = bool(directives.input_gur) and directives.input_gur != gur_id
            if answers_earlier_gur:
                result.findings.append(
                    Finding(
                        "review_answered_by_new_gur",
                        "info",
                        f"{directives.review_id} reviewed a patch built from "
                        f"{directives.input_gur}; this build uses {gur_id}. Rows added since "
                        f"that revision are new Analyst work and are carried for review.",
                    )
                )

            # True when the newest Review in the chain judged exactly the row
            # population being compiled, which makes it authoritative over what
            # the patch should contain.
            newest_covers_this_gur = directives.input_gur == gur_id

            unmatched = sorted(set(directives.rows) - {e.get("ref") for e in candidate_edges})
            for ref in unmatched:
                directive = directives.rows[ref]
                # Which Review is asking decides whether a missing row is a
                # defect, and in a chain that is not always the newest one. An
                # early Review judged a population the Analyst has since
                # revised; rows it decided that the revision dropped are stale,
                # not lost. Using the merged (newest) input GUR here would call
                # every such row an error.
                deciding_review = directive.review_id or directives.review_id
                stale = bool(directive.review_input_gur) and directive.review_input_gur != gur_id
                if stale and directive.omits_row:
                    result.findings.append(
                        Finding(
                            "review_rejection_applied_at_source",
                            "info",
                            f"{ref} was rejected by {deciding_review} and the Analyst removed "
                            f"it in {gur_id}. The rejection is satisfied at source.",
                            ref=ref,
                        )
                    )
                    continue
                # An approved row that vanished is normally a loss. It is not one
                # when a *later* Review in the chain reviewed a patch built from
                # this very GUR: that Review judged the current population in
                # full, so a row it does not mention is one the Analyst withdrew
                # and the Reviewer has already signed off on the result.
                if stale and newest_covers_this_gur:
                    result.findings.append(
                        Finding(
                            "review_ref_superseded_by_new_gur",
                            "info",
                            f"{ref} was decided by {deciding_review}, which reviewed a patch built "
                            f"from {directive.review_input_gur}. {gur_id} no longer proposes it and "
                            f"{directives.review_id} reviewed this GUR in full, so the ruling is "
                            f"spent.",
                            ref=ref,
                        )
                    )
                    continue
                result.findings.append(
                    Finding(
                        "review_ref_not_in_gur",
                        "error",
                        f"review decides ref {ref!r}, which does not appear in {gur_id}",
                    )
                )

            # Must run before any edge is resolved: a Review can repoint an
            # endpoint at a node that does not exist yet, and the proposal has
            # to be on the books before resolution asks whether it does.
            self._register_reviewer_directed_nodes(directives, candidate_edges, result)
            approved_repoints = self._reviewer_approved_repoints(
                directives, candidate_edges, result
            )
            self._apply_node_directives(directives, result)
            self._prune_rejected_dependents(directives, candidate_edges, result)
            self._drop_reviewer_rejected_nodes(directives, candidate_edges, result)

        for edge in candidate_edges:
            ref = edge.get("ref")
            if ref in seen_refs:
                result.findings.append(
                    Finding("duplicate_ref", "error", f"ref {ref!r} appears more than once in the GUR")
                )
            seen_refs.add(ref)

            for role in ("source", "target"):
                legacy = str(edge.get(f"{role}_id") or "")
                replacement = approved_repoints.get(legacy)
                if replacement is None:
                    continue
                edge = dict(edge)
                edge[f"{role}_id"] = replacement
                result.findings.append(
                    Finding(
                        "endpoint_repointed_by_review",
                        "info",
                        f"{ref}: {role}_id {legacy!r} repointed to {replacement!r}, the "
                        f"replacement the Reviewer confirmed for this row.",
                        ref=ref,
                        field_name=f"{role}_id",
                    )
                )

            architect = self.governance.row_disposition(packet_id, ref)

            undecided = False
            if directives is not None:
                directive = directives.for_ref(ref)
                if directive is None and architect is not None:
                    # The Architect ruled this row directly, which settles it
                    # whether or not the Review covered it.
                    pass
                elif directive is None:
                    # A row this build rejects on its own was never in the
                    # reviewed patch, so no disposition is expected for it.
                    # Whether it survives is only known once it is compiled, so
                    # the finding is deferred until after that.
                    undecided = True
                else:
                    revised = self._apply_directive(edge, directive, result)
                    if revised is None:
                        continue
                    edge = revised

            if architect is not None:
                # An Architect decision outranks both the GUR and a Reviewer
                # correction. Applied last so its values are the ones that stand.
                edge = self._apply_architect_disposition(edge, architect, result)

            row = self._compile_edge(edge, gur, result)

            if undecided:
                if row is None:
                    result.findings.append(
                        Finding(
                            "review_row_not_presented",
                            "info",
                            f"{ref} carries no Reviewer disposition because this build rejects it "
                            f"independently; it was never part of the reviewed patch",
                            ref=ref,
                        )
                    )
                elif answers_earlier_gur:
                    result.findings.append(
                        Finding(
                            "review_row_new_since_review",
                            "info",
                            f"{ref} is new in {gur_id} and postdates {directives.review_id}, so "
                            f"no disposition could exist for it. Carried for review.",
                            ref=ref,
                        )
                    )
                else:
                    result.findings.append(
                        Finding(
                            "review_row_undecided",
                            "error",
                            f"{ref} carries no Reviewer disposition; review is per row and this "
                            f"one was not decided",
                            ref=ref,
                        )
                    )

            if row is not None:
                result.rows.append(row)

        # Carry the Analyst's own architectural escalations through; Builder
        # does not resolve them (invariant 27).
        for item in gur.get("architectural_escalations") or []:
            if not isinstance(item, dict):
                continue
            escalation_id = (item.get("id") or "").strip()
            if escalation_id and self.governance.is_decided(escalation_id):
                # The Architect has since ruled. Carrying it forward as open
                # would block the patch on a settled question.
                result.findings.append(
                    Finding(
                        "gur_escalation_since_decided",
                        "info",
                        f"{escalation_id} was open when the GUR was written and has since been "
                        f"decided by {self.governance.decided_by(escalation_id)}; it no longer "
                        f"blocks this patch.",
                    )
                )
                result.resolved_escalations.append(
                    {
                        "id": escalation_id,
                        "decided_by": self.governance.decided_by(escalation_id),
                        "question": item.get("question"),
                    }
                )
                continue
            if not escalation_id:
                # ESCALATION_CONTRACT: "Every escalation must include: 1.
                # escalation ID". Without it the build cannot tell an open
                # question from one the Architect has already ruled on, so it
                # must carry the entry forward and block. Saying that plainly
                # turns a mystified `status: blocked` into a one-line fix for
                # the role that owns the artifact; the Builder does not resolve
                # escalations (invariant 27) and never guesses which one it is.
                result.findings.append(
                    Finding(
                        "gur_escalation_omits_id",
                        "warning",
                        "A GUR architectural_escalations entry omits the escalation ID "
                        "that ESCALATION_CONTRACT requires, so it cannot be matched "
                        "against the decided escalations and is carried forward as "
                        "open. If the Architect has already ruled, the GUR must name "
                        f"the escalation ID. Topic: {item.get('topic') or item.get('question') or 'unstated'}",
                    )
                )
            result.escalations.append({"kind": "carried_from_gur", **item})

        # -- duplicates and neighbourhood ------------------------------------
        result.duplicate_findings.extend(intra_patch_duplicates(result.rows))
        for row in result.rows:
            directive = directives.for_ref(row["ref"]) if directives is not None else None
            if directive is not None and directive.targets_canonical_row:
                # The Reviewer ruled this row a repair to a named canonical row.
                # That is a decision about the graph, not about the row's fields,
                # so it cannot be reached by the build's own duplicate detection.
                self._emit_directed_update(row, directive, result)
                continue

            for match in self.canonical.exact_matches(row):
                diff = self._field_diff(row, match["canonical_index"])
                build_diff = {k: v for k, v in diff.items() if k in BUILD_OWNED_FIELDS}
                other_diff = {k: v for k, v in diff.items() if k not in BUILD_OWNED_FIELDS}
                canonical_basis = (diff.get("polarity_basis") or {}).get(
                    "canonical", row["polarity_basis"]
                )

                # The assertion already exists. Where this patch supplies a read
                # polarity over a canonical row that has none, that is a repair
                # of an existing row, not a second insertion of the same
                # assertion. Only the build-owned fields are proposed for
                # change; a differing `pass` or `section` is the Reviewer's to
                # judge and is reported rather than silently applied.
                if build_diff and canonical_basis in {"unset", "heuristic"} and row[
                    "polarity_basis"
                ] == "read":
                    result.updates.append(
                        {
                            "ref": row["ref"],
                            "canonical_row": match["canonical_row"],
                            "reason": "polarity_repair",
                            "changes": build_diff,
                            "differences_not_applied": other_diff,
                            "detail": (
                                f"assertion already canonical with polarity_basis="
                                f"{canonical_basis!r}; this patch supplies an authored reading. "
                                f"Only polarity fields are proposed for change."
                            ),
                        }
                    )
                    result.findings.append(
                        Finding(
                            "duplicate_resolved_as_update",
                            "warning",
                            f"{row['ref']} restates canonical row {match['canonical_row']}, which "
                            f"carries polarity_basis={canonical_basis!r}. Emitted as a polarity "
                            f"update rather than a duplicate insertion; Reviewer must confirm the "
                            f"reading against source."
                            + (
                                f" {len(other_diff)} further field(s) differ and are not applied: "
                                f"{', '.join(sorted(other_diff))}."
                                if other_diff
                                else ""
                            ),
                            ref=row["ref"],
                        )
                    )
                    result.rows_superseded.add(row["ref"])
                    continue

                if build_diff and canonical_basis == "read":
                    result.findings.append(
                        Finding(
                            "polarity_conflict_with_canonical",
                            "error",
                            f"{row['ref']} and canonical row {match['canonical_row']} assert the "
                            f"same relationship with different read polarity "
                            f"({row['polarity']!r} vs "
                            f"{(diff.get('polarity') or {}).get('canonical')!r}); "
                            f"Builder does not choose between two source readings",
                            ref=row["ref"],
                        )
                    )

                result.duplicate_findings.append(
                    {
                        "grade": "exact_vs_canonical",
                        "ref": row["ref"],
                        "canonical": match,
                        "field_diff": diff,
                        "detail": (
                            "assertion key already present in the canonical graph; inserting it "
                            "again would violate invariant 12"
                        ),
                    }
                )
            for match in self.canonical.near_matches(row):
                result.duplicate_findings.append(
                    {
                        "grade": "near_vs_canonical",
                        "ref": row["ref"],
                        "canonical": match,
                        "detail": (
                            "same endpoints and edge type as an existing canonical edge, differing "
                            "in aspect or condition; Reviewer must decide restatement vs addition"
                        ),
                    }
                )
            # The Reviewer approved this row as a repair to the graph. If the
            # build reached the end of duplicate resolution without producing
            # one, the ruling has been lost and the row would be inserted as a
            # new assertion. That is the defect two Reviews caught by hand; it
            # fails the build rather than shipping.
            if (
                directive is not None
                and directive.presented_operation == "updates"
                and not directive.omits_row
                and not directive.holds_row
                and row["ref"] not in result.rows_superseded
            ):
                result.findings.append(
                    Finding(
                        "reviewer_operation_not_preserved",
                        "error",
                        f"{row['ref']}: {directives.review_id} approved this row as an update to "
                        f"the canonical graph, but the build produced an addition. The canonical "
                        f"row it repairs is named in an earlier Review; pass that Review too.",
                        ref=row["ref"],
                    )
                )

            neighbours = self.canonical.neighbourhood(row)
            if neighbours:
                result.conflict_findings.append(
                    {
                        "ref": row["ref"],
                        "endpoints": [row["source_id"], row["target_id"]],
                        "existing_edges": neighbours,
                        "detail": "the same node pair is already related by other edge types",
                    }
                )

        for finding in self_edges(result.rows):
            result.findings.append(
                Finding("self_edge", "error", finding["detail"], ref=finding["ref"])
            )

        for dup in result.duplicate_findings:
            if dup["grade"] in {"exact", "exact_vs_canonical"}:
                result.findings.append(
                    Finding("duplicate_assertion", "error", dup["detail"], ref=dup.get("ref"))
                )

        # Deterministic row order: canonical assertion order, ref as tiebreak.
        result.rows.sort(
            key=lambda r: (
                r["source_id"],
                r["edge_type"],
                r["target_id"],
                r["aspect"],
                r["condition"],
                r["ref"],
            )
        )
        return result


def load_general_rules(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "general_rules" in data:
        return data["general_rules"]
    return data if isinstance(data, dict) else {}


def edge_row(row: dict) -> dict:
    """Project a compiled row onto the 18 production columns, in order."""
    return {column: row.get(column, "") for column in COLUMNS}
