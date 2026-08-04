# Builder Tooling

Deterministic GUR → GUP compiler for the AD&D 1e mechanical relationship graph.
Owned by the Builder role (`agents/builder/INSTRUCTIONS.md`).

## Guarantees

- **Deterministic.** Identical inputs produce byte-identical outputs. Row order is
  the canonical assertion order, not GUR order. No timestamps are written into
  artifacts. Nothing depends on conversation history.
- **Non-authoring.** The compiler assigns polarity only for the ten edge types the
  constitution says are determined by edge type. It never invents node identity,
  never widens the edge vocabulary, and never merges two concepts by label.
- **Fail-loud.** Where it cannot decide, it emits an escalation and marks the patch
  `blocked`. A schema-valid patch is not an approvable one.

## Usage

    PYTHONPATH=tooling/builder/src python -m adnd1e_builder compile \
        books/adnd1e/phb/artifacts/gur/GUR-<packet>-rNN.yaml --repo-root .

Writes, per GUR:

    books/<ruleset>/<book>/artifacts/gup/GUP-<packet>-rNN.yaml
    books/<ruleset>/<book>/artifacts/gup/GUP-<packet>-rNN.edges.csv
    build/reports/GUP-<packet>-rNN.validation.json

The invariant suite runs before any artifact is written, and its result is
recorded in every artifact produced. Exit code is `1` when a patch is blocked,
`2` when the test suite fails.

Independently cross-check citations against the packet source:

    PYTHONPATH=tooling/builder/src python -m adnd1e_builder verify-pages \
        books/adnd1e/phb/packets/claimed/PKT-* --gup-dir books/adnd1e/phb/artifacts/gup

## Modules

| Module | Responsibility |
|---|---|
| `vocab.py` | Every controlled vocabulary and derivation table, transcribed from constitution v1.7. The single source of truth. |
| `review.py` | Reviewer row dispositions and exact corrections, read as revision directives. |
| `registry.py` | Node registry loading; exact / normalized-label resolution. Never merges by label. |
| `polarity.py` | Section 6.1 derivation; validation of authored polarity on `MODIFIES`, `TRIGGERS`, `CONSTRAINS`. |
| `grain.py` | Invariant 11 — magnitudes, dice, bonuses and percentages out of `aspect` and `condition`. |
| `duplicates.py` | Assertion key, exact/near/neighbourhood matching against canonical, intra-patch duplicates, self-edges. |
| `pagemarkers.py` | Pandoc-backed page-marker resolution per `contracts/SOURCE_MARKDOWN.md`. |
| `compiler.py` | Orchestration, conditional-field enforcement, citation checks, escalation emission. |
| `migration.py` | Identity-merge migration (DEC-2026-0007): every row incident on a retired ID moves to a survivor. |
| `decision_migration.py` | Row-by-row migration for decisions that enumerate specific canonical rows (DEC-2026-0015, DEC-2026-0016). |
| `emit.py` | Canonical serialization: GUP YAML, 18-column edges CSV, validation JSON. |

## The assertion key

Constitution 1.7 **section 5.1** defines edge identity. GRAPH_INVARIANTS 1.0
invariant 12 requires each ruleset constitution to define its key and forbids
tooling inventing, omitting or widening one, so the build implements section 5.1
rather than choosing a key of its own:

    (source_id, edge_type, target_id, aspect, condition)

Comparison follows section 5.1 exactly. Canonical IDs and the controlled edge
type are compared directly. `aspect` and `condition` are compared
case-insensitively after collapsing non-alphanumeric separator runs, so cosmetic
wording or punctuation changes do not create a new assertion. `ALTERNATIVE_TO`
is the one symmetric type and its endpoints are sorted before comparison;
endpoint order stays significant for every directed type.

An exact key match is one assertion and only one may enter production. Rows
sharing source, type and target but differing in aspect or condition are **near
matches** — distinct assertions when the facet is genuinely source-supported,
which is the Reviewer's call and never the build's. Paraphrase alone does not
make a facet distinct.

