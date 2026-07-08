"""Personal patterns — data-driven insights from *this* athlete's own history.

Instead of generic advice ("run in the morning"), we test whether a pattern
actually holds in the athlete's data and only surface it when it clears a sample-
size and effect-size threshold. Every insight carries the numbers behind it, so
it's honest: if the evidence isn't there (e.g. evening runs don't hurt *your*
sleep), we say nothing rather than parrot the textbook.

Signals available: run start time (hour / weekday), efficiency factor (EF),
aerobic decoupling, plus overnight sleep / HRV / readiness per day.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from garmin_coach.store import db

# Time-of-day buckets (local hour of the run's start).
_BUCKETS = [("morning", 0, 11), ("midday", 11, 16),
            ("afternoon", 16, 19), ("evening", 19, 24)]
_BUCKET_LABEL = {"morning": "before 11am", "midday": "midday (11–4)",
                 "afternoon": "late afternoon (4–7pm)", "evening": "evening (after 7pm)"}

_MIN_BUCKET = 12      # runs needed in a bucket to trust its average
_MIN_PAIRS = 20       # paired run/health days needed for a correlation
_MIN_LATE = 6         # late-run nights needed to judge the sleep effect


def _runs() -> pd.DataFrame:
    with db.connect() as conn:
        df = pd.read_sql(
            "SELECT start_time, avg_hr, ef, decoupling_pct, avg_cadence_spm, "
            "distance_m, avg_pace_s_km FROM activity_metrics "
            "WHERE sport LIKE '%running%' AND start_time IS NOT NULL", conn)
    if df.empty:
        return df
    ts = pd.to_datetime(df["start_time"])
    df["hour"] = ts.dt.hour
    df["date"] = ts.dt.date
    df["weekday"] = ts.dt.day_name()
    return df


def _health_map(col: str) -> dict:
    with db.connect() as conn:
        df = pd.read_sql(
            f"SELECT day, {col} FROM health_daily WHERE {col} IS NOT NULL", conn)
    if df.empty:
        return {}
    return dict(zip(pd.to_datetime(df["day"]).dt.date, df[col]))


# ---- rigour helpers: control for confounders ------------------------------
# Insights compare runs of different kinds, so a raw pattern can be a mirage
# (e.g. "morning runs are efficient" might just mean morning = your easy runs).
# We remove the linear effect of confounders before judging a pattern.
#
# EF = speed / HR, so it is a deterministic function of pace *and* HR — never
# control for both at once (the residual would be ~0). Controlling for one of
# them plus distance is the meaningful adjustment.

def _design(df, controls):
    return np.column_stack([np.ones(len(df))]
                           + [df[c].to_numpy(float) for c in controls])


def _residualise(df, ycol, controls):
    """df with ``ycol_adj`` = ycol minus the linear effect of controls (mean added
    back so it stays on the original scale). None if too few clean rows."""
    sub = df.dropna(subset=[ycol, *controls]).copy()
    if len(sub) < len(controls) + 10:
        return None
    y = sub[ycol].to_numpy(float)
    z = _design(sub, controls)
    beta, *_ = np.linalg.lstsq(z, y, rcond=None)
    sub[ycol + "_adj"] = (y - z @ beta) + y.mean()
    return sub


def _partial_corr(df, xcol, ycol, controls):
    """Correlation of x and y after removing the linear effect of controls from
    both. Returns (r or None, n)."""
    sub = df.dropna(subset=[xcol, ycol, *controls])
    if len(sub) < len(controls) + _MIN_PAIRS:
        return None, len(sub)
    z = _design(sub, controls)

    def resid(col):
        y = sub[col].to_numpy(float)
        beta, *_ = np.linalg.lstsq(z, y, rcond=None)
        return y - z @ beta

    rx, ry = resid(xcol), resid(ycol)
    if rx.std() == 0 or ry.std() == 0:
        return None, len(sub)
    return float(np.corrcoef(rx, ry)[0, 1]), len(sub)


def _lag_corr(runs, series_map, ycol="ef", controls=("distance_m", "avg_hr")):
    """Correlate a per-day health value with a run metric, controlling for run
    distance + intensity so the link isn't just 'hard days feel different'."""
    d = runs.copy()
    d["x"] = d["date"].map(lambda k: series_map.get(k))
    return _partial_corr(d, "x", ycol, list(controls))


def _bucket(hour: int) -> str:
    for name, lo, hi in _BUCKETS:
        if lo <= hour < hi:
            return name
    return "evening"


def time_of_day_insight(runs: pd.DataFrame) -> dict | None:
    """Which time of day the athlete runs most efficiently (EF) — after adjusting
    for run distance + intensity, so it isn't just 'mornings are my easy runs'."""
    d = runs.dropna(subset=["ef"]).copy()
    if len(d) < 2 * _MIN_BUCKET:
        return None
    adj = _residualise(d, "ef", ["distance_m", "avg_hr"])
    ycol = "ef_adj" if adj is not None else "ef"   # fall back if controls missing
    d = adj if adj is not None else d
    d["bucket"] = d["hour"].apply(_bucket)
    g = d.groupby("bucket").agg(n=(ycol, "size"), ef=(ycol, "mean"))
    g = g[g["n"] >= _MIN_BUCKET]
    if len(g) < 2:
        return None
    best = g["ef"].idxmax()
    rest = d[d["bucket"] != best][ycol].mean()
    lift = (g.loc[best, "ef"] - rest) / rest if rest else 0
    if lift < 0.02:                     # < 2% better → not worth calling out
        return None
    return {
        "kind": "time_of_day",
        "title": f"Run your key sessions in the {best}",
        "detail": (f"Even comparing like-for-like runs, your {_BUCKET_LABEL[best]} "
                   f"runs come out about {lift * 100:.0f}% more efficient — that's "
                   f"genuinely your best window. Schedule the hard stuff then."),
    }


