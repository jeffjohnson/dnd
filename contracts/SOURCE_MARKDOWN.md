# Pandoc Source Markdown Contract

**Version 1.8.**

## Scope

Every source-text file in a source packet must:

- use the `.md` extension;
- contain Pandoc Markdown, not merely CommonMark or GitHub-Flavored Markdown;
- preserve the source's semantic structure, including Pandoc tables,
  subscript/superscript, attributes, and any other Pandoc syntax present;
- encode printed-page boundaries with the page markers defined below.

Packet manifests and workflow artifacts retain their formats defined elsewhere.
Only packet source text is required to be Markdown.

Printed-page attribution is the only physical page-layout information workers must
derive from these files. Do not infer columns, coordinates, lineation, or other
visual layout unless a separate packet artifact explicitly requires it.

## External Source Intake

The five graph-processing roles consume source packets; none acquires a book, recreates
missing rulebook text, or authors a packet's source prose from recollection. The
**repository source steward** is the repository owner, or an explicitly delegated
external operator, responsible for lawful source acquisition and intake. This is
an external repository responsibility, not a pipeline role or a scanner queue.
Each role routes missing-source requests directly to the steward/user under
`contracts/HERDR_HANDOFFS.md`; no pipeline role acquires or reconstructs source.

The source steward supplies a bounded incoming packet with its source text and
required packet metadata. A claimed packet remains immutable after an Analyst
uses it. The steward may transcribe or package supplied source material, but may
not reconstruct unavailable text from memory or inference and present it as
source-read evidence.

### Steward frontmatter

An incoming Markdown file may begin with a Pandoc YAML metadata block. It is
informational steward intake metadata only: it is not rulebook prose,
source-read evidence, graph content, a packet identity, or authority over
ruleset, book, source, packet, page, or citation fields. Pandoc consumes the
block as document metadata before its block stream; parsers must not report it
as unattributed leading content.

The metadata may describe the supplied source, series, product line, chapter,
chapter title, or printed-page range. `packet.yaml` remains the authoritative
claimed-packet record. If frontmatter conflicts with that manifest, use the
manifest and record the intake discrepancy; do not resolve it by changing graph
data or by treating the frontmatter as a source-reading claim.

When a required source locus is absent, every downstream task that needs its
reading remains blocked. An Analyst may resume only after the source steward has
provided the conforming incoming packet; Builder, Reviewer, and Integrator may
not assign source acquisition or source authoring to Analyst by elimination.

## Parser Requirements

Any software that parses packet source text must use Pandoc itself, preferably
through its JSON AST, or a library that explicitly supports the Pandoc Markdown
extensions used by the source. A CommonMark-only or GFM-only parser is
nonconforming.

Do not use regular expressions or line splitting as the primary Markdown parser.
Exact page-marker recognition may be implemented after the parser has preserved:

- original source-line position;
- block, list-item, table-row, and table-cell boundaries;
- inline ordering and soft breaks;
- Pandoc attributes, including a heading or fenced-Div identifier such as `p1`.

Do not flatten tables or normalize whitespace before resolving page markers.
Pandoc may represent a marker at the end of a heading as the heading identifier
rather than literal text. Both representations have the same page-marker meaning
in packet source.

## Page Marker

A plain page marker has the exact form `{#pN}`, where `N` is one or more decimal digits:

```text
{#p1}
{#p23}
{#p104}
```

The marker identifies the printed source page. It is metadata, not rulebook
content. Remove it from extracted prose, labels, aspects, conditions, and quoted
evidence while retaining its page attribution in provenance and citations.

Identifiers matching `pN` are reserved for page markers in packet source. They
must not be treated as ordinary document anchors.

The most recent page assignment remains in effect until the next marker. The
marker placement determines where that assignment begins.

### Page classes

A class-bearing page marker uses the same reserved `pN` identifier on a Pandoc
attribute-bearing block. The closed vocabulary contains exactly:

- `.full-page-artwork`: the source steward declares that the identified printed
  page contains full-page artwork and no graph-constitutable content.
- `.page-intentionally-ignored`: the source steward deliberately excludes the
  identified printed page from graph extraction, for example a character sheet
  or a reader's write-in list. This records exclusion, not emptiness or artwork.
- `.blank-page`: the source steward declares that the identified printed page
  is blank and supplies no source content for graph extraction.

