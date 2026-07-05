"""Garmin Connect authentication.

`Garmin.login(tokenstore)` does the right thing on its own:
  - if cached tokens exist under `tokenstore`, it loads them (no SSO call, so no
    rate-limit risk) and refreshes if near expiry;
  - otherwise it logs in with the configured credentials, prompts for an MFA code
    if the account requires one, and persists tokens to `tokenstore` so future
    (and scheduled) runs are non-interactive.

Credentials, if provided via env, are only used to obtain tokens — never stored
by us. After the first successful login the cached token is reused for months.
"""
from __future__ import annotations

import getpass
import logging

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

from garmin_coach import config

log = logging.getLogger(__name__)


def _prompt_mfa() -> str:
    return input("Garmin MFA code: ").strip()


def get_client() -> Garmin:
    config.ensure_dirs()
    tokenstore = str(config.TOKENS_DIR)

    # A cached token means we're already authenticated (e.g. after the onboarding
    # login) — login(tokenstore) reuses it with no SSO call, so we must NOT prompt
    # for credentials here: the packaged .app has no stdin and input() would crash.
    tp = config.TOKENS_DIR
    has_token = tp.exists() and any(tp.iterdir())
    email, password = config.GARMIN_EMAIL, config.GARMIN_PASSWORD
    if not has_token:
        email = email or input("Garmin email: ").strip()
        password = password or getpass.getpass("Garmin password: ")

    client = Garmin(email=email or "", password=password or "", prompt_mfa=_prompt_mfa)
    try:
        client.login(tokenstore)
    except GarminConnectTooManyRequestsError as exc:
        raise SystemExit(
            "Garmin is rate-limiting this IP (HTTP 429). Wait ~30-60 min and "
            "retry, or switch networks (e.g. phone hotspot) for the first login. "
            "Once tokens are cached, later runs won't hit the login endpoint.\n"
            f"  ({exc})"
        ) from exc
    except GarminConnectAuthenticationError as exc:
        raise SystemExit(f"Garmin authentication failed: {exc}") from exc

    log.info("Garmin session ready (tokens at %s).", tokenstore)
    return client
