# Rules Graph Generation: Remediation and Forward-Compatible Specification

**Priority:** Shadowdark first; requirements apply to every subsequently ingested RPG ruleset (including D&D 5e 2014 and 2024).  
**Date:** November 4, 2026  
**Inputs audited:** `graph.json`, `nodes_master.csv`, `edges_master.csv`, `classification_gaps.csv`, Claude's earlier review and combined analysis, Argon's review, and the previous independent audit.  
**Intended audience:** Graph-generation architect, extraction agent, QA/validation agent, retrieval-engine developer.

## Executive decision

**Do not merely append missing `CLASSIFIED_AS` edges.** Correct the *generation pipeline*: (1) source inventory, (2) packet extraction, (3) classification/normalization, (4) cross-packet relationship reconciliation, (5) source-grounded verification, (6) graph publishing, and (7) retrieval testing. Apply these upgraded phases retroactively to already processed packets. Use Shadowdark as the first gold-standard regression corpus, then reuse the same architecture for every ruleset.

The current graph is valuable as a **relationship/navigation index**, not yet a closed-world rules authority. It should direct retrieval to *authoritative source passages*; neither a graph edge nor a model-generated interpretation should substitute for the actual rule.

### Verified starting point (from the uploaded exports)

| Metric | Actual |
|---|---:|
| Nodes / edges | 732 / 1,498 |
| Node kinds / edge types | 17 / 14 |
| Unique `(book,page,section)` location tuples | 646 |
| Missing outgoing classification entries in Claude's file | 240: 122 items, 26 weapons, 31 spells missing tier *and* class, 61 spells missing class only |
| Nodes whose display label equals raw ID | 23 |
| Spell-type grouping nodes incorrectly counted as individual spells for audit purposes | 4 |
| Edge rows with `general_rule_id` | 0 |
| Edge rows with `review_flag` | 0 |
| Non-empty node `roles` values | 0 |
| Distinct `pass` values | 1 (every edge has `pass=1`) |
| Edge rows with `condition` | 515 |
| Edge rows with exact immutable passage IDs | 0 |
| Undirected connected components | 7; main component has 718 nodes |

**Interpretation of the gap count:** The 240 rows correctly describe *existing nodes missing specific outgoing links*. They do **not** tell us how many sourcebook rules were never extracted, and do **not** mean that every flagged generic/category node should become a classified leaf.

## A. Where the existing generation process succeeded

1. **Semantic, typed relationships:** `GATES`, `CONSTRAINS`, `MODIFIES`, `FEEDS_INTO`, `RESOLVED_BY`, `OVERRIDES`, etc. express more than a table of contents. Edges include `aspect`, frequently a `condition`, and polarity.
2. **Source-location provenance:** All 1,498 edges include book, page and section locators. These are useful candidates for joining to source passages, though they are not exact text spans.
3. **Broad mechanical coverage:** Combat, spellcasting, abilities, classes, items, tables, optional variants, and Cursed Scroll supplements are represented.
4. **Preserved directional semantics:** Incoming constraints and outgoing effects can be used for question-specific traversal. Repeated triples with different conditions/aspects should be retained.
5. **Structurally coherent export:** Node IDs are unique; edge endpoints exist; JSON/CSV record sets are aligned. This makes repair and regression comparison feasible.

**Do not throw this graph away or rebuild every relationship from scratch.** Keep valid edges; source-verify and repair the deficient parts.

## B. Where generation or validation was lacking

