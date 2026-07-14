"""Timely coach 'moments' surfaced at the top of the tips drawer.

Two kinds, newest-relevant first:
  * post-workout debrief — the coach's read of your most recent run
    (reuses the cached notes from `coach/execution.py`);
  * end-of-block / week summary — a recap of the block you just finished plus
    what to aim for next (`coach/block_summary.py`).

Both are cheap to render because the LLM output is cached; this module only reads
caches and lays them out as cards. Generation is triggered from the drawer
callbacks (Phase D), never here.
"""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import html

from garmin_coach.coach import execution
from garmin_coach.dashboard import data


def _card(kind_label, icon, headline, detail=None, tone="amp"):
    body = [
        dmc.Group([html.Span(icon, className="gc-moment-ic"),
                   dmc.Text(kind_label, size="xs", c="dimmed", tt="uppercase",
                            fw=700)], gap="xs"),
        dmc.Text(headline, fw=700, size="sm", mt=6, style={"lineHeight": 1.4}),
    ]
    if detail and detail != headline:
        body.append(dmc.Text(detail, size="sm", c="dimmed", mt=4,
                             style={"lineHeight": 1.5}))
    return dmc.Card(body, className=f"gc-moment gc-moment-{tone}", radius="md",
                    p="md", withBorder=True)


def _post_workout_card():
    """The coach's read of the latest run, if one has been generated & cached."""
    r = data.last_run()
    if not r:
        return None
    hit = execution.cached(r.get("activity_id"))
    if not hit:
        return None
    headline = hit.get("headline") or hit.get("note", "")
    detail = hit.get("detail") or ""
    if not headline:
        return None
    return _card("Your last run", "🏃", headline, detail, tone="run")


def moment_cards():
    """Ordered list of moment cards to show above the tips (may be empty).

    Moments are a nicety layered on the tips popup, so any data hiccup degrades to
    'no moment' rather than breaking the drawer."""
    cards = []
    for builder in (_block_summary_card, _post_workout_card):
        try:
            card = builder()
        except Exception:  # noqa: BLE001 — never let a moment break the drawer
            card = None
        if card:
            cards.append(card)
    return cards


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


def ensure_moments():
    """Generate any missing moments (each cached), so the cards can render fresh.

    Called when the tips drawer opens. Every step is guarded — a missing LLM
    provider or data gap must never break opening the drawer; it just means no
    moment card that time."""
    try:
        r = data.last_run()
    except Exception:  # noqa: BLE001
        r = None
    if r and r.get("activity_id") is not None and not execution.cached(r["activity_id"]):
        try:
            session = _matched_session(r)
            streams = data.run_streams(r["activity_id"])
            execution.ensure_note(r, session, streams)
        except Exception:  # noqa: BLE001 — debrief is best-effort
            pass
    try:
        from garmin_coach.coach import block_summary
        block_summary.ensure_current()
    except Exception:  # noqa: BLE001 — wrap-up is best-effort
        pass


def _block_summary_card():
    """End-of-block/week recap — filled in Phase D (block_summary)."""
    try:
        from garmin_coach.coach import block_summary
    except ImportError:
        return None
    hit = block_summary.current_cached()
    if not hit:
        return None
    return _card("Block wrap-up", "📦", hit.get("headline", ""),
                 hit.get("detail", ""), tone="block")
