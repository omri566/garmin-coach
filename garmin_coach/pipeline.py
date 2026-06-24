"""One-shot update of the whole data + analytics pipeline.

Logs in once, then: syncs new activities, refreshes recent health days,
re-fetches the athlete profile, and recomputes per-activity features. Safe to
run repeatedly (everything is incremental) — this is the command a scheduled job
calls. Launch the dashboard separately.

Usage:
    python -m garmin_coach.pipeline                 # examine 50 recent + 14 health days
    python -m garmin_coach.pipeline --examine 200   # deeper activity backfill
    python -m garmin_coach.pipeline --health-days 30 --no-profile
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging

from garmin_coach import profile as prof
from garmin_coach.analytics import compute
from garmin_coach.coach import recommend
from garmin_coach.ingest import health, sync
from garmin_coach.ingest.client import get_client

log = logging.getLogger(__name__)


def update(examine: int = 50, health_days: int = 14,
           refresh_profile: bool = True,
           refresh_recommendations: bool = True) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    client = get_client()

    log.info("→ syncing activities (examining %d most recent)…", examine)
    sync.run(limit=examine, client=client)

    log.info("→ syncing last %d health days…", health_days)
    end = dt.date.today()
    start = end - dt.timedelta(days=health_days - 1)
    health.sync_health(client, start, end)

    if refresh_profile:
        log.info("→ refreshing athlete profile…")
        prof.save_profile(prof.fetch_profile(client))

    log.info("→ computing per-activity features…")
    compute.run()

    # Recommendations refresh with the latest data; the PLAN is intentionally
    # left untouched so a plan in progress never changes mid-block.
    if refresh_recommendations:
        log.info("→ refreshing recommendations (plan left unchanged)…")
        try:
            recommend.recommend()
        except Exception as exc:  # noqa: BLE001 - never fail the data update on LLM
            log.warning("  recommendations skipped: %s", exc)

    log.info("✓ update complete.")


def main() -> None:
    p = argparse.ArgumentParser(description="Update the full Garmin Coach pipeline.")
    p.add_argument("--examine", type=int, default=50,
                   help="How many recent activities to examine (incremental).")
    p.add_argument("--health-days", type=int, default=14)
    p.add_argument("--no-profile", action="store_true",
                   help="Skip re-fetching the athlete profile.")
    p.add_argument("--no-recommend", action="store_true",
                   help="Skip refreshing recommendations (data only).")
    args = p.parse_args()
    update(examine=args.examine, health_days=args.health_days,
           refresh_profile=not args.no_profile,
           refresh_recommendations=not args.no_recommend)


if __name__ == "__main__":
    main()
