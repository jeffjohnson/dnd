# Integrator Precondition Audit — 2026-07-27

**Not an integration record.** No canonical state was mutated. No `INT-` ID is claimed,
because no batch was supplied.

- `ruleset_id`: `adnd1e`
- `constitution_version`: 1.2 (`rulesets/adnd1e/governance/constitution.md`)
- `ruleset.yaml status`: `migration_pending`
- `book_id` / `source_id` / `packet_id`: **unresolved** — no manifest supplied

## 1. Why integration did not run

The assigned task named an integration manifest but supplied no content for it. No
substitute exists in the repository:

| Expected input | State |
|---|---|
| `rulesets/adnd1e/manifests/` | empty (`.gitkeep` only) |
| `books/adnd1e/{phb,dmg,mm,ua}/artifacts/approved/` | all empty |
| `books/adnd1e/{phb,dmg,mm,ua}/artifacts/gup/` | all empty |
| `books/adnd1e/{phb,dmg,mm,ua}/artifacts/reviews/` | all empty |
| `books/adnd1e/{phb,dmg,mm,ua}/packets/{incoming,claimed,completed}/` | all empty |
| `rulesets/adnd1e/escalations/decisions/` | empty |
| `tooling/integrator/src/` | empty (`.gitkeep` only) |

There are zero Approved GUPs in the repository. Per `GRAPH_INVARIANTS.md` §29
("Integrator applies only Approved GUPs") and the Integrator prohibition on manual
graph changes outside an integration batch, no canonical write is permissible.

## 2. Current canonical state

Read-only measurement of `rulesets/adnd1e/canonical/`:

| Artifact | Count |
|---|---|
| `edges_master.csv` | 3,809 edges, 18 columns |
| `nodes_master.csv` | 1,094 nodes |
| `registries/nodes.csv` | 1,094 nodes |
| `graph.json` | 3,809 edges / 1,094 nodes, schema 1.2 |

### Consistency checks that PASS

- `edges_master.csv` header matches the constitution §12 column order exactly (18 columns).
- Every row carries exactly 18 columns.
- `graph.json` counts and `polarity_basis` histogram reproduce exactly from
  `edges_master.csv` — the generated JSON is not stale relative to the CSV.
- `nodes_master.csv` `in_degree` / `out_degree` recompute exactly from the edge list
  for all 1,094 nodes.
- `registries/nodes.csv` and `nodes_master.csv` cover an identical node set.
- No duplicate edge identity (invariant 12).
- No edge endpoint missing from `nodes_master.csv` (invariant 1).
- No node with zero incident edges.
- All `edge_type` values are within the thirteen-type closed vocabulary (invariant 7).
- All `book`, `evidence`, `status`, `polarity`, `polarity_basis`, `review_flag`,
  `supersession_basis` values are within their controlled vocabularies.
- Every edge carries a citation — page and/or section (invariant 9).
- `supersession_basis` present on every `OVERRIDES` and absent elsewhere (invariant 20).
- `general_rule_id` set only under `pass=general-rule`, and every value resolves in
  `registries/general_rules.json` (invariants 18, 19).

### Invariant violations — 2,088 edge rows affected

| Count | Violation | Invariant |
|---|---|---|
| 1,490 | `MODIFIES`/`TRIGGERS`/`CONSTRAINS` with `polarity_basis=unset` | 15, 16 |
| 210 | `MODIFIES`/`TRIGGERS`/`CONSTRAINS` with `polarity_basis=heuristic` | 16; constitution §6.1 "No approved patch may retain `heuristic`" |
| 379 | edge endpoint uses a node prefix not in constitution §3.1 | 3 |
| 8 | digit in `condition` | 11 |
| 1 | digit in `aspect` | 11 |

The 379 prefix violations trace to **23 distinct nodes**:

| Prefix | Nodes | Examples |
|---|---|---|
| `wpn_` | 7 | `wpn_length`, `wpn_range`, `wpn_space_required` |
| `str_` | 3 | `str_bend_bars`, `str_exceptional`, `str_open_doors` |
| `magic_` | 2 | `magic_item_determination`, `magic_resistance` |
| `death_` | 2 | `death_character`, `death_drowning` |
| `dex_` | 2 | `dex_defensive_adj`, `dex_reaction_adj` |
| `turn_` | 1 | `turn_undead` |
| `cursed_` | 1 | `cursed_item` |
| `comeliness_` | 1 | `comeliness` |
| `time_` | 1 | `time_segment_round_turn` |
| `align_` | 1 | `align_change` |
| `fatigue_` | 1 | `fatigue` |
| `training_` | 1 | `training` |

**This is an Architect matter, not an integration defect.** The constitution's own worked
examples use `turn_undead` (§6.2) and `str_bend_bars` (§4.1) while §3.1 approves neither
`turn_` nor `str_`. Per `ESCALATION_CONTRACT.md`, "the constitution and production data
disagree in a way that cannot be fixed mechanically" is an escalation trigger. The
Integrator must not resolve ontology conflicts.

## 3. Baseline is unreconciled

`canonical/BASELINE.md` records `verification_status: pending`. The counts do not
reconcile against the figures in the Integrator instructions:

| Source | Edges | Columns |
|---|---|---|
| Legacy CSV (`migrations/.../original/edges_master.csv`) | 3,851 | 13 |
| Legacy JSON (`migrations/.../original/addnd_graph.json`) | 3,613 | — |
| Current canonical | 3,809 | 18 |
| `profiles/roles.yaml` `corpus_state.edges` | 3,851 | — |
| Constitution §6.1 derived-polarity claim | 2,026 of 3,851 | — |

Current canonical sits between the two legacy figures and matches neither. 42 legacy CSV
rows are unaccounted for against canonical, with no migration report explaining the
drift. The Integrator prohibition on permitting "count drift without explanation" means
this baseline cannot be certified as-is, and per instructions the baseline must be
rebuilt from the most complete preserved source through Builder tooling rather than
patched forward.

`roles.yaml` and the constitution both describe a 3,851-edge corpus, so the derived role
thresholds and the §6.1 percentages are stated against a corpus that is not the current
canonical file.

## 4. Documentation defects found

- `CLAUDE.md` step 3 and the Ownership section reference `contracts/ownership.md`. That
  file does not exist. `contracts/` contains only `ARTIFACT_LIFECYCLE.md`,
  `ESCALATION_CONTRACT.md`, `FILE_NAMING.md`, `GRAPH_INVARIANTS.md`, `SCOPE_AND_IDENTITY.md`.
- `agents/integrator/INSTRUCTIONS.md` "Read at startup" item 1 names
  `rulesets/<ruleset-id>/governance/graph_constitution.md`. The actual file is
  `governance/constitution.md`.
- Constitution §3.2 names the node registry `node_registry.csv`; the actual path is
  `rulesets/adnd1e/registries/nodes.csv`.
- Constitution §13b names `roles_profile.yaml`; the actual path is
  `rulesets/adnd1e/profiles/roles.yaml`.

## 5. Required to unblock integration

1. An integration manifest listing specific Approved GUP artifacts, or the artifacts
   themselves under `books/adnd1e/<book>/artifacts/approved/` with matching Review
   artifacts carrying no blocking disposition.
2. Integrator tooling under `tooling/integrator/src/` — none exists, so there is no
   transactional patch applier, snapshot/rollback tool, exporter, or invariant suite to
   run a batch through.
3. An Architect decision on the 23 unapproved node prefixes.
4. A migration policy and reviewed baseline reconciling 3,851 / 3,613 / 3,809.
