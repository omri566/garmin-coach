"""Garmin Coach dashboard — single-page app with show/hide tab sections.

Both tab sections are always mounted in the DOM (toggled via CSS), so every
callback's component IDs always exist — this avoids the "ID not found in layout"
errors that Mantine Tabs cause by unmounting inactive panels.

Run:  .venv/bin/python -m garmin_coach.dashboard.app   then open http://127.0.0.1:8050
"""
from __future__ import annotations

import dash
import dash_mantine_components as dmc
from dash import Input, Output, _dash_renderer, callback, html

from garmin_coach.dashboard import figures
from garmin_coach.dashboard.pages import analysis, overview

_dash_renderer._set_react_version("18.2.0")

app = dash.Dash(__name__, external_stylesheets=dmc.styles.ALL,
                title="Garmin Coach", suppress_callback_exceptions=True)
server = app.server

_SHOW: dict = {}
_HIDE = {"display": "none"}


def shell():
    return dmc.MantineProvider(
        forceColorScheme="dark",
        children=html.Div(
            style={"backgroundColor": figures.BG, "minHeight": "100vh"},
            children=dmc.Container([
                dmc.Group([
                    dmc.Title("🏃 Garmin Coach", order=2),
                    dmc.Text("personal endurance analytics", c="dimmed", size="sm"),
                ], justify="space-between", mt="md", mb="sm"),
                dmc.SegmentedControl(
                    id="tab-switch", value="overview", mb="md", color="blue",
                    data=[{"label": "Overview", "value": "overview"},
                          {"label": "Deep Analysis", "value": "analysis"}],
                ),
                html.Div(overview.layout(), id="tab-overview"),
                html.Div(analysis.layout(), id="tab-analysis", style=_HIDE),
                dmc.Space(h="xl"),
            ], fluid=True, style={"paddingBottom": "2rem"}),
        ),
    )


@callback(Output("tab-overview", "style"), Output("tab-analysis", "style"),
          Input("tab-switch", "value"))
def switch_tab(tab):
    return (_SHOW, _HIDE) if tab == "overview" else (_HIDE, _SHOW)


app.layout = shell

if __name__ == "__main__":
    app.run(debug=True, port=8050)
