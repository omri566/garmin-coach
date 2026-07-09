"""Best-sustained-effort detection (`analytics/segments.py`) — the basis for
judging a structured workout on its work segment, not the whole-run average."""
from __future__ import annotations

import pandas as pd

from garmin_coach.analytics import segments


def test_finds_the_fast_work_segment():
    # 10 min easy, 5 min fast, 5 min easy (per-second speed in m/s).
    speed = [2.8] * 600 + [3.4] * 300 + [2.8] * 300
    hr = [140] * 600 + [176] * 300 + [140] * 300
    seg = segments.best_sustained(pd.DataFrame({"enhanced_speed": speed,
                                                "heart_rate": hr}), 300)
    assert seg is not None
    assert abs(seg["pace_s_km"] - 1000 / 3.4) < 6      # ~4:54/km, the fast bit
    assert 170 <= seg["hr"] <= 180                     # HR from the work, not the average
    assert seg["minutes"] == 5


def test_none_without_a_speed_stream():
    assert segments.best_sustained(None, 300) is None
    assert segments.best_sustained(pd.DataFrame({"heart_rate": [140] * 200}), 300) is None
