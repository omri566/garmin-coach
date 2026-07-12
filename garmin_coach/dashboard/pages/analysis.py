"""Deep Analysis tab — per-run splits, intra-run drift, decoupling, technique."""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import Input, Output, callback, clientside_callback, dcc, html

from garmin_coach.analytics import intra
from garmin_coach.dashboard import data, figures
from garmin_coach.dashboard.ui import (
    CARD, GRAPH_CFG, fig_id, fmt_pace, panel, range_tabs, section, with_info,
)

# Reference ranges (sport-science typical bands) for the technique comparison.
TECH_REFS = {
    "avg_cadence_spm": dict(label="Cadence", unit="spm", info="cadence",
                            fmt="{:.0f}", good=(170, 185), ok=(165, 190)),
    "avg_vert_ratio": dict(label="Vertical ratio", unit="%", info="vert_ratio",
                           fmt="{:.1f}", good=(0, 8), ok=(8, 10), lower=True),
    "avg_gct_ms": dict(label="Ground contact", unit="ms", info="gct",
                       fmt="{:.0f}", good=(0, 250), ok=(250, 300), lower=True),
    "avg_gct_balance": dict(label="GCT balance", unit="% L", info="gct_balance",
                            fmt="{:.1f}", good=(48.5, 51.5), ok=(47.5, 52.5)),
    "avg_step_len_mm": dict(label="Step length", unit="mm", info="step_len",
                            fmt="{:.0f}"),
}


def _status(ref, val):
    if val is None:
        return "—", "gray"
    good, ok = ref.get("good"), ref.get("ok")
    if good and good[0] <= val <= good[1]:
        return "Good", "green"
    if ok and ok[0] <= val <= ok[1]:
        return "OK", "yellow"
    if good is None:
        return "—", "gray"
    return "Watch", "orange"


def technique_panel(m: dict) -> dmc.Card:
    base = data.technique_baselines()
    rows = []
    for col, ref in TECH_REFS.items():
        val = m.get(col)
        b = base.get(col)
        label, color = _status(ref, val)
        rng = (f"{ref['good'][0]:g}–{ref['good'][1]:g}" if ref.get("good") else "—")
        name = dmc.Group([dmc.Text(ref["label"], size="sm"),
                          dmc.Text("ⓘ", size="9px", c="dimmed")], gap=4,
                         style={"cursor": "help"})
        rows.append(html.Tr([
            html.Td(with_info(name, ref["info"], position="right")),
            html.Td(dmc.Text(ref["fmt"].format(val) + f" {ref['unit']}" if val is not None else "—",
                             size="sm", fw=600)),
            html.Td(dmc.Text(ref["fmt"].format(b) if b is not None else "—",
                             size="sm", c="dimmed")),
            html.Td(dmc.Text(rng, size="sm", c="dimmed")),
            html.Td(dmc.Badge(label, color=color, variant="light", size="sm")),
        ]))
    head = html.Thead(html.Tr([html.Th(h) for h in
                               ["Metric", "This run", "Your median", "Reference", ""]]))
    return dmc.Card([
        dmc.Text("Running technique vs reference", fw=600, mb=6),
        dmc.Table([head, html.Tbody(rows)], striped=True, highlightOnHover=True),
    ], **CARD)


def _f(val, fmt="{:.0f}", prefix=""):
    if val is None or (isinstance(val, float) and val != val):  # None or NaN
        return "—"
    return prefix + fmt.format(val)


def splits_table(df) -> dmc.Card:
    if df is None or df.empty:
        return dmc.Card(dmc.Text("No split data."), **CARD)
    rows = []
    for _, r in df.iterrows():
        rows.append(html.Tr([
            html.Td(f"{int(r['km'])}"),
            html.Td(fmt_pace(r["pace_s_km"])),
            html.Td(_f(r["avg_hr"])),
            html.Td(_f(r["cadence"])),
            html.Td(_f(r["vert_ratio"], "{:.1f}")),
            html.Td(_f(r["elev_gain"], "{:.0f}", prefix="+")),
        ]))
    head = html.Thead(html.Tr([html.Th(h) for h in
                               ["Km", "Pace", "HR", "Cad", "V.ratio", "Elev"]]))
    return dmc.Card([
        dmc.Text("Per-kilometre splits", fw=600, mb=6),
        dmc.Table([head, html.Tbody(rows)], striped=True, highlightOnHover=True,
                  withTableBorder=False),
    ], **CARD)


