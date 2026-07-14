"""End-of-block wrap-up: a short recap of the training week you just finished plus
a pointer into the next one, grounded in the plan's execution state.

A "block" here is a completed training week (Sun–Sat). Cached per block id so the
LLM runs at most once per finished week; the tips drawer surfaces it as a moment
card and regenerates only when a new week completes.
"""
from __future__ import annotations

import datetime as dt
import json

from garmin_coach import config
from garmin_coach.coach import plan as plan_mod
from garmin_coach.coach import schedule
from garmin_coach.llm import get_provider

_DIR = config.DATA_DIR / "block_summaries"

SYSTEM = (
    "You are an experienced running coach writing a brief, motivating wrap-up of "
    "the training week an athlete just finished, and a pointer into the next one. "
    "Use ONLY the plan-execution facts given. Be specific about what got done vs "
    "planned and the week's theme; then give ONE concrete focus for the coming "
    "week. Return a punchy one-line 'headline' (max ~10 words) and a 'detail' of "
    "2-3 sentences. Honest but encouraging."
)

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "punchy one-line recap"},
        "detail": {"type": "string",
                   "description": "2-3 sentences: what happened + one focus for next week"},
    },
    "required": ["headline", "detail"],
}


def _path(bid: str):
    return _DIR / f"{bid}.json"


def cached(bid: str) -> dict | None:
    p = _path(bid)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def _weeks(today: dt.date | None):
    plan = plan_mod.load_latest()
    if not plan:
        return None, None, None
    sched = schedule.build_schedule(plan, today)
    return plan, sched, sched["current_index"]


def current_block_id(today: dt.date | None = None) -> str | None:
    """Id of the most recently *completed* plan week, or None if we're still in
    the first week (nothing finished yet)."""
    _, sched, cur = _weeks(today)
    if not sched or cur < 1:
        return None
    done_week = sched["weeks"][cur - 1]
    return f"week-{done_week['start'].isoformat()}"


def current_cached(today: dt.date | None = None) -> dict | None:
    bid = current_block_id(today)
    return cached(bid) if bid else None


def _week_facts(wk) -> str:
    lines = [f"{wk['label']} · theme: {wk.get('theme') or '—'} "
             f"({wk['done']}/{wk['total']} key sessions done)"]
    for s in wk["sessions"]:
        if (s["type"] or "").lower() == "rest":
            continue
        ran = ""
        m = s.get("match")
        if m:
            ran = f" → ran {(m.get('distance_m') or 0) / 1000:.1f} km"
        lines.append(f"  - {s['date']:%a}: {s['type']} · {s.get('description', '')}"
                     f" [{s['status']}]{ran}")
    return "\n".join(lines)


def make_summary(bid: str, today: dt.date | None = None, provider=None,
                 model: str | None = None) -> dict | None:
    plan, sched, cur = _weeks(today)
    if not sched or cur < 1:
        return None
    done_week = sched["weeks"][cur - 1]
    next_week = sched["weeks"][cur] if cur < len(sched["weeks"]) else None
    provider = provider or get_provider("claude")
    prompt = (
        f"Goal: {plan.get('goal') or '—'}\n\n"
        f"# The week just finished\n{_week_facts(done_week)}\n\n"
        + (f"# The coming week\n{_week_facts(next_week)}\n\n" if next_week else "")
        + "Recap the finished week (what got done vs planned, and the theme), then "
          "give one concrete focus for the coming week."
    )
    res = provider.generate_json(prompt, SUMMARY_SCHEMA, system=SYSTEM, model=model)
    out = {"block_id": bid,
           "headline": (res.get("headline") or "").strip(),
           "detail": (res.get("detail") or "").strip(),
           "generated_at": dt.datetime.now().isoformat(timespec="seconds")}
    _DIR.mkdir(parents=True, exist_ok=True)
    _path(bid).write_text(json.dumps(out, indent=2))
    return out


def ensure_current(today: dt.date | None = None, provider=None,
                   model: str | None = None) -> dict | None:
    """The wrap-up for the just-finished week, generating it once if missing."""
    bid = current_block_id(today)
    if not bid:
        return None
    return cached(bid) or make_summary(bid, today=today, provider=provider, model=model)
