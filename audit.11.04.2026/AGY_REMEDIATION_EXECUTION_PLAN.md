# AGY Execution Plan: November 4 Rules Graph Remediation

Date: 2026-11-04. Prepared by Codex in the Architect role.
Status: implementation handoff plan; audit conclusions accepted, not re-audited.

## 1. Mandate and Inputs

Implement the recommendations in these three supplied artifacts:

- `shadowdark_graph_generation_remediation_spec.md` (the remediation requirements).
- `rules_graph_defect_register.csv` (17 tracked defects).
- `rules_graph_regression_cases.json` (15 specified behavioral cases, not executed results).

All three paths are relative to this directory. Preserve them unchanged.
This plan does not reopen their conclusions, infer new extraction root causes,
or certify that the audited export is the current repository baseline.
The reported 732 nodes, 1,498 edges, 240 classification gaps and other counts
are audit-snapshot measurements, not counts agents must force the live graph to match.

Shadowdark is the remediation pilot: core `sd`, then affected supplements,
including `cs1`, `cs2`, and `cs3`. Inventory all already-processed Shadowdark
source content, not just existing gap rows. Include other processed Shadowdark
books if the packet ledger identifies them. Do not silently extend repair to
unprocessed books or unrelated systems.

The owner currently wants 2024 for actual 5e onboarding. Future 2014 isolation
tests do not authorize a 2014 ingestion project. Rules Cyclopedia is authorized
under current owner instructions; this plan neither withdraws that authorization
nor starts RC work. Respect the existing repository-wide packet relay when
scheduling remediation packets.

## 2. Execution Rules

1. Fix generation and validation, then repair existing data through reviewed
   migrations and packet successors. Do not merely append classification edges.
2. Preserve valid relationships, original source, published artifacts, and history.
   Do not deduplicate by subject/predicate/object alone.
3. The graph remains a navigation index until release gates establish the supported
   scope. Answers require authoritative source passages, not edge labels alone.
4. Treat gap lists as investigation assignments, never executable patches.
   Source verification while authoring corrections is mandatory; repeating the
   audit or debating whether these defects matter is not.
5. Any schema/ontology/storage change needs Architect authority before implementation.
   Do not place numeric tier values or new predicates in existing fields merely
   because the audit uses an illustrative schema. Govern their representation.
6. Only Integrator writes `rulesets/<ruleset>/canonical/`. Reviewer independently
   verifies; an agent's self-test or a passing schema is not independent approval.
7. No blanket rerun, overwrite, source deletion, identity merge, or export-only
   patch. Every change must have issue IDs, evidence, an owner and a reviewed diff.
8. Do not rebuild orchestration or add a Dispatcher. Use the owner's current AGY
   sessions. This document is the durable handoff; no Herdr session is assumed.

### Five Role Assignments

| Role | Primary responsibility in this program | Cannot substitute for |
|---|---|---|
| Architect | Approve contracts, identity/claim/passage semantics, profiles, migration authority and activation order | Source extraction, routine Review, canonical integration |
| Analyst | Independent source inventory, exact passage mapping, entity-role proposals, source-grounded GUR successors | Compiler changes or canonical patches |
| Builder | Pipeline/gate implementation, approved migrations, compiled GUPs, retrieval implementation under assigned scope | Ontology decisions or independent approval |
| Reviewer | Independently verify source fidelity, test expectations, implementations, corrections and deletion/merge diffs | Editing another role's immutable artifacts |
| Integrator | Baseline snapshot, transaction/rollback support, approved canonical application, derived export regeneration and release | Accepting unreviewed repair rows |

Use the normal correction route: Integrator -> Reviewer -> Builder -> Analyst.
Any stage may escalate to Architect; pause that packet and return the Decision
to its originator. Analyst processes one packet at a time, with the next selected
after successful integration and the Integrator's notification. Batch inventories
and cross-packet worklists do not authorize simultaneous packet extraction.

## 3. First Work: Locate and Bind, Do Not Re-Audit

**First owner: Architect.** Assign the bounded work below, then publish the
contract/migration authorization in Phase 1. Do not allocate guessed DEC IDs.

