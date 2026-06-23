# Garmin Coach — System Specification

> Personal endurance analytics & AI coaching built on **maximum-fidelity** Garmin data.
> Single user. Running-primary, cycling secondary. Everything science-backed, validated models + cited research.

Status: **spec locked, stack TBD.**

---

## 0. Foundations (cross-cutting)

- **Single user** (the owner). Running-primary; cycling as a secondary/cross-training sport.
- **Max-fidelity ingest** — keep everything:
  - Raw **FIT files** (per-second / per-record streams: pace, HR, cadence, running dynamics, GPS, grade, temp).
  - Garmin **Connect API** summaries (derived metrics not in the FIT: VO2max, training load, race predictions, readiness).
  - **Daily health metrics** (HRV, resting HR, sleep, body battery, stress).
- **Incremental sync** — never re-fetch; new activities + new health days only.
- **Science-backed + cited** — every metric/recommendation traces to a validated model or a literature source.

### Hardware on record
- Garmin watch (wrist) **+ Running Dynamics source** (HRM-Pro / RD pod).
  - ✅ Full running dynamics: cadence, stride length, vertical oscillation, **vertical ratio**, **ground-contact time + L/R balance**.
  - ⚠️ **Running power** = Garmin wrist estimate → used for *relative/trend* effort only, flagged lower-confidence. No Stryd form-power / leg-spring / running-effectiveness.
  - ⚠️ **Bike** = HR-based load + Garmin estimated power (no cycling power meter) → coarser; mainly feeds cross-training load into CTL/ATL.

### Data history & gap handling
- ~1 year of history **with gaps**. Gaps are a first-class subsystem:
  - Distinguish **"no training" (load = 0, legitimate)** from **"trained-but-unrecorded / device not worn"** (artifact → flagged, optionally manually annotated).
  - Daily health metrics: short gaps interpolated; long gaps left blank with **confidence flags**; rolling baselines tolerate missing days.
  - Trends show **confidence bands**; no trendline drawn below a minimum data density.
  - First ~6 weeks treated as **CTL ramp-in / low-confidence**.

---

## 1. Dashboard (overview)

- **Last-activity card** (run or bike): map, splits, pace/power/HR, technique proxies at a glance.
- **Plan-adherence badge** on the last activity if it maps to a planned session (see §6).
- **Long-trend panels** (weeks → years):
  - **Fitness / Fatigue / Form** — CTL / ATL / TSB (Banister impulse-response) + **ACWR** (acute:chronic, 0.8–1.3 sweet spot).
  - **Aerobic efficiency** — Efficiency Factor (speed ÷ HR), pace-at-HR drift over months.
  - **VO2max**, **lactate-threshold pace/HR**, **race-time predictions**.
  - **Technique trends** — cadence, stride length, vertical oscillation, vertical ratio, GCT + balance, running power.
  - **Zone distribution / polarization** (80/20 check).

## 2. Deep Analysis (per-activity + comparative)

- **Split analysis** — per-km/mi and per-effort; grade-adjusted pace; **HR/power decoupling (Pa:Hr)** for durability/fade.
- **Technique breakdown** — full running-dynamics set vs reference ranges *and* personal baselines; intra-run drift with fatigue.
- **Every meaningful Garmin metric, contextualized** — physiological meaning + science range, not bare numbers.
- **Power/pace–duration curve** & **critical speed/power** estimate from history.

## 3. Plan (goal-driven, adaptive)

- User defines a **goal**. Three supported modes:
  - **Race + date** → full reverse-periodization to race day (base/build/peak/taper).
  - **Performance target** (e.g. sub-20 5k, raise threshold) → open-ended progression, no fixed taper.
  - **General fitness** → base-building + load management.
- AI assesses **current state** (fitness, recent load, recovery, technique limiters) →
  - **3-month macro plan**, polarized 80/20.
  - **Next-month detail** (specific weekly sessions), regenerated as you progress.
- **Adaptive** — re-plans from actual completed load, adherence, and recovery; ramps guided by ACWR, not a fixed template.
- **Autonomy = you-in-the-loop**: AI always *proposes*; nothing changes the plan until approved. Full audit trail of why each change was suggested.

## 4. Health & Recovery integration

- Pull **HRV (rMSSD), resting HR, sleep, body battery, stress, training readiness**.
- Compute a **recovery state** that **gates** plan/recommendations (e.g. suppressed HRV + poor sleep → swap hard day for easy/rest). HRV-guided training logic.

## 5. Recommendations (science-backed)

- Synthesize **all** data into specific, actionable guidance with reasoning + citations — not generic Garmin tips.
- **Layered rigor**:
  - Core engine = validated models (CTL/ATL/TSB, ACWR, 80/20, Riegel/VO2max predictions, EF, decoupling, HRV-guided recovery).
  - Recommendation text = adds **cited sport-science research** on top.
- **Knowledge base**:
  - Built by an **initial deep-research pass** (assembles trusted source list + extracts methods from scratch — done *first*).
  - **Versioned**; refreshed every few months via a new deep-research pass so recommendations are reproducible.

## 6. Plan-adherence / execution scoring

If the last (or any) activity maps to a planned session, grade execution by session type:

- **Easy / recovery** → % time HR stayed in easy zone, pace cap respected, low decoupling.
- **Threshold / tempo** → time-in-target pace/HR/power band + fade.
- **Intervals** → per-rep target-hit rate + recovery completeness.
- **Long run** → duration/distance vs target + durability (decoupling).
- Output: **execution score + "what to adjust next time."**

---

## Open items (pre-build)
- Stack / architecture selection (next step).
- Exact session-type taxonomy + adherence thresholds.
- Knowledge-base source vetting criteria for the deep-research pass.
