"""Plotly figure builders with a shared dark theme."""
from __future__ import annotations

import plotly.graph_objects as go

# Palette — "Telemetry" theme. Chrome lives in app.css; these drive the charts.
BG = "#0E1217"        # app background
PANEL = "#151B23"     # card surface (charts draw transparent over this)
GRID = "#222B36"      # hairline gridlines
TEXT = "#E8EDF3"
MUTED = "#93A1B1"
AMP = "#FFB02E"       # signature accent
BLUE = "#5AA2F0"      # fitness / CTL
ORANGE = "#FF9F45"    # fatigue / ATL
GREEN = "#46D08A"
RED = "#FF6B6B"
VIOLET = "#B49CFF"
TEAL = "#34C7D6"
# HR zones 1→5: easy blue → aerobic teal → tempo green → threshold amber → red
ZONE_COLORS = ["#5AA2F0", "#34C7D6", "#46D08A", "#FFB02E", "#FF6B6B"]

_MONO = "JetBrains Mono, ui-monospace, monospace"
_SANS = "Archivo, system-ui, sans-serif"


def _base(height: int = 320, title: str | None = None) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=MUTED, size=12, family=_SANS),
        margin=dict(l=48, r=24, t=36 if title else 12, b=34),
        height=height,
        title=dict(text=title, font=dict(size=14, color=TEXT)) if title else None,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    font=dict(size=11, color=MUTED)),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#0B0F14", bordercolor=GRID,
                        font=dict(family=_MONO, size=12, color=TEXT)),
    )
    tick = dict(tickfont=dict(family=_MONO, size=10, color=MUTED))
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID, **tick)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID, **tick)
    return fig


def _end_label(fig, df, col, color, fmt="{:.0f}", yaxis="y"):
    """Tag the last point of a series with its value, so the chart reads without
    decoding the legend."""
    s = df[col].dropna()
    if s.empty:
        return
    # Anchor the label at the real date. Frames built by rolling_metric carry the
    # date in a "date" column over a positional RangeIndex; using s.index there
    # would place the label at an integer (e.g. 273), which a date x-axis reads
    # as ~1970 and which drags the whole auto-range back to the epoch. Frames
    # like the load series are DatetimeIndex-indexed, so the index is the date.
    last = s.index[-1]
    x = df["date"].loc[last] if "date" in df.columns else last
    fig.add_annotation(x=x, y=float(s.iloc[-1]), yref=yaxis,
                       text=" " + fmt.format(float(s.iloc[-1])), showarrow=False,
                       xanchor="left", font=dict(family=_MONO, size=12, color=color))


def _x_rangeslider(fig, thickness=0.05):
    """Add a draggable bar under the x-axis for manual window adjustment. The
    trace preview is hidden in CSS so it reads as a plain slider, not a chart."""
    fig.update_xaxes(rangeslider=dict(visible=True, thickness=thickness,
                                      bgcolor="rgba(255,255,255,0.03)",
                                      bordercolor=GRID, borderwidth=1))


def fitness_form(df) -> go.Figure:
    """Fitness (CTL) & fatigue (ATL) lines + form (TSB) as a fresh/tired band.

    Fitness is the hero (thick blue); fatigue rides on top (thin orange); the
    green/red band below zero shows whether you're rested or carrying load."""
    fig = _base(height=400)
    if df.empty:
        return fig
    x = df.index
    fig.add_bar(x=x, y=df["tsb"].clip(lower=0), name="Form · fresh", marker_color=GREEN,
                opacity=0.30, yaxis="y2", hovertemplate="Form +%{y:.0f}<extra></extra>")
    fig.add_bar(x=x, y=df["tsb"].clip(upper=0), name="Form · tired", marker_color=RED,
                opacity=0.30, yaxis="y2", hovertemplate="Form %{y:.0f}<extra></extra>")
    fig.add_scatter(x=x, y=df["atl"], name="Fatigue",
                    line=dict(color=ORANGE, width=1.6, shape="spline", smoothing=0.6),
                    hovertemplate="Fatigue %{y:.0f}<extra></extra>")
    fig.add_scatter(x=x, y=df["ctl"], name="Fitness",
                    line=dict(color=BLUE, width=2.8, shape="spline", smoothing=0.6),
                    hovertemplate="Fitness %{y:.0f}<extra></extra>")
    _end_label(fig, df, "ctl", BLUE)
    _end_label(fig, df, "atl", ORANGE)
    fig.update_layout(
        barmode="relative", bargap=0,
        yaxis=dict(title="Training load"),
        yaxis2=dict(title="Form", overlaying="y", side="right",
                    showgrid=False, zeroline=True, zerolinecolor=GRID),
        margin=dict(l=48, r=46, t=36, b=20),
    )
    _x_rangeslider(fig)
    return fig


