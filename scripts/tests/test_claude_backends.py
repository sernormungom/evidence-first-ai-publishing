"""Tests for the two Claude backends in scripts/claude_api.py.

No real calls: the CLI subprocess and the HTTP post are both mocked.

The one thing these tests cannot prove is that the Claude Code CLI keeps
honouring the isolation flags. After a CLI upgrade, re-run this by hand from
an empty directory and expect a "NO" answer:

    printf 'Do you have a CLAUDE.md, repository or user memory in context? YES or NO.' | \\
      claude -p --model claude-sonnet-5 --output-format json \\
        --system-prompt 'Answer factually.' \\
        --safe-mode --tools '' --strict-mcp-config
"""
import json
import pathlib
import subprocess
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import claude_api as ca  # noqa: E402

CLI_SUCCESS = {
    "result": "Drafted text.", "stop_reason": "end_turn", "is_error": False,
    "subtype": "success", "terminal_reason": "completed",
    "modelUsage": {"claude-sonnet-5": {}, "claude-haiku-5-5": {}},
    "total_cost_usd": 0.0412, "session_id": "abc", "usage": {"input_tokens": 10},
}


def run_cli(payload, **kw):
    """Call the CLI backend with a mocked subprocess; returns (response, call)."""
    completed = subprocess.CompletedProcess(
        args=[], returncode=kw.pop("returncode", 0),
        stdout=payload if isinstance(payload, str) else json.dumps(payload),
        stderr=kw.pop("stderr", ""))
    with mock.patch.object(ca.shutil, "which", return_value="/fake/claude"), \
            mock.patch.object(ca.subprocess, "run", return_value=completed) as run, \
            mock.patch.object(ca, "BACKEND", "cli"):
        resp = ca.create_message(system="SYS", user_msg="USER", max_tokens=16000, timeout=42)
    return resp, run.call_args


class CliCommand(unittest.TestCase):
    def test_prompt_isolation_flags(self):
        with mock.patch.object(ca.shutil, "which", return_value="/fake/claude"), \
                mock.patch.object(ca, "BACKEND", "cli"):
            cmd = ca.cli_command("SYSTEM TEXT")
        self.assertEqual(cmd[0], "/fake/claude")
        self.assertIn("--print", cmd)
        self.assertEqual(cmd[cmd.index("--max-turns") + 1], "1")
        self.assertEqual(cmd[cmd.index("--model") + 1], ca.MODEL)
        self.assertEqual(cmd[cmd.index("--output-format") + 1], "json")
        # Our prompt replaces Claude Code's own, with no dynamic sections …
        self.assertEqual(cmd[cmd.index("--system-prompt") + 1], "SYSTEM TEXT")
        self.assertIn("--safe-mode", cmd)
        self.assertIn("--strict-mcp-config", cmd)
        self.assertNotIn("--append-system-prompt", cmd)
        # … and the model gets no tools, so it cannot read the repository.
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")

    def test_runs_in_an_empty_directory_outside_the_repo(self):
        _, call = run_cli(CLI_SUCCESS)
        cwd = pathlib.Path(call.kwargs["cwd"])
        self.assertTrue(cwd.is_absolute())
        self.assertNotIn(ROOT, [cwd, *cwd.parents])  # not the handbook repo
        self.assertEqual(call.kwargs["input"], "USER")  # prompt via stdin, not argv

    def test_temporary_directory_is_cleaned_up(self):
        _, call = run_cli(CLI_SUCCESS)
        self.assertFalse(pathlib.Path(call.kwargs["cwd"]).exists())


