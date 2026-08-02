"""Pandoc-backed page-marker resolution for packet source Markdown.

Implements `contracts/SOURCE_MARKDOWN.md` v1.0. Pandoc itself parses the
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


@dataclass
class SourcePages:
    path: Path
    spans: list[PageSpan] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def pages(self) -> tuple[int, ...]:
        return tuple(sorted({s.page for s in self.spans if s.page is not None}))

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
    return None


def _marker_from_attr(attr: list) -> int | None:
    """A heading identifier of the form `pN` is a page marker, per the contract."""
    if not attr:
        return None
    match = MARKER_IDENTIFIER.match(attr[0] or "")
    return int(match.group(1)) if match else None


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


def _split_inlines_on_markers(inlines: list[dict]) -> list[tuple[int | None, str]]:
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
        chunks.append((pending, "".join(buffer).strip()))
        buffer = []
        pending = page

    chunks.append((pending, "".join(buffer).strip()))
    return chunks


def _emit_block(inlines: list[dict], kind: str, state: dict, out: list[PageSpan]) -> None:
    """Resolve one non-table block and append its spans."""
    chunks = _split_inlines_on_markers(inlines)
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
            chunks = _split_inlines_on_markers(inlines)
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
            if attr_page is not None:
                state["page"] = attr_page
                text = "".join(_inline_text(n) for n in payload[2]).strip()
                out.append(PageSpan(state["page"], "heading", text))
            else:
                _emit_block(payload[2], "heading", state, out)
        elif kind in {"Para", "Plain"}:
            _emit_block(block.get("c") or [], "paragraph", state, out)
        elif kind == "LineBlock":
            for line in block.get("c") or []:
                _emit_block(line, "line", state, out)
        elif kind in {"BlockQuote", "Div"}:
            payload = block.get("c")
            inner = payload if kind == "BlockQuote" else (payload or [None, []])[1]
            _walk(inner or [], state, out, warnings)
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


def parse_source(path: str | Path) -> SourcePages:
    """Resolve every printed-page attribution in one packet source file."""
    path = Path(path)
    ast = _pandoc_ast(path)
    result = SourcePages(path=path)
    state: dict = {"page": None}
    _walk(ast.get("blocks") or [], state, result.spans, result.warnings)

    if result.unattributed_text:
        result.warnings.append(
            "content appears before the first page marker; it has no resolved page "
            "unless packet metadata supplies an independent locator"
        )
    return result


def strip_markers(text: str) -> str:
    """Remove marker tokens from a string of already-extracted prose."""
    return re.sub(r"\s*\{#p\d+\}", "", text)
