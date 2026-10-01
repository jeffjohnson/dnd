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

    def test_an_unknown_role_is_rejected(self):
        """Exit 2, as before. DEC-2026-0082 moved the check off argparse
        `choices` so a retired role can be told what retired it; an unknown
        role still gets the plain unrecognized-role refusal."""
        self.assertEqual(
            self.run_cli("verify", "--role", "steward", "--ruleset", "adnd1e",
                         "--session-id", self.SESSION),
            2,
        )



# ---------------------------------------------------------------------------
# DEC-2026-0082: five active roles.
#
# DEC-2026-0081 had added a sixth, and the tests that asserted it were deleted
# rather than adjusted -- they tested a role governance has withdrawn. What
# follows keeps the manifest language readable for history while proving the
# role itself is unreachable, and pins the five roles' behaviour unchanged.
# ---------------------------------------------------------------------------


class TestManifestVersionsAndInheritance(RoleContextCase):
    """DEC-2026-0081 acceptance test 1: which manifests this verifier accepts."""

    def manifest_with(self, **changes):
        document = json.loads(json.dumps(self.MANIFEST))
        document.update(changes)
        return document

    def refuses(self, document, fragment):
        self.write_manifest(document)
        with self.assertRaises(role_context.ContextError) as caught:
            role_context.load_manifest(self.root)
        self.assertIn(fragment, str(caught.exception))

    def test_a_legacy_five_role_manifest_is_still_accepted(self):
        """1.0 predates the Dispatcher and stays valid for the roles it declares."""
        self.assertEqual(self.verify()["status"], "reload_required")
        self.assertEqual(self.warm()["status"], "cache_hit")

    def test_a_legacy_manifest_may_not_declare_the_retired_role(self):
        """1.0 predates it, so finding it there is malformed, not history."""
        document = self.manifest_with()
        document["roles"]["dispatcher"] = {
            "inherit_common_patterns": False,
            "stable_patterns": ["README.md"],
        }
        self.refuses(document, "retired by DEC-2026-0082")

    def test_a_retired_role_request_names_the_decision_that_retired_it(self):
        """"Unrecognized" would read like a typo and hide the ruling."""
        with self.assertRaises(role_context.ContextError) as caught:
            role_context.verify(self.root, "dispatcher", "adnd1e", None, self.SESSION)
        message = str(caught.exception)
        self.assertIn("retired by DEC-2026-0082", message)
        self.assertNotIn("unrecognized role", message)

    def test_an_unsupported_schema_version_fails_closed(self):
        for version in ("1.2", "2.0", 1.0, None, ""):
            with self.subTest(version=version):
                self.refuses(
                    self.manifest_with(schema_version=version), "this verifier implements"
                )

    def test_an_unsupported_cache_format_version_fails_closed(self):
        for value in (2, 0, "1", None):
            with self.subTest(value=value):
                self.refuses(
                    self.manifest_with(cache_format_version=value),
                    "cache_format_version",
                )

    def test_version_1_1_still_parses_as_history(self):
        """DEC-2026-0082 keeps the language readable; it grants nothing."""
        document = self.manifest_with(schema_version="1.1")
        document["roles"]["dispatcher"] = {
            "inherit_common_patterns": False,
            "stable_patterns": ["README.md"],
        }
        self.write_manifest(document)
        manifest = role_context.load_manifest(self.root)
        self.assertIn("dispatcher", manifest["roles"])
        # Parsed, but not runnable: no set is resolved for it.
        with self.assertRaises(role_context.ContextError) as caught:
            role_context.resolve_paths(self.root, manifest, "dispatcher", "adnd1e", None)
        self.assertIn("retired by DEC-2026-0082", str(caught.exception))

    def test_version_1_1_does_not_require_the_retired_role(self):
        """A 1.1 manifest someone already trimmed still loads."""
        self.write_manifest(self.manifest_with(schema_version="1.1"))
        self.assertEqual(self.verify()["status"], "reload_required")

    def test_a_malformed_historical_entry_is_still_an_error(self):
        """A manifest is well formed or it is not; one key is not exempt."""
        document = self.manifest_with(schema_version="1.1")
        document["roles"]["dispatcher"] = {"stable_patterns": ["README.md"]}
        self.refuses(document, "must still declare inherit_common_patterns: false")

    def test_a_missing_worker_role_fails_closed(self):
        document = self.manifest_with()
        del document["roles"]["reviewer"]
        self.refuses(document, "omits role(s): reviewer")

    def test_an_unknown_role_fails_closed(self):
        document = self.manifest_with()
        document["roles"]["steward"] = {"stable_patterns": ["README.md"]}
        self.refuses(document, "unknown role(s): steward")

    def test_a_worker_may_not_opt_out_of_the_common_set(self):
        """The opt-out exists for the Dispatcher; it cannot subtract worker authority."""
        document = self.manifest_with()
        document["roles"]["builder"]["inherit_common_patterns"] = False
        self.refuses(document, "every active role inherits the common set")

    def test_a_worker_may_declare_the_default_explicitly(self):
        document = self.manifest_with()
        document["roles"]["builder"]["inherit_common_patterns"] = True
        self.write_manifest(document)
        self.assertIn("AGENTS.md", self.verify()["stable_authority_paths"])

    def test_a_malformed_inheritance_value_fails_closed(self):
        """`1` is not `True` here. A truthy near-miss must not grant the set."""
        for value in (None, "false", "true", 0, 1, [], {}):
            with self.subTest(value=value):
                document = self.manifest_with()
                document["roles"]["builder"]["inherit_common_patterns"] = value
                self.refuses(document, "it must be a boolean")

    def test_a_missing_worker_role_fails_closed_at_either_language(self):
        for version in ("1.0", "1.1"):
            with self.subTest(schema_version=version):
                document = self.manifest_with(schema_version=version)
                del document["roles"]["analyst"]
                self.refuses(document, "omits role(s): analyst")

    def test_a_malformed_role_entry_fails_closed(self):
        document = self.manifest_with()
        document["roles"]["builder"] = ["agents/builder/INSTRUCTIONS.md"]
        self.refuses(document, "is not a mapping")


