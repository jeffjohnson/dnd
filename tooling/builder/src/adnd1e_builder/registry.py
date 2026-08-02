"""Canonical node registry loading and identity resolution.

Resolution order follows Builder instruction 2: exact ID, then alias, then
normalized label, then local-neighborhood. Anything that does not resolve
exactly is reported, never silently merged (instruction 3, invariant 2).
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from .vocab import NODE_PREFIXES


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    kind: str
    degree: int
    roles: tuple[str, ...]


@dataclass(frozen=True)
class Resolution:
    """Outcome of resolving one candidate ID against the registry."""

    requested_id: str
    resolved_id: str | None
    method: str  # exact | normalized_label | unresolved
    canonical: bool
    detail: str = ""
    ambiguous_with: tuple[str, ...] = ()


def normalize_label(label: str) -> str:
    """Fold a label to a comparison key. Never used to assign identity."""
    text = label.strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def prefix_of(node_id: str) -> str | None:
    """Return the approved prefix a node ID carries, or None."""
    for prefix in NODE_PREFIXES:
        if node_id.startswith(prefix):
            return prefix
    return None


ID_FORMAT = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


@dataclass
class NodeRegistry:
    """`rulesets/<ruleset>/registries/nodes.csv`, read-only to the Builder."""

    path: Path
    nodes: dict[str, Node] = field(default_factory=dict)
    _by_label: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "NodeRegistry":
        path = Path(path)
        registry = cls(path=path)
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                roles = tuple(r for r in (row.get("roles") or "").split("|") if r)
                node = Node(
                    id=row["id"].strip(),
                    label=(row.get("label") or "").strip(),
                    kind=(row.get("kind") or "").strip(),
                    degree=int(row["degree"]) if (row.get("degree") or "").strip() else 0,
                    roles=roles,
                )
                if node.id in registry.nodes:
                    raise ValueError(f"duplicate node id in registry: {node.id}")
                registry.nodes[node.id] = node
                registry._by_label.setdefault(normalize_label(node.label), []).append(node.id)
        return registry

    def __contains__(self, node_id: str) -> bool:
        return node_id in self.nodes

    def __len__(self) -> int:
        return len(self.nodes)

    def get(self, node_id: str) -> Node | None:
        return self.nodes.get(node_id)

    def resolve(self, requested_id: str, label: str = "") -> Resolution:
        """Resolve a candidate node reference to a canonical ID."""
        requested = (requested_id or "").strip()
        if not requested:
            return Resolution(requested_id, None, "unresolved", False, "empty node id")

        if requested in self.nodes:
            return Resolution(requested, requested, "exact", True)

        # Normalized-label fallback. A unique hit is reported as a proposal,
        # not applied silently; an ambiguous hit is an identity escalation.
        if label:
            hits = self._by_label.get(normalize_label(label), [])
            if len(hits) == 1:
                return Resolution(
                    requested,
                    hits[0],
                    "normalized_label",
                    True,
                    f"label {label!r} matches canonical {hits[0]}",
                )
            if len(hits) > 1:
                return Resolution(
                    requested,
                    None,
                    "unresolved",
                    False,
                    f"label {label!r} matches {len(hits)} canonical nodes; ambiguous",
                    tuple(sorted(hits)),
                )

        return Resolution(requested, None, "unresolved", False, "no canonical ID matches")

    def label_collisions(self, node_id: str, label: str) -> tuple[str, ...]:
        """Canonical nodes sharing this normalized label under a different ID."""
        return tuple(sorted(n for n in self._by_label.get(normalize_label(label), []) if n != node_id))
