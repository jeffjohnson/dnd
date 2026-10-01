"""Independent DEC-2026-0082 acceptance probes; fake endpoints and temp roots only.

Run from the repository root:
  python tooling/reviewer/tests/test_dec0082_relay_acceptance.py
These assert required safety properties, not the current implementation's behavior.
No production herdr endpoint or repository artifact is mutated.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tooling/common/tests"))
from test_herdr_handoff import RelayCase, agent, INVALID, UNCERTAIN, POWERSHELL, RELAY


class IndependentRelayAcceptance(RelayCase):
    def start_slow_prompt(self, request):
        # ExecuteRequest models the deferred phase.  Reserve first to model the
        # scheduler, whose queued record is now an explicit F4 prerequisite.
        self.ensure_reserved(request)
        text = self.fake.read_text(encoding="utf-8")
        marker = "if ($CliArgs[0] -eq 'agent' -and $CliArgs[1] -eq 'prompt') {"
        self.fake.write_text(text.replace(marker, marker + "\nStart-Sleep -Milliseconds 3000"),
                             encoding="utf-8")
        process = subprocess.Popen([
            POWERSHELL, "-NoLogo", "-NonInteractive", "-NoProfile", "-File", str(RELAY),
            "-RequestPath", str(request), "-TimeoutMs", "8000", "-ExecuteRequest"
        ], cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={**os.environ, "FAKE_HERDR_SCENARIO": str(self.scenario_path),
                 "FAKE_HERDR_LOG": str(self.log), "HERDR_BIN_PATH": str(self.fake)})
        deadline = time.monotonic() + 5
        while not self.prompts_sent() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(self.prompts_sent(), "first fake prompt did not begin")
        return process

    def test_two_competing_relays_do_not_prompt_concurrently(self):
        first = self.start_slow_prompt(self.request())
        try:
            self.run_relay(self.request(request_id="competitor"), 4000, "-ExecuteRequest")
            self.assertEqual(len(self.prompts_sent()), 1)
        finally:
            first.communicate(timeout=10)

    def test_process_interruption_cannot_erase_possible_send(self):
        path = self.request()
        first = self.start_slow_prompt(path)
        first.terminate()
        first.communicate(timeout=10)
        self.assertEqual(self.state()["state"], "submitting")
        self.run_relay(path, 4000, "-ExecuteRequest")
        self.assertIn(self.state()["state"], ("submitting", "uncertain"),
                      "retry overwrote possible-delivery evidence with a terminal refusal")

    def test_incomplete_request_cannot_validate(self):
        document = json.loads(self.request().read_text(encoding="utf-8"))
        for key in ("endpoint", "scope", "inputs", "prerequisites", "ordered_next_steps"):
            del document[key]
        path = self.write("incomplete.json", json.dumps(document))
        code, payload, _ = self.run_relay(path, 4000, "-ValidateOnly")
        self.assertEqual(code, INVALID, payload)

    def test_unassigned_invalid_scope_cannot_validate(self):
        code, payload, _ = self.run_relay(
            self.request(scope={"ruleset_id": "../not-a-ruleset", "book_id": "missing"}),
            4000, "-ValidateOnly")
        self.assertEqual(code, INVALID, payload)

    def test_existing_prefix_sibling_is_outside_root(self):
        with tempfile.TemporaryDirectory(prefix=self.root.name + "-", dir=self.root.parent) as sibling:
            target = Path(sibling) / "outside.yaml"
            target.write_text("id: outside\n", encoding="utf-8")
            code, payload, _ = self.run_relay(self.request(inputs=[{
                "id": "outside", "path": "../" + Path(sibling).name + "/outside.yaml"
            }]), 4000, "-ValidateOnly")
            self.assertEqual(code, INVALID, payload)

    def test_changed_sender_identity_cannot_send(self):
        frame = self.frame()
        frame[0] = agent(self.SENDER_PANE, "analyst", "claude", "idle",
                         str(self.root), "replacement-session")
        self.set_scenario(frame)
        path = self.request(sender={"role": "builder", "name": "builder",
                                  "pane_id": self.SENDER_PANE, "session_id": "sess-sender"})
        self.run_relay(path, 4000, "-ExecuteRequest")
        self.assertEqual(self.prompts_sent(), [], "substituted sender authorized a prompt")

    def test_wrong_recipient_role_alias_cannot_send(self):
        frame = self.frame()
        frame[1]["name"] = "architect"  # Same provider; wrong named role.
        self.set_scenario(frame)
        self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(self.prompts_sent(), [], "reviewer assignment sent to architect alias")

    def test_duplicate_recipient_alias_cannot_send(self):
        duplicate = agent("w1:p8", "reviewer", "codex", "idle", str(self.root), "other-session")
        self.set_scenario(self.frame(extra=[duplicate]))
        self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(self.prompts_sent(), [], "ambiguous reviewer alias was accepted")

    def test_execute_phase_cannot_replay_same_request(self):
        path = self.request()
        self.run_relay(path, 4000, "-ExecuteRequest")
        self.run_relay(path, 4000, "-ExecuteRequest")
        self.assertEqual(len(self.prompts_sent()), 1, "same request delivered twice")

    def test_execute_phase_honors_outstanding_uncertainty(self):
        self.write(".local/herdr/requests/other.state.json", json.dumps({
            "request_id": "other", "state": "uncertain"
        }))
        self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(self.prompts_sent(), [], "prior uncertainty did not block execution")

    def test_blocked_response_is_not_settlement(self):
        self.set_scenario(self.frame(), prompt_output={"result": {"status": "blocked"}})
        code, payload, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, UNCERTAIN, payload)
        self.assertEqual(self.state()["state"], "uncertain")

    def test_submitted_response_is_not_settlement(self):
        self.set_scenario(self.frame(), prompt_output={"result": {"status": "submitted"}})
        code, payload, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, UNCERTAIN, payload)
        self.assertEqual(self.state()["state"], "uncertain")

    def test_child_endpoint_call_obeys_finite_wait(self):
        # The endpoint deliberately ignores --timeout, as a hung client could.
        text = self.fake.read_text(encoding="utf-8")
        text = text.replace("$ErrorActionPreference = 'Stop'",
                            "$ErrorActionPreference = 'Stop'\nStart-Sleep -Milliseconds 3000")
        self.fake.write_text(text, encoding="utf-8")
        start = time.monotonic()
        self.run_relay(self.request(), 1000, "-ExecuteRequest")
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 4, "1000ms bound failed to interrupt the endpoint call")


if __name__ == "__main__":
    unittest.main(verbosity=2)
