# 5th Edition (2024 Revised) Rules Graph Integration Proposal

**Author:** Antigravity  
**Architect Reviewer:** Codex  
**Date:** 2026-10-26 (Revision 4)  
**Status:** Revised Proposal (Addressing Evidence Specification Review Points 1–3)  
**Target Ruleset:** `dnd5e-2024` (2024 D&D 5th Edition Revised Core)  
**Primary Source Work:** *Player's Handbook* (2024 Revision, `XPHB`)  

---

## 1. Executive Summary & Strategic Directive

Owner instruction on 2026-10-26 explicitly confirmed the primary ruleset focus:
> **Target the 2024 Revised Edition (`XPHB 2024`) as a self-contained ruleset.** The 2024 ruleset should stand alone and contain all necessary rules without requiring backward reference to the 2014 edition.

Following independent technical audits by Codex and Antigravity, and incorporating all architectural feedback from `FIVE_E_AGY_REVISION_REQUESTS.md` and subsequent review, this proposal establishes the complete architecture and phased delivery plan for ingesting 2024 5e content into the repository.

The approach combines a **core-first delivery roadmap** with **rigorous source, identity, and provenance safeguards**:
1. **Scope Bounding:** The 151.7 MiB `5etools/` folder is treated as a temporary, read-only intake reference. No bulk dump of non-rules content (adventures, bestiary statblocks, web assets) will enter the repository.
2. **Typed Embedded-Definition Resolution:** 5etools book files are structural skeletons, not self-contained text. The adapter explicitly detects and resolves embedded definition stubs (`type: "statblock"`) against their respective typed collections across five upstream files.
3. **Auditability After Upstream Deletion (Implementable Evidence Contract):** To honor the owner's goal of deleting `5etools/` after setup, every generated packet retains not just cryptographic hashes, but the **actual canonical input records, dependency context, and a versioned page calibration map** in an immutable sidecar (`evidence.json`). Serialization follows RFC 8785 JSON Canonicalization Scheme (JCS) and establishes a concrete, implementable contract with verified values.
4. **Contract-Conforming Pagination & Replay Architecture:** Addresses `contracts/SOURCE_MARKDOWN.md:95` directly. Because preceding page markers remain in effect continuously, leaving paragraphs "unanchored" would falsely attribute multi-page sections to the initial page. Multi-page sections lacking internal boundary data are **held at the intake gate for physical page calibration** before release. Calibration markers are captured as structured, versioned input in `evidence.json`, enabling deterministic replay of calibrated markdown without upstream files.
5. **Decoupled Adapter Staging:** We build a lightweight **Core Document Profile** first (prose, tables, lists, and typed definition embeds), deferring complex entity-hydration machinery (`_copy`, magic-item variants, subrace composition) until entity catalogs are actually claimed.
6. **Separation of Proposal from Governance & Strict Graph Invariants:** All ontology prefixes, entity identities, and edge relations are presented as candidate models awaiting formal Architect decision. Mathematical formulas and calculation rules remain in source evidence and are **not** embedded into graph aspect/condition strings, preserving `contracts/GRAPH_INVARIANTS.md`.

---

## 2. Source Analysis: The 2024 Player's Handbook (`XPHB`)

The 2024 Player's Handbook provides a formalized rules engine. Its structure in `5etools/data/book/book-xphb.json` and associated data files includes:

| Locus | Page(s) | 5etools Structure | Mechanical Description |
| :--- | :---: | :--- | :--- |
| **Chapter 1: Playing the Game** | 7–31 | `book-xphb.json#/bookData/0/data/1` | D20 Tests, Advantage/Disadvantage, Ability Checks, Saving Throws, Attack Rolls, Movement, Vision, Rest & Recovery. |
| **Chapter 6: Equipment** | 213–233 | `book-xphb.json#/bookData/0/data/6` | Armor, weapons, shields, weapon mastery properties, adventuring gear, tool proficiencies. |
| **Chapter 7: Spells** | 235–343 | `book-xphb.json#/bookData/0/data/7` + `data/spells/spells-xphb.json` | Spellcasting mechanics (spell slots, casting times, components, concentration, 6 areas of effect) and 391 revised spells. |
| **Rules Glossary** | 360–378 | `book-xphb.json#/bookData/0/data/10` | Alphabetical definitions of 155 formal game rules, actions, conditions, senses, statuses, and environmental hazards. |

### The 155 Embedded Definitions of the Rules Glossary

The Rules Glossary (`book-xphb.json#/bookData/0/data/10/entries/1/entries`) contains 159 total entries comprising 1 introductory text block, 3 illustration blocks, and **155 embedded definition references**.