def decoupling_card(halves: dict) -> dmc.Card:
    if not halves:
        body = dmc.Text("Not enough data.", c="dimmed")
    else:
        d = halves["decoupling_pct"]
        good = d is not None and d <= 5
        verdict = ("Good durability — held efficiency." if good
                   else "Faded — efficiency dropped in the 2nd half (heat, fatigue, or too hard).")
        body = dmc.Stack([
            dcc.Graph(figure=figures.decoupling_bar(halves), config=GRAPH_CFG),
            dmc.Group([
                dmc.Text("Decoupling", size="sm", c="dimmed"),
                dmc.Badge(f"{d:.1f} %", color="green" if good else "red",
                          variant="light", size="lg"),
            ], justify="space-between"),
            dmc.Text(verdict, size="xs", c="dimmed"),
        ], gap=8)
    header = dmc.Group([dmc.Text("Aerobic decoupling", fw=600),
                        dmc.Text("ⓘ", size="xs", c="dimmed")], gap=4,
                       style={"cursor": "help"}, mb=6)
    return dmc.Card([with_info(header, "decoupling", position="top-start"), body], **CARD)


def layout():
    opts = data.run_options()
    default = opts[0]["value"] if opts else None
    workout = dmc.Stack([
        section("Splits & durability"),
        dmc.Grid([
            dmc.GridCol(html.Div(id="an-splits"), span={"base": 12, "md": 5}),
            dmc.GridCol(html.Div(id="an-decoupling"), span={"base": 12, "md": 7}),
        ], gutter="md"),
        section("Intra-run drift"),
        html.Div(id="an-drift"),
        html.Div(id="an-cadence"),
        section("Running technique"),
        html.Div(id="an-technique"),
    ], gap="md")
    return dmc.Stack([
        dmc.Group([
            dmc.Text("Run", size="xs", c="dimmed", className="mono",
                     style={"letterSpacing": "0.12em", "textTransform": "uppercase"}),
            dmc.Select(id="an-run", data=opts, value=default, searchable=True,
                       w=320, allowDeselect=False),
        ], align="center"),
        html.Div(id="an-summary"),
        html.Div(dmc.Accordion(
            id="an-workout-acc", multiple=True, value=[],
            chevronPosition="right", variant="separated", children=[
                dmc.AccordionItem([
                    dmc.AccordionControl(dmc.Group([
                        dmc.Text("Deep workout analysis", fw=600, size="sm"),
                        dmc.Text("splits · drift · technique", size="xs", c="dimmed"),
                    ], gap="sm")),
                    dmc.AccordionPanel(workout, pt="sm"),
                ], value="workout"),
            ]), className="gc-recs"),
        html.Div(id="an-resize-dummy", style={"display": "none"}),
        trends_section(),
    ], gap="md")


def _col(comp, md):
    return dmc.GridCol(comp, span={"base": 12, "md": md})


def _volume_figs(rng):
    sl = lambda df: data.slice_since(df, rng)
    return {
        "an-volume": figures.weekly_volume(sl(data.weekly_volume())),
        "an-zonetime": figures.zone_time(sl(data.zone_time_weekly())),
        "an-elevation": figures.elevation(sl(data.elevation_weekly())),
    }


def _aerobic_figs(rng):
    sl = lambda df: data.slice_since(df, rng)
    return {
        "an-ef": figures.line_trend(sl(data.efficiency_trend()), "ef", "EF",
                                    figures.GREEN, fmt="{:.2f}"),
        "an-vo2": figures.line_trend(sl(data.vo2max_trend()), "vo2max", "VO₂max",
                                     figures.VIOLET),
        "an-pace": figures.pace_trend(sl(data.aerobic_pace_trend())),
        "an-power": figures.line_trend(sl(data.power_trend()), "avg_power_w",
                                       "Power", figures.AMP),
    }


def _technique_figs(rng):
    sl = lambda df: data.slice_since(df, rng)
    tt = data.technique_trends()
    return {
        "an-cadence": figures.line_trend(sl(tt["avg_cadence_spm"]), "avg_cadence_spm",
                                         "Cadence", figures.BLUE, band=(170, 185)),
        "an-vert": figures.line_trend(sl(tt["avg_vert_ratio"]), "avg_vert_ratio",
                                      "Vert ratio", figures.VIOLET, fmt="{:.1f}",
                                      band=(0, 8)),
        "an-gct": figures.line_trend(sl(tt["avg_gct_ms"]), "avg_gct_ms", "GCT",
                                     figures.TEAL),
        "an-gctbal": figures.gct_balance_trend(sl(tt["avg_gct_balance"])),
    }