| Failure class | Evidence in current export | Root cause status | Engine-level correction |
|---|---|---|---|
| **Missing entities** | Four confirmed core Shadowdark spell nodes absent; `Control Water` stored as `Control Weather` | Exact extraction cause unknown | Build independent source inventory before extraction; reconcile expected entities to emitted nodes |
| **Partial classification** | 92 actual spell entries lack a casting-class link; 31 lack a tier; item/weapon taxonomy sparse | Exact extraction cause unknown; A–H region suggests a localized pass omission | Separate required classification pass, validated against spell lists and equipment tables |
| **Wrong attribution** | Three spell classification errors on SD p.70 | Pattern is consistent with a column/entry association error; verify actual extractor | Attach every attribute to a source-entry ID and source span, especially in multi-column PDFs |
| **Type/category conflation** | `item_armor`, `item_wand`, named items, and other generic types all use `kind=item`; spell-list hubs use `kind=spell` | Schema design | Add an `entity_role`/subtype or explicit `is_category`, `is_list`, `is_entry`, `is_reference_only` field |
| **Missing taxonomy and permission edges** | No shared `item_weapon` hub; no class-to-weapon restriction links; named armor not linked to armor category | Cross-packet reconciliation gap | Run global class × equipment taxonomy/permission validation after packets are merged |
| **Split spell-list architecture** | Individual spell → class, class → spell-list hub; list mechanics reside on hub | Modeling inconsistency | Add direct membership in class spell list; distinguish eligibility from general mechanics |
| **Unresolvable specifics** | `Wizard CONSTRAINS Armor` indicates a rule exists but doesn't encode allowed armor | Incomplete claim semantics | Store exact rule passage and optionally machine-readable predicates; never infer permission from mere graph connectivity |
| **Applicability conflation** | Cursed Scroll edges all `optional`, as are 39 SD edges, including rules that should be opt-in | Schema limitation | Separate book availability, variant activation, character/feature possession, and conditional applicability |
| **Weak provenance/lineage** | No `packet_id`, `passage_id`, extractor/version, source span, or review record; all `pass=1` | Output schema gap | Versioned extraction and immutable provenance IDs so processed packets can be replayed safely |
| **No independent coverage gate** | Classification-gap script never flags a node that doesn't exist | Validation design | Reconcile graph with source inventories and cross-references, not only with itself |

**Important:** These failures are demonstrated by the outputs, **not** proof of exactly which internal prompt, code path, OCR step or packet-processing phase caused them. The existing generator implementation and packet artifacts were not supplied.

## C. Shadowdark: mandatory corrections (P0/P1)

### P0 — Fix the actual core-spell coverage errors

* Create source-verified entries for four core spells absent from graph: `spell_alarm` (Wizard, Tier 1), `spell_bless` (Priest, Tier 2), `spell_fixed_object` (Wizard, Tier 2), `spell_fabricate` (Wizard, Tier 3).
* Repair the **identity**, not just classification, of `spell_control_weather`: source citations SD p.57 and p.319 refer to **Control Water**, not Control Weather. Migrate to `spell_control_water` (Priest and Wizard, Tier 4) with a redirect/alias for old ID references. Do not retain a duplicate false `Control Weather` spell for that source/version.
* Re-audit all core spell entries from the actual book's lists—not only the four/five cases above; do not assume an external list covers all sourcebook printings.
* On SD p.70, fix these *source-validated* classifications: `spell_sending` = Wizard/Tier 3, `spell_shapechange` = Wizard/Tier 5, `spell_shield_of_faith` = Priest/Tier 1. Re-extract/review the entire **page 70** entry layout, including Scrying, rather than swapping two rows. Preserve correct nonclassification edges unless evidence contradicts them.
* Reprocess SD spell material around pp.54–62 to recover absent tier/class links. This *page-range correlation* suggests a systematic extraction failure, not confirmed code root cause.

### P1 — Complete, but don't blindly mass-assign, the classification layer

