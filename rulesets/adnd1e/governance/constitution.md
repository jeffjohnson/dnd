# Graph Constitution — AD&D 1e Mechanical Relationship Graph

**Version 1.8.** This document is authoritative. Any conversation producing graph
data must follow it exactly. If a rule here conflicts with a habit from another
conversation, this document wins. Changes to this file are made only by the
Architect conversation.

---

## 1. Purpose

Impact analysis: *if I change rule X, what else moves?*

This is not a rules reference, a bestiary, or a searchable rulebook. It records
**that a relationship exists, its direction, its type, and its conditions** — never
values, magnitudes, dice, or prose.

Test for any candidate edge: *if this rule were changed or removed, would the
target need review?* If no, it is not an edge.

---

## 2. The grain rule

**Capture the relationship. Never the number.**

| Correct | Incorrect |
|---|---|
| `abil_strength MODIFIES cbt_tohit` aspect="hit probability" | "Strength 18/00 gives +3 to hit" |
| `rule_aging TRIGGERS rule_system_shock` | "Aging past Venerable requires a 40% roll" |
| `tbl_poisons MODIFIES save_poison` condition="by poison class" | "Type A poison is +4 to save" |

Magnitudes change between printings, house rules, and editions. Relationships do
not. A graph of magnitudes is a badly formatted rulebook.

### 2.1 Scaling dependencies are relationships

Do not confuse a magnitude with the fact that one mechanic depends on another.
When the source explicitly says that changing one mechanic changes another,
record the dependency and omit the numeric value or formula.

For a spell description that explicitly makes an effect scale with the caster's
experience level, record `exp_level MODIFIES spell_<id>`. The `aspect` names the
affected facet without its value. `MODIFIES` polarity remains Analyst-authored
under section 6.1.

These are per-spell assertions when only a subset of spells states the
dependency. Do not infer the edge for a spell that does not state it, and do not
replace a selective set of per-spell dependencies with one aggregate edge. An
aggregate or inherited representation is appropriate only when the source states
a general rule with that scope; inherited edges then follow section 7.1.

---

## 3. Node identity

### 3.1 Format

`snake_case`, prefixed by kind:

| Prefix | Kind | Example |
|---|---|---|
| `abil_` | ability score or derived ability mechanic | `abil_constitution` |
| `class_` | character class | `class_paladin` |
| `race_` | race or subrace | `race_half_elf` |
| `rule_` | named rule or procedure | `rule_system_shock` |
| `tbl_` | table consulted as a unit | `tbl_poisons` |
| `spell_` | spell or source-named spell family/category | `spell_polymorph_other` |
| `item_` | magic item or item class | `item_ring` |
| `potion_` | potion | `potion_speed` |
| `sword_` | intelligent-sword mechanic | `sword_ego_vs_personality` |
| `monster_` | creature or creature family | `monster_undead` |
| `cbt_` | combat mechanic | `cbt_initiative` |
| `save_` | saving throw category | `save_poison` |
| `psi_` | psionic mechanic | `psi_attack_modes` |
| `sys_` | whole subsystem | `sys_alignment` |
| `exp_` | experience mechanic | `exp_level` |
| `xp_` | experience award source | `xp_treasure` |
| `hench_` | hireling / henchman | `hench_loyalty` |
| `campaign_` | campaign-level system | `campaign_social_class` |
| `gen_` | generator or random table system | `gen_random_dungeon` |
| `ex_` | exploration mechanic | `ex_movement_rate` |
| `enc_` | encumbrance | `enc_encumbrance` |
| `money_` | currency | `money_gp` |
| `prof_` | proficiency | `prof_specialization` |
| `wpn_` | weapon property or weapon statistic | `wpn_speed_factor` |
| `weapon_` | mundane weapon, weapon category, or source-named weapon family | `weapon_lance` |
| `thief_` | thief skill | `thief_open_locks` |

