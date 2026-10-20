"""Pandoc-backed page-marker resolution for packet source Markdown.

Implements `contracts/SOURCE_MARKDOWN.md` v1.5. Pandoc itself parses the
document, via its JSON AST, so Pandoc tables, subscript/superscript and
attributes survive; no regex or line splitting is used as the primary parser.

Marker recognition runs over the AST after Pandoc has preserved block,
list-item, table-row and table-cell boundaries and inline ordering. Pandoc
renders a trailing heading marker as the heading identifier and every other
marker as literal inline text; the contract states both spellings carry the
same meaning, and both are handled here.

Placement rules, applied in the contract's stated precedence:

1. table cell (last column)  -> the whole row starts on page N
2. end of a non-table line   -> the whole structural unit starts on page N
3. between words in a para   -> the boundary falls at the marker

Contract 1.5 adds two pieces of intake metadata, neither of which is graph
content. A leading YAML block is steward intake metadata: Pandoc consumes it as
document metadata before the block stream, so it never reaches `spans` and must
never be reported as unattributed leading content. And a page marker may carry
a class from the closed vocabulary in `PAGE_CLASSES`, which the contract admits
only on an attribute-bearing block -- a heading or a fenced Div. A bare
paragraph spelling of the same token is not an attribute: Pandoc reads it as
ordinary text, which is why it is recognised here from the AST as literal text
rather than by matching the raw file.

DEC-2026-0084 extends that vocabulary from one class to three, adding
`page-intentionally-ignored` and `blank-page`. The three are handled uniformly:
recognition, placement and page-state behaviour are the class's, not the
vocabulary's, so nothing below branches on which class was read. What differs
between them is only what the steward is declaring, which `PAGE_CLASS_MEANINGS`
records. The set is authorized here for implementation and Review; new-class
production intake waits on the Architect's activation of SOURCE_MARKDOWN 1.8.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

MARKER_TEXT = re.compile(r"^\{#p(\d+)\}$")
MARKER_IDENTIFIER = re.compile(r"^p(\d+)$")

# Anything marker-shaped that survived into *extracted text*. Reaching the text
# is itself the defect: a well-formed plain marker is consumed as a marker and a
# well-formed class-bearing marker is a Pandoc attribute, so neither is ever
# here. Scanning the AST-derived text rather than the raw file is what keeps a
# valid `{#p23 .full-page-artwork}` on a heading or Div from being reported as
# malformed -- contract 1.5, "raw-text matching must not reject a valid
# attributed marker as malformed".
MARKER_SHAPED = re.compile(r"\{#\s*[pP][^}\n]*\}")

#: The closed page-class vocabulary and what each class actually declares.
#:
#: A class is intake metadata about one printed page inside the claimed span.
#: It is never a node, edge, domain, general rule or citation, and it creates no
#: coverage obligation. Only the steward declares a class; no pipeline role may
#: invent one to avoid reading source that is missing, uncertain or mechanically
#: difficult.
#:
#: The three classes do not mean the same thing, which is why the meaning is
#: carried here rather than left to a single generic sentence at the reporting
#: site. `blank-page` asserts that the printed page has no content;
#: `page-intentionally-ignored` asserts only that the steward excluded it, and
#: says nothing about whether printed matter is there. Collapsing the exclusion
#: into artwork or emptiness would relabel the page and lose the steward's
#: actual declaration (DEC-2026-0084).
PAGE_CLASS_MEANINGS: dict[str, str] = {
    "full-page-artwork": (
        "the steward declares this printed page contains full-page artwork and "
        "no graph-constitutable content"
    ),
    "page-intentionally-ignored": (
        "the steward deliberately excludes this printed page from graph "
        "extraction, for example a character sheet or a reader's write-in list; "
        "this records an exclusion, not that the page is blank or artwork"
    ),
    "blank-page": (
        "the steward declares this printed page is blank and supplies no source "
        "content for graph extraction"
    ),
    "front-cover": (
        "the steward declares this printed page is the front cover of the "
        "publication; where no game mechanics are present, it supplies no "
        "source content for graph extraction"
    ),
    "back-cover": (
        "the steward declares this printed page is the back cover of the "
        "publication; where printed game content or tables appear on the back "
        "cover, that content remains eligible for graph extraction"
    ),
}

#: Closed page-class vocabulary (contract 1.5 "Page classes", extended by the
#: prospective amendment in DEC-2026-0084). Derived from the meanings above so
#: the set and its documentation cannot drift apart, and closed: membership is
#: the only test anywhere, so there is no wildcard or permissive fallback for a
#: fourth class to pass through.
PAGE_CLASSES: frozenset[str] = frozenset(PAGE_CLASS_MEANINGS)

# Inline node types whose payload `c` is a plain list of child inlines.
_INLINE_CONTAINERS = {"Emph", "Strong", "Strikeout", "Superscript", "Subscript", "SmallCaps", "Underline"}


class PandocUnavailable(RuntimeError):
    """Raised when the Pandoc executable cannot be found."""


@dataclass(frozen=True)
class PageSpan:
    """A run of source content resolved to one printed page."""

    page: int | None
    kind: str
    text: str


@dataclass(frozen=True)
class PageClassMarker:
    """A class-bearing page marker resolved from a Pandoc attribute."""

    page: int
    classes: tuple[str, ...]
    #: The attribute-bearing block the class was read from: `heading` or `div`.
    block: str
    #: Classes outside `PAGE_CLASSES`. The vocabulary is closed, so an unknown
    #: class is reported rather than carried: admitting one would let intake
    #: metadata grow a meaning no contract has given it.
    unknown: tuple[str, ...] = ()


@dataclass(frozen=True)
class MalformedMarker:
    """Marker-shaped text the parser refused to read as a marker."""

    text: str
    reason: str


@dataclass
class SourcePages:
    path: Path
    spans: list[PageSpan] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: Pandoc YAML metadata, as informational steward intake metadata only.
    #: `packet.yaml` governs identity and page metadata when the two conflict
    #: (contract 1.5, "Steward frontmatter"); this is carried so that a
    #: discrepancy can be recorded, never so that it can decide anything.
    frontmatter: dict = field(default_factory=dict)
    page_classes: list[PageClassMarker] = field(default_factory=list)
    malformed_markers: list[MalformedMarker] = field(default_factory=list)

    @property
    def pages(self) -> tuple[int, ...]:
        return tuple(sorted({s.page for s in self.spans if s.page is not None}))

    def pages_with_class(self, name: str) -> tuple[int, ...]:
        """Every page the steward marked with `name`, in printed order."""
        return tuple(
            sorted({m.page for m in self.page_classes if name in m.classes})
        )

    @property
    def unattributed_text(self) -> str:
        """Content preceding the first marker, which has no resolved page."""
        return " ".join(s.text for s in self.spans if s.page is None).strip()

    def text_for_page(self, page: int) -> str:
        return " ".join(s.text for s in self.spans if s.page == page).strip()


def _pandoc_ast(path: Path) -> dict:
    exe = shutil.which("pandoc")
    if exe is None:
        raise PandocUnavailable(
            "pandoc not found on PATH; contracts/SOURCE_MARKDOWN.md requires a "
            "Pandoc-compatible parser for packet source"
        )
    result = subprocess.run(
        [exe, "-f", "markdown", "-t", "json", str(path)],
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout.decode("utf-8"))


def _marker_from_inline(node: dict) -> int | None:
    if node.get("t") == "Str":
        match = MARKER_TEXT.match(node.get("c") or "")
        if match:
            return int(match.group(1))
    elif node.get("t") == "Span":
        payload = node.get("c") or [["", [], []], []]
        attr = payload[0] if payload else ["", [], []]
        return _marker_from_attr(attr)
    return None


def _marker_from_attr(attr: list) -> int | None:
    """A heading identifier of the form `pN` is a page marker, per the contract."""
    if not attr:
        return None
    match = MARKER_IDENTIFIER.match(attr[0] or "")
    return int(match.group(1)) if match else None


def _classes_from_attr(attr: list) -> tuple[str, ...]:
    """The class list of a Pandoc Attr, in source order."""
    if not attr or len(attr) < 2:
        return ()
    return tuple(str(c) for c in (attr[1] or []))


def _record_page_class(
    attr: list, page: int | None, block: str, state: dict
) -> None:
    """Record a class-bearing marker, or say why the classes resolve nowhere.

    A class without a `pN` identifier is not a page class. The contract binds
    the class to the reserved identifier, so classes on an unidentified block
    are someone's ordinary Pandoc markup and must not be guessed onto whichever
    page happens to be in effect.
    """
    classes = tuple(c for c in _classes_from_attr(attr) if c)
    if not classes:
        return
    if page is None:
        if any(c in PAGE_CLASSES for c in classes):
            state["malformed"].append(
                MalformedMarker(
                    text=" ".join(f".{c}" for c in classes),
                    reason=(
                        f"page class {classes!r} on a {block} with no reserved "
                        f"pN identifier; SOURCE_MARKDOWN binds a page class to "
                        f"a page marker, so this class resolves to no page"
                    ),
                )
            )
        return
    state["page_classes"].append(
        PageClassMarker(
            page=page,
            classes=classes,
            block=block,
            unknown=tuple(c for c in classes if c not in PAGE_CLASSES),
        )
    )


def _scrub_marker_shaped(text: str, state: dict) -> str:
    """Strip marker-shaped tokens out of extracted text and record each one.

    Anything matched here reached the prose, which means Pandoc did not read it
    as a marker or an attribute. The exact `{#pN}` form is left alone: it is a
    well-formed marker that happened to abut other text, and it was already
    treated as content before contract 1.5 rather than being reported.
    """
    if "{" not in text:
        return text

    def replace(match: re.Match) -> str:
        token = match.group(0)
        if MARKER_TEXT.match(token):
            return token
        state["malformed"].append(
            MalformedMarker(
                text=token,
                reason=(
                    "Pandoc read this as ordinary text, not a marker or an "
                    "attribute. A plain marker is exactly {#pN}; a class-bearing "
                    "marker must sit on a heading or an empty fenced Div"
                    if re.match(r"\{#p\d+\s", token)
                    else "malformed marker; the plain form is exactly {#pN}"
                ),
            )
        )
        return ""

    return re.sub(MARKER_SHAPED, replace, text).strip()


def _inline_text(node: dict) -> str:
    kind = node.get("t")
    if kind == "Str":
        return node.get("c") or ""
    if kind in {"Space", "SoftBreak", "LineBreak"}:
        return " "
    if kind in _INLINE_CONTAINERS:
        return "".join(_inline_text(child) for child in node.get("c") or [])
    if kind == "Quoted":
        return "".join(_inline_text(child) for child in (node.get("c") or [None, []])[1])
    if kind in {"Cite"}:
        return "".join(_inline_text(child) for child in (node.get("c") or [None, []])[1])
    if kind in {"Link", "Image"}:
        payload = node.get("c") or [None, [], None]
        return "".join(_inline_text(child) for child in payload[1])
    if kind == "Span":
        payload = node.get("c") or [None, []]
        return "".join(_inline_text(child) for child in payload[1])
    if kind == "Code":
        payload = node.get("c") or [None, ""]
        return payload[1]
    if kind == "Math":
        payload = node.get("c") or [None, ""]
        return payload[1]
    if kind in {"RawInline"}:
        return ""
    if kind == "Note":
        return ""
    return ""


def _split_inlines_on_markers(
    inlines: list[dict], state: dict | None = None
) -> list[tuple[int | None, str]]:
    """Split one inline sequence at its markers.

    Returns ``(marker_or_None, text)`` chunks in document order. ``marker`` is
    the page that begins at that chunk; ``None`` means the chunk continues the
    page already in effect. Marker text is dropped from every chunk.
    """
    chunks: list[tuple[int | None, str]] = []
    buffer: list[str] = []
    pending: int | None = None

    for node in inlines:
        page = _marker_from_inline(node)
        if page is None:
            buffer.append(_inline_text(node))
            continue
        if node.get("t") == "Span" and state is not None:
            payload = node.get("c") or [["", [], []], []]
            attr = payload[0] if payload else ["", [], []]
            _record_page_class(attr, page, "span", state)
        chunks.append((pending, "".join(buffer).strip()))
        buffer = []
        pending = page

    chunks.append((pending, "".join(buffer).strip()))
    return chunks


def _emit_block(inlines: list[dict], kind: str, state: dict, out: list[PageSpan]) -> None:
    """Resolve one non-table block and append its spans."""
    chunks = [
        (page, _scrub_marker_shaped(text, state))
        for page, text in _split_inlines_on_markers(inlines, state)
    ]
    markers = [page for page, _ in chunks if page is not None]

    # Rule 1: the marker is the final non-whitespace token, so no content
    # follows it. The whole structural unit starts on that page.
    trailing_only = len(markers) == 1 and chunks[-1][0] is not None and not chunks[-1][1]
    if trailing_only:
        state["page"] = markers[0]
        text = " ".join(t for _, t in chunks if t).strip()
        out.append(PageSpan(state["page"], kind, text))
        return

    # Rule 3: content follows the marker, so the boundary falls at the marker.
    for page, text in chunks:
        if page is not None:
            state["page"] = page
        if text:
            out.append(PageSpan(state["page"], kind, text))


def _row_inlines(row: list) -> list[list[dict]]:
    """Inline sequences per cell for one Pandoc Row, in column order."""
    cells = row[1] if len(row) > 1 else []
    per_cell: list[list[dict]] = []
    for cell in cells:
        blocks = cell[4] if len(cell) > 4 else []
        inlines: list[dict] = []
        for block in blocks:
            if block.get("t") in {"Plain", "Para"}:
                inlines.extend(block.get("c") or [])
        per_cell.append(inlines)
    return per_cell


def _emit_table(table: list, state: dict, out: list[PageSpan], warnings: list[str]) -> None:
    """Rule 2: a marker in a row's last cell puts the entire row on that page."""
    rows: list[list] = []
    head = table[3] if len(table) > 3 else None
    if head:
        rows.extend(head[1] or [])
    for body in table[4] if len(table) > 4 else []:
        rows.extend(body[2] or [])
        rows.extend(body[3] or [])
    foot = table[5] if len(table) > 5 else None
    if foot:
        rows.extend(foot[1] or [])

    for row in rows:
        per_cell = _row_inlines(row)
        row_marker: int | None = None
        texts: list[str] = []
        for index, inlines in enumerate(per_cell):
            chunks = [
                (page, _scrub_marker_shaped(text, state))
                for page, text in _split_inlines_on_markers(inlines, state)
            ]
            markers = [page for page, _ in chunks if page is not None]
            if markers:
                if index != len(per_cell) - 1:
                    warnings.append(
                        f"page marker in column {index + 1} of {len(per_cell)}; the contract "
                        f"states a table marker occurs in the last column"
                    )
                row_marker = markers[-1]
            texts.extend(t for _, t in chunks if t)

        if row_marker is not None:
            state["page"] = row_marker
        out.append(PageSpan(state["page"], "table_row", " | ".join(texts).strip()))


