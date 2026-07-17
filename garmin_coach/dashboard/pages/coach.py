"""Training Plan tab — the goal-driven plan and its execution (you-in-the-loop).

Shows the active plan: a progress hero, today's/next session, milestones, the
week board (drag to reschedule, Done/Skip to log), and the macro timeline. Plan
settings (goal / race date / preferred days / generate) live in the Settings
drawer (`pages/settings.py`); coaching tips live in the floating coach popup
(`pages/tips.py`). Those modules reuse `render_plan`/`render_boards`/`_week_track`
from here, so keep them importable.
"""
from __future__ import annotations

import datetime as dt
import re

import dash_mantine_components as dmc
from dash import (
    ALL,
    ClientsideFunction,
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    ctx,
    dcc,
    html,
    no_update,
)
from dash.exceptions import PreventUpdate

from garmin_coach.coach import plan as plan_mod
from garmin_coach.coach import schedule
from garmin_coach.dashboard import data, figures
from garmin_coach.dashboard.ui import CARD, fmt_pace, section


def _empty(msg):
    return dmc.Card(dmc.Text(msg, c="dimmed"), **CARD)


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
    cls = "plan-board-week" + (f" {anim}" if anim else "")
    return html.Div([head, grid], className=cls)


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


def _view_idx(data):
    """The viewed week index from the plan-week-view store (dict or int)."""
    return data.get("idx") if isinstance(data, dict) else data


def _week_track(plan, idx):
    """All weeks rendered side-by-side as slides; the client-side arrows slide the
    track (a CSS transform) with no server round-trip, and JS sizes the viewport
    to the active week — a smooth transition with no flash / empty space."""
    sched = schedule.build_schedule(plan)
    cur = sched["current_index"]
    weeks = sched["weeks"]
    idx = cur if idx is None else max(0, min(len(weeks) - 1, idx))
    slides = []
    for wk in weeks:
        tag, color = _week_tag(wk, cur)
        slides.append(html.Div(_board(wk, tag=tag, tag_color=color),
                               className="plan-week-slide"))
    return html.Div(slides, id="plan-week-track", className="plan-week-track",
                    style={"transform": f"translateX(-{idx * 100}%)"})


def _week_nav(plan):
    """Prev/next arrows around the sliding week carousel (rendered once)."""
    sched = schedule.build_schedule(plan)
    return html.Div([
        html.Button("‹", id="plan-week-prev", n_clicks=0,
                    className="plan-nav-arrow", **{"aria-label": "Previous week"}),
        html.Div(_week_track(plan, sched["current_index"]),
                 id="plan-week-body", className="plan-week-port"),
        html.Button("›", id="plan-week-next", n_clicks=0,
                    className="plan-nav-arrow", **{"aria-label": "Next week"}),
    ], className="plan-week-nav")


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


def _total_plan_weeks(plan):
    """Highest week number across the macro phases (the full plan length), e.g.
    'weeks 13-15' / 'weeks 16' → 16. 0 if the macro can't be parsed."""
    total = 0
    for ph in plan.get("macro", []):
        nums = re.findall(r"\d+", ph.get("weeks", "").split("(")[0])
        if nums:
            total = max(total, int(nums[-1]))
    return total


