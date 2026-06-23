# Garmin Coach

Personal endurance analytics & AI coaching on maximum-fidelity Garmin data.
See `SPEC.md` (what) and `ARCHITECTURE.md` (how).

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Sync your data

First run logs in to Garmin interactively (supports MFA) and caches tokens
under `data/.garth` so later runs are non-interactive. Put credentials in `.env`
(copy `.env.example`) to skip the prompt.

**Activities** (raw FIT → per-second streams + summary):
```bash
.venv/bin/python -m garmin_coach.ingest.sync --limit 1     # prove the pipeline
.venv/bin/python -m garmin_coach.ingest.sync --limit 50    # backfill recent
.venv/bin/python -m garmin_coach.ingest.sync --all         # full history
```

**Daily health** (recovery inputs: HRV, resting HR, sleep, body battery, stress, readiness):
```bash
.venv/bin/python -m garmin_coach.ingest.health --days 30
.venv/bin/python -m garmin_coach.ingest.health --days 400   # ~13 months backfill
```

Both are incremental/idempotent: activities already stored are skipped; health
days are re-tried until Garmin finalizes their overnight metrics.

## One-shot update (everything)

```bash
.venv/bin/python -m garmin_coach.pipeline            # sync activities + health, refresh profile, compute features
```

Incremental and safe to re-run — this is what a scheduled job calls.

## Analytics & dashboard

```bash
.venv/bin/python -m garmin_coach.profile             # fetch athlete anchors (one-time / refresh)
.venv/bin/python -m garmin_coach.analytics.compute   # per-activity features (incremental)
.venv/bin/python -m garmin_coach.dashboard.app       # launch dashboard -> http://127.0.0.1:8050
```

### What lands where
- `data/garmin.db` — SQLite: activity summaries + daily health (indexed metrics + full raw JSON).
- `data/streams/<id>.parquet` — dense per-second streams (pace, HR, cadence, running dynamics, GPS…).
- `data/fit/<id>.fit` — raw FIT files, source of truth.

## Status
- **Phase 1 (ingest + storage) — complete.** Activities + daily health, incremental, max-fidelity.
- **Phase 2 (analytics) — core complete.** Per-activity features, CTL/ATL/TSB/ACWR load model, trend layer.
- **Phase 3 (dashboard) — Overview page live.** Fitness/Fatigue/Form, ACWR, last-run card, weekly volume, HR-zone mix, EF & VO₂max trends.
- Next: Deep Analysis page (splits, technique drill-down), then Phase 4 (plan, recommendations, knowledge base).
