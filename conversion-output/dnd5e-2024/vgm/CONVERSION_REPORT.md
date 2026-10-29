# Volo's Guide to Monsters (VGM) Conversion Report

## 1. Overview & Generated Files

The 5e supplement *Volo's Guide to Monsters* (`VGM`) has been converted from local 5etools JSON records into readable Pandoc Markdown files.
All source sections, rules text, tables, lists, images, quotes, and embedded statblocks were converted with zero content loss and zero mechanical summarization.

| Filename | Section Name | Source Page | Size (Bytes) | SHA-256 Digest |
| :--- | :--- | :---: | :---: | :--- |
| `00-monster-lore.md` | Monster Lore | 5 | 426,013 | `82c185b29045...` |
| `01-character-races.md` | Character Races | 103 | 70,692 | `ac563982aa83...` |
| `02-bestiary.md` | Bestiary | — | 329,381 | `337f4b38eed0...` |
| `03-assorted-beasts.md` | Assorted Beasts | — | 9,305 | `f82854f17653...` |
| `04-nonplayer-characters.md` | Nonplayer Characters | — | 34,522 | `5f53d2c12c8a...` |
| `05-credits.md` | Credits | — | 4,094 | `7ff1cc0cf443...` |

---

## 2. Validation & Fidelity Results

### 2.1. Top-Level Book Sections
- **Sections Defined in book-vgm.json:** 6
- **Files Successfully Emitted:** 6
- **Incomplete or Dropped Sections:** 0 (All 6 sections converted)

### 2.2. Embedded Statblock Definitions Resolved
- **Total Statblocks Encountered:** 236
- **Total Successfully Resolved:** 236
- **Failed / Missing Statblocks:** 0

| Entity Kind | Resolved Count | Upstream Source Locus |
| :--- | :---: | :--- |
| `creature` | 136 | 5etools/data/bestiary/bestiary-vgm.json |
| `deity` | 6 | 5etools/data/deities.json |
| `monsterFluff` | 79 | 5etools/data/bestiary/fluff-bestiary-vgm.json |
| `race` | 15 | 5etools/data/races.json |

### 2.3. Section Breakdown of Embedded Definitions
- **Chapter 1: Monster Lore:** 6 statblocks
  - `deity`: 6 (Orc pantheon deities: Bahgtru, Ilneval, Luthic, Shargaas, Yurtrus)
- **Chapter 2: Character Races:** 15 statblocks
  - `race`: 15 (Aasimar base & 3 subraces, Firbolg, Goliath, Kenku, Lizardfolk, Tabaxi, Triton, Bugbear, Goblin, Hobgoblin, Kobold, Orc, Yuan-ti Pureblood)
- **Chapter 3: Bestiary:** 157 statblocks
  - `monsterFluff`: 52 lore blocks
  - `creature`: 105 monster statblocks
- **Appendix A: Assorted Beasts:** 12 statblocks
  - `monsterFluff`: 4 lore blocks
  - `creature`: 8 beast statblocks
- **Appendix B: Nonplayer Characters:** 46 statblocks
  - `monsterFluff`: 23 lore blocks
  - `creature`: 23 NPC statblocks

### 2.4. Tag Parsing & Unresolved Tags
- **Unresolved Raw Tags:** 0

### 2.5. Asset References Preserved
- **Image References Preserved:** 111
- **Silent Asset Drops:** 0 (All image references preserved in standard Markdown format `![alt](href)` with captions)

---

## 3. Reproduction Command

```bash
python tooling/dnd5e/convert_vgm_to_markdown.py --verify-deterministic
```