Repository locations confirmed for routing, not implementation validation:

| Area | Starting locations | Owner |
|---|---|---|
| Common authority | `contracts/GRAPH_INVARIANTS.md`, `SOURCE_MARKDOWN.md`, `ARTIFACT_LIFECYCLE.md`, `SCOPE_AND_IDENTITY.md`, `WORK_QUEUES.md`, `FILE_NAMING.md` | Architect |
| Shadowdark authority | `rulesets/shadowdark/ruleset.yaml`, `governance/`, `profiles/`, `registries/`, `schemas/shadowdark/` | Architect under existing boundaries |
| Source and packet history | `books/shadowdark/<book>/`, `tooling/analyst/packet_inputs.py` | Analyst; tooling changes explicitly assigned |
| Compile/normalization | `tooling/builder/src/adnd1e_builder/` including `compiler.py`, `registry.py`, `review.py`, `emit.py`, migration modules | Builder |
| Publication/shared checks | `tooling/common/artifact_io.py`, `validate_artifact.py`, `scan_agent_queues.py`, tests | Existing owner; exact changes authorized before editing |
| Review checks | `tooling/reviewer/` | Reviewer-owned tooling; retain independent verification |
| Integration/export | `tooling/integrator/src/adnd1e_integrator/` including `integrate.py`, `canonical.py`, `derive.py`, `snapshot.py`, `invariants.py` | Integrator |
| Canonical and releases | `rulesets/shadowdark/canonical/`, `releases/`, `reports/` | Integrator for canonical changes |
| Retrieval application | Locate the actual serving/index code; do not presume a path or invent an existing subsystem | Architect assigns Builder the bounded implementation surface |

The `adnd1e_*` package names do not mean these modules are unused by Shadowdark.
Map actual call paths before choosing edit locations; no unrelated rename/refactor.

**Phase 0 deliverables:**

- Integrator: immutable baseline snapshot manifest with source/export/canonical
  hashes, repository revision and dirty-state identification, a baseline version,
  actual snapshot location, and restoration procedure. Snapshotting is not repair.
- Analyst: packet ledger linking existing packet IDs and source IDs to audit
  scopes. `shadowdark/sd` currently declares `sd-steward-intake` as its default;
  resolve each real artifact's source, printing and revision rather than assume
  that default for every book. Record unknown printing explicitly.
- Builder: component map identifying concrete code/schema/test entry points and
  which pipeline checks already exist. No fresh defect analysis or graph census.
- Reviewer: regression crosswalk from Section 7 and independently pinned fixtures.

Locate the audited `graph.json`, master CSVs, and `classification_gaps.csv`; the
audit directory supplies specifications, not those data files. If unavailable,
record the missing input and use the accepted defect list plus retained sources
for work planning. Do not fabricate a gap file or claim an old export is current.
If a target is already corrected in the working baseline, close it with exact
existing artifact/test evidence rather than apply the correction twice.

Record these deliverables under existing role-authorized report/work locations;
link them from `audit.11.04.2026/execution/STATUS.md` (to be created by AGY).

## 4. Delivery Phases and Gates

### Phase 1: Approve the Minimal Shared Contracts

**Owner:** Architect. **Prerequisite:** Phase 0 component and baseline mapping.

Publish bounded Decision step(s) covering:

- Source version registration and independent `SourceEntityManifest`: source
  entries, definitions versus mentions, tables/headers, exact expected coverage,
  reviewed exclusions and ambiguous entries.
- Stable passage IDs, retained text/spans, source hashes, source version and
  table/column context. Same source/version replay must preserve passage IDs.
- `entity_role`, `definition_status`, aliases, review state and identity redirects.
- Stable claim IDs, extraction packet ownership, evidence kind and review lineage;
  exact target claim for an override, separate from artifact revision lineage.
- Coupled spell offerings (spell, class list, tier, edition/source version), and
  separate armor use, weapon permission, proficiency, and item usability semantics.
- Applicability dimensions: availability, book selection, variant opt-in,
  possession and encounter predicates. Unknown interpretation is not true.
