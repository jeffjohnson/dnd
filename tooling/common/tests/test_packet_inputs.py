import copy
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tooling/analyst"))
from packet_inputs import packet_inputs, plan_claim
from artifact_io import PublicationError, digest, load_mapping, publish, yaml_bytes


class PacketInputsCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "schemas", self.root / "schemas")
        source_registry = self.root / "rulesets/shadowdark/registries/sources.yaml"
        source_registry.parent.mkdir(parents=True)
        shutil.copy2(ROOT / source_registry.relative_to(self.root), source_registry)
        self.incoming = self.root / "books/shadowdark/sd/packets/incoming/test.md"
        self.incoming.parent.mkdir(parents=True)
        self.incoming.write_bytes(b"# Title {#p1}\r\n\r\nFirst text. Next {#p2} page text.\r\n")
        original = ROOT / "books/shadowdark/sd/packets/claimed/PKT-SD-204-205-monster-family-demons/packet.yaml"
        self.manifest = load_mapping(original)
        self.manifest.update(id="PKT-SD-001-002-fixture", packet_id="PKT-SD-001-002-fixture",
                             original_filename="test.md", source_file="source.md", status="claimed",
                             source_checksum=digest(self.incoming.read_bytes().replace(b"\r\n", b"\n")),
                             source_checksum_basis="lf_normalized")
        self.staged = self.root / "claim.yaml"
        self.write_manifest()

    def write_manifest(self):
        self.staged.write_bytes(yaml_bytes(self.manifest))

    def test_claim_preserves_source_bytes_and_resolves_pandoc_pages(self):
        outputs, pins = plan_claim(self.root, self.incoming, self.staged, set())
        self.assertFalse(outputs[0].path.exists())
        publish(self.root, outputs, expected_inputs=pins)
        packet = packet_inputs(self.root, outputs[0].path)
        self.assertEqual(packet["pages"], [1, 2])
        self.assertEqual(outputs[1].path.read_bytes(), self.incoming.read_bytes())
        self.assertEqual(packet["checksum"], digest(self.incoming.read_bytes()))

    def test_active_packet_refuses_claim(self):
        with self.assertRaisesRegex(PublicationError, "another packet"):
            plan_claim(self.root, self.incoming, self.staged, {"PKT-existing"})

    def test_stale_source_refuses_claim(self):
        self.incoming.write_bytes(b"changed")
        with self.assertRaisesRegex(PublicationError, "actual incoming"):
            plan_claim(self.root, self.incoming, self.staged, set())

    def test_second_claim_of_same_input_refuses(self):
        outputs, pins = plan_claim(self.root, self.incoming, self.staged, set())
        publish(self.root, outputs, expected_inputs=pins)
        self.manifest.update(id="PKT-SD-001-002-another", packet_id="PKT-SD-001-002-another")
        self.write_manifest()
        with self.assertRaisesRegex(PublicationError, "already claimed"):
            plan_claim(self.root, self.incoming, self.staged, set())

    def test_unregistered_source_refuses(self):
        self.manifest["source_id"] = "made-up"
        self.write_manifest()
        with self.assertRaisesRegex(PublicationError, "not registered"):
            plan_claim(self.root, self.incoming, self.staged, set())

    def test_wrong_book_refuses(self):
        self.manifest["book_id"] = "cs1"
        self.manifest["source_id"] = "cs1-steward-intake"
        self.write_manifest()
        with self.assertRaisesRegex(PublicationError, "outside its incoming book"):
            plan_claim(self.root, self.incoming, self.staged, set())

    def test_rc_paused(self):
        self.manifest.update(ruleset_id="basicdnd", book_id="rc")
        self.write_manifest()
        with self.assertRaisesRegex(PublicationError, "RC is owner-paused"):
            plan_claim(self.root, self.incoming, self.staged, set())

    def test_marker_free_source_refuses(self):
        self.incoming.write_text("unpaged prose", encoding="utf-8")
        with self.assertRaisesRegex(PublicationError, "resolvable pages"):
            packet_inputs(self.root, self.incoming)

    def test_claim_validates_pages_before_creating_claimed_paths(self):
        self.incoming.write_bytes(b"uncitable source")
        self.manifest["source_checksum"] = digest(self.incoming.read_bytes())
        self.write_manifest()
        with self.assertRaisesRegex(PublicationError, "resolvable pages"):
            plan_claim(self.root, self.incoming, self.staged, set())
        self.assertFalse((self.root / "books/shadowdark/sd/packets/claimed").exists())

    def test_supplied_slices_are_returned_without_truncation(self):
        content = "[" + ",".join(str(i) for i in range(2000)) + "]"
        (self.incoming.parent / "local_neighborhood.json").write_text(content, encoding="utf-8")
        packet = packet_inputs(self.root, self.incoming)
        self.assertEqual(packet["supplied_inputs"][0]["content"], content)


if __name__ == "__main__":
    unittest.main()
