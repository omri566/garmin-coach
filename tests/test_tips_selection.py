"""The coach surfaces only the few most-relevant tips.

`tips._top_recs` caps to `TIP_LIMIT`, highest priority + nearest horizon first.
"""
from __future__ import annotations

from garmin_coach.dashboard.pages import tips


def _rec(priority, horizon, title):
    return {"title": title, "priority": priority, "horizon": horizon,
            "rationale": "", "action": ""}


def test_top_recs_caps_and_orders():
    recs = [
        _rec("low", "this_block", "a"),
        _rec("high", "this_week", "b"),
        _rec("medium", "today", "c"),
        _rec("high", "today", "d"),
    ]
    top = tips._top_recs(recs, limit=3)
    assert [r["title"] for r in top] == ["d", "b", "c"]   # high/today, high/week, med/today
    assert all(r["priority"] != "low" for r in top)       # the low one is dropped


def test_default_limit_is_three():
    recs = [_rec("high", "today", str(i)) for i in range(6)]
    assert len(tips._top_recs(recs)) == tips.TIP_LIMIT == 3
