# Deduplication Pass - PHB proposed edges against the canonical graph

**Date:** 2026-07-29  
**Produced by:** Analyst  
**Scope:** the latest revision of every PHB GUR, compared against `rulesets/adnd1e/canonical/edges_master.csv` (3809 edges).

This report mutates nothing. It exists because no packet was ever supplied with a
`local_neighborhood.json`, so no Analyst could perform this check at extraction time
(BLK-02). It is that check, run once, after the fact.

## Method

Every proposed edge was compared against canonical on three tests, in order:

1. **Exact duplicate** - the same `(source, edge_type, target)` triple already exists.
   Invariant 12 forbids duplicate edge identity, so both cannot be integrated.
2. **Type conflict** - same source and target, same direction, *different* edge type.
   Not forbidden, but two types between one ordered pair usually means one reading is wrong.
3. **Direction conflict** - the same pair exists with source and target reversed.
   Constitution section 4 fixes direction per edge type, so a reversal is a substantive
   disagreement about which mechanic depends on which.

## Summary

| Result | Count |
|---|---|
| Proposed edges across all PHB GURs | 389 |
| **Exact duplicates** of a canonical triple | **115** |
| **Type conflicts** | **35** |
| **Direction conflicts** | **20** |
| No canonical counterpart found | 219 |

| GUR | exact | type | direction |
|---|---|---|---|
| `GUR-PKT-PHB-007-008-intro-r02` | 0 | 1 | 1 |
| `GUR-PKT-PHB-009-013-ability-scores-r01` | 48 | 3 | 6 |
| `GUR-PKT-PHB-013-018-races-r03` | 27 | 10 | 8 |
| `GUR-PKT-PHB-018-033-classes-r02` | 21 | 13 | 3 |
| `GUR-PKT-PHB-033-035-alignment-hp-languages-r01` | 3 | 1 | 0 |
| `GUR-PKT-PHB-035-038-money-equipment-r02` | 10 | 4 | 2 |
| `GUR-PKT-PHB-039-040-hirelings-time-distance-r01` | 4 | 3 | 0 |
| `GUR-PKT-PHB-040-042-spells-intro-r01` | 2 | 0 | 0 |

## 3. Direction conflicts - highest priority

A reversed pair means the Analyst and the legacy import disagree about which way the
dependency runs. One of them is wrong. Resolve these before anything else.

### `E1` in `GUR-PKT-PHB-007-008-intro-r02`

- **Proposed:** `rule_languages` **DERIVED_FROM** `race_any` - aspect='known languages' [PHB p8]
- **Canonical (reversed):** `race_any` **CONSTRAINS** `rule_languages` - aspect='racial limits' [PHB p10]
- **Canonical (reversed):** `race_any` **FEEDS_INTO** `rule_languages` - aspect='tongues known by race' [DMG p102]

### `G1` in `GUR-PKT-PHB-009-013-ability-scores-r01`

- **Proposed:** `sys_ability_scores` **DERIVED_FROM** `rule_ability_generation` - aspect='score determination' [PHB p9]
- **Canonical (reversed):** `rule_ability_generation` **FEEDS_INTO** `sys_ability_scores` - aspect='initial scores' [DMG p11]

### `I13` in `GUR-PKT-PHB-009-013-ability-scores-r01`

- **Proposed:** `rule_spell_book` **FEEDS_INTO** `rule_chance_know_spell` - aspect='spell acquisition' cond='from acquired books or scrolls' [PHB p10]
- **Canonical (reversed):** `rule_chance_know_spell` **GATES** `rule_spell_book` - aspect='which spells may be recorded' [DMG p39]

### `D1` in `GUR-PKT-PHB-009-013-ability-scores-r01`

- **Proposed:** `dex_reaction_adj` **DERIVED_FROM** `abil_dexterity` - aspect='adjustment value' [PHB p11]
- **Canonical (reversed):** `abil_dexterity` **MODIFIES** `dex_reaction_adj` - aspect='tabulated adjustment' [PHB p11]

### `D2` in `GUR-PKT-PHB-009-013-ability-scores-r01`

- **Proposed:** `dex_defensive_adj` **DERIVED_FROM** `abil_dexterity` - aspect='adjustment value' [PHB p11]
- **Canonical (reversed):** `abil_dexterity` **MODIFIES** `dex_defensive_adj` - aspect='tabulated adjustment' [PHB p11]

### `H1` in `GUR-PKT-PHB-009-013-ability-scores-r01`

- **Proposed:** `abil_cha_max_henchmen` **DERIVED_FROM** `abil_charisma` - aspect='henchman ceiling' [PHB p13]
- **Canonical (reversed):** `abil_charisma` **MODIFIES** `abil_cha_max_henchmen` - aspect='tabulated adjustment' [PHB p13]

### `H2` in `GUR-PKT-PHB-009-013-ability-scores-r01`

