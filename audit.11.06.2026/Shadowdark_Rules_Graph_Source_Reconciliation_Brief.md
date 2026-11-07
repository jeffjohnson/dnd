# Shadowdark Rules Graph — Source Reconciliation and Generator Remediation Brief

**Prepared:** 2026-11-06  
**Audience:** Rules graph architect / extraction pipeline maintainer  
**Priority:** Shadowdark Core + Cursed Scroll 1–3 first; changes must generalize to later D&D editions and other RPG systems.  
**Purpose:** Reconcile the revised Shadowdark graph to its source materials, correct remaining defects, and make the generator catch the same classes of errors automatically on future packet processing.

> **Important scope statement:** This brief reports **confirmed structural and targeted spell-inventory findings**, plus explicitly identified risks requiring further source review. It is **not** a completed source-by-source verification of every graph edge, item, class feature, monster, and table. The architect should not mark the corpus validated on the basis of these findings alone.

## 1. Input baseline

### Updated graph under review

- `graph(1).json`
- `nodes_master(1).csv`
- `edges_master(1).csv`

### Earlier graph / supporting analyses

- `graph.json`, `nodes_master.csv`, `edges_master.csv`
- `classification_gaps.csv`
- `shadowdark_graph_independent_audit.md`
- `shadowdark_graph_generation_remediation_spec.md`
- `rules_graph_defect_register.csv`
- `rules_graph_regression_cases.json`
- Claude / Argon combined and separate analysis documents

### Source rulebooks

The source comparisons used accessible Markdown copies of:

| Source | File used | Key sections |
|---|---|---|
| Shadowdark Core | `shadowdark.md` | Priest Spell List (around text line 1360); Wizard Spell List (around 1407); spell descriptions (around 1484 onward) |
| Cursed Scroll 1 | `cs1.md` | Witch Spell List (around line 510); individual spell descriptions (around line 571 onward) |
| Cursed Scroll 2 | `cs2.md` | Class abilities, optional mechanics, items and encounter content — **not yet exhaustively reconciled** |
| Cursed Scroll 3 | `cs3.md` | Seer Spell List (around line 563); individual spell descriptions (around line 600 onward) |

**Reproducibility:** Confirm these Markdown copies are the intended canonical source versions before applying changes. They were retrieved from the project-associated file library; a different local revision may contain corrections. Hashes of the specific Markdown copies used for this brief (SHA-256):

```text
shadowdark.md  b8595008c98498387c777a845eb543109ccacc3a32d08db05b6088dddd6f365c
cs1.md        b37f62daca2ed7f2c0920c90f59bdfc959197886a24fec1e6d2e70e6ab2e1c03
cs2.md        d032918d203f0eaa957c094520fece33be447b93a1dcd0bc78a24eedb3b2f851
cs3.md        d6b50a93684f24660f639ea4b1c12ab2091375ba6de9c625620f88866be34161
```

## 2. Executive assessment

**What succeeded:** The update preserves the existing semantic graph and adds substantial missing coverage. The updated exports contain **737 nodes** and **1,801 edges**, compared with **732 nodes** and **1,498 edges** before. The update adds `item_weapon` and four formerly absent core spells (`spell_alarm`, `spell_bless`, `spell_fixed_object`, `spell_fabricate`), and replaces the incorrect `spell_control_weather` identity with `spell_control_water`. The known Sending / Shapechange / Shield of Faith classification errors are fixed in the revised edges. The previous raw-ID labeling problems and weapon-category gaps were also addressed.

**What is still inadequate:** An entry may exist and have a class and tier while lacking the mechanics needed for graph navigation. Spell-list memberships can be omitted or spuriously added. An OCR/Markdown entry may disagree with the spell list. A graph edge can cite a plausible page while still making an unsupported assertion. In short, the generator requires **independent completeness, attribution, and bidirectional correctness checks**, not simply validation that the resulting graph is well formed.

**Architectural decision:** Retain a graph-first retrieval design, with exact/keyword/vector fallback and authoritative source-passage retrieval. Do **not** treat the graph as a full rules adjudicator or an exhaustive passage corpus until source-evidence validation is complete.

## 3. Confirmed outstanding defects in the revised graph

### P0 — Invalid Priest classification on two core Wizard spells

