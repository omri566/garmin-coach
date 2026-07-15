"""Overview tab — headline fitness/fatigue/form, last run, key trends."""
from __future__ import annotations

import datetime as dt
import re

import dash_mantine_components as dmc
from dash import Input, Output, callback, dcc, html
from dash.exceptions import PreventUpdate

from garmin_coach.analytics import segments
from garmin_coach.coach import plan as plan_mod
from garmin_coach.coach import recommend as rec_mod
from garmin_coach.coach import schedule
from garmin_coach.dashboard import data, figures
from garmin_coach.dashboard.ui import (
    CARD, acwr_color, fig_id, fmt_pace, kpi, panel, range_tabs, section,
    section_with_control, tsb_color, with_info,
)

_TYPE_COLOR = {"easy": "teal", "long": "blue", "tempo": "orange",
               "threshold": "orange", "intervals": "red", "workout": "red",
               "race": "grape", "rest": "gray", "cross": "gray"}


def next_session():
    """The next workout still to do — skips rest and already-done/skipped sessions."""
    plan = plan_mod.load_latest()
    if not plan:
        return None
    sched = schedule.build_schedule(plan)
    today = sched["today"]
    best = None
    for wk in sched["weeks"]:
        for s in wk["sessions"]:
            if (s["type"] or "").lower() == "rest" or s["status"] in ("done", "skipped"):
                continue
            if s["date"] < today:        # don't surface a missed past session here
                continue
            if best is None or s["date"] < best["date"]:
                best = s
    if not best:
        return None
    when = "Today" if best["date"] == today else f"{best['date']:%a}"
    return {"type": best["type"], "description": best["description"],
            "target": best["target"], "when": when}


def _verdict(tsb, acwr, readiness):
    """Plain-language read of today's state, driven by Form (TSB)."""
    if tsb is None:
        return "—", figures.MUTED, "Not enough recent training to read your form."
    if tsb > 8:
        word, color = "Fresh", figures.GREEN
        read = "You're rested and peaked — a good window to race or hit a hard key session."
    elif tsb > -5:
        word, color = "Balanced", figures.BLUE
        read = "Form and fatigue are in balance. Hold the rhythm; train as planned."
    elif tsb > -15:
        word, color = "Building", figures.ORANGE
        read = "You're carrying productive fatigue from recent load. Keep easy days easy."
    else:
        word, color = "Fatigued", figures.RED
        read = "Heavy fatigue load. Back off and prioritise recovery before the next hard effort."
    if acwr is not None and acwr > 1.5:
        read += " Load is ramping fast — watch injury risk."
    elif readiness is not None and readiness < 40:
        read += " Recovery markers are low this morning."
    return word, color, read


def hero():
    st = data.current_state()
    h = data.latest_health()
    tsb = st.get("tsb")
    acwr = st.get("acwr")

    def hv(key):
        v = h.get(key)
        return v["value"] if v else None

    rdy, hrv = hv("readiness_score"), hv("hrv_overnight")
    rhr, sleep = hv("resting_hr"), hv("sleep_score")
    word, color, read = _verdict(tsb, acwr, rdy)

    # Zone 1 — today's form verdict.
    verdict = html.Div([
        html.Div("Today · Form", className="gc-verdict-eyebrow"),
        html.Div(f"{tsb:+.0f}" if tsb is not None else "—",
                 className="gc-verdict-num", style={"color": color}),
        html.Div(word, className="gc-verdict-word", style={"color": color}),
        html.Div(read, className="gc-verdict-read"),
    ], className="gc-hero-col")

    # Zone 2 — morning recovery markers (distinct from the metrics row below).
    def stat(label, val, unit="", c=figures.TEXT):
        shown = f"{val:.0f}" if isinstance(val, (int, float)) else "—"
        return html.Div([
            html.Div(label, className="gc-hero-k"),
            html.Div([shown, html.Span(unit, className="gc-hero-u")
                      if (unit and val is not None) else ""],
                     className="gc-hero-v", style={"color": c}),
        ], className="gc-hero-stat")

    recovery = html.Div([
        html.Div("Recovery", className="gc-hero-lab"),
        html.Div([
            stat("Readiness", rdy, "", figures.TEAL),
            stat("Sleep", sleep, "", figures.GREEN),
            stat("HRV", hrv, " ms"),
            stat("Resting HR", rhr, " bpm"),
        ], className="gc-hero-stats"),
    ], className="gc-hero-col gc-hero-side")

    # Zone 3 — next planned workout.
    ns = next_session()
    if ns:
        tgt = ns.get("target")
        next_body = [
            dmc.Group([
                dmc.Text(ns["when"], className="gc-readout", fw=700, size="sm"),
                dmc.Badge(ns["type"], variant="light", size="sm",
                          color=_TYPE_COLOR.get((ns["type"] or "").lower(), "gray")),
            ], gap="sm", align="center"),
            html.Div(ns.get("description", ""), className="gc-hero-next-desc"),
            html.Div(tgt, className="gc-hero-next-target")
            if tgt and tgt != "—" else None,
        ]
    else:
        next_body = [html.Div("No plan yet — set a goal in the Coach tab to get a "
                              "scheduled workout here.", className="gc-hero-next-desc")]
    nxt = html.Div([
        html.Div("Next session", className="gc-hero-lab"),
        *next_body,
    ], className="gc-hero-col gc-hero-side")

    return html.Div(html.Div([verdict, recovery, nxt], className="gc-hero-grid"),
                    className="gc-hero")