Labels, polarity, citations, evidence, pass, status and review metadata are not
identity (`vocab.IDENTITY_EXCLUDED_FIELDS`). A disagreement in one of those is
resolved on the existing assertion rather than kept as a second edge; where
another book restates the same assertion, the extra locus goes in provenance.

Tests read the governing text and compare it against what the build does, so an
edit to either side has to move both, and the corpus is checked for exact
duplicates against the real file rather than a pinned count.

## What the edges CSV means

`GUP-<packet>-rNN.edges.csv` contains **only rows that could be integrated as they
stand**. Every row satisfies invariant 1: both endpoints exist in the canonical
registry today. A row whose endpoint depends on a node this patch merely
*proposes* is held out of the CSV and carried in the GUP YAML under
`edge_changes.pending_additions`. It is not rejected — it is waiting on an
Architect ruling.

This matters because the CSV is the artifact an Integrator reads. A blocked GUP
still ships a CSV, and that CSV must never contain an edge pointing at a node
that does not exist.

    edges_in = edge_additions + edge_pending_additions + edge_updates + edges_rejected

## Additions vs updates

When a compiled edge matches an existing canonical assertion exactly and differs
only in `polarity` / `polarity_basis`, and the canonical row carries
`unset` or `heuristic`, it is emitted as an **update** rather than an addition.
Inserting it would duplicate the assertion; dropping it would discard a source
reading the canonical row lacks. Fields outside the build's ownership that also
differ (`pass`, `section`) are reported under `differences_not_applied` for the
Reviewer rather than silently applied.

Where both rows carry `polarity_basis=read` and disagree, that is a conflict
between two source readings and the compiler refuses to choose.

## Applying a Review

    PYTHONPATH=tooling/builder/src python -m adnd1e_builder compile \
        books/adnd1e/phb/artifacts/gur/GUR-<packet>-rNN.yaml --repo-root . \
        --review books/adnd1e/phb/artifacts/reviews/REV-<gup-id>-rNN.yaml \
        --revision <next>

The Review is the revision directive: it decides every row of the reviewed patch,
so the compiler reads it directly rather than asking for a second format. Two
ownership rules govern what a directive may change.

**The Reviewer owns readings; the build owns derivations.** A correction to
`polarity` or `polarity_basis` is applied on `MODIFIES`, `TRIGGERS` and
`CONSTRAINS`, whose polarity section 6.1 leaves to a reading of the source. On
the other ten types polarity follows from `edge_type`, and a correction to it is
refused and reported. Where the same directive retypes the edge, the corrected
type decides which rule applies. Corrections are revalidated like any other
value, so a Reviewer cannot introduce a grain or vocabulary violation.

**Only rows that reached the Reviewer need a disposition.** A GUR row the build
rejects on its own — a duplicate, or a direction reversal under DEC-2026-0011 —
was never in the reviewed patch, so its missing disposition is recorded as
`review_row_not_presented` rather than treated as an omission. A row that
survives compilation and still carries no disposition is an error.

**A Review can rule on the shape of an operation, not just field values.**
Inside `exact_corrections`, `operation`, `canonical_row` and
`obsolete_conflicting_row` are instructions rather than columns: they say the row
repairs a named canonical assertion instead of inserting a new one. They never
reach an edge. Whether an assertion is already in the graph under different
wording is a judgement about the neighbourhood, which the build cannot always
reach on its own, so where a Review names the row the build honours it.

The same instruction is written several ways across the Reviews in this
repository, and all of them are read:

| Shape | Means |
|---|---|
| `edge_changes.<bucket>: {remove_ref: R}` | drop R from that bucket; its other operation stands |
| `edge_changes.<bucket>: {retain_ref: R, canonical_row: N}` | R belongs in that bucket, against row N |
| `edge_changes.<bucket>: {replace_ref: R, fields: {...}}` | correct those columns of R |
| `edge_changes.<bucket>: {add: {...}}` | the corrected row, restated in full |
| `submitted_operation_records: [{canonical_row: N, ...}]` | the placement the Review is approving |