These classes are page-local intake metadata, never graph nodes, edges, domains,
general rules, source citations, or evidence of mechanics. Only the source
steward declares them; pipeline roles must not invent classifications to avoid
reading missing, uncertain, or mechanically difficult source material.

Use an existing source heading when it genuinely carries the marker:

```markdown
# CHAPTER TITLE {#p23 .full-page-artwork}
# CHARACTER SHEET {#p24 .page-intentionally-ignored}
# BACK MATTER {#p25 .blank-page}
```

For a classified page without a source heading, use an empty fenced Div. Do not
invent a heading merely to carry metadata:

```markdown
::: {#p23 .full-page-artwork}
:::

::: {#p24 .page-intentionally-ignored}
:::

::: {#p25 .blank-page}
:::
```

A bare paragraph such as `{#p23 .page-intentionally-ignored}` is invalid.
Pandoc treats it as ordinary text and does not preserve an attribute. Parsers
and linters must inspect the Pandoc AST for a heading or Div attribute;
raw-text matching must not reject a valid attributed marker as malformed.
Unknown classes and recognized classes without a reserved `pN` identifier remain
errors.

At claim, retain the exact classified page and class in `packet.yaml`
composition metadata. Keep the page in the packet's actual declared span and
completeness accounting; do not renumber or delete it. The manifest remains
authoritative if the source class and intake description conflict; record the
discrepancy rather than silently overwriting the manifest. Each class applies
only to its identified page, never to later pages. A classified page inside a
packet's declared span is not an uncovered-page or graph-content obligation.
Classification does not waive out-of-span, malformed-marker, or unrelated
source defects.

## Placement Semantics

The following rules are exhaustive. Apply the table-cell rule before the
end-of-line rule.

### 1. End of a non-table source line

When a marker is the final non-whitespace token on a source line outside a table
cell, the entire containing structural unit starts on that page. This includes a
heading, paragraph, list item, block quote, or comparable block.

The marker appears after the text but applies from the start of the structural
unit:

```markdown
# ADVANCED DUNGEONS & DRAGONS PLAYER'S HANDBOOK {#p1}
```

The complete heading is on page 1.

```markdown
This entire paragraph begins and lives on page 6. {#p6}
```

The complete paragraph starts on page 6. Do not assign only content following the
marker, because there is no following content on that source line.

### 2. Last cell of a table row

When a marker occurs in a table cell, it will occur in the last column. The entire
row starts on that page, including every cell before the marker:

```markdown
| Encumbrance | 101 {#p4} |
```

Every cell in that row is on page 4. Later rows inherit page 4 until another page
marker changes the assignment.

### 3. Between words in a paragraph

When text follows a marker on the same source line within a paragraph, the page
boundary occurs at the marker:

```markdown
A good Dungeon Master will make each game a surpassing {#p8} challenge.
```

Text through `surpassing` remains on the previously active page. `challenge` and
all following content begin on page 8, until another marker changes the
assignment.

## Attribution Rules

- Derive citations from marker semantics, not Markdown line numbers, file names,
  packet names, or estimated page length.
- Content before the first applicable marker has no resolved page unless packet
  metadata supplies an independent authoritative page locator.
- If a marker is malformed, appears in an unsupported location, or creates
  ambiguous attribution, flag the packet for correction. Do not guess.
- Preserve section headings independently of page attribution.
- A table-row marker applies to the row as a unit even when the cited evidence is
  in a cell before the marker.
- An inline marker divides a paragraph. Verify which side contains the cited
  evidence before assigning its page.

## Page Authority and Conflicts

For packet-backed work, the current input packet identified by the artifact's
`ruleset_id`, `book_id`, `source_id`, and `packet_id` is authoritative for printed
page attribution. Page markers in that packet, interpreted under this contract,
take precedence over legacy extraction files, pre-packet citations, inferred
offsets, and conflicting page values already present in canonical data.

Workers must use the packet-derived page in new GURs, GUPs, Reviews, and Approved
bundles. Do not alter a correct packet-derived page merely to agree with a legacy
or neighbouring canonical citation.

A conflict with an existing canonical page is a citation-correction issue. It
does not by itself change node identity, assertion identity, edge semantics, or
evidence class. Record the exact conflicting assertion and route a reviewed
correction to the Integrator; only the Integrator may edit canonical data. If the
packet marker is malformed or ambiguous, follow the attribution rules above and
return the packet for correction rather than preferring either value.

## Source Identity Authority and Conflicts

