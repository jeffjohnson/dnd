# Shadowdark Workspace

**Version 1.0.** Bootstrap authority: DEC-2026-0083.

Shadowdark is an independent ruleset (`ruleset_id: shadowdark`), not a book
inside AD&D or Basic D&D. Compatible Shadowdark books contribute to one new
Shadowdark graph. No existing graph or source artifact is copied into it.

## Filesystem Map

The ruleset-wide directories below exist. Empty stores contain `.gitkeep`.
Paths with angle brackets expand to the registered books/sources listed below;
they are not literal directories. All six book trees exist. Canonical paths
are reserved for Integrator creation.

```text
rulesets/shadowdark/
  ruleset.yaml                  system identity and authoritative paths
  WORKSPACE.md                  this map and readiness gates
  governance/constitution.md    independent Constitution 1.0
  registries/
    books.yaml                  six registered source works
    sources.yaml                six distinct steward-intake sources
    nodes.csv                   header only; no pre-seeded identities
    character_races.yaml        inactive, no assumed membership
    domain_registry.yaml       empty domains
    general_rules.json         empty inherited-rule registry
  profiles/{roles,impact}.yaml  ruleset-local analysis policies
  escalations/{pending,returned,decided,decisions}/
  decision-implementations/     Builder implementation reports
  decision-implementation-reviews/  independent Reviewer dispositions
  cross-book/                  future cross-book conflict artifacts
  manifests/                  Integrator transaction manifests
  reports/                    validation and integration reports
  releases/                   future published graph releases
  canonical/                  RESERVED, not initialized by Architect
    nodes_master.csv           future approved graph nodes
    edges_master.csv           future approved graph edges
    graph.json                 future generated graph
schemas/shadowdark/
  graph/{edge,gur,gup}.schema.json
  registries/{book,source,character-race,domain,general-rule}.schema.json
  books/                      extraction profiles and source schemas per book
books/shadowdark/
  README.md                   intake entry point
  <book-id>/                  one complete tree per registered book
    book.yaml                 actual work identity/default source
    source/<source-id>/        exact edition/printing/transcription assets
    packets/{incoming,claimed,completed}/
    artifacts/{gur,gup,reviews,approved,integrated}/
    work/{architect,analyst,builder,reviewer,integrator}/
    reports/
    archive/
schemas/shadowdark/books/<book-id>/
  source_metadata.schema.json
  extraction_profile.yaml
migrations/shadowdark/         empty; no legacy import is authorized
```

Reusable implementations remain under `tooling/`; do not fork a copy of the
compiler or scanner per system. Build outputs remain under the existing
`build/` conventions with exact provenance. No Dispatcher directory is needed.

## Intake and Readiness

| Book ID | Title | Citation | Source ID |
|---|---|---|---|
| sd | Shadowdark Main Rules | SD | sd-steward-intake |
| cs1 | Cursed Scroll Zine 1 | CS1 | cs1-steward-intake |
| cs2 | Cursed Scroll Zine 2 | CS2 | cs2-steward-intake |
| cs3 | Cursed Scroll Zine 3 | CS3 | cs3-steward-intake |
| shadowdome | Shadowdome | SHADOWDOME | shadowdome-steward-intake |
| western-reaches-pg | Western Reaches Player's Guide | WRPG | western-reaches-pg-steward-intake |

The requested `western_reaches_pg` is normalized to `western-reaches-pg` to
preserve the repository's existing hyphen-only book-ID contract. No underscore
alias or second book workspace is registered. All editions/printings are
explicitly unspecified, not guessed; each source is an awaiting-intake steward
transcription identity. Do not combine different editions under one source ID.

Ready now: namespace, independent governance, empty graph registries, six book
workspaces, source manifests, ruleset/book schemas, role-context resolution,
and the ruleset-wide artifact stores. This is not a
claim that extraction, compilation, or the first integration has been approved.

Place each book's packets in
`books/shadowdark/<registered-book-id>/packets/incoming/`.
Start with `books/shadowdark/sd/packets/incoming/` for the main rules. Supply
edition/printing when known; a different source needs its own registration.
Do not file packets in another system or in governance/artifact directories.

Use the existing Pandoc Markdown packet and page-marker contract. Incoming
packet text governs source names and citations. Informational metadata does
not become graph data. Packet IDs are assigned from actual bounded input.

## Ordered Next Steps

1. Steward/user: supply bounded packets, preferably main rules first, and
   identify the edition/printing when known. This precedes extraction because
   no source text or packet is present yet.
2. Analyst: after packet intake, claim bounded packets and
   publish Shadowdark GURs. Escalate only source-supported ontology questions;
   an escalation precedes only the work it actually blocks.
3. Builder: compile only after checking current approved tooling admission and
   Shadowdark vocabulary/schema isolation. No assertion that AD&D-specific
   normalization is automatically safe here. Escalate a required semantics
   change before coding it; submit GUPs to Reviewer normally.
4. Reviewer: independently verify source, schema, isolation, and dependencies;
   approve only conforming outputs. A notification is not a review assignment.
5. Integrator: after an Approved bundle, verify a safe first-graph transaction
   path; create canonical state only with the required authorization/tests.

The user's notification request authorizes one bounded serial maintenance
batch: each role reads this map and acknowledges awareness, with no queue scan,
source extraction, implementation, review, or integration. No ordinary work is
launched by that notification. Await the actual registered input/assignment.
