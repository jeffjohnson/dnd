"""The active ruleset's vocabulary, read from its own Constitution.

DEC-2026-0092. Before this module the transaction found the node-prefix table by
splitting on the literal heading `### 3.1 Format` and rejected any parse of
fewer than twenty prefixes. Both are AD&D facts. Shadowdark Constitution 1.2
carries its prefix table under `## 2. Node Identity` and declares thirteen
prefixes, so the first Shadowdark transaction raised `IndexError` before it had
read a single bundle.

The edge-type and derived-polarity vocabularies had the same defect in a quieter
form: they were transcribed into `derive.py` from AD&D constitution section 6.1.
Shadowdark happens to declare the same ten derived types, so the transcription
agreed by luck. Nothing detected divergence, which is the same failure mode as
the heading, only deferred.

So every vocabulary here is located by *table structure* -- the header cells a
table declares -- and never by a section number, a heading string, or an
expected row count. A ruleset that does not declare a required table fails
closed, before a transaction starts, rather than silently inheriting AD&D's.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

# Polarity and basis *values* are stated as prose in both constitutions rather
# than as a table, so they stay shared constants. They are used only to
# recognize which rows of a polarity table state a derived polarity; the
# per-ruleset mapping itself is always read from that ruleset's own table.
POLARITY_VALUES = ("inflicts", "improves", "worsens", "negates", "enables", "governs", "neutral")
POLARITY_BASIS_VALUES = ("derived", "read", "heuristic", "unset")

PREFIX_PATTERN = re.compile(r"^[a-z][a-z0-9]*_$")
EDGE_TYPE_PATTERN = re.compile(r"^[A-Z][A-Z_]+$")


class VocabularyError(ValueError):
    """A constitution does not declare a vocabulary this package requires.

    Raised before any transaction begins. Failing closed is the point: the
    alternative is a ruleset silently inheriting another ruleset's ontology,
    which `contracts/GRAPH_INVARIANTS.md` invariant 27 and the Shadowdark
    constitution's "matching IDs in other rulesets are unrelated identities"
    both forbid.
    """


def _clean(cell: str) -> str:
    """One table cell, stripped of Markdown emphasis and code ticks."""
    return cell.strip().strip("`").replace("**", "").strip()


def _tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    """Every Markdown pipe table in the document, as (header cells, rows).

    A table is a `|`-led line followed by a delimiter row. Locating tables this
    way means an Architect may renumber, retitle, or move a section without
    breaking the transaction, which is exactly what went wrong before.
    """
    def cells(line: str) -> list[str]:
        return [_clean(c) for c in line.strip().strip("|").split("|")]

    def is_delimiter(line: str) -> bool:
        stripped = line.strip()
        return (stripped.startswith("|")
                and set(stripped) <= set("|-: \t")
                and "-" in stripped)

    lines = text.splitlines()
    found = []
    index = 0
    while index < len(lines) - 1:
        line = lines[index]
        if line.strip().startswith("|") and is_delimiter(lines[index + 1]):
            header = cells(line)
            rows = []
            cursor = index + 2
            while cursor < len(lines) and lines[cursor].strip().startswith("|"):
                rows.append(cells(lines[cursor]))
                cursor += 1
            found.append((header, rows))
            index = cursor
            continue
        index += 1
    return found


def _header_is(header: list[str], first: str, *contains: str) -> bool:
    if not header or header[0].strip().lower() != first:
        return False
    for position, needle in enumerate(contains, start=1):
        if position >= len(header) or needle not in header[position].lower():
            return False
    return True


@dataclass(frozen=True)
class RulesetVocabulary:
    """What one ruleset's Constitution declares that the transaction enforces."""

    ruleset_id: str
    prefixes: frozenset[str]
    edge_types: tuple[str, ...]
    derived_polarity: dict[str, str]
    authored_types: tuple[str, ...]
    citation_books: frozenset[str]

    def polarity_for(self, edge_type: str) -> tuple[str, str] | None:
        """(polarity, basis) when the build owns it, or None when authored."""
        if edge_type in self.derived_polarity:
            return self.derived_polarity[edge_type], "derived"
        return None


def read_prefixes(text: str) -> frozenset[str]:
    """The node-prefix table, located by its `Prefix | Kind` header."""
    for header, rows in _tables(text):
        if not _header_is(header, "prefix", "kind"):
            continue
        found = {_clean(row[0]) for row in rows
                 if row and PREFIX_PATTERN.match(_clean(row[0]))}
        if not found:
            raise VocabularyError(
                "the constitution's Prefix table declares no usable node prefix; "
                "each row's first cell must be a snake_case prefix ending in '_'")
        return frozenset(found)
    raise VocabularyError(
        "the constitution declares no node-prefix table; expected a Markdown "
        "table whose header begins 'Prefix | Kind'")


