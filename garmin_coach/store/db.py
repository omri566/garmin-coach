"""SQLite store for activity & health summaries.

Dense per-second streams live in parquet (see store/streams.py); SQLite holds
summary/metric rows that drive trends and fast queries. We keep the full raw
Garmin summary JSON per activity so no upstream field is ever lost.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from garmin_coach import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    activity_id   INTEGER PRIMARY KEY,
    start_time    TEXT,          -- ISO8601 local
    start_time_utc TEXT,
    sport         TEXT,
    sub_sport     TEXT,
    distance_m    REAL,
    duration_s    REAL,
    moving_s      REAL,
    avg_hr        REAL,
    max_hr        REAL,
    avg_speed_mps REAL,
    avg_cadence   REAL,
    avg_power_w   REAL,
    elevation_gain_m REAL,
    vo2max        REAL,
    training_load REAL,
    fit_path      TEXT,
    streams_path  TEXT,
    n_records     INTEGER,       -- per-second sample count captured
    raw_json      TEXT,          -- full Garmin summary
    ingested_at   TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_activities_start ON activities(start_time_utc);
CREATE INDEX IF NOT EXISTS idx_activities_sport ON activities(sport);

CREATE TABLE IF NOT EXISTS health_daily (
    day            TEXT PRIMARY KEY,   -- YYYY-MM-DD
    resting_hr     REAL,
    resting_hr_7d  REAL,               -- Garmin 7-day avg resting HR
    hrv_overnight  REAL,               -- overnight avg HRV (ms, rMSSD-based)
    hrv_weekly     REAL,               -- 7-day avg HRV
    hrv_status     TEXT,               -- BALANCED / UNBALANCED / LOW / ...
    sleep_score    REAL,
    sleep_seconds  REAL,
    body_battery_high REAL,
    body_battery_low  REAL,
    stress_avg     REAL,
    steps          INTEGER,
    readiness_score REAL,              -- training readiness (0-100)
    acute_load     REAL,               -- acute training load from readiness payload
    raw_json       TEXT,               -- combined raw payloads (summary/hrv/sleep/readiness)
    ingested_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sync_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Per-activity derived features (Phase 2). Computed once from the per-second
-- streams + athlete profile; all trends read from here, not from parquet.
CREATE TABLE IF NOT EXISTS activity_metrics (
    activity_id   INTEGER PRIMARY KEY,
    start_time    TEXT,
    sport         TEXT,
    moving_s      REAL,
    distance_m    REAL,
    avg_pace_s_km REAL,
    avg_hr        REAL,
    max_hr        REAL,
    z1_s REAL, z2_s REAL, z3_s REAL, z4_s REAL, z5_s REAL,
    avg_cadence_spm  REAL,
    avg_vert_osc_mm  REAL,
    avg_vert_ratio   REAL,
    avg_gct_ms       REAL,
    avg_gct_balance  REAL,
    avg_step_len_mm  REAL,
    avg_power_w   REAL,
    np_power_w    REAL,
    ef            REAL,    -- efficiency factor: speed(m/min)/avg HR
    decoupling_pct REAL,   -- aerobic decoupling (Pa:Hr), 1st vs 2nd half
    trimp         REAL,    -- Banister training impulse
    rtss          REAL,    -- pace-based training stress (runs)
    training_stress REAL,  -- Garmin load if present, else trimp
    has_dynamics  INTEGER,
    computed_at   TEXT DEFAULT (datetime('now')),
    features_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_metrics_start ON activity_metrics(start_time);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        # Drop empty legacy health_daily so the richer schema applies cleanly.
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='health_daily'"
        ).fetchone()
        if row:
            n = conn.execute("SELECT COUNT(*) FROM health_daily").fetchone()[0]
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(health_daily)")}
            if n == 0 and "hrv_overnight" not in cols:
                conn.execute("DROP TABLE health_daily")
        conn.executescript(SCHEMA)


def health_day_has_data(day: str) -> bool:
    """True only if the day is stored *and* has at least one real metric.

    An all-null row (e.g. today's not-yet-computed metrics) returns False so it
    gets retried on the next sync once Garmin finalizes the overnight data.
    """
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM health_daily WHERE day = ? AND "
            "(resting_hr IS NOT NULL OR hrv_overnight IS NOT NULL "
            "OR sleep_score IS NOT NULL OR readiness_score IS NOT NULL)",
            (day,),
        ).fetchone()
        return row is not None


def upsert_health(row: dict[str, Any]) -> None:
    if isinstance(row.get("raw_json"), (dict, list)):
        row = {**row, "raw_json": json.dumps(row["raw_json"], default=str)}
    cols = list(row.keys())
    placeholders = ",".join("?" for _ in cols)
    collist = ",".join(cols)
    with connect() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO health_daily ({collist}) VALUES ({placeholders})",
            [row[c] for c in cols],
        )


def activity_exists(activity_id: int) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM activities WHERE activity_id = ?", (activity_id,)
        ).fetchone()
        return row is not None


def upsert_metrics(row: dict[str, Any]) -> None:
    if isinstance(row.get("features_json"), (dict, list)):
        row = {**row, "features_json": json.dumps(row["features_json"], default=str)}
    cols = list(row.keys())
    placeholders = ",".join("?" for _ in cols)
    with connect() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO activity_metrics ({','.join(cols)}) "
            f"VALUES ({placeholders})",
            [row[c] for c in cols],
        )


def upsert_activity(row: dict[str, Any]) -> None:
    """Insert/replace an activity summary row. `raw_json` may be a dict."""
    if isinstance(row.get("raw_json"), (dict, list)):
        row = {**row, "raw_json": json.dumps(row["raw_json"])}
    cols = list(row.keys())
    placeholders = ",".join("?" for _ in cols)
    collist = ",".join(cols)
    with connect() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO activities ({collist}) VALUES ({placeholders})",
            [row[c] for c in cols],
        )
