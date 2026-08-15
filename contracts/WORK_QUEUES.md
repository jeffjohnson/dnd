# Agent Work Queue Contract

**Version 1.9.**

## Purpose

This contract defines how repository artifacts become work for a role. Artifact
directories are durable, append-only stores. They are not inboxes merely because
they are named `gur`, `gup`, `reviews`, or `approved`.

Queue state is derived from machine-readable artifact lineage. Do not move or
rewrite a published artifact to signal that another role consumed it. Published
paths and checksums are provenance and must remain valid.

## Core Rules

1. One logical artifact bundle is one work item.
2. The primary YAML artifact supplies the bundle ID. Companion CSV and validation
   files with that base ID are components, not separate jobs.
3. Only the active leaf revision of an artifact can create work.
4. A revision is a leaf when no later artifact of the same kind names its ID in
   `supersedes`.
5. A downstream artifact consumes its input by recording the exact upstream ID
   and checksum in provenance.
6. Superseded, consumed, reviewed, integrated, failed, and blocked artifacts are
   not ready work for the ordinary downstream role.
7. Filesystem modification time never determines workflow order.
8. A role must not move, rename, overwrite, or delete an upstream artifact after
   publication.
9. A GUP has one lineage root selected by `artifact_kind`: `packet_update` or
   `decision_migration`. A declared kind is never reinterpreted to make an
   invalid artifact appear ready.
10. New GUPs must declare `artifact_kind`. Legacy omission may be inferred as
    `packet_update` only when valid GUR provenance exists, and the inference must
    be reported.
11. `packet_id` is scope metadata, not a decision-migration revision key.
    Decision-migration revisions are grouped by their stable `lineage_id`.
12. A later approved Architect Decision may replace the ready handoff of the
    artifact that raised its escalation. The original artifact remains immutable;
    queue tooling derives the current handoff from the Decision lineage.
13. A non-migration Architect Decision assigned to Builder is complete only when
    an Approved Decision Implementation Review consumes the exact active
    implementation-report leaf. File state or passing tests alone never imply
    completion.

## Decision Handoff Replacement

An approved Architect Decision replaces an originating artifact's ready handoff
only when all of these conditions hold:

1. the Decision's `escalation_id` resolves to a package under the same ruleset's
   `escalations/decided/` directory;
2. that package's `originating_artifacts` explicitly names the artifact ID and
   repository path whose handoff is being replaced;
3. the named artifact is still the active leaf of its kind; and
4. the Decision has an explicit `handoff` block.

Queue tooling must suppress the originating artifact's earlier ready item. It
then applies the Decision handoff as follows:

- `readiness: ready` routes the Decision to `handoff.next_role` under the
  applicable role rule;
- `readiness: blocked` produces blocked state, never ready state, and preserves
  the Decision's `blocking_ids`;
- `readiness: terminal` produces no downstream work.

This rule does not rewrite, delete, or supersede the originating artifact. It
changes queue state because the Architect has resolved the question that caused
the earlier handoff. Free-text references do not replace a handoff: the decided
escalation must supply the exact originating artifact ID and path. A Decision
that does not satisfy this section leaves the existing artifact handoff intact.

When multiple eligible Decisions name the same active artifact ID and path, only
the later Decision applies. Order candidates by `decision_date`, then Decision
ID as a deterministic tie-breaker; never use filesystem timestamps. The scanner
reports the effective Decision and ignores earlier replacement candidates for
that artifact.

When the Decision is already visible as a ready item for the same role, the
replacement does not create a second item for the originating artifact. The
Decision is the one logical coordination job; independently ready packet GURs or
other input bundles remain separate jobs.

## Required Handoff Metadata

New GURs, GUPs, Reviews, Approved bundles, Decision Implementation Reports,
Decision Implementation Reviews, and Integration records must contain:

```yaml
revision: 1
supersedes: null
handoff:
  next_role: builder
  readiness: ready
  reason: analyst extraction complete
  blocking_ids: []
```

`next_role` is one of `analyst`, `builder`, `reviewer`, `architect`,
`integrator`, or `none`.

`readiness` is one of:

- `ready` - the named role can act immediately;
- `blocked` - the named role cannot act until every `blocking_id` is resolved;
- `terminal` - no downstream work remains from this artifact.

For revision 2 or later, `supersedes` is required and names the immediately prior
revision. Revision chains must not fork. A replacement artifact must preserve the
original input provenance and state why a revision was needed.

