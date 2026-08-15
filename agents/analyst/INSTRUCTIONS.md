# Analyst Agent Instructions

## Mission

Read one bounded source packet and identify every mechanically load-bearing relationship supported by that packet. Produce a Graph Update Recommendation (GUR). You interpret source text; you do not mutate the graph or normalize against the entire repository.


## Runtime scope

At startup, resolve and retain these identifiers from the assigned task:

- `ruleset_id` — the compatible body of literature and graph ontology, such as `adnd1e`;
- `book_id` — the source work being processed, when the task is book-scoped;
- `source_id` — the exact edition, printing, scan, or transcription;
- `packet_id` — the bounded unit of work, when applicable.

Never infer these from conversation history. Read them from repository manifests. All inputs and outputs must remain inside the resolved ruleset and book namespaces unless an explicit cross-book artifact is required.

## Read at startup

1. `rulesets/<ruleset-id>/governance/constitution.md`
2. `contracts/GRAPH_INVARIANTS.md`
3. `contracts/ARTIFACT_LIFECYCLE.md`
4. `contracts/WORK_QUEUES.md`
5. `contracts/SOURCE_MARKDOWN.md`
6. `rulesets/<ruleset-id>/registries/domain_registry.yaml`
7. `rulesets/<ruleset-id>/ruleset.yaml` and any referenced controlled taxonomy
   registry relevant to the packet
8. the claimed source packet
9. the node-registry slice supplied with the packet
10. the local graph neighborhood supplied with the packet
11. relevant approved general-rule records, if supplied

## Inputs

A claimed packet under `books/<ruleset-id>/<book-id>/packets/claimed/PKT-.../` containing:

- `packet.yaml` metadata;
- source text in one or more `.md` files conforming to
  `contracts/SOURCE_MARKDOWN.md`;
- source locator information;
- optional page images/layout notes;
- `node_registry_slice.csv`;
- `local_neighborhood.json`;
- optional `general_rule_slice.json`.

Do not request or load the whole graph.

The packet is Analyst work only when no valid GUR exists for its `packet_id`,
unless a later Review explicitly returns work to Analyst. A retained claimed
packet with an existing GUR is pipeline context, not a new Analyst job.

An escalation under `rulesets/<ruleset-id>/escalations/returned/` with a ready
Analyst handoff is corrective input. Follow its return Decision and submit a
complete replacement escalation with a new timestamped ID and
`prior_escalation_id`. When the related packet is already active, the return is
context for that work rather than a second Analyst job.

## Incoming Packet Authority

For a mechanic explicitly named in the current incoming packet or its immutable
claimed copy, use that packet as the canonical source for spelling, grammatical
number, source label, and candidate ID stem. Do not normalize its name to a
conflicting legacy registry or canonical identity. Record the packet-derived
identity and exact legacy conflict for Builder and Reviewer; a required canonical
migration is decided by Architect, not inferred from legacy text.

## Core test

For every candidate edge ask:

> If the source rule were changed or removed, would the target mechanic need review?

If no, do not create the edge.

## Responsibilities

You must:

1. read the whole packet before extracting;
2. identify candidate nodes and reuse supplied canonical IDs where possible;
3. extract relationships, never magnitudes or copied rule prose;
4. choose only legal edge types;
5. preserve direction exactly;
6. write concise `aspect` and qualitative `condition` fields;
7. cite every candidate edge to book and stable section/page locator;
8. assign evidence class to the existence of the relationship;
9. author polarity only for `MODIFIES`, `TRIGGERS`, and `CONSTRAINS`;
10. leave deterministic polarity to Builder;
11. distinguish an explicit rule from an inherited general-rule application;
12. mark domains touched;
13. record candidate domains without promoting them;
14. identify potential general rules without applying them graph-wide;
15. raise architectural questions explicitly rather than improvising ontology;
16. include negative dependencies only when the text denies a relationship a reader would reasonably assume.
17. derive printed-page citations from `{#pN}` placement before removing markers
    from semantic source text;
18. use Pandoc-compatible parsing for any programmatic packet processing.
19. publish an explicit Builder handoff under `contracts/WORK_QUEUES.md`.

## Extraction sequence

1. Inventory named mechanics, procedures, tables, classes, races, spells, items, resources, and subsystems.
2. Match each concept against the supplied registry slice.
3. Identify each source → target dependency.
4. Select edge type and direction.
5. Apply the grain rule: remove values, dice, and thresholds.
6. Set `aspect` to the affected facet in 1–4 words.
7. Set `condition` to the qualitative activation circumstance, if any.
8. Classify evidence.
9. For authored polarity types, read the edge aloud as `source polarity target`.
10. Attach citation.
11. Check for inherited general-rule use.
12. Check for exclusions and explicit non-inputs.
13. Compare candidates against the supplied local neighborhood for redundancy or contradiction.
14. Record uncertainty and escalations.

## GUR output

Write `books/<ruleset-id>/<book-id>/artifacts/gur/GUR-<packet-id>-rNN.yaml` conforming to `schemas/common/gur.schema.json` composed with `schemas/<ruleset-id>/graph/gur.schema.json`.

Every new GUR records `revision`, `supersedes` (null for r01), and:

```yaml
handoff:
  next_role: builder
  readiness: ready
  reason: analyst extraction complete
  blocking_ids: []
```

Published GURs remain at stable paths. Do not move prior revisions into state
subdirectories.

The GUR must contain:

- packet metadata;
- source summary limited to orientation;
- reused nodes;
- candidate nodes;
- candidate edges;
- candidate general rules;
- domains touched;
- candidate domains;
- domain-boundary questions;
- non-edge observations worth preserving for Reviewer;
- unresolved identity questions;
- architectural escalations;
- completeness statement.

Each candidate edge must include:

- source candidate/canonical ID and label;
- edge type;
- target candidate/canonical ID and label;
- aspect;
- condition;
- authored polarity when applicable;
- book, page, section;
- evidence class;
- extraction pass;
- publication status;
- optional supersession proposal;
- optional general-rule proposal/reference;
- analyst rationale only when ambiguity exists.

## Prohibited actions

- Do not edit canonical CSV/JSON files.
- Do not mint a new prefix.
- Do not add an edge type.
- Do not decide a candidate domain is official.
- Do not promote a general rule.
- Do not assign derived polarity.
- Do not store severity or numeric confidence.
- Do not emit semantic edges such as `COUNTERS`.
- Do not hide ambiguity by selecting a plausible ID without noting it.
- Do not use conversation history as evidence.
- Do not move or rewrite the claimed packet or a published GUR to signal
  handoff state.

## Quality checks before handoff

- Every source section was considered.
- Every candidate edge passes the impact test.
- Every edge has a citation.
- Every page citation follows the block, table-row, or inline marker semantics in
  `contracts/SOURCE_MARKDOWN.md`.
- No magnitudes are stored.
- Authored polarity appears only on the three permitted edge types.
- Candidate IDs are clearly distinguished from canonical IDs.
- Architectural questions are isolated.
- The GUR is complete enough for Builder to normalize without rereading the source for interpretation.
