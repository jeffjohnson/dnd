# The Book of Many Things (BMT) Conversion Report

## 1. Overview & Generated Files

The 5e supplement *The Book of Many Things* (`BMT`) has been converted from local 5etools JSON records into readable Pandoc Markdown files.
All source sections, rules text, tables, lists, images, quotes, and embedded statblocks were converted with zero content loss and zero mechanical summarization.

| Filename | Section Name | Source Page | Size (Bytes) | SHA-256 Digest |
| :--- | :--- | :---: | :---: | :--- |
| `00-chapter-1-fool.md` | Chapter 1: Fool | 4 | 18,209 | `f806c09ba1e6...` |
| `01-chapter-2-key.md` | Chapter 2: Key | 9 | 25,000 | `18c0b4a7e225...` |
| `02-chapter-3-balance.md` | Chapter 3: Balance | 16 | 29,702 | `38c687baa270...` |
| `03-chapter-4-puzzle.md` | Chapter 4: Puzzle | 24 | 27,649 | `72029ce26eb2...` |
| `04-chapter-5-gem.md` | Chapter 5: Gem | 32 | 28,609 | `c1440d1826f7...` |
| `05-chapter-6-rogue.md` | Chapter 6: Rogue | 40 | 14,403 | `42739083ef08...` |
| `06-chapter-7-sage.md` | Chapter 7: Sage | 49 | 23,847 | `75e11d1f3b99...` |
| `07-chapter-8-fates.md` | Chapter 8: Fates | 57 | 19,716 | `37f03efab2e4...` |
| `08-chapter-9-knight.md` | Chapter 9: Knight | 65 | 25,654 | `3660f131e99e...` |
| `09-chapter-10-sun.md` | Chapter 10: Sun | 73 | 24,543 | `84d6afff73ca...` |
| `10-chapter-11-moon.md` | Chapter 11: Moon | 81 | 24,105 | `c095dfe45465...` |
| `11-chapter-12-comet.md` | Chapter 12: Comet | 89 | 28,199 | `2ff77e251a79...` |
| `12-chapter-13-star.md` | Chapter 13: Star | 98 | 26,904 | `7700e9b5d67d...` |
| `13-chapter-14-jester.md` | Chapter 14: Jester | 106 | 23,040 | `5b58d832508c...` |
| `14-chapter-15-throne.md` | Chapter 15: Throne | 114 | 30,754 | `8bdefc2ab353...` |
| `15-chapter-16-ruin.md` | Chapter 16: Ruin | 123 | 25,221 | `ba066fd0126b...` |
| `16-chapter-17-donjon.md` | Chapter 17: Donjon | 132 | 44,940 | `3e70fad9eaef...` |
| `17-chapter-18-void.md` | Chapter 18: Void | 144 | 38,494 | `741fb589eeeb...` |
| `18-chapter-19-skull.md` | Chapter 19: Skull | 155 | 23,404 | `ab1365ff3e15...` |
| `19-chapter-20-flames.md` | Chapter 20: Flames | 165 | 23,370 | `6a6a9fb0668f...` |
| `20-chapter-21-talons.md` | Chapter 21: Talons | 175 | 2,728 | `66f7b39b2537...` |
| `21-chapter-22-euryale.md` | Chapter 22: Euryale | 185 | 20,710 | `f58884b6900a...` |
| `22-credits.md` | Credits | 2 | 3,257 | `7d75dbc28521...` |

---

## 2. Validation & Fidelity Results

### 2.1. Top-Level Book Sections
- **Sections Defined in book-bmt.json:** 23
- **Files Successfully Emitted:** 23
- **Incomplete or Dropped Sections:** 0 (All 23 sections converted)

### 2.2. Embedded Statblock Definitions Resolved
- **Total Statblocks Encountered:** 92
- **Total Successfully Resolved:** 92
- **Failed / Missing Statblocks:** 0

| Entity Kind | Resolved Count | Upstream Source Locus |
| :--- | :---: | :--- |
| `feat` | 1 | 5etools/data/feats.json |
| `item` | 62 | 5etools/data/items.json & magicvariants.json |
| `reward` | 26 | 5etools/data/rewards.json |
| `trap` | 3 | 5etools/data/trapshazards.json |

### 2.3. Section Breakdown of Embedded Definitions
- **Chapter 4: Puzzle:** 3 statblocks
  - `trap`: 3 (Balance and Ruin, Surface of the Sun, Test of the Empty Moon)
- **Chapter 5: Gem:** 41 statblocks
  - `item`: 41 (Cards, decks, wondrous items, and artifacts)
- **Chapter 8: Fates:** 26 statblocks
  - `reward`: 26 (Supernatural gifts, blessings, and consequences)
- **Chapter 14: Jester:** 21 statblocks
  - `item`: 21 (Games, festival items, and magic curiosities)
- **Chapter 17: Donjon:** 1 statblock
  - `feat`: 1 (Cartomancer feat)

### 2.4. Tag Parsing & Unresolved Tags
- **Unresolved Raw Tags:** 0

### 2.5. Asset References Preserved
- **Image References Preserved:** 95
- **Silent Asset Drops:** 0 (All image references preserved in standard Markdown format `![alt](href)` with captions)

---

## 3. Reproduction Command

```bash
python tooling/dnd5e/convert_bmt_to_markdown.py --verify-deterministic
```
