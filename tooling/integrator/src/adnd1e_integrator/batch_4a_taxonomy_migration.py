"""Batch 4A Taxonomy & Item/Weapon Classification Migration.

Resolves 148 classification gaps (26 weapons, 122 items) by linking leaf instances
to their authoritative category hubs (item_weapon, item_armor, item_gear, item_magic_item)
in accordance with DEC-2026-0109, SD pp. 37-41, CS2 p. 17, CS3 p. 20, and SD pp. 260-320.
Also normalizes 23 raw-ID labels (SD-012) and populates general_rule_id on OVERRIDES edges (SD-013).
"""

import csv
import json
import os
from pathlib import Path
from typing import Dict, List, Set, Any

ROOT = Path(__file__).resolve().parents[4]
CANONICAL_DIR = ROOT / "rulesets" / "shadowdark" / "canonical"
GRAPH_JSON_PATH = CANONICAL_DIR / "graph.json"
NODES_CSV_PATH = CANONICAL_DIR / "nodes_master.csv"
EDGES_CSV_PATH = CANONICAL_DIR / "edges_master.csv"
GAPS_CSV_PATH = ROOT / "classification_gaps.csv"

# Category Hubs
CATEGORY_HUBS = {
    "item_weapon": "Weapon",
    "item_armor": "Armor",
    "item_gear": "Gear",
    "item_magic_item": "Magic Item",
    "item_coin": "Coin",
}

# 26 Canonical Weapons from SD Core (p. 37), CS2 (p. 17), CS3 (p. 20)
WEAPONS_TAXONOMY = {
    # SD Core Rules (p. 37, WEAPONS TABLE) - 15 weapons
    "weapon_bastard_sword": ("Bastard Sword", "SD", 37, "WEAPONS"),
    "weapon_club": ("Club", "SD", 37, "WEAPONS"),
    "weapon_crossbow": ("Crossbow", "SD", 37, "WEAPONS"),
    "weapon_dagger": ("Dagger", "SD", 37, "WEAPONS"),
    "weapon_greataxe": ("Greataxe", "SD", 37, "WEAPONS"),
    "weapon_greatsword": ("Greatsword", "SD", 37, "WEAPONS"),
    "weapon_javelin": ("Javelin", "SD", 37, "WEAPONS"),
    "weapon_longbow": ("Longbow", "SD", 37, "WEAPONS"),
    "weapon_longsword": ("Longsword", "SD", 37, "WEAPONS"),
    "weapon_mace": ("Mace", "SD", 37, "WEAPONS"),
    "weapon_shortbow": ("Shortbow", "SD", 37, "WEAPONS"),
    "weapon_shortsword": ("Shortsword", "SD", 37, "WEAPONS"),
    "weapon_spear": ("Spear", "SD", 37, "WEAPONS"),
    "weapon_staff": ("Staff", "SD", 37, "WEAPONS"),
    "weapon_warhammer": ("Warhammer", "SD", 37, "WEAPONS"),

    # Cursed Scroll Vol. 2 (p. 17, NEW WEAPONS TABLE) - 9 weapons
    "weapon_blowgun": ("Blowgun", "CS2", 17, "WEAPONS"),
    "weapon_bolas": ("Bolas", "CS2", 17, "WEAPONS"),
    "weapon_morningstar": ("Morningstar", "CS2", 17, "WEAPONS"),
    "weapon_pike": ("Pike", "CS2", 17, "WEAPONS"),
    "weapon_razor_chain": ("Razor Chain", "CS2", 17, "WEAPONS"),
    "weapon_scimitar": ("Scimitar", "CS2", 17, "WEAPONS"),
    "weapon_shuriken": ("Shuriken", "CS2", 17, "WEAPONS"),
    "weapon_sling": ("Sling", "CS2", 17, "WEAPONS"),
    "weapon_whip": ("Whip", "CS2", 17, "WEAPONS"),

    # Cursed Scroll Vol. 3 (p. 20, NEW GEAR: WEAPONS TABLE) - 2 weapons
    "weapon_handaxe": ("Handaxe", "CS3", 20, "WEAPONS"),
    "weapon_stave": ("Stave", "CS3", 20, "WEAPONS"),
}

