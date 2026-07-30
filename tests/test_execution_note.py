"""The post-workout coach read works for an unplanned run (no session), grounded
in the run's own metrics, and caches so the LLM runs once per activity.
See `coach/execution.py`.
"""
from __future__ import annotations

import time

import pytest

from garmin_coach import config
from garmin_coach.coach import execution


class FakeProvider:
    def __init__(self, out):
        self.out = out
        self.calls = 0

    def generate_json(self, prompt, schema, system=None, model=None):
        self.calls += 1
        return self.out


@pytest.fixture(autouse=True)
def verdicts_dir(monkeypatch):
    monkeypatch.setattr(execution, "_DIR", config.DATA_DIR / "verdicts")


def test_note_for_unplanned_run_caches():
    fake = FakeProvider({"headline": "Easy and controlled",
                         "detail": "Steady aerobic run, HR in check."})
    run = {"activity_id": 7, "distance_m": 8000, "avg_pace_s_km": 330,
           "avg_hr": 140, "decoupling_pct": 3.2}
    out = execution.make_note(None, run, streams=None, provider=fake)
    assert out["headline"] == "Easy and controlled"
    assert execution.cached(7)["activity_id"] == 7

    # ensure_note reads the cache instead of calling the LLM again.
    again = execution.ensure_note(run, None, streams=None, provider=fake)
    assert fake.calls == 1
    assert again["detail"].startswith("Steady")


# --- Async generation (background thread + note_state poll) -----------------


def _wait_state(aid, target, timeout=4.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if execution.note_state(aid).get("state") == target:
            break
        time.sleep(0.02)
    return execution.note_state(aid)


def test_note_state_reflects_on_disk_status():
    assert execution.note_state(101)["state"] == "idle"          # nothing yet
    execution._write_status(101, "running")
    assert execution.note_state(101)["state"] == "running"
    # A 'running' status older than the cap reads as a timeout error.
    import datetime as dt
    import json
    execution._status_path(101).write_text(json.dumps(
        {"state": "running", "error": None,
         "ts": (dt.datetime.now() - dt.timedelta(seconds=execution._NOTE_MAX_S + 5)).isoformat()}))
    assert execution.note_state(101)["state"] == "error"


def test_start_note_runs_in_background_and_caches():
    fake = FakeProvider({"headline": "Nailed the tempo", "detail": "Reps on pace."})
    run = {"activity_id": 21, "distance_m": 9000, "avg_pace_s_km": 300, "avg_hr": 165}
    assert execution.note_state(21)["state"] == "idle"
    execution.start_note(run, None, streams=None, provider=fake)
    st = _wait_state(21, "done")
    assert st["state"] == "done"
    assert execution.cached(21)["headline"] == "Nailed the tempo"
    assert not execution._status_path(21).exists()               # status cleared on success


def test_start_note_surfaces_errors():
    class Boom:
        def generate_json(self, prompt, schema, system=None, model=None):
            raise RuntimeError("cli exploded")

    run = {"activity_id": 22, "distance_m": 5000, "avg_pace_s_km": 360, "avg_hr": 150}
    execution.start_note(run, None, streams=None, provider=Boom())
    st = _wait_state(22, "error")
    assert st["state"] == "error"
    assert "cli exploded" in st["error"]


def test_start_note_is_a_noop_when_already_cached():
    fake = FakeProvider({"headline": "h", "detail": "d"})
    run = {"activity_id": 23, "distance_m": 4000, "avg_pace_s_km": 400, "avg_hr": 140}
    execution.make_note(None, run, streams=None, provider=fake)   # pre-cache (1 call)
    execution.start_note(run, None, streams=None, provider=fake)  # cached → no thread
    time.sleep(0.1)
    assert fake.calls == 1
