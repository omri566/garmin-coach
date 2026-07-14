"""Regression tests for run -> planned-session matching and the manual-done path.

These cover the two coaching-engine defects:

  1. A completed run must satisfy the planned session for the day it was *really*
     performed (its activity start date), never the day it was synced — and it
     must not spill onto a later session even when its own day is already marked
     done. (`coach/schedule.build_schedule` / `_automatch`)
  2. The athlete's manual done/skip toggle must persist and be reflected in the
     schedule. (`coach/plan.set_override` + `build_schedule`)

Week model: training weeks run Sunday -> Saturday. The plan week below spans
Sun Jun 21 .. Sat Jun 27 2026, so Mon = Jun 22, Wed = Jun 24, Sat = Jun 27.
"""

from __future__ import annotations

import datetime as dt

from garmin_coach.coach import plan as plan_mod
from garmin_coach.coach import schedule

TODAY = dt.date(2026, 6, 24)  # a Wednesday, inside the plan week

# Mon easy + Wed easy + Sat long, with a Tue rest day.
SESSIONS = [
    {"day": "Mon", "type": "easy", "description": "easy 5k", "target": "Z2"},
    {"day": "Tue", "type": "rest", "description": "rest day"},
    {"day": "Wed", "type": "easy", "description": "easy 5k", "target": "Z2"},
    {"day": "Sat", "type": "long", "description": "long 15k"},
]


def base_plan(sessions=None, overrides=None):
    return {
        "generated_at": "2026-06-21T10:00:00",
        "overrides": overrides or {},
        "next_month": [{
            "week": "Week 1 (Jun 21 – Jun 27)",
            "theme": "base",
            "target_volume_km": 40,
            "sessions": sessions if sessions is not None else SESSIONS,
        }],
    }


def _by_day(sched):
    return {s["day"]: s for s in sched["weeks"][0]["sessions"]}


# --- 1. matching anchors to the activity's real day -------------------------


def test_same_day_run_matches_its_own_session(add_metric):
    """A run on Wednesday satisfies the Wednesday session, with no 'ran' note."""
    add_metric("2026-06-24T08:00:00", distance_m=5000.0)
    by_day = _by_day(schedule.build_schedule(base_plan(), today=TODAY))
    assert by_day["Wed"]["status"] == "done"
    assert by_day["Wed"]["match_date"] == dt.date(2026, 6, 24)
    assert by_day["Wed"]["note"] is None
    # The Monday session got no run, so it stays open.
    assert by_day["Mon"]["status"] == "missed"


def test_late_synced_run_matches_real_day_not_a_later_session(add_metric):
    """The reported bug: a Monday run, synced a day late, must satisfy Monday.

    The athlete had already marked Monday done. Before the fix the Monday run
    spilled onto the still-open Wednesday session (matched the wrong day); now it
    is consumed by its own day and Wednesday stays open.
    """
    # start_time is the real activity start (Monday); it was ingested Tuesday.
    add_metric("2026-06-22T19:42:00", distance_m=5000.0,
               computed_at="2026-06-23T08:03:00")
    overrides = {"0:0": {"status": "done"}}  # athlete marked Monday done
    by_day = _by_day(schedule.build_schedule(base_plan(overrides=overrides),
                                             today=TODAY))
    # Monday stays done (its own run); Wednesday is NOT credited the Monday run.
    assert by_day["Mon"]["status"] == "done"
    assert by_day["Wed"]["status"] != "done"
    assert by_day["Wed"].get("match") is None
    # No session is ever credited a run from a different day in this scenario.
    for s in (by_day["Mon"], by_day["Wed"], by_day["Sat"]):
        md = s.get("match_date")
        assert md is None or md == s["date"]


def test_run_anchored_to_start_date_when_a_session_exists_that_day(add_metric):
    """Even with other open sessions nearby, a run lands on its own day."""
    # Run on Monday with Mon/Wed/Sat sessions all open.
    add_metric("2026-06-22T18:00:00", distance_m=5000.0)
    by_day = _by_day(schedule.build_schedule(base_plan(), today=TODAY))
    assert by_day["Mon"]["status"] == "done"
    assert by_day["Mon"]["match_date"] == dt.date(2026, 6, 22)
    assert by_day["Wed"]["status"] != "done"