- Compatibility/migration shape: select versioned authoritative tables or
  sidecars and define legacy export projection. Do not silently change the
  five-field assertion contract or overload magnitude-free condition fields.
- Versioned profiles, exact file ownership, old-artifact admissibility, rollout
  gates and rollback. Include end-to-end lineage through GUR/GUP/Review/Approved/
  Integration/export so newly added evidence is not dropped downstream.

The audit fixes the required capabilities; Architect settles their concrete
representation, not whether to implement them. Keep this first contract focused
on Shadowdark and shared machinery. No universal rules engine build is needed.

**Exit:** published implementable authority with exact owned files, acceptance
cases, staged activation order and originating-role return instructions.

### Phase 2: Implement the Pipeline and Prevent Recurrence

**Owners:** Builder for compiler/shared work as assigned; Integrator for transaction
and export surfaces; Analyst for source manifest production; Reviewer for approval.
**Prerequisite:** Phase 1 authority.

Implement the audit's stages 0-6 with existing components where possible:

1. Register sources and produce a manifest independent of emitted graph nodes.
2. Bind packet extraction to source entry IDs and exact passage spans.
3. Normalize roles/aliases and classify against source lists/tables independently.
4. Reconcile definitions, class lists, equipment permissions and overrides across
   packets; unresolved references stay explicit, not invented definitions.
5. Enforce inventory, correctness, structure, coverage, precedence, provenance
   and change-safety gates before authoritative publication.
6. Preserve schema/version/identity compatibility, apply migrations transactionally,
   regenerate exports, and prove rollback and deterministic replay in fixtures.

Builder converts supplied regression assertions into executable tests; Reviewer
owns independent expectation checks. Add tests for omitted entities, column/row
misattribution, unverified claims, reference-only entries, identity redirects,
disabled variants, conflicting overrides and loss of valid parallel claims.

**Exit:** approved implementation reports, applicable existing suites green,
negative gates demonstrated, source-to-export provenance retained, and migration
transaction/rollback independently verified. Activate new gates prospectively;
track historical debt explicitly instead of relabeling all old data verified.

### Phase 3: Repair Shadowdark P0 in Bounded Reviewed Batches

**Relay:** Analyst -> Builder -> Reviewer -> Integrator -> Analyst.
**Prerequisite:** approved repair-capable tooling and applicable contract activation.

| Order | Batch | Required result |
|---|---|---|
| 3A | Entire core spell inventory; missing entries | Reconcile actual source lists/descriptions; add Alarm (Wizard 1), Bless (Priest 2), Fixed Object (Wizard 2), Fabricate (Wizard 3), with exact passages and verified memberships |
| 3B | SD pp.57/319 identity | Migrate `spell_control_weather` to `spell_control_water`; Priest and Wizard tier 4; redirect old ID and update all affected current references without rewriting history |
| 3C | Entire SD p.70 packet/layout | Sending Wizard 3, Shapechange Wizard 5, Shield of Faith Priest 1; preserve Scrying Wizard 5 and correct nonclassification claims |
| 3D | SD pp.54-62 and core classification reconciliation | Repair missing class/tier offerings against complete lists; do not stop after the four missing spells or force list hubs into leaf-spell roles |
| 3E | P0 authority/applicability safety | Exact passage links for claims in the trusted release scope; Fatality Mode inactive unless explicitly enabled; unverified/ambiguous claims not served as authoritative |

Use audit counts to locate work, not as a fixed patch size. The 31/61 spell gaps
span source scopes; reconcile supplement cases in Phase 4 rather than attributing
all of them to core pp.54-62. Give each actual packet one active owner and route.

**Exit:** P0 corrections independently approved and integrated; complete core
inventory accounted for; tested identity redirects; correct page-70 attribution;
applicability safety demonstrated. No authoritative-answer claim for books or
claims whose provenance backfill is still incomplete.

### Phase 4: Complete P1 and Retroactive Coverage

**Prerequisite:** Phase 2 support; execute after prioritized Phase 3 repairs.