def read_edge_types(text: str) -> tuple[str, ...]:
    """The closed edge vocabulary, located by its `Type | Meaning | Direction` header."""
    for header, rows in _tables(text):
        if not _header_is(header, "type", "meaning", "direction"):
            continue
        found = [_clean(row[0]) for row in rows
                 if row and EDGE_TYPE_PATTERN.match(_clean(row[0]))]
        if not found:
            raise VocabularyError(
                "the constitution's edge-vocabulary table declares no edge type")
        if len(set(found)) != len(found):
            raise VocabularyError(
                "the constitution's edge-vocabulary table declares a duplicate edge type")
        return tuple(found)
    raise VocabularyError(
        "the constitution declares no edge-vocabulary table; expected a Markdown "
        "table whose header begins 'Type | Meaning | Direction'")


def read_derived_polarity(text: str, edge_types: tuple[str, ...]) -> dict[str, str]:
    """The derivation table, located by its `Edge type | ...polarity...` header.

    Both shapes in the repository are accepted without special-casing either
    ruleset: AD&D writes three columns and states the basis per row, Shadowdark
    writes two and states the basis in prose. A row counts as derived only when
    its polarity is a legal value *and* it does not declare some other basis, so
    AD&D's second table -- the authored types, whose polarity cell reads
    'Analyst-authored' -- contributes nothing rather than needing to be skipped
    by position.
    """
    found: dict[str, str] = {}
    saw_table = False
    for header, rows in _tables(text):
        if not _header_is(header, "edge type", "polarity"):
            continue
        saw_table = True
        for row in rows:
            if len(row) < 2:
                continue
            edge_type = _clean(row[0])
            polarity = _clean(row[1]).lower()
            basis = _clean(row[2]).lower() if len(row) > 2 else "derived"
            if polarity not in POLARITY_VALUES or basis != "derived":
                continue
            if not EDGE_TYPE_PATTERN.match(edge_type):
                raise VocabularyError(
                    f"the constitution's polarity table names {edge_type!r}, "
                    "which is not an edge-type identifier")
            if edge_type not in edge_types:
                raise VocabularyError(
                    f"the constitution's polarity table derives {edge_type}, which its "
                    "own edge vocabulary does not declare")
            if edge_type in found and found[edge_type] != polarity:
                raise VocabularyError(
                    f"the constitution derives two different polarities for {edge_type}: "
                    f"{found[edge_type]} and {polarity}")
            found[edge_type] = polarity
    if not saw_table:
        raise VocabularyError(
            "the constitution declares no derived-polarity table; expected a Markdown "
            "table whose header begins 'Edge type' and names a polarity column")
    if not found:
        raise VocabularyError(
            "the constitution's derived-polarity table states no derived polarity; "
            f"a polarity cell must be one of {POLARITY_VALUES}")
    return found


def read_citation_books(books_registry: Path) -> frozenset[str]:
    """Legal citation codes for invariant 9, from the ruleset's book registry.

    The registry rather than the constitution because that is where a book's
    citation code is actually declared, and `contracts/SCOPE_AND_IDENTITY.md`
    makes the registry authoritative for book identity.
    """
    path = Path(books_registry)
    if not path.exists():
        raise VocabularyError(f"the ruleset declares no book registry at {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    codes = {str(b["citation_code"]) for b in data.get("books", []) if b.get("citation_code")}
    if not codes:
        raise VocabularyError(f"{path} registers no book citation code")
    return frozenset(codes)


def load_vocabulary(root: Path, ruleset_id: str) -> RulesetVocabulary:
    """Everything the transaction needs from one ruleset's own governance."""
    ruleset_root = Path(root) / "rulesets" / ruleset_id
    constitution = ruleset_root / "governance" / "constitution.md"
    if not constitution.exists():
        raise VocabularyError(f"{ruleset_id} has no constitution at {constitution}")
    text = constitution.read_text(encoding="utf-8")

    edge_types = read_edge_types(text)
    derived = read_derived_polarity(text, edge_types)
    return RulesetVocabulary(
        ruleset_id=ruleset_id,
        prefixes=read_prefixes(text),
        edge_types=edge_types,
        derived_polarity=derived,
        authored_types=tuple(t for t in edge_types if t not in derived),
        citation_books=read_citation_books(ruleset_root / "registries" / "books.yaml"),
    )
