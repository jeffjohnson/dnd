# Graph Constitution - Shadowdark Mechanical Relationship Graph

**Version 1.8.** Authorities: DEC-2026-0083, DEC-2026-0087, DEC-2026-0089, DEC-2026-0093, DEC-2026-0098, DEC-2026-0100, DEC-2026-0103, DEC-2026-0104, DEC-2026-0105. Applies only to `shadowdark`.
This bootstrap defines representation, not facts about an unread source book.
No AD&D or Basic D&D identities, mechanics, Decisions, or graph rows are inherited.

## 1. Purpose and Grain

Record mechanical dependencies for impact analysis: if one mechanic changes,
which other mechanics need review? Capture a relationship, not its numeric
value, dice expression, formula, threshold, or copied rulebook prose.
Source layout and document metadata are not graph mechanics.

## 2. Node Identity

IDs use lowercase snake_case and one approved prefix. Preserve source-defined
names and grammatical number under `contracts/SOURCE_MARKDOWN.md`.
The examples below are format illustrations, not registered Shadowdark nodes.

| Prefix | Kind | Example |
|---|---|---|
| `abil_` | ability or derived ability mechanic | `abil_strength` |
| `ancestry_` | character ancestry | `ancestry_dwarf` |
| `alignment_` | individual chosen alignment | `alignment_lawful` |
| `class_` | character class | `class_fighter` |
| `deity_` | source-named individual deity | `deity_saint_terragnis` |
| `lang_` | source-named individual language | `lang_dwarvish` |
| `rule_` | named rule or procedure | `rule_example` |
| `tbl_` | separately referenced mechanical table | `tbl_example` |
| `spell_` | spell or source-named spell family | `spell_example` |
| `item_` | item or item category | `item_example` |
| `monster_` | creature or creature family | `monster_example` |
| `mstat_` | shared creature statistic or rating used by a mechanic | `mstat_monster_level` |
| `cbt_` | combat mechanic | `cbt_attack_roll` |
| `sys_` | whole subsystem | `sys_example` |
| `exp_` | character advancement mechanic | `exp_level` |
| `ex_` | exploration mechanic | `ex_movement` |
| `weapon_` | weapon identity or weapon family | `weapon_example` |

`rulesets/shadowdark/registries/nodes.csv` is the only node registry for this
graph. Matching IDs in other rulesets are unrelated identities. Normal new
nodes under these prefixes follow GUR/GUP/Review, not individual Architect
approval. A new prefix or changed kind requires an evidence-bearing escalation.
Ancestry, class and creature identity are distinct. The character-race registry
remains inactive; its empty membership set is not a gate on ancestry proposals.

### 2.5 Creature Statistic Boundary

`mstat_` names a shared creature statistic or rating only when a source-backed
mechanical dependency uses that statistic across creatures. It is not a
creature identity, a stat-block field instance, or a container for a creature's
printed numeric value. `mstat_monster_level` is the ordinary source-backed
proposal for the printed `LV` statistic: it may participate in the explicit
relationship that monster level feeds hit-point calculation, but no row stores
how many levels a particular creature has.

Individual creature stat-block values, including AC, HP, LV, attacks, movement,
modifiers, alignment, DC, and tier, are not graph content merely because they
are printed for that creature. The graph may retain an explicit dependency
between shared mechanics when the source states one; it reuses an existing
identity where one fits, and uses `mstat_` only for an otherwise-unrepresented
shared creature statistic or rating. A stat-block description or an individual
value never creates an identity, edge, property store, or completeness
obligation. Ordinary source-backed GUR/GUP/Review workflow governs each
`mstat_` proposal; a use outside this boundary requires an Architect Decision.

### 2.1 Source-Defined Ancestries and Benefits

DEC-2026-0087 authorizes `ancestry_` for playable ancestry options. The defining
packet `PKT-SD-016-017-ancestries` establishes these identities and separately
named ability mechanics:

| Ancestry ID | Source label | Named benefit ID | Benefit label |
|---|---|---|---|
| `ancestry_dwarf` | Dwarf | `abil_stout` | Stout |
| `ancestry_elf` | Elf | `abil_farsight` | Farsight |
| `ancestry_goblin` | Goblin | `abil_keen_senses` | Keen Senses |
| `ancestry_half_orc` | Half-Orc | `abil_mighty` | Mighty |
| `ancestry_halfling` | Halfling | `abil_stealthy` | Stealthy |
| `ancestry_human` | Human | `abil_ambitious` | Ambitious |