A `fields` block is an authored correction and goes through the ownership check
above, so it can set an authored polarity and cannot set a derived one. A
restated whole row is an echo of the patch rather than a ruling, so its
build-owned columns are ignored — otherwise every restatement would be reported
as a Reviewer authoring a derived polarity.

**A key inside a bucket instruction that is neither a column nor one of these is
an error.** `reviewer_directive_not_understood` fails the build. An instruction
the build cannot carry out must not be silently dropped, and it must not be
absorbed as a write to a field of that name.

**One GUR candidate is one operation.** A row the Review placed as a repair to a
named canonical row is not also an insertion waiting on a proposed node, even
where one of its endpoints is such a node. Emitting both turns one assertion into
two operations — the duplicate two Reviews caught by hand.

## Review chains

Pass `--review` once per Review, oldest first, when a packet has been reviewed
more than once:

    --review .../REV-<gup>-r01-r01.yaml --review .../REV-<gup>-r02-r01.yaml

The newest Review is authoritative on disposition. Corrections and placement then
carry forward on different rules, because the two Reviews are saying different
kinds of thing about them.

**Corrections merge, later winning field by field.** Each Review judges a patch
compiled from the same GUR, so a correction round one made is already in the
patch round two approves. Dropping it would recompile the GUR without it and hand
back the defect that Review fixed — an approval would undo the corrections it
approves.

**Placement does not merge.** A Review states which bucket every row belongs in,
via `submitted_operations`, `submitted_operation_records` or an explicit
instruction. Where the later Review states a placement it is complete and
replaces the earlier one; merging would resurrect a canonical row number or a
withheld field that Review deliberately dropped. Only where the later Review is
silent about placement does the earlier one stand.

Each row also carries the buckets the reviewed patch presented it in. If a Review
approved a row as an update and the build produces an addition, that ruling has
been lost, and `reviewer_operation_not_preserved` fails the build rather than
shipping a second copy of an assertion the graph already holds. A row presented
in two buckets has no single presented operation — that is the state a Review
resolves with `remove_ref`, not one to pick between.

**A Review that returned the packet to the Analyst is answered by a new GUR.**
That replacement drops rows the Review rejected and adds rows it demanded, so the
Review covers only part of the population being compiled. Comparing the Review's
own `input_provenance.gur.id` against the GUR in hand tells the two cases apart.
Rows added since are carried for review; rows the Analyst removed on a rejection
are recorded as satisfied at source.

That comparison is **per Review, not per chain**. In a chain the newest Review is
not always the one that decided a given row, and judging every row against the
newest Review's input GUR would report each stale ruling as a lost row. An
approved row that went missing is still an error — unless a later Review in the
chain reviewed a patch built from this very GUR, which means it judged the
current population in full and already signed off on the row being gone.

**A Review can introduce a node.** Deciding that a source names a spell family
rather than one spell is an identity judgement, and it lands as an exact
correction pointing at an ID that may not exist yet. The build proposes the node,
holds the row pending, and lets the Integrator write the registry — rather than
reporting the Reviewer's own ruling as an unresolved endpoint. Prefix and ID
format are still enforced: a Reviewer may rule on identity, not widen the
ontology. Where an Architect decision already named that ID as a rejected-prefix
node's replacement, the label and provenance come from the legacy node instead.

**`node_registry_decisions` is read.** It is the node-level counterpart of
`row_decisions`, and it is where a Reviewer supplies the label a proposal is
missing. Ignoring it re-ships a defect the Reviewer already wrote the fix for.

**An Architect relabel beats the registry.** When a decision assigns a node a new
canonical label and the Integrator has not applied it yet, the build writes the
ruled label. Normalizing to the registry would reintroduce the replaced label on
every row that touches the node.

