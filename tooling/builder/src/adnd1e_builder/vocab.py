"""Controlled vocabularies and derivation tables from the graph constitution.

Every constant here is transcribed from
``rulesets/adnd1e/governance/constitution.md`` v1.7. This module is the single
source of truth for the compiler; nothing downstream may hard-code a vocabulary.

Section references in comments point at the constitution.
"""

from __future__ import annotations

CONSTITUTION_VERSION = "1.7"

# Versions this compiler accepts on an incoming GUR. An older GUR is compilable
# but is *revalidated under the current constitution*, never trusted on the
# strength of its declared version (DEC-2026-0008 acceptance test: "Historical
# 1.2 and 1.3 GURs are revalidated under 1.4 rather than silently trusted").
#
# 1.4 is not merely permissive over its predecessors: it fixes citation
# cardinality to one locus per edge and settles MODIFIES vs DERIVED_FROM for
# table lookups. A 1.2 or 1.3 GUR can therefore contain rows that 1.4 forbids,
# and the validators below apply the 1.4 rules regardless of what the GUR says.
#
# 1.5 (DEC-2026-0015) adds no row-level rule. It leaves the closed prefix set
# untouched and only makes explicit that `spell_` already covered source-named
# spell families, plus a stem rule governing how such a node is *minted*. The
# Builder does not mint nodes, so a 1.4 row stays valid as written under 1.5.
#
# 1.6 adds constitution section 2.1 (DEC-2026-0017), which requires *more* rows
# where a source states caster-level scaling -- Analyst work the Builder is
# forbidden to synthesize -- and requires historical GURs to be revalidated under
# it. Packet-over-legacy page authority is a separate ruling (DEC-2026-0016) and
# lives in SOURCE_MARKDOWN 1.1, not in the constitution; it makes a page
# disagreement a citation correction rather than a row defect. Neither
# invalidates an existing row.
#
# 1.7 (DEC-2026-0020) adds section 5.1 and changes no row. It writes down the
# assertion key this compiler already applied, so every row valid under 1.6 is
# valid under 1.7 and no GUP needs re-emitting for the version change alone.
# Historical 1.6 GURs stay compilable and are revalidated under 1.7 like any
# other older revision.
ACCEPTED_GUR_CONSTITUTION_VERSIONS: frozenset[str] = frozenset(
    {"1.2", "1.3", "1.4", "1.5", "1.6", "1.7"}
)

# -- section 12: production column order --------------------------------------
# edges_master.csv is authoritative for column order. 18 columns.
COLUMNS: tuple[str, ...] = (
    "source_id",
    "source_label",
    "edge_type",
    "target_id",
    "target_label",
    "aspect",
    "condition",
    "polarity",
    "polarity_basis",
    "book",
    "page",
    "section",
    "evidence",
    "pass",
    "status",
    "supersession_basis",
    "general_rule_id",
    "review_flag",
)

# -- section 4: the closed edge vocabulary -------------------------------------
EDGE_TYPES: frozenset[str] = frozenset(
    {
        "MODIFIES",
        "DERIVED_FROM",
        "GATES",
        "TRIGGERS",
        "ALTERNATIVE_TO",
        "CONSUMES",
        "CONSTRAINS",
        "OVERRIDES",
        "FEEDS_INTO",
        "RESOLVED_BY",
        "CROSS_REFERENCES",
        "EXCLUDES",
        "EXCLUDED_FROM",
    }
)

# Direction semantics, recorded for the direction validator's error messages.
EDGE_DIRECTION: dict[str, str] = {
    "MODIFIES": "modifier -> modified",
    "DERIVED_FROM": "derived -> source",
    "GATES": "gate -> gated",
    "TRIGGERS": "cause -> effect",
    "ALTERNATIVE_TO": "either direction",
    "CONSUMES": "consumer -> resource",
    "CONSTRAINS": "constrainer -> constrained",
    "OVERRIDES": "overrider -> overridden",
    "FEEDS_INTO": "input -> process",
    "RESOLVED_BY": "thing -> procedure",
    "CROSS_REFERENCES": "source -> target",
    "EXCLUDES": "excluder -> excluded",
    "EXCLUDED_FROM": "excluded -> excluder",
}

# Section 5.1: ALTERNATIVE_TO is the only symmetric type. Its endpoints are
# sorted before the assertion key is compared, so reversing them does not create
# a second assertion. Every other type is directed and endpoint order matters.
SYMMETRIC_EDGE_TYPES: frozenset[str] = frozenset({"ALTERNATIVE_TO"})

# -- section 6: polarity -------------------------------------------------------
POLARITY_VALUES: frozenset[str] = frozenset(
    {"inflicts", "improves", "worsens", "negates", "enables", "governs", "neutral"}
)

POLARITY_BASIS_VALUES: frozenset[str] = frozenset({"derived", "read", "heuristic", "unset"})