def _recovery_figs(rng):
    rec = data.slice_since(data.recovery_trend(), rng, col="day")
    return {
        "an-hrv": figures.daily_metric(rec, "hrv_overnight", "HRV", figures.VIOLET),
        "an-rhr": figures.daily_metric(rec, "resting_hr", "Resting HR", figures.RED),
        "an-sleep": figures.daily_metric(rec, "sleep_score", "Sleep", figures.TEAL,
                                         yrange=[0, 100]),
        "an-bb": figures.body_battery_trend(rec),
        "an-stress": figures.daily_metric(rec, "stress_avg", "Stress", figures.ORANGE,
                                          yrange=[0, 100]),
        "an-readiness": figures.daily_metric(rec, "readiness_score", "Readiness",
                                             figures.GREEN, yrange=[0, 100]),
    }


# Per-collapsible group: (range control id, builder, ordered output keys).
_GROUPS = {
    "volume": ("an-range-volume", _volume_figs,
               ["an-volume", "an-zonetime", "an-elevation"]),
    "aerobic": ("an-range-aerobic", _aerobic_figs,
                ["an-ef", "an-vo2", "an-pace", "an-power"]),
    "technique": ("an-range-technique", _technique_figs,
                  ["an-cadence", "an-vert", "an-gct", "an-gctbal"]),
    "recovery": ("an-range-recovery", _recovery_figs,
                 ["an-hrv", "an-rhr", "an-sleep", "an-bb", "an-stress",
                  "an-readiness"]),
}


def _range_row(group):
    """Right-aligned range tabs at the top of a collapsible's body."""
    return html.Div(range_tabs(_GROUPS[group][0]), className="gc-panel-range")


def trends_section():
    """Long-term trend + recovery charts, collapsed by default. Each collapsible
    carries its own 3M/1Y/5Y range tabs; every chart is enlargeable via ⤢."""
    fv, fa, ft, fr = (_volume_figs("1y"), _aerobic_figs("1y"),
                      _technique_figs("1y"), _recovery_figs("1y"))

    volume = dmc.Stack([
        _range_row("volume"),
        dmc.Grid([
            _col(panel("Weekly volume", fv["an-volume"], "chart_volume",
                       key="an-volume"), 8),
            _col(panel("HR-zone mix (12 wk)", figures.zone_donut(
                data.zone_distribution()), "chart_zones", key="an-zones"), 4),
        ], gutter="md"),
        dmc.Grid([
            _col(panel("Time in HR zones (weekly)", fv["an-zonetime"],
                       key="an-zonetime"), 8),
            _col(panel("Elevation gain (weekly)", fv["an-elevation"],
                       key="an-elevation"), 4),
        ], gutter="md"),
    ], gap="md")
    aerobic = dmc.Stack([
        _range_row("aerobic"),
        dmc.Grid([
            _col(panel("Aerobic efficiency (EF)", fa["an-ef"], "chart_ef",
                       key="an-ef"), 6),
            _col(panel("VO₂max", fa["an-vo2"], "chart_vo2", key="an-vo2"), 6),
        ], gutter="md"),
        dmc.Grid([
            _col(panel("Easy-run pace (aerobic, Z2)", fa["an-pace"], "pace",
                       key="an-pace"), 6),
            _col(panel("Running power", fa["an-power"], key="an-power"), 6),
        ], gutter="md"),
    ], gap="md")
    technique = dmc.Stack([
        _range_row("technique"),
        dmc.Grid([
            _col(panel("Cadence", ft["an-cadence"], "cadence", key="an-cadence"), 6),
            _col(panel("Vertical ratio", ft["an-vert"], "vert_ratio",
                       key="an-vert"), 6),
        ], gutter="md"),
        dmc.Grid([
            _col(panel("Ground contact time", ft["an-gct"], "gct", key="an-gct"), 6),
            _col(panel("Left/right GCT balance", ft["an-gctbal"], "gct_balance",
                       key="an-gctbal"), 6),
        ], gutter="md"),
    ], gap="md")
    recovery = dmc.Stack([
        _range_row("recovery"),
        dmc.Grid([
            _col(panel("HRV (overnight)", fr["an-hrv"], key="an-hrv"), 6),
            _col(panel("Resting heart rate", fr["an-rhr"], key="an-rhr"), 6),
        ], gutter="md"),
        dmc.Grid([
            _col(panel("Sleep score", fr["an-sleep"], key="an-sleep"), 6),
            _col(panel("Body Battery", fr["an-bb"], key="an-bb"), 6),
        ], gutter="md"),
        dmc.Grid([
            _col(panel("Stress", fr["an-stress"], key="an-stress"), 6),
            _col(panel("Training readiness", fr["an-readiness"], key="an-readiness"), 6),
        ], gutter="md"),
    ], gap="md")

    def item(title, sub, value, body):
        return dmc.AccordionItem([
            dmc.AccordionControl(dmc.Group([
                dmc.Text(title, fw=600, size="sm"),
                dmc.Text(sub, size="xs", c="dimmed"),
            ], gap="sm")),
            dmc.AccordionPanel(body, pt="sm"),
        ], value=value)

    return dmc.Stack([
        section("Trends"),
        html.Div(dmc.Accordion(
            id="an-trends-acc", multiple=True, value=[], chevronPosition="right",
            variant="separated", children=[
                item("Volume & intensity", "weekly load · zones · elevation",
                     "volume", volume),
                item("Aerobic & fitness trends", "EF · VO₂max · easy pace · power",
                     "aerobic", aerobic),
                item("Running technique trends",
                     "cadence · vertical ratio · ground contact · balance", "technique",
                     technique),
                item("Recovery & health",
                     "HRV · resting HR · sleep · Body Battery · stress · readiness",
                     "recovery", recovery),
            ]), className="gc-recs"),
    ], gap="sm")


