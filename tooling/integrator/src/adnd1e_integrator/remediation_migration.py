#!/usr/bin/env python3
"""
Remediation Migration Runner for Shadowdark Canonical Graph.

Applies Batches 3A-3E authorized by DEC-2026-0109:
- 3A: Add 4 core missing spells (alarm, bless, fixed_object, fabricate).
- 3B: Migrate spell_control_weather to spell_control_water with Priest/Wizard tier 4 and redirect.
- 3C: Correct SD p.70 attributions (Sending Wizard 3, Shapechange Wizard 5, Shield of Faith Priest 1, Scrying Wizard 5).
- 3D: Reconcile core spell offerings from pp. 54-62.
- 3E: Weapon taxonomy (item_weapon) and optional rule status for Fatality Mode.
- Re-derives nodes_master.csv and edges_master.csv.
"""

import json
import csv
import os
import sys

CANONICAL_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "../../../../rulesets/shadowdark/canonical")
)
GRAPH_PATH = os.path.join(CANONICAL_DIR, "graph.json")
NODES_CSV_PATH = os.path.join(CANONICAL_DIR, "nodes_master.csv")
EDGES_CSV_PATH = os.path.join(CANONICAL_DIR, "edges_master.csv")

# Authoritative spell offerings from SD pp. 51-53 (file 019-priest-and-wizard-spell-lists.md)
CORE_SPELL_OFFERINGS = {
    # PRIEST TIER 1
    "spell_cure_wounds": [("class_priest", 1)],
    "spell_holy_weapon": [("class_priest", 1)],
    "spell_light": [("class_priest", 1), ("class_wizard", 1)],
    "spell_protection_from_evil": [("class_priest", 1), ("class_wizard", 1)],
    "spell_shield_of_faith": [("class_priest", 1)],
    "spell_turn_undead": [("class_priest", 1)],

    # PRIEST TIER 2
    "spell_augury": [("class_priest", 2)],
    "spell_blind_deafen": [("class_priest", 2)],
    "spell_bless": [("class_priest", 2)],
    "spell_cleansing_weapon": [("class_priest", 2)],
    "spell_smite": [("class_priest", 2)],
    "spell_zone_of_truth": [("class_priest", 2)],

    # PRIEST TIER 3
    "spell_command": [("class_priest", 3)],
    "spell_lay_to_rest": [("class_priest", 3)],
    "spell_mass_cure": [("class_priest", 3)],
    "spell_rebuke_unholy": [("class_priest", 3)],
    "spell_restoration": [("class_priest", 3)],
    "spell_speak_with_dead": [("class_priest", 3), ("class_wizard", 3)],

    # PRIEST TIER 4
    "spell_commune": [("class_priest", 4)],
    "spell_control_water": [("class_priest", 4), ("class_wizard", 4)],
    "spell_flame_strike": [("class_priest", 4)],
    "spell_pillar_of_salt": [("class_priest", 4)],
    "spell_regenerate": [("class_priest", 4)],
    "spell_wrath": [("class_priest", 4)],

    # PRIEST TIER 5
    "spell_divine_vengeance": [("class_priest", 5)],
    "spell_dominion": [("class_priest", 5)],
    "spell_heal": [("class_priest", 5)],
    "spell_judgment": [("class_priest", 5)],
    "spell_plane_shift": [("class_priest", 5), ("class_wizard", 5)],
    "spell_prophecy": [("class_priest", 5)],

    # WIZARD TIER 1
    "spell_alarm": [("class_wizard", 1)],
    "spell_burning_hands": [("class_wizard", 1)],
    "spell_charm_person": [("class_wizard", 1)],
    "spell_detect_magic": [("class_wizard", 1)],
    "spell_feather_fall": [("class_wizard", 1)],
    "spell_floating_disk": [("class_wizard", 1)],
    "spell_hold_portal": [("class_wizard", 1)],
    "spell_mage_armor": [("class_wizard", 1)],
    "spell_magic_missile": [("class_wizard", 1)],
    "spell_sleep": [("class_wizard", 1)],

    # WIZARD TIER 2
    "spell_acid_arrow": [("class_wizard", 2)],
    "spell_alter_self": [("class_wizard", 2)],
    "spell_detect_thoughts": [("class_wizard", 2)],
    "spell_fixed_object": [("class_wizard", 2)],
    "spell_hold_person": [("class_wizard", 2)],
    "spell_invisibility": [("class_wizard", 2)],
    "spell_knock": [("class_wizard", 2)],
    "spell_levitate": [("class_wizard", 2)],
    "spell_mirror_image": [("class_wizard", 2)],
    "spell_misty_step": [("class_wizard", 2)],
    "spell_silence": [("class_wizard", 2)],
    "spell_web": [("class_wizard", 2)],

    # WIZARD TIER 3
    "spell_animate_dead": [("class_wizard", 3)],
    "spell_dispel_magic": [("class_wizard", 3)],
    "spell_fabricate": [("class_wizard", 3)],
    "spell_fireball": [("class_wizard", 3)],
    "spell_fly": [("class_wizard", 3)],
    "spell_gaseous_form": [("class_wizard", 3)],
    "spell_illusion": [("class_wizard", 3)],
    "spell_lightning_bolt": [("class_wizard", 3)],
    "spell_magic_circle": [("class_wizard", 3)],
    "spell_protection_from_energy": [("class_wizard", 3)],
    "spell_sending": [("class_wizard", 3)],

    # WIZARD TIER 4
    "spell_arcane_eye": [("class_wizard", 4)],
    "spell_cloudkill": [("class_wizard", 4)],
    "spell_confusion": [("class_wizard", 4)],
    "spell_dimension_door": [("class_wizard", 4)],
    "spell_divination": [("class_wizard", 4)],
    "spell_passwall": [("class_wizard", 4)],
    "spell_polymorph": [("class_wizard", 4)],
    "spell_resilient_sphere": [("class_wizard", 4)],
    "spell_stoneskin": [("class_wizard", 4)],
    "spell_telekinesis": [("class_wizard", 4)],
    "spell_wall_of_force": [("class_wizard", 4)],

    # WIZARD TIER 5
    "spell_antimagic_shell": [("class_wizard", 5)],
    "spell_create_undead": [("class_wizard", 5)],
    "spell_disintegrate": [("class_wizard", 5)],
    "spell_hold_monster": [("class_wizard", 5)],
    "spell_power_word_kill": [("class_wizard", 5)],
    "spell_prismatic_orb": [("class_wizard", 5)],
    "spell_scrying": [("class_wizard", 5)],
    "spell_shapechange": [("class_wizard", 5)],
    "spell_summon_extraplanar": [("class_wizard", 5)],
    "spell_teleport": [("class_wizard", 5)],
    "spell_wish": [("class_wizard", 5)],
}

