"""Coach tab — science-backed recommendations + goal-driven plan (you-in-the-loop).

Displays the latest saved recommendation/plan, and lets the athlete regenerate
them on demand (each runs the LLM over current data — a slow call, wrapped in a
loading spinner).
"""
from __future__ import annotations

import re

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, ctx, dcc, html
from dash.exceptions import PreventUpdate

from garmin_coach.coach import plan as plan_mod
from garmin_coach.coach import recommend as rec_mod
from garmin_coach.coach import schedule
from garmin_coach.dashboard import figures
from garmin_coach.dashboard.ui import CARD, fmt_pace, section
from garmin_coach.knowledge import kb

PRIORITY_COLOR = {"high": "red", "medium": "orange", "low": "gray"}
PRIORITY_HEX = {"high": figures.RED, "medium": figures.ORANGE, "low": figures.MUTED}


def _empty(msg):
    return dmc.Card(dmc.Text(msg, c="dimmed"), **CARD)


# Split a free-text flag into a short bold topic + the detail that follows.
_FLAG_LEAD = re.compile(r"^(.{3,46}?)(?::\s|\s[—–-]\s)(.+)$", re.S)


_FLAG_STOP = {"on", "the", "and", "with", "of", "in", "a", "to", "is", "are",
              "at", "for", "that", "but", "so", "as", "by", "from", "signals", "mean"}


def _flag_parts(text):
    text = text.strip()
    m = _FLAG_LEAD.match(text)
    if m:
        return m.group(1).strip(" .,:—–-"), m.group(2).strip()
    # No clean delimiter: take leading words up to the first filler word (max 4).
    words = text.split()
    lead = [words[0]]
    for w in words[1:4]:
        if w.lower().strip(".,") in _FLAG_STOP:
            break
        lead.append(w)
    return " ".join(lead), " ".join(words[len(lead):])


def _flag_row(text):
    lead, rest = _flag_parts(text)
    body = [html.B(lead)]
    if rest:
        body.append(" — " + rest)
    return html.Div([
        html.Span(className="dot"),
        html.Div(body, className="txt"),
    ], className="gc-flag")


def render_recs(rec):
    if not rec:
        return _empty("No recommendations yet — click “Refresh recommendations”.")
    items = []
    for i, r in enumerate(rec.get("recommendations", [])):
        accent = PRIORITY_HEX.get(r["priority"], figures.MUTED)
        control = dmc.AccordionControl(dmc.Group([
            dmc.Badge(r["priority"], color=PRIORITY_COLOR.get(r["priority"], "gray"),
                      variant="filled", size="sm", w=64),
            dmc.Text(r["title"], fw=600, size="sm"),
            dmc.Badge(r["horizon"].replace("_", " "), variant="outline",
                      color="gray", size="xs"),
        ], gap="sm", align="center", wrap="nowrap"))
        panel = dmc.AccordionPanel(dmc.Stack([
            dmc.Text(r["action"], className="gc-rec-action",
                     style={"color": accent}),
            dmc.Text(r["rationale"], size="sm", c="dimmed",
                     style={"lineHeight": 1.6}),
            *([dmc.Text("Sources · " + "; ".join(r["citations"]), size="xs",
                        c="dimmed", fs="italic")] if r.get("citations") else []),
        ], gap=8))
        items.append(dmc.AccordionItem([control, panel], value=str(i),
                     style={"--accent": accent}))
    actions = html.Div(
        dmc.Accordion(items, multiple=True, chevronPosition="right", variant="filled"),
        className="gc-recs")
    flags = rec.get("flags", [])
    head = [
        dmc.Group([
            dmc.Text("Assessment", fw=700, size="md"),
            dmc.Text(f"generated {rec.get('generated_at','')[:16]} · KB v{rec.get('kb_version','?')}",
                     size="xs", c="dimmed", className="mono"),
        ], justify="space-between"),
        dmc.Spoiler(
            showLabel="Show full assessment", hideLabel="Show less", maxHeight=80,
            children=html.Div(rec.get("assessment", ""), className="gc-assessment"),
            mt=10),
    ]
    if flags:
        head.append(html.Div([
            html.Div("Flags", className="gc-flags-lab"),
            *[_flag_row(f) for f in flags],
        ], className="gc-flags"))
    return dmc.Stack([
        dmc.Card(head, className="gc-console", p="lg"),
        section("Prioritised actions"),
        actions,
    ], gap="md")


TYPE_COLOR = {"easy": "teal", "long": "blue", "tempo": "orange",
              "threshold": "orange", "intervals": "red", "workout": "red",
              "race": "grape", "rest": "gray", "cross": "gray"}
# status -> (glyph, css class)
STATUS_META = {
    "done": ("✓", "done"), "today": ("●", "today"), "missed": ("!", "missed"),
    "upcoming": ("", "upcoming"), "rest": ("·", "rest"), "skipped": ("✕", "skipped"),
}


def _act_btn(label, key, act, active):
    return html.Button(label, id={"type": "plan-act", "key": key, "act": act},
                       n_clicks=0,
                       className="plan-actbtn" + (" active" if active else ""))