def recs_ticker():
    """A news-style scrolling bar of the coach's prioritised actions; click to
    open the Coach tab for the full write-up."""
    rec = rec_mod.load_latest()
    recs = (rec or {}).get("recommendations", [])
    if recs:
        items = [html.Span([
            html.Span(className=f"gc-ticker-dot {r.get('priority', 'low')}"),
            html.Span(r.get("title", ""), className="gc-ticker-ttl"),
        ], className="gc-ticker-item") for r in recs]
        # Scale the scroll duration to the content so the speed stays constant
        # (~70px/s, a readable broadcast crawl) no matter how many actions there are.
        approx_px = sum(len(r.get("title", "")) for r in recs) * 9 + len(recs) * 130
        dur = max(14, round(approx_px / 110))
    else:
        items = [html.Span("No recommendations yet — open Coach to generate guidance.",
                           className="gc-ticker-item")]
        dur = 24
    # Two identical groups side by side + a -50% slide = seamless loop.
    move = html.Div([html.Div(items, className="gc-ticker-group"),
                     html.Div(items, className="gc-ticker-group")],
                    className="gc-ticker-move", style={"--gc-ticker-dur": f"{dur}s"})
    return html.Div([
        html.Div([html.Span(className="live"), "Coach",
                  html.Span("›", className="arr")], className="gc-ticker-label"),
        html.Div(move, className="gc-ticker-track"),
    ], id="ticker-goto-coach", className="gc-ticker", n_clicks=0,
        title="Open the Coach tab for full recommendations")


@callback(Output("tab-switch", "value"), Input("ticker-goto-coach", "n_clicks"),
          prevent_initial_call=True)
def _ticker_to_coach(_n):
    return "coach"


def kpi_row():
    st = data.current_state()
    vo2 = data.latest_vo2max()
    cards = [
        kpi("Fitness · CTL", f"{st.get('ctl','—')}", "chronic load (42d)", figures.BLUE, "ctl"),
        kpi("Fatigue · ATL", f"{st.get('atl','—')}", "acute load (7d)", figures.ORANGE, "atl"),
        kpi("Form · TSB", f"{st.get('tsb','—')}", "fitness − fatigue",
            tsb_color(st.get("tsb")), "tsb"),
        kpi("ACWR", f"{st.get('acwr','—')}", "sweet spot 0.8–1.3",
            acwr_color(st.get("acwr")), "acwr"),
        kpi("VO₂max", f"{vo2 or '—'}", "ml/kg/min", figures.VIOLET, "vo2max"),
    ]
    return dmc.SimpleGrid(cards, cols={"base": 2, "sm": 3, "lg": 5}, spacing="md",
                          className="gc-metrics-grid")