# section 6.1: ten types determine polarity completely. The build assigns these
# and workers must never author them (invariants 13, 14).
DERIVED_POLARITY: dict[str, str] = {
    "GATES": "enables",
    "RESOLVED_BY": "governs",
    "EXCLUDES": "negates",
    "EXCLUDED_FROM": "negates",
    "DERIVED_FROM": "neutral",
    "ALTERNATIVE_TO": "neutral",
    "OVERRIDES": "neutral",
    "FEEDS_INTO": "neutral",
    "CROSS_REFERENCES": "neutral",
    "CONSUMES": "neutral",
}

# section 6.1: polarity is authored only on these three, where it carries
# information the edge type does not determine.
AUTHORED_POLARITY_TYPES: frozenset[str] = frozenset({"MODIFIES", "TRIGGERS", "CONSTRAINS"})

# A basis legal on an authored edge at GUR time. `heuristic` and `unset` are
# legal to carry but block approval (invariant 16).
AUTHORED_BASIS_APPROVAL_READY: frozenset[str] = frozenset({"read"})
AUTHORED_BASIS_BLOCKS_APPROVAL: frozenset[str] = frozenset({"heuristic", "unset"})

# -- section 7: evidence classes -----------------------------------------------
EVIDENCE_CLASSES: frozenset[str] = frozenset(
    {
        "explicit_rule",
        "explicit_reference",
        "inferred_rule",
        "analytic_classification",
        "speculative",
    }
)

# -- section 5 / 8 / 9: remaining controlled fields ----------------------------
BOOKS: frozenset[str] = frozenset({"PHB", "DMG", "UA", "MM"})

STATUS_VALUES: frozenset[str] = frozenset({"core", "optional"})

SUPERSESSION_BASIS_VALUES: frozenset[str] = frozenset(
    {"later_publication", "explicit_replacement", "conflicting_procedure", "optional_variant"}
)

REVIEW_FLAG_VALUES: frozenset[str] = frozenset(
    {"class_level_conflation", "mm_keyword_derived", "grouped_entry_attribution"}
)

# `pass` is extraction provenance and is open-ended by section 5, but
# `general-rule` is load-bearing: it is the trigger for requiring
# general_rule_id (section 7.1).
PASS_GENERAL_RULE = "general-rule"

# -- section 3.1: approved node prefixes ---------------------------------------
NODE_PREFIXES: frozenset[str] = frozenset(
    {
        "abil_",
        "class_",
        "race_",
        "rule_",
        "tbl_",
        # At constitution 1.5 by DEC-2026-0015 this reads "spell or source-named
        # spell family/category". No new prefix: a family is a `spell_` node with
        # a plural or category-specific stem, and is a distinct identity from any
        # specific spell -- `spell_fire_spells` does not alias `spell_fireball`.
        "spell_",
        "item_",
        "potion_",
        "sword_",
        "monster_",
        "cbt_",
        "save_",
        "psi_",
        "sys_",
        "exp_",
        "xp_",
        "hench_",
        "campaign_",
        "gen_",
        "ex_",
        "enc_",
        "money_",
        "prof_",
        "thief_",
        # Added at constitution 1.3 by DEC-2026-0004: "weapon property or weapon
        # statistic". The seven existing wpn_ nodes keep their IDs unchanged.
        "wpn_",
    }
)

# DEC-2026-0004 rejected str_, dex_, magic_, death_, turn_, cursed_, time_ and
# align_, and ruled the bare IDs comeliness, fatigue and training invalid. Those
# prefixes are absent from NODE_PREFIXES above and must stay absent; the affected
# node IDs are handled as a reviewed migration, not by widening the vocabulary.
REJECTED_PREFIXES: frozenset[str] = frozenset(
    {"str_", "dex_", "magic_", "death_", "turn_", "cursed_", "time_", "align_"}
)

# -- section 5.1: assertion key ------------------------------------------------
# Constitution 1.7 section 5.1 defines edge identity, and GRAPH_INVARIANTS 1.0
# invariant 12 requires tooling to implement the constitution's key rather than
# invent, omit or widen one. This tuple is that key, transcribed; it is not a
# tooling choice, and a test asserts it against the governing text.
#
# Two edges equal under it after the normalization in `duplicates.py` are one
# assertion and only one may enter production. Rows sharing source, type and
# target but differing in aspect or condition are near matches -- distinct
# assertions the Reviewer rules on, not duplicates the build may collapse.
ASSERTION_KEY: tuple[str, ...] = ("source_id", "edge_type", "target_id", "aspect", "condition")

# Section 5.1: fields that describe or review an assertion rather than identify
# it. A disagreement in one of these is resolved on the existing assertion, never
# preserved as a second edge.
IDENTITY_EXCLUDED_FIELDS: frozenset[str] = frozenset(
    {
        "source_label",
        "target_label",
        "polarity",
        "polarity_basis",
        "book",
        "page",
        "section",
        "evidence",
        "pass",
        "status",
        "supersession_basis",
        "general_rule_id",
        "review_flag",
    }
)

# Fields the Analyst may not author; the build owns them.
BUILD_OWNED_FIELDS: frozenset[str] = frozenset({"polarity", "polarity_basis"})
