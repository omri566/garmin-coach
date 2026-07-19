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
           refresh_recommendations: bool = True,
           advance_plan: bool = True) -> None:
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

    # Pre-build the next training phase *here*, on the server, where the LLM runs
    # for real and there's no web-request timeout. `advance_phase` is a no-op unless
    # the current 4-week block is finished (calendar passed OR all work done) and a
    # next macro phase exists — so calling it every run is safe and idempotent. When
    # it does fire, the detailed next block is already in place the moment the athlete
    # opens the app: no on-demand "building your next phase…" spinner, just the new
    # weeks + a congrats. (The dashboard keeps an on-demand path as a fallback for
    # finishing a block between nightly runs.)
    if advance_plan:
        log.info("→ pre-building the next training phase if the block is finished…")
        try:
            from garmin_coach.coach import plan as plan_mod
            before = (plan_mod.load_latest() or {}).get("phase_index", 0)
            new = plan_mod.advance_phase()
            after = (new or {}).get("phase_index", 0)
            if after != before:
                log.info("  ✓ advanced to phase_index=%d — next block ready.", after)
            else:
                log.info("  (block not finished or no next phase — nothing to do)")
        except Exception as exc:  # noqa: BLE001 - never fail the data update on LLM
            log.warning("  next-phase pre-generation skipped: %s", exc)

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
    p.add_argument("--no-advance", action="store_true",
                   help="Skip pre-building the next training phase when a block is finished.")
    args = p.parse_args()
    update(examine=args.examine, health_days=args.health_days,
           refresh_profile=not args.no_profile,
           refresh_recommendations=not args.no_recommend,
           advance_plan=not args.no_advance)


if __name__ == "__main__":
    main()
