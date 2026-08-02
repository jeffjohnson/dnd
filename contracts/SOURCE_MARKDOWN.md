# Pandoc Source Markdown Contract

**Version 1.1.**

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
- Pandoc attributes, including a heading identifier such as `p1`.

Do not flatten tables or normalize whitespace before resolving page markers.
Pandoc may represent a marker at the end of a heading as the heading identifier
rather than literal text. Both representations have the same page-marker meaning
in packet source.

## Page Marker

A page marker has the exact form `{#pN}`, where `N` is one or more decimal digits:

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

## Role Obligations

- Analyst derives every candidate citation page using this contract.
- Builder preserves page attribution and makes any source-inspection tooling
  Pandoc-compatible.
- Reviewer independently verifies citation pages against the original Markdown
  and these placement rules.
- Integrator carries approved page provenance without reinterpretation.
- Architect applies these rules to source excerpts used in governance decisions.

## Acceptance Tests for Parsers

Any programmatic packet parser must demonstrate that it:

1. assigns a trailing heading marker to the whole heading;
2. assigns a trailing paragraph marker to the whole paragraph;
3. assigns a last-column table marker to the whole row;
4. splits inline paragraph attribution immediately after the marker;
5. preserves Pandoc table and subscript/superscript structure;
6. excludes marker text from semantic content while retaining page provenance.

## Version History

- **1.1 - 2026-07-31:** Made the current input packet authoritative for printed
  page attribution and defined conflicting legacy or canonical pages as reviewed
  Integrator citation corrections.