class TestTheRetiredRoleIsGone(unittest.TestCase):
    """DEC-2026-0082 acceptance test 2, against the repository as it stands.

    The previous revision of this file asserted an active sixth role, and those
    assertions are deleted rather than adjusted: they tested a role governance
    has withdrawn. What replaces them is the opposite claim -- the role is
    absent from the live manifest, its files are gone, and every entry point
    refuses it without writing anything.
    """

    RETIRED = "dispatcher"

    def test_the_live_manifest_declares_exactly_the_five_active_roles(self):
        manifest = role_context.load_manifest(REPO_ROOT)
        self.assertEqual(sorted(manifest["roles"]), sorted(role_context.ROLES))
        self.assertEqual(sorted(role_context.ROLES), sorted(role_context.WORKER_ROLES))
        self.assertNotIn(self.RETIRED, manifest["roles"])
        self.assertEqual(manifest["schema_version"], "1.0")
        self.assertEqual(manifest["cache_format_version"], 1)

    def test_the_retired_role_definition_files_are_absent(self):
        """Verified by absence, never pinned as an existing file."""
        for relative in ("agents/dispatcher/INSTRUCTIONS.md", "contracts/DISPATCHER.md"):
            with self.subTest(path=relative):
                self.assertFalse((REPO_ROOT / relative).exists(), relative)

    def test_every_entry_point_refuses_it_and_writes_nothing(self):
        manifest = role_context.load_manifest(REPO_ROOT)
        session = "unit-test-not-an-actor"
        calls = {
            "validate_scope": lambda: role_context.validate_scope(
                self.RETIRED, "adnd1e", None
            ),
            "resolve_paths": lambda: role_context.resolve_paths(
                REPO_ROOT, manifest, self.RETIRED, "adnd1e", None
            ),
            "receipt_path": lambda: role_context.receipt_path(
                REPO_ROOT, self.RETIRED, "adnd1e", None, session
            ),
            "build_receipt": lambda: role_context.build_receipt(
                REPO_ROOT, self.RETIRED, "adnd1e", None, session
            ),
            "verify": lambda: role_context.verify(
                REPO_ROOT, self.RETIRED, "adnd1e", None, session
            ),
            "record": lambda: role_context.record(
                REPO_ROOT, self.RETIRED, "adnd1e", None, session
            ),
        }
        for name, call in calls.items():
            with self.subTest(entry_point=name):
                with self.assertRaises(role_context.ContextError) as caught:
                    call()
                self.assertIn("retired by DEC-2026-0082", str(caught.exception))

    def test_the_retirement_is_read_from_a_table_not_a_literal(self):
        """So a future retirement names its own Decision instead of this one."""
        self.assertEqual(role_context.RETIRED_ROLES[self.RETIRED], "DEC-2026-0082")
        self.assertFalse(set(role_context.RETIRED_ROLES) & set(role_context.ROLES))