Use a plural or otherwise category-specific stem when a source assertion applies
to a spell family rather than one spell. A family node and a specific spell are
different identities; for example, `spell_fire_spells` does not broaden or alias
`spell_fireball`.

For a derived ability mechanic, use
`abil_<three-letter ability abbreviation>_<snake_case rule name>`. The approved
ability abbreviations are `str`, `dex`, `con`, `int`, `wis`, and `cha`; for
example, `abil_dex_reaction_adjustment` and `abil_str_exceptional`. Full-name
base-score identities such as `abil_strength` and `abil_dexterity` remain
unchanged. The abbreviated form is for the mechanic derived from a score, not a
replacement spelling for the score itself.

`weapon_` names the mundane weapon identity. `wpn_` remains reserved for a
weapon property or statistic, such as range, speed factor, or weight. Do not use
`item_` for a mundane weapon merely because it is equipment: `item_` remains
the magic-item and item-class namespace.

### 3.2 Canonical registry

`rulesets/adnd1e/registries/nodes.csv` is the list of approved node IDs. **Builders must reuse an
existing ID rather than mint a variant.** Before creating a node, search the
registry for:

- the same concept under a different prefix (`con_system_shock` vs `rule_system_shock`)
- singular/plural variants (`race_maximums` vs `tbl_race_maximums`)
- rule/table pairs of the same name

If a rule and its table are separately referenced, they are **two nodes joined by
`DERIVED_FROM`** — not one node. If they are never referenced apart, they are one node.

Drift is the single most common defect in this graph. Five duplicate IDs were found
in one conversation; parallel conversations will produce more.

---

## 4. Edge vocabulary

Thirteen types. No others. No `RELATED_TO`.

| Type | Meaning | Direction |
|---|---|---|
| `MODIFIES` | changes a value, chance, or rating | modifier → modified |
| `DERIVED_FROM` | computed or looked up from | derived → source |
| `GATES` | is a precondition for | gate → gated |
| `TRIGGERS` | causes to fire or be checked | cause → effect |
| `ALTERNATIVE_TO` | mutually exclusive or substitutable | either direction |
| `CONSUMES` | expends a finite resource | consumer → resource |
| `CONSTRAINS` | bounds without changing a value | constrainer → constrained |
| `OVERRIDES` | supersedes or replaces | overrider → overridden |
| `FEEDS_INTO` | supplies input to | input → process |
| `RESOLVED_BY` | resolution procedure | thing → procedure |
| `CROSS_REFERENCES` | text explicitly points elsewhere | source → target |
| `EXCLUDES` | asserts a connection does NOT exist | excluder → excluded |
| `EXCLUDED_FROM` | inverse of EXCLUDES | excluded → excluder |

### 4.1 On EXCLUDES and EXCLUDED_FROM

These are **positive assertions of non-connection**, and they are load-bearing.
*Knock* cannot raise a portcullis. Paladins cannot contract disease. Metal armor
gives no bonus against electrical attacks.

**They are not inverses of each other.** Zero mirrored pairs exist in the corpus.

| Type | Assertion | Example |
|---|---|---|
| `EXCLUDES` | X **actively prevents** Y | `spell_knock EXCLUDES abil_strength_bend_bars` — knock will not raise a portcullis |
| `EXCLUDED_FROM` | X **is not an input to** Y | `abil_constitution EXCLUDED_FROM tbl_parasite` — Constitution does not factor into parasite determination |

"A prevents B" and "A is irrelevant to B" are different claims and both are needed.
Keep both types. Do not collapse them.

Record either only when the text **denies a dependency a reader would otherwise
assume**. Do not record the infinite set of things a rule simply doesn't touch.

### 4.2 Choosing between similar types

- `MODIFIES` vs `CONSTRAINS` — modifies changes a number; constrains sets a bound
  or forbids a case without altering any value.
- `GATES` vs `CONSTRAINS` — gates is binary permission; constrains limits an
  already-permitted thing.
