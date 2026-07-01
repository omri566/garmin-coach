"""Per-activity feature extraction: TRIMP, EF, decoupling, zone time."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from garmin_coach.analytics import features
from garmin_coach.profile import Profile


def make_profile() -> Profile:
    return Profile(
        sex="MALE",
        hr_max=200.0,
        resting_hr=50.0,
        lthr=170.0,
        # Floors chosen so that 120->z1, 140->z2, 155->z3, 170->z4, 185->z5.
        hr_zone_floors={"z1": 100, "z2": 130, "z3": 150, "z4": 165, "z5": 180},
        threshold_pace_s_per_km=300.0,  # 5:00/km
    )


def steady_run(n: int = 600, hr: float = 150.0, speed: float = 3.0) -> pd.DataFrame:
    """A flat n-second run at constant HR and speed, 1 Hz samples."""
    ts = pd.date_range("2026-01-01T08:00:00", periods=n, freq="1s")
    return pd.DataFrame(
        {
            "timestamp": ts,
            "heart_rate": np.full(n, hr, dtype=float),
            "enhanced_speed": np.full(n, speed, dtype=float),
            "distance": np.arange(n, dtype=float) * speed,  # cumulative metres
        }
    )


def test_empty_df_returns_empty():
    out = features.compute_features(pd.DataFrame(), make_profile(), {})
    assert out == {}


def test_trimp_matches_banister_formula():
    prof = make_profile()
    df = steady_run(n=600, hr=150.0, speed=3.0)
    out = features.compute_features(df, prof, {})
    hrr = (150.0 - prof.resting_hr) / (prof.hr_max - prof.resting_hr)
    # 600 samples; first dt is 1.0 (diff fillna), so 600 minutes-fractions of 1s.
    minutes = 600 / 60.0
    expected = minutes * hrr * 0.64 * math.exp(1.92 * hrr)
    assert out["trimp"] == pytest.approx(expected, rel=1e-6)


def test_efficiency_factor_speed_over_hr():
    df = steady_run(n=600, hr=150.0, speed=3.0)
    out = features.compute_features(df, make_profile(), {})
    # EF = mean speed (m/min) / mean HR = (3.0 * 60) / 150
    assert out["ef"] == pytest.approx((3.0 * 60.0) / 150.0)


def test_zone_distribution_sums_to_moving_time():
    prof = make_profile()
    # Two halves: 300s in z1-ish HR (120) and 300s in z4 HR (170).
    n = 600
    ts = pd.date_range("2026-01-01T08:00:00", periods=n, freq="1s")
    hr = np.concatenate([np.full(300, 120.0), np.full(300, 170.0)])
    df = pd.DataFrame(
        {
            "timestamp": ts,
            "heart_rate": hr,
            "enhanced_speed": np.full(n, 3.0),
            "distance": np.arange(n, dtype=float) * 3.0,
        }
    )
    out = features.compute_features(df, prof, {})
    zsum = sum(out[f"z{i}_s"] for i in range(1, 6))
    assert zsum == pytest.approx(out["moving_s"])
    # HR 120 -> z1, HR 170 -> z4 per the floors in make_profile.
    assert out["z1_s"] > 0
    assert out["z4_s"] > 0
    assert out["z5_s"] == 0.0


def test_decoupling_zero_for_perfectly_steady_run():
    df = steady_run(n=600, hr=150.0, speed=3.0)
    out = features.compute_features(df, make_profile(), {})
    assert out["decoupling_pct"] == pytest.approx(0.0, abs=1e-9)


def test_decoupling_positive_when_hr_drifts_up():
    """Same pace but HR climbing in 2nd half = positive cardiac drift."""
    n = 600
    ts = pd.date_range("2026-01-01T08:00:00", periods=n, freq="1s")
    hr = np.concatenate([np.full(300, 145.0), np.full(300, 160.0)])
    df = pd.DataFrame(
        {
            "timestamp": ts,
            "heart_rate": hr,
            "enhanced_speed": np.full(n, 3.0),
            "distance": np.arange(n, dtype=float) * 3.0,
        }
    )
    out = features.compute_features(df, make_profile(), {})
    assert out["decoupling_pct"] > 0


def test_decoupling_none_for_short_activity():
    df = steady_run(n=60, hr=150.0, speed=3.0)  # under the 120-sample floor
    out = features.compute_features(df, make_profile(), {})
    assert out.get("decoupling_pct") is None or "decoupling_pct" not in out


def test_moving_mask_excludes_stops():
    """Samples below MOVING_SPEED_MIN should not count toward moving time."""
    n = 600
    ts = pd.date_range("2026-01-01T08:00:00", periods=n, freq="1s")
    speed = np.concatenate([np.full(300, 3.0), np.full(300, 0.0)])  # stopped 2nd half
    df = pd.DataFrame(
        {
            "timestamp": ts,
            "heart_rate": np.full(n, 150.0),
            "enhanced_speed": speed,
            "distance": np.concatenate([np.arange(300) * 3.0, np.full(300, 300 * 3.0)]),
        }
    )
    out = features.compute_features(df, make_profile(), {})
    # ~300s moving (first dt is 1.0); the stopped half is excluded.
    assert out["moving_s"] == pytest.approx(300.0, abs=1.0)


def test_rtss_computed_for_runs_with_threshold_pace():
    prof = make_profile()
    df = steady_run(n=600, hr=150.0, speed=3.0)  # 3 m/s = 333 s/km
    summary = {"activityType": {"typeKey": "running"}}
    out = features.compute_features(df, prof, summary)
    intensity = prof.threshold_pace_s_per_km / out["avg_pace_s_km"]
    expected = (out["moving_s"] * intensity**2) / 3600.0 * 100.0
    assert out["rtss"] == pytest.approx(expected, rel=1e-9)


def test_training_stress_prefers_garmin_load():
    df = steady_run(n=600, hr=150.0, speed=3.0)
    out = features.compute_features(df, make_profile(), {"activityTrainingLoad": 123.0})
    assert out["training_stress"] == 123.0


def test_training_stress_falls_back_to_trimp():
    df = steady_run(n=600, hr=150.0, speed=3.0)
    out = features.compute_features(df, make_profile(), {})
    assert out["training_stress"] == pytest.approx(out["trimp"])