def last_run_card():
    r = data.last_run()
    if not r:
        return dmc.Card(dmc.Text("No runs yet."), **CARD)

    def row(k, v, info_key=None, value_color=None):
        label = dmc.Group([
            dmc.Text(k, size="sm", c="dimmed"),
            dmc.Text("ⓘ", size="9px", c="dimmed") if info_key else None,
        ], gap=4, style={"cursor": "help"} if info_key else None)
        if info_key:
            label = with_info(label, info_key, position="left")
        value = dmc.Text(v, size="sm", fw=600,
                         **({"c": value_color} if value_color else {}))
        return dmc.Group([label, value], justify="space-between", w="100%")

    dyn = []
    if r.get("avg_vert_ratio"):
        dyn = [
            row("Cadence", f"{r['avg_cadence_spm']:.0f} spm", "cadence"),
            row("Vertical ratio", f"{r['avg_vert_ratio']:.1f} %", "vert_ratio"),
            row("Ground contact", f"{r['avg_gct_ms']:.0f} ms ({r['avg_gct_balance']:.1f}% L)", "gct"),
            row("Step length", f"{r['avg_step_len_mm']:.0f} mm", "step_len"),
        ]
    decoup = r.get("decoupling_pct")
    decoup_c = figures.RED if decoup and decoup > 5 else figures.GREEN
    return dmc.Card([
        dmc.Group([
            dmc.Text(r["name"], fw=700, size="lg"),
            dmc.Badge(r["start_time"][:10], variant="light"),
        ], justify="space-between"),
        dmc.Divider(my="sm"),
        row("Distance", f"{r['distance_m']/1000:.1f} km"),
        row("Pace", fmt_pace(r.get("avg_pace_s_km")), "pace"),
        row("Avg / Max HR", f"{r['avg_hr']:.0f} / {r['max_hr']:.0f} bpm"),
        row("Efficiency (EF)", f"{r['ef']:.2f}" if r.get("ef") else "—", "ef"),
        row("Decoupling", f"{decoup:.1f} %" if decoup is not None else "—",
            "decoupling", value_color=decoup_c),
        row("Training load", f"{r['training_stress']:.0f}" if r.get("training_stress") else "—", "load"),
        *([dmc.Divider(my="sm"), *dyn] if dyn else []),
    ], **CARD)


# --- last run vs plan -------------------------------------------------------
_CHIP_COLOR = {"ok": "green", "warn": "orange", "soft": "blue"}


def _parse_target(text):
    """Pull distance / pace-range / HR-cap out of a planned session's target."""
    out = {}
    if not text:
        return out
    m = re.search(r"(\d+(?:\.\d+)?)\s*km", text)
    if m:
        out["dist_km"] = float(m.group(1))
    m = re.search(r"(\d):(\d\d)\s*[–—-]\s*(\d):(\d\d)", text)
    if m:
        out["pace_lo"] = int(m.group(1)) * 60 + int(m.group(2))
        out["pace_hi"] = int(m.group(3)) * 60 + int(m.group(4))
    else:
        m = re.search(r"(\d):(\d\d)\s*/?\s*km", text)
        if m:
            v = int(m.group(1)) * 60 + int(m.group(2))
            out["pace_lo"], out["pace_hi"] = v - 10, v + 10
    m = re.search(r"HR\s*<\s*(\d+)", text)
    if m:
        out["hr_cap"] = int(m.group(1))
    return out


# Structured sessions are judged on their work segment, not the whole-run average.
_STRUCTURED = ("tempo", "interval", "threshold", "workout", "vo2", "cruise",
               "fartlek", "speed", "race")


def _is_structured(session_type: str) -> bool:
    t = (session_type or "").lower()
    return any(k in t for k in _STRUCTURED)


def _rep_seconds(text: str) -> int:
    """Work-window length parsed from the target ('2 × 5 min' → 300s); ~5 min if
    it can't be read."""
    m = re.search(r"(\d+)\s*min", text or "")
    return max(60, min(900, int(m.group(1)) * 60)) if m else 300


def _matched_session(r):
    """The planned session this run fulfilled, via the schedule auto-match."""
    plan = plan_mod.load_latest()
    if not plan or not r:
        return None
    for wk in schedule.build_schedule(plan)["weeks"]:
        for s in wk["sessions"]:
            m = s.get("match")
            if m and m.get("activity_id") == r.get("activity_id"):
                return s
    return None


def _verdict_reps(r, t, text):
    """Judge a structured session on its fastest sustained work segment (from the
    per-second streams) instead of the whole-run average, which a warm-up/cool-down
    drags below rep pace. Returns (checks, too_hard, too_easy)."""
    checks, too_hard, too_easy = [], False, False
    seg = (segments.best_sustained(data.run_streams(r["activity_id"]),
                                   _rep_seconds(text)) if r.get("activity_id") else None)
    if not (seg and seg.get("pace_s_km")):
        return [("Work reps", "no per-second data to check the reps", "soft")], False, False
    wp, mins = seg["pace_s_km"], seg["minutes"]
    tgt = (t["pace_lo"] + t["pace_hi"]) / 2
    if wp < t["pace_lo"] - 10:
        checks.append(("Work reps", f"fastest {mins} min {fmt_pace(wp)} — faster than "
                       f"the {fmt_pace(tgt)} target", "warn"))
        too_hard = True
    elif wp > t["pace_hi"] + 12:
        checks.append(("Work reps", f"fastest {mins} min {fmt_pace(wp)} — slower than "
                       f"the {fmt_pace(tgt)} target", "soft"))
        too_easy = True
    else:
        checks.append(("Work reps", f"fastest {mins} min {fmt_pace(wp)} — on the "
                       f"{fmt_pace(tgt)} target", "ok"))
    if seg.get("hr"):
        checks.append(("HR in the work", f"{seg['hr']:.0f} bpm", "ok"))
    return checks, too_hard, too_easy


