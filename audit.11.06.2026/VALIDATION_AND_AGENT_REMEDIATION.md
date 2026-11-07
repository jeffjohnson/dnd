# November 6 Audit: Local Validation and Agent Remediation

Validated locally: 2026-11-07. Role: Architect. Status: findings and recommended
work assignments, not a published Decision, implementation approval, or data patch.

## Verdict

The brief's principal outstanding findings reproduce against the current local
canonical graph and registered packet copies. The previous remediation improved
coverage, but its "all closed" and production-readiness claims are not supported
by the checks performed here. Preserve the improvements; do not rebuild the graph.

Most importantly, **19 existing remediation tests pass while the defects remain**.
Eight tested retrieval methods produce identical results with an empty graph and
with the live graph. Fix the evidence and test paths, not merely the reported counts.

## Evidence and Limits

- Input: `Shadowdark_Rules_Graph_Source_Reconciliation_Brief.md` in this directory.
- Canonical: `rulesets/shadowdark/canonical/{graph.json,nodes_master.csv,edges_master.csv}`.
- Baseline: `build/snapshots/INT-20261104-BASE/graph.json`.
- Source comparisons use actual incoming packets; the three spell-list packets
  and two page-70 packets were also compared to their claimed `source.md` copies
  and are byte-identical. `sd_resources` was not treated as canonical authority.
- The brief's four complete book files and their supplied hashes were not reproduced
  here. Matching local packet passages support the findings, not a claim that the
  remote whole-book snapshots are identical to local sources.
- CS2 and all individual mechanics across the corpus have NOT been exhaustively
  verified. No source page images were inspected. Column/OCR causation remains
  unproven; inconsistent text is confirmed.
- The read-only probe uses Pandoc's JSON AST for bounded spell-list parsing, with
  one explicit diagnostic Judgment/Judgement alias. It does not register aliases,
  extract production GURs, or replace the governed source inventory implementation.
- `local_validation_results.json` contains complete list rows, missing links,
  extra rows, taxonomy-only node lists, hashes and the existing test transcript.
  `remediation_register.json` supplies the role-assigned issue register.

Reproduce:

```powershell
python audit.11.06.2026/validate_local_findings.py --output audit.11.06.2026/local_validation_results.json
```

This executes the 19-test remediation suite and diagnostic probes, not migration
scripts. It writes only its requested audit JSON (and ordinary Python caches).
It requires installed Pandoc and the repository's Python dependencies.

## 1. Validation Results

| Finding | Local result | Disposition |
|---|---|---|
| Revised graph size | 737 nodes, 1,801 edges | Confirmed |
| Original snapshot | 732 nodes, 1,498 edges; `meta` present | Confirmed |
| JSON/CSV parity | Current common exported fields match as multisets | Confirmed; parity is not semantic correctness |
| Structural integrity | Zero dangling endpoints; components 733 and 4; zero raw-ID labels | Confirmed improvements |
| Core spell inventory | 90 class-list entries resolve to 85 distinct nodes | Confirmed; 90 offerings is not 90 distinct spells |
| Core unexpected classes | Hold Person and Dispel Magic each have an unsupported SD Priest edge | Confirmed, CSV lines 1276 and 1213 respectively |
| Witch inventory | 46 entries; only 36 Witch memberships; ten missing | Confirmed exact names and tiers below |
| Seer inventory | 20 entries, all class/tier links present | Confirmed taxonomy, not mechanics completion |
| No incident non-classification edges | 38 Witch, 20 Seer, all four newly added core spells | Confirmed warning/review trigger, not proof that every spell needs an edge |
| Additional core mechanics-review candidates | Nine core-list spells are taxonomy-only in total | Five beyond the four identified in the brief, listed below |
| Page-70 source contradictions | Sending says Wizard 5; Shapechange Priest 1; Shield of Faith Wizard 3 | Confirmed in incoming AND claimed packets; graph list classifications are corrected |
| Alias mismatch | Source Judgment resolves to graph `spell_judgement` with explicit comparison alias | Confirmed; do not create a duplicate |
| Override addressing | Five `OVERRIDES` set `general_rule_id` equal to target node ID | Confirmed, not claim-addressability |
| Export metadata | Live graph has only `nodes` and `edges`; node CSV no longer has `roles` | Confirmed; decide compatibility, do not blindly restore blank roles |
| Claim/passages/roles | Zero populated claim/edge IDs, passage IDs or `entity_role` fields in current graph export | Export deficiency confirmed; historical artifact lineage is a separate matter |

