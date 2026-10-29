# 2014 D&D 5e Dungeon Master's Guide (DMG) Conversion Report

## 1. Executive Summary

The 2014 D&D 5e *Dungeon Master's Guide* (`DMG`) has been converted from local 5etools JSON records into readable Pandoc Markdown files.
All source sections, rules text, tables, lists, images, quotes, and embedded statblocks were converted with zero content loss and zero mechanical summarization.

| Filename | Section Name | Source Page | Size (Bytes) | SHA-256 Digest |
| :--- | :--- | :---: | :---: | :--- |
| `00-introduction.md` | Introduction | 4 | 13,897 | `0d3fc9df3cb8...` |
| `01-a-world-of-your-own.md` | A World of Your Own | 9 | 161,241 | `de22ba9ec597...` |
| `02-creating-a-multiverse.md` | Creating a Multiverse | 43 | 110,390 | `ecb5c517ec6d...` |
| `03-creating-adventures.md` | Creating Adventures | 71 | 73,494 | `ea497ca44972...` |
| `04-creating-nonplayer-characters.md` | Creating Nonplayer Characters | 88 | 29,001 | `5494494de167...` |
| `05-adventure-environments.md` | Adventure Environments | 99 | 78,903 | `95769da087ae...` |
| `06-between-adventures.md` | Between Adventures | 125 | 33,166 | `8f6229734acc...` |
| `07-treasure.md` | Treasure | 133 | 431,015 | `2f93bf203b92...` |
| `08-running-the-game.md` | Running the Game | 235 | 126,985 | `95daca4421b2...` |
| `09-dungeon-masters-workshop.md` | Dungeon Master's Workshop | 263 | 118,078 | `9dcbfa2e309b...` |
| `10-appendix-a-random-dungeons.md` | Appendix A: Random Dungeons | 290 | 46,348 | `8b2aa4c91c16...` |
| `11-appendix-b-monster-lists.md` | Appendix B: Monster Lists | 302 | 1,509 | `d18a6c8bc3a1...` |
| `12-appendix-c-maps.md` | Appendix C: Maps | 310 | 840 | `d910b0586e7d...` |
| `13-appendix-d-dungeon-master-inspiration.md` | Appendix D: Dungeon Master Inspiration | 316 | 2,763 | `7886b94c6323...` |
| `14-credits.md` | Credits | — | 4,296 | `7c68b2afa397...` |

---

## 2. Validation & Fidelity Results

### 2.1. Top-Level Book Sections
- **Sections Defined in book-dmg.json:** 15
- **Files Successfully Emitted:** 15
- **Incomplete or Dropped Sections:** 0 (All 15 sections converted)

### 2.2. Embedded Statblock Definitions Resolved
- **Total Statblocks Encountered:** 65
- **Total Successfully Resolved:** 65
- **Failed / Missing Statblocks:** 0

| Entity Kind | Resolved Count | Upstream Source Locus |
| :--- | :---: | :--- |
| `action` | 6 | 5etools/data/actions.json |
| `disease` | 3 | 5etools/data/conditionsdiseases.json |
| `item` | 26 | 5etools/data/items.json & fluff-items.json |
| `object` | 7 | 5etools/data/objects.json |
| `reward` | 14 | 5etools/data/rewards.json |
| `variantrule` | 9 | 5etools/data/variantrules.json |

### 2.3. Section Breakdown of Embedded Definitions
- **Chapter 6: Between Adventures:** 9 downtime activity variant rules
- **Chapter 7: Treasure:**
  - 12 embedded item statblocks (4 sentient items + 8 artifacts)
  - 14 supernatural gift / blessing / charm statblocks
  - 460 magic items appended under Magic Items Catalog (A-Z) from `items.json` & `fluff-items.json`
- **Chapter 8: Running the Game:**
  - 14 poison item statblocks
  - 7 siege equipment object statblocks
  - 3 disease statblocks
- **Chapter 9: Dungeon Master's Workshop:** 6 combat option action statblocks

### 2.4. Tag Parsing & Unresolved Tags
- **Unresolved Raw Tags:** 0

### 2.5. Asset References Preserved
- **Image References Preserved:** 312
- **Silent Asset Drops:** 0 (All image references preserved in standard Markdown format `![alt](href)` with captions)

---

## 3. Reproduction Command

```bash
python tooling/dnd5e/convert_dmg_to_markdown.py --verify-deterministic
```
