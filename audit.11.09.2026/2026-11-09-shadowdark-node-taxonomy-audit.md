# Shadowdark Rules Graph — Semantic Node Taxonomy Audit

**Date:** 2026-11-09  
**Audience:** Rules Graph Architect AI  
**Priority:** P1 — resolve before implementing graph-first retrieval or importing D&D 5e  
**Scope:** Shadowdark graph generation, migration of existing packets, and reusable ruleset-independent validation  
**Inputs examined:** latest `graph.json`, `nodes_master.csv`, `edges_master.csv`; prior source-reconciliation findings

## Executive summary

The graph currently uses `kind: abil` for two mechanically different concepts:

1. **Primary character attributes:** Strength, Dexterity, Constitution, Intelligence, Wisdom, Charisma.
2. **Special abilities and features:** Backstab, Weapon Mastery, Keen Senses, and other class/ancestry/special features.

It also places `abil_stat_modifier` in the same category. This conflation is not a graph-integrity error, but it **is a semantic schema error**: GraphRAG traversal rules, type-specific validation, and future ruleset imports cannot safely treat a fundamental character attribute as interchangeable with a granted feature.

**Recommendation:** Introduce semantic kinds/roles, reclassify the existing nodes without changing their IDs or relationships, update generation instructions and validation gates, and replay taxonomy reconciliation on already-processed packets. Do not indiscriminately relabel all other `abil` nodes as class features: verify their origin and function against source text.

## Current-state evidence

Latest graph export metadata:

| Property | Current value |
|---|---:|
| Schema version | `1.2` |
| Nodes | 737 |
| Edges | 1,809 |
| Nodes with `kind: abil` | 38 |
| Primary attribute nodes within `abil` | 6 |
| Stat modifier node within `abil` | 1 |
| Remaining nodes requiring semantic review | 31 |

The six primary attribute IDs are:

| Existing ID | Label | Proposed kind | Proposed subtype |
|---|---|---|---|
| `abil_strength` | Strength | `stat` | `primary_attribute` |
| `abil_dexterity` | Dexterity | `stat` | `primary_attribute` |
| `abil_constitution` | Constitution | `stat` | `primary_attribute` |
| `abil_intelligence` | Intelligence | `stat` | `primary_attribute` |
| `abil_wisdom` | Wisdom | `stat` | `primary_attribute` |
| `abil_charisma` | Charisma | `stat` | `primary_attribute` |

`abil_stat_modifier` should be **reviewed** as either `derived_stat` / `modifier` (if it represents the derived quantity) or `rule` / `stat_modifier_calculation` (if it represents the calculation rule). The label alone cannot settle that distinction.

Examples of other nodes that need explicit semantic roles:

- `abil_backstab` → candidate `feature`, subtype `class_feature`.
- `abil_weapon_mastery` → candidate `feature`, subtype `class_feature`.
- `abil_keen_senses` → candidate `feature`, subtype `ancestry_trait`.

These examples illustrate the target ontology; the engine must determine the actual role from its cited source and granting relationship, not from the `abil_` prefix.

## Why this matters

**1. Retrieval quality.** A graph walker that suppresses unrelated class/ancestry abilities to avoid hub explosion must **not** suppress STR or DEX. Primary attributes are universal mechanic entry points and may affect numerous checks and combat rules.

**2. Correct validation.** A class feature may require a granting class, level, ancestry, or other prerequisite; an ability score does not. Treating both identically produces incorrect missing-edge diagnostics and hides real problems.

**3. Cross-ruleset portability.** D&D 5e separates ability scores, ability modifiers, skill proficiencies, saving throws, class features, ancestry traits, and combat-resolution rules. A single `abil` bucket loses critical distinctions before retrieval or adjudication begins.

**4. Data modeling.** `kind` should represent **what an entity is**. Relationship edges describe **what it affects or how it is acquired**. An entity is not an “ability” merely because it modifies a roll.

## Recommended schema

Use stable top-level semantics with a finer role/subtype:

| Kind | Intended meaning | Example |
|---|---|---|
| `stat` | Fundamental character attribute | Strength, Wisdom |
| `derived_stat` | Calculated character quantity, when modeled as a value | Ability modifier, movement speed *if modeled as a derived value* |
| `feature` | Special ability, benefit, talent, or trait | Backstab, Keen Senses |
| `rule` | General rule or calculation/procedure | Ability checks, stat-modifier calculation |
| `cbt` / existing mechanic types | Existing resolution/combat concepts | Attack Roll, Damage Roll |

Suggested `feature.subtype` values, as supported by source evidence: `class_feature`, `ancestry_trait`, `talent`, `special_ability`, `other_feature`. Avoid inventing narrower subtypes where the source does not establish them.

Suggested additional properties:

- `semantic_role` or `subtype` (required where the kind is broad).
- `source_book`, `source_page`, `source_section` or stable passage references, when available.
- `classification_evidence` / `classification_confidence` for adjudication of ambiguous entities.
- Optionally `legacy_kind` during migration, if downstream clients need compatibility.

