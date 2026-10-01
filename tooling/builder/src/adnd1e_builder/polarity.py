"""Polarity derivation and authored-polarity validation.

Constitution section 6.1 and invariants 13-17. Ten edge types determine
polarity completely and the build assigns them; three carry authored polarity
the build must preserve and validate but never invent.

DEC-2026-0103: which edge types are derived, and to what value, is read from
the active ruleset's own `RulesetVocabulary.derived_polarity` rather than a
single shared constant, so a ruleset-scoped derived type such as Shadowdark's
`CLASSIFIED_AS` does not have to become every ruleset's derived type. The
`AUTHORED_POLARITY_TYPES`/vocabulary constants stay a shared transcription:
no ruleset has yet needed its own authored-polarity set, so widening that
axis is left for the Decision that actually needs it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .vocab import (
    AUTHORED_BASIS_BLOCKS_APPROVAL,
    AUTHORED_POLARITY_TYPES,
    DERIVED_POLARITY,
    POLARITY_BASIS_VALUES,
    POLARITY_VALUES,
)

if TYPE_CHECKING:
    from .vocab import RulesetVocabulary


@dataclass(frozen=True)
class PolarityResult:
    polarity: str
    polarity_basis: str
    findings: tuple[dict[str, str], ...]
    blocks_approval: bool


def resolve(
    edge_type: str,
    authored_polarity: str | None,
    authored_basis: str | None,
    vocabulary: "RulesetVocabulary | None" = None,
) -> PolarityResult:
    """Determine the polarity pair for one edge.

    Deterministic types are computed and any authored value is a worker error
    (invariant 14). Authored types are preserved and validated (invariant 15).

    DEC-2026-0103: `vocabulary`, when supplied, derives from the active
    ruleset's own `derived_polarity` table instead of the shared AD&D 1e
    transcription, so a ruleset-scoped derived type is derived only for the
    ruleset that declares it. Omitting it keeps every existing caller -- test
    fixtures included -- on the exact prior AD&D 1e-transcribed behavior.
    """
    findings: list[dict[str, str]] = []
    authored_polarity = (authored_polarity or "").strip()
    authored_basis = (authored_basis or "").strip()
    derived_table = vocabulary.derived_polarity if vocabulary is not None else DERIVED_POLARITY

    if edge_type in derived_table:
        derived = derived_table[edge_type]
        if authored_polarity:
            if authored_polarity != derived:
                findings.append(
                    {
                        "rule": "polarity_authored_on_derived_type",
                        "severity": "error",
                        "detail": (
                            f"{edge_type} determines polarity={derived}; GUR authored "
                            f"{authored_polarity!r}. Invariant 14 forbids authoring it. "
                            f"Build value used."
                        ),
                    }
                )
            else:
                findings.append(
                    {
                        "rule": "polarity_authored_on_derived_type",
                        "severity": "warning",
                        "detail": (
                            f"{edge_type} determines polarity; GUR restated the correct "
                            f"value {derived!r}. Invariant 14 says workers do not author it."
                        ),
                    }
                )
        if authored_basis and authored_basis != "derived":
            findings.append(
                {
                    "rule": "polarity_basis_authored_on_derived_type",
                    "severity": "error",
                    "detail": (
                        f"{edge_type} requires polarity_basis=derived; GUR supplied "
                        f"{authored_basis!r}. Build value used."
                    ),
                }
            )
        return PolarityResult(derived, "derived", tuple(findings), blocks_approval=False)

    if edge_type in AUTHORED_POLARITY_TYPES:
        blocks = False
        if not authored_polarity:
            findings.append(
                {
                    "rule": "polarity_missing_on_authored_type",
                    "severity": "error",
                    "detail": (
                        f"{edge_type} requires Analyst-authored polarity (invariant 15). "
                        f"None supplied; recorded as unset, which blocks approval."
                    ),
                }
            )
            return PolarityResult("", "unset", tuple(findings), blocks_approval=True)

        if authored_polarity not in POLARITY_VALUES:
            findings.append(
                {
                    "rule": "polarity_value_illegal",
                    "severity": "error",
                    "detail": f"polarity {authored_polarity!r} is outside the section 6 vocabulary",
                }
            )
            blocks = True

        basis = authored_basis or "unset"
        if basis not in POLARITY_BASIS_VALUES:
            findings.append(
                {
                    "rule": "polarity_basis_illegal",
                    "severity": "error",
                    "detail": f"polarity_basis {basis!r} is outside the four legal values",
                }
            )
            blocks = True
        elif basis == "derived":
            findings.append(
                {
                    "rule": "polarity_basis_derived_on_authored_type",
                    "severity": "error",
                    "detail": (
                        f"{edge_type} polarity is authored, not derived; basis 'derived' is "
                        f"reserved for the ten deterministic types"
                    ),
                }
            )
            blocks = True
        elif basis in AUTHORED_BASIS_BLOCKS_APPROVAL:
            findings.append(
                {
                    "rule": "polarity_basis_blocks_approval",
                    "severity": "error",
                    "detail": (
                        f"polarity_basis={basis!r} may not survive into an approved patch "
                        f"(invariant 16, constitution section 6.1)"
                    ),
                }
            )
            blocks = True

        return PolarityResult(authored_polarity, basis, tuple(findings), blocks_approval=blocks)

    # Unknown edge type: the caller reports the vocabulary violation.
    return PolarityResult(
        authored_polarity,
        authored_basis or "unset",
        (
            {
                "rule": "polarity_undeterminable",
                "severity": "error",
                "detail": f"cannot derive polarity for unknown edge type {edge_type!r}",
            },
        ),
        blocks_approval=True,
    )
