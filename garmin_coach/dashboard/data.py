"""Cached data access for the dashboard — wraps the analytics layer.

Single-user, local: trends compute in well under a second over the whole
history, so we just memoize per process and clear on demand after a sync.
"""
from __future__ import annotations

import datetime as dt
import json
from functools import lru_cache

from garmin_coach import profile as prof
from garmin_coach.analytics import load, trends
from garmin_coach.store import db


@lru_cache(maxsize=1)
def profile():
    return prof.load_profile()


def default_start(months: int = 18) -> str:
    return (dt.date.today() - dt.timedelta(days=months * 30)).isoformat()


def load_series(start: str | None = None):
    return load.load_series(start=start or default_start())


def current_state():
    return load.current_state()


def weekly_volume():
    return trends.weekly_volume()


def efficiency_trend():
    return trends.efficiency_trend()


def vo2max_trend():
    return trends.vo2max_trend()


def zone_distribution(weeks: int = 12):
    return trends.zone_distribution(weeks)


def health_trend():
    return trends.health_trend()


def latest_health() -> dict:
    """Most recent non-null value for each recovery metric."""
    out = {}
    with db.connect() as conn:
        for col in ("hrv_overnight", "resting_hr", "sleep_score",
                    "readiness_score", "body_battery_high"):
            row = conn.execute(
                f"SELECT day, {col} FROM health_daily "
                f"WHERE {col} IS NOT NULL ORDER BY day DESC LIMIT 1"
            ).fetchone()
            out[col] = {"day": row[0], "value": row[1]} if row else None
    return out


def latest_vo2max() -> float | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT vo2max FROM activities WHERE vo2max IS NOT NULL "
            "ORDER BY start_time DESC LIMIT 1"
        ).fetchone()
    return row[0] if row else None


def last_run() -> dict | None:
    """Latest running activity: metrics row + name/raw from the summary."""
    with db.connect() as conn:
        m = conn.execute(
            "SELECT * FROM activity_metrics WHERE sport LIKE '%running%' "
            "ORDER BY start_time DESC LIMIT 1"
        ).fetchone()
        if not m:
            return None
        a = conn.execute(
            "SELECT raw_json FROM activities WHERE activity_id = ?",
            (m["activity_id"],),
        ).fetchone()
    d = dict(m)
    summary = json.loads(a["raw_json"]) if a and a["raw_json"] else {}
    d["name"] = summary.get("activityName") or "Run"
    return d
