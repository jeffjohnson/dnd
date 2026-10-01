"""Additional independent r02 relay probes; no real Herdr prompt is possible.

Run: python tooling/reviewer/tests/test_dec0082_r02_acceptance.py
The native-call probe uses Python solely as a local JSON-emitting executable.
Other probes use the Builder's fake endpoint in disposable fixture roots.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tooling/common/tests"))
from test_herdr_handoff import RelayCase, POWERSHELL, RELAY, OK, INVALID


class R02Acceptance(RelayCase):
    def run_relay(self, request_path=None, timeout_ms=4000, *flags):
        # Keep execution independent of later Builder test-helper changes:
        # in particular, never synthesize queued state before ExecuteRequest.
        request_path = request_path or self.request()
        result = subprocess.run([
            POWERSHELL, "-NoLogo", "-NonInteractive", "-NoProfile", "-File", str(RELAY),
            "-RequestPath", str(request_path), "-TimeoutMs", str(timeout_ms), *flags
        ], capture_output=True, text=True, cwd=self.root, timeout=12,
            env={**os.environ, "FAKE_HERDR_SCENARIO": str(self.scenario_path),
                 "FAKE_HERDR_LOG": str(self.log), "HERDR_BIN_PATH": str(self.fake),
                 "HERDR_SOCKET_PATH": "reviewer-fake-inherited-socket"})
        try:
            payload = json.loads(result.stdout)
        except ValueError:
            payload = {"unparsed": result.stdout}
        return result.returncode, payload, result.stderr

    def test_native_executable_endpoint_is_supported(self):
        # Load only the actual two helper definitions, not the relay entrypoint.
        # Native Python emits JSON without contacting any server.
        harness = self.write("native-probe.ps1", r'''
param([string]$Relay, [string]$Native)
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Relay, [ref]$tokens, [ref]$errors)
foreach ($name in @('Get-RemainingMs', 'Invoke-Herdr')) {
    $definition = $ast.FindAll({param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst]
    }, $false) | Where-Object Name -eq $name
    Invoke-Expression $definition.Extent.Text
}
$script:BudgetMs = 4000
$script:DeadlineStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$response = Invoke-Herdr -HerdrBin $Native -Arguments @('-c', 'print("{\"result\":{\"status\":\"done\"}}")')
$response | ConvertTo-Json -Depth 10 -Compress
''')
        result = subprocess.run([POWERSHELL, "-NoProfile", "-File", str(harness),
                                 "-Relay", str(RELAY), "-Native", sys.executable],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["result"]["status"], "done")

    def test_null_evidence_collections_are_rejected(self):
        code, payload, _ = self.run_relay(self.request(inputs=None, prerequisites=None,
                                                      ordered_next_steps=None),
                                          4000, "-ValidateOnly")
        self.assertEqual(code, INVALID, payload)

    def test_endpoint_socket_identity_mismatch_is_rejected(self):
        # Binary identity alone does not identify a Herdr server.
        code, payload, _ = self.run_relay(self.request(endpoint={
            "herdr_bin": str(self.fake), "socket_path": "not-the-inherited-socket"
        }), 4000, "-ValidateOnly")
        self.assertEqual(code, INVALID, payload)

    def test_unscheduled_execution_is_rejected(self):
        # F4 expressly requires an unconsumed scheduled request.
        code, payload, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(self.prompts_sent(), [], payload)
        self.assertEqual(code, INVALID, payload)

    def test_blocked_sender_fails_closed_instead_of_waiting_it_out(self):
        path = self.request()
        self.write(".local/herdr/requests/req-0001.state.json", json.dumps({
            "request_id": "req-0001", "state": "queued", "request_path": str(path),
            "request_checksum": "sha256:" + self.digest("request.json")
        }))
        self.set_scenario(self.frame(sender="blocked"), self.frame(sender="idle"))
        self.run_relay(path, 4000, "-ExecuteRequest")
        self.assertEqual(self.prompts_sent(), [], "blocked sender was polled until delivery became possible")

    def test_link_to_external_file_is_outside_repository(self):
        with tempfile.TemporaryDirectory() as other:
            target = Path(other) / "external.yaml"
            target.write_text("id: external\n", encoding="utf-8")
            # A hard link is avoided: a directory junction has a resolvable
            # external target and can be created without elevation on Windows.
            link = self.root / "junction"
            harness = self.write("junction-probe.ps1", "param([string]$Link, [string]$Target)\n"
                                 "New-Item -ItemType Junction -Path $Link -Target $Target | Out-Null\n")
            create = subprocess.run([POWERSHELL, "-NoProfile", "-File", str(harness),
                                     "-Link", str(link), "-Target", other],
                                    capture_output=True, text=True)
            self.assertEqual(create.returncode, 0, create.stderr)
            try:
                import hashlib
                checksum = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
                code, payload, _ = self.run_relay(self.request(inputs=[{
                    "id": "external", "path": "junction/external.yaml", "checksum": checksum
                }]), 4000, "-ValidateOnly")
                self.assertEqual(code, INVALID, payload)
            finally:
                # Remove only the junction itself, never its external target.
                os.rmdir(link)

    def test_finishing_recipient_can_stage_deferred_continuation(self):
        self.write(".local/herdr/requests/parent.state.json", json.dumps({
            "request_id": "parent", "state": "submitting", "recipient_pane": self.SENDER_PANE
        }))
        self.write(".local/herdr/handoff.lock", json.dumps({"request_id": "parent", "pid": 0}))
        # No real endpoint can be used even if staging launches a background relay.
        self.set_scenario(self.frame(sender="working"))
        code, payload, _ = self.run_relay(self.request(), 1000)
        try:
            self.assertEqual(code, OK, payload)
            self.assertEqual(payload["status"], "queued")
            self.assertEqual(self.prompts_sent(), [])
        finally:
            if code == OK:
                self.wait_for_relay(seconds=3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