- Analyst inventories all previously processed Shadowdark material and assigns
  each packet a route: `ENRICH_EXISTING`, `REEXTRACT_SOURCE`, `RENAME_IDENTITY`,
  `RECONCILE_CROSS_PACKET`, or `REVIEW_MANUALLY`. Retain original packet IDs.
  Reconstructed location groupings are provisional, not invented historical IDs.
- Assign entity roles before classifying the 122 item-gap candidates. Handle
  generic types, categories and lists separately from named definitions. Allow
  source-backed multiple functional/magical classifications.
- Add weapon taxonomy and source-backed class-specific permission sets, covering
  the audited 26 weapon entries and 12 class rules without confusing proficiency
  with permission or inferring permission from category membership.
- Reconcile Priest/Wizard/Witch/Seer offerings and list mechanics across core and
  CS books. Preserve book availability separately from optional activation.
- Backfill exact passages, claim/packet lineage and review states across the
  release corpus; quarantine unsupported authoritative claims pending source work.
- Repair the 23 label candidates where evidence is unambiguous; explicit
  exceptions otherwise. Preserve aliases without guessing canonical identities.
- Source-verify conditions and claim-targeted overrides. Inspect tavern/table
  memberships and each isolate; record intentional disconnection, never force links.

**Exit:** corpus reconciliation complete for the declared scope; all repair diffs
approved; no unexplained loss, role-classification gaps, high-severity conflicts,
or unreviewed inventory omissions. Unresolved references have structured debt
records and are not passed off as complete definitions.

### Phase 5: Retrieval Correctness and Release Qualification

**Owner:** Builder on assigned retrieval surface; Reviewer independently validates;
Integrator publishes versioned exports. **Prerequisite:** repaired approved corpus.

Implement exact/alias lookup, keyword/semantic fallback, typed bidirectional
traversal, intent-sensitive category/list expansion, applicable exception retrieval,
and exact source passage fetch. Never answer from edge labels alone or interpret
absence of an edge as proof that a rule does not exist.

Separate searchable information from active play rules. Test disabled/enabled
Fatality Mode, missing definitions, possession predicates, class equipment rules,
and focus-under-damage without retrieving unrelated spell catalogs.

**Exit:** all applicable deterministic gold cases pass; source/relation/scope/
citation/adjudication failures reported separately. Publish a versioned release
with baseline-to-release diffs, approvals, metrics, debt and rollback instructions.
Regenerate all graph/CSV/degree products from canonical state, never patch exports
independently. Keep candidate data out of the live serving view until approved.

### Phase 6: P2 Generalization, Then P3 Performance

**Owner:** Architect defines edition/profile contracts; Builder implements;
Reviewer validates; Integrator owns any future canonical publication.

- Make source inventory, vocabulary, offerings and permissions ruleset-profile
  driven. No hardcoded Shadowdark page ranges/classes/tier counts in shared logic.
- Exercise 2014/2024 isolation and proficiency/feature exception fixtures. This is
  compatibility validation, not authorization to ingest 2014. Scope 5e expectations
  to admitted books, not an SRD assumed to be the full Player's Handbook.
- Preserve independent edition/errata identities and explicit cross-edition links.
  Future application overlays retain the owner's order: campaign > setting >
  selected optional rules > core; edition identity is not an optional-rule layer.
- Only after correctness: compare graph-only, search-only and combined retrieval;
  measure recall, citation accuracy, answer correctness, latency and token cost
  separately. Evaluate stable-core caching as a hypothesis, not a requirement.

**Exit:** profile/isolation tests pass before 5e graph onboarding; performance
recommendations have measured evidence, not assumed graph-only superiority.

## 5. Complete Defect-to-Work Crosswalk

Priorities below preserve the CSV. The specification additionally elevates exact
passages and optional-mode safety into the P0 trusted-answer gate. Deliver those
parts early without silently changing the register. D5-017 remains CSV P1 but
is scheduled in the specification's P2 readiness phase, before 5e onboarding.

