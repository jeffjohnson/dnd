"""The global invariant suite (`contracts/GRAPH_INVARIANTS.md`).

Checks the mechanically decidable invariants over whole canonical state. The
ones requiring source interpretation (5, 8, 24, and the source-support half of
11) belong to the Reviewer and are reported here as `not_machine_checkable`
rather than silently passed.

Two results matter to an integration:

- `blocking` findings caused by rows this batch introduces, which must abort it;
- `baseline` findings that already existed, which must be reported but must not
  let a batch mutate them silently.

Separating the two is what lets a repository with known legacy defects still
accept a clean patch, without the patch inheriting an alibi for new breakage.
"""

from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field
from pathlib import Path

from .derive import (
    AUTHORED_TYPES,
    DERIVED_POLARITY,
    EDGE_TYPES,
    POLARITY_BASIS_VALUES,
    POLARITY_VALUES,
    Degrees,
    derive_polarity,
)

BOOKS = ("PHB", "DMG", "UA", "MM")
EVIDENCE_CLASSES = (
    "explicit_rule", "explicit_reference", "inferred_rule",
    "analytic_classification", "speculative",
)
STATUS_VALUES = ("core", "optional")
SUPERSESSION_BASIS = (
    "later_publication", "explicit_replacement", "conflicting_procedure", "optional_variant",
)
REVIEW_FLAGS = ("class_level_conflation", "mm_keyword_derived", "grouped_entry_attribution")

# Invariant 12. The Builder's documented assertion key; the narrowest tuple under
# which the canonical corpus is duplicate-free. ALTERNATIVE_TO is symmetric, so
# its endpoints are sorted before comparison.
ASSERTION_KEY = ("source_id", "edge_type", "target_id", "aspect", "condition")

ID_PATTERN = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)+$")

# Invariant 11: magnitudes, dice, bonuses, thresholds out of aspect and condition.
MAGNITUDE = re.compile(r"\d")


def approved_prefixes(constitution: Path) -> frozenset[str]:
    """Read the section 3.1 prefix table rather than transcribing it.

    A transcribed copy goes stale the moment the Architect amends the
    constitution, and the Integrator is forbidden from resolving ontology
    questions -- so the constitution has to be the live source.
    """
    text = Path(constitution).read_text(encoding="utf-8")
    section = text.split("### 3.1 Format", 1)[1].split("### 3.2", 1)[0]
    found = re.findall(r"^\|\s*`([a-z]+_)`\s*\|", section, re.MULTILINE)
    if len(found) < 20:
        raise ValueError(
            f"parsed only {len(found)} node prefixes from constitution section 3.1; "
            "the table format changed and this parser must be updated"
        )
    return frozenset(found)


@dataclass
class Finding:
    invariant: int
    rule: str
    detail: str
    row: int | None = None
    edge: str | None = None

    def as_dict(self) -> dict:
        out = {"invariant": self.invariant, "rule": self.rule, "detail": self.detail}
        if self.row is not None:
            out["row"] = self.row
        if self.edge is not None:
            out["edge"] = self.edge
        return out


@dataclass
class Result:
    findings: list[Finding] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)
    not_machine_checkable: list[str] = field(default_factory=list)

    def add(self, invariant: int, rule: str, detail: str, row=None, edge=None) -> None:
        self.findings.append(Finding(invariant, rule, detail, row, edge))

    @property
    def ok(self) -> bool:
        return not self.findings

    def by_invariant(self) -> dict[int, int]:
        counts = collections.Counter(f.invariant for f in self.findings)
        return dict(sorted(counts.items()))


def edge_ref(edge: dict) -> str:
    return f"{edge['source_id']} {edge['edge_type']} {edge['target_id']}"


def assertion_key(edge: dict) -> tuple:
    source, target = edge["source_id"], edge["target_id"]
    if edge["edge_type"] == "ALTERNATIVE_TO":
        source, target = sorted((source, target))
    return (source, edge["edge_type"], target, edge["aspect"], edge["condition"])


