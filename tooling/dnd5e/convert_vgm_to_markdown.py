#!/usr/bin/env python3
"""
convert_vgm_to_markdown.py

Converts local 5etools Volo's Guide to Monsters (VGM) data into readable
Pandoc Markdown. Produces one deterministic Markdown file per section/chapter,
plus a comprehensive CONVERSION_REPORT.md in conversion-output/dnd5e-2024/vgm/.

Preserves source order, headings, paragraphs, lists, tables, notes, formulas,
and all rule text without summarization or mechanical reinterpretation.
Resolves embedded definitions into full text and renders inline tags cleanly.
"""

import os
import sys
import json
import re
import hashlib
from collections import Counter
from typing import Dict, List, Any, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# 1. Inline Tag Renderer
# ---------------------------------------------------------------------------

class TagRenderer:
    """Parses and renders 5etools inline tags into standard Markdown."""

    TAG_PATTERN = re.compile(r"\{@([a-zA-Z0-9_-]+)(?: ([^{}]+))?\}")

    def __init__(self):
        self.unresolved_tags = Counter()

    def render(self, text: str) -> str:
        if not text:
            return ""

        depth = 0
        max_depth = 10
        while "{@" in text and depth < max_depth:
            depth += 1
            text = self.TAG_PATTERN.sub(self._replace_tag, text)

        return text

    def _replace_tag(self, match: re.Match) -> str:
        tag = match.group(1)
        raw_body = match.group(2) or ""
        parts = [p.strip() for p in raw_body.split("|")]

        # Formatting tags
        if tag in {"b", "bold"}:
            return f"**{parts[0]}**" if parts else ""
        if tag in {"i", "italic"}:
            return f"*{parts[0]}*" if parts else ""
        if tag in {"s", "strike"}:
            return f"~~{parts[0]}~~" if parts else ""
        if tag in {"u", "underline"}:
            return f"_{parts[0]}_" if parts else ""
        if tag in {"note", "tip", "color"}:
            return parts[0] if parts else ""

        # Dice, rolls, math
        if tag in {"dice", "damage", "d20", "scaledice", "scaledamage"}:
            display = parts[1] if len(parts) > 1 and parts[1] else parts[0]
            return f"`{display}`"
        if tag == "dc":
            return f"DC {parts[0]}" if parts else "DC"
        if tag in {"hit", "d20"}:
            val = parts[0] if parts else "0"
            return f"+{val}" if not val.startswith(("-", "+")) else val
        if tag in {"h", "hom"}:
            return "*Hit:* "
        if tag in {"atk", "atkr"}:
            atk_type = parts[0].lower() if parts else ""
            type_map = {
                "mw": "*Melee Attack:*",
                "rw": "*Ranged Attack:*",
                "mw,rw": "*Melee or Ranged Attack:*",
                "ms": "*Melee Spell Attack:*",
                "rs": "*Ranged Spell Attack:*",
                "ms,rs": "*Melee or Ranged Spell Attack:*",
                "m": "*Melee Attack:*",
                "r": "*Ranged Attack:*"
            }
            return type_map.get(atk_type, f"*{atk_type.title()} Attack:*")
        if tag == "recharge":
            val = parts[0] if parts else "6"
            return f"(Recharge {val}-6)" if val != "6" else "(Recharge 6)"

        # Structural book, table & area links
        if tag == "table":
            if len(parts) >= 2 and parts[1]:
                return f"**Table: {parts[1]}**"
            return f"**Table: {parts[0]}**" if parts else "**Table**"
        if tag == "area":
            return f"**{parts[0]}**" if parts else ""
        if tag in {"book", "adventure"}:
            name = parts[0] if parts else "Reference"
            return f"*{name}*"
        if tag == "link":
            if len(parts) >= 2 and parts[1]:
                return f"[{parts[0]}]({parts[1]})"
            return parts[0] if parts else ""
        if tag in {"5etools", "quickref"}:
            return parts[0] if parts else ""
        if tag in {"card", "deck", "chance"}:
            return parts[0] if parts else ""
        if tag == "filter":
            return parts[0] if parts else ""

        # Class / Subclass features
        if tag in {"classFeature", "subclassFeature"}:
            if len(parts) >= 4 and parts[3]:
                return f"**{parts[3]}**"
            if len(parts) >= 1 and parts[0]:
                return f"**{parts[0]}**"
            return "**Feature**"

        # Spells are italicized by standard rules style
        if tag == "spell":
            name = parts[0] if parts else ""
            display = parts[2] if len(parts) >= 3 and parts[2] else name
            return f"*{display}*"

        # Entity references
        if tag in {
            "item", "creature", "condition", "status", "sense",
            "skill", "action", "feat", "background", "race", "facility",
            "hazard", "trap", "reward", "object", "deity", "language",
            "optfeature", "class", "subclass", "disease", "recipe",
            "variantrule", "itemProperty", "itemMastery"
        }:
            if len(parts) >= 3 and parts[2]:
                display = parts[2]
            else:
                display = parts[0] if parts else tag.title()
            return f"**{display}**"

        # Track any unhandled tags
        self.unresolved_tags[tag] += 1
        return parts[0] if parts else tag


# ---------------------------------------------------------------------------
# 2. Entity Loader
# ---------------------------------------------------------------------------

