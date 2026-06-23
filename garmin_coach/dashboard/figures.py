"""Plotly figure builders with a shared dark theme."""
from __future__ import annotations

import plotly.graph_objects as go

# Palette
BG = "#11151c"
PANEL = "#161b22"
GRID = "#222b36"
TEXT = "#c9d1d9"
BLUE = "#4dabf7"      # fitness / CTL
ORANGE = "#ffa94d"    # fatigue / ATL
GREEN = "#51cf66"
RED = "#ff6b6b"
VIOLET = "#b197fc"
TEAL = "#3bc9db"
ZONE_COLORS = ["#4dabf7", "#51cf66", "#ffd43b", "#ffa94d", "#ff6b6b"]


def _base(height: int = 320, title: str | None = None) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=PANEL, plot_bgcolor=PANEL,
        font=dict(color=TEXT, size=12),
        margin=dict(l=48, r=24, t=40 if title else 16, b=36),
        height=height,
        title=dict(text=title, font=dict(size=15)) if title else None,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def fitness_form(df) -> go.Figure:
    """CTL (fitness) & ATL (fatigue) lines + TSB (form) as colored area."""
    fig = _base(height=360)
    if df.empty:
        return fig
    x = df.index
    tsb_pos = df["tsb"].clip(lower=0)
    tsb_neg = df["tsb"].clip(upper=0)
    fig.add_bar(x=x, y=tsb_pos, name="Form (fresh)", marker_color=GREEN,
                opacity=0.35, yaxis="y2")
    fig.add_bar(x=x, y=tsb_neg, name="Form (fatigued)", marker_color=RED,
                opacity=0.35, yaxis="y2")
    fig.add_scatter(x=x, y=df["ctl"], name="Fitness (CTL)", line=dict(color=BLUE, width=2.5))
    fig.add_scatter(x=x, y=df["atl"], name="Fatigue (ATL)", line=dict(color=ORANGE, width=1.6))
    fig.update_layout(
        barmode="relative",
        yaxis=dict(title="Load"),
        yaxis2=dict(title="Form", overlaying="y", side="right",
                    showgrid=False, zeroline=True, zerolinecolor=GRID),
    )
    return fig


def acwr(df) -> go.Figure:
    fig = _base(height=220)
    if df.empty:
        return fig
    fig.add_hrect(y0=0.8, y1=1.3, fillcolor=GREEN, opacity=0.10, line_width=0)
    fig.add_scatter(x=df.index, y=df["acwr"].clip(upper=2.5), name="ACWR",
                    line=dict(color=VIOLET, width=2))
    fig.add_hline(y=1.5, line=dict(color=RED, width=1, dash="dot"))
    fig.update_yaxes(title="ACWR", range=[0, 2.5])
    return fig


def weekly_volume(df) -> go.Figure:
    fig = _base(height=300)
    if df.empty:
        return fig
    df = df.tail(26)
    fig.add_bar(x=df["date"], y=df["distance_km"], name="Distance (km)",
                marker_color=BLUE)
    fig.add_scatter(x=df["date"], y=df["hours"] * 10, name="Hours (×10)",
                    line=dict(color=TEAL, width=2), yaxis="y2")
    fig.update_layout(
        yaxis=dict(title="km/week"),
        yaxis2=dict(overlaying="y", side="right", showgrid=False, visible=False),
    )
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
               height: int = 300) -> go.Figure:
    fig = _base(height=height)
    if df is None or df.empty:
        return fig
    xcol = "date" if "date" in df.columns else df.columns[0]
    fig.add_scatter(x=df[xcol], y=df[col], mode="markers", name=label,
                    marker=dict(color=color, size=4, opacity=0.35))
    if "rolling" in df.columns:
        fig.add_scatter(x=df[xcol], y=df["rolling"], name=f"{label} (trend)",
                        line=dict(color=color, width=2.5))
    return fig
