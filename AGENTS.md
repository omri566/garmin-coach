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

## Plan / run matching (`coach/schedule.py`)

- A completed run is anchored to the day it was **actually performed** — its
  activity *start* time (`activity_metrics.start_time`, which is Garmin's
  `startTimeLocal`), never the sync/ingest time (`ingested_at` / `computed_at`,
  which can be a day later for a late sync).
- `_automatch` runs two passes: (1) same-day — a run lands on the non-rest
  session planned for its own date, and is *consumed* there even if that day was
  manually marked done/skipped (so it can't spill onto a neighbouring session);
  (2) nearest — a run with no session on its own day attaches to the closest
  open session ("did it a day early/late"). Without pass 1, a Monday run whose
  Monday session was already marked done would greedily grab a later open
  session (e.g. Wednesday) — the late-sync-matched-the-wrong-day bug.
- A matched session shows `done` regardless of override, so an auto-match landing
  on the wrong session also blocks the athlete from clearing it manually; keeping
  runs anchored to their own day is what makes the manual done/skip toggle stick.

## Tests

Hermetic pytest suite in `tests/` (autouse `gc_data` fixture in `conftest.py`
repoints `config`, `store.db`, and `coach.plan` paths at a scratch dir). Run:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

The suite covers the pure-function core:

- `test_load.py` — training-load model (`analytics/load.py`): CTL/ATL/TSB/ACWR,
  ramp, `current_state`, `load_series`.
- `test_features.py` — per-activity features (`analytics/features.py`): TRIMP,
  efficiency factor, decoupling, HR-zone distribution.
- `test_schedule.py` — plan scheduling (`coach/schedule.py`): `parse_week_range`
  and `build_schedule` status logic + Sunday→Saturday date anchoring.
- `test_llm_provider.py` — LLM JSON extraction (`llm/provider.py`) and
  `ClaudeCodeProvider` with the `claude` CLI subprocess mocked.
- `test_figures_dates.py`, `test_schedule_matching.py` — dashboard date-axis and
  run-matching regressions (see the sections above).

Hermeticity notes — no test hits the network, Garmin, or a real LLM:

- The autouse `gc_data` fixture points every data path at a per-test `tmp_path`
  scratch dir and seeds a fresh schema via the project's own DDL, so tests never
  touch the real data dir. `GC_DATA_DIR` is therefore optional locally; CI sets
  it to a throwaway dir as belt-and-suspenders.
- The `claude` CLI subprocess in `llm/provider.py` is mocked via
  `monkeypatch.setattr(provider.subprocess, "run", ...)`.

CI (`.github/workflows/ci.yml`) runs `pytest` on Python 3.13. It installs
`requirements.txt` + `requirements-dev.txt`; `pytest` config (including
`pythonpath = ["."]`, needed so the flat-layout `garmin_coach` package imports
under a bare `pytest`) lives in `pyproject.toml`. Ruff runs there non-blocking;
the existing codebase predates a lint baseline, so only `tests/` is expected to
be ruff-clean. The Playwright smoke test (`tools/browser_check.py`) needs a live
dashboard + real data and is **not** part of CI.
