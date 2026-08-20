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

The fixture uses the two real magic-user bundles, which between them declare
`rule_hit_dice` and `monster_extra_dimensional` twice over with agreeing values.
Their only other blocker is three spell identities the unpublished druid-spells
packet owns, so the clone registers those to isolate the behaviour under test.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap
from _bootstrap import REPO_ROOT, RULESET_ID

from adnd1e_integrator.bundles import discover
from adnd1e_integrator.canonical import CanonicalPaths, Registry
from adnd1e_integrator.checksums import checksum_file
from adnd1e_integrator.integrate import IntegrationError, integrate

FIRST = "APPROVED-GUP-PKT-PHB-064-079-magic-user-spells-1-4-r07-r01"
SECOND = "APPROVED-GUP-PKT-PHB-079-094-magic-user-spells-5-9-r06-r01"

#: Declared by both bundles above, with identical label and kind in each. The
#: two exercise different paths: `rule_hit_dice` was already registered by
#: playing-the-game in INT-20260815-001, so it collides with the *registry*,
#: while `monster_extra_dimensional` is new and collides only within the batch.
ALREADY_REGISTERED = {"rule_hit_dice": ("Hit Dice", "rule")}
NEW_TO_THIS_BATCH = {"monster_extra_dimensional": ("Extra-Dimensional Creature", "monster")}
SHARED = {**ALREADY_REGISTERED, **NEW_TO_THIS_BATCH}

#: Owned by GUP-PKT-PHB-054-064-druid-spells-r01, which is not yet published.
DRUID_SPELLS = {
    "spell_charm_person_or_mammal": ("Charm Person or Mammal", "spell"),
    "spell_heat_metal": ("Heat Metal", "spell"),
    "spell_pyrotechnics": ("Pyrotechnics", "spell"),
}


def clone(target: Path) -> Path:
    for relative in [
        f"rulesets/{RULESET_ID}/canonical",
        f"rulesets/{RULESET_ID}/registries",
        f"rulesets/{RULESET_ID}/profiles",
        f"rulesets/{RULESET_ID}/governance",
        f"books/{RULESET_ID}/phb/artifacts",
    ]:
        source = REPO_ROOT / relative
        if source.exists():
            shutil.copytree(source, target / relative, dirs_exist_ok=True)

    # Stand in for the unpublished druid packet so the batch fails or succeeds
    # on the registration question alone, not on a missing endpoint.
    paths = CanonicalPaths(root=target, ruleset_id=RULESET_ID)
    registry = Registry.load(paths.registry)
    for node_id, (label, kind) in DRUID_SPELLS.items():
        if node_id not in registry.ids:
            registry.add({"id": node_id, "label": label, "kind": kind,
                          "degree": "0", "roles": ""})
    registry.save(paths.registry)
    return target


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
            self.assertEqual(set(by_id), set(SHARED))

            # Already in the registry: both bundles' declarations are absorbed.
            for node_id in ALREADY_REGISTERED:
                sources = {e["first_declared_by"] for e in by_id[node_id]}
                self.assertEqual(sources, {"already in the registry"})
                self.assertEqual({e["bundle_id"] for e in by_id[node_id]}, {FIRST, SECOND})

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
        self._assert_aborts("rule_hit_dice", "Hit Die", "INT-19700101-202")

    def test_conflicting_with_a_sibling_bundle_aborts(self):
        self._assert_aborts(
            "monster_extra_dimensional", "Extradimensional Creature", "INT-19700101-203")


if __name__ == "__main__":
    unittest.main()