def _make_group_callback(builder, keys):
    def _update(rng):
        f = builder(rng)
        return [f[k] for k in keys]
    return _update


# One range callback per collapsible group, scoped to just its charts.
for _gid, (_ctl, _builder, _keys) in _GROUPS.items():
    callback([Output(fig_id(k), "figure") for k in _keys],
             Input(_ctl, "value"))(_make_group_callback(_builder, _keys))


# Plotly graphs rendered inside a collapsed panel come up at zero width; nudge
# them to re-measure whenever any accordion section is expanded. A single
# callback (not one per accordion) — duplicate inline clientside functions hash
# to the same name and break Dash's registration.
clientside_callback(
    "function(a, b){ setTimeout(function(){ "
    "window.dispatchEvent(new Event('resize')); }, 80); return ''; }",
    Output("an-resize-dummy", "children"),
    Input("an-workout-acc", "value"), Input("an-trends-acc", "value"))


@callback(
    Output("an-summary", "children"),
    Output("an-splits", "children"),
    Output("an-decoupling", "children"),
    Output("an-drift", "children"),
    Output("an-cadence", "children"),
    Output("an-technique", "children"),
    Input("an-run", "value"),
)
def render(activity_id):
    if not activity_id:
        return "—", None, None, None, None, None
    m = data.run_metrics(activity_id) or {}
    df = data.run_streams(activity_id)

    def cell(k, v, color=None):
        return html.Div([
            html.Div(k, className="k"),
            html.Div(v, className="v", style={"color": color} if color else None),
        ], className="cell")

    hr = (f"{m['avg_hr']:.0f}/{m['max_hr']:.0f}"
          if m.get("avg_hr") and m.get("max_hr") else "—")
    summary = html.Div([
        cell("Date", m.get("start_time", "")[:10]),
        cell("Distance", f"{(m.get('distance_m') or 0)/1000:.1f} km", figures.BLUE),
        cell("Pace", fmt_pace(m.get("avg_pace_s_km")), figures.TEAL),
        cell("HR avg/max", hr, figures.RED),
        cell("EF", f"{m['ef']:.2f}" if m.get("ef") else "—", figures.GREEN),
        cell("Load", f"{m['training_stress']:.0f}" if m.get("training_stress") else "—",
             figures.VIOLET),
    ], className="gc-runhead")

    drift = intra.drift_series(df)
    halves = intra.decoupling_halves(df)
    splits = intra.per_km_splits(df)

    drift_panel = panel("Pace & heart-rate drift", figures.drift_pace_hr(drift),
                        key="an-driftfig")
    cad_panel = panel("Cadence drift", figures.cadence_drift(drift), key="an-cadfig")
    tech = technique_panel(m) if m.get("avg_vert_ratio") else dmc.Card(
        dmc.Text("No running-dynamics data for this activity (pre-2023 device)."), **CARD)

    return (summary, splits_table(splits), decoupling_card(halves),
            drift_panel, cad_panel, tech)
