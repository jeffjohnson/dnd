# Claude Dump Analysis

## Files analyzed

- `governance/graph_constitution.md` — Constitution v1.2
- `source/edges_master.csv`
- `source/addnd_graph.json`

The uploaded ZIP wrapper was empty, but these three intended contents were mounted separately and analyzed directly.

## Inventory

| Artifact | Rows/nodes | Schema |
|---|---:|---|
| `edges_master.csv` | 3,851 edges | legacy 13 columns |
| `addnd_graph.json` | 3,613 edges, 971 nodes | legacy 13 edge fields |
| Constitution v1.2 | production contract | 18 edge columns |

## Material inconsistencies

### 1. CSV and JSON are not synchronized

The JSON contains no edge absent from the CSV, but the CSV contains 238 edges absent from the JSON. The omitted rows begin in late DMG material around page 240 and appear consistent with the JSON being generated before the latest CSV sweep completed.

Consequence: `addnd_graph.json` is stale and must not be treated as canonical.

### 2. Production schema has not been applied to either data artifact

The current CSV fields are:

```text
source_id, source_label, edge_type, target_id, target_label,
aspect, condition, book, page, section, explicit, pass, status
```

The constitution requires:

```text
source_id, source_label, edge_type, target_id, target_label,
aspect, condition, polarity, polarity_basis,
book, page, section, evidence, pass, status,
supersession_basis, general_rule_id, review_flag
```

Therefore the constitution describes the target production contract, not the current stored data.

### 3. Legacy evidence field

All legacy rows use `explicit`, while v1.2 requires categorical `evidence`. Migration must be conservative. A boolean `TRUE` does not automatically distinguish `explicit_rule` from `explicit_reference`, and `FALSE` does not distinguish `inferred_rule`, `analytic_classification`, or `speculative`.

### 4. Polarity migration debt

No CSV row currently contains polarity or polarity basis. Ten edge types can receive deterministic derived polarity. Only `MODIFIES`, `TRIGGERS`, and `CONSTRAINS` require authored review. The migration tool should derive the former and queue the latter rather than inventing polarity.

### 5. Constitution/data identity drift

The JSON still contains nodes such as `hit_points`, while Constitution v1.2 examples and role derivations refer to `rule_hit_points`. This indicates that ontology cleanup described in the constitution has not necessarily been applied to the supplied graph artifacts. Node-registry migration must precede or accompany edge migration.

### 6. Count metadata is stale by design

JSON metadata reports 3,613 edges and 2,613 core edges. The CSV contains 3,851 edges: 2,851 core and 1,000 optional. Those values reconcile exactly to the 238 missing core edges.

## Recommended baseline procedure

1. Preserve all supplied files unchanged under `source/`.
2. Declare the CSV the most complete legacy edge source, not yet canonical production data.
3. Build a schema migration in the Builder role.
4. Reconcile node IDs against the current registry and Architect decisions.
5. Derive deterministic polarity.
6. Queue authored polarity and ambiguous evidence for Reviewer batches.
7. Populate `review_flag=mm_keyword_derived` for the MM keyword/index pass where applicable.
8. Validate and approve migration batches.
9. Integrator creates new canonical CSV and nodes registry.
10. Generate JSON from canonical data; never patch the stale JSON directly.
11. Emit a manifest proving that all 3,851 legacy rows were preserved, transformed, rejected with reason, or intentionally superseded.

## Multi-agent design incorporated

The package uses repository state rather than a long-lived chat as memory. Each artifact has one owner:

- Architect governs contracts.
- Analyst owns source interpretation and GUR.
- Builder owns deterministic compilation and migration tooling.
- Reviewer independently verifies source correctness.
- Integrator owns canonical state and generated artifacts.

Builder and Integrator remain AI roles, but their recurring decisions are expected to become code and tests under their control.