| Defect | Priority | Delivery | Primary change owner(s) | Closure evidence |
|---|---|---|---|---|
| SD-001 | P0 | 3A | Analyst / Builder | Four defined spells, source spans, classifications; complete list reconciliation |
| SD-002 | P0 | 3B | Architect identity authority; Builder migration; Integrator apply | One Control Water identity, complete incoming/outgoing-reference migration, old-ID redirect, preserved provenance |
| SD-003 | P0 | 3C | Analyst / Builder | Sending Wizard 3 and correct entry span |
| SD-004 | P0 | 3C | Analyst / Builder | Shapechange Wizard 5 and correct entry span |
| SD-005 | P0 | 3C | Analyst / Builder | Shield of Faith Priest 1; Scrying and valid neighbors preserved |
| SD-006 | P0 | 3D + 4 | Analyst / Builder | Core and supplement offerings reconciled separately; reviewed reference-only exceptions |
| SD-007 | P1 | 1 + 2 + 4 | Architect model; Analyst roles; Builder normalization | No blanket leaf assignment; source-backed functional/magical types |
| SD-008 | P1 | 4 | Analyst / Builder | Weapon categories plus actual permitted sets; source-backed equipment retrieval |
| SD-009 | P1 | 4 | Analyst / Builder | Coupled spell/list/tier offerings, multi-list support and reachable list mechanics |
| SD-010 | P1 | 1 + 2 + 3E + 4 | Architect contract; all pipeline owners | Exact passage joins and packet/generator/Review lineage for every authoritative claim |
| SD-011 | P1 | 1 + 2 + 3E + 4 | Architect applicability; Builder implementation | Availability/activation/possession/condition separated; Fatality Mode opt-in |
| SD-012 | P1 | 4 | Analyst / Builder | Label/alias evidence or explicit reviewed exceptions for all candidates |
| SD-013 | P1 | 1 + 2 + 4 | Architect claim identity; Builder / Integrator | Overrides resolve the intended scoped claim, not an ambiguous triple |
| SD-014 | P1 | 4 | Analyst / Builder | Source-backed table links or documented intentional isolates/debt |
| SD-015 | P0 | 1 + 2 + 3A + 4 | Analyst manifest; Builder gate | Independently omitted source entry blocks packet and corpus publication |
| UNIV-016 | P0 | 1 + 2 + 5 | Architect; Builder / Integrator; Reviewer verification | All hard publication gates enforced, including negative tests |
| D5-017 | P1 | 6 | Architect / Builder | Edition isolation, proficiency versus use, scoped feature exceptions |

Reviewer verifies every closure; Integrator applies only approved data changes.
No issue is closed merely because its implementation report exists.

## 6. Migration Safety and Status Tracking

AGY should create `execution/STATUS.md` and a machine-readable issue ledger in
this audit directory. These are program trackers, not replacements for existing
governed artifacts or queue semantics. Every entry must identify:

- defect ID; current state; owning role; exact affected packet/book/source scope;
- prerequisite and next action; blocking Decision/ESC ID if any;
- selected remediation route and baseline version;
- implementation/GUR/GUP/Review/Integration/release artifact paths as applicable;
- regression IDs, run command/result evidence, and unresolved exception disposition.

Suggested states: `planned`, `authority_pending`, `ready`, `in_progress`,
`review_required`, `integration_ready`, `blocked`, `verified_closed`, `deferred`.
These tracker states do not grant authority. A deferred test is not a passed test.

Each staged repair needs added/changed/deleted node and claim diffs, reason codes,
exact source evidence, baseline checksum preconditions, and explicit Review for
deletions, merges and permission changes. Fail stale-base application rather than
blindly applying an old patch. Integrator proves rollback in an isolated copy,
including schema/sidecars/redirects/index products, before the first live migration.

Maintain current-state redirects separately from immutable historical artifacts.
Unknown source, unresolved printing, unavailable definition, or interpretive
condition stays visible with owner and reason. Such debt cannot silently waive a
hard release gate or mark a required defined entity excluded merely to pass tests.

## 7. Regression Crosswalk: Preserve Both Audit Lists

The Markdown section H and JSON have different identifiers and partly different
coverage. Use namespaced keys `spec:<id>` and `json:<id>`; retain both and map by
assertion meaning. Do not replace or renumber the supplied artifacts.

