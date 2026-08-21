"""The last-run card must never crash the dashboard on a run with missing metrics.

A run can arrive without HR, distance, or some/all running-dynamics fields
(treadmill, no dynamics pod, a structured workout). An unguarded f-string on one
of those Nones raised ``TypeError: unsupported format string passed to
NoneType.__format__`` and took down the whole Overview page. See
``overview.last_run_card``.
"""
from __future__ import annotations

from garmin_coach.dashboard.pages import overview


def test_partial_dynamics_does_not_crash(add_metric):
    # Vertical ratio present but ground-contact / cadence / step-length absent —
    # the exact shape from the crash report.
    add_metric("2026-08-20T07:00:00", distance_m=8000, avg_pace_s_km=330,
               avg_hr=150, max_hr=165, avg_vert_ratio=9.0)
    card = overview.last_run_card()
    assert card is not None                       # built without raising


def test_run_missing_hr_and_distance_does_not_crash(add_metric):
    # A near-empty running row (only the required columns) must still render.
    add_metric("2026-08-21T07:00:00")
    assert overview.last_run_card() is not None
