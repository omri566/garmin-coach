"""Settings drawer — a growing surface for athlete-controlled configuration.

Sections (each a collapsed accordion item):
  * Profile — height/weight/HR anchors etc., saved as manual overrides that win
    over Garmin's nightly re-fetch (`profile.save_overrides`).
  * Coach avatar — pick one of the bundled images under assets/avatars/
    (stored as prefs['avatar_preset']); it becomes the floating coach on-screen.
  * Plan settings — goal / race date / preferred days / generate plan (relocated
    from the old Coach tab; the component ids and their callbacks are unchanged).
"""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, ctx, html, no_update
from dash.exceptions import PreventUpdate

from garmin_coach import profile as prof
from garmin_coach.coach import plan as plan_mod
from garmin_coach.dashboard import data
from garmin_coach.dashboard.pages import coach
from garmin_coach.knowledge import kb

_DAYS_SUN_FIRST = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

# (field, label, suffix) for the numeric profile inputs.
_NUM_FIELDS = [
    ("age", "Age", "yr"), ("height_cm", "Height", "cm"),
    ("weight_kg", "Weight", "kg"), ("resting_hr", "Resting HR", "bpm"),
    ("hr_max", "Max HR", "bpm"), ("lthr", "Threshold HR", "bpm"),
    ("vo2max", "VO₂max", ""),
]


def _profile_values() -> dict:
    try:
        p = prof.load_profile()
    except FileNotFoundError:
        return {}
    return {f: getattr(p, f, None) for f in prof.EDITABLE_FIELDS}


def _profile_section():
    vals = _profile_values()
    inputs = [
        dmc.NumberInput(id={"type": "gc-prof", "field": f}, label=label,
                        value=vals.get(f), suffix=(f" {suf}" if suf else ""),
                        decimalScale=1, step=1, w=150, size="sm")
        for f, label, suf in _NUM_FIELDS
    ]
    inputs.insert(1, dmc.Select(
        id={"type": "gc-prof", "field": "sex"}, label="Sex",
        value=(vals.get("sex") or None), data=["MALE", "FEMALE"], w=150, size="sm"))
    return dmc.Stack([
        dmc.Text("Your physiological anchors — resting/max/threshold HR and VO₂max "
                 "included. Edits override Garmin and stick through the next sync; "
                 "leave a field blank to use Garmin's value.",
                 size="xs", c="dimmed"),
        dmc.Group(inputs, gap="sm"),
        dmc.Group([
            dmc.Button("Save profile", id="gc-profile-save", variant="light", size="xs"),
            html.Span(id="gc-profile-status", className="plan-save-status"),
        ], gap="sm", align="center"),
    ], gap="sm")


def _active_avatar_name(avail):
    """Which bundled avatar is currently selected (falls back to the default)."""
    chosen = plan_mod.load_prefs().get("avatar_preset")
    if chosen in avail:
        return chosen
    cur = data.coach_avatar()
    return cur.rsplit("/", 1)[-1] if cur else None


def _avatar_thumb(name, selected):
    return html.Button(
        html.Img(src=data.avatar_url(name), className="gc-avatar-thumb-img"),
        id={"type": "gc-avatar-pick", "name": name}, n_clicks=0,
        className="gc-avatar-thumb" + (" selected" if selected else ""))


def _avatar_gallery(avail, active):
    return html.Div([_avatar_thumb(n, n == active) for n in avail],
                    id="gc-avatar-gallery", className="gc-avatar-gallery")


def _avatar_section():
    avail = data.available_avatars()
    if not avail:
        return dmc.Text("No coach images bundled yet — drop pictures into "
                        "dashboard/assets/avatars/.", size="xs", c="dimmed")
    return dmc.Stack([
        dmc.Text("Pick your coach — tap an image.", size="xs", c="dimmed"),
        _avatar_gallery(avail, _active_avatar_name(avail)),
        html.Span(id="gc-avatar-status", className="plan-save-status"),
    ], gap="sm")