The Shadowdark core **Wizard Spell List** and their individual spell descriptions identify both spells as Wizard-only in the supplied source. However, the updated graph has *additional* Priest classifications:

| Node | Defective graph edge | Expected | Edge CSV line (including header) |
|---|---|---|---:|
| `spell_hold_person` | `CLASSIFIED_AS -> class_priest` | Wizard, Tier 2; **remove Priest** | 1276 |
| `spell_dispel_magic` | `CLASSIFIED_AS -> class_priest` | Wizard, Tier 3; **remove Priest** | 1213 |

Retain their existing `CLASSIFIED_AS -> class_wizard` and tier edges. These are **false-positive class memberships**, a defect that a “missing classification” audit cannot detect.

**Acceptance:** Compare the graph's class memberships to a normalized set generated independently from source spell-list entries. Flag unexpected edges as well as missing ones. Do not automatically remove classes where another source book or house rule explicitly grants the spell; represent that grant separately with provenance and scope.

### P0 — Ten Witch spell memberships missing

The **Cursed Scroll 1 Witch Spell List** contains **46 entries**. Ten entries exist as spell nodes but lack a `CLASSIFIED_AS -> class_witch` relationship:

| Spell node | CS1 Witch tier |
|---|---:|
| `spell_charm_person` | 1 |
| `spell_alter_self` | 2 |
| `spell_augury` | 2 |
| `spell_invisibility` | 2 |
| `spell_speak_with_dead` | 3 |
| `spell_dimension_door` | 4 |
| `spell_divination` | 4 |
| `spell_polymorph` | 4 |
| `spell_scrying` | 5 |
| `spell_shapechange` | 5 |

These are **shared spells** already modeled for another class. The generator appears to have processed some individual spell entries but failed to attach every applicable **class-list membership** when the name already existed. This is an inference about root cause; confirm from extraction packets and code.

**Required action:** Add the missing Witch membership edges with **CS1 list/page provenance**, retaining other class memberships. Reconcile both spell lists and individual spell descriptions. Do not infer that an existing node is fully processed merely because its ID already exists.

**Acceptance:** For each spell-list tuple `(source, class, tier, spell)`, check that the canonical spell node exists and carries a provenance-supported membership. The check must support multiple class memberships per spell and source/edition-specific spell tiers.

### P0 — Spell nodes with no extracted mechanical relationships

The updated graph includes class/tier classifications but **no non-`CLASSIFIED_AS` edges** for:

- **38** spells appearing on the CS1 Witch Spell List.
- **All 20** spells appearing on the CS3 Seer Spell List.
- The **four newly added** core spell nodes: `spell_alarm`, `spell_bless`, `spell_fixed_object`, `spell_fabricate`.

These categories may overlap by neither node nor count in the current data, but don't interpret the total as a definitive count of *missing facts*. Some spells may have few or no modeled mechanical cross-references under the chosen ontology. It is nonetheless a **mandatory extraction-review trigger**: the nodes currently contribute only taxonomy, not mechanical graph traversal.

Examples:

```text
spell_world_tree -> class_seer
spell_world_tree -> rule_spell_tier_5
# No non-classification relation exists.

spell_alarm -> class_wizard
spell_alarm -> rule_spell_tier_1
# No non-classification relation exists.
```

**Required action:** Re-examine the *individual spell descriptions*, extract applicable effects, requirements, constraints, focus/duration, range, targeting, checks, damage, conditions, and references **when actually supported by the text**. Do not manufacture a mechanical edge just to satisfy a degree threshold. Preserve a distinct outcome of `reviewed_no_modeled_relationships` for genuinely self-contained spells.

**Acceptance:** Every spell receives an explicit processing status and an evidence-backed result (`extracted`, `reviewed_self_contained`, `needs_review`, etc.). `classification-only` is a warning until reviewed, not automatically an error.

### P0 — Source Markdown has mutually inconsistent spell classifications

The supplied Shadowdark core `shadowdark.md` is **internally inconsistent**:

| Spell | Core spell list | Individual description currently says | Source area |
|---|---|---|---|
| Sending | Wizard, Tier 3 | `Tier 5, wizard` | Around text line 2161 |
| Shapechange | Wizard, Tier 5 | `Tier 1, priest` | Around text line 2169 |
| Shield of Faith | Priest, Tier 1 | `Tier 3, wizard` | Around text line 2179 |

