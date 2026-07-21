"""Health sync re-fetches the trailing window so late overnight metrics backfill.

Garmin finalizes sleep / HRV / readiness hours apart. `health_day_has_data` marks
a day 'done' once *any* metric exists, so a day first written before sleep landed
would be skipped forever by the incremental sync. `sync_health` therefore force-
re-fetches the most recent `recent_days`, regardless of that skip check.
"""
from __future__ import annotations

import datetime as dt

from garmin_coach.ingest import health


def _capture_calls(monkeypatch):
    calls: list[tuple[str, bool]] = []

    def fake_sync_day(client, day, overwrite):
        calls.append((day, overwrite))
        return True

    monkeypatch.setattr(health, "sync_day", fake_sync_day)
    return calls


def test_recent_days_are_forced_older_days_incremental(monkeypatch):
    calls = _capture_calls(monkeypatch)
    end = dt.date(2026, 7, 21)
    start = end - dt.timedelta(days=5)                 # 6-day window
    health.sync_health(client=object(), start=start, end=end, pause=0, recent_days=3)

    forced = {day for day, ov in calls if ov}
    incremental = {day for day, ov in calls if not ov}
    # The last 3 days (19th, 20th, 21st) are always re-fetched…
    assert forced == {"2026-07-19", "2026-07-20", "2026-07-21"}
    # …older days stay incremental (skip-if-already-present).
    assert incremental == {"2026-07-16", "2026-07-17", "2026-07-18"}


def test_overwrite_forces_every_day(monkeypatch):
    calls = _capture_calls(monkeypatch)
    end = dt.date(2026, 7, 21)
    health.sync_health(client=object(), start=end - dt.timedelta(days=4), end=end,
                       overwrite=True, pause=0, recent_days=3)
    assert all(ov for _, ov in calls) and len(calls) == 5
