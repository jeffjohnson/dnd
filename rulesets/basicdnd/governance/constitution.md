# Graph Constitution - Basic D&D Mechanical Relationship Graph

**Version 1.0.** This document is authoritative for `basicdnd`. It is an
independent ruleset constitution; no AD&D 1e registry, canonical row, node
identity, or artifact lineage is inherited by reference.

## 1. Purpose

Impact analysis: if rule X changes, what other mechanics require review? The
graph records relationships, directions, types, and conditions. It does not
store rulebook prose, values, magnitudes, dice, or tables transcribed as data.

The test for an edge is: if its source mechanic changed or disappeared, would
the target mechanic need review? If not, it is not an edge.

## 2. Grain

Capture a relationship, never its number. A stated input-to-mechanic dependency
is an edge even when the source expresses its outcome numerically. The value or
formula is omitted. A source's document layout, frontmatter, table formatting,
and page classification are intake metadata, not graph mechanics.

## 3. Node identity

### 3.1 Format

IDs are lowercase `snake_case` and use an approved prefix.

| Prefix | Kind | Example |
|---|---|---|
| `abil_` | ability score or derived ability mechanic | `abil_strength` |
| `class_` | character class | `class_fighter` |
| `race_` | explicitly separate race or subrace | `race_human` |
| `rule_` | named rule or procedure | `rule_alignment_language` |
| `tbl_` | table consulted as a unit | `tbl_attack_rolls` |
| `spell_` | spell or named spell family | `spell_sleep` |
| `item_` | magic item or item class | `item_wand` |
| `potion_` | potion | `potion_healing` |
| `sword_` | intelligent-sword mechanic | `sword_ego` |
| `monster_` | creature or creature family | `monster_dragon` |
| `cbt_` | combat mechanic | `cbt_attack_roll` |
| `save_` | saving throw category | `save_spells` |
| `psi_` | psionic mechanic | `psi_power` |
| `sys_` | whole subsystem | `sys_alignment` |
| `exp_` | experience mechanic | `exp_level` |
| `xp_` | experience award source | `xp_monsters` |
| `hench_` | retainer or hireling mechanic | `hench_retainer_morale` |
| `campaign_` | campaign-level system | `campaign_dominion` |
| `gen_` | generator or random-table system | `gen_wandering_monsters` |
| `ex_` | exploration mechanic | `ex_movement` |
| `enc_` | encumbrance mechanic | `enc_load` |
| `money_` | currency | `money_gp` |
| `prof_` | proficiency or skill | `prof_general_skill` |
| `wpn_` | weapon property or statistic | `wpn_range` |
| `weapon_` | mundane weapon or weapon family | `weapon_sword` |
| `thief_` | thief skill | `thief_open_locks` |

`class_dwarf`, `class_elf`, and `class_halfling` are Basic D&D character-class
identities. They are not `race_` identities. The `race_` prefix remains reserved
until a source establishes a distinct Basic D&D race axis. Same-looking IDs in
another ruleset are different identities by namespace.

### 3.2 Registry

`rulesets/basicdnd/registries/nodes.csv` is the approved node registry. Reuse
an existing Basic D&D ID when it expresses the same source-defined concept. Do
not search AD&D 1e canonical data as an identity authority.

## 4. Edge vocabulary

The only edge types are:

| Type | Meaning | Direction |
|---|---|---|
| `MODIFIES` | changes a value, chance, or rating | modifier to modified |
| `DERIVED_FROM` | computed or looked up from | derived to source |
| `GATES` | is a precondition for | gate to gated |
| `TRIGGERS` | causes a check or procedure | cause to effect |
| `ALTERNATIVE_TO` | mutually exclusive or substitutable | either direction |
| `CONSUMES` | expends a finite resource | consumer to resource |
| `CONSTRAINS` | bounds without changing a value | constrainer to constrained |
| `OVERRIDES` | supersedes or replaces | overrider to overridden |
| `FEEDS_INTO` | supplies an input | input to process |
| `RESOLVED_BY` | identifies a resolution procedure | thing to procedure |
| `CROSS_REFERENCES` | explicitly points elsewhere | source to target |
| `EXCLUDES` | actively prevents a relation | excluder to excluded |
| `EXCLUDED_FROM` | is not an input to a mechanic | excluded to mechanic |

