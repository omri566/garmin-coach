"""Coaching tips — the floating coach's popup, reachable from every screen.

The coach avatar button (mounted in the app shell) opens this right-side drawer.
It shows, top-down: any timely coach *moments* (post-workout debrief / end-of-block
summary — see `coach_moments`), a one-line read of how you're doing, and the
**few most relevant** tips (capped, priority-first). Content is the saved
recommendation (`coach/recommend.py`); the LLM only re-runs on "Refresh tips".
"""
from __future__ import annotations

import re

import dash_mantine_components as dmc
from dash import Input, Output, State, callback, ctx, dcc, html
from dash.exceptions import PreventUpdate

from garmin_coach.coach import recommend as rec_mod
from garmin_coach.dashboard import coach_moments, data, figures
from garmin_coach.dashboard.ui import section

PRIORITY_COLOR = {"high": "red", "medium": "orange", "low": "gray"}
PRIORITY_HEX = {"high": figures.RED, "medium": figures.ORANGE, "low": figures.MUTED}
PRIORITY_LABEL = {"high": "Do first", "medium": "Soon", "low": "Optional"}
_PRIO_RANK = {"high": 0, "medium": 1, "low": 2}
_HORIZON_RANK = {"today": 0, "this_week": 1, "this_block": 2}

# How many tips the coach surfaces at once — deliberately few, most-relevant only.
TIP_LIMIT = 3

_FLAG_LEAD = re.compile(r"^(.{3,46}?)(?::\s|\s[—–-]\s)(.+)$", re.S)
_FLAG_STOP = {"on", "the", "and", "with", "of", "in", "a", "to", "is", "are",
              "at", "for", "that", "but", "so", "as", "by", "from", "signals", "mean"}
_INSIGHT_ICON = {"time_of_day": "🕑", "late_sleep": "😴", "sleep_perf": "😴",
                 "rest_rebound": "🛌", "cadence": "🦶", "readiness": "⚡",
                 "hrv": "💓", "resting_hr": "❤️"}


def _empty(msg):
    return dmc.Text(msg, c="dimmed", size="sm")


def _flag_parts(text):
    text = text.strip()
    m = _FLAG_LEAD.match(text)
    if m:
        return m.group(1).strip(" .,:—–-"), m.group(2).strip()
    words = text.split()
    lead = [words[0]] if words else [""]
    for w in words[1:4]:
        if w.lower().strip(".,") in _FLAG_STOP:
            break
        lead.append(w)
    return " ".join(lead), " ".join(words[len(lead):])


def _short_title(title: str) -> str:
    lead = re.split(r"\s[—–-]\s|\s*\(", title, maxsplit=1)[0].strip()
    return lead or title


def _watchout_chips(flags):
    chips = []
    for f in flags:
        lead, rest = _flag_parts(f)
        chip = dmc.Badge("⚠ " + lead, color="orange", variant="light", size="sm",
                         className="gc-watch-chip")
        chips.append(dmc.Tooltip(chip, label=rest, multiline=True, w=300,
                                 withArrow=True, openDelay=120, position="top")
                     if rest else chip)
    return dmc.Group(chips, gap="xs")


def _insights_blocks():
    """A short 'what your data shows' list, or [] if no pattern is strong enough."""
    try:
        insights = data.personal_insights()
    except Exception:  # noqa: BLE001 — insights are a nicety, never break the drawer
        insights = []
    if not insights:
        return []
    cards = [dmc.Card([
        dmc.Group([html.Span(_INSIGHT_ICON.get(ins["kind"], "📈"),
                             className="gc-insight-ic"),
                   dmc.Text(ins["title"], fw=700, size="sm")], gap="sm", wrap="nowrap"),
        dmc.Text(ins["detail"], size="sm", c="dimmed", style={"lineHeight": 1.5}),
    ], className="gc-card", radius="md", p="sm") for ins in insights[:2]]
    return [section("What your data shows"),
            dmc.Stack(cards, gap="sm")]


def _top_recs(recs, limit=TIP_LIMIT):
    """The few most relevant tips — highest priority, nearest horizon first."""
    return sorted(recs, key=lambda r: (_PRIO_RANK.get(r.get("priority"), 3),
                                       _HORIZON_RANK.get(r.get("horizon"), 3)))[:limit]