* `classification_gaps.csv` is a **work queue**, not a patch file. Reconcile the 31 + 61 flagged spell nodes against sourcebook lists. Treat **spell-list hubs** as lists and **mention-only** entries as unresolved references until authoritative definitions are found.
* The 122 unclassified `item` nodes include known category hubs (`item_armor`, `item_gear`, `item_magic_item`) **and other generic concepts** (`item_wand`, `item_spell_scroll`, `item_coin`, etc.). Claude's proposed 119 automatic classifications are therefore **not** the number of true unclassified leaf items. First assign each node an `entity_role`; then classify named instances with source evidence. Named magic armor/weapons may have multiple applicable types.
* Add `item_weapon` (or equivalent generic `equipment:weapon` category) and classify the 26 weapon entries. Class-to-weapon relations must link to **actual permitted/proficient weapon sets**, not just to a broad `item_weapon` category.
* Model **armor use**, **weapon permission**, **weapon proficiency**, **spell availability**, and **item usability** as distinct predicates. They are *not synonymous across editions*. In 5e, lacking weapon proficiency does not itself prohibit wielding the weapon; it affects proficiency bonus.
* Add explicit membership links from individual spells to `spell_priest_spells`, `spell_wizard_spells`, `spell_witch_spells`, `spell_seer_spells` (or replace list hubs with a normalized SpellOffering relation). Support *multiple* class lists and possible different tier/level for a particular offering in future systems.
* Restore 23 raw-ID display labels from edge labels where consistent; add aliases and an identity-normalization policy. Never silently turn a guessed alias into a canonical entity.
* Review disconnected clusters individually; the tavern drinks should link to their actual source table if the source confirms it. Do not connect unrelated item–monster pairs merely to force one graph component.

### P1 — Source and rule applicability

* Add immutable `passage_id` and source span for every meaningful rule claim. `(book,page,section)` is a useful locator, **not a unique, exact passage ID**. Preserve a deterministic source-to-passage index; table entries retain headers and row context.
* Add stable `claim_id` / `edge_id` plus `source_passage_id` and `target_claim_id` (where one claim overrides another). `general_rule_id` is currently blank everywhere and cannot disambiguate multiple aspects/conditions without a target claim ID.
* Distinguish **document included**, **source available**, **optional variant enabled**, **class feature or item present**, and **predicate true in the encounter**. Never activate `rule_fatality_mode` simply because SD itself is enabled. Allow inactive rules to be *found* for informational queries without treating them as applicable to play.
* Normalize conditions where possible into explicit predicates, retaining the human-readable condition and its source. Any condition that cannot be formalized stays `requires_interpretation`, not implicitly true.

## C2. What to retain—and amend—from Claude's latest combined analysis

* **Retain:** cache a *small, measured* stable rules core if warranted; graph-guided retrieval of whole entries/sections; bidirectional traversal; edge-type ranking; source text alongside edge traces; packet-specific graph repair.
* **Correct:** “the graph can replace similarity search entirely” is not safe. Natural language, aliases, absent nodes, incorrectly named entries, and sourcebook gaps still require keyword/semantic fallbacks. Graph-only should be a benchmark candidate, not an assumption.
* **Correct:** 646 source-location tuples are not 646 proven exact text passages. Attach stable span IDs and validate joins.
* **Correct:** the list of 119 item “leaf” fixes still includes additional generic equipment concepts. Determine `entity_role` before assigning categories.
* **Correct:** page 70 has a **three-spell** error involving Sending, Shapechange, and Shield of Faith, not just the two highlighted in earlier exchanges.
* **Correct:** generic class-to-weapon edges do not encode actual permission; that distinction becomes even more critical in 5e where permission and proficiency differ.
* **Qualify:** automatic node-kind gating can hide an exception contributed by a feat, item, class feature or monster ability even if the question does not mention it. Retrieve *applicable* exceptions from active character/session state; for enumeration questions, descend category/list memberships deliberately. Do not blindly traverse all mechanics nodes either.
* **Qualify:** ordering passages by the count of surviving edges can overpromote hub-heavy passages. Rank using query intent, exact match, evidence quality, applicable exceptions, hop cost and passage relevance. Measure recall before enforcing a context/token cap.
* **Qualify:** caching 15K–30K tokens of core rules is a **hypothesis to benchmark**, not a universal design contract. Do not let a cached summary override an exact retrieved source rule.

## D. Required engine redesign: seven stages

### Stage 0 — Source registration and versioning