TIER_RULE_MAP = {
    1: "rule_spell_tier_1",
    2: "rule_spell_tier_2",
    3: "rule_spell_tier_3",
    4: "rule_spell_tier_4",
    5: "rule_spell_tier_5",
}

CLASS_LABEL_MAP = {
    "class_priest": "Priest",
    "class_wizard": "Wizard",
}


def run_remediation():
    with open(GRAPH_PATH, "r", encoding="utf-8") as f:
        graph = json.load(f)

    nodes = {n["id"]: n for n in graph["nodes"]}
    edges = list(graph["edges"])

    print(f"Initial graph: {len(nodes)} nodes, {len(edges)} edges")

    # ----------------------------------------------------
    # BATCH 3B: Migrate spell_control_weather -> spell_control_water
    # ----------------------------------------------------
    if "spell_control_weather" in nodes:
        cw_node = nodes.pop("spell_control_weather")
        cw_node["id"] = "spell_control_water"
        cw_node["label"] = "Control Water"
        nodes["spell_control_water"] = cw_node
        print("Migrated spell_control_weather node to spell_control_water")

    for e in edges:
        if e["source_id"] == "spell_control_weather":
            e["source_id"] = "spell_control_water"
            e["source_label"] = "Control Water"
        if e["target_id"] == "spell_control_weather":
            e["target_id"] = "spell_control_water"
            e["target_label"] = "Control Water"

    # ----------------------------------------------------
    # BATCH 3A: Add 4 missing core spells
    # ----------------------------------------------------
    missing_spells = [
        ("spell_alarm", "Alarm"),
        ("spell_bless", "Bless"),
        ("spell_fixed_object", "Fixed Object"),
        ("spell_fabricate", "Fabricate"),
    ]
    for sid, slabel in missing_spells:
        if sid not in nodes:
            nodes[sid] = {
                "id": sid,
                "label": slabel,
                "kind": "spell",
                "degree": 0,
                "core_degree": 0,
                "in_degree": 0,
                "out_degree": 0,
            }
            print(f"Added missing core spell node: {sid}")

    # ----------------------------------------------------
    # BATCH 3C: Correct SD p.70 attributions
    # ----------------------------------------------------
    # Remove existing incorrect classification edges for page 70 spells
    p70_spells = {"spell_sending", "spell_shapechange", "spell_shield_of_faith"}
    retained_edges = []
    for e in edges:
        if e["source_id"] in p70_spells and e["edge_type"] == "CLASSIFIED_AS":
            continue  # remove old wrong classification
        retained_edges.append(e)
    edges = retained_edges

    # ----------------------------------------------------
    # BATCH 3D: Reconcile all core spell offerings
    # ----------------------------------------------------
    # Helper to check if edge already exists
    edge_set = set()
    for e in edges:
        edge_set.add((e["source_id"], e["edge_type"], e["target_id"]))

    def add_edge_if_missing(src_id, edge_type, tgt_id, src_label, tgt_label, aspect, page="54", book="SD"):
        key = (src_id, edge_type, tgt_id)
        if key not in edge_set:
            edge_set.add(key)
            edges.append({
                "source_id": src_id,
                "source_label": src_label,
                "edge_type": edge_type,
                "target_id": tgt_id,
                "target_label": tgt_label,
                "aspect": aspect,
                "condition": "",
                "polarity": "neutral",
                "polarity_basis": "derived",
                "book": book,
                "page": page,
                "section": "SPELLS",
                "evidence": "explicit_rule",
                "pass": "1",
                "status": "core",
                "supersession_basis": "",
                "general_rule_id": "",
                "review_flag": "",
            })

    for spell_id, offerings in CORE_SPELL_OFFERINGS.items():
        if spell_id not in nodes:
            continue
        spell_label = nodes[spell_id]["label"]
        for class_id, tier in offerings:
            class_label = CLASS_LABEL_MAP.get(class_id, class_id)
            tier_rule_id = TIER_RULE_MAP[tier]
            tier_label = f"Spell Tier {tier}"

            # Class offering edge
            page_num = "70" if spell_id in {"spell_sending", "spell_shapechange", "spell_shield_of_faith", "spell_scrying"} else "54"
            add_edge_if_missing(spell_id, "CLASSIFIED_AS", class_id, spell_label, class_label, "casting class", page=page_num)
            add_edge_if_missing(spell_id, "CLASSIFIED_AS", tier_rule_id, spell_label, tier_label, "spell tier", page=page_num)

    # ----------------------------------------------------
    # BATCH 3E: Weapon taxonomy (item_weapon category)
    # ----------------------------------------------------
    if "item_weapon" not in nodes:
        nodes["item_weapon"] = {
            "id": "item_weapon",
            "label": "Weapons",
            "kind": "category",
            "degree": 0,
            "core_degree": 0,
            "in_degree": 0,
            "out_degree": 0,
        }
        print("Created item_weapon category hub")

    # Link weapons to item_weapon
    weapon_ids = [
        "item_bastard_sword", "item_club", "item_crossbow", "item_dagger",
        "item_greataxe", "item_greatsword", "item_javelin", "item_longbow",
        "item_longsword", "item_mace", "item_shortbow", "item_shortsword",
        "item_spear", "item_staff", "item_warhammer",
    ]
    for wid in weapon_ids:
        if wid in nodes:
            wlabel = nodes[wid]["label"]
            add_edge_if_missing(wid, "CLASSIFIED_AS", "item_weapon", wlabel, "Weapons", "weapon taxonomy", page="37")

    # Fatality mode optional status
    if "rule_fatality_mode" in nodes:
        nodes["rule_fatality_mode"]["status"] = "optional"

    # ----------------------------------------------------
    # Recompute node degrees
    # ----------------------------------------------------
    in_degrees = {}
    out_degrees = {}
    core_degrees = {}
    for e in edges:
        s = e["source_id"]
        t = e["target_id"]
        out_degrees[s] = out_degrees.get(s, 0) + 1
        in_degrees[t] = in_degrees.get(t, 0) + 1
        if e.get("status") == "core":
            core_degrees[s] = core_degrees.get(s, 0) + 1
            core_degrees[t] = core_degrees.get(t, 0) + 1

    for nid, node in nodes.items():
        ind = in_degrees.get(nid, 0)
        outd = out_degrees.get(nid, 0)
        tot = ind + outd
        node["in_degree"] = ind
        node["out_degree"] = outd
        node["degree"] = tot
        node["core_degree"] = core_degrees.get(nid, 0)

    # Sort nodes and edges for deterministic output
    sorted_nodes = sorted(nodes.values(), key=lambda n: n["id"])
    sorted_edges = sorted(edges, key=lambda e: (e["source_id"], e["edge_type"], e["target_id"], e["aspect"]))

    updated_graph = {
        "nodes": sorted_nodes,
        "edges": sorted_edges,
    }

    # Save graph.json
    with open(GRAPH_PATH, "w", encoding="utf-8") as f:
        json.dump(updated_graph, f, indent=2, ensure_ascii=False)

    print(f"Saved canonical graph.json: {len(sorted_nodes)} nodes, {len(sorted_edges)} edges")

    # Re-derive nodes_master.csv
    with open(NODES_CSV_PATH, "w", encoding="utf-8", newline="\n") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "label", "kind", "degree", "core_degree", "in_degree", "out_degree"])
        for n in sorted_nodes:
            writer.writerow([n["id"], n["label"], n["kind"], n["degree"], n["core_degree"], n["in_degree"], n["out_degree"]])
    print(f"Re-derived {NODES_CSV_PATH}")

    # Re-derive edges_master.csv
    with open(EDGES_CSV_PATH, "w", encoding="utf-8", newline="\n") as f:
        writer = csv.writer(f)
        writer.writerow([
            "source_id", "source_label", "edge_type", "target_id", "target_label",
            "aspect", "condition", "polarity", "polarity_basis", "book", "page",
            "section", "evidence", "pass", "status", "supersession_basis",
            "general_rule_id", "review_flag"
        ])
        for e in sorted_edges:
            writer.writerow([
                e["source_id"], e["source_label"], e["edge_type"], e["target_id"], e["target_label"],
                e["aspect"], e["condition"], e["polarity"], e["polarity_basis"], e["book"], e["page"],
                e["section"], e["evidence"], e["pass"], e["status"], e["supersession_basis"],
                e["general_rule_id"], e["review_flag"]
            ])
    print(f"Re-derived {EDGES_CSV_PATH}")


if __name__ == "__main__":
    run_remediation()