def acwr(df) -> go.Figure:
    """Acute:chronic load ratio — how fast you're ramping vs the injury-risk zones."""
    fig = _base(height=270)
    if df.empty:
        return fig
    afont = dict(family=_MONO, size=10)
    fig.add_hrect(y0=0.8, y1=1.3, fillcolor=GREEN, opacity=0.10, line_width=0,
                  annotation_text="sweet spot", annotation_position="bottom left",
                  annotation_font=dict(color=GREEN, **afont))
    fig.add_hline(y=1.5, line=dict(color=RED, width=1, dash="dot"),
                  annotation_text="injury risk", annotation_position="top left",
                  annotation_font=dict(color=RED, **afont))
    a = df["acwr"].clip(upper=2.5)
    fig.add_scatter(x=df.index, y=a, name="ACWR",
                    line=dict(color=VIOLET, width=2, shape="spline", smoothing=0.6),
                    showlegend=False, hovertemplate="ACWR %{y:.2f}<extra></extra>")
    _end_label(fig, df.assign(acwr=a), "acwr", VIOLET, fmt="{:.2f}")
    fig.update_yaxes(title="ACWR", range=[0, 2.5])
    fig.update_layout(margin=dict(l=48, r=42, t=12, b=18))
    _x_rangeslider(fig)
    return fig


def weekly_volume(df) -> go.Figure:
    fig = _base(height=320)
    if df.empty:
        return fig
    fig.add_bar(x=df["date"], y=df["distance_km"], name="Distance (km)",
                marker_color=BLUE, hovertemplate="%{y:.0f} km<extra></extra>")
    fig.add_scatter(x=df["date"], y=df["hours"], name="Hours",
                    line=dict(color=TEAL, width=2, shape="spline", smoothing=0.6),
                    yaxis="y2", hovertemplate="%{y:.1f} h<extra></extra>")
    fig.update_layout(
        yaxis=dict(title="km / week"),
        yaxis2=dict(title="hours", overlaying="y", side="right", showgrid=False),
    )
    _x_rangeslider(fig)
    return fig


def zone_donut(df) -> go.Figure:
    fig = _base(height=300)
    if df.empty:
        return fig
    fig.add_pie(labels=df["zone"], values=df["seconds"], hole=0.55,
                marker=dict(colors=ZONE_COLORS),
                textinfo="label+percent", sort=False)
    fig.update_layout(showlegend=False, margin=dict(l=8, r=8, t=16, b=8))
    return fig


def drift_pace_hr(df, height: int = 360) -> go.Figure:
    """Intra-run pace (reversed: up = faster) and HR vs distance."""
    fig = _base(height=height)
    if df is None or df.empty:
        return fig
    fig.add_scatter(x=df["distance_km"], y=df["pace_s_km"], name="Pace",
                    line=dict(color=BLUE, width=2))
    fig.add_scatter(x=df["distance_km"], y=df["heart_rate"], name="Heart rate",
                    line=dict(color=RED, width=1.8), yaxis="y2")
    fig.update_layout(
        xaxis=dict(title="distance (km)"),
        yaxis=dict(title="pace (s/km)", autorange="reversed"),
        yaxis2=dict(title="HR", overlaying="y", side="right", showgrid=False),
    )
    return fig


def cadence_drift(df, height: int = 300) -> go.Figure:
    fig = _base(height=height)
    if df is None or df.empty or "cadence_spm" not in df:
        return fig
    fig.add_scatter(x=df["distance_km"], y=df["cadence_spm"], name="Cadence",
                    line=dict(color=GREEN, width=1.8))
    fig.update_layout(xaxis=dict(title="distance (km)"),
                      yaxis=dict(title="cadence (spm)"))
    return fig