The **revised graph has the correct list-derived classifications** for these three, but that does not make the source discrepancy disappear. It is likely related to multi-column layout association, yet this root cause is **not proven** from the Markdown alone. Verify questionable passages against the original page image or authoritative source edition when available.

**Required action:** Source ingestion must compare canonical inventories (spell list, class tables, indexes) with entity-detail headers and flag contradictions. Store uncertainty explicitly, retain both evidence locations, and route conflicts for review. **Never silently trust whichever text the extraction process encountered last.**

### P1 — Source identity and alias normalization must be explicit

The supplied Shadowdark core list spells **Judgment** while the graph uses `spell_judgement` / label “Judgement.” That is not proof that the spell is absent. Likewise, names with apostrophes can have intentionally compact IDs, e.g. `spell_cats_eye`, `spell_freyas_omen`, `spell_lokis_trickery`, `spell_odins_wisdom`, and `spell_thors_thunder`.

**Required action:** Use a canonical ID, a display label, a source-preserved name, and a searchable alias set. A mismatch between a naïvely slugified name and an ID must generate an **entity-resolution review**, not an automatically created duplicate node.

**Acceptance:** Canonical inventory reconciliation should report **85 distinct Shadowdark core spells**, **46 CS1 Witch list entries**, and **20 CS3 Seer list entries** in these source snapshots, with the spell-list aliases normalized and no false “missing” results caused solely by spelling/punctuation.

### P1 — Exceptions currently reference nodes, not exact rules/claims

The updated `general_rule_id` field is no longer universally empty: **five** `OVERRIDES` edges now populate it with values such as `rule_dying` and `rule_death`. However, these are **node IDs**, not stable claim/edge IDs. The edge export still has no distinct `edge_id` column.

**Required action:** Define stable claim IDs for individual assertions, and use separate fields for `overridden_node_id` and `overridden_claim_id` (or equivalent). Preserve multiple conditions/aspects between the same pair of nodes. Keep compatibility with existing `general_rule_id` only through a clearly documented migration.

**Acceptance:** Two different claims on the same target node can be independently superseded without ambiguity.

### P1 — Graph export compatibility regression

`graph.json` originally included a top-level `meta` object with schema version and counts. The revision `graph(1).json` has only `nodes` and `edges`.

**Required action:** Restore versioned export metadata or make removal an intentional, documented breaking schema change. Validate CSV ↔ JSON parity and version compatibility in CI. The previous `roles` column was also removed from the node CSV (previously entirely blank); decide whether it belongs in the stable schema before restoring it.

## 4. Previously identified defects to keep under regression tests

The latest graph **appears to address** the following previously documented issues; do not drop the tests:

- Four absent Shadowdark core spell nodes added: Alarm, Bless, Fixed Object, Fabricate.
- `spell_control_weather` removed and replaced with `spell_control_water`; validate that all incoming/outgoing references were migrated.
- Page-70 Sending, Shapechange, and Shield of Faith classifications corrected in graph edges.
- All 26 `weapon_*` nodes now have category classification relationships.
- Item taxonomy and `item_weapon` category node added.
- The 23 earlier raw-ID labels repaired.
- Connected-component count improved from seven to two.

**Important:** Correct classifications and graph connectivity do **not** prove that an entity's descriptive mechanical content was extracted.

## 5. Required changes to the graph generation engine

### Stage A — Build a source inventory independently of relationship extraction

Before processing a packet for edges, enumerate all authoritative entries the material explicitly lists:

- Spells and per-class spell lists, tiers, spells available from other books.
- Classes, class features, ancestries, conditions, equipment categories, weapons, armor, items.
- Monsters and stat blocks, tables and table rows, variant/optional rules, named subsystems.

Save source location and stable source-entry ID for each inventory record. Build this independently from the edge extractor to avoid two components sharing the same blind spot.

### Stage B — Extract entities, claims and evidence from source spans

Each extracted relationship should include:

```yaml
claim_id: stable-id
ruleset: shadowdark
edition: core-or-supplement-revision
source_book: SD | CS1 | CS2 | CS3
source_entry_id: stable-entry-id
source_passage_id: stable-passage-id
page: source-page
section: source-section
source_span: precise-line-or-offset
source_hash: hash-of-normalized-evidence
source_id: node-id
edge_type: CLASSIFIED_AS | MODIFIES | ...
target_id: node-id
aspect: optional-specific-aspect
condition: optional-scope-condition
status: core | optional
extraction_method: parsed | inferred | human-reviewed
confidence_or_review_status: explicit-status
```

