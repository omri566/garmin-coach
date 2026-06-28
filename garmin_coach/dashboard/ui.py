"""Shared UI helpers used across dashboard pages."""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc

from garmin_coach.dashboard import explain, figures

GRAPH_CFG = {"displayModeBar": False, "responsive": True}
CARD = dict(className="gc-card", radius="md", p="md")


def fmt_pace(s):
    return f"{int(s // 60)}:{int(s % 60):02d}/km" if s else "—"


def section(label, idx=None):
    """Mono eyebrow + hairline lane-rule that opens a content section."""
    from dash import html
    inner = [html.Span(label, className="lab")]
    if idx:
        inner.insert(0, html.Span(f"{idx} ", className="lab idx"))
    inner.append(html.Span(className="rule"))
    return html.Div(inner, className="gc-section")


def info_dropdown(key):
    info = explain.METRICS[key]
    label, color = explain.DIRECTION_LABEL[info.direction]
    return dmc.HoverCardDropdown(
        dmc.Stack([
            dmc.Text(info.title, fw=700, size="sm"),
            dmc.Text(info.desc, size="xs", c="dimmed"),
            dmc.Badge(label, color=color, variant="light", size="sm"),
        ], gap=6),
        style={"maxWidth": 300},
    )


def with_info(target, key, position="top"):
    """Wrap a component so hovering it opens an explanation card."""
    if key not in explain.METRICS:
        return target
    return dmc.HoverCard(
        [dmc.HoverCardTarget(target), info_dropdown(key)],
        withArrow=True, shadow="lg", position=position, openDelay=120, width=300,
    )


def kpi(label, value, sub=None, color=figures.TEXT, info_key=None):
    from dash import html
    head = html.Div([
        html.Span(label, className="gc-kpi-label"),
        html.Span(" ⓘ", className="gc-kpi-label",
                  style={"opacity": 0.5}) if info_key else None,
    ], style={"cursor": "help"} if info_key else None)
    card = dmc.Card(
        html.Div([
            head,
            html.Div(value, className="gc-kpi-val", style={"color": color}),
            html.Div(sub or "", className="gc-kpi-sub"),
        ], className="gc-kpi-body",
            style={"display": "flex", "flexDirection": "column", "gap": "5px"}),
        className="gc-card gc-kpi", radius="md", p="md",
        style={"--accent": color},
    )
    return with_info(card, info_key) if info_key else card


# Registry so the global expand modal can title itself from a chart's key.
PANEL_TITLES: dict[str, str] = {}


def fig_id(key):
    return {"type": "gc-fig", "index": key}


def expand_id(key):
    return {"type": "gc-expand", "index": key}


def panel(title, fig, info_key=None, key=None, **graph_kwargs):
    """A titled chart card. Pass ``key`` to make it expandable to fullscreen and
    to give its graph a stable pattern-matching id (``fig_id(key)``) that range
    callbacks can target."""
    title_grp = dmc.Group([
        dmc.Text(title, fw=600, size="sm"),
        dmc.Text("ⓘ", size="xs", c="dimmed") if info_key else None,
    ], gap=4, style={"cursor": "help"} if info_key else None)
    if info_key:
        title_grp = with_info(title_grp, info_key, position="top-start")
    if key:
        PANEL_TITLES[key] = title
        graph_kwargs.setdefault("id", fig_id(key))
        header = dmc.Group([
            title_grp,
            dmc.ActionIcon("⤢", id=expand_id(key), variant="subtle", color="gray",
                           size="sm", radius="sm", n_clicks=0,
                           **{"aria-label": "Enlarge"}),
        ], justify="space-between", align="center", mb=8)
    else:
        header = dmc.Group([title_grp], mb=8)
    return dmc.Card([header, dcc.Graph(figure=fig, config=GRAPH_CFG, **graph_kwargs)],
                    **CARD)


def range_tabs(control_id, value="1y"):
    """Stock-style 3M / 1Y / 5Y selector, used in section headers."""
    return dmc.SegmentedControl(
        id=control_id, value=value, size="xs", radius="sm",
        data=[{"label": "3M", "value": "3m"},
              {"label": "1Y", "value": "1y"},
              {"label": "5Y", "value": "5y"}],
    )


def section_with_control(label, control):
    """A section eyebrow with a trailing control (e.g. range tabs) on the right."""
    from dash import html
    return html.Div([section(label), control], className="gc-section-row")


def tsb_color(tsb):
    if tsb is None:
        return figures.TEXT
    if tsb > 5:
        return figures.GREEN
    if tsb < -15:
        return figures.RED
    return figures.ORANGE


def acwr_color(a):
    if a is None:
        return figures.TEXT
    return figures.GREEN if 0.8 <= a <= 1.3 else figures.RED