def _run_verdict(r, session):
    """(headline, badge_tone, [(label, detail, chip_kind)…]) comparing run↔plan."""
    pace, hr = r.get("avg_pace_s_km"), r.get("avg_hr")
    dist = (r.get("distance_m") or 0) / 1000
    decoup = r.get("decoupling_pct")
    checks, too_hard, too_easy, structured = [], False, False, False

    if session:
        text = f"{session.get('target','')} {session.get('description','')}"
        t = _parse_target(text)
        structured = _is_structured(session.get("type"))

        if structured and "pace_lo" in t:
            checks, too_hard, too_easy = _verdict_reps(r, t, text)
        else:
            if pace and "pace_lo" in t:
                if pace < t["pace_lo"] - 8:
                    checks.append(("Pace", f"{fmt_pace(pace)} — faster than prescribed", "warn"))
                    too_hard = True
                elif pace > t["pace_hi"] + 12:
                    checks.append(("Pace", f"{fmt_pace(pace)} — slower than prescribed", "soft"))
                    too_easy = True
                else:
                    checks.append(("Pace", f"{fmt_pace(pace)} — in target range", "ok"))
            if hr and "hr_cap" in t:
                if hr <= t["hr_cap"] + 2:
                    checks.append(("Heart rate", f"{hr:.0f} — within Z2 cap (<{t['hr_cap']})", "ok"))
                else:
                    checks.append(("Heart rate", f"{hr:.0f} — above cap (<{t['hr_cap']})", "warn"))
                    too_hard = True
            if "dist_km" in t and dist:
                tol = max(0.5, 0.12 * t["dist_km"])
                tag = (f"{dist:.1f}/{t['dist_km']:.0f} km")
                if abs(dist - t["dist_km"]) <= tol:
                    checks.append(("Distance", f"{tag} — on target", "ok"))
                else:
                    checks.append(("Distance", f"{tag} — {'longer' if dist > t['dist_km'] else 'short'}", "soft"))

        ok_any = any(c[2] == "ok" for c in checks)
        if structured:
            head, tone = (("Ran the reps hard", "orange") if too_hard
                          else ("Reps under target", "blue") if too_easy and not ok_any
                          else ("Workout on target", "green") if ok_any
                          else ("Logged", "gray"))
        else:
            head, tone = (("Ran harder than prescribed", "orange") if too_hard
                          else ("Easier than planned", "blue") if too_easy and not ok_any
                          else ("On plan", "green") if ok_any
                          else ("Logged", "gray"))
    else:
        head, tone = "Extra session — not in plan", "grape"

    # Decoupling reads durability on steady runs; on intervals it's by design, skip.
    if decoup is not None and not structured:
        if decoup <= 5:
            checks.append(("Durability", f"{decoup:.1f}% decoupling — held pace", "ok"))
        else:
            checks.append(("Durability", f"{decoup:.1f}% decoupling — faded late", "warn"))
    return head, tone, checks


def _note_view(hit):
    """Headline + expandable detail (handles both the new {headline,detail} shape
    and any older cached {note})."""
    headline = hit.get("headline") or hit.get("note", "")
    detail = hit.get("detail") or (hit.get("note", "") if not hit.get("headline") else "")
    children = [dmc.Text(headline, size="sm", fw=600, style={"lineHeight": 1.4})]
    if detail and detail != headline:
        children.append(dmc.Spoiler(
            showLabel="more", hideLabel="less", maxHeight=0,
            children=dmc.Text(detail, size="sm", c="dimmed", mt=4,
                              style={"lineHeight": 1.5})))
    return html.Div(children)


def _ai_note_block(r, session):
    """For a structured session, the coach's execution note — a short headline
    (expandable) if cached, else a button to generate it (one LLM call, cached)."""
    if not (session and _is_structured(session.get("type"))):
        return None
    from garmin_coach.coach import execution
    hit = execution.cached(r.get("activity_id"))
    body = (_note_view(hit) if hit
            else dmc.Button("Coach's read of this workout →", id="last-run-ai-btn",
                            variant="light", size="xs"))
    return html.Div([
        dmc.Divider(my="sm"),
        dmc.Text("Coach's read", size="xs", c="dimmed", tt="uppercase", fw=600, mb=6),
        dcc.Loading(html.Div(body, id="last-run-ai-out"), type="dot", color="#FFB02E"),
    ])


