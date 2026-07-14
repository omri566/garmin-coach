"""The post-workout coach read works for an unplanned run (no session), grounded
in the run's own metrics, and caches so the LLM runs once per activity.
See `coach/execution.py`.
"""
from __future__ import annotations

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