The nine core taxonomy-only spells are Alarm, Alter Self, Augury, Bless, Fabricate,
Fixed Object, Knock, Passwall and Restoration. Alter Self and Augury overlap the
Witch list; these counts must not be summed as disjoint populations. No minimum
degree requirement is recommended. Each needs an evidence-backed extraction status.

### Exact Near-Term Correction Proposal

These are candidate source-grounded operations, not an executable migration.
Pin full before-rows and current graph hashes before packaging the changes.

**Remove only the two unsupported SD class claims:**

| Subject | Predicate | Target | Current source locator | Preserve |
|---|---|---|---|---|
| `spell_hold_person` | CLASSIFIED_AS | `class_priest` | SD / 54 / SPELLS, casting class, empty condition | Wizard, tier 2, all valid mechanics and other scoped grants |
| `spell_dispel_magic` | CLASSIFIED_AS | `class_priest` | SD / 54 / SPELLS, casting class, empty condition | Wizard, tier 3, all valid mechanics and other scoped grants |

The full rows are in `local_validation_results.json` under
`inventories.SD.extra_scoped_class_edges`. CSV line numbers are diagnostic only,
not migration identity. Lists in packet 019 and detail headers in packets 023
(Hold Person) and 022 (Dispel Magic) independently agree on Wizard-only core scope.

**Add ten CS1 Witch memberships; retain other class memberships:**

| Node | Witch tier | List page from current packet markers |
|---|---:|---:|
| spell_charm_person | 1 | 24 |
| spell_alter_self | 2 | 24 |
| spell_augury | 2 | 24 |
| spell_invisibility | 2 | 24 |
| spell_speak_with_dead | 3 | 24 |
| spell_dimension_door | 4 | 24 |
| spell_divination | 4 | 24 |
| spell_polymorph | 4 | 24 |
| spell_scrying | 5 | 25 |
| spell_shapechange | 5 | 25 |

Use CS1 list evidence and the governed offering model. A tier node already linked
from another source is not a complete source-scoped offering. Verify shared spell
descriptions before assuming their effects are identical across books. Do not
overwrite other classes or copy the core spell's detail page as CS1 provenance.

## 2. Root Causes and Additional Risks Found Locally

### R01: Migration introduced the two false Priest claims (P0, confirmed code path)

`tooling/integrator/src/adnd1e_integrator/remediation_migration.py:85` and `:96`
hardcode Priest alongside Wizard for Hold Person and Dispel Magic. The migration
adds those memberships. This is more specific than blaming an unknown extractor.
Correcting canonical rows without correcting/retiring this path risks recurrence.

The same file assigns page 54 to most added core class/tier edges (`:252`), even
though its stated evidence is the spell lists on pp.51-53. Therefore new provenance
must be derived from exact entries, not this default. Review all rows produced by
that migration for citation support, not only the two erroneous classes.

### R02: Gap-driven migration misses shared memberships (P0, confirmed design)

`batch_4b_supplement_spells_migration.py:51` loops over `classification_gaps.csv`,
selects the class from an existing tier edge's book, and never reconciles the
complete Witch list. Batch 4A explicitly drops core-classified spells from that
gap file. Batch 4B then writes an empty gap file rather than recomputing complete
source-scoped obligations. Thus "zero gaps" is not evidence of 46/46 Witch coverage.

Both migration paths use subject/type/target-only duplicate keys, losing the
ability to distinguish valid same-triple source/condition/aspect claims. Preserve
the governed full assertion/provenance identity in replacement tooling.

### R03: Taxonomy completion was mistaken for mechanics review (P0 review trigger)

