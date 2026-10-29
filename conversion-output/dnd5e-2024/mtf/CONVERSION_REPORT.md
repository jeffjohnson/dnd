# Mordenkainen's Tome of Foes (MTF) Conversion Report

## 1. Overview & Generated Files

The 5e supplement *Mordenkainen's Tome of Foes* (`MTF`) has been converted from local 5etools JSON records into readable Pandoc Markdown files.
All source sections, rules text, tables, lists, images, quotes, and embedded statblocks were converted with zero content loss and zero mechanical summarization.

| Filename | Section Name | Source Page | Size (Bytes) | SHA-256 Digest |
| :--- | :--- | :---: | :---: | :--- |
| `00-the-blood-war.md` | The Blood War | 5 | 121,441 | `ad68ea78e17b...` |
| `01-elves.md` | Elves | 35 | 145,154 | `9e14e3155bb9...` |
| `02-dwarves-and-duergar.md` | Dwarves and Duergar | 65 | 87,111 | `e9577210cbd8...` |
| `03-gith-and-their-endless-war.md` | Gith and Their Endless War | 85 | 59,297 | `2973f561956a...` |
| `04-halflings-and-gnomes.md` | Halflings and Gnomes | 99 | 78,103 | `4368b7b00023...` |
| `05-bestiary.md` | Bestiary | — | 387,271 | `0c89a34dd9d2...` |
| `06-credits.md` | Credits | — | 4,128 | `bfcf3b047d68...` |

---

## 2. Validation & Fidelity Results

### 2.1. Top-Level Book Sections
- **Sections Defined in book-mtf.json:** 7
- **Files Successfully Emitted:** 7
- **Incomplete or Dropped Sections:** 0 (All 7 sections converted)

### 2.2. Embedded Statblock Definitions Resolved
- **Total Statblocks Encountered:** 205
- **Total Successfully Resolved:** 205
- **Failed / Missing Statblocks:** 0

| Entity Kind | Resolved Count | Upstream Source Locus |
| :--- | :---: | :--- |
| `creature` | 140 | 5etools/data/bestiary/bestiary-mtf.json |
| `item` | 2 | 5etools/data/items.json |
| `monsterFluff` | 47 | 5etools/data/bestiary/fluff-bestiary-mtf.json |
| `race` | 16 | 5etools/data/races.json |

### 2.3. Section Breakdown of Embedded Definitions
- **Chapter 1: The Blood War:** 9 statblocks
  - `race`: 9 (Tiefling subraces of the Lords of the Nine)
- **Chapter 2: Elves:** 4 statblocks
  - `race`: 3 (Eladrin, Sea Elf, Shadar-kai)
  - `item`: 1 (Elven Trinket)
- **Chapter 3: Dwarves and Duergar:** 1 statblock
  - `race`: 1 (Duergar)
- **Chapter 4: Gith and Their Endless War:** 3 statblocks
  - `race`: 2 (Githyanki, Githzerai - with base Gith race prelude and traits)
  - `item`: 1 (Greater Silver Sword)
- **Chapter 5: Halflings and Gnomes:** 1 statblock
  - `race`: 1 (Deep Gnome)
- **Chapter 6: Bestiary:** 187 statblocks
  - `monsterFluff`: 47 lore blocks
  - `creature`: 140 monster statblocks

### 2.4. Tag Parsing & Unresolved Tags
- **Unresolved Raw Tags:** 0

### 2.5. Asset References Preserved
- **Image References Preserved:** 75
- **Silent Asset Drops:** 0 (All image references preserved in standard Markdown format `![alt](href)` with captions)

---

## 3. Reproduction Command

```bash
python tooling/dnd5e/convert_mtf_to_markdown.py --verify-deterministic
```
