# Tasha's Cauldron of Everything (TCE) Conversion Report

## 1. Overview & Generated Files

The 5e supplement *Tasha's Cauldron of Everything* (`TCE`) has been converted from local 5etools JSON records into readable Pandoc Markdown files.
All source sections, rules text, tables, lists, images, quotes, and embedded statblocks were converted with zero content loss and zero mechanical summarization.

| Filename | Section Name | Source Page | Size (Bytes) | SHA-256 Digest |
| :--- | :--- | :---: | :---: | :--- |
| `00-using-this-book.md` | Using This Book | 4 | 8,174 | `4885e6a00c66...` |
| `01-character-options.md` | Character Options | 7 | 186,979 | `e2c726243863...` |
| `02-group-patrons.md` | Group Patrons | 83 | 76,393 | `703cbdced3f0...` |
| `03-magical-miscellany.md` | Magical Miscellany | 105 | 83,414 | `33cc9ae300f2...` |
| `04-dungeon-master-s-tools.md` | Dungeon Master's Tools | 139 | 167,732 | `9f522ee74df5...` |
| `05-credits.md` | Credits | — | 1,391 | `1d5573e100bc...` |

---

## 2. Validation & Fidelity Results

### 2.1. Top-Level Book Sections
- **Sections Defined in book-tce.json:** 6
- **Files Successfully Emitted:** 6
- **Incomplete or Dropped Sections:** 0 (All 6 sections converted)

### 2.2. Embedded Statblock Definitions Resolved
- **Total Statblocks Encountered:** 130
- **Total Successfully Resolved:** 130
- **Failed / Missing Statblocks:** 0

| Entity Kind | Resolved Count | Upstream Source Locus |
| :--- | :---: | :--- |
| `class` | 4 | 5etools/data/class/class-artificer.json & class-sidekick.json |
| `feat` | 15 | 5etools/data/feats.json |
| `hazard` | 7 | 5etools/data/trapshazards.json |
| `item` | 48 | 5etools/data/items.json & magicvariants.json |
| `optfeature` | 26 | 5etools/data/optionalfeatures.json |
| `subclass` | 30 | 5etools/data/class/class-*.json & fluff-class-*.json |

### 2.3. Section Breakdown of Embedded Definitions
- **Chapter 1: Character Options:** 75 statblocks
  - `class`: 1 (Artificer)
  - `subclass`: 30 (Alchemist, Armorer, Beast, Creation, Eloquence, Peace, Twilight, Stars, Wildfire, Psi Warrior, Rune Knight, Mercy, Astral Self, Fey Wanderer, Swarmkeeper, Phantom, Soulknife, Aberrant Mind, Clockwork Soul, Fathomless, Genie, Bladesinging, Scribes, etc.)
  - `optfeature`: 26 (Fighting Styles, Maneuvers, and Eldritch Invocations)
  - `feat`: 15 (Artificer Initiate, Chef, Crusher, Fey Touched, Shadow Touched, Telekinetic, Telepathic, etc.)
- **Chapter 3: Magical Miscellany:** 48 statblocks
  - `item`: 48 (Magic tattoos, artifacts, class focuses, wondrous items)
- **Chapter 4: Dungeon Master's Tools:** 10 statblocks
  - `class`: 3 (Sidekick classes: Expert, Spellcaster, Warrior)
  - `hazard`: 7 (Environmental and wilderness hazards)

### 2.4. Tag Parsing & Unresolved Tags
- **Unresolved Raw Tags:** 0

### 2.5. Asset References Preserved
- **Image References Preserved:** 133
- **Silent Asset Drops:** 0 (All image references preserved in standard Markdown format `![alt](href)` with captions)

---

## 3. Reproduction Command

```bash
python tooling/dnd5e/convert_tce_to_markdown.py --verify-deterministic
```
