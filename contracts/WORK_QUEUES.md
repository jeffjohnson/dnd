# Agent Work Queue Contract

**Version 1.2.**

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

## Required Handoff Metadata

New GURs, GUPs, Reviews, Approved bundles, and Integration records must contain:

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

`identity_merge_migration` is a legacy spelling found in earlier Builder output.
It remains immutable history but is not a third lineage root and is not
Reviewer-ready as written. A Builder revision may supersede it using
`artifact_kind: decision_migration` and the complete current envelope.

Queue discovery covers both book-scoped GUP stores and ruleset-scoped
`rulesets/<ruleset-id>/cross-book/` stores. Scope location does not change the
lineage checks.

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
   `provenance.decision_inputs`.

One decision-migration GUP may consume several compatible Decisions. Before a
valid combined GUP exists, each unconsumed Decision remains independently visible
as Builder work; after it exists, those Decision jobs disappear and the single
GUP bundle becomes the Reviewer job.

A GUP built from a superseded GUR is stale input. Queue tooling must report it as
a lineage diagnostic and must not send it to Reviewer.

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

An Approved bundle consists of one manifest plus its edge, node, and report
components. Components never count as separate jobs.

New Approved bundles must use:

```text
APPROVED-<gup-id>-rNN.yaml
APPROVED-<gup-id>-rNN.edges.csv
```

The manifest records the Review ID, GUP ID, component paths, and checksums.

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

## Version History

- **1.2 - 2026-07-31:** Added decision migrations as a first-class GUP lineage
  root, defined checksummed Decision and canonical provenance, separated their
  revision grouping from packet IDs, and added Builder/Reviewer queue rules and
  acceptance tests.
- **1.1 - 2026-07-30:** Added the returned-escalation state, unresolved-blocker
  semantics, replacement lineage, and correction-job coalescing.
- **1.0 - 2026-07-30:** Established append-only artifact stores,
  lineage-derived logical queues, bundle grouping, role readiness rules, and
  legacy inference.