- **Proposed:** `hench_loyalty` **DERIVED_FROM** `abil_charisma` - aspect='loyalty base' [PHB p13]
- **Canonical (reversed):** `abil_charisma` **MODIFIES** `hench_loyalty` - aspect='loyalty' [PHB p13]
- **Canonical (reversed):** `abil_charisma` **FEEDS_INTO** `hench_loyalty` - aspect='initial score' [DMG p36]

### `D3` in `GUR-PKT-PHB-013-018-races-r03`

- **Proposed:** `abil_strength` **GATES** `race_halfling` - aspect='racial minimum' [PHB p15]
- **Canonical (reversed):** `race_halfling` **MODIFIES** `abil_strength` - aspect='racial adjustment' [PHB p14]

### `D4` in `GUR-PKT-PHB-013-018-races-r03`

- **Proposed:** `abil_strength` **GATES** `race_half_orc` - aspect='racial minimum' [PHB p15]
- **Canonical (reversed):** `race_half_orc` **MODIFIES** `abil_strength` - aspect='racial adjustment' [PHB p14]

### `E6` in `GUR-PKT-PHB-013-018-races-r03`

- **Proposed:** `race_half_orc` **CONSTRAINS** `abil_intelligence` - aspect='maximum score' [PHB p15]
- **Canonical (reversed):** `abil_intelligence` **CONSTRAINS** `race_half_orc` - aspect='score ceiling' [PHB p10]

### `E7` in `GUR-PKT-PHB-013-018-races-r03`

- **Proposed:** `race_halfling` **CONSTRAINS** `abil_wisdom` - aspect='maximum score' [PHB p15]
- **Canonical (reversed):** `abil_wisdom` **CONSTRAINS** `race_halfling` - aspect='score ceiling' [PHB p11]

### `E8` in `GUR-PKT-PHB-013-018-races-r03`

- **Proposed:** `race_half_orc` **CONSTRAINS** `abil_wisdom` - aspect='maximum score' [PHB p15]
- **Canonical (reversed):** `abil_wisdom` **CONSTRAINS** `race_half_orc` - aspect='score ceiling' [PHB p11]

### `E13` in `GUR-PKT-PHB-013-018-races-r03`

- **Proposed:** `race_halfling` **CONSTRAINS** `abil_constitution` - aspect='maximum score' cond='ceiling raised above the human maximum' [PHB p15]
- **Canonical (reversed):** `abil_constitution` **GATES** `race_halfling` - aspect='eligibility' cond='minimum score' [PHB p12]

### `G1` in `GUR-PKT-PHB-013-018-races-r03`

- **Proposed:** `race_dwarf` **GATES** `rule_multiclass` - aspect='multi-class eligibility' [PHB p15]
- **Canonical (reversed):** `rule_multiclass` **EXCLUDED_FROM** `race_dwarf` - aspect='no other class permitted' [DMG p18]

### `G4` in `GUR-PKT-PHB-013-018-races-r03`

- **Proposed:** `race_half_elf` **GATES** `rule_multiclass` - aspect='multi-class eligibility' [PHB p17]
- **Canonical (reversed):** `rule_multiclass` **EXCLUDED_FROM** `race_half_elf` - aspect='no other class permitted' [DMG p18]

### `A11` in `GUR-PKT-PHB-018-033-classes-r02`

- **Proposed:** `class_druid` **CONSTRAINS** `exp_level` - aspect='class level limit' cond='hard class ceiling, and contested for the highest ranks' [PHB p19]
- **Canonical (reversed):** `exp_level` **GATES** `class_druid` - aspect='abdication opens the higher discipline' [UA p17]

### `C2` in `GUR-PKT-PHB-018-033-classes-r02`

- **Proposed:** `sys_alignment` **GATES** `class_druid` - aspect='alignment eligibility' [PHB p21]
- **Canonical (reversed):** `class_druid` **GATES** `sys_alignment` - aspect='fixed to true neutral' [PHB p33]

### `F43` in `GUR-PKT-PHB-018-033-classes-r02`

- **Proposed:** `class_assassin` **GATES** `rule_assassins_guild` - aspect='guild membership' [PHB p29]
- **Canonical (reversed):** `rule_assassins_guild` **CONSTRAINS** `class_assassin` - aspect='membership pressure' cond='within guild territory' [PHB p29]

### `B1` in `GUR-PKT-PHB-035-038-money-equipment-r02`

- **Proposed:** `rule_starting_money` **DERIVED_FROM** `sys_classes` - aspect='starting funds' [PHB p35]
- **Canonical (reversed):** `sys_classes` **MODIFIES** `rule_starting_money` - aspect='class explains the sum held' [DMG p25]

### `B10` in `GUR-PKT-PHB-035-038-money-equipment-r02`

- **Proposed:** `prof_weapon` **DERIVED_FROM** `sys_classes` - aspect='initial weapon count' [PHB p37]
- **Canonical (reversed):** `sys_classes` **MODIFIES** `prof_weapon` - aspect='initial number permitted' [PHB p37]


### Classification of the twenty direction conflicts

Raw, these look like twenty independent errors. They are not. They fall into four classes,
and three of the four have a single disposition each.

