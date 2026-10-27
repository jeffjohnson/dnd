# 5e Graph Integration Proposal

Date: 2026-10-26. Authoring role: Architect.

**Status: architecture proposal, not an approved Decision or import authorization.**
This assessment inspects the owner's temporary `5etools/` directory and the
existing repository contracts. It does not initialize a ruleset, claim a packet,
publish a GUR/GUP, change canonical state, install upstream dependencies, or
execute the upstream application. No existing packet relay is advanced.

## 1. Recommendation

**Use 5etools as a structured source adapter and research index, not as an
already-correct mechanical graph.** Preserve three separate representations:

1. An immutable, externally retained source snapshot and source catalog.
2. Bounded, deterministic, citation-preserving packets with structured evidence
   sidecars, prepared under the source steward's authority.
3. The reviewed mechanical relationship graph, produced through the existing
   Analyst -> Builder -> Reviewer -> Integrator lifecycle.

Do not import the website, every JSON property, or every inline link as a node
or edge. Do not make thousands of model requests to discover facts that a local
parser can inventory in one run. The expensive reasoning belongs in selecting
mechanical assertions, interpreting exceptions, and independently reviewing
them, not locating records, expanding references, or copying metadata.

Start with a narrow core-rules pilot. Design for both 2014 and revised 2024
content, but keep their semantics isolated. Under today's unversioned canonical
edge contract, my preferred initial storage is **two ruleset namespaces**,
`dnd5e-2014` and `dnd5e-2024`, with a shared source adapter. These names are
proposals, not registered identifiers. A future family-level application can
present both as D&D 5e and apply explicit compatibility mappings.

If only one is wanted initially, the other need not be initialized. If a single
mixed canonical graph is required instead, approve a version-aware identity,
assertion, validation, and activation contract before importing either edition.
Do not silently fold 2024 into an optional layer above 2014.

## 2. What Was Actually Inspected

### 2.1 Snapshot and method

- Local application package version: **2.39.0**, from `5etools/package.json`.
- The supplied directory has no root `.git` directory in the observed listing;
  a verified upstream commit was not established. Package version alone is not
  an adequate source snapshot identifier.
- Every `data/**/*.json` file was read as JSON bytes and hashed: **519 files,
  120,637,208 bytes**, approximately 115.05 MiB; **zero JSON parse failures**.
- This is a structural census plus targeted source/code reading, not a semantic
  review of every entry or a pass of the upstream JSON schemas.
- The three entity indexes resolve all their listed files: spells 18, classes
  15, bestiary 112. This checks file existence, not every entity reference.
- Read-only inventory helper and detailed evidence are ignored scratch files:
  `.local/5e-assessment/inventory.py` and `inventory.json`.
- Inventory manifest digest:
  `f61e7a73281f2e2f23ffeafc7dff5d9c5cf987d75f7a4032f9f96a1b78cbe629`.
  This hashes the sorted inventory's path/byte-count/file-hash/category records,
  not an upstream release archive or a canonical graph.

The inspection covered representative PHB/XPHB spells, class structures and
features, feats, copy-derived creatures and subclasses, magic-item templates,
book trees, source indexes, reference parsing, and spell-list generation. No
external homebrew corpus was downloaded. `homebrew/` and `prerelease/` each
contained an index in the top-level listing; these are not evidence that all
referenced remote content is locally present.

### 2.2 File families

| Inventory category | JSON files | Interpretation |
|---|---:|---|
| Structured data and support files | 191 | Entity arrays, catalogs, indexes, lookup inputs, generators' inputs; not all are source entities |
| Book text | 67 | Nested `bookData` trees, including rulebooks and supplements |
| Adventure text | 102 | Nested narrative, encounters, mechanics, and references; defer bulk extraction |
| Fluff | 138 | Descriptive/image-support records; not an automatic mechanical assertion source |
| Foundry support | 11 | VTT-specific data, not publisher rules authority |
| Generated | 10 | Derived reference, spell, table, and navigation indexes; not independent evidence |

The census distinguishes these categories before counting entity arrays, so a
generated lookup or repeated book-text passage is not counted as another spell.

### 2.3 Raw entity counts

| Top-level entity array | Raw records |
|---|---:|
| `monster` | 4,574 |
| `item` | 2,512 |
| `baseitem` | 230 |
| `magicvariant` | 230 |
| `spell` | 969 |
| `class` | 30 |
| `subclass` | 330 |
| `classFeature` | 677 |
| `subclassFeature` | 1,499 |
| `feat` | 305 |
| `background` | 175 |
| `race` / `subrace` | 160 / 98 |
| `optionalfeature` | 221 |
| `variantrule` | 231 |
| `condition` / `action` / `skill` | 30 / 48 / 36 |
| `deity` / `language` | 563 / 201 |

These are **stored records before copy expansion, version materialization,
source filtering, identity resolution, and mechanical relevance review**.
They are not unique game concepts, packet counts, or the expected graph size.
The 30 classes do not mean 30 distinct core classes.

