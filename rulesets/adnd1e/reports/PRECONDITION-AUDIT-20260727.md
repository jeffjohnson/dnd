# Integrator Precondition Audit

**Not an integration record.** This document records preconditions only. The first
integration batch is recorded at `rulesets/adnd1e/manifests/INT-20260730-001.json`.

> **Superseded in part, 2026-07-30.** Section 1 ("Integration is still blocked") no
> longer holds. Two Approved bundles reached the queue and were applied as
> `INT-20260730-001`: `APPROVED-GUP-PKT-PHB-001-006-preamble-r02-r01` (null yield)
> and `APPROVED-GUP-PKT-PHB-007-008-intro-r05-r01` (6 edges). Canonical edges moved
> 3,809 → 3,815. Integrator tooling now exists under `tooling/integrator/`.
> Sections 4 through 7 are updated below; sections 2, 3 and 5 still stand.

- First issued: 2026-07-27
- **Revised: 2026-07-29** after Architect changes (DEC-2026-0001, DEC-2026-0002,
  `contracts/SOURCE_MARKDOWN.md`, agent instruction updates)
- **Revised: 2026-07-30** after `INT-20260730-001`
- `ruleset_id`: `adnd1e`
- `constitution_version`: 1.2 (`rulesets/adnd1e/governance/constitution.md`, unchanged)
- `ruleset.yaml status`: `migration_pending`
- `book_id`: `phb` has live work; `source_id` `phb-legacy-unspecified`
- `packet_id`: five claimed, none carried past GUR

## 1. Integration is still blocked — no Approved GUP exists

The pipeline has advanced but has not reached the Integrator. Current artifact census:

| Stage | State |
|---|---|
| `packets/claimed/` (phb) | **5 packets** (preamble, intro, ability-scores, races, classes) |
| `artifacts/gur/` (phb) | **9 GURs** across those 5 packets |
| `artifacts/gup/` (all books) | empty |
| `artifacts/reviews/` (all books) | empty |
| `artifacts/approved/` (all books) | empty |
| `artifacts/integrated/` (all books) | empty |
| `rulesets/adnd1e/manifests/` | empty |
| `rulesets/adnd1e/releases/` | empty |
| `rulesets/adnd1e/cross-book/` | empty |

Work sits at Analyst output. No Builder GUP and no Reviewer approval exist, so
invariant 29 ("Integrator applies only Approved GUPs") still bars any canonical write.

Builder tooling has begun appearing under `tooling/builder/src/adnd1e_builder/`
(`grain.py`, `polarity.py`, `registry.py`, `vocab.py`). `tooling/integrator/src/`
remains empty — there is still no patch applier, snapshot/rollback tool, exporter, or
invariant suite owned by this role.

## 2. Architect decisions — all acceptance tests PASS

Both approved decisions were verified against actual repository state. Every acceptance
test in both files passes.

### DEC-2026-0001 — `race_human` added

| Acceptance test | Result |
|---|---|
| exactly one `race_human` row in `nodes.csv` | PASS |
| label `Human`, kind `race`, degree `0`, no authored roles | PASS |
| no duplicate IDs after insertion | PASS |
| `race_any` remains the generic Race node | PASS |
| no canonical edge changed | PASS (0 edges touch `race_human`) |

### DEC-2026-0002 — character-race taxonomy and `race_demihuman`

| Acceptance test | Result |
|---|---|
| registry contains exactly seven unique member IDs | PASS |
| `race_human` is the only `human` classification | PASS |
| exactly six `demihuman` members | PASS |
| `race_any` group contains all seven | PASS |
| `race_demihuman` contains exactly the six demihuman | PASS |
| every member and group ID resolves exactly once in `nodes.csv` | PASS |
| `race_half-elf` / `race_half-orc` absent as canonical IDs | PASS |
| registry membership creates no canonical edge | PASS (0 found) |
| no canonical edge changed | PASS |

The registry additions were made under Architect authority over controlled registries
(`REPOSITORY_STRUCTURE.md`). Both rows carry `degree 0` and empty `roles`, which is the
correct deterministic pre-integration value — degrees and roles are build-derived.

### Expected, benign registry/canonical divergence

`registries/nodes.csv` now holds **1,096** nodes; `canonical/nodes_master.csv` holds
**1,094**. The difference is exactly `race_human` and `race_demihuman`. This is the
registry correctly leading canonical: the IDs are approved and mintable, but no approved
edge has yet been integrated to give them degree. This is **not** drift and requires no
remediation.

## 3. Two migration review sets are queued for this role

