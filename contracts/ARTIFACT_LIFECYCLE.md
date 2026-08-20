# Artifact Lifecycle

**Version 1.14.**

Artifact files are durable, append-only records. Their directories preserve
artifact kind, not current queue state. Role readiness, revision leaves,
component grouping, and downstream consumption follow
`contracts/WORK_QUEUES.md`.

Do not move, rename, overwrite, or delete a published GUR, GUP, Review, Approved
bundle, or Integration record to indicate progress. Downstream artifacts consume
upstream artifacts through IDs, paths, and checksums.

## Artifact Integrity Breach

If a checksum named by a published consumer no longer resolves to the bytes at
its recorded artifact path, retain the altered artifact and every consumer
unchanged. Do not reconstruct a matching file, replace the recorded checksum,
or treat later equivalent content as the original input. The discovering role
raises an Architect escalation that identifies the artifact, consumer, expected
checksum, and current checksum. The resolving Architect Decision is the durable
incident record; every corrective artifact is a new successor revision under
the normal lifecycle.

## 1. Source Packet

A bounded unit of source text and metadata. It is immutable once claimed.

Required contents:

- packet ID
- source book
- printed page range or stable section locator
- extracted text
- source-file checksum or identifier
- optional page images or layout notes
- packet-creation metadata

Once a valid GUR exists for its `packet_id`, a claimed packet is no longer
Analyst work. It may remain under `packets/claimed/` because published provenance
references that stable path. Do not move it merely to signal Analyst completion.

## 2. GUR — Graph Update Recommendation

Created by Analyst. It is interpretive and may contain candidates or unresolved identity.

A GUR may contain:

- candidate nodes
- candidate edges
- reused canonical nodes
- source citations
- evidence classification
- authored polarity proposals
- domains touched
- candidate domains
- general-rule candidates
- architectural questions
- analyst notes explaining only ambiguity, not rulebook prose

A GUR never mutates the graph.

Every ordinary new GUR records `revision`, `supersedes`, and a `handoff` to
Builder. When a later packet wholly supersedes its source scope, the Analyst may
instead publish a successor GUR withdrawal revision with no proposals and the
terminal handoff `next_role: none`, `readiness: terminal`. The withdrawal records
the replacement packet or GUR and does not create a synthetic empty GUP or
Review. Earlier revisions remain in place and do not remain Builder work after
supersession or downstream consumption.

## 3. GUP — Graph Update Patch

Created by Builder. It is normalized and schema-valid.

A GUP must contain:

- canonical IDs only
- legal edge types
- normalized direction
- deterministic fields derived by code
- proposed registry additions isolated from edge changes
- no unresolved duplicates
- validation report
- escalation references for unresolved architecture

A GUP has exactly one lineage root:

- `artifact_kind: packet_update` consumes one active-leaf GUR through
  `provenance.gur_id` and `provenance.gur_checksum`;
- `artifact_kind: decision_migration` consumes one or more approved Architect
  Decisions through `authority` and checksummed `provenance.decision_inputs`.

Legacy GUPs that omit `artifact_kind` may be treated as `packet_update` only when
their GUR provenance is unambiguous. A declared `decision_migration` never needs
or accepts a GUR merely to satisfy packet lineage.

The historical value `identity_merge_migration` is a legacy decision-migration
spelling, not a third lineage root. Existing published artifacts retain it for
audit, but it is not Reviewer-ready under the legacy shape. Any new revision
must declare `decision_migration`, name the legacy artifact in `supersedes`, and
satisfy the current Decision-provenance contract.

A decision migration must also record a stable `lineage_id`, ordinary revision
and supersession metadata, the checksummed canonical baseline it was planned
against, and the complete before-state and delta for every canonical mutation.
Its authority IDs are not sufficient provenance by themselves. Exact required
fields and queue semantics are defined by `contracts/WORK_QUEUES.md`.

