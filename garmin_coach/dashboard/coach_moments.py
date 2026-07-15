"""Timely coach 'moments' surfaced at the top of the tips drawer.

Two kinds:
  * post-workout debrief — the coach's read of your most recent run, for ANY run
    (free or structured, planned or not); reuses `coach/execution.py`. Handled by
    `last_run_read`, which generates on demand and *surfaces failures* (e.g. the
    LLM being unreachable) instead of silently showing nothing.
  * end-of-block / week summary — a recap of the block you just finished
    (`coach/block_summary.py`), shown via `moment_cards`.

The LLM output is cached, so generation runs at most once per run / block.
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


def _error_card(msg: str):
    """Show *why* the coach's read couldn't be produced, so it's diagnosable
    instead of silently blank (single-user app — a raw reason is useful)."""
    return dmc.Card([
        dmc.Group([html.Span("⚠️", className="gc-moment-ic"),
                   dmc.Text("Coach's read unavailable", size="xs", c="dimmed",
                            tt="uppercase", fw=700)], gap="xs"),
        dmc.Text("Couldn't generate a read of your last run.", fw=600, size="sm", mt=6),
        dmc.Text((msg or "")[:300], size="xs", c="dimmed", mt=4,
                 style={"whiteSpace": "pre-wrap", "wordBreak": "break-word"}),
    ], className="gc-moment gc-moment-run", radius="md", p="md", withBorder=True)


def last_run_read():
    """The coach's read of the most recent run — any run type. Generates once and
    caches; returns a card, an error card (with the reason), or None if no run."""
    try:
        r = data.last_run()
    except Exception as e:  # noqa: BLE001
        return _error_card(f"Couldn't load your last run: {e}")
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
            return _error_card(f"{type(e).__name__}: {e}")
    if not hit or not (hit.get("headline") or hit.get("detail")):
        return None
    return _card("Your last run", "🏃", hit.get("headline") or hit.get("note", ""),
                 hit.get("detail", ""), tone="run")


def moment_cards():
    """Block-summary moment card(s) for the tips popup (may be empty). The
    post-workout read is handled separately by `last_run_read`."""
    try:
        card = _block_summary_card()
    except Exception:  # noqa: BLE001 — a moment must never break the popup
        card = None
    return [card] if card else []


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
    """Generate the block-summary moment (cached) when the popup opens. The
    post-workout read generates itself in `last_run_read`. Guarded — a missing LLM
    or data gap must never break opening the popup."""
    try:
        from garmin_coach.coach import block_summary
        block_summary.ensure_current()
    except Exception:  # noqa: BLE001 — wrap-up is best-effort
        pass


def _block_summary_card():
    """End-of-block/week recap (`coach/block_summary.py`)."""
    try:
        from garmin_coach.coach import block_summary
    except ImportError:
        return None
    hit = block_summary.current_cached()
    if not hit:
        return None
    return _card("Block wrap-up", "📦", hit.get("headline", ""),
                 hit.get("detail", ""), tone="block")
