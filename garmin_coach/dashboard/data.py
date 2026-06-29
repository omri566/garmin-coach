"""Cached data access for the dashboard — wraps the analytics layer.

Single-user, local: trends compute in well under a second over the whole
history, so we just memoize per process and clear on demand after a sync.
"""
from __future__ import annotations

import datetime as dt
import json
from functools import lru_cache

import pandas as pd

from garmin_coach import profile as prof
from garmin_coach.analytics import load, trends
from garmin_coach.store import db


@lru_cache(maxsize=1)
def profile():
    return prof.load_profile()


def default_start(months: int = 18) -> str:
    return (dt.date.today() - dt.timedelta(days=months * 30)).isoformat()


RANGE_DAYS = {"3m": 90, "1y": 365, "5y": 365 * 5}


def range_start(rng: str = "1y") -> str:
    """ISO start date for a 3m/1y/5y range key."""
    days = RANGE_DAYS.get(rng, 365)
    return (dt.date.today() - dt.timedelta(days=days)).isoformat()


def slice_since(df, rng: str = "1y", col: str = "date"):
    """Trim a date-indexed/columned trend frame to the chosen range window."""
    if df is None or df.empty:
        return df
    start = pd.to_datetime(range_start(rng))
    if col in df.columns:
        return df[df[col] >= start]
    if isinstance(df.index, pd.DatetimeIndex):
        return df[df.index >= start]
    return df


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


def aerobic_pace_trend():
    return trends.aerobic_pace_trend()


def technique_trends():
    return trends.technique_trends()


def zone_distribution(weeks: int = 12):
    return trends.zone_distribution(weeks)


def health_trend():
    return trends.health_trend()


def power_trend():
    return trends.power_trend()


def zone_time_weekly():
    return trends.zone_time_weekly()


def elevation_weekly():
    return trends.elevation_weekly()


def recovery_trend():
    return trends.recovery_trend()


# --- motivation / progression metrics for the Coach tab ---------------------
def _running_run_dates() -> list[dt.date]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT date(start_time) FROM activity_metrics "
            "WHERE sport LIKE '%running%' AND start_time IS NOT NULL"
        ).fetchall()
    out = []
    for (d,) in rows:
        try:
            out.append(dt.date.fromisoformat(d))
        except (TypeError, ValueError):
            pass
    return out


def running_streak_weeks(today: dt.date | None = None) -> int:
    """Consecutive Sun–Sat weeks (up to now) with at least one run."""
    from garmin_coach.coach.schedule import _week_start
    today = today or dt.date.today()
    weeks = {_week_start(d) for d in _running_run_dates()}
    if not weeks:
        return 0
    cur = _week_start(today)
    if cur not in weeks:            # this week not started yet → don't break streak
        cur -= dt.timedelta(days=7)
    n = 0
    while cur in weeks:
        n += 1
        cur -= dt.timedelta(days=7)
    return n


def activity_highlights(today: dt.date | None = None) -> dict:
    """Headline numbers for the milestones strip."""
    today = today or dt.date.today()
    month_start = today.replace(day=1).isoformat()
    with db.connect() as conn:
        longest = conn.execute(
            "SELECT MAX(distance_m) FROM activity_metrics WHERE sport LIKE '%running%'"
        ).fetchone()[0]
        month_km = conn.execute(
            "SELECT COALESCE(SUM(distance_m), 0) / 1000.0 FROM activity_metrics "
            "WHERE sport LIKE '%running%' AND date(start_time) >= ?", (month_start,)
        ).fetchone()[0]
    return {"longest_km": (longest or 0) / 1000.0, "month_km": float(month_km or 0)}


def fitness_progress(since_iso: str | None = None) -> dict | None:
    """Current CTL (fitness) and its change since a plan-start date."""
    df = load.load_series(start=default_start())
    if df is None or df.empty:
        return None
    cur = float(df["ctl"].iloc[-1])
    delta = None
    if since_iso:
        sub = df[df.index <= pd.to_datetime(str(since_iso)[:10])]
        if not sub.empty:
            delta = cur - float(sub["ctl"].iloc[-1])
    return {"ctl": round(cur, 1), "delta": round(delta, 1) if delta is not None else None}


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


def run_options(limit: int = 100) -> list[dict]:
    """Recent runs for the activity selector (label/value pairs)."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT activity_id, start_time, distance_m FROM activity_metrics "
            "WHERE sport LIKE '%running%' ORDER BY start_time DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        km = (r["distance_m"] or 0) / 1000.0
        out.append({"value": str(r["activity_id"]),
                    "label": f"{r['start_time'][:10]} · {km:.1f} km"})
    return out


def run_streams(activity_id):
    from garmin_coach.store import streams
    return streams.read_streams(int(activity_id))


def run_metrics(activity_id) -> dict | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM activity_metrics WHERE activity_id = ?",
            (int(activity_id),),
        ).fetchone()
    return dict(row) if row else None


def technique_baselines() -> dict:
    """Personal median for each dynamics metric over runs that have them."""
    cols = ["avg_cadence_spm", "avg_vert_ratio", "avg_gct_ms",
            "avg_gct_balance", "avg_step_len_mm"]
    with db.connect() as conn:
        out = {}
        for c in cols:
            row = conn.execute(
                f"SELECT {c} FROM activity_metrics WHERE {c} IS NOT NULL "
                f"ORDER BY {c}"
            ).fetchall()
            vals = [r[0] for r in row]
            out[c] = vals[len(vals) // 2] if vals else None
    return out


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
