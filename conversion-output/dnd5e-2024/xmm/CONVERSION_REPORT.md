# 2024 Monster Manual (XMM) Markdown Conversion Report

**Date:** 2026-10-26
**Source Document:** `D:\analysis\dnd\5etools\data\book\book-xmm.json`
**Output Directory:** `D:\analysis\dnd\conversion-output\dnd5e-2024\xmm`
**Target Ruleset:** `dnd5e-2024` (2024 Monster Manual, XMM)

---

## 1. Summary of Generated Files

| Index | Section Name | Source Page | Output File | Size (Bytes) | SHA-256 Digest |
| :---: | :--- | :---: | :--- | :---: | :--- |
| 00 | How to Use a Monster | p. 5 | `00-how-to-use-a-monster.md` | 21,868 | `471924b2512a7536...` |
| 01 | Monsters A to Z | p. 10 | `01-monsters-a-to-z.md` | 949,438 | `f23b54bcb807cf7b...` |
| 02 | Animals | p. 348 | `02-animals.md` | 79,056 | `41501fffa459183b...` |
| 03 | Monster Lists | p. 374 | `03-monster-lists.md` | 35,678 | `983e3441920c69b6...` |
| 04 | Credits | p. 2 | `04-credits.md` | 4,189 | `f4d6ad79f8ddaf80...` |

---

## 2. Validation & Fidelity Results

### 2.1. Top-Level Book Sections
- **Sections Defined in book-xmm.json:** 5
- **Files Successfully Emitted:** 5
- **Incomplete or Dropped Sections:** 0 (All 5 sections converted)

### 2.2. Embedded Statblock Definitions Resolved
- **Total Statblocks Encountered:** 750
- **Total Successfully Resolved:** 750
- **Failed / Missing Statblocks:** 0

| Entity Kind | Resolved Count | Upstream Source Locus |
| :--- | :---: | :--- |
| `creature` | 503 | 5etools/data/bestiary/ |
| `monsterFluff` | 247 | 5etools/data/bestiary/ |

### 2.3. Section Breakdown of Embedded Definitions
- **Monsters A to Z (Section 1):** 654 embedded statblocks resolved
  - `creature`: 407 (bestiary/bestiary-xmm.json)
  - `monsterFluff`: 247 (bestiary/fluff-bestiary-xmm.json)
- **Animals (Section 2):** 96 creature statblocks resolved
  - `creature`: 96 (bestiary/bestiary-xmm.json)
- **Total Unique Creatures:** 503 / 503 (100% of 2024 Monster Manual bestiary)

### 2.4. Tag Parsing & Unresolved Tags
- **Unresolved Raw Tags:** 0

### 2.5. Asset References Checked
- **Image References Recorded:** 322
- **Silent Asset Drops:** 0 (All image references preserved in Markdown format `![alt](href)` with captions)

---

## 3. Reproduction Command

```bash
python tooling/dnd5e/convert_xmm_to_markdown.py --verify-deterministic
```
