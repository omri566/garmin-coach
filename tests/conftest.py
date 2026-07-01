"""Shared fixtures: keep every test hermetic and offline.

No test touches the real data dir, hits Garmin, or calls an LLM. The ``gc_data``
fixture repoints ``config`` (and therefore ``store.db`` and ``coach.plan``) at a
per-test scratch directory and seeds a fresh SQLite schema via the project's own
DDL.
"""

from __future__ import annotations

import pytest

from garmin_coach import config
from garmin_coach.coach import plan as plan_mod
from garmin_coach.store import db


@pytest.fixture(autouse=True)
def gc_data(tmp_path, monkeypatch):
    """Point all data paths at a throwaway dir so tests never touch real data."""
    data = tmp_path / "gc-data"
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "DB_PATH", data / "garmin.db")
    monkeypatch.setattr(config, "FIT_DIR", data / "fit")
    monkeypatch.setattr(config, "STREAMS_DIR", data / "streams")
    monkeypatch.setattr(config, "TOKENS_DIR", data / ".garth")
    # coach.plan binds these paths at import time, so repoint them too.
    monkeypatch.setattr(plan_mod, "PLAN_DIR", data / "plans")
    monkeypatch.setattr(plan_mod, "_PREFS_PATH", data / "plans" / "preferences.json")
    db.init_db()
    return data


def seed_metric(start_time: str, **cols) -> int:
    """Insert one ``activity_metrics`` row, auto-assigning a unique id."""
    with db.connect() as conn:
        next_id = conn.execute(
            "SELECT COALESCE(MAX(activity_id), 0) + 1 FROM activity_metrics"
        ).fetchone()[0]
    row = {"activity_id": next_id, "start_time": start_time,
           "sport": "running", **cols}
    db.upsert_metrics(row)
    return next_id


@pytest.fixture
def add_metric():
    """Factory fixture to seed activity_metrics rows in a test's scratch DB."""
    return seed_metric
