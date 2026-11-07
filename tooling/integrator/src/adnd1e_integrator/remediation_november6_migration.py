"""November 6 Remediation Migration Script (Integrator).

Governing Decision: DEC-2026-0110
Audit Reference: audit.11.06.2026/remediation_register.json (R01, R02, R08)

Actions:
1. Deletes the 2 false Priest edges (R01):
   - spell_hold_person -> CLASSIFIED_AS -> class_priest (SD p.51/p.57 Wizard-only)
   - spell_dispel_magic -> CLASSIFIED_AS -> class_priest (SD p.51/p.57 Wizard-only)
2. Adds the 10 missing CS1 Witch edges (R02):
   - spell_charm_person (Tier 1, CS1 p.24) -> CLASSIFIED_AS -> class_witch
   - spell_alter_self (Tier 2, CS1 p.24) -> CLASSIFIED_AS -> class_witch
   - spell_augury (Tier 2, CS1 p.24) -> CLASSIFIED_AS -> class_witch
   - spell_invisibility (Tier 2, CS1 p.24) -> CLASSIFIED_AS -> class_witch
   - spell_speak_with_dead (Tier 3, CS1 p.24) -> CLASSIFIED_AS -> class_witch
   - spell_dimension_door (Tier 4, CS1 p.24) -> CLASSIFIED_AS -> class_witch
   - spell_divination (Tier 4, CS1 p.24) -> CLASSIFIED_AS -> class_witch
   - spell_polymorph (Tier 4, CS1 p.24) -> CLASSIFIED_AS -> class_witch
   - spell_scrying (Tier 5, CS1 p.25) -> CLASSIFIED_AS -> class_witch
   - spell_shapechange (Tier 5, CS1 p.25) -> CLASSIFIED_AS -> class_witch
3. Restores canonical meta block (R08):
   - schema_version: 1.2
   - nodes count
   - edges count
   - polarity_basis breakdown
4. Recomputes all degree and core_degree metrics.
5. Re-derives canonical graph.json, nodes_master.csv, and edges_master.csv.
6. Creates snapshot in build/snapshots/INT-20261107-REL/.
"""

import collections
import csv
import io
import json
from pathlib import Path
import shutil
from typing import Dict, List, Set, Any

ROOT = Path(__file__).resolve().parents[4]
CANONICAL_DIR = ROOT / "rulesets" / "shadowdark" / "canonical"
GRAPH_JSON_PATH = CANONICAL_DIR / "graph.json"
NODES_CSV_PATH = CANONICAL_DIR / "nodes_master.csv"
EDGES_CSV_PATH = CANONICAL_DIR / "edges_master.csv"
GAPS_CSV_PATH = ROOT / "classification_gaps.csv"
SNAPSHOT_DIR = ROOT / "build" / "snapshots" / "INT-20261107-REL"

EDGE_COLUMNS = [
    "source_id", "source_label", "edge_type", "target_id", "target_label",
    "aspect", "condition", "polarity", "polarity_basis",
    "book", "page", "section", "evidence", "pass", "status",
    "supersession_basis", "general_rule_id", "review_flag",
]

NODE_COLUMNS = ["id", "label", "kind", "degree", "core_degree", "in_degree", "out_degree"]

TEN_CS1_WITCH_SPells = [
    ("spell_charm_person", "24"),
    ("spell_alter_self", "24"),
    ("spell_augury", "24"),
    ("spell_invisibility", "24"),
    ("spell_speak_with_dead", "24"),
    ("spell_dimension_door", "24"),
    ("spell_divination", "24"),
    ("spell_polymorph", "24"),
    ("spell_scrying", "25"),
    ("spell_shapechange", "25"),
]

FALSE_PRIEST_EDGES = {
    ("spell_hold_person", "CLASSIFIED_AS", "class_priest"),
    ("spell_dispel_magic", "CLASSIFIED_AS", "class_priest"),
}


