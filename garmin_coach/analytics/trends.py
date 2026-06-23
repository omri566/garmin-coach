"""Long-term trend series for the dashboard.

Each function returns a tidy DataFrame keyed by date/week so the dashboard can
plot directly. Trends auto-scope to where each metric exists (e.g. running
dynamics only post-2023) and expose sample counts so the UI can draw confidence.
"""
from __future__ import annotations

import pandas as pd

from garmin_coach.store import db

RUN = "%running%"


def _metrics_df(cols: str, sport_like: str = RUN,
                where: str = "") -> pd.DataFrame:
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT start_time, {cols} FROM activity_metrics "
            f"WHERE sport LIKE ? {where} ORDER BY start_time",
            (sport_like,),
        ).fetchall()
    df = pd.DataFrame([dict(r) for r in rows])
    if not df.empty:
        df["date"] = pd.to_datetime(df["start_time"])
    return df


def weekly_volume() -> pd.DataFrame:
    """Weekly running distance (km), moving hours, and run count."""
    df = _metrics_df("distance_m, moving_s")
    if df.empty:
        return df
    g = df.set_index("date").resample("W").agg(
        distance_km=("distance_m", lambda s: s.sum() / 1000.0),
        hours=("moving_s", lambda s: s.sum() / 3600.0),
        runs=("distance_m", "count"),
    )
    return g.reset_index()


def rolling_metric(col: str, window: int = 42, min_periods: int = 3,
                   sport_like: str = RUN, extra_where: str = "") -> pd.DataFrame:
    """Per-activity values + a rolling (time-based) mean for a metric column."""
    df = _metrics_df(f"{col}", sport_like, extra_where)
    if df.empty:
        return df
    df = df.dropna(subset=[col]).set_index("date").sort_index()
    df["rolling"] = df[col].rolling(f"{window}D", min_periods=min_periods).mean()
    return df.reset_index()[["date", col, "rolling"]]


def efficiency_trend(window: int = 42) -> pd.DataFrame:
    """Efficiency factor on aerobic runs only (avg HR < LTHR-ish), rolling."""
    # Aerobic filter keeps EF comparable (excludes races/intervals).
    return rolling_metric("ef", window=window,
                          extra_where="AND avg_hr < 175 AND ef IS NOT NULL")


def technique_trends(window: int = 42) -> dict[str, pd.DataFrame]:
    return {
        c: rolling_metric(c, window=window, extra_where=f"AND {c} IS NOT NULL")
        for c in ("avg_cadence_spm", "avg_vert_ratio", "avg_gct_ms",
                  "avg_gct_balance", "avg_step_len_mm")
    }


def vo2max_trend() -> pd.DataFrame:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT start_time, vo2max FROM activities "
            "WHERE vo2max IS NOT NULL ORDER BY start_time"
        ).fetchall()
    df = pd.DataFrame([dict(r) for r in rows])
    if not df.empty:
        df["date"] = pd.to_datetime(df["start_time"])
    return df


def zone_distribution(weeks: int = 12) -> pd.DataFrame:
    """Recent share of running time in each HR zone (polarization check)."""
    df = _metrics_df("z1_s, z2_s, z3_s, z4_s, z5_s")
    if df.empty:
        return df
    cutoff = pd.Timestamp.now() - pd.Timedelta(weeks=weeks)
    df = df[df["date"] >= cutoff]
    sums = {f"Z{i}": df[f"z{i}_s"].sum() for i in range(1, 6)}
    total = sum(sums.values()) or 1.0
    return pd.DataFrame(
        [{"zone": z, "seconds": s, "pct": 100 * s / total} for z, s in sums.items()]
    )


def health_trend(cols=("hrv_overnight", "resting_hr", "sleep_score",
                       "readiness_score")) -> pd.DataFrame:
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT day, {', '.join(cols)} FROM health_daily ORDER BY day"
        ).fetchall()
    df = pd.DataFrame([dict(r) for r in rows])
    if not df.empty:
        df["day"] = pd.to_datetime(df["day"])
    return df