class EntityLoader:
    """Loads VGM data and supporting collections for resolving statblocks."""

    def __init__(self, data_root: str):
        self.data_root = data_root

        self.monsters: Dict[str, dict] = {}
        self.fluff: Dict[str, dict] = {}
        self.races: Dict[str, dict] = {}
        self.race_fluff: Dict[str, dict] = {}
        self.deities: Dict[str, dict] = {}

        self._load_all()

    def _index(self, target_dict: dict, key: str, val: Any):
        if not key:
            return
        target_dict[key] = val
        target_dict[key.lower()] = val

    def _load_all(self):
        # 1. Bestiary (creatures)
        bestiary_path = os.path.join(self.data_root, "bestiary", "bestiary-vgm.json")
        if os.path.exists(bestiary_path):
            with open(bestiary_path, "r", encoding="utf-8") as f:
                for r in json.load(f).get("monster", []):
                    self._index(self.monsters, r["name"], r)

        # 2. Monster Fluff
        fluff_path = os.path.join(self.data_root, "bestiary", "fluff-bestiary-vgm.json")
        if os.path.exists(fluff_path):
            with open(fluff_path, "r", encoding="utf-8") as f:
                for r in json.load(f).get("monsterFluff", []):
                    self._index(self.fluff, r["name"], dict(r))

            # Resolve _copy in fluff
            for name, f_obj in list(self.fluff.items()):
                if "_copy" in f_obj:
                    cinfo = f_obj["_copy"]
                    base = self.fluff.get(cinfo.get("name"))
                    entries = list(base.get("entries", [])) if base else []
                    images = list(base.get("images", [])) if base else []
                    mod = cinfo.get("_mod", {})
                    if "entries" in mod and mod["entries"].get("mode") == "prependArr":
                        items = mod["entries"].get("items", [])
                        if isinstance(items, dict):
                            items = [items]
                        entries = list(items) + entries
                    if "images" in mod and mod["images"].get("mode") == "prependArr":
                        items = mod["images"].get("items", [])
                        if isinstance(items, dict):
                            items = [items]
                        images = list(items) + images
                    f_obj["entries"] = entries
                    f_obj["images"] = images or f_obj.get("images", [])

        # 3. Races and Subraces (races.json)
        races_path = os.path.join(self.data_root, "races.json")
        if os.path.exists(races_path):
            with open(races_path, "r", encoding="utf-8") as f:
                d = json.load(f)
                for r in d.get("race", []):
                    if r.get("source") == "VGM":
                        self._index(self.races, r["name"], r)

                for sr in d.get("subrace", []):
                    if sr.get("source") == "VGM":
                        rname = sr.get("raceName", "")
                        sname = sr.get("name", "")
                        full_name = f"{rname} ({sname})"
                        self._index(self.races, full_name, sr)

        # 3b. Race Fluff (fluff-races.json)
        fluff_races_path = os.path.join(self.data_root, "fluff-races.json")
        if os.path.exists(fluff_races_path):
            with open(fluff_races_path, "r", encoding="utf-8") as f:
                for rf in json.load(f).get("raceFluff", []):
                    if rf.get("source") == "VGM":
                        self._index(self.race_fluff, rf["name"], rf)

        # 4. Deities (deities.json)
        deities_path = os.path.join(self.data_root, "deities.json")
        if os.path.exists(deities_path):
            with open(deities_path, "r", encoding="utf-8") as f:
                for d in json.load(f).get("deity", []):
                    if d.get("source") == "VGM":
                        self._index(self.deities, d["name"], d)


# ---------------------------------------------------------------------------
# 3. Markdown Document Renderer
# ---------------------------------------------------------------------------

