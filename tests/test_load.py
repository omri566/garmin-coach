"""Training-load model: CTL/ATL/TSB/ACWR/ramp and current_state."""

from __future__ import annotations

import datetime as dt
import math

import pandas as pd
import pytest

from garmin_coach.analytics import load


def _seed_constant(add_metric, start: str, days: int, trimp: float) -> None:
    base = pd.Timestamp(start)
    for i in range(days):
        d = (base + pd.Timedelta(days=i)).strftime("%Y-%m-%dT08:00:00")
        add_metric(d, trimp=trimp, sport="running")


def test_empty_db_returns_empty(add_metric):
    assert load.load_series().empty
    assert load.current_state() == {}


def test_single_day_ctl_equals_atl_equals_trimp(add_metric):
    add_metric("2026-01-01T08:00:00", trimp=100.0, sport="running")
    df = load.load_series(start="2026-01-01", end="2026-01-01")
    assert list(df.index) == [pd.Timestamp("2026-01-01")]
    row = df.iloc[0]
    # First sample of an EWMA (adjust=False) is the value itself.
    assert row["ctl"] == pytest.approx(100.0)
    assert row["atl"] == pytest.approx(100.0)
    # TSB needs a prior day; ramp needs 7 prior days.
    assert math.isnan(row["tsb"])
    assert math.isnan(row["ramp"])
    # acute = 100, chronic = 100/4 = 25 -> ACWR = 4.0
    assert row["acwr"] == pytest.approx(4.0)


def test_rest_days_are_zero_filled(add_metric):
    add_metric("2026-01-01T08:00:00", trimp=100.0, sport="running")
    add_metric("2026-01-03T08:00:00", trimp=50.0, sport="running")
    df = load.load_series(start="2026-01-01", end="2026-01-04")
    assert len(df) == 4  # contiguous daily index
    assert df.loc[pd.Timestamp("2026-01-02"), "tss"] == 0.0
    assert df.loc[pd.Timestamp("2026-01-04"), "tss"] == 0.0


def test_same_day_loads_sum(add_metric):
    add_metric("2026-01-01T08:00:00", trimp=40.0, sport="running")
    add_metric("2026-01-01T17:00:00", trimp=60.0, sport="running")
    df = load.load_series(start="2026-01-01", end="2026-01-01")
    assert df.iloc[0]["tss"] == pytest.approx(100.0)


def test_ewma_matches_reference_formula(add_metric):
    """CTL/ATL must be EWMAs with the documented 42/7-day time constants."""
    _seed_constant(add_metric, "2026-01-01", days=10, trimp=80.0)
    df = load.load_series(start="2026-01-01", end="2026-01-10")
    a_ctl = 1 - math.exp(-1 / load.CTL_TAU)
    a_atl = 1 - math.exp(-1 / load.ATL_TAU)
    expect_ctl = df["tss"].ewm(alpha=a_ctl, adjust=False).mean()
    expect_atl = df["tss"].ewm(alpha=a_atl, adjust=False).mean()
    pd.testing.assert_series_equal(df["ctl"], expect_ctl, check_names=False)
    pd.testing.assert_series_equal(df["atl"], expect_atl, check_names=False)


def test_atl_leads_ctl_during_ramp_so_form_is_negative(add_metric):
    """Fatigue rises faster than fitness, so TSB (form) is negative while ramping."""
    _seed_constant(add_metric, "2026-01-01", days=20, trimp=100.0)
    # Window opens before training starts, so both EWMAs build up from zero.
    df = load.load_series(start="2025-12-20", end="2026-01-20")
    # ATL (7-day) outpaces CTL (42-day) while load ramps from rest.
    assert (df["atl"] >= df["ctl"] - 1e-9).all()
    assert (df["atl"] > df["ctl"]).any()  # genuinely leading, not just equal
    # TSB after the first day is yesterday's (ctl - atl) <= 0.
    assert (df["tsb"].dropna() <= 1e-9).all()


def test_acwr_converges_to_one_under_steady_load(add_metric):
    _seed_constant(add_metric, "2026-01-01", days=40, trimp=70.0)
    df = load.load_series(start="2026-01-01", end="2026-02-09")
    # After >=28 days, acute(7*L) / (chronic 28*L/4 = 7*L) == 1.0
    assert df.iloc[-1]["acwr"] == pytest.approx(1.0, abs=1e-6)


def test_ramp_is_positive_when_fitness_building(add_metric):
    _seed_constant(add_metric, "2026-01-01", days=20, trimp=90.0)
    # Open the window during rest so CTL climbs from zero as training begins.
    df = load.load_series(start="2025-12-20", end="2026-01-20")
    # ramp = CTL today - CTL 7 days ago; building -> positive once defined.
    assert df["ramp"].iloc[-1] > 0


def test_current_state_shape_and_rounding(add_metric):
    # current_state() runs load_series() with end defaulting to today.
    start = (dt.date.today() - dt.timedelta(days=39)).isoformat()
    _seed_constant(add_metric, start, days=40, trimp=70.0)
    state = load.current_state()
    assert set(state) == {"ctl", "atl", "tsb", "acwr", "ramp"}
    # Rounded to documented precision.
    assert state["ctl"] == round(state["ctl"], 1)
    assert state["acwr"] is None or state["acwr"] == round(state["acwr"], 2)