def decoupling_bar(halves: dict, height: int = 300) -> go.Figure:
    fig = _base(height=height)
    if not halves:
        return fig
    fig.add_bar(x=["1st half", "2nd half"],
                y=[halves["ef_first"], halves["ef_second"]],
                marker_color=[BLUE, ORANGE], width=0.5,
                text=[f"{halves['ef_first']:.2f}", f"{halves['ef_second']:.2f}"],
                textposition="outside")
    fig.update_layout(yaxis=dict(title="Efficiency (speed/HR)"), showlegend=False)
    return fig


def line_trend(df, col: str, label: str, color: str = TEAL,
               height: int = 300, band=None, fmt="{:.0f}") -> go.Figure:
    """Per-activity markers + a smooth rolling trend, with an optional green
    reference band and a direct end-of-trend value tag."""
    fig = _base(height=height)
    if df is None or df.empty:
        return fig
    xcol = "date" if "date" in df.columns else df.columns[0]
    if band:
        fig.add_hrect(y0=band[0], y1=band[1], fillcolor=GREEN, opacity=0.08,
                      line_width=0)
    fig.add_scatter(x=df[xcol], y=df[col], mode="markers", name=label,
                    marker=dict(color=color, size=4, opacity=0.35),
                    hoverinfo="skip")
    if "rolling" in df.columns:
        fig.add_scatter(x=df[xcol], y=df["rolling"], name=f"{label} (trend)",
                        line=dict(color=color, width=2.5, shape="spline",
                                  smoothing=0.5))
        _end_label(fig, df, "rolling", color, fmt=fmt)
    _x_rangeslider(fig)
    return fig


def pace_trend(df, col: str = "avg_pace_s_km", label: str = "Easy pace",
               color: str = GREEN, height: int = 300) -> go.Figure:
    """Pace trend with a reversed axis (up = faster) and m:ss/km tick labels."""
    fig = _base(height=height)
    if df is None or df.empty:
        return fig
    fig.add_scatter(x=df["date"], y=df[col], mode="markers", name=label,
                    marker=dict(color=color, size=4, opacity=0.30), hoverinfo="skip")
    if "rolling" in df.columns:
        fig.add_scatter(x=df["date"], y=df["rolling"], name=f"{label} (trend)",
                        line=dict(color=color, width=2.5, shape="spline",
                                  smoothing=0.5))
    vals = df[col].dropna()
    if not vals.empty:
        lo, hi = float(vals.min()), float(vals.max())
        ticks = [lo + (hi - lo) * i / 4 for i in range(5)]
        fig.update_yaxes(
            autorange="reversed", tickvals=ticks,
            ticktext=[f"{int(t // 60)}:{int(t % 60):02d}" for t in ticks],
            title="pace /km")
    _x_rangeslider(fig)
    return fig


def gct_balance_trend(df, col: str = "avg_gct_balance",
                      height: int = 300) -> go.Figure:
    """Left/right ground-contact symmetry with the balanced reference band."""
    fig = _base(height=height)
    if df is None or df.empty:
        return fig
    fig.add_hrect(y0=48.5, y1=51.5, fillcolor=GREEN, opacity=0.10, line_width=0,
                  annotation_text="even", annotation_position="top left",
                  annotation_font=dict(family=_MONO, size=10, color=GREEN))
    fig.add_hline(y=50, line=dict(color=GRID, width=1, dash="dot"))
    fig.add_scatter(x=df["date"], y=df[col], mode="markers", name="% left",
                    marker=dict(color=TEAL, size=4, opacity=0.30), hoverinfo="skip")
    if "rolling" in df.columns:
        fig.add_scatter(x=df["date"], y=df["rolling"], name="Balance (trend)",
                        line=dict(color=TEAL, width=2.5, shape="spline",
                                  smoothing=0.5))
        _end_label(fig, df, "rolling", TEAL, fmt="{:.1f}")
    fig.update_yaxes(title="% left (50 = even)")
    _x_rangeslider(fig)
    return fig