def _walk(blocks: list[dict], state: dict, out: list[PageSpan], warnings: list[str]) -> None:
    for block in blocks:
        kind = block.get("t")
        if kind == "Header":
            payload = block.get("c") or [1, ["", [], []], []]
            attr_page = _marker_from_attr(payload[1])
            _record_page_class(payload[1], attr_page, "heading", state)
            if attr_page is not None:
                state["page"] = attr_page
                text = _scrub_marker_shaped(
                    "".join(_inline_text(n) for n in payload[2]).strip(), state
                )
                out.append(PageSpan(state["page"], "heading", text))
            else:
                _emit_block(payload[2], "heading", state, out)
        elif kind in {"Para", "Plain"}:
            _emit_block(block.get("c") or [], "paragraph", state, out)
        elif kind == "LineBlock":
            for line in block.get("c") or []:
                _emit_block(line, "line", state, out)
        elif kind == "Div":
            # A fenced Div is the contract's home for artwork that has no
            # heading, so its attribute carries the page the same way a heading
            # identifier does. The span is emitted with empty text even when the
            # Div is empty: the page is marked, and a marked page that produced
            # no span would read downstream as an unmarked gap.
            payload = block.get("c") or [["", [], []], []]
            attr = payload[0] if payload else ["", [], []]
            attr_page = _marker_from_attr(attr)
            _record_page_class(attr, attr_page, "div", state)
            if attr_page is not None:
                state["page"] = attr_page
                out.append(PageSpan(state["page"], "page_marker", ""))
            _walk(payload[1] or [], state, out, warnings)
        elif kind == "BlockQuote":
            _walk(block.get("c") or [], state, out, warnings)
        elif kind in {"BulletList", "OrderedList"}:
            items = block.get("c") if kind == "BulletList" else (block.get("c") or [None, []])[1]
            for item in items or []:
                _walk(item, state, out, warnings)
        elif kind == "DefinitionList":
            for term, definitions in block.get("c") or []:
                _emit_block(term, "definition_term", state, out)
                for definition in definitions:
                    _walk(definition, state, out, warnings)
        elif kind == "Table":
            _emit_table(block.get("c") or [], state, out, warnings)
        elif kind == "Figure":
            payload = block.get("c") or [None, None, []]
            _walk(payload[2] or [], state, out, warnings)
        elif kind in {"CodeBlock", "RawBlock", "HorizontalRule", "Null"}:
            continue


