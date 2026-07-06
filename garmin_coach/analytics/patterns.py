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
            "SELECT start_time, avg_hr, ef, decoupling_pct FROM activity_metrics "
            "WHERE sport LIKE '%running%' AND start_time IS NOT NULL", conn)
    if df.empty:
        return df
    ts = pd.to_datetime(df["start_time"])
    df["hour"] = ts.dt.hour
    df["date"] = ts.dt.date
    df["weekday"] = ts.dt.day_name()
    return df


def _sleep_map() -> dict:
    with db.connect() as conn:
        df = pd.read_sql(
            "SELECT day, sleep_score FROM health_daily WHERE sleep_score IS NOT NULL",
            conn)
    if df.empty:
        return {}
    return dict(zip(pd.to_datetime(df["day"]).dt.date, df["sleep_score"]))


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
        dec_note = f" and hold pace better ({dec_best:.0f}% vs {dec_rest:.0f}% decoupling)"
    return {
        "kind": "time_of_day",
        "title": f"You run best in the {best}",
        "detail": (f"Your {_BUCKET_LABEL[best]} runs are {lift * 100:.0f}% more "
                   f"efficient (EF {g.loc[best, 'ef']:.2f} vs {rest:.2f}){dec_note}. "
                   f"Put key sessions there when you can."),
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
        "title": "Late runs cost you sleep",
        "detail": (f"After runs starting past 8pm your sleep score averages "
                   f"{late['next_sleep'].mean():.0f} vs {early['next_sleep'].mean():.0f} "
                   f"otherwise — try to finish hard efforts earlier."),
    }


def _corr_insight(runs, series_map, *, title_pos, title_neg, detail, kind):
    d = runs.dropna(subset=["ef"]).copy()
    d["x"] = d["date"].apply(lambda x: series_map.get(x))
    d = d.dropna(subset=["x"])
    if len(d) < _MIN_PAIRS:
        return None
    r = d["x"].corr(d["ef"])
    if pd.isna(r) or abs(r) < 0.25:
        return None
    return {"kind": kind, "title": title_pos if r > 0 else title_neg,
            "detail": detail.format(r=abs(r), n=len(d))}


def sleep_performance_insight(runs: pd.DataFrame, sleep: dict) -> dict | None:
    return _corr_insight(
        runs, sleep, kind="sleep_perf",
        title_pos="Good sleep lifts your runs",
        title_neg="Your runs hold up regardless of sleep",
        detail=("Nights you sleep well line up with more efficient runs the next "
                "day (r={r:.2f} across {n} runs) — protect sleep before key sessions."))


def personal_insights() -> list[dict]:
    """All patterns that clear their significance bar, strongest first."""
    runs = _runs()
    if runs.empty:
        return []
    sleep = _sleep_map()
    candidates = [
        time_of_day_insight(runs),
        late_run_sleep_insight(runs, sleep),
        sleep_performance_insight(runs, sleep),
    ]
    return [c for c in candidates if c]
