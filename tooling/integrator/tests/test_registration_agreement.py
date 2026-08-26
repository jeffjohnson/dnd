"""Two bundles in one batch declaring the same new node identity.

Packets are worked in parallel, so two of them can legitimately need the same
new identity and each Review approves it independently. The registry is the list
of approved node IDs (constitution 3.2), so that identity needs exactly one row:
registering it twice would be the defect, and refusing the second declaration as
an "overwrite" blocks a batch that is actually well formed.

The distinction that matters is agreement. An identical redeclaration is
absorbed; the same ID carrying a different label or kind is a real identity
conflict, and choosing between two definitions is not an integration decision --
so it must abort the batch rather than pick one.

The fixture uses the two real magic-user bundles, rewound from the clone so the
batch is measured against canonical as it stood before they landed. Pinning them
without the rewind tests a different thing entirely: once their rows are in
canonical the batch aborts on invariant 12 long before it reaches a registration
decision.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap
from _bootstrap import RULESET_ID
from test_transaction import clone_repo

from adnd1e_integrator.bundles import discover
from adnd1e_integrator.canonical import CanonicalPaths, Registry
from adnd1e_integrator.checksums import checksum_file
from adnd1e_integrator.integrate import IntegrationError, integrate

FIRST = "APPROVED-GUP-PKT-PHB-064-079-magic-user-spells-1-4-r08-r04"
SECOND = "APPROVED-GUP-PKT-PHB-079-094-magic-user-spells-5-9-r07-r03"

#: The two absorption paths this module exists to separate.
#:
#: `rule_concentration` is declared by SECOND and was already registered by the
#: illusionist packet in INT-20260825-001, so it collides with the *registry*.
#: `monster_extra_dimensional` is new to canonical and declared by both bundles,
#: so it collides only *within the batch*. Neither is special: what must hold is
#: that one identity keeps one registry row however many Reviews approve it.
ALREADY_REGISTERED = {"rule_concentration": ("Concentration", "rule")}
NEW_TO_THIS_BATCH = {"monster_extra_dimensional": ("Extra-Dimensional Creature", "monster")}
SHARED = {**ALREADY_REGISTERED, **NEW_TO_THIS_BATCH}


def clone(target: Path) -> Path:
    """A clone rewound to just before these two bundles were integrated.

    Only these two are rewound. The registry is shared, so rewinding a sibling
    as well would retire identities these bundles depend on but do not
    themselves register -- including the eight the illusionist packet landed,
    which are exactly what makes the already-in-the-registry path testable here.
    """
    return clone_repo(target, rewind_only={FIRST, SECOND})


def bundles_in(root: Path):
    found = {b.bundle_id: b for b in discover(root, RULESET_ID, "phb")[0]}
    return [found[FIRST], found[SECOND]]


def review_path(root: Path, bundle) -> Path:
    return root / "books" / RULESET_ID / "phb" / "artifacts" / "reviews" / \
        f"{bundle.review_id}.yaml"


def relabel_in_review(root: Path, bundle, node_id: str, label: str) -> None:
    """Rewrite one approved registration's label, re-pinning what covers it."""
    path = review_path(root, bundle)
    review = yaml.safe_load(path.read_text(encoding="utf-8"))
    for decision in review["node_registry_decisions"]:
        if decision["proposed_id"] == node_id:
            decision["submitted_label"] = label
            break
    else:
        raise AssertionError(f"{node_id} is not declared by {bundle.review_id}")
    path.write_text(yaml.safe_dump(review, sort_keys=False), encoding="utf-8")

    manifest_path = root / "books" / RULESET_ID / "phb" / "artifacts" / "approved" / \
        f"{bundle.bundle_id}.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["approves"]["review_checksum"] = checksum_file(path)
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


