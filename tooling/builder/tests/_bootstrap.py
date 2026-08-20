"""Put the Builder package on sys.path for test discovery."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Aspect for fixture edges that must NOT collide with a real canonical row.
#:
#: Fixtures used to name a plausible aspect like "class eligibility". That works
#: until the Integrator lands a bundle containing the same assertion, at which
#: point a test about polarity or identity starts failing on `duplicate_assertion`
#: and every such test has to be re-pinned by hand. The corpus grows on its own
#: schedule; the suite must not depend on what is absent from it today.
#:
#: An aspect no extraction would ever produce keeps the assertion key unique
#: without pinning anything. Tests that *want* a collision build it from a live
#: canonical row instead of hoping one exists.
FIXTURE_ASPECT = "builder test fixture aspect"


def canonical_row_where(canonical, predicate):
    """First live canonical row satisfying `predicate`, with its 1-based line.

    Tests that need a real row with some property -- an unset polarity basis, a
    particular edge type -- should ask for one rather than name a row number
    that renumbers whenever the graph is rebuilt.
    """
    for index, row in enumerate(canonical.rows):
        if predicate(row):
            return row, index + 2
    raise AssertionError("no canonical row satisfies the fixture predicate")


def unregistered_migration_pair(governance, registry):
    """A DEC-2026-0004 mapping whose target is still absent from the registry.

    The Integrator retires these one bundle at a time, so any single pair is a
    moving target. Asking for whichever one is still pending keeps the test
    meaningful for as long as the migration is unfinished.

    IDs whose migration DEC-2026-0050 made *due* are skipped. The rule this
    fixture serves -- that without Reviewer confirmation the legacy ID stands --
    still governs an ordinary pending migration, but a due ID is refused outright
    by the compiler, so selecting one would test the new rule while claiming to
    test the old one. Six pending-not-due pairs remain, and the assertion below
    fires if that ever stops being true rather than letting the subject drift.
    """
    for legacy, target in sorted(governance.migration_map.items()):
        if legacy in registry and target not in registry:
            if governance.migration_due(legacy):
                continue
            return legacy, target
    raise AssertionError(
        "every DEC-2026-0004 migration target is registered or its migration is due"
    )


def unregistered_returned_to_workflow(governance, registry):
    """A DEC-2026-0003 ordinary node proposal the registry does not hold yet.

    These are consumed as bundles land, so the test asks for whichever is still
    outstanding rather than naming one that will be registered next week. Once
    the last one lands there is no live case left, and the rule under test --
    that a returned-to-workflow node is proposed rather than escalated -- still
    has to hold for the next decision that returns one. So the fixture adds a
    synthetic entry to a copy of governance rather than expiring.

    Returns `(node_id, governance)`; the governance is the live one whenever a
    real case exists, so the live path stays covered while it lasts.
    """
    for node_id in sorted(governance.nodes_returned_to_workflow):
        if node_id not in registry:
            return node_id, governance

    synthetic = "rule_builder_test_returned_to_workflow"
    assert synthetic not in registry, "synthetic fixture ID collides with the registry"
    stand_in = copy.copy(governance)
    stand_in.nodes_returned_to_workflow = {
        **governance.nodes_returned_to_workflow,
        synthetic: "DEC-2026-0003",
    }
    return synthetic, stand_in