Core missing-node repair creates nodes and class/tier edges, not a description
extraction pass. Supplement repair does likewise. The structural trigger is
confirmed; whether each source supports additional modeled relationships must be
decided through Analyst extraction and independent Review, not by this report.

### R04: Source contradictions survive repaired classifications (P0)

`026-spells-prophecy-to-shapechange.md:95` and `:103`, plus
`027-spells-shield-of-faith-to-turn-undead.md:9`, retain conflicting headers.
Duration and range fields in those same blocks also warrant page-image verification;
do not infer a rotation or silently rewrite them. Hold affected mechanics claims
until the disputed source attributes have a governed resolution. Preserve both
list and detail evidence and immutable original packets.

### R05: Existing retrieval tests validate canned answers (P0)

`tooling/builder/src/adnd1e_builder/rules_retrieval.py` returns embedded prose,
fixed outcomes and success flags rather than fetching retained source passages.
Eight public query methods returned identical answers with no graph loaded.

Examples of consequential divergence:

- Wizard query wrappers return page 44 (`:233`, `:243`); the actual Wizard class
  packet declares page 24. Embedded prose itself uses page 23.
- Focus helper (`:81`) invents a Constitution/DC formula; its wrapper says the
  spell ends immediately. The actual focus passage in packet 018, p.50, requires
  an immediate spellcasting check when damaged or distracted, not automatic ending.
- Fatality wrapper reports page 89 (`:270`), its helper cites 97, while the packet
  and graph locate Fatality Mode on p.111.
- `get_reference_only_entry` (`:213`) labels any supplied node reference-only;
  the regression uses Wish even though Wish is on the loaded core list and has
  a source description. This is not genuine missing-definition handling.

Do not present this engine as authoritative retrieval. Treat these methods as
prototype fixtures until replaced with evidence-backed lookup and applicability.

### R06: Manifest helper is not an enforced publication gate (P0)

Searches for `SourceEntityManifestGate` / `verify_packet_manifest_completeness`
found definitions and tests, but no invocation in the examined live compiler,
CLI, publication helper or Integrator admission path. The helper accepts an empty
manifest and checks missing IDs only; it cannot detect false-positive memberships.
This validates a helper, not the claimed end-to-end publication protection.

### R07: Passing tests do not establish the claims in closure notes (P0)

`tooling/reviewer/tests/test_remediation_regressions.py` ran 19/19 green. But:

- `:203` accepts at least 36 Witch spells, not the independent 46-entry set.
- The inventory test checks five named nodes and nonempty book/page fields, not
  complete inventory or exact spans.
- `:265` tests "replay" by rebuilding tuples from the same loaded graph, without
  invoking extraction, migration or integration twice.
- `:318` requires `general_rule_id == target_id`, proving node-level addressing
  rather than the required claim-level distinction.
- Retrieval tests assert the hardcoded outputs described above, including wrong
  source pages, and therefore cannot establish fidelity or edition isolation.

Reopen unsupported closure claims in the November 4 ledger. Keep genuinely
verified outcomes closed (identity presence, corrected list classifications, label
cleanup), but do not extend those successes to mechanics, provenance or retrieval.

### R08: Export and transaction path is unsafe to reuse unchanged (P1)

The remediation scripts construct `{nodes, edges}` afresh, explaining the lost
`meta`. Fixed CSV headers also drop fields. They directly write three canonical
files in sequence; the inspected runners do not route through the normal Approved
bundle transaction. A separate snapshot does not make these writes atomic.
Do not rerun them on live canonical state. Replace their repair behavior with a
reviewed, baseline-pinned migration through Integrator's governed transaction.

### R09: Decision evidence pins require reconciliation (P1)

All three current raw-byte evidence checksums named in DEC-2026-0109 disagree with
the referenced files. The defect CSV and regression JSON still have the hashes
observed on November 4; do not assume the mismatch is only later documentation churn.
This does not itself prove why the pins differ or invalidate every substantive
ruling. Architect must resolve exact evidence lineage through a successor Decision
or other governed correction, not edit the immutable Decision in place.

