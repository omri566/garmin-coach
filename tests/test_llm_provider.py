"""LLM provider: JSON extraction and a mocked CLI boundary (no real subprocess).

The CLI is exercised at the `_exec` seam — the method that actually spawns the
process — so the tests cover argv construction + envelope handling without a real
`claude`. One real-subprocess test (`/bin/sleep`) covers the timeout + process-
group kill path, which is the whole point of the file-backed `_exec` rewrite.
"""

from __future__ import annotations

import json
import time

import pytest

from garmin_coach.llm import provider
from garmin_coach.llm.provider import ClaudeCodeProvider, LLMError, _extract_json

# --- _extract_json ----------------------------------------------------------


def test_extract_plain_object():
    assert _extract_json('{"a": 1, "b": [2, 3]}') == {"a": 1, "b": [2, 3]}


def test_extract_plain_array():
    assert _extract_json("[1, 2, 3]") == [1, 2, 3]


def test_extract_from_json_fence():
    text = 'Sure!\n```json\n{"plan": "easy"}\n```\nHope that helps.'
    assert _extract_json(text) == {"plan": "easy"}


def test_extract_from_bare_fence():
    text = '```\n{"k": 9}\n```'
    assert _extract_json(text) == {"k": 9}


def test_extract_ignores_surrounding_prose():
    assert _extract_json('Here is the result: {"ok": true} — done.') == {"ok": True}


def test_extract_malformed_raises():
    with pytest.raises(json.JSONDecodeError):
        _extract_json("this is not json at all")


# --- ClaudeCodeProvider with a mocked subprocess ----------------------------


def fake_exec_factory(stdout="", returncode=0, stderr="", raises=None):
    """Patch ClaudeCodeProvider._exec — the process-spawning seam — so tests never
    launch a real `claude`. Returns the (rc, stdout, stderr, elapsed) tuple _run
    expects, or raises."""
    captured = {}

    def fake_exec(self, cmd, prompt, timeout):
        captured["cmd"] = cmd
        captured["prompt"] = prompt
        captured["timeout"] = timeout
        if raises is not None:
            raise raises
        return returncode, stdout, stderr, 0.01

    fake_exec.captured = captured
    return fake_exec


def test_generate_returns_envelope_result(monkeypatch):
    envelope = json.dumps({"is_error": False, "result": "hello world"})
    fake = fake_exec_factory(stdout=envelope)
    monkeypatch.setattr(ClaudeCodeProvider, "_exec", fake)
    out = ClaudeCodeProvider().generate("hi")
    assert out == "hello world"
    # Sanity: it shelled out to the resolved claude binary in headless print mode.
    cmd = fake.captured["cmd"]
    assert cmd[0].split("/")[-1] == "claude"
    assert cmd[1:3] == ["-p", "--output-format"]
    assert fake.captured["prompt"] == "hi"


def test_generate_raises_on_nonzero_exit(monkeypatch):
    fake = fake_exec_factory(returncode=1, stderr="boom")
    monkeypatch.setattr(ClaudeCodeProvider, "_exec", fake)
    with pytest.raises(LLMError, match="failed"):
        ClaudeCodeProvider().generate("hi")


def test_generate_raises_on_non_json_output(monkeypatch):
    fake = fake_exec_factory(stdout="not-json")
    monkeypatch.setattr(ClaudeCodeProvider, "_exec", fake)
    with pytest.raises(LLMError, match="non-JSON"):
        ClaudeCodeProvider().generate("hi")


def test_generate_raises_when_envelope_is_error(monkeypatch):
    envelope = json.dumps({"is_error": True, "result": "rate limited"})
    fake = fake_exec_factory(stdout=envelope)
    monkeypatch.setattr(ClaudeCodeProvider, "_exec", fake)
    with pytest.raises(LLMError, match="error"):
        ClaudeCodeProvider().generate("hi")


def test_generate_json_parses_result(monkeypatch):
    inner = '```json\n{"sessions": 3}\n```'
    envelope = json.dumps({"is_error": False, "result": inner})
    fake = fake_exec_factory(stdout=envelope)
    monkeypatch.setattr(ClaudeCodeProvider, "_exec", fake)
    out = ClaudeCodeProvider().generate_json("plan it", schema={"type": "object"})
    assert out == {"sessions": 3}
    # The JSON schema instruction is appended to the prompt sent to the CLI.
    assert "JSON" in fake.captured["prompt"]


def test_generate_json_raises_on_unparseable(monkeypatch):
    envelope = json.dumps({"is_error": False, "result": "no json here"})
    fake = fake_exec_factory(stdout=envelope)
    monkeypatch.setattr(ClaudeCodeProvider, "_exec", fake)
    with pytest.raises(LLMError, match="valid JSON"):
        ClaudeCodeProvider().generate_json("x", schema={})


# --- The real _exec: timeout + kill, and a lingering child can't wedge it ----


def test_exec_times_out_and_kills(monkeypatch):
    """A process that outlives the timeout is killed and surfaced as an LLMError —
    exercised against a real /bin/sleep, not a mock, so the file-backed wait +
    process-group kill actually run."""
    p = ClaudeCodeProvider(binary="/bin/sleep")
    t0 = time.monotonic()
    with pytest.raises(LLMError, match="timed out after 1s"):
        p._exec(["/bin/sleep", "30"], prompt="", timeout=1)
    # Returned promptly at the timeout, not after the full 30s sleep.
    assert time.monotonic() - t0 < 10


def test_exec_returns_output_even_if_a_child_holds_the_pipe():
    """The regression that motivated this rewrite: the CLI prints its result and
    exits, but a forked child keeps stdout/stderr open. With pipe capture the read
    would block until the timeout; capturing to files, _exec returns as soon as the
    main process exits — the leftover child can't wedge it."""
    # sh prints, then backgrounds a child that holds stdout open for 30s and exits.
    script = 'printf hello; sleep 30 & exit 0'
    p = ClaudeCodeProvider(binary="/bin/sh")
    t0 = time.monotonic()
    rc, out, err, elapsed = p._exec(["/bin/sh", "-c", script], prompt="", timeout=15)
    assert rc == 0
    assert out == "hello"
    assert time.monotonic() - t0 < 10        # did NOT wait on the lingering child


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError):
        provider.get_provider("nope")
