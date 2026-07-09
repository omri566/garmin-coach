"""Garmin Coach dashboard — single-page app with show/hide tab sections.

Both tab sections are always mounted in the DOM (toggled via CSS), so every
callback's component IDs always exist — this avoids the "ID not found in layout"
errors that Mantine Tabs cause by unmounting inactive panels.

Run:  .venv/bin/python -m garmin_coach.dashboard.app   then open http://127.0.0.1:8050
"""
from __future__ import annotations

import copy
import datetime as dt

import dash
import dash_mantine_components as dmc
from dash import (ALL, Input, Output, State, _dash_renderer, callback, ctx, dcc,
                  html)
from dash.exceptions import PreventUpdate

from garmin_coach import config
from garmin_coach.dashboard import figures, ui
from garmin_coach.dashboard.pages import analysis, coach, onboarding, overview
from garmin_coach.setup import state as setup_state
from garmin_coach.store import db

# Guarantee the data dir + an initialised schema exist before any layout queries,
# so a brand-new user (or one whose first sync failed) gets an empty dashboard
# instead of a "no such table" crash / "Error loading layout".
config.ensure_dirs()
db.init_db()

_dash_renderer._set_react_version("18.2.0")

app = dash.Dash(__name__, external_stylesheets=dmc.styles.ALL,
                title="Garmin Coach", suppress_callback_exceptions=True)
server = app.server

# Set the page background before the React app mounts so there's no flash.
app.index_string = """<!DOCTYPE html>
<html>
<head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>html,body{margin:0;background:#0E1217;}</style></head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body>
</html>"""

# Amber accent ramp (Mantine wants 10 shades, light → dark).
_AMBER = ["#FFF6E5", "#FFE9BF", "#FFD98A", "#FFC957", "#FFBC38",
          "#FFB02E", "#E89A1E", "#C47E15", "#9C630F", "#73480A"]

THEME = {
    "fontFamily": "Archivo, system-ui, sans-serif",
    "fontFamilyMonospace": "JetBrains Mono, ui-monospace, monospace",
    "headings": {"fontFamily": "Archivo, system-ui, sans-serif",
                 "fontWeight": "700"},
    "defaultRadius": "md",
    "primaryColor": "amp",
    "primaryShade": 5,
    "colors": {"amp": _AMBER},
}

_SHOW: dict = {}
_HIDE = {"display": "none"}


def _shell_inner():
    return html.Div(
            style={"backgroundColor": figures.BG, "minHeight": "100vh",
                   "paddingBottom": "3rem"},
            children=html.Div(className="gc-shell", children=[
                html.Header(className="gc-mast", children=[
                    html.Div([
                        html.Span("●", className="spark",
                                  style={"marginRight": "8px", "fontSize": "0.7em"}),
                        "Garmin Coach",
                    ], className="gc-wordmark"),
                    html.Div("endurance telemetry", className="gc-tagline"),
                ]),
                html.Div(className="gc-nav", children=[
                    dmc.SegmentedControl(
                        id="tab-switch", value="overview",
                        data=[{"label": "Overview", "value": "overview"},
                              {"label": "Deep Analysis", "value": "analysis"},
                              {"label": "Coach", "value": "coach"}],
                    ),
                    html.Div(className="gc-sync-cluster", children=[
                        dcc.Loading(
                            html.Span(id="sync-status", className="gc-sync-status"),
                            type="dot", color=figures.AMP),
                        dmc.Button("↻ Sync now", id="sync-btn",
                                   variant="default", size="sm"),
                    ]),
                ]),
                html.Div(overview.layout(), id="tab-overview"),
                html.Div(analysis.layout(), id="tab-analysis", style=_HIDE),
                html.Div(coach.layout(), id="tab-coach", style=_HIDE),
                _chart_modal(),
            ]),
        )


def _error_panel(tb: str):
    return html.Div(style={"maxWidth": "620px", "margin": "60px auto",
                           "padding": "0 20px", "color": "#E8EDF3"}, children=[
        dmc.Text("Something went wrong loading your dashboard", fw=700, size="lg"),
        dmc.Text("Your data is safe. Try ‘↻ Sync now’ after reopening, or reopen "
                 "the app. If it keeps happening, send this file to support:",
                 c="dimmed", size="sm", mt=8),
        dmc.Code(str(config.DATA_DIR / "last_error.log"), mt=8),
        dmc.Text(tb[-600:], size="xs", c="dimmed", mt=12,
                 style={"whiteSpace": "pre-wrap", "fontFamily": "monospace"}),
    ])


def layout():
    """Onboarding on first run (until Garmin + Claude are connected), then the
    dashboard on every launch after that."""
    try:
        inner = (_shell_inner() if setup_state.is_configured()
                 else onboarding.layout())
    except Exception:
        import traceback
        tb = traceback.format_exc()
        try:
            (config.DATA_DIR / "last_error.log").write_text(tb)
        except OSError:
            pass
        inner = _error_panel(tb)
    return dmc.MantineProvider(forceColorScheme="dark", theme=THEME, children=inner)