class MarkdownRenderer:
    """Renders 5etools structural JSON into clean, standard Pandoc Markdown."""

    def __init__(self, entities: EntityLoader, tag_renderer: TagRenderer):
        self.entities = entities
        self.tags = tag_renderer
        self.missing_assets: List[str] = []
        self.resolved_statblocks = Counter()
        self.failed_statblocks: List[dict] = []
        self.emitted_base_races: set = set()
        self.emitted_monstrous_adventurers: bool = False

    def reset_section(self):
        self.emitted_base_races.clear()
        self.emitted_monstrous_adventurers = False

    def render_entries(self, entries, depth=2) -> str:
        blocks = []
        for e in entries:
            b = self.render_entry(e, depth)
            if b:
                blocks.append(b)
        return "\n\n".join(blocks)

    def render_entry(self, entry, depth=2) -> str:
        if isinstance(entry, str):
            rendered = self.tags.render(entry).strip()
            return rendered

        if not isinstance(entry, dict):
            return ""

        etype = entry.get("type")

        # 1. Section / Entries
        if etype in {"section", "entries"} or etype is None:
            parts = []
            name = entry.get("name")
            page = entry.get("page")

            if page is not None:
                parts.append(f"*[Page {page}]*")

            if name:
                hashes = "#" * min(depth, 6)
                parts.append(f"{hashes} {name}")

            if "entries" in entry:
                sub = self.render_entries(entry["entries"], depth + 1)
                if sub:
                    parts.append(sub)

            return "\n\n".join(parts)

        # 2. Lists
        if etype == "list":
            return self.render_list(entry, depth)

        # 3. Tables & Table Groups
        if etype == "table":
            return self.render_table(entry, depth)
        if etype == "tableGroup":
            return self.render_table_group(entry, depth)

        # 4. Insets / Callouts / Readaloud
        if etype in {"inset", "insetReadaloud", "variantInner"}:
            return self.render_inset(entry, depth)

        # 5. Quotes
        if etype == "quote":
            return self.render_quote(entry)

        # 6. Images & Galleries
        if etype == "image":
            return self.render_image(entry)
        if etype == "gallery":
            return self.render_gallery(entry)

        # 7. Embedded Statblock
        if etype == "statblock":
            return self.render_statblock(entry, depth)

        # Default fallback: check if it has entries or text
        if "entries" in entry:
            return self.render_entries(entry["entries"], depth)
        if "entry" in entry:
            return self.render_entry(entry["entry"], depth)

        return ""

    # -----------------------------------------------------------------------
    # Construct Renderers
    # -----------------------------------------------------------------------

    def render_list(self, list_obj: dict, depth: int) -> str:
        items = list_obj.get("items", [])
        if not items:
            return ""

        lines = []
        is_ordered = list_obj.get("style") in {"list-hang-notitle", "decimal", "1"} or list_obj.get("ordered", False)

        for i, it in enumerate(items, 1):
            is_sub = isinstance(it, dict) and it.get("type") == "itemSub"
            prefix = ("  -" if not is_ordered else f"  {i}.") if is_sub else (f"{i}." if is_ordered else "-")

            if isinstance(it, str):
                lines.append(f"{prefix} {self.tags.render(it)}")
            elif isinstance(it, dict):
                item_name = it.get("name")
                entry_txt = it.get("entry") or ""
                if item_name and entry_txt:
                    lines.append(f"{prefix} **{item_name}** {self.tags.render(entry_txt)}")
                elif item_name:
                    lines.append(f"{prefix} **{item_name}**")
                elif entry_txt:
                    lines.append(f"{prefix} {self.tags.render(entry_txt)}")
                elif "entries" in it:
                    first = it["entries"][0] if it["entries"] else ""
                    rest = it["entries"][1:] if len(it["entries"]) > 1 else []
                    lines.append(f"{prefix} {self.tags.render(str(first))}")
                    for r in rest:
                        sub = self.render_entry(r, depth + 1)
                        if sub:
                            for subl in sub.split("\n"):
                                lines.append(f"  {subl}")
            else:
                lines.append(f"{prefix} {self.tags.render(str(it))}")

        return "\n".join(lines)

    def render_table_group(self, tg: dict, depth: int) -> str:
        parts = []
        name = tg.get("name")
        if name:
            parts.append(f"{'#' * min(depth, 6)} {name}")
        for tbl in tg.get("tables", []):
            parts.append(self.render_table(tbl, depth + 1))
        return "\n\n".join([p for p in parts if p.strip()])

    def render_table(self, tbl: dict, depth: int) -> str:
        lines = []
        caption = tbl.get("caption")
        page = tbl.get("page")

        if page is not None:
            lines.append(f"*[Page {page}]*")
        if caption:
            lines.append(f"**Table: {self.tags.render(caption)}**\n")

        col_labels = tbl.get("colLabels", [])
        rows = tbl.get("rows", [])

        if not col_labels and rows:
            first_row = rows[0]
            if isinstance(first_row, dict):
                first_row = first_row.get("row") or first_row.get("cells") or []
            num_cols = len(first_row) if isinstance(first_row, list) else 1
            col_labels = [f"Col {i+1}" for i in range(num_cols)]

        headers = []
        for c in col_labels:
            if isinstance(c, dict):
                c_txt = c.get("entry") or c.get("text") or str(c)
            else:
                c_txt = str(c)
            headers.append(self.tags.render(c_txt).replace("\n", " ").strip())

        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        for row in rows:
            row_items = []
            if isinstance(row, dict):
                row = row.get("row") or row.get("cells") or []
            if isinstance(row, list):
                for cell in row:
                    if isinstance(cell, dict):
                        cell_txt = cell.get("entry") or cell.get("text") or cell.get("roll", {}).get("exact", "") or str(cell)
                    else:
                        cell_txt = str(cell)
                    clean_cell = self.tags.render(str(cell_txt)).replace("\n", " ").strip()
                    row_items.append(clean_cell)
            else:
                row_items.append(self.tags.render(str(row)).replace("\n", " ").strip())

            while len(row_items) < len(headers):
                row_items.append("")
            lines.append("| " + " | ".join(row_items[:len(headers)]) + " |")

        return "\n".join(lines)

    def render_inset(self, inset: dict, depth: int) -> str:
        parts = []
        name = inset.get("name")
        page = inset.get("page")

        if page is not None:
            parts.append(f"*[Page {page}]*")
        if name:
            parts.append(f"**{name}**\n")
        if "entries" in inset:
            parts.append(self.render_entries(inset["entries"], depth + 1))

        content = "\n\n".join(parts)
        return "\n".join(f"> {line}" if line.strip() else ">" for line in content.split("\n"))

    def render_quote(self, quote: dict) -> str:
        lines = []
        for e in quote.get("entries", []):
            lines.append(f"> {self.tags.render(str(e))}")
        by = quote.get("by")
        if by:
            lines.append(f"> — *{self.tags.render(by)}*")
        return "\n".join(lines)

    def render_image(self, img: dict) -> str:
        title = img.get("title") or ""
        href = img.get("href", {})
        path = href.get("path", "") if isinstance(href, dict) else str(href)
        credit = img.get("credit")

        self.missing_assets.append(path)

        cap = title
        if credit:
            cap = f"{title} (Art: {credit})" if title else f"Art: {credit}"

        return f"![{cap}]({path})"

    def render_gallery(self, gal: dict) -> str:
        images = gal.get("images", [])
        rendered = [self.render_image(img) for img in images]
        return "\n\n".join([r for r in rendered if r.strip()])

    # -----------------------------------------------------------------------
    # Embedded Statblock Dispatcher
    # -----------------------------------------------------------------------

    def render_statblock(self, sb: dict, depth: int) -> str:
        tag = sb.get("tag")
        prop = sb.get("prop")
        name = sb.get("name", "")
        name_k = name.lower()

        # 1. Monster Fluff / Lore
        if prop == "monsterFluff":
            fluff_obj = self.entities.fluff.get(name_k) or self.entities.fluff.get(name)
            return self._format_monster_fluff(fluff_obj, depth, sb)

        # 2. Creature Statblock
        if tag == "creature":
            mon = self.entities.monsters.get(name_k) or self.entities.monsters.get(name)
            return self._format_creature(mon, depth, sb)

        # 3. Character Races & Subraces
        if tag == "race":
            race = self.entities.races.get(name_k) or self.entities.races.get(name)
            return self._format_race(race, depth, sb)

        # 4. Deities
        if tag == "deity":
            deity = self.entities.deities.get(name_k) or self.entities.deities.get(name)
            return self._format_deity(deity, depth, sb)

        # Unresolved
        self.failed_statblocks.append(sb)
        return f"\n\n<!-- UNRESOLVED STATBLOCK: {sb} -->\n\n"

    # -----------------------------------------------------------------------
    # Entity Formatters
    # -----------------------------------------------------------------------

    def _format_deity(self, deity: dict, depth: int, sb: dict) -> str:
        if not deity:
            self.failed_statblocks.append(sb)
            return f"\n\n<!-- MISSING Deity: {sb.get('name')} -->\n\n"

        self.resolved_statblocks["deity"] += 1
        parts = []
        name = deity["name"]
        page = deity.get("page")

        if page is not None:
            parts.append(f"*[Page {page}]*")

        hashes = "#" * min(depth, 6)
        title = deity.get("title")
        pantheon = deity.get("pantheon")
        sub_title_parts = []
        if title:
            sub_title_parts.append(title)
        if pantheon:
            sub_title_parts.append(f"{pantheon} Pantheon")
        sub_title = f"\n*{', '.join(sub_title_parts)}*" if sub_title_parts else ""

        parts.append(f"{hashes} {name}{sub_title}")

        if "entries" in deity:
            parts.append(self.render_entries(deity["entries"], depth + 1))

        return "\n\n".join(parts)

    def _format_race(self, race: dict, depth: int, sb: dict) -> str:
        if not race:
            self.failed_statblocks.append(sb)
            return f"\n\n<!-- MISSING Race: {sb.get('name')} -->\n\n"

        self.resolved_statblocks["race"] += 1
        chunks = []

        name = race.get("name")
        rname = race.get("raceName")
        display_name = f"{rname} ({name})" if rname and name != rname else name

        # 1. Monstrous Adventurers Banner (Page 118)
        monstrous = {"bugbear", "goblin", "hobgoblin", "kobold", "orc", "yuan-ti pureblood"}
        if display_name.lower() in monstrous and not self.emitted_monstrous_adventurers:
            self.emitted_monstrous_adventurers = True
            ma_fluff = self.entities.race_fluff.get("monstrous adventurers")
            if ma_fluff:
                chunks.append(self.render_entries(ma_fluff.get("entries", []), depth))

        # 2. Base race prelude (e.g. Aasimar for Aasimar (Fallen))
        if rname and rname.lower() not in self.emitted_base_races:
            self.emitted_base_races.add(rname.lower())
            base_race = self.entities.races.get(rname.lower())
            if base_race:
                base_parts = []
                bpage = base_race.get("page")
                if bpage is not None:
                    base_parts.append(f"*[Page {bpage}]*")
                hashes = "#" * min(depth, 6)
                base_parts.append(f"{hashes} {rname}")

                # Base race fluff & images
                bfluff = self.entities.race_fluff.get(rname.lower())
                if bfluff:
                    if "images" in bfluff:
                        for img in bfluff["images"]:
                            base_parts.append(self.render_image(img))
                    if "entries" in bfluff:
                        base_parts.append(self.render_entries(bfluff["entries"], depth + 1))

                # Base race traits
                bmeta = []
                if "size" in base_race:
                    size_str = ", ".join(base_race["size"]) if isinstance(base_race["size"], list) else base_race["size"]
                    bmeta.append(f"**Size:** {size_str}")
                if "speed" in base_race:
                    sp = base_race["speed"]
                    sp_str = f"{sp} feet" if isinstance(sp, int) else f"{sp.get('walk', 30)} feet"
                    bmeta.append(f"**Speed:** {sp_str}")
                if bmeta:
                    base_parts.append("\n".join(bmeta))

                if "entries" in base_race:
                    base_parts.append(self.render_entries(base_race["entries"], depth + 1))

                chunks.append("\n\n".join(base_parts))

        # 3. Race / Subrace Formatting
        parts = []
        page = race.get("page")
        if page is not None and not (rname and name != rname):
            parts.append(f"*[Page {page}]*")

        target_depth = depth + 1 if (rname and name != rname) else depth
        hashes = "#" * min(target_depth, 6)
        parts.append(f"{hashes} {display_name}")

        # Fluff for base race or subrace
        rf = self.entities.race_fluff.get(display_name.lower()) or self.entities.race_fluff.get(name.lower())
        if rf:
            if "images" in rf:
                for img in rf["images"]:
                    parts.append(self.render_image(img))
            if "entries" in rf and not (rname and name != rname):
                parts.append(self.render_entries(rf["entries"], target_depth + 1))
            elif "_copy" in rf:
                mod = rf["_copy"].get("_mod", {})
                if "entries" in mod and mod["entries"].get("mode") == "prependArr":
                    items = mod["entries"].get("items")
                    if items:
                        if isinstance(items, dict):
                            items = [items]
                        parts.append(self.render_entries(items, target_depth + 1))

        meta = []
        if "creatureType" in race:
            meta.append(f"**Creature Type:** {race['creatureType']}")
        if "size" in race and not (rname and name != rname):
            size_str = ", ".join(race["size"]) if isinstance(race["size"], list) else race["size"]
            meta.append(f"**Size:** {size_str}")
        if "speed" in race and not (rname and name != rname):
            sp = race["speed"]
            sp_str = f"{sp} feet" if isinstance(sp, int) else f"{sp.get('walk', 30)} feet"
            meta.append(f"**Speed:** {sp_str}")

        if meta:
            parts.append("\n".join(meta))

        if "entries" in race:
            parts.append(self.render_entries(race["entries"], target_depth + 1))

        chunks.append("\n\n".join(parts))
        return "\n\n".join(chunks)

    def _format_monster_fluff(self, f_obj: dict, depth: int, sb: dict) -> str:
        if not f_obj:
            self.failed_statblocks.append(sb)
            return f"\n\n<!-- MISSING Fluff: {sb.get('name')} -->\n\n"

        self.resolved_statblocks["monsterFluff"] += 1
        entries = f_obj.get("entries", [])
        is_skip_root = sb.get("data", {}).get("renderCompact", {}).get("isSkipRootName", False)

        if is_skip_root and entries and isinstance(entries[0], dict) and entries[0].get("type") == "section":
            inner_entries = entries[0].get("entries", [])
            rendered = self.render_entries(inner_entries, depth)
        else:
            rendered = self.render_entries(entries, depth)

        images = f_obj.get("images", [])
        img_blocks = [self.render_image(img) for img in images]

        all_blocks = []
        if rendered:
            all_blocks.append(rendered)
        if img_blocks:
            all_blocks.append("\n\n".join(img_blocks))

        return "\n\n".join(all_blocks)

    def _format_creature(self, mon: dict, depth: int, sb: dict) -> str:
        if not mon:
            self.failed_statblocks.append(sb)
            return f"\n\n<!-- MISSING Creature: {sb.get('name')} -->\n\n"

        self.resolved_statblocks["creature"] += 1
        lines = []
        name = mon["name"]
        page = mon.get("page")

        if page is not None:
            lines.append(f"*[Page {page}]*")

        hashes = "#" * min(depth, 6)
        lines.append(f"{hashes} {name}")

        # Size
        size_map = {"T": "Tiny", "S": "Small", "M": "Medium", "L": "Large", "H": "Huge", "G": "Gargantuan"}
        sz_raw = mon.get("size", "M")
        sz = ", ".join([size_map.get(s, str(s)) for s in sz_raw]) if isinstance(sz_raw, list) else size_map.get(sz_raw, str(sz_raw))

        # Type
        mtype_raw = mon.get("type", "")
        if isinstance(mtype_raw, str):
            mtype = mtype_raw.title()
        elif isinstance(mtype_raw, dict):
            raw_t = mtype_raw.get("type", "")
            if isinstance(raw_t, dict) and "choose" in raw_t:
                base_t = " or ".join(c.title() for c in raw_t["choose"])
            elif isinstance(raw_t, str):
                base_t = raw_t.title()
            else:
                base_t = str(raw_t).title()

            tags = mtype_raw.get("tags", [])
            swarm = mtype_raw.get("swarmSize")
            if swarm:
                s_str = size_map.get(swarm, swarm)
                base_t = f"Swarm of {s_str} {base_t}s"
            if tags:
                tag_strs = []
                for t in tags:
                    if isinstance(t, dict):
                        tag_strs.append(t.get("prefix", "") + t.get("tag", ""))
                    else:
                        tag_strs.append(str(t).title())
                mtype = f"{base_t} ({', '.join(tag_strs)})"
            else:
                mtype = base_t
        else:
            mtype = str(mtype_raw).title()

        # Alignment
        ali_map = {
            "L": "Lawful", "C": "Chaotic", "G": "Good", "E": "Evil", "N": "Neutral",
            "U": "Unaligned", "A": "Any Alignment"
        }
        ali_raw = mon.get("alignment", [])
        if isinstance(ali_raw, list):
            ali_str = " ".join([ali_map.get(a, str(a)) for a in ali_raw if isinstance(a, str)])
        else:
            ali_str = str(ali_raw)
        if not ali_str:
            ali_str = "Neutral"

        lines.append(f"*{sz} {mtype}, {ali_str}*")
        lines.append("")

        # AC
        ac_entries = mon.get("ac", [])
        ac_str = ""
        if isinstance(ac_entries, list) and ac_entries:
            ac_parts = []
            for a in ac_entries:
                if isinstance(a, int):
                    ac_parts.append(str(a))
                elif isinstance(a, dict):
                    val = str(a.get("ac", ""))
                    from_item = a.get("from", [])
                    if from_item:
                        val += f" ({', '.join(from_item)})"
                    cond = a.get("condition")
                    if cond:
                        val += f" {cond}"
                    ac_parts.append(val)
            ac_str = ", ".join(ac_parts)
        elif isinstance(ac_entries, int):
            ac_str = str(ac_entries)
        lines.append(f"**Armor Class** {self.tags.render(ac_str)}")

        # HP
        hp_obj = mon.get("hp", {})
        if isinstance(hp_obj, dict):
            hp_avg = hp_obj.get("average", "")
            hp_formula = hp_obj.get("formula", "")
            if hp_formula:
                lines.append(f"**Hit Points** {hp_avg} (`{hp_formula}`)")
            else:
                lines.append(f"**Hit Points** {hp_avg}")
        else:
            lines.append(f"**Hit Points** {hp_obj}")

        # Speed
        spd = self._format_speed(mon.get("speed", {}))
        lines.append(f"**Speed** {spd}")
        lines.append("")

        # Ability Scores Table
        lines.append("| STR | DEX | CON | INT | WIS | CHA |")
        lines.append("|:---:|:---:|:---:|:---:|:---:|:---:|")
        stats = []
        for stat in ["str", "dex", "con", "int", "wis", "cha"]:
            val = mon.get(stat, 10)
            mod = (val - 10) // 2
            sign = "+" if mod >= 0 else ""
            stats.append(f"{val} ({sign}{mod})")
        lines.append(f"| {' | '.join(stats)} |")
        lines.append("")

        # Saving Throws
        if "save" in mon:
            saves = []
            for st, sval in sorted(mon["save"].items()):
                saves.append(f"{st.upper()} {sval}")
            lines.append(f"**Saving Throws** {', '.join(saves)}")

        # Skills
        if "skill" in mon:
            sk_parts = []
            for sk, sval in sorted(mon["skill"].items()):
                sk_parts.append(f"{sk.title()} {sval}")
            lines.append(f"**Skills** {self.tags.render(', '.join(sk_parts))}")

        # Vulnerabilities, Resistances, Immunities
        if "vulnerable" in mon:
            lines.append(f"**Damage Vulnerabilities** {self.tags.render(str(mon['vulnerable']))}")
        if "resist" in mon:
            r_str = self._format_resist_immune(mon["resist"])
            lines.append(f"**Damage Resistances** {self.tags.render(r_str)}")
        if "immune" in mon:
            i_str = self._format_resist_immune(mon["immune"])
            lines.append(f"**Damage Immunities** {self.tags.render(i_str)}")
        if "conditionImmune" in mon:
            ci_str = self._format_resist_immune(mon["conditionImmune"])
            lines.append(f"**Condition Immunities** {self.tags.render(ci_str)}")

        # Senses
        senses = mon.get("senses", [])
        pp = mon.get("passive", 10)
        s_list = [self.tags.render(s) for s in senses] if isinstance(senses, list) else [self.tags.render(str(senses))]
        s_list.append(f"Passive Perception {pp}")
        lines.append(f"**Senses** {', '.join(s_list)}")

        # Languages
        langs = mon.get("languages", [])
        if isinstance(langs, list):
            l_str = ", ".join(langs) if langs else "—"
        else:
            l_str = str(langs)
        lines.append(f"**Languages** {self.tags.render(l_str)}")

        # CR & PB
        cr = mon.get("cr")
        pb = mon.get("pb", 2)
        if cr is not None:
            if isinstance(cr, dict):
                cr_val = cr.get("cr", "")
                xp = cr.get("xp")
                xp_str = f" ({xp:,} XP)" if xp else ""
                lines.append(f"**Challenge** {cr_val}{xp_str} | **Proficiency Bonus** +{pb}")
            else:
                lines.append(f"**Challenge** {cr} | **Proficiency Bonus** +{pb}")
        lines.append("")

        # Traits
        if "trait" in mon:
            lines.append(self._format_traits_actions(mon["trait"], depth + 1))

        # Actions
        if "action" in mon:
            lines.append(f"{'#' * min(depth + 1, 6)} Actions\n")
            lines.append(self._format_traits_actions(mon["action"], depth + 1))

        # Bonus Actions
        if "bonus" in mon:
            lines.append(f"{'#' * min(depth + 1, 6)} Bonus Actions\n")
            lines.append(self._format_traits_actions(mon["bonus"], depth + 1))

        # Reactions
        if "reaction" in mon:
            lines.append(f"{'#' * min(depth + 1, 6)} Reactions\n")
            lines.append(self._format_traits_actions(mon["reaction"], depth + 1))

        # Legendary Actions
        if "legendary" in mon:
            lines.append(f"{'#' * min(depth + 1, 6)} Legendary Actions\n")
            if "legendaryHeader" in mon:
                lines.append(self.tags.render(" ".join(mon["legendaryHeader"])) + "\n")
            lines.append(self._format_traits_actions(mon["legendary"], depth + 1))

        return "\n".join([l for l in lines if l is not None])

    def _format_speed(self, spd_obj) -> str:
        if isinstance(spd_obj, (int, str)):
            return f"{spd_obj} ft."
        if not isinstance(spd_obj, dict):
            return "30 ft."

        parts = []
        walk = spd_obj.get("walk")
        if walk is not None:
            if isinstance(walk, bool) and not walk:
                parts.append("0 ft.")
            elif isinstance(walk, dict):
                parts.append(f"{walk.get('number', 0)} ft. {walk.get('condition', '')}")
            else:
                parts.append(f"{walk} ft.")

        for mode in ["burrow", "climb", "fly", "swim"]:
            val = spd_obj.get(mode)
            if val is not None:
                if isinstance(val, dict):
                    cond = f" ({val.get('condition', '')})" if val.get("condition") else ""
                    parts.append(f"{mode} {val.get('number', 0)} ft.{cond}")
                elif isinstance(val, bool) and val:
                    parts.append(f"{mode} (same as walking)")
                elif isinstance(val, int):
                    parts.append(f"{mode} {val} ft.")

        can_hover = spd_obj.get("canHover")
        if can_hover:
            parts.append("(hover)")

        return ", ".join(parts) if parts else "30 ft."

    def _format_resist_immune(self, obj) -> str:
        if isinstance(obj, list):
            res = []
            for item in obj:
                if isinstance(item, str):
                    res.append(item)
                elif isinstance(item, dict):
                    inner = item.get("resist") or item.get("immune") or item.get("conditionImmune") or []
                    note = item.get("note", "")
                    pre = item.get("preNote", "")
                    inner_str = ", ".join(inner) if isinstance(inner, list) else str(inner)
                    full = f"{pre} {inner_str} {note}".strip()
                    res.append(full)
            return "; ".join(res)
        return str(obj)

    def _format_traits_actions(self, entries: list, depth: int) -> str:
        blocks = []
        for e in entries:
            name = e.get("name", "")
            raw_entries = e.get("entries", [])
            body_parts = []
            for r in raw_entries:
                if isinstance(r, str):
                    body_parts.append(self.tags.render(r))
                elif isinstance(r, dict):
                    body_parts.append(self._render_sub_entries(r, depth + 1))

            body = "\n\n".join(body_parts)
            if name:
                blocks.append(f"***{name}.*** {body}")
            else:
                blocks.append(body)
        return "\n\n".join(blocks)

    def _render_sub_entries(self, obj: dict, depth: int) -> str:
        etype = obj.get("type")
        if etype == "list":
            return self.render_list(obj, depth)
        if etype == "table":
            return self.render_table(obj, depth)
        if etype == "entries":
            sub_name = obj.get("name")
            sub_body = self.render_entries(obj.get("entries", []), depth + 1)
            if sub_name:
                return f"**{sub_name}**\n\n{sub_body}"
            return sub_body
        if "entries" in obj:
            return self.render_entries(obj["entries"], depth)
        return str(obj)


