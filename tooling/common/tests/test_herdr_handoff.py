"""The deferred serial handoff relay, per DEC-2026-0082.

The relay exists because herdr will prompt an agent that is still working and
does not correlate a wait to a turn. Every test here is therefore about a
refusal: what must not be sent, what must not be sent twice, and what must stop
for a human instead of guessing.

Real herdr is never called. A stub stands in, driven by a JSON scenario the test
writes, and it records every invocation. That makes the races deterministic --
"sender still working" is a fact the test states rather than a timing accident --
and it means a passing run has provably sent nothing anywhere.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

RELAY = REPO_ROOT / "tooling" / "common" / "send-agent-handoff.ps1"

#: Exit codes the relay contracts for. Named so a test says why it expects one.
OK, NOT_READY, INVALID, UNCERTAIN = 0, 1, 2, 3

POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")

FAKE_HERDR = r"""
param([Parameter(ValueFromRemainingArguments = $true)][string[]] $CliArgs)
$ErrorActionPreference = 'Stop'
$scenario = Get-Content -LiteralPath $env:FAKE_HERDR_SCENARIO -Raw | ConvertFrom-Json
$logPath = $env:FAKE_HERDR_LOG
Add-Content -LiteralPath $logPath -Value ($CliArgs -join ' ')