Legacy artifacts without this block remain valid. Queue tooling must apply the
legacy rules below and report that inference in diagnostics.

## GUP Lineage Roots

### Packet update

A packet update declares `artifact_kind: packet_update` and consumes one GUR.
Its provenance contains the exact active-leaf `gur_id` and `gur_checksum`. The
existing packet-based Builder and Reviewer rules apply.

Legacy GUPs without `artifact_kind` remain packet updates only when this GUR
lineage is recoverable. `stale_gup_input` is reserved for packet updates whose
GUR is missing or no longer the active leaf.

### Decision migration

A decision migration is a GUP planned directly from one or more approved
Architect Decisions. It does not have a GUR and must not include `gur_id` or
`gur_checksum`. Its minimum lineage envelope is:

```yaml
artifact_kind: decision_migration
lineage_id: MIG-DEC-2026-0015-0016
revision: 2
supersedes: GUP-MIG-DEC-2026-0015-0016-r01
authority: [DEC-2026-0015, DEC-2026-0016]
provenance:
  decision_inputs:
    - id: DEC-2026-0015
      path: rulesets/adnd1e/escalations/decisions/DEC-2026-0015.yaml
      checksum: sha256:<hex>
    - id: DEC-2026-0016
      path: rulesets/adnd1e/escalations/decisions/DEC-2026-0016.yaml
      checksum: sha256:<hex>
  canonical_source: rulesets/adnd1e/canonical/edges_master.csv
  canonical_checksum: sha256:<hex>
  canonical_rows_read: 3815
  registry_source: rulesets/adnd1e/registries/nodes.csv
  registry_checksum: sha256:<hex>
  registry_rows_read: 1097
validation_report: build/reports/GUP-MIG-DEC-2026-0015-0016-r02.validation.json
validation_report_checksum: sha256:<hex>
```

The following conditions are mandatory:

1. `lineage_id` is stable across every revision and separates independent
   migrations even when they share `packet_id: cross-packet`.
2. `authority` is non-empty and contains unique Decision IDs.
3. `provenance.decision_inputs` contains exactly the same Decision IDs, plus
   repository paths and SHA-256 checksums that match the current immutable files.
4. Every authority Decision exists, has `status: approved`, belongs to the same
   `ruleset_id`, and declares `migration_required: true`.
5. The canonical source path, SHA-256 checksum, and row count identify the exact
   baseline used to plan the migration. If that baseline changes, the GUP is
   stale and Builder must issue a new revision.
6. Every canonical mutation carries enough before-state and delta information
   for independent Review. A Decision ID alone never substitutes for the rows to
   be reviewed.
7. The validation report exists as a bundle component and its checksum matches.

A structurally invalid decision migration is not Reviewer-ready and does not
consume its authority Decisions for Builder queue purposes. Queue tooling reports
an error diagnostic specific to decision-migration lineage; it must not report
`stale_gup_input` merely because no GUR exists.

### Direct decision-migration operations

`operation_model: decision_migration_v1` is the narrow executable model for a
Decision migration that has no edge-CSV representation. It applies only these
operations, all carried in the reviewed GUP YAML:

1. `node_changes.additions_proposed`: register a previously absent approved node;
2. `node_changes.replacements`: replace one registry identity and retire its old
   ID without creating an alias;
3. `canonical_changes`: repoint one enumerated canonical endpoint and its paired
   label by exact compare-and-swap; and
4. `canonical_removals`: remove one exact, complete canonical before-image with
   `replacement_edge: null`.

The GUP must pin the node registry as well as the canonical edge baseline. Each
replacement lists the complete incident canonical-row set measured against those
baselines. Each repoint supplies all 18 canonical fields in `before`, changes
only one endpoint ID and its matching label, and declares the old and new value
for both fields. Each removal supplies the full 18-field before-image. Direct
operations are never copied into an Approved manifest, inferred from a retired
ID, or broadened to another row.

`operation_model: decision_migration_v2` is a separate, equally narrow model
for a bounded node-ID merge that cannot be represented by a sequence of v1
replacements. It has the same checksummed GUP/Approved-manifest form as v1, but
its plan may contain only:

1. one or more `node_changes.merges`, each consolidating at least two retired
   registry IDs into one previously absent canonical ID;
2. the complete, enumerated paired endpoint repoints for those retired IDs; and
3. empty `additions_proposed`, `relabels`, `replacements`, and
   `canonical_removals` arrays.

