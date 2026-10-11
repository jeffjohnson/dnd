import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from artifact_io import Output, PublicationError, contained, digest, publish


class PublicationCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.schema = self.root / "schema.json"
        self.schema.write_text('{"type":"object","required":["id"]}', encoding="utf-8")

    def output(self, name="artifact.yaml", content=b"id: example\n"):
        return Output(self.root / name, content, (self.schema,))

    def test_all_bytes_are_validated_before_any_write(self):
        with self.assertRaises(PublicationError):
            publish(self.root, [self.output(), self.output("bad.yaml", b"bad: [")])
        self.assertFalse((self.root / "artifact.yaml").exists())

    def test_existing_companion_blocks_every_output(self):
        companion = self.root / "artifact.pending.csv"
        companion.write_bytes(b"old")
        with self.assertRaises(PublicationError):
            publish(self.root, [self.output()], companions=[companion])
        self.assertEqual(companion.read_bytes(), b"old")
        self.assertFalse((self.root / "artifact.yaml").exists())

    def test_exact_bytes_and_hash_are_published(self):
        result = publish(self.root, [self.output()])
        self.assertEqual(result, [{"path": "artifact.yaml", "checksum": digest(b"id: example\n")}])
        self.assertEqual((self.root / "artifact.yaml").read_bytes(), b"id: example\n")

    def test_changed_input_refuses_writes(self):
        source = self.root / "source.md"
        source.write_bytes(b"new")
        with self.assertRaises(PublicationError):
            publish(self.root, [self.output()], expected_inputs={"source.md": digest(b"old")})
        self.assertFalse((self.root / "artifact.yaml").exists())

    def test_path_escape_and_duplicate_outputs_are_refused(self):
        with self.assertRaises(PublicationError):
            contained(self.root, "../outside.yaml")
        with self.assertRaises(PublicationError):
            publish(self.root, [self.output(), self.output()])

    def test_write_failure_cleans_only_owned_unchanged_outputs(self):
        second = self.root / "second.yaml"
        original = Path.open
        def fail(path, *args, **kwargs):
            if path == second and args and args[0] == "xb":
                raise OSError("simulated failure")
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", fail), self.assertRaises(OSError):
            publish(self.root, [self.output(), self.output("second.yaml")])
        self.assertFalse((self.root / "artifact.yaml").exists())
        self.assertTrue(self.schema.exists())


if __name__ == "__main__":
    unittest.main()