def run_migration() -> Dict[str, Any]:
    print("=" * 60)
    print("Starting November 6 Remediation Migration...")
    print("=" * 60)

    # 1. Load existing canonical graph
    with open(GRAPH_JSON_PATH, "r", encoding="utf-8") as f:
        graph = json.load(f)

    nodes = graph["nodes"]
    edges = graph["edges"]
    nodes_dict = {n["id"]: n for n in nodes}

    print(f"Initial state: {len(nodes)} nodes, {len(edges)} edges")

    # 2. Remove false Priest edges (R01)
    retained_edges = []
    removed_edges = []
    for e in edges:
        key = (e["source_id"], e["edge_type"], e["target_id"])
        if key in FALSE_PRIEST_EDGES:
            removed_edges.append(e)
            print(f"Removed false edge: {key} (status={e.get('status')})")
        else:
            retained_edges.append(e)

    assert len(removed_edges) == 2, f"Expected 2 false edges removed, got {len(removed_edges)}"

    # 3. Add 10 CS1 Witch edges (R02)
    new_edges = []
    existing_keys = {(e["source_id"], e["edge_type"], e["target_id"]) for e in retained_edges}

    for sid, page in TEN_CS1_WITCH_SPells:
        assert sid in nodes_dict, f"Node {sid} not found in canonical nodes"
        key = (sid, "CLASSIFIED_AS", "class_witch")
        if key not in existing_keys:
            edge = {
                "source_id": sid,
                "source_label": nodes_dict[sid]["label"],
                "edge_type": "CLASSIFIED_AS",
                "target_id": "class_witch",
                "target_label": "Witch",
                "aspect": "casting class",
                "condition": "",
                "polarity": "neutral",
                "polarity_basis": "derived",
                "book": "CS1",
                "page": str(page),
                "section": "WITCH SPELLS",
                "evidence": "explicit_rule",
                "pass": "1",
                "status": "optional",
                "supersession_basis": "",
                "general_rule_id": "",
                "review_flag": "",
            }
            new_edges.append(edge)
            existing_keys.add(key)
            print(f"Added Witch edge: {sid} -> class_witch (CS1 p.{page})")

    assert len(new_edges) == 10, f"Expected 10 new Witch edges, got {len(new_edges)}"

    all_edges = retained_edges + new_edges
    print(f"Updated edge count: {len(all_edges)} (1801 - 2 + 10 = 1809)")
    assert len(all_edges) == 1809, f"Expected exactly 1809 edges, got {len(all_edges)}"

    # 4. Recompute degrees for all nodes
    in_degrees: collections.Counter = collections.Counter()
    out_degrees: collections.Counter = collections.Counter()
    core_degrees: collections.Counter = collections.Counter()

    for e in all_edges:
        s = e["source_id"]
        t = e["target_id"]
        out_degrees[s] += 1
        in_degrees[t] += 1
        if e.get("status") == "core":
            core_degrees[s] += 1
            core_degrees[t] += 1

    updated_nodes = []
    for n in nodes:
        nid = n["id"]
        ind = in_degrees[nid]
        outd = out_degrees[nid]
        tot = ind + outd
        cd = core_degrees[nid]
        updated_nodes.append({
            "id": nid,
            "label": n["label"],
            "kind": n["kind"],
            "degree": tot,
            "core_degree": cd,
            "in_degree": ind,
            "out_degree": outd,
        })

    # Sort deterministically
    updated_nodes.sort(key=lambda x: x["id"])
    all_edges.sort(key=lambda e: (e["source_id"], e["edge_type"], e["target_id"], e.get("book", ""), str(e.get("page", ""))))

    # 5. Build canonical graph payload with meta block (R08)
    polarity_basis_counts = collections.Counter(e["polarity_basis"] for e in all_edges)
    meta = {
        "schema_version": "1.2",
        "edges": len(all_edges),
        "nodes": len(updated_nodes),
        "polarity_basis": {
            k: polarity_basis_counts[k]
            for k in sorted(polarity_basis_counts.keys())
        },
    }

    canonical_payload = {
        "meta": meta,
        "nodes": updated_nodes,
        "edges": all_edges,
    }

    # 6. Save canonical files (CRLF, exact formatting)
    CRLF = "\r\n"

    # Save graph.json (indent=1, CRLF, no trailing newline)
    json_text = json.dumps(canonical_payload, indent=1, ensure_ascii=False).replace("\n", CRLF)
    GRAPH_JSON_PATH.write_bytes(json_text.encode("utf-8"))
    print(f"Saved canonical graph.json ({len(updated_nodes)} nodes, {len(all_edges)} edges)")

    # Save nodes_master.csv
    buf_nodes = io.StringIO(newline="")
    writer_nodes = csv.writer(buf_nodes, lineterminator=CRLF)
    writer_nodes.writerow(NODE_COLUMNS)
    for n in updated_nodes:
        writer_nodes.writerow([n[c] for c in NODE_COLUMNS])
    NODES_CSV_PATH.write_bytes(buf_nodes.getvalue().encode("utf-8"))
    print(f"Saved canonical nodes_master.csv")

    # Save edges_master.csv
    buf_edges = io.StringIO(newline="")
    writer_edges = csv.writer(buf_edges, lineterminator=CRLF)
    writer_edges.writerow(EDGE_COLUMNS)
    for e in all_edges:
        writer_edges.writerow([e.get(c, "") for c in EDGE_COLUMNS])
    EDGES_CSV_PATH.write_bytes(buf_edges.getvalue().encode("utf-8"))
    print(f"Saved canonical edges_master.csv")

    # 7. Create Snapshot INT-20261107-REL
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(GRAPH_JSON_PATH, SNAPSHOT_DIR / "graph.json")
    shutil.copy2(NODES_CSV_PATH, SNAPSHOT_DIR / "nodes_master.csv")
    shutil.copy2(EDGES_CSV_PATH, SNAPSHOT_DIR / "edges_master.csv")
    if GAPS_CSV_PATH.exists():
        shutil.copy2(GAPS_CSV_PATH, SNAPSHOT_DIR / "classification_gaps.csv")
    print(f"Created snapshot at {SNAPSHOT_DIR}")

    print("=" * 60)
    print("Migration completed successfully!")
    print(f"Meta: {meta}")
    print("=" * 60)

    return {
        "status": "success",
        "nodes": len(updated_nodes),
        "edges": len(all_edges),
        "meta": meta,
        "removed_edges": [f"{e['source_id']} -> {e['target_id']}" for e in removed_edges],
        "added_edges": [f"{e['source_id']} -> {e['target_id']}" for e in new_edges],
    }


if __name__ == "__main__":
    run_migration()