Every merge names its canonical ID, label, and kind; every retired ID, label,
and one-based registry row; `registry_action:
merge_retired_rows_into_one`; `require_no_remaining_retired_endpoints: true`;
its authority Decision; and its complete incident canonical-row set. Before
planning, the canonical ID must be absent, every retired node must match its
declared registry row and label, and every discovered endpoint using a retired
ID must equal that merge's declared incident set. Each incident row is exactly
one paired endpoint-ID/label repoint with a full 18-field before-image. The
Integrator replaces all retired registry rows with exactly one canonical row,
creates no alias, and rejects the transaction if any retired ID remains in the
registry, canonical endpoints, or derived outputs.

Version 2 does not authorize a label-only edit, a one-to-one replacement, an
alias, a removal, a non-endpoint mutation, an inferred incident row, or any
other merge shape. Version 1 remains unchanged and cannot be used for a merge.

The Reviewer must independently verify the two baseline checksums, every
before-image, each replacement's complete incident set, the resulting absence of
retired endpoints, and absence of duplicate assertion keys. It may emit an
Approved bundle only when the manifest declares:

```yaml
artifact_kind: decision_migration
operation_model: decision_migration_v1 # or decision_migration_v2
components:
  - kind: decision_migration
    path: books/<ruleset>/<book>/artifacts/gup/<gup-id>.yaml
    checksum: sha256:<exact reviewed GUP checksum>
  - kind: validation
    path: build/reports/<gup-id>.validation.json
    checksum: sha256:<exact report checksum>
```

The manifest's `approves.gup_checksum` and `approves.review_checksum` are
mandatory for this model. An edge CSV is forbidden in this bundle shape. The
Integrator reads the operation plan only from the checksummed GUP component and
rejects a manifest whose plan, Review, Decision inputs, canonical baseline, or
registry baseline does not match exactly.

### Architect Decision Reissue

Architect Decisions are immutable. When a published Decision's executable
migration instructions need correction, the Architect publishes a new Decision
with a new `DEC-YYYY-NNNN` ID; it does not rewrite the earlier Decision. The
reissue uses the ordinary envelope fields to form one unforked Decision lineage:

```yaml
id: DEC-2026-0031
revision: 2
supersedes: DEC-2026-0030
```

A valid Decision reissue must name an existing approved Decision from the same
ruleset as its immediate `supersedes` predecessor. It must preserve the
predecessor's `migration_required` value. Its ruling must state the correction
and, where it directs a migration, enumerate the complete replacement operation
set; a migration must cite the active reissue only, never both it and a
superseded predecessor. A reissue may not be used to erase history or silently
broaden a Decision's scope.

For queue derivation, only the leaf of a valid Decision reissue lineage creates
Builder work or can be consumed as decision-migration authority. The scanner must
validate the predecessor exists, is approved, has the same ruleset and migration
flag, and has no more than one direct successor. An invalid reissue is a lineage
error and does not suppress either Decision's otherwise-ready work. The
superseded Decision remains at its original path and is retained as immutable
history.

`identity_merge_migration` is a legacy spelling found in earlier Builder output.
It remains immutable history but is not a third lineage root and is not
Reviewer-ready as written. A Builder revision may supersede it using
`artifact_kind: decision_migration` and the complete current envelope.

Queue discovery covers both book-scoped GUP stores and ruleset-scoped
`rulesets/<ruleset-id>/cross-book/` stores. Scope location does not change the
lineage checks.

## Non-Migration Decision Implementations

An approved Architect Decision with `handoff.next_role: builder`,
`handoff.readiness: ready`, and `migration_required: false` is a non-migration
Builder Decision. It is not consumed by a GUP. Its completion lineage has one
Decision Implementation Report and one independent Review.

### Builder report

Builder publishes one report lineage per Decision under:

```text
rulesets/<ruleset-id>/decision-implementations/
```

The minimum envelope is:

```yaml
id: IMP-DEC-2026-0022-r01
artifact_kind: decision_implementation
status: proposed
revision: 1
supersedes: null
approval_ready: true
decision_input:
  id: DEC-2026-0022
  path: rulesets/adnd1e/escalations/decisions/DEC-2026-0022.yaml
  checksum: sha256:<hex>
implemented_by: builder
implementation_files:
  - path: tooling/common/scan_agent_queues.py
    checksum: sha256:<hex>
acceptance_results:
  - acceptance_test_index: 1
    result: passed
    evidence: exact repository evidence or test result
validation:
  passed: true
  commands:
    - command: python -m unittest discover -s tooling/common/tests
      exit_code: 0
      result: passed
      summary: complete suite passed
handoff:
  next_role: reviewer
  readiness: ready
  reason: every Decision acceptance test is implemented and evidenced
  blocking_ids: []
```

