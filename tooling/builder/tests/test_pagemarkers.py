"""Acceptance tests for the Pandoc page-marker parser.

Items 1-8 are the acceptance tests stated in `contracts/SOURCE_MARKDOWN.md`,
which any programmatic packet parser must demonstrate. 7 and 8 arrive with
contract 1.5 under DEC-2026-0080: steward frontmatter, and the class-bearing
page marker.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401
from _bootstrap import REPO_ROOT

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


class TestStewardFrontmatter(unittest.TestCase):
    """Contract 1.5 acceptance test 7, and DEC-2026-0080 acceptance test 4.

    Pandoc consumes a leading YAML block into document metadata before the
    block stream. That is the whole mechanism: the frontmatter never becomes a
    block, so it cannot become a span, so it cannot be leading unattributed
    content. These tests pin the consequence rather than the mechanism, because
    the consequence is what the contract states.
    """

    FRONTMATTER = (
        "---\n"
        "source: Rules Cyclopedia\n"
        "series: RC\n"
        "product_line: Basic D&D\n"
        "pages: 6-12\n"
        "---\n\n"
    )

    def test_frontmatter_is_not_unattributed_content(self):
        result = parse(self.FRONTMATTER + "# Chapter 1 {#p6}\n\nbody\n")
        self.assertEqual(result.unattributed_text, "")
        self.assertEqual(result.warnings, [])

    def test_frontmatter_is_kept_as_informational_intake_metadata(self):
        result = parse(self.FRONTMATTER + "# Chapter 1 {#p6}\n")
        self.assertEqual(result.frontmatter["source"], "Rules Cyclopedia")
        self.assertEqual(result.frontmatter["pages"], "6-12")

    def test_frontmatter_does_not_supply_a_page(self):
        """It is not a page locator, however page-shaped its values look."""
        result = parse(self.FRONTMATTER + "orphan paragraph\n\n# T {#p6}\n")
        orphan = [s for s in result.spans if "orphan" in s.text][0]
        self.assertIsNone(orphan.page, "declaring pages: 6-12 does not attribute prose")

    def test_real_leading_content_is_still_reported_alongside_frontmatter(self):
        """Admitting frontmatter must not suppress the check it sits in front of."""
        result = parse(self.FRONTMATTER + "orphan paragraph\n\n# T {#p6}\n")
        self.assertEqual(result.unattributed_text, "orphan paragraph")
        self.assertTrue(any("before the first page marker" in w for w in result.warnings))

    def test_the_live_incoming_packets_carry_frontmatter_and_no_orphan_prose(self):
        """Against the steward's actual files, not a fixture of them.

        Deliberately tolerant about their marker content: DEC-2026-0080 requires
        the page-1 input to be reissued before claim, and these are unclaimed
        inputs no pipeline role owns. What must hold across that reissue is that
        their frontmatter is metadata and none of it is read as prose.
        """
        incoming = REPO_ROOT / "books" / "basicdnd" / "rc" / "packets" / "incoming"
        sources = sorted(incoming.glob("RC_pages_*.md"))
        if not sources:
            # Incoming packets belong to the source steward, who may withdraw,
            # reissue or rename them at any time; they are not a Builder input
            # and their absence says nothing about the parser. Skipping keeps
            # this an assertion about parsing rather than about intake state.
            self.skipTest("no Rules Cyclopedia incoming source is present")
        for source in sources:
            with self.subTest(source=source.name):
                result = pagemarkers.parse_source(source)
                self.assertIn("source", result.frontmatter)
                self.assertNotIn("Rules Cyclopedia", result.unattributed_text)


class TestPageClasses(unittest.TestCase):
    """Contract 1.5 acceptance test 8: `full-page-artwork` on an attribute.

    The class is intake metadata for a page the steward declares carries no
    graph-constitutable content. The parser's whole job here is to tell the two
    admitted spellings from the bare one that looks identical in the raw file.
    """

    DIV = "::: {#p23 .full-page-artwork}\n:::\n"
    HEADING = "# CHAPTER TITLE {#p23 .full-page-artwork}\n"
    BARE = "{#p23 .full-page-artwork}\n"

    def test_a_fenced_div_resolves_its_page_and_class(self):
        result = parse(self.DIV)
        self.assertEqual(len(result.page_classes), 1)
        marker = result.page_classes[0]
        self.assertEqual(marker.page, 23)
        self.assertEqual(marker.classes, ("full-page-artwork",))
        self.assertEqual(marker.block, "div")
        self.assertEqual(marker.unknown, ())

    def test_an_artwork_page_counts_as_a_marked_page(self):
        """Otherwise a classified page reads downstream as an unmarked gap."""
        result = parse(self.DIV + "\n# Next {#p24}\n")
        self.assertEqual(result.pages, (23, 24))

    def test_a_heading_resolves_its_page_and_class(self):
        result = parse(self.HEADING)
        marker = result.page_classes[0]
        self.assertEqual((marker.page, marker.block), (23, "heading"))
        self.assertEqual(marker.classes, ("full-page-artwork",))
        heading = [s for s in result.spans if s.kind == "heading"][0]
        self.assertEqual(heading.page, 23)
        self.assertIn("CHAPTER TITLE", heading.text)

    def test_pages_with_class_lists_the_classified_pages(self):
        result = parse(self.DIV + "\n# Next {#p24}\n")
        self.assertEqual(result.pages_with_class("full-page-artwork"), (23,))
        self.assertEqual(result.pages_with_class("not-a-class"), ())

    def test_a_class_bearing_marker_is_not_reported_as_malformed(self):
        """The regression the contract names by hand: raw-text matching must not
        reject a valid attributed marker. Both admitted forms carry exactly the
        characters of the invalid one; only the AST separates them."""
        for markdown in (self.DIV, self.HEADING):
            with self.subTest(form=markdown.split()[0]):
                self.assertEqual(parse(markdown).malformed_markers, [])

    def test_the_bare_paragraph_form_is_rejected(self):
        result = parse(self.BARE)
        self.assertEqual(result.pages, (), "a bare token resolves no page")
        self.assertEqual(result.page_classes, [], "and carries no class")
        self.assertEqual(len(result.malformed_markers), 1)
        self.assertEqual(result.malformed_markers[0].text, "{#p23 .full-page-artwork}")
        self.assertIn("heading or an empty fenced Div", result.malformed_markers[0].reason)

    def test_the_bare_form_is_not_carried_into_prose(self):
        """It is metadata the steward misspelled, not rulebook text."""
        result = parse("# T {#p1}\n\n" + self.BARE)
        self.assertNotIn("full-page-artwork", " ".join(s.text for s in result.spans))

    def test_an_unknown_class_is_recorded_as_unknown(self):
        """The vocabulary is closed; a new class is an Architect question."""
        result = parse("::: {#p23 .full-page-diagram}\n:::\n")
        marker = result.page_classes[0]
        self.assertEqual(marker.unknown, ("full-page-diagram",))
        self.assertEqual(result.pages_with_class("full-page-artwork"), ())

    def test_a_class_without_a_page_identifier_resolves_to_no_page(self):
        """The contract binds the class to the reserved pN identifier."""
        result = parse("# T {#p1}\n\n::: {.full-page-artwork}\ncontent\n:::\n")
        self.assertEqual(result.page_classes, [])
        self.assertEqual(len(result.malformed_markers), 1)
        self.assertIn("no reserved", result.malformed_markers[0].reason)

    def test_an_ordinary_div_still_passes_its_content_through(self):
        """Divs existed before page classes; they must keep working."""
        result = parse("# T {#p1}\n\n::: {.sidebar}\ninner prose\n:::\n")
        inner = [s for s in result.spans if "inner prose" in s.text]
        self.assertEqual(inner[0].page, 1)
        self.assertEqual(result.malformed_markers, [])


class TestPageClassLint(unittest.TestCase):
    """`lint-source` behaviour on the forms DEC-2026-0080 admits and refuses."""

    def lint(self, **files):
        import io
        from contextlib import redirect_stdout

        from adnd1e_builder.cli import lint_source

        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, text in files.items():
                path = Path(tmp) / (name + ".md")
                path.write_text(text, encoding="utf-8", newline="\n")
                paths.append(path)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = lint_source(paths)
        return code, buffer.getvalue()

    def test_a_fenced_div_artwork_page_passes_and_is_reported_for_the_manifest(self):
        code, output = self.lint(
            packet="::: {#p1 .full-page-artwork}\n:::\n\n# Contents {#p2}\n\nbody\n"
        )
        self.assertEqual(code, 0, output)
        self.assertNotIn("PROBLEM", output)
        self.assertIn("page 1 classified full-page-artwork", output)
        self.assertIn("packet.yaml composition metadata", output)
        # The classified page is marked, so it is not reported as a gap either.
        self.assertNotIn("no marker for page", output)

    def test_the_bare_form_fails_and_names_the_correction(self):
        code, output = self.lint(
            packet="{#p1 .full-page-artwork}\n\n# Contents {#p2}\n\nbody\n"
        )
        self.assertEqual(code, 1)
        self.assertIn("malformed marker", output)
        self.assertIn("fenced Div", output)

    def test_frontmatter_is_reported_as_informational_only(self):
        code, output = self.lint(
            packet="---\nsource: Rules Cyclopedia\n---\n\n# Contents {#p2}\n\nbody\n"
        )
        self.assertEqual(code, 0, output)
        self.assertIn("packet.yaml is authoritative", output)
        self.assertNotIn("PROBLEM", output)

    def test_an_unknown_page_class_fails(self):
        code, output = self.lint(packet="::: {#p1 .full-page-diagram}\n:::\n\nbody\n")
        self.assertEqual(code, 1)
        self.assertIn("unknown page class", output)

    def test_a_plain_marker_packet_is_unaffected(self):
        """No page class, no frontmatter: the pre-1.5 output, unchanged."""
        code, output = self.lint(packet="### A {#p12}\n\nbody\n")
        self.assertEqual(code, 0, output)
        self.assertIn("pages resolved: 12-12", output)
        self.assertNotIn("classified", output)


PROSPECTIVE_CLASSES = ("full-page-artwork", "page-intentionally-ignored", "blank-page")


def lint_text(**files):
    """Run `lint-source` over synthetic files and return (exit code, output)."""
    import io
    from contextlib import redirect_stdout

    from adnd1e_builder.cli import lint_source

    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for name, text in files.items():
            path = Path(tmp) / (name + ".md")
            path.write_text(text, encoding="utf-8", newline="\n")
            paths.append(path)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = lint_source(paths)
    return code, buffer.getvalue()


class TestClosedPageClassVocabulary(unittest.TestCase):
    """DEC-2026-0084 acceptance test 1: exactly three classes, closed."""

    def test_the_vocabulary_is_exactly_the_three_ruled_classes(self):
        self.assertEqual(pagemarkers.PAGE_CLASSES, frozenset(PROSPECTIVE_CLASSES))

    def test_the_set_and_its_documentation_cannot_drift_apart(self):
        self.assertEqual(
            set(pagemarkers.PAGE_CLASS_MEANINGS), set(pagemarkers.PAGE_CLASSES))

    def test_no_fourth_class_is_admitted(self):
        """Membership is the only test, so there is nothing to fall through."""
        for outsider in ("full-page-diagram", "page-ignored", "blank",
                         "blank-pages", "full-page-artwork-2", ""):
            with self.subTest(name=outsider):
                self.assertNotIn(outsider, pagemarkers.PAGE_CLASSES)

    def test_each_class_declares_something_different(self):
        meanings = list(pagemarkers.PAGE_CLASS_MEANINGS.values())
        self.assertEqual(len(set(meanings)), len(meanings))

    def test_the_exclusion_class_does_not_claim_the_page_is_empty(self):
        """The Decision is explicit: exclusion is not a claim of absence."""
        ignored = pagemarkers.PAGE_CLASS_MEANINGS["page-intentionally-ignored"]
        self.assertIn("exclu", ignored)
        self.assertIn("not that the page is blank or artwork", ignored)
        self.assertIn("blank", pagemarkers.PAGE_CLASS_MEANINGS["blank-page"])

    def test_only_the_steward_declares_a_class(self):
        self.assertIn("steward", pagemarkers.__doc__ or "")
        for name, meaning in pagemarkers.PAGE_CLASS_MEANINGS.items():
            with self.subTest(name=name):
                self.assertIn("steward", meaning)


class TestEveryPageClassIsParsed(unittest.TestCase):
    """Acceptance test 2, parameterized over the whole vocabulary.

    The three classes are deliberately exercised through the same assertions:
    recognition and page-state behaviour belong to the marker, not to which
    class it carries, so any difference between them here would be a defect.
    """

    def div(self, name, page=23):
        return f"::: {{#p{page} .{name}}}\n:::\n"

    def heading(self, name, page=23):
        return f"# CHAPTER TITLE {{#p{page} .{name}}}\n"

    def forms(self, name, page=23):
        return (("div", self.div(name, page)), ("heading", self.heading(name, page)))

    def test_both_admitted_forms_resolve_the_page_and_class(self):
        for name in PROSPECTIVE_CLASSES:
            for block, markdown in self.forms(name):
                with self.subTest(page_class=name, form=block):
                    result = parse(markdown)
                    self.assertEqual(len(result.page_classes), 1)
                    marker = result.page_classes[0]
                    self.assertEqual(marker.page, 23)
                    self.assertEqual(marker.classes, (name,))
                    self.assertEqual(marker.block, block)
                    self.assertEqual(marker.unknown, ())

    def test_a_classified_page_counts_as_a_marked_page(self):
        """Otherwise it reads downstream as an unmarked gap in the span."""
        for name in PROSPECTIVE_CLASSES:
            for block, markdown in self.forms(name):
                with self.subTest(page_class=name, form=block):
                    result = parse(markdown + "\n# Next {#p24}\n")
                    self.assertEqual(result.pages, (23, 24))

    def test_pages_with_class_lists_only_that_class(self):
        for name in PROSPECTIVE_CLASSES:
            with self.subTest(page_class=name):
                result = parse(self.div(name) + "\n# Next {#p24}\n")
                self.assertEqual(result.pages_with_class(name), (23,))
                for other in PROSPECTIVE_CLASSES:
                    if other != name:
                        self.assertEqual(result.pages_with_class(other), ())

    def test_no_admitted_form_is_reported_as_malformed(self):
        for name in PROSPECTIVE_CLASSES:
            for block, markdown in self.forms(name):
                with self.subTest(page_class=name, form=block):
                    self.assertEqual(parse(markdown).malformed_markers, [])

    def test_no_marker_token_survives_into_extracted_prose(self):
        for name in PROSPECTIVE_CLASSES:
            for block, markdown in self.forms(name):
                with self.subTest(page_class=name, form=block):
                    result = parse("# T {#p1}\n\nbody\n\n" + markdown)
                    prose = " ".join(s.text for s in result.spans)
                    self.assertNotIn(name, prose)
                    self.assertNotIn("{#p", prose)

    def test_the_class_belongs_only_to_its_own_page(self):
        """It is not inherited by whatever page follows it."""
        for name in PROSPECTIVE_CLASSES:
            with self.subTest(page_class=name):
                result = parse(self.div(name, 322) + "\n# Later {#p323}\n\nbody\n")
                self.assertEqual(result.pages_with_class(name), (322,))
                self.assertNotIn(323, result.pages_with_class(name))


class TestEveryPageClassLints(unittest.TestCase):
    """Acceptance test 3, parameterized over the whole vocabulary."""

    def test_a_classified_page_passes_and_is_reported_for_the_manifest(self):
        for name in PROSPECTIVE_CLASSES:
            with self.subTest(page_class=name):
                code, output = lint_text(
                    packet=f"::: {{#p1 .{name}}}\n:::\n\n# Contents {{#p2}}\n\nbody\n")
                self.assertEqual(code, 0, output)
                self.assertIn(f"page 1 classified {name}", output)
                self.assertIn("packet.yaml composition metadata", output)

    def test_the_note_states_what_that_class_actually_declares(self):
        for name in PROSPECTIVE_CLASSES:
            with self.subTest(page_class=name):
                code, output = lint_text(
                    packet=f"::: {{#p1 .{name}}}\n:::\n\n# Contents {{#p2}}\n\nbody\n")
                self.assertIn(pagemarkers.PAGE_CLASS_MEANINGS[name], output)

    def test_a_classified_page_raises_no_uncovered_page_error(self):
        for name in PROSPECTIVE_CLASSES:
            with self.subTest(page_class=name):
                code, output = lint_text(
                    packet=f"::: {{#p1 .{name}}}\n:::\n\n# Contents {{#p2}}\n\nbody\n")
                self.assertEqual(code, 0, output)
                self.assertNotIn("no marker for page", output)
                self.assertNotIn("PROBLEM", output)

    def test_a_later_plain_page_is_not_reported_as_classified(self):
        for name in PROSPECTIVE_CLASSES:
            with self.subTest(page_class=name):
                code, output = lint_text(
                    packet=f"::: {{#p1 .{name}}}\n:::\n\n# Contents {{#p2}}\n\nbody\n")
                self.assertEqual(code, 0, output)
                self.assertIn("page 1 classified", output)
                self.assertNotIn("page 2 classified", output)

    def test_the_heading_form_lints_the_same_way(self):
        for name in PROSPECTIVE_CLASSES:
            with self.subTest(page_class=name):
                code, output = lint_text(
                    packet=f"# CREDITS {{#p1 .{name}}}\n\n# Contents {{#p2}}\n\nbody\n")
                self.assertEqual(code, 0, output)
                self.assertIn(f"page 1 classified {name}", output)


class TestRejectedPageClassForms(unittest.TestCase):
    """Acceptance test 4: what the extension must not start accepting."""

    def test_an_unknown_class_fails_lint(self):
        for unknown in ("full-page-diagram", "page-skipped", "blank"):
            with self.subTest(page_class=unknown):
                code, output = lint_text(
                    packet=f"::: {{#p1 .{unknown}}}\n:::\n\nbody\n")
                self.assertEqual(code, 1, output)
                self.assertIn("unknown page class", output)

    def test_a_near_miss_typo_of_a_real_class_fails(self):
        """The closed vocabulary is exact; a typo is a steward correction."""
        for typo in ("blank_page", "blank-pages", "page-intentionaly-ignored",
                     "Page-Intentionally-Ignored", "full-page-art"):
            with self.subTest(page_class=typo):
                code, output = lint_text(packet=f"::: {{#p1 .{typo}}}\n:::\n\nbody\n")
                self.assertEqual(code, 1, output)
                self.assertIn("unknown page class", output)

    def test_the_bare_paragraph_form_stays_malformed_for_every_class(self):
        for name in PROSPECTIVE_CLASSES:
            with self.subTest(page_class=name):
                result = parse(f"{{#p23 .{name}}}\n")
                self.assertEqual(result.pages, ())
                self.assertEqual(result.page_classes, [])
                self.assertEqual(len(result.malformed_markers), 1)
                self.assertIn("heading or an empty fenced Div",
                              result.malformed_markers[0].reason)

    def test_the_bare_form_fails_lint_for_every_class(self):
        for name in PROSPECTIVE_CLASSES:
            with self.subTest(page_class=name):
                code, output = lint_text(
                    packet=f"{{#p1 .{name}}}\n\n# Contents {{#p2}}\n\nbody\n")
                self.assertEqual(code, 1, output)
                self.assertIn("malformed marker", output)

    def test_a_recognized_class_without_a_reserved_identifier_is_malformed(self):
        for name in PROSPECTIVE_CLASSES:
            with self.subTest(page_class=name):
                result = parse(f"# T {{#p1}}\n\n::: {{.{name}}}\ncontent\n:::\n")
                self.assertEqual(result.page_classes, [])
                self.assertEqual(len(result.malformed_markers), 1)
                self.assertIn("no reserved", result.malformed_markers[0].reason)

    def test_an_ordinary_non_page_div_class_is_untouched(self):
        """Divs predate page classes and are not intake metadata."""
        for ordinary in ("sidebar", "note", "example"):
            with self.subTest(div_class=ordinary):
                result = parse(f"# T {{#p1}}\n\n::: {{.{ordinary}}}\ninner prose\n:::\n")
                inner = [s for s in result.spans if "inner prose" in s.text]
                self.assertEqual(inner[0].page, 1)
                self.assertEqual(result.malformed_markers, [])
                self.assertEqual(result.page_classes, [])


class TestIgnoredPageInASpan(unittest.TestCase):
    """Acceptance test 5, on a bounded synthetic fixture.

    This reproduces the shape the escalation reported -- an excluded page 322
    followed by ordinary pages 323-325 -- without reading or depending on the
    live packet, whose unrelated wrapper defects are outside this ruling.
    """

    FIXTURE = (
        "::: {#p322 .page-intentionally-ignored}\n"
        ":::\n"
        "\n"
        "# COMMUNITY {#p323}\n"
        "\n"
        "first body paragraph\n"
        "\n"
        "# CREDITS {#p324}\n"
        "\n"
        "second body paragraph\n"
        "\n"
        "# LICENSING {#p325}\n"
        "\n"
        "third body paragraph\n"
    )

    def test_all_four_pages_resolve(self):
        self.assertEqual(parse(self.FIXTURE).pages, (322, 323, 324, 325))

    def test_only_page_322_is_classified(self):
        result = parse(self.FIXTURE)
        self.assertEqual(
            result.pages_with_class("page-intentionally-ignored"), (322,))
        self.assertEqual(len(result.page_classes), 1)

    def test_the_following_pages_keep_their_content(self):
        """The exclusion applies to its own page and nothing after it."""
        result = parse(self.FIXTURE)
        self.assertIn("first body paragraph", result.text_for_page(323))
        self.assertIn("third body paragraph", result.text_for_page(325))

    def test_nothing_is_reported_as_unknown_or_malformed(self):
        result = parse(self.FIXTURE)
        self.assertEqual(result.malformed_markers, [])
        self.assertEqual(result.page_classes[0].unknown, ())

    def test_the_span_lints_clean_and_reports_the_exclusion(self):
        code, output = lint_text(packet=self.FIXTURE)
        self.assertEqual(code, 0, output)
        self.assertIn("pages resolved: 322-325 (4 marked)", output)
        self.assertIn("page 322 classified page-intentionally-ignored", output)
        self.assertNotIn("no marker for page", output)

    def test_the_excluded_page_is_not_relabelled_as_artwork_or_blank(self):
        """Preserving the actual classification is the point of the ruling."""
        code, output = lint_text(packet=self.FIXTURE)
        self.assertNotIn("full-page-artwork", output)
        self.assertNotIn("blank-page", output)


class TestImplementationStaysMetadataOnly(unittest.TestCase):
    """Acceptance test 7: parsing and linting classify, and nothing more."""

    def test_a_class_is_not_a_node_edge_or_citation(self):
        """`PageClassMarker` carries a page, its classes and its block. If it
        ever grew graph fields, a class would have become graph content."""
        marker = parse("::: {#p1 .blank-page}\n:::\n").page_classes[0]
        self.assertEqual(
            set(marker.__dataclass_fields__), {"page", "classes", "block", "unknown"})

    def test_a_classified_page_is_not_excluded_from_the_packet(self):
        """Automatic exclusion would hide source coverage; the page stays."""
        result = parse("::: {#p1 .page-intentionally-ignored}\n:::\n\n# T {#p2}\n\nbody\n")
        self.assertIn(1, result.pages)

    def test_linting_writes_nothing_back_to_the_source(self):
        import hashlib

        from adnd1e_builder.cli import lint_source

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "packet.md"
            path.write_text(TestIgnoredPageInASpan.FIXTURE, encoding="utf-8",
                            newline="\n")
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            import io
            from contextlib import redirect_stdout

            with redirect_stdout(io.StringIO()):
                lint_source([path])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["packet.md"])


if __name__ == "__main__":
    unittest.main()
