# Arcana Unleashed (AU) Conversion Report

## 1. Overview & Generated Files

The 2024-generation supplement *Arcana Unleashed* (`AU`) has been converted from local 5etools JSON records into readable Pandoc Markdown files.
All source sections, rules text, tables, lists, images, quotes, and embedded statblocks were converted with zero content loss and zero mechanical summarization.

| Filename | Section Name | Source Page | Size (Bytes) | SHA-256 Digest |
| :--- | :--- | :---: | :---: | :--- |
| `00-introduction-a-multiverse-of-magic.md` | Introduction: A Multiverse of Magic | 4 | 5,943 | `9e45fcd897cd...` |
| `01-chapter-1-character-options.md` | Chapter 1: Character Options | 7 | 71,920 | `532bc5f68c70...` |
| `02-chapter-2-spells.md` | Chapter 2: Spells | 35 | 31,499 | `2ca82b599292...` |
| `03-chapter-3-creating-magical-worlds.md` | Chapter 3: Creating Magical Worlds | 47 | 109,645 | `81f35afd2d0a...` |
| `04-chapter-4-magical-factions.md` | Chapter 4: Magical Factions | 79 | 118,122 | `4cfb871070d8...` |
| `05-chapter-5-magic-items.md` | Chapter 5: Magic Items | 115 | 67,446 | `1dab05dcecc3...` |
| `06-chapter-6-magical-creatures.md` | Chapter 6: Magical Creatures | 135 | 37,399 | `a5271ccc50bd...` |
| `07-appendix-tomb-of-the-shadow-serpents.md` | Appendix: Tomb of the Shadow Serpents | 151 | 26,649 | `c8b1206516c9...` |
| `08-credits.md` | Credits | — | 10,632 | `2c9731e306a1...` |

---

## 2. Validation & Fidelity Results

### 2.1. Top-Level Book Sections
- **Sections Defined in book-au.json:** 9
- **Files Successfully Emitted:** 9
- **Incomplete or Dropped Sections:** 0 (All 9 sections converted)

### 2.2. Embedded Statblock Definitions Resolved
- **Total Statblocks Encountered:** 208
- **Total Successfully Resolved:** 208
- **Failed / Missing Statblocks:** 0

| Entity Kind | Resolved Count | Upstream Source Locus |
| :--- | :---: | :--- |
| `background` | 10 | 5etools/data/backgrounds.json |
| `creature` | 20 | 5etools/data/bestiary/bestiary-au.json |
| `facility` | 9 | 5etools/data/bastions.json |
| `feat` | 29 | 5etools/data/feats.json |
| `item` | 91 | 5etools/data/items.json & magicvariants.json |
| `monsterFluff` | 8 | 5etools/data/bestiary/fluff-bestiary-au.json |
| `spell` | 33 | 5etools/data/spells/spells-au.json |
| `subclass` | 8 | 5etools/data/class/class-*.json & fluff-class-*.json |

### 2.3. Section Breakdown of Embedded Definitions
- **Chapter 1: Character Options:** 47 statblocks
  - `subclass`: 8 (Arcana Domain, Arcane Archer, Warrior of the Mystic Arts, Vestige Patron, Conjurer, Enchanter, Necromancer, Transmuter)
  - `background`: 10 (Agent of the Ninth Quill, Conclave Bejeweled, etc.)
  - `feat`: 29 (Abjuration Adept, Arcane Infiltrator, etc.)
- **Chapter 2: Spells:** 33 statblocks
  - `spell`: 33 (Aura of Evasion, Chrono-Shift, etc.)
- **Chapter 4: Magical Factions:** 18 statblocks
  - `facility`: 9 (Bastion special facilities: Circus Tent, Faction Sanctum, etc.)
  - `item`: 9 (Faction trinkets)
- **Chapter 5: Magic Items:** 56 statblocks
  - `item`: 56 (Wondrous items, magic weapons, evolving items, and generic variants)
- **Chapter 6: Magical Creatures:** 27 statblocks
  - `monsterFluff`: 8 lore blocks
  - `creature`: 19 monster statblocks

### 2.4. Tag Parsing & Unresolved Tags
- **Unresolved Raw Tags:** 0

### 2.5. Asset References Preserved
- **Image References Preserved:** 63
- **Silent Asset Drops:** 0 (All image references preserved in standard Markdown format `![alt](href)` with captions)

---

## 3. Reproduction Command

```bash
python tooling/dnd5e/convert_au_to_markdown.py --verify-deterministic
```