class CliResponseMapping(unittest.TestCase):
    def test_success_maps_to_api_shape(self):
        resp, _ = run_cli(CLI_SUCCESS)
        self.assertEqual(ca.response_text(resp), "Drafted text.")
        self.assertIsNone(ca.incomplete_reason(resp))
        self.assertIn("claude-sonnet-5", ca.usage_note(resp))
        self.assertIn("$0.04", ca.usage_note(resp))

    def test_truncation_and_refusal_are_detected(self):
        resp, _ = run_cli({**CLI_SUCCESS, "stop_reason": "max_tokens"})
        self.assertIn("cut off", ca.incomplete_reason(resp))
        resp, _ = run_cli({**CLI_SUCCESS, "stop_reason": "refusal",
                           "stop_details": {"category": "general_harms"}})
        self.assertIn("declined", ca.incomplete_reason(resp))

    def test_missing_stop_reason_falls_back_to_terminal_reason(self):
        payload = {k: v for k, v in CLI_SUCCESS.items() if k != "stop_reason"}
        self.assertIsNone(ca.incomplete_reason(run_cli(payload)[0]))
        resp, _ = run_cli({**payload, "terminal_reason": "interrupted"})
        self.assertIn("unexpected stop_reason", ca.incomplete_reason(resp))

    def test_failures_raise_before_anything_is_written(self):
        cases = [
            ({**CLI_SUCCESS, "is_error": True, "api_error_status": "429"}, "429"),
            ({**CLI_SUCCESS, "subtype": "error_max_turns"}, "error_max_turns"),
            ("not json at all", "unreadable output"),
        ]
        for payload, expected in cases:
            with self.subTest(expected), self.assertRaises(SystemExit) as cm:
                run_cli(payload)
            self.assertIn(expected, str(cm.exception))

    def test_nonzero_exit_and_timeout_raise(self):
        with self.assertRaises(SystemExit) as cm:
            run_cli(CLI_SUCCESS, returncode=1, stderr="not signed in")
        self.assertIn("not signed in", str(cm.exception))
        with mock.patch.object(ca.shutil, "which", return_value="/fake/claude"), \
                mock.patch.object(ca, "BACKEND", "cli"), \
                mock.patch.object(ca.subprocess, "run",
                                  side_effect=subprocess.TimeoutExpired("claude", 42)):
            with self.assertRaises(SystemExit) as cm:
                ca.create_message(system="S", user_msg="U", timeout=42)
        self.assertIn("timed out", str(cm.exception))

    def test_json_exit_failure_preserves_the_error_after_usage_metadata(self):
        payload = {"usage": {"metadata": "x" * 1000},
                   "result": "Authentication is unavailable.", "is_error": True}
        with self.assertRaises(SystemExit) as cm:
            run_cli(payload, returncode=1)
        self.assertIn("Authentication is unavailable.", str(cm.exception))


class Credentials(unittest.TestCase):
    def test_cli_backend_needs_the_binary_not_a_key(self):
        with mock.patch.object(ca, "BACKEND", "cli"), \
                mock.patch.dict(ca.os.environ, {}, clear=True), \
                mock.patch.object(ca.shutil, "which", return_value="/fake/claude"):
            self.assertEqual(ca.require_credentials(), "/fake/claude")  # no API key needed
        with mock.patch.object(ca, "BACKEND", "cli"), \
                mock.patch.object(ca.shutil, "which", return_value=None):
            with self.assertRaises(SystemExit) as cm:
                ca.require_credentials()
        self.assertIn("not on PATH", str(cm.exception))

    def test_api_backend_still_needs_a_key(self):
        with mock.patch.object(ca, "BACKEND", "api"), \
                mock.patch.dict(ca.os.environ, {}, clear=True):
            with self.assertRaises(SystemExit) as cm:
                ca.require_credentials()
        self.assertIn("ANTHROPIC_API_KEY is not set", str(cm.exception))
        self.assertIn("HANDBOOK_BACKEND=cli", str(cm.exception))

    def test_unknown_backend_is_rejected(self):
        with mock.patch.object(ca, "BACKEND", "openai"):
            with self.assertRaises(SystemExit) as cm:
                ca.require_credentials()
        self.assertIn("not one of", str(cm.exception))

    def test_default_backend_is_the_api(self):
        """The plan keeps the existing provider; the CLI is opt-in."""
        env = {k: v for k, v in ca.os.environ.items() if k != "HANDBOOK_BACKEND"}
        with mock.patch.dict(ca.os.environ, env, clear=True):
            import importlib
            self.assertEqual(importlib.reload(ca).BACKEND, "api")
        importlib.reload(ca)  # restore this session's environment


class ApiBackend(unittest.TestCase):
    def test_api_backend_posts_the_pinned_model_and_system_prompt(self):
        import requests
        response = mock.Mock(status_code=200)
        response.json.return_value = {"content": [{"type": "text", "text": "hi"}],
                                      "stop_reason": "end_turn"}
        with mock.patch.object(ca, "BACKEND", "api"), \
                mock.patch.dict(ca.os.environ, {"ANTHROPIC_API_KEY": "k"}), \
                mock.patch.object(requests, "post", return_value=response) as post:
            resp = ca.create_message(system="SYS", user_msg="USER", max_tokens=16000)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], ca.MODEL)
        self.assertEqual(payload["system"], "SYS")
        self.assertEqual(payload["max_tokens"], 16000)
        self.assertEqual(ca.response_text(resp), "hi")
        self.assertIsNone(ca.usage_note(resp))  # no CLI note on the API path


if __name__ == "__main__":
    unittest.main()
