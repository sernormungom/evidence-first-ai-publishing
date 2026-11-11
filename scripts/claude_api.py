#!/usr/bin/env python3
"""
Shared Claude call for draft.py, translate.py and translate_policy.py.

Two interchangeable backends, selected by HANDBOOK_BACKEND:

  api  (default)  Raw HTTP to the Messages API, as the pipeline has always
                  used. Needs ANTHROPIC_API_KEY. This is what CI would use.
  cli             Shells out to the Claude Code CLI (`claude -p`), which uses
                  the credentials of whoever is signed in to Claude Code —
                  no API key to obtain or manage. For a maintainer's laptop.

Both return the same response shape, so callers are backend-agnostic. The
model is pinned by HANDBOOK_MODEL either way.

Callers must check `incomplete_reason()` before writing anything: a truncated
or declined response is never written or stamped, so the existing file stays
intact.

Differences in `cli` mode, kept deliberate and visible:
  - `max_tokens` cannot be set; the CLI's own output limit applies. A cut-off
    response is still detected through stop_reason.
  - The CLI is run from an empty directory with no tools, so no CLAUDE.md,
    project files or user memory can reach the prompt. (Verify after a CLI
    upgrade: scripts/tests/test_claude_backends.py documents the check.)
  - Claude Code may use a small auxiliary model for its own bookkeeping; the
    drafting itself runs on HANDBOOK_MODEL. `usage_note()` reports what ran.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import uuid
import datetime

# Model strings change over time — check https://docs.claude.com for current
# ones. Overridable so the scripts don't need editing when they do.
MODEL = os.environ.get("HANDBOOK_MODEL", "claude-sonnet-5")
BACKEND = os.environ.get("HANDBOOK_BACKEND", "api").strip().lower()
API_URL = "https://api.anthropic.com/v1/messages"
CLI = os.environ.get("HANDBOOK_CLI", "claude")
BACKENDS = ("api", "cli")
COMPLETE_STOP_REASONS = {"end_turn", "stop_sequence"}


def _check_backend():
    if BACKEND not in BACKENDS:
        sys.exit(f"HANDBOOK_BACKEND={BACKEND!r} is not one of {BACKENDS}.")


def cli_path():
    """Absolute path to the Claude Code CLI, or None if it is not installed."""
    return shutil.which(CLI)


def require_credentials():
    """Exit before any work is written if the backend cannot run."""
    _check_backend()
    if BACKEND == "cli":
        path = cli_path()
        if path is None:
            sys.exit(f"HANDBOOK_BACKEND=cli but {CLI!r} is not on PATH. Nothing was "
                     f"written. Install Claude Code, or unset HANDBOOK_BACKEND to use "
                     f"the API with ANTHROPIC_API_KEY.")
        return path
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ANTHROPIC_API_KEY is not set. Nothing was written. "
                 "(Use --dry-run to build the prompt without calling Claude, or set "
                 "HANDBOOK_BACKEND=cli to use the Claude Code CLI instead.)")
    return key


def describe_backend():
    return f"{MODEL} via the {'Claude Code CLI' if BACKEND == 'cli' else 'Messages API'}"


def create_message(*, system: str, user_msg: str, max_tokens: int = 8000,
                   timeout: int = 180, effort=None) -> dict:
    """One invocation, no retries/continuations; optionally retain exact payload/result."""
    _check_backend()
    if effort is not None and effort not in ('low', 'medium', 'high'):
        raise ValueError('Unsupported effort; use low, medium or high')
    capture = os.environ.get('HANDBOOK_CAPTURE_DIR')
    path = None
    if capture:
        directory = Path(capture)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')
                            + '-' + uuid.uuid4().hex[:8])
        Path(str(path) + '.request.json').write_text(json.dumps({
            'backend': BACKEND, 'model': MODEL, 'effort': effort,
            'max_tokens': max_tokens if BACKEND == 'api' else None,
            'timeout': timeout, 'system': system, 'user_msg': user_msg,
            'automatic_retries': 0, 'automatic_continuations': 0}, ensure_ascii=False))
    try:
        if BACKEND == 'cli':
            kwargs = {'effort': effort} if effort is not None else {}
            result = _create_message_cli(system=system, user_msg=user_msg, timeout=timeout, **kwargs)
        else:
            result = _create_message_api(system=system, user_msg=user_msg,
                                        max_tokens=max_tokens, timeout=timeout, effort=effort)
    except (Exception, SystemExit) as exc:
        if path:
            Path(str(path) + '.error.json').write_text(json.dumps({
                'outcome': 'failed_or_unknown', 'error': str(exc)}))
        raise
    if path:
        Path(str(path) + '.response.json').write_text(json.dumps(result, ensure_ascii=False))
        print(f'   Capture → {path}')
    return result


def _create_message_api(*, system, user_msg, max_tokens, timeout, effort=None) -> dict:
    import requests  # only needed for this backend

    payload = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user_msg}],
    }
    if effort is not None:
        payload["output_config"] = {"effort": effort}
    headers = {
        "x-api-key": require_credentials(),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    resp = requests.post(API_URL, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except json.JSONDecodeError:
            detail = resp.text
        raise SystemExit(f"Anthropic API error ({resp.status_code}): {detail}")
    return resp.json()


def cli_command(system, effort=None):
    """The argv used in cli mode (also asserted by the tests)."""
    return [require_credentials(), "--print",
            "--max-turns", "1",
            *(["--effort", effort] if effort else []),
            "--model", MODEL,
            "--output-format", "json",
            # Replace Claude Code's own system prompt with ours. Safe mode
            # disables discovered instructions, memory, skills and hooks
            # while retaining the maintainer's signed-in authentication.
            "--system-prompt", system,
            "--safe-mode",
            # Pure text generation: the model gets no tools at all.
            "--tools", "",
            "--strict-mcp-config"]


def _create_message_cli(*, system, user_msg, timeout, effort=None) -> dict:
    cmd = cli_command(system, effort)
    # An empty cwd keeps CLAUDE.md, repository files and user memory out of
    # the prompt, so the draft depends only on the attached sources.
    with tempfile.TemporaryDirectory(prefix="handbook-claude-") as neutral:
        try:
            proc = subprocess.run(cmd, input=user_msg, cwd=neutral, text=True,
                                  capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise SystemExit(f"Claude Code CLI timed out after {timeout}s. Nothing was written.")
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        # JSON failures can put the useful error after a large usage record.
        # Show the error/result, rather than truncating away its explanation.
        if not proc.stderr:
            try:
                failed = json.loads(proc.stdout)
                detail = failed.get("result") or failed.get("error") or detail
                if not isinstance(detail, str):
                    detail = json.dumps(detail)
            except (json.JSONDecodeError, AttributeError):
                pass
        raise SystemExit(f"Claude Code CLI failed (exit {proc.returncode}): "
                         f"{detail[:500]}")
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise SystemExit(f"Claude Code CLI returned unreadable output: {proc.stdout[:500]}")
    return _cli_to_api_shape(out)


def _cli_to_api_shape(out: dict) -> dict:
    """Map the CLI's result JSON onto the Messages API response shape."""
    if out.get("is_error") or out.get("subtype") not in (None, "success"):
        detail = out.get("api_error_status") or out.get("subtype") or "unknown error"
        raise SystemExit(f"Claude Code CLI reported an error: {detail}")
    stop_reason = out.get("stop_reason")
    if stop_reason is None:
        # Older CLIs omit stop_reason; fall back to its completion fields.
        stop_reason = "end_turn" if out.get("terminal_reason") == "completed" else "unknown"
    return {
        "content": [{"type": "text", "text": out.get("result") or ""}],
        "stop_reason": stop_reason,
        "stop_details": out.get("stop_details"),
        "usage": out.get("usage"),
        "_cli_raw": out,
        "_cli": {"models": sorted(out.get("modelUsage") or {}),
                 "cost_usd": out.get("total_cost_usd"),
                 "session_id": out.get("session_id")},
    }


