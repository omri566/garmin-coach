"""Shared UI helpers used across dashboard pages."""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc

from garmin_coach.dashboard import explain, figures

GRAPH_CFG = {"displayModeBar": False, "responsive": True}
CARD = dict(withBorder=True, radius="md", p="md",
            style={"backgroundColor": figures.PANEL, "borderColor": figures.GRID})


def fmt_pace(s):
    return f"{int(s // 60)}:{int(s % 60):02d}/km" if s else "—"


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
    card = dmc.Card(
        dmc.Stack([
            dmc.Group([
                dmc.Text(label, size="xs", c="dimmed", tt="uppercase", fw=600),
                dmc.Text("ⓘ", size="xs", c="dimmed") if info_key else None,
            ], gap=4, justify="space-between",
                style={"cursor": "help"} if info_key else None),
            dmc.Text(value, fw=700, style={"fontSize": "1.7rem", "color": color,
                                           "lineHeight": 1.1}),
            dmc.Text(sub or "", size="xs", c="dimmed"),
        ], gap=2),
        **CARD,
    )
    return with_info(card, info_key) if info_key else card


def panel(title, fig, info_key=None, **graph_kwargs):
    header = dmc.Group([
        dmc.Text(title, fw=600),
        dmc.Text("ⓘ", size="xs", c="dimmed") if info_key else None,
    ], gap=4, mb=6, style={"cursor": "help"} if info_key else None)
    if info_key:
        header = with_info(header, info_key, position="top-start")
    return dmc.Card([header, dcc.Graph(figure=fig, config=GRAPH_CFG, **graph_kwargs)],
                    **CARD)


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