def late_run_sleep_insight(runs: pd.DataFrame, sleep: dict) -> dict | None:
    """Whether running late (after 8pm) measurably lowers *this* athlete's sleep
    that night — reported only if there's a real effect."""
    if not sleep:
        return None
    d = runs.copy()
    d["next_sleep"] = d["date"].apply(lambda x: sleep.get(x + dt.timedelta(days=1)))
    late = d[(d["hour"] >= 20)].dropna(subset=["next_sleep"])
    early = d[(d["hour"] < 20)].dropna(subset=["next_sleep"])
    if len(late) < _MIN_LATE or len(early) < _MIN_LATE:
        return None
    delta = late["next_sleep"].mean() - early["next_sleep"].mean()
    if delta > -3:                      # not meaningfully worse → don't warn
        return None
    return {
        "kind": "late_sleep",
        "title": "Try to finish your runs earlier",
        "detail": (f"Running past 8pm seems to cost you sleep — you rest noticeably "
                   f"worse on those nights (about {abs(delta):.0f} points lower). "
                   f"Wrap up hard efforts earlier in the evening when you can."),
    }


def rest_day_rebound_insight(runs: pd.DataFrame) -> dict | None:
    """Whether the athlete runs better on days *following a rest day* than on
    back-to-back days — a sign hard efforts need spacing."""
    d = runs.dropna(subset=["ef"]).copy()
    if len(d) < 2 * _MIN_BUCKET:
        return None
    dates = set(d["date"])
    d["rested"] = d["date"].apply(lambda x: (x - dt.timedelta(days=1)) not in dates)
    rested, b2b = d[d["rested"]], d[~d["rested"]]
    if len(rested) < _MIN_BUCKET or len(b2b) < _MIN_BUCKET:
        return None
    lift = (rested["ef"].mean() - b2b["ef"].mean()) / b2b["ef"].mean()
    if lift < 0.02:
        return None
    return {
        "kind": "rest_rebound",
        "title": "Put a rest day before big sessions",
        "detail": (f"You run about {lift * 100:.0f}% better the day after a rest "
                   f"day than on back-to-back days — space your hard efforts out."),
    }


def cadence_efficiency_insight(runs: pd.DataFrame) -> dict | None:
    """Whether a quicker cadence goes with better economy — controlling for pace,
    so it isn't just 'faster runs have both a higher cadence and higher EF'."""
    r, _ = _partial_corr(runs, "avg_cadence_spm", "ef", ["avg_pace_s_km"])
    if r is None or r < 0.25:
        return None
    return {
        "kind": "cadence",
        "title": "Lean into a quicker cadence",
        "detail": ("Even at the same pace, your higher-cadence runs take less effort "
                   "(better economy) — a slightly quicker turnover pays off for you."),
    }


def readiness_performance_insight(runs, readiness) -> dict | None:
    r, _ = _lag_corr(runs, readiness)
    if r is None or r < 0.25:
        return None
    return {
        "kind": "readiness",
        "title": "Trust your green days",
        "detail": ("When Garmin flags you as ready your runs come out sharper — "
                   "save the quality sessions for high-readiness days."),
    }


def hrv_performance_insight(runs, hrv) -> dict | None:
    r, _ = _lag_corr(runs, hrv)
    if r is None or r < 0.25:
        return None
    return {
        "kind": "hrv",
        "title": "Let HRV pick your hard days",
        "detail": ("Your runs are noticeably better on high-HRV mornings — push "
                   "when HRV is up and keep it easy when it dips."),
    }


def resting_hr_insight(runs, rhr) -> dict | None:
    r, _ = _lag_corr(runs, rhr)
    if r is None or r > -0.25:          # want a real *negative* link
        return None
    return {
        "kind": "resting_hr",
        "title": "Ease off when your resting HR is up",
        "detail": ("A higher-than-usual resting heart rate lines up with flatter "
                   "runs for you — treat it as a cue to go easy that day."),
    }


def sleep_performance_insight(runs, sleep) -> dict | None:
    r, _ = _lag_corr(runs, sleep)
    if r is None or r < 0.25:
        return None
    return {
        "kind": "sleep_perf",
        "title": "Protect your sleep before big sessions",
        "detail": ("When you sleep well your next run is noticeably sharper, so "
                   "bank a good night before the hard stuff — it pays off for you."),
    }


def personal_insights() -> list[dict]:
    """All patterns that clear their significance bar, most actionable first."""
    runs = _runs()
    if runs.empty:
        return []
    sleep = _health_map("sleep_score")
    readiness = _health_map("readiness_score")
    hrv = _health_map("hrv_overnight")
    rhr = _health_map("resting_hr")
    candidates = [
        time_of_day_insight(runs),
        rest_day_rebound_insight(runs),
        readiness_performance_insight(runs, readiness),
        hrv_performance_insight(runs, hrv),
        resting_hr_insight(runs, rhr),
        sleep_performance_insight(runs, sleep),
        cadence_efficiency_insight(runs),
        late_run_sleep_insight(runs, sleep),
    ]
    return [c for c in candidates if c]