- `TRIGGERS` vs `FEEDS_INTO` — triggers causes something to happen; feeds_into
  supplies data to something that was going to happen anyway.
- `OVERRIDES` vs `ALTERNATIVE_TO` — overrides means one wins; alternative means
  the user chooses.
- `MODIFIES` vs `DERIVED_FROM` — when an ability, class, or other input changes
  a mechanic, use `input MODIFIES mechanic`, including when the mechanic is
  read directly from a table. Use `DERIVED_FROM` for computation or lookup
  lineage between separately represented concepts, such as a rule and its
  separately addressable table. Do not record both types for the same
  dependency merely because both descriptions could be made to fit.

---

## 5. Required fields

```
source_id, source_label, edge_type, target_id, target_label,
aspect, condition, polarity, polarity_basis,
book, page, section, evidence, pass, status,
supersession_basis, general_rule_id, review_flag
```

| Field | Rule |
|---|---|
| `aspect` | which facet is touched. 1–4 words. **No magnitudes.** |
| `condition` | qualitative trigger. Empty if unconditional. **No numbers.** |
| `polarity` | see §6 |
| `polarity_basis` | `derived` \| `read` \| `heuristic` \| `unset` — see §6.1 |
| `book` | `PHB`, `DMG`, `UA`, `MM` |
| `page` | one printed page number from the source's own footer; blank when one section is the sufficient locator |
| `section` | one section heading — **preferred over page**, survives repagination |
| `evidence` | see §7 |
| `pass` | extraction provenance (`page-sweep`, `spell-scan`, `general-rule`, …) |
| `status` | `core` or `optional` — see §8 |
| `supersession_basis` | **Required only for `OVERRIDES`; empty otherwise.** Controlled vocabulary: `later_publication`, `explicit_replacement`, `conflicting_procedure`, `optional_variant` |
| `general_rule_id` | **Required when `pass=general-rule`; empty otherwise.** Must reference an Architect-approved entry in the general-rule register (§7.1) |
| `review_flag` | Empty unless the edge is queued for Architect attention. Controlled vocabulary: `class_level_conflation`, `mm_keyword_derived`, `grouped_entry_attribution` |

Every edge must carry a citation. An uncited edge is rejected.

Each production edge carries exactly one primary citation locus. `page` never
contains a list, range, or delimiter-separated value, and `section` never
contains a list of headings. When the evidence spans printed pages but remains
within one section, leave `page` blank and cite that section.

If the same assertion is stated at several loci, keep one edge and preserve the
additional source assertions in the provenance manifest or ledger. Do not place
multiple loci in one edge field, and do not create duplicate edges solely to
carry additional citations.

### 5.1 Edge identity

The assertion key is:

```
(source_id, edge_type, target_id, aspect, condition)
```

Two edges are the same assertion when these five fields agree after canonical
normalization. Compare canonical IDs and the controlled edge type directly.
Compare `aspect` and `condition` case-insensitively after collapsing
non-alphanumeric separators and surrounding whitespace. Cosmetic wording or
punctuation changes do not create a new assertion.

`ALTERNATIVE_TO` is symmetric, so its two endpoint IDs are sorted before the key
is compared. Endpoint order remains significant for every directed edge type.

An exact assertion-key match is a duplicate and must not become a second
production edge. Edges that share source, type, and target but have genuinely
different aspects or conditions are distinct assertions; Builder reports them
as near matches and Reviewer determines whether each facet is independently
supported. A paraphrase of the same facet is not distinct.

Labels, polarity, citations, evidence, extraction pass, publication status, and
other provenance or review fields are not part of identity. A disagreement in
one of those fields is resolved on the existing assertion rather than preserved
as another edge. When another locus restates the same assertion, retain one edge
and record the additional locus in provenance.

---

## 6. Polarity

**The most important field for impact analysis.** Without it, `dwarf → save_poison`
and `giant spider → save_poison` are indistinguishable, and the answer to "what
breaks if poison becomes hit point damage?" is a list the user must re-read the
books to interpret.

