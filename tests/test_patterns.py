"""Personal-pattern detection (`analytics/patterns.py`).

Insights must be evidence-gated: surfaced only when the athlete's own data shows
a real, big-enough effect — never as generic advice.
"""
from __future__ import annotations

from garmin_coach.analytics import patterns


def _seed(add_metric, hour, ef, n, day_start=1):
    for i in range(n):
        # spread across days so ids/dates differ; hour drives the bucket
        add_metric(f"2026-03-{day_start + i:02d}T{hour:02d}:00:00", ef=ef,
                   avg_hr=150.0, decoupling_pct=8.0 if hour < 11 else 12.0)


def test_no_insight_without_enough_data(add_metric):
    _seed(add_metric, 7, 1.10, 3)
    assert patterns.personal_insights() == []


def test_morning_efficiency_is_surfaced(add_metric):
    _seed(add_metric, 7, 1.12, 15, day_start=1)     # efficient mornings
    _seed(add_metric, 20, 1.00, 15, day_start=1)    # weaker evenings
    ins = patterns.personal_insights()
    tod = [i for i in ins if i["kind"] == "time_of_day"]
    assert tod, "a clear morning EF edge should surface a time-of-day insight"
    assert "morning" in tod[0]["title"].lower()
    assert "%" in tod[0]["detail"]                  # carries the numbers


def test_uniform_efficiency_surfaces_nothing(add_metric):
    # Same EF morning and evening → no time-of-day edge to report.
    _seed(add_metric, 7, 1.05, 15, day_start=1)
    _seed(add_metric, 20, 1.05, 15, day_start=1)
    assert [i for i in patterns.personal_insights() if i["kind"] == "time_of_day"] == []