# --- recovery / health (daily) ----------------------------------------------
def daily_metric(df, col, label, color, day="day", yrange=None, band=None,
                 fmt="{:.0f}", height=300, recent_avg=False) -> go.Figure:
    """Daily markers + a smooth 14-day trend for a recovery metric, with an
    optional reference band, end-of-trend value tag, and (if ``recent_avg``) a
    horizontal line at the last-14-day average for a baseline to read against."""
    fig = _base(height=height)
    if df is None or df.empty or col not in df.columns:
        return fig
    d = df.dropna(subset=[col]).sort_values(day)
    if d.empty:
        return fig
    if band:
        fig.add_hrect(y0=band[0], y1=band[1], fillcolor=GREEN, opacity=0.08,
                      line_width=0)
    fig.add_scatter(x=d[day], y=d[col], mode="markers", name=label,
                    marker=dict(color=color, size=4, opacity=0.26), hoverinfo="skip")
    roll = d.set_index(day)[col].rolling("14D", min_periods=2).mean()
    fig.add_scatter(x=roll.index, y=roll.values, name=f"{label} (trend)",
                    line=dict(color=color, width=2.5, shape="spline", smoothing=0.5),
                    hovertemplate=label + " %{y:.0f}<extra></extra>")
    rv = roll.dropna()
    if not rv.empty:
        fig.add_annotation(x=rv.index[-1], y=float(rv.iloc[-1]),
                           text=" " + fmt.format(float(rv.iloc[-1])), showarrow=False,
                           xanchor="left", font=dict(family=_MONO, size=12, color=color))
    if recent_avg and not rv.empty:
        avg = float(rv.iloc[-1])      # 14-day rolling at the last point = last-14d mean
        fig.add_hline(y=avg, line=dict(color=AMP, width=1.4, dash="dash"),
                      annotation_text=f"14-day avg · {fmt.format(avg)}",
                      annotation_position="bottom right",
                      annotation_font=dict(family=_MONO, size=10, color=AMP))
        fig.add_scatter(x=[None], y=[None], mode="lines", name="14-day avg",
                        line=dict(color=AMP, width=1.4, dash="dash"))
    if yrange:
        fig.update_yaxes(range=yrange)
    _x_rangeslider(fig)
    return fig


def body_battery_trend(df, day="day", height=300) -> go.Figure:
    """Garmin's Body Battery as a daily peak→low filled band."""
    fig = _base(height=height)
    if df is None or df.empty:
        return fig
    d = df.dropna(subset=["body_battery_high", "body_battery_low"]).sort_values(day)
    if d.empty:
        return fig
    fig.add_scatter(x=d[day], y=d["body_battery_high"], name="Peak",
                    line=dict(color=GREEN, width=1.5, shape="spline", smoothing=0.5),
                    hovertemplate="Peak %{y:.0f}<extra></extra>")
    fig.add_scatter(x=d[day], y=d["body_battery_low"], name="Low",
                    line=dict(color=ORANGE, width=1.5, shape="spline", smoothing=0.5),
                    fill="tonexty", fillcolor="rgba(70,208,138,0.10)",
                    hovertemplate="Low %{y:.0f}<extra></extra>")
    fig.update_yaxes(title="Body Battery", range=[0, 100])
    _x_rangeslider(fig)
    return fig


# --- running trends (weekly) ------------------------------------------------
def zone_time(df, day="date", height=320) -> go.Figure:
    """Weekly hours in each HR zone, stacked — a polarization trend over time."""
    fig = _base(height=height)
    if df is None or df.empty:
        return fig
    for i in range(1, 6):
        fig.add_bar(x=df[day], y=df[f"Z{i}"], name=f"Z{i}",
                    marker_color=ZONE_COLORS[i - 1],
                    hovertemplate=f"Z{i} " + "%{y:.1f} h<extra></extra>")
    fig.update_layout(barmode="stack", yaxis=dict(title="hours / week"))
    _x_rangeslider(fig)
    return fig


def elevation(df, day="date", height=300) -> go.Figure:
    """Weekly total elevation gain (m)."""
    fig = _base(height=height)
    if df is None or df.empty:
        return fig
    fig.add_bar(x=df[day], y=df["elev_gain_m"], name="Elevation gain",
                marker_color=VIOLET, hovertemplate="%{y:.0f} m<extra></extra>")
    fig.update_layout(yaxis=dict(title="m / week"), showlegend=False)
    _x_rangeslider(fig)
    return fig