| Class | Count | Disposition |
|---|---|---|
| **A** - `DERIVED_FROM` proposed where canonical uses `MODIFIES` / `FEEDS_INTO` | 8 | Analyst yields; convention mismatch |
| **B** - different mechanic, not actually a conflict | 3 | Keep both |
| **C** - same mechanic, genuinely opposed direction | 7 | Reviewer decides case by case |
| **D** - direct contradiction between PHB and DMG | 2 | Favour PHB per standing direction |

**Class A (8).** `E1`, `G1`(abilities), `D1`, `D2`, `H1`, `H2`, `B1`, `B10`. In every case the
Analyst modelled a derived value as `DERIVED_FROM` its input, while canonical models the input
as `MODIFIES` the derived value. Same dependency, opposite arrow, different type. This is one
mistake made eight times, not eight mistakes: the Analyst applied a consistent reading that
differs from the graph's established convention. Canonical's convention is also the better fit
for constitution section 6, which treats an ability score as a `modifier_source` and gives
`abil_strength MODIFIES cbt_tohit` as its own worked example in section 2. **Recommendation:
the Analyst yields on all eight.** They should be dropped from the GUP as duplicates of the
canonical rows, not re-typed and re-proposed.

**Class B (3).** `D3`, `D4`, `E13`. Flagged by the pair test but not conflicts. `D3` and `D4`
propose that a strength *minimum* gates a race, while canonical records that the race *adjusts*
strength. Those are the Table III minimum and the Penalties and Bonuses table respectively, two
different mechanics that happen to join the same two nodes. `E13` is the same shape: a racial
*maximum* against an eligibility *minimum*. This is precisely the split recorded as a
deliberate grain decision in `GUR-PKT-PHB-013-018-races-r03`. **Recommendation: keep both
sides.** No action beyond confirming the aspects stay distinct.

**Class C (7).** `I13`, `E6`, `E7`, `E8`, `A11`, `C2`, `F43`. Genuine disagreements needing a
reading of both sources. The three race-versus-ability maximum rows (`E6`, `E7`, `E8`) are one
question asked three times: canonical cites the *ability* tables at PHB p10 and p11 and points
ability to race; the Analyst cites *Table III* at p15 and points race to ability. Both loci are
real and state the same fact. Settling the direction once settles all three. `C2` is worth
attention on its own: canonical has `class_druid GATES sys_alignment`, which reads as the class
determining the alignment, while the Analyst proposed the reverse. `A11` conflicts with a **UA**
row, not a DMG one, so the PHB-favouring direction does not obviously apply.

**Class D (2).** `G1` and `G4` of the races packet. Canonical holds
`rule_multiclass EXCLUDED_FROM race_dwarf` and `rule_multiclass EXCLUDED_FROM race_half_elf`,
both cited to **DMG p18**. The PHB states the opposite outright: p15 says a dwarf may work
simultaneously in the fighter and thief classes, and p17 lists eight multi-class combinations
open to half-elves. This is a flat contradiction, not a grain difference, and it is concrete
evidence that the operator's standing direction to favour the PHB is needed rather than
theoretical. **Recommendation: favour the PHB, and flag the two canonical rows for the DMG
re-analysis to re-derive from source.**

## 2. Type conflicts

Same ordered pair, different edge type. Usually one reading is wrong; occasionally both
hold and describe different facets, which constitution section 4.2 allows.

- `E5` **007-008-intro-r02** - proposed `rule_starting_money` **FEEDS_INTO** `sys_equipment` (aspect='purchasing power' cond='at character creation')
  - canonical has **GATES** - aspect='limits initial outfitting' [DMG p25]
- `S13` **009-013-ability-scores-r01** - proposed `str_exceptional` **DERIVED_FROM** `abil_strength` (aspect='percentile subdivision')
  - canonical has **GATES** - aspect='percentile rating' cond='fighter classes only' [PHB p9]
- `I4` **009-013-ability-scores-r01** - proposed `abil_intelligence` **MODIFIES** `rule_spells_per_level` (aspect='spells knowable')
  - canonical has **CONSTRAINS** - aspect='minimum and maximum' [PHB p10]
- `I12` **009-013-ability-scores-r01** - proposed `abil_intelligence` **TRIGGERS** `rule_chance_know_spell` (aspect='recheck of known spells' cond='on relatively permanent score change')
  - canonical has **MODIFIES** - aspect='learning chance' [PHB p10]
- `B5` **013-018-races-r03** - proposed `race_halfling` **CONSTRAINS** `exp_level` (aspect='maximum level' cond='varies by class')
  - canonical has **GATES** - aspect='halflings and humans may be zero level' [DMG p74]
- `E5` **013-018-races-r03** - proposed `race_halfling` **CONSTRAINS** `abil_strength` (aspect='maximum score' cond='both sexes, lower for females')
  - canonical has **MODIFIES** - aspect='racial adjustment' [PHB p14]
- `E10` **013-018-races-r03** - proposed `race_elf` **CONSTRAINS** `abil_dexterity` (aspect='maximum score' cond='ceiling raised above the human maximum')
  - canonical has **MODIFIES** - aspect='racial adjustment' [PHB p14]
