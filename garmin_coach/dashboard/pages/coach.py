"""Coach tab — science-backed recommendations + goal-driven plan (you-in-the-loop).

Displays the latest saved recommendation/plan, and lets the athlete regenerate
them on demand (each runs the LLM over current data — a slow call, wrapped in a
loading spinner).
"""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html

from garmin_coach.coach import plan as plan_mod
from garmin_coach.coach import recommend as rec_mod
from garmin_coach.dashboard.ui import CARD
from garmin_coach.knowledge import kb

PRIORITY_COLOR = {"high": "red", "medium": "orange", "low": "gray"}


def _empty(msg):
    return dmc.Card(dmc.Text(msg, c="dimmed"), **CARD)


def render_recs(rec):
    if not rec:
        return _empty("No recommendations yet — click “Refresh recommendations”.")
    cards = []
    for r in rec.get("recommendations", []):
        cards.append(dmc.Card([
            dmc.Group([
                dmc.Text(r["title"], fw=700),
                dmc.Group([
                    dmc.Badge(r["priority"], color=PRIORITY_COLOR.get(r["priority"], "gray"),
                              variant="filled", size="sm"),
                    dmc.Badge(r["horizon"].replace("_", " "), variant="light", size="sm"),
                ], gap=6),
            ], justify="space-between"),
            dmc.Text(f"→ {r['action']}", fw=600, mt=6),
            dmc.Text(r["rationale"], size="sm", c="dimmed", mt=4),
            *([dmc.Text("Sources: " + "; ".join(r["citations"]), size="xs",
                        c="dimmed", mt=4, fs="italic")] if r.get("citations") else []),
        ], **CARD))
    flags = rec.get("flags", [])
    head = [
        dmc.Group([
            dmc.Text("Assessment", fw=700, size="lg"),
            dmc.Text(f"generated {rec.get('generated_at','')[:16]} · KB v{rec.get('kb_version','?')}",
                     size="xs", c="dimmed"),
        ], justify="space-between"),
        dmc.Text(rec.get("assessment", ""), size="sm", mt=4),
    ]
    if flags:
        head.append(dmc.Alert(
            dmc.Stack([dmc.Text(f"⚠ {f}", size="sm") for f in flags], gap=4),
            title="Flags", color="orange", variant="light", mt="sm"))
    return dmc.Stack([dmc.Card(head, **CARD), *cards], gap="md")


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

    weeks = []
    for wk in plan.get("next_month", []):
        rows = [html.Tr([
            html.Td(s["day"]),
            html.Td(dmc.Badge(s["type"], variant="light", size="sm")),
            html.Td(s["description"]),
            html.Td(dmc.Text(s.get("target", ""), size="xs", c="dimmed")),
        ]) for s in wk.get("sessions", [])]
        weeks.append(dmc.Card([
            dmc.Group([dmc.Text(wk["week"], fw=700),
                       dmc.Text(wk["theme"], c="dimmed", size="sm")]),
            dmc.Table([html.Thead(html.Tr([html.Th(h) for h in
                       ["Day", "Type", "Session", "Target"]])),
                       html.Tbody(rows)], striped=True),
        ], **CARD))

    return dmc.Stack([
        dmc.Card([
            dmc.Group([dmc.Text(f"Plan · {plan.get('goal','')}", fw=700, size="lg"),
                       dmc.Text(f"target {plan.get('goal_date','') or '—'} · "
                                f"generated {plan.get('generated_at','')[:16]}",
                                size="xs", c="dimmed")], justify="space-between"),
            dmc.Text(plan.get("assessment", ""), size="sm", mt=4),
        ], **CARD),
        dmc.Text("3-month macro", fw=600, mt="sm"),
        dmc.SimpleGrid(macro, cols={"base": 1, "sm": 2, "lg": 3}, spacing="md"),
        dmc.Text("Next month", fw=600, mt="sm"),
        *weeks,
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
        dmc.Group([
            dmc.TextInput(id="coach-goal", placeholder="Goal e.g. sub-50 10k",
                          w=260, value=(plan_mod.load_latest() or {}).get("goal", "")),
            dmc.TextInput(id="coach-date", placeholder="Race date YYYY-MM-DD", w=180,
                          value=(plan_mod.load_latest() or {}).get("goal_date", "") or ""),
            dmc.Button("Generate plan", id="coach-plan-btn", color="blue"),
            dmc.Button("Refresh recommendations", id="coach-rec-btn", variant="light"),
        ], gap="sm"),
        dmc.Text(kb_note, size="xs", c="dimmed"),
        dmc.Tabs([
            dmc.TabsList([
                dmc.TabsTab("Recommendations", value="recs"),
                dmc.TabsTab("Plan", value="plan"),
            ]),
            dmc.TabsPanel(dcc.Loading(html.Div(render_recs(rec_mod.load_latest()),
                                               id="coach-recs")), value="recs", pt="md"),
            dmc.TabsPanel(dcc.Loading(html.Div(render_plan(plan_mod.load_latest()),
                                               id="coach-plan")), value="plan", pt="md"),
        ], value="recs", color="blue"),
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
