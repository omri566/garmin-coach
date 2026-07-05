"""Drive the local Claude Code CLI's auth so the athlete can connect their own
Claude subscription from the dashboard — the AI (`claude -p`) then runs on their
plan, no API key needed.

Mechanism (all first-party `claude` subcommands):
  - `claude auth status --json` → {"loggedIn": bool, "email", "subscriptionType"}
  - `claude auth login`         → browser OAuth against claude.ai (their sub)
  - `claude install`            → installs the native build if only a shim exists

A packaged .app is launched by Finder with a minimal PATH, so we resolve the
binary from the usual install locations rather than trusting `claude` on PATH.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

# Where the native installer / Homebrew / npm drop the CLI.
_CANDIDATES = [
    "~/.local/bin/claude",
    "~/.claude/local/claude",
    "/opt/homebrew/bin/claude",
    "/usr/local/bin/claude",
    "/opt/homebrew/opt/claude-code/bin/claude",
]

_INSTALL_URL = "https://claude.ai/install.sh"


def find_claude() -> str | None:
    """Absolute path to a usable `claude` binary, or None if not installed."""
    if env := os.getenv("CLAUDE_BIN"):
        if Path(env).exists():
            return env
    if found := shutil.which("claude"):
        return found
    for c in _CANDIDATES:
        p = Path(c).expanduser()
        if p.exists():
            return str(p)
    return None


def is_installed() -> bool:
    return find_claude() is not None


def _run(args: list[str], timeout: int = 20) -> subprocess.CompletedProcess | None:
    binary = find_claude()
    if not binary:
        return None
    try:
        return subprocess.run([binary, *args], capture_output=True, text=True,
                              timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return None


def status() -> dict:
    """Parsed `claude auth status --json`; {} if the CLI is missing or errors."""
    proc = _run(["auth", "status", "--json"])
    if not proc or proc.returncode != 0 or not proc.stdout.strip():
        return {}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def is_connected() -> bool:
    return bool(status().get("loggedIn"))


def account_label() -> str | None:
    """e.g. 'omri@example.com · pro' for showing which account is linked."""
    s = status()
    if not s.get("loggedIn"):
        return None
    email, sub = s.get("email"), s.get("subscriptionType")
    return " · ".join(x for x in (email, sub) if x)


def install() -> tuple[bool, str]:
    """Install the Claude Code native build. If a shim already exists, upgrade it
    in place; otherwise run the official installer. Returns (ok, message)."""
    if is_installed():
        proc = _run(["install"], timeout=180)
        if proc and proc.returncode == 0:
            return True, "Claude Code is ready."
    try:
        # curl … | bash — the official, Node-free native installer.
        p = subprocess.run(
            f"curl -fsSL {_INSTALL_URL} | bash", shell=True,
            capture_output=True, text=True, timeout=300)
    except (subprocess.TimeoutExpired, OSError) as e:
        return False, f"Install failed: {e}"
    if is_installed():
        return True, "Installed Claude Code."
    return False, (p.stderr or p.stdout or "Install failed.")[:400]


def start_login() -> tuple[bool, str]:
    """Open a Terminal window running `claude auth login` so the athlete signs in
    with their Claude subscription (real TTY + browser OAuth). The onboarding page
    then polls `is_connected()`. Returns (launched, message)."""
    binary = find_claude()
    if not binary:
        return False, "Claude Code isn't installed yet."
    # A real TTY is the most reliable way to run the interactive OAuth on macOS.
    script = f'tell application "Terminal" to activate\n' \
             f'tell application "Terminal" to do script "{binary} auth login"'
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True,
                       text=True, timeout=15)
    except (subprocess.TimeoutExpired, OSError) as e:
        return False, f"Couldn't open Terminal: {e}"
    return True, "Sign in to Claude in the Terminal window, then come back here."