@callback(Output("last-run-ai-out", "children"),
          Input("last-run-ai-btn", "n_clicks"), prevent_initial_call=True)
def _generate_ai_note(_n):
    from garmin_coach.coach import execution
    r = data.last_run()
    session = _matched_session(r)
    if not (r and session):
        raise PreventUpdate
    return _note_view(execution.make_note(session, r, data.run_streams(r["activity_id"])))


def last_run_section():
    r = data.last_run()
    if not r:
        return dmc.Card(dmc.Text("No runs yet."), **CARD)
    session = _matched_session(r)
    head, tone, checks = _run_verdict(r, session)

    if session:
        planned = dmc.Group([
            dmc.Badge(session["type"], variant="light", size="sm"),
            dmc.Text(session.get("target") or session.get("description", ""),
                     size="sm", c="dimmed"),
        ], gap="xs")
        if session.get("note"):
            planned = dmc.Stack([planned, dmc.Text(session["note"], size="xs",
                                                   c="dimmed", fs="italic")], gap=4)
    else:
        planned = dmc.Text("No matching planned session — counts as an extra run.",
                           size="sm", c="dimmed")

    verdict = dmc.Card([
        dmc.Group([dmc.Text("Versus plan", fw=600, size="sm"),
                   dmc.Badge(head, color=tone, variant="filled", size="sm")],
                  justify="space-between"),
        dmc.Text("Planned", size="xs", c="dimmed", tt="uppercase", fw=600, mt=8),
        planned,
        dmc.Divider(my="sm"),
        dmc.Stack([dmc.Group([
            dmc.Text(label, size="sm", c="dimmed"),
            dmc.Badge(detail, color=_CHIP_COLOR.get(kind, "gray"),
                      variant="light", size="sm"),
        ], justify="space-between", wrap="nowrap") for label, detail, kind in checks],
            gap=8),
        _ai_note_block(r, session),
    ], **CARD)

    return dmc.Grid([
        dmc.GridCol(last_run_card(), span={"base": 12, "md": 5}),
        dmc.GridCol(verdict, span={"base": 12, "md": 7}),
    ], gutter="md")


# --- load & fatigue with a stock-style range selector -----------------------
_RANGE_DAYS = {"3m": 90, "1y": 365, "5y": 365 * 5}


def load_fatigue_series(rng: str = "1y"):
    """Daily fitness/fatigue/form/ACWR for the chosen window, averaged to weekly
    points so the lines read as smooth trends rather than day-to-day noise."""
    days = _RANGE_DAYS.get(rng, 365)
    start = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    df = data.load_series(start=start)
    if df.empty:
        return df
    return df.resample("W").mean(numeric_only=True)


@callback(Output(fig_id("ov-ff"), "figure"), Output(fig_id("ov-acwr"), "figure"),
          Input("ov-range", "value"), prevent_initial_call=True)
def _update_load_fatigue(rng):
    # layout() already renders these at the default "1y"; only rebuild on a range
    # change, so the landing tab doesn't compute the same figures twice on load.
    ldf = load_fatigue_series(rng)
    return figures.fitness_form(ldf), figures.acwr(ldf)


def recovery_fig(rng="1y"):
    """Overnight HRV — the headline recovery signal — over the chosen window,
    with a last-14-day average baseline."""
    rec = data.slice_since(data.recovery_trend(), rng, col="day")
    return figures.daily_metric(rec, "hrv_overnight", "HRV", figures.VIOLET,
                                height=300)


@callback(Output(fig_id("ov-recovery"), "figure"), Input("ov-rec-range", "value"),
          prevent_initial_call=True)
def _update_recovery(rng):
    return recovery_fig(rng)   # layout() already renders the default "1y"


def layout():
    ldf = load_fatigue_series("1y")
    return dmc.Stack([
        hero(),
        recs_ticker(),
        section("Key metrics"),
        kpi_row(),
        section("Last run"),
        last_run_section(),
        section_with_control("Load & fatigue", range_tabs("ov-range")),
        dmc.Grid([
            dmc.GridCol(panel("Fitness · Fatigue · Form", figures.fitness_form(ldf),
                              "chart_fitness_form", key="ov-ff"),
                        span={"base": 12, "md": 8}),
            dmc.GridCol(panel("Training-load ratio (ACWR)", figures.acwr(ldf),
                              "chart_acwr", key="ov-acwr"),
                        span={"base": 12, "md": 4}),
        ], gutter="md"),
        section_with_control("Recovery", range_tabs("ov-rec-range")),
        panel("HRV (overnight)", recovery_fig("1y"), key="ov-recovery"),
    ], gap="md")
