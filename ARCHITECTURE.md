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
| Dashboard | **Dash + Dash Mantine Components + Plotly (WebGL)** | single-page tabbed app |
| Background jobs | **threaded Dash callbacks** (`app.run(threaded=True)`) | slow LLM callbacks don't block the UI; diskcache background callbacks are a future option |
| Scheduling | run `python -m garmin_coach.pipeline` (incremental) | manually or from an external scheduler (e.g. launchd); no scheduler is wired up in-repo yet |
| AI | **LLMProvider abstraction** (see below) | no API key required today |

### LLM provider (no API key)
Abstraction so AI calls are backend-agnostic:
- **`ClaudeCodeProvider`** (default) → `claude -p "<prompt>" --output-format json`, runs on existing Claude Code subscription auth. Used for recommendations, plan generation, deep-research KB build (Claude Code has WebSearch/WebFetch).
- **`CodexProvider`** (fallback) → `codex exec`.
- **`AnthropicAPIProvider`** (planned, not yet built) → drop-in when an API key exists.
- Contract: every call requests **structured JSON** + is **schema-validated**; LLM sees **computed trends/summaries only, never raw per-second rows** (token control).
- Caveats: headless = slower (agent loop, seconds) and needs an active login for scheduled jobs. Acceptable for this workload.

---

## Modules

```
garmin_coach/
  config.py          # central paths + configuration
  profile.py         # athlete profile: physiological anchors for zone-based metrics
  pipeline.py        # one-shot incremental update of the whole data + analytics pipeline
  ingest/            # Garmin Connect sync + FIT parsing
    client.py        #   Garmin Connect authentication
    sync.py          #   incremental activity sync into the store
    health.py        #   daily health-metrics sync (recovery inputs)
    fit_parser.py    #   raw FIT -> per-second streams + laps + session summary
    gaps.py          #   gap & data-availability detection, confidence flags
  store/             # persistence
    db.py            #   SQLite store for activity & health summaries
    streams.py       #   Parquet IO for dense per-second streams
  analytics/         # metrics & trends over stored data
    features.py      #   per-activity feature extraction (backbone of every trend)
    compute.py       #   compute features for every activity into activity_metrics
    load.py          #   training load: Fitness/Fatigue/Form + ACWR time series
    trends.py        #   long-term trend series for the dashboard
    intra.py         #   within-activity: per-km splits, intra-run drift, decoupling
  coach/             # coaching engine
    context.py       #   assemble athlete state into a compact brief for the coach LLM
    recommend.py     #   science-backed recommendation engine over real data
    plan.py          #   goal-driven adaptive training plan (you-in-the-loop)
    schedule.py      #   anchor planned sessions to dates, match completed runs
  knowledge/         # cited endurance-science knowledge base
    kb.py            #   versioned KB of cited guidance
    research.py      #   deep-research pass that builds the KB
  llm/               # AI backend
    provider.py      #   LLMProvider abstraction + Claude Code / Codex impls
  dashboard/         # Dash single-page app — tabs: Overview / Deep Analysis / Coach
    app.py           #   app shell, tab switching, sync-now callback
    pages/
      overview.py    #     Overview tab: fitness/fatigue/form, last run, key trends
      analysis.py    #     Deep Analysis tab: splits, drift, decoupling, technique
      coach.py       #     Coach tab: recommendations + goal-driven plan
    data.py          #   cached data access wrapping the analytics layer
    figures.py       #   Plotly figure builders with a shared dark theme
    explain.py       #   plain-English metric explanations for hover cards
    ui.py            #   shared UI helpers
tools/
  browser_check.py   # headless-browser smoke test for the dashboard
tests/               # hermetic pytest unit suite over the pure-function core
  conftest.py        #   autouse fixture: scratch data dir + fresh schema
  test_load.py       #   training-load model (CTL/ATL/TSB/ACWR)
  test_features.py   #   per-activity features (TRIMP, EF, decoupling, zones)
  test_schedule.py   #   plan scheduling + run/session matching
  test_llm_provider.py #   LLM JSON extraction (mocked claude CLI)
```

---

## Build order (phased)

**Phase 1 — Ingest + storage**
Incremental sync, FIT parsing to parquet, SQLite schema, gap detection. Goal: full history captured, queryable.

**Phase 2 — Analytics / trends**
Per-activity features (`analytics/features.py`, `compute.py`), training load — Fitness/Fatigue/Form + ACWR (`load.py`), long-term trend series (`trends.py`), within-activity splits/drift/decoupling (`intra.py`). Goal: every metric computed with confidence flags.

**Phase 3 — Dashboard**
Dash app over Phase 2 outputs: Overview + Deep Analysis tabs, optimized WebGL charts, last-activity card. Goal: usable visual tool.

**Phase 4 — Coach: plan + recommendations + knowledge base**
LLMProvider, deep-research KB build (first), athlete-state context, goal-driven adaptive plan (you-in-the-loop), recommendation engine, plan/run scheduling. Surfaced in the **Coach** tab. Goal: full coaching loop.

---

## Open items
- Per-session-type execution/adherence scoring — not yet built; `coach/schedule.py` matches completed runs to planned sessions but does not score adherence.
- KB source-vetting criteria for the deep-research pass (`knowledge/research.py`).
- `AnthropicAPIProvider` LLM backend (planned, not yet built).
- In-repo scheduler wiring (e.g. launchd plist) for periodic `pipeline.update()` and KB refresh.