## Migrations

Two shapes, and they are not interchangeable.

`plan-migration` handles an approved **identity merge**: a retired ID is folded
into a survivor and *every* incident row follows. The set of affected rows is
derived.

    PYTHONPATH=tooling/builder/src python -m adnd1e_builder plan-decision-migration \
        rulesets/adnd1e/escalations/decisions/DEC-2026-0015.yaml \
        rulesets/adnd1e/escalations/decisions/DEC-2026-0016.yaml \
        --repo-root . --gup-id GUP-MIG-DEC-2026-0015-0016-r02 \
        --lineage-id MIG-DEC-2026-0015-0016 --revision 2 \
        --supersedes GUP-MIG-DEC-2026-0015-0016-r01 \
        --out books/adnd1e/phb/artifacts/gup/GUP-MIG-DEC-2026-0015-0016-r02.yaml

`plan-decision-migration` handles the other shape, where the decision names
individual rows. DEC-2026-0015 decided row by row which assertion is about a
specific spell and which is about a spell family; that set cannot be derived from
a rule without the Builder guessing at identity, which is what the decision
removed. So the planner applies exactly what a decision enumerates and refuses
where the corpus has moved under it: a row whose current value does not match the
`from` the decision recorded is an error, not something to reinterpret. A
decision whose stated `counts` disagree with its own enumeration is likewise
refused rather than half-applied.

The audit is the reason the module exists. The plan is applied to an in-memory
copy of the whole corpus and re-keyed on the five-field assertion key, because a
repoint can silently collapse two distinct assertions into one and nothing local
to the row would show it. A duplicate that already existed is reported as a
warning; one this migration would create fails the plan.

Node additions, relabels, endpoint repoints, label normalizations and the
provenance merge travel as **one package**, per DEC-2026-0015: implementing only
the rows that unblock a packet would leave the other approved conflicts half
migrated.

### Lineage

A decision migration is the second GUP lineage root (WORK_QUEUES 1.2,
DEC-2026-0018). It has no GUR, and the absence is not a defect — but it does mean
the artifact needs an alternate auditable root, or any GUP could bypass source
lineage by declaring the kind. That root is `lineage_id` plus revision metadata,
the authority Decisions with their paths and SHA-256 checksums, the canonical
baseline checksum, and an external validation report pinned by checksum. Both
`--lineage-id` and `--revision` are stable inputs, not derived from the filename:
`packet_id` is `cross-packet` for every migration and cannot group them.

The checksums are what stop a reviewed plan being applied to a graph that has
moved. If either the Decisions or the canonical file changes after planning, the
queue scanner refuses to route the GUP and the Builder issues a new revision.

`identity_merge_migration` is the earlier spelling of this same root. Published
artifacts keep it as immutable history; any new revision declares
`decision_migration` and carries the full envelope.

## Tests

    cd tooling/builder/tests && python -m unittest discover -s . -p "test_*.py" -t .

`test_pagemarkers.py` implements the six acceptance tests required of any packet
parser by `contracts/SOURCE_MARKDOWN.md`. `test_decision_migration.py` implements
the acceptance tests of DEC-2026-0015 and DEC-2026-0016 against the real corpus,
including a proof that planning is never a write path.
`test_edge_schema.py` implements the
acceptance tests of DEC-2026-0014 and is the full-corpus schema audit that
decision assigns to the Builder; it pins the known migration debt at 53 rows and
60 errors so the debt cannot grow unnoticed. Several tests assert against the
real canonical corpus and registry, so a change to those files that breaks an
invariant surfaces here.

## Not yet built

The legacy 13→18 field migration described under "Migration responsibility" in
the role instructions. The 3,851 / 3,613 / 3,809 count drift recorded in
`rulesets/adnd1e/reports/PRECONDITION-AUDIT-20260727.md` is unreconciled and no
migration tool exists.
