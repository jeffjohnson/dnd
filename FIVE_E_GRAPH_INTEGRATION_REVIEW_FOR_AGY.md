# 5e Proposal Reconciliation: Codex Review for AGY

Date: 2026-10-26. Role: Architect. Status: review and proposed reconciliation,
not an implementation Decision, source admission, or graph mutation authority.

Reviewed inputs:

- [AGY proposal](FIVE_E_GRAPH_INTEGRATION_PROPOSAL_AGY.md)
- [Codex proposal](FIVE_E_GRAPH_INTEGRATION_PROPOSAL_CODEX.md)
- The supplied local `5etools/` snapshot and targeted repository contracts/code.

## 1. Verdict

**Keep AGY's core-first delivery plan, keep Codex's source/identity/provenance
controls, and reduce the initial implementation to the constructs the selected
core packets actually use. Neither proposal is implementation-ready as written.**

AGY describes the first useful graph more concretely. Codex explains why the
whole dataset cannot be imported naively, but makes too much of the eventual
general-purpose adapter look like a prerequisite for the first packet.

The most important new finding is shared: **book JSON is not necessarily
self-contained source text.** The PHB condition appendix and most of the revised
glossary are embedded record references. Even a small book-first converter
needs typed definition expansion, not just recursive prose extraction.

### Priority Findings

| ID | Severity | Proposal | Finding |
|---|---|---|---|
| R01 | High | Both | First-packet readiness was not grounded in a measured render/dependency closure; essential definitions live outside the book file. |
| R02 | High | AGY | `<!-- p189 -->` is not an accepted page marker; entry page metadata cannot prove every evidence fragment's printed page. |
| R03 | High | AGY | The future 2024 supersession option does not specify how incompatible assertions remain isolated under the current five-field key. |
| R04 | High | AGY | No retained snapshot/dependency/transform evidence plan survives removal of the temporary checkout. |
| R05 | High | AGY | Published-source rights and permitted output are not addressed, despite the intended multi-user application. |
| R06 | Medium | Codex | General hydration, a catalog, and broad fixtures are front-loaded before a much smaller core-only pilot. |
| R07 | Medium | AGY | Chapter-scoped packet contents cross source chapters; five broad topics are presented as five fixed packets. |
| R08 | Medium | AGY | Folder-level permanent exclusions discard potentially mechanical content and useful parser implementation evidence. |
| R09 | Medium | AGY | Ontology examples conflate skills/proficiencies and features/resources, and leave parent-qualified feature identity unspecified. |
| R10 | Medium | Both | The converter and Reviewer need explicit source-unit coverage and independent fidelity oracles, not only parse/schema success. |

These priorities concern the proposed implementation. No defective canonical
5e data was found because no 5e canonical import has been authorized here.

## 2. What Codex Missed or Underemphasized

### C01. The smallest useful delivery slice

AGY correctly makes the shared rules machinery the first deliverable: checks,
advantage, proficiency, actions, damage, conditions, resting, and spellcasting.
My proposal contains that ordering, but buries it behind a broad resolver and
catalog architecture. That could cause avoidable implementation work and delay.

Correction: make a **core document renderer with bounded embedded-definition
expansion** the first adapter capability. Do not require creature `_copy`,
subrace merging, magic-item templates, every feature UID, or all 114 observed
inline tag names before processing a selected core subsection.

A simple manifest plus immutable evidence files can serve the first pilot.
SQLite remains an optional later indexing implementation, not a gate. A Node
bridge is appropriate where upstream semantics are needed, not a mandatory
dependency for every plain-text source block.

### C02. The glossary as a bounded acceptance fixture

AGY identifies the revised glossary as a tractable collection of definitions.
I should have measured its exact structure and used it as a concrete fixture.
It is not automatically our ontology, but it is an excellent test of reference
resolution, ordering, citations, and coverage.

The measured correction is **155 embedded definitions**, not 159 definitions:
the Rules Definitions array has 159 entries comprising 155 `statblock`
references, one introductory string, and three images. Those references span
six entity kinds; see R01 below.

### C03. Rendering completeness is more specific than generic reference support

I described inline tags and `refClassFeature`-style references, but did not
identify the immediate `statblock` dependency in the first core work. Nor did
I call out `abilityGeneric`, which occurs in the 2014 ability-check chapter
and carries the passive-check formula as source text.

Correction: record a per-packet inventory of source AST node types, embedded
definitions, and inline tags before implementation. An unknown node cannot be
silently dropped. In particular, numeric/formula text must remain in **source
evidence**, even though it must not be placed in canonical edge fields.

### C04. A concrete ontology review worksheet