def usage_note(resp: dict):
    """One line describing what actually ran, or None for the API backend."""
    cli = resp.get("_cli")
    if not cli:
        return None
    models = ", ".join(cli["models"]) or MODEL
    cost = cli.get("cost_usd")
    note = f"Claude Code CLI · models used: {models}"
    if cost is not None:
        note += f" · estimated equivalent API cost ${cost:.2f}"
    return note


def unwrap_fences(text):
    """Undo the two ways a model wraps a Markdown file it was asked to output:
    a leading title line before the frontmatter, and a ```yaml / ```markdown
    fence around it. Anything else is rejected rather than repaired."""
    text = re.sub(r"\A(?:#[^\n]*\n+)?```(?:ya?ml|markdown|md)?\n(---\n.*?\n---)\n```\n*",
                  r"\1\n\n", text, count=1, flags=re.S)
    text = re.sub(r"\A#[^\n]*\n+(?=---\n)", "", text, count=1)
    # A duplicated '# Title' right after the frontmatter is the usual leftover.
    fm_end = text.find("\n---", 3)
    if text.startswith("---") and fm_end != -1:
        head, body = text[:fm_end + 4], text[fm_end + 4:]
        body = re.sub(r"\A\s*(#[^\n]*)\n+(?=\1\n)", "", body, count=1)
        text = head + body
    return text.strip()


def response_text(resp: dict) -> str:
    return "".join(block.get("text", "") for block in resp.get("content", [])
                   if block.get("type") == "text")


def incomplete_reason(resp: dict):
    """None if the response finished normally, else a human-readable reason."""
    reason = resp.get("stop_reason")
    if reason in COMPLETE_STOP_REASONS:
        return None
    if reason == "max_tokens":
        return "the response was cut off (max_tokens)"
    if reason == "refusal":
        category = (resp.get("stop_details") or {}).get("category")
        return f"the model declined the request (refusal{', ' + category if category else ''})"
    return f"unexpected stop_reason {reason!r}"
