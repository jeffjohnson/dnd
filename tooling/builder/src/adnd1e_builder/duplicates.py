"""Duplicate detection and local-neighborhood conflict analysis.

Invariant 12 forbids duplicate edge identity. The assertion key is defined in
`vocab.ASSERTION_KEY`; it is the tuple under which the canonical corpus is
duplicate-free, so widening it here would silently admit duplicates.

Three grades are reported, because they need different dispositions:

exact      identical assertion key -> the edge must not be inserted again
near       same endpoints and type, different aspect/condition -> Reviewer call
neighbour  same endpoints, any type/direction -> context, not a defect
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .vocab import ASSERTION_KEY, SYMMETRIC_EDGE_TYPES


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def assertion_key(edge: dict) -> tuple:
    """The identity of an assertion, per invariant 12."""
    key = tuple(_normalize_text(edge.get(f, "")) for f in ASSERTION_KEY)
    if edge.get("edge_type") in SYMMETRIC_EDGE_TYPES:
        # Symmetric types assert the same thing with endpoints swapped.
        source, edge_type, target, *rest = key
        endpoints = tuple(sorted((source, target)))
        return (endpoints[0], edge_type, endpoints[1], *rest)
    return key


def endpoint_type_key(edge: dict) -> tuple[str, str, str]:
    source = (edge.get("source_id") or "").strip()
    target = (edge.get("target_id") or "").strip()
    edge_type = (edge.get("edge_type") or "").strip()
    if edge_type in SYMMETRIC_EDGE_TYPES:
        source, target = sorted((source, target))
    return (source, edge_type, target)


def endpoint_pair(edge: dict) -> tuple[str, str]:
    source = (edge.get("source_id") or "").strip()
    target = (edge.get("target_id") or "").strip()
    return tuple(sorted((source, target)))  # type: ignore[return-value]


@dataclass
class CanonicalEdges:
    """`rulesets/<ruleset>/canonical/edges_master.csv`, read-only to the Builder."""

    path: Path
    rows: list[dict] = field(default_factory=list)
    by_assertion: dict[tuple, list[int]] = field(default_factory=lambda: defaultdict(list))
    by_endpoint_type: dict[tuple, list[int]] = field(default_factory=lambda: defaultdict(list))
    by_pair: dict[tuple, list[int]] = field(default_factory=lambda: defaultdict(list))

    @classmethod
    def load(cls, path: str | Path) -> "CanonicalEdges":
        path = Path(path)
        store = cls(path=path)
        with path.open(newline="", encoding="utf-8") as handle:
            for index, row in enumerate(csv.DictReader(handle)):
                store.rows.append(row)
                store.by_assertion[assertion_key(row)].append(index)
                store.by_endpoint_type[endpoint_type_key(row)].append(index)
                store.by_pair[endpoint_pair(row)].append(index)
        return store

    def _describe(self, index: int) -> dict:
        row = self.rows[index]
        return {
            # `canonical_row` is the 1-based line number in the CSV including
            # its header, for a human opening the file. `canonical_index` is the
            # list position, for code. Keep both; deriving one from the other at
            # the call site is an off-by-one waiting to happen.
            "canonical_row": index + 2,
            "canonical_index": index,
            "source_id": row["source_id"],
            "edge_type": row["edge_type"],
            "target_id": row["target_id"],
            "aspect": row["aspect"],
            "condition": row["condition"],
            "book": row["book"],
            "page": row["page"],
            "section": row["section"],
        }

    def exact_matches(self, edge: dict) -> list[dict]:
        return [self._describe(i) for i in self.by_assertion.get(assertion_key(edge), [])]

    def near_matches(self, edge: dict) -> list[dict]:
        exact = set(self.by_assertion.get(assertion_key(edge), []))
        return [
            self._describe(i)
            for i in self.by_endpoint_type.get(endpoint_type_key(edge), [])
            if i not in exact
        ]

    def neighbourhood(self, edge: dict) -> list[dict]:
        seen = set(self.by_endpoint_type.get(endpoint_type_key(edge), []))
        return [self._describe(i) for i in self.by_pair.get(endpoint_pair(edge), []) if i not in seen]

    def reversed_edges(self, edge: dict) -> list[dict]:
        """Canonical edges joining the same pair in the opposite direction."""
        source = (edge.get("source_id") or "").strip()
        target = (edge.get("target_id") or "").strip()
        return [
            self._describe(i)
            for i in self.by_pair.get(endpoint_pair(edge), [])
            if self.rows[i]["source_id"] == target and self.rows[i]["target_id"] == source
        ]

    def incident(self, node_id: str) -> list[dict]:
        return [
            self._describe(i)
            for i, row in enumerate(self.rows)
            if row["source_id"] == node_id or row["target_id"] == node_id
        ]


def intra_patch_duplicates(edges: list[dict]) -> list[dict]:
    """Exact and near duplicate pairs inside one patch."""
    findings: list[dict] = []

    by_assertion: dict[tuple, list[dict]] = defaultdict(list)
    for edge in edges:
        by_assertion[assertion_key(edge)].append(edge)
    for group in by_assertion.values():
        if len(group) > 1:
            refs = [e["ref"] for e in group]
            for edge in group[1:]:
                findings.append(
                    {
                        "grade": "exact",
                        "ref": edge["ref"],
                        "conflicts_with": [r for r in refs if r != edge["ref"]],
                        "detail": (
                            f"identical assertion key to {', '.join(r for r in refs if r != edge['ref'])} "
                            f"within this patch (invariant 12)"
                        ),
                    }
                )

    by_endpoint: dict[tuple, list[dict]] = defaultdict(list)
    for edge in edges:
        by_endpoint[endpoint_type_key(edge)].append(edge)
    for group in by_endpoint.values():
        if len(group) < 2:
            continue
        keys = {assertion_key(e) for e in group}
        if len(keys) == 1:
            continue  # already reported as exact
        refs = [e["ref"] for e in group]
        findings.append(
            {
                "grade": "near",
                "ref": refs[0],
                "conflicts_with": refs[1:],
                "detail": (
                    f"{len(group)} edges share endpoints and type "
                    f"({group[0]['source_id']} {group[0]['edge_type']} {group[0]['target_id']}) "
                    f"but differ in aspect or condition; Reviewer must confirm they are "
                    f"distinct assertions rather than one restated"
                ),
            }
        )

    return findings


def self_edges(edges: list[dict]) -> list[dict]:
    """Invariant: self-edges are legal only with explicit justification."""
    return [
        {
            "ref": edge["ref"],
            "node": edge["source_id"],
            "edge_type": edge["edge_type"],
            "detail": (
                f"self-edge {edge['source_id']} {edge['edge_type']} {edge['target_id']}; "
                f"legal only with explicit justification (Builder instruction 11)"
            ),
        }
        for edge in edges
        if edge.get("source_id") and edge.get("source_id") == edge.get("target_id")
    ]