A new decision migration that applies direct registry or canonical operations
declares `operation_model: decision_migration_v1`, `operation_model: decision_migration_v2`, or `operation_model: decision_migration_v3`. It pins both the canonical edge and node-registry
baselines, carries the executable operation plan only in its GUP YAML, and has
no edge CSV merely to satisfy packet-update conventions. Version 1 covers
additions, one-to-one replacements, endpoint repoints, and exact no-replacement
removals. Version 2 covers only a bounded two-or-more-retired-IDs-to-one-new-ID
merge and its exact endpoint repoints. Version 3 covers one-or-more one-to-one
replacements, their closed paired endpoint repoints, and explicitly enumerated
blank endpoint-label normalization to the exact current registry labels; it
cannot perform additions, relabels, merges, aliases, removals, nonblank-label
edits, or non-endpoint mutation. The Approved manifest references that exact
GUP YAML and validation report as checksummed components; it does not restate
or translate the operations.

A GUP is not approved merely because it is schema-valid.

For a packet update, the GUP YAML, edge CSV, and validation report are one
artifact bundle and one Reviewer job. For a decision migration, the GUP YAML and
validation report are required components; edge or node CSV components are
included only when the GUP declares them. Canonical row changes may be carried
directly in the decision-migration YAML. A `decision_migration_v1`,
`decision_migration_v2`, or `decision_migration_v3` Approved bundle consists of
its manifest plus the exact reviewed migration GUP YAML and validation report;
it must not add a synthetic edge CSV. Every new revision names the immediately
prior GUP in `supersedes`.

For a v2 merge, `retired_nodes[].registry_csv_row` is optional and advisory: it
is an auditable observed-row locator, not the retirement identity or a
transaction precondition. The retired ID and label, complete incident set, and
pinned registry checksum remain authoritative.

## 4. Review

Created by Reviewer. Every GUP row receives a disposition:

- `approved`
- `approved_with_revision`
- `rejected`
- `architect_escalation`

For a new Review declaring `review_contract_version: '1.1'`, every per-row
`edge_decisions` or `row_decisions` value must be one of those four dispositions
and validate through `schemas/common/review.schema.json` before publication.
The disposition records the judgment about the row, not whether the row belongs
in an Approved edge component. A source-supported `approved` row may remain in a
checksummed `blocked.csv` outside the bundle; record that exclusion as packaging
evidence. `approved_but_excluded_from_bundle` is not a legal disposition.

Review is per field, not only per edge. The Reviewer produces either:

- Approved GUP
- Revision Request
- Architect Escalation

A Review records the reviewed GUP ID and an explicit handoff to Integrator,
Builder, Analyst, Architect, or no downstream role. A reviewed GUP is never
Reviewer-ready again.

## 5. Architect Decision

Created only for architectural questions. It may:

- approve/reject a node kind or prefix
- resolve canonical identity
- approve/reject a domain
- approve/reject a general rule
- approve/reject a Tier 3 role
- amend edge semantics or constitution
- direct migration

The decision must identify affected artifacts and whether a constitution version bump is required.

An Architect Decision is immutable after publication. A correction to executable
migration instructions is published as a new Decision ID with a later
`revision` and `supersedes` naming the immediately prior Decision ID. The active
Decision-reissue leaf is the only Decision that can authorize the replacement
migration; the predecessor remains at its original path as history. The exact
lineage validity and queue behavior are defined in `contracts/WORK_QUEUES.md`.

## 6. Decision Implementation

A non-migration Architect Decision may assign Builder or Integrator work such as
schema, documentation, validator, queue-tool, or integration-capability
alignment without authorizing a canonical graph migration. Its ready handoff
selects the implementation owner. That work is completed through two immutable,
ruleset-scoped artifacts:

1. The implementation owner publishes a Decision Implementation Report under
   `rulesets/<ruleset-id>/decision-implementations/`.
2. Reviewer publishes an independent Decision Implementation Review under
   `rulesets/<ruleset-id>/decision-implementation-reviews/`.

The implementation report consumes exactly one immutable Decision by ID, path,
and SHA-256 checksum. It records every implementation file and checksum,
accounts for every Decision acceptance test, and records the exact validation
commands and outcomes. `implemented_by` must exactly equal the Decision's ready
Builder or Integrator handoff. It is not a GUP and never enters the Integrator
queue.