For every book: `ruleset_id`, `edition_id`, `book_id`, printing/errata revision, permitted rights/visibility scope, original file hash, extracted-text hash, and source locations. Shadowdark core and each Cursed Scroll should have distinct `book_id` and availability flags. D&D 5e 2014 and 2024 must have distinct editions even when names match.

### Stage 1 — **Pre-extraction source inventory** (new hard requirement)

Parse and record a `SourceEntityManifest`: all headings, spell-list entries, individual spell descriptions, class features, weapons/equipment entries, table identifiers and rows, monsters, conditions, variant rules and cross-references **actually present in the chosen source edition**. Attach source spans and distinguish `defined_entry` from `mentioned_reference`. Inventory extraction may itself be imperfect; unresolved ambiguities require review.

The manifest is the independent expected set. Extraction success must be computed against it; an absent graph node is otherwise undetectable.

### Stage 2 — Packet-local extraction

Process bounded logical packets (source pages/sections/entries) with **immutable packet IDs** and the exact passage spans included. Extract nodes, properties, and evidence-bearing relationships. Each value is tied to one source entry and span—not merely a page shared by two columns. For two-column layouts, record entry bounding regions/reading order or verified structured positions so page-70 attribute shifts fail validation. Preserve original passages untouched.

Recommended packet product:

```json
{
  "packet_id": "shadowdark-core:v1:p070:section-spells",
  "source_hash": "<hash>",
  "generator_version": "<semver>",
  "extraction_schema_version": "2",
  "expected_entry_ids": ["spell_scrying", "spell_sending", "spell_shapechange", "spell_shield_of_faith"],
  "emitted_entry_ids": ["..."],
  "claims": [
    {"claim_id":"<stable-id>", "subject_id":"spell_sending",
     "predicate":"HAS_TIER", "object_value":3,
     "source_passage_id":"<exact-source-span>", "status":"verified"}
  ],
  "open_issues": []
}
```

*Example schema only; the precise packet boundary must match the actual source/ingestion code.*

### Stage 3 — Independent normalization and classification

Normalize IDs/aliases, roles/subtypes, spell membership/tier, item categories, weapon types/proficiencies, and cross-reference resolution. Validate against manifest facts **without reusing an extraction agent's assumptions as independent evidence**. Where the source lists a spell under multiple classes, create all memberships. For edition-specific spell levels, use source-scoped offerings or validated common level facts. Distinguish explicit text, direct table value, and inferred relation.

### Stage 4 — Cross-packet reconciliation (new hard requirement)

After a book or defined batch is assembled, link cross-section dependencies and exceptions (spell ↔ class list ↔ spellcasting mechanics; armor/weapon entry ↔ category ↔ class rule; table ↔ effects; general rule ↔ variant override). Scan `mentioned_reference` targets to find their definitions. Reconcile node IDs across packets, duplicate display names, renamed identities, and conflicting assertions. Do not auto-merge semantic equivalents across editions.

### Stage 5 — Graph QA and publishing gates

Automated gates for each packet and corpus:

1. **Inventory:** every required manifest entity has exactly one correct canonical node (or a documented unresolved/excluded status), all source listings reconcile, and reference-only entities are explicitly tagged.
2. **Correctness:** every class/tier/permission/category assertion matches its own source entry and source span. Flag adjacent-entry leakage, contradictory class/tier assignments, and source-heading/name mismatches.
3. **Structure:** all edge endpoints exist; IDs are unique; `entity_role` is valid; no unresolved raw-ID labels without exceptions; enumerated edge predicates and type signatures are valid.
4. **Coverage:** classifications are complete for node roles that require them, or listed as justified exceptions. Spells should have list memberships/tiers if definitions exist. Mandatory class permissions and weapon categories have full source-backed coverage.
5. **Precedence:** variant and override targets resolve correctly; optional/disabled content remains discoverable but inactive.
6. **Provenance:** every claim intended for authoritative use has exact source locator, passage ID, version, and extraction/verification state. Any unsupported or inferred claim is not treated as fact.
7. **Change safety:** idempotent replay and graph-diff tests; no unexplained loss of pre-existing correct nodes/edges or loss of source provenance.

