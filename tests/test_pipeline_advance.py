"""The nightly pipeline pre-builds the next training phase.

When a 4-week block is finished, `pipeline.update` calls `plan.advance_phase` on
the server (where the LLM runs for real, off any web-request timeout) so the next
block is already in place when the athlete opens the app — no on-demand spinner.
This checks the wiring: the pipeline advances a finished plan and leaves an
unfinished one untouched, with all the network/compute steps stubbed out.
"""
from __future__ import annotations

import datetime as dt

import pytest

from garmin_coach import config, pipeline
from garmin_coach import profile as prof
from garmin_coach.coach import plan as plan_mod


class _Fake:
    def generate_json(self, prompt, schema, system=None, model=None, **kwargs):
        return {"weeks": [{"week": "W", "theme": "build",
                           "sessions": [{"day": "Tue", "type": "tempo",
                                         "description": "20 min tempo"}]}],
                "debrief": {"headline": "Base nailed.", "improve": ["Add a tempo"]}}


_MACRO = [
    {"phase": "Base", "weeks": "weeks 1-4", "focus": "aerobic base"},
    {"phase": "Build 1", "weeks": "weeks 5-8", "focus": "threshold"},
]


@pytest.fixture(autouse=True)
def _stub_pipeline(monkeypatch):
    """Point profile paths at the scratch dir and stub every network/compute step
    so `update` exercises only the pre-generation wiring."""
    monkeypatch.setattr(prof, "PROFILE_PATH", config.DATA_DIR / "profile.json")
    monkeypatch.setattr(prof, "OVERRIDES_PATH", config.DATA_DIR / "profile_overrides.json")
    prof.save_profile(prof.Profile(age=30, weight_kg=72.0))
    monkeypatch.setattr(pipeline, "get_client", lambda: object())
    monkeypatch.setattr(pipeline.sync, "run", lambda **k: None)
    monkeypatch.setattr(pipeline.health, "sync_health", lambda *a, **k: None)
    monkeypatch.setattr(pipeline.compute, "run", lambda *a, **k: None)
    monkeypatch.setattr(plan_mod, "get_provider", lambda *a, **k: _Fake())


def _finished_plan():
    """A Base block whose 4 weeks all ended ~10 days ago (calendar finished)."""
    today = dt.date.today()
    end = today - dt.timedelta(days=10)
    end -= dt.timedelta(days=(end.weekday() - 5) % 7)       # snap to a Saturday
    weeks = []
    for i in range(4):
        s = end - dt.timedelta(days=7 * (3 - i) + 6)
        e = s + dt.timedelta(days=6)
        weeks.append({"week": f"Week {i + 1} ({s:%b %-d} – {e:%b %-d})", "theme": "base",
                      "sessions": [{"day": "Mon", "type": "easy", "description": "easy"}]})
    return {"generated_at": f"{today.isoformat()}T08:00:00", "goal": "sub-50 10k",
            "preferred_days": [], "overrides": {}, "macro": _MACRO, "next_month": weeks}


def _unfinished_plan():
    """A Base block starting this week — not finished, nothing done."""
    from garmin_coach.coach.schedule import _week_start
    start = _week_start(dt.date.today())
    weeks = []
    for i in range(4):
        s = start + dt.timedelta(days=7 * i)
        e = s + dt.timedelta(days=6)
        weeks.append({"week": f"Week {i + 1} ({s:%b %-d} – {e:%b %-d})", "theme": "base",
                      "sessions": [{"day": "Mon", "type": "easy", "description": "easy"}]})
    return {"generated_at": f"{dt.date.today().isoformat()}T08:00:00", "goal": "g",
            "preferred_days": [], "overrides": {}, "macro": _MACRO, "next_month": weeks}


def test_pipeline_advances_a_finished_block():
    plan_mod.save_latest(_finished_plan())
    pipeline.update(refresh_profile=False, refresh_recommendations=False)
    assert plan_mod.load_latest()["phase_index"] == 1          # moved into Build 1


def test_pipeline_leaves_an_unfinished_block_untouched():
    plan_mod.save_latest(_unfinished_plan())
    pipeline.update(refresh_profile=False, refresh_recommendations=False)
    assert plan_mod.load_latest().get("phase_index", 0) == 0   # nothing to advance


def test_no_advance_flag_skips_pregeneration():
    plan_mod.save_latest(_finished_plan())
    pipeline.update(refresh_profile=False, refresh_recommendations=False,
                    advance_plan=False)
    assert plan_mod.load_latest().get("phase_index", 0) == 0   # skipped