| Value | Reads as | Example |
|---|---|---|
| `inflicts` | X inflicts this on others | giant spider **inflicts** save_poison |
| `improves` | X improves this for its bearer | dwarf **improves** save_poison |
| `worsens` | X worsens this for its bearer | ring of clumsiness **worsens** thief_skills |
| `negates` | X makes this not apply | golem **negates** save_poison |
| `enables` | X is required for this to work | cleric **enables** rule_turn_undead |
| `governs` | X is the resolution machinery | tbl_poisons **governs** save_poison |
| `neutral` | not applicable | default |

Read edges aloud as `source polarity target`. Ambiguity comes from choosing the
wrong **target**, not from the vocabulary. `dwarf improves save_poison` is
unambiguous. `dwarf improves poison` would mean dwarves are better *at poisoning*,
which is a different claim about a different node. **Point at the mechanic you mean.**

### 6.1 Polarity is only informative where edge type underdetermines it

**Governing principle: do not author information that follows deterministically from
another field.**

Ten of the thirteen edge types determine polarity completely. The build assigns
these. **Workers must never author polarity on them.**

| Edge type | Polarity | Basis |
|---|---|---|
| `GATES` | `enables` | `derived` |
| `RESOLVED_BY` | `governs` | `derived` |
| `EXCLUDES` | `negates` | `derived` |
| `EXCLUDED_FROM` | `negates` | `derived` |
| `DERIVED_FROM` | `neutral` | `derived` |
| `ALTERNATIVE_TO` | `neutral` | `derived` |
| `OVERRIDES` | `neutral` | `derived` |
| `FEEDS_INTO` | `neutral` | `derived` |
| `CROSS_REFERENCES` | `neutral` | `derived` |
| `CONSUMES` | `neutral` | `derived` |

That is **2,026 of 3,851 edges (53%) where polarity cannot drift**, because no human
assigns it.

Polarity is authored only on three types, where it carries real information:

| Edge type | Polarity | Basis |
|---|---|---|
| `MODIFIES` | Analyst-authored | `read` or `unset` |
| `TRIGGERS` | Analyst-authored | `read` or `unset` |
| `CONSTRAINS` | Analyst-authored | `read` or `unset` |

`CONSUMES` was tested and does not need authored polarity: a resource is spent
regardless of who benefits, so the direction is always `neutral`.

`polarity_basis` records how the value arrived:

| Value | Meaning | Who resolves |
|---|---|---|
| `derived` | computed from edge type per the tables above | build, automatic |
| `read` | taken from the page by an Analyst | Analyst |
| `heuristic` | pattern-matched during migration | **Reviewer must resolve** |
| `unset` | authored type, not yet determined | Analyst on next touch |

These four values are exhaustive. No other value is legal.

**No approved patch may retain `heuristic`.**

### 6.2 Do not conflate enabling with improving

`exp_level enables rule_turn_undead` is wrong. **The class enables; the level improves.**

```
class_cleric  GATES     rule_turn_undead   polarity=enables  (you must be a cleric)
exp_level     MODIFIES  rule_turn_undead   polarity=improves (higher level turns better)
```

Note the notation: `ENABLES` and `IMPROVES` are **polarity values, not edge types**.
The thirteen-type vocabulary in §4 is closed. Never write a polarity where an edge
type belongs.

Where a level threshold genuinely unlocks a thing that no class alone grants —
scribing scrolls at 7th, reading languages at 4th — `exp_level GATES` is correct.
The test: *does the class alone permit this at any level?* If yes, the class enables
and the level improves. Edges failing this test are marked `review_flag=class_level_conflation`.

A change to a mechanic affects `inflicts` and `governs` edges structurally,
`improves` edges by making a bonus meaningless or overpowered, and `negates` edges
not at all. Those are three different impact reports.

---

## 7. Evidence classes

