# Integrator Tooling

Transactional applier for Approved GUP bundles. Owned by the Integrator role
(`agents/integrator/INSTRUCTIONS.md`). This package is the only sanctioned
writer of `rulesets/<ruleset-id>/canonical/` (invariant 30).

## Guarantees

- **Transactional.** Canonical files are snapshotted before the first write and
  restored byte-for-byte if any later step fails. A batch either lands whole or
  leaves no trace. Preconditions are checked *before* the snapshot, so a bundle
  that fails verification never reaches a write.
- **Deterministic.** Identical inputs produce byte-identical canonical outputs,
  including row and node ordering. Asserted by `test_transaction.py`.
- **Non-authoring.** Nothing here interprets a rule, resolves an ontology
  question, or repairs an upstream artifact. Where an input is wrong, the batch
  is rejected and the defect is attributed to a role.
- **Derived-only rebuild.** `graph.json`, node degrees and node roles are
  recomputed from `edges_master.csv` on every run and never edited in place.

## Usage

    PYTHONPATH=tooling/integrator/src python -m adnd1e_integrator \
        --repo-root . queue

    PYTHONPATH=tooling/integrator/src python -m adnd1e_integrator \
        --repo-root . integrate [BUNDLE_ID ...] [--dry-run]

    PYTHONPATH=tooling/integrator/src python -m adnd1e_integrator \
        --repo-root . validate

Global options precede the subcommand. Exit codes follow the `WORK_QUEUES`
scanner convention: `0` clean, `1` ready work remains or a batch was rejected,
`2` lineage or tooling error.

`integrate` writes, per batch:

    rulesets/<ruleset>/canonical/{edges_master.csv,nodes_master.csv,graph.json}
    rulesets/<ruleset>/manifests/INT-YYYYMMDD-NNN.json
    rulesets/<ruleset>/reports/INT-YYYYMMDD-NNN.validation.json
    rulesets/<ruleset>/reports/INT-YYYYMMDD-NNN.diff.md
    books/<ruleset>/<book>/artifacts/integrated/INT-...-<bundle-id>.json
    build/snapshots/INT-YYYYMMDD-NNN/          (rollback copies)

## Modules

| Module | Responsibility |
|---|---|
| `canonical.py` | Exact readers and writers for the canonical files and the registry. |
| `derive.py` | Deterministic polarity, degrees, and tier 1/2 roles. |
| `invariants.py` | The machine-checkable subset of `contracts/GRAPH_INVARIANTS.md`. |
| `bundles.py` | Approved-bundle discovery and lineage-derived queue state. |
| `operations.py` | Reads a bundle's `operation_index` and its approved node registrations. |
| `snapshot.py` | Snapshot, rollback, and the `Transaction` context manager. |
| `integrate.py` | The sixteen-step transactional sequence. |
| `records.py` | Integration manifest, validation report, human-readable diff. |

## Operation classes

An Approved bundle no longer carries a flat list of additions. Its
`operation_index` classifies every CSV row, and the applier refuses a bundle
whose index does not account for each row exactly once:

- **`additions`** — a new assertion whose endpoints already exist;
- **`pending_additions`** — a new assertion that depends on a node this batch
  registers, applied only after the registration;
- **`updates`** — a compare-and-swap against an existing canonical row.

### Updates address rows by file line number

`canonical_row` is a line number in `edges_master.csv`, where the header is
line 1 — so line N is edge index N-2. Reading it as a data index selects a
*neighbouring* assertion and silently rewrites the wrong rule, which is why an
update is accepted only when all of the following hold:

1. the endpoints of the canonical row match the endpoints the manifest declares
   it currently holds — the `canonical` side of the change where the update
   repoints or reverses an edge, the patch row's endpoints otherwise;
2. every field named in `changes` still holds its declared `canonical` value;
3. the patch row equals the canonical row with exactly those changes applied —
   nothing else may ride along in the CSV;
4. the resulting assertion key does not collide with another row.

Fields listed under `differences_not_applied` are deliberately left at their
canonical values, and a test asserts they are unchanged after the batch.

## The node registry

`registries/nodes.csv` is the list of approved node IDs (constitution 3.2) and
is the authority for whether an edge endpoint is legal — not the set of nodes
currently carrying an edge, since an approved ID may sit at degree 0.

