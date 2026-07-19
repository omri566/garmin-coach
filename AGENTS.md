# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## LLM provider — CLI subprocess must capture to files, not pipes

`llm/provider.ClaudeCodeProvider` shells out to the `claude` CLI. **Never capture
its output with `subprocess.run(capture_output=True)` / pipes.** `communicate()`
reads the stdout/stderr pipes until **EOF**, which only arrives once *every*
process holding the write end has exited — and the Claude Code CLI forks
short-lived children (update check, tool/IPC helpers, node/ripgrep workers) that
**inherit** those pipe fds. If one lingers a moment after `claude` prints its JSON
and exits, the pipe never reaches EOF and the read blocks until the `timeout` —
so a generation that finished in ~20s looks like `LLMError: claude CLI timed out
after Ns`. This bit the phase-advance plan generation hard (always failed at the
timeout cap, never at ~200s — the tell for a deadlock vs. slow generation).

`_exec` writes stdin/stdout/stderr to **temp files** and waits on the CLI's *own*
exit (`Popen.wait(timeout=…)`, `start_new_session=True` so a real timeout can
`killpg` the whole group). With no pipe there is no EOF to wait on, so a leftover
child can't wedge us. See `test_llm_provider.py::test_exec_returns_output_even_if_
a_child_holds_the_pipe` (a real `/bin/sh` that backgrounds a child holding stdout).
Keep new CLI plumbing on `_exec`.

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
  session planned for its own date, and is *consumed and attributed* (`match`)
  there even if that day was manually marked done/skipped (so it can't spill
  onto a neighbouring session); (2) nearest — a run with no session on its own
  day attaches to the closest open session ("did it a day early/late"). Without
  pass 1, a Monday run whose Monday session was already marked done would
  greedily grab a later open session (e.g. Wednesday) — the
  late-sync-matched-the-wrong-day bug.
- `match` is the run→session attribution and is set on the same-day session
  **regardless of manual status** — it is a fact ("this run happened on this
  planned day"), separate from the *displayed* status which `_status` keeps
  authoritative (skipped stays skipped; done stays done, no drift note for a
  same-day match). This is deliberate: the overview's "Versus plan" card
  recognises a run as planned **only** via `match.activity_id`
  (`dashboard/pages/overview.py:_matched_session`), so withholding `match` from a
  manually-done day made the plan view show the session done while the overview
  flagged the same run as an "extra — not in plan". Keep `match` complete so the
  two views can never disagree. See `test_manually_done_session_still_exposes_its_run_match`.
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
- `test_patterns.py` — personal-pattern detection (`analytics/patterns.py`):
  evidence-gated insights (e.g. time-of-day EF edge) surfaced only when the
  athlete's own data clears the sample-size + effect-size bar.
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