Replaces the earlier `explicit` boolean. Categorical and checkable — no invented decimals.

| Class | Meaning |
|---|---|
| `explicit_rule` | the text states the relationship directly |
| `explicit_reference` | the text points at the other rule by name |
| `inferred_rule` | the relationship must hold given two explicit rules |
| `analytic_classification` | our categorization, not the book's |
| `speculative` | plausible, flagged for review |

**Do not assign numeric confidence.** A made-up 0.87 is less honest than a category
a reviewer can check against the page. If you cannot name which class applies,
the edge is not ready.

### 7.1 Inherited general rules

Some rules are stated once and silently assumed everywhere after. Record these with
`pass=general-rule`, cited to **where the general rule appears**, not to the entry
relying on it.

Each accepted general rule carries an **ID**, registered in `general_rules.json`.

**Two kinds of edge relate to a general rule, and only one carries the ID.**

| Relationship | `pass` | `general_rule_id` | Meaning |
|---|---|---|---|
| **Derived under** the rule | `general-rule` | set | The entry never restates the rule; the edge exists by inheritance |
| **Establishes** the rule | any | **empty** | The text states it outright; this is the evidence the rule generalises *from* |

*Polymorph self* saying "no system shock check is required" **establishes**
`GR_SELF_FORM_CHANGE_NO_SHOCK`. It is an `explicit_rule` edge and carries no
`general_rule_id`. The wand of polymorphing, which says nothing about shock,
**derives under** `GR_IMPOSED_FORM_CHANGE_SYSTEM_SHOCK` and does carry it.

The register records both sides, plus the counter-example that bounds the rule:

```json
"GR_SELF_FORM_CHANGE_NO_SHOCK": {
  "rule": "A self-initiated or innate form change does not force System Shock.",
  "established_by": ["PHB POLYMORPH SELF", "PHB SHAPE CHANGE"],
  "counter_example_tested": "polymorph other — does invoke; confirms the boundary",
  "applies_to": ["spell_polymorph_self", "spell_shape_change", "rule_lycanthropy"]
}
```

This lets all inherited edges be audited together, and lets a single overgeneralised
rule be repaired centrally rather than edge by edge.

| ID | General rule | Cited at | Applies to |
|---|---|---|---|
| `GR_IMPOSED_FORM_CHANGE_SYSTEM_SHOCK` | A form change **imposed on another** forces System Shock | PHB p.12; *polymorph other* | polymorph other/any object, wand of polymorphing, petrification, flesh to stone, magical aging |
| `GR_SELF_FORM_CHANGE_NO_SHOCK` | **Self-initiated or innate** form change does **not** | *polymorph self*; *shape change* | polymorph self, shape change, druidic shapechange, lycanthropy |
| `GR_HELPLESS_TARGET_AUTOHIT` | Paralyzed/held/immobile targets are struck automatically, take maximum damage, gain no Dexterity benefit | DMG p.70 | every paralysis or hold effect |

**Caution.** Inherited rules are the easiest place to over-generalize. The polymorph
rule above was first recorded as "any form change triggers System Shock," which is
wrong — the books state the opposite for two spells. Before adding a row here,
confirm against at least one entry that **declines** to invoke the rule. If no
counter-example exists in the text, mark the row provisional.

---

## 8. Core vs optional

`status` is `core` or `optional`.

**Unearthed Arcana is optional in its entirety.** Within the core books, flag as
optional: psionics, weapon-vs-armor-class adjustments, secondary skills, the bard,
gambling, artifacts, genre conversions, and anything the text marks a DM option.

Filtering `status == core` yields a rules-as-written 1979 game. This is not
cosmetic — excluding optional material changes which *version* of a rule is active,
because UA supersedes the DMG's grappling and subdual systems wholesale.

---

## 9. Publication order

MM (1977) → PHB (1978) → DMG (1979) → UA (1985).