if ($CliArgs[0] -eq 'agent' -and $CliArgs[1] -eq 'list') {
    $calls = @(Get-Content -LiteralPath $logPath | Where-Object { $_ -like 'agent list*' }).Count
    # A scenario may describe a world that changes between polls: entry N is
    # used for the Nth listing, and the last entry repeats thereafter.
    $frames = @($scenario.agent_frames)
    $index = [Math]::Min($calls - 1, $frames.Count - 1)
    @{ result = @{ agents = @($frames[$index]) } } | ConvertTo-Json -Depth 12
    exit 0
}
if ($CliArgs[0] -eq 'agent' -and $CliArgs[1] -eq 'prompt') {
    if ($scenario.PSObject.Properties.Name -contains 'prompt_exit_code' -and
        $scenario.prompt_exit_code -ne 0) {
        Write-Output ($scenario.prompt_output | ConvertTo-Json -Depth 12)
        exit $scenario.prompt_exit_code
    }
    if ($scenario.PSObject.Properties.Name -contains 'prompt_output') {
        $scenario.prompt_output | ConvertTo-Json -Depth 12
    } else {
        # The shape herdr 0.8.2 actually returns: the agent object nested under
        # result, with no flat result.status. Emitting a convenient
        # `result.status = done` here is what let the relay ship reading a field
        # the real binary never sends.
        $frames = @($scenario.agent_frames)
        $target = $CliArgs[2]
        $match = @($frames[$frames.Count - 1] | Where-Object { $_.pane_id -eq $target })
        $agent = if ($match.Count -gt 0) { $match[0] } else { $null }
        @{ id = 'cli:agent:prompt'; result = @{ agent = $agent; type = 'agent_prompt' } } |
            ConvertTo-Json -Depth 12
    }
    exit 0
}
@{ error = @{ code = 'unsupported'; message = ($CliArgs -join ' ') } } | ConvertTo-Json
exit 1
"""


def agent(pane, name, provider, status, cwd, session="sess-" + "0" * 8, seq=100):
    return {
        "pane_id": pane, "name": name, "agent": provider,
        "agent_status": status, "cwd": cwd,
        "state_change_seq": seq,
        "agent_session": {"agent": provider, "kind": "id", "value": session},
    }


@unittest.skipIf(POWERSHELL is None, "PowerShell is required to exercise the relay")
class RelayCase(unittest.TestCase):
    """A private repository root with a fake herdr endpoint."""

    SENDER_PANE, RECIPIENT_PANE = "w1:p1", "w1:p2"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        (self.root / ".local" / "herdr").mkdir(parents=True)
        self.write("README.md", "# fixture\n")
        self.write("inputs/GUP-X-r01.yaml", "id: GUP-X-r01\n")

        self.fake = self.root / "fake-herdr.ps1"
        self.fake.write_text(FAKE_HERDR, encoding="utf-8")
        self.log = self.root / ".local" / "herdr" / "fake.log"
        self.log.write_text("", encoding="utf-8")
        self.scenario_path = self.root / ".local" / "herdr" / "scenario.json"
        self.set_scenario(self.frame(sender="idle", recipient="idle"))

    def tearDown(self):
        try:
            self.temp.cleanup()
        except OSError:
            # A scheduled relay may still be exiting and holding the directory.
            shutil.rmtree(self.root, ignore_errors=True)

    def wait_for_relay(self, request_id="req-0001", seconds=20):
        """Block until a spawned background relay reaches a terminal state.

        Scheduling deliberately detaches, so a test that schedules owns the
        child's lifetime; leaving it running would leak a process holding the
        fixture open.
        """
        terminal = {"settled", "failed", "refused", "uncertain"}
        deadline = time.time() + seconds
        while time.time() < deadline:
            record = self.state(request_id)
            if record and record.get("state") in terminal:
                return record
            time.sleep(0.2)
        return self.state(request_id)

    # -- fixture helpers ----------------------------------------------------

    def digest(self, relative):
        import hashlib
        return hashlib.sha256((self.root / relative).read_bytes()).hexdigest()

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def frame(self, sender="idle", recipient="idle", extra=None,
              recipient_provider="codex", recipient_session="sess-recipient",
              sender_seq=100, recipient_seq=100):
        frame = [
            agent(self.SENDER_PANE, "builder", "claude", sender, str(self.root),
                  "sess-sender", seq=sender_seq),
            agent(self.RECIPIENT_PANE, "reviewer", recipient_provider, recipient,
                  str(self.root), recipient_session, seq=recipient_seq),
        ]
        if extra:
            frame.extend(extra)
        return frame

    def set_scenario(self, *frames, prompt_output=None, prompt_exit_code=0):
        scenario = {
            "agent_frames": list(frames),
            "prompt_exit_code": prompt_exit_code,
        }
        if prompt_output is not None:
            scenario["prompt_output"] = prompt_output
        self.scenario_path.write_text(json.dumps(scenario), encoding="utf-8")

    def request(self, **overrides):
        document = {
            "request_id": "req-0001",
            "repository_root": str(self.root),
            "endpoint": {"herdr_bin": str(self.fake)},
            "authority": "DEC-2026-0082 step 3",
            "scope": {"ruleset_id": "adnd1e", "book_id": "cross-book"},
            "sender": {
                "role": "builder", "name": "builder",
                "pane_id": self.SENDER_PANE, "session_id": "sess-sender",
            },
            "recipient": {
                "role": "reviewer", "name": "reviewer",
                "pane_id": self.RECIPIENT_PANE, "session_id": "sess-recipient",
            },
            "inputs": [{
                "id": "GUP-X-r01", "path": "inputs/GUP-X-r01.yaml",
                "checksum": "sha256:" + self.digest("inputs/GUP-X-r01.yaml"),
            }],
            "prerequisites": [],
            "action": "Review GUP-X-r01.",
            "ordered_next_steps": [
                {"priority": 1, "role": "reviewer", "artifact": "GUP-X-r01",
                 "action": "review", "prerequisites": [], "readiness": "ready",
                 "reason": "nothing blocks it"},
            ],
            "prompt": "Reviewer: review GUP-X-r01 at inputs/GUP-X-r01.yaml.",
        }
        document.update(overrides)
        path = self.root / "request.json"
        path.write_text(json.dumps(document, indent=2), encoding="utf-8")
        return path

    def ensure_reserved(self, request_path):
        """Create the queued reservation a direct execution now requires.

        R4 makes an unconsumed scheduled record a precondition for delivery, so
        a test that drives the deferred phase directly has to stand in for the
        scheduler. Only created when absent: a test that sets its own state --
        to prove a protected state survives, say -- keeps it.
        """
        import hashlib

        document = json.loads(Path(request_path).read_text(encoding="utf-8"))
        directory = self.root / ".local" / "herdr" / "requests"
        directory.mkdir(parents=True, exist_ok=True)
        state = directory / f"{document['request_id']}.state.json"
        if state.exists():
            return
        digest = hashlib.sha256(Path(request_path).read_bytes()).hexdigest()
        state.write_text(json.dumps({
            "request_id": document["request_id"], "state": "queued",
            "request_path": str(Path(request_path).resolve()),
            "request_checksum": f"sha256:{digest}",
            "recipient_pane": document["recipient"]["pane_id"],
        }), encoding="utf-8")

    def run_relay_unreserved(self, request_path=None, timeout_ms=4000, *flags):
        """Drive the relay without standing in for the scheduler."""
        return self._invoke_relay(request_path or self.request(), timeout_ms, flags)

    def run_relay(self, request_path=None, timeout_ms=4000, *flags):
        request_path = request_path or self.request()
        if "-ExecuteRequest" in flags:
            self.ensure_reserved(request_path)
        return self._invoke_relay(request_path, timeout_ms, flags)

    def _invoke_relay(self, request_path, timeout_ms, flags):
        command = [
            POWERSHELL, "-NoLogo", "-NonInteractive", "-NoProfile",
            "-File", str(RELAY), "-RequestPath", str(request_path),
            "-TimeoutMs", str(timeout_ms), *flags,
        ]
        completed = subprocess.run(
            command, capture_output=True, text=True, cwd=str(self.root),
            env={
                **__import__("os").environ,
                "FAKE_HERDR_SCENARIO": str(self.scenario_path),
                "FAKE_HERDR_LOG": str(self.log),
                "HERDR_BIN_PATH": str(self.fake),
            },
        )
        payload = {}
        text = completed.stdout.strip()
        if text:
            try:
                payload = json.loads(text[text.index("{"):text.rindex("}") + 1])
            except (ValueError, json.JSONDecodeError):
                payload = {"unparsed": text}
        return completed.returncode, payload, completed.stderr

    def herdr_calls(self):
        return [line for line in self.log.read_text(encoding="utf-8").splitlines() if line]

    def prompts_sent(self):
        return [c for c in self.herdr_calls() if c.startswith("agent prompt")]

    def state(self, request_id="req-0001"):
        path = self.root / ".local" / "herdr" / "requests" / f"{request_id}.state.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


class TestRequestValidation(RelayCase):
    """Acceptance test 3: a complete bounded request, or nothing happens."""

    def refuses(self, fragment, **overrides):
        code, payload, _ = self.run_relay(self.request(**overrides), 4000, "-ValidateOnly")
        self.assertEqual(code, INVALID, payload)
        joined = " ".join(payload.get("problems", []))
        self.assertIn(fragment, joined)
        self.assertEqual(self.prompts_sent(), [])
        return payload

    def test_a_complete_request_validates(self):
        code, payload, err = self.run_relay(self.request(), 4000, "-ValidateOnly")
        self.assertEqual(code, OK, f"{payload} {err}")
        self.assertEqual(payload["status"], "valid")

    def test_validate_only_launches_nothing_and_writes_nothing(self):
        self.run_relay(self.request(), 4000, "-ValidateOnly")
        self.assertEqual(self.herdr_calls(), [], "no endpoint call may be made")
        self.assertIsNone(self.state(), "no state record may be written")
        self.assertFalse((self.root / ".local" / "herdr" / "handoff.lock").exists())

    def test_a_missing_field_is_refused(self):
        for field in ("request_id", "sender", "recipient", "authority", "action", "prompt"):
            with self.subTest(field=field):
                document = json.loads(self.request().read_text(encoding="utf-8"))
                del document[field]
                path = self.root / "request.json"
                path.write_text(json.dumps(document), encoding="utf-8")
                code, payload, _ = self.run_relay(path, 4000, "-ValidateOnly")
                self.assertEqual(code, INVALID)
                self.assertIn(f"missing required field '{field}'",
                              " ".join(payload.get("problems", [])))

    def test_an_empty_prompt_is_refused(self):
        self.refuses("prompt is empty", prompt="   ")

    def test_a_request_id_that_could_escape_its_store_is_refused(self):
        """The ID becomes a filename under .local/herdr/."""
        for bad in ("../escape", "a/b", "with space", ""):
            with self.subTest(request_id=bad):
                code, payload, _ = self.run_relay(
                    self.request(request_id=bad), 4000, "-ValidateOnly")
                self.assertEqual(code, INVALID)

    def test_addressing_the_retired_role_is_refused_by_name(self):
        payload = self.refuses(
            "retired by DEC-2026-0082",
            recipient={"role": "dispatcher", "pane_id": self.RECIPIENT_PANE})
        self.assertNotIn("is not one of", " ".join(payload["problems"]))

    def test_an_invalid_role_is_refused(self):
        self.refuses("is not one of",
                     recipient={"role": "steward", "pane_id": self.RECIPIENT_PANE})

    def test_a_missing_recipient_pane_is_refused(self):
        self.refuses("recipient.pane_id is missing", recipient={"role": "reviewer"})

    def test_a_handoff_to_oneself_is_refused(self):
        self.refuses("sender and recipient are the same role",
                     recipient={"role": "builder", "pane_id": self.RECIPIENT_PANE})

    def test_an_input_outside_the_repository_root_is_refused(self):
        self.refuses("does not exist",
                     inputs=[{"id": "X", "path": "../outside.yaml"}])

    def test_a_missing_prerequisite_is_refused(self):
        self.refuses("prerequisite path 'inputs/absent.yaml' does not exist",
                     prerequisites=[{"id": "P", "path": "inputs/absent.yaml"}])

    def test_a_stale_input_checksum_is_refused(self):
        """The worker measured a different file than the recipient would open."""
        self.refuses("checksum is stale", inputs=[{
            "id": "GUP-X-r01", "path": "inputs/GUP-X-r01.yaml",
            "checksum": "sha256:" + "0" * 64,
        }])

    def test_a_correct_input_checksum_passes(self):
        import hashlib
        digest = hashlib.sha256(
            (self.root / "inputs/GUP-X-r01.yaml").read_bytes()).hexdigest()
        code, payload, _ = self.run_relay(self.request(inputs=[{
            "id": "GUP-X-r01", "path": "inputs/GUP-X-r01.yaml",
            "checksum": f"sha256:{digest}",
        }]), 4000, "-ValidateOnly")
        self.assertEqual(code, OK, payload)

    def test_an_unreadable_request_is_refused(self):
        path = self.root / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        code, payload, _ = self.run_relay(path, 4000, "-ValidateOnly")
        self.assertEqual(code, INVALID)
        self.assertIn("not readable JSON", " ".join(payload.get("problems", [])))

    def test_a_missing_request_file_is_refused(self):
        code, payload, _ = self.run_relay(self.root / "absent.json", 4000, "-ValidateOnly")
        self.assertEqual(code, INVALID)


class TestSenderSerialization(RelayCase):
    """Acceptance test 4: a working sender means nobody is prompted."""

    def test_a_working_sender_prompts_nobody(self):
        self.set_scenario(self.frame(sender="working", recipient="idle"))
        code, payload, _ = self.run_relay(self.request(), 2000, "-ExecuteRequest")
        self.assertEqual(code, NOT_READY, payload)
        self.assertEqual(self.prompts_sent(), [])
        self.assertIn("had not settled", " ".join(payload["problems"]))
        self.assertEqual(self.state()["state"], "refused")

    def test_delivery_happens_once_the_sender_settles(self):
        """The world changes between polls; the relay re-reads it each time."""
        self.set_scenario(
            self.frame(sender="working", recipient="idle"),
            self.frame(sender="working", recipient="idle"),
            self.frame(sender="idle", recipient="idle"),
        )
        code, payload, err = self.run_relay(self.request(), 8000, "-ExecuteRequest")
        self.assertEqual(code, OK, f"{payload} {err}")
        self.assertTrue(payload["delivered"])
        self.assertEqual(len(self.prompts_sent()), 1, "exactly one prompt")
        self.assertEqual(self.state()["state"], "settled")

    def test_an_unexpected_third_agent_blocks_delivery(self):
        """A manual launch elsewhere is exactly what this catches."""
        intruder = agent("w1:p9", "analyst", "claude", "working", str(self.root), "sess-x")
        self.set_scenario(self.frame(sender="idle", recipient="idle", extra=[intruder]))
        code, payload, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, NOT_READY, payload)
        self.assertEqual(self.prompts_sent(), [])
        self.assertIn("not idle", " ".join(payload["problems"]))

    def test_an_agent_in_another_repository_does_not_block(self):
        """Serialization is per repository, not per herdr server."""
        elsewhere = agent("w2:p1", "builder", "claude", "working", "C:/other/repo", "sess-y")
        self.set_scenario(self.frame(sender="idle", recipient="idle", extra=[elsewhere]))
        code, payload, err = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, OK, f"{payload} {err}")
        self.assertEqual(len(self.prompts_sent()), 1)

    def test_a_disappeared_sender_fails_closed(self):
        self.set_scenario([
            agent(self.RECIPIENT_PANE, "reviewer", "codex", "idle", str(self.root),
                  "sess-recipient"),
        ])
        code, payload, _ = self.run_relay(self.request(), 2000, "-ExecuteRequest")
        self.assertEqual(code, INVALID, payload)
        self.assertEqual(self.prompts_sent(), [])


class TestRecipientIdentity(RelayCase):
    """Acceptance test 4: re-resolve immediately before delivery."""

    def test_a_recipient_on_the_wrong_provider_fails_closed(self):
        self.set_scenario(self.frame(recipient_provider="claude"))
        code, payload, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, INVALID, payload)
        self.assertIn("provider is 'claude'", " ".join(payload["problems"]))
        self.assertEqual(self.prompts_sent(), [])

    def test_a_changed_native_session_fails_closed(self):
        """The pane is reused by a different agent run; the alias survived."""
        self.set_scenario(self.frame(recipient_session="sess-somebody-else"))
        code, payload, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, INVALID, payload)
        self.assertIn("native session", " ".join(payload["problems"]))
        self.assertEqual(self.prompts_sent(), [])

    def test_a_vanished_recipient_fails_closed(self):
        self.set_scenario([
            agent(self.SENDER_PANE, "builder", "claude", "idle", str(self.root), "sess-sender"),
        ])
        code, payload, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, INVALID, payload)
        self.assertIn("not bound to this repository", " ".join(payload["problems"]))


class TestTheGlobalLock(RelayCase):
    """Acceptance test 4: one exclusive lock serializes competing relays."""

    def lock_path(self):
        return self.root / ".local" / "herdr" / "handoff.lock"

    def test_a_held_lock_refuses_a_second_relay(self):
        self.lock_path().write_text('{"request_id": "other", "pid": 1}', encoding="utf-8")
        code, payload, _ = self.run_relay(self.request(), 2000, "-ExecuteRequest")
        self.assertEqual(code, NOT_READY, payload)
        self.assertIn("holds the repository handoff lock", " ".join(payload["problems"]))
        self.assertEqual(self.prompts_sent(), [])

    def test_a_held_lock_is_never_stolen_by_age(self):
        """A stale-looking lock may belong to a live recipient mid-turn."""
        import os, time
        path = self.lock_path()
        path.write_text('{"request_id": "ancient", "pid": 1}', encoding="utf-8")
        ancient = time.time() - 86400
        os.utime(path, (ancient, ancient))
        code, _, _ = self.run_relay(self.request(), 2000, "-ExecuteRequest")
        self.assertEqual(code, NOT_READY)
        self.assertTrue(path.exists(), "the lock must survive")
        self.assertIn("ancient", path.read_text(encoding="utf-8"))

    def test_the_lock_is_released_after_a_successful_delivery(self):
        code, _, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, OK)
        self.assertFalse(self.lock_path().exists())

    def test_the_lock_is_released_after_a_refusal(self):
        self.set_scenario(self.frame(sender="working"))
        self.run_relay(self.request(), 2000, "-ExecuteRequest")
        self.assertFalse(self.lock_path().exists(), "a refusal must not strand the lock")


class TestDuplicateAndUncertainDelivery(RelayCase):
    """Acceptance test 5: nothing resubmits work."""

    def test_a_duplicate_request_id_cannot_schedule(self):
        for state in ("queued", "submitting", "acknowledged", "settled", "uncertain"):
            with self.subTest(prior_state=state):
                directory = self.root / ".local" / "herdr" / "requests"
                directory.mkdir(parents=True, exist_ok=True)
                (directory / "req-0001.state.json").write_text(
                    json.dumps({"request_id": "req-0001", "state": state}), encoding="utf-8")
                code, payload, _ = self.run_relay(self.request(), 4000)
                self.assertEqual(code, INVALID, payload)
                self.assertIn("duplicate ID cannot resubmit", " ".join(payload["problems"]))
                self.assertEqual(self.prompts_sent(), [])

    def test_a_second_outstanding_request_cannot_schedule(self):
        directory = self.root / ".local" / "herdr" / "requests"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "req-other.state.json").write_text(
            json.dumps({"request_id": "req-other", "state": "queued"}), encoding="utf-8")
        code, payload, _ = self.run_relay(self.request(), 4000)
        self.assertEqual(code, NOT_READY, payload)
        self.assertIn("another request is outstanding", " ".join(payload["problems"]))

    def test_a_settled_earlier_request_does_not_block_a_new_one(self):
        directory = self.root / ".local" / "herdr" / "requests"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "req-old.state.json").write_text(
            json.dumps({"request_id": "req-old", "state": "settled"}), encoding="utf-8")
        self.set_scenario(self.frame(sender="working"))
        code, payload, err = self.run_relay(self.request(), 1000)
        self.assertEqual(code, OK, f"{payload} {err}")
        self.assertEqual(payload["status"], "queued")
        self.wait_for_relay()

    def test_a_failing_prompt_is_uncertain_not_failed(self):
        """Submission may have landed. Only a human may decide it did not."""
        self.set_scenario(self.frame(), prompt_exit_code=1,
                          prompt_output={"error": {"code": "agent_prompt_stalled"}})
        code, payload, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, UNCERTAIN, payload)
        self.assertFalse(payload["delivered"])
        self.assertEqual(self.state()["state"], "uncertain")

    def test_a_herdr_error_response_is_uncertain(self):
        self.set_scenario(self.frame(),
                          prompt_output={"error": {"code": "agent_busy"}})
        code, payload, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, UNCERTAIN, payload)
        self.assertEqual(self.state()["state"], "uncertain")

    def test_an_uncertain_request_cannot_be_rerun(self):
        self.set_scenario(self.frame(), prompt_exit_code=1, prompt_output={"error": {}})
        self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(self.state()["state"], "uncertain")
        code, payload, _ = self.run_relay(self.request(), 4000)
        self.assertEqual(code, INVALID, payload)
        self.assertIn("duplicate ID cannot resubmit", " ".join(payload["problems"]))

    def test_submitting_is_recorded_before_the_prompt(self):
        """So an interrupted relay leaves evidence a send may have landed."""
        self.set_scenario(self.frame(), prompt_exit_code=1, prompt_output={"error": {}})
        self.run_relay(self.request(), 4000, "-ExecuteRequest")
        record = self.state()
        self.assertEqual(record["state"], "uncertain")
        self.assertEqual(record["request_id"], "req-0001")


class TestScheduling(RelayCase):
    """Acceptance test 4: scheduling returns promptly and sends nothing itself."""

    def test_scheduling_returns_queued_without_prompting(self):
        """The scheduler itself never prompts; that is the whole point."""
        self.set_scenario(self.frame(sender="working"))
        code, payload, err = self.run_relay(self.request(), 1000)
        self.assertEqual(code, OK, f"{payload} {err}")
        self.assertEqual(payload["status"], "queued")
        self.assertFalse(payload["delivered"])
        self.assertEqual(payload["request_id"], "req-0001")
        self.assertIsNotNone(self.state(), "a durable record exists before the sender yields")
        self.wait_for_relay()
        self.assertEqual(self.prompts_sent(), [], "the working sender was never interrupted")

    def test_scheduling_records_the_bounded_timeout_and_parties(self):
        self.set_scenario(self.frame(sender="working"))
        self.run_relay(self.request(), 1000)
        record = self.state()
        self.addCleanup(self.wait_for_relay)
        self.assertEqual(record["timeout_ms"], 1000)
        self.assertEqual(record["sender"]["role"], "builder")
        self.assertEqual(record["recipient"]["role"], "reviewer")

    def test_a_timeout_outside_the_bounded_range_is_rejected(self):
        for value in (0, 500, 3600001):
            with self.subTest(timeout_ms=value):
                code, _, _ = self.run_relay(self.request(), value, "-ValidateOnly")
                self.assertNotEqual(code, OK)


class TestTheRelayTransportsWithoutDeciding(RelayCase):
    """Acceptance test 6: it carries the worker's order and consumes nothing."""

    BLOCKING = [
        {"priority": 1, "role": "architect", "artifact": "ESC-2026-09-20T00.00.00.000Z",
         "action": "rule on the blocking escalation", "prerequisites": [],
         "readiness": "ready", "reason": "blocks both GURs below"},
        {"priority": 2, "role": "builder", "artifact": "GUR-PKT-A-r01",
         "action": "compile", "prerequisites": ["ESC-2026-09-20T00.00.00.000Z"],
         "readiness": "blocked", "reason": "waits on the ruling"},
        {"priority": 3, "role": "builder", "artifact": "GUR-PKT-B-r01",
         "action": "compile", "prerequisites": [], "readiness": "ready",
         "reason": "independent of the escalation"},
    ]

    def test_the_ordered_list_is_carried_verbatim(self):
        path = self.request(ordered_next_steps=self.BLOCKING)
        code, payload, err = self.run_relay(path, 4000, "-ValidateOnly")
        self.assertEqual(code, OK, f"{payload} {err}")
        carried = json.loads(path.read_text(encoding="utf-8"))["ordered_next_steps"]
        self.assertEqual(carried, self.BLOCKING, "the relay reorders nothing")
        self.assertEqual(carried[0]["role"], "architect")
        self.assertEqual(carried[2]["readiness"], "ready",
                         "an unrelated ESC does not block independent work")

    def test_the_prompt_is_delivered_exactly_as_written(self):
        exact = "Reviewer: review GUP-X-r01. Remaining order: 1 architect ESC, 2 builder GUR."
        self.run_relay(self.request(prompt=exact), 4000, "-ExecuteRequest")
        prompt_calls = self.prompts_sent()
        self.assertEqual(len(prompt_calls), 1)
        self.assertIn(exact, prompt_calls[0])

    def test_no_artifact_is_written_or_consumed(self):
        before = {p: p.read_bytes() for p in (self.root / "inputs").rglob("*")}
        self.run_relay(self.request(), 4000, "-ExecuteRequest")
        after = {p: p.read_bytes() for p in (self.root / "inputs").rglob("*")}
        self.assertEqual(before, after, "inputs are read, never modified")

    def test_relay_records_live_only_under_the_ignored_local_directory(self):
        self.run_relay(self.request(), 4000, "-ExecuteRequest")
        written = [
            p.relative_to(self.root).as_posix()
            for p in self.root.rglob("*")
            if p.is_file() and p.name not in ("README.md", "request.json", "fake-herdr.ps1")
            and "inputs" not in p.parts
        ]
        for relative in written:
            self.assertTrue(relative.startswith(".local/"), relative)

    def test_a_reload_only_request_carries_no_onward_work(self):
        """A maintenance notification authorizes no task processing."""
        path = self.request(
            request_id="reload-0001",
            action="Reload instructions only.",
            ordered_next_steps=[],
            prompt="Reload only: read your instructions and acknowledge. Do not process work.",
        )
        code, payload, err = self.run_relay(path, 4000, "-ValidateOnly")
        self.assertEqual(code, OK, f"{payload} {err}")
        self.assertEqual(
            json.loads(path.read_text(encoding="utf-8"))["ordered_next_steps"], [])