Both decisions assign `canonical_migration: integrator`, but explicitly gate it behind
Builder/Reviewer source review. I re-derived both review sets from canonical data and
they reproduce the Architect's census exactly:

| Set | Decision | Rows | Labels found |
|---|---|---|---|
| `race_any` rows meaning Human | DEC-2026-0001 | **3** (decision says 3) | `Human`, `Humanity` |
| `race_any` rows meaning Demihuman | DEC-2026-0002 | **4** (decision says 4) | `Demihuman Craftsmen`, `Demihuman Race`, `Small Demi-Humans`, `Demi-Humans` |

`race_any` carries **49 incident edges** under **13 distinct labels** — matching
ESC-2026-0004's census exactly.

Standing constraints on that future migration, taken from the decisions:

- Do **not** automatically repoint all 49 `race_any` edges.
- The `Small Demi-Humans` row must **not** be broadened to all demihumans.
- Only source-reviewed, approved rows may be repointed.
- GUR leaf edges B1–B6 are independent proposals and must be deduplicated at
  source-supported grain before any repointing interacts with them.

Neither migration can proceed until a Builder GUP and a Reviewer approval exist.

## 4. Canonical state measurement (updated after `INT-20260730-001`)

| Artifact | Before | After |
|---|---|---|
| `edges_master.csv` | 3,809 edges, 18 columns | **3,815** edges, 18 columns |
| `nodes_master.csv` | 1,094 nodes | 1,094 nodes |
| `graph.json` | 3,809 / 1,094, schema 1.2 | **3,815** / 1,094, schema 1.2 |

Ten nodes were recomputed. One role changed as a genuine derived consequence:
`rule_spell_level_access` reached a third inbound `GATES` and gained
`gated_privilege`. No node was created or retired.

### Consistency checks that PASS

- Header matches constitution §12 column order exactly (18 columns); every row has 18.
- `graph.json` counts and `polarity_basis` histogram reproduce exactly from
  `edges_master.csv` — generated JSON is not stale.
- All 1,094 `in_degree` / `out_degree` values recompute exactly from the edge list.
- No duplicate edge identity (invariant 12); no dangling endpoint (invariant 1); no
  isolated node.
- All `edge_type`, `book`, `evidence`, `status`, `polarity`, `polarity_basis`,
  `review_flag`, `supersession_basis` values within controlled vocabularies.
- Every edge cited (invariant 9); `supersession_basis` correct on/off `OVERRIDES`
  (invariant 20); `general_rule_id` gated on `pass=general-rule` and fully resolvable
  (invariants 18, 19).

### Invariant violations — 1,728 findings across 1,702 rows

Measured by the Integrator invariant suite immediately before and after
`INT-20260730-001`. The counts are identical on both sides: **the batch introduced
nothing**.

| Count | Violation | Invariant |
|---|---|---|
| 1,700 | `MODIFIES`/`TRIGGERS`/`CONSTRAINS` with `polarity_basis` of `unset` or `heuristic` | 16 |
| 19 | edge endpoint uses a node prefix absent from constitution §3.1 | 3 |
| 9 | digit in `aspect` or `condition` | 11 |

The prefix count fell from 379 to 19 because DEC-2026-0004 approved `wpn_` and
`thief_` at constitution 1.3 and rejected the other eight, directing a reviewed
migration rather than a wider vocabulary. The constitution's own §4.1 and §6.2
examples were corrected at the same time and no longer use unapproved prefixes.

The residual 1,700 polarity findings are the legacy corpus awaiting the 13→18
migration in section 5. They are recorded as baseline in every integration manifest
and may not grow: the applier rejects any batch that regresses an invariant count.

## 5. Baseline still unreconciled

`canonical/BASELINE.md` still records `verification_status: pending`, and the counts
still do not close:

| Source | Edges | Columns |
|---|---|---|
| Legacy CSV | 3,851 | 13 |
| Legacy JSON | 3,613 | — |
| Current canonical | 3,809 | 18 |
| `profiles/roles.yaml` `corpus_state.edges` | 3,851 | — |
| Constitution §6.1 derived-polarity claim | 2,026 of 3,851 | — |

42 legacy CSV rows remain unaccounted for against canonical with no migration report.
Role thresholds in `roles.yaml` and the §6.1 percentages are stated against a
3,851-edge corpus that is not the current canonical file.

## 6. Repository consistency findings

### Resolved since 2026-07-27

- `agents/integrator/INSTRUCTIONS.md` startup item 1 now correctly names
  `governance/constitution.md`.
- `CLAUDE.md` no longer references the non-existent `contracts/ownership.md`; ownership
  now derives from `REPOSITORY_STRUCTURE.md` and per-role prohibited-actions sections.