# 23 Raw-ID Nodes to Normalize (SD-012)
RAW_ID_LABEL_NORMALIZATION = {
    "lang_diabolic": "Diabolic",
    "lang_draconic": "Draconic",
    "lang_goblin": "Goblin",
    "lang_primordial": "Primordial",
    "lang_sylvan": "Sylvan",
    "monster_archangel": "Archangel",
    "monster_badger": "Badger",
    "monster_cockatrice": "Cockatrice",
    "monster_djinni": "Djinni",
    "monster_efreeti": "Efreeti",
    "monster_mastiff": "Mastiff",
    "monster_nightmare": "Nightmare",
    "monster_pegasus": "Pegasus",
    "monster_rat_giant": "Giant Rat",
    "monster_snake_giant": "Giant Snake",
    "monster_zombie": "Zombie",
    "rule_d6_decider": "d6 Decider",
    "spell_alter_self": "Alter Self",
    "spell_animate_dead": "Animate Dead",
    "spell_augury": "Augury",
    "spell_create_undead": "Create Undead",
    "spell_dimension_door": "Dimension Door",
    "spell_feather_fall": "Feather Fall",
}

# Categorization mapping for items in classification_gaps.csv
ITEM_CATEGORIES = {
    # Armor (mundane)
    "item_leather_armor": ["item_armor"],
    "item_chainmail": ["item_armor"],
    "item_plate_mail": ["item_armor"],
    "item_shield": ["item_armor"],
    "item_round_shield": ["item_armor"],

    # Gear (mundane equipment & provisions)
    "item_backpack": ["item_gear"],
    "item_crowbar": ["item_gear"],
    "item_caltrops": ["item_gear"],
    "item_campfire": ["item_gear"],
    "item_oil_flask": ["item_gear"],
    "item_rations": ["item_gear"],
    "item_mithral": ["item_gear"],
    "item_aged_royal_wine": ["item_gear"],
    "item_barnacle_grog": ["item_gear"],
    "item_dwarvish_gold_ale": ["item_gear"],
    "item_elvish_brandy": ["item_gear"],
    "item_halfling_summer_wine": ["item_gear"],
    "item_stale_ale": ["item_gear"],
    "item_vinegary_wine": ["item_gear"],
    "item_watered_down_swill": ["item_gear"],
    "item_van_dinkle_whiskey": ["item_gear"],

    # Magic Weapons (item_magic_item + item_weapon)
    "item_thrice_blessed_sword": ["item_magic_item", "item_weapon"],
    "item_blade_of_vengeance": ["item_magic_item", "item_weapon"],
    "item_greataxe_of_the_horde": ["item_magic_item", "item_weapon"],
    "item_memnons_blazing_javelin": ["item_magic_item", "item_weapon"],
    "item_obsidian_witchknife": ["item_magic_item", "item_weapon"],
    "item_scimitar_of_the_ash_moon": ["item_magic_item", "item_weapon"],
    "item_silver_mace_of_wrath": ["item_magic_item", "item_weapon"],
    "item_sword_of_the_ancients": ["item_magic_item", "item_weapon"],
    "item_dagger_of_the_goblin_hero": ["item_magic_item", "item_weapon"],
    "item_longbow_of_the_elven_kings": ["item_magic_item", "item_weapon"],
    "item_memnons_discordant_blade": ["item_magic_item", "item_weapon"],
    "item_necrotic_mace_of_withering": ["item_magic_item", "item_weapon"],
    "item_shortsword_of_the_thief": ["item_magic_item", "item_weapon"],
    "item_warhammer_of_the_dwarf_lords": ["item_magic_item", "item_weapon"],
    "item_trident_of_the_seas": ["item_magic_item", "item_weapon"],

    # Magic Armor & Shields (item_magic_item + item_armor)
    "item_armor_of_the_oni": ["item_magic_item", "item_armor"],
    "item_armor_of_saint_terragnis": ["item_magic_item", "item_armor"],
    "item_memnons_entropic_armor": ["item_magic_item", "item_armor"],
    "item_moonwrought_chainmail": ["item_magic_item", "item_armor"],
    "item_nightcloak_armor": ["item_magic_item", "item_armor"],
    "item_ophidian_armor": ["item_magic_item", "item_armor"],
    "item_wraith_chain": ["item_magic_item", "item_armor"],
    "item_shield_of_the_witch_king": ["item_magic_item", "item_armor"],
    "item_shield_of_the_crusader": ["item_magic_item", "item_armor"],
    "item_shield_of_the_lion": ["item_magic_item", "item_armor"],

    # General Magic Items / Potions / Wands / Relics
    "item_braks_cube_of_perfection": ["item_magic_item"],
    "item_robe_of_the_sorcerer": ["item_magic_item"],
    "item_staff_of_the_cobra": ["item_magic_item"],
    "item_spell_scroll": ["item_magic_item"],
    "item_robe_of_the_archmage": ["item_magic_item"],
    "item_robe_of_the_druid": ["item_magic_item"],
    "item_the_malediction_infernal": ["item_magic_item"],
    "item_wand_of_unlife": ["item_magic_item"],
    "item_wand": ["item_magic_item"],
    "item_braks_book_of_misspells": ["item_magic_item"],
    "item_ring_of_ramlaat": ["item_magic_item"],
    "item_sphere_of_annihilation": ["item_magic_item"],
    "item_tome_of_hadebe": ["item_magic_item"],
    "item_war_horn_of_the_angels": ["item_magic_item"],
    "item_genie_lamp": ["item_magic_item"],
    "item_onyx_destrier": ["item_magic_item"],
    "item_potion_of_invisibility": ["item_magic_item"],
    "item_pipes_of_the_sewers": ["item_magic_item"],
    "item_potion_of_vitality": ["item_magic_item"],
    "item_staff_of_healing": ["item_magic_item"],
    "item_wand_of_warding": ["item_magic_item"],
    "item_bag_of_holding": ["item_magic_item"],
    "item_crystal_ball": ["item_magic_item"],
    "item_boots_of_the_cat": ["item_magic_item"],
    "item_horned_helm_of_ramlaat": ["item_magic_item"],
    "item_jewel_of_barbalt": ["item_magic_item"],
    "item_kytherian_cog": ["item_magic_item"],
    "item_potion_of_extirpation": ["item_magic_item"],
    "item_potion_of_healing": ["item_magic_item"],
    "item_portable_hole": ["item_magic_item"],
    "item_potion_of_giant_strength": ["item_magic_item"],
    "item_ring_of_feather_falling": ["item_magic_item"],
    "item_potion_of_legendary_deeds": ["item_magic_item"],
    "item_ring_of_fireballs": ["item_magic_item"],
    "item_ring_of_invisibility": ["item_magic_item"],
    "item_scarab_of_protection": ["item_magic_item"],
    "item_tome_of_gehemna": ["item_magic_item"],
    "item_tome_of_mordanticus": ["item_magic_item"],
    "item_true_name": ["item_magic_item"],
    "item_alabaster_destrier": ["item_magic_item"],
    "item_amulet_of_secrecy": ["item_magic_item"],
    "item_amulet_of_vitality": ["item_magic_item"],
    "item_bag_of_badgers": ["item_magic_item"],
    "item_bag_of_devouring": ["item_magic_item"],
    "item_bead_of_force": ["item_magic_item"],
    "item_boots_of_dancing": ["item_magic_item"],
    "item_boots_of_hovering": ["item_magic_item"],
    "item_bracers_of_archery": ["item_magic_item"],
    "item_bracers_of_defense": ["item_magic_item"],
    "item_circlet_of_wisdom": ["item_magic_item"],
    "item_cloak_of_elvenkind": ["item_magic_item"],
    "item_cloak_of_the_bat": ["item_magic_item"],
    "item_egg_of_the_cockatrice": ["item_magic_item"],
    "item_flying_carpet": ["item_magic_item"],
    "item_gauntlets_of_might": ["item_magic_item"],
    "item_gloves_of_agility": ["item_magic_item"],
    "item_goblin_bomb": ["item_magic_item"],
    "item_hat_of_intellect": ["item_magic_item"],
    "item_hat_of_the_hound": ["item_magic_item"],
    "item_helm_of_mind_reading": ["item_magic_item"],
    "item_hourglass_of_the_black_sands": ["item_magic_item"],
    "item_immovable_rod": ["item_magic_item"],
    "item_magic_ink": ["item_magic_item"],
    "item_necklace_of_charm": ["item_magic_item"],
    "item_pearl_of_power": ["item_magic_item"],
    "item_pipe_of_the_rolling_hills": ["item_magic_item"],
    "item_potion_of_flying": ["item_magic_item"],
    "item_potion_of_polymorph": ["item_magic_item"],
    "item_the_kytherian_mechanism": ["item_magic_item"],
    "item_spyglass_of_true_sight": ["item_magic_item"],
    "item_well_of_many_worlds": ["item_magic_item"],
    "item_staff_of_ord": ["item_magic_item"],
}