- `E12` **013-018-races-r03** - proposed `race_dwarf` **CONSTRAINS** `abil_constitution` (aspect='maximum score' cond='ceiling raised above the human maximum')
  - canonical has **MODIFIES** - aspect='racial adjustment' [PHB p14]
- `E14` **013-018-races-r03** - proposed `race_half_orc` **CONSTRAINS** `abil_constitution` (aspect='maximum score' cond='ceiling raised above the human maximum')
  - canonical has **MODIFIES** - aspect='racial adjustment' [PHB p14]
- `E15` **013-018-races-r03** - proposed `race_dwarf` **CONSTRAINS** `abil_charisma` (aspect='maximum score' cond="outside the character's own race")
  - canonical has **MODIFIES** - aspect='racial adjustment' [PHB p14]
- `E16` **013-018-races-r03** - proposed `race_half_orc` **CONSTRAINS** `abil_charisma` (aspect='maximum score' cond="outside the character's own race")
  - canonical has **MODIFIES** - aspect='racial adjustment' [PHB p14]
- `F33` **013-018-races-r03** - proposed `race_subrace` **GATES** `race_infravision` (aspect='racial vision' cond='halfling blood determines range')
  - canonical has **MODIFIES** - aspect='ranges vary by subrace' [UA p10]
- `G9` **013-018-races-r03** - proposed `tbl_racial_preferences` **FEEDS_INTO** `cbt_encounter_reactions` (aspect='racial reaction' cond='by race pair')
  - canonical has **MODIFIES** - aspect='dealings with other races' [PHB p18]
- `G10` **013-018-races-r03** - proposed `tbl_racial_preferences` **FEEDS_INTO** `hench_hirelings` (aspect='acquisition by racial type')
  - canonical has **MODIFIES** - aspect='acquisition difficulty' cond='outside preferred races' [PHB p18]
- `B6` **018-033-classes-r02** - proposed `class_assassin` **CONSTRAINS** `sys_equipment` (aspect='armour and weapons permitted')
  - canonical has **GATES** - aspect='any shield and weapon' [PHB p28]
- `C1` **018-033-classes-r02** - proposed `sys_alignment` **GATES** `class_cleric` (aspect='alignment eligibility')
  - canonical has **CONSTRAINS** - aspect='permitted alignments' cond='true neutral excluded' [PHB p20]
- `F1` **018-033-classes-r02** - proposed `class_cleric` **GATES** `turn_undead` (aspect='undead turning')
  - canonical has **TRIGGERS** - aspect='turn or command' [PHB p20]
- `F9` **018-033-classes-r02** - proposed `class_paladin` **GATES** `rule_detect_evil` (aspect='evil detection' cond='when concentrating')
  - canonical has **TRIGGERS** - aspect='at will' cond='requires concentration' [PHB p23]
- `F11` **018-033-classes-r02** - proposed `class_paladin` **EXCLUDED_FROM** `rule_disease` (aspect='disease immunity')
  - canonical has **EXCLUDES** - aspect='immune to all forms' [PHB p23]
- `F12` **018-033-classes-r02** - proposed `class_paladin` **GATES** `rule_lay_on_hands` (aspect='wound healing' cond='once per day')
  - canonical has **TRIGGERS** - aspect='healing power' [PHB p23]
- `F13` **018-033-classes-r02** - proposed `class_paladin` **GATES** `turn_undead` (aspect='undead turning' cond='from third level')
  - canonical has **DERIVED_FROM** - aspect='turns at reduced effective level' [PHB p23]
- `F35` **018-033-classes-r02** - proposed `exp_level` **CONSTRAINS** `thief_pick_pockets` (aspect='success chance' cond='victim level')
  - canonical has **MODIFIES** - aspect='success chance' cond="victim's level modifies" [PHB p27]
- `F36` **018-033-classes-r02** - proposed `thief_move_silently` **MODIFIES** `cbt_surprise` (aspect='surprise chance')
  - canonical has **GATES** - aspect='improved chance to surprise' [PHB p102]
- `F52` **018-033-classes-r02** - proposed `abil_dexterity` **EXCLUDED_FROM** `cbt_armor_class` (aspect='defensive adjustment')
  - canonical has **MODIFIES** - aspect='defensive adjustment' [PHB p11]
- `F53` **018-033-classes-r02** - proposed `abil_strength` **EXCLUDED_FROM** `cbt_tohit` (aspect='attack adjustment')
  - canonical has **MODIFIES** - aspect='hit probability' [PHB p9]
- `F54` **018-033-classes-r02** - proposed `abil_strength` **EXCLUDED_FROM** `cbt_damage` (aspect='damage adjustment')
  - canonical has **MODIFIES** - aspect='damage dealt' [PHB p9]
- `F56` **018-033-classes-r02** - proposed `class_monk` **MODIFIES** `save_matrix` (aspect='saving throw')
  - canonical has **FEEDS_INTO** - aspect='uses thief table' [PHB p30]
  - canonical has **OVERRIDES** - aspect='no damage on success' [PHB p30]