def test_manually_done_session_still_exposes_its_run_match(add_metric):
    """A manually-done day keeps the run→session link so the overview agrees.

    Regression: marking the day's session done (the natural post-run action)
    must not strip the run's `match`. The plan view shows the session done via
    the override; the overview recognises the run as planned only through
    `match.activity_id`. Before the fix the same-day run was silently consumed
    without a `match`, so the overview flagged an on-plan run as an "extra".
    """
    add_metric("2026-06-24T08:00:00", distance_m=5000.0)   # Wednesday run
    overrides = {"0:2": {"status": "done"}}                 # athlete marked Wed done
    by_day = _by_day(schedule.build_schedule(base_plan(overrides=overrides),
                                             today=TODAY))
    wed = by_day["Wed"]
    assert wed["status"] == "done"                          # manual status preserved
    assert wed.get("match") is not None                     # run stays attributed
    assert wed["match_date"] == dt.date(2026, 6, 24)
    assert wed["note"] is None                              # same-day: no drift note


def test_off_day_run_still_attaches_to_nearest_open_session(add_metric):
    """A run with no session on its own day keeps the 'did it early/late' note."""
    # Thursday run: no Thursday session -> nearest open is Wednesday.
    add_metric("2026-06-25T08:00:00", distance_m=8000.0)
    by_day = _by_day(schedule.build_schedule(base_plan(), today=TODAY))
    assert by_day["Wed"]["status"] == "done"
    assert by_day["Wed"]["note"] is not None and "ran" in by_day["Wed"]["note"]


def test_session_matches_main_run_not_same_day_strides(add_metric):
    """Two runs on one day: the session anchors to the main workout, not strides.

    The athlete logs a short strides set as a separate activity. Regardless of
    which run was started (or synced) first, the 5 km session run — not the
    0.5 km strides — must satisfy the day's session; the strides are an extra
    and must not spill onto another day's open session either.
    """
    # Strides logged *first* (and even synced first) — the pre-fix greedy pass
    # would have handed Wednesday's session to it.
    strides = add_metric("2026-06-24T07:30:00", distance_m=500.0)
    main = add_metric("2026-06-24T08:00:00", distance_m=5000.0)
    sched = schedule.build_schedule(base_plan(), today=TODAY)
    week = sched["weeks"][0]
    by_day = _by_day(sched)
    wed = by_day["Wed"]
    assert wed["status"] == "done"
    assert wed["match"]["activity_id"] == main
    # The strides are an extra, and they did NOT drift onto the open Sat session.
    assert by_day["Sat"]["status"] != "done"
    assert any(r["activity_id"] == strides for r in week["extras"])


# --- 2. manual done/skip toggle persists ------------------------------------


def test_manual_done_toggle_persists_and_reflects():
    """Marking an un-matched session done sticks across reload; clearing reverts."""
    plan_mod.save_latest(base_plan())          # active plan, no runs, no overrides
    by_day = _by_day(schedule.build_schedule(plan_mod.load_latest(), today=TODAY))
    assert by_day["Sat"]["status"] == "upcoming"

    # Mark the Saturday long run done (session index 3 in week 0).
    plan = plan_mod.set_override("0:3", {"status": "done"})
    assert plan["overrides"]["0:3"]["status"] == "done"
    # Persisted to disk: a fresh load still has it.
    assert plan_mod.load_latest()["overrides"]["0:3"]["status"] == "done"
    by_day = _by_day(schedule.build_schedule(plan_mod.load_latest(), today=TODAY))
    assert by_day["Sat"]["status"] == "done"

    # Toggling it off clears the override and the session returns to upcoming.
    plan = plan_mod.set_override("0:3", {"status": None})
    assert "0:3" not in plan.get("overrides", {})
    assert "0:3" not in plan_mod.load_latest().get("overrides", {})
    by_day = _by_day(schedule.build_schedule(plan_mod.load_latest(), today=TODAY))
    assert by_day["Sat"]["status"] == "upcoming"


def test_manual_skip_persists_over_no_run():
    """A manual skip is reflected as skipped and survives reload."""
    plan_mod.save_latest(base_plan())
    plan_mod.set_override("0:2", {"status": "skipped"})
    by_day = _by_day(schedule.build_schedule(plan_mod.load_latest(), today=TODAY))
    assert by_day["Wed"]["status"] == "skipped"
    assert plan_mod.load_latest()["overrides"]["0:2"]["status"] == "skipped"
