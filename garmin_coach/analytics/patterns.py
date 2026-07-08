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
            "distance_m FROM activity_metrics "
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


def _lag_corr(runs, series_map, ycol="ef"):
    """Correlate a per-day health value with a run metric on the same day.
    Returns (pearson_r or None, n)."""
    d = runs.dropna(subset=[ycol]).copy()
    d["x"] = d["date"].map(lambda k: series_map.get(k))
    d = d.dropna(subset=["x"])
    if len(d) < _MIN_PAIRS:
        return None, 0
    r = d["x"].corr(d[ycol])
    return (None if pd.isna(r) else float(r)), len(d)


def _bucket(hour: int) -> str:
    for name, lo, hi in _BUCKETS:
        if lo <= hour < hi:
            return name
    return "evening"


def time_of_day_insight(runs: pd.DataFrame) -> dict | None:
    """Which time of day the athlete runs most efficiently (EF), if one clearly
    stands out. EF = speed per heartbeat, so higher = more aerobically efficient."""
    d = runs.dropna(subset=["ef"]).copy()
    if len(d) < 2 * _MIN_BUCKET:
        return None
    d["bucket"] = d["hour"].apply(_bucket)
    g = d.groupby("bucket").agg(n=("ef", "size"), ef=("ef", "mean"),
                                decoup=("decoupling_pct", "mean"))
    g = g[g["n"] >= _MIN_BUCKET]
    if len(g) < 2:
        return None
    best = g["ef"].idxmax()
    rest = d[d["bucket"] != best]["ef"].mean()
    lift = (g.loc[best, "ef"] - rest) / rest if rest else 0
    if lift < 0.02:                     # < 2% better → not worth calling out
        return None
    dec_best, dec_rest = g.loc[best, "decoup"], d[d["bucket"] != best]["decoupling_pct"].mean()
    dec_note = ""
    if pd.notna(dec_best) and pd.notna(dec_rest) and dec_best < dec_rest - 1:
        dec_note = " and you hold pace better through the run"
    return {
        "kind": "time_of_day",
        "title": f"Run your key sessions in the {best}",
        "detail": (f"That's when you're at your best — your {_BUCKET_LABEL[best]} "
                   f"runs come out about {lift * 100:.0f}% more efficient"
                   f"{dec_note}. Try to schedule the hard stuff then."),
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
    """Whether a quicker cadence goes with more efficient running for the athlete."""
    d = runs.dropna(subset=["ef", "avg_cadence_spm"])
    if len(d) < _MIN_PAIRS:
        return None
    r = d["avg_cadence_spm"].corr(d["ef"])
    if pd.isna(r) or r < 0.25:
        return None
    return {
        "kind": "cadence",
        "title": "Lean into a quicker cadence",
        "detail": ("Your runs come out more efficient when your cadence is higher — "
                   "a slightly quicker turnover pays off for you."),
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