Upstream embedded definitions use typed reference objects:
```json
{
  "type": "statblock",
  "tag": "status",
  "name": "Surprised",
  "source": "XPHB"
}
```

These 155 embedded definitions represent **six distinct entity kinds across five upstream data files** (conditions and statuses share a single file):

| Entity Kind (`tag`) | Count | Target File | Example Resolved Definitions |
| :--- | :---: | :--- | :--- |
| `variantrule` | 115 | `data/variantrules.json` | *Ability Check, Advantage, Armor Class, Attack Roll, Attunement, Bonus Action, Cover, Critical Hit, D20 Test, Damage Roll, Difficult Terrain, Disadvantage, Dying, Heroic Inspiration (p. 368, index 124), Long Rest, Short Rest, Resistance, Vulnerability, Temporary Hit Points* |
| `condition` | 15 | `data/conditionsdiseases.json` | *Blinded, Charmed, Deafened, Exhaustion, Frightened, Grappled, Incapacitated, Invisible, Paralyzed, Petrified, Poisoned, Prone, Restrained, Stunned, Unconscious* |
| `status` | 3 | `data/conditionsdiseases.json` | *Bloodied, Concentration, Surprised* |
| `action` | 13 | `data/actions.json` | *Attack, Dash, Disengage, Dodge, Help, Hide, Influence, Magic, Ready, Search, Study, Utilize* |
| `hazard` | 5 | `data/trapshazards.json` | *Burning, Dehydration, Malnutrition, Suffocation, Falling* |
| `sense` | 4 | `data/senses.json` | *Blindsight, Darkvision, Tremorsense, Truesight* |

**Resolution & Dependency Boundary:**
* All 155 embedded definitions resolve uniquely by `tag`, `name`, and `source: "XPHB"`.
* While the direct top-level definition objects do not invoke `_copy` inheritance macros, their inner AST structures contain nested formatting tags (`{@dice}`, `{@condition}`, `{@damage}`, etc.), tables, and list structures. The Profile 1 adapter must validate and render these inner AST constructs deterministically; it must not assume all transitive dependencies are supported without explicit validation.
* Ordinary inline reference tags (e.g. `{@condition blinded}`) must remain hyperlinks or semantic tags in `source.md`; they must **not** be recursively inlined as full definition blocks, which would destroy the modularity and text boundaries of the source packet.

---

## 3. Two-Profile Adapter Architecture

To prevent over-engineering while guaranteeing correctness and auditability, extraction tooling in `tooling/dnd5e/` is structured into two phased profiles:

```
┌────────────────────────────────────────────────────────────────────────┐
│                       Adapter Profile 1: Core Document                 │
│                 (Immediate: Core Rules, Actions, Conditions)           │
├────────────────────────────────────────────────────────────────────────┤
│ • Resolves bookData hierarchy (sections, entries, lists, tables).       │
│ • Detects `type: "statblock"` and dispatches typed lookups across the  │
│   6 entity kinds in the 5 upstream files.                              │
│ • Inlines the 155 glossary definitions with provenance metadata.       │
│ • Honors SOURCE_MARKDOWN.md:95 pagination rules:                       │
│   - Emits {#pNNN} for verified single-page entries.                    │
│   - Preserves definition-specific citations (e.g. p. 368).             │
│   - Holds unannotated multi-page sections at intake gate for physical  │
│     calibration rather than permitting continuous false inheritance.   │
│   - Consumes versioned page calibration maps to replay calibrated      │
│     page markers deterministically.                                    │
│ • Emits conforming Pandoc Markdown (source.md) and implementable       │
│   canonical source records in the evidence sidecar (evidence.json).    │
│ • Zero creature copy, magic-item templates, or subrace logic needed.   │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       Adapter Profile 2: Entity & Class                │
│                 (Deferred: Phase 3 Classes, Phase 4 Catalogs)          │
├────────────────────────────────────────────────────────────────────────┤
│ • Fully qualified feature UIDs: source|class|subclass|feature|level    │
│ • Resolves class feature trees, progression tables, and spell slots.   │
│ • Disambiguates spell grants: base list, prepared, innate, or choice.  │
│ • Upstream Node-assisted resolver for _copy, _preserve, and _mod.      │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Core Rules Delivery Plan: Five Topic Groups

Work is organized into **five coherent mechanical Topic Groups**. Each Topic Group is extracted into bounded, create-only packets conforming to `contracts/FILE_NAMING.md` and `contracts/SOURCE_MARKDOWN.md`.

> [!NOTE]
> All node IDs, relationship types, and mechanical assertions below are **candidate models** grounded in the 2024 source text. They illustrate intended scope and boundaries. They do **not** predetermine Analyst extraction, represent approved ontology, or imply prior independent mechanical review.

```mermaid
flowchart LR
    TG1[Topic Group 1: D20 Tests & Adjudication] --> TG2[Topic Group 2: Action Economy & Movement]
    TG2 --> TG3[Topic Group 3: Combat Resolution & Damage]
    TG3 --> TG4[Topic Group 4: Standardized Conditions]
    TG4 --> TG5[Topic Group 5: Spellcasting Rules Engine]
