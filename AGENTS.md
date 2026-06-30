# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Dashboard charts — date x-axis gotcha

`analytics.trends.rolling_metric` (and the trends built on it: `efficiency_trend`,
`power_trend`, `technique_trends`) returns a frame with the date in a **`"date"`
column over a positional `RangeIndex`**, whereas the load-series frames feeding
`figures.fitness_form`/`acwr` are **`DatetimeIndex`-indexed** with no `date`
column. Plotly figure helpers that need the x position of a row must use the
`"date"` column when present and only fall back to `df.index` otherwise — using
`series.index[-1]` blindly places points/annotations at an integer like `273` on
a date x-axis, which renders as ~1970-01-01 and drags the whole auto-range back
to the epoch (and makes the 3M/1Y/5Y range buttons look dead). See
`figures._end_label` and `tests/test_figures_dates.py`.
