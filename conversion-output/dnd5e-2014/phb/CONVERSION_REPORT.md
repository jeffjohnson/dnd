# 2014 D&D 5e Player's Handbook (PHB) Conversion Report

## 1. Executive Summary

The 2014 D&D 5e *Player's Handbook* (`PHB`) has been converted from local 5etools JSON records into readable Pandoc Markdown files.
All source sections, rules text, tables, lists, images, quotes, and embedded statblocks were converted with zero content loss and zero mechanical summarization.

| Filename | Section Name | Source Page | Size (Bytes) | SHA-256 Digest |
| :--- | :--- | :---: | :---: | :--- |
| `00-introduction.md` | Introduction | 5 | 22,258 | `6bce7a7cfa7a...` |
| `01-step-by-step-characters.md` | Step-by-Step Characters | 11 | 25,910 | `d06bc0ebc6cc...` |
| `02-races.md` | Races | 17 | 71,608 | `02adc9ad2090...` |
| `03-classes.md` | Classes | 45 | 317,482 | `7d6f636e9de3...` |
| `04-personality-and-background.md` | Personality and Background | 121 | 86,011 | `6fbd03e1b4bd...` |
| `05-equipment.md` | Equipment | 143 | 58,251 | `065e8e114a95...` |
| `06-customization-options.md` | Customization Options | 163 | 31,072 | `58f67f2c1a65...` |
| `07-using-ability-scores.md` | Using Ability Scores | 173 | 33,599 | `83c6d8bafe78...` |
| `08-adventuring.md` | Adventuring | 181 | 33,978 | `b6e16ca91f04...` |
| `09-combat.md` | Combat | 189 | 47,133 | `e19ce03e83c2...` |
| `10-spellcasting.md` | Spellcasting | 201 | 21,646 | `dcef29e94f3b...` |
| `11-spells.md` | Spells | 207 | 386,524 | `1cb29b2ab0ea...` |
| `12-conditions.md` | Conditions | 289 | 6,260 | `ff4a028297bf...` |
| `13-gods-of-the-multiverse.md` | Gods of the Multiverse | 293 | 26,149 | `b47e4a570c27...` |
| `14-the-planes-of-existence.md` | The Planes of Existence | 300 | 16,572 | `a12c0cd37d08...` |
| `15-credits.md` | Credits | — | 3,417 | `58e0e6e2ecd6...` |

---

## 2. Validation & Fidelity Results

### 2.1. Top-Level Book Sections
- **Sections Defined in book-phb.json:** 16
- **Files Successfully Emitted:** 16
- **Incomplete or Dropped Sections:** 0 (All 16 sections converted)

### 2.2. Embedded Statblock Definitions Resolved
- **Total Statblocks Encountered:** 421
- **Total Successfully Resolved:** 421
- **Failed / Missing Statblocks:** 0

| Entity Kind | Resolved Count | Upstream Source Locus |
| :--- | :---: | :--- |
| `action` | 11 | 5etools/data/actions.json |
| `background` | 13 | 5etools/data/backgrounds.json & fluff-backgrounds.json |
| `class` | 12 | 5etools/data/class/class-*.json & fluff-class-*.json |
| `condition` | 15 | 5etools/data/conditionsdiseases.json |
| `race` | 9 | 5etools/data/races.json & fluff-races.json |
| `spell` | 361 | 5etools/data/spells/spells-phb.json |

### 2.3. Section Breakdown of Embedded Definitions
- **Chapter 2: Races:** 9 race statblocks (with ability score increases, subraces, and racial lore)
- **Chapter 3: Classes:** 12 class statblocks (with hit dice, saving throws, full progression tables, features, subclasses, and subclass features)
- **Chapter 4: Personality and Background:** 13 background statblocks (with skills, tools, languages, equipment, traits, and variants)
- **Chapter 6: Customization Options:** 42 feats appended from `feats.json`
- **Chapter 9: Combat:** 11 action statblocks
- **Chapter 11: Spells:** 361 spell statblocks
- **Appendix A: Conditions:** 15 condition statblocks

### 2.4. Tag Parsing & Unresolved Tags
- **Unresolved Raw Tags:** 0

### 2.5. Asset References Preserved
- **Image References Preserved:** 68
- **Silent Asset Drops:** 0 (All image references preserved in standard Markdown format `![alt](href)` with captions)

---

## 3. Reproduction Command

```bash
python tooling/dnd5e/convert_phb_to_markdown.py --verify-deterministic
```