The following conditions are mandatory:

1. One report consumes exactly one Decision. Combined reports are forbidden.
2. The Decision exists, is approved, belongs to the same ruleset, has a ready
   Builder handoff, declares `migration_required: false`, and contains a
   non-empty `acceptance_tests` list.
3. `decision_input` records the exact Decision ID, repository path, and current
   SHA-256 checksum.
4. `implementation_files` is non-empty. Every path exists and every checksum
   matches. The list accounts for every file the Decision requires Builder to
   change or verify.
5. `acceptance_results` contains every Decision `acceptance_tests` entry exactly
   once by one-based index. No index is repeated or outside that list.
6. `approval_ready: true` requires every acceptance result to be `passed` or a
   valid `retired_by_lineage` result as defined below, the validation result to
   be passed, and a ready Reviewer handoff with no blocker.
7. Exact commands, exit codes, and concise results are recorded. A partial
   spot-check may be retained with `approval_ready: false`, but it is not
   Reviewer-ready.
8. Revisions form one unforked lineage keyed by Decision ID. A later revision
   names the immediately prior report in `supersedes`.

A structurally invalid or checksum-stale report is diagnostic, is not
Reviewer-ready, and does not consume the Decision for Builder queue purposes.

### Retired-by-lineage acceptance outcomes

An acceptance test that asserts a named artifact is presently visible in a
role queue is a `live_queue_snapshot` test. Its literal assertion can become
false because the named artifact completed ordinary Approval and Integration.
That successful completion does not permit Builder to call the old snapshot
`passed`, and it must not leave the Decision permanently undischargeable.

`retired_by_lineage` is a successful result only for a
`live_queue_snapshot` test. It means the named subject departed the asserted
queue through the full ordinary lineage, not that the historical queue state
still holds. It is never an outcome for a behavior, file-content, schema,
validation, graph, or other non-snapshot acceptance test.

A report may use `retired_by_lineage` only when all of the following are true:

1. The original Decision declares the indexed test with structured
   `acceptance_test_semantics` of `kind: live_queue_snapshot` and
   `retirement_allowed: true`, **or** a later approved Architect Decision
   authorizes that exact original Decision checksum, acceptance-test index, and
   complete subject list. Existing Decisions without structured semantics may
   use only the latter, explicit authorization.
2. The result records a `retirement_authority` with that approved Decision's
   exact ID, repository path, and SHA-256 checksum. The authority must be
   current and must authorize the result's exact input Decision checksum and
   index; a report cannot authorize itself.
3. The result records `retired_subjects` covering every subject named by the
   test or its authorization. Each subject records its ID, repository path,
   retirement state, exact Integration record path, and SHA-256 checksum. The
   supported states are `consumed_by_integrated_bundle` and
   `superseded_by_integrated_revision`.
4. The referenced Integration record exists, its checksum matches, and it
   proves the subject or its declared successor completed the ordinary
   Approval-and-Integration lineage. Handoff replacement, deletion, an
   unapproved revision, and a merely superseded artifact do not retire a
   subject.
5. A validator verifies every authority, subject, successor where applicable,
   Integration record, and checksum from repository state. It rejects missing
   evidence, partial multi-subject coverage, a wrong index, stale authority,
   or a result that uses this outcome for a non-snapshot test.

For a future Decision, `acceptance_test_semantics` must bind each snapshot test
to its one-based acceptance-test index and enumerate its expected subject IDs
and paths. A later authorization is permitted only to resolve a legacy Decision
or an unforeseen ambiguity; it must be similarly exact and cannot generalize a
named subject to an inferred class of work.

An approval-ready report may contain `passed` and valid
`retired_by_lineage` results only. Its independent Review uses
`verified_retired_by_lineage` for the latter, repeats and independently checks
the authority and Integration evidence, and may be Approved only when every
other result is `verified`. A normal `verified` disposition cannot approve a
retired result.

### Independent Review

Reviewer publishes under:

```text
rulesets/<ruleset-id>/decision-implementation-reviews/
```