The Decision describes passage IDs, roles and offerings, but current exports lack
them. A prose authorization is not implementation evidence. Map schema, compiler,
review and export activation explicitly before declaring those clauses implemented.

## 3. Role-Specific Next Work

### Architect: First Governance Owner

1. Reconcile DEC-2026-0109's pins and define the exact corrective authorization;
   preserve it and its history. No new Decision ID is allocated by this report.
2. Govern bidirectional, source-scoped offering reconciliation; explicit alias
   handling; extraction outcomes (`extracted`, reviewed self-contained, unresolved);
   stable claim IDs and override targets; retained passage evidence; export metadata.
3. Set source-conflict handling: list/detail contradictions require both evidence
   loci and authoritative calibration, never last-text-wins. Resolve the page-70
   source route before new disputed mechanics are approved.
4. Require real pipeline admission checks and independent source-backed acceptance
   fixtures. Set exact file ownership for Builder and Integrator edits.
5. Issue a release-status correction limiting the existing release to verified
   scope. Do not call the graph a rules adjudicator or the corpus fully reconciled.

Deliver: bounded Decision(s), compatibility/activation sequence, named tests and
owners, and an explicit return to each originating work owner.

### Analyst: Evidence and Bounded Packet Successors

1. Produce independent scoped offering manifests from packet 019, CS1 21-38 and
   CS3 29-36, preserving list pages, tiers and source names. Expected counts are
   90 core offerings/85 identities, 46 Witch offerings, 20 Seer offerings for these
   specific snapshots, not hardcoded universal constants.
2. Prepare the two core deletions and ten CS1 additions with exact source spans.
   Retain other source-specific grants and explain each add/remove operation.
3. Raise the page-70 source contradiction with original packet checksums and both
   loci. Obtain steward/page-image evidence for tier, duration and range; do not
   modify published source or guess corrected attributes.
4. Review descriptions of four new core spells first, then the 38 Witch and 20
   Seer candidates, plus the remaining core warnings. Deduplicate overlapping
   candidates. Publish supported mechanics or an evidence-backed no-modeled-edge
   disposition; never add edges just to increase degree.
5. Record Judgment/Judgement and punctuation aliases as resolution proposals.
   No duplicate identity from naive slugging, and no unapproved canonical rename.

Packet anchors already identified:

- `PKT-SD-051-053-priest-and-wizard-spell-lists`
- `PKT-CS1-021-038-diabolical-mishaps-and-witch-spells`
- `PKT-CS3-029-036-magic-and-seer-spells`
- `PKT-SD-068-070-spells-prophecy-to-shapechange`
- `PKT-SD-070-072-spells-shield-of-faith-to-turn-undead`

Find current active GUR/Review successors before publication. Use one packet relay
at a time; this candidate list is not authorization to start all packets together.

### Builder: Real Reconciliation, Provenance and Retrieval

1. Implement bidirectional comparisons over source/class/tier/spell offerings,
   including already-registered/shared identities and unexpected extra memberships.
2. Wire the manifest and review-state checks into the real compile/publication
   path. Reject missing required inventory, not an empty-default success. Test
   ordinary public entry points, not only helper functions.
3. Preserve exact passage/claim identifiers and source version through artifacts
   and exports. Do not reduce duplicate keys to a bare triple.
4. Replace canned retrieval methods with graph plus retained-source lookup,
   activation predicates and explicit unavailable-evidence results. Empty/mutated
   evidence must change the outcome; eliminate fabricated text and page literals.
5. Compile approved source corrections into GUP/migration bundles. Hand code
   changes in Integrator-owned migration scripts to Integrator, not unilateral edits.

Deliver: scoped implementation report, focused and applicable existing tests,
real negative CLI/publication tests, and correction bundles for Reviewer.

### Reviewer: Replace Circular Evidence With Independent Tests

1. Pin source-derived expected offering sets independently of migration constants.
   Assert exact scoped set equality: missing AND extra. Retain true multi-source grants.
