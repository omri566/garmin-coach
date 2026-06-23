"""Per-activity feature extraction — the backbone of every trend.

Each activity's per-second stream is read once and reduced to a row of derived
metrics (training stress, HR-zone time, efficiency, decoupling, technique
aggregates). Trends and the dashboard read these rows, never the parquet.

Science notes:
- TRIMP (Banister): dt * HRr * 0.64 * e^(1.92*HRr) for male athletes, where
  HRr = (HR - rest) / (max - rest). Weights time by exponential HR intensity.
- rTSS (run training stress): (moving_s * IF^2) / 3600 * 100, IF = threshold
  pace / avg pace. ~100 = one hour at threshold.
- EF (efficiency factor): speed (m/min) / avg HR. Rising over time = aerobic gain.
- Decoupling (Pa:Hr): EF of 1st half vs 2nd half; >5% suggests poor durability /
  too hard / heat. Computed on moving samples only.
- Normalized power: 4th-root of mean of 30 s rolling-avg power^4.
"""
from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
import pandas as pd

from garmin_coach.profile import Profile

log = logging.getLogger(__name__)

MOVING_SPEED_MIN = 0.5  # m/s; below this we treat the athlete as stopped


def _series(df: pd.DataFrame, col: str) -> pd.Series | None:
    return df[col] if col in df.columns and df[col].notna().any() else None


def _trimp(hr: pd.Series, dt_s: pd.Series, rest: float, hrmax: float) -> float:
    hrr = ((hr - rest) / (hrmax - rest)).clip(0, 1)
    return float((dt_s / 60.0 * hrr * 0.64 * np.exp(1.92 * hrr)).sum())


def _normalized_power(power: pd.Series) -> float | None:
    if power is None or power.isna().all():
        return None
    roll = power.rolling(30, min_periods=1).mean()
    return float((np.mean(roll**4)) ** 0.25)


def _decoupling(speed: pd.Series, hr: pd.Series) -> float | None:
    """Percent drift in speed/HR from first to second half of moving time."""
    n = len(speed)
    if n < 120:  # need a couple minutes to be meaningful
        return None
    h1 = slice(0, n // 2)
    h2 = slice(n // 2, n)
    ef1 = speed.iloc[h1].mean() / hr.iloc[h1].mean()
    ef2 = speed.iloc[h2].mean() / hr.iloc[h2].mean()
    if not ef1:
        return None
    return float((ef1 - ef2) / ef1 * 100.0)


def compute_features(df: pd.DataFrame, profile: Profile,
                     summary: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if df.empty or "timestamp" not in df.columns:
        return out

    ts = pd.to_datetime(df["timestamp"])
    dt_s = ts.diff().dt.total_seconds().fillna(1.0).clip(0, 10)  # guard big gaps

    speed = _series(df, "enhanced_speed")
    hr = _series(df, "heart_rate")

    # --- moving mask (exclude stops) ---
    moving = speed > MOVING_SPEED_MIN if speed is not None else pd.Series(True, index=df.index)
    out["moving_s"] = float(dt_s[moving].sum())

    # --- distance ---
    dist = _series(df, "distance")
    distance_m = float(dist.max() - dist.min()) if dist is not None else summary.get("distance")
    out["distance_m"] = distance_m

    if distance_m and out["moving_s"]:
        out["avg_pace_s_km"] = out["moving_s"] / (distance_m / 1000.0)

    # --- HR + zone time ---
    if hr is not None:
        out["avg_hr"] = float(hr.mean())
        out["max_hr"] = float(hr.max())
        zsec = {f"z{i}_s": 0.0 for i in range(1, 6)}
        zones = hr.apply(profile.zone_of_hr)
        for z, secs in dt_s.groupby(zones).sum().items():
            zsec[f"z{int(z)}_s"] = float(secs)
        out.update(zsec)
        out["trimp"] = _trimp(hr, dt_s, profile.resting_hr or 45, profile.hr_max or 200)
        if speed is not None:
            out["ef"] = float(speed[moving].mean() * 60.0 / hr[moving].mean())
            out["decoupling_pct"] = _decoupling(
                speed[moving].reset_index(drop=True), hr[moving].reset_index(drop=True)
            )

    # --- cadence (per-leg rpm -> steps/min) ---
    cad = _series(df, "cadence")
    if cad is not None:
        frac = _series(df, "fractional_cadence")
        spm = (cad + (frac if frac is not None else 0)) * 2
        out["avg_cadence_spm"] = float(spm[moving].mean())

    # --- running dynamics (present only on recent activities) ---
    dyn = {
        "avg_vert_osc_mm": "vertical_oscillation",
        "avg_vert_ratio": "vertical_ratio",
        "avg_gct_ms": "stance_time",
        "avg_gct_balance": "stance_time_balance",
        "avg_step_len_mm": "step_length",
    }
    has_dyn = False
    for out_key, col in dyn.items():
        s = _series(df, col)
        if s is not None:
            out[out_key] = float(s[moving].mean())
            has_dyn = True
    out["has_dynamics"] = int(has_dyn)

    # --- power ---
    power = _series(df, "power")
    if power is not None:
        out["avg_power_w"] = float(power[moving].mean())
        out["np_power_w"] = _normalized_power(power[moving].reset_index(drop=True))

    # --- pace-based training stress (runs with a threshold pace) ---
    tp = profile.threshold_pace_s_per_km
    sport = (summary.get("activityType") or {}).get("typeKey", "")
    if tp and out.get("avg_pace_s_km") and "running" in sport:
        intensity = tp / out["avg_pace_s_km"]
        out["rtss"] = (out["moving_s"] * intensity**2) / 3600.0 * 100.0

    # --- headline training stress: prefer Garmin load, else TRIMP ---
    out["training_stress"] = summary.get("activityTrainingLoad") or out.get("trimp")

    return {k: v for k, v in out.items() if v is None or not (
        isinstance(v, float) and math.isnan(v))}