The Review records the exact implementation-report ID, path, and SHA-256
checksum; repeats the exact Decision input; independently dispositions every
acceptance-test index; and records its own validation evidence. Review does not
merely accept Builder's test summary.

`overall_disposition: approved` requires every acceptance test to be verified
or independently verified retired-by-lineage as applicable, an exact active
implementation-report leaf, matching Decision provenance, and a terminal
handoff. That Approved Review consumes the Decision. A
`revision_required` Review hands the active implementation lineage back to
Builder and prevents a duplicate Decision job. No Approved bundle or Integrator
handoff is created because this lineage changes no canonical graph or registry
state.

## Role Queues

### Analyst

Ready work consists of non-hidden entries under:

```text
books/<ruleset-id>/<book-id>/packets/incoming/
```

A claimed packet is active Analyst work only while no GUR exists for its
`packet_id`. Once any valid GUR publishes a Builder handoff, the packet is not
Analyst work even if its immutable directory remains under `packets/claimed/`.

Do not move a claimed packet merely to signal Analyst completion. Existing
artifacts cite claimed packet paths and checksums. Overall packet completion is
proven by an Integration record, not inferred from packet location.

### Builder

A Builder job is ready when either:

1. an active-leaf GUR has no GUP whose `provenance.gur_id` names that GUR; or
2. an active-leaf GUP or Review requests Builder revision, every architectural
   blocker it names has a decided escalation, and no later GUP consumes that
   request; or
3. an approved Architect Decision has a ready Builder handoff and
   `migration_required: true`, and no structurally valid decision-migration GUP
   consumes it through matching `authority` and checksummed
   `provenance.decision_inputs`; or
4. an approved Architect Decision has a ready Builder handoff and
   `migration_required: false`, and no structurally valid active Decision
   Implementation Report or its active revision-required Review currently
   consumes the assignment.

One decision-migration GUP may consume several compatible Decisions. Before a
valid combined GUP exists, each unconsumed Decision remains independently visible
as Builder work; after it exists, those Decision jobs disappear and the single
GUP bundle becomes the Reviewer job.

A GUP built from a superseded GUR is stale input. Queue tooling must report it as
a lineage diagnostic and must not send it to Reviewer.

For non-migration Decisions, a valid proposed implementation report replaces the
Decision job with one Reviewer job. A revision-required implementation Review
replaces both with one Builder revision job. An Approved implementation Review
removes the Decision from ready work and may be reported as informational
completed history.

### Reviewer

A Reviewer job is ready only when an active-leaf GUP:

- has `status: proposed`;
- has `approval_ready: true`;
- has a ready handoff to Reviewer with no blocking IDs;
- satisfies exactly one lineage-root rule below; and
- is not named by any Review's `reviewed_gup.id`.

Lineage-root eligibility is:

- `packet_update`: the GUP is based on the active-leaf GUR for that packet;
- `decision_migration`: every mandatory condition in the Decision Migration
  section passes, the GUP is the active leaf for its `lineage_id`, and its
  canonical baseline still matches.

The complete kind-specific GUP bundle forms one job. A valid decision migration
is routed as `REVIEWER-DECISION-MIGRATION`; absence of a GUR is expected and is
not a warning.

A structurally valid, approval-ready active Decision Implementation Report with
no Review is one `REVIEWER-DECISION-IMPLEMENTATION` job. Its files and validation
evidence form one bundle. It does not enter the GUP queue and cannot produce an
Approved GUP.

### Architect

Architect work consists only of complete escalation packages under:

```text
rulesets/<ruleset-id>/escalations/pending/
```

Once decided, the package moves to `escalations/decided/` and the Decision names
its ID. A blocked GUP that references the same escalation is not a second
Architect job.

An incomplete package is not a decided escalation. Architect writes a return
Decision, moves the package to:

```text
rulesets/<ruleset-id>/escalations/returned/
```

and records a `handoff` to the originating role. A returned escalation never
resolves a `blocking_id` and must not unblock Builder, Reviewer, or Integrator.
The replacement package uses a new timestamped escalation ID and records
`prior_escalation_id` naming the return.

Queue tooling attaches a ready returned-escalation handoff to an existing work
item for the same packet or input artifact rather than counting it twice. If no
matching work item exists, the handoff is one correction job for
`handoff.next_role`. Once a replacement escalation names the returned ID, the
return is informational history.

### Integrator