For packet-backed work, the current incoming packet, and then its immutable
claimed copy, is canonical for every source name explicitly present in that
packet. This includes spelling, grammatical number, source label, and the
corresponding canonical ID stem. A direct packet heading or table entry takes
precedence over legacy extraction files, pre-packet GURs/GUPs/Reviews, and a
conflicting canonical label or ID derived from unpacketized legacy text.

For an identity that already exists in canonical data, a packet name may replace
that identity only when it occurs in the concept's defining locus: its heading,
named entry, table row, or other bounded source unit whose subject is the
concept. A secondary listing, permission list, cross-reference, or incidental
mention can support the relationship stated in its own packet, but it does not
rename a concept whose defining mechanics belong to another source. In that
case, reuse the existing canonical identity unless an Architect Decision directs
an identity migration.

When no packet yet contains the defining locus, only an Architect Decision may
adopt a repository-owner-specified canonical identity. The Decision must name
the unavailable defining locus, preserve that the direction is not source-read
evidence, and require a fresh identity comparison when the defining source is
packetized. This does not permit a worker to infer a spelling from unpacketized
legacy text.

Do not normalize a current packet name back to a legacy singular, plural, or
otherwise different spelling merely because that legacy identity is already in
the registry. Treat the legacy identity as drift. Builder and Reviewer must
surface the exact affected registry row and canonical neighborhood; a canonical
ID replacement or other migration proceeds only through an Architect Decision,
reviewed GUP, and Integrator transaction.

This precedence applies only to source material directly present in the current
packet. It does not authorize a worker to infer a renamed concept in another
packet or source. If two current packets give genuinely incompatible direct
names for the same concept, preserve both packet readings and escalate the
cross-packet identity conflict. Do not select a legacy reading as a tie-breaker.

## Role Obligations

- Analyst derives every candidate citation page and direct source identity from
  the current packet under this contract.
- Builder preserves packet-derived identity and page attribution; it never
  silently restores a conflicting legacy ID or label.
- Reviewer independently verifies citation pages and direct source names against
  the original Markdown and these placement rules.
- Integrator carries approved packet-derived identity and page provenance
  without reinterpretation.
- Architect applies these rules to source excerpts and identity migrations used
  in governance decisions.

## Acceptance Tests for Parsers

Any programmatic packet parser must demonstrate that it:

1. assigns a trailing heading marker to the whole heading;
2. assigns a trailing paragraph marker to the whole paragraph;
3. assigns a last-column table marker to the whole row;
4. splits inline paragraph attribution immediately after the marker;
5. preserves Pandoc table and subscript/superscript structure;
6. excludes marker text from semantic content while retaining page provenance.
7. consumes YAML frontmatter without treating it as leading unattributed text;
8. resolves every member of the closed page-class vocabulary from a heading or
   fenced Div attribute, preserves its exact page-local class as intake metadata,
   rejects bare paragraph forms and unknown classes, and does not classify a
   later plain page by inheritance.

## Version History

- **1.8 - 2026-09-21:** DEC-2026-0084 admitted
  `page-intentionally-ignored` and `blank-page` after independent implementation
  approval. The vocabulary remains closed; classifications are steward-authored,
  page-local intake metadata with exact composition retention and no graph or
  inheritance semantics.

- **1.7 - 2026-09-19:** Routed missing-source requests directly to the steward
  after Dispatcher retirement; source and page-marker semantics are unchanged.

- **1.6 - 2026-09-07:** Distinguished Dispatcher coordination from the external
  source steward; source metadata and page-marker semantics are unchanged.

- **1.5 - 2026-09-06:** Admitted informational Pandoc YAML frontmatter with
  claimed-manifest precedence, and defined the closed `full-page-artwork`
  class-bearing page-marker form on headings and fenced Divs.

- **1.4 - 2026-08-15:** Distinguished a defining source locus from a secondary
  mention for existing-identity migrations, and bounded owner-directed naming
  decisions while a defining source packet is unavailable.
- **1.3 - 2026-08-06:** Named the external repository source steward as the
  owner of source acquisition and intake; prohibited pipeline roles from
  fabricating unavailable packet text or routing that work to Analyst.
- **1.2 - 2026-08-04:** Made the current incoming/claimed packet authoritative
  for directly stated source identity, including spelling, grammatical number,
  labels, and ID stems; legacy identity conflicts are governed migrations.
- **1.1 - 2026-07-31:** Made the current input packet authoritative for printed
  page attribution and defined conflicting legacy or canonical pages as reviewed
  Integrator citation corrections.