def _progress_hero(plan, sched, streak):
    weeks, cur, today = sched["weeks"], sched["current_index"], sched["today"]
    # "Plan complete" spans the whole macro plan (e.g. 16 weeks), not just the few
    # detailed next_month weeks — measured by weeks elapsed since the plan began.
    total_weeks = _total_plan_weeks(plan) or len(weeks)
    plan_start = weeks[0]["start"] if weeks else today
    weeks_done = max(0, min(total_weeks, (today - plan_start).days // 7))
    pct = round(100 * weeks_done / total_weeks) if total_weeks else 0
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
        chips.append(html.Div(["🔥 ", html.B(f"{streak}"), "-week streak"],
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
    # Streak reflects consistency within this plan (weeks before it started don't
    # count), so it lines up with plan progress instead of lifetime running.
    plan_start = sched["weeks"][0]["start"] if sched["weeks"] else None
    streak = data.running_streak_weeks(sched["today"], since=plan_start)
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


def _phase_building_view(status):
    """Shown the moment a phase finishes: a congrats card + a one-shot Interval
    that fires the auto-advance callback to generate the next block."""
    cur = (status["current_phase"] or {}).get("phase", "this phase")
    nxt = (status["next_phase"] or {}).get("phase", "the next phase")
    return dmc.Stack([
        dcc.Interval(id="gc-phase-advance", interval=350, max_intervals=1),
        dcc.Loading(dmc.Card([
            dmc.Text(f"🎉 You finished the {cur} phase!", fw=800, size="lg"),
            dmc.Text(f"Building your {nxt} plan — this takes a few seconds…",
                     c="dimmed", size="sm", mt=6),
        ], className="gc-card", radius="md", p="xl"), type="dot", color=figures.AMP),
    ], gap="md")


def _phase_error_view(msg):
    return dmc.Card([
        dmc.Text("Couldn't build your next phase", fw=700, size="md"),
        dmc.Text(msg[:300], c="dimmed", size="sm", mt=6,
                 style={"whiteSpace": "pre-wrap"}),
        dmc.Button("Try again", id="gc-phase-retry", variant="light", mt="md"),
    ], className="gc-card", radius="md", p="lg")


def _plan_complete_view(plan):
    return dmc.Card([
        dmc.Text("🏁 Plan complete — great work!", fw=800, size="lg"),
        dmc.Text(f"You've finished every phase of “{plan.get('goal', 'your plan')}”. "
                 "Set a new goal in ⚙ Settings when you're ready for what's next.",
                 c="dimmed", size="sm", mt=8),
    ], className="gc-card", radius="md", p="xl")


def render_plan(plan):
    if not plan:
        return _empty("No plan yet — open ⚙ Settings, set a goal under Plan "
                      "settings, and click Generate plan.")
    status = plan_mod.phase_status(plan)
    if status["block_finished"] and status["next_phase"]:
        return _phase_building_view(status)      # auto-advance to the next phase
    if status["is_last"]:
        return _plan_complete_view(plan)
    sched = schedule.build_schedule(plan)
    return dmc.Stack([
        dcc.Store(id="plan-dnd-store"),
        dcc.Store(id="plan-week-view",
                  data={"idx": sched["current_index"],
                        "n": len(sched["weeks"]), "np": 0, "nn": 0}),
        dcc.Store(id="plan-anim-dummy"),
        html.Div(html.Span(id="plan-save-status", className="plan-save-status"),
                 className="plan-save-row"),
        html.Div(render_boards(plan), id="plan-board"),
        section("Your week"),
        html.Div("Drag to reschedule · Done / Skip to log. Use ‹ › to step "
                 "through past and upcoming weeks.", className="plan-hint"),
        _week_nav(plan),
        section("The bigger picture"),
        _macro_timeline(plan, sched["today"]),
    ], gap="md")


def layout():
    return dcc.Loading(
        html.Div(render_plan(plan_mod.load_latest()), id="coach-plan"),
        delay_show=400)


# Arrow nav is entirely client-side: slide the pre-rendered carousel (transform)
# and size the viewport to the active week — no server round-trip, so it's smooth.
# (Functions live in assets/plan_carousel.js under the gcplan namespace.)
clientside_callback(
    ClientsideFunction(namespace="gcplan", function_name="nav"),
    Output("plan-week-view", "data"),
    Input("plan-week-prev", "n_clicks"), Input("plan-week-next", "n_clicks"),
    State("plan-week-view", "data"), prevent_initial_call=True)

# Re-apply position + height after the track is (re-)rendered: initial load and
# after an edit re-renders the carousel.
clientside_callback(
    ClientsideFunction(namespace="gcplan", function_name="reapply"),
    Output("plan-anim-dummy", "data"),
    Input("plan-week-body", "children"),
    State("plan-week-view", "data"))

# The carousel lives on the Training Plan tab, which is display:none until
# selected — so the viewport height can't be measured until then. Re-apply once
# the tab's own style flips to visible (this fires after the show).
clientside_callback(
    ClientsideFunction(namespace="gcplan", function_name="onTab"),
    Output("plan-anim-dummy", "data", allow_duplicate=True),
    Input("tab-coach", "style"),
    State("plan-week-view", "data"), prevent_initial_call=True)


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
    return render_boards(plan), _week_track(plan, _view_idx(viewed)), status


def congrats_content(plan):
    """Body of the phase-complete congrats modal (built from the advanced plan)."""
    deb = plan.get("phase_debrief") or {}
    macro = plan.get("macro") or []
    idx = plan.get("phase_index", 0)
    moved_into = macro[idx].get("phase") if 0 <= idx < len(macro) else "your next phase"
    finished = deb.get("finished_phase") or "your phase"
    improve = deb.get("improve") or []
    body = [
        dmc.Text(f"🎉 You finished the {finished} phase!", fw=800, size="lg"),
        dmc.Text(deb.get("headline", ""), c="dimmed", size="sm", mt=6),
    ]
    if improve:
        body.append(dmc.Stack(
            [dmc.Text(f"To get the most from {moved_into}:", fw=600, size="sm", mt=10),
             *[dmc.Text("• " + s, size="sm", c="dimmed") for s in improve]], gap=4))
    body.append(dmc.Button(f"See your {moved_into} plan →", id="gc-congrats-ok", mt="lg"))
    return dmc.Stack(body, gap=6)


def _advance_or_error():
    """Run advance_phase once and return (plan-view, overlay_class, congrats_body).
    Guards against re-firing: if the phase index didn't move, the advance didn't
    happen (LLM error / no next phase) — show a retryable error, don't loop."""
    try:
        before = (plan_mod.load_latest() or {}).get("phase_index", 0)
        plan = plan_mod.advance_phase()
    except Exception as e:  # noqa: BLE001 — surface the reason, don't crash the tab
        return _phase_error_view(f"{type(e).__name__}: {e}"), no_update, no_update
    if not plan or plan.get("phase_index", 0) == before:
        return _phase_error_view("The coach didn't return a valid next block."), \
            no_update, no_update
    return render_plan(plan), "gc-congrats-overlay open", congrats_content(plan)


@callback(Output("coach-plan", "children", allow_duplicate=True),
          Output("gc-congrats", "className", allow_duplicate=True),
          Output("gc-congrats-body", "children", allow_duplicate=True),
          Input("gc-phase-advance", "n_intervals"), prevent_initial_call=True)
def _do_advance(_n):
    """Fires once when the 'building…' view mounts (a finished phase was detected)."""
    return _advance_or_error()


@callback(Output("coach-plan", "children", allow_duplicate=True),
          Output("gc-congrats", "className", allow_duplicate=True),
          Output("gc-congrats-body", "children", allow_duplicate=True),
          Input("gc-phase-retry", "n_clicks"), prevent_initial_call=True)
def _retry_advance(_n):
    return _advance_or_error()
