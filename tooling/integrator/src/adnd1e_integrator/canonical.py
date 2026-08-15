"""Canonical graph storage: exact readers and writers.

The Integrator owns the canonical storage format. The three canonical files are
the authoritative representation; `graph.json` is generated from the tabular
data and is never edited independently (role instructions, "Programmatic
ownership").

Serialization was reverse-engineered from the existing corpus and is asserted by
`tests/test_canonical.py`, which round-trips the real files byte-for-byte:

- CSV: UTF-8, CRLF terminators, `csv` module QUOTE_MINIMAL, trailing newline.
- JSON: `indent=1`, CRLF, and **no** trailing newline.

Writing anything else would produce a diff of thousands of unrelated lines and
destroy the reviewability of an integration commit.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path

# Constitution section 5 / section 12. edges_master.csv is authoritative for order.
EDGE_COLUMNS = [
    "source_id", "source_label", "edge_type", "target_id", "target_label",
    "aspect", "condition", "polarity", "polarity_basis",
    "book", "page", "section", "evidence", "pass", "status",
    "supersession_basis", "general_rule_id", "review_flag",
]

NODE_COLUMNS = ["id", "label", "kind", "degree", "core_degree", "in_degree", "out_degree", "roles"]
REGISTRY_COLUMNS = ["id", "label", "kind", "degree", "roles"]

GRAPH_SCHEMA_VERSION = "1.2"

CRLF = "\r\n"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    text = Path(path).read_bytes().decode("utf-8")
    return list(csv.DictReader(io.StringIO(text, newline="")))


def write_csv_rows(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator=CRLF)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(c, "") for c in columns])
    Path(path).write_bytes(buf.getvalue().encode("utf-8"))


def write_graph_json(path: Path, payload: dict) -> None:
    text = json.dumps(payload, indent=1, ensure_ascii=False).replace("\n", CRLF)
    Path(path).write_bytes(text.encode("utf-8"))


@dataclass
class RegistryRow:
    """One approved node ID, plus the exact terminator its line already used."""

    values: dict[str, str]
    terminator: str = CRLF


class Registry:
    """`registries/nodes.csv` — the list of approved node IDs, sorted by ID.

    `degree` and `roles` are a derived snapshot of canonical state, so they are
    rebuilt from the post-batch graph on every integration. Rows for IDs that are
    approved but carry no edge stay at degree 0.

    The file on disk mixes terminators: nine lines in the `race_` block end with
    a bare LF while the other 1,088 use CRLF. Normalizing them would rewrite
    lines this batch has no business touching, so each existing line keeps its
    own terminator and only rows added here are written CRLF. The mixed-terminator
    defect is reported, not silently repaired.
    """

    def __init__(self, header: str, rows: list[RegistryRow], header_terminator: str = CRLF):
        self.header = header
        self.header_terminator = header_terminator
        self.rows = rows

    @classmethod
    def load(cls, path: Path) -> "Registry":
        text = Path(path).read_bytes().decode("utf-8")
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()  # trailing newline, not a row

        def split(line: str) -> tuple[str, str]:
            return (line[:-1], CRLF) if line.endswith("\r") else (line, "\n")

        header, header_terminator = split(lines[0])
        rows = []
        for line in lines[1:]:
            content, terminator = split(line)
            values = next(csv.reader(io.StringIO(content, newline="")))
            rows.append(RegistryRow(values=dict(zip(REGISTRY_COLUMNS, values)),
                                    terminator=terminator))
        return cls(header=header, rows=rows, header_terminator=header_terminator)

    @property
    def ids(self) -> set[str]:
        return {r.values["id"] for r in self.rows}

    def add(self, values: dict[str, str]) -> None:
        """Insert a new approved ID in sorted position."""
        row = RegistryRow(values={c: values.get(c, "") for c in REGISTRY_COLUMNS})
        position = len(self.rows)
        for index, existing in enumerate(self.rows):
            if existing.values["id"] > row.values["id"]:
                position = index
                break
        self.rows.insert(position, row)

    def replace(self, retired_id: str, values: dict[str, str]) -> None:
        """Retire one approved ID and register its replacement, leaving no alias.

        The retired row is removed rather than kept as a pointer: `decision_
        migration_v1` prohibits retaining a retired ID as an alias or duplicate
        registry row, so the replacement is an in-place identity swap and the
        file stays sorted by ID.
        """
        remaining = [r for r in self.rows if r.values["id"] != retired_id]
        if len(remaining) == len(self.rows):
            raise KeyError(f"{retired_id} is not in the registry")
        self.rows = remaining
        self.add(values)

    def save(self, path: Path) -> None:
        out = io.StringIO(newline="")
        out.write(self.header + self.header_terminator)
        for row in self.rows:
            buf = io.StringIO(newline="")
            csv.writer(buf, lineterminator="").writerow(
                [row.values.get(c, "") for c in REGISTRY_COLUMNS])
            out.write(buf.getvalue() + row.terminator)
        Path(path).write_bytes(out.getvalue().encode("utf-8"))


@dataclass(frozen=True)
class CanonicalPaths:
    """Every file this package may write, resolved from the ruleset root."""

    root: Path
    ruleset_id: str

    @property
    def canonical_dir(self) -> Path:
        return self.root / "rulesets" / self.ruleset_id / "canonical"

    @property
    def edges(self) -> Path:
        return self.canonical_dir / "edges_master.csv"

    @property
    def nodes(self) -> Path:
        return self.canonical_dir / "nodes_master.csv"

    @property
    def graph_json(self) -> Path:
        return self.canonical_dir / "graph.json"

    @property
    def registry(self) -> Path:
        return self.root / "rulesets" / self.ruleset_id / "registries" / "nodes.csv"

    @property
    def manifests_dir(self) -> Path:
        return self.root / "rulesets" / self.ruleset_id / "manifests"

    @property
    def reports_dir(self) -> Path:
        return self.root / "rulesets" / self.ruleset_id / "reports"

    def writable(self) -> list[Path]:
        """Files the transactional applier snapshots and may restore.

        The node registry is included because an approved registry addition is
        applied inside the same transaction as the edges that depend on it; a
        rollback must not leave a registered node with no edges.
        """
        return [self.edges, self.nodes, self.graph_json, self.registry]


class CanonicalGraph:
    """In-memory canonical state. Load, mutate through the applier, then save."""

    def __init__(self, edges: list[dict[str, str]], nodes: list[dict[str, str]]):
        self.edges = edges
        self.nodes = nodes

    @classmethod
    def load(cls, paths: CanonicalPaths) -> "CanonicalGraph":
        return cls(read_csv_rows(paths.edges), read_csv_rows(paths.nodes))

    @property
    def node_ids(self) -> set[str]:
        return {n["id"] for n in self.nodes}

    def node_labels(self) -> dict[str, str]:
        return {n["id"]: n["label"] for n in self.nodes}

    def save(self, paths: CanonicalPaths) -> None:
        write_csv_rows(paths.edges, EDGE_COLUMNS, self.edges)
        write_csv_rows(paths.nodes, NODE_COLUMNS, self.nodes)
        write_graph_json(paths.graph_json, self.to_graph_json())

    def to_graph_json(self) -> dict:
        basis: dict[str, int] = {}
        for edge in self.edges:
            key = edge["polarity_basis"]
            basis[key] = basis.get(key, 0) + 1
        return {
            "meta": {
                "schema_version": GRAPH_SCHEMA_VERSION,
                "edges": len(self.edges),
                "nodes": len(self.nodes),
                "polarity_basis": basis,
            },
            "nodes": [
                {
                    "id": n["id"],
                    "label": n["label"],
                    "kind": n["kind"],
                    "degree": int(n["degree"]),
                    "core_degree": int(n["core_degree"]),
                    "in_degree": int(n["in_degree"]),
                    "out_degree": int(n["out_degree"]),
                }
                for n in self.nodes
            ],
            "edges": [{c: e.get(c, "") for c in EDGE_COLUMNS} for e in self.edges],
        }
