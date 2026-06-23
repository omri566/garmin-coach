# Garmin Coach — Architecture

Companion to `SPEC.md`. Stack + module layout + build order.

Status: **stack locked.**

---

## Stack

| Layer | Choice | Notes |
|---|---|---|
| Language | **Python 3.13** | `/Users/omrizalstein/miniconda3/bin/python3` |
| Garmin API | `garminconnect` | summaries, health metrics, race predictions, readiness |
| Raw streams | `fitparse` / `garmin-fit-sdk` | per-second/per-record FIT data |
| Analytics | `pandas` (+ `polars` if needed) | trends, models |
| Storage | **SQLite** (metrics/trends) + **Parquet** (dense per-second streams) | |
| Dashboard | **Dash + Dash Mantine Components + Plotly (WebGL)** | optimized + polished |
| Background jobs | **diskcache-backed Dash background callbacks** | long LLM calls without blocking UI |
| Scheduling | **launchd** (macOS) | incremental sync + periodic KB refresh |
| AI | **LLMProvider abstraction** (see below) | no API key required today |

### LLM provider (no API key)
Abstraction so AI calls are backend-agnostic:
- **`ClaudeCodeProvider`** (default) → `claude -p "<prompt>" --output-format json`, runs on existing Claude Code subscription auth. Used for recommendations, plan generation, deep-research KB build (Claude Code has WebSearch/WebFetch).
- **`CodexProvider`** (fallback) → `codex exec`.
- **`AnthropicAPIProvider`** (future) → drop-in when an API key exists.
- Contract: every call requests **structured JSON** + is **schema-validated**; LLM sees **computed trends/summaries only, never raw per-second rows** (token control).
- Caveats: headless = slower (agent loop, seconds) and needs an active login for scheduled jobs. Acceptable for this workload.

---

## Modules

```
garmin-coach/
  ingest/          # garminconnect sync, FIT download, incremental state
    sync.py        #   incremental: new activities + new health days only
    fit_parser.py  #   FIT -> per-second parquet
    gaps.py        #   no-training vs unrecorded detection, confidence flags
  store/           # SQLite schema + parquet IO + query helpers
  analytics/
    load.py        #   CTL/ATL/TSB (Banister), ACWR
    efficiency.py  #   EF, Pa:Hr decoupling, pace-at-HR drift
    technique.py   #   running dynamics vs ranges + personal baselines
    fitness.py     #   VO2max, LT, Riegel/VO2 race predictions
    curves.py      #   power/pace-duration, critical speed/power
    recovery.py    #   HRV/RHR/sleep -> recovery state gate
    adherence.py   #   per-session-type execution scoring (SPEC §6)
  plan/            # goal -> macro (3mo) + next-month detail, ACWR-guided, adaptive
  knowledge/       # versioned KB; deep-research build + refresh pass
  llm/             # LLMProvider interface + Claude Code / Codex / API impls
  dashboard/       # Dash app (Pages: Overview, Deep Analysis, Plan, Recommendations)
  jobs/            # launchd entrypoints: sync, kb_refresh
```

---

## Build order (phased)

**Phase 1 — Ingest + storage**
Incremental sync, FIT parsing to parquet, SQLite schema, gap detection. Goal: full history captured, queryable.

**Phase 2 — Analytics / trends**
Load (CTL/ATL/TSB/ACWR), efficiency/decoupling, technique baselines, fitness/predictions, curves, recovery state. Goal: every SPEC metric computed with confidence flags.

**Phase 3 — Dashboard**
Dash app over Phase 2 outputs: Overview + Deep Analysis pages, optimized WebGL charts, last-activity card. Goal: usable visual tool.

**Phase 4 — Plan + recommendations + knowledge base**
LLMProvider, deep-research KB build (first), execution scoring, goal-driven adaptive plan (you-in-the-loop), recommendation engine. Plan + Recommendations pages. launchd schedules. Goal: full coaching loop.

---

## Open items
- Session-type taxonomy + adherence thresholds (Phase 4, needs SPEC §6 detail).
- KB source-vetting criteria for deep-research pass.
- Exact SQLite schema (Phase 1).