A packet passes only when all hard gates pass; questionable data goes to `needs_review` and does not get silently published as authoritative.

### Stage 6 — Retrieval validation, separate from extraction validation

Use exact/alias match first; BM25 and/or vectors as fallback; typed bidirectional traversal with query-specific edge priorities; conditional expansion through hubs; scoped source-text fetch; cite actual passages. **Do not globally ban high-degree nodes or always expand every `rule` node.** For a particular named item, expand to its categories; for *list all items of category X*, traverse category members downward. Use both source text and edge traces, but never answer solely from an edge label.

Benchmark graph-only, hybrid-search-only, and combined retrieval on a gold QA set. Record missing source, wrong node, wrong relation, wrong applicability, wrong citation, and wrong adjudication **separately**.

## E. Retroactive repairs for **already processed packets**

Do not simply rerun every packet and overwrite the graph. Use a migration + replay process that preserves trusted work and exposes all differences.

1. **Snapshot:** freeze `graph.json`, both master CSVs, source files, and any available raw packet/agent outputs; compute hashes and establish a `baseline_graph_version`.
2. **Reconstruct packet ledger:** if original packet IDs exist, use them; otherwise derive provisional book/page/section groups from the 646 location tuples and re-associate each group with its original structured Markdown/PDF source. A location tuple is not proof of the original packet boundary.
3. **Run the new manifest extractor on *all* previously processed source content**, not just packets with existing classification gaps. This catches the four absent Shadowdark spells and other absent entities.
4. **Classify each packet's remediation route:** `ENRICH_EXISTING` for missing verified attributes/relations, `REEXTRACT_SOURCE` for page-70 alignment or incomplete A–H spell processing, `RENAME_IDENTITY` for Control Water, `RECONCILE_CROSS_PACKET` for spell-list/class/equipment links, `REVIEW_MANUALLY` for ambiguous source or contradictory facts.
5. **Replay idempotently:** upsert by canonical identity and stable claim/source keys; maintain a redirect from old to new IDs when renaming. Never deduplicate by `(source,edge_type,target)` alone; aspects, conditions, source versions and evidence may distinguish valid parallel claims.
6. **Compare staged output to baseline:** generate added/changed/deleted node and edge diffs, with source evidence and reason codes. Prefer keeping correctly verified edges and replacing only superseded claims. Require review on deletions, identity merges and changed permissions.
7. **Rebuild derived exports:** after approval, recompute degrees, core degrees, connection metrics, and the JSON graph from canonical records—not by independently editing the three published files.
8. **Run global reconciliation and behavioral regression tests** across the whole repaired Shadowdark corpus (including CS1–CS3 and optional modes). Publish a versioned graph only after gates pass. Preserve an easy rollback.
9. **Track remaining debt:** each unresolved reference or claim carries a machine-readable reason, owner, affected packets, and source locator; no silent completion status.

### Suggested first replay batches

| Batch | Work | Required review |
|---|---|---|
| `SD:spells:inventory` | Core spell lists versus spell entries, including Alarm/Bless/Fixed Object/Fabricate | Cross-check complete spell inventory |
| `SD:p57,p319` | Rename/migrate Control Water; verify both source references | Identity merge and source text |
| `SD:p70` | Repair Sending, Shapechange, Shield of Faith; inspect all neighboring spell rows | Attribute attribution/column alignment |
| `SD:pp54-62` | Re-extract class/tier links, including spells already in graph | Verify complete local inventory and classification |
| `SD:classes+equipment` | Item/weapon taxonomy, 12 class armor and weapon permissions, item usability | Restrictions must match actual rule statements |
| `SD:tables+isolates` | Generic equipment roles, missing aliases, tavern table memberships, detached nodes | Confirm relationships rather than force connectivity |
| `CS1,CS2,CS3` | Reconcile Witch/Seer spell lists, class offerings, mention-only spell nodes, optional content | Don't mistake book availability for variant activation |