The MM references a rules system that did not yet exist. Where an MM entry says
"save vs. poison" or "drains a level," it is inventing the subsystem inline; the DMG
later formalized it, sometimes differently. Those divergences are analytically
valuable. Record them as `OVERRIDES` with `supersession_basis` identifying why the
later rule supersedes:

| Value | Meaning |
|---|---|
| `later_publication` | a later book restates the mechanic differently |
| `explicit_replacement` | the text says it replaces the earlier rule |
| `conflicting_procedure` | two procedures cannot both run; precedence needed |
| `optional_variant` | an alternative offered alongside, not instead of |

Do not place prose in `aspect` or `condition`. There is no free-text note field.

---

## 10. What severity is, and is not

Severity is **not** an edge property and must not be stored as one.

The importance of `wpn_speed_factor → cbt_initiative` is zero if the table doesn't
use weapon speed and high if it does. Severity is a function of the **query and the
active ruleset**, not of the edge.

**Policy:** severity is computed at query time from the active ruleset profile by a
**versioned impact-analysis algorithm**. The algorithm may consider reachable
mechanical paths, edge type, polarity, optionality, articulation effects, and known
graph completeness. It **must not** treat all edge types or all paths as equally
consequential — `CROSS_REFERENCES` contributes a path without a mechanical
dependency, and a single hard `GATES` may outweigh a dozen weak `MODIFIES`.

The constitution fixes the *policy*, not the formula. The formula lives in the build
profile and is versioned there, because topology is not identical to impact: a
high-degree generic node can dominate results, and a low-degree leaf mechanic can be
critical.

Storing hand-assigned severity invites thousands of subjective judgments that will
drift between conversations and cannot be validated.

---

## 11. Roles — the semantic layer

Semantics attach to **nodes as roles**, not to edges as assertions. A role says what
function a node serves. `money_gp` is a *resource*, an *advancement_currency*, and a
*logistical_burden* — three roles on one node, not three new edge types.

Roles are admitted in three tiers. **The tier a role belongs to is the Architect's
decision and is the mechanism that prevents sprawl.**

### Tier 1 — structural roles

Derived from edge topology on every build. No worker touches them. Objective, free,
cannot drift.

| Role | Derivation |
|---|---|
| `resource` | ≥2 inbound CONSUMES |
| `consumer` | ≥2 outbound CONSUMES |
| `sink` | ≥3 inbound CONSUMES, none outbound |
| `gatekeeper` | ≥4 outbound GATES |
| `gated_privilege` | ≥3 inbound GATES |
| `tuning_point` | ≥5 inbound MODIFIES |
| `modifier_source` | ≥5 outbound MODIFIES |
| `trigger_source` / `triggered_procedure` | ≥4 outbound / inbound TRIGGERS |
| `resolution_machinery` | any RESOLVED_BY |
| `aggregator` | ≥4 inbound FEEDS_INTO |
| `override_source` | ≥3 outbound OVERRIDES |
| `boundary_marker` | ≥3 EXCLUDES / EXCLUDED_FROM |
| `index` | ≥20 outbound, ≤4 inbound |
| `accumulator` | ≥20 inbound, ≤6 outbound |

248 of 1,091 nodes currently qualify for at least one.

### Tier 2 — functional roles with a derivation rule

Semantic in meaning, mechanical in derivation, therefore checkable.

| Role | Derivation rule |
|---|---|
| `advancement_currency` | has outbound `FEEDS_INTO` to a node with prefix `xp_` |
| `logistical_burden` | has outbound `FEEDS_INTO` to `enc_encumbrance` |
| `wealth_sink` | has **outbound** `CONSUMES` targeting `money_gp` |
| `time_sink` | has **outbound** `CONSUMES` targeting `rule_time` |
| `attrition_pressure` | has outbound `MODIFIES` to `rule_hit_points` with polarity `worsens` |

Direction matters and was wrong in v1.0. `CONSUMES` runs **consumer → resource**,
so a wealth sink points *at* `money_gp`, not away from it.

