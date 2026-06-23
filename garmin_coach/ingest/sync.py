"""Incremental Garmin sync: pull activities end-to-end into the store.

For each new activity:
  1. download the ORIGINAL (.fit) -> highest-fidelity per-second streams
  2. parse FIT -> parquet streams
  3. upsert the Garmin summary (full raw JSON + indexed metrics) into SQLite

Already-ingested activities are skipped, so re-running only fetches new work.

Usage:
    python -m garmin_coach.ingest.sync --limit 1     # prove the pipeline
    python -m garmin_coach.ingest.sync --limit 50    # backfill recent
    python -m garmin_coach.ingest.sync --all         # full history
    python -m garmin_coach.ingest.sync --activity-id 1234567890
"""
from __future__ import annotations

import argparse
import logging
from typing import Any

from garminconnect import Garmin

from garmin_coach import config
from garmin_coach.ingest import fit_parser
from garmin_coach.ingest.client import get_client
from garmin_coach.store import db, streams

log = logging.getLogger(__name__)


def _g(d: dict[str, Any], *keys, default=None):
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return default


def _summary_row(act: dict[str, Any], fit_path: str, streams_path: str,
                 n_records: int) -> dict[str, Any]:
    atype = act.get("activityType") or {}
    return {
        "activity_id": int(act["activityId"]),
        "start_time": _g(act, "startTimeLocal"),
        "start_time_utc": _g(act, "startTimeGMT"),
        "sport": atype.get("typeKey"),
        "sub_sport": (act.get("eventType") or {}).get("typeKey")
        if isinstance(act.get("eventType"), dict) else None,
        "distance_m": _g(act, "distance"),
        "duration_s": _g(act, "duration"),
        "moving_s": _g(act, "movingDuration"),
        "avg_hr": _g(act, "averageHR"),
        "max_hr": _g(act, "maxHR"),
        "avg_speed_mps": _g(act, "averageSpeed"),
        "avg_cadence": _g(act, "averageRunningCadenceInStepsPerMinute",
                          "averageBikingCadenceInRevPerMinute"),
        "avg_power_w": _g(act, "avgPower"),
        "elevation_gain_m": _g(act, "elevationGain"),
        "vo2max": _g(act, "vO2MaxValue"),
        "training_load": _g(act, "activityTrainingLoad"),
        "fit_path": fit_path,
        "streams_path": streams_path,
        "n_records": n_records,
        "raw_json": act,
    }


def ingest_activity(client: Garmin, act: dict[str, Any]) -> bool:
    activity_id = int(act["activityId"])
    if db.activity_exists(activity_id):
        log.info("skip %s (already ingested)", activity_id)
        return False

    log.info("ingest %s  %s  %s", activity_id,
             act.get("startTimeLocal"), (act.get("activityType") or {}).get("typeKey"))

    raw = client.download_activity(
        activity_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL
    )
    parsed = fit_parser.parse_fit(raw)

    # Persist raw .fit (unwrapped) as source of truth.
    fit_path = config.FIT_DIR / f"{activity_id}.fit"
    fit_path.write_bytes(fit_parser.extract_fit_bytes(raw))

    n_records = len(parsed.records)
    spath = ""
    if n_records:
        spath = str(streams.write_streams(activity_id, parsed.records))

    db.upsert_activity(
        _summary_row(act, str(fit_path), spath, n_records)
    )
    log.info("  -> %d per-second records, %d laps", n_records, len(parsed.laps))
    return True


def run(limit: int | None, activity_id: int | None = None,
        client: Garmin | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db.init_db()
    client = client or get_client()

    if activity_id is not None:
        act = client.get_activity(activity_id)
        ingest_activity(client, act)
        return

    fetched = 0
    page = 0
    page_size = 50 if (limit is None or limit > 50) else limit
    new = 0
    while True:
        acts = client.get_activities(page, page_size)
        if not acts:
            break
        for act in acts:
            if limit is not None and fetched >= limit:
                log.info("done: %d new of %d examined", new, fetched)
                return
            fetched += 1
            if ingest_activity(client, act):
                new += 1
        page += page_size
        if limit is None:  # --all: keep paging until Garmin returns nothing
            continue
        if fetched >= limit:
            break
    log.info("done: %d new of %d examined", new, fetched)


def main() -> None:
    p = argparse.ArgumentParser(description="Sync Garmin activities into the store.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--limit", type=int, default=1,
                   help="Examine the N most recent activities (default 1).")
    g.add_argument("--all", action="store_true", help="Full history.")
    p.add_argument("--activity-id", type=int, help="Ingest one specific activity.")
    args = p.parse_args()

    run(limit=None if args.all else args.limit, activity_id=args.activity_id)


if __name__ == "__main__":
    main()