An Integrator job is one Approved bundle whose approving Review is complete and
whose bundle ID is not named by any Integration manifest.

An Approved bundle consists of one manifest plus its declared, checksummed
components. Components never count as separate jobs.

New packet-update Approved bundles must use:

```text
APPROVED-<gup-id>-rNN.yaml
APPROVED-<gup-id>-rNN.edges.csv
```

New `decision_migration_v1` and `decision_migration_v2` Approved bundles use the
same manifest filename but no edge CSV. Their required `decision_migration` and
`validation` components are the existing checksummed reviewed GUP YAML and
validation report described in the Direct decision-migration operations section.
The manifest records the Review ID, GUP ID, component paths, checksums, artifact
kind, and operation model.

## Scanner Output

A queue scanner must separate:

- `ready` - available work;
- `active` - claimed by a role but not complete;
- `blocked` - waiting on a named blocker;
- `diagnostic` - broken or ambiguous lineage;
- `informational` - retained history and in-flight pipeline context.

`PendingCount` or `ReadyCount` counts logical `ready` jobs only. It does not count
active, blocked, diagnostic, informational, superseded, or companion files.

Recommended process exit codes:

- `0` - no ready work and no lineage errors;
- `1` - one or more ready jobs;
- `2` - invalid or ambiguous lineage prevents a trustworthy result.

JSON output must include the input artifact ID, bundle component paths, readiness
reason, and any legacy inference or lineage diagnostic.

## Legacy Queue Derivation

For artifacts published before this contract:

1. Prefer explicit `supersedes`, provenance, Review, and Integration links.
2. When `supersedes` is absent, infer the latest `rNN` only within one artifact
   kind and packet. Mark the result `legacy_revision_inference`.
3. Never infer order from creation or modification time.
4. Treat a claimed packet with any GUR as Analyst-handed-off, not Analyst-active.
5. Group GUP YAML and `.edges.csv` files by the GUP ID.
6. Group legacy Approved components by the Approved filename stem and approving
   Review. Report a diagnostic if the approving Review cannot be identified.
7. Do not relocate or edit legacy artifacts solely to improve queue display.
8. Treat `identity_merge_migration` as a legacy decision-migration spelling that
   requires a conforming superseding revision; do not silently alias it into
   Reviewer readiness.

## Acceptance Tests

Queue tooling must prove that:

1. two GUR revisions with an explicit supersession produce at most one Builder
   job;
2. a GUP YAML and its edge CSV produce one Reviewer job;
3. a reviewed GUP produces no Reviewer job;
4. a blocked GUP produces no Reviewer job;
5. a GUP based on a superseded GUR is diagnostic, not Reviewer-ready;
6. a claimed packet with a GUR is not counted as active Analyst work;
7. an Approved bundle with several components produces one Integrator job;
8. an integrated Approved bundle produces no Integrator job;
9. modification times do not change queue results;
10. invalid or forked revision lineage returns the lineage-error exit code;
11. a returned incomplete escalation neither resolves its blocker nor creates
    a duplicate correction job when its originating work is already active.
12. a valid `decision_migration` with no GUR produces exactly one Reviewer job
    and no `stale_gup_input` diagnostic;
13. a missing, non-approved, wrong-ruleset, or checksum-mismatched authority
    Decision prevents Review and produces a lineage-error diagnostic;
14. missing `lineage_id`, revision metadata, canonical checksum, decision-input
    checksum, validation report, or validation-report checksum prevents Review;
15. an invalid decision migration does not consume its authority Decisions, so
    their ready Builder handoffs remain visible;
16. two decision migrations sharing `packet_id: cross-packet` but using different
    `lineage_id` values remain independent jobs;
17. two revisions with one decision-migration `lineage_id` produce at most one
    Reviewer job, and only the active leaf is eligible;
18. a reviewed decision migration produces no Reviewer job.
19. new packet GUPs declare `artifact_kind: packet_update`, while a published
    `identity_merge_migration` remains non-ready until superseded by a conforming
    `decision_migration` revision;
20. decision-migration discovery produces equivalent results from book-scoped
    GUP stores and ruleset-scoped cross-book stores.
21. an approved Decision whose decided escalation exactly names an active Review
    suppresses that Review's earlier ready handoff, routes only the Decision's
    current handoff, and leaves the Review file byte-immutable.
22. an unconsumed approved non-migration Decision with a ready Builder handoff
    produces exactly one Builder job;