AGY's prefix table makes the intended concepts easy to discuss. My list of
candidate kinds is safer than premature approval but less actionable.

Correction: prepare a proposed kind/identity worksheet with defining source
loci, distinction from existing kinds, permitted relationships, and examples.
Do not approve the names solely because they look familiar. Especially separate
skill, proficiency in that skill, proficiency bonus, saving throw, saving-throw
proficiency, feature, and resource. They are not interchangeable nodes.

### C05. The entry point should not depend on resolving every future product choice

My report correctly preserves campaign-layer and access requirements, but the
first private source-rendering pilot does not need a deployed multi-tenant
resolver, Spanner, complete compatibility mappings, or every sharing-policy
answer. Preserve the necessary provenance and version boundaries now; defer
unneeded application implementation.

Similarly, two eventual edition namespaces do not require two simultaneous
bootstrap efforts. Pick one initial edition after the owner's answer and keep
the other as an isolation fixture. Namespace naming should not imply that the
second graph already exists.

### C06. Audit portability and clearer denominators

My 519-file census is specifically `data/**/*.json`. AGY's larger file count
is the whole tree. I should have put both denominators in the summary to avoid
the appearance of disagreement. My detailed audit helper is ignored scratch;
AGY should not need that unavailable helper to understand the proposed pilot.

Correction: keep a small portable fixture manifest and reproducible read-only
checks with the eventual implementation. Do not ship the entire upstream tree
or a new permanent script for every exploratory measurement.

## 3. What AGY Missed or Needs to Correct

### R01. Resolve embedded definitions before calling a packet complete

AGY sections 4 and 6 describe extracting chapters into Markdown. A renderer
that only copies `entries` strings would lose central rules:

| Source locus | Measured structure | Required supporting input |
|---|---|---|
| PHB `/bookData/0/data/12` | 15 embedded condition references | `data/conditionsdiseases.json`, PHB records |
| PHB `/bookData/0/data/9` | 11 embedded action references | `data/actions.json`, PHB records |
| XPHB `/bookData/0/data/10/entries/1/entries` | 155 embedded definition references | Six typed collections below |
| PHB `/bookData/0/data/7` | One `abilityGeneric` node | Preserve its supplied entry text, not a synthesized explanation |

The revised glossary references resolve to:

| Tag | Definitions | File |
|---|---:|---|
| `variantrule` | 115 | `data/variantrules.json` |
| `action` | 13 | `data/actions.json` |
| `condition` | 15 | `data/conditionsdiseases.json` |
| `sense` | 4 | `data/senses.json` |
| `status` | 3 | `data/conditionsdiseases.json` |
| `hazard` | 5 | `data/trapshazards.json` |

All 155 references resolved uniquely by their declared name/source in this
targeted check. None of those target records had `_copy`. This supports a
small initial resolver; it does not validate their transitive references or
the whole upstream hydration engine.

Important distinction: **`statblock` is a renderer construct, not a synonym
for monster data.** Do not exclude it under a blanket creature-statblock rule.
The upstream implementation handles this through
`Renderer.utils.preload` in `5etools/js/render.js`, around lines 5607-5667.

Preserve the containing book locus and the resolved definition's original
file/record/citation. Inline expansion must not erase where the definition
actually came from. Ordinary hyperlinks need not recursively inline all their
targets; definition embeds do. This distinction bounds packet size.

### R02. Fix the page-marker and attribution contract

AGY line 177 offers `{#p189}` or `<!-- p189 -->` as alternatives. Only the former
belongs to the current reserved page-marker syntax. The latter is an HTML
comment, not the page marker defined by
[SOURCE_MARKDOWN](contracts/SOURCE_MARKDOWN.md), section Page Marker.

AGY line 188 also overstates provenance as exact citations derived from
official printed markers. The supplied JSON contains upstream page metadata,
not a fresh independent verification of printed layout. For example, the PHB
conditions container starts at page 289, while its resolved Blinded entry
declares 290 and Exhaustion declares 291. Propagating the container page to
all expanded definitions would miscite them.

Required correction:

- Use only supported Pandoc markers and their exact structural semantics.
- Record whether a page belongs to a containing section, entry, or evidence
  fragment. Do not manufacture finer precision.
- Preserve stable section/record locators where a fragment page is unknown.
- Test the existing page parser on generated Markdown.
- If a selected page-less unit cannot pass current preparation, authorize the
  bounded locator/gate change rather than inventing a page number.

### R03. Separate rollout order from edition storage policy

AGY section 3's 2014-first recommendation is a reasonable product choice, not
a technical error. The unresolved part is the later introduction of 2024 as a
revision or supersession layer in the same `dnd5e` graph.