def check(
    edges: list[dict[str, str]],
    nodes: list[dict[str, str]],
    prefixes: frozenset[str],
    general_rule_ids: set[str],
    columns: list[str],
) -> Result:
    """Run every machine-checkable invariant over the supplied canonical state."""
    result = Result()
    node_ids = {n["id"] for n in nodes}

    result.checked = [
        "1 endpoints exist", "2 one canonical ID per node", "3 approved prefix and snake_case",
        "6 exact production columns", "7 legal edge type", "9 citation present",
        "10 one evidence class", "11 no magnitude in aspect/condition",
        "12 no duplicate assertion identity", "13/14/17 derived polarity owned by build",
        "15/16 authored polarity resolved", "18/19 general_rule_id gating",
        "20 supersession_basis gating", "22 derived roles match recomputation",
    ]
    result.not_machine_checkable = [
        "4 labels do not determine identity (advisory; IDs are compared everywhere)",
        "5 rule/table separation requires source judgement (Reviewer)",
        "8 direction follows the vocabulary requires source judgement (Reviewer)",
        "21 provenance retention is checked against the integration manifest, not the CSV",
        "23/24/25 governance invariants; no severity column exists to violate 25",
        "26-32 workflow invariants enforced by role tooling and queue lineage",
    ]

    # -- invariant 2: one row per node ID ------------------------------------
    seen_nodes = collections.Counter(n["id"] for n in nodes)
    for node_id, count in seen_nodes.items():
        if count > 1:
            result.add(2, "one canonical ID per node", f"{node_id} appears {count} times in nodes_master")

    # -- invariant 3: node identity format -----------------------------------
    for node_id in sorted(node_ids):
        if not any(node_id.startswith(p) for p in prefixes):
            result.add(3, "approved prefix", f"{node_id} uses a prefix absent from constitution 3.1")
        if not ID_PATTERN.match(node_id):
            result.add(3, "snake_case", f"{node_id} is not prefixed snake_case")

    keys: dict[tuple, int] = {}

    for index, edge in enumerate(edges):
        row = index + 2  # 1-based, past the header
        ref = edge_ref(edge)

        # -- invariant 6 -----------------------------------------------------
        missing = [c for c in columns if c not in edge]
        extra = [c for c in edge if c not in columns]
        if missing or extra:
            result.add(6, "exact production columns",
                       f"missing={missing} extra={extra}", row, ref)

        # -- invariant 1 -----------------------------------------------------
        for side in ("source_id", "target_id"):
            if edge[side] not in node_ids:
                result.add(1, "endpoint exists", f"{side}={edge[side]} is not a canonical node", row, ref)

        # -- invariant 7 -----------------------------------------------------
        if edge["edge_type"] not in EDGE_TYPES:
            result.add(7, "legal edge type", f"{edge['edge_type']} is not one of the thirteen", row, ref)

        # -- invariant 9 -----------------------------------------------------
        if edge["book"] not in BOOKS:
            result.add(9, "citation book", f"book={edge['book']!r} is not one of {BOOKS}", row, ref)
        if not (edge["page"].strip() or edge["section"].strip()):
            result.add(9, "citation locus", "neither page nor section is present", row, ref)

        # -- invariant 10 ----------------------------------------------------
        if edge["evidence"] not in EVIDENCE_CLASSES:
            result.add(10, "one evidence class", f"evidence={edge['evidence']!r}", row, ref)

        # -- invariant 11 ----------------------------------------------------
        for column in ("aspect", "condition"):
            if MAGNITUDE.search(edge[column]):
                result.add(11, "no magnitude", f"{column}={edge[column]!r} contains a digit", row, ref)

        # -- status vocabulary (constitution section 8) ----------------------
        if edge["status"] not in STATUS_VALUES:
            result.add(7, "status vocabulary", f"status={edge['status']!r}", row, ref)

        # -- invariants 13, 14, 15, 16, 17 -----------------------------------
        if edge["polarity"] not in POLARITY_VALUES:
            result.add(17, "polarity vocabulary", f"polarity={edge['polarity']!r}", row, ref)
        if edge["polarity_basis"] not in POLARITY_BASIS_VALUES:
            result.add(17, "polarity_basis vocabulary", f"polarity_basis={edge['polarity_basis']!r}", row, ref)

        derived = derive_polarity(edge)
        if derived is not None:
            polarity, basis = derived
            if edge["polarity"] != polarity or edge["polarity_basis"] != basis:
                result.add(
                    17, "derived polarity matches the derivation table",
                    f"{edge['edge_type']} must be {polarity}/{basis}, found "
                    f"{edge['polarity']}/{edge['polarity_basis']}", row, ref)
        elif edge["edge_type"] in AUTHORED_TYPES:
            if edge["polarity_basis"] in ("unset", "heuristic"):
                result.add(
                    16, "no unresolved authored polarity",
                    f"{edge['edge_type']} carries polarity_basis={edge['polarity_basis']}", row, ref)

        # -- invariants 18, 19 -----------------------------------------------
        general_rule_id = edge["general_rule_id"].strip()
        if edge["pass"] == "general-rule":
            if not general_rule_id:
                result.add(18, "general_rule_id required", "pass=general-rule with no general_rule_id", row, ref)
            elif general_rule_id not in general_rule_ids:
                result.add(18, "general_rule_id resolves",
                           f"{general_rule_id} is not in the general-rule register", row, ref)
        elif general_rule_id:
            result.add(19, "general_rule_id only under an inherited rule",
                       f"general_rule_id={general_rule_id} with pass={edge['pass']}", row, ref)

        # -- invariant 20 ----------------------------------------------------
        basis_value = edge["supersession_basis"].strip()
        if edge["edge_type"] == "OVERRIDES":
            if not basis_value:
                result.add(20, "supersession_basis required on OVERRIDES", "value is empty", row, ref)
            elif basis_value not in SUPERSESSION_BASIS:
                result.add(20, "supersession_basis vocabulary", f"{basis_value!r}", row, ref)
        elif basis_value:
            result.add(20, "supersession_basis only on OVERRIDES",
                       f"{edge['edge_type']} carries {basis_value!r}", row, ref)

        # -- review_flag vocabulary (constitution section 5) -----------------
        flag = edge["review_flag"].strip()
        if flag and flag not in REVIEW_FLAGS:
            result.add(7, "review_flag vocabulary", f"review_flag={flag!r}", row, ref)

        # -- invariant 12 ----------------------------------------------------
        key = assertion_key(edge)
        if key in keys:
            result.add(12, "no duplicate assertion identity",
                       f"identical assertion key to row {keys[key]}", row, ref)
        else:
            keys[key] = row

    return result


def check_derived_state(
    edges: list[dict[str, str]],
    nodes: list[dict[str, str]],
    thresholds: dict,
    result: Result,
) -> None:
    """Invariant 22: stored degrees and roles must equal a fresh recomputation."""
    degrees = Degrees(edges)
    for node in nodes:
        node_id = node["id"]
        expected = {
            "in_degree": degrees.inbound[node_id],
            "out_degree": degrees.outbound[node_id],
            "degree": degrees.degree(node_id),
            "core_degree": degrees.core[node_id],
        }
        for column, want in expected.items():
            if int(node[column]) != want:
                result.add(22, "derived degree matches recomputation",
                           f"{node_id}.{column} stored {node[column]}, recomputed {want}")
        want_roles = "|".join(sorted(degrees.roles(node_id, thresholds)))
        if node["roles"] != want_roles:
            result.add(22, "derived roles match recomputation",
                       f"{node_id} stored roles {node['roles']!r}, recomputed {want_roles!r}")