The implementation Review consumes the exact active implementation-report leaf
by ID, path, and checksum and independently dispositions every Decision
acceptance test. Only an Approved implementation Review completes the Decision.
A Builder claim by itself is not completion.

An implementation report may use `retired_by_lineage` only for a live
queue-snapshot acceptance test whose named subject completed ordinary Approval
and Integration. The report and its independent Review must preserve exact
Architect authority and checksummed Integration evidence; this outcome does not
restate the old queue snapshot as passing. Its required structure, validation,
and review disposition are defined in `contracts/WORK_QUEUES.md`.

For a versioned-contract-content acceptance test, the report instead records the
current contract checksums and versions together with the exact Decision semantics
or legacy authorization that applies. The version must meet the stated minimum and
the named substantive anchors must remain present. Its independent Review uses the
corresponding versioned-contract-content disposition. This is current-state
verification, not a retirement outcome, and an unstructured legacy exact-version
test has no such path without a later checksummed Architect authorization.

Exact schemas, naming, and queue behavior follow
`schemas/common/decision-implementation.schema.json`,
`schemas/common/decision-implementation-review.schema.json`,
`contracts/FILE_NAMING.md`, and `contracts/WORK_QUEUES.md`.

## 7. Integration rejection

When an Integrator cannot apply an otherwise Approved bundle, it publishes an
immutable rejection record under `rulesets/<ruleset-id>/reports/` rather than
altering the bundle, Review, or GUP. New records conform to
`schemas/common/integration-rejection.schema.json` and pin the rejected bundle,
approving Review, and reviewed GUP by ID and SHA-256 checksum, with one or more
machine-readable blocking failures.

A valid rejection returns accountability to Reviewer through the queue. The
Reviewer publishes an immutable successor Review that records the exact
rejection record and routes the ordinary repair or a new escalation. A malformed
or stale rejection never retires integration work. The exact queue derivation is
defined in `contracts/WORK_QUEUES.md`.

## 8. Integration Batch

Created by Integrator after applying one or more Approved GUPs.

Required outputs:

- updated canonical graph files
- registry updates
- provenance manifest
- validation report
- derived artifact rebuild report
- rejected merge report, if any
- deterministic commit-ready diff

An Integration manifest consumes each Approved bundle by ID and checksum.

## Version History

- **1.14 - 2026-08-20:** Defined immutable handling and Architect recording of
  an unrecoverable published checksum; all corrective work is a successor
  revision.
- **1.11 - 2026-08-19:** Defined checksummed minimum-version and substantive-
  anchor evidence for Decision Implementation contract-content acceptance tests.
- **1.10 - 2026-08-18:** Added immutable checksummed Integration rejection
  records and generalized non-migration implementation ownership to Builder or
  Integrator.
- **1.9 - 2026-08-15:** Defined immutable terminal GUR withdrawal revisions for
  source scope superseded by a later packet.
- **1.8 - 2026-08-15:** Recorded the advisory, auditable v2 registry-row
  locator; identity and the pinned registry snapshot remain strict.
- **1.7 - 2026-08-14:** Recorded the bounded direct-YAML
  `decision_migration_v2` node-ID merge path and its no-edge-CSV bundle form.
- **1.6 - 2026-08-14:** Defined the checked, direct-YAML
  `decision_migration_v1` bundle path for exact registry and canonical
  operations that do not have an edge CSV representation.
- **1.5 - 2026-08-13:** Recorded immutable Architect Decision reissues for
  corrections to executable migration instructions.
- **1.4 - 2026-08-06:** Recorded the checksummed retired-by-lineage outcome for
  Decision Implementation acceptance tests tied to completed queue subjects.

- **1.3 - 2026-08-04:** Added reviewed Decision Implementation Reports as the
  completion lineage for non-migration Builder Decisions.
- **1.2 - 2026-07-31:** Defined packet updates and decision migrations as the
  two GUP lineage roots, with checksummed Decision and canonical provenance and
  kind-specific bundle components.
- **1.1 - 2026-07-30:** Declared artifact stores append-only, separated queue
  state from artifact location, required revision/handoff lineage, and defined
  bundle-level work items through `contracts/WORK_QUEUES.md`.
