"""Regression: trend figures must anchor on real activity dates, not 1970.

Frames built by ``analytics.trends.rolling_metric`` carry their date in a
``"date"`` column over a positional ``RangeIndex``. ``figures._end_label`` used
to place its end-of-trend annotation at ``series.index[-1]`` — an integer on
those frames — which a Plotly date x-axis renders as ~1970-01-01 and which then
drags the whole auto-range back to the epoch (and makes the 3M/1Y/5Y range
buttons look dead). These tests guard both the RangeIndex frames (EF, power,
running technique) and the DatetimeIndex frames (fitness/ACWR) that already
worked.
"""

from __future__ import annotations

import pandas as pd

from garmin_coach.dashboard import figures

EPOCH = pd.Timestamp("1970-01-01")


def _rolling_metric_frame(col: str) -> pd.DataFrame:
    """Mimic analytics.trends.rolling_metric: date column + RangeIndex."""
    dates = pd.date_range("2025-01-01", periods=30, freq="3D")
    df = pd.DataFrame({
        "date": dates,
        col: range(30),
        "rolling": [float(i) for i in range(30)],
    })
    # reset_index() in rolling_metric leaves a positional RangeIndex — reproduce it.
    return df.reset_index(drop=True)


def _annotation_x(fig):
    # The end-of-trend label's text is the formatted numeric value; skip band
    # labels like "even" that some builders also add.
    labels = [a for a in fig.layout.annotations
              if any(ch.isdigit() for ch in (a.text or ""))]
    assert labels, "expected an end-of-trend value annotation"
    return pd.Timestamp(labels[-1].x)


def test_line_trend_annotation_is_real_date_not_epoch():
    df = _rolling_metric_frame("ef")
    fig = figures.line_trend(df, "ef", "EF", fmt="{:.2f}")
    x = _annotation_x(fig)
    assert x.year >= 2025, f"annotation anchored at {x}, expected the last real date"
    assert x == df["date"].iloc[-1]
    assert abs((x - EPOCH).days) > 365 * 30  # nowhere near 1970


def test_gct_balance_trend_annotation_is_real_date_not_epoch():
    df = _rolling_metric_frame("avg_gct_balance")
    fig = figures.gct_balance_trend(df)
    x = _annotation_x(fig)
    assert x.year >= 2025
    assert x == df["date"].iloc[-1]


def test_no_figure_x_value_lands_near_epoch():
    """No trace point or annotation may sit near 1970 — an epoch-anchored point
    is exactly what forced the date x-axis auto-range back to the epoch."""
    df = _rolling_metric_frame("avg_power_w")
    fig = figures.line_trend(df, "avg_power_w", "Power")
    xs = [a.x for a in fig.layout.annotations]
    for tr in fig.data:
        xs.extend(list(tr.x) if tr.x is not None else [])
    for x in xs:
        assert pd.Timestamp(x).year >= 2024, f"x value {x!r} regressed toward 1970"


def test_datetimeindex_end_label_still_anchors_on_index_date():
    """fitness_form / acwr pass DatetimeIndex frames (no 'date' column); the
    label must still land on the timestamp index, not regress."""
    idx = pd.date_range("2025-01-01", periods=10, freq="W")
    df = pd.DataFrame({"ctl": range(10)}, index=idx)
    fig = figures._base()
    figures._end_label(fig, df, "ctl", figures.BLUE)
    x = _annotation_x(fig)
    assert x == idx[-1]


if __name__ == "__main__":  # allow running without pytest installed
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all figure-date regression checks passed")