class TestTheRetiredRoleCliIsRefused(RoleContextCase):
    """Acceptance test 2's command-line half: refused, with no receipt written."""

    def run_cli(self, *args):
        return role_context.main([*args, "--root", str(self.root)])

    def receipts(self):
        directory = self.root / ".local" / "role-context"
        return sorted(p.name for p in directory.glob("*.json")) if directory.is_dir() else []

    def test_a_retired_role_exits_2_and_writes_no_receipt(self):
        for command in ("verify", "record"):
            with self.subTest(command=command):
                code = self.run_cli(
                    command, "--role", "dispatcher",
                    "--ruleset", "adnd1e", "--session-id", self.SESSION,
                )
                self.assertEqual(code, 2)
                self.assertEqual(self.receipts(), [])

    def test_the_refusal_distinguishes_retired_from_unknown(self):
        import io
        from contextlib import redirect_stderr

        messages = {}
        for role in ("dispatcher", "bogus"):
            buffer = io.StringIO()
            with redirect_stderr(buffer):
                self.run_cli(
                    "verify", "--role", role,
                    "--ruleset", "adnd1e", "--session-id", self.SESSION,
                )
            messages[role] = buffer.getvalue()
        self.assertIn("retired by DEC-2026-0082", messages["dispatcher"])
        self.assertIn("unrecognized role", messages["bogus"])
        self.assertNotIn("unrecognized role", messages["dispatcher"])

    def test_an_active_role_still_works_from_the_same_cli(self):
        self.assertEqual(
            self.run_cli(
                "verify", "--role", "builder", "--ruleset", "adnd1e",
                "--book", "phb", "--session-id", self.SESSION,
            ),
            1,
        )


class TestManifestUpgradeInvalidatesExistingReceipts(RoleContextCase):
    """Acceptance test 7: the 1.0 -> 1.1 upgrade, with receipt format still 1."""

    def test_a_worker_receipt_written_under_1_0_misses_after_the_upgrade(self):
        self.record()
        path = role_context.receipt_path(self.root, "builder", "adnd1e", "phb", self.SESSION)
        before = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(before["cache_format_version"], 1)

        upgraded = json.loads(json.dumps(self.MANIFEST))
        upgraded["schema_version"] = "1.1"
        upgraded["roles"]["dispatcher"] = {
            "inherit_common_patterns": False,
            "stable_patterns": ["README.md", "agents/dispatcher/INSTRUCTIONS.md"],
        }
        self.write_manifest(upgraded)
        self.write("schemas/common/role-context-manifest.schema.json", '{"upgraded": true}\n')

        result = self.verify()
        self.assertEqual(result["status"], "reload_required")
        self.assertTrue(
            any("manifest_checksum" in d for d in result["differences"]), result["differences"]
        )
        # The receipt encoding did not change, so this is ordinary hash
        # invalidation rather than a format migration.
        self.assertEqual(role_context.SUPPORTED_CACHE_FORMAT_VERSION, 1)
        after = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(after, before, "the stale receipt is left exactly as it was")