# ---------------------------------------------------------------------------
# REV-IMP-DEC-2026-0082-r01-r01 findings F1-F5.
#
# The Reviewer reproduced each of these against r01 with independent probes.
# Those probes live in the Reviewer's own tree and are theirs to change, so the
# properties are pinned here too: a defect that was once real should fail this
# suite, not only someone else's.
# ---------------------------------------------------------------------------


class TestCompleteTypedRequest(RelayCase):
    """F1: required evidence is required, and containment is a real boundary."""

    def refuse(self, fragment=None, **overrides):
        code, payload, _ = self.run_relay(self.request(**overrides), 4000, "-ValidateOnly")
        self.assertEqual(code, INVALID, payload)
        if fragment:
            self.assertIn(fragment, " ".join(payload.get("problems", [])))
        self.assertEqual(self.prompts_sent(), [])
        return payload

    def test_each_evidence_section_is_required(self):
        """r01 accepted a request with all five of these absent."""
        for field in ("endpoint", "scope", "inputs", "prerequisites", "ordered_next_steps"):
            with self.subTest(field=field):
                document = json.loads(self.request().read_text(encoding="utf-8"))
                del document[field]
                path = self.write("partial.json", json.dumps(document))
                code, payload, _ = self.run_relay(path, 4000, "-ValidateOnly")
                self.assertEqual(code, INVALID, payload)
                self.assertIn(f"missing required field '{field}'",
                              " ".join(payload.get("problems", [])))

    def test_an_input_without_a_checksum_is_refused(self):
        """A path alone does not say which bytes the worker measured."""
        self.refuse("is missing 'checksum'",
                    inputs=[{"id": "GUP-X-r01", "path": "inputs/GUP-X-r01.yaml"}])

    def test_a_prerequisite_without_a_checksum_is_refused(self):
        self.refuse("is missing 'checksum'",
                    prerequisites=[{"id": "P", "path": "inputs/GUP-X-r01.yaml"}])

    def test_a_scope_identifier_may_be_null_but_not_malformed(self):
        """Unassigned is recorded, never invented -- and never a path fragment."""
        code, payload, err = self.run_relay(
            self.request(scope={"ruleset_id": None, "book_id": None}), 4000, "-ValidateOnly")
        self.assertEqual(code, OK, f"{payload} {err}")
        for bad in ("../escape", "Adnd1e", "has space", "-leading"):
            with self.subTest(value=bad):
                self.refuse("not a well-formed identifier",
                            scope={"ruleset_id": bad, "book_id": None})

    def test_a_missing_scope_key_is_refused(self):
        self.refuse("scope.book_id is missing", scope={"ruleset_id": "adnd1e"})

    def test_a_sibling_sharing_the_root_prefix_is_outside_the_root(self):
        """`repo-backup` beside `repo` passes a bare StartsWith. It must not."""
        sibling = self.root.parent / (self.root.name + "-sibling")
        sibling.mkdir()
        try:
            (sibling / "outside.yaml").write_text("id: outside\n", encoding="utf-8")
            import hashlib
            digest = hashlib.sha256((sibling / "outside.yaml").read_bytes()).hexdigest()
            self.refuse("does not exist inside repository_root", inputs=[{
                "id": "outside", "path": f"../{sibling.name}/outside.yaml",
                "checksum": f"sha256:{digest}",
            }])
        finally:
            import shutil
            shutil.rmtree(sibling, ignore_errors=True)

    def test_an_endpoint_other_than_the_inherited_one_is_refused(self):
        other = self.root / "other-herdr.ps1"
        other.write_text("exit 0\n", encoding="utf-8")
        self.refuse("is not the inherited endpoint", endpoint={"herdr_bin": str(other)})

    def test_a_missing_endpoint_binary_is_refused(self):
        self.refuse("does not exist", endpoint={"herdr_bin": str(self.root / "absent.ps1")})

    def test_an_ordered_step_must_be_complete_and_active(self):
        for step, fragment in (
            ({"priority": 1, "role": "reviewer", "action": "a", "readiness": "ready"}, "missing 'reason'"),
            ({"priority": 1, "role": "dispatcher", "action": "a", "readiness": "ready",
              "reason": "r"}, "which is not active"),
            ({"priority": 1, "role": "reviewer", "action": "a", "readiness": "maybe",
              "reason": "r"}, "must be ready or blocked"),
        ):
            with self.subTest(fragment=fragment):
                self.refuse(fragment, ordered_next_steps=[step])