def _session_card(s):
    typ = (s["type"] or "").lower()
    glyph, scls = STATUS_META.get(s["status"], ("", "upcoming"))
    is_rest = typ == "rest"
    draggable = s["editable"] and not is_rest and s["status"] in (
        "upcoming", "today", "missed")
    body = [html.Div([
        dmc.Badge(s["type"], color=TYPE_COLOR.get(typ, "gray"),
                  variant="light", size="xs"),
        html.Span(glyph, className=f"plan-stat-ic s-{scls}"),
    ], className="plan-card-top")]
    if s.get("description"):
        body.append(html.Div(s["description"], className="plan-card-desc"))
    if s.get("target") and not is_rest:
        body.append(html.Div(s["target"], className="plan-card-target"))
    m = s.get("match")
    if s["status"] == "done" and m:
        body.append(html.Div(
            f"ran {(m['distance_m'] or 0) / 1000:.1f} km · {fmt_pace(m['avg_pace_s_km'])}",
            className="plan-card-actual"))
    if s.get("note"):
        body.append(html.Div(s["note"], className="plan-card-note"))
    if s["editable"] and not is_rest:
        body.append(html.Div([
            _act_btn("Done", s["key"], "done", s["status"] == "done"),
            _act_btn("Skip", s["key"], "skip", s["status"] == "skipped"),
        ], className="plan-card-acts"))
    return html.Div(body, className=f"plan-card s-{scls}",
                    draggable="true" if draggable else "false",
                    **{"data-key": s["key"], "data-week": str(s["week_index"])})


def _day_column(day, week):
    d = day["date"]
    hcls = "plan-daycol-head"
    if day["is_today"]:
        hcls += " today"
    elif day["is_past"]:
        hcls += " past"
    # Rest days aren't workouts — leave them empty rather than showing a card, so
    # every day reads the same (a workout card or nothing).
    cards = [_session_card({**s, "editable": week["editable"]})
             for s in day["sessions"] if (s["type"] or "").lower() != "rest"]
    if not cards:
        cards = [html.Div("—", className="plan-empty")]
    return html.Div([
        html.Div([html.Span(f"{d:%a}", className="dow"),
                  html.Span(f"{d:%-d}", className="dom")], className=hcls),
        html.Div(cards, className="plan-daycol-body"),
    ], className="plan-daycol" + (" editable" if week["editable"] else ""),
        **{"data-date": d.isoformat(), "data-week": str(week["week_index"]),
           "data-editable": "1" if week["editable"] else "0"})


def _board(week):
    badge = dmc.Badge("This week" if week["is_current"] else "Next week",
                      color="yellow" if week["is_current"] else "gray",
                      variant="light", size="sm")
    head = html.Div([
        html.Div([dmc.Text(week["label"], fw=700, size="sm"), badge],
                 style={"display": "flex", "gap": "10px", "alignItems": "center"}),
        dmc.Text(f"{week['done']}/{week['total']} done"
                 + (f" · {week['theme']}" if week["theme"] else ""),
                 size="xs", c="dimmed"),
    ], className="plan-week-head")
    grid = html.Div([_day_column(day, week) for day in week["days"]],
                    className="plan-board-grid")
    return html.Div([head, grid], className="plan-board-week")


def _later_table(week):
    rows = [html.Tr([
        html.Td(f"{s['date']:%a}"),
        html.Td(dmc.Badge(s["type"], color=TYPE_COLOR.get((s["type"] or "").lower(),
                          "gray"), variant="light", size="xs")),
        html.Td(s["description"]),
        html.Td(dmc.Text(s.get("target", ""), size="xs", c="dimmed")),
    ]) for s in week["sessions"] if (s["type"] or "").lower() != "rest"]
    return dmc.Card([
        dmc.Group([dmc.Text(week["label"], fw=700, size="sm"),
                   dmc.Text(week["theme"], c="dimmed", size="xs")]),
        dmc.Table([html.Thead(html.Tr([html.Th(h) for h in
                   ["Day", "Type", "Session", "Target"]])),
                   html.Tbody(rows)], striped=True),
    ], **CARD)


def render_boards(plan):
    """The dynamic, editable part of the plan (re-rendered on each edit)."""
    sched = schedule.build_schedule(plan)
    cur = sched["current_index"]
    boards = [w for w in sched["weeks"] if w["week_index"] in (cur, cur + 1)]
    later = [w for w in sched["weeks"] if w["week_index"] > cur + 1]
    out = []
    if boards:
        out.append(section("This week & next"))
        out.append(html.Div(
            "Drag a workout to another day to reschedule. "
            "Use Done / Skip to log what you actually did.",
            className="plan-hint"))
        out.extend(_board(w) for w in boards)
    if later:
        out.append(section("Later weeks"))
        out.extend(_later_table(w) for w in later)
    return out