class TestWorkerBehaviourIsUnchanged(RoleContextCase):
    """Acceptance test 4: the five roles keep everything they had."""

    def run_cli(self, *args):
        return role_context.main([*args, "--root", str(self.root)])

    def test_each_worker_still_requires_a_ruleset(self):
        """argparse rejects the absent argument; the exit code is still 2."""
        for role in role_context.WORKER_ROLES:
            with self.subTest(role=role):
                with self.assertRaises(SystemExit) as caught:
                    self.run_cli("verify", "--role", role, "--session-id", self.SESSION)
                self.assertEqual(caught.exception.code, 2)

    def test_an_empty_ruleset_is_refused_rather_than_resolved(self):
        self.assertEqual(
            self.run_cli(
                "verify", "--role", "builder", "--ruleset", "", "--session-id", self.SESSION
            ),
            2,
        )

    def test_book_remains_optional(self):
        self.assertEqual(
            self.run_cli(
                "verify", "--role", "builder", "--ruleset", "adnd1e",
                "--session-id", self.SESSION,
            ),
            1,
        )

    def test_the_worker_scope_key_and_filename_formulas_are_unchanged(self):
        import hashlib

        for role in role_context.WORKER_ROLES:
            for book in ("phb", None):
                with self.subTest(role=role, book=book):
                    material = "\0".join(
                        [
                            str(self.root.resolve()).replace("\\", "/"),
                            role,
                            "adnd1e",
                            book or "",
                            self.SESSION,
                        ]
                    )
                    key = hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
                    self.assertEqual(
                        role_context._scope_key(
                            self.root, role, "adnd1e", book, self.SESSION
                        ),
                        key,
                    )
                    self.assertEqual(
                        role_context.receipt_path(
                            self.root, role, "adnd1e", book, self.SESSION
                        ).name,
                        f"{role}-adnd1e-{book or 'no-book'}-{key}.json",
                    )

    def test_worker_receipt_fields_are_unchanged(self):
        self.record()
        stored = json.loads(
            role_context.receipt_path(
                self.root, "builder", "adnd1e", "phb", self.SESSION
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(stored["scope"], {"ruleset_id": "adnd1e", "book_id": "phb"})
        self.assertEqual(stored["cache_format_version"], 1)
        self.assertEqual(stored["role"], "builder")


class TestBothRegisteredRulesetsResolve(unittest.TestCase):
    """Acceptance test 4's live half: AD&D 1e and Basic D&D worker scopes."""

    SCOPES = (("adnd1e", "phb"), ("basicdnd", "rc"))

    def test_every_worker_resolves_a_stable_set_in_each_registered_ruleset(self):
        manifest = role_context.load_manifest(REPO_ROOT)
        for ruleset, book in self.SCOPES:
            for role in role_context.WORKER_ROLES:
                with self.subTest(ruleset=ruleset, role=role):
                    resolved = role_context.resolve_paths(
                        REPO_ROOT, manifest, role, ruleset, book
                    )
                    self.assertTrue(resolved)
                    self.assertEqual(resolved, sorted(resolved))
                    self.assertIn("AGENTS.md", resolved)
                    self.assertIn(f"agents/{role}/INSTRUCTIONS.md", resolved)
                    self.assertTrue(
                        any(r.startswith(f"rulesets/{ruleset}/") for r in resolved),
                        "a worker set is ruleset-scoped",
                    )

    def test_a_worker_set_is_different_per_ruleset(self):
        manifest = role_context.load_manifest(REPO_ROOT)
        first = role_context.resolve_paths(REPO_ROOT, manifest, "builder", "adnd1e", "phb")
        second = role_context.resolve_paths(REPO_ROOT, manifest, "builder", "basicdnd", "rc")
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