This schema is illustrative; map it to existing storage while preserving the semantics. In particular, **a source pointer and an inference must not masquerade as an explicit rule**.

### Stage C — Reconcile in both directions

For every source-inventory tuple, verify the required node/relationship exists; for every graph node/classification, verify supporting source evidence exists. Implement at least these validations:

1. **Missing entity:** source lists a named rule or spell but graph lacks a resolvable node.
2. **Missing relationship:** source lists a class/tier/permission, but graph lacks it.
3. **Unsupported extra relationship:** graph claims a class/tier not supported by its scoped source.
4. **Header/list conflict:** source's entry detail disagrees with an index, spell list, or table.
5. **Incomplete extraction:** source's rule-bearing passage has only taxonomy links without review.
6. **Wrong source attribution:** edge's cited page/section does not support its asserted claim.
7. **Alias/identity collision:** same rule split into multiple nodes due to spelling/punctuation, or different rules incorrectly merged.
8. **Optional/edition collision:** content from a supplement, house rule, or other edition is used without appropriate scope.

A missing edge is not always a mistake. Require the reviewer or extraction engine to mark the reason a claim was intentionally not modeled.

### Stage D — Source-evidence verification

For each graph edge, reopen its source span and ask two separate questions:

- Does the source **actually state or imply** the claimed relation, polarity, condition and scope?
- Is any crucial exception, qualifier, timing rule or conditional requirement omitted?

Prioritize high-impact classes: `OVERRIDES`, `GATES`, `EXCLUDES`, `CONSTRAINS`, class access, spell lists and permission restrictions. Verify sampled lower-risk edges and increase coverage for packets whose error rate is high. Do not declare 100% evidence verification until every in-scope claim has been checked.

### Stage E — Produce and validate graph exports

- IDs must be deterministic and reprocessing idempotent.
- No dangling references or accidental duplicated claims.
- Preserve valid multigraph edges with distinct conditions/aspects or sources.
- Preserve graph metadata and export schema version.
- Enforce node-kind taxonomy and field validation.
- Report unverified source spans and unresolved contradictions as **blocking defects** where they change gameplay.

## 6. Reconciliation procedure for already-processed Shadowdark packets

**Do not discard previously processed packets or blindly regenerate the entire graph without a diff.** Use a controlled migration:

1. **Snapshot** the revised graph, all source Markdown versions, packet outputs and generator version. Record hashes.
2. **Inventory** SD/CS1/CS2/CS3 entries independently from the original lists and section headings.
3. **Map each packet** to its source book, pages, section IDs and any graph claims it produced. Where historical lineage is missing, record that explicitly.
4. **Run defect detectors** against current output: missing/extra classifications, alias collisions, classification-only spell entries, unsupported edge evidence and source contradictions.
5. **Re-extract only affected source spans first:** SD spell section/list (including page 70), CS1 Witch spell list + each affected shared spell, CS3 Seer descriptions, and the four newly added core spell descriptions.
6. **Reconcile proposed claims** by stable identity and provenance. Present add/update/remove operations, preserving legitimate existing claims; do not silently remove claims used elsewhere.
7. **Review conflicts** against the authoritative book/page image or corrected source where source Markdown is internally contradictory.
8. **Merge transactionally** with an audit log and explicit alias/ID migrations.
9. **Re-run the entire source inventory and regression suite**, then publish a revised graph plus a remaining-defects report.
10. **Backfill prior packets** from other processed books with the same checks, prioritized by exposure and known failure patterns.

A packet replay must distinguish **a newly discovered rule** from **an already-known rule gaining another source/class/edition membership**. The latter caused the Witch gap pattern.

## 7. Required regression scenarios / acceptance gates

