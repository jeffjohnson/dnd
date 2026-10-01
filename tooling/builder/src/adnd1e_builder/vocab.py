"""Controlled vocabularies and derivation tables from the graph constitution.

Every module-level constant here is transcribed from
``rulesets/adnd1e/governance/constitution.md`` v1.8. This module is the single
source of truth for the compiler; nothing downstream may hard-code a vocabulary.

Section references in comments point at the constitution.

`RulesetVocabulary` at the foot of the file is the ruleset-scoped form of the
same tables, read from a registered ruleset's own governance rather than from
these constants (DEC-2026-0080). The constants remain the AD&D 1e transcription
and keep their Decision history; a test pins the loaded AD&D 1e vocabulary to
them, so generalizing the compiler cannot quietly change what it accepts for
the ruleset it already compiles.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONSTITUTION_VERSION = "1.8"

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
#
# 1.8 (DEC-2026-0032 and DEC-2026-0033, one release) only *widens* section 3.1:
# `weapon_` is added for the mundane weapon identity, and `abil_` is extended to
# cover derived ability mechanics under an abbreviated stem. Neither retires a
# prefix nor changes any row-level rule, so every row valid under 1.7 stays
# valid under 1.8 and no GUP needs re-emitting for the version change alone.
# The node IDs the two Decisions retire are handled as reviewed migrations, not
# by this compiler rejecting rows that were valid when written.
ACCEPTED_GUR_CONSTITUTION_VERSIONS: frozenset[str] = frozenset(
    {"1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8"}
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
        # Added at constitution 1.8 by DEC-2026-0033: the mundane weapon
        # identity itself. `wpn_` stays reserved for a property or statistic of
        # a weapon (range, speed factor, weight), and `item_` stays the
        # magic-item and item-class namespace -- a mundane weapon is not an
        # `item_` merely because it is equipment.
        "weapon_",
    }
)

# -- section 3.1: derived ability mechanics (constitution 1.8) -----------------
# DEC-2026-0032 extends `abil_` from "ability score" to "ability score or
# derived ability mechanic" and fixes the derived form as
# `abil_<abbreviation>_<snake_case rule name>`, e.g. `abil_dex_reaction_adjustment`.
# The abbreviation names the score a mechanic derives from; it is not an
# alternate spelling for the score itself, so `abil_strength` and
# `abil_dexterity` keep their full-name identities.
ABILITY_ABBREVIATIONS: frozenset[str] = frozenset(
    {"str", "dex", "con", "int", "wis", "cha"}
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


# -- ruleset-scoped vocabulary (DEC-2026-0080) ---------------------------------
# A second ruleset makes the constants above what they always were: the AD&D 1e
# transcription. `basicdnd` is a separate graph with its own constitution, and
# DEC-2026-0080 states its parallel-looking prefix and edge tables are parallel
# vocabulary, not shared identity. So the compiler is given a vocabulary rather
# than importing one, and that vocabulary is read from the ruleset the artifact
# actually declares.
#
# The tables are read from the constitution's own Markdown rather than
# re-transcribed here. Transcription is what the constants above are for, and a
# second transcription of a second ruleset would be a second thing to keep in
# step by hand. Reading the governing table is also the check the Builder is
# allowed to make: it is a mechanical column read, not an interpretation.


class UnknownRuleset(LookupError):
    """A ruleset with no `rulesets/<id>/ruleset.yaml` in this repository.

    Not a validation finding. A GUR naming an unregistered ruleset has no
    governance to be compiled against, so there is nothing to compile it into
    and the Builder refuses before reading a row.
    """


class MalformedHistoricalVersionList(ValueError):
    """A ruleset's own `historical_gur_constitution_versions` is invalid.

    DEC-2026-0100: a malformed governed list is a configuration error, not a
    permissive fallback and not a reason to fall back to a retired hardcoded
    history. Raised rather than silently dropping the bad entries, because a
    silently narrowed set would reject a GUR the governing ruleset actually
    admits, and a silently widened one would accept a GUR it does not.
    """


#: Older constitution versions a ruleset still accepts on an incoming GUR.
#: This is transcribed governance and belongs per ruleset: the AD&D 1e range
#: exists because Decisions kept historical GURs compilable under revalidation
#: (see `ACCEPTED_GUR_CONSTITUTION_VERSIONS` above). A newly initialized ruleset
#: has no history, so it accepts its own current version and nothing else --
#: which is a fact about the ruleset, not a default worth widening.
HISTORICAL_ACCEPTED_GUR_CONSTITUTION_VERSIONS: dict[str, frozenset[str]] = {
    "adnd1e": ACCEPTED_GUR_CONSTITUTION_VERSIONS,
    # DEC-2026-0100 retired the Shadowdark entry that used to live here. That
    # transcription was correctly extended twice (DEC-2026-0087 for 1.0,
    # DEC-2026-0090 for 1.1) and then missed twice running -- the constitution
    # and both structural schemas moved to admit 1.2 and 1.3 while this
    # constant sat still, stranding sixteen published GURs that had done
    # nothing wrong. Shadowdark's historical-version set is now read from its
    # own `rulesets/shadowdark/ruleset.yaml` (`_historical_versions` below),
    # so amending the constitution updates the gate by construction and this
    # dict never needs a matching edit again. A ruleset with no entry here and
    # no governed list in its manifest simply has no historical compatibility,
    # which is the correct default for a newly registered ruleset.
}

#: `^\d+\.\d+$` -- the same dotted-numeric shape every constitution version
#: string in this repository already uses (`"1.0"`, `"1.4"`, ...).
_DOTTED_VERSION = re.compile(r"^[0-9]+\.[0-9]+$")


def _historical_versions(ruleset_id: str, manifest: dict) -> frozenset[str]:
    """A ruleset's historical GUR-version compatibility set.

    DEC-2026-0100: `historical_gur_constitution_versions` in the ruleset's own
    manifest is authoritative when present. Its absence preserves each other
    ruleset's existing behavior -- the transcribed `adnd1e` entry, or nothing
    for a ruleset with neither. A present-but-malformed list is a
    configuration error the Builder refuses to guess past, never a silent
    fallback to the retired hardcoded history: guessing here would mean the
    compiler, not the ruleset's own governance, decides what counts as
    historically admissible.
    """
    governed = manifest.get("historical_gur_constitution_versions")
    if governed is None:
        return HISTORICAL_ACCEPTED_GUR_CONSTITUTION_VERSIONS.get(ruleset_id, frozenset())

    if not isinstance(governed, list) or not governed:
        raise MalformedHistoricalVersionList(
            f"{ruleset_id!r} declares historical_gur_constitution_versions as "
            f"{governed!r}, which is not a nonempty list."
        )
    values = [str(entry) for entry in governed]
    bad = [value for value in values if not _DOTTED_VERSION.match(value)]
    if bad:
        raise MalformedHistoricalVersionList(
            f"{ruleset_id!r} historical_gur_constitution_versions contains "
            f"non-dotted-numeric value(s) {bad!r}; expected entries shaped like "
            f"'1.0'."
        )
    if len(values) != len(set(values)):
        duplicates = sorted({v for v in values if values.count(v) > 1})
        raise MalformedHistoricalVersionList(
            f"{ruleset_id!r} historical_gur_constitution_versions repeats "
            f"{duplicates!r}; every entry must be unique."
        )
    return frozenset(values)

_PREFIX_TABLE_HEADER = "| Prefix | Kind | Example |"
_EDGE_TABLE_HEADER = "| Type | Meaning | Direction |"
_POLARITY_TABLE_HEADER = "| Edge type | Derived polarity |"


def _first_column(text: str, header: str, cell: re.Pattern) -> frozenset[str]:
    """Values in column one of the Markdown table introduced by `header`.

    Reading stops at the first non-table line after the table has started, so a
    later table with the same shape elsewhere in the document cannot leak in.
    """
    if header not in text:
        return frozenset()
    found: set[str] = set()
    for line in text.split(header, 1)[1].splitlines():
        if not line.startswith("|"):
            if found:
                break
            continue
        match = cell.fullmatch(line.split("|")[1].strip())
        if match:
            found.add(match.group(1))
    return frozenset(found)


def _derived_polarity_table(text: str) -> dict[str, str]:
    """The `{edge_type: polarity}` pairing from a ruleset's own polarity table.

    Same table-reading discipline as `_first_column`, kept separate because a
    derivation table is a pairing, not a one-column set.
    """
    if _POLARITY_TABLE_HEADER not in text:
        return {}
    found: dict[str, str] = {}
    # Unlike the vocabulary table's `` `GATES` ``, this table's edge-type
    # column is plain, unquoted uppercase (`| GATES | enables |`).
    type_cell = re.compile(r"([A-Z_]+)")
    for line in text.split(_POLARITY_TABLE_HEADER, 1)[1].splitlines():
        if not line.startswith("|"):
            if found:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        match = type_cell.fullmatch(cells[0])
        polarity = cells[1]
        if match and polarity:
            found[match.group(1)] = polarity
    return found


def ruleset_derived_polarity(ruleset_id: str, ruleset_root: Path) -> dict[str, str]:
    """A ruleset's own `{edge_type: polarity}` derivation table.

    DEC-2026-0103: read from the ruleset's own constitution when it has the
    parseable two-column shape (Shadowdark section 5 does, and this is how a
    ruleset-scoped edge type such as `CLASSIFIED_AS` gets a derived polarity
    without adding it to another ruleset's vocabulary in code).

    Before this Decision, every ruleset shared one global `DERIVED_POLARITY`
    table unconditionally; AD&D 1e's own constitution states it as prose plus
    a three-column authored-polarity table rather than this two-column shape,
    and Basic D&D's constitution does not enumerate derived types at all --
    both rulesets' existing GURs and tests depend on the shared constant, not
    a per-ruleset one. So a ruleset with no parseable table of its own falls
    back to that same shared constant, not to an empty mapping: an empty
    fallback would silently turn every one of their GATES/RESOLVED_BY/etc.
    edges into "cannot derive polarity", which is the regression this
    fallback exists to avoid, not a scope narrowing this Decision asked for.
    """
    constitution = Path(ruleset_root) / "governance" / "constitution.md"
    if constitution.is_file():
        parsed = _derived_polarity_table(constitution.read_text(encoding="utf-8"))
        if parsed:
            return parsed
    return dict(DERIVED_POLARITY)


def constitution_prefixes(ruleset_root: Path) -> frozenset[str]:
    """The approved prefixes a ruleset's own constitution declares.

    Read from the governing table rather than a transcription, and addressed by
    ruleset root so a caller holding only that path -- `Governance.load` does --
    can scope itself without being handed a vocabulary it has no other use for.
    Falls back to the AD&D 1e constants when no constitution is present, which
    keeps every existing caller and fixture behaving exactly as before.
    """
    constitution = Path(ruleset_root) / "governance" / "constitution.md"
    if not constitution.is_file():
        return NODE_PREFIXES
    found = _first_column(
        constitution.read_text(encoding="utf-8"),
        _PREFIX_TABLE_HEADER,
        re.compile(r"`([a-z]+_)`"),
    )
    return found or NODE_PREFIXES


def registered_rulesets(repo_root: Path) -> frozenset[str]:
    """Every ruleset this repository has registered, by directory manifest."""
    root = Path(repo_root) / "rulesets"
    if not root.is_dir():
        return frozenset()
    return frozenset(
        child.name for child in root.iterdir() if (child / "ruleset.yaml").is_file()
    )


@dataclass(frozen=True)
class RulesetVocabulary:
    """The controlled vocabulary one registered ruleset compiles under."""

    ruleset_id: str
    constitution_version: str
    accepted_gur_constitution_versions: frozenset[str]
    #: Citation codes from the ruleset's book registry, which is what an edge's
    #: `book` column carries.
    books: frozenset[str]
    node_prefixes: frozenset[str]
    edge_types: frozenset[str]
    #: DEC-2026-0103: `{edge_type: polarity}` for this ruleset's own
    #: deterministic edge types, read from its own governance rather than a
    #: shared constant. `polarity.resolve` looks up an edge type here first;
    #: an edge type absent from this mapping is not derived for this ruleset,
    #: even if some other ruleset derives it.
    derived_polarity: dict[str, str] = field(default_factory=dict)
    #: Every ruleset registered when this vocabulary was loaded. Kept so the
    #: compiler can tell "this artifact belongs to another registered ruleset"
    #: from "this ruleset does not exist here" -- two different mistakes with
    #: two different fixes.
    registered_rulesets: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def for_adnd1e(cls) -> RulesetVocabulary:
        """The transcribed AD&D 1e vocabulary, with no filesystem read.

        The default for a compiler constructed without one, so existing callers
        and fixtures behave exactly as they did before this module grew a second
        ruleset.
        """
        return cls(
            ruleset_id="adnd1e",
            constitution_version=CONSTITUTION_VERSION,
            accepted_gur_constitution_versions=ACCEPTED_GUR_CONSTITUTION_VERSIONS,
            books=BOOKS,
            node_prefixes=NODE_PREFIXES,
            edge_types=EDGE_TYPES,
            derived_polarity=dict(DERIVED_POLARITY),
            registered_rulesets=frozenset({"adnd1e"}),
        )

    @classmethod
    def load(cls, repo_root: Path, ruleset_id: str) -> RulesetVocabulary:
        """Read one registered ruleset's vocabulary from its own governance."""
        repo_root = Path(repo_root)
        registered = registered_rulesets(repo_root)
        ruleset_root = repo_root / "rulesets" / ruleset_id
        manifest_path = ruleset_root / "ruleset.yaml"
        if ruleset_id not in registered or not manifest_path.is_file():
            raise UnknownRuleset(
                f"{ruleset_id!r} is not a registered ruleset in this repository; "
                f"registered: {', '.join(sorted(registered)) or 'none'}"
            )

        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        version = str(manifest.get("constitution_version") or "").strip()

        constitution = ruleset_root / "governance" / "constitution.md"
        text = constitution.read_text(encoding="utf-8") if constitution.is_file() else ""
        prefixes = _first_column(text, _PREFIX_TABLE_HEADER, re.compile(r"`([a-z]+_)`"))
        edges = _first_column(text, _EDGE_TABLE_HEADER, re.compile(r"`([A-Z_]+)`"))
        derived_polarity = _derived_polarity_table(text) or dict(DERIVED_POLARITY)

        books_path = ruleset_root / "registries" / "books.yaml"
        books: set[str] = set()
        if books_path.is_file():
            document = yaml.safe_load(books_path.read_text(encoding="utf-8")) or {}
            for book in document.get("books") or []:
                code = str((book or {}).get("citation_code") or "").strip()
                if code:
                    books.add(code)

        accepted = set(_historical_versions(ruleset_id, manifest))
        if version:
            accepted.add(version)

        return cls(
            ruleset_id=ruleset_id,
            constitution_version=version,
            accepted_gur_constitution_versions=frozenset(accepted),
            books=frozenset(books),
            node_prefixes=prefixes,
            edge_types=edges,
            derived_polarity=derived_polarity,
            registered_rulesets=registered,
        )