class TestPartyIdentityIsVerified(RelayCase):
    """F2: resolve by unique alias, then cross-check; never take the first pane."""

    def expect_no_prompt(self, fragment, frame=None, **overrides):
        if frame is not None:
            self.set_scenario(frame)
        code, payload, _ = self.run_relay(self.request(**overrides), 4000, "-ExecuteRequest")
        self.assertEqual(code, INVALID, payload)
        self.assertIn(fragment, " ".join(payload.get("problems", [])))
        self.assertEqual(self.prompts_sent(), [], "an unverified party authorized a prompt")

    def test_a_replaced_sender_cannot_authorize_delivery(self):
        """r01 trusted the pane alone, so a substituted agent still sent."""
        frame = self.frame()
        frame[0] = agent(self.SENDER_PANE, "analyst", "claude", "idle",
                         str(self.root), "replacement-session")
        self.expect_no_prompt("is not bound to this repository", frame=frame)

    def test_a_sender_on_a_different_pane_cannot_authorize_delivery(self):
        frame = self.frame()
        frame[0]["pane_id"] = "w1:p7"
        self.expect_no_prompt("request names", frame=frame)

    def test_a_changed_sender_session_cannot_authorize_delivery(self):
        frame = self.frame()
        frame[0]["agent_session"]["value"] = "a-different-run"
        self.expect_no_prompt("native session", frame=frame)

    def test_a_reassigned_recipient_alias_cannot_receive(self):
        frame = self.frame()
        frame[1]["name"] = "architect"
        self.expect_no_prompt("is not bound to this repository", frame=frame)

    def test_an_ambiguous_alias_refuses_rather_than_choosing(self):
        duplicate = agent("w1:p8", "reviewer", "codex", "idle", str(self.root), "another")
        self.expect_no_prompt("is ambiguous across panes", frame=self.frame(extra=[duplicate]))

    def test_a_recipient_on_the_wrong_provider_cannot_receive(self):
        self.expect_no_prompt("provider is 'claude'", frame=self.frame(recipient_provider="claude"))

    def test_the_request_must_name_the_alias_matching_its_role(self):
        self.expect_no_prompt("the herdr alias is the role name", recipient={
            "role": "reviewer", "name": "not-reviewer",
            "pane_id": self.RECIPIENT_PANE, "session_id": "sess-recipient",
        })


