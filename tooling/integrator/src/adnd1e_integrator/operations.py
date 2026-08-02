"""What an Approved bundle asks the Integrator to do, and to what.

Before WORK_QUEUES 1.2 an Approved edge CSV was read as a flat list of additions.
Bundles now carry an `operation_index` that classifies every CSV row as one of:

- `additions` — a new assertion whose endpoints already exist;
- `pending_additions` — a new assertion that depends on a node this batch is
  about to register, and which therefore may not be applied until it is;
- `updates` — a compare-and-swap against an existing canonical row.

An update names the canonical row by **file line number**, where the header is
line 1. That is the same convention `derive.py` uses when it reports a polarity
correction, and it is what makes a manifest row reference resolvable by hand in
an editor. Reading it as a zero- or one-based data index silently selects a
neighbouring row, so the applier proves identity from the endpoints as well as
the declared preconditions before it writes anything.

Node registrations are read from the approving Review, not from the GUP: the
Review is the artifact that approved the identity, and the Approved manifest
points at it by JSON pointer.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class OperationError(ValueError):
    """A bundle's operation index is not internally consistent."""


@dataclass
class EdgeUpdate:
    csv_row: int
    ref: str
    canonical_line: int
    changes: dict[str, dict[str, str]]
    differences_not_applied: dict[str, dict[str, str]] = field(default_factory=dict)

    @property
    def canonical_index(self) -> int:
        """Index into the edge list: line 1 is the header, so line N is index N-2."""
        return self.canonical_line - 2

    def as_dict(self) -> dict:
        return {
            "ref": self.ref,
            "canonical_row": self.canonical_line,
            "csv_row": self.csv_row,
            "changed_fields": sorted(self.changes),
            "changes": {f: {"from": c["canonical"], "to": c["patch"]}
                        for f, c in self.changes.items()},
            "differences_not_applied": sorted(self.differences_not_applied),
        }


@dataclass
class NodeRegistration:
    node_id: str
    label: str
    kind: str
    basis: str
    depends: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"id": self.node_id, "label": self.label, "kind": self.kind,
                "basis": self.basis, "edges_depending_on_it": self.depends}


@dataclass
class Operations:
    additions: list[int] = field(default_factory=list)
    pending_additions: list[int] = field(default_factory=list)
    updates: list[EdgeUpdate] = field(default_factory=list)
    registrations: list[NodeRegistration] = field(default_factory=list)
    inferred: list[str] = field(default_factory=list)

    @property
    def added_rows(self) -> list[int]:
        """Additions first, then pending additions — the declared application order."""
        return self.additions + self.pending_additions

    def summary(self) -> dict:
        return {
            "additions": len(self.additions),
            "pending_additions": len(self.pending_additions),
            "updates": len(self.updates),
            "node_registrations": len(self.registrations),
        }


def read_operations(manifest: dict | None, review: dict, row_count: int) -> Operations:
    """Classify every CSV row, or fail loudly rather than guess.

    A legacy bundle with no `operation_index` is read as all-additions, which is
    what the pre-1.2 Approved bundles are; the inference is reported.
    """
    operations = Operations()

    index = (manifest or {}).get("operation_index")
    if index is None:
        operations.additions = list(range(1, row_count + 1))
        operations.inferred.append(
            "bundle carries no operation_index; every CSV row read as an addition")
    else:
        operations.additions = [entry["csv_row"] for entry in index.get("additions") or []]
        operations.pending_additions = [
            entry["csv_row"] for entry in index.get("pending_additions") or []]
        for entry in index.get("updates") or []:
            operations.updates.append(EdgeUpdate(
                csv_row=entry["csv_row"],
                ref=entry.get("ref", ""),
                canonical_line=entry["canonical_row"],
                changes=entry.get("changes") or {},
                differences_not_applied=entry.get("differences_not_applied") or {},
            ))

        claimed = operations.added_rows + [u.csv_row for u in operations.updates]
        if sorted(claimed) != list(range(1, row_count + 1)):
            missing = sorted(set(range(1, row_count + 1)) - set(claimed))
            duplicated = sorted({r for r in claimed if claimed.count(r) > 1})
            raise OperationError(
                f"operation_index does not classify the CSV exactly once: "
                f"{row_count} row(s), unclassified={missing}, claimed twice={duplicated}")

    for decision in review.get("node_registry_decisions") or []:
        if decision.get("disposition") != "approved":
            continue
        operations.registrations.append(NodeRegistration(
            node_id=decision["proposed_id"],
            label=decision.get("submitted_label", decision["proposed_id"]),
            kind=decision.get("kind", decision["proposed_id"].split("_", 1)[0]),
            basis=decision.get("basis", ""),
            depends=list(decision.get("edges_depending_on_it") or []),
        ))

    declared = ((manifest or {}).get("node_operations") or {}).get("count")
    if declared is not None and declared != len(operations.registrations):
        raise OperationError(
            f"manifest declares {declared} node operation(s) but the Review approves "
            f"{len(operations.registrations)}")

    return operations
