# Builder Handoff — 2026-07-29

Compilation of five PHB GURs into five GUPs. Every finding below is routed to the
role that owns the fix. Builder resolves none of them.

- `ruleset_id`: `adnd1e`
- `book_id`: `phb`
- `source_id`: `phb-legacy-unspecified`
- `constitution_version`: 1.2
- Builder tool: `adnd1e-builder` 1.0.0, 118 tests passing

## 1. Artifacts produced

| GUP | Status | Additions | Pending | Updates |
|---|---|---|---|---|
| `GUP-PKT-PHB-001-006-preamble-r02` | proposed | 0 | 0 | 0 |
| `GUP-PKT-PHB-007-008-intro-r02` | proposed | 7 | 0 | 0 |
| `GUP-PKT-PHB-009-013-ability-scores-r01` | blocked | 75 | 5 | 4 |
| `GUP-PKT-PHB-013-018-races-r03` | blocked | 133 | 3 | 0 |
| `GUP-PKT-PHB-018-033-classes-r01` | blocked | 98 | 9 | 1 |

335 candidate edges in; 313 integrable, 17 pending a node ruling, 5 emitted as
updates. Nothing was dropped.

Each GUP is accompanied by `<gup-id>.edges.csv` (18 production columns, only rows
satisfying invariant 1) and `build/reports/<gup-id>.validation.json`.

Verified: 15/15 artifacts byte-identical across repeated runs; 5/5 GUPs valid
against `schemas/common/gup.schema.json` composed with
`schemas/adnd1e/graph/gup.schema.json`; every cited page resolves to a `{#pN}`
marker in the packet source.

## 2. For the Analyst — 9 technical defects to fix in the GUR

All nine are in `GUR-PKT-PHB-018-033-classes-r01`. None blocks approval on its
own; all are grain and field-format issues the Builder will not silently rewrite,
because changing `condition` or `aspect` text would alter what the edge asserts.

### Spelled-out magnitudes in `condition` (constitution section 2, invariant 11)

| Ref | Current `condition` |
|---|---|
| F13 | `from third level` |
| F20 | `below the eighth level` |
| F33 | `from the fourth level` |
| F40 | `two levels below assassin level` |
| F45 | `assassins from the fourth level` |
| F57 | `from the fifth level` |
| F58 | `below the sixth level` |

A digit check does not catch these; the magnitude is spelled. Invariant 11 forbids
threshold values in `condition`, and a level threshold is a magnitude. If the
qualitative fact is "this applies only above some level", the level number is not
part of it. If the specific level *is* the assertion, it belongs in the graph as a
relationship to `exp_level`, not as prose in a field.

Builder reports these as warnings rather than errors because the call between
"copied threshold" and "legitimate qualitative phrasing" is the Analyst's, not a
compiler's.

### `aspect` longer than four words (constitution section 5)

| Ref | Current `aspect` | Words |
|---|---|---|
| G5 | `advancement in the original class` | 5 |
| G6 | `hit dice on class change` | 5 |

## 3. For the Architect — 6 node registrations blocking 17 edges

Every error in every GUP traces here. All six use approved prefixes; none
collides with an existing canonical ID.

| Proposed node | Edges blocked | Packets |
|---|---|---|
| `rule_prime_requisite` | 9 | abilities (S14, I11, W8, D19), classes (D1–D4, plus one) |
| `rule_racial_detection` | 3 | races (F6, F20, F31) |
| `rule_dual_class` | 4 | classes (G3–G6) |
| `rule_tracking` | 1 | classes (F19) |
| `rule_revivification_limit` | 1 | abilities (C5) |

`rule_prime_requisite` spans two packets — the Analyst proposed it in the
abilities GUR and carried it forward in the classes GUR. One ruling clears both.

On a ruling, Builder recompiles and the three blocked GUPs are expected to reach
`proposed`. No other change is required.

## 4. For the Reviewer — 5 polarity repairs to confirm against source

These assertions already exist canonically carrying `polarity_basis=unset`. The
GURs supply an authored reading. They are emitted as **updates** to the existing
rows, not insertions: inserting would duplicate the assertion (invariant 12),
dropping would discard a reading the canonical row lacks.

| Ref | Canonical row | Assertion | Change |
|---|---|---|---|
| C3 | 4 | `abil_constitution MODIFIES rule_system_shock` | `neutral/unset` → `improves/read` |
| C4 | 5 | `abil_constitution MODIFIES rule_resurrection_survival` | `neutral/unset` → `improves/read` |
| I3 | 105 | `abil_intelligence MODIFIES rule_chance_know_spell` | `neutral/unset` → `improves/read` |
| H3 | 143 | `abil_charisma MODIFIES cbt_encounter_reactions` | `neutral/unset` → `improves/read` |
| F32 | 283 | `exp_level MODIFIES thief_skills` | `neutral/unset` → `improves/read` |

Only `polarity` and `polarity_basis` are proposed for change. Where `pass` or
`section` also differ, those are listed per-update under
`differences_not_applied` and are the Reviewer's to judge — Builder does not
overwrite another pass's extraction provenance.

Approving these repairs 5 of the 1,490 `polarity_basis=unset` rows recorded in
`rulesets/adnd1e/reports/PRECONDITION-AUDIT-20260727.md`, through the normal
pipeline rather than a migration.

### Advisory, not defects

100 `near_vs_canonical` findings: same endpoints and edge type as an existing
canonical edge, differing in `aspect` or `condition`. Zero exact duplicates
remain and zero duplicates exist within any patch. 63 neighbourhood notes record
node pairs already related by other edge types. Both sets are context for the
Reviewer's redundancy judgement — the Analyst flagged the same risk as `BLK-02`,
having been given no neighbourhood slice.

## 5. Observations outside Builder scope

Recorded so they are not rediscovered. Builder took no action on any of these.

- **14 canonical labels are carried by two node IDs each** — `Dwarf` is both
  `monster_dwarf` and `race_dwarf`; `Strength` is both `abil_strength` and
  `spell_strength`. Surfaced because the node resolver refuses to merge by label
  (invariant 4). This is the failure mode `ESC-2026-07-30T01.21.13.768Z` reports. The set is
  pinned by a test so a change becomes visible.
- **`phb.09.spells_intro.md` in `packets/incoming/` carries no page markers.**
  Every citation from it would be unresolvable, so an extraction pass on it
  cannot yield a citable edge. Pages 41–42 are claimed by no packet and the file
  falls in that gap. Builder did not infer its page range. Reproduce with
  `python -m adnd1e_builder lint-source books/adnd1e/phb/packets/incoming/*.md`.
- **Page 33 appears in both** the completed classes packet (18–33) and incoming
  `phb.06` (33–35).
- **The legacy 13→18 field migration is unbuilt.** The 3,851 / 3,613 / 3,809
  count drift remains unreconciled and blocks the Integrator independently of
  everything above.