23. a valid active Decision Implementation Report suppresses the separate
    Decision job and produces exactly one Reviewer job;
24. a report with a missing or mismatched Decision ID, path, checksum, status,
    ruleset, handoff, or migration flag is diagnostic and leaves the Decision
    visible to Builder;
25. an approval-ready report accounts for every Decision acceptance-test index
    exactly once, has only passed or valid retired-by-lineage results, and
    records passed validation;
26. a partial acceptance-test spot-check is not Reviewer-ready;
27. implementation-file checksum drift makes the report diagnostic and restores
    the Decision as Builder work;
28. a revision-required implementation Review produces one Builder revision job
    and does not also republish the Decision as a second job;
29. an Approved implementation Review with exact report and Decision checksums
    consumes the non-migration Decision and creates no Integrator job;
30. implementation reports for two Decisions remain independent even when the
    Decisions share ruleset, book, source, or packet scope.
31. a `decision_migration_v1` or `decision_migration_v2` Approved manifest with no edge CSV and exactly one
    checksummed migration-GUP component plus one validation component discovers
    as one Integrator job;
32. a packet-update manifest without its required edge CSV remains a diagnostic;
33. a direct-migration manifest with an edge CSV, missing/multiple migration
    components, absent/mismatched Review or GUP checksum, or a plan not equal to
    the reviewed GUP is rejected before snapshotting canonical state;
34. a direct migration rejects a canonical or registry baseline checksum drift,
    an incomplete before-image, an unlisted endpoint field, a non-paired
    ID/label change, or a replacement whose incident set is incomplete;
35. a valid direct migration makes only its declared registry additions,
    replacements, bounded merges, canonical repoints, and exact removals; it
    never creates an alias, mutates another row, or leaves a retired endpoint;
36. a direct migration rejects a post-operation duplicate assertion key and
    rebuilds nodes and graph outputs only after every post-operation invariant
    passes; and
37. every direct-migration failure, including a late invariant failure, restores
    all canonical and registry files byte-for-byte.
38. a `decision_migration_v2` merge rejects fewer than two or duplicate retired
    IDs, an existing canonical ID, a registry row or label mismatch, an
    incomplete incident set, a non-paired repoint, or any nonempty operation
    array outside `node_changes.merges`;
39. a valid `decision_migration_v2` merge replaces every named retired registry
    row with exactly one canonical registry row, repoints every and only its
    enumerated endpoints, leaves no retired ID in registry or derived output,
    and remains fully transactional.

## Version History

- **1.9 - 2026-08-14:** Defined `decision_migration_v2`: a direct-YAML,
  two-or-more-retired-IDs-to-one-new-ID merge model with closed incident sets
  and no other operation shapes.
- **1.8 - 2026-08-14:** Defined `decision_migration_v1`: a checksummed direct
  GUP operation plan and Approved-bundle form for exact registry replacement,
  endpoint repoint, and row-removal migrations without an edge CSV.
- **1.7 - 2026-08-13:** Defined immutable Architect Decision reissues using the
  standard revision and `supersedes` lineage, including queue and migration
  authority derivation.
- **1.6 - 2026-08-06:** Defined the narrowly scoped, independently verifiable
  `retired_by_lineage` acceptance outcome for live queue-snapshot tests whose
  named subjects completed ordinary Approval and Integration.

- **1.5 - 2026-08-06:** Defined deterministic later-Decision precedence when
  multiple eligible Decisions replace the same active artifact handoff.
- **1.4 - 2026-08-04:** Added checksummed Builder Decision Implementation
  Reports and independent Reviews as the uniform completion lineage for
  non-migration Decisions, with Builder/Reviewer routing and consumption tests.
- **1.3 - 2026-08-03:** Defined exact, provenance-backed replacement of a stale
  originating-artifact handoff by the approved Decision that resolves its
  escalation, without rewriting immutable artifacts or double-counting work.
- **1.2 - 2026-07-31:** Added decision migrations as a first-class GUP lineage
  root, defined checksummed Decision and canonical provenance, separated their
  revision grouping from packet IDs, and added Builder/Reviewer queue rules and
  acceptance tests.
- **1.1 - 2026-07-30:** Added the returned-escalation state, unresolved-blocker
  semantics, replacement lineage, and correction-job coalescing.
- **1.0 - 2026-07-30:** Established append-only artifact stores,
  lineage-derived logical queues, bundle grouping, role readiness rules, and
  legacy inference.
