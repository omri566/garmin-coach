"""Compute per-activity features for every activity into `activity_metrics`.

Incremental by default (skips activities already computed); --rebuild redoes all.

Usage:
    python -m garmin_coach.analytics.compute
    python -m garmin_coach.analytics.compute --rebuild
"""
from __future__ import annotations

import argparse
import json
import logging

from garmin_coach.analytics.features import compute_features
from garmin_coach.profile import load_profile
from garmin_coach.store import db, streams

log = logging.getLogger(__name__)

METRIC_COLS = {
    "moving_s", "distance_m", "avg_pace_s_km", "avg_hr", "max_hr",
    "z1_s", "z2_s", "z3_s", "z4_s", "z5_s", "avg_cadence_spm",
    "avg_vert_osc_mm", "avg_vert_ratio", "avg_gct_ms", "avg_gct_balance",
    "avg_step_len_mm", "avg_power_w", "np_power_w", "ef", "decoupling_pct",
    "trimp", "rtss", "training_stress", "has_dynamics",
}


def _computed_ids() -> set[int]:
    with db.connect() as conn:
        return {r[0] for r in conn.execute("SELECT activity_id FROM activity_metrics")}


def run(rebuild: bool = False) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db.init_db()
    profile = load_profile()
    done = set() if rebuild else _computed_ids()

    with db.connect() as conn:
        acts = conn.execute(
            "SELECT activity_id, start_time, sport, streams_path, raw_json "
            "FROM activities ORDER BY start_time"
        ).fetchall()

    n = errors = 0
    for a in acts:
        aid = a["activity_id"]
        if aid in done:
            continue
        if not a["streams_path"]:
            continue
        try:
            df = streams.read_streams(aid)
            summary = json.loads(a["raw_json"]) if a["raw_json"] else {}
            feats = compute_features(df, profile, summary)
            row = {
                "activity_id": aid,
                "start_time": a["start_time"],
                "sport": a["sport"],
                "features_json": feats,
                **{k: feats.get(k) for k in METRIC_COLS},
            }
            db.upsert_metrics(row)
            n += 1
        except Exception as exc:  # noqa: BLE001
            errors += 1
            log.warning("  features failed for %s: %s", aid, exc)
    log.info("computed features for %d activities (%d errors)", n, errors)


def main() -> None:
    p = argparse.ArgumentParser(description="Compute per-activity features.")
    p.add_argument("--rebuild", action="store_true", help="Recompute all activities.")
    run(rebuild=p.parse_args().rebuild)


if __name__ == "__main__":
    main()