The ancestry machine kind is `ancestry`. The hyphen in Half-Orc becomes an
underscore in its ID, not a deleted separator or a hyphenated ID. These are
authorized ordinary node proposals, not registered nodes or approved edges.
Further source-defined ancestries use the same kind through normal workflow.

`sys_ancestry` identifies the subsystem, not an individual member. `class_`
identifies classes; `monster_` identifies separately source-defined creatures.
A shared label does not merge an ancestry with a creature. No human/demihuman
classification, race membership registry, automatic inheritance or other
ruleset's identities are imported.

Independently named mechanical benefits use the existing `abil_` kind. Preserve
their source-defined names and model their actual dependencies, not numeric
properties or copied rule prose on an ancestry. Existing `GATES` may express
ancestry eligibility for its benefit without asserting global exclusivity.
Do not duplicate a benefit's effects directly on the ancestry solely to create
a transitive shortcut. No new edge type or inherited general rule is created;
source extraction, conditions, polarity and individual rows still need Review.

### 2.2 Source-Defined Alignments And Deities

DEC-2026-0093 authorizes `alignment_` for individual chosen alignments and
`deity_` for source-named individual deities. `sys_alignment` and `sys_deity`
remain the axis or subsystem identities; neither merges with an individual.
These are ordinary node proposals, not registered nodes or approved edges.

| Alignment ID | Source label |
|---|---|
| `alignment_chaotic` | Chaotic |
| `alignment_lawful` | Lawful |
| `alignment_neutral` | Neutral |

| Deity ID | Source label |
|---|---|
| `deity_saint_terragnis` | Saint Terragnis |
| `deity_gede` | Gede |
| `deity_madeera_the_covenant` | Madeera the Covenant |
| `deity_ord` | Ord |
| `deity_memnon` | Memnon |
| `deity_ramlaat` | Ramlaat |
| `deity_shune_the_vile` | Shune the Vile |

The Four Lords, The Dark Trio, The Nine, and The Lost are source context, not
graph identities or membership evidence. The Lost identifies two unnamed
deities with an unknown alignment; do not create `deity_the_lost`, anonymous
deity nodes, or an unknown-alignment node. A later source that names an
individual follows ordinary `deity_` proposal and Review workflow. This section
creates no grouping kind, membership edge, hierarchy, general rule, or inferred
relationship; Analyst extracts only explicit packet relationships using the
existing edge vocabulary.

### 2.3 Source-Defined Languages

DEC-2026-0098 authorizes `lang_` for individually source-named languages.
`sys_language` remains the aggregate language axis; it neither merges with nor
replaces an individual language. These are ordinary node proposals, not
registered nodes or approved edges.

| Language ID | Source label | Source table |
|---|---|---|
| `lang_common` | Common | Common Languages |
| `lang_dwarvish` | Dwarvish | Common Languages |
| `lang_elvish` | Elvish | Common Languages |
| `lang_giant` | Giant | Common Languages |
| `lang_goblin` | Goblin | Common Languages |
| `lang_merran` | Merran | Common Languages |
| `lang_orcish` | Orcish | Common Languages |
| `lang_reptilian` | Reptilian | Common Languages |
| `lang_sylvan` | Sylvan | Common Languages |
| `lang_thanian` | Thanian | Common Languages |
| `lang_celestial` | Celestial | Rare Languages |
| `lang_diabolic` | Diabolic | Rare Languages |
| `lang_draconic` | Draconic | Rare Languages |
| `lang_primordial` | Primordial | Rare Languages |

When an explicit source relationship needs a table, ordinary `tbl_` proposals
may use `tbl_common_languages` and `tbl_rare_languages`. Table headings are
source context, not a stored language property, automatic table-membership
edge, general rule, or inferred relationship. Do not use the table layout to
invent a membership vocabulary or a language hierarchy. This amendment does
not automatically authorize another kind for named members of another
subsystem; each new kind still needs a defining-locus Architect Decision.

### 2.4 Mechanically Operative Classifications

`CLASSIFIED_AS` records a source-declared classification only when the exact
classification is a direct input to a named Shadowdark mechanic. It is not a
general taxonomy, hierarchy, parent relation, table-membership relation, or
substitute for a shared prefix. An individual points to its classification.
The classification target must be an existing or ordinarily proposed identity,
not a `sys_` axis or an invented grouping identity.

