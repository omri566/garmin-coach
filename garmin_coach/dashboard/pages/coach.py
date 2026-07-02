"""Coach tab — science-backed recommendations + goal-driven plan (you-in-the-loop).

Displays the latest saved recommendation/plan, and lets the athlete regenerate
them on demand (each runs the LLM over current data — a slow call, wrapped in a
loading spinner).
"""
from __future__ import annotations

import datetime as dt
import re

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from garmin_coach.coach import plan as plan_mod
from garmin_coach.coach import recommend as rec_mod
from garmin_coach.coach import schedule
from garmin_coach.dashboard import data, figures
from garmin_coach.dashboard.ui import CARD, fmt_pace, section
from garmin_coach.knowledge import kb

PRIORITY_COLOR = {"high": "red", "medium": "orange", "low": "gray"}
PRIORITY_HEX = {"high": figures.RED, "medium": figures.ORANGE, "low": figures.MUTED}
PRIORITY_LABEL = {"high": "Do first", "medium": "Soon", "low": "When you can"}
_DAYS_SUN_FIRST = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


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
            dmc.Badge(PRIORITY_LABEL.get(r["priority"], r["priority"]),
                      color=PRIORITY_COLOR.get(r["priority"], "gray"),
                      variant="light", size="sm", w=92),
            dmc.Text(r["title"], fw=600, size="sm"),
            dmc.Badge(r["horizon"].replace("_", " "), variant="outline",
                      color="gray", size="xs"),
        ], gap="sm", align="center", wrap="nowrap"))
        panel = dmc.AccordionPanel(dmc.Stack([
            dmc.Text(r["action"], className="gc-rec-action",
                     style={"color": accent}),
            dmc.Text(r["rationale"], size="sm", c="dimmed",
                     style={"lineHeight": 1.6}),
            *([dmc.Text("Based on · " + "; ".join(r["citations"]), size="xs",
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
            dmc.Text("How you're doing", fw=700, size="md"),
            dmc.Text(f"updated {rec.get('generated_at','')[:10]}",
                     size="xs", c="dimmed", className="mono"),
        ], justify="space-between"),
        dmc.Spoiler(
            showLabel="Read more", hideLabel="Show less", maxHeight=80,
            children=html.Div(rec.get("assessment", ""), className="gc-assessment"),
            mt=10),
    ]
    if flags:
        head.append(html.Div([
            html.Div("Watch-outs", className="gc-flags-lab"),
            *[_flag_row(f) for f in flags],
        ], className="gc-flags"))
    return dmc.Stack([
        dmc.Card(head, className="gc-console", p="lg"),
        section("Your focus right now"),
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


def _board(week, tag=None, tag_color=None, anim=""):
    if tag is None:
        tag = "This week" if week["is_current"] else "Next week"
        tag_color = "yellow" if week["is_current"] else "gray"
    badge = dmc.Badge(tag, color=tag_color or "gray", variant="light", size="sm")
    head = html.Div([
        html.Div([dmc.Text(week["label"], fw=700, size="sm"), badge],
                 style={"display": "flex", "gap": "10px", "alignItems": "center"}),
        dmc.Text(f"{week['done']}/{week['total']} done"
                 + (f" · {week['theme']}" if week["theme"] else ""),
                 size="xs", c="dimmed"),
    ], className="plan-week-head")
    grid = html.Div([_day_column(day, week) for day in week["days"]],
                    className="plan-board-grid")
    return html.Div([head, grid],
                    className="plan-board-week" + (f" {anim}" if anim else ""))


def _week_tag(wk, cur):
    """(badge label, colour) describing a week relative to the current one."""
    i = wk["week_index"]
    if i == cur:
        return "This week", "yellow"
    if i == cur + 1:
        return "Next week", "teal"
    if i < cur:
        done = wk["total"] and wk["done"] >= wk["total"]
        return ("Completed" if done else "Past"), "gray"
    return (f"In {i - cur} weeks", "grape")


def _week_nav():
    """Static shell: prev/next arrows around the single-week board container."""
    return html.Div([
        html.Button("‹", id="plan-week-prev", n_clicks=0,
                    className="plan-nav-arrow", **{"aria-label": "Previous week"}),
        html.Div(id="plan-week-body", className="plan-week-single"),
        html.Button("›", id="plan-week-next", n_clicks=0,
                    className="plan-nav-arrow", **{"aria-label": "Next week"}),
    ], className="plan-week-nav")


def _view(data):
    """Unpack the plan-week-view store into (index, direction)."""
    if isinstance(data, dict):
        return data.get("idx"), data.get("dir", 0)
    return data, 0


def _render_week_body(plan, data, animate=True):
    """The one navigated week, as a board (editable only for this/next week).

    ``animate`` adds a directional slide-in class when the week changed via the
    arrows; edits re-render in place with no slide so a Done toggle doesn't lurch.
    """
    sched = schedule.build_schedule(plan)
    cur = sched["current_index"]
    weeks = sched["weeks"]
    idx, direction = _view(data)
    idx = cur if idx is None else max(0, min(len(weeks) - 1, idx))
    wk = weeks[idx]
    tag, color = _week_tag(wk, cur)
    anim = ""
    if animate and direction:
        anim = "wk-next" if direction > 0 else "wk-prev"
    return _board(wk, tag=tag, tag_color=color, anim=anim)


def _countdown(goal_date, today):
    if not goal_date:
        return "No race date set"
    try:
        d = dt.date.fromisoformat(goal_date)
    except (ValueError, TypeError):
        return "No race date set"
    days = (d - today).days
    if days > 7:
        wks = days // 7
        return f"{wks} weeks to race day"
    if days > 0:
        return f"{days} day{'s' if days != 1 else ''} to race day"
    if days == 0:
        return "Race day is today 🏁"
    return "Race day has passed"


def _ring(pct, color, caption):
    return html.Div([
        dmc.RingProgress(size=92, thickness=9, roundCaps=True,
                         sections=[{"value": max(0, min(100, pct)), "color": color}],
                         label=dmc.Text(f"{pct}%", ta="center", fw=700, size="sm")),
        html.Div(caption, className="gc-ring-cap"),
    ], className="gc-ring")


def _progress_hero(plan, sched, streak):
    weeks, cur, today = sched["weeks"], sched["current_index"], sched["today"]
    done = sum(w["done"] for w in weeks)
    total = sum(w["total"] for w in weeks)
    pct = round(100 * done / total) if total else 0
    this = weeks[cur] if weeks else None
    tdone, ttotal = (this["done"], this["total"]) if this else (0, 0)
    if ttotal and tdone >= ttotal:
        enc = "This week's done — great work! 🎉"
    elif ttotal:
        left = ttotal - tdone
        enc = f"{left} session{'s' if left != 1 else ''} to go this week — you've got this."
    else:
        enc = "Let's get moving."
    fit = data.fitness_progress(plan.get("generated_at"))

    chips = []
    if streak >= 2:
        chips.append(html.Div(["🔥 ", html.B(f"{streak}"), f"-week streak"],
                              className="gc-hero-chip hot"))
    if fit and fit.get("delta") is not None and abs(fit["delta"]) >= 1:
        up = fit["delta"] >= 0
        chips.append(html.Div([("▲ " if up else "▼ "), "Fitness ",
                               html.B(f"{'+' if up else ''}{fit['delta']:.0f}"),
                               " since you started"],
                              className="gc-hero-chip" + (" good" if up else "")))

    left_col = html.Div([
        html.Div(_countdown(plan.get("goal_date"), today), className="gc-hero-eyebrow"),
        html.Div(plan.get("goal", "Your plan"), className="gc-hero-goal"),
        html.Div(enc, className="gc-hero-enc"),
        html.Div(chips, className="gc-hero-chips") if chips else None,
    ], className="gc-hero-left")
    rings = html.Div([
        _ring(pct, "amp", "plan complete"),
        _ring(round(100 * tdone / ttotal) if ttotal else 0, "teal", "this week"),
    ], className="gc-hero-rings")
    return html.Div([left_col, rings], className="gc-plan-hero")


def _today_card(sched):
    today = sched["today"]
    todays, upcoming = [], []
    for w in sched["weeks"]:
        for s in w["sessions"]:
            if (s["type"] or "").lower() == "rest" or s["status"] in ("done", "skipped"):
                continue
            if s["date"] == today:
                todays.append(s)
            elif s["date"] > today:
                upcoming.append(s)
    if todays:
        s, when, is_today = todays[0], "Today", True
    elif upcoming:
        s = min(upcoming, key=lambda x: x["date"])
        when, is_today = (f"{s['date']:%A}" if (s["date"] - today).days < 7
                          else f"{s['date']:%a %b %-d}"), False
    else:
        return html.Div([
            html.Div("Nice — nothing left to do", className="gc-today-when"),
            html.Div("You're all caught up. Set a new goal when you're ready.",
                     className="gc-today-desc"),
        ], className="gc-today done")

    typ = (s["type"] or "").lower()
    body = [
        html.Div([
            html.Span("Today" if is_today else f"Next · {when}", className="gc-today-when"),
            dmc.Badge(s["type"], color=TYPE_COLOR.get(typ, "gray"), variant="light",
                      size="sm"),
        ], className="gc-today-head"),
        html.Div(s.get("description", ""), className="gc-today-desc"),
    ]
    if s.get("target"):
        body.append(html.Div(s["target"], className="gc-today-target"))
    body.append(dmc.Button(
        "Mark today done" if is_today else "Mark done", size="sm",
        id={"type": "plan-act", "key": s["key"], "act": "done-today"},
        n_clicks=0, className="gc-today-cta"))
    return html.Div(body, className="gc-today" + (" is-today" if is_today else ""))


def _milestones(plan, sched, streak):
    hl = data.activity_highlights(sched["today"])
    month_km = hl["month_km"]
    nxt = 50 * (int(month_km) // 50 + 1)        # next 50 km band this month
    chips = [
        ("🏅", "Longest run", f"{hl['longest_km']:.1f} km"),
        ("📅", "This month", f"{month_km:.0f} km"),
        ("🔥", "Streak", f"{streak} wk" if streak else "—"),
        ("🎯", "Next up", f"{nxt - month_km:.0f} km to {nxt}"),
    ]
    return html.Div([
        html.Div([html.Span(icon, className="ic"),
                  html.Div([html.Div(val, className="val"),
                            html.Div(lab, className="lab")], className="body")],
                 className="gc-mile")
        for icon, lab, val in chips
    ], className="gc-miles")


def render_boards(plan):
    """Progress summary (hero + today + milestones). The week board itself is
    navigated separately via the prev/next controls, so only this part is
    re-rendered when overall progress changes."""
    sched = schedule.build_schedule(plan)
    streak = data.running_streak_weeks(sched["today"])
    return [
        _progress_hero(plan, sched, streak),
        _today_card(sched),
        _milestones(plan, sched, streak),
    ]


def _macro_progress(ph, base_year, today):
    """(state, percent-complete) for a phase relative to today's date."""
    rng = schedule.parse_week_range(ph.get("weeks", ""), base_year, today)
    if not rng:
        return "", 0
    start, end = rng
    if today > end:
        return "past", 100
    if today < start:
        return "future", 0
    span = (end - start).days or 1
    return "current", max(0, min(100, round(100 * (today - start).days / span)))


def _phase_node(ph, i, state, pct):
    """One sleek accent card in the bigger-picture strip, with detail on hover."""
    weeks = ph.get("weeks", "")
    weeks_short = weeks.split("(")[0].strip().title() or weeks
    num = "✓" if state == "past" else str(i + 1)
    node = html.Div([
        html.Div([
            html.Span(num, className="gc-phase-num"),
            html.Div(ph["phase"], className="gc-phase-name"),
        ], className="gc-phase-row"),
        html.Div(weeks_short, className="gc-phase-weeks"),
        html.Div(html.I(style={"width": f"{pct}%"}), className="gc-phase-bar"),
    ], className="gc-phase" + (f" {state}" if state else ""))

    m = re.search(r"\((.*?)\)", weeks)
    dd = [dmc.Text(ph["phase"], fw=700, size="sm")]
    if m:
        dd.append(dmc.Text(m.group(1), size="xs", c="dimmed", className="mono"))
    if ph.get("focus"):
        dd.append(dmc.Text(ph["focus"], size="xs", c="dimmed",
                           style={"lineHeight": 1.5}))
    if ph.get("weekly_volume_km"):
        dd.append(dmc.Text(f"Volume · {ph['weekly_volume_km']}/wk", size="xs",
                           c="dimmed"))
    if ph.get("key_workouts"):
        dd.append(dmc.Stack([dmc.Text(f"• {w}", size="xs", c="dimmed")
                             for w in ph["key_workouts"]], gap=2))
    return dmc.HoverCard(
        [dmc.HoverCardTarget(node),
         dmc.HoverCardDropdown(dmc.Stack(dd, gap=6), style={"maxWidth": 340})],
        withArrow=True, shadow="lg", position="top", openDelay=120, width=340)


def _macro_timeline(plan, today):
    phases = plan.get("macro", [])
    if not phases:
        return None
    try:
        base_year = dt.date.fromisoformat((plan.get("generated_at") or "")[:10]).year
    except (ValueError, TypeError):
        base_year = today.year
    nodes = []
    for i, ph in enumerate(phases):
        state, pct = _macro_progress(ph, base_year, today)
        nodes.append(_phase_node(ph, i, state, pct))
    return html.Div(nodes, className="gc-phase-timeline")


def render_plan(plan):
    if not plan:
        return _empty("No plan yet — open ⚙ Plan settings above, set a goal, "
                      "and click Generate plan.")
    sched = schedule.build_schedule(plan)
    return dmc.Stack([
        dcc.Store(id="plan-dnd-store"),
        dcc.Store(id="plan-week-view", data={"idx": sched["current_index"], "dir": 0}),
        html.Div(html.Span(id="plan-save-status", className="plan-save-status"),
                 className="plan-save-row"),
        html.Div(render_boards(plan), id="plan-board"),
        section("Your week"),
        html.Div("Drag to reschedule · Done / Skip to log. Use ‹ › to step "
                 "through past and upcoming weeks.", className="plan-hint"),
        _week_nav(),
        section("The bigger picture"),
        _macro_timeline(plan, sched["today"]),
    ], gap="md")


def _settings_panel():
    kb_doc = kb.load_kb()
    kb_note = (f"Knowledge base v{kb_doc['version']} · {len(kb_doc['entries'])} cited topics"
               if kb_doc else "Knowledge base not built yet — run the research pass.")
    latest = plan_mod.load_latest() or {}
    pref_days = (plan_mod.load_prefs().get("preferred_days")
                 or latest.get("preferred_days") or [])
    day_picker = dmc.Stack([
        dmc.Text("Preferred running days", size="sm", fw=600),
        dmc.Text("Pick your usual days, then apply them to your current plan "
                 "(no need to regenerate). You can still drag any session to move "
                 "it for a specific week.", size="xs", c="dimmed"),
        dmc.ChipGroup(
            dmc.Group([dmc.Chip(d, value=d, size="sm") for d in _DAYS_SUN_FIRST],
                      gap="xs", mt=4),
            id="coach-days", value=pref_days, multiple=True),
        dmc.Group([
            dmc.Button("Apply to current plan", id="coach-days-apply",
                       variant="light", size="xs"),
            html.Span(id="coach-days-status", className="plan-save-status"),
        ], gap="sm", align="center"),
    ], gap=4)
    body = dmc.Stack([
        dmc.Group([
            dmc.TextInput(id="coach-goal", placeholder="e.g. sub-50 10k", w=260,
                          label="Race goal", value=latest.get("goal", "")),
            dmc.TextInput(id="coach-date", placeholder="YYYY-MM-DD", w=180,
                          label="Race date", value=latest.get("goal_date", "") or ""),
            dmc.Button("Generate plan", id="coach-plan-btn", mt=22),
            dmc.Button("Refresh coaching tips", id="coach-rec-btn",
                       variant="default", mt=22),
        ], gap="sm", align="end"),
        day_picker,
        dmc.Text(kb_note, size="xs", c="dimmed", className="mono"),
    ], gap="sm")
    return dmc.Accordion(
        chevronPosition="right", variant="separated", className="gc-recs",
        children=[dmc.AccordionItem([
            dmc.AccordionControl(dmc.Group([
                dmc.Text("⚙  Plan settings", fw=600, size="sm"),
                dmc.Text("set your goal · regenerate your plan or tips",
                         size="xs", c="dimmed"),
            ], gap="sm")),
            dmc.AccordionPanel(body, pt="sm"),
        ], value="settings")])


def layout():
    return dmc.Stack([
        _settings_panel(),
        dmc.Tabs([
            dmc.TabsList([
                dmc.TabsTab("My plan", value="plan"),
                dmc.TabsTab("Coaching tips", value="recs"),
            ]),
            dmc.TabsPanel(dcc.Loading(html.Div(render_plan(plan_mod.load_latest()),
                                               id="coach-plan")), value="plan", pt="md"),
            dmc.TabsPanel(dcc.Loading(html.Div(render_recs(rec_mod.load_latest()),
                                               id="coach-recs")), value="recs", pt="md"),
        ], value="plan"),
    ], gap="md")


@callback(Output("coach-recs", "children"), Input("coach-rec-btn", "n_clicks"),
          prevent_initial_call=True)
def _refresh_recs(_n):
    return render_recs(rec_mod.recommend())


@callback(Output("coach-plan", "children"), Input("coach-plan-btn", "n_clicks"),
          State("coach-goal", "value"), State("coach-date", "value"),
          State("coach-days", "value"), prevent_initial_call=True)
def _make_plan(_n, goal, date, days):
    if not goal:
        return _empty("Enter a goal first.")
    ordered = [d for d in _DAYS_SUN_FIRST if d in (days or [])]
    return render_plan(plan_mod.make_plan(goal, goal_date=date or None,
                                          preferred_days=ordered))


@callback(Output("coach-days-status", "children", allow_duplicate=True),
          Input("coach-days", "value"), prevent_initial_call=True)
def _save_days(days):
    ordered = [d for d in _DAYS_SUN_FIRST if d in (days or [])]
    plan_mod.save_prefs({**plan_mod.load_prefs(), "preferred_days": ordered})
    return "Saved — click Apply to update your plan" if ordered else "Cleared"


@callback(Output("plan-board", "children", allow_duplicate=True),
          Output("plan-week-body", "children", allow_duplicate=True),
          Output("coach-days-status", "children", allow_duplicate=True),
          Input("coach-days-apply", "n_clicks"),
          State("coach-days", "value"), State("plan-week-view", "data"),
          prevent_initial_call=True)
def _apply_days(_n, days, viewed):
    ordered = [d for d in _DAYS_SUN_FIRST if d in (days or [])]
    if not ordered:                       # fall back to the persisted selection
        ordered = plan_mod.load_prefs().get("preferred_days") or []
    plan = plan_mod.load_latest()
    if not plan or not ordered:
        return no_update, no_update, "Pick at least one day first."
    plan_mod.save_prefs({**plan_mod.load_prefs(), "preferred_days": ordered})
    plan = plan_mod.apply_preferred_days(plan, ordered)
    return (render_boards(plan), _render_week_body(plan, viewed, animate=False),
            "Applied to your plan ✓")


@callback(Output("plan-week-view", "data"),
          Input("plan-week-prev", "n_clicks"), Input("plan-week-next", "n_clicks"),
          State("plan-week-view", "data"), prevent_initial_call=True)
def _nav_week(_p, _n, data):
    """Step the viewed week back/forward, clamped to the weeks the plan covers.
    Records the direction so the board can slide in the matching way."""
    if not (ctx.triggered and ctx.triggered[0]["value"]):
        raise PreventUpdate
    plan = plan_mod.load_latest()
    if not plan:
        raise PreventUpdate
    sched = schedule.build_schedule(plan)
    idx, _ = _view(data)
    idx = sched["current_index"] if idx is None else idx
    direction = -1 if ctx.triggered_id == "plan-week-prev" else 1
    idx = max(0, min(len(sched["weeks"]) - 1, idx + direction))
    return {"idx": idx, "dir": direction}


@callback(Output("plan-week-body", "children"), Input("plan-week-view", "data"))
def _show_week(data):
    plan = plan_mod.load_latest()
    if not plan:
        raise PreventUpdate
    return _render_week_body(plan, data, animate=True)


@callback(Output("plan-board", "children"),
          Output("plan-week-body", "children", allow_duplicate=True),
          Output("plan-save-status", "children"),
          Input("plan-dnd-store", "data"),
          Input({"type": "plan-act", "key": ALL, "act": ALL}, "n_clicks"),
          State("plan-week-view", "data"), prevent_initial_call=True)
def _edit_plan(dnd, _clicks, viewed):
    """Apply a drag-reschedule or a Done/Skip toggle, persist, then re-render the
    progress summary and the currently-viewed week."""
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
        want = "skipped" if act == "skip" else "done"
        plan = plan_mod.load_latest() or {}
        cur = (plan.get("overrides", {}).get(key) or {}).get("status")
        plan = plan_mod.set_override(key, {"status": None if cur == want else want})
        status = "Updated ✓"
    else:
        raise PreventUpdate
    if plan is None:
        raise PreventUpdate
    return (render_boards(plan), _render_week_body(plan, viewed, animate=False),
            status)
