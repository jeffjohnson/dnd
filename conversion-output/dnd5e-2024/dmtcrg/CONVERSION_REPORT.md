# The Deck of Many Things Card Reference Guide (DMTCRG) Conversion Report

## 1. Overview & Generated Files

The 5e supplement *The Deck of Many Things Card Reference Guide* (`DMTCRG`) has been converted from local 5etools JSON records into readable Pandoc Markdown files.
All source sections, rules text, tables, lists, images, quotes, and card descriptions were converted with zero content loss and zero mechanical summarization.

| Filename | Section Name | Source Page | Size (Bytes) | SHA-256 Digest |
| :--- | :--- | :---: | :---: | :--- |
| `00-the-deck-of-many-things.md` | The Deck of Many Things | 3 | 5,133 | `262e41b6a657...` |
| `01-divinatory-uses.md` | Divinatory Uses | 6 | 5,582 | `ec265c247819...` |
| `02-adventure-spreads.md` | Adventure Spreads | 8 | 14,820 | `bfb1c4a9fcfc...` |
| `03-reading-the-cards.md` | Reading the Cards | 14 | 83,789 | `135b5ad54059...` |
| `04-credits.md` | Credits | 1 | 2,419 | `0334571ae4fd...` |

---

## 2. Validation & Fidelity Results

### 2.1. Top-Level Book Sections
- **Sections Defined in book-dmtcrg.json:** 5
- **Files Successfully Emitted:** 5
- **Incomplete or Dropped Sections:** 0 (All 5 sections converted)

### 2.2. Embedded Statblock Definitions Resolved
- **Total Statblocks Encountered:** 0
- **Dropped or Unresolved Entities:** 0

### 2.3. Tag Parsing & Unresolved Tags
- **Unresolved Raw Tags:** 0

### 2.4. Asset References Preserved
- **Image References Preserved:** 78
- **Silent Asset Drops:** 0 (All image references preserved in standard Markdown format `![alt](href)` with captions)

---

## 3. Reproduction Command

```bash
python tooling/dnd5e/convert_dmtcrg_to_markdown.py --verify-deterministic
```