2. Add the new audit's 16 regression IDs (mapped below), not only the old count checks.
3. Verify source passage fetch and meaning, not presence of `book`/`page` strings.
   Empty graph/source, missing span, wrong page and changed source tests must fail
   closed or return explicitly unavailable evidence.
4. Execute replay twice in a temporary baseline copy, compare complete claims and
   provenance, and exercise injected integration failure/rollback. Comparing a
   loaded graph with itself is not a replay test.
5. Verify mechanics-review dispositions, source contradictions and aliases. Do not
   approve invented relationships or silently waived gameplay conflicts.
6. Reassess previous closure records with current evidence. Publish successor
   Reviews where needed; preserve prior immutable Reviews and their limitations.

Deliver: independent implementation/correction Reviews, executable negative
regressions and a scoped coverage report. No full-corpus claim from sampled edges.

### Integrator: Transactional Repair and Versioned Exports

1. Snapshot current canonical, registry/redirect state, exports and exact hashes.
   Preserve the November 4 baseline and release snapshots.
2. Retire the unsafe direct-write repair route from operational use. Implement
   only authorized migration fixes on the Integrator surface with dry-run diffs,
   stale-baseline refusal, complete backup/rollback and normal approval admission.
3. Apply only independently approved row removals/additions and identity/schema
   migrations. Preserve valid parallel claims and historical artifact references.
4. Restore governed export metadata/version; define compatibility for dropped
   roles rather than blindly reintroducing an empty column. Derive CSV and JSON
   together from canonical authority and verify parity plus all added fields.
5. Publish a revised scoped release and remaining-debt report after all required
   gates pass. Then notify Analyst to select the next permitted packet.

## 4. Sequence and Acceptance

**Immediate:** stop relying on the canned retrieval engine and "all 17 closed"
status as production evidence. Do not erase the graph or silently rewrite history.

**First:** Architect resolves authority/closure scope; Reviewer pins independent
fixtures; Analyst prepares source evidence. Then Builder/Integrator implement
authorized checks and transactional repair support. Reviewer approves those changes.

**Data sequence:** two unsupported Priest rows -> ten shared Witch memberships ->
four core mechanics reviews -> remaining Witch/Seer/core review candidates. The
page-70 conflict runs as a bounded escalation and gates only dependent work, not
unrelated verified membership corrections. Finish with corpus reconciliation and
the scoped release. Respect the existing normal role relay and correction routes.

| Brief regression IDs | Required acceptance evidence |
|---|---|
| SD-01, SD-02 | 85 core identities; exact source-scoped class/tier set; two false Priest rows absent |
| CS1-01, CS1-02 | All 46 Witch offerings; ten shared memberships restored with CS1 evidence |
| CS3-01, MECH-01, MECH-02 | All targeted descriptions have verified extraction/no-modeled-edge dispositions, not just taxonomy |
| SRC-01 | Conflict detector catches list/header discrepancies; final disputed attributes have authoritative evidence |
| ID-01 | Judgment/punctuation names resolve deliberately; no false missing or duplicate identities |
| EVID-01 | Claims retrieve exact supporting retained spans; missing/wrong span fails |
| CLAIM-01 | Same-node claims with different aspects/conditions remain independently addressable |
| OPT-01 | Disabled variants discoverable but inactive; tested with data, not canned booleans |
| EXP-01 | Versioned metadata and full exported-field parity, including newly governed provenance |
| REPLAY-01 | Actual pipeline applied twice in isolated state: no duplicates or second semantic diff |
| DND-01, DND-02 | Real edition/profile fixtures and proficiency-vs-permission evidence; no 2014 ingestion implied |

CS2 and other processed content need the same source-backed inventory and risk-
prioritized semantic verification subsequently. Their completeness was not tested
here. The recommendations do not resume unrelated RC work or change 5e scope.

## 5. What Was Not Done

No source packets, canonical data, migration code, contracts, published Decisions,
Reviews or prior closure reports were changed. No migration script was executed.
No AGY notification was sent; use this report as the handoff. The diagnostic JSON
and script are audit aids, not production gates or approval artifacts.