DEC-2026-0103 initially authorizes only these source-backed spell
classifications:

| Individual | Classification target | Aspect | Cardinality |
|---|---|---|---|
| `spell_` | `class_wizard` or `class_priest` | casting class | one or more |
| `spell_` | `rule_spell_tier_1` through `rule_spell_tier_5` | spell tier | exactly one |
| `rule_spell_tier_1` through `rule_spell_tier_5` | `rule_spell_tier` | spell tier category | exactly one |
| `item_` | `rule_light_source` | light source | at most one |

`rule_spell_tier_1` through `rule_spell_tier_5` are ordinary `rule_` proposals
with source labels Tier 1 through Tier 5. The tier-value-to-aggregate rows make
the existing spell-tier rule's downstream mechanical effects reachable without
storing a numeric value in an edge field. A spell's casting class and tier are
both classifications, but they are not the same fact: class may be plural;
tier is one of five ordered source categories.

DEC-2026-0104 additionally authorizes only source-explicit item Light Source
classification. A source locus must explicitly identify the individual item as
a light source; the presence of Light Source mechanics or an item's nearby
mention does not establish that membership. This is not a generic item
hierarchy, provider relation, property store, or a classification form for
another `rule_` target. An item need not be classified merely because it exists
in the registry, and one item may have at most one `light source` row.

Ancestry, alignment, deity, language, table, creature-family, and other
taxonomy-only membership remains outside the graph unless a later
evidence-bearing Architect Decision establishes a source-defined classification
as a direct mechanical input. Sections 2.1 through 2.3 remain in force: no
`CLASSIFIED_AS` edge points to `sys_ancestry`, `sys_alignment`, `sys_deity`,
`sys_language`, `sys_class`, Common Languages, Rare Languages, The Four Lords,
The Dark Trio, The Nine, The Lost, or another source-context grouping.

## 3. Closed Edge Vocabulary

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
| `EXCLUDED_FROM` | is not an input to a mechanic | excluded to excluder |
| `CLASSIFIED_AS` | source-declared mechanically operative classification | individual to classification |

No other edge type is legal; do not use RELATED_TO.

## 4. Production Columns and Assertion Identity

The CSV columns, in order, are:

```text
source_id,source_label,edge_type,target_id,target_label,aspect,condition,polarity,polarity_basis,book,page,section,evidence,pass,status,supersession_basis,general_rule_id,review_flag
```

The assertion key is `source_id, edge_type, target_id, aspect, condition`.
Only ALTERNATIVE_TO is symmetric: sort its endpoint IDs before comparing keys.
Labels, citations, evidence, and provenance do not create separate assertions.
An aspect has one to four words and no copied rule prose or numeric magnitude.
Conditions express applicability without encoding numeric rule data.

## 5. Polarity and Evidence

Builder derives polarity for the following types; workers do not author it:

| Edge type | Derived polarity |
|---|---|
| GATES | enables |
| RESOLVED_BY | governs |
| EXCLUDES | negates |
| EXCLUDED_FROM | negates |
| DERIVED_FROM | neutral |
| ALTERNATIVE_TO | neutral |
| OVERRIDES | neutral |
| FEEDS_INTO | neutral |
| CROSS_REFERENCES | neutral |
| CONSUMES | neutral |
| CLASSIFIED_AS | neutral |

MODIFIES, TRIGGERS, and CONSTRAINS require source-reviewed authored polarity.
The vocabulary is inflicts, improves, worsens, negates, enables, governs,
neutral, or empty. Bases are derived, read, heuristic, unset, or empty.
Approved authored polarity requires basis read; heuristic and unset block
approval. Deterministic polarity uses basis derived.

Evidence classes are explicit_rule, explicit_reference, inferred_rule,
analytic_classification, and speculative. Speculation is not production proof.
General rules require a separate Architect ruling with an establishing locus,
scope, counterexamples, and affected set. Their establishing edges leave
general_rule_id empty; derived applications cite the approved rule ID.

## 6. Citations and Source Authority

Register each book and exact source before claiming its first packet. A book's
citation code must be present in this ruleset's book registry. A citation names
one page, or a stable section when no page exists. The current incoming packet,
then its immutable claimed copy, governs source spelling and page attribution.

