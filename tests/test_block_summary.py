"""End-of-block wrap-up: identified per completed training week and cached so the
LLM runs at most once per finished week. See `coach/block_summary.py`.
"""
from __future__ import annotations

import datetime as dt

import pytest

from garmin_coach import config
from garmin_coach.coach import block_summary
from garmin_coach.coach import plan as plan_mod


class FakeProvider:
    """Stand-in LLM: records call count, returns a fixed JSON payload."""

    def __init__(self, out):
        self.out = out
        self.calls = 0

    def generate_json(self, prompt, schema, system=None, model=None):
        self.calls += 1
        return self.out


@pytest.fixture(autouse=True)
def bs_dir(monkeypatch):
    monkeypatch.setattr(block_summary, "_DIR", config.DATA_DIR / "block_summaries")


_SESSIONS = [
    {"day": "Mon", "type": "easy", "description": "easy 5k"},
    {"day": "Wed", "type": "easy", "description": "easy 5k"},
    {"day": "Sat", "type": "long", "description": "long 12k"},
]


def _two_week_plan():
    return {
        "generated_at": "2026-06-20T10:00:00", "goal": "sub-50 10k", "overrides": {},
        "next_month": [
            {"week": "Week 1 (Jun 21 – Jun 27)", "theme": "base",
             "target_volume_km": 30, "sessions": _SESSIONS},
            {"week": "Week 2 (Jun 28 – Jul 4)", "theme": "build",
             "target_volume_km": 34, "sessions": _SESSIONS},
        ],
    }


def test_no_block_while_still_in_first_week():
    plan_mod.save_latest(_two_week_plan())
    # A Wednesday inside week 1 — nothing has finished yet.
    assert block_summary.current_block_id(dt.date(2026, 6, 24)) is None
    assert block_summary.current_cached(dt.date(2026, 6, 24)) is None


def test_block_id_and_generate_once():
    plan_mod.save_latest(_two_week_plan())
    today = dt.date(2026, 6, 30)              # in week 2 → week 1 is finished
    bid = block_summary.current_block_id(today)
    assert bid and bid.startswith("week-")
    assert block_summary.current_cached(today) is None

    fake = FakeProvider({"headline": "Solid base week",
                         "detail": "3/3 done. Next week: add a tempo."})
    out = block_summary.ensure_current(today, provider=fake)
    assert out["headline"] == "Solid base week"
    assert out["block_id"] == bid
    assert fake.calls == 1

    # Second open reads the cache — no second LLM call.
    out2 = block_summary.ensure_current(today, provider=fake)
    assert fake.calls == 1
    assert out2["detail"].startswith("3/3")
    assert block_summary.current_cached(today)["block_id"] == bid