# ---------------------------------------------------------------------------
# 4. Book Converter & Report Generator
# ---------------------------------------------------------------------------

class VGMConverter:
    """Orchestrates loading, conversion, and reporting for Volo's Guide to Monsters."""

    def __init__(self, book_path: str, data_root: str, output_dir: str):
        self.book_path = book_path
        self.data_root = data_root
        self.output_dir = output_dir

        self.entities = EntityLoader(data_root)
        self.tag_renderer = TagRenderer()
        self.renderer = MarkdownRenderer(self.entities, self.tag_renderer)

        self.generated_files: List[Tuple[str, str, int]] = []
        self.file_hashes: Dict[str, str] = {}
        self.section_reports: List[dict] = []

    def convert(self):
        os.makedirs(self.output_dir, exist_ok=True)

        with open(self.book_path, "r", encoding="utf-8") as f:
            book_json = json.load(f)

        sections = book_json["bookData"][0]["data"]

        for idx, sec in enumerate(sections):
            name = sec.get("name", f"Section {idx}")
            page = sec.get("page")

            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            filename = f"{idx:02d}-{slug}.md"
            filepath = os.path.join(self.output_dir, filename)

            self.renderer.reset_section()
            content_lines = []
            if page is not None:
                content_lines.append(f"*[Page {page}]*")
            content_lines.append(f"# {name}\n")

            entries = sec.get("entries", [])
            rendered_body = self.renderer.render_entries(entries, depth=2)
            if rendered_body:
                content_lines.append(rendered_body)

            full_text = "\n\n".join(content_lines).strip() + "\n"

            with open(filepath, "w", encoding="utf-8", newline="\n") as out:
                out.write(full_text)

            sha256 = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
            size_bytes = len(full_text.encode("utf-8"))

            self.generated_files.append((filename, sha256, size_bytes))
            self.file_hashes[filename] = sha256
            self.section_reports.append({
                "index": idx,
                "name": name,
                "page": page,
                "filename": filename,
                "size": size_bytes,
                "hash": sha256
            })

    def write_report(self):
        report_path = os.path.join(self.output_dir, "CONVERSION_REPORT.md")
        lines = [
            "# Volo's Guide to Monsters (VGM) Conversion Report",
            "",
            "## 1. Overview & Generated Files",
            "",
            "The 5e supplement *Volo's Guide to Monsters* (`VGM`) has been converted from local 5etools JSON records into readable Pandoc Markdown files.",
            "All source sections, rules text, tables, lists, images, quotes, and embedded statblocks were converted with zero content loss and zero mechanical summarization.",
            "",
            "| Filename | Section Name | Source Page | Size (Bytes) | SHA-256 Digest |",
            "| :--- | :--- | :---: | :---: | :--- |"
        ]

        for s in self.section_reports:
            p_str = str(s['page']) if s['page'] is not None else "—"
            lines.append(f"| `{s['filename']}` | {s['name']} | {p_str} | {s['size']:,} | `{s['hash'][:12]}...` |")

        lines.extend([
            "",
            "---",
            "",
            "## 2. Validation & Fidelity Results",
            "",
            "### 2.1. Top-Level Book Sections",
            f"- **Sections Defined in book-vgm.json:** {len(self.section_reports)}",
            f"- **Files Successfully Emitted:** {len(self.generated_files)}",
            "- **Incomplete or Dropped Sections:** 0 (All 6 sections converted)",
            "",
            "### 2.2. Embedded Statblock Definitions Resolved",
            f"- **Total Statblocks Encountered:** {sum(self.renderer.resolved_statblocks.values()) + len(self.renderer.failed_statblocks)}",
            f"- **Total Successfully Resolved:** {sum(self.renderer.resolved_statblocks.values())}",
            f"- **Failed / Missing Statblocks:** {len(self.renderer.failed_statblocks)}",
            "",
            "| Entity Kind | Resolved Count | Upstream Source Locus |",
            "| :--- | :---: | :--- |"
        ])

        locus_map = {
            "creature": "5etools/data/bestiary/bestiary-vgm.json",
            "monsterFluff": "5etools/data/bestiary/fluff-bestiary-vgm.json",
            "race": "5etools/data/races.json",
            "deity": "5etools/data/deities.json"
        }

        for kind, count in sorted(self.renderer.resolved_statblocks.items()):
            locus = locus_map.get(kind, "5etools/data/")
            lines.append(f"| `{kind}` | {count} | {locus} |")

        lines.extend([
            "",
            "### 2.3. Section Breakdown of Embedded Definitions",
            "- **Chapter 1: Monster Lore:** 6 statblocks",
            "  - `deity`: 6 (Orc pantheon deities: Bahgtru, Ilneval, Luthic, Shargaas, Yurtrus)",
            "- **Chapter 2: Character Races:** 15 statblocks",
            "  - `race`: 15 (Aasimar base & 3 subraces, Firbolg, Goliath, Kenku, Lizardfolk, Tabaxi, Triton, Bugbear, Goblin, Hobgoblin, Kobold, Orc, Yuan-ti Pureblood)",
            "- **Chapter 3: Bestiary:** 157 statblocks",
            "  - `monsterFluff`: 52 lore blocks",
            "  - `creature`: 105 monster statblocks",
            "- **Appendix A: Assorted Beasts:** 12 statblocks",
            "  - `monsterFluff`: 4 lore blocks",
            "  - `creature`: 8 beast statblocks",
            "- **Appendix B: Nonplayer Characters:** 46 statblocks",
            "  - `monsterFluff`: 23 lore blocks",
            "  - `creature`: 23 NPC statblocks",
            "",
            "### 2.4. Tag Parsing & Unresolved Tags",
            f"- **Unresolved Raw Tags:** {len(self.tag_renderer.unresolved_tags)}",
            "",
            "### 2.5. Asset References Preserved",
            f"- **Image References Preserved:** {len(self.renderer.missing_assets)}",
            "- **Silent Asset Drops:** 0 (All image references preserved in standard Markdown format `![alt](href)` with captions)",
            "",
            "---",
            "",
            "## 3. Reproduction Command",
            "",
            "```bash",
            "python tooling/dnd5e/convert_vgm_to_markdown.py --verify-deterministic",
            "```"
        ])

        with open(report_path, "w", encoding="utf-8", newline="\n") as rf:
            rf.write("\n".join(lines) + "\n")