Registrations come from the approving **Review**'s `node_registry_decisions`,
because that is the artifact that approved the identity. They are applied before
any edge references them, may not overwrite an existing ID, and must use an
approved prefix.

A registration need not carry an edge. The registry is a strict superset of the
graph's nodes, and a Review may approve a complete named list — the cleric spell
list at `INT-20260803-001` — while only part of it has mechanical relationships
drawn so far. Those IDs sit at degree 0 until a later packet asserts one, and
each is listed in the manifest's `registry_changes.nodes_added_without_edges`
so the registry outrunning the node count always has a stated reason.

`degree` and `roles` in the registry are a derived snapshot and are rebuilt for
every row on every batch. `INT-20260730-001` recomputed ten node rows without
resyncing them; `INT-20260801-001` corrected that drift and records the ten rows
it repaired.

The registry file mixes terminators — nine lines in the `race_` block end with a
bare LF against 1,095 CRLF lines. `Registry` preserves each existing line's
terminator so an integration diff shows only rows whose data changed. The defect
is reported rather than silently normalized, and a test round-trips the real file
byte-for-byte.

## Serialization is load-bearing

The canonical formats were reverse-engineered from the shipped corpus and are
pinned by tests that round-trip the real files byte-for-byte:

- CSV: UTF-8, CRLF, `QUOTE_MINIMAL`, trailing newline.
- `graph.json`: `indent=1`, CRLF, **no** trailing newline.

Getting this wrong would rewrite thousands of untouched lines and destroy the
reviewability of an integration commit.

### Node ordering

`nodes_master.csv` and `graph.json` order nodes by **degree descending, ties
broken by introduction order** — a single scan of the edge list visiting each
edge's source before its target. Keying the tie-break on edge position alone is
not enough, because one edge introduces both of its endpoints at the same
position. The total order is what keeps an integration diff limited to the nodes
whose numbers actually moved.

## Baseline versus introduced findings

Canonical state carries known legacy defects. The suite measures findings before
the batch and after it, and rejects the batch if it introduces **any** new
finding or regresses any invariant count — while still permitting a clean patch
to land on a corpus with pre-existing defects. A baseline defect never becomes an
alibi for new breakage.

At `INT-20260730-001` the baseline was 1,728 findings: invariant 16
(unresolved authored polarity, 1,700), invariant 3 (unapproved node prefix, 19,
owned by DEC-2026-0004), and invariant 11 (digits in `aspect`/`condition`, 9).

`INT-20260801-001` introduced none and *resolved* six: its compare-and-swap
updates replaced four `unset` and two `heuristic` polarity bases with values read
from the source, taking invariant 16 from 1,700 to 1,694.

No batch since has introduced one either. `INT-20260803-001` resolved seven more
while adding 148 rows, taking the baseline to 1,711.

## Approved bundles are never rewritten

Consumption is recorded by naming a bundle's ID and checksums in the Integration
manifest. The bundle files themselves are immutable after publication, so
`schemas/common/approved-bundle.schema.json`'s optional `integration` block is
deliberately left unset — the role instructions forbid rewriting a published
bundle to represent integration state, and `test_bundles.py` asserts it.

## Tests

    cd tooling/integrator/tests && python -m unittest discover -s . -p "test_*.py" -t .

61 tests. Several assert against the real canonical corpus, registry, and
constitution, so a change to those files that breaks an invariant surfaces here.
`test_transaction.py` rewinds its temporary clone to pre-integration state, so it
behaves identically whether or not the live repository has already applied the
ready bundles. The rewind reverses each operation class the way it was applied —
updates first, from the manifest's declared `canonical` values, then additions
and registrations — because dropping added rows alone shifts every line number an
update depends on.

## Not yet built

The legacy 13→18 field migration. The 3,851 / 3,613 / 3,809 count drift recorded
in `rulesets/adnd1e/canonical/BASELINE.md` is still unreconciled and no migration
runner exists.

Node retirement remains unexercised — no bundle has yet proposed one, and
`integrate.py` has no path for removing a registered identity or the edges that
cite it. Decision migrations (`artifact_kind: decision_migration`,
WORK_QUEUES 1.2) have not reached an Approved bundle yet; when one does, its
components differ from a packet update's and `operations.py` will need to read
canonical mutations carried in the GUP YAML rather than an edge CSV.
