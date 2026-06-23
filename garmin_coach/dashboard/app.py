"""Garmin Coach dashboard — Overview page (Phase 3).

Run:  .venv/bin/python -m garmin_coach.dashboard.app   then open http://127.0.0.1:8050
"""
from __future__ import annotations

import dash
import dash_mantine_components as dmc
from dash import _dash_renderer, dcc, html

from garmin_coach.dashboard import data, explain, figures

_dash_renderer._set_react_version("18.2.0")

app = dash.Dash(__name__, external_stylesheets=dmc.styles.ALL,
                title="Garmin Coach")
server = app.server

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
        withArrow=True, shadow="lg", position=position, openDelay=120,
        width=300,
    )


def kpi(label, value, sub=None, color=figures.TEXT, info_key=None):
    card = dmc.Card(
        dmc.Stack([
            dmc.Group([
                dmc.Text(label, size="xs", c="dimmed", tt="uppercase", fw=600),
                dmc.Text("ⓘ", size="xs", c="dimmed") if info_key else None,
            ], gap=4, justify="space-between", style={"cursor": "help"} if info_key else None),
            dmc.Text(value, fw=700, style={"fontSize": "1.7rem", "color": color,
                                           "lineHeight": 1.1}),
            dmc.Text(sub or "", size="xs", c="dimmed"),
        ], gap=2),
        **CARD,
    )
    return with_info(card, info_key) if info_key else card


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


def kpi_row():
    st = data.current_state()
    h = data.latest_health()
    vo2 = data.latest_vo2max()
    hrv = h.get("hrv_overnight")
    rhr = h.get("resting_hr")
    rdy = h.get("readiness_score")
    cards = [
        kpi("Fitness · CTL", f"{st.get('ctl','—')}", "chronic load (42d)", figures.BLUE, "ctl"),
        kpi("Fatigue · ATL", f"{st.get('atl','—')}", "acute load (7d)", figures.ORANGE, "atl"),
        kpi("Form · TSB", f"{st.get('tsb','—')}", "fitness − fatigue",
            tsb_color(st.get("tsb")), "tsb"),
        kpi("ACWR", f"{st.get('acwr','—')}", "sweet spot 0.8–1.3",
            acwr_color(st.get("acwr")), "acwr"),
        kpi("VO₂max", f"{vo2 or '—'}", "ml/kg/min", figures.VIOLET, "vo2max"),
        kpi("Readiness", f"{int(rdy['value']) if rdy else '—'}",
            f"HRV {int(hrv['value']) if hrv else '—'} · RHR {int(rhr['value']) if rhr else '—'}",
            figures.TEAL, "readiness"),
    ]
    return dmc.SimpleGrid(cards, cols={"base": 2, "sm": 3, "lg": 6}, spacing="md")


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
        # Outer row stays full-width & unwrapped so space-between right-aligns it.
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
        *( [dmc.Divider(my="sm"), *dyn] if dyn else [] ),
    ], **CARD)


def panel(title, fig, info_key=None, **graph_kwargs):
    header = dmc.Group([
        dmc.Text(title, fw=600),
        dmc.Text("ⓘ", size="xs", c="dimmed") if info_key else None,
    ], gap=4, mb=6, style={"cursor": "help"} if info_key else None)
    if info_key:
        header = with_info(header, info_key, position="top-start")
    return dmc.Card([header, dcc.Graph(figure=fig, config=GRAPH_CFG, **graph_kwargs)],
                    **CARD)


def layout():
    ldf = data.load_series()
    return dmc.MantineProvider(
        forceColorScheme="dark",
        children=dmc.Container([
            dmc.Group([
                dmc.Title("🏃 Garmin Coach", order=2),
                dmc.Text("Overview", c="dimmed"),
            ], justify="space-between", mt="md", mb="md"),

            kpi_row(),
            dmc.Space(h="md"),

            panel("Fitness · Fatigue · Form", figures.fitness_form(ldf), "chart_fitness_form"),
            dmc.Space(h="md"),

            dmc.Grid([
                dmc.GridCol(panel("Training-load ratio (ACWR)", figures.acwr(ldf), "chart_acwr"), span={"base": 12, "md": 8}),
                dmc.GridCol(last_run_card(), span={"base": 12, "md": 4}),
            ], gutter="md"),
            dmc.Space(h="md"),

            dmc.Grid([
                dmc.GridCol(panel("Weekly volume", figures.weekly_volume(data.weekly_volume()), "chart_volume"), span={"base": 12, "md": 8}),
                dmc.GridCol(panel("HR-zone mix (12 wk)", figures.zone_donut(data.zone_distribution()), "chart_zones"), span={"base": 12, "md": 4}),
            ], gutter="md"),
            dmc.Space(h="md"),

            dmc.Grid([
                dmc.GridCol(panel("Aerobic efficiency (EF)", figures.line_trend(
                    data.efficiency_trend(), "ef", "EF", figures.GREEN), "chart_ef"), span={"base": 12, "md": 6}),
                dmc.GridCol(panel("VO₂max", figures.line_trend(
                    data.vo2max_trend(), "vo2max", "VO₂max", figures.VIOLET), "chart_vo2"), span={"base": 12, "md": 6}),
            ], gutter="md"),
            dmc.Space(h="xl"),
        ], fluid=True, style={"backgroundColor": figures.BG, "minHeight": "100vh",
                              "paddingBottom": "2rem"}),
    )


app.layout = layout

if __name__ == "__main__":
    app.run(debug=True, port=8050)
