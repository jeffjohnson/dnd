"""The same-session role context verifier, per DEC-2026-0040.

The tool's value is entirely in what it refuses. A verifier that returned a hit
one time it should not have would let a role act on superseded governance while
believing it was current -- worse than never caching at all. So most of this file
is invalidation: one test per thing that must turn a hit into a miss, and one per
thing that must fail closed rather than answer at all.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

MODULE_PATH = Path(__file__).parents[1] / "role_context.py"
SPEC = importlib.util.spec_from_file_location("role_context", MODULE_PATH)
assert SPEC and SPEC.loader
role_context = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = role_context
SPEC.loader.exec_module(role_context)

REPO_ROOT = Path(__file__).resolve().parents[3]


class RoleContextCase(unittest.TestCase):
    """A private repository skeleton.

    Built as a fixture rather than run against the live tree because these tests
    have to change authority files to prove invalidation, and the live governance
    files are not ours to touch.
    """

    SESSION = "session-alpha"

    MANIFEST = {
        "schema_version": "1.0",
        "cache_format_version": 1,
        "common_patterns": ["AGENTS.md", "contracts/*.md"],
        "roles": {
            "architect": {"stable_patterns": ["agents/architect/INSTRUCTIONS.md"]},
            "analyst": {"stable_patterns": ["agents/analyst/INSTRUCTIONS.md"]},
            "builder": {
                "stable_patterns": [
                    "agents/builder/INSTRUCTIONS.md",
                    "rulesets/{ruleset}/ruleset.yaml",
                    "schemas/{ruleset}/books/{book}/*.json",
                ]
            },
            "reviewer": {"stable_patterns": ["agents/reviewer/INSTRUCTIONS.md"]},
            "integrator": {"stable_patterns": ["agents/integrator/INSTRUCTIONS.md"]},
        },
    }

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.write("README.md", "# fixture\n")
        self.write("AGENTS.md", "# agents\n")
        self.write("contracts/WORK_QUEUES.md", "# queues\n")
        self.write("contracts/ARTIFACT_LIFECYCLE.md", "# lifecycle\n")
        for role in role_context.ROLES:
            self.write(f"agents/{role}/INSTRUCTIONS.md", f"# {role}\n")
        self.write("rulesets/adnd1e/ruleset.yaml", 'constitution_version: "1.8"\n')
        self.write("schemas/adnd1e/books/phb/source_metadata.schema.json", "{}\n")
        self.write_manifest(self.MANIFEST)
        self.write("schemas/common/role-context-manifest.schema.json", "{}\n")

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def write_manifest(self, document: dict) -> Path:
        return self.write(
            "contracts/ROLE_CONTEXT_MANIFEST.yaml",
            yaml.safe_dump(document, sort_keys=False),
        )

    def verify(self, *, role="builder", ruleset="adnd1e", book="phb", session=None):
        return role_context.verify(
            self.root, role, ruleset, book, session or self.SESSION
        )

    def record(self, *, role="builder", ruleset="adnd1e", book="phb", session=None):
        return role_context.record(
            self.root, role, ruleset, book, session or self.SESSION
        )

    def warm(self, **kwargs):
        """A recorded receipt and the hit that follows it."""
        self.record(**kwargs)
        return self.verify(**kwargs)


class TestColdAndWarm(RoleContextCase):
    def test_a_cold_verify_requires_a_reload_and_names_the_paths(self):
        result = self.verify()
        self.assertEqual(result["status"], "reload_required")
        self.assertIn("AGENTS.md", result["stable_authority_paths"])
        self.assertIn("agents/builder/INSTRUCTIONS.md", result["stable_authority_paths"])

    def test_recording_then_verifying_is_a_hit(self):
        self.assertEqual(self.warm()["status"], "cache_hit")

    def test_a_hit_does_not_re_emit_stable_context_content(self):
        """The paths are fine to print; their contents would defeat the point."""
        printed = self.warm()
        self.assertNotIn("stable_authority", printed)
        for value in printed.values():
            self.assertNotIn("# queues", str(value))

    def test_a_hit_is_repeatable(self):
        self.record()
        self.assertEqual(self.verify()["status"], "cache_hit")
        self.assertEqual(self.verify()["status"], "cache_hit")


class TestInvalidation(RoleContextCase):
    """One test per thing that must turn a hit back into a miss."""

    def assert_miss(self, result, fragment):
        self.assertEqual(result["status"], "reload_required")
        self.assertTrue(
            any(fragment in difference for difference in result["differences"]),
            f"{fragment!r} not in {result['differences']}",
        )

    def test_a_changed_authority_file_invalidates(self):
        self.record()
        self.write("contracts/WORK_QUEUES.md", "# queues, revised\n")
        self.assert_miss(self.verify(), "contracts/WORK_QUEUES.md changed on disk")

    def test_a_changed_role_instruction_invalidates(self):
        self.record()
        self.write("agents/builder/INSTRUCTIONS.md", "# builder, revised\n")
        self.assert_miss(self.verify(), "agents/builder/INSTRUCTIONS.md changed on disk")

    def test_a_changed_manifest_invalidates(self):
        self.record()
        manifest = json.loads(json.dumps(self.MANIFEST))
        manifest["common_patterns"] = ["AGENTS.md"]
        self.write_manifest(manifest)
        self.assert_miss(self.verify(), "manifest_checksum changed")

    def test_a_changed_manifest_schema_invalidates(self):
        self.record()
        self.write("schemas/common/role-context-manifest.schema.json", '{"x": 1}\n')
        self.assert_miss(self.verify(), "manifest_schema_checksum changed")

    def test_a_new_authority_file_invalidates(self):
        """A contract added under a glob is context the role has not read."""
        self.record()
        self.write("contracts/NEW_CONTRACT.md", "# new\n")
        self.assert_miss(self.verify(), "contracts/NEW_CONTRACT.md is new to the stable set")

    def test_a_removed_authority_file_invalidates(self):
        self.record()
        (self.root / "contracts" / "ARTIFACT_LIFECYCLE.md").unlink()
        self.assert_miss(
            self.verify(), "contracts/ARTIFACT_LIFECYCLE.md is no longer in the stable set"
        )

    def test_a_different_session_is_always_a_miss(self):
        """The stateless-agent rule: a fresh actor never inherits a receipt."""
        self.record()
        self.assert_miss(self.verify(session="session-beta"), "no receipt exists")

    def test_a_different_role_is_a_miss(self):
        self.record(role="builder")
        self.assert_miss(self.verify(role="reviewer"), "no receipt exists")

    def test_a_different_ruleset_is_a_miss(self):
        self.write("rulesets/other/ruleset.yaml", 'constitution_version: "1.8"\n')
        self.write("schemas/other/books/phb/source_metadata.schema.json", "{}\n")
        self.record()
        self.assert_miss(self.verify(ruleset="other"), "no receipt exists")

    def test_a_different_book_is_a_miss(self):
        self.write("schemas/adnd1e/books/dmg/source_metadata.schema.json", "{}\n")
        self.record()
        self.assert_miss(self.verify(book="dmg"), "no receipt exists")

    def test_a_different_repository_root_is_a_miss(self):
        """A receipt copied to another checkout describes a different tree."""
        self.record()
        stored = json.loads(
            role_context.receipt_path(
                self.root, "builder", "adnd1e", "phb", self.SESSION
            ).read_text(encoding="utf-8")
        )
        stored["repository_root"] = "/somewhere/else"
        role_context.receipt_path(
            self.root, "builder", "adnd1e", "phb", self.SESSION
        ).write_text(json.dumps(stored), encoding="utf-8")
        self.assert_miss(self.verify(), "repository_root changed")

    def test_an_unreadable_receipt_fails_closed(self):
        self.record()
        role_context.receipt_path(
            self.root, "builder", "adnd1e", "phb", self.SESSION
        ).write_text("{not json", encoding="utf-8")
        self.assert_miss(self.verify(), "the receipt is unreadable")

    def test_a_receipt_that_is_not_a_mapping_fails_closed(self):
        self.record()
        role_context.receipt_path(
            self.root, "builder", "adnd1e", "phb", self.SESSION
        ).write_text("[]", encoding="utf-8")
        self.assert_miss(self.verify(), "not a mapping")

    def test_a_receipt_with_no_file_set_fails_closed(self):
        self.record()
        path = role_context.receipt_path(self.root, "builder", "adnd1e", "phb", self.SESSION)
        stored = json.loads(path.read_text(encoding="utf-8"))
        del stored["stable_authority"]
        path.write_text(json.dumps(stored), encoding="utf-8")
        self.assert_miss(self.verify(), "records no stable_authority set")

    def test_every_identity_field_is_actually_compared(self):
        """A field added to the receipt must not quietly stop being checked."""
        for field in role_context.RECEIPT_IDENTITY_FIELDS:
            with self.subTest(field=field):
                current = role_context.build_receipt(
                    self.root, "builder", "adnd1e", "phb", self.SESSION
                )
                stored = json.loads(json.dumps(current))
                stored[field] = "tampered"
                self.assertTrue(
                    any(
                        difference.startswith(f"{field} changed")
                        for difference in role_context.compare(current, stored)
                    ),
                    field,
                )


class TestFailsClosed(RoleContextCase):
    def test_an_unrecognized_role_is_an_error(self):
        with self.assertRaises(role_context.ContextError) as caught:
            role_context.resolve_paths(
                self.root, self.MANIFEST, "steward", "adnd1e", "phb"
            )
        self.assertIn("unrecognized role", str(caught.exception))

    def test_a_missing_literal_path_is_an_error(self):
        manifest = json.loads(json.dumps(self.MANIFEST))
        manifest["common_patterns"] = ["AGENTS.md", "contracts/ABSENT.md"]
        self.write_manifest(manifest)
        with self.assertRaises(role_context.ContextError) as caught:
            self.verify()
        self.assertIn("does not exist", str(caught.exception))

    def test_a_missing_manifest_is_an_error(self):
        (self.root / "contracts" / "ROLE_CONTEXT_MANIFEST.yaml").unlink()
        with self.assertRaises(role_context.ContextError):
            self.verify()

    def test_a_manifest_omitting_a_role_is_an_error(self):
        manifest = json.loads(json.dumps(self.MANIFEST))
        del manifest["roles"]["integrator"]
        self.write_manifest(manifest)
        with self.assertRaises(role_context.ContextError) as caught:
            self.verify()
        self.assertIn("integrator", str(caught.exception))

    def test_an_unparseable_manifest_is_an_error(self):
        self.write("contracts/ROLE_CONTEXT_MANIFEST.yaml", "a: [1\nb: }\n")
        with self.assertRaises(role_context.ContextError):
            self.verify()

    def test_a_missing_manifest_schema_is_an_error(self):
        (self.root / "schemas" / "common" / "role-context-manifest.schema.json").unlink()
        with self.assertRaises(role_context.ContextError) as caught:
            self.verify()
        self.assertIn("schema is missing", str(caught.exception))

    def test_an_unresolved_placeholder_is_an_error(self):
        manifest = json.loads(json.dumps(self.MANIFEST))
        manifest["common_patterns"] = ["AGENTS.md", "rulesets/{unknown}/x.yaml"]
        self.write_manifest(manifest)
        with self.assertRaises(role_context.ContextError) as caught:
            self.verify()
        self.assertIn("unresolved placeholder", str(caught.exception))

    def test_an_escaping_pattern_is_an_error(self):
        outside = self.root.parent / "outside.md"
        outside.write_text("# outside\n", encoding="utf-8")
        self.addCleanup(outside.unlink)
        manifest = json.loads(json.dumps(self.MANIFEST))
        manifest["common_patterns"] = ["AGENTS.md", "../outside.md"]
        self.write_manifest(manifest)
        with self.assertRaises(role_context.ContextError) as caught:
            self.verify()
        self.assertIn("outside the repository root", str(caught.exception))

    def test_a_role_resolving_nothing_is_an_error(self):
        manifest = json.loads(json.dumps(self.MANIFEST))
        manifest["common_patterns"] = ["contracts/*.absent"]
        manifest["roles"]["builder"]["stable_patterns"] = ["agents/builder/*.absent"]
        self.write_manifest(manifest)
        with self.assertRaises(role_context.ContextError) as caught:
            self.verify()
        self.assertIn("resolved no stable authority files", str(caught.exception))


class TestTheCacheExcludesLiveState(RoleContextCase):
    """The boundary that keeps the repository authoritative for evidence.

    A manifest pattern is one edit away from pulling canonical data or a packet
    artifact into the cached set, and a role holding a stale canonical baseline is
    how a migration gets planned against a graph that no longer exists. The guard
    is deliberately independent of the manifest so that widening one cannot widen
    the other.
    """

    EXCLUDED = {
        "canonical graph": "rulesets/adnd1e/canonical/edges_master.csv",
        "node registry": "rulesets/adnd1e/registries/nodes.csv",
        "a packet artifact": "books/adnd1e/phb/artifacts/gur/GUR-PKT-PHB-001-002-x-r01.yaml",
        "a claimed packet": "books/adnd1e/phb/packets/claimed/x/source.md",
        "an escalation": "rulesets/adnd1e/escalations/pending/ESC-x.yaml",
        "a Decision": "rulesets/adnd1e/escalations/decisions/DEC-2026-0001.yaml",
        "an implementation report": "rulesets/adnd1e/decision-implementations/IMP-x-r01.yaml",
        "an integration manifest": "rulesets/adnd1e/manifests/INT-x.json",
        "a validation report": "rulesets/adnd1e/reports/INT-x.validation.json",
        "a build snapshot": "build/snapshots/INT-x/edges_master.csv",
    }

    def test_no_excluded_area_may_be_cached(self):
        for label, relative in self.EXCLUDED.items():
            with self.subTest(area=label):
                self.write(relative, "x\n")
                manifest = json.loads(json.dumps(self.MANIFEST))
                manifest["common_patterns"] = ["AGENTS.md", relative]
                self.write_manifest(manifest)
                with self.assertRaises(role_context.ContextError) as caught:
                    self.verify()
                self.assertIn("would cache", str(caught.exception))

    def test_the_live_manifest_caches_nothing_excluded(self):
        """The real manifest, checked against the real tree."""
        manifest = role_context.load_manifest(REPO_ROOT)
        for role in role_context.ROLES:
            with self.subTest(role=role):
                for relative in role_context.resolve_paths(
                    REPO_ROOT, manifest, role, "adnd1e", "phb"
                ):
                    self.assertEqual(role_context._excluded(relative), "", relative)

    def test_the_builder_set_excludes_the_registry_csv(self):
        """The Builder must re-read nodes.csv every task; it is never cached."""
        manifest = role_context.load_manifest(REPO_ROOT)
        resolved = role_context.resolve_paths(REPO_ROOT, manifest, "builder", "adnd1e", "phb")
        self.assertNotIn("rulesets/adnd1e/registries/nodes.csv", resolved)
        self.assertTrue(
            (REPO_ROOT / "rulesets" / "adnd1e" / "registries" / "nodes.csv").is_file(),
            "the registry exists, so its absence from the set is a rule not an accident",
        )


class TestReceiptContent(RoleContextCase):
    def test_a_receipt_holds_no_authority_file_content(self):
        self.record()
        text = role_context.receipt_path(
            self.root, "builder", "adnd1e", "phb", self.SESSION
        ).read_text(encoding="utf-8")
        for content in ("# queues", "# builder", "# lifecycle", "constitution_version"):
            self.assertNotIn(content, text)

    def test_a_receipt_holds_exactly_the_declared_fields(self):
        receipt = role_context.build_receipt(
            self.root, "builder", "adnd1e", "phb", self.SESSION
        )
        self.assertEqual(
            set(receipt),
            set(role_context.RECEIPT_IDENTITY_FIELDS) | {"stable_authority"},
        )

    def test_receipts_are_written_only_under_the_local_cache_directory(self):
        """Found by content, not by filename: `role-context` also names the schema."""
        self.record()
        receipts = []
        for path in self.root.rglob("*.json"):
            if not path.is_file():
                continue
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(document, dict) and "session_id" in document:
                receipts.append(path)
        self.assertTrue(receipts, "expected the recorded receipt to be found")
        for path in receipts:
            self.assertEqual(
                path.relative_to(self.root).parts[:2], (".local", "role-context")
            )

    def test_the_local_cache_directory_is_git_ignored(self):
        ignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".local/", [line.strip() for line in ignore])


class TestPathSetIsDeterministic(RoleContextCase):
    def test_the_set_is_sorted_and_duplicate_free(self):
        paths = self.verify()["stable_authority_paths"]
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(len(paths), len(set(paths)))

    def test_two_patterns_resolving_one_file_is_an_error(self):
        """ROLE_CONTEXT_LOADING 1.0: a duplicate resolved path fails closed.

        Collapsing it would make the resolved set depend on which pattern the
        manifest happens to list first, and the contract requires that set to be
        deterministic for a role and scope.
        """
        manifest = json.loads(json.dumps(self.MANIFEST))
        manifest["common_patterns"] = [
            "AGENTS.md",
            "contracts/*.md",
            "contracts/WORK_QUEUES.md",
        ]
        self.write_manifest(manifest)
        with self.assertRaises(role_context.ContextError) as caught:
            self.verify()
        self.assertIn("declares that authority twice", str(caught.exception))

    def test_the_live_manifest_has_no_overlapping_patterns(self):
        """The rule above is only safe if governance already conforms to it."""
        manifest = role_context.load_manifest(REPO_ROOT)
        for role in role_context.ROLES:
            for book in ("phb", "dmg", "ua", None):
                with self.subTest(role=role, book=book):
                    role_context.resolve_paths(REPO_ROOT, manifest, role, "adnd1e", book)

    def test_the_set_is_stable_across_calls(self):
        self.assertEqual(
            self.verify()["stable_authority_paths"],
            self.verify()["stable_authority_paths"],
        )

    def test_a_book_scoped_pattern_is_skipped_without_a_book(self):
        """An unfilled placeholder is absence, never a literal directory name."""
        paths = role_context.resolve_paths(
            self.root, self.MANIFEST, "builder", "adnd1e", None
        )
        self.assertFalse([p for p in paths if "{book}" in p])
        self.assertNotIn("schemas/adnd1e/books/phb/source_metadata.schema.json", paths)

    def test_a_book_scoped_pattern_resolves_with_a_book(self):
        paths = role_context.resolve_paths(
            self.root, self.MANIFEST, "builder", "adnd1e", "phb"
        )
        self.assertIn("schemas/adnd1e/books/phb/source_metadata.schema.json", paths)


class TestTheLiveManifest(unittest.TestCase):
    """DEC-2026-0040 acceptance test 1, against the repository as it stands."""

    def manifest(self):
        return role_context.load_manifest(REPO_ROOT)

    def test_the_manifest_validates_against_its_schema(self):
        from jsonschema import Draft202012Validator

        schema = json.loads(
            (REPO_ROOT / "schemas" / "common" / "role-context-manifest.schema.json").read_text(
                encoding="utf-8"
            )
        )
        errors = sorted(
            Draft202012Validator(schema).iter_errors(self.manifest()),
            key=lambda e: list(e.path),
        )
        self.assertEqual([f"{list(e.path)}: {e.message}" for e in errors], [])

    def test_every_role_is_declared_exactly_once(self):
        roles = self.manifest()["roles"]
        self.assertEqual(sorted(roles), sorted(role_context.ROLES))

    def test_every_role_resolves_a_deterministic_set(self):
        manifest = self.manifest()
        for role in role_context.ROLES:
            with self.subTest(role=role):
                first = role_context.resolve_paths(REPO_ROOT, manifest, role, "adnd1e", "phb")
                second = role_context.resolve_paths(REPO_ROOT, manifest, role, "adnd1e", "phb")
                self.assertEqual(first, second)
                self.assertEqual(first, sorted(first))
                self.assertEqual(len(first), len(set(first)))
                self.assertTrue(first)

    def test_every_resolved_path_is_a_file_inside_the_repository(self):
        manifest = self.manifest()
        for role in role_context.ROLES:
            for relative in role_context.resolve_paths(
                REPO_ROOT, manifest, role, "adnd1e", "phb"
            ):
                self.assertTrue((REPO_ROOT / relative).is_file(), relative)
                self.assertFalse(relative.startswith(".."), relative)

    def test_each_role_gets_its_own_instructions_and_no_others(self):
        manifest = self.manifest()
        for role in role_context.ROLES:
            with self.subTest(role=role):
                resolved = role_context.resolve_paths(
                    REPO_ROOT, manifest, role, "adnd1e", "phb"
                )
                others = [
                    f"agents/{other}/INSTRUCTIONS.md"
                    for other in role_context.ROLES
                    if other != role
                ]
                self.assertIn(f"agents/{role}/INSTRUCTIONS.md", resolved)
                for other in others:
                    self.assertNotIn(other, resolved)


class TestCli(RoleContextCase):
    def run_cli(self, *args):
        return role_context.main([*args, "--root", str(self.root)])

    def test_a_cold_verify_exits_one_and_a_hit_exits_zero(self):
        common = ("--role", "builder", "--ruleset", "adnd1e", "--book", "phb",
                  "--session-id", self.SESSION, "--json")
        self.assertEqual(self.run_cli("verify", *common), 1)
        self.assertEqual(self.run_cli("record", *common), 0)
        self.assertEqual(self.run_cli("verify", *common), 0)

    def test_a_verification_error_exits_two(self):
        (self.root / "contracts" / "ROLE_CONTEXT_MANIFEST.yaml").unlink()
        self.assertEqual(
            self.run_cli("verify", "--role", "builder", "--ruleset", "adnd1e",
                         "--session-id", self.SESSION),
            2,
        )

    def test_a_non_repository_root_exits_two(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(
                role_context.main(
                    ["verify", "--root", empty, "--role", "builder",
                     "--ruleset", "adnd1e", "--session-id", self.SESSION]
                ),
                2,
            )

    def test_an_unknown_role_is_rejected_by_the_parser(self):
        with self.assertRaises(SystemExit):
            self.run_cli("verify", "--role", "steward", "--ruleset", "adnd1e",
                         "--session-id", self.SESSION)


if __name__ == "__main__":
    unittest.main()
