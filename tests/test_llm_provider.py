"""LLM provider: JSON extraction and a fully-mocked CLI boundary (no subprocess)."""

from __future__ import annotations

import json
import subprocess
import types

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


def fake_run_factory(stdout="", returncode=0, stderr="", raises=None):
    captured = {}

    def fake_run(cmd, input=None, capture_output=None, text=None, timeout=None):
        captured["cmd"] = cmd
        captured["input"] = input
        captured["timeout"] = timeout
        if raises is not None:
            raise raises
        return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    fake_run.captured = captured
    return fake_run


def test_generate_returns_envelope_result(monkeypatch):
    envelope = json.dumps({"is_error": False, "result": "hello world"})
    fake = fake_run_factory(stdout=envelope)
    monkeypatch.setattr(provider.subprocess, "run", fake)
    out = ClaudeCodeProvider().generate("hi")
    assert out == "hello world"
    # Sanity: it shelled out to the configured binary in headless print mode.
    assert fake.captured["cmd"][:3] == ["claude", "-p", "--output-format"]
    assert fake.captured["input"] == "hi"


def test_generate_raises_on_nonzero_exit(monkeypatch):
    fake = fake_run_factory(returncode=1, stderr="boom")
    monkeypatch.setattr(provider.subprocess, "run", fake)
    with pytest.raises(LLMError, match="failed"):
        ClaudeCodeProvider().generate("hi")


def test_generate_raises_on_non_json_output(monkeypatch):
    fake = fake_run_factory(stdout="not-json")
    monkeypatch.setattr(provider.subprocess, "run", fake)
    with pytest.raises(LLMError, match="non-JSON"):
        ClaudeCodeProvider().generate("hi")


def test_generate_raises_when_envelope_is_error(monkeypatch):
    envelope = json.dumps({"is_error": True, "result": "rate limited"})
    fake = fake_run_factory(stdout=envelope)
    monkeypatch.setattr(provider.subprocess, "run", fake)
    with pytest.raises(LLMError, match="error"):
        ClaudeCodeProvider().generate("hi")


def test_generate_raises_on_timeout(monkeypatch):
    fake = fake_run_factory(raises=subprocess.TimeoutExpired(cmd="claude", timeout=1))
    monkeypatch.setattr(provider.subprocess, "run", fake)
    with pytest.raises(LLMError, match="timed out"):
        ClaudeCodeProvider().generate("hi", timeout=1)


def test_generate_json_parses_result(monkeypatch):
    inner = '```json\n{"sessions": 3}\n```'
    envelope = json.dumps({"is_error": False, "result": inner})
    fake = fake_run_factory(stdout=envelope)
    monkeypatch.setattr(provider.subprocess, "run", fake)
    out = ClaudeCodeProvider().generate_json("plan it", schema={"type": "object"})
    assert out == {"sessions": 3}
    # The JSON schema instruction is appended to the prompt sent to the CLI.
    assert "JSON" in fake.captured["input"]


def test_generate_json_raises_on_unparseable(monkeypatch):
    envelope = json.dumps({"is_error": False, "result": "no json here"})
    fake = fake_run_factory(stdout=envelope)
    monkeypatch.setattr(provider.subprocess, "run", fake)
    with pytest.raises(LLMError, match="valid JSON"):
        ClaudeCodeProvider().generate_json("x", schema={})


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError):
        provider.get_provider("nope")
