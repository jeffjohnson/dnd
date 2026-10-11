"""Ruleset-local generated authority, including all six observed regressions."""
from dataclasses import replace
import json
from pathlib import Path
import unittest

import _bootstrap
from _bootstrap import REPO_ROOT
from adnd1e_builder.compiler import Compiler
from adnd1e_builder.duplicates import CanonicalEdges
from adnd1e_builder.emit import gup_document, validation_report
from adnd1e_builder.registry import NodeRegistry
from adnd1e_builder.vocab import RulesetVocabulary


class RegistrationAuthorityCase(unittest.TestCase):
    def compiler(self, ruleset="shadowdark"):
        vocabulary = RulesetVocabulary.load(REPO_ROOT, ruleset)
        return Compiler(NodeRegistry(Path("fixture.csv")), CanonicalEdges(Path("fixture.csv")), vocabulary=vocabulary)

    def test_adnd_authority_bytes_are_unchanged(self):
        self.assertEqual(self.compiler("adnd1e").registration_basis,
                         "DEC-2026-0003: approved prefix and kind, valid ID, no duplicate")

    def test_shadowdark_uses_the_loaded_version(self):
        compiler = self.compiler()
        compiler.vocabulary = replace(compiler.vocabulary, constitution_version="9.8")
        self.assertEqual(compiler.registration_authority, "Constitution 9.8 section 2")

    def test_another_ruleset_does_not_inherit_adnd_authority(self):
        compiler = self.compiler("basicdnd")
        self.assertNotIn("DEC-2026-0003", compiler.registration_basis)
        self.assertIn("rulesets/basicdnd/governance/constitution.md", compiler.registration_basis)

    def test_six_observed_packets_have_no_generated_foreign_authority(self):
        packets = (
            "195-195-monster-family-angels", "196-198-monsters-animated-armor-to-bat-giant",
            "198-200-monsters-bat-swarm-to-cave-brute", "200-203-monsters-cave-creeper-to-cultist",
            "203-203-monsters-cyclops-to-deep-one", "204-205-monster-family-demons",
        )
        proposals = 0
        for packet in packets:
            with self.subTest(packet=packet):
                path = REPO_ROOT / f"books/shadowdark/sd/artifacts/gur/GUR-PKT-SD-{packet}-r01.yaml"
                compiler = self.compiler()
                result = compiler.compile(path)
                for node in result.node_additions:
                    if not node["architect_required"]:
                        proposals += 1
                        self.assertEqual(node["routing_basis"], compiler.registration_basis)
                rendered = json.dumps([gup_document(result, {}), validation_report(result, {})])
                self.assertNotIn("DEC-2026-0003", rendered)
        self.assertEqual(proposals, 48)


if __name__ == "__main__":
    unittest.main()