### Tier 3 — asserted roles

Everything else. Requires Architect approval and must clear the **promotion rule**:

> A candidate role is adopted only if it recurs across **at least five nodes** and
> **two domains**, and offers a useful boundary for analysis.

**Governing test: if a proposed role cannot be written as an edge pattern, it is
tier 3 and probably should not exist.** This is the brake. It is structural, not a
judgement call per case.

### What is still excluded

Free-form semantic edges. `Fireball COUNTERS Troll` is derivable from
`monster_troll EXCLUDED_FROM monster_regeneration` conditioned on fire — record the
mechanic, derive the counter. `Holy Water THEMATICALLY_RELATED Undead` is unbounded
and unfalsifiable; it does not enter the graph.

---

## 12. Worked examples

**Correct.** Every example carries exactly the production column count. Empty
fields are explicit, never omitted.

Column order:
```
source_id,source_label,edge_type,target_id,target_label,aspect,condition,
polarity,polarity_basis,book,page,section,evidence,pass,status,
supersession_basis,general_rule_id,review_flag
```

**18 columns. Every example below carries exactly 18.** The production file
`edges_master.csv` is authoritative for column order; any example that disagrees is
a defect in this document.

Authored polarity on a `TRIGGERS` edge, read from the page:
```csv
spell_polymorph_other,Polymorph Other,TRIGGERS,rule_system_shock,System Shock Survival,recipient must survive the change,,inflicts,read,PHB,,POLYMORPH OTHER,explicit_rule,spell-scan,core,,,
```

Authored polarity on a `MODIFIES` edge:
```csv
race_dwarf,Dwarf,MODIFIES,save_poison,Saving Throw vs Poison,save bonus by constitution,,improves,read,PHB,11,DWARVES,explicit_rule,page-sweep,core,,,
```

Derived polarity — the worker leaves polarity blank and the build fills it:
```csv
class_cleric,Cleric,GATES,rule_turn_undead,Turning Undead,class prerequisite,,enables,derived,PHB,,CLERICS,explicit_rule,page-sweep,core,,,
```

An `OVERRIDES` edge requires `supersession_basis`:
```csv
cbt_pummel_grapple,Grappling,OVERRIDES,cbt_pummel_grapple,DMG Grappling Rules,UA supersedes the earlier system,,neutral,derived,UA,108,APPENDIX Q: WEAPONLESS COMBAT,explicit_rule,page-sweep,optional,later_publication,,
```

An edge created under an inherited general rule requires `general_rule_id`:
```csv
item_wand,Wand of Polymorphing,TRIGGERS,rule_system_shock,System Shock Survival,polymorph forces the survival roll,,inflicts,read,DMG,136,"TREASURE (RODS, STAVES & WANDS)",explicit_rule,general-rule,core,,GR_IMPOSED_FORM_CHANGE_SYSTEM_SHOCK,
```

**Incorrect**

```
strength, Strength, RELATED_TO, combat, Combat, gives +3 to hit, ...
```
Four errors: unprefixed ID, illegal edge type, vague target, magnitude in aspect.

```
spell_fireball, Fireball, COUNTERS, monster_troll, Troll, ...
```
Semantic assertion presented as mechanical, and `COUNTERS` is not in the vocabulary.
A troll is **not** excluded from regeneration — it regenerates normally; fire
suspends it. Correct form names the suspending mechanic:

```
rule_fire_damage, Fire Damage, EXCLUDES, monster_regeneration, Regeneration,
suspends regeneration, while burning, negates, read, MM, 96, TROLL, explicit_rule, ...
```

The "fireball counters troll" conclusion is then *derivable* rather than asserted.

---

## 13. Known defects

Carried forward honestly so downstream conversations do not trust the graph further
than it deserves.

- **MM layer is keyword-derived, not read.** 218 edges from a mechanic scan. Some
  are miscategorized (a monster flagged for poison may resist rather than inflict).