## F. Universal schema additions (not Shadowdark-only)

**Node**: `id`, `label`, `kind`, **`entity_role`** (`definition|category|type|list|reference_only`), `aliases[]`, `ruleset_id`, `edition_id`, `source_versions[]`, `source_passage_ids[]`, `definition_status` (`defined|mentioned_only|unresolved|excluded`), `review_status`.

**Claim/edge**: `claim_id`, `source_id`, `predicate`, `target_id` or typed literal `value`, `aspect`, `condition_text`, `condition_ast?`, `applicability_scope`, `polarity`, `evidence_kind` (`explicit|tabular|derived|inferred`), `source_passage_id`, `extraction_packet_id`, `generator_version`, `review_status`, `supersedes_claim_id?`, `override_basis?`.

**Source passage**: `passage_id`, `ruleset_id`, `edition_id`, `book_id`, printing/revision, `page`, `section`, `entry_id`, document span, optional geometric region/column, text locator, hash. Source passage IDs **must** survive a reprocessing of the same source/version. Different errata/printings can yield distinct passage versions.

**Catalog membership / authorization**: represent `spell + class-list + tier`, `class + allowed/equipped/proficient weapon-set`, `class + permitted armor`, and `rule + predicate/effect` as *separate claims*. Where a relationship involves more than two parties (e.g., spell membership with level and edition), use a reified claim or a typed edge with scoped attributes. Avoid spreading coupled facts across independent edges that can be mismatched.

**Applicability**: `source_available` ≠ `book_enabled` ≠ `variant_enabled` ≠ `entity_possessed` ≠ `condition_satisfied`. Rules may be retrievable as references when they are not active in a session.

**Versioned authority**: different rulesets/editions and source versions have independent canonical identities. Cross-edition correspondences are *linked*, not implicitly merged. Campaign house rules, setting changes and session state should be separate overlays with an explicit precedence policy.

## G. 5e / other-RPG readiness requirements

**Do not hard-code Shadowdark page numbers, five spell tiers, four classes, or its 14 edge types into the core generator.** The engine should load edition-specific extraction profiles containing entity types, inventory sources, vocabulary, relation expectations, semantic validation, and authority rules.

For **D&D 5e 2014** and **2024**, use separate edition/version profiles. Official SRD 5.1 and SRD 5.2.1 are distinct and **not exhaustive copies of their corresponding Player's Handbooks**. The manifest's expected entities must be scoped to the actual imported, authorized books, not to an SRD assumed to contain everything. SRD 5.2.1 includes renamed and revised content; retain explicit edition + errata scope.

5e-specific requirements include conditions and action economy, class and subclass features, feats, spell-list membership, multiclass prerequisites, equipment proficiency, concentration, reactions, and specific-over-general exceptions. Treat **weapon proficiency** separately from **permission to wield** (2014/2024 generally allow using an unproficient weapon, without the proficiency bonus). Subclass features, feats and magic items can add permissions or alter applicability; capture them as claims with predicates and priority rules rather than just generic `MODIFIES` edges.

**Other RPGs** may use different notions entirely (e.g., skill ranks, dice pools, spell schools instead of class lists, armor encumbrance rather than prohibition). The universal engine should handle typed claims, provenance, scope, and manifests; a game adapter defines domain semantics and validation—not the other way around.

## H. Regression tests and acceptance criteria

