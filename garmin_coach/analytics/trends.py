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


def aerobic_pace_trend(window: int = 42) -> pd.DataFrame:
    """Easy-run pace (s/km) on aerobic runs only (HR in Z1–Z2), rolling.

    Filtered to avg HR between 135 and the Z3 floor (170) to exclude recovery
    walks and tempo/harder efforts, so the trend reflects easy-pace-at-effort.
    """
    return rolling_metric(
        "avg_pace_s_km", window=window,
        extra_where="AND avg_hr >= 135 AND avg_hr < 170 AND avg_pace_s_km IS NOT NULL")


def technique_trends(window: int = 42) -> dict[str, pd.DataFrame]:
    return {
        c: rolling_metric(c, window=window, extra_where=f"AND {c} IS NOT NULL")
        for c in ("avg_cadence_spm", "avg_vert_ratio", "avg_gct_ms",
                  "avg_gct_balance", "avg_step_len_mm")
    }


def vo2max_trend(window: int = 42) -> pd.DataFrame:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT start_time, vo2max FROM activities "
            "WHERE vo2max IS NOT NULL ORDER BY start_time"
        ).fetchall()
    df = pd.DataFrame([dict(r) for r in rows])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["start_time"])
    # A rolling mean gives line_trend a connecting trend line (VO₂max is a slow-
    # moving estimate, so the raw points alone read as scattered dots).
    df = df.dropna(subset=["vo2max"]).set_index("date").sort_index()
    df["rolling"] = df["vo2max"].rolling(f"{window}D", min_periods=2).mean()
    return df.reset_index()[["date", "vo2max", "rolling"]]


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


def power_trend(window: int = 42) -> pd.DataFrame:
    """Running power (W) per activity + rolling mean."""
    return rolling_metric("avg_power_w", window=window,
                          extra_where="AND avg_power_w IS NOT NULL")


def zone_time_weekly() -> pd.DataFrame:
    """Weekly time (hours) in each HR zone — a polarization trend over time."""
    df = _metrics_df("z1_s, z2_s, z3_s, z4_s, z5_s")
    if df.empty:
        return df
    g = df.set_index("date").resample("W").agg(
        {f"z{i}_s": "sum" for i in range(1, 6)})
    for i in range(1, 6):
        g[f"Z{i}"] = g[f"z{i}_s"] / 3600.0
    return g.reset_index()[["date"] + [f"Z{i}" for i in range(1, 6)]]


def elevation_weekly() -> pd.DataFrame:
    """Weekly total elevation gain (m) on runs."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT start_time, elevation_gain_m FROM activities "
            "WHERE sport LIKE ? AND elevation_gain_m IS NOT NULL ORDER BY start_time",
            (RUN,),
        ).fetchall()
    df = pd.DataFrame([dict(r) for r in rows])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["start_time"])
    g = df.set_index("date").resample("W").agg(elev_gain_m=("elevation_gain_m", "sum"))
    return g.reset_index()


def recovery_trend() -> pd.DataFrame:
    """Daily recovery markers for the health charts."""
    cols = ("resting_hr", "resting_hr_7d", "hrv_overnight", "hrv_weekly",
            "sleep_score", "body_battery_high", "body_battery_low",
            "stress_avg", "readiness_score")
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT day, {', '.join(cols)} FROM health_daily ORDER BY day"
        ).fetchall()
    df = pd.DataFrame([dict(r) for r in rows])
    if not df.empty:
        df["day"] = pd.to_datetime(df["day"])
    return df


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
