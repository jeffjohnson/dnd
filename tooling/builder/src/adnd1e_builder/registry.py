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
    method: str  # exact | retired_replacement | normalized_label | unresolved
    canonical: bool
    detail: str = ""
    ambiguous_with: tuple[str, ...] = ()
    #: Set only for `retired_replacement`: the authority Decision and the
    #: Integration that applied the retirement, so the resolution can be audited
    #: back to the record that justifies it rather than taken on trust.
    retirement_authority: str = ""
    retirement_integration_id: str = ""


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



def load_applied_retirements(manifests_dir: str | Path) -> dict[str, dict[str, str]]:
    """Node retirements an Integration manifest records as applied.

    Keyed by retired ID, carrying `replaced_by`, `authority` and
    `integration_id`. This is published Integrator fact written when a migration
    transaction commits, not an inference: the Builder reads it and never writes
    it.

    Only rows carrying both a retired ID and a surviving ID are returned. A
    retirement with no successor is a removal, and nothing can be repointed to
    it.
    """

    import json

    directory = Path(manifests_dir)
    applied: dict[str, dict[str, str]] = {}
    if not directory.is_dir():
        return applied
    for path in sorted(directory.glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):  # pragma: no cover - unreadable manifest
            continue
        changes = document.get("registry_changes")
        if not isinstance(changes, dict):
            continue
        for row in changes.get("nodes_retired") or []:
            if not isinstance(row, dict):
                continue
            retired = str(row.get("id") or "").strip()
            survivor = str(row.get("replaced_by") or "").strip()
            if not retired or not survivor:
                continue
            applied[retired] = {
                "replaced_by": survivor,
                "authority": str(row.get("authority") or ""),
                "integration_id": str(document.get("integration_id") or path.stem),
            }
    return applied


@dataclass
class NodeRegistry:
    """`rulesets/<ruleset>/registries/nodes.csv`, read-only to the Builder."""

    path: Path
    nodes: dict[str, Node] = field(default_factory=dict)
    _by_label: dict[str, list[str]] = field(default_factory=dict)
    #: retired ID -> {replaced_by, authority, integration_id}, from published
    #: Integration manifests. Empty when none are available, which makes every
    #: retirement-aware path a no-op rather than a different answer.
    retirements: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        manifests_dir: str | Path | None = None,
    ) -> "NodeRegistry":
        """Read the registry, and the applied retirements that redirect into it.

        `manifests_dir` defaults to the ruleset's own `manifests/` directory,
        resolved from the registry path, so ordinary callers get retirement
        resolution without asking. Pass an explicit directory to pin a fixture,
        or a nonexistent one to switch it off.
        """
        path = Path(path)
        if manifests_dir is None:
            manifests_dir = path.parent.parent / "manifests"
        registry = cls(path=path, retirements=load_applied_retirements(manifests_dir))
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

    def row_of(self, node_id: str) -> int | None:
        """The 1-based CSV line, header included, or None if absent.

        A Decision that names a registry row by number was written against one
        registry state; comparing the number back is how a migration notices
        the file moved underneath it rather than merging whatever now sits
        there. `nodes` preserves CSV order, so position is the row.
        """
        for position, existing in enumerate(self.nodes, start=2):
            if existing == node_id:
                return position
        return None

    def resolve(self, requested_id: str, label: str = "") -> Resolution:
        """Resolve a candidate node reference to a canonical ID."""
        requested = (requested_id or "").strip()
        if not requested:
            return Resolution(requested_id, None, "unresolved", False, "empty node id")

        if requested in self.nodes:
            return Resolution(requested, requested, "exact", True)

        # An applied retirement is an exact, published statement that this ID
        # became that one. It is checked before the label fallback because the
        # two are not the same kind of evidence: a label match is a guess the
        # Builder must refuse under invariant 4, while this is the Integrator's
        # own record of a transaction it committed under an approved Decision.
        # Without it, a GUR authored before a merge integrates cannot be
        # compiled at all -- the retired ID resolves to nothing, and the label
        # fallback then finds the survivor and correctly refuses to trust it.
        retirement = self.retirements.get(requested)
        if retirement:
            survivor = retirement.get("replaced_by", "")
            if survivor in self.nodes:
                return Resolution(
                    requested,
                    survivor,
                    "retired_replacement",
                    True,
                    f"{requested} was retired into {survivor} by "
                    f"{retirement.get('integration_id') or 'an integration'} under "
                    f"{retirement.get('authority') or 'an approved Decision'}",
                    retirement_authority=retirement.get("authority", ""),
                    retirement_integration_id=retirement.get("integration_id", ""),
                )

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
