"""Daily health-metrics sync: recovery inputs for the coaching engine.

Per day we pull (and keep the full raw payloads for):
  - user summary  -> resting HR (+7d), body battery high/low, stress, steps
  - HRV           -> overnight avg (rMSSD-based), weekly avg, status
  - sleep         -> sleep score, total sleep seconds
  - readiness     -> training-readiness score, acute load

Incremental: days already stored are skipped unless --overwrite. Days with no
data still get a row (nulls) so gap detection (Phase 2) can tell "no data" from
"not yet synced".

Usage:
    python -m garmin_coach.ingest.health --days 30
    python -m garmin_coach.ingest.health --since 2025-06-01
    python -m garmin_coach.ingest.health --days 400 --overwrite
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import time
from typing import Any

from garminconnect import Garmin

from garmin_coach.ingest.client import get_client
from garmin_coach.store import db

log = logging.getLogger(__name__)


def _safe(fn, *args):
    """Call a Garmin endpoint, returning None on any per-day failure."""
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001
        log.debug("  endpoint %s failed: %s", getattr(fn, "__name__", fn), exc)
        return None


def _dig(d: Any, *path, default=None):
    cur = d
    for key in path:
        if isinstance(cur, list):
            cur = cur[key] if isinstance(key, int) and len(cur) > key else None
        elif isinstance(cur, dict):
            cur = cur.get(key)
        else:
            return default
        if cur is None:
            return default
    return cur


def build_row(day: str, summary, hrv, sleep, readiness) -> dict[str, Any]:
    return {
        "day": day,
        "resting_hr": _dig(summary, "restingHeartRate"),
        "resting_hr_7d": _dig(summary, "lastSevenDaysAvgRestingHeartRate"),
        "hrv_overnight": _dig(hrv, "hrvSummary", "lastNightAvg"),
        "hrv_weekly": _dig(hrv, "hrvSummary", "weeklyAvg"),
        "hrv_status": _dig(hrv, "hrvSummary", "status"),
        "sleep_score": _dig(sleep, "dailySleepDTO", "sleepScores", "overall", "value"),
        "sleep_seconds": _dig(sleep, "dailySleepDTO", "sleepTimeSeconds"),
        "body_battery_high": _dig(summary, "bodyBatteryHighestValue"),
        "body_battery_low": _dig(summary, "bodyBatteryLowestValue"),
        "stress_avg": _dig(summary, "averageStressLevel"),
        "steps": _dig(summary, "totalSteps"),
        "readiness_score": _dig(readiness, 0, "score"),
        "acute_load": _dig(readiness, 0, "acuteLoad"),
        "raw_json": {
            "summary": summary, "hrv": hrv, "sleep": sleep, "readiness": readiness,
        },
    }


def sync_day(client: Garmin, day: str, overwrite: bool) -> bool:
    if not overwrite and db.health_day_has_data(day):
        return False
    summary = _safe(client.get_user_summary, day)
    hrv = _safe(client.get_hrv_data, day)
    sleep = _safe(client.get_sleep_data, day)
    readiness = _safe(client.get_training_readiness, day)
    row = build_row(day, summary, hrv, sleep, readiness)
    db.upsert_health(row)
    log.info("health %s  rhr=%s hrv=%s sleep=%s readiness=%s",
             day, row["resting_hr"], row["hrv_overnight"],
             row["sleep_score"], row["readiness_score"])
    return True


def sync_health(client: Garmin, start: dt.date, end: dt.date,
                overwrite: bool = False, pause: float = 0.3,
                recent_days: int = 3) -> int:
    """Sync [start, end]. Days already holding a metric are skipped (incremental) —
    EXCEPT the most recent `recent_days`, which are always re-fetched. Garmin
    finalizes overnight metrics (sleep, HRV, readiness) hours apart, so a day first
    written when only some metrics existed would otherwise be 'locked' by
    `health_day_has_data` and never backfill last night's sleep. Re-pulling the
    trailing window each run fills those in."""
    db.init_db()
    n = 0
    recent_cutoff = end - dt.timedelta(days=max(0, recent_days - 1))
    day = start
    while day <= end:
        force = overwrite or day >= recent_cutoff
        if sync_day(client, day.isoformat(), force):
            n += 1
            time.sleep(pause)  # be polite to Garmin
        day += dt.timedelta(days=1)
    return n


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description="Sync daily Garmin health metrics.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--days", type=int, help="Sync the last N days (incl. today).")
    g.add_argument("--since", type=str, help="Sync from YYYY-MM-DD to today.")
    p.add_argument("--until", type=str, help="End date YYYY-MM-DD (default today).")
    p.add_argument("--overwrite", action="store_true", help="Re-sync existing days.")
    args = p.parse_args()

    end = dt.date.fromisoformat(args.until) if args.until else dt.date.today()
    if args.since:
        start = dt.date.fromisoformat(args.since)
    elif args.days:
        start = end - dt.timedelta(days=args.days - 1)
    else:
        start = end - dt.timedelta(days=29)  # default: last 30 days

    client = get_client()
    n = sync_health(client, start, end, overwrite=args.overwrite)
    log.info("done: %d day(s) synced (%s..%s)", n, start, end)


if __name__ == "__main__":
    main()