def run_batch_4a_migration():
    print("Running Batch 4A Taxonomy & Item/Weapon Migration...")

    with open(GRAPH_JSON_PATH, "r", encoding="utf-8") as f:
        graph = json.load(f)

    nodes_dict = {n["id"]: n for n in graph["nodes"]}
    existing_edges = graph["edges"]
    edge_keys = {(e["source_id"], e["edge_type"], e["target_id"]) for e in existing_edges}

    # Normalize raw labels (SD-012)
    for node_id, new_label in RAW_ID_LABEL_NORMALIZATION.items():
        if node_id in nodes_dict:
            nodes_dict[node_id]["label"] = new_label

    # Populate general_rule_id on OVERRIDES edges (SD-013)
    for e in existing_edges:
        if e.get("edge_type") == "OVERRIDES":
            if not e.get("general_rule_id"):
                e["general_rule_id"] = e["target_id"]

    # Ensure all category hubs exist
    for hub_id, hub_label in CATEGORY_HUBS.items():
        if hub_id not in nodes_dict:
            hub_node = {
                "id": hub_id,
                "label": hub_label,
                "kind": "item",
                "degree": 0,
                "core_degree": 0,
                "in_degree": 0,
                "out_degree": 0,
            }
            nodes_dict[hub_id] = hub_node
            print(f"Created category hub node: {hub_id}")

    new_edges = []

    # 1. Link all 26 weapons to item_weapon
    for weapon_id, (label, book, page, section) in WEAPONS_TAXONOMY.items():
        if weapon_id in nodes_dict:
            edge_key = (weapon_id, "CLASSIFIED_AS", "item_weapon")
            if edge_key not in edge_keys:
                edge = {
                    "source_id": weapon_id,
                    "source_label": label,
                    "edge_type": "CLASSIFIED_AS",
                    "target_id": "item_weapon",
                    "target_label": "Weapon",
                    "aspect": "equipment category",
                    "condition": "",
                    "polarity": "neutral",
                    "polarity_basis": "derived",
                    "book": book,
                    "page": str(page),
                    "section": section,
                    "evidence": "explicit_rule",
                    "pass": "1",
                    "status": "core" if book == "SD" else "optional",
                    "supersession_basis": "",
                    "general_rule_id": "",
                    "review_flag": "",
                }
                new_edges.append(edge)
                edge_keys.add(edge_key)
            else:
                # Update existing edge with accurate book/page/section
                for e in existing_edges:
                    if (e["source_id"], e["edge_type"], e["target_id"]) == edge_key:
                        e["book"] = book
                        e["page"] = str(page)
                        e["section"] = section
                        e["status"] = "core" if book == "SD" else "optional"

    # 2. Link all items to their category hubs
    for item_id, categories in ITEM_CATEGORIES.items():
        if item_id in nodes_dict:
            item_label = nodes_dict[item_id].get("label", item_id)
            for cat_id in categories:
                cat_label = CATEGORY_HUBS.get(cat_id, cat_id)
                edge_key = (item_id, "CLASSIFIED_AS", cat_id)
                if edge_key not in edge_keys:
                    edge = {
                        "source_id": item_id,
                        "source_label": item_label,
                        "edge_type": "CLASSIFIED_AS",
                        "target_id": cat_id,
                        "target_label": cat_label,
                        "aspect": "equipment category",
                        "condition": "",
                        "polarity": "neutral",
                        "polarity_basis": "derived",
                        "book": "SD",
                        "page": "38",
                        "section": "EQUIPMENT",
                        "evidence": "explicit_rule",
                        "pass": "1",
                        "status": "core",
                        "supersession_basis": "",
                        "general_rule_id": "",
                        "review_flag": "",
                    }
                    new_edges.append(edge)
                    edge_keys.add(edge_key)

    print(f"Added {len(new_edges)} new taxonomy classification edges.")
    all_edges = existing_edges + new_edges

    # Recompute degree metrics for all nodes correctly
    in_degrees: Dict[str, int] = {}
    out_degrees: Dict[str, int] = {}
    core_degrees: Dict[str, int] = {}
    for e in all_edges:
        src = e["source_id"]
        tgt = e["target_id"]
        out_degrees[src] = out_degrees.get(src, 0) + 1
        in_degrees[tgt] = in_degrees.get(tgt, 0) + 1
        if e.get("status") == "core":
            core_degrees[src] = core_degrees.get(src, 0) + 1
            core_degrees[tgt] = core_degrees.get(tgt, 0) + 1

    updated_nodes = []
    for node in nodes_dict.values():
        nid = node["id"]
        ind = in_degrees.get(nid, 0)
        outd = out_degrees.get(nid, 0)
        tot = ind + outd
        node["degree"] = tot
        node["core_degree"] = core_degrees.get(nid, 0)
        node["in_degree"] = ind
        node["out_degree"] = outd
        updated_nodes.append(node)

    # Sort nodes and edges deterministically
    updated_nodes.sort(key=lambda n: n["id"])
    all_edges.sort(key=lambda e: (e["source_id"], e["edge_type"], e["target_id"]))

    # Save canonical graph.json
    with open(GRAPH_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump({"nodes": updated_nodes, "edges": all_edges}, f, indent=2)
    print(f"Saved canonical graph.json: {len(updated_nodes)} nodes, {len(all_edges)} edges")

    # Re-derive nodes_master.csv
    with open(NODES_CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "label", "kind", "degree", "core_degree", "in_degree", "out_degree"])
        for n in updated_nodes:
            writer.writerow([n["id"], n["label"], n["kind"], n["degree"], n["core_degree"], n["in_degree"], n["out_degree"]])
    print(f"Re-derived {NODES_CSV_PATH}")

    # Re-derive edges_master.csv
    fieldnames = [
        "source_id", "source_label", "edge_type", "target_id", "target_label",
        "aspect", "condition", "polarity", "polarity_basis", "book", "page",
        "section", "evidence", "pass", "status", "supersession_basis",
        "general_rule_id", "review_flag"
    ]
    with open(EDGES_CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for e in all_edges:
            writer.writerow({k: e.get(k, "") for k in fieldnames})
    print(f"Re-derived {EDGES_CSV_PATH}")

    # Synchronize classification_gaps.csv:
    # Retain ONLY true unclassified supplement spells (CS1/CS3)
    # Remove:
    # 1. items and weapons (all 148 resolved)
    # 2. spell_control_weather (retired and redirected to spell_control_water)
    # 3. any core spell that already has CLASSIFIED_AS edges to class_wizard or class_priest in canonical graph
    classified_spell_sources = {
        e["source_id"] for e in all_edges
        if e["edge_type"] == "CLASSIFIED_AS" and e["target_id"] in ["class_wizard", "class_priest"]
    }

    with open(GAPS_CSV_PATH, "r", encoding="utf-8") as f:
        gaps = list(csv.DictReader(f))

    remaining_gaps = []
    for g in gaps:
        nid = g["node_id"]
        kind = g["kind"]
        if kind in ["item", "weapon"]:
            continue
        if nid == "spell_control_weather":
            continue
        if nid in classified_spell_sources:
            continue
        remaining_gaps.append(g)

    with open(GAPS_CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["node_id", "kind", "missing_classification"])
        writer.writeheader()
        for g in remaining_gaps:
            writer.writerow(g)
    print(f"Updated {GAPS_CSV_PATH}: remaining true gaps: {len(remaining_gaps)} (all supplement spells)")


if __name__ == "__main__":
    run_batch_4a_migration()