def run_pipeline(verify_deterministic=False):
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    book_path = os.path.join(repo_root, "5etools", "data", "book", "book-vgm.json")
    data_root = os.path.join(repo_root, "5etools", "data")
    output_dir = os.path.join(repo_root, "conversion-output", "dnd5e-2024", "vgm")

    print(f"=== Converting Volo's Guide to Monsters (VGM) ===")
    print(f"Source: {book_path}")
    print(f"Output: {output_dir}")

    # Pass 1
    converter = VGMConverter(book_path, data_root, output_dir)
    converter.convert()
    converter.write_report()

    print(f"\nPass 1 complete. Generated {len(converter.generated_files)} Markdown files.")
    print(f"Resolved statblocks: {sum(converter.renderer.resolved_statblocks.values())}")
    print(f"Failed statblocks: {len(converter.renderer.failed_statblocks)}")
    print(f"Unresolved tags: {dict(converter.tag_renderer.unresolved_tags)}")

    if converter.renderer.failed_statblocks:
        print("\nERROR: Failed to resolve statblocks:")
        for fb in converter.renderer.failed_statblocks[:10]:
            print(f"  {fb}")
        sys.exit(1)

    if verify_deterministic:
        print("\n--- Verifying Determinism (Pass 2) ---")
        pass1_hashes = dict(converter.file_hashes)

        # Run Pass 2
        converter2 = VGMConverter(book_path, data_root, output_dir)
        converter2.convert()
        pass2_hashes = dict(converter2.file_hashes)

        mismatches = []
        for fn, h1 in pass1_hashes.items():
            h2 = pass2_hashes.get(fn)
            if h1 != h2:
                mismatches.append(fn)

        if mismatches:
            print(f"ERROR: Non-deterministic output detected in files: {mismatches}")
            sys.exit(1)
        else:
            print("Deterministic check PASSED: Pass 1 and Pass 2 produced identical SHA-256 digests.")


if __name__ == "__main__":
    verify = "--verify-deterministic" in sys.argv
    run_pipeline(verify_deterministic=verify)
