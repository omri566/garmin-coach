"""Best sustained effort within a run, from its per-second streams.

A structured workout (intervals/tempo) must be judged on its *work* segment, not
the whole-run average — a warm-up and cool-down drag the average pace far below
the rep pace, which otherwise makes an on-target session look "too easy".
"""
from __future__ import annotations


def best_sustained(streams, seconds: int) -> dict | None:
    """The fastest sustained ``seconds``-long window in the run: its mean pace
    (s/km) and heart rate. Returns None if there's no usable speed stream.

    The window adapts down for short runs so we always report *something* from
    the fastest part of the effort.
    """
    if streams is None or getattr(streams, "empty", True):
        return None
    if "enhanced_speed" not in streams.columns:
        return None
    d = streams.dropna(subset=["enhanced_speed"]).reset_index(drop=True)
    if len(d) < 60:
        return None
    win = min(seconds, max(60, len(d) // 3))
    roll = d["enhanced_speed"].rolling(win, min_periods=int(win * 0.8)).mean()
    if roll.notna().sum() == 0:
        return None
    end = int(roll.idxmax())                         # window with the highest mean speed
    seg = d.iloc[max(0, end - win + 1): end + 1]
    ms = seg["enhanced_speed"].mean()
    if not ms or ms <= 0:
        return None
    hr = (seg["heart_rate"].mean()
          if "heart_rate" in seg.columns and seg["heart_rate"].notna().any() else None)
    return {"pace_s_km": 1000.0 / ms, "hr": hr,
            "seconds": len(seg), "minutes": max(1, round(len(seg) / 60))}
