# 2024 Dungeon Master's Guide (XDMG) Markdown Conversion Report

**Date:** 2026-10-26
**Source Document:** `D:\analysis\dnd\5etools\data\book\book-xdmg.json`
**Output Directory:** `D:\analysis\dnd\conversion-output\dnd5e-2024\xdmg`
**Target Ruleset:** `dnd5e-2024` (2024 Dungeon Master's Guide, XDMG)

---

## 1. Summary of Generated Files

| Index | Section Name | Source Page | Output File | Size (Bytes) | SHA-256 Digest |
| :---: | :--- | :---: | :--- | :---: | :--- |
| 00 | Chapter 1: The Basics | p. 5 | `00-chapter-1-the-basics.md` | 61,114 | `b22d260b7ab1c4e5...` |
| 01 | Chapter 2: Running the Game | p. 21 | `01-chapter-2-running-the-game.md` | 107,806 | `bebed91bfb927d34...` |
| 02 | Chapter 3: DM's Toolbox | p. 51 | `02-chapter-3-dms-toolbox.md` | 171,912 | `ec8d6a01520b3503...` |
| 03 | Chapter 4: Creating Adventures | p. 105 | `03-chapter-4-creating-adventures.md` | 79,455 | `b2d1a38e13ec807a...` |
| 04 | Chapter 5: Creating Campaigns | p. 127 | `04-chapter-5-creating-campaigns.md` | 157,351 | `957da15fee2b359d...` |
| 05 | Chapter 6: Cosmology | p. 173 | `05-chapter-6-cosmology.md` | 144,888 | `d0ae5dd30522ad15...` |
| 06 | Chapter 7: Treasure | p. 213 | `06-chapter-7-treasure.md` | 350,984 | `c329328f0c4f2c9d...` |
| 07 | Chapter 8: Bastions | p. 334 | `07-chapter-8-bastions.md` | 70,732 | `fa69c4de844c8206...` |
| 08 | Appendix A: Lore Glossary | p. 354 | `08-appendix-a-lore-glossary.md` | 41,198 | `b8be8fea7f34f7b1...` |
| 09 | Appendix B: Maps | p. 365 | `09-appendix-b-maps.md` | 2,818 | `5a7de1f6856e6814...` |
| 10 | Appendix C: Tracking Sheets | N/A | `10-appendix-c-tracking-sheets.md` | 2,008 | `83b145b3b518e216...` |
| 11 | Credits | N/A | `11-credits.md` | 3,470 | `a88dd7c32cca43a9...` |

---

## 2. Validation & Fidelity Results

### 2.1. Top-Level Book Sections
- **Sections Defined in book-xdmg.json:** 12
- **Files Successfully Emitted:** 12
- **Incomplete or Dropped Sections:** 0 (All 12 sections converted)

### 2.2. Embedded Statblock Definitions Resolved
- **Total Statblocks Encountered:** 463
- **Total Successfully Resolved:** 463
- **Failed / Missing Statblocks:** 0

| Entity Kind | Resolved Count | Upstream Source Locus |
| :--- | :---: | :--- |
| `disease` | 3 | 5etools/data/ |
| `facility` | 35 | 5etools/data/ |
| `hazard` | 24 | 5etools/data/ |
| `item` | 369 | 5etools/data/ |
| `object` | 10 | 5etools/data/ |
| `reward` | 14 | 5etools/data/ |
| `trap` | 8 | 5etools/data/ |

### 2.3. Chapter Breakdown of Embedded Statblocks
- **Chapter 3 (DM's Toolbox):** 59 statblocks resolved across 5 entity types
  - `hazard`: 24 (trapshazards.json)
  - `trap`: 8 (trapshazards.json)
  - `reward`: 14 (rewards.json)
  - `object`: 10 (objects.json)
  - `disease`: 3 (conditionsdiseases.json)
- **Chapter 7 (Treasure):** 369 magic items resolved
  - `item`: 369 (items.json [item & itemGroup] + magicvariants.json)
- **Chapter 8 (Bastions):** 35 bastion facilities resolved
  - `facility`: 35 (bastions.json)

### 2.4. Tag Parsing & Unresolved Tags
- **Unresolved Raw Tags:** 0

### 2.5. Asset References Checked
- **Image References Recorded:** 160
- **Silent Asset Drops:** 0 (All image references preserved in Markdown format `![alt](href)` with captions)

---

## 3. Reproduction Command

```bash
python tooling/dnd5e/convert_xdmg_to_markdown.py --verify-deterministic
```
