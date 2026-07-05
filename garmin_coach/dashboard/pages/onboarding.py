"""First-run landing page: connect Garmin + Claude, then sync and enter the app.

Shown only until `setup.state.is_configured()` is true (both a cached Garmin token
and a connected Claude account); after that every launch goes straight to the
dashboard. The AI runs on the athlete's own Claude subscription via `claude auth`.
"""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, no_update
from dash.exceptions import PreventUpdate

from garmin_coach.setup import claude_auth, garmin_auth, state

_SHOW: dict = {}
_HIDE = {"display": "none"}


def _msg(text: str, kind: str = "info"):
    color = {"ok": "#46D08A", "err": "#F2555A", "warn": "#FFB02E",
             "info": "#93A1B1"}.get(kind, "#93A1B1")
    return dmc.Text(text, size="sm", style={"color": color})


def _tick(done: bool):
    return dmc.Badge("✓ connected" if done else "not yet",
                     color="teal" if done else "gray", variant="light", size="sm")


def _step(n: int, title: str, subtitle: str, check_id: str, body):
    return dmc.Card(className="gc-card", radius="md", p="lg", children=dmc.Stack([
        dmc.Group([
            dmc.Group([
                dmc.Badge(str(n), variant="filled", color="amp", size="lg", circle=True),
                dmc.Stack([dmc.Text(title, fw=700),
                           dmc.Text(subtitle, size="xs", c="dimmed")], gap=0),
            ], gap="sm"),
            html.Span(_tick(False), id=check_id),
        ], justify="space-between", align="center", wrap="nowrap"),
        body,
    ], gap="md"))


def layout():
    return html.Div(
        style={"maxWidth": "620px", "margin": "0 auto", "padding": "48px 20px 80px"},
        children=[
            dcc.Location(id="onb-location", refresh=True),
            dcc.Interval(id="onb-poll", interval=2500),
            html.Div(style={"marginBottom": "28px"}, children=[
                dmc.Text("GARMIN COACH", className="gc-wordmark",
                         style={"fontSize": "1.4rem"}),
                dmc.Text("Let's get you set up — two quick connections and you're in.",
                         c="dimmed", size="sm", mt=6),
            ]),

            # --- Step 1: Garmin -------------------------------------------------
            _step(1, "Connect Garmin", "So we can read your activities & recovery.",
                  "onb-garmin-check", dmc.Stack([
                      dmc.TextInput(id="onb-garmin-email", label="Garmin email",
                                    placeholder="you@example.com"),
                      dmc.PasswordInput(id="onb-garmin-pass", label="Garmin password"),
                      dmc.Group([
                          dmc.Button("Connect Garmin", id="onb-garmin-btn"),
                          html.Span(id="onb-garmin-status"),
                      ], gap="sm", align="center"),
                      html.Div(id="onb-garmin-mfa-wrap", style=_HIDE, children=dmc.Group([
                          dmc.TextInput(id="onb-garmin-mfa", label="MFA code",
                                        placeholder="6-digit code", w=160),
                          dmc.Button("Verify code", id="onb-garmin-mfa-btn",
                                     variant="light", mt=22),
                      ], gap="sm", align="end")),
                      dmc.Text("We use your login once to get a token, then never "
                               "store your password.", size="xs", c="dimmed"),
                  ], gap="sm")),

            html.Div(style={"height": "16px"}),

            # --- Step 2: Claude -------------------------------------------------
            _step(2, "Connect Claude", "Your Claude subscription powers the coaching.",
                  "onb-claude-check", dmc.Stack([
                      dmc.Group([
                          dmc.Button("Connect Claude", id="onb-claude-btn"),
                          dmc.Button("Install Claude Code", id="onb-claude-install",
                                     variant="default"),
                          html.Span(id="onb-claude-status"),
                      ], gap="sm", align="center"),
                      dmc.Text(id="onb-claude-account", size="xs", c="dimmed"),
                      dmc.Text("A Terminal window opens — sign in with your Claude "
                               "account, then come back here.", size="xs", c="dimmed"),
                  ], gap="sm")),

            html.Div(style={"height": "24px"}),

            # --- Finish ---------------------------------------------------------
            dmc.Button("Finish & open dashboard", id="onb-finish",
                       size="md", fullWidth=True, disabled=True),
            dcc.Loading(  # spins only while the first sync runs
                html.Div(id="onb-finish-status",
                         style={"marginTop": "10px", "textAlign": "center",
                                "minHeight": "20px"}),
                type="dot", color="#FFB02E"),
        ])


# --- callbacks --------------------------------------------------------------
@callback(Output("onb-garmin-status", "children"),
          Output("onb-garmin-mfa-wrap", "style"),
          Input("onb-garmin-btn", "n_clicks"),
          State("onb-garmin-email", "value"), State("onb-garmin-pass", "value"),
          prevent_initial_call=True)
def _garmin_connect(_n, email, pw):
    if not email or not pw:
        return _msg("Enter your Garmin email and password.", "warn"), _HIDE
    st = garmin_auth.start_login(email, pw)
    if st == "mfa_required":
        return _msg("Garmin sent you a code — enter it below.", "info"), _SHOW
    if st == "connected":
        return _msg("Connected ✓", "ok"), _HIDE
    return _msg(garmin_auth.poll()["error"] or "Login failed.", "err"), _HIDE


@callback(Output("onb-garmin-status", "children", allow_duplicate=True),
          Output("onb-garmin-mfa-wrap", "style", allow_duplicate=True),
          Input("onb-garmin-mfa-btn", "n_clicks"),
          State("onb-garmin-mfa", "value"), prevent_initial_call=True)
def _garmin_mfa(_n, code):
    st = garmin_auth.submit_mfa(code or "")
    if st == "connected":
        return _msg("Connected ✓", "ok"), _HIDE
    return _msg(garmin_auth.poll()["error"] or "That code didn't work — try again.",
                "err"), _SHOW


@callback(Output("onb-claude-status", "children"),
          Input("onb-claude-install", "n_clicks"), prevent_initial_call=True)
def _claude_install(_n):
    ok, msg = claude_auth.install()
    return _msg(msg, "ok" if ok else "err")


@callback(Output("onb-claude-status", "children", allow_duplicate=True),
          Input("onb-claude-btn", "n_clicks"), prevent_initial_call=True)
def _claude_connect(_n):
    if not claude_auth.is_installed():
        return _msg("Click ‘Install Claude Code’ first.", "warn")
    ok, msg = claude_auth.start_login()
    return _msg(msg, "info" if ok else "err")


@callback(Output("onb-garmin-check", "children"),
          Output("onb-claude-check", "children"),
          Output("onb-claude-account", "children"),
          Output("onb-finish", "disabled"),
          Input("onb-poll", "n_intervals"))
def _poll(_n):
    g = state.garmin_connected()
    c = claude_auth.is_connected()
    acct = claude_auth.account_label()
    return _tick(g), _tick(c), (f"Linked: {acct}" if acct else ""), not (g and c)


@callback(Output("onb-location", "href"), Output("onb-finish-status", "children"),
          Input("onb-finish", "n_clicks"), prevent_initial_call=True)
def _finish(_n):
    if not state.is_configured():
        raise PreventUpdate
    try:
        from garmin_coach import pipeline
        pipeline.update(examine=100, health_days=60, refresh_profile=True,
                        refresh_recommendations=False)
    except Exception as exc:  # noqa: BLE001 — land them in the app regardless.
        return "/", _msg(f"You're set up. First sync hit a snag ({exc}); "
                         "use ‘Sync now’ in the app.", "warn")
    return "/", _msg("All set — opening your dashboard…", "ok")
