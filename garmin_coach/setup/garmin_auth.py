"""Garmin login driven from the onboarding page.

`garminconnect` handles MFA through a synchronous `prompt_mfa` callback, so we run
the login on a background thread and feed the code in from the web form via a
queue. Single-user local app → one in-flight login held in module state.

States: idle → connecting → [mfa_required → verifying] → connected | error
"""
from __future__ import annotations

import queue
import threading
import time

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

from garmin_coach import config

_RATE_LIMIT = ("Garmin is temporarily rate-limiting this network. Wait ~30–60 min "
               "and try again, or switch networks (e.g. a phone hotspot).")

_s: dict = {"status": "idle", "error": None, "thread": None, "mfa_q": None}


def _worker(email: str, password: str) -> None:
    config.ensure_dirs()

    def prompt_mfa() -> str:
        _s["status"] = "mfa_required"
        code = _s["mfa_q"].get()          # blocks until submit_mfa() feeds it
        _s["status"] = "verifying"
        return code

    try:
        Garmin(email=email, password=password, prompt_mfa=prompt_mfa).login(
            str(config.TOKENS_DIR))
        _s["status"] = "connected"
    except GarminConnectTooManyRequestsError:
        _s["status"], _s["error"] = "error", _RATE_LIMIT
    except GarminConnectAuthenticationError:
        _s["status"], _s["error"] = "error", "Login failed — check your email and password."
    except Exception as e:                 # noqa: BLE001 — surface anything else briefly
        _s["status"], _s["error"] = "error", str(e)[:200] or "Login failed."


def _wait_while(status: str, timeout: float) -> str:
    """Block until the login leaves ``status`` (or timeout), return the new one."""
    end = time.time() + timeout
    while time.time() < end and _s["status"] == status:
        time.sleep(0.25)
    return _s["status"]


def start_login(email: str, password: str, timeout: float = 35) -> str:
    """Begin a login. Returns once it settles into mfa_required/connected/error."""
    if _s["status"] in ("connecting", "mfa_required", "verifying"):
        return _s["status"]
    _s.update(status="connecting", error=None, mfa_q=queue.Queue())
    _s["thread"] = threading.Thread(target=_worker, args=(email, password),
                                    daemon=True)
    _s["thread"].start()
    return _wait_while("connecting", timeout)


def submit_mfa(code: str, timeout: float = 35) -> str:
    """Feed the MFA code to the waiting login. Returns connected | error."""
    if _s["status"] != "mfa_required" or not _s["mfa_q"]:
        return _s["status"]
    _s["mfa_q"].put((code or "").strip())
    _wait_while("verifying", timeout)
    return _s["status"]


def poll() -> dict:
    return {"status": _s["status"], "error": _s["error"]}
