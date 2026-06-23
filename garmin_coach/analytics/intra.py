"""Within-activity analysis: per-km splits, intra-run drift, decoupling halves.

Computed on demand for a single activity's per-second stream (the Deep Analysis
page), so nothing here is persisted.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MOVING_SPEED_MIN = 0.5


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ts"] = pd.to_datetime(df["timestamp"])
    df["dt"] = df["ts"].diff().dt.total_seconds().fillna(1.0).clip(0, 10)
    if "fractional_cadence" in df:
        df["cadence_spm"] = (df.get("cadence", 0).fillna(0)
                             + df["fractional_cadence"].fillna(0)) * 2
    elif "cadence" in df:
        df["cadence_spm"] = df["cadence"].fillna(0) * 2
    return df


def per_km_splits(df: pd.DataFrame) -> pd.DataFrame:
    """Per-kilometre splits: pace, HR, cadence, vertical ratio, elevation."""
    if df.empty or "distance" not in df or "enhanced_speed" not in df:
        return pd.DataFrame()
    d = _prep(df)
    d = d[d["distance"].notna()]
    d["km"] = (d["distance"] // 1000).astype(int)
    rows = []
    for km, g in d.groupby("km"):
        dist = g["distance"].max() - g["distance"].min()
        if dist <= 0:
            continue
        dur = g["dt"].sum()
        rows.append({
            "km": int(km) + 1,
            "dist_m": dist,
            "time_s": dur,
            "pace_s_km": dur / (dist / 1000.0),
            "avg_hr": g["heart_rate"].mean() if "heart_rate" in g else None,
            "cadence": g["cadence_spm"].mean() if "cadence_spm" in g else None,
            "vert_ratio": g["vertical_ratio"].mean() if "vertical_ratio" in g else None,
            "elev_gain": (g["enhanced_altitude"].diff().clip(lower=0).sum()
                          if "enhanced_altitude" in g else None),
        })
    return pd.DataFrame(rows)


def drift_series(df: pd.DataFrame, smooth_s: int = 30) -> pd.DataFrame:
    """Smoothed HR / pace / cadence vs distance for intra-run drift plots."""
    if df.empty or "enhanced_speed" not in df:
        return pd.DataFrame()
    d = _prep(df)
    moving = d["enhanced_speed"] > MOVING_SPEED_MIN
    d = d[moving].copy()
    if d.empty:
        return pd.DataFrame()
    d["distance_km"] = (d["distance"] - d["distance"].min()) / 1000.0
    spd = d["enhanced_speed"].rolling(smooth_s, min_periods=1).mean()
    out = pd.DataFrame({
        "distance_km": d["distance_km"].values,
        "pace_s_km": (1000.0 / spd).clip(upper=900).values,
        "heart_rate": d["heart_rate"].rolling(smooth_s, min_periods=1).mean().values
        if "heart_rate" in d else np.nan,
        "cadence_spm": d["cadence_spm"].rolling(smooth_s, min_periods=1).mean().values
        if "cadence_spm" in d else np.nan,
    })
    # Downsample for a light, fast plot (~600 points max).
    step = max(1, len(out) // 600)
    return out.iloc[::step].reset_index(drop=True)


def decoupling_halves(df: pd.DataFrame) -> dict:
    """Efficiency (speed/HR) of first vs second half + decoupling percent."""
    if df.empty or "enhanced_speed" not in df or "heart_rate" not in df:
        return {}
    d = _prep(df)
    d = d[(d["enhanced_speed"] > MOVING_SPEED_MIN) & d["heart_rate"].notna()]
    n = len(d)
    if n < 120:
        return {}
    h1, h2 = d.iloc[: n // 2], d.iloc[n // 2:]
    ef1 = h1["enhanced_speed"].mean() / h1["heart_rate"].mean() * 60
    ef2 = h2["enhanced_speed"].mean() / h2["heart_rate"].mean() * 60
    return {
        "ef_first": float(ef1),
        "ef_second": float(ef2),
        "decoupling_pct": float((ef1 - ef2) / ef1 * 100.0) if ef1 else None,
    }
