"""Lineage-derived queue state — contracts/WORK_QUEUES.md 1.0.

Artifact directories are append-only stores, not inboxes. Which revision is
live is derived from `supersedes` links, never from filesystem modification
time.

This module currently implements leaf resolution, which every role queue is
built on. The full multi-role scanner assigned by DEC-2026-0012 is not built
yet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

REVISION_SUFFIX = re.compile(r"-r(\d+)$")


@dataclass
class LeafResult:
    leaf_id: str | None = None
    superseded: set[str] = field(default_factory=set)
    diagnostics: list[dict] = field(default_factory=list)
    legacy_inference: bool = False

    @property
    def ok(self) -> bool:
        return self.leaf_id is not None and not any(
            d["severity"] == "error" for d in self.diagnostics
        )


def revision_of(artifact_id: str) -> int | None:
    match = REVISION_SUFFIX.search(artifact_id or "")
    return int(match.group(1)) if match else None


def active_leaf(documents: dict[str, dict]) -> LeafResult:
    """Resolve the one live revision from a set of same-kind, same-packet artifacts.

    Rule 4: a revision is a leaf when no later artifact names its ID in
    `supersedes`. Artifacts published before WORK_QUEUES carry no `supersedes`,
    so when that leaves several candidates the contract's legacy rule applies:
    infer the highest `rNN` within one artifact kind and packet, and report the
    inference rather than passing it off as an explicit link.
    """
    result = LeafResult()
    if not documents:
        return result

    for artifact_id, document in documents.items():
        prior = document.get("supersedes")
        if prior:
            if prior not in documents:
                result.diagnostics.append(
                    {
                        "severity": "error",
                        "rule": "supersedes_target_missing",
                        "detail": f"{artifact_id} supersedes {prior!r}, which is not present",
                    }
                )
            result.superseded.add(prior)

    claimants: dict[str, list[str]] = {}
    for artifact_id, document in documents.items():
        prior = document.get("supersedes")
        if prior:
            claimants.setdefault(prior, []).append(artifact_id)
    for prior, claiming in claimants.items():
        if len(claiming) > 1:
            result.diagnostics.append(
                {
                    "severity": "error",
                    "rule": "forked_revision_chain",
                    "detail": (
                        f"{prior} is superseded by more than one artifact: "
                        f"{', '.join(sorted(claiming))}"
                    ),
                }
            )

    candidates = [i for i in documents if i not in result.superseded]

    if len(candidates) == 1:
        result.leaf_id = candidates[0]
        return result

    if not candidates:
        result.diagnostics.append(
            {
                "severity": "error",
                "rule": "no_active_leaf",
                "detail": "every revision is superseded; the chain is cyclic or malformed",
            }
        )
        return result

    # Several candidates: legacy artifacts predating the handoff block.
    numbered = [(revision_of(i), i) for i in candidates]
    if any(revision is None for revision, _ in numbered):
        result.diagnostics.append(
            {
                "severity": "error",
                "rule": "unresolvable_lineage",
                "detail": (
                    "several candidate leaves and at least one carries no rNN suffix, so the "
                    "legacy rule cannot order them: "
                    + ", ".join(sorted(candidates))
                ),
            }
        )
        return result

    result.legacy_inference = True
    result.leaf_id = max(numbered)[1]
    result.diagnostics.append(
        {
            "severity": "info",
            "rule": "legacy_revision_inference",
            "detail": (
                f"{len(candidates)} revisions carry no `supersedes` link, so the leaf was "
                f"inferred as the highest rNN ({result.leaf_id}) within this artifact kind and "
                f"packet. Inferred, not explicit."
            ),
        }
    )
    return result
