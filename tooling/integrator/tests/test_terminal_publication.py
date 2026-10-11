"""A record failure is a transaction failure, including first integration."""
from pathlib import Path
from unittest import mock

from test_genesis import GenesisCase, GENESIS_RULESET
from adnd1e_integrator.integrate import integrate
from adnd1e_integrator.records import write_records
from adnd1e_integrator.bundles import discover


class TerminalPublicationCase(GenesisCase):
    def setUp(self):
        super().setUp()
        self.bundles = discover(self.root, GENESIS_RULESET, "sd")[0]
        for bundle in self.bundles:
            bundle.packet_id = "PKT-SD-TEST-genesis"

    def test_record_failure_rolls_back_canonical_and_registry(self):
        before = self.paths.registry.read_bytes()
        def fail(batch):
            self.assertTrue(self.paths.edges.exists())
            raise OSError("record write failed")
        with self.assertRaises(OSError):
            integrate(self.root, GENESIS_RULESET, self.bundles, record_writer=fail)
        self.assertFalse(self.paths.edges.exists())
        self.assertEqual(self.paths.registry.read_bytes(), before)

    def test_success_requires_complete_terminal_records(self):
        written = {}
        def complete(batch):
            written.update(write_records(batch, self.root, GENESIS_RULESET, "1.8"))
        batch = integrate(self.root, GENESIS_RULESET, self.bundles, record_writer=complete)
        self.assertTrue(written["manifest"].is_file())
        self.assertTrue(any(key.startswith("integrated:") for key in written))
        with self.assertRaises(ValueError):
            write_records(batch, self.root, GENESIS_RULESET, "1.8")

    def test_dry_run_never_publishes(self):
        writer = mock.Mock()
        integrate(self.root, GENESIS_RULESET, self.bundles, dry_run=True, record_writer=writer)
        writer.assert_not_called()
        self.assertFalse(self.paths.edges.exists())

    def test_late_record_write_failure_removes_new_records_and_restores_absence(self):
        before = self.paths.registry.read_bytes()
        original_open = Path.open
        def fail(path, *args, **kwargs):
            if str(path).endswith(".diff.md") and args and args[0] == "xb":
                raise OSError("late record failure")
            return original_open(path, *args, **kwargs)
        def complete(batch):
            write_records(batch, self.root, GENESIS_RULESET, "1.8")
        with mock.patch.object(Path, "open", fail), self.assertRaisesRegex(OSError, "late record failure"):
            integrate(self.root, GENESIS_RULESET, self.bundles, record_writer=complete)
        self.assertEqual(self.paths.registry.read_bytes(), before)
        self.assertFalse(self.paths.edges.exists())
        self.assertEqual(list((self.root / "rulesets/shadowdark/manifests").glob("INT-*")), [])
        self.assertEqual(list((self.root / "rulesets/shadowdark/reports").glob("INT-*")), [])
