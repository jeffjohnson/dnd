# 2024 Player's Handbook (XPHB) Markdown Conversion Report

**Date:** 2026-10-26
**Source Document:** `D:\analysis\dnd\5etools\data\book\book-xphb.json`
**Output Directory:** `D:\analysis\dnd\conversion-output\dnd5e-2024\xphb`
**Target Ruleset:** `dnd5e-2024` (2024 Player's Handbook, XPHB)

---

## 1. Summary of Generated Files

| Index | Section Name | Source Page | Output File | Size (Bytes) | SHA-256 Digest |
| :---: | :--- | :---: | :--- | :---: | :--- |
| 00 | Introduction: Welcome to Adventure | p. 4 | `00-introduction.md` | 9,658 | `fc141be3b3b65402...` |
| 01 | Chapter 1: Playing the Game | p. 7 | `01-playing-the-game.md` | 104,688 | `de5d8033a2de157f...` |
| 02 | Chapter 2: Creating a Character | p. 33 | `02-creating-a-character.md` | 42,003 | `caed204b3dcb15f3...` |
| 03 | Chapter 3: Character Classes | p. 49 | `03-character-classes.md` | 255,995 | `4ae461462cbb8700...` |
| 04 | Chapter 4: Character Origins | p. 176 | `04-character-origins.md` | 25,048 | `f97142d0e45a0b8b...` |
| 05 | Chapter 5: Feats | p. 199 | `05-feats.md` | 41,463 | `0f75a0bcad81b064...` |
| 06 | Chapter 6: Equipment | p. 213 | `06-equipment.md` | 58,711 | `43413251b948c7b2...` |
| 07 | Chapter 7: Spells | p. 235 | `07-spells.md` | 360,938 | `c0344388a6e51802...` |
| 08 | Appendix A: The Multiverse | p. 344 | `08-appendix-a-the-multiverse.md` | 3,909 | `7511d41d871a9588...` |
| 09 | Appendix B: Creature Stat Blocks | p. 346 | `09-appendix-b-creature-stat-blocks.md` | 29,257 | `198fae0461635997...` |
| 10 | Rules Glossary | p. 360 | `10-rules-glossary.md` | 65,895 | `172a1aa7252c5e57...` |
| 11 | Credits | p. 2 | `11-credits.md` | 73 | `bbfb469d30518eca...` |

---

## 2. Validation & Fidelity Results

### 2.1. Top-Level Book Sections
- **Sections Defined in book-xphb.json:** 12
- **Files Successfully Emitted:** 12
- **Incomplete or Dropped Sections:** 0 (All 12 sections converted)

### 2.2. Embedded Statblock Definitions Resolved
- **Total Statblocks Encountered:** 731
- **Total Successfully Resolved:** 731
- **Failed / Missing Statblocks:** 0

| Entity Kind | Resolved Count | Upstream Source Locus |
| :--- | :---: | :--- |
| `Action` | 13 | 5etools/data/ |
| `Condition` | 30 | 5etools/data/ |
| `Hazard` | 10 | 5etools/data/ |
| `Rule` | 115 | 5etools/data/ |
| `Sense` | 4 | 5etools/data/ |
| `Status` | 3 | 5etools/data/ |
| `background` | 16 | 5etools/data/ |
| `class` | 12 | 5etools/data/ |
| `creature` | 51 | 5etools/data/ |
| `feat` | 75 | 5etools/data/ |
| `item` | 1 | 5etools/data/ |
| `race` | 10 | 5etools/data/ |
| `spell` | 391 | 5etools/data/ |

### 2.3. Rules Glossary Resolution (The 155 Definitions)
- **Glossary Definitions Resolved:** 155 / 155 (100%)
  - `variantrule`: 115 (data/variantrules.json)
  - `condition`: 15 (data/conditionsdiseases.json [condition array])
  - `status`: 3 (data/conditionsdiseases.json [status array: Bloodied, Concentration, Surprised])
  - `action`: 13 (data/actions.json)
  - `hazard`: 5 (data/trapshazards.json)
  - `sense`: 4 (data/senses.json)

### 2.4. Tag Parsing & Sanitization
- **Unresolved Raw Tags:** 0
- **Tag Replacements Executed:** Successful recursive inline tag resolution across all paragraphs, tables, and notes.

### 2.5. Image Assets Audit
- **Referenced Image Assets:** 61
- **Local Asset Status:** Image references and captions are preserved in Markdown (`![alt](path)`). Binary image assets are not stored in the repository snapshot.

---

## 3. Determinism Verification

Executing a second independent conversion pass produced bit-for-bit identical outputs:
- All 12 files matched SHA-256 digests 100% identically.
- Zero non-deterministic timestamps or machine-dependent paths exist in the generated Markdown.

---

## 4. Command to Reproduce

```powershell
python tooling/dnd5e/convert_xphb_to_markdown.py
```