def _plan_settings_section():
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
    return dmc.Stack([
        dmc.Group([
            dmc.TextInput(id="coach-goal", placeholder="e.g. sub-50 10k", w=220,
                          label="Race goal", value=latest.get("goal", "")),
            dmc.TextInput(id="coach-date", placeholder="YYYY-MM-DD", w=160,
                          label="Race date", value=latest.get("goal_date", "") or ""),
            dmc.Button("Generate plan", id="coach-plan-btn", mt=22),
        ], gap="sm", align="end"),
        day_picker,
        dmc.Text(kb_note, size="xs", c="dimmed", className="mono"),
    ], gap="sm")


def _acc_item(value, title, subtitle, body):
    return dmc.AccordionItem([
        dmc.AccordionControl(dmc.Group([
            dmc.Text(title, fw=700, size="sm"),
            dmc.Text(subtitle, size="xs", c="dimmed"),
        ], gap="sm")),
        dmc.AccordionPanel(body, pt="sm"),
    ], value=value)


def drawer():
    """The Settings drawer, mounted once in the app shell. Sections start
    collapsed (no default open value)."""
    return dmc.Drawer(
        id="gc-settings-drawer", position="right", size="min(520px, 96vw)",
        zIndex=3000, padding="lg", title="Settings",
        children=dmc.Accordion(
            multiple=True, chevronPosition="right", variant="separated",
            children=[
                _acc_item("profile", "Profile",
                          "height · weight · resting/max/threshold HR · VO₂max",
                          _profile_section()),
                _acc_item("avatar", "Coach avatar", "pick your coach",
                          _avatar_section()),
                _acc_item("plan", "Plan settings", "goal · race date · days",
                          _plan_settings_section()),
            ]),
    )


# --- Profile save ----------------------------------------------------------
@callback(Output("gc-profile-status", "children"),
          Input("gc-profile-save", "n_clicks"),
          State({"type": "gc-prof", "field": ALL}, "value"),
          State({"type": "gc-prof", "field": ALL}, "id"),
          prevent_initial_call=True)
def _save_profile(_n, values, ids):
    overrides = {i["field"]: v for i, v in zip(ids, values)}
    prof.save_overrides(overrides)
    data.profile.cache_clear()          # so analytics re-read the edited values
    return "Saved ✓"


# --- Avatar pick -----------------------------------------------------------
@callback(Output("gc-avatar-gallery", "children"),
          Output("gc-coach-fab", "children"),
          Output("gc-avatar-status", "children"),
          Input({"type": "gc-avatar-pick", "name": ALL}, "n_clicks"),
          prevent_initial_call=True)
def _pick_avatar(_clicks):
    trig = ctx.triggered_id
    # Ignore the re-render that recreates the thumbs with n_clicks=0.
    if not (isinstance(trig, dict) and ctx.triggered and ctx.triggered[0]["value"]):
        raise PreventUpdate
    name = trig["name"]
    plan_mod.save_prefs({**plan_mod.load_prefs(), "avatar_preset": name})
    avail = data.available_avatars()
    return (_avatar_gallery(avail, name).children,
            fab_content(data.avatar_url(name)), "Saved ✓")


def fab_content(src):
    """The floating coach button's inner content — the avatar image or a default."""
    if src:
        return html.Img(src=src, className="gc-coach-fab-img")
    return html.Span("🧑‍🏫", className="gc-coach-fab-emoji")


# --- Plan settings (relocated from coach.py; ids/behaviour unchanged) -------
@callback(Output("coach-plan", "children"), Input("coach-plan-btn", "n_clicks"),
          State("coach-goal", "value"), State("coach-date", "value"),
          State("coach-days", "value"), prevent_initial_call=True)
def _make_plan(_n, goal, date, days):
    if not goal:
        return coach._empty("Enter a goal first.")
    ordered = [d for d in _DAYS_SUN_FIRST if d in (days or [])]
    return coach.render_plan(plan_mod.make_plan(goal, goal_date=date or None,
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
    if not ordered:
        ordered = plan_mod.load_prefs().get("preferred_days") or []
    plan = plan_mod.load_latest()
    if not plan or not ordered:
        return no_update, no_update, "Pick at least one day first."
    plan_mod.save_prefs({**plan_mod.load_prefs(), "preferred_days": ordered})
    plan = plan_mod.apply_preferred_days(plan, ordered)
    return (coach.render_boards(plan), coach._week_track(plan, coach._view_idx(viewed)),
            "Applied to your plan ✓")
