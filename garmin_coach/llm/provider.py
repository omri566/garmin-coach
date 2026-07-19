"""LLM provider abstraction — backend-agnostic text/JSON generation.

Default backend shells out to the **Claude Code CLI** in headless mode
(`claude -p ... --output-format json`), which runs on the user's existing Claude
Code subscription — no API key required. Swap to an API-key backend later by
adding a provider with the same interface; callers never change.

The model only ever sees computed summaries/trends (passed in the prompt), never
raw per-second rows — token control is the caller's responsibility.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from typing import Any

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


def _extract_json(text: str) -> Any:
    """Pull a JSON value out of a model response (tolerating prose / ``` fences)."""
    t = text.strip()
    if "```" in t:  # strip a fenced code block
        parts = t.split("```")
        for part in parts:
            p = part.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{") or p.startswith("["):
                t = p
                break
    # Fall back to the outermost {...} or [...] span.
    for open_c, close_c in (("{", "}"), ("[", "]")):
        s, e = t.find(open_c), t.rfind(close_c)
        if 0 <= s < e:
            try:
                return json.loads(t[s:e + 1])
            except json.JSONDecodeError:
                continue
    return json.loads(t)  # last resort: raises with context


_JSON_INSTRUCTION = (
    "\n\nRespond with ONLY a single JSON value matching this schema — no prose, "
    "no markdown fences:\n{schema}"
)


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, system: str | None = None,
                 model: str | None = None, allow_web: bool = False,
                 timeout: int = 600) -> str:
        ...

    @abstractmethod
    def generate_json(self, prompt: str, schema: dict[str, Any],
                      system: str | None = None, model: str | None = None,
                      allow_web: bool = False, timeout: int = 600) -> dict[str, Any]:
        ...


class ClaudeCodeProvider(LLMProvider):
    """Runs the local `claude` CLI in headless print mode."""

    def __init__(self, binary: str | None = None, default_model: str | None = None):
        # Resolve the real binary path — a Finder-launched .app has a minimal PATH
        # that usually omits Homebrew/npm, so plain "claude" wouldn't be found.
        if not binary:
            from garmin_coach.setup import claude_auth
            binary = claude_auth.find_claude() or "claude"
        self.binary = binary
        self.default_model = default_model

    def _exec(self, cmd: list[str], prompt: str,
              timeout: int) -> tuple[int, str, str, float]:
        """Run `cmd` with `prompt` on stdin, capturing stdout/stderr to temp
        **files** rather than pipes, and wait only on the CLI's own exit.

        This is deliberate and load-bearing. `subprocess.run(capture_output=True)`
        reads the stdout/stderr *pipes* until EOF — which only arrives once every
        process holding the write end has exited. The Claude Code CLI routinely
        forks short-lived children (update check, tool/IPC helpers, node workers)
        that inherit those pipe fds; if one lingers a moment after `claude` prints
        its JSON and exits, the pipe never reaches EOF and the read blocks until the
        timeout — so a generation that finished in seconds looks like "claude CLI
        timed out after Ns". Writing to files removes the pipe (nothing to reach EOF
        on), so a leftover child can't wedge us. `start_new_session=True` lets a real
        timeout kill the whole process group. Returns (rc, stdout, stderr, seconds).
        """
        with tempfile.TemporaryFile("w+") as fin, \
                tempfile.TemporaryFile("w+") as fout, \
                tempfile.TemporaryFile("w+") as ferr:
            fin.write(prompt)
            fin.seek(0)
            t0 = time.monotonic()
            proc = subprocess.Popen(cmd, stdin=fin, stdout=fout, stderr=ferr,
                                    text=True, start_new_session=True)
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._kill_group(proc)
                ferr.seek(0)
                log.warning("claude CLI hit %ss timeout — killed; stderr tail: %r",
                            timeout, ferr.read()[-500:])
                raise LLMError(f"claude CLI timed out after {timeout}s")
            elapsed = time.monotonic() - t0
            fout.seek(0)
            ferr.seek(0)
            return proc.returncode, fout.read(), ferr.read(), elapsed

    @staticmethod
    def _kill_group(proc: subprocess.Popen) -> None:
        """SIGKILL the CLI's whole process group so no inherited child survives."""
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass

    def _run(self, prompt: str, system: str | None, model: str | None,
             allow_web: bool, timeout: int, schema: dict | None) -> str:
        cmd = [self.binary, "-p", "--output-format", "json"]
        if model or self.default_model:
            cmd += ["--model", model or self.default_model]
        if system:
            cmd += ["--append-system-prompt", system]
        if schema is not None:
            cmd += ["--json-schema", json.dumps(schema)]
        if allow_web:
            cmd += ["--allowed-tools", "WebSearch", "WebFetch"]
        else:
            # No tools needed for pure reasoning over provided data.
            cmd += ["--disallowed-tools", "Bash", "Edit", "Write"]

        returncode, out, err, elapsed = self._exec(cmd, prompt, timeout)
        log.info("claude CLI finished in %.1fs (rc=%s, %d chars out)",
                 elapsed, returncode, len(out))
        if returncode != 0:
            raise LLMError(f"claude CLI failed ({returncode}): {err[:500]}")

        try:
            envelope = json.loads(out)
        except json.JSONDecodeError as e:
            raise LLMError(f"non-JSON CLI output: {out[:300]}") from e
        if envelope.get("is_error"):
            raise LLMError(f"claude returned error: {envelope.get('result')}")
        return envelope.get("result", "")

    def generate(self, prompt, system=None, model=None, allow_web=False,
                 timeout=600) -> str:
        return self._run(prompt, system, model, allow_web, timeout, schema=None)

    def generate_json(self, prompt, schema, system=None, model=None,
                      allow_web=False, timeout=600) -> dict[str, Any]:
        full = prompt + _JSON_INSTRUCTION.format(schema=json.dumps(schema))
        out = self._run(full, system, model, allow_web, timeout, schema=None)
        try:
            return _extract_json(out)
        except json.JSONDecodeError as e:
            raise LLMError(f"structured output was not valid JSON: {out[:300]}") from e


class CodexProvider(LLMProvider):
    """Fallback: OpenAI Codex CLI (`codex exec`). Best-effort JSON parsing."""

    def __init__(self, binary: str = "codex"):
        self.binary = binary

    def generate(self, prompt, system=None, model=None, allow_web=False,
                 timeout=600) -> str:
        full = f"{system}\n\n{prompt}" if system else prompt
        try:
            proc = subprocess.run([self.binary, "exec", full], capture_output=True,
                                  text=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise LLMError("codex CLI timed out") from e
        if proc.returncode != 0:
            raise LLMError(f"codex CLI failed: {proc.stderr[:500]}")
        return proc.stdout.strip()

    def generate_json(self, prompt, schema, system=None, model=None,
                      allow_web=False, timeout=600) -> dict[str, Any]:
        hint = prompt + _JSON_INSTRUCTION.format(schema=json.dumps(schema))
        out = self.generate(hint, system, model, allow_web, timeout)
        try:
            return _extract_json(out)
        except json.JSONDecodeError as e:
            raise LLMError(f"no JSON in codex output: {out[:300]}") from e


_PROVIDERS = {"claude": ClaudeCodeProvider, "codex": CodexProvider}


def get_provider(name: str = "claude", **kwargs) -> LLMProvider:
    if name not in _PROVIDERS:
        raise ValueError(f"unknown provider {name!r}; choose from {list(_PROVIDERS)}")
    return _PROVIDERS[name](**kwargs)
