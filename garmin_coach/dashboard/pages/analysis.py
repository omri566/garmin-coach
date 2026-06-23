"""Deep Analysis tab — per-run splits, intra-run drift, decoupling, technique."""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import Input, Output, callback, dcc, html

from garmin_coach.analytics import intra
from garmin_coach.dashboard import data, figures
from garmin_coach.dashboard.ui import CARD, GRAPH_CFG, fmt_pace, panel, with_info

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
    return dmc.Stack([
        dmc.Group([
            dmc.Text("Select run", size="sm", c="dimmed"),
            dmc.Select(id="an-run", data=opts, value=default, searchable=True,
                       w=320, allowDeselect=False),
        ]),
        html.Div(id="an-summary"),
        dmc.Grid([
            dmc.GridCol(html.Div(id="an-splits"), span={"base": 12, "md": 5}),
            dmc.GridCol(html.Div(id="an-decoupling"), span={"base": 12, "md": 7}),
        ], gutter="md"),
        html.Div(id="an-drift"),
        html.Div(id="an-cadence"),
        html.Div(id="an-technique"),
    ], gap="md")


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

    def b(text, color):
        return dmc.Badge(text, color=color, variant="light", size="lg")

    hr = (f"{m['avg_hr']:.0f}/{m['max_hr']:.0f}"
          if m.get("avg_hr") and m.get("max_hr") else "—")
    summary = dmc.Group([
        b(m.get("start_time", "")[:10], "gray"),
        b(f"{(m.get('distance_m') or 0)/1000:.1f} km", "blue"),
        b(f"Pace {fmt_pace(m.get('avg_pace_s_km'))}", "teal"),
        b(f"HR {hr}", "red"),
        b(f"EF {m['ef']:.2f}" if m.get("ef") else "EF —", "green"),
        b(f"Load {m['training_stress']:.0f}" if m.get("training_stress") else "Load —", "grape"),
    ], gap="xs")

    drift = intra.drift_series(df)
    halves = intra.decoupling_halves(df)
    splits = intra.per_km_splits(df)

    drift_panel = panel("Pace & heart-rate drift", figures.drift_pace_hr(drift))
    cad_panel = panel("Cadence drift", figures.cadence_drift(drift))
    tech = technique_panel(m) if m.get("avg_vert_ratio") else dmc.Card(
        dmc.Text("No running-dynamics data for this activity (pre-2023 device)."), **CARD)

    return (summary, splits_table(splits), decoupling_card(halves),
            drift_panel, cad_panel, tech)