def render_plan(plan):
    if not plan:
        return _empty("No plan yet — set a goal and click “Generate plan”.")
    macro = [dmc.Card([
        dmc.Group([dmc.Text(ph["phase"], fw=700),
                   dmc.Badge(ph["weeks"], variant="light", size="sm")],
                  justify="space-between"),
        dmc.Text(ph["focus"], size="sm", c="dimmed", mt=4),
        *([dmc.Text(f"Volume: {ph['weekly_volume_km']} km/wk", size="xs", c="dimmed", mt=2)]
          if ph.get("weekly_volume_km") else []),
    ], **CARD) for ph in plan.get("macro", [])]

    return dmc.Stack([
        dcc.Store(id="plan-dnd-store"),
        dmc.Card([
            dmc.Group([dmc.Text(f"Plan · {plan.get('goal','')}", fw=700, size="lg"),
                       dmc.Group([
                           html.Span(id="plan-save-status", className="plan-save-status"),
                           dmc.Text(f"target {plan.get('goal_date','') or '—'} · "
                                    f"generated {plan.get('generated_at','')[:16]}",
                                    size="xs", c="dimmed")], gap="md")],
                      justify="space-between"),
            dmc.Text(plan.get("assessment", ""), size="sm", mt=4),
        ], **CARD),
        section("3-month macro"),
        dmc.SimpleGrid(macro, cols={"base": 1, "sm": 2, "lg": 3}, spacing="md"),
        html.Div(render_boards(plan), id="plan-board"),
        *([dmc.Alert(dmc.Stack([dmc.Text(f"• {n}", size="sm")
                                for n in plan["adaptation_notes"]], gap=2),
                     title="How this adapts", color="blue", variant="light")]
          if plan.get("adaptation_notes") else []),
    ], gap="md")


def layout():
    kb_doc = kb.load_kb()
    kb_note = (f"Knowledge base v{kb_doc['version']} · {len(kb_doc['entries'])} cited topics"
               if kb_doc else "Knowledge base not built yet — run the research pass.")
    return dmc.Stack([
        section("Coach console"),
        dmc.Card([
            dmc.Group([
                dmc.TextInput(id="coach-goal", placeholder="Goal e.g. sub-50 10k",
                              w=260, label="Race goal",
                              value=(plan_mod.load_latest() or {}).get("goal", "")),
                dmc.TextInput(id="coach-date", placeholder="YYYY-MM-DD", w=180,
                              label="Race date",
                              value=(plan_mod.load_latest() or {}).get("goal_date", "") or ""),
                dmc.Button("Generate plan", id="coach-plan-btn", mt=22),
                dmc.Button("Refresh recommendations", id="coach-rec-btn",
                           variant="default", mt=22),
            ], gap="sm", align="end"),
            dmc.Text(kb_note, size="xs", c="dimmed", className="mono", mt="sm"),
        ], className="gc-console", p="md"),
        dmc.Tabs([
            dmc.TabsList([
                dmc.TabsTab("Recommendations", value="recs"),
                dmc.TabsTab("Plan", value="plan"),
            ]),
            dmc.TabsPanel(dcc.Loading(html.Div(render_recs(rec_mod.load_latest()),
                                               id="coach-recs")), value="recs", pt="md"),
            dmc.TabsPanel(dcc.Loading(html.Div(render_plan(plan_mod.load_latest()),
                                               id="coach-plan")), value="plan", pt="md"),
        ], value="recs"),
    ], gap="md")


@callback(Output("coach-recs", "children"), Input("coach-rec-btn", "n_clicks"),
          prevent_initial_call=True)
def _refresh_recs(_n):
    return render_recs(rec_mod.recommend())


@callback(Output("coach-plan", "children"), Input("coach-plan-btn", "n_clicks"),
          State("coach-goal", "value"), State("coach-date", "value"),
          prevent_initial_call=True)
def _make_plan(_n, goal, date):
    if not goal:
        return _empty("Enter a goal first.")
    return render_plan(plan_mod.make_plan(goal, goal_date=date or None))


@callback(Output("plan-board", "children"), Output("plan-save-status", "children"),
          Input("plan-dnd-store", "data"),
          Input({"type": "plan-act", "key": ALL, "act": ALL}, "n_clicks"),
          prevent_initial_call=True)
def _edit_plan(dnd, _clicks):
    """Apply a drag-reschedule or a Done/Skip toggle, persist, re-render boards."""
    trig = ctx.triggered_id
    if trig == "plan-dnd-store":
        if not dnd or not dnd.get("key"):
            raise PreventUpdate
        plan = plan_mod.set_override(dnd["key"], {"date": dnd["date"]})
        status = "Rescheduled ✓"
    elif isinstance(trig, dict) and trig.get("type") == "plan-act":
        # Ignore the re-render that recreates these buttons with n_clicks=0.
        if not (ctx.triggered and ctx.triggered[0]["value"]):
            raise PreventUpdate
        key, act = trig["key"], trig["act"]
        want = "done" if act == "done" else "skipped"
        plan = plan_mod.load_latest() or {}
        cur = (plan.get("overrides", {}).get(key) or {}).get("status")
        plan = plan_mod.set_override(key, {"status": None if cur == want else want})
        status = "Updated ✓"
    else:
        raise PreventUpdate
    if plan is None:
        raise PreventUpdate
    return render_boards(plan), status