def render_recs(rec, limit=TIP_LIMIT):
    insights = _insights_blocks()
    if not rec:
        empty = _empty("No tips yet — tap “Refresh tips” to ask your coach.")
        return dmc.Stack([*insights, empty], gap="md") if insights else empty
    items = []
    for i, r in enumerate(_top_recs(rec.get("recommendations", []), limit)):
        accent = PRIORITY_HEX.get(r["priority"], figures.MUTED)
        control = dmc.AccordionControl(dmc.Group([
            dmc.Badge(PRIORITY_LABEL.get(r["priority"], r["priority"]),
                      color=PRIORITY_COLOR.get(r["priority"], "gray"),
                      variant="light", size="sm", w=92),
            dmc.Text(_short_title(r["title"]), fw=600, size="sm", lineClamp=1),
        ], gap="sm", align="center", wrap="nowrap"))
        panel = dmc.AccordionPanel(dmc.Stack([
            dmc.Text(r["action"], className="gc-rec-action", style={"color": accent}),
            dmc.Text(r["rationale"], size="sm", c="dimmed", style={"lineHeight": 1.6}),
            *([dmc.Text("Based on · " + "; ".join(r["citations"]), size="xs",
                        c="dimmed", fs="italic")] if r.get("citations") else []),
        ], gap=8))
        items.append(dmc.AccordionItem([control, panel], value=str(i),
                     style={"--accent": accent}))
    actions = html.Div(
        dmc.Accordion(items, multiple=True, chevronPosition="right", variant="filled"),
        className="gc-recs")

    text = (rec.get("assessment", "") or "").strip()
    bits = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
    headline = bits[0] if bits else text
    head = [dmc.Text("How you're doing", fw=700, size="md"),
            dmc.Text(headline, className="gc-assessment-lead", mt=6)]
    flags = rec.get("flags", [])
    if flags:
        head.append(html.Div([
            html.Div("Watch-outs", className="gc-flags-lab"),
            _watchout_chips(flags),
        ], className="gc-flags", style={"marginTop": "10px"}))
    return dmc.Stack([
        dmc.Card(head, className="gc-console", p="md"),
        *insights,
        section("Your focus right now"),
        actions,
    ], gap="md")


def _tips_body():
    return dmc.Stack([
        dmc.Group([
            dmc.Text("Your coach", fw=700, size="sm"),
            html.Button("✕", id="gc-tips-close", n_clicks=0,
                        className="gc-tips-close", **{"aria-label": "Close"}),
        ], justify="space-between", align="center"),
        dcc.Loading(html.Div(coach_moments.moment_cards(), id="gc-coach-moments"),
                    type="dot", color=figures.AMP),
        html.Div(render_recs(rec_mod.load_latest()), id="coach-recs"),
        dmc.Button("↻ Refresh tips", id="coach-rec-btn", variant="light",
                   size="xs", mt="sm"),
    ], gap="md")


def widget():
    """The movable floating coach + its tips popup, mounted once in the shell.

    The dock is a fixed, draggable wrapper (see assets/coach_fab.js); inside it the
    tips panel is anchored just above the plain-`html.Button` avatar and shown/
    hidden purely by a CSS class we toggle from a store we own — so opening is
    100% reliable (no Mantine Popover cloning the button or de-syncing its state).
    """
    from garmin_coach.dashboard.pages import settings
    fab = html.Button(settings.fab_content(data.coach_avatar()),
                      id="gc-coach-fab", n_clicks=0, className="gc-coach-fab",
                      **{"aria-label": "Coaching tips"})
    return html.Div([
        dcc.Store(id="gc-tips-open", data=False),
        html.Div(_tips_body(), id="gc-tips-pop", className="gc-tips-pop"),
        fab,
    ], id="gc-coach-dock", className="gc-coach-dock")


@callback(Output("gc-tips-open", "data"),
          Input("gc-coach-fab", "n_clicks"), Input("gc-tips-close", "n_clicks"),
          State("gc-tips-open", "data"), prevent_initial_call=True)
def _toggle(_fab, _close, is_open):
    """Coach tap toggles the popup; the ✕ always closes it. Fully deterministic —
    we own the open state, so a tap always registers."""
    if ctx.triggered_id == "gc-tips-close":
        return False
    return not is_open


@callback(Output("gc-tips-pop", "className"), Input("gc-tips-open", "data"))
def _visibility(is_open):
    return "gc-tips-pop open" if is_open else "gc-tips-pop"


@callback(Output("gc-coach-moments", "children"),
          Input("gc-tips-open", "data"), prevent_initial_call=True)
def _fill_moments(is_open):
    """When the coach popup opens, generate any missing moments (cached) and show
    them. Generation is one-time per run/block, so repeat opens are instant."""
    if not is_open:
        raise PreventUpdate
    coach_moments.ensure_moments()
    return coach_moments.moment_cards()


@callback(Output("coach-recs", "children"), Input("coach-rec-btn", "n_clicks"),
          prevent_initial_call=True)
def _refresh_recs(_n):
    return render_recs(rec_mod.recommend())