class TestAcknowledgmentIsNotSettlement(RelayCase):
    """F3: the message leaving is not the turn finishing."""

    def expect_uncertain(self, fragment, **scenario):
        self.set_scenario(self.frame(), **scenario)
        code, payload, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, UNCERTAIN, payload)
        self.assertEqual(self.state()["state"], "uncertain")
        self.assertIn(fragment, " ".join(payload.get("problems", [])))

    def test_submitted_is_delivery_not_completion(self):
        self.expect_uncertain("does not confirm the turn finished",
                              prompt_output={"result": {"status": "submitted"}})

    def test_blocked_needs_a_human_and_is_never_settlement(self):
        self.expect_uncertain("does not confirm the turn finished",
                              prompt_output={"result": {"status": "blocked"}})

    def test_a_response_without_a_result_envelope_is_uncertain(self):
        self.expect_uncertain("no result envelope", prompt_output={"unexpected": True})

    def test_the_real_herdr_envelope_settles(self):
        """The shape herdr 0.8.2 returns: the agent nested under result.

        The relay used to read `result.status`, which this envelope does not
        carry, so it filed every genuine delivery `uncertain` and blocked the
        next handoff until a human cleared it. Three consecutive confirmed
        deliveries were lost that way.
        """
        self.set_scenario(self.frame(), prompt_output={
            "id": "cli:agent:prompt",
            "result": {
                "type": "agent_prompt",
                "agent": {"pane_id": self.RECIPIENT_PANE, "name": "reviewer",
                          "agent_status": "idle", "state_change_seq": 164},
            },
        })
        code, payload, err = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, OK, f"{payload} {err}")
        self.assertEqual(self.state()["state"], "settled")

    def test_the_default_double_never_sends_a_flat_result_status(self):
        """The double must speak the installed binary's envelope.

        A convenient `result.status = done` here is exactly what let the relay
        ship reading a field the real herdr never sends, with 95 tests passing.
        """
        self.set_scenario(self.frame())
        self.run_relay(self.request(), 4000, "-ExecuteRequest")
        import os
        probe = subprocess.run(
            [POWERSHELL, "-NoProfile", "-File", str(self.fake), "agent", "prompt",
             self.RECIPIENT_PANE, "text"],
            capture_output=True, text=True,
            env={**os.environ, "FAKE_HERDR_SCENARIO": str(self.scenario_path),
                 "FAKE_HERDR_LOG": str(self.log)})
        envelope = json.loads(probe.stdout)
        self.assertNotIn("status", envelope["result"],
                         "the double invented a flat result.status again")
        self.assertIn("agent", envelope["result"])
        self.assertEqual(envelope["result"]["agent"]["agent_status"], "idle")