Our current assertion key does not carry edition, package version, or activation
profile. Matching spell names can have incompatible dependencies; simply adding
new citations or newer-publication overrides does not yield an isolated 2014
view. The owner's four application layers are also not an edition migration
mechanism.

Recommendation: select one initial edition, use an explicit edition-qualified
namespace, and share adapter code. Add a second governed baseline only when
requested. A single mixed graph is an alternative requiring a larger explicit
contract and resolver design, not something the extractor gets to infer.

AGY's phrase 'every single entity' has an explicit source code is too broad.
For example, the first magic variant has no top-level `source`; its source is
under `inherits`. References may omit source and rely on type-specific defaults.
Class/feature identity additionally needs parent and sometimes level context.

### R04. Make the temporary-directory removal survivable

AGY's book/page/section citations are necessary but insufficient to reproduce
the transform. The owner explicitly intends to remove `5etools/` from the repo.
Keeping it 'untouched as a read-only intake reference' does not address that.

Retain a snapshot manifest, exact input bytes or accessible authorized archive,
native identity, JSON pointer, file/record hashes, embedded-definition closure,
transform version, and rendered-packet checksum. A source instance such as
`phb-5etools-intake` must point to an exact snapshot, not a mutable directory.
Hashes alone cannot reconstruct missing evidence.

Also retain byte-immutable claims and use ordinary successor artifacts after
upstream changes. No upstream removal or changed `reprintedAs` field directly
changes canonical data.

### R05. Include a source-admission and permitted-output gate

AGY does not distinguish the software's license from the included publisher
content or the future application's access policies. Before distributing
packets, fixtures, or a public product, record the permission basis and allowed
use for the selected source. The Codex proposal's section 9 discusses an
official-SRD baseline and the alternate-name `srd`/`srd52` fields.

This is not a reason to stop inspecting the owner's supplied data. It is a
reason not to treat availability as redistribution permission. Keep private
analysis, shared source evidence, and application-visible content distinct.
Source selection still awaits the owner's answer; neither proposal is that
answer or a legal determination.

### R07. Correct packet loci and use topics rather than fixed packet sizes

AGY's Chapter 8 packet includes action economy, standard actions, and Cover.
In the supplied 2014 PHB tree, these named loci are in Chapter 9:

| Topic | JSON pointer within `book-phb.json` | Declared page |
|---|---|---:|
| Bonus Actions | `/bookData/0/data/9/entries/6/entries/3/entries/4` | 189 |
| Reactions | `/bookData/0/data/9/entries/6/entries/4` | 190 |
| Actions in Combat | `/bookData/0/data/9/entries/8` | 192 |
| Cover | `/bookData/0/data/9/entries/10` | 196 |

A cross-chapter topical packet is possible if its manifest and retained evidence
declare the actual units. It cannot be described as just a Chapter 8 extraction.
Prefer five **topic groups**, split into complete bounded packets after measuring
their text and dependencies. Chapter 9 alone contains 41,297 characters across
all raw JSON strings before expanding its 11 action definitions; that measure
is not a token count but demonstrates why chapter count is a poor workload cap.

The proposed `PKT-5E-PHB-CH07-...` names also differ from
[FILE_NAMING](contracts/FILE_NAMING.md)'s page-range convention. Do not assume
permissive schemas ratify new naming. Choose conforming IDs once page scope is
known or explicitly authorize a stable-section naming extension.

Finally, one repeated `incoming/source.md` cannot be the durable output path
for several separately claimable packets. Use distinct deterministic intake
names and create-only publication. Pandoc frontmatter is informational under
SOURCE_MARKDOWN; it does not replace the authoritative claimed `packet.yaml`
and required identity/checksum metadata.

### R08. Defer broad collections instead of classifying them all as non-rules

AGY's 'Excluded Entirely' tier groups website code, adventures, monsters, and
decks together. These do not have one semantic status.

- Website assets need not become graph content, but the renderer and resolver
  code are useful specifications for decoding the data.
- Individual creature numeric values are not our mechanical graph's purpose;
  shared creature rules and source-defined exceptions can be relevant.
- Adventure and deck records may contain mechanically operative effects.
  Their directory does not prove they are only narrative or flavor.

Use 'outside initial import; admit selected mechanical loci later' for content
collections, and 'not graph content; may be adapter implementation evidence'
for code. This preserves the core-first focus without a permanent blind spot.

### R09. Tighten the concept boundaries before approving prefixes

AGY's prefix examples should remain proposals, not registrations. Specific
questions for the ontology worksheet:

