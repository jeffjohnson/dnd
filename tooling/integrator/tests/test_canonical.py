"""Serialization fidelity against the real canonical corpus.

If these fail, an integration would rewrite thousands of lines it did not
change and the commit would stop being reviewable.
"""

from __future__ import annotations

import io
import unittest

import _bootstrap
from _bootstrap import REPO_ROOT, RULESET_ID

from adnd1e_integrator.canonical import (
    EDGE_COLUMNS,
    NODE_COLUMNS,
    CanonicalGraph,
    CanonicalPaths,
    read_csv_rows,
    write_csv_rows,
    write_graph_json,
)


class TestSerialization(unittest.TestCase):
    def setUp(self):
        self.paths = CanonicalPaths(root=REPO_ROOT, ruleset_id=RULESET_ID)

    def test_edges_round_trip_byte_identical(self):
        original = self.paths.edges.read_bytes()
        rows = read_csv_rows(self.paths.edges)
        out = REPO_ROOT / "build" / "tmp-test-edges.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        write_csv_rows(out, EDGE_COLUMNS, rows)
        try:
            self.assertEqual(out.read_bytes(), original)
        finally:
            out.unlink(missing_ok=True)

    def test_nodes_round_trip_byte_identical(self):
        original = self.paths.nodes.read_bytes()
        rows = read_csv_rows(self.paths.nodes)
        out = REPO_ROOT / "build" / "tmp-test-nodes.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        write_csv_rows(out, NODE_COLUMNS, rows)
        try:
            self.assertEqual(out.read_bytes(), original)
        finally:
            out.unlink(missing_ok=True)

    def test_graph_json_regenerates_byte_identical(self):
        original = self.paths.graph_json.read_bytes()
        graph = CanonicalGraph.load(self.paths)
        out = REPO_ROOT / "build" / "tmp-test-graph.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        write_graph_json(out, graph.to_graph_json())
        try:
            self.assertEqual(out.read_bytes(), original)
        finally:
            out.unlink(missing_ok=True)

    def test_edge_header_is_the_production_contract(self):
        header = self.paths.edges.read_bytes().decode("utf-8").splitlines()[0]
        self.assertEqual(header.split(","), EDGE_COLUMNS)
        self.assertEqual(len(EDGE_COLUMNS), 18)


if __name__ == "__main__":
    unittest.main()