```

### Topic Group 1: D20 Tests & Core Adjudication
* **Source Loci:** `book-xphb.json` Chapter 1 (pp. 7–14) + Rules Glossary definitions (*D20 Test, Ability Check, Saving Throw, Attack Roll, Advantage, Disadvantage, Heroic Inspiration, Proficiency Bonus, Difficulty Class*).
* **Source-Backed Candidate Assertions:**
  - *D20 Test Umbrella:* D20 Tests comprise three distinct rolls: Ability Checks, Saving Throws, and Attack Rolls. Candidate: `rule_d20_test` gates/subsumes `rule_ability_check`, `rule_saving_throw`, `cbt_attack_roll`.
  - *Advantage & Disadvantage:* Advantage and Disadvantage are roll-selection mechanics (roll two d20s, select higher or lower die); they are distinct from die rerolls. Candidate: `rule_advantage` and `rule_disadvantage` modify dice selection in `rule_d20_test`.
  - *Heroic Inspiration:* Allows a creature to reroll *any die* (including damage dice, ability checks, saving throws, etc.), not exclusively a D20 Test. Candidate: `rule_heroic_inspiration` grants reroll mechanic on any die roll.
  - *Proficiency Bonus:* Adds to D20 Tests when using a proficient skill, weapon, or tool, scaling by character level. Candidate: `prof_bonus` modifies qualified rolls under proficiency conditions.
  - *Ability Scores & Modifiers:* Base ability scores (`abil_strength`, etc.) deterministically calculate derived modifiers (`stat_strength_mod`, etc.), which apply to checks, saves, and attacks.

### Topic Group 2: Action Economy, Movement & Environment
* **Source Loci:** `book-xphb.json` Chapter 1 (pp. 15–24) + Rules Glossary definitions (*Action, Bonus Action, Reaction, Movement, Difficult Terrain, Vision, Senses, Hazards, Short Rest, Long Rest*).
* **Source-Backed Candidate Assertions:**
  - *Action Budget:* On a turn, a creature can take one Action and move. If an ability grants a Bonus Action, it can take one. 
  - *Reaction Availability:* A Reaction is an instant response to a trigger. Once taken, another Reaction is unavailable until the start of the creature's next turn.
  - *Standard Actions:* Candidate gating: `rule_action` gates standard actions (`act_attack`, `act_dash`, `act_disengage`, `act_dodge`, `act_help`, `act_hide`, `act_influence`, `act_magic`, `act_ready`, `act_search`, `act_study`, `act_utilize`).
  - *Movement Speeds:* Separate speed modes (`ex_speed_walk`, `ex_speed_fly`, `ex_speed_swim`, `ex_speed_climb`, `ex_speed_burrow`).
  - *Rest Recovery:* Short and Long Rests govern recovery of hit points, hit point dice, and tracked resource pools (`pool_`).

### Topic Group 3: Combat Resolution, Damage & Healing
* **Source Loci:** `book-xphb.json` Chapter 1 (pp. 25–31) + Rules Glossary definitions (*Initiative, Armor Class, Cover, Damage Roll, Critical Hit, Resistance, Vulnerability, Immunity, Bloodied, Dying, Death Saving Throw, Temporary Hit Points*).
* **Source-Backed Candidate Assertions:**
  - *Turn Sequencing:* Combat initiative (`cbt_initiative`) determines turn order at combat start.
  - *Attack Resolution:* Attack rolls (`cbt_attack_roll`) are compared against target Armor Class (`cbt_armor_class`).
  - *Cover:* Half Cover (+2 AC, +2 Dex saves), Three-Quarters Cover (+5 AC, +5 Dex saves), Total Cover (cannot be targeted directly by attacks or spells).
  - *Damage Modifiers:* Resistance (damage halved), Vulnerability (damage doubled), Immunity (damage negated).
  - *Dropping to 0 HP:* Triggers the `cond_unconscious` condition and requires `cbt_death_save` rolls at the start of turns while dying.

### Topic Group 4: The 15 Standardized Conditions & Statuses
* **Source Loci:** `book-xphb.json` Rules Glossary (pp. 360–378) + `data/conditionsdiseases.json` (*Blinded, Charmed, Deafened, Exhaustion, Frightened, Grappled, Incapacitated, Invisible, Paralyzed, Petrified, Poisoned, Prone, Restrained, Stunned, Unconscious* + statuses *Bloodied, Concentration, Surprised*).
* **Source-Backed Candidate Assertions:**
  - *15 Formal Conditions:* Candidate nodes `cond_blinded`, `cond_charmed`, `cond_deafened`, `cond_exhaustion`, `cond_frightened`, `cond_grappled`, `cond_incapacitated`, `cond_invisible`, `cond_paralyzed`, `cond_petrified`, `cond_poisoned`, `cond_prone`, `cond_restrained`, `cond_stunned`, `cond_unconscious`.
  - *3 Formal Statuses:* `status_bloodied` (HP at or below 50% max), `status_concentration` (maintaining spell/feature), `status_surprised` (disadvantage on initiative rolls).
  - *Condition Interactions:*
    - `cond_incapacitated`: creature cannot take Actions, Bonus Actions, or Reactions, and its concentration is broken.
    - `cond_exhaustion`: cumulative -2 penalty per level to D20 tests and speed reduction.
    - `cond_prone`: creature's attack rolls have disadvantage. An attack roll against the creature has advantage if the attacker is within 5 feet (regardless of melee or ranged attack); otherwise, the attack roll has disadvantage.
    - `cond_paralyzed` & `cond_unconscious`: creature has Incapacitated; automatically fails Strength and Dexterity saving throws; attack rolls against it have advantage; any attack roll that hits is a critical hit if the attacker is within 5 feet.

### Topic Group 5: Spellcasting Rules Engine
* **Source Loci:** `book-xphb.json` Chapter 7 (pp. 235–243) + Rules Glossary definitions (*Spell, Cantrip, Spell Slot, Casting Time, Concentration, Range, Area of Effect*).
* **Source-Backed Candidate Assertions:**
  - Leveled spells expend spell slot resources (`pool_spell_slot_1`, etc.).
  - Spell components (Verbal, Somatic, Material) gate casting.
  - Concentration limits: maximum 1 concentration effect active at a time; taking damage triggers Constitution saving throw (DC 10 or half damage taken, whichever is higher, **up to a maximum DC of 30**).
  - Areas of effect shapes: **Cone, Cube, Cylinder, Emanation, Line, Sphere** (six standard area shapes in the 2024 revision).

---

## 5. Proposed Prefix and Identity Worksheet

To prevent concept conflation and enforce `contracts/GRAPH_INVARIANTS.md`, 5e entities must adhere to strict category disambiguation.

> [!IMPORTANT]
> The prefixes and schemas below are **proposals** submitted for Architect approval. They do not constitute approved canonical registry entries until a formal Architect Decision and schema/tool validation are completed.

```
┌─────────────────────────┬────────────────────────────────────────────────────────┐
│ Conflation Risk         │ Proposed Separation                                    │
├─────────────────────────┼────────────────────────────────────────────────────────┤
│ Skill vs. Proficiency   │ • The Skill Check Rule: rule_skill_athletics           │
│ vs. Ability Check       │ • Proficiency Bonus Value: prof_bonus                  │
│                         │ • Proficiency Grant: class/origin gates prof_bonus     │
├─────────────────────────┼────────────────────────────────────────────────────────┤
│ Saving Throw vs.        │ • The Save Check Rule: save_dexterity                  │
│ Save Proficiency        │ • Proficiency Grant: prof_bonus modifies save          │
├─────────────────────────┼────────────────────────────────────────────────────────┤
│ Class Feature vs.       │ • Feature Rule: feature UIDs (parent-qualified)        │
│ Tracked Resource        │ • Tracked Resource Pool: pool_fighter_action_surge     │
├─────────────────────────┼────────────────────────────────────────────────────────┤
│ Category Membership vs. │ • Category Membership: TAG / IS_A relation             │
│ Mechanical Gating       │ • Rule Gating: GATES / CONSTRAINS mechanical edge      │
└─────────────────────────┴────────────────────────────────────────────────────────┘
```

### Proposed Prefix Worksheet

| Prefix | Domain / Semantics | Candidate Examples |
| :--- | :--- | :--- |
| `rule_` | General rules, subsystems, rests, movement rules | `rule_d20_test`, `rule_ability_check`, `rule_cover`, `rule_short_rest`, `rule_long_rest` |
| `act_` | Standardized game actions | `act_attack`, `act_dash`, `act_disengage`, `act_dodge`, `act_help`, `act_magic`, `act_utilize` |
| `cond_` | The 15 official conditions | `cond_blinded`, `cond_exhaustion`, `cond_incapacitated`, `cond_paralyzed`, `cond_prone` |
| `status_`| The 3 official glossary statuses | `status_bloodied`, `status_concentration`, `status_surprised` |
| `cbt_` | Combat adjudication variables & mechanics | `cbt_attack_roll`, `cbt_armor_class`, `cbt_damage`, `cbt_initiative`, `cbt_hit_points`, `cbt_death_save` |
| `abil_` | Core ability scores (attributes) | `abil_strength`, `abil_dexterity`, `abil_constitution`, `abil_intelligence`, `abil_wisdom`, `abil_charisma` |
| `stat_` | Derived ability modifiers | `stat_strength_mod`, `stat_dexterity_mod`, etc. |
| `save_` | The 6 saving throw types | `save_strength`, `save_dexterity`, `save_constitution`, `save_intelligence`, `save_wisdom`, `save_charisma` |
| `prof_` | Proficiency mechanics & grants | `prof_bonus`, `prof_armor_light`, `prof_weapon_martial`, `prof_tool_thieves` |
| `pool_` | Tracked, expendable resource pools | `pool_hit_dice`, `pool_spell_slots_1`, `pool_fighter_action_surge`, `pool_monk_focus` |
| `ex_` | Movement modes & environmental rates | `ex_speed_walk`, `ex_speed_fly`, `ex_speed_swim`, `ex_speed_climb` |
| `class_`| Character class identities | `class_barbarian`, `class_cleric`, `class_fighter`, `class_rogue`, `class_wizard` |
| `spell_`| Individual spell identities | `spell_fireball`, `spell_counterspell`, `spell_shield`, `spell_cure_wounds` |
| `feat_` | Feat identities | `feat_alert`, `feat_war_caster`, `feat_great_weapon_master` |
| `item_` | Equipment & weapon archetypes | `item_longsword`, `item_plate_armor`, `item_shield` |

### Disambiguation & Identity Policies
1. **Unification of Overlapping Terms:** 
   - Attack Roll is fundamentally a combat resolution mechanic governed under `cbt_attack_roll`; `rule_attack_roll` is eliminated to prevent collision.
   - Initiative is combat turn-ordering governed under `cbt_initiative`; `rule_initiative` is eliminated.
2. **Feature Identity Qualification:**
   - Class features cannot use simple `name|class|level` strings. They must be fully qualified by edition, class/subclass, parent feature, and level:  
     `dnd5e-2024:xphb:class:fighter:action_surge:level_2`
3. **Candidate Edge Vocabulary (Awaiting Governance):**
   - Candidate edges (`GATES`, `MODIFIES`, `CONSTRAINS`, `TRIGGERS`) must be formalized by Architect Decision specifying directionality, domain/range constraints, and allowable condition predicates before executable graph compilation begins.

---

## 6. Provenance, Source Retention & Pagination

Because the owner will delete `5etools/` from the workspace after ingestion is established, **source provenance cannot rely on machine-local filesystem pointers or hash-only checks**.

### Implementable Evidence Contract in `evidence.json`

Hashes detect differences, but they cannot reconstruct missing evidence. Therefore, every generated packet committed under `books/dnd5e-2024/xphb/packets/incoming/PKT-.../` includes a concrete, implementable evidence sidecar conforming to a proposed repository schema (`repo:tooling/dnd5e/schemas/evidence-manifest.schema.json`).

The following single-record example is an **illustrative, verified record snippet** demonstrating the manifest structure using actual data from the local `5etools` snapshot (verified file digests, JSON pointer `/variantrule/124` for the XPHB *Heroic Inspiration* record, and its canonical RFC 8785 JCS hash). It serves as an illustrative proof of contract structure, not as a complete glossary packet or evidence of independently verified physical pagination for the whole glossary:

```json
{
  "$schema": "repo:tooling/dnd5e/schemas/evidence-manifest.schema.json",
  "manifest_version": "1.0.0",
  "packet_id": "PKT-5E-XPHB-360-378-rules-glossary",
  "environment": {
    "snapshot_identity": "5etools-snapshot-2024-local",
    "tool_version": "tooling/dnd5e/extract_packet.py@v1.0.0-draft",
    "parser_profile": "core-document-v1",
    "hash_algorithm": "SHA-256",
    "canonicalization_method": "RFC-8785-JCS"
  },
  "raw_file_digests": {
    "data/book/book-xphb.json": "92aa9216f130eaf25804a453d57f0c5207d0531df6648e88021bf5432bb8ebd6",
    "data/variantrules.json": "fbbaed4bb8002076fac0e38a59ed65bac34e261ac753602f3a02b0bdfb1a6485"
  },
  "page_calibration_map": {
    "calibration_version": "1.0.0",
    "status": "calibrated",
    "anchors": [
      {
        "page": 368,
        "marker": "{#p368}",
        "target_entity": "xphb:variantrule:heroic_inspiration",
        "json_pointer": "/variantrule/124",
        "insertion_point": "entry_start"
      }
    ]
  },
  "retained_records": [
    {
      "entity_uid": "xphb:variantrule:heroic_inspiration",
      "source_file": "data/variantrules.json",
      "json_pointer": "/variantrule/124",
      "declared_page": 368,
      "raw_record_sha256": "6f796a23d42d0547260569ef8f325bc77d33e556dfab8167f389597f90e66a80",
      "canonical_record": {
        "basicRules2024": true,
        "entries": [
          "If you ({@variantrule Player Character|XPHB|a player character}) have Heroic Inspiration, you can expend it to reroll any die immediately after rolling it, and you must use the new roll.",
          "If you gain Heroic Inspiration but already have it, it's lost unless you give it to a {@variantrule Player Character|XPHB|player character} who lacks it."
        ],
        "name": "Heroic Inspiration",
        "page": 368,
        "ruleType": "C",
        "source": "XPHB",
        "srd52": true
      }
    }
  ],
  "provenance_content_digest": "82ea052a77c391e007b0fd1a007ca0b092a6fdfe8f313c58ba582e29b531dd3c"
}
```

### Deterministic Serialization & Exact Field-Selection Rule for Digest
1. **Canonical JSON Serialization (JCS):** All retained structures are serialized strictly using RFC 8785 JSON Canonicalization Scheme (JCS) (keys sorted lexicographically, IEEE 754 float normalization, UTF-8 encoded without whitespace).
2. **Digest Definitions & Exact Field-Selection Rule:**
   - `raw_file_digests`: Standard SHA-256 of the unparsed file on disk at extraction time.
   - `raw_record_sha256`: SHA-256 computed over the JCS byte serialization of the extracted JSON sub-object.
   - `provenance_content_digest`: SHA-256 computed over the canonical JCS serialization of the **closed set of six semantic integrity fields**:
     1. `manifest_version`
     2. `packet_id`
     3. `environment` (tool identity, profile, hash and JCS algorithm versions)
     4. `raw_file_digests`
     5. `page_calibration_map`
     6. `retained_records` (including pointers, hashes, and canonical records)
     
     All other fields are explicitly excluded from this digest calculation:
     - Document schema identifier `$schema` (a reference URI for validation, not semantic packet state).
     - The `provenance_content_digest` field itself (preventing self-referential circularity).
     - Any non-semantic, transient execution metadata (such as execution duration or local machine hostname).
3. **Retained Selection & Order:** Records are captured in their exact upstream presentation/glossary order, retaining their JSON pointer path and immediate parent section locus.

---

### Retaining Page Calibration as Replay Input

`contracts/SOURCE_MARKDOWN.md:95` dictates that preceding page markers remain in effect continuously. Multi-page sections lacking internal boundary data in 5etools JSON must be calibrated against print/PDF sources.

However, if a contributor manually inserts `{#pN}` markers into `source.md`, an automated replay from upstream JSON records alone cannot reproduce those markers. Therefore:
1. **Calibration Map Storage:** All manual calibration decisions are formalized as a versioned `page_calibration_map` stored directly inside `evidence.json`.
2. **Anchor Precision:** The calibration map binds each printed page boundary (`{#pN}`) to an exact upstream location:
   - Target entity UID and JSON pointer.
   - Structural insertion point: entry start, intra-paragraph character/word offset, or table row index. *(Note: Exact offset coordinate units—whether UTF-8 code units, Unicode codepoints, and whether they index upstream JSON source strings or intermediate AST blocks—will be settled in the implementation specification.)*
   - Calibration authority, verifier, and verification date.
3. **Required Replay Test with Calibration:** The automated replay test takes both `retained_records` AND `page_calibration_map` as inputs. The adapter deterministically weaves the calibrated page markers into the rendered text, reproducing `source.md` bit-for-bit without manual re-editing or upstream files.

---

### Pagination Evidence & Page Marker Governance

`contracts/SOURCE_MARKDOWN.md:95` governs page attribution:
> *"The most recent page assignment remains in effect until the next marker. The marker placement determines where that assignment begins."*

Because of this continuous attribution rule, leaving paragraphs "unanchored" after an initial page marker does **not** leave their page unknown; instead, it authoritatively attributes all subsequent text to that initial marker until a new marker appears. Emitting a section-level page marker for a multi-page section would therefore falsely attribute later pages to the section's starting page.

To guarantee pagination fidelity under repository contracts:
1. **Verified Single-Page Units:** Where an upstream record explicitly carries `"page": N` and its entire text is verified to reside within page `N` (such as individual glossary definitions), an authoritative `{#pN}` marker is emitted at the unit boundary.
2. **Definition-Specific Citations:** Each embedded definition preserves its own upstream source page citation (e.g. Heroic Inspiration at `{#p368}`) rather than inheriting the page of the container referencing it.
3. **Multi-Page Intake Gate (Contract Blocker):** When extracting multi-page sections (such as Chapter 1 prose across pages 7–31) where upstream data lacks interior paragraph-level page breaks, the adapter **must not** emit a single starting marker and leave the remainder unanchored. Instead:
   - The packet is **held at the intake gate for physical page calibration** (manual verification against the printed book or PDF layout to record exact anchor coordinates in `page_calibration_map` and insert verified `{#pNNN}` markers at the exact paragraph where each page turns).
   - Alternatively, an explicit contract amendment for uncalibrated spans would need formal Architect authorization before release.

---

## 7. Independent Adapter Verification & Acceptance Gate

To ensure source fidelity and prevent silent data loss, the Profile 1 adapter must pass eight concrete acceptance checks verified independently by the **Reviewer** before any packet enters the active relay:

1. **Glossary Completeness:** All 155 embedded definitions in the XPHB Rules Glossary resolve uniquely under `source: "XPHB"` and preserve their exact source order and attribution. Introductory text and image blocks are accounted for separately.
2. **Fail-Closed References:** Any missing, ambiguous, or unsupported embedded target immediately halts processing with a clear source pointer; no reference may be silently skipped or omitted.
3. **Unrendered AST Detection:** All upstream AST nodes (tables, dice tags, definition lists) must have verified rendering paths. Unsupported tags trigger fatal errors, never silent string drops.
4. **Dual-Baseline Tamper & Drift Detection:**
   - *Render Tamper Test (Output vs. Frozen Evidence):* Deliberately mutating rendered Markdown output (`source.md`) must be detected and rejected by comparing against the frozen, committed `evidence.json`.
   - *Upstream Drift Test (Input vs. Pinned Manifest):* Deliberately altering an upstream input record (or source file) must fail against an independently pinned test manifest (which records expected record counts, typed keys, and root source digests). This prevents regenerating mutually consistent but corrupted evidence and output pairs.
5. **Pagination Provenance Separation:** The adapter output explicitly distinguishes declared entry pages from inherited section pages in the generated evidence sidecar.
6. **Deterministic Replay:** Executing the adapter with identical inputs produces identical byte-level outputs. If upstream inputs change, the adapter rejects stale publication evidence.
7. **Offline Replay Validation with Calibration:** The verification suite verifies that `source.md` can be regenerated and verified strictly from `evidence.json` (using `retained_records` and `page_calibration_map`) with the `5etools/` directory completely hidden/inaccessible.
8. **Edition Isolation:** Zero fallback to 2014 data collections (`book-phb.json`, 2014 spells, 2014 variantrules) is permitted. Any missing definition halts rather than falling back.

**Role Boundaries:**
* **Builder:** Implements the adapter script (`tooling/dnd5e/extract_packet.py`) and evidence generator.
* **Reviewer:** Independently executes acceptance tests and validates offline replay before approving packet release.
* **Architect:** Governs ruleset schemas, prefixes, and edge contracts under `rulesets/dnd5e-2024/`.
* **Integrator:** Sole authority to mutate `canonical/` state after verified genesis.

---

## 8. Source Admission, Rights & Permitted Output Gate

This repository does not manufacture copyright permissions. To protect repository integrity and ensure compliant downstream distribution, the following boundaries are established:

1. **Separation of Concerns:**
   - **Software Tools & Code:** Governed under the repository's open-source license (MIT).
   - **Publisher Rules Text:** Copyright Wizards of the Coast / Hasbro. Retained locally as private study/research reference evidence.
   - **Canonical Relationship Graph:** Governed mechanical relationship tuples (subject, predicate, object, aspect, condition) conforming strictly to `contracts/GRAPH_INVARIANTS.md`. In accordance with repository invariants, numeric formulas, mathematical calculations, and value thresholds are **not** encoded as aspect/condition strings; they remain in source evidence/prose unless a separate, formally governed formula payload schema is approved by the Architect.
   - **Application-Visible Output:** Downstream consumer interfaces must filter out raw publisher text expressions unless authorized.
2. **SRD 5.2 / Creative Commons Alignment:**
   - Publicly distributable text expressions must align strictly with the **System Reference Document 5.2.1 (SRD 5.2)** released under **Creative Commons Attribution 4.0 International (CC BY 4.0)**.
   - Upstream 5etools flags (`srd: true`, `srd52: true`) and alternate-name strings (e.g. *Bigby's Hand* $\to$ *Arcane Hand*) are treated as **unverified upstream metadata**. They do not constitute automatic publication authorization.
   - Before any text fragment is designated as distributable CC-BY content, its presence in the official WotC SRD 5.2 publication must be verified against an authoritative CC-BY manifest.
3. **No Legal Determination:** This technical proposal establishes data gating; it makes no legal determinations regarding fair use or copyright boundaries.

---

## 9. Summary of Reconciled Architecture

| Area | Initial Proposal | Architect Review Findings | Reconciled Strategy (Revision 4) |
| :--- | :--- | :--- | :--- |
| **Ruleset Target** | Dual / Ambiguous | Isolate editions; avoid mixed unqualified keys | **`dnd5e-2024` standalone baseline (`XPHB`)**. |
| **Data Scope** | Bulk import risk | 5etools is 85% instance data | **Core rules first (~5 MB); exclude adventures, bestiary, web code**. |
| **Embedded Definitions** | Assumed `statblock: true` boolean | Uses typed objects: `{"type":"statblock","tag":"...","name":"..."}` | **Typed lookup table across 6 entity kinds in 5 upstream files**. |
| **Transitive Dependencies** | Assumed supported because no `_copy` | Inner AST structures contain tables, dice tags, lists | **Fail-closed AST parser; explicit acceptance testing**. |
| **Provenance Retention** | Hash-only sidecar | Hashes cannot reconstruct missing records after deletion | **Retain canonical records (RFC 8785 JCS), context, and calibration maps in `evidence.json`**. |
| **Evidence Example & Provenance** | Unverified / mismatched hashes & pointer | Disagreed with files; `/variantrule/42` was TCE | **Verified against 5etools: exact SHA-256s, pointer `/variantrule/124`, proposed local schema**. |
| **Calibration Replay** | Manual edits not reproducible by replay | Manual markers in markdown cannot be replayed from JSON | **Versioned `page_calibration_map` stored in sidecar; replayed deterministically**. |
| **Provenance Digest Scope** | Only hashed environment and records | Excluded packet ID, manifest version, raw digests, calibration | **Digest hashes entire canonical payload (all integrity fields); excludes only digest & runtime transients**. |
| **Pagination Markers** | Left multi-page spans "unanchored" | Under `SOURCE_MARKDOWN.md:95`, unanchored spans inherit preceding marker | **Hold multi-page packets for physical page calibration at intake gate**. |
| **Ontology Status** | "Approved Canonical Prefix Table" | Unapproved; missing `pool_`, duplicate prefixes, unverified edges | **"Proposed Prefix and Identity Worksheet"; await Architect governance**. |
| **Mechanical Accuracy** | 2014 remnants (Ki, DC formulas, missing Emanation) | Contradicted 2024 source text | **Corrected to 2024: max DC 30, Emanation AoE, Monk Focus Points**. |
| **Independent Verification** | Generic schema check | Parse success cannot detect omissions or tandem corruption | **8-point gate with dual-baseline tamper and upstream drift tests**. |
| **Graph Boundaries** | Included "mathematical formulas" in graph | Contradicted `GRAPH_INVARIANTS.md` | **Formulas kept in source prose/evidence; graph strictly governed tuples**. |
| **Rights & Distribution** | Claimed private ingest "without restriction" | Unfounded; conflated software license with copyright text | **Explicit Permitted Output Gate; SRD 5.2 CC-BY verification required**. |

---

## 10. Current Status & Next Actions

* **Hygiene (Complete):** `5etools/` and `scratch/` are safely ignored in `.gitignore`. Working tree is clean.
* **Scope Confirmed:** 2024 Revised Edition (`XPHB`), standalone ruleset (`dnd5e-2024`), 2014 deferred.
* **Proposal Status:** Revision 4 completely resolves the three evidence specification findings (verified values, calibration replay map, comprehensive provenance digest).
* **Next Milestone:** The proposal specification is now fully grounded and ready for drafting the bounded implementation specification (`tooling/dnd5e/extract_packet.py` specification, ruleset configuration under `rulesets/dnd5e-2024/`, and Topic Group 1 calibration plan).
* **Implementation Status:** As instructed, **zero implementation, graph mutations, ruleset bootstrapping, or canonical edits have begun**. Standing by for user review and further instructions.