There are 261,935 lexical inline-tag occurrences across all data, with 114 tag
names. This count includes repeated book/entity text and generated material.
It measures parser diversity, not 261,935 candidate mechanical edges.

## 3. Why a Straight Import Would Be Wrong

### 3.1 Two core-rule versions coexist

`books.json` distinguishes PHB/DMG/MM from XPHB/XDMG/XMM. The latter Monster
Manual is dated 2025 even though it belongs to the revised core line; a date
cutoff is not a rules-version classifier.

The snapshot contains 361 PHB spell records and 391 XPHB spell records, sharing
**359 names**. The paired Counterspell records illustrate why name-based merging
fails: the earlier version has a spell-level/ability-check resolution, while
the revised record uses a Constitution save and different resource behavior.
Conjure Animals changes its mechanical dependencies substantially as well.

`reprintedAs` is useful cross-version discovery data, not proof of identical
mechanics or unconditional activation of the newer version. The publisher's
2024 compatibility guidance describes replacement with specific exceptions;
it is not blanket equivalence between matching names. Any executable
compatibility policy needs its own bounded source reading. [Publisher guidance](https://www.dndbeyond.com/posts/1810-updates-in-the-players-handbook-2024).

### 3.2 Name plus source is not a universal identity

Grouping raw records by `(entity type, case-folded name, source)` produces:

| Family | Collision groups |
|---|---:|
| Subclasses | 124 |
| Class features | 55 |
| Subclass features | 117 |

These are not necessarily defects. A feature can recur at different levels or
belong to different classes. Some subclass records adapt a source-defined
subclass to another class version. The native key needs parent identity.

`js/utils.js` defines class-feature UIDs using name, class name, class source,
level, and feature source. Subclass-feature UIDs additionally carry subclass
short name and subclass source. Using those fields on the observed raw arrays
produced zero collision groups for class features, subclass features, and
subclasses. That is a useful local check, not validation of all hydrated UIDs.

Preserve a type-specific upstream key, a physical source locator, and the
repository's canonical ID as **three different identifiers**. A JSON array
index is an exact snapshot locator, not a stable identity across updates.

### 3.3 Many records are instructions for constructing records

- 1,144 of 4,574 monsters carry `_copy`.
- 124 subclasses and 75 subclass features carry `_copy`.
- 67 items and 16 races carry `_copy`.
- 85 monsters and 17 races carry `_versions`.
- Magic variants use `requires`, `inherits`, templates, and substitutions.
- Files declare `_meta.dependencies` and `_meta.internalCopies`.

The effective object cannot be obtained with a shallow dictionary merge.
`js/utils.js` implements property-specific copy behavior, `_preserve`, `_mod`
operations, templates, and variable expansion. Missing values on a raw copied
record are not evidence that the effective creature lacks those mechanics.

`_copy` and `_versions` describe source-data construction. They must not become
game-rule `DERIVED_FROM` or `OVERRIDES` edges merely because the names resemble
graph concepts. Preserve the construction history as provenance instead.

### 3.4 Inline tags have different purposes

`{@spell ...}`, `{@condition ...}`, `{@creature ...}`, `{@item ...}`, and
`{@class ...}` can identify referenced entities. Dice, damage, roll, formatting,
filter, book, area, and display tags serve other purposes. Feature references
also occur as typed objects such as `refClassFeature`, not only inline text.

A link identifies a target; surrounding source establishes whether the
relationship gates, modifies, excludes, consumes, or merely mentions it.
Negative assertions and exceptions are especially dangerous to flatten.

Resolve tags using the pinned grammar and type-specific default-source rules.
Do not use global string splitting, strip all markup before reading, or default
every omitted source to the currently selected core edition. Preserve nested
tags and distinguish target identity from display text.

### 3.5 Generated spell lookups flatten distinctions we need

Spell records do not directly contain every class-list relationship.
`data/spells/sources.json` contains basic source-list mappings. The generated
spell-source lookup combines these with subclass, feat, race, optional-feature,
and other grants.

The generator's `_SpellSourceUtil.getSpellUids` collects `innate`, `known`,
`prepared`, and `expanded` references and resolves `choose`/`all` expressions
to candidate UIDs. The generated Fireball lookup includes both PHB and XPHB
class/subclass contexts. Treating this as unconditional spell access loses
grant type, choice, prerequisite, and version information.

Use the generated lookup as an index and differential-check input. Evidence
must trace to the actual list or granting rule and retain the distinctions:
on a base list, expanded list, always prepared, learned, innate, available as
a choice, or cast through another feature.

### 3.6 Upstream categories are not our semantics

- `optionalfeature` includes selectable class features; it does not mean an
  optional publication or the application's optional precedence layer.
- `variantrule` includes revised core glossary entries such as Advantage and
  D20 Test; it does not mean every record is optional.
- A book's `group: core` is catalog metadata, not sufficient authority for every
  contained rule's activation or optionality.
- `damageInflict`, `conditionInflict`, `savingThrow`, and similar useful fields
  are upstream annotations. Their meaning and coverage need validation against
  entries before they can support approved graph assertions.
- `referenceSources`, `otherSources`, and `additionalSources` are not all
  equivalent citations and must not each generate duplicate assertions.
- Foundry automation and UI filter tags can help discovery but are not source
  text or evidence that a mechanic behaves in a particular way.

## 4. Scope, Identity, and Edition Policy

### 4.1 Initial model

| Dimension | Proposed representation |
|---|---|
| Product family | `dnd5e`, application/catalog metadata |
| Governed graphs | `dnd5e-2014`, `dnd5e-2024`, if both are selected |
| Book | An exact work, e.g. PHB 2014 versus PHB 2024; not the entire 5etools website |
| Source instance | Exact supplied transcription/snapshot and work, including unresolved printing/errata status |
| Source record | Entity type plus native UID and snapshot-qualified JSON pointer |
| Canonical node | Ruleset-scoped approved identity with source-defined label |
| Activation profile | Which compatible source packages/options a campaign selects |

The existing assertion key has no edition or package-version field. Putting two
versions under a single unqualified node can both collapse distinct assertions
and retain incompatible outgoing dependencies. Citation differences cannot
solve this because citations are deliberately outside assertion identity.

Separate rulesets provide a bounded initial solution without changing all
existing systems. Shared code, external raw blobs, and source indexes can be
deduplicated without merging game semantics. Cross-version equivalence belongs
in a reviewed mapping catalog, not inferred same-ID canonical edges.

Within each ruleset, separately source-defined incompatible variants also need
an explicit identity/variant policy. Do not append a book code to every node
blindly, but do not merge two different mechanics because their headings match.
Compatible reprints may supply additional evidence for the same identity only
after the defining-locus comparison.

### 4.2 Supplements and compatibility

The old/new split is not an import rule that excludes all older supplements
from a revised campaign. Instead, define explicit source compatibility and
adaptation policies. A chosen older option may be admitted under the revised
profile with the relevant compatibility rule; automatic cross-version UID
redirection is not enough.

Never classify a source only by its code prefix, date, or folder. Official,
partner, playtest, promotional, setting, adventure, and homebrew content require
source-registry classification. Unknown authority remains unadmitted until
resolved. Upstream availability does not mean enabled in every campaign.

## 5. Proposed Ingestion Architecture

```text
External immutable snapshot + steward-approved source/rights selection
  -> local structural inventory and type-specific source index
  -> pinned copy/reference/variant resolver
  -> normalized records + origin/dependency map
  -> bounded Pandoc packets + structured evidence sidecars
  -> Analyst GUR -> Builder GUP -> Reviewer approval -> Integrator
  -> ruleset canonical graph
  -> optional versioned application/query projection
```

### 5.1 Snapshot and admission

Keep the full upstream tree outside the tracked repository. The owner can
remove this temporary copy after retaining an authorized immutable archive in
a local/content-addressed source store. Record its manifest and retrieval
instructions, not a machine-specific absolute path as durable identity.

Before source material becomes evidence, pin file bytes, package version,
available upstream revision, resolver/code version, and selected sources.
Retain content hashes even when an upstream commit is available. No production
job fetches mutable live upstream data during extraction or review.

Maintain a source admission list with explicit work, core revision,
publication category, provenance, permission basis, and approved purpose.
Allowlists apply to resolver dependencies too. If an admitted record requires
unavailable or unadmitted evidence, report that dependency instead of silently
fetching or copying it into a distributable packet.

### 5.2 Resolver

Prefer a small, tested Node bridge to the pinned upstream resolver over a new
Python implementation of its entire merge language. The observed package
requires Node >=24. Its JSON schema tests import `JsonTester` from
`5etools-utils`; installing the website alone is not proof that schema tooling
is present. Pin the lockfile and audit dependency execution before using it.

The bridge must have a strictly local data loader, immutable input copies, no
homebrew/prerelease auto-fetch, no network fallback, and bounded expansion.
Browser-oriented defaults must not select the newest version implicitly.
Do not use `generate-all` or a website build as an ingestion command: those
commands write upstream generated files and introduce unrelated work.

If upstream functions cannot run safely headless, implement only a declared
subset behind the same adapter interface, compare it against pinned upstream
fixtures, and fail on unsupported constructs. Do not silently approximate.

Resolution outputs retain both the raw record and effective representation,
plus every parent/template/reference input and field-origin mapping. Detect
cycles, missing targets, ambiguity, unknown operations, invalid default-source
resolution, and expansion limits explicitly. A technical resolution failure is
not an Analyst judgment call.

Avoid generating every magic-item/template permutation upfront. Keep template
definitions and materialize only selected instances when a source-backed
mechanical dependency or pilot test needs them.

Treat source strings as untrusted data, including apparent instructions to an
agent, HTML, URLs, and formula-like text. Never execute source expressions with
`eval`, follow external links automatically, or let a source record choose a
shell command or output path. Sanitize rendered content, reject path escapes,
and bound recursion, record size, and generated variants. The inspected
upstream code is a candidate dependency, not automatically trusted executable
code merely because the owner supplied the dataset.

### 5.3 Normalized source catalog, not a second canonical graph

Use one rebuildable local catalog, such as SQLite with JSON payloads, rather
than a separate script and data file for every entity type. This is an adapter
implementation choice, not a new deployment requirement.

| Logical relation | Purpose |
|---|---|
| `SourceSnapshots` | Exact manifests, source selection, resolver versions, rights classification |
| `SourceRecords` | Native type-specific keys, work identity, raw and resolved hashes, external blob references |
| `SourceLocators` | File hash, JSON pointer, section path, upstream entry ID, declared page and page basis |
| `ResolutionDependencies` | Copies, templates, feature references, filter inputs, and transformation provenance |
| `SourceReferences` | Parsed references with role, target resolution, original tag, and surrounding locus |
| `IdentityMappings` | Reviewed mapping from source identity to graph identity; no implicit label merge |
| `PacketPlans` | Exact selected record/section closure, deterministic boundaries, input digest, coverage disposition |

These are **source-processing records**, not new production edge types. No
normal packet worker writes directly to the catalog to alter canonical truth.
The catalog can be regenerated; immutable claimed evidence cannot.

### 5.4 Provenance through deletion of the temporary directory

For every materialized source unit retain:

```text
snapshot ID and manifest checksum
source work and repository source-instance ID
native entity type and full native UID
original relative file path, file SHA-256, JSON pointer, record digest
section/entry ID and page locator with its attribution basis
all resolver dependency file/record digests and transformation version
normalized record digest, rendered Markdown digest, packet ID
ordinary GUR -> GUP -> Review -> Approved -> Integration lineage
```

A JSON pointer is reproducible only together with its exact file bytes. A hash
without retained content is not enough to let a future Reviewer inspect the
source. Store permitted raw slices and their complete dependency closure in
the immutable evidence bundle, or require a retained, accessible external
archive. The packet must remain independently reviewable after `5etools/` is
removed. Restricted evidence must not leak through Git, reports, or logs.

The canonical CSV's `source_id` is the source **node** endpoint. Do not put
5etools book codes or source-instance IDs in it. Those belong in source
registries and artifact provenance.

## 6. Packetization Without Losing Structure

The source adapter is steward-operated tooling. It may deterministically render
supplied material; it may not author missing rules or turn inferred summaries
into source. Analyst remains responsible for interpretation, not acquisition.

Preserve the existing Pandoc Markdown packet interface for the first rollout.
Attach a schema-governed structured sidecar and locator map rather than asking
every role to parse arbitrary upstream JSON. The sidecar is supplemental
evidence, not an unchecked alias for GUR fields.

The current SOURCE_MARKDOWN contract does not specify precedence between
JSON-derived fields and rendered prose. An Architect Decision must define:

- Which fields are source transcription, upstream annotation, generated
  metadata, or repository-derived output.
- That rendering faithfully preserves supplied text, choices, tables, nested
  references, exceptions, and source labels.
- How conflicts between structured annotation and source text are reported.
  A structured convenience field never silently overrides its defining text.
- How a packet records complete selected source units without claiming to
  cover every printed page of a book.
- How the Reviewer independently checks the transform against the original
  retained source slice rather than trusting a shared rendered view alone.

### Page attribution

The upstream `page` field may identify an entry's starting page. It is not
proof that all nested paragraphs or rows occupy that page. Book trees have
nested page-bearing entries; arrays do not encode every physical page break.

Emit `{#pN}` only where the source map supports that attribution under the
existing marker semantics. Keep a declared entry page separate from an exact
evidence-fragment page. Where the latter is unknown, use a stable source
section/record locator, or request the supplied primary source if a page is
required. Never invent markers by interpolation, token count, or inherited
page estimates.

The candidate `tooling/analyst/packet_inputs.py` currently rejects packets
without resolved pages even though graph citations can use a stable section.
If page-less units are admitted, this specific preparation gate and packet
manifest/naming constraints need a reviewed adjustment. Do not use fake page
numbers to bypass it.

### Bounded unit policy

Prefer a complete rules subsection, a class feature group with its prerequisites,
or a small same-source spell group. Include the bounded supporting loci needed
to interpret it, not a recursive dump of every referenced spell and creature.
Keep dependency references to previously registered mechanics where possible.

Start the pilot with approximately 10-20 complete source units, not a full
rulebook. Treat that as an experimental cap: split at semantic boundaries and
measure actual context/output size. A record with extensive choices or inherited
text may need its own packet. A tiny label-only record may need no graph work.

Keep ordinary packet scope within one work/source. Where a granting rule or
copy depends on another work, declare the evidence dependency; do not relabel
it as the current book. Cross-book assertions follow the existing cross-book
contract or require an explicit packet-evidence amendment.

Planning many bounded packets locally is not permission for Analyst to claim
several at once. Preserve the existing single-packet relay unless the owner
separately changes it.

## 7. What Belongs in the 5e Graph

The project is an impact-analysis graph, not a complete character sheet,
compendium, encounter database, or executable combat engine. Preserve rich
source records outside canonical edges, even when most fields do not project.

| Source material | Recommended graph treatment |
|---|---|
| Named rule and explicit dependent mechanic | Candidate reviewed mechanical relationship |
| Save/check, concentration, action economy, recovery rules | Core dependency concepts, with direction justified by source |
| Spell-list eligibility | Mechanically operative classification/access relationship; distinguish grant modes |
| Class/subclass feature at a source-defined level | Parent-qualified identity and explicit eligibility dependencies |
| Feat prerequisites | Preserve AND/OR/choice structure; do not flatten into unconditional gates |
| Specific exception, immunity, replacement | Source-scoped negation/override/constraint, not mere mention |
| Damage dice, AC, HP, prices, speeds, DC values | Source/reference payload, not values in `aspect`/`condition` |
| Creature taxonomy | Include only where an evidenced mechanic uses that classification |
| Cosmetic description, artwork, maps, navigation | No mechanical edge solely because it exists |
| Explicit source cross-reference | At most reviewed reference evidence; not assumed impact propagation |

Existing edge concepts such as GATES, MODIFIES, CONSUMES, CONSTRAINS,
RESOLVED_BY, and EXCLUDES are useful candidates. Do not inherit Shadowdark's
classification whitelist, ancestry policy, or AD&D's race taxonomy as 5e
authority. Approve a 5e constitution from its own pilot evidence.

Candidate kinds to settle together include class/subclass/feature, species or
race as source-defined, feat, background, spell, condition, action, resource,
damage type, creature type, and item/weapon properties. Do not pre-register
every enum as a node. Some fit existing broad kinds; choose new prefixes only
when the mechanical role and identity rules warrant them.

### Conditional prerequisites and choices

The upstream prerequisite renderer explicitly handles multiple choices and
shared prerequisites. A list of alternatives must not become several mandatory
GATES edges. Preserve the Boolean/choice structure in the evidence model.
For an impact graph, reviewed dependencies can express relevance with bounded
qualitative applicability; they are not an executable eligibility engine.

If precise numeric eligibility or rule execution is wanted, define a separate
typed rule model and its projection. Do not encode thresholds in forbidden
edge fields or pretend free-text conditions are machine-evaluable predicates.

### A useful pilot example

For one edition's Counterspell, prepare the complete spell entry, its reaction
trigger, and the relevant casting/resolution loci. Analyst determines the
actual reaction, check/save, and resource dependencies; Builder normalizes;
Reviewer verifies those assertions. The opposite edition's record is a
negative isolation fixture, not additional mechanics merged into the spell.

For a Fireball access example, distinguish its base class lists from a subclass
grant or an optional choice. The presence of a generated lookup hit alone
cannot prove the caster always knows or may cast that spell.

## 8. Deterministic Work Versus Model Work

**Do locally and in batches:** JSON parsing, schema checks, hashes, native UID
resolution, copy expansion, reference indexes, coverage accounting, source
selection, bounded packet rendering, input/output integrity, and duplicate
candidate detection.

**Keep interpretive:** whether a relationship is mechanically load-bearing,
direction, exceptions, applicability, authored polarity, contested identity,
and source authority. Analyst proposes; Reviewer independently verifies.

Initially, structured fields may prefill candidate hints, never silently
approved GURs or graph rows. Repeated source-to-edge transformations can later
become governed extraction templates with explicit semantics and regression
fixtures. Any inherited general rule retains its existing Architect approval
requirements; a convenient mapping table is not that approval.

Prefer one adapter CLI with subcommands such as `inspect`, `plan`, `materialize`,
and `verify`, implemented as modules, over dozens of per-book scripts. These
names are proposed interfaces, not commands installed by this assessment.
Integrate approved preparation into the existing batched workflow rather than
creating a second queue or five separate parser implementations.

Each role should receive a compact manifest, complete bounded source units,
targeted graph/registry slices, unresolved dependencies, and an exact next
command. Keep full mechanical logs on disk and return concise failures/counts.
Never feed 115 MiB of data or a generated cross-reference index to the model.

## 9. Rights, Retention, and the Multi-User Product

The local project declares MIT for its software. That is not, by itself,
evidence that every included publisher text or asset is licensed for our
redistribution. Keep software license, source-content permission, and campaign
access as separate records. This is a design boundary, not a legal opinion.

For a distributable baseline, use the publisher's SRD as the authoritative
content selection and preserve its attribution. The publisher makes SRD 5.1
and 5.2 available under CC BY 4.0 and currently provides 5.2.1 downloads. This
does not establish permission for every rulebook represented in the local
dataset. [Official SRD page](https://www.dndbeyond.com/srd).

CC BY requires attribution, a license link, and indication of changes; its
terms also prohibit additional restrictions on the licensed material. Verify
the actual selected source's notice and obtain appropriate advice for a
commercial release, restricted publisher material, or customer uploads.
[Creative Commons terms](https://creativecommons.org/licenses/by/4.0/).

Do not simply filter `srd == true`. The snapshot uses `srd` and `srd52` as
booleans **or alternate-name strings**, such as Bigby's Hand -> Arcane Hand.
Basic Rules availability is another field and is not an interchangeable
license. A rights-safe SRD pipeline must compare the selected record to the
actual SRD version and resolve labels, text, citations, and coverage against
that source. Keeping a book label with an SRD flag is not sufficient.

For private analysis, the adapter can inspect the owner-supplied wider corpus
without treating it as publishable product content. Decide retention and
permitted output explicitly before staging a shared dataset. Graph-only
output should not be assumed automatically exempt from all content concerns.

### Relationship to the four-layer design

Preserve the owner's precedence: **campaign > setting > selected optional >
core**. Edition selection is a compatibility baseline, not another layer.
Keep source truth immutable; resolve campaign-specific replacements before
traversal in an effective query graph, not by deleting the shared source rule.

The earlier [Spanner review, section 12](SPANNER_GRAPH_CONVERSION_REVIEW.md)
already separates packages, versions, settings, campaign overrides, access,
and source assertions. The 5e adapter should retain the source identity and
variant mapping needed by that design without requiring Spanner for intake.

Settings are not identified solely by a label such as Forgotten Realms. Pin
the work, rule revision, package version, and access basis. A user setting fork
does not confer redistribution rights to its inherited contents. Keep the
unanswered campaign-member sharing policy explicit; this assessment does not
decide whether a member inherits the campaign owner's content access.

## 10. Repository Integration and Ownership

Proposed layout, instantiated only after approval and source selection:

```text
rulesets/dnd5e-2014/             # optional first/second governed baseline
rulesets/dnd5e-2024/
  ruleset.yaml
  governance/constitution.md
  registries/                   # books, exact sources, nodes, governed metadata
  profiles/                     # ruleset-specific impact/role policy
  escalations/                  # normal Decisions and escalation lifecycle
  canonical/                    # created only by approved Integrator genesis
schemas/<selected-5e-ruleset>/
  graph/
  registries/
  books/<selected-work>/
books/<selected-5e-ruleset>/<selected-work>/
  book.yaml
  source/<exact-source-instance>/
  packets/incoming/
  packets/claimed/
  artifacts/                    # existing GUR/GUP/Review/Approved/Integrated kinds
tooling/source_adapters/fivetools/  # proposed shared deterministic adapter
```

An official SRD-first import gets its own work/source records. Do not register
its source as PHB simply because upstream spell records cite PHB pages.
No canonical directory or header-only fake baseline is created by Architect.

| Work | Proposed owner | Required boundary |
|---|---|---|
| Select and retain lawful exact source snapshot | Owner/source steward | No pipeline role reconstructs missing content |
| Ruleset bootstrap, identity/version/rights metadata contract, extraction boundary | Architect | Durable Decisions, versioned contracts, exact ownership |
| Shared adapter, schemas within assigned implementation scope, reproducibility and packet-generation tooling | Builder, explicitly assigned | No canonical writes or automatic source judgments |
| GUR interpretation from complete steward-materialized packet | Analyst | One active packet, no silent edition/identity merge |
| Independent adapter evidence tests and ordinary assertion review | Reviewer | Check raw-to-rendered fidelity and independent source judgment |
| Genesis, transactional integration and any required sidecar retention hook | Integrator | Independently verified support, rollback and terminal provenance |

Existing reuse points:

- `tooling/builder/src/adnd1e_builder/vocab.py` loads registered rulesets,
  prefixes, edge types, book codes, and governed historical versions. Do not
  create a second complete compiler merely because its package name is old.
- `tooling/integrator/src/adnd1e_integrator/vocabulary.py` and `canonical.py`
  support ruleset-scoped vocabulary and in-memory genesis. Validate them with
  the selected 5e configuration; do not assume that old passing tests prove it.
- `tooling/analyst/packet_inputs.py` and the Pandoc page parser can consume
  materialized Markdown, subject to the locator/sidecar changes above.
- `tooling/common/artifact_io.py`, `validate_artifact.py`, and the existing
  lineage-derived queues retain publication and ownership gates.
- `tooling/common/BATCH_WORKFLOW.md` explicitly labels its consolidation
  tooling as a candidate. Do not treat availability as live rollout approval.

A new ruleset must supply its own parsed polarity table and identity policy.
The Builder vocabulary code retains legacy fallback constants in some paths;
acceptance tests must prove missing/malformed 5e governance cannot silently
borrow AD&D semantics. Do not broaden that repair into unrelated refactoring.

## 11. Pilot and Rollout

### Phase A: source and identity proof

Choose the initial edition and allowed works. Freeze the snapshot and a small
golden fixture set. Build the source inventory, resolver, identity mapping,
provenance, and raw-to-Pandoc checks without creating graph assertions.

Use fixtures that expose the real hard cases: paired Counterspell versions,
Fireball list/grant distinctions, a concentration rule, a feat with alternative
prerequisites, a repeated class feature, a copied subclass, a copied monster,
a magic variant, a negative/immunity statement, and a nested page/table entry.
Use SRD-authorized or independently permitted fixtures for shared test data;
private fixtures may be verified by digest without copying their content into
the public repository.

### Phase B: one end-to-end mechanical slice

Approve the initial 5e constitution and schemas, then run a complete small
packet through all four worker roles. Include source coverage, independent
Review, successful genesis, simulated rollback, and explanation queries.
No bulk ingest until this proves the source map survives the entire lifecycle.

Verify useful explained queries, not only row counts: which reviewed mechanics
depend on concentration, which dependencies differ between the two Counterspell
versions, and why a particular class or feature grants access to a spell.
Results must distinguish mechanical paths from references and disclose
conditional applicability. These are impact explanations, not simulated play
or a claim of complete character eligibility calculation.

### Phase C: dependency-ordered core coverage

Build shared mechanics first: checks/saves, actions/reactions, advantage,
proficiency, conditions, concentration, spellcasting resources, recovery,
damage/resistance, and eligibility. Then classes/features, species/backgrounds,
feats, spells, equipment, and selected creature mechanics.

Order is based on the selected source's dependencies, not alphabetical file
order. Keep a deterministic packet plan and an explicit covered/held/excluded
source-unit ledger. An intentionally excluded stat value is not a missing edge;
an unresolved source reference is not completed coverage.

### Phase D: supplements and incremental changes

Add opted-in supplements, setting mechanics, and adventure-specific mechanical
rules after core. Do not extract every encounter and narrative mention.

On upstream update, diff source records and resolver dependencies by key and
digest. Re-materialize only affected units. Classify adds, changes, removals,
renames, and version moves; file reordering alone must not recreate identities.
Existing claimed packets stay immutable; updates use successor source/artifact
lineages and reviewed changes. Upstream deletion never directly deletes a
canonical node or assertion.

Measure pilot source tokens, model turns, correction cycles, extraction time,
and accepted assertions before estimating the full corpus. Raw entity counts
cannot support an honest token-cost or completion-time estimate.

## 12. Acceptance Criteria Before Bulk Import

1. All selected files parse and validate against the pinned upstream schema
   set; unknown constructs fail explicitly instead of disappearing.
2. Native identities resolve uniquely with source/parent/level context. Default
   source handling matches the pinned upstream grammar, not current UI style.
3. PHB and XPHB Counterspell stay distinct. A 2014 effective graph cannot gain
   the revised save dependency merely because that record is newer.
4. Copy, preservation, modification, templates, subrace merge where admitted,
   and version expansion match golden fixtures; cycles and missing dependencies
   fail. Raw inputs remain byte-identical.
5. Every output source fragment resolves to retained input bytes, native key,
   JSON pointer, all construction inputs, and renderer/resolver versions after
   the temporary checkout has been removed.
6. Unknown pages remain unknown. Nested pages, tables, inline references,
   superscripts/subscripts, and choices survive Pandoc rendering and parsing.
7. SRD alternate-name strings and Basic Rules flags cannot bypass source
   admission or label verification; restricted parent dependencies do not leak.
8. Generated spell lookups, `optionalfeature`, `variantrule`, `_copy`, and
   `reprintedAs` do not create unreviewed activation or mechanical assertions.
9. Alternative prerequisites remain alternatives; negative rules, conditional
   grants, exception clauses, and limited-use resources retain their scope.
10. Both graph endpoints are registered, production fields and assertion keys
    conform, citations are retained, and duplicate evidence is not duplicated
    into canonical assertions. Numeric stat values do not enter forbidden fields.
11. A complete packet has source-unit coverage accounting, not merely an edge
    count. Multiple representations of one locus do not create multiple jobs.
12. Repeating materialization with identical inputs yields identical outputs;
    dependency changes invalidate affected packets, while unrelated changes do
    not. Corrupt/stale inputs fail before publication.
13. Reviewer can detect an adapter error from original retained evidence even
    if Analyst and Builder both used the same bad rendering.
14. Normal genesis succeeds only after independent approval. Injected failures
    restore absent canonical state or the previous state exactly; replay cannot
    duplicate an integration. Other rulesets remain unchanged.
15. Baseline selection and campaign layers resolve before traversal. Disabled
    or unauthorized variants cannot create intermediate paths or leak evidence.
16. Pilot tests work with a local supplied snapshot and no network calls. No
    website build, remote homebrew fetch, corpus-wide prompt, or unapproved
    canonical write is needed.

## 13. Decisions Needed

The owner was asked during this assessment whether to target 2014, revised
2024, or both, and whether initial use is private or a multi-user product.
No reply had been received when this proposal was written. The recommendations
above remain conditional, not recorded answers.

The next bounded Architect assignment should settle:

1. First edition/work and permitted source scope; recommended public baseline
   is the matching official SRD, with wider supplied data used as research until
   admitted for the intended use.
2. Two governed baselines initially versus a larger version-aware canonical
   redesign. Recommend two namespaces with shared tooling for the initial rollout.
3. Exact source evidence, page/section, sidecar, identity-mapping, and packet
   coverage contracts, including conflicts and reproducibility after removal.
4. The pilot ontology and which structured mappings remain candidate hints.
5. Exact implementation paths and owners, with Reviewer approval before normal
   packet work or canonical genesis.

This assessment deliberately does not assign live work to Gemini or another
role. The owner requested a proposal and is obtaining an independent proposal
from Gemini. Compare these decisions before either agent implements a competing
source model.

## 14. Evidence Map and Limits

| Local input | What it supports |
|---|---|
| `5etools/package.json`, `LICENSE.md` | Snapshot application version, runtime/dependencies, software license declaration |
| `5etools/data/books.json`, `adventures.json` | Work catalogs and versioned core identities |
| `5etools/data/book/book-phb.json`, `book-xphb.json` | `bookData` nested source trees and page-bearing units |
| `5etools/data/spells/spells-phb.json`, `spells-xphb.json` | Paired mechanics, metadata, source/page fields, SRD alternate names |
| `5etools/data/class/class-wizard.json`, `class-artificer.json` | Parent-qualified features, classic/one editions, mixed-source grants and copies |
| `5etools/data/feats.json`, `magicvariants.json`, `races.json` | Prerequisites, choices, templates, inherited/variant records |
| `5etools/data/bestiary/bestiary-bgdia.json` | Multi-source copy dependencies and modifications |
| `5etools/js/utils.js` | Metadata merge, copy engine, type-specific UID packing/unpacking |
| `5etools/js/utils-dataloader/utils-dataloader-dereferencing.js` | Feature/reference expansion machinery and bounds |
| `5etools/js/render.js` | Prerequisite rendering and alternative/shared structure |
| `5etools/js/converter/converterutils-spell-sources.js` | Grant flattening and generated spell lookup construction |
| `5etools/test/test-json.js` | Upstream schema-test dependency and file routing |
| `contracts/SOURCE_MARKDOWN.md`, `SCOPE_AND_IDENTITY.md` | Current packet source and namespace boundaries |
| `contracts/ARTIFACT_LIFECYCLE.md`, `WORK_QUEUES.md` | Immutable artifacts, independent review, consumption, and active packet routing |
| `rulesets/shadowdark/governance/constitution.md` | Existing impact-graph grain as a comparison, not 5e authority |

Key inspected code-file SHA-256 values:

```text
5etools/package.json
380f8024f70a309262b1862d1c0dc0d43c7c856d95a67c4908ecf1ea42f8b78c
5etools/js/utils.js
06df4edef6739498e420709b5c2e31599f723d12310a4c61bd90e9b33acf96d2
5etools/js/render.js
44c5db7bebb3f32751311a0d6536242455882de7dbbb83e31f452e52d45114e3
5etools/js/converter/converterutils-spell-sources.js
55a051d95bc841a2a9dddf0cdc0e793efb97bde9ed666f4132cd165be3255821
5etools/test/test-json.js
b4c1a799228c66df9cd03bc305a63419d6757f7903efd5b2636eb0646dff0a5a
```

The broad census ran successfully. Two exploratory read snippets initially
assumed the wrong book wrapper/default Windows encoding; reruns used
`bookData[0].data` and JSON bytes. These were probe issues, not upstream parse
failures. Upstream tests, resolver execution, production graph suites, cloud
queries, and a 5e end-to-end integration were **not** run or claimed to pass.

`5etools/` was not tracked by Git at inspection time, but the current `.gitignore`
does not exclude it. Avoid `git add .` while it remains here. Prefer moving it
outside the checkout or adding an owner-approved local exclusion. This task
does not stage, commit, delete, or modify that supplied directory.

The source pointers above intentionally describe a temporary local snapshot.
This proposal embeds the important findings so it can travel without that
directory. Reproducing the measurements requires the retained snapshot and the
ignored inventory helper, or an equivalent independent census. Do not treat
the report's dated numbers as a substitute for verification of later inputs.