class TestStalledAndBlockedAreDifferent(RelayCase):
    """herdr distinguishes 'nothing was sent' from 'nothing was observed'.

    Filing both as `uncertain` made every blocked recipient leave behind a
    record a human had to clear, for a submission that never happened.
    """

    def test_agent_blocked_sent_nothing_and_needs_no_reconciliation(self):
        self.set_scenario(self.frame(), prompt_exit_code=1,
                          prompt_output={"error": {"code": "agent_blocked"}})
        code, payload, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, NOT_READY, payload)
        self.assertFalse(payload["delivered"])
        self.assertEqual(self.state()["state"], "refused")
        self.assertIn("before sending any input", " ".join(payload["problems"]))

    def test_a_stall_whose_recipient_ran_a_turn_is_settled(self):
        """The 5000ms observation window expiring is not proof of non-delivery."""
        self.set_scenario(
            self.frame(recipient_seq=100),
            self.frame(recipient_seq=170),
            prompt_exit_code=1,
            prompt_output={"error": {"code": "agent_prompt_stalled"}})
        code, payload, err = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, OK, f"{payload} {err}")
        self.assertEqual(self.state()["state"], "settled")

    def test_a_stall_with_no_observed_turn_stays_uncertain(self):
        """Fail-closed is preserved where the evidence really is absent."""
        self.set_scenario(
            self.frame(recipient_seq=164),
            self.frame(recipient_seq=164),
            prompt_exit_code=1,
            prompt_output={"error": {"code": "agent_prompt_stalled"}})
        code, payload, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, UNCERTAIN, payload)
        self.assertEqual(self.state()["state"], "uncertain")
        self.assertIn("did not advance", " ".join(payload["problems"]))

    def test_a_wait_killed_at_the_deadline_records_the_delivery_it_can_see(self):
        """`--wait` holds the budget for the recipient's whole turn.

        A recipient that works longer than the budget has the waiting call
        killed out from under it, after its prompt already landed. That was
        filed as an unexplained 'submission outcome unknown', which is how a
        plainly successful handoff still demanded a human reconciliation.
        """
        self.set_scenario(
            self.frame(recipient_seq=100),
            self.frame(recipient="working", recipient_seq=205),
            prompt_exit_code=1, prompt_output="not json at all")
        code, payload, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, UNCERTAIN, payload)
        record = self.state()
        self.assertTrue(record["delivery_observed"], record)
        self.assertEqual(record["reason"],
                         "delivered; recipient turn outlasted the relay budget")
        self.assertTrue(payload["delivered"])
        self.assertIn("would duplicate a prompt the recipient already has", payload["note"])

    def test_a_wait_killed_with_no_observed_turn_stays_unknown(self):
        """Where nothing moved, the old fail-closed wording is still right."""
        self.set_scenario(
            self.frame(recipient_seq=100),
            self.frame(recipient_seq=100),
            prompt_exit_code=1, prompt_output="not json at all")
        code, payload, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, UNCERTAIN, payload)
        record = self.state()
        self.assertFalse(record["delivery_observed"], record)
        self.assertEqual(record["reason"], "submission outcome unknown")
        self.assertFalse(payload["delivered"])

    def test_a_short_timeout_is_classified_like_a_stall(self):
        """herdr returns `timeout` for the same unobserved-state situation."""
        self.set_scenario(
            self.frame(recipient_seq=100),
            self.frame(recipient_seq=170),
            prompt_exit_code=1, prompt_output={"error": {"code": "timeout"}})
        code, payload, err = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, OK, f"{payload} {err}")
        self.assertEqual(self.state()["state"], "settled")

    def test_an_unknown_herdr_error_is_still_uncertain(self):
        self.set_scenario(self.frame(), prompt_output={"error": {"code": "agent_busy"}})
        code, payload, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, UNCERTAIN, payload)
        self.assertEqual(self.state()["state"], "uncertain")

    def test_settlement_records_the_observation_it_rested_on(self):
        self.set_scenario(self.frame(recipient_seq=100), self.frame(recipient_seq=170))
        code, payload, err = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, OK, f"{payload} {err}")
        record = self.state()
        self.assertEqual(str(record["observation_before"]), "100")
        self.assertEqual(str(record["observation_after"]), "170")

    def test_a_recipient_still_working_after_delivery_is_uncertain(self):
        """The response said idle; the agent disagrees. Believe the agent.

        The envelope is stated explicitly, in herdr's real shape, because the
        premise is a disagreement between it and the observed agent: a response
        derived from the same frames could not disagree with them.
        """
        self.set_scenario(
            self.frame(sender="idle", recipient="idle"),
            self.frame(sender="idle", recipient="working"),
            prompt_output={"id": "cli:agent:prompt", "result": {
                "type": "agent_prompt",
                "agent": {"pane_id": self.RECIPIENT_PANE, "name": "reviewer",
                          "agent_status": "idle", "state_change_seq": 170}}},
        )
        code, payload, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, UNCERTAIN, payload)
        self.assertIn("not idle or done", " ".join(payload["problems"]))

    def test_a_confirmed_settled_recipient_releases_the_lock(self):
        code, _, err = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, OK, err)
        self.assertEqual(self.state()["state"], "settled")
        self.assertFalse((self.root / ".local" / "herdr" / "handoff.lock").exists())


class TestIdentityIsClaimedAtomically(RelayCase):
    """F4: claim under the lock, and never erase evidence of a possible send."""

    def test_execution_cannot_be_replayed(self):
        """r01's duplicate guard lived only in the scheduler."""
        path = self.request()
        first, _, _ = self.run_relay(path, 4000, "-ExecuteRequest")
        self.assertEqual(first, OK)
        second, payload, _ = self.run_relay(path, 4000, "-ExecuteRequest")
        self.assertEqual(second, INVALID, payload)
        self.assertIn("cannot be replayed", " ".join(payload["problems"]))
        self.assertEqual(len(self.prompts_sent()), 1, "the same request was delivered twice")

    def test_an_unrelated_uncertainty_blocks_execution(self):
        """Uncertainty is not terminal: it blocks until a human clears it."""
        self.write(".local/herdr/requests/other.state.json",
                   json.dumps({"request_id": "other", "state": "uncertain"}))
        code, payload, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, NOT_READY, payload)
        self.assertEqual(self.prompts_sent(), [])

    def test_a_terminal_unrelated_request_does_not_block(self):
        for state in ("settled", "failed", "refused"):
            with self.subTest(state=state):
                self.write(".local/herdr/requests/other.state.json",
                           json.dumps({"request_id": "other", "state": state}))
                code, _, err = self.run_relay(
                    self.request(request_id=f"req-{state}"), 4000, "-ExecuteRequest")
                self.assertEqual(code, OK, err)

    def test_possible_send_evidence_is_never_overwritten(self):
        """A competitor recording `refused` would erase the only warning."""
        for protected in ("submitting", "acknowledged", "uncertain"):
            with self.subTest(state=protected):
                self.write(".local/herdr/requests/req-0001.state.json",
                           json.dumps({"request_id": "req-0001", "state": protected}))
                self.run_relay(self.request(), 4000, "-ExecuteRequest")
                self.assertEqual(self.state()["state"], protected)

    def test_a_payload_changed_after_queueing_is_refused(self):
        """The recipient must receive what the sender approved."""
        path = self.request()
        self.write(".local/herdr/requests/req-0001.state.json", json.dumps({
            "request_id": "req-0001", "state": "queued",
            "request_checksum": "sha256:" + "0" * 64,
        }))
        code, payload, _ = self.run_relay(path, 4000, "-ExecuteRequest")
        self.assertEqual(code, INVALID, payload)
        self.assertIn("payload changed after it was queued", " ".join(payload["problems"]))
        self.assertEqual(self.prompts_sent(), [])


class TestEveryChildCallIsBounded(RelayCase):
    """F5: one monotonic budget, enforced by the parent."""

    def slow_endpoint(self, milliseconds):
        text = self.fake.read_text(encoding="utf-8")
        self.fake.write_text(
            text.replace("$ErrorActionPreference = 'Stop'",
                         f"$ErrorActionPreference = 'Stop'\nStart-Sleep -Milliseconds {milliseconds}"),
            encoding="utf-8")

    def test_a_hung_agent_list_is_killed_at_the_deadline(self):
        """The endpoint ignores --timeout, as a hung client would."""
        import time
        self.slow_endpoint(4000)
        started = time.monotonic()
        code, payload, _ = self.run_relay(self.request(), 1000, "-ExecuteRequest")
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 5, "the parent did not enforce its own bound")
        self.assertNotEqual(code, OK, payload)
        self.assertEqual(self.prompts_sent(), [])

    def test_nothing_is_sent_after_the_window_closes(self):
        self.slow_endpoint(1500)
        code, _, _ = self.run_relay(self.request(), 1000, "-ExecuteRequest")
        self.assertNotEqual(code, OK)
        self.assertEqual(self.prompts_sent(), [], "a prompt went out past the deadline")

    def test_the_lock_is_released_when_a_child_call_is_killed(self):
        self.slow_endpoint(4000)
        self.run_relay(self.request(), 1000, "-ExecuteRequest")
        self.assertFalse((self.root / ".local" / "herdr" / "handoff.lock").exists(),
                         "a killed child stranded the global lock")


