"""Advancing to the next training phase when a detailed block is finished.

A plan carries a full `macro` (Base → Build → …) but only one detailed 4-week
block in `next_month`. When it's done, `plan.advance_phase` generates the next
phase's weeks + a debrief. See `coach/plan.py`.
"""
from __future__ import annotations

import datetime as dt

import pytest

from garmin_coach import config
from garmin_coach import profile as prof
from garmin_coach.coach import plan as plan_mod


class FakeProvider:
    def __init__(self, out):
        self.out = out
        self.calls = 0

    def generate_json(self, prompt, schema, system=None, model=None, **kwargs):
        self.calls += 1
        return self.out


@pytest.fixture(autouse=True)
def _profile(monkeypatch):
    # context.brief_text (used by advance_phase) needs a profile; point it at the
    # scratch dir and seed one.
    monkeypatch.setattr(prof, "PROFILE_PATH", config.DATA_DIR / "profile.json")
    monkeypatch.setattr(prof, "OVERRIDES_PATH", config.DATA_DIR / "profile_overrides.json")
    prof.save_profile(prof.Profile(age=30, weight_kg=72.0))


def _finished_block_weeks(n=4):
    """n consecutive Sun–Sat weeks whose last week ended ~10 days ago (so the
    block is finished regardless of when the test runs)."""
    today = dt.date.today()
    end = today - dt.timedelta(days=10)
    end -= dt.timedelta(days=(end.weekday() - 5) % 7)      # snap to a Saturday
    weeks = []
    for i in range(n):
        s = end - dt.timedelta(days=7 * (n - 1 - i) + 6)   # that week's Sunday
        e = s + dt.timedelta(days=6)
        weeks.append({"week": f"Week {i + 1} ({s:%b %-d} – {e:%b %-d})",
                      "theme": "base",
                      "sessions": [{"day": "Mon", "type": "easy", "description": "easy"}]})
    return weeks, weeks[0]["week"]


def _plan(macro):
    weeks, first = _finished_block_weeks()
    gen = dt.date.today() - dt.timedelta(days=40)
    return {"generated_at": f"{gen.isoformat()}T08:00:00", "goal": "sub-50 10k",
            "preferred_days": [], "overrides": {"0:0": {"status": "done"}},
            "macro": macro, "next_month": weeks}


_MACRO = [
    {"phase": "Base", "weeks": "weeks 1-4", "focus": "aerobic base"},
    {"phase": "Build 1", "weeks": "weeks 5-8", "focus": "threshold",
     "weekly_volume_km": "40-45", "key_workouts": ["tempo"]},
]


def test_phase_status_detects_finished_block():
    plan = _plan(_MACRO)
    st = plan_mod.phase_status(plan)
    assert st["block_finished"] is True
    assert st["current_phase"]["phase"] == "Base"
    assert st["next_phase"]["phase"] == "Build 1"
    assert st["is_last"] is False


def test_advance_generates_next_block_and_debrief():
    plan_mod.save_latest(_plan(_MACRO))
    fake = FakeProvider({
        "weeks": [{"week": "Week 1 (build)", "theme": "build",
                   "sessions": [{"day": "Tue", "type": "tempo", "description": "20 min tempo"}]}],
        "debrief": {"headline": "Base nailed.",
                    "improve": ["Add a weekly tempo", "Keep easy days easy"]},
    })
    new = plan_mod.advance_phase(provider=fake)
    assert fake.calls == 1
    assert new["phase_index"] == 1                       # moved into Build 1
    assert new["next_month"] == fake.out["weeks"]        # block replaced
    assert new["phase_debrief"]["finished_phase"] == "Base"
    assert new["phase_debrief"]["improve"] == ["Add a weekly tempo", "Keep easy days easy"]
    assert new["overrides"] == {}                        # stale session keys cleared
    assert "congrats_ack" not in new

    # Idempotent: the new block isn't finished, so a second call is a no-op.
    again = plan_mod.advance_phase(provider=fake)
    assert fake.calls == 1
    assert again["phase_index"] == 1


def _future_block_all_done(n=2):
    """n training weeks starting *next* week (calendar not passed), every session
    marked done — the 'finished the work early' case."""
    from garmin_coach.coach.schedule import _week_start
    start = _week_start(dt.date.today()) + dt.timedelta(days=7)
    weeks, ov = [], {}
    for i in range(n):
        s = start + dt.timedelta(days=7 * i)
        e = s + dt.timedelta(days=6)
        weeks.append({"week": f"Week {i + 1} ({s:%b %-d} – {e:%b %-d})", "theme": "base",
                      "sessions": [{"day": "Mon", "type": "easy", "description": "easy"}]})
        ov[f"{i}:0"] = {"status": "done"}
    return weeks, ov


def test_finishing_the_work_early_advances_before_the_calendar():
    weeks, ov = _future_block_all_done()
    plan_mod.save_latest({"generated_at": f"{dt.date.today().isoformat()}T08:00:00",
                          "goal": "g", "preferred_days": [], "overrides": ov,
                          "macro": _MACRO, "next_month": weeks})
    st = plan_mod.phase_status(plan_mod.load_latest())
    assert st["block_finished"] is True          # all sessions done, calendar still future
    fake = FakeProvider({"weeks": [{"week": "W", "theme": "build",
                                    "sessions": [{"day": "Tue", "type": "tempo", "description": "t"}]}],
                         "debrief": {"headline": "h", "improve": ["a"]}})
    assert plan_mod.advance_phase(provider=fake)["phase_index"] == 1


def test_force_advances_when_block_not_finished():
    weeks, _ = _future_block_all_done()          # future weeks, but nothing done
    plan_mod.save_latest({"generated_at": f"{dt.date.today().isoformat()}T08:00:00",
                          "goal": "g", "preferred_days": [], "overrides": {},
                          "macro": _MACRO, "next_month": weeks})
    assert plan_mod.phase_status(plan_mod.load_latest())["block_finished"] is False
    fake = FakeProvider({"weeks": [{"week": "W", "theme": "build",
                                    "sessions": [{"day": "Tue", "type": "tempo", "description": "t"}]}],
                         "debrief": {"headline": "h", "improve": ["a"]}})
    assert plan_mod.advance_phase(provider=fake, force=False).get("phase_index", 0) in (0, None)
    assert fake.calls == 0                        # no-op without force
    assert plan_mod.advance_phase(provider=fake, force=True)["phase_index"] == 1
    assert fake.calls == 1


def test_last_phase_is_not_advanced():
    plan = _plan(_MACRO[:1])                             # only Base, no next phase
    plan_mod.save_latest(plan)
    st = plan_mod.phase_status(plan)
    assert st["block_finished"] is True and st["is_last"] is True and st["next_phase"] is None
    fake = FakeProvider({})
    out = plan_mod.advance_phase(provider=fake)
    assert fake.calls == 0                               # nothing to generate
    assert out.get("phase_index", 0) == 0