| ID | Test | Minimum passing behavior |
|---|---|---|
| `SD-INV-01` | Compare complete SD core spell lists with graph | All listed spells accounted for as defined nodes or explicitly reviewed exceptions; no phantom Control Weather |
| `SD-SPL-02` | Sending / Shapechange / Shield of Faith | Correct class/tier and exact p.70 evidence; Scrying unaffected |
| `SD-SPL-03` | Shadowdark Control Water | One canonical node, Priest + Wizard / Tier 4, correct p.57/p.319 references and old-ID redirect |
| `SD-SPL-04` | Sleep / Fireball / Cure Wounds / Witch/Seer spells | Required book-scoped spell-list membership/tier verified; references distinguished from entries |
| `SD-ITEM-05` | Wizard + plate mail, Wizard + greatsword | Correct class restriction text retrieved; no permission inferred from category membership alone |
| `SD-ITEM-06` | Magic armor and weapon taxonomy | Instance classified by function and magical status, sourced; class rules reachable via category |
| `SD-REL-07` | Focus under damage | Retrieve proper constraints and related focus check without dumping unrelated spells |
| `SD-VAR-08` | Normal dying vs optional Fatality Mode | Disabled optional mode does not apply; enabled mode and override do |
| `SD-QA-09` | A missing/unknown spell name | Exact index detects missing entity; falls back to source search; no invented rules |
| `SD-QA-10` | Rerun same packet | Identical canonical identities and claims; no duplicate edges; deterministic diff |
| `D5-ED-01` | 2014 vs 2024 named rule/spell | Edition-specific results and source citations; no cross-edition leakage |
| `D5-PROF-02` | 5e wizard uses a weapon without proficiency | Distinguish wieldability from attack-bonus proficiency |
| `D5-MULTI-03` | 5e multiclass/feat/subclass exception | Requires/prerequisite/modifier/override pathways and applicability evidence |
| `UNIV-TBL-04` | Multi-column source, tables, nested exceptions | Correct entry attribution, full table header context, references to exact spans |
| `UNIV-COV-05` | Intentionally omit a manifest entry from packet output | QA blocks publishing and reports missing source entity |
| `UNIV-SCOPE-06` | Book enabled, variant disabled, entity absent | Searchable inactive rules stay inactive; runtime applicability is correct |

**Publish gates (target criteria):** zero dangling endpoints; zero unsupported source passages on authoritative claims; zero unreviewed source-inventory omissions; zero unexplained classified-role gaps; zero unresolved high-severity contradictions; 100% pass on deterministic gold regression cases; no unexplained losses versus baseline. Performance, retrieval recall, citation correctness and final answer correctness must be measured separately—do not claim 100% future-rule recall from structural completeness alone.

## I. Priority/order of delivery to the architect agent

- **P0 (before trusting Shadowdark answers):** inventory manifest; four absent spells + Control Water identity; page-70 correction; classification source verification; exact passage IDs; disable inappropriate optional modes.
- **P1 (before building graph-first production retrieval):** taxonomy roles and categories; class equipment/weapon permissions; per-spell list membership; source-verified conditions and overrides; packet lineage + idempotent replay; targeted regression suite.
- **P2 (before 5e onboarding):** edition/errata namespace; ruleset profiles; generalized spell-list/feature/proficiency semantics; migration tooling; cross-edition isolation and benchmark suite.
- **P3 (after correctness):** graph-vs-hybrid benchmarks, query planner optimization, optional cache/cost benchmarking. Retrieval performance and KV prompt caching are downstream concerns; don't conflate them with graph extraction quality.

### Information still needed to implement this literally

The uploaded files contain the **exported graph**, not the generator's source code, prompts, packet boundaries, input manifest, normalization rules or storage schema. An architect implementation should first map the above requirements to those actual components, and record which existing packet artifacts can be replayed vs which require source re-extraction. Treat named processing stages as a *target architecture*, not claims about current implementation internals.

### External reference anchors (verification / future 5e onboarding)

- Published Shadowdark spell lists and page-70 class/tier spot-check: https://anjours-arsenal.net/tools/shadowdark-spells and https://d1vzi28wh99zvq.cloudfront.net/pdf_previews/521133-sample.pdf
- D&D Beyond official SRD 5.1 and 5.2.1 (plus conversion notes): https://www.dndbeyond.com/srd
- D&D Beyond 2014 equipment/proficiency rules: https://www.dndbeyond.com/sources/dnd/basic-rules-2014/equipment
- D&D Beyond 2024 equipment/proficiency rules: https://www.dndbeyond.com/sources/dnd/br-2024/equipment