Packets are Pandoc Markdown; use Pandoc-supported parsers. For `{#pNNN}`:
at line end the entire preceding block starts on NNN; in the final table cell
the entire row starts on NNN; inside prose only following text switches to NNN.
Apply the complete SOURCE_MARKDOWN contract, including its ambiguity handling.
Frontmatter and page-layout annotations remain informational, not graph nodes.
Other systems' books and legacy graphs cannot resolve Shadowdark ambiguity.

## 7. Status, Optionality, and Provenance

Edge status is core or optional, established from registered Shadowdark source
authority, never from another game's publication hierarchy. OVERRIDES alone
requires supersession_basis: later_publication, explicit_replacement,
conflicting_procedure, or optional_variant. Other edges leave it empty.
SD is the steward-designated main rules work. Supplement source authority,
optionality, and compatibility must be established from supplied source; do not
infer that a supplement overrides the main rules merely from its title or date.
Every integrated row retains packet, GUR, GUP, Review, and integration lineage.

## 8. Roles, Domains, and Workflow

Follow the universal contracts and the five role instructions. Structural roles
and severity are query-time conclusions, not stored assertions. Tier 3 roles
and domain promotions require Architect Decisions; a lone occurrence does not
promote a domain. Source-supported dependencies, not resemblance to familiar
games, determine edges.

The lifecycle is packet, GUR, GUP, Review, Approved bundle, Integration.
Only Integrator creates or edits canonical graph files. The first integration
requires independently verified new-ruleset initialization support; do not
fabricate a header-only canonical baseline to bypass that gate.
Independent repository roles may work concurrently. Artifact ownership,
active-leaf verification, and normal publication lifecycle remain mandatory.

## 9. Initial State and Change Control

Six steward-named books and their separate steward-intake sources are registered
at bootstrap. Editions/printings remain explicitly unspecified. Nodes, general
rules, domains, and ancestry/race memberships are empty. There are no canonical
data files and no packet identities before actual intake.
Future source-backed amendments receive a version and durable Decision. This
constitution does not import system-specific rulings from another ruleset.

Historical Shadowdark GURs declaring a version listed in
`rulesets/shadowdark/ruleset.yaml` under
`historical_gur_constitution_versions` remain admissible only with full
revalidation under the current Constitution. That list is 1.0 through 1.7 at
this amendment. New GURs and GUPs declare the current version (1.8 at this
amendment); historical acceptance does not authorize new output at an earlier
version. Unknown or future versions fail.
Do not rewrite immutable GURs or packet manifests merely for this additive bump.
Ancestry GUP publication requires the independent implementation approval named
in DEC-2026-0087; no canonical initialization or registration is authorized here.

## Version History

- **1.8 - 2026-09-30:** DEC-2026-0105 added `mstat_` for shared
  creature-statistic mechanics and excluded individual creature stat-block
  values from graph content. `mstat_monster_level` may feed hit-point
  calculation; this is not a creature property store or generic stat-block
  taxonomy.

- **1.7 - 2026-09-25:** DEC-2026-0104 added the one bounded source-explicit
  `item_` to `rule_light_source` `CLASSIFIED_AS` form, with aspect `light
  source` and at-most-one cardinality. It does not create general item
  taxonomy or a property relation.
- **1.6 - 2026-09-24:** DEC-2026-0103 added the bounded `CLASSIFIED_AS`
  relation for source-declared mechanically operative spell class and tier
  classifications. Taxonomy-only membership remains outside the graph.
- **1.5 - 2026-09-23:** DEC-2026-0100 moved historical incoming-GUR version
  compatibility to governed ruleset metadata, preserving 1.0 through 1.4 under
  current-version revalidation and eliminating Shadowdark-specific Builder
  transcription.
- **1.4 - 2026-09-22:** DEC-2026-0098 added individual `lang_` identities,
  retained `sys_language` as the aggregate axis, and defined the Common/Rare
  language-table boundary without a language property or membership edge.

- **1.3 - 2026-09-22:** DEC-2026-0093 added individual `alignment_` and
  `deity_` identities, preserving subsystem axes and excluding source-named
  collective groupings and the unnamed Lost from graph identity.

- **1.2 - 2026-09-22:** DEC-2026-0089 removed serialized repository work;
  independent roles may work concurrently while artifact lifecycle controls
  remain mandatory.

- **1.1 - 2026-09-21:** DEC-2026-0087 added the source-defined ancestry kind,
  six ancestry IDs and separate named ability identities, retaining historical
  1.0 GUR revalidation and independent graph initialization gates.
- **1.0 - 2026-09-19:** DEC-2026-0083 established the independent bootstrap.
