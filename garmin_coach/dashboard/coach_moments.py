"""Data helpers for the coach 'moments' shown in the tips popup.

  * `last_run_note` — the coach's read of the most recent run (any run: free or
    structured, planned or not), reusing `coach/execution.py`. Returns plain data
    ({headline, detail} / {error} / None) so the popup can render it as a message.
  * `ensure_moments` — generates the end-of-block wrap-up (`coach/block_summary.py`)
    once, cached; the popup reads it via `block_summary.current_cached`.

LLM output is cached, so generation runs at most once per run / block.
"""
from __future__ import annotations

from garmin_coach.coach import execution
from garmin_coach.dashboard import data


def _matched_session(r):
    """The planned session this run fulfilled (via the schedule auto-match)."""
    from garmin_coach.coach import plan as plan_mod
    from garmin_coach.coach import schedule
    plan = plan_mod.load_latest()
    if not plan or not r:
        return None
    for wk in schedule.build_schedule(plan)["weeks"]:
        for s in wk["sessions"]:
            m = s.get("match")
            if m and m.get("activity_id") == r.get("activity_id"):
                return s
    return None


def last_run_note() -> dict | None:
    """The coach's read of the most recent run — any run type. Generates once and
    caches. Returns {'headline','detail'} on success, {'error': reason} on failure
    (so the popup can *show why* instead of silently blank), or None if no run."""
    try:
        r = data.last_run()
    except Exception as e:  # noqa: BLE001
        return {"error": f"Couldn't load your last run: {e}"}
    if not r:
        return None
    aid = r.get("activity_id")
    hit = execution.cached(aid)
    if not hit:
        try:
            session = _matched_session(r)          # None for a free/unplanned run
            streams = data.run_streams(aid)
            hit = execution.ensure_note(r, session, streams)
        except Exception as e:  # noqa: BLE001 — surface it, don't swallow
            return {"error": f"{type(e).__name__}: {e}"}
    if not hit or not (hit.get("headline") or hit.get("detail")):
        return None
    return {"headline": hit.get("headline") or hit.get("note", ""),
            "detail": hit.get("detail", "")}


def ensure_moments():
    """Generate the block-summary wrap-up (cached) when the popup opens. Guarded —
    a missing LLM or data gap must never break opening the popup."""
    try:
        from garmin_coach.coach import block_summary
        block_summary.ensure_current()
    except Exception:  # noqa: BLE001 — wrap-up is best-effort
        pass