def _plain_meta(node):
    """Flatten one Pandoc metadata value to plain Python.

    Frontmatter is informational, so this only has to be faithful enough to
    report and compare. Nothing downstream may decide anything from it.
    """
    if not isinstance(node, dict):
        return node
    kind = node.get("t")
    payload = node.get("c")
    if kind == "MetaMap":
        return {k: _plain_meta(v) for k, v in (payload or {}).items()}
    if kind == "MetaList":
        return [_plain_meta(v) for v in payload or []]
    if kind == "MetaBool":
        return bool(payload)
    if kind == "MetaString":
        return payload or ""
    if kind in {"MetaInlines", "MetaBlocks"}:
        inlines = payload or []
        if kind == "MetaBlocks":
            inlines = [i for b in inlines for i in (b.get("c") or [])]
        return "".join(_inline_text(n) for n in inlines).strip()
    return payload


def parse_source(path: str | Path) -> SourcePages:
    """Resolve every printed-page attribution in one packet source file."""
    path = Path(path)
    ast = _pandoc_ast(path)
    result = SourcePages(path=path)
    # Pandoc consumes a leading YAML block into `meta`, ahead of the block
    # stream. That is what keeps steward frontmatter out of `spans` -- and so
    # out of the unattributed-content check below -- without this parser having
    # to strip anything by hand.
    result.frontmatter = {
        key: _plain_meta(value) for key, value in (ast.get("meta") or {}).items()
    }
    state: dict = {"page": None, "page_classes": [], "malformed": []}
    _walk(ast.get("blocks") or [], state, result.spans, result.warnings)
    result.page_classes.extend(state["page_classes"])
    result.malformed_markers.extend(state["malformed"])

    if result.unattributed_text:
        result.warnings.append(
            "content appears before the first page marker; it has no resolved page "
            "unless packet metadata supplies an independent locator"
        )
    return result


def strip_markers(text: str) -> str:
    """Remove marker tokens from a string of already-extracted prose."""
    text = re.sub(r"\s*\[\]\{#p\d+\}", "", text)
    return re.sub(r"\s*\{#p\d+\}", "", text)
