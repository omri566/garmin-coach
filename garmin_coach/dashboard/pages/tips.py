"""Coaching tips — the floating coach's popup ('Coach says' design).

Reachable from every screen via the coach avatar button (see app shell + tips.widget).
Instead of dumping every section at once, the coach shows ONE focused message at a
time; a row of chips switches topic (top tip · last run · this week · watch-outs),
swapped client-side (see assets/coach_says.js) so it's instant. The LLM-backed
messages (last-run read, block wrap-up) are generated once on open and cached.
"""
from __future__ import annotations

import datetime as dt
import re

import dash_mantine_components as dmc
from dash import Input, Output, State, callback, ctx, dcc, html
from dash.exceptions import PreventUpdate

from garmin_coach.coach import plan as plan_mod
from garmin_coach.coach import recommend as rec_mod
from garmin_coach.dashboard import coach_moments, data, figures

_PRIO_RANK = {"high": 0, "medium": 1, "low": 2}
_HORIZON_RANK = {"today": 0, "this_week": 1, "this_block": 2}

# How many tips the coach considers (the top one leads; the rest fold into 'More').
TIP_LIMIT = 3


def _short_title(title: str) -> str:
    lead = re.split(r"\s[—–-]\s|\s*\(", title or "", maxsplit=1)[0].strip()
    return lead or (title or "")


def _top_recs(recs, limit=TIP_LIMIT):
    """The few most relevant tips — highest priority, nearest horizon first."""
    return sorted(recs, key=lambda r: (_PRIO_RANK.get(r.get("priority"), 3),
                                       _HORIZON_RANK.get(r.get("horizon"), 3)))[:limit]


def _messages():
    """Ordered coach messages for the popup: dicts of {label, head, detail}. One is
    shown at a time; chips switch between them. Only messages with content appear."""
    msgs: list[dict] = []
    phase = _phase_done_message()                  # leads if a phase just finished
    if phase:
        msgs.append(phase)
    coach_moments.ensure_moments()                 # generate the block wrap-up (cached)
    rec = rec_mod.load_latest() or {}
    recs = _top_recs(rec.get("recommendations", []))

    if recs:
        r0 = recs[0]
        msgs.append({"label": "Top tip",
                     "head": r0.get("action") or _short_title(r0.get("title", "")),
                     "detail": r0.get("rationale", "")})

    note = coach_moments.last_run_note()           # {headline,detail} / {error} / None
    if note:
        if note.get("error"):
            msgs.append({"label": "Last run",
                         "head": "Couldn't read your last run",
                         "detail": note["error"]})
        elif note.get("headline") or note.get("detail"):
            msgs.append({"label": "Last run", "head": note.get("headline", ""),
                         "detail": note.get("detail", "")})

    week = _this_week(rec)
    if week:
        msgs.append(week)

    flags = rec.get("flags") or []
    if flags:
        msgs.append({"label": f"Watch-outs · {len(flags)}",
                     "head": "Keep an eye on these", "detail": " · ".join(flags)})

    if len(recs) > 1:
        extra = recs[1:]
        msgs.append({"label": "More tips",
                     "head": f"{len(extra)} more suggestion{'s' if len(extra) != 1 else ''}",
                     "detail": "  •  ".join(
                         (r.get("action") or _short_title(r.get("title", ""))) for r in extra)})
    return msgs


def _phase_done_message():
    """A temporary 'Phase done 🎉' message for the ~10 days after advancing into a
    new phase — congrats + what to improve, from `plan.advance_phase`'s debrief."""
    plan = plan_mod.load_latest() or {}
    deb = plan.get("phase_debrief") or {}
    if deb.get("phase_index") != plan.get("phase_index", 0):
        return None
    if not (deb.get("headline") or deb.get("improve")):
        return None
    gen = (deb.get("generated_at") or "")[:10]
    try:
        if gen and (dt.date.today() - dt.date.fromisoformat(gen)).days > 10:
            return None
    except ValueError:
        pass
    macro = plan.get("macro") or []
    idx = plan.get("phase_index", 0)
    moved_into = macro[idx].get("phase") if 0 <= idx < len(macro) else "your new phase"
    return {"label": "Phase done 🎉",
            "head": deb.get("headline") or f"You started {moved_into}!",
            "detail": "  •  ".join(deb.get("improve") or [])}


def _this_week(rec):
    """Prefer the end-of-block wrap-up; fall back to the overall assessment."""
    try:
        from garmin_coach.coach import block_summary
        bs = block_summary.current_cached()
    except Exception:  # noqa: BLE001
        bs = None
    if bs and (bs.get("headline") or bs.get("detail")):
        return {"label": "This week", "head": bs.get("headline", ""),
                "detail": bs.get("detail", "")}
    if rec.get("assessment"):
        return {"label": "This week", "head": "How you're doing",
                "detail": rec["assessment"]}
    return None


def _says_view():
    """The 'Coach says' body: one message bubble + topic chips (swapped client-side)."""
    msgs = _messages()
    if not msgs:
        return dmc.Text("No coaching yet — tap “Refresh tips” to ask your coach.",
                        c="dimmed", size="sm")
    first = msgs[0]
    avatar = data.coach_avatar()
    av = (html.Img(src=avatar, className="gc-says-avimg") if avatar
          else html.Span("🧑‍🏫"))
    bubble = html.Div([
        html.Div(first["head"], id="gc-says-h", className="gc-says-h"),
        html.Div(first["detail"], id="gc-says-p", className="gc-says-p"),
    ], className="gc-says-bubble")
    chips = html.Div([
        html.Button(m["label"], className="gc-says-chip" + (" on" if i == 0 else ""),
                    **{"data-h": m["head"], "data-p": m["detail"], "type": "button"})
        for i, m in enumerate(msgs)
    ], className="gc-says-chips")
    return html.Div([html.Div([html.Div(av, className="gc-says-av"), bubble],
                              className="gc-says"), chips])


def _tips_body():
    return dmc.Stack([
        dmc.Group([
            dmc.Text("Your coach", fw=700, size="sm"),
            html.Button("✕", id="gc-tips-close", n_clicks=0,
                        className="gc-tips-close", **{"aria-label": "Close"}),
        ], justify="space-between", align="center"),
        dcc.Loading(html.Div(id="gc-coach-says"), type="dot", color=figures.AMP),
        dmc.Button("↻ Refresh tips", id="coach-rec-btn", variant="light",
                   size="xs", mt="sm"),
    ], gap="md")


def widget():
    """The movable floating coach + its tips popup, mounted once in the shell.

    The dock is a fixed, draggable wrapper (assets/coach_fab.js); inside it the
    tips panel is anchored just above the plain-`html.Button` avatar and shown/
    hidden purely by a CSS class we toggle from a store we own — so opening is
    100% reliable."""
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
    """Coach tap toggles the popup; the ✕ always closes it."""
    if ctx.triggered_id == "gc-tips-close":
        return False
    return not is_open


@callback(Output("gc-tips-pop", "className"), Input("gc-tips-open", "data"))
def _visibility(is_open):
    return "gc-tips-pop open" if is_open else "gc-tips-pop"


@callback(Output("gc-coach-says", "children"),
          Input("gc-tips-open", "data"), prevent_initial_call=True)
def _fill(is_open):
    """Build the coach's messages on first open (generating cached LLM content)."""
    if not is_open:
        raise PreventUpdate
    return _says_view()


@callback(Output("gc-coach-says", "children", allow_duplicate=True),
          Input("coach-rec-btn", "n_clicks"), prevent_initial_call=True)
def _refresh(_n):
    rec_mod.recommend()
    return _says_view()
