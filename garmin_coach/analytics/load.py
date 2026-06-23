"""Training load: Fitness / Fatigue / Form + ACWR as daily time series.

Model (Banister impulse-response, as popularised by TrainingPeaks):
  - daily load    = sum of per-activity stress on that calendar day (0 if rest)
  - CTL (Fitness) = exponentially-weighted avg, 42-day time constant
  - ATL (Fatigue) = exponentially-weighted avg, 7-day time constant
  - TSB (Form)    = yesterday's CTL - yesterday's ATL  (positive = fresh)
  - ACWR          = 7-day load / (28-day load / 4); 0.8-1.3 = "sweet spot"
  - ramp          = week-over-week change in CTL (injury risk if too steep)

Load unit: **TRIMP** (per-activity, HR-derived) for one consistent metric across
the whole history. Garmin's own load only exists on recent activities and is on a
different scale, so mixing it would break CTL continuity.
"""
from __future__ import annotations

import datetime as dt
import math

import pandas as pd

from garmin_coach.store import db

CTL_TAU = 42
ATL_TAU = 7


def _daily_stress(stress_col: str = "trimp") -> pd.Series:
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT start_time, {stress_col} AS s FROM activity_metrics "
            f"WHERE {stress_col} IS NOT NULL"
        ).fetchall()
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = pd.to_datetime(df["start_time"]).dt.normalize()
    return df.groupby("date")["s"].sum()


def load_series(stress_col: str = "trimp",
                start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Daily fitness/fatigue/form/ACWR over the full (or bounded) timeline."""
    daily = _daily_stress(stress_col)
    if daily.empty:
        return pd.DataFrame()

    first = pd.to_datetime(start) if start else daily.index.min()
    last = pd.to_datetime(end) if end else pd.Timestamp(dt.date.today())
    idx = pd.date_range(first, last, freq="D")
    tss = daily.reindex(idx, fill_value=0.0)

    df = pd.DataFrame({"tss": tss})
    a_ctl = 1 - math.exp(-1 / CTL_TAU)
    a_atl = 1 - math.exp(-1 / ATL_TAU)
    df["ctl"] = tss.ewm(alpha=a_ctl, adjust=False).mean()
    df["atl"] = tss.ewm(alpha=a_atl, adjust=False).mean()
    df["tsb"] = df["ctl"].shift(1) - df["atl"].shift(1)

    acute = tss.rolling(7, min_periods=1).sum()
    chronic = tss.rolling(28, min_periods=1).sum() / 4.0
    df["acwr"] = acute / chronic.replace(0, float("nan"))
    df["ramp"] = df["ctl"] - df["ctl"].shift(7)
    df.index.name = "date"
    return df


def current_state(stress_col: str = "trimp") -> dict[str, float | None]:
    """Latest fitness/fatigue/form snapshot for headline display."""
    df = load_series(stress_col)
    if df.empty:
        return {}
    last = df.iloc[-1]
    return {
        "ctl": round(float(last["ctl"]), 1),
        "atl": round(float(last["atl"]), 1),
        "tsb": round(float(last["tsb"]), 1) if pd.notna(last["tsb"]) else None,
        "acwr": round(float(last["acwr"]), 2) if pd.notna(last["acwr"]) else None,
        "ramp": round(float(last["ramp"]), 1) if pd.notna(last["ramp"]) else None,
    }