# Global "enlarge any chart" overlay — opened by any panel's ⤢ button.
_MODAL_CFG = {"displayModeBar": True, "scrollZoom": True, "responsive": True,
              "displaylogo": False}


def _chart_modal():
    return dmc.Modal(
        id="gc-chart-modal", opened=False, size="90%", centered=True, zIndex=2000,
        children=dcc.Graph(id="gc-modal-graph", style={"height": "78vh"},
                           config=_MODAL_CFG))


@callback(Output("gc-chart-modal", "opened"), Output("gc-chart-modal", "title"),
          Output("gc-modal-graph", "figure"),
          Input({"type": "gc-expand", "index": ALL}, "n_clicks"),
          State({"type": "gc-fig", "index": ALL}, "figure"),
          State({"type": "gc-fig", "index": ALL}, "id"),
          prevent_initial_call=True)
def _expand_any(_clicks, figs, ids):
    trig = ctx.triggered_id
    if not trig or not ctx.triggered or not ctx.triggered[0].get("value"):
        raise PreventUpdate          # membership change / initial, not a real click
    key = trig["index"]
    fig = {fid["index"]: f for fid, f in zip(ids, figs)}.get(key)
    if not fig:
        raise PreventUpdate
    fig = copy.deepcopy(fig)
    fig.setdefault("layout", {})
    fig["layout"]["height"] = None       # fill the modal via autosize
    fig["layout"]["autosize"] = True
    return True, ui.PANEL_TITLES.get(key, ""), fig


@callback(Output("tab-overview", "style"), Output("tab-analysis", "style"),
          Output("tab-coach", "style"), Input("tab-switch", "value"))
def switch_tab(tab):
    return (_SHOW if tab == "overview" else _HIDE,
            _SHOW if tab == "analysis" else _HIDE,
            _SHOW if tab == "coach" else _HIDE)


def _activity_count() -> int:
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]


def _latest_dates() -> tuple[str | None, str | None]:
    """(latest activity date, latest health day with any recovery value)."""
    with db.connect() as conn:
        la = conn.execute(
            "SELECT MAX(date(start_time)) FROM activity_metrics").fetchone()[0]
        lh = conn.execute(
            "SELECT MAX(day) FROM health_daily WHERE hrv_overnight IS NOT NULL "
            "OR readiness_score IS NOT NULL OR resting_hr IS NOT NULL "
            "OR sleep_score IS NOT NULL").fetchone()[0]
    return la, lh


def _fmt_day(d: str | None) -> str:
    return dt.date.fromisoformat(d).strftime("%b %-d") if d else "—"


@callback(Output("tab-overview", "children"), Output("sync-status", "children"),
          Output("an-run", "data"), Output("an-run", "value"),
          Input("sync-btn", "n_clicks"), prevent_initial_call=True)
def sync_now(_n):
    """Pull new Garmin activities + health, recompute metrics, and refresh the
    Overview *and* the Deep-Analysis run picker (which is otherwise built once at
    page load, so a freshly-synced run wouldn't appear there without a reload).

    Data-only: skips the slow LLM recommendation refresh and profile re-fetch —
    use the Coach tab's 'Refresh recommendations' for those.
    """
    from garmin_coach import pipeline
    from garmin_coach.dashboard import data

    try:
        before = _activity_count()
        pipeline.update(examine=50, health_days=14, refresh_profile=False,
                        refresh_recommendations=False)
        new = _activity_count() - before
    except Exception as exc:  # noqa: BLE001 — surface the failure in the UI.
        return (dash.no_update, html.Span(f"Sync failed · {exc}", className="err"),
                dash.no_update, dash.no_update)

    la, lh = _latest_dates()
    head = (f"Synced · {new} new workout{'s' if new != 1 else ''}"
            if new else "Synced · up to date")
    if la == lh:
        freshness = f"data through {_fmt_day(la)}"
    else:
        freshness = f"runs to {_fmt_day(la)} · health to {_fmt_day(lh)}"
    # Rebuild the run picker; select the newest run so Deep Analysis shows it.
    opts = data.run_options()
    value = opts[0]["value"] if opts else dash.no_update
    return (overview.layout(), html.Span(f"{head} · {freshness}", className="ok"),
            opts, value)


app.layout = layout

if __name__ == "__main__":
    import os
    # Local dev keeps the old behaviour (localhost + hot reload); a server sets
    # GC_HOST=0.0.0.0 and GC_DEBUG=0 to serve on the network without the reloader.
    # threaded so a slow LLM callback doesn't block the whole UI.
    app.run(host=os.getenv("GC_HOST", "127.0.0.1"),
            port=int(os.getenv("GC_PORT", "8050")),
            debug=os.getenv("GC_DEBUG", "1") == "1",
            threaded=True)
