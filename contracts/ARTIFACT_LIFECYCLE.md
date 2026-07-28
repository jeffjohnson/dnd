# Artifact Lifecycle

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

A GUP is not approved merely because it is schema-valid.

## 4. Review

Created by Reviewer. Every GUP row receives a disposition:

- `approved`
- `approved_with_revision`
- `rejected`
- `architect_escalation`

Review is per field, not only per edge. The Reviewer produces either:

- Approved GUP
- Revision Request
- Architect Escalation

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

## 6. Integration Batch

Created by Integrator after applying one or more Approved GUPs.

Required outputs:

- updated canonical graph files
- registry updates
- provenance manifest
- validation report
- derived artifact rebuild report
- rejected merge report, if any
- deterministic commit-ready diff
