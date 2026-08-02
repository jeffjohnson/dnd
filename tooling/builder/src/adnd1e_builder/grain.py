"""The grain rule: capture the relationship, never the number.

Constitution section 2 and invariant 11 forbid magnitudes, die expressions,
numeric bonuses, threshold values, and copied rule prose in `aspect` and
`condition`. This module makes that check mechanical.
"""

from __future__ import annotations

import re

# A bare digit anywhere in these fields is a magnitude, a threshold, or a page
# number that belongs in `page`. The audit of canonical found 9 such rows.
DIGIT = re.compile(r"\d")

# Die expressions: d6, 1d8, 2d4, d%. The percentile form ends in a non-word
# character, so the trailing boundary applies only to the numeric form.
DIE_EXPRESSION = re.compile(r"\b\d*d(?:\d+\b|%)", re.IGNORECASE)

# Signed numeric bonuses: +3, -1, +10%
SIGNED_NUMBER = re.compile(r"[+−-]\s*\d")

PERCENT = re.compile(r"%")

# Spelled-out magnitudes. These evade the digit check and are the more likely
# residue of copied prose. Ordinals are the common case in this corpus
# ("ninth-level spells", "eighteenth level"), so they are checked as words.
NUMBER_WORDS = frozenset(
    """zero one two three four five six seven eight nine ten eleven twelve
    thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty
    forty fifty sixty seventy eighty ninety hundred thousand
    first second third fourth fifth sixth seventh eighth ninth tenth eleventh
    twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth
    nineteenth twentieth""".split()
)

# `second` and `first` occur in non-numeric idiom often enough to be noise.
NUMBER_WORD_ALLOWLIST = frozenset({"first", "second"})

WORD = re.compile(r"[a-z]+")

# Section 5: aspect is "which facet is touched. 1-4 words."
ASPECT_MAX_WORDS = 4


def check_field(field_name: str, value: str) -> list[dict[str, str]]:
    """Return grain violations for one `aspect` or `condition` value."""
    findings: list[dict[str, str]] = []
    text = value or ""
    if not text.strip():
        return findings

    if DIE_EXPRESSION.search(text):
        findings.append(
            {
                "rule": "grain_die_expression",
                "severity": "error",
                "field": field_name,
                "detail": f"die expression in {field_name}: {text!r}",
            }
        )
    elif SIGNED_NUMBER.search(text):
        findings.append(
            {
                "rule": "grain_numeric_bonus",
                "severity": "error",
                "field": field_name,
                "detail": f"signed numeric bonus in {field_name}: {text!r}",
            }
        )
    elif DIGIT.search(text):
        findings.append(
            {
                "rule": "grain_magnitude",
                "severity": "error",
                "field": field_name,
                "detail": f"digit in {field_name}: {text!r}",
            }
        )

    if PERCENT.search(text):
        findings.append(
            {
                "rule": "grain_percentage",
                "severity": "error",
                "field": field_name,
                "detail": f"percentage in {field_name}: {text!r}",
            }
        )

    hits = sorted(
        {
            word
            for word in WORD.findall(text.lower())
            if word in NUMBER_WORDS and word not in NUMBER_WORD_ALLOWLIST
        }
    )
    if hits:
        findings.append(
            {
                "rule": "grain_spelled_magnitude",
                "severity": "warning",
                "field": field_name,
                "detail": f"spelled-out number in {field_name}: {', '.join(hits)} in {text!r}",
            }
        )

    return findings


def check_aspect_length(value: str) -> list[dict[str, str]]:
    """Section 5 caps `aspect` at four words. Advisory, not an invariant."""
    words = (value or "").split()
    if len(words) > ASPECT_MAX_WORDS:
        return [
            {
                "rule": "aspect_word_count",
                "severity": "warning",
                "field": "aspect",
                "detail": f"aspect is {len(words)} words, constitution section 5 says 1-4: {value!r}",
            }
        ]
    return []


def check_edge(aspect: str, condition: str) -> list[dict[str, str]]:
    """All grain findings for one edge."""
    findings = check_field("aspect", aspect)
    findings += check_field("condition", condition)
    findings += check_aspect_length(aspect)
    return findings
