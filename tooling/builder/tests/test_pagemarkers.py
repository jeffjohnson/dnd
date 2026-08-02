"""Acceptance tests for the Pandoc page-marker parser.

Items 1-6 are the acceptance tests stated in `contracts/SOURCE_MARKDOWN.md`,
which any programmatic packet parser must demonstrate.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401

from adnd1e_builder import pagemarkers


def parse(markdown: str) -> pagemarkers.SourcePages:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "packet.md"
        path.write_text(markdown, encoding="utf-8", newline="\n")
        return pagemarkers.parse_source(path)


class TestAcceptance(unittest.TestCase):
    def test_1_trailing_heading_marker_covers_whole_heading(self):
        result = parse("# ADVANCED DUNGEONS AND DRAGONS PLAYER'S HANDBOOK {#p1}\n")
        headings = [s for s in result.spans if s.kind == "heading"]
        self.assertEqual(len(headings), 1)
        self.assertEqual(headings[0].page, 1)
        self.assertIn("ADVANCED", headings[0].text)
        self.assertIn("HANDBOOK", headings[0].text)

    def test_2_trailing_paragraph_marker_covers_whole_paragraph(self):
        result = parse("This entire paragraph begins and lives on page 6. {#p6}\n")
        paragraphs = [s for s in result.spans if s.kind == "paragraph"]
        self.assertEqual(len(paragraphs), 1)
        self.assertEqual(paragraphs[0].page, 6)
        self.assertTrue(paragraphs[0].text.startswith("This entire paragraph"))

    def test_3_last_column_table_marker_covers_whole_row(self):
        markdown = (
            "| Section | Page |\n"
            "|---------|------|\n"
            "| Encumbrance | 101 {#p4} |\n"
            "| Ethereal Travel | 105 |\n"
        )
        result = parse(markdown)
        rows = [s for s in result.spans if s.kind == "table_row"]
        encumbrance = [r for r in rows if "Encumbrance" in r.text]
        self.assertEqual(len(encumbrance), 1)
        # Every cell in the marked row is on page 4, including cells before the marker.
        self.assertEqual(encumbrance[0].page, 4)
        # Later rows inherit page 4 until another marker changes the assignment.
        ethereal = [r for r in rows if "Ethereal" in r.text]
        self.assertEqual(ethereal[0].page, 4)

    def test_4_inline_marker_splits_attribution_at_the_marker(self):
        result = parse(
            "# Start {#p7}\n\n"
            "A good Dungeon Master will make each game a surpassing {#p8} challenge.\n"
        )
        paragraphs = [s for s in result.spans if s.kind == "paragraph"]
        before = [p for p in paragraphs if "surpassing" in p.text]
        after = [p for p in paragraphs if "challenge" in p.text]
        self.assertEqual(before[0].page, 7, "text through 'surpassing' stays on the prior page")
        self.assertEqual(after[0].page, 8, "'challenge' onward begins page 8")
        self.assertNotIn("challenge", before[0].text)
        self.assertNotIn("surpassing", after[0].text)

    def test_5_preserves_pandoc_table_and_sub_superscript(self):
        markdown = (
            "| Formula | Page |\n"
            "|---------|------|\n"
            "| H~2~O and E^2^ | 12 {#p3} |\n"
        )
        result = parse(markdown)
        rows = [s for s in result.spans if s.kind == "table_row"]
        self.assertEqual(len(rows), 2, "header row and body row both survive as rows")
        body = [r for r in rows if "H" in r.text and "O" in r.text]
        # Subscript/superscript content is preserved, not dropped with the markup.
        self.assertIn("H2O", body[0].text.replace(" ", ""))
        self.assertIn("E2", body[0].text.replace(" ", ""))

    def test_6_marker_text_excluded_from_content_but_page_retained(self):
        result = parse("Ability scores are generated first. {#p9}\n")
        span = [s for s in result.spans if s.kind == "paragraph"][0]
        self.assertNotIn("{#p9}", span.text)
        self.assertNotIn("p9", span.text)
        self.assertEqual(span.page, 9)


class TestPlacementSemantics(unittest.TestCase):
    def test_assignment_persists_until_next_marker(self):
        result = parse("# A {#p2}\n\nfirst para\n\nsecond para\n\n# B {#p5}\n\nthird para\n")
        pages = {s.text: s.page for s in result.spans}
        self.assertEqual(pages["first para"], 2)
        self.assertEqual(pages["second para"], 2)
        self.assertEqual(pages["third para"], 5)

    def test_content_before_first_marker_has_no_page(self):
        result = parse("orphan paragraph\n\n# Title {#p1}\n")
        self.assertIsNone(result.spans[0].page)
        self.assertTrue(any("before the first page marker" in w for w in result.warnings))

    def test_table_precedence_over_end_of_line_rule(self):
        # The marker is both the last token of the line and inside a table cell.
        # The table-cell rule wins, so the whole row is attributed, not just a block.
        markdown = "| A | B |\n|---|---|\n| left | right {#p11} |\n"
        result = parse(markdown)
        body = [s for s in result.spans if s.kind == "table_row" and "left" in s.text]
        self.assertEqual(body[0].page, 11)
        self.assertIn("left", body[0].text)

    def test_pages_property_collects_every_marked_page(self):
        result = parse("# T {#p1}\n\nx\n\nmore {#p2}\n\n| a | b |\n|---|---|\n| c | d {#p4} |\n")
        self.assertEqual(result.pages, (1, 2, 4))

    def test_strip_markers_helper(self):
        self.assertEqual(pagemarkers.strip_markers("some prose {#p12}"), "some prose")


class TestListsAndQuotes(unittest.TestCase):
    def test_list_item_marker_covers_the_item(self):
        result = parse("# H {#p1}\n\n- first item {#p3}\n- second item\n")
        items = [s for s in result.spans if s.text.startswith(("first", "second"))]
        self.assertEqual(items[0].page, 3)
        self.assertEqual(items[1].page, 3)

    def test_block_quote_marker(self):
        result = parse("# H {#p1}\n\n> quoted line {#p4}\n")
        quoted = [s for s in result.spans if "quoted" in s.text]
        self.assertEqual(quoted[0].page, 4)


class TestSourceLint(unittest.TestCase):
    """Backing checks for the `lint-source` command."""

    def test_source_with_no_markers_resolves_no_pages(self):
        result = parse("### CHARACTER SPELLS\n\nProse with no marker anywhere.\n")
        self.assertEqual(result.pages, ())
        self.assertTrue(result.unattributed_text)

    def test_malformed_marker_is_not_recognised_as_a_marker(self):
        # These are marker-shaped but not the exact {#pN} form.
        for bad in ("{#p}", "{# p4}", "{#page4}", "{#P4}"):
            with self.subTest(bad=bad):
                result = parse(f"Some prose {bad}\n")
                self.assertEqual(
                    result.pages, (), f"{bad} must not be accepted as a page marker"
                )

    def test_lint_flags_the_unmarked_packet_and_passes_the_others(self):
        import io
        from contextlib import redirect_stdout

        from adnd1e_builder.cli import lint_source

        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.md"
            good.write_text("### A {#p12}\n\nbody\n", encoding="utf-8", newline="\n")
            bad = Path(tmp) / "bad.md"
            bad.write_text("### A\n\nbody with no marker\n", encoding="utf-8", newline="\n")

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = lint_source([good, bad])

        output = buffer.getvalue()
        self.assertEqual(code, 1, "a packet with no markers must fail the lint")
        self.assertIn("ok   good.md", output)
        self.assertIn("FAIL bad.md", output)
        self.assertIn("no page markers at all", output)


if __name__ == "__main__":
    unittest.main()