- `A7` **033-035-alignment-hp-languages-r01** - proposed `sys_alignment` **CONSTRAINS** `rule_alignment_languages` (aspect='dialects speakable' cond='one only')
  - canonical has **GATES** - aspect='tongue known by alignment' [DMG p24]
- `B3` **035-038-money-equipment-r02** - proposed `enc_encumbrance` **CONSTRAINS** `sys_equipment` (aspect='carrying choice')
  - canonical has **DERIVED_FROM** - aspect='light average or heavy bands' [DMG p58]
- `B7` **035-038-money-equipment-r02** - proposed `rule_shield` **EXCLUDED_FROM** `cbt_armor_class` (aspect='shield bonus' cond='attacks from the right flank or rear')
  - canonical has **MODIFIES** - aspect='improves rating' [PHB p36]
  - canonical has **CONSTRAINS** - aspect='covers only the front and shield side' [DMG p28]
- `B9` **035-038-money-equipment-r02** - proposed `item_magic_armor` **EXCLUDED_FROM** `enc_encumbrance` (aspect='carried weight')
  - canonical has **MODIFIES** - aspect='weight halved' [DMG p28]
- `B19` **035-038-money-equipment-r02** - proposed `wpn_stats` **MODIFIES** `cbt_damage` (aspect='damage against larger opponents' cond='set weapons and charging mounts')
  - canonical has **FEEDS_INTO** - aspect='damage by weapon type' [PHB p37]
  - canonical has **EXCLUDES** - aspect='lighter javelins do full damage due to velocity' [UA p77]
- `C1` **039-040-hirelings-time-distance-r01** - proposed `abil_charisma` **EXCLUDED_FROM** `hench_hirelings` (aspect='number retainable')
  - canonical has **MODIFIES** - aspect='hiring success' [PHB p39]
- `C7` **039-040-hirelings-time-distance-r01** - proposed `hench_loyalty` **TRIGGERS** `hench_betrayal` (aspect='betrayal' cond='under combat or stress')
  - canonical has **GATES** - aspect='lowest band will kill or capture the liege' [DMG p36]
- `C12` **039-040-hirelings-time-distance-r01** - proposed `rule_movement_scale` **CONSTRAINS** `ex_movement_rate` (aspect='scale by setting')
  - canonical has **MODIFIES** - aspect='varies by situation' [PHB p39]

## 1. Exact duplicates

These triples already exist. Each needs a disposition: **reject** the proposal as
redundant, or **merge** it where the PHB citation or a sharper aspect adds something the
existing row lacks. The citation column is the deciding evidence: where canonical cites a
different book, the proposal is a second independent witness worth recording on the
existing edge rather than discarding.