### Example of desired output

```json
[
  {
    "id": "abil_strength",
    "label": "Strength",
    "kind": "stat",
    "subtype": "primary_attribute"
  },
  {
    "id": "abil_backstab",
    "label": "Backstab",
    "kind": "feature",
    "subtype": "class_feature"
  }
]
```

**Compatibility requirement:** Keep the IDs `abil_strength`, etc. in the first migration. Their prefix is a historical artifact, not a reliable indicator of semantic type. Do not rename nodes until consumers and edge references can be migrated with an explicit mapping.

## Required work for the Architect AI

### A. Update the graph-generation engine

1. Define a ruleset-independent taxonomy contract for `stat`, `derived_stat`, `feature`, and `rule`; keep existing specialized kinds where appropriate.
2. Classify by function and source evidence **during extraction**, before building final graph edges.
3. Extract/classify **granting relationships** separately from node kind (e.g., class grants feature). Do not infer that every feature is granted by a class.
4. Emit a review finding when a candidate could denote either a numeric value, a derived value, or a calculation rule.
5. Provide a per-ruleset profile/mapping layer, not a hard-coded six-stat assumption for every RPG.
6. Update graph traversal policies so universal stats remain searchable when context-gating character-specific features.
7. Validate the taxonomy before final CSV/JSON export; regenerate graph-level degree data after changes.

### B. Reconcile already-processed Shadowdark packets

1. Produce a complete inventory of the 38 `abil` nodes with their cited source and proposed type/subtype.
2. Reclassify the six primary attribute nodes as `stat` / `primary_attribute`.
3. Inspect `abil_stat_modifier` and choose a value or procedural representation, based on its actual source semantics.
4. Review the remaining 31 individually as features/traits/talents or another documented kind.
5. Preserve all node IDs, edge endpoints, conditions, evidence fields, and source references unless source verification establishes another defect.
6. Rebuild `nodes_master.csv`, `edges_master.csv` (only if edge data genuinely changes), and `graph.json` from a single canonical dataset.
7. Report a before/after diff that separates **reclassification-only changes** from **semantic or relational corrections**.
8. Run reconciliation against original packet inventories so older extracted packets do not reintroduce `kind: abil` indiscriminately on subsequent merges.

### C. Add reusable regression tests

| Test ID | Test | Passing condition |
|---|---|---|
| `TAX-01` | Six Shadowdark primary stats | Each exists and has `kind: stat`, `subtype: primary_attribute` |
| `TAX-02` | Distinguish Backstab from STR | `abil_backstab` is **not** a primary stat; `abil_strength` is **not** a class feature |
| `TAX-03` | Stat modifier semantics | `abil_stat_modifier` classified according to cited source; ambiguity flagged rather than guessed |
| `TAX-04` | Preservation of node identity | No changed IDs or dangling edges during reclassification |
| `TAX-05` | Traversal visibility | Queries about Strength/Dexterity still retrieve their relevant mechanics with specific-feature gating active |
| `TAX-06` | Packet reprocessing | Reprocessing any pre-migration packet does not revert semantic kinds or duplicate edges |
| `TAX-07` | Cross-ruleset profile | A 5e import distinguishes ability score, ability modifier, skill, saving throw, proficiency, and class feature according to source semantics |
| `TAX-08` | Structural export parity | Canonical node/edge records agree across both CSV exports and JSON; derived degrees are correct |
| `TAX-09` | Source-backed classification | Every reclassification is traceable to an authoritative passage or explicitly marked for review |

## Scope boundaries / outstanding work

This audit concerns **semantic node taxonomy**, not a fresh complete source audit. Previous work already confirmed that the latest graph update added ten Witch-class spell relationships, removed two unsupported Priest-class relationships, and restored graph metadata. Those repairs should remain intact.

Other known source-reconciliation work—especially the mechanical-effect coverage of Witch and Seer spells, and the validation of graph edges against source passages—remains outside this taxonomy change and should continue in the broader audit backlog. A successful taxonomy migration does **not** prove total graph completeness.

## Acceptance / definition of done

- The six primary attribute nodes and the stat-modifier concept are no longer conflated with granted special abilities.
- All 31 other former-`abil` nodes have reviewed, source-supported semantic classifications (or an explicit unresolved review record).
- No orphaned edges, renamed legacy IDs, or duplicate classification relationships are introduced.
- The engine uses the new ontology when processing fresh packets **and** when replaying old packets.
- A 5e regression fixture verifies the distinction between ability scores, ability checks, saving throws, skills/proficiencies, and features.
- The architect provides a machine-readable migration diff and regression-test results.

**Priority recommendation:** Complete this P1 ontology migration before building retrieval heuristics around node kinds or importing 5e. Implement it as a generator-level behavior change, not a one-off rewrite of Shadowdark JSON.