# ---------------------------------------------------------------------------
# REV-IMP-DEC-2026-0082-r02-r01 findings R1-R5.
#
# R1 is the one worth reading twice: the relay had never run against the real
# endpoint. Every call went through `pwsh -File <endpoint>`, and the installed
# client is herdr.exe, which -File refuses. A .ps1 test double hid it, so the
# fake below is exercised in both shapes and a genuinely native executable is
# used as an endpoint.
# ---------------------------------------------------------------------------


class TestNativeAndScriptEndpoints(RelayCase):
    """R1: a native client is executed, not handed to a script host."""

    HELPERS = ("Get-RemainingMs", "Invoke-Herdr")

    def call_invoke_herdr(self, endpoint, arguments, budget=4000):
        """Drive Invoke-Herdr alone, with no server and no relay entrypoint.

        Arguments travel as JSON: a [string[]] parameter on a command line
        silently binds only its first element, which quietly turned
        `agent list` into `agent` the first time this was written.
        """
        import os as _os

        harness = self.write("invoke-probe.ps1", r"""
param([string]$Relay, [string]$Endpoint, [string]$CallArgsJson, [int]$Budget)
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Relay, [ref]$tokens, [ref]$errors)
foreach ($name in @('Get-RemainingMs', 'Invoke-Herdr')) {
    $definition = $ast.FindAll({param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst]
    }, $false) | Where-Object Name -eq $name
    Invoke-Expression $definition.Extent.Text
}
$script:BudgetMs = $Budget
$script:DeadlineStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$callArgs = [string[]]($CallArgsJson | ConvertFrom-Json)
(Invoke-Herdr -HerdrBin $Endpoint -Arguments $callArgs) | ConvertTo-Json -Depth 10 -Compress
""")
        return subprocess.run(
            [POWERSHELL, "-NoProfile", "-File", str(harness),
             "-Relay", str(RELAY), "-Endpoint", str(endpoint),
             "-CallArgsJson", json.dumps(list(arguments)), "-Budget", str(budget)],
            capture_output=True, text=True, timeout=25,
            env={**_os.environ,
                 "FAKE_HERDR_SCENARIO": str(self.scenario_path),
                 "FAKE_HERDR_LOG": str(self.log)})

    def test_a_native_executable_endpoint_runs(self):
        """The production shape. Python stands in as a local JSON emitter.

        The one-liner deliberately avoids embedded double quotes: Windows
        command-line escaping mangles them through a JSON round-trip, and the
        point here is the process launch, not the quoting of a fixture.
        """
        import sys as _sys
        result = self.call_invoke_herdr(
            _sys.executable,
            ["-c", "import json;print(json.dumps({'result':{'status':'done'}}))"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["result"]["status"], "done")

    def test_a_script_endpoint_still_runs(self):
        """The test-double shape, supported explicitly rather than universally."""
        result = self.call_invoke_herdr(self.fake, ["agent", "list"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("result", json.loads(result.stdout))

    def test_an_endpoint_path_containing_spaces_runs(self):
        """ArgumentList, not a joined string: a quoted path must survive."""
        spaced = self.root / "a folder with spaces"
        spaced.mkdir()
        endpoint = spaced / "fake herdr.ps1"
        endpoint.write_text(self.fake.read_text(encoding="utf-8"), encoding="utf-8")
        result = self.call_invoke_herdr(endpoint, ["agent", "list"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("result", json.loads(result.stdout))

    def test_an_argument_containing_spaces_survives(self):
        """ArgumentList, not a joined string: a spaced argument stays one."""
        import sys as _sys
        result = self.call_invoke_herdr(
            _sys.executable,
            ["-c", "import json;print(json.dumps({'result':{'status':'done with spaces'}}))"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["result"]["status"], "done with spaces")


class TestFullyTypedEvidence(RelayCase):
    """R2: presence was checked, type was not."""

    def test_a_null_collection_is_not_an_empty_collection(self):
        for field in ("inputs", "prerequisites", "ordered_next_steps"):
            with self.subTest(field=field):
                code, payload, _ = self.run_relay(
                    self.request(**{field: None}), 4000, "-ValidateOnly")
                self.assertEqual(code, INVALID, payload)
                self.assertIn(f"{field} must be an array",
                              " ".join(payload.get("problems", [])))

    def test_a_scalar_collection_is_refused(self):
        code, payload, _ = self.run_relay(
            self.request(ordered_next_steps="none"), 4000, "-ValidateOnly")
        self.assertEqual(code, INVALID, payload)

    def test_genuinely_empty_collections_are_allowed(self):
        """A reload-only handoff has no inputs and no onward work."""
        code, payload, err = self.run_relay(self.request(
            inputs=[], prerequisites=[], ordered_next_steps=[],
            prompt="Reload only: read your instructions and acknowledge.",
        ), 4000, "-ValidateOnly")
        self.assertEqual(code, OK, f"{payload} {err}")

    def test_a_socket_other_than_the_inherited_one_is_refused(self):
        """The binary identifies the client; the socket identifies the server."""
        code, payload, _ = self.run_relay(self.request(endpoint={
            "herdr_bin": str(self.fake), "socket_path": "some-other-server",
        }), 4000, "-ValidateOnly")
        self.assertEqual(code, INVALID, payload)
        self.assertIn("is not the inherited socket", " ".join(payload["problems"]))

    def test_a_matching_socket_is_accepted(self):
        import os as _os
        inherited = _os.environ.get("HERDR_SOCKET_PATH")
        if not inherited:
            self.skipTest("no inherited HERDR_SOCKET_PATH in this environment")
        code, payload, err = self.run_relay(self.request(endpoint={
            "herdr_bin": str(self.fake), "socket_path": inherited,
        }), 4000, "-ValidateOnly")
        self.assertEqual(code, OK, f"{payload} {err}")


class TestContainmentSurvivesLinks(RelayCase):
    """R3: a lexical boundary does not follow a junction."""

    def make_junction(self, link, target):
        harness = self.write("junction.ps1",
                             "param([string]$Link, [string]$Target)\n"
                             "New-Item -ItemType Junction -Path $Link -Target $Target | Out-Null\n")
        return subprocess.run([POWERSHELL, "-NoProfile", "-File", str(harness),
                               "-Link", str(link), "-Target", str(target)],
                              capture_output=True, text=True)

    def test_an_input_reached_through_a_junction_is_outside_the_root(self):
        import hashlib
        import os as _os
        import tempfile as _tempfile

        with _tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "external.yaml"
            external.write_text("id: external\n", encoding="utf-8")
            link = self.root / "junction"
            created = self.make_junction(link, outside)
            if created.returncode != 0:
                self.skipTest(f"junction creation unavailable: {created.stderr.strip()}")
            try:
                digest = hashlib.sha256(external.read_bytes()).hexdigest()
                code, payload, _ = self.run_relay(self.request(inputs=[{
                    "id": "external", "path": "junction/external.yaml",
                    "checksum": f"sha256:{digest}",
                }]), 4000, "-ValidateOnly")
                self.assertEqual(code, INVALID, payload)
            finally:
                # Remove the junction only, never what it points at.
                _os.rmdir(link)

    def test_an_ordinary_nested_input_still_resolves(self):
        """The guard must not reject honest subdirectories."""
        import hashlib
        nested = self.write("deeply/nested/input.yaml", "id: nested\n")
        digest = hashlib.sha256(nested.read_bytes()).hexdigest()
        code, payload, err = self.run_relay(self.request(inputs=[{
            "id": "nested", "path": "deeply/nested/input.yaml",
            "checksum": f"sha256:{digest}",
        }]), 4000, "-ValidateOnly")
        self.assertEqual(code, OK, f"{payload} {err}")


class TestScheduleToExecuteChain(RelayCase):
    """R4: the whole chain, including real concurrency and continuation."""

    def slow_prompt_endpoint(self, milliseconds=3000):
        text = self.fake.read_text(encoding="utf-8")
        marker = "if ($CliArgs[0] -eq 'agent' -and $CliArgs[1] -eq 'prompt') {"
        self.fake.write_text(
            text.replace(marker, marker + f"\nStart-Sleep -Milliseconds {milliseconds}"),
            encoding="utf-8")

    def start_execute(self, request_path, timeout_ms=8000):
        """Begin a deferred phase in the background, reservation included."""
        import os as _os
        self.ensure_reserved(request_path)
        process = subprocess.Popen(
            [POWERSHELL, "-NoLogo", "-NonInteractive", "-NoProfile", "-File", str(RELAY),
             "-RequestPath", str(request_path), "-TimeoutMs", str(timeout_ms),
             "-ExecuteRequest"],
            cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={**_os.environ, "FAKE_HERDR_SCENARIO": str(self.scenario_path),
                 "FAKE_HERDR_LOG": str(self.log), "HERDR_BIN_PATH": str(self.fake)})
        deadline = time.monotonic() + 6
        while not self.prompts_sent() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(self.prompts_sent(), "the first prompt never began")
        return process

    def test_a_scheduled_request_is_delivered_by_its_own_relay(self):
        """Schedule, then let the detached relay do the whole deferred phase."""
        code, payload, err = self.run_relay(self.request(), 8000)
        self.assertEqual(code, OK, f"{payload} {err}")
        self.assertEqual(payload["status"], "queued")
        record = self.wait_for_relay(seconds=25)
        self.assertEqual(record["state"], "settled", record)
        self.assertEqual(len(self.prompts_sent()), 1)

    def test_two_concurrent_relays_prompt_exactly_once(self):
        self.slow_prompt_endpoint()
        first = self.start_execute(self.request())
        try:
            competitor = self.request(request_id="competitor")
            code, payload, _ = self.run_relay(competitor, 4000, "-ExecuteRequest")
            self.assertEqual(code, NOT_READY, payload)
            self.assertEqual(len(self.prompts_sent()), 1, "two relays prompted at once")
        finally:
            first.communicate(timeout=20)

    def test_an_interrupted_relay_leaves_possible_send_evidence(self):
        self.slow_prompt_endpoint()
        path = self.request()
        first = self.start_execute(path)
        first.terminate()
        first.communicate(timeout=20)
        self.assertEqual(self.state()["state"], "submitting")
        # A retry must neither resend nor erase the warning.
        before = len(self.prompts_sent())
        self.run_relay(path, 4000, "-ExecuteRequest")
        self.assertIn(self.state()["state"], ("submitting", "uncertain"))
        self.assertEqual(len(self.prompts_sent()), before, "an interrupted send was repeated")

    def test_a_finishing_recipient_may_stage_its_continuation(self):
        """The chain depends on this: a parent holding the lock must not stop
        its recipient from queueing the next assignment."""
        self.write(".local/herdr/requests/parent.state.json", json.dumps({
            "request_id": "parent", "state": "submitting",
            "recipient_pane": self.SENDER_PANE,
        }))
        (self.root / ".local" / "herdr" / "handoff.lock").write_text(
            json.dumps({"request_id": "parent", "pid": 0}), encoding="utf-8")
        self.set_scenario(self.frame(sender="working"))
        code, payload, err = self.run_relay(self.request(), 1000)
        self.assertEqual(code, OK, f"{payload} {err}")
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(self.prompts_sent(), [], "staging must not deliver")
        self.wait_for_relay(seconds=10)

    def test_an_independent_competitor_may_not_stage(self):
        """Only the parent's own recipient continues; others still wait."""
        self.write(".local/herdr/requests/parent.state.json", json.dumps({
            "request_id": "parent", "state": "submitting",
            "recipient_pane": "w1:p9",
        }))
        code, payload, _ = self.run_relay(self.request(), 4000)
        self.assertEqual(code, NOT_READY, payload)
        self.assertIn("outstanding", " ".join(payload["problems"]))

    def test_an_uncertain_predecessor_blocks_even_a_continuation(self):
        self.write(".local/herdr/requests/parent.state.json", json.dumps({
            "request_id": "parent", "state": "uncertain",
            "recipient_pane": self.SENDER_PANE,
        }))
        code, payload, _ = self.run_relay(self.request(), 4000)
        self.assertEqual(code, NOT_READY, payload)
        self.assertIn("uncertain", " ".join(payload["problems"]))

    def test_execution_without_a_reservation_is_refused(self):
        """Authorization is never created merely because no record exists."""
        path = self.request()
        code, payload, _ = self.run_relay_unreserved(path, 4000, "-ExecuteRequest")
        self.assertEqual(code, INVALID, payload)
        self.assertIn("no queued reservation", " ".join(payload["problems"]))
        self.assertEqual(self.prompts_sent(), [])

    def test_a_concurrent_reservation_wins_only_once(self):
        """CreateNew makes the claim its own test; check-then-write does not."""
        self.set_scenario(self.frame(sender="working"))
        first, payload, err = self.run_relay(self.request(), 1000)
        self.assertEqual(first, OK, f"{payload} {err}")
        second, payload, _ = self.run_relay(self.request(), 1000)
        self.assertEqual(second, INVALID, payload)
        self.assertIn("duplicate ID cannot resubmit", " ".join(payload["problems"]))
        self.wait_for_relay(seconds=10)


class TestSenderStatusIsVerified(RelayCase):
    """R5: only a working sender is waited for."""

    def test_a_blocked_sender_stops_rather_than_being_waited_out(self):
        """A later idle observation must not resume a blocked request."""
        self.set_scenario(self.frame(sender="blocked"), self.frame(sender="idle"))
        code, payload, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
        self.assertEqual(code, INVALID, payload)
        self.assertEqual(self.prompts_sent(), [])
        self.assertIn("neither settled nor working", " ".join(payload["problems"]))
        self.assertEqual(self.state()["state"], "failed")

    def test_an_unknown_sender_status_stops(self):
        for status in ("unknown", "starting", ""):
            with self.subTest(status=status):
                self.set_scenario(self.frame(sender=status), self.frame(sender="idle"))
                code, payload, _ = self.run_relay(self.request(), 4000, "-ExecuteRequest")
                self.assertEqual(code, INVALID, payload)
                self.assertEqual(self.prompts_sent(), [])

    def test_a_working_sender_is_still_waited_for(self):
        """The narrowing must not break the ordinary case."""
        self.set_scenario(
            self.frame(sender="working"), self.frame(sender="working"),
            self.frame(sender="idle"))
        code, payload, err = self.run_relay(self.request(), 8000, "-ExecuteRequest")
        self.assertEqual(code, OK, f"{payload} {err}")
        self.assertEqual(len(self.prompts_sent()), 1)


class TestTheRelayIsDeclaredByTheDecision(unittest.TestCase):
    """The path and owner come from DEC-2026-0082, not from this test."""

    def test_the_relay_exists_at_the_path_the_decision_assigns(self):
        import yaml

        decision = yaml.safe_load(
            (REPO_ROOT / "rulesets/adnd1e/escalations/decisions/DEC-2026-0082.yaml")
            .read_text(encoding="utf-8"))
        declared = decision["relay_requirements"]["path"]
        self.assertEqual(declared, "tooling/common/send-agent-handoff.ps1")
        self.assertTrue((REPO_ROOT / declared).is_file())
        owners = {entry["path"]: entry["owner"] for entry in decision["exact_diff_ownership"]}
        self.assertEqual(owners[declared], "builder")

    def test_the_relay_requires_powershell_7(self):
        text = (REPO_ROOT / "tooling/common/send-agent-handoff.ps1").read_text(encoding="utf-8")
        self.assertIn("#Requires -Version 7.0", text)


if __name__ == "__main__":
    unittest.main()