| ID | Test | Expected result |
|---|---|---|
| SD-01 | Shadowdark core spell lists vs graph | 85 distinct spells resolved; no missing or extra core class/tier memberships |
| SD-02 | Hold Person / Dispel Magic | Wizard-only in the core scope; no unsupported Priest edge |
| CS1-01 | CS1 Witch spell list | All 46 entries resolve and have Witch memberships at listed tiers |
| CS1-02 | Shared Charm Person / Alter Self / Invisibility / Shapechange | Same canonical spell may have multiple supported class-list memberships, with per-source provenance |
| CS3-01 | CS3 Seer spell list | All 20 entries resolve with Seer + tier; each description has a recorded mechanics-extraction review status |
| MECH-01 | 38 CS1 classification-only spells | Re-reviewed against individual description; valid derived edges added or explicit `reviewed_self_contained` outcome |
| MECH-02 | Four new core spells | Source passages processed beyond bare class/tier identities or documented why not |
| SRC-01 | Sending / Shapechange / Shield of Faith | Contradictory source Markdown headers detected; final classification justified by verified source evidence |
| ID-01 | Judgment/Judgement and apostrophe names | Resolve to one intended node, with alias; no false “missing” or duplicate nodes |
| EVID-01 | Any edge with `(book,page,section)` | Exact supporting text/span can be retrieved and independently validated |
| CLAIM-01 | Two claims sharing source/target but differing conditions | Independently addressable by `claim_id`; no accidental merge |
| OPT-01 | Optional mode inactive | Optional override does not affect default core ruling merely because a book is enabled |
| EXP-01 | JSON/CSV exports | Counts, identity, schema version and all exported claims remain consistent |
| REPLAY-01 | Reprocess same packet twice | Identical canonical IDs and claims, zero duplicate records, stable diff |
| DND-01 | 5e 2014 and 2024 imports | Edition-specific rules never silently coalesce; inventory checks use actual imported books/SRD scope |
| DND-02 | Weapon proficiency / use permissions | Generator distinguishes permission to wield from proficiency benefits and class restrictions |

## 8. Ruleset-agnostic requirements (before importing D&D 5e)

Make the validation rules configurable by ruleset **without weakening the universal invariants**:

- Keep `ruleset`, `edition`, `book`, `revision/errata`, `source`, and `active optional rule` distinct.
- Preserve the difference between **is-a taxonomy**, **permission**, **proficiency**, **prerequisite**, **mechanical effect**, **exception**, **reference**, and **override**.
- Treat spell level/tier and eligible class list as a relation with source scope; do not assume a single globally applicable class or tier.
- Store stable source-passage IDs and enough source evidence to verify each derived claim independently.
- Enforce inventory coverage for classes, spells, equipment, conditions, tables, monsters and features according to the source actually imported. Do not equate an SRD inventory with the contents of all published books.
- Ensure explicit exceptions and more-specific source authority do not silently overwrite baseline rules; resolve precedence in a dedicated policy layer.
- Use retrieval fallback when no suitable anchor node is found; **absence from graph is not evidence that no rule exists**.

## 9. Deliverables requested from the architect AI

Produce the following **before declaring Shadowdark reconciled**:

1. **Generator root-cause analysis** for each confirmed defect, citing the packet/stage that introduced it (or noting unavailability).
2. **Patch proposal** with exact node and edge add/update/remove operations, each tied to source evidence and rule scope.
3. **Reprocessing plan** identifying affected packets and a full-corpus verification pass; no unreviewed bulk changes.
4. **Machine-readable defect register** with severity, source span, current claim, expected claim, confidence, resolution and regression-test ID.
5. **Validation report** containing inventory coverage, false-positive relations, incomplete mechanics reviews, source contradictions, and unresolved findings, separated by SD, CS1, CS2 and CS3.
6. **Reusable test suite** running on every future ruleset import, including explicit 2014/2024 5e isolation and proficiency-vs-permission cases.
7. **Export-contract migration** describing graph `meta`, stable claim IDs, compatibility and idempotence.

### Definition of done

Shadowdark is ready for retrieval production when (a) every in-scope inventory entry resolves to an appropriate node, (b) all class/tier memberships agree with source evidence or have an explicit documented conflict, (c) gameplay-relevant graph claims have validated source spans, (d) taxonomy-only entries are reviewed, (e) packet replay is stable, and (f) outstanding exceptions are published rather than hidden.

**Do not claim full semantic validation from node/edge counts alone.** The remaining high-value work is source-backed claim verification across class features, equipment, spells, monsters, tables and optional rules—not simply adding more edges.
