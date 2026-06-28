# Exact change ledger: `kb_v2.json` → `kb_v3.json`

Date: 2026-06-28

Files:

- Old: `data/knowledge/kb_v2.json`
- New: `data/knowledge/kb_v3.json`
- Active pointer: `data/knowledge/current.json` contains `{"version": 2}`. Version 3 is retained as an inactive research draft.

For a literal line-by-line JSON diff, run:

```bash
diff -u data/knowledge/kb_v2.json data/knowledge/kb_v3.json
```

## Global changes

| Field | v2 | v3 |
|---|---:|---:|
| Version | 2 | 3 |
| Topics | 10 | 10 |
| Guidance items | 61 | 60 |
| Citations | 57 | 42 |
| High-confidence entries | 9 | 3 |
| Medium-confidence entries | 1 | 7 |
| Build method | LLM `default` | `human-reviewed evidence synthesis` |

Added metadata:

- `replaces_version`
- `reviewed_at`
- `evidence_policy`
- `material_changes`

Evidence-policy changes:

- Systematic reviews, meta-analyses, consensus statements, and peer-reviewed original studies are preferred.
- Commercial help pages and ResearchGate mirrors were removed.
- Association is now distinguished from causation.
- Population and measurement limitations are stated.
- A favorable paper no longer automatically makes the whole topic `high` confidence.

## Entry 1: training intensity distribution

Topic renamed from:

> Polarized vs. threshold training intensity distribution (the 80/20 rule) for distance runners

to:

> Training intensity distribution for distance runners: polarized, pyramidal, and threshold work

Confidence: `high` → `medium`  
Citations: 6 → 4

Removed or reversed:

- Removed the prescriptive `75-85% easy / 15-20% hard` target.
- Removed the universal recommendation for `2-3 quality sessions per week`.
- Removed the claim that moderate training is generally a harmful gray zone.
- Removed ACWR `0.8-1.3` and TSB as controls for intensity distribution.
- Removed nasal breathing as a boundary-setting method.
- Removed the claim that polarized training is generally superior for performance.

Added:

- Explicit warning that 80/20 changes with session-goal versus time-in-zone measurement.
- Pyramidal training and purposeful LT1-LT2 work are treated as legitimate.
- Recreational runners are advised to start with one quality session and progress by demonstrated tolerance.
- Outcomes include adherence, performance, threshold/economy, symptoms, and individual response—not VO2max alone.
- 2024 Oliveira meta-analysis and 2022 Casado runner-specific systematic review are central evidence.

## Entry 2: ACWR and injury risk

Topic renamed from:

> Acute:chronic workload ratio (ACWR) and running injury risk; safe load progression

to:

> Training-load progression and running-related injury: ACWR limitations and session spikes

Confidence: `medium` → `high` for the conclusion that ACWR is unsuitable as a causal injury-control rule  
Citations: 6 → 5

Removed or reversed:

- Removed the `0.8-1.3` sweet spot.
- Removed the recommendation to use exponentially weighted ACWR as an injury flag.
- Removed `1.3-1.5` as an actionable danger range.
- Removed the classic weekly 10% rule as a safety ceiling.
- Removed the statement that high chronic workload is inherently protective.

Added:

- Explicit instruction that ACWR must not approve, reject, or automatically modify workouts.
- Added the 2025 Frandsen cohort: 5,205 runners and 588,071 sessions.
- Added single-session distance relative to the longest run in the prior 30 days as a contextual review signal.
- The observed >10% association is explicitly labeled observational, not a universal injury boundary.
- Added multifactorial review and symptom-based stop/escalation criteria.
- Corrected the Impellizzeri citation to the 2020 paper and its actual authors.

## Entry 3: CTL/ATL/TSB and tapering

Topic renamed from:

> Fitness-Fatigue Model (CTL/ATL/TSB): Interpretation, Form, and Race Tapering

to:

> CTL, ATL, and TSB as workload heuristics; evidence-based tapering

Confidence: `high` → `medium`  
Citations: 5 → 4

Removed or reversed:

- Removed the claim that CTL measures fitness, ATL measures fatigue, and TSB measures form.
- Removed `TSB below -30`, `-10 to -30`, and race-day `+5 to +25` ranges.
- Removed the recommendation to build fitness by raising CTL.
- Removed TrainingPeaks as an evidence source.

Retained with qualification:

- CTL/ATL/TSB remain useful visual summaries of one consistently measured load input.
- The 41-60% taper volume reduction and maintained intensity are retained because meta-analytic support is substantially stronger.

Added:

- The 2025 Marchal analysis of poor fitness-fatigue model identifiability and predictive behavior.
- Explicit prohibition on mixing Garmin load, TRIMP, rTSS, and session-RPE on one continuous scale.
- Athlete-history calibration instead of universal form ranges.
- Corrected Mujika PubMed identifier to `20840559`.

## Entry 4: HRV-guided training

Topic shortened from:

> HRV-guided training and autonomic recovery monitoring for endurance athletes

to:

> HRV-guided training and autonomic recovery monitoring

Confidence: `high` → `medium`  
Citations: 6 → 4

Removed or reversed:

- Removed the claim that HRV-guided training often outperforms fixed training.
- Removed a deterministic rule to schedule hard work when HRV is normal and easy/rest when it is low.
- Removed `mean ± 0.5 SD` as a universal normal band.
- Removed collapsing HRV coefficient of variation as an early overtraining diagnosis.
- Removed ACWR/TSB cross-checking as injury/recovery confirmation.
- Removed single case-comparison evidence from the core recommendations.

Added:

- Exact 2021 meta-analysis conclusion: clearer vagal-HRV benefit, but small and statistically non-significant average fitness/performance advantages.
- 2025 Ranieri runner trial: all approaches improved, with no group-by-time interaction.
- Device/method continuity and multi-day personal baselines.
- Illness, alcohol, travel, heat, menstrual-cycle context, sleep, stress, and data quality as confounders.
- Subjective recovery as a first-class input.

## Entry 5: cadence and running dynamics

Topic renamed from:

> Running economy and technique: cadence, vertical oscillation/ratio, ground contact time

to:

> Running economy and wearable technique metrics: cadence, vertical motion, and ground contact

Confidence remains `high`, but for the conclusion that these metrics require cautious contextual interpretation.  
Guidance items: 7 → 6  
Citations: 5 → 4

Removed or reversed:

- Removed `170-185 spm` as a typical target range.
- Removed elite `6-8 cm` oscillation and `<200 ms` ground-contact reference targets.
- Removed the claim that a 5-10% cadence increase improves injury risk.
- Removed the claim that shorter GCT and lower vertical motion are consistently better economy targets.
- Removed persistent GCT balance as an injury/compensation flag.
- Removed a thesis and a ResearchGate source.

Added:

- 2024 Van Hooren meta-analysis: cadence association was small, vertical displacement moderate, and pooled GCT association trivial.
- 2022 Anderson meta-analysis: cadence changes alter biomechanics, but long-term injury/performance evidence is insufficient.
- Speed, grade, terrain, footwear, fatigue, device, and sensor placement as mandatory comparison context.
- Strength training has stronger intervention evidence for economy than generic wearable form cues.

## Entry 6: Pa:Hr decoupling and durability

Topic renamed from:

> Aerobic decoupling (Pa:Hr) as a marker of durability and aerobic fitness

to:

> Cardiovascular drift, Pa:Hr decoupling, and endurance durability

Confidence: `high` → `medium`  
Citations: 5 → 4

Removed or reversed:

- Removed `<5% = base established`, `5-10% = developing`, and `>10% = underdeveloped` categories.
- Removed Pa:Hr as a clearance gate for adding intensity.
- Removed the claim that declining Pa:Hr is a clear aerobic-base-development signal.
- Removed TrainingPeaks as the source for the 5% rule.
- Removed claims that low/high intensity training findings directly validate Pa:Hr.
- Removed anomalous v2 fields `"type": "object"` and empty `summary_note`.

Added:

- Pa:Hr is defined as a field calculation, not a validated direct measure of durability.
- Heat, hydration, terrain, pacing, duration, fatigue, and measurement error are explicit confounders.
- 2025 Hunter methodological review and 2021 Maunder durability definition.
- Coyle cardiovascular-drift physiology and Wingo heat-confounding evidence.
- Standardization requirements and prohibition on pass/fail labels.

## Entry 7: race periodization

Topic renamed from:

> Periodization for a goal race: base, build, peak, and taper phases

to:

> Periodization for a goal race: preparation, specificity, and taper

Confidence: `high` → `medium`  
Citations: 6 → 4

Removed or reversed:

- Removed a rigid base/build/peak/taper template as evidence-proven.
- Removed mandatory 80/20 base training.
- Removed ACWR `0.8-1.3` and `>=1.5` injury claims.
- Removed the assertion that middle-zone work offers no advantage.
- Removed fixed positive TSB as the race-day goal.
- Removed the unsupported claim that runners generally need longer tapers than cyclists.

Added:

- Start from recently tolerated frequency, long run, and intensity.
- Preparation, specificity, and taper are functions, not fixed calendar blocks.
- Pyramidal and polarized patterns are selectable rather than mandatory.
- Plan revision is required when symptoms, illness, travel, recovery, or completion invalidate assumptions.
- Taper recommendations remain, supported by the 2023 meta-analysis.

## Entry 8: threshold and VO2max

Topic changed from:

> Developing lactate threshold and VO2max in distance runners

to:

> Developing lactate-threshold performance and VO2max in distance runners

Confidence: `high` → `medium`  
Citations: 6 → 4

Removed or reversed:

- Removed fixed `<2 mmol/L` and `2-4.5 mmol/L` as universal zone/prescription boundaries.
- Removed `90-95% HRmax/vVO2max` as a universal interval prescription.
- Removed the claim that short intervals are inferior for long-term VO2max development.
- Removed the Stöggl `+11.7%` result as a general prescription.
- Removed the implied endorsement of three to four threshold sessions plus one VO2 session per week.
- Removed a narrative review from the Montenegrin journal.

Added:

- 2021 Parmar review: interval dose-response in trained runners remains equivocal.
- 2026 Schoenmakers meta-analysis: longer intervals create more acute time near VO2max, but long-term adaptation is not established by that metric.
- Explicit warning that elite double-threshold practice is descriptive and should not be copied into recreational plans.
- Corrected lactate-guided paper PMID to `36900796`.
- Conservative progression and quality-session limits for recreational runners.

## Entry 9: easy running and the “gray zone”

Topic renamed from:

> Easy-run intensity, aerobic base building, and the cost of the 'grey zone'

to:

> Easy running, aerobic development, and purposeful moderate intensity

Confidence: `high` → `medium`  
Citations: 5 → 4

Removed or reversed:

- Removed the claim that moderate running accumulates fatigue faster than adaptation.
- Removed the claim that polarized training generally outperforms pyramidal or threshold work.
- Removed `<75% HRmax`, `<2 mmol/L`, and an exact 80/20 target as universal easy-run rules.
- Removed the rule to default every session to clearly easy or clearly hard.
- Removed `<5%` decoupling as proof of aerobic-base progress.
- Removed DFA-a1 as a production-ready intensity-setting recommendation.

Added:

- Clear distinction between purposeful moderate training and accidental pace drift.
- Talk test, RPE, field response, and valid LT1/VT1 evidence are combined.
- Efficiency factor and Pa:Hr are explicitly condition-sensitive and non-diagnostic.
- Elite runner evidence for commonly pyramidal distributions is included.

## Entry 10: recovery and sleep

Topic renamed from:

> Recovery monitoring with sleep, resting heart rate, and readiness for runners

to:

> Recovery monitoring with sleep, resting heart rate, HRV, readiness, and subjective state

Confidence remains `high` for the multi-signal, non-diagnostic conclusion.  
Citations: 7 → 5

Removed or reversed:

- Removed `±0.5 × coefficient of variation` as a universal smallest-worthwhile-change band.
- Removed hard HRV-based substitution rules.
- Removed low HRV/high RHR and unusually high/flat HRV as overtraining diagnoses.
- Removed `8+ hours` as a universal athlete sleep target.
- Removed the youth `<8 h ≈ 1.7× injury` result from adult runner guidance.
- Removed exact `3-10%` performance-loss claims.
- Removed ResearchGate and lower-priority duplicate HRV sources.

Added:

- Subjective fatigue, soreness/pain, stress, illness, and motivation check-in.
- 2021 athlete sleep consensus: sleep need should be individualized.
- 2023 endurance sleep-deprivation meta-analysis.
- 2026 wearable-versus-polysomnography meta-analysis: wearables overestimate sleep/efficiency, underestimate waking, and are not diagnostic.
- Explicit warning that Garmin readiness, sleep stages, and Body Battery are proprietary estimates.
- Clinical escalation for persistent or serious symptoms rather than an AI training response.

## Runtime status

Version 3 is retained for private review, but is not active. `data/knowledge/current.json` contains:

```json
{"version": 2}
```

The existing `load_kb()` and `kb_context()` code therefore load v2. No application code was changed.
