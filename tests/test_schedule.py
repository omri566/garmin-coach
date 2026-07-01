"""Plan scheduling: week-range parsing, date anchoring and per-session status."""

from __future__ import annotations

import datetime as dt

from garmin_coach.coach import schedule

# --- parse_week_range -------------------------------------------------------


def test_parse_week_range_basic():
    assert schedule.parse_week_range("Week 1 (Jun 23 – Jun 29)", 2026) == (
        dt.date(2026, 6, 23),
        dt.date(2026, 6, 29),
    )


def test_parse_week_range_hyphen_and_full_month_names():
    # Plain hyphen separator and long month names both supported.
    assert schedule.parse_week_range("Week 2 (July 1 - July 7)", 2026) == (
        dt.date(2026, 7, 1),
        dt.date(2026, 7, 7),
    )


def test_parse_week_range_crosses_new_year():
    start, end = schedule.parse_week_range("Week 5 (Dec 29 – Jan 4)", 2026)
    assert start == dt.date(2026, 12, 29)
    assert end == dt.date(2027, 1, 4)  # end bumped into the next year


def test_parse_week_range_ref_bumps_inferred_year():
    # If the parsed start is >60 days before the reference date, assume next year.
    ref = dt.date(2027, 6, 1)
    start, end = schedule.parse_week_range("Week 1 (Jun 23 – Jun 29)", 2026, ref=ref)
    assert start.year == 2027 and end.year == 2027


def test_parse_week_range_malformed_returns_none():
    assert schedule.parse_week_range("Week 1 — no dates here", 2026) is None
    assert schedule.parse_week_range("", 2026) is None
    assert schedule.parse_week_range("Week (Foo 3 – Bar 9)", 2026) is None


# --- build_schedule ---------------------------------------------------------

TODAY = dt.date(2026, 6, 24)  # a Wednesday


def base_plan(sessions, overrides=None):
    return {
        "generated_at": "2026-06-21T10:00:00",
        "overrides": overrides or {},
        "next_month": [
            {
                "week": "Week 1 (Jun 21 – Jun 27)",
                "theme": "base",
                "target_volume_km": 40,
                "sessions": sessions,
            }
        ],
    }


SESSIONS = [
    {"day": "Sun", "type": "easy", "description": "easy 5k", "target": "Z2"},
    {"day": "Wed", "type": "intervals", "description": "6x800"},
    {"day": "Sat", "type": "long", "description": "long 15k"},
    {"day": "Mon", "type": "rest", "description": "rest day"},
]


def test_schedule_anchors_to_sunday_saturday_window():
    sched = schedule.build_schedule(base_plan(SESSIONS), today=TODAY)
    wk = sched["weeks"][0]
    assert wk["start"] == dt.date(2026, 6, 21)  # Sunday
    assert wk["end"] == dt.date(2026, 6, 27)  # Saturday
    assert wk["is_current"] is True
    assert sched["current_index"] == 0
    assert sched["today"] == TODAY
    assert len(wk["days"]) == 7


def test_status_missed_today_upcoming_rest():
    sched = schedule.build_schedule(base_plan(SESSIONS), today=TODAY)
    by_day = {s["day"]: s for s in sched["weeks"][0]["sessions"]}
    assert by_day["Sun"]["status"] == "missed"  # Jun 21 < today
    assert by_day["Wed"]["status"] == "today"  # Jun 24 == today
    assert by_day["Sat"]["status"] == "upcoming"  # Jun 27 > today
    assert by_day["Mon"]["status"] == "rest"


def test_session_dates_match_weekday():
    sched = schedule.build_schedule(base_plan(SESSIONS), today=TODAY)
    by_day = {s["day"]: s for s in sched["weeks"][0]["sessions"]}
    assert by_day["Sun"]["date"] == dt.date(2026, 6, 21)
    assert by_day["Wed"]["date"] == dt.date(2026, 6, 24)
    assert by_day["Sat"]["date"] == dt.date(2026, 6, 27)


def test_done_and_total_counts_exclude_rest():
    sched = schedule.build_schedule(base_plan(SESSIONS), today=TODAY)
    wk = sched["weeks"][0]
    assert wk["total"] == 3  # easy, intervals, long (rest excluded)
    assert wk["done"] == 0  # nothing matched/overridden yet


def test_status_override_done_and_skipped():
    overrides = {"0:0": {"status": "done"}, "0:1": {"status": "skipped"}}
    sched = schedule.build_schedule(base_plan(SESSIONS, overrides), today=TODAY)
    by_day = {s["day"]: s for s in sched["weeks"][0]["sessions"]}
    assert by_day["Sun"]["status"] == "done"
    assert by_day["Wed"]["status"] == "skipped"
    assert sched["weeks"][0]["done"] == 1


def test_date_override_reschedules_session():
    overrides = {"0:2": {"date": "2026-06-25"}}  # move long run to Thu
    sched = schedule.build_schedule(base_plan(SESSIONS, overrides), today=TODAY)
    by_day = {s["day"]: s for s in sched["weeks"][0]["sessions"]}
    assert by_day["Sat"]["date"] == dt.date(2026, 6, 25)
    assert by_day["Sat"]["status"] == "upcoming"  # Jun 25 > today


def test_automatch_marks_session_done(add_metric):
    # A real run on Wednesday should auto-match the Wed session.
    add_metric("2026-06-24T08:00:00", sport="running", distance_m=8000.0)
    sched = schedule.build_schedule(base_plan(SESSIONS), today=TODAY)
    wed = next(s for s in sched["weeks"][0]["sessions"] if s["day"] == "Wed")
    assert wed["status"] == "done"
    assert wed["note"] is None  # ran on the planned day, no "ran X" note


def test_automatch_done_on_different_day_adds_note(add_metric):
    # Run on Thursday (no session) matches the nearest open session with a note.
    add_metric("2026-06-25T08:00:00", sport="running", distance_m=8000.0)
    sched = schedule.build_schedule(base_plan(SESSIONS), today=TODAY)
    done = [s for s in sched["weeks"][0]["sessions"] if s["status"] == "done"]
    assert len(done) == 1
    assert done[0]["note"] is not None and "ran" in done[0]["note"]


def test_unparseable_week_falls_back_without_crashing():
    plan = {
        "generated_at": "2026-06-21T10:00:00",
        "next_month": [{"week": "Week 1", "sessions": SESSIONS}],
    }
    sched = schedule.build_schedule(plan, today=TODAY)
    assert len(sched["weeks"]) == 1  # fallback 7-day block, no exception


def test_execution_summary_text_mentions_today_and_status():
    text = schedule.execution_summary_text(base_plan(SESSIONS), today=TODAY)
    assert "today is" in text
    assert "TODAY" in text  # the Wed session's status, upper-cased
