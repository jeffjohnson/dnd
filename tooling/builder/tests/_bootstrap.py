"""Put the Builder package on sys.path for test discovery."""

from __future__ import annotations

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
    """
    for legacy, target in sorted(governance.migration_map.items()):
        if legacy in registry and target not in registry:
            return legacy, target
    raise AssertionError("every DEC-2026-0004 migration target is already registered")


def unregistered_returned_to_workflow(governance, registry):
    """A DEC-2026-0003 ordinary node proposal the registry does not hold yet.

    These are consumed as bundles land, so the test asks for whichever is still
    outstanding rather than naming one that will be registered next week.
    """
    for node_id in sorted(governance.nodes_returned_to_workflow):
        if node_id not in registry:
            return node_id
    raise AssertionError("every returned-to-workflow node is already registered")
