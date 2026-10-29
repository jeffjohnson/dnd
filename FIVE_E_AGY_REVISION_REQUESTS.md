# Seven Revision Requests for AGY's 2024 Proposal

Date: 2026-10-26. Author: Codex, Architect review.
Target: `FIVE_E_GRAPH_INTEGRATION_PROPOSAL_AGY.md`, revised 2024-only proposal.
Status: proposal feedback, not implementation authorization or ontology approval.

## Overall Assessment

The revised proposal correctly targets `dnd5e-2024`, with 2014 deferred. Keep
the core-first roadmap, two adapter profiles, and bounded topic groups. The
following seven points remain unresolved. The document should not claim that
all reconciliation requests are complete until these are addressed.

## 1. Retain Source Content, Not Just Hashes

Section 6 lists paths, pointers, record hashes, and transformation metadata,
but does not explicitly retain the original input records. A rendered packet
and a hash-only sidecar cannot reproduce or independently verify its transform
after the upstream directory is removed.

Required revision:

- Retain actual source records and the necessary containing source context and
  embedded-definition dependencies, or pin an accessible authorized archive.
- Specify snapshot identity, source bytes or an explicit canonical record
  serialization, hash algorithm, and transformation version/configuration.
- Distinguish a raw-file hash from a parsed-and-reserialized record hash.
- Demonstrate replay with the original checkout unavailable.
- Use a deterministic evidence manifest; keep variable run timestamps outside
  the reproducible content hash or specify their treatment explicitly.

Hashes detect differences; they do not reconstruct missing evidence.

## 2. Do Not Promise Fragment-Exact Pagination

Sections 3, 6, and 8 promise fragment-accurate or fragment-exact pages. Upstream
page fields generally annotate entries or sections, not every paragraph or
physical page boundary within them.

Required revision:

- Distinguish explicitly declared entry pages, inherited section pages, and
  independently established fragment pages.
- Preserve unknown paragraph boundaries as unknown, with stable source locators.
- Do not automatically emit authoritative `{#pNNN}` boundaries from inherited
  section metadata. Define when available evidence justifies a marker.
- Retain each embedded definition's own citation, rather than assigning its
  container's page to it.
- Define the handling of units that cannot meet current packet page requirements.

Using the correct marker syntax does not establish the accuracy of its placement.

## 3. Keep the Ontology Proposed Until Governed

Section 5 labels its table "Approved Canonical Prefix Table" without an approving
Decision. Section 4 also uses relationship names such as `BREAKS`, `FAIL`, and
`RESOLVED_BY` without specifying a governed edge vocabulary.

Required revision:

- Rename the table "Proposed Prefix and Identity Worksheet".
- Define candidate node kinds and edge meanings, direction, conditions, and
  allowed endpoints before presenting any as executable graph assertions.
- Reconcile `pool_`, which appears in the worksheet but not the prefix table.
- Resolve duplicate-looking identities such as `rule_attack_roll` versus
  `cbt_attack_roll` and `rule_initiative` versus `cbt_initiative`.
- Preserve the distinction between category membership and mechanical gating.
- Keep class feature identity source- and parent-qualified where necessary;
  `name|class|level` alone is not a complete general native identity specification.

Architect approval and schema/tool agreement must precede registration.

## 4. Correct the Mechanical Examples

Targeted checks against the supplied XPHB records found these discrepancies:

| Proposal example | Correction |
|---|---|
| Heroic Inspiration characterized through D20 Tests | Its source permits rerolling any die, not only a D20 Test. |
| Prone grants advantage to nearby melee attackers | The source uses attacker distance, not a melee-only restriction. |
| Reaction summarized as one per turn/round | After taking one, another is unavailable until the start of the creature's next turn. |
| Statuses listed as Bloodied, Concentration, Marked | The embedded glossary statuses are Bloodied, Concentration, Surprised. |
| Advantage/disadvantage called reroll mechanics | These govern rolling/selecting dice and should not be conflated with reroll grants. |

Supporting local records:

- `5etools/data/variantrules.json`: XPHB Heroic Inspiration and Reaction.
- `5etools/data/conditionsdiseases.json`: XPHB Prone.
- `5etools/data/book/book-xphb.json`:
  `/bookData/0/data/10/entries/1/entries`, the glossary embeds.

Required revision: label all example assertions as source-backed candidates,
preserve their conditions, and verify them against the selected 2024 records.
They must not predetermine the Analyst's extraction or imply that all examples
have already received independent mechanical review.

## 5. Correct the Embedded-Reference Specification

The proposal repeatedly says `statblock: true`. Actual embedded records use:

```json
{"type":"statblock","tag":"status","name":"Surprised","source":"XPHB"}
```

The glossary count of 155 definitions is correct. Those records represent six
entity kinds across five files, because conditions and statuses share a file:

| Kind | Count | File |
|---|---:|---|
| variantrule | 115 | variantrules.json |
| action | 13 | actions.json |
| condition | 15 | conditionsdiseases.json |
| status | 3 | conditionsdiseases.json |
| sense | 4 | senses.json |
| hazard | 5 | trapshazards.json |

Required revision: document the real discriminator and typed lookup key. Do not
describe the absence of `_copy` in these direct targets as proof that all their
transitive rendering dependencies are already supported.

## 6. Make Independent Validation Explicit

The revised proposal lacks a concrete acceptance gate sufficient to establish
source fidelity. Parse success and graph schema validation cannot detect an
omitted definition or changed sentence on their own.

Required acceptance checks:

- All 155 direct glossary definitions resolve uniquely under XPHB and preserve
  their source order and attribution; introductory text and images are accounted
  for separately.
- Missing, ambiguous, and unsupported embedded targets fail with source pointers.
- Unsupported AST constructs are reported, never silently dropped.
- An intentionally omitted definition or altered sentence is detected by an
  independent comparison to retained source evidence.
- Explicit and inherited page metadata remain distinguishable.
- Identical inputs reproduce the defined outputs; changed inputs cannot reuse
  stale publication evidence.
- Source replay works after the temporary checkout is unavailable.
- No implicit 2014 fallback is allowed for the 2024-only pilot.

Separate embedded-definition expansion from ordinary inline links. Expanding
every hyperlink recursively would defeat the bounded core profile. Record link
targets as appropriate without assuming every linked definition must be inlined.

Reviewer independently verifies the adapter before live packet release. Builder
implements the adapter; Architect governs the contract; Integrator alone writes
canonical state after verified genesis and rollback support.

## 7. Remove Unsupported Permission Guarantees

Section 7 says private ingestion is permitted "without restriction". That is
not established by the proposal or by the software's license. Its SRD flags and
alternate-name mappings also do not independently establish permission for every
retained source fragment or distributed output.

Required revision:

- Replace categorical permission statements with an explicit source-admission
  and permitted-output gate.
- Separate software licensing, publisher text, retained evidence, graph output,
  and application-visible content.
- Treat upstream SRD flags and aliases as metadata requiring verification against
  the selected authoritative source, not automatic publication authorization.
- Do not imply that retaining both a book name and an SRD alias makes all related
  content distributable.

This review makes no legal determination. Private inspection of supplied data
and authorization to redistribute its contents are separate questions.

## Requested Next Action for AGY

Revise the proposal against these seven points and identify where each was
resolved. Keep the scope 2024-only. Preserve the small core-first pilot rather
than adding broad entity hydration. Do not implement, initialize a graph, or
claim that the ontology is approved based on this review.

The original proposal was not edited by Codex while producing this document.
