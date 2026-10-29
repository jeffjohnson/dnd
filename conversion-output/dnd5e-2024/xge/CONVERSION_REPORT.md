# Xanathar's Guide to Everything (XGE) Conversion Report

## 1. Overview & Generated Files

The 5e supplement *Xanathar's Guide to Everything* (`XGE`) has been converted from local 5etools JSON records into readable Pandoc Markdown files.
All source sections, rules text, tables, lists, images, quotes, and embedded statblocks were converted with zero content loss and zero mechanical summarization.

| Filename | Section Name | Source Page | Size (Bytes) | SHA-256 Digest |
| :--- | :--- | :---: | :---: | :--- |
| `00-introduction.md` | Introduction | 4 | 8,679 | `dfc18299f637...` |
| `01-character-options.md` | Character Options | 7 | 37,843 | `3900fca97408...` |
| `02-dungeon-master-s-tools.md` | Dungeon Master's Tools | 77 | 149,475 | `9dc47cf804f7...` |
| `03-spells.md` | Spells | 147 | 1,401 | `f770d78764a7...` |
| `04-shared-campaigns.md` | Shared Campaigns | 172 | 8,841 | `833edb99d18e...` |
| `05-character-names.md` | Character Names | 173 | 1,109 | `9b3eaa1382d9...` |
| `06-credits.md` | Credits | — | 4,538 | `5c85737df6be...` |

---

## 2. Validation & Fidelity Results

### 2.1. Top-Level Book Sections
- **Sections Defined in book-xge.json:** 7
- **Files Successfully Emitted:** 7
- **Incomplete or Dropped Sections:** 0 (All 7 sections converted)

### 2.2. Embedded Statblock Definitions Resolved
- **Total Statblocks Encountered:** 12
- **Total Successfully Resolved:** 12
- **Failed / Missing Statblocks:** 0

| Entity Kind | Resolved Count | Upstream Source Locus |
| :--- | :---: | :--- |
| `trap` | 12 | 5etools/data/trapshazards.json |

### 2.3. Section Breakdown of Embedded Definitions
- **Chapter 2: Dungeon Master's Tools (Traps Revisited):** 12 trap statblocks
  - Simple Traps (6): Bear Trap, Crossbow Trap, Falling Portcullis, Fiery Blast Trap, Net Trap, Pit Trap, Poison Needle Trap, Scything Blade Trap, Sleep of Ages Trap
  - Complex Traps (3): Path of Blades, Poisoned Tempest, Sphere of Crushing Doom

### 2.4. Tag Parsing & Unresolved Tags
- **Unresolved Raw Tags:** 0

### 2.5. Asset References Preserved
- **Image References Preserved:** 24
- **Silent Asset Drops:** 0 (All image references preserved in standard Markdown format `![alt](href)` with captions)

---

## 3. Reproduction Command

```bash
python tooling/dnd5e/convert_xge_to_markdown.py --verify-deterministic
```