- **28 of 294 MM stat blocks are column-collapsed** in the doctags source; grouped
  entries (bears, dragons, demons) lost their column separation.
- **297 degree-1 nodes.** Mostly leaf concepts named once, but this is where missed
  edges hide.
- **63 deduced edges** are interpretive, flagged in `evidence`.
- **DMG back-matter unswept** — sample dungeon narration, monster stat listings,
  glossary. List content; low expected yield but not verified empty.

---

## 13a. Ruleset profiles

`status` records **publication status**, not runtime activation. Two edges may both
be valid history while being mutually incompatible in one active game — DMG grappling
and UA grappling are the clearest case.

Activation lives in a separate profile, never duplicated onto edges:

```yaml
ruleset_profile: jeff_campaign
base: ADD_1979
enabled_supplements: [UA]
enabled_options: [weapon_speed]
replacements: [ua_grappling]      # resolves OVERRIDES conflicts
house_rules: [shield_vs_magic_missile]
```

The query engine selects edges using `status`, `book`, `supersession_basis`, and the
profile. The graph stores classification; the profile stores choice.

## 13b. Versioned build profiles

Numeric thresholds are **graph-policy settings, not constitutional truths**. A node
can become an `index` merely because one book was processed more completely than
another. Thresholds live in `rulesets/adnd1e/profiles/roles.yaml`, versioned:

```yaml
role_derivation_profile: roles-v1
thresholds:
  tuning_point:   {inbound_MODIFIES: 5}
  index:          {outbound_min: 20, inbound_max: 4}
  resolution_machinery: {inbound_RESOLVED_BY: 1}   # direction explicit
```

The constitution defines role **meaning and governance**. The profile defines current
numbers. Re-derivation on a changed profile is expected and cheap.

## 14. Workflow

```
ARCHITECT  — owns this file. Never extracts. Resolves ontology questions.
    ↓
ANALYST    — reads a bounded section. Emits candidate nodes/edges as a packet.
             Does not mutate the master graph.
    ↓
BUILDER    — normalizes packets against rulesets/adnd1e/registries/nodes.csv. Rejects duplicates,
             enforces direction, attaches evidence. Emits a patch.
    ↓
REVIEWER   — checks each edge against source. Approves or revises per field,
             not per edge wholesale.
    ↓
INTEGRATOR — applies approved patches, preserves provenance, rebuilds artifacts.
```

Artifacts are named:

```
Source Packet → ANALYST → GUR (Graph Update Recommendation)
             → BUILDER  → GUP (Graph Update Patch, schema-valid)
             → REVIEWER → Approved GUP
             → INTEGRATOR
```

A **GUR** may contain candidate nodes, unresolved identity, proposed polarity, and
open questions. A **GUP** must contain only canonical IDs, legal edge types,
normalised directions, and no unresolved duplicates. The Reviewer reviews a
deterministic patch, not free-form analysis.

### Role-specific inputs

| Role | Receives |
|---|---|
| **Architect** | constitution, domain registry, escalations, graph slice; source excerpts *only* when resolving a disputed interpretation |
| **Analyst** | constitution, source packet, domain registry, node-registry slice, local neighborhood |
| **Builder** | constitution, GUR, node registry, local neighborhood; citations for preservation, not re-analysis |
| **Reviewer** | constitution, normalised GUP, source packet, **every source cited by an `inferred_rule`**, local neighborhood, relevant general-rule records |
| **Integrator** | approved GUP, node registry, master graph, build scripts — **not** the original packet |

**No worker receives the whole graph.**

## 15. Domains

Domains organise work; they are not edge properties. The GUR carries:

```yaml
domains_touched: [combat, spellcasting]
candidate_domains: []
domain_boundary_questions: []
```

**Promotion rule:** a candidate domain is not adopted from one GUR. It must recur
across multiple packets, contain a coherent cluster of mechanics, and offer a useful
boundary for work assignment.
