"""Architect decisions as compiler input.

Decisions under `rulesets/<ruleset>/escalations/decisions/` carry machine-readable
rulings that change what the Builder may do. Reading them directly keeps the
compiler honest: when the Architect rules, the behaviour follows from the
decision file rather than from a constant someone remembered to edit.

What is extracted:

- `candidate_migration_map` — node IDs whose prefix was rejected, mapped to the
  candidate replacement (DEC-2026-0004).
- `ordinary_node_registration_routing` — proposed nodes explicitly returned to
  normal Builder/Reviewer workflow (DEC-2026-0003).
- `package_assignments` — escalation packages reserved but not yet filed. A node
  named in an undecided package stays Architect-held (DEC-2026-0005).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .vocab import NODE_PREFIXES

RETURN_TO_WORKFLOW = "return_to_builder_and_reviewer"

# Fields of an escalation package that name what the escalation is *about*.
# `local_graph_neighborhood` and `source_excerpts` are deliberately excluded:
# they list surrounding canonical nodes as context, and treating those as the
# subject would hold identities nobody escalated.
# Edge fields an Architect decision may rule on directly.
#
# `polarity` and `polarity_basis` are included. Invariants 13-14 bar *workers*
# from authoring polarity, and the Architect is not a worker: the constitution
# gives that role authority to amend edge semantics, and DEC-2026-0010 rules F33
# as "polarity neutral with basis read" outright. A ruled polarity is recorded as
# decision-sourced so it is never mistaken for a build derivation, and the
# Reviewer still verifies it against source.
_RULED_EDGE_FIELDS: frozenset[str] = frozenset(
    {
        "polarity",
        "polarity_basis",
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
        "supersession_basis",
        "general_rule_id",
        "review_flag",
    }
)

SUBJECT_FIELDS: tuple[str, ...] = (
    "topic",
    "question",
    "affected_proposed_ids",
    "proposed_id",
    "proposed_ids",
    "recommended_exact_follow_up",
)


def _load_migration_due(governance: "Governance", decision_id: str, document: dict) -> None:
    """Read DEC-2026-0050-style `migration_due_ids` from one Decision.

    The mapping is exact: only IDs the Decision literally names become due. A
    later Decision naming the same ID replaces the earlier entry, so the active
    ruling wins without the loader having to know which Decisions exist.
    """

    due = document.get("migration_due_ids")
    if not isinstance(due, dict):
        return
    for retired, successor in due.items():
        retired_id = str(retired).strip()
        successor_id = str(successor or "").strip()
        if retired_id and successor_id:
            governance.migration_due_ids[retired_id] = (successor_id, decision_id)


@dataclass
class Governance:
    """Rulings in force, loaded from Architect decision files."""

    migration_map: dict[str, str] = field(default_factory=dict)
    migration_source: dict[str, str] = field(default_factory=dict)
    nodes_returned_to_workflow: dict[str, str] = field(default_factory=dict)
    nodes_held_by_package: dict[str, dict] = field(default_factory=dict)
    decisions_loaded: list[str] = field(default_factory=list)
    decided_escalations: dict[str, str] = field(default_factory=dict)
    open_escalation_ids: set[str] = field(default_factory=set)
    rejected_identities: dict[str, dict] = field(default_factory=dict)
    identity_merges: list[dict] = field(default_factory=list)
    row_dispositions: dict[tuple[str, str], dict] = field(default_factory=dict)
    #: Node IDs the Architect has given a new canonical label, before the
    #: Integrator has written it into the registry (DEC-2026-0015
    #: `node_dispositions[*].canonical_label`). Value is (label, decision_id).
    approved_labels: dict[str, tuple[str, str]] = field(default_factory=dict)
    #: DEC-2026-0050 `migration_due_ids`: legacy endpoint IDs whose replacement is
    #: due, not merely proposed. Value is (successor_id, decision_id). These are a
    #: closed, exactly-named set; every other pending migration keeps its warning.
    migration_due_ids: dict[str, tuple[str, str]] = field(default_factory=dict)

    @classmethod
    def load(cls, ruleset_root: str | Path) -> "Governance":
        root = Path(ruleset_root)
        decisions_dir = root / "escalations" / "decisions"
        governance = cls()
        if not decisions_dir.is_dir():
            return governance

        decided_escalations = cls._decided_escalation_ids(root)
        governance.decided_escalations = decided_escalations

        # A pending escalation still holds its subject. Scan open packages first
        # so a node named in one is held even if no decision reserved an ID.
        for path, document in cls._open_escalations(root):
            escalation_id = document.get("id") or path.stem
            governance.open_escalation_ids.add(escalation_id)
            subject = {k: document.get(k) for k in SUBJECT_FIELDS if document.get(k)}
            for node_id in _node_ids_in_values(subject):
                governance.nodes_held_by_package.setdefault(
                    node_id,
                    {
                        "decision_id": document.get("assigned_by"),
                        "reserved_escalation_id": escalation_id,
                        "topic": document.get("topic"),
                        "package_owner": document.get("raised_by"),
                        "state": "escalation_filed_and_pending",
                    },
                )

        for path in sorted(decisions_dir.glob("DEC-*.yaml")):
            try:
                document = yaml.safe_load(path.read_text(encoding="utf-8"))
            except yaml.YAMLError:
                continue
            if not isinstance(document, dict):
                continue
            if (document.get("status") or "").strip() != "approved":
                continue

            decision_id = document.get("id") or path.stem
            governance.decisions_loaded.append(decision_id)

            _load_migration_due(governance, decision_id, document)

            for old_id, new_id in (document.get("candidate_migration_map") or {}).items():
                governance.migration_map[str(old_id)] = str(new_id)
                governance.migration_source[str(old_id)] = decision_id

            # A decision can relabel a node it keeps. The registry still carries
            # the old label until the Integrator applies the migration, so a
            # build that normalized to the registry would undo the ruling and
            # keep re-emitting the label the decision replaced.
            for node_id, disposition in (document.get("node_dispositions") or {}).items():
                if not isinstance(disposition, dict):
                    continue
                label = str(disposition.get("canonical_label") or "").strip()
                if label:
                    governance.approved_labels[str(node_id)] = (label, decision_id)

            # Approved canonical merges (DEC-2026-0007 `identity_merges`).
            for merge in document.get("identity_merges") or []:
                survivor = (merge.get("survivor_id") or "").strip()
                retired = (merge.get("retired_id") or "").strip()
                if survivor and retired:
                    governance.identity_merges.append(
                        {
                            "decision_id": decision_id,
                            "label": merge.get("label"),
                            "survivor_id": survivor,
                            "retired_id": retired,
                            "assertion_key_audit": document.get("assertion_key_audit") or {},
                        }
                    )

            # A candidate identity the Architect refused, with the ID to use
            # instead (DEC-2026-0009 `rejected_identity_map`).
            for rejected, replacement in (document.get("rejected_identity_map") or {}).items():
                governance.rejected_identities[str(rejected)] = {
                    "replacement_id": str(replacement),
                    "decision_id": decision_id,
                    "disposition": (document.get("registry_disposition") or {}).get(
                        "disposition"
                    ),
                }

            # Per-row field rulings. `row_dispositions` is the general form;
            # `<ref>_disposition` is the single-row convention used by
            # DEC-2026-0008. Both carry a `ref` plus authoritative field values.
            packet_id = (document.get("packet_id") or "").strip()
            dispositions = list(document.get("row_dispositions") or [])
            for key, value in document.items():
                if (
                    key.endswith("_disposition")
                    and key != "registry_disposition"
                    and isinstance(value, dict)
                    and value.get("ref")
                ):
                    dispositions.append(value)
            for entry in dispositions:
                ref = (entry.get("ref") or "").strip()
                if not ref:
                    continue
                fields = {
                    k: v
                    for k, v in entry.items()
                    if k in _RULED_EDGE_FIELDS and v is not None
                }
                if not fields:
                    continue
                governance.row_dispositions[(packet_id, ref)] = {
                    "decision_id": decision_id,
                    "fields": fields,
                }

            for entry in document.get("ordinary_node_registration_routing") or []:
                if (entry.get("disposition") or "").strip() == RETURN_TO_WORKFLOW:
                    node_id = (entry.get("proposed_id") or "").strip()
                    if node_id:
                        governance.nodes_returned_to_workflow[node_id] = decision_id

            for assignment in document.get("package_assignments") or []:
                reserved = (assignment.get("reserved_escalation_id") or "").strip()
                if not reserved or reserved in decided_escalations:
                    continue
                # The package is reserved and its escalation is not decided,
                # whether or not it has been filed yet. Any node ID named inside
                # it is still an open architectural question.
                for node_id in _node_ids_in_values(assignment):
                    governance.nodes_held_by_package.setdefault(
                        node_id,
                        {
                            "decision_id": decision_id,
                            "reserved_escalation_id": reserved,
                            "topic": assignment.get("topic"),
                            "package_owner": assignment.get("package_owner"),
                            "state": "package_reserved",
                        },
                    )

        return governance

    @staticmethod
    def _decided_escalation_ids(root: Path) -> dict[str, str]:
        """Escalations that are settled and therefore no longer hold anything.

        Maps escalation ID to the decision that settled it, or to the directory
        that records it as decided.
        """
        decided: dict[str, str] = {}
        directory = root / "escalations" / "decided"
        if directory.is_dir():
            for path in directory.glob("ESC-*.yaml"):
                decided[path.stem] = "escalations/decided"
        # A decision naming its escalation settles it wherever the file sits.
        decisions = root / "escalations" / "decisions"
        if decisions.is_dir():
            for path in decisions.glob("DEC-*.yaml"):
                try:
                    document = yaml.safe_load(path.read_text(encoding="utf-8"))
                except yaml.YAMLError:
                    continue
                if isinstance(document, dict) and (document.get("status") or "") == "approved":
                    escalation_id = (document.get("escalation_id") or "").strip()
                    if escalation_id:
                        decided[escalation_id] = document.get("id") or path.stem
        return decided

    @staticmethod
    def _open_escalations(root: Path) -> list[tuple[Path, dict]]:
        """Escalation packages still awaiting a decision."""
        open_packages: list[tuple[Path, dict]] = []
        directory = root / "escalations" / "pending"
        if not directory.is_dir():
            return open_packages
        decided = Governance._decided_escalation_ids(root)
        for path in sorted(directory.glob("ESC-*.yaml")):
            try:
                document = yaml.safe_load(path.read_text(encoding="utf-8"))
            except yaml.YAMLError:
                continue
            if not isinstance(document, dict):
                continue
            if (document.get("status") or "").strip() == "decided":
                continue
            if (document.get("id") or path.stem) in decided:
                continue
            open_packages.append((path, document))
        return open_packages

    # -- queries -------------------------------------------------------------
    def migration_target(self, node_id: str) -> str | None:
        return self.migration_map.get(node_id)

    def migration_due(self, node_id: str) -> tuple[str, str] | None:
        """The successor and Decision for an ID whose migration is due.

        `None` for every other ID, including ones with a proposed-but-not-due
        migration. DEC-2026-0050 draws that line deliberately: a due ID may not
        enter new ordinary work at all, while a merely pending one still compiles
        with a warning.
        """
        return self.migration_due_ids.get(node_id)

    def approved_label(self, node_id: str) -> tuple[str, str] | None:
        """The label an Architect decision assigned, ahead of the registry."""
        return self.approved_labels.get(node_id)

    def migration_origin(self, node_id: str) -> str | None:
        """The legacy ID an Architect decision slated to become `node_id`.

        The inverse of `migration_target`. A Review that repoints an edge at a
        migration target is applying a ruling, not minting a node, and the
        legacy node is where its label and provenance come from.
        """
        for old_id, new_id in self.migration_map.items():
            if new_id == node_id:
                return old_id
        return None

    def is_returned_to_workflow(self, node_id: str) -> bool:
        return node_id in self.nodes_returned_to_workflow

    def held_by_package(self, node_id: str) -> dict | None:
        return self.nodes_held_by_package.get(node_id)

    def rejected_identity(self, node_id: str) -> dict | None:
        """An identity the Architect refused, with its named replacement."""
        return self.rejected_identities.get(node_id)

    def row_disposition(self, packet_id: str, ref: str) -> dict | None:
        """Authoritative per-row field values ruled by an Architect decision."""
        return self.row_dispositions.get((packet_id, ref))

    def is_decided(self, escalation_id: str) -> bool:
        return escalation_id in self.decided_escalations

    def decided_by(self, escalation_id: str) -> str | None:
        return self.decided_escalations.get(escalation_id)


_ID_TOKEN = re.compile(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b")


def _values_of(node) -> Iterator[str]:
    """Every scalar value in a nested structure, ignoring mapping keys.

    Keys are skipped deliberately: `package_owner` and `required_contents` are
    field names, not node identities, and matching them would hold nodes that
    nobody escalated.
    """
    if isinstance(node, dict):
        for value in node.values():
            yield from _values_of(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from _values_of(value)
    elif isinstance(node, str):
        yield node


def _node_ids_in_values(structure) -> set[str]:
    """Node IDs named in the values of an escalation or assignment.

    A match must carry an approved prefix, so ordinary prose like
    `source_review` cannot be mistaken for an identity. Over-matching would only
    widen what the compiler treats as Architect-held, which fails safe, but
    precision keeps the reported reason truthful.
    """
    found: set[str] = set()
    for text in _values_of(structure):
        for match in _ID_TOKEN.finditer(text):
            candidate = match.group(1)
            if any(candidate.startswith(prefix) for prefix in NODE_PREFIXES):
                found.add(candidate)
    return found
