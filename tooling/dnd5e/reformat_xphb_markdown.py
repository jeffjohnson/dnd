#!/usr/bin/env python3
"""
Reformat XPHB (2024 Player's Handbook) Markdown files 03 through 11
to match the established formatting of exemplars 00, 01, and 02.

Formatting Rules:
1. Table Captions: Always a heading one level deeper than parent level (min(6, parent + 1)).
   Format: {'#' * level} Table: Caption
2. Page Breaks:
   - Standalone format: ::: {#pXX}\n:::\n\n
   - Replace first occurrence of *[Source Page: XX]* with ::: {#pXX}\n::: before the title.
   - For all subsequent *[Page YY]* or *[Source Page: YY]*, replace first occurrence with ::: {#pYY}\n:::
   - Delete all duplicate occurrences of the same page number.
   - For 03-character-classes.md: strip cross-reference page tags in the intro summary before ## Barbarian so p49 spans the overview and p50 begins at ## Barbarian.
   - For 09-appendix-b-creature-stat-blocks.md: only pages in range [346, 359] belong to Appendix B; stray pages from other sources are stripped.
3. Images: Remove all markdown images (![...](...)) and immediately following *Image: ...* description text.
4. Insets / Blockquotes: Convert blockquotes (> ...) into ::: inset\n...\n::: matching 01 and 02.
5. Do NOT modify 00-introduction.md, 01-playing-the-game.md, or 02-creating-a-character.md.
"""

import os
import re
import sys

TARGET_FILES = [
    "03-character-classes.md",
    "04-character-origins.md",
    "05-feats.md",
    "06-equipment.md",
    "07-spells.md",
    "08-appendix-a-the-multiverse.md",
    "09-appendix-b-creature-stat-blocks.md",
    "10-rules-glossary.md",
    "11-credits.md",
]


def convert_blockquotes_to_insets(text: str) -> str:
    lines = text.splitlines()
    new_lines = []
    in_bq = False
    bq_lines = []

    for line in lines:
        if line.startswith(">"):
            in_bq = True
            if line.startswith("> "):
                bq_lines.append(line[2:])
            else:
                bq_lines.append(line[1:])
        else:
            if in_bq:
                while bq_lines and not bq_lines[0].strip():
                    bq_lines.pop(0)
                while bq_lines and not bq_lines[-1].strip():
                    bq_lines.pop()
                new_lines.append("::: inset")
                new_lines.extend(bq_lines)
                new_lines.append(":::")
                bq_lines = []
                in_bq = False
            new_lines.append(line)

    if in_bq:
        while bq_lines and not bq_lines[0].strip():
            bq_lines.pop(0)
        while bq_lines and not bq_lines[-1].strip():
            bq_lines.pop()
        new_lines.append("::: inset")
        new_lines.extend(bq_lines)
        new_lines.append(":::")

    return "\n".join(new_lines)


def remove_images(text: str) -> str:
    # Pattern to match ![...](...) and optional following *Image: ...* caption
    pattern = re.compile(
        r"(!\[.*?\]\([^\)]+\))\s*(?:\*Image:[^\n]*\*)?",
        re.DOTALL,
    )
    return pattern.sub("", text)


def reformat_content(content: str, fname: str) -> str:
    # Step 1: Convert blockquotes to ::: inset
    content = convert_blockquotes_to_insets(content)

    # Step 2: Remove all images and image descriptions
    content = remove_images(content)

    # Step 3: Handle 03 intro summary cross references
    if fname == "03-character-classes.md":
        barb_match = re.search(r"\n## Barbarian\b", content)
        if barb_match:
            barb_pos = barb_match.start()
            source_match = re.search(r"\*\[Source Page:\s*(\d+)\]\*", content)
            if source_match:
                source_end = source_match.end()
                # Find the last *[Page 50]* before ## Barbarian
                p50_matches = list(re.finditer(r"\*\[Page\s*50\]\*", content[:barb_pos]))
                if p50_matches:
                    last_p50_start = p50_matches[-1].start()
                    intro_part = content[source_end:last_p50_start]
                    intro_clean = re.sub(r"\*\[(?:Source )?Page:?\s*\d+\]\*", "", intro_part)
                    content = content[:source_end] + intro_clean + content[last_p50_start:]

    # Step 4: Handle chapter start page marker
    seen_pages = set()
    source_match = re.search(r"\*\[Source Page:\s*(\d+)\]\*", content)
    if source_match:
        start_page = int(source_match.group(1))
        seen_pages.add(start_page)
        # remove source_match from content
        content = content[:source_match.start()] + content[source_match.end():]
        # remove any leading whitespace/newlines from content
        content = content.lstrip("\r\n")
        # put ::: {#pXX}\n:::\n\n before title
        content = f"::: {{#p{start_page}}}\n:::\n\n" + content

    # Step 5: Table captions and subsequent page breaks
    lines = content.splitlines()
    final_lines = []
    parent_level = 1
    is_app_b = (fname == "09-appendix-b-creature-stat-blocks.md")

    for line in lines:
        stripped = line.strip()

        # Check section header
        h_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if h_match:
            title = h_match.group(2).strip()
            if not title.startswith("Table:"):
                parent_level = len(h_match.group(1))

        # Check table caption: **Table: ...** or # Table: ...
        t_match = re.match(r"^\*\*Table:\s*(.+?)\*\*\s*$", stripped)
        if not t_match:
            t_match = re.match(r"^#{1,6}\s+Table:\s*(.+?)\s*$", stripped)
        if t_match:
            tbl_title = t_match.group(1).rstrip("*").strip()
            cap_level = min(6, parent_level + 1)
            final_lines.append(f"{'#' * cap_level} Table: {tbl_title}")
            continue

        # Check page tags: *[Page XX]* or *[Source Page: XX]*
        p_match = re.match(r"^\*\[(?:Source )?Page:\s*(\d+)\]\*$", stripped)
        if not p_match:
            p_match = re.match(r"^\*\[Page\s*(\d+)\]\*$", stripped)
        if p_match:
            p_num = int(p_match.group(1))
            if is_app_b and not (346 <= p_num <= 359):
                # skip stray creature page from outside Appendix B
                continue
            if p_num not in seen_pages:
                seen_pages.add(p_num)
                final_lines.append(f"::: {{#p{p_num}}}")
                final_lines.append(":::")
                final_lines.append("")
            # if already seen, remove it (do not append)
            continue

        final_lines.append(line)

    result = "\n".join(final_lines)
    # Step 6: Normalize blank lines (max 1 blank line = max 2 newlines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    result = result.strip() + "\n"
    return result


def main():
    base_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "../../conversion-output/dnd5e-2024/xphb")
    )

    print(f"Reformatting XPHB markdown files in: {base_dir}")
    for fname in TARGET_FILES:
        filepath = os.path.join(base_dir, fname)
        if not os.path.exists(filepath):
            print(f"WARNING: File not found: {filepath}")
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        reformatted = reformat_content(content, fname)

        with open(filepath, "w", encoding="utf-8", newline="\n") as f:
            f.write(reformatted)

        print(f"Reformatted {fname}: {len(content)} -> {len(reformatted)} bytes")


if __name__ == "__main__":
    main()