- `contracts/SOURCE_MARKDOWN.md` (v1.0) added and wired into the Integrator startup
  reads as item 4. Integrator obligation under it: *carry approved page provenance
  without reinterpretation.*
- `ruleset.yaml` now names `character_race_registry`.
- **Both missing escalations now exist.** `ESC-2026-0002` and
  `ESC-2026-07-30T01.21.13.768Z` are filed under `escalations/decided/`, which now
  holds twelve escalations against thirteen decisions.
- **The misfiled escalations were moved.** `escalations/pending/` is empty;
  `decided/` and `returned/` exist and `FILE_NAMING.md` 1.3 documents the
  `returned/` state.
- **The unapproved-prefix question is decided.** DEC-2026-0004 approved `wpn_` and
  `thief_`, rejected eight others, and bumped the constitution to 1.3.

### Outstanding

- **An upstream GUR was edited after publication**, breaking a Review-pinned
  checksum. See "Defects found during `INT-20260730-001`" in section 7.
- **`schemas/adnd1e/graph/edge.schema.json` is unusable for meta-validation** —
  duplicate `source_id` in its `required` array.
- **Superseded, for the record.** The two findings below were outstanding at the
  2026-07-29 revision and are now resolved; they are retained so the audit trail
  reads correctly.
  - `ESC-2026-0001`/`ESC-2026-0002` referenced but absent — now present under
    `decided/`.
  - `ESC-2026-0003`/`ESC-2026-0004` carrying `status: decided` while filed under
    `escalations/pending/`. `FILE_NAMING.md` states folders represent state. Both had
    `decision_id` set to decisions that exist and are approved, so the folder
    contradicted the field.
  - Constitution §3.2 and §13b naming `node_registry.csv` and `roles_profile.yaml`.
    Constitution 1.4 now names `registries/nodes.csv` and `profiles/roles.yaml`
    correctly.

## 7. Required to unblock integration — status at 2026-07-30

| # | Precondition | Status |
|---|---|---|
| 1 | A Builder GUP and Reviewer-approved artifact for at least one PHB packet | **Met.** Two Approved bundles applied as `INT-20260730-001`. |
| 2 | Integrator tooling under `tooling/integrator/src/` | **Met.** Applier, snapshot/rollback, exporter, role derivation, invariant suite and queue scanner, with 43 tests. |
| 3 | An Architect decision on the unapproved node prefixes | **Met.** DEC-2026-0004 approved `wpn_` and `thief_` at constitution 1.3 and rejected the other eight, directing a reviewed migration. Residual invariant-3 findings: 19. |
| 4 | A migration policy and reviewed baseline reconciling 3,851 / 3,613 / 3,809 | **Outstanding.** No migration runner exists. See section 5. |

### Defects found during `INT-20260730-001`

Recorded here because they belong to other roles and the Integrator may not repair
them. All three are advisory in the integration manifest, not blocking, because the
preamble bundle contributed zero rows and therefore no canonical assertion depends on
them.

1. **`GUR-PKT-PHB-001-006-preamble-r02.yaml` was edited after publication.** Its
   `downstream_notes` block is self-dated "added 2026-07-30, after the GUR body was
   written". `REV-GUP-PKT-PHB-001-006-preamble-r02-r01` pinned the GUR at
   `sha256:5aa466ce…`; the file now hashes to `sha256:d94e0a98…`. This violates
   `contracts/WORK_QUEUES.md` rule 8 and the append-only rule in
   `contracts/ARTIFACT_LIFECYCLE.md`, and breaks a published provenance chain.
   Owner: the artifact's author, with the Architect to decide whether a replacement
   revision is required.
2. **The preamble Approved bundle has no manifest.** Reconstructed under
   `WORK_QUEUES` legacy rule 6 from its filename stem and approving Review, exactly as
   DEC-2026-0012 anticipated. Every inference is recorded in the integration manifest.
3. **`registries/nodes.csv` has mixed line endings.** The `race_demihuman` and
   `race_human` rows are LF-terminated in an otherwise CRLF file. Cosmetic, but it
   makes the registry fail a byte-exact round-trip. Owner: Architect. Untouched by
   this batch, which proposed no registry change.

### Schema defect still open

`schemas/adnd1e/graph/edge.schema.json` repeats `source_id` in its `required` array,
violating JSON Schema 2020-12 uniqueness. Reported by the Reviewer in
`REV-GUP-PKT-PHB-001-006-preamble-r02-r01` and still unrepaired, so the edge schema
cannot be used for meta-validation. Owner: Builder (schema implementation).