| Markdown specification ID | JSON case(s) | Execution requirement |
|---|---|---|
| SD-INV-01 | SD-INV-01 | Complete core inventory, four omissions, corrected identity and spans |
| SD-SPL-02 | SD-SPL-02 | All p.70 corrections; Scrying unchanged |
| SD-SPL-03 | SD-SPL-03 | Control Water dual-list tier 4, p.57/p.319, old-ID redirect |
| SD-SPL-04 | SD-SPL-04; SD-SPL-09 | Keep JSON armor/Sleep and Priest/Burning Hands checks; add specification's Fireball/Cure Wounds/Witch/Seer offering coverage |
| SD-ITEM-05 | SD-SPL-04; SD-ITEM-05 | Both wizard/plate and wizard/greatsword; source text, no category-only permission |
| SD-ITEM-06 | No direct JSON counterpart | Add magic armor/weapon functional and magical taxonomy case |
| SD-REL-07 | SD-REL-06 | Focus under damage with bounded relevant retrieval |
| SD-VAR-08 | SD-VAR-07; SD-VAR-08 | Both disabled and enabled variant directions |
| SD-QA-09 | No exact counterpart | Add unknown-name lookup/fallback/no-invention case; retain separate JSON SD-SPL-09 absence-of-edge test |
| SD-QA-10 | SD-QUAL-10 | Replay twice, stable identities, no duplicates, second diff empty |
| D5-ED-01 | D5-ED-13 | Same-name cross-edition isolation and revision citations |
| D5-PROF-02 | D5-PROF-14 | Weapon usability versus proficiency, scoped to edition |
| D5-MULTI-03 | No direct JSON counterpart | Add multiclass/feat/subclass prerequisite and applicable exception coverage |
| UNIV-TBL-04 | UNIV-TBL-12 | Columns, table headers/rows, nested exceptions and exact spans |
| UNIV-COV-05 | UNIV-SRC-11 | Deliberately omit a required manifest entry; publication fails |
| UNIV-SCOPE-06 | SD-VAR-07; SD-VAR-08 | Extend beyond variants to entity absent and predicate unknown/false |
| No direct Markdown counterpart | UNIV-REF-15 | Mention-only spell: no invented definition/tier, explicit evidence limitation |

Tests must assert the supplied assertions, not only that IDs exist. Reviewer
records missing source, wrong node, wrong relation, wrong applicability, wrong
citation and wrong adjudication separately. Add preservation tests for valid
parallel claims and exporter consistency under the audit's change-safety gate.

## 8. Ready-to-Paste AGY Kickoff

```text
Repository: D:\analysis\dnd

Execute audit.11.04.2026/AGY_REMEDIATION_EXECUTION_PLAN.md using the existing
five role boundaries. The owner accepts the three supplied audit inputs;
do not re-audit the findings or produce another competing assessment.

Start with Phase 0: map the accepted requirements to actual components and
artifact IDs, bind the current baseline, and create execution/STATUS.md plus
the issue ledger. Architect then publishes the bounded Phase 1 authority.
Do not jump directly to classification patches or canonical edits.

Track all 17 defects and both regression ID sets. Preserve valid graph work,
immutable artifacts and exact evidence. Only Integrator writes canonical.
Keep Shadowdark remediation first; no 2014 ingestion or orchestration rewrite.

At each completed step, update durable status and provide the permitted next
role with the exact artifact, priority, prerequisite and next action. Select one
next packet at a time through the normal relay. Escalations return to their
originator after an Architect ruling; blocked work does not advance.

Report completed steps, tests actually run, remaining blockers, and the next
ready owner. Do not call a defect closed on self-tests or a notification alone.
```

## 9. Planning Validation

This plan covers every supplied CSV issue ID, every JSON case ID, and all
Markdown section H cases, including requirements absent from the JSON list.
No audit finding was re-derived, no graph/source repair performed, no tests
reported as passed, and no agent notification or live queue operation performed.
The listed implementation locations are routing starting points, not certified
root causes. Phase 0 is the bounded implementation mapping required by the audit.
