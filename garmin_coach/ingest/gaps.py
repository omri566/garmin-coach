"""Gap & data-availability detection.

Three distinct notions of "missing", which trends/recommendations must not
conflate:

1. Training gaps   — stretches with no activity (rest, travel, injury, breaks).
                     Legitimately load = 0; not an error.
2. Metric eras     — a metric may not exist before a certain date because the
                     device/sensor didn't record it yet (e.g. running dynamics on
                     older activities). "Absent because impossible" != "missing".
3. Health coverage — days inside the synced window with no wellness data
                     (device not worn / not yet finalized).

These feed Phase-2 confidence bands so we never draw a trend through a void.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd
import pyarrow.parquet as pq

from garmin_coach.store import db

# Running-dynamics / power fields whose availability changed over the years.
DYNAMIC_FIELDS = [
    "vertical_oscillation", "vertical_ratio", "stance_time",
    "stance_time_balance", "step_length", "power", "heart_rate",
]


@dataclass
class TrainingGap:
    start: str          # date of last activity before the gap
    end: str            # date of next activity after the gap
    days: int           # idle days between them


def _activities_df(sport_like: str | None = "running") -> pd.DataFrame:
    with db.connect() as conn:
        q = "SELECT activity_id, start_time, sport, streams_path FROM activities"
        if sport_like:
            q += " WHERE sport LIKE ?"
            rows = conn.execute(q + " ORDER BY start_time", (f"%{sport_like}%",)).fetchall()
        else:
            rows = conn.execute(q + " ORDER BY start_time").fetchall()
    df = pd.DataFrame([dict(r) for r in rows])
    if not df.empty:
        df["date"] = pd.to_datetime(df["start_time"]).dt.date
    return df


def training_gaps(min_days: int = 5, sport_like: str | None = "running") -> list[TrainingGap]:
    """Idle stretches >= `min_days` between consecutive qualifying activities."""
    df = _activities_df(sport_like)
    gaps: list[TrainingGap] = []
    prev = None
    for d in df["date"]:
        if prev is not None:
            delta = (d - prev).days
            if delta >= min_days:
                gaps.append(TrainingGap(prev.isoformat(), d.isoformat(), delta))
        prev = d
    return gaps


def metric_first_seen(fields: list[str] | None = None,
                      sport_like: str | None = "running") -> dict[str, str | None]:
    """First activity date on which each field appears in the per-second streams.

    Reads parquet *schemas only* (no row data), so it's cheap across hundreds of
    files. A field absent before its first-seen date is "didn't exist yet", not a
    recording gap.
    """
    fields = fields or DYNAMIC_FIELDS
    df = _activities_df(sport_like).sort_values("date")
    first: dict[str, str | None] = {f: None for f in fields}
    remaining = set(fields)
    for _, row in df.iterrows():
        if not remaining or not row["streams_path"]:
            continue
        try:
            cols = set(pq.read_schema(row["streams_path"]).names)
        except Exception:
            continue
        for f in list(remaining):
            if f in cols:
                first[f] = row["date"].isoformat()
                remaining.discard(f)
    return first


def health_coverage() -> dict[str, object]:
    """Coverage of daily health metrics across the synced date window."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT day, resting_hr, hrv_overnight, sleep_score, readiness_score "
            "FROM health_daily ORDER BY day"
        ).fetchall()
    if not rows:
        return {"days_in_window": 0, "stored": 0, "missing_days": []}

    df = pd.DataFrame([dict(r) for r in rows])
    df["day"] = pd.to_datetime(df["day"]).dt.date
    start, end = df["day"].min(), df["day"].max()
    full = {start + dt.timedelta(days=i) for i in range((end - start).days + 1)}
    stored = set(df["day"])
    missing = sorted(d.isoformat() for d in (full - stored))

    def cov(col: str) -> str:
        nn = df[col].notna().sum()
        return f"{nn}/{len(df)} ({100 * nn / len(df):.0f}%)"

    return {
        "window": f"{start} .. {end}",
        "days_in_window": len(full),
        "stored": len(stored),
        "missing_days": missing,
        "coverage": {c: cov(c) for c in
                     ["resting_hr", "hrv_overnight", "sleep_score", "readiness_score"]},
    }