| ref | GUR | proposed triple | canonical citation(s) | canonical aspect |
|---|---|---|---|---|
| `S1` | 009-013-ability-scores-r01 | `abil_strength` GATES `class_fighter` | PHB p22 | eligibility |
| `S2` | 009-013-ability-scores-r01 | `abil_strength` GATES `class_assassin` | PHB p28 | eligibility |
| `S3` | 009-013-ability-scores-r01 | `abil_strength` GATES `class_paladin` | PHB p22 | eligibility |
| `S5` | 009-013-ability-scores-r01 | `abil_strength` GATES `class_monk` | PHB p30 | eligibility |
| `S7` | 009-013-ability-scores-r01 | `abil_strength` MODIFIES `cbt_tohit` | PHB p9 | hit probability |
| `S8` | 009-013-ability-scores-r01 | `abil_strength` MODIFIES `cbt_damage` | PHB p9 | damage dealt |
| `S9` | 009-013-ability-scores-r01 | `abil_strength` MODIFIES `enc_weight_allowance` | PHB p9 | carrying capacity |
| `S10` | 009-013-ability-scores-r01 | `abil_strength` MODIFIES `str_open_doors` | PHB p9 | chances out of six |
| `S11` | 009-013-ability-scores-r01 | `abil_strength` MODIFIES `str_bend_bars` | PHB p9 | percentage chance |
| `I1` | 009-013-ability-scores-r01 | `abil_intelligence` MODIFIES `rule_languages` | PHB p10 | number known |
| `I2` | 009-013-ability-scores-r01 | `abil_intelligence` GATES `rule_spell_level_access` | PHB p10 | comprehension |
| `I3` | 009-013-ability-scores-r01 | `abil_intelligence` MODIFIES `rule_chance_know_spell` | PHB p10 | learning chance |
| `I5` | 009-013-ability-scores-r01 | `abil_intelligence` GATES `class_magic_user` | PHB p10 | eligibility |
| `I6` | 009-013-ability-scores-r01 | `abil_intelligence` GATES `class_paladin` | PHB p10 | eligibility |
| `I7` | 009-013-ability-scores-r01 | `abil_intelligence` GATES `class_assassin` | PHB p10 | eligibility |
| `I8` | 009-013-ability-scores-r01 | `abil_intelligence` GATES `class_ranger` | PHB p10 | eligibility |
| `I9` | 009-013-ability-scores-r01 | `abil_intelligence` GATES `class_illusionist` | PHB p10 | eligibility |
| `W1` | 009-013-ability-scores-r01 | `abil_wisdom` MODIFIES `save_magical_attack` | PHB p11 | die roll / tabulated adjustment |
| `W2` | 009-013-ability-scores-r01 | `abil_wisdom` GATES `class_cleric` | PHB p11, PHB p20 | eligibility |
| `W3` | 009-013-ability-scores-r01 | `abil_wisdom` GATES `class_druid` | PHB p11 | eligibility |
| `W4` | 009-013-ability-scores-r01 | `abil_wisdom` GATES `class_paladin` | PHB p11 | eligibility |
| `W5` | 009-013-ability-scores-r01 | `abil_wisdom` GATES `class_ranger` | PHB p11 | eligibility |
| `W6` | 009-013-ability-scores-r01 | `abil_wisdom` GATES `class_monk` | PHB p11 | eligibility |
| `W9` | 009-013-ability-scores-r01 | `abil_wisdom` MODIFIES `rule_cleric_bonus_spells` | PHB p11 | additional spells |
| `W10` | 009-013-ability-scores-r01 | `abil_wisdom` MODIFIES `rule_spell_failure` | PHB p11 | failure chance |
| `W11` | 009-013-ability-scores-r01 | `abil_wisdom` GATES `rule_spell_level_access` | PHB p11 | clerical 6th and 7th |
| `D3` | 009-013-ability-scores-r01 | `dex_reaction_adj` MODIFIES `cbt_surprise` | DMG p62 | mitigates surprise individually |
| `D5` | 009-013-ability-scores-r01 | `dex_defensive_adj` MODIFIES `cbt_armor_class` | DMG p28 | in addition to other protection |
| `D7` | 009-013-ability-scores-r01 | `abil_dexterity` MODIFIES `cbt_initiative` | PHB p11 | reaction adjustment |
| `D13` | 009-013-ability-scores-r01 | `abil_dexterity` GATES `class_thief` | PHB p27 | eligibility |
| `D14` | 009-013-ability-scores-r01 | `abil_dexterity` GATES `class_assassin` | PHB p28 | eligibility |
| `D15` | 009-013-ability-scores-r01 | `abil_dexterity` GATES `class_monk` | PHB p30 | eligibility |
| `D17` | 009-013-ability-scores-r01 | `abil_dexterity` GATES `class_magic_user` | PHB p11 | eligibility |
| `C1` | 009-013-ability-scores-r01 | `abil_constitution` MODIFIES `rule_hit_points` | PHB p12 | per-die adjustment / raised ceiling |
| `C3` | 009-013-ability-scores-r01 | `abil_constitution` MODIFIES `rule_system_shock` | PHB p12 | survival chance |
| `C4` | 009-013-ability-scores-r01 | `abil_constitution` MODIFIES `rule_resurrection_survival` | PHB p12 | survival chance |
| `C6` | 009-013-ability-scores-r01 | `spell_raise_dead` MODIFIES `abil_constitution` | PHB p12 | permanent loss per raise |
| `C7` | 009-013-ability-scores-r01 | `abil_constitution` GATES `class_fighter` | PHB p12 | eligibility |
| `C8` | 009-013-ability-scores-r01 | `abil_constitution` GATES `class_paladin` | PHB p12 | eligibility |
| `C9` | 009-013-ability-scores-r01 | `abil_constitution` GATES `class_monk` | PHB p12 | eligibility |
| `C10` | 009-013-ability-scores-r01 | `abil_constitution` GATES `class_ranger` | PHB p12 | eligibility |
| `C12` | 009-013-ability-scores-r01 | `rule_aging` TRIGGERS `rule_system_shock` | PHB p12 | roll required |
| `C13` | 009-013-ability-scores-r01 | `rule_petrification` TRIGGERS `rule_system_shock` | PHB p12 | roll required |
| `C14` | 009-013-ability-scores-r01 | `spell_flesh_to_stone` TRIGGERS `rule_system_shock` | PHB p12 | roll required |
| `C15` | 009-013-ability-scores-r01 | `spell_polymorph_any_object` TRIGGERS `rule_system_shock` | PHB p12 | roll required |
| `C16` | 009-013-ability-scores-r01 | `spell_polymorph_other` TRIGGERS `rule_system_shock` | PHB p12 | roll required |
| `H3` | 009-013-ability-scores-r01 | `abil_charisma` MODIFIES `cbt_encounter_reactions` | PHB p13 | reaction adjustment |
| `H5` | 009-013-ability-scores-r01 | `abil_charisma` GATES `class_paladin` | PHB p22 | eligibility |
| `B7` | 013-018-races-r03 | `abil_strength` MODIFIES `exp_level` | PHB p14 | raises racial level cap |
| `B8` | 013-018-races-r03 | `abil_intelligence` MODIFIES `exp_level` | PHB p14 | raises racial level cap |
| `B9` | 013-018-races-r03 | `abil_dexterity` MODIFIES `exp_level` | PHB p14 | raises racial level cap |
| `B10` | 013-018-races-r03 | `race_subrace` CONSTRAINS `exp_level` | UA p8 | expanded level limit table |
| `C1` | 013-018-races-r03 | `race_dwarf` MODIFIES `abil_constitution` | PHB p14 | racial adjustment |
| `C2` | 013-018-races-r03 | `race_dwarf` MODIFIES `abil_charisma` | PHB p14 | racial adjustment |
| `C3` | 013-018-races-r03 | `race_elf` MODIFIES `abil_dexterity` | PHB p14 | racial adjustment |
| `C4` | 013-018-races-r03 | `race_elf` MODIFIES `abil_constitution` | PHB p14 | racial adjustment |
| `C5` | 013-018-races-r03 | `race_half_orc` MODIFIES `abil_strength` | PHB p14 | racial adjustment |
| `C6` | 013-018-races-r03 | `race_half_orc` MODIFIES `abil_constitution` | PHB p14 | racial adjustment |
| `C7` | 013-018-races-r03 | `race_half_orc` MODIFIES `abil_charisma` | PHB p14 | racial adjustment |
| `C8` | 013-018-races-r03 | `race_halfling` MODIFIES `abil_strength` | PHB p14 | racial adjustment |
| `C9` | 013-018-races-r03 | `race_halfling` MODIFIES `abil_dexterity` | PHB p14 | racial adjustment |
| `D5` | 013-018-races-r03 | `abil_intelligence` GATES `race_elf` | PHB p10 | eligibility |
| `D6` | 013-018-races-r03 | `abil_intelligence` GATES `race_gnome` | PHB p10 | eligibility |
| `D7` | 013-018-races-r03 | `abil_intelligence` GATES `race_half_elf` | PHB p10 | eligibility |
| `D8` | 013-018-races-r03 | `abil_intelligence` GATES `race_halfling` | PHB p10 | eligibility |
| `D9` | 013-018-races-r03 | `abil_dexterity` GATES `race_elf` | PHB p11 | eligibility |
| `D10` | 013-018-races-r03 | `abil_dexterity` GATES `race_half_elf` | PHB p11 | eligibility |
| `D11` | 013-018-races-r03 | `abil_dexterity` GATES `race_halfling` | PHB p11 | eligibility |
| `D12` | 013-018-races-r03 | `abil_constitution` GATES `race_dwarf` | PHB p12 | eligibility |
| `D13` | 013-018-races-r03 | `abil_constitution` GATES `race_elf` | PHB p12 | eligibility |
| `D14` | 013-018-races-r03 | `abil_constitution` GATES `race_gnome` | PHB p12 | eligibility |
| `D16` | 013-018-races-r03 | `abil_constitution` GATES `race_halfling` | PHB p12 | eligibility |
| `D17` | 013-018-races-r03 | `abil_constitution` GATES `race_half_orc` | PHB p12 | eligibility |
| `F14` | 013-018-races-r03 | `race_elf` MODIFIES `ex_secret_doors` | DMG p172 | better chance to locate |
| `G2` | 013-018-races-r03 | `race_elf` GATES `rule_multiclass` | UA p72 | widest range of combinations |
| `A14` | 018-033-classes-r02 | `exp_level` GATES `thief_read_scrolls` | PHB p27, UA p13 | ability unlocked / upper level thieves and assassins gain  |
| `B1` | 018-033-classes-r02 | `class_cleric` CONSTRAINS `sys_equipment` | PHB p20 | edged and pointed forbidden |
| `B3` | 018-033-classes-r02 | `class_magic_user` CONSTRAINS `sys_equipment` | PHB p25 | very limited selection |
| `B5` | 018-033-classes-r02 | `class_thief` CONSTRAINS `sys_equipment` | PHB p27 | limited selection |
| `C3` | 018-033-classes-r02 | `sys_alignment` GATES `class_paladin` | PHB p18, PHB p22 | eligibility / must begin and remain lawful good |
| `C5` | 018-033-classes-r02 | `sys_alignment` GATES `class_thief` | UA p12 | non-good at start |
| `C6` | 018-033-classes-r02 | `sys_alignment` GATES `class_assassin` | PHB p18, PHB p28 | eligibility / evil required |
| `C7` | 018-033-classes-r02 | `sys_alignment` GATES `class_monk` | PHB p30 | must be lawful |
| `F2` | 018-033-classes-r02 | `exp_level` GATES `class_followers` | PHB p20, PHB p27 | attracted at name level / gang of thieves attracted |
| `F3` | 018-033-classes-r02 | `exp_level` GATES `rule_stronghold` | PHB p20 | construction option |
| `F10` | 018-033-classes-r02 | `class_paladin` MODIFIES `save_matrix` | PHB p23 | bonus to all saves |
| `F30` | 018-033-classes-r02 | `exp_level` MODIFIES `thief_backstab` | PHB p27 | damage multiplier tier |
| `F31` | 018-033-classes-r02 | `thief_backstab` MODIFIES `cbt_tohit` | PHB p27 | bonus from behind |
| `F32` | 018-033-classes-r02 | `exp_level` MODIFIES `thief_skills` | PHB p27 | success chance |
| `F33` | 018-033-classes-r02 | `exp_level` GATES `thief_read_languages` | PHB p27 | ability unlocked |
| `F37` | 018-033-classes-r02 | `race_infravision` CONSTRAINS `thief_hide_in_shadows` | PHB p102 | body heat betrays the thief |
| `F41` | 018-033-classes-r02 | `class_assassin` GATES `rule_disguise` | PHB p29 | class ability |
| `F42` | 018-033-classes-r02 | `abil_intelligence` GATES `rule_alignment_languages` | PHB p29 | ability to learn |
| `F46` | 018-033-classes-r02 | `class_monk` GATES `thief_skills` | PHB p31 | performed at equal level |
| `F47` | 018-033-classes-r02 | `class_monk` GATES `rule_open_hand_combat` | PHB p30 | class ability |
| `F51` | 018-033-classes-r02 | `exp_level` MODIFIES `cbt_surprise` | PHB p30 | harder to surprise per level |
| `A2` | 033-035-alignment-hp-languages-r01 | `align_change` CONSTRAINS `sys_alignment` | PHB p33 | voluntary change limited |
| `A3` | 033-035-alignment-hp-languages-r01 | `rule_hit_points` DERIVED_FROM `exp_level` | DMG p82 | skill and experience raise effective survivability |
| `A6` | 033-035-alignment-hp-languages-r01 | `rule_alignment_languages` DERIVED_FROM `sys_alignment` | PHB p29 | one tongue per alignment |
| `B2` | 035-038-money-equipment-r02 | `sys_equipment` CONSUMES `money_gp` | DMG p64 | acquisition cost at DM adjudication |
| `B6` | 035-038-money-equipment-r02 | `rule_shield` MODIFIES `cbt_armor_class` | PHB p36 | improves rating |
| `B8` | 035-038-money-equipment-r02 | `item_magic_armor` MODIFIES `cbt_armor_class` | PHB p36 | one step per plus |
| `B11` | 035-038-money-equipment-r02 | `exp_level` MODIFIES `prof_weapon` | PHB p37, UA p26 | additional weapons gained / rate of gain differs by class |
| `B12` | 035-038-money-equipment-r02 | `prof_nonproficiency_penalty` MODIFIES `cbt_tohit` | PHB p37 | subtraction from attack |
| `B13` | 035-038-money-equipment-r02 | `wpn_weight` FEEDS_INTO `enc_encumbrance` | PHB p37 | carried load |
| `B15` | 035-038-money-equipment-r02 | `wpn_type_vs_ac` MODIFIES `cbt_tohit` | UA p27 | per weapon against each armor class |
| `B16` | 035-038-money-equipment-r02 | `wpn_range` MODIFIES `cbt_tohit` | DMG p64 | penalty at medium and long range |
| `B17` | 035-038-money-equipment-r02 | `cbt_surprise` MODIFIES `cbt_tohit` | UA p107 | bonus to strike |
| `B18` | 035-038-money-equipment-r02 | `wpn_stats` FEEDS_INTO `cbt_damage` | PHB p37 | damage by weapon type |
| `C2` | 039-040-hirelings-time-distance-r01 | `abil_charisma` MODIFIES `hench_hirelings` | PHB p39 | hiring success |
| `C5` | 039-040-hirelings-time-distance-r01 | `sys_alignment` MODIFIES `hench_loyalty` | DMG p37, PHB p39 | compatibility required / penalty grows with places removed |
| `C6` | 039-040-hirelings-time-distance-r01 | `money_gp` MODIFIES `hench_loyalty` | DMG p37, PHB p39 | recent generosity / remuneration and bonuses |
| `C9` | 039-040-hirelings-time-distance-r01 | `hench_henchmen` CONSUMES `money_gp` | DMG p36, PHB p39 | liege must equip them entirely / recruitment costs / wage  |
| `A1` | 040-042-spells-intro-r01 | `rule_rest` GATES `rule_spell_memorization` | PHB p40 | mind must be rested |
| `A3` | 040-042-spells-intro-r01 | `rule_spell_book` GATES `rule_spell_memorization` | PHB p25 | must consult to prepare |

## Recommended disposition

1. **Direction conflicts** to Reviewer with both sources in hand. Correctness, not tidiness.
2. **Type conflicts** to Reviewer. Where canonical cites the DMG and the proposal cites the
   PHB, the operator's standing direction is to favour the PHB pending Architect
   ratification; see OBS-30 of `GUR-PKT-PHB-035-038-money-equipment-r02`.
3. **Exact duplicates** to Builder. Most should be dropped from the GUP. Those whose
   canonical row cites a different book should instead have the PHB citation added to the
   existing row.
4. **No GUR changes are proposed on the strength of this report.** A GUR records what a
   packet says. Whether an assertion is already held by the graph is a Builder and Reviewer
   determination, and writing that answer back into an interpretive artifact would put a
   normalisation decision in the wrong place.