1. `prof_athletics` versus an Athletics skill and proficiency in Athletics:
   which concept does the node represent, and how does a rule granting
   proficiency differ from a rule modifying a check?
2. Saving throw versus proficiency in that saving throw: do not merge them.
3. Class feature versus expended resource: Action Surge, Sneak Attack, Favored
   Enemy, and Spellbook do not all become the same kind of 'resource track'.
4. Features with repeated names need parent-qualified identity, including
   source/level distinctions where they identify different definitions.
5. Numeric hit-die values and progression tables remain source payload;
   dependencies on the Hit Dice mechanic can be graph assertions.

The existence of a closed vocabulary in GRAPH_INVARIANTS does not itself
approve a new prefix or its 5e semantics. The ruleset constitution must define
them and the production schema/tooling must agree.

### R10. Replace '100% unchanged' with explicit proof obligations

AGY line 187 promises unchanged governance and identical invariant checking.
Reuse is desirable, but this is not demonstrated. JSON transcriptions,
embedded evidence, transform authority, page provenance, and optional sidecars
need a declared contract. Some choices can preserve the existing Markdown-only
worker interface; that does not remove the source-adapter verification work.

The quoted CLI option names exist in the local parsers. The Builder example
still needs an actual GUR positional input; neither example demonstrates that
an unregistered 5e ruleset compiles or integrates. Do not run an import merely
to test an illustrative command.

Require focused 5e fixtures, publication integrity, independent transform
verification, current schema/vocabulary agreement, and Integrator genesis and
rollback tests before the first live integration. A header-only node registry
is not the same as fabricated canonical state; AGY's empty registry proposal
is not itself a violation. Keep canonical initialization Integrator-owned.

## 4. Inventory and Completeness Corrections

These measurements reconcile the reports; they do not decide source quality.

| Scope | Measured count/size |
|---|---|
| Whole `5etools/` tree | 2,146 files, 159,095,713 bytes = 151.725 MiB |
| `data/**/*.json` | 519 files, 120,637,208 bytes = 115.049 MiB |
| AGY Tier 1's exact listed files | 2,058,615 bytes, about 1.96 MiB |
| AGY Tier 2: `class-*.json` plus PHB/XPHB spells | 3,464,687 bytes, about 3.30 MiB |
| AGY Tier 3's exact listed files | 4,779,762 bytes, about 4.56 MiB |

AGY's total file count is correct. Its 151.7 figure uses binary units, so label
it MiB, not decimal MB. Its tier sizes are not a reproducible partition of the
listed paths; recompute them or label them illustrative scope groupings rather
than an audited allocation. Codex's smaller total is not evidence of missing
JSON files: the denominators differ.

The supplied files do not prove a 'complete digital extraction' of all 5e.
Neither a large inventory nor a zero-error schema result establishes source
completeness. Describe the selected snapshot and coverage rather than 'all'.

AGY's repository-success introduction also omits Shadowdark, whose independent
ruleset vocabulary/genesis work is particularly relevant precedent. Do not call
AD&D a fully verified complete graph solely because canonical files exist.
The earlier [Spanner review](SPANNER_GRAPH_CONVERSION_REVIEW.md) documents its
legacy quality boundary with dated measurements. This review did not rescan
AD&D or RC; AGY's RC counts are not independently certified here and are not
needed to decide the 5e adapter architecture.

## 5. Reconciled Minimum Implementation

### Step 1: choose one baseline and the first admitted source

Owner chooses 2014 or revised 2024 first and the intended permitted use. That
choice is still unanswered in this conversation. AGY's preference for 2014 is
a recommendation, not an instruction already given. Keep the other edition
as a negative isolation test without initializing its graph.

### Step 2: define one small source contract and capability profile

Architect records the source-instance/snapshot model, evidence retention,
supported source AST, page/section rules, embedded-definition expansion,
unknown-construct behavior, edition isolation, and exact ownership.

Separate two capabilities:

- **Core document profile:** nested entries, lists, tables, relevant special
  blocks, supported inline tags, and the exact action/condition/glossary embeds.
- **Entity profile, later:** complex native identities, copies, templates,
  variants, subrace composition, class-feature expansion, and spell grants.

Discover the required closure from the selected input before choosing what to
implement. Do not silently ignore an unsupported node to keep the first profile
small. If an input needs a later capability, defer that input explicitly or
extend the profile with tests.

### Step 3: build one tool, not two pipelines

Builder implements one bounded source-adapter interface. A Python entry point
with a pinned Node helper where needed is compatible with both proposals.
Use manifests/files initially; introduce a database only if indexing or update
requirements justify it. Do not duplicate the graph compiler or queues.