No other edge type is permitted. `RELATED_TO` is never permitted.

## 5. Assertions

An edge records source and target ID and label, type, aspect, condition,
polarity and basis, book, page, section, evidence, pass, status,
supersession basis, general-rule ID, and review flag. The assertion key is
`source_id, edge_type, target_id, aspect, condition`; duplicate keys are not
separate graph rows. A citation records one printed page from the current packet
or a stable section locator where a page is unavailable.

## 6. Polarity

Polarity is authored only when `MODIFIES`, `TRIGGERS`, or `CONSTRAINS` needs it
to distinguish impact. Allowed values are `inflicts`, `improves`, `worsens`,
`negates`, `enables`, `governs`, `neutral`, and empty. The basis is `read`,
`derived`, `heuristic`, `unset`, or empty. Do not infer polarity merely from a
node label.

## 7. Evidence and general rules

Evidence is `explicit_rule`, `explicit_reference`, `inferred_rule`,
`analytic_classification`, or `speculative`. A general rule is added only after
its establishing locus, scope, counterexample boundary, and affected set are
explicitly recorded. It does not arise merely because a familiar AD&D rule
looks similar.

## 8. Core and optional source

Core source material carries `core`; optional variants carry `optional` and
their supersession basis. Basic D&D optionality is determined from Basic D&D
source authority, not an AD&D publication hierarchy.

## 9. Publication order

The ordinary lifecycle is source packet, GUR, GUP, Review, Approved bundle, and
Integration. Only the Integrator creates or changes Basic D&D canonical state.

## 10. Non-graph metadata

Steward frontmatter and `full-page-artwork` markers are informational intake
metadata under `contracts/SOURCE_MARKDOWN.md`. They create no nodes, edges,
domains, general rules, or coverage gaps when the classified page is inside its
claimed packet span.

## 11. Initial ontology decisions

Ability scores directly `MODIFY` or `GATE` each target mechanic the source
states. A unified printed adjustment table does not by itself become a node or
an aggregate adjustment mechanic. A separately addressable table node is used
only when source text makes the table itself a mechanical input.

THAC0 and attack-roll tables are alternate presentations of `cbt_attack_roll`
when the source states they encode the same information. The alternative is a
non-edge observation unless later source gives it independent mechanics.

A prime requisite can produce an ability `GATES` class assertion and a separate
ability `MODIFIES` experience-mechanic assertion when each relationship is
stated. Compound requirements remain conditions; do not mint synthetic
aggregate identities. `sys_alignment`, alignment-language rules, and retainer
mechanics are Basic D&D-local identities when source-supported. Dice notation
is a reading convention, not a node or general rule without a target-specific
dependency.

## 12. Roles and domains

Structural and derived roles are query-time conclusions, never asserted node
metadata. Domains require recurrence across source packets; a single packet may
propose but not promote one.

## 13. Source authority

The current incoming packet and then its immutable claimed copy govern page
attribution and source names under `contracts/SOURCE_MARKDOWN.md`. Legacy AD&D
material is neither a baseline nor a tie-breaker for Basic D&D.

## 14. Workflow

Architect resolves ontology, registry, and contract questions. Analyst reads
bounded source; Builder compiles deterministically; Reviewer verifies source
and constitution; Integrator alone mutates canonical data. Every role uses the
current Basic D&D packet and registry slice, not conversation history.

## 15. Initial state

This ruleset begins with an empty node registry, no canonical baseline, no
domains, no general rules, and no active character-race membership. The first
approved packet establishes graph data through the ordinary lifecycle.
