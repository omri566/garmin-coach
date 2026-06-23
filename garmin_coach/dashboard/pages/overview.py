"""Overview tab — headline fitness/fatigue/form, last run, key trends."""
from __future__ import annotations

import dash_mantine_components as dmc

from garmin_coach.dashboard import data, figures
from garmin_coach.dashboard.ui import (
    CARD, acwr_color, fmt_pace, kpi, panel, tsb_color, with_info,
)


def kpi_row():
    st = data.current_state()
    h = data.latest_health()
    vo2 = data.latest_vo2max()
    hrv, rhr, rdy = h.get("hrv_overnight"), h.get("resting_hr"), h.get("readiness_score")
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
        *([dmc.Divider(my="sm"), *dyn] if dyn else []),
    ], **CARD)


def layout():
    ldf = data.load_series()
    return dmc.Stack([
        kpi_row(),
        panel("Fitness · Fatigue · Form", figures.fitness_form(ldf), "chart_fitness_form"),
        dmc.Grid([
            dmc.GridCol(panel("Training-load ratio (ACWR)", figures.acwr(ldf), "chart_acwr"), span={"base": 12, "md": 8}),
            dmc.GridCol(last_run_card(), span={"base": 12, "md": 4}),
        ], gutter="md"),
        dmc.Grid([
            dmc.GridCol(panel("Weekly volume", figures.weekly_volume(data.weekly_volume()), "chart_volume"), span={"base": 12, "md": 8}),
            dmc.GridCol(panel("HR-zone mix (12 wk)", figures.zone_donut(data.zone_distribution()), "chart_zones"), span={"base": 12, "md": 4}),
        ], gutter="md"),
        dmc.Grid([
            dmc.GridCol(panel("Aerobic efficiency (EF)", figures.line_trend(
                data.efficiency_trend(), "ef", "EF", figures.GREEN), "chart_ef"), span={"base": 12, "md": 6}),
            dmc.GridCol(panel("VO₂max", figures.line_trend(
                data.vo2max_trend(), "vo2max", "VO₂max", figures.VIOLET), "chart_vo2"), span={"base": 12, "md": 6}),
        ], gutter="md"),
    ], gap="md")