Its first demonstration must produce a retained raw evidence slice, exact
dependency list, Pandoc Markdown, transform map, coverage report, and reproducible
hashes without publishing graph artifacts or mutating the source snapshot.

### Step 4: independently prove fidelity before packet release

Reviewer verifies the transform against original input, not just Analyst's
rendered packet. Minimum concrete fixtures:

| Fixture | Required outcome |
|---|---|
| PHB condition appendix | All 15 definitions expand once in source order; references are not mistaken for complete text. |
| PHB Blinded and Exhaustion | Their target pages remain 290 and 291; neither inherits 289 solely from the appendix container. |
| PHB combat actions | All 11 embedded records resolve under the correct defaults; none silently switches to XPHB. |
| Revised glossary | 155 definitions resolve across six types; intro/images are accounted for but not counted as definitions. |
| Passive check source block | `abilityGeneric` text survives in the evidence; no formula is copied into prohibited graph fields. |
| Malformed/missing target | Fail with the source pointer and native target key; no empty successful packet. |
| Unsupported page comment | `<!-- p189 -->` is not accepted as our printed-page marker. |
| Source mutation/replay | Changed inputs fail stale publication checks; identical inputs reproduce identical output. |
| Independence | An intentionally omitted definition or altered sentence is detected from original evidence. |

### Step 5: release one bounded packet through the normal relay

For a 2014 pilot, the exact Advantage and Disadvantage and Proficiency Bonus
subsections are useful candidates:

```text
book-phb.json#/bookData/0/data/7/entries/7
book-phb.json#/bookData/0/data/7/entries/8
```

Read their complete supporting context before selecting them. This review does
not author a packet, decide its final ID, or claim those two subsections alone
establish every required mechanic. A revised-core pilot should select its own
same-edition definitions instead of importing these by familiarity.

Use normal GUR/GUP/Review/Approved/Integration artifacts. Verify genesis and
rollback in fixtures before live integration. Integrator remains the canonical
writer and returns the normal next-packet notification only after successful
completion. Later expand by dependency-ordered topic groups, not by reading all
catalogs in advance.

## 6. Requested Changes to AGY's Proposal

1. Retain core-first sequencing, but describe five topic groups rather than
   five guaranteed packet sizes; correct the Chapter 8/9 loci.
2. Replace the glossary count and add the measured embedded-definition closure.
3. Remove HTML-comment page markers and unconditional exact-page claims.
4. Make the eventual edition storage/isolation decision explicit and separate
   it from the owner's choice of first edition.
5. Add retained evidence, source admission, create-only packet publication,
   snapshot pinning, and independent converter verification.
6. Change permanent folder exclusions into initial-scope deferrals where
   mechanically relevant source material can occur.
7. Treat prefixes as a kind/identity worksheet and separate skills,
   proficiencies, features, and resources.
8. Replace '100% unchanged' and 'complete extraction' claims with bounded
   tested statements. Include Shadowdark's relevant implementation precedent.
9. Assign converter implementation to Builder, governance to Architect,
   source selection/materialization responsibility to the steward, independent
   verification to Reviewer, and canonical transactions to Integrator.
10. Deliver the small core profile first; defer Codex's broader entity adapter
    capabilities until a selected source requires them.

These are requests for a revised proposal, not permission to begin live
extraction. The owner can compare this report with both original proposals;
neither original document was modified during this review.

## 7. Evidence and Validation Limits

The targeted checks read original JSON with a structured parser, measured file
sizes, located source pointers, counted AST shapes, resolved the 155 explicitly
source-qualified glossary references, and inspected the renderer and repository
CLI declarations. No upstream code, production import, source transformation,
or graph suite was executed. No pending role queue was scanned or advanced.

Input SHA-256 values at review:

```text
FIVE_E_GRAPH_INTEGRATION_PROPOSAL_AGY.md
f45d03fc5355c883df1561fb7db3c9a01fd25fe5e510581fef6af5809797ce61
FIVE_E_GRAPH_INTEGRATION_PROPOSAL_CODEX.md
66c8942c27f75710caebe6c4b4f1a0fda38859727b8e6b0a8a584a11d6944a30
5etools/data/book/book-phb.json
b1d28c6f7e24644bac97155ef27bd7a2f4c99f52f1ad6aa0bc9c6911b50a0b25
5etools/data/book/book-xphb.json
92aa9216f130eaf25804a453d57f0c5207d0531df6648e88021bf5432bb8ebd6
```

The source paths describe the temporary snapshot. Retain the small evidence
manifest and permitted source archive before removing it if these measurements
must be reproduced on another machine. The review does not assume continued
access to that directory or authorize committing it.
