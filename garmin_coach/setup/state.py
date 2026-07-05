"""Whether first-run setup is complete: both a cached Garmin token and a
connected Claude account. The app shows the onboarding landing page until this
returns True, then the normal dashboard."""
from __future__ import annotations

from garmin_coach import config
from garmin_coach.setup import claude_auth


def garmin_connected() -> bool:
    """A Garmin token has been cached (login already succeeded once)."""
    d = config.TOKENS_DIR
    return d.exists() and any(d.iterdir())


def claude_connected() -> bool:
    return claude_auth.is_connected()


def is_configured() -> bool:
    return garmin_connected() and claude_connected()
