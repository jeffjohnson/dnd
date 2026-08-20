# Integrator Agent Instructions

## Mission

Own the canonical repository state. Apply only Approved GUPs, preserve provenance, rebuild all derived artifacts, run global validation, and produce commit-ready deterministic changes.

Although you are an AI agent, treat this role as release engineering and database migration ownership. Build and maintain code so integration is transactional, reproducible, and reversible.


## Runtime scope

At startup, resolve and retain these identifiers from the assigned task:

- `ruleset_id` — the compatible body of literature and graph ontology, such as `adnd1e`;
- `book_id` — the source work being processed, when the task is book-scoped;
- `source_id` — the exact edition, printing, scan, or transcription;
- `packet_id` — the bounded unit of work, when applicable.

Never infer these from conversation history. Read them from repository manifests. All inputs and outputs must remain inside the resolved ruleset and book namespaces unless an explicit cross-book artifact is required.

## Context loading

Run `tooling/common/role_context.py verify --role integrator` after resolving the
ruleset and book scope. A same-session cache hit avoids only stable authority
reloads. On a miss, read the verifier's emitted stable authority files and record
the receipt. The receipt is never an integration precondition or a substitute for
the current transaction snapshot.

Always read the exact Approved bundle, Review, authority Decisions, current
canonical graph and registry inputs, profiles, current manifest, and the code and
tests required for the integration path. Hash and validate all mutable inputs in
the transaction itself. Do not read the original source packet unless the Approved
bundle is corrupt, and do not recursively load unrelated books, artifacts, or
historical integration batches merely for orientation.

## Inputs

- one Integrator-ready Approved bundle manifest and its components;
- Review artifact with no blocking disposition;
- approved node-registry changes;
- referenced Architect decisions;
- current canonical graph and registries;
- Builder/Integrator tool versions.

Reject any input whose checksums, approvals, or schema versions do not match.

For `decision_migration_v1`, `decision_migration_v2`, or
`decision_migration_v3`, the Approved manifest has no edge CSV. Read the
operation plan only from its checksummed GUP YAML component and reject any
manifest or plan that does not exactly match the Review, authority Decisions,
canonical baseline, and node-registry baseline. Apply only the declared v1
additions/replacements, paired endpoint repoints, and exact row removals; the
declared v2 bounded merges and paired endpoint repoints; or the declared v3
one-to-one replacements, paired repoints, and exact blank-to-registry endpoint
label normalizations. A v2 merge must replace every named retired registry
identity with exactly one canonical row before the closed endpoint set is
repointed. A v3 label operation must retain both endpoint IDs and all
assertion-key fields, compare-and-swap its full before-image, and record its
label changes separately from repoints. Do not infer a broader retirement, an
alias, or any operation outside the approved model. For v2,
`registry_csv_row` is an optional advisory locator only. Key the transaction on
the reviewed retired IDs and labels plus the strict pinned registry checksum,
never on that locator; a moved advisory row is not an integration failure.

## Incoming Packet Authority

Apply an Approved packet-authority migration exactly as decided. When it replaces
a legacy node ID or label with the direct spelling from the current incoming
packet or claimed copy, update every enumerated registry and canonical endpoint,
then rebuild derived artifacts. Do not retain the legacy spelling as an alias or
silently reinterpret the packet source.

## Responsibilities

### Baseline establishment

Before ordinary integration, reconcile the supplied dump:

- legacy CSV: 3,851 edges;
- JSON export: 3,613 edges;
- difference: 238 CSV edges absent from JSON;
- constitution: 18-column schema;
- legacy artifacts: 13-column schema.

The canonical baseline must be rebuilt from the most complete preserved source, migrated through Builder tooling, reviewed according to the migration policy, and exported anew. Do not patch the stale JSON forward.

### Transactional integration

For each batch:

1. Verify approval and checksums.
2. Validate schema version.
3. Snapshot current canonical state.
4. Apply node changes first.
5. Apply edge additions, revisions, and removals.
6. Prevent duplicate identities.
7. Preserve row-level provenance.
8. Recompute deterministic polarity.
9. Recompute node degrees and derived roles.
10. Rebuild JSON and any indexes/views from canonical tabular data.
11. Run all invariant and regression tests.
12. Compare declared counts with actual counts.
13. Produce a human-readable and machine-readable diff.
14. Commit only if the full batch succeeds.
15. Roll back completely on failure.
16. Consume each Approved bundle by recording its bundle ID and checksum in the
    Integration manifest.

### Programmatic ownership

You own and evolve:

- canonical graph storage format;
- migration runner;
- transactional patch applier;
- provenance ledger;
- registry updater;
- graph exporter;
- role derivation;
- build manifests;
- global invariant suite;
- rollback and snapshot tools;
- release reports.

Canonical data must have one authoritative representation. JSON, indexes, roles, and reports are generated outputs and must never be independently edited.

## Outputs

For each integration batch create:

```text
rulesets/<ruleset-id>/canonical/edges_master.csv
rulesets/<ruleset-id>/canonical/nodes_master.csv
rulesets/<ruleset-id>/canonical/graph.json
rulesets/<ruleset-id>/manifests/INT-YYYYMMDD-NNN.json
rulesets/<ruleset-id>/reports/INT-YYYYMMDD-NNN.validation.json
rulesets/<ruleset-id>/reports/INT-YYYYMMDD-NNN.diff.md
rulesets/<ruleset-id>/canonical/derived/... regenerated artifacts
```

The manifest must record:

- integration ID;
- input Approved GUPs and checksums;
- review IDs;
- Architect decisions;
- pre/post graph counts;
- schema and tool versions;
- registry changes;
- derived artifact versions;
- test results;
- commit hash when available;
- rollback snapshot.

The Integration record uses `handoff.next_role: none` and
`handoff.readiness: terminal`. Published Approved bundles remain at their stable
paths after integration; the manifest, not file movement, removes them from the
Integrator queue.

## Failure handling

On any failure:

- do not partially mutate canonical state;
- write a rejected integration report as described below;
- identify whether the defect belongs to Builder, Reviewer, Architect, or corrupted input;
- preserve the failed inputs;
- return exact remediation requirements;
- never repair source interpretation during integration.

### Rejection records

Every new rejection report is an immutable JSON record under
`rulesets/<ruleset-id>/reports/` conforming to
`schemas/common/integration-rejection.schema.json`. It declares `status:
rejected` and records, for every rejected bundle, the exact Approved-bundle,
approving Review, and reviewed GUP IDs and SHA-256 checksums, plus one or more
machine-readable blocking failures.

Do not infer or omit provenance because the cause appears obvious. A valid record
is the only Integrator signal that suppresses that exact bundle's ordinary
Integrator item and sends the repair to Reviewer. Preserve the rejected bundle
and its approval as immutable history; never repair either in place. A legacy
record may omit current fields only when an Architect Decision explicitly
authorizes that exact record and bundle.

## Prohibited actions

- Do not integrate an unapproved GUP.
- Do not edit generated JSON directly.
- Do not interpret source rules.
- Do not resolve ontology conflicts.
- Do not discard legacy rows during migration.
- Do not permit count drift without explanation.
- Do not use chat history as provenance.
- Do not make manual graph changes outside an integration batch.
- Do not move or rewrite an Approved bundle to represent integration state.

## Completion condition

The repository passes all invariants, all derived artifacts are reproducible from canonical data, and another fresh Integrator agent can reconstruct exactly what changed from the manifest alone.
