# Repository Structure

## Authority hierarchy

From most stable to most local:

1. `contracts/` — universal inter-agent workflow contracts.
2. `schemas/common/` — universal artifact envelopes.
3. `agents/` — universal role instructions.
4. `schemas/<ruleset-id>/` — ruleset graph and registry schemas.
5. `rulesets/<ruleset-id>/` — ruleset governance, registries, canonical graph, and releases.
6. `schemas/<ruleset-id>/books/<book-id>/` — book-specific extraction constraints.
7. `books/<ruleset-id>/<book-id>/` — source and packet workspaces.
8. `tooling/` — deterministic implementations owned by Builder, Reviewer, and Integrator.

Artifact-kind directories are append-only stores. They are not role inboxes.
Logical work queues are derived from artifact revision and provenance lineage
under `contracts/WORK_QUEUES.md`.

## Main layout

```text
agents/                         universal agent instructions
contracts/                      universal workflow and ownership contracts
schemas/common/                 universal artifact-envelope schemas
schemas/<ruleset>/graph/        graph schemas for one ruleset
schemas/<ruleset>/registries/   registry schemas for one ruleset
schemas/<ruleset>/books/<book>/ source and extraction schemas for one book
rulesets/<ruleset>/             governance and canonical combined graph
books/<ruleset>/<book>/         book-specific source and intermediate work
migrations/<ruleset>/           imported legacy data and migration reports
tooling/                        shared deterministic code and tests
```

## Ruleset-wide state

`rulesets/<ruleset-id>/` contains:

- the constitution and invariant extensions;
- ruleset registries and profiles;
- the canonical nodes, edges, and generated graph;
- cross-book conflicts and identity resolution;
- architect escalations and decisions;
- Builder Decision Implementation Reports and their independent Reviews;
- integration manifests and releases.

Non-migration Decision implementation lineage is stored under:

```text
rulesets/<ruleset-id>/decision-implementations/
rulesets/<ruleset-id>/decision-implementation-reviews/
```

These are append-only artifact stores governed by `contracts/WORK_QUEUES.md`.
They are not code-owner directories and do not grant Builder or Reviewer
authority over ruleset governance or canonical graph state.

Only Integrator mutates canonical graph state. Architect may alter governance and controlled registries through durable decisions.

## Book workspace

`books/<ruleset-id>/<book-id>/` contains:

- `book.yaml` — stable work identity;
- `source/<source-id>/` — exact source edition/printing assets;
- `packets/` — incoming, claimed, and completed packet directories;
- `artifacts/gur/` — immutable Analyst GUR revisions;
- `artifacts/gup/` — immutable Builder GUP bundles and revisions;
- `artifacts/reviews/` and `artifacts/approved/` — Reviewer output;
- `artifacts/integrated/` — immutable copies of integrated artifacts;
- `work/<role>/` — disposable role scratch space;
- `reports/` and `archive/`.

Do not infer pending work by counting files in `artifacts/gur/`,
`artifacts/gup/`, or `artifacts/approved/`. Companion files form one bundle,
superseded revisions remain for audit, and downstream artifacts record
consumption by ID and checksum.

## Cross-book work

Relationships involving multiple works belong under `rulesets/<ruleset-id>/cross-book/`, not arbitrarily under whichever book was processed second.

## Schema composition

The effective schema for a book artifact is composed from:

```text
schemas/common/
+ schemas/<ruleset-id>/graph/ or registries/
+ schemas/<ruleset-id>/books/<book-id>/
```

Book schemas extend extraction and citation constraints. They must not fork the ruleset's edge ontology.
