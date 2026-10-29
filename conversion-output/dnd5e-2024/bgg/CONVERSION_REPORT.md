# Bigby Presents: Glory of the Giants (BGG) Conversion Report

## 1. Overview & Generated Files

The 5e supplement *Bigby Presents: Glory of the Giants* (`BGG`) has been converted from local 5etools JSON records into readable Pandoc Markdown files.
All source sections, rules text, tables, lists, images, quotes, and embedded statblocks were converted with zero content loss and zero mechanical summarization.

| Filename | Section Name | Source Page | Size (Bytes) | SHA-256 Digest |
| :--- | :--- | :---: | :---: | :--- |
| `00-diancastra-s-saga.md` | Diancastra's Saga | 4 | 23,579 | `28c4e57e4e39...` |
| `01-chapter-1-character-creation.md` | Chapter 1: Character Creation | 11 | 25,294 | `8fca129896fe...` |
| `02-chapter-2-giants-in-play.md` | Chapter 2: Giants in Play | 21 | 81,625 | `0c3c5aec4b5e...` |
| `03-chapter-3-giant-adventures.md` | Chapter 3: Giant Adventures | 43 | 83,040 | `b80b6998d390...` |
| `04-chapter-4-giant-enclaves.md` | Chapter 4: Giant Enclaves | 67 | 94,820 | `4dcffe4a512d...` |
| `05-chapter-5-giant-treasures.md` | Chapter 5: Giant Treasures | 105 | 47,204 | `5b77b1ce4540...` |
| `06-chapter-6-bestiary.md` | Chapter 6: Bestiary | 119 | 207,346 | `6a8012ea7d4d...` |
| `07-appendix-a-concept-art.md` | Appendix A: Concept Art | 190 | 1,190 | `9c02453ee317...` |
| `08-appendix-b-adventure-hooks.md` | Appendix B: Adventure Hooks | 192 | 3,835 | `0bdb8fa58eef...` |
| `09-credits.md` | Credits | — | 3,419 | `33e97f98e4a2...` |

---

## 2. Validation & Fidelity Results

### 2.1. Top-Level Book Sections
- **Sections Defined in book-bgg.json:** 10
- **Files Successfully Emitted:** 10
- **Incomplete or Dropped Sections:** 0 (All 10 sections converted)

### 2.2. Embedded Statblock Definitions Resolved
- **Total Statblocks Encountered:** 182
- **Total Successfully Resolved:** 182
- **Failed / Missing Statblocks:** 0

| Entity Kind | Resolved Count | Upstream Source Locus |
| :--- | :---: | :--- |
| `creature` | 72 | 5etools/data/bestiary/bestiary-bgg.json |
| `feat` | 10 | 5etools/data/feats.json |
| `item` | 27 | 5etools/data/items.json & magicvariants.json |
| `monsterFluff` | 54 | 5etools/data/bestiary/fluff-bestiary-bgg.json |
| `subclass` | 1 | 5etools/data/class/class-barbarian.json |
| `table` | 18 | 5etools/data/generated/gendata-tables.json |

### 2.3. Section Breakdown of Embedded Definitions
- **Chapter 1: Character Creation:** 11 statblocks
  - `subclass`: 1 (Path of the Giant barbarian subclass)
  - `feat`: 10 (Giant feats and background feats: Strike of the Giants, Rune Shaper, Keenness, Guile, Fury, etc.)
- **Chapter 3: Giant Adventures:** 18 statblocks
  - `table`: 18 (Giant and planar encounter tables)
- **Chapter 5: Giant Treasures:** 27 statblocks
  - `item`: 27 (Giant magic items, runic artifacts, prehistoric figurines, zephyr armor, etc.)
- **Chapter 6: Bestiary:** 126 statblocks
  - `monsterFluff`: 54 lore blocks
  - `creature`: 72 monster statblocks

### 2.4. Tag Parsing & Unresolved Tags
- **Unresolved Raw Tags:** 0

### 2.5. Asset References Preserved
- **Image References Preserved:** 127
- **Silent Asset Drops:** 0 (All image references preserved in standard Markdown format `![alt](href)` with captions)

---

## 3. Reproduction Command

```bash
python tooling/dnd5e/convert_bgg_to_markdown.py --verify-deterministic
```