class TestAgreeingRedeclaration(unittest.TestCase):
    def test_shared_identity_is_registered_exactly_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
            before = Registry.load(paths.registry)

            batch = integrate(root, RULESET_ID, bundles_in(root),
                              integration_id="INT-19700101-200")

            after = Registry.load(paths.registry)
            for node_id in SHARED:
                rows = [r for r in after.rows if r.values["id"] == node_id]
                self.assertEqual(len(rows), 1, f"{node_id} has {len(rows)} registry rows")

            registered = [r["id"] for r in batch.registrations]
            for node_id in NEW_TO_THIS_BATCH:
                self.assertEqual(registered.count(node_id), 1)
            for node_id in ALREADY_REGISTERED:
                self.assertNotIn(node_id, registered,
                                 "an identity the registry already holds is not re-added")

            # The registry grows by the distinct new identities, not by the
            # number of declarations.
            self.assertEqual(len(after.rows) - len(before.rows), len(set(registered)))

    def test_the_absorbed_redeclaration_is_recorded_not_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            batch = integrate(root, RULESET_ID, bundles_in(root),
                              integration_id="INT-19700101-201")

            by_id: dict[str, list[dict]] = {}
            for entry in batch.registrations_redeclared:
                by_id.setdefault(entry["id"], []).append(entry)
            # Absorption must never be silent: every redeclaration records the
            # bundle that declared it and where the identity already came from.
            for node_id, entries in by_id.items():
                for entry in entries:
                    self.assertTrue(entry["bundle_id"], node_id)
                    self.assertTrue(entry["first_declared_by"], node_id)

            # The two pinned identities exercise the two distinct absorption
            # paths, which is what this test is for. Other packets may
            # legitimately come to share an identity with these bundles -- the
            # illusionist packet registered ten of them in INT-20260825-001 --
            # and reaching this line at all proves those agreed, because a
            # label or kind mismatch aborts the batch (TestDisagreeingRedeclaration).
            # So the pinned set must be absorbed; it need not be all that is.
            self.assertLessEqual(set(SHARED), set(by_id))

            # Already in the registry: the declaration is absorbed and says so,
            # naming the registry rather than a sibling bundle as the origin.
            for node_id in ALREADY_REGISTERED:
                sources = {e["first_declared_by"] for e in by_id[node_id]}
                self.assertEqual(sources, {"already in the registry"})
                self.assertEqual({e["bundle_id"] for e in by_id[node_id]}, {SECOND})

            # New to the batch: the first declaration registers it, the second
            # is absorbed and names the bundle that got there first.
            for node_id in NEW_TO_THIS_BATCH:
                self.assertEqual([e["bundle_id"] for e in by_id[node_id]], [SECOND])
                self.assertEqual(by_id[node_id][0]["first_declared_by"], FIRST)


class TestDisagreeingRedeclaration(unittest.TestCase):
    """A mismatch is invariant 4, on either path, and must not write a byte."""

    def _assert_aborts(self, node_id: str, label: str, integration_id: str):
        with tempfile.TemporaryDirectory() as tmp:
            root = clone(Path(tmp))
            paths = CanonicalPaths(root=root, ruleset_id=RULESET_ID)
            relabel_in_review(root, bundles_in(root)[1], node_id, label)

            before = {p: checksum_file(p) for p in paths.writable()}
            with self.assertRaises(IntegrationError) as caught:
                integrate(root, RULESET_ID, bundles_in(root), integration_id=integration_id)
            message = str(caught.exception)
            self.assertIn(node_id, message)
            self.assertIn(label, message)
            self.assertIn("invariant 4", message)
            self.assertEqual({p: checksum_file(p) for p in paths.writable()}, before)

    def test_conflicting_with_the_existing_registry_aborts(self):
        self._assert_aborts("rule_concentration", "Concentrating", "INT-19700101-202")

    def test_conflicting_with_a_sibling_bundle_aborts(self):
        self._assert_aborts(
            "monster_extra_dimensional", "Extradimensional Creature", "INT-19700101-203")


if __name__ == "__main__":
    unittest.main()
