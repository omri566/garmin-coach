"""Plain-English explanations for every metric, shown in hover cards.

Each entry: a short title, what it means, and which direction is desirable so the
dashboard can render a "higher / lower / in-range is better" indicator.
"""
from __future__ import annotations

from dataclasses import dataclass

HIGHER, LOWER, INRANGE, CONTEXT = "higher", "lower", "inrange", "context"

DIRECTION_LABEL = {
    HIGHER: ("Higher is better ↑", "green"),
    LOWER: ("Lower is better ↓", "green"),
    INRANGE: ("Best kept in range", "blue"),
    CONTEXT: ("Depends on context", "gray"),
}


@dataclass(frozen=True)
class Info:
    title: str
    desc: str
    direction: str


METRICS: dict[str, Info] = {
    "ctl": Info(
        "Fitness (CTL)",
        "Chronic Training Load — your rolling 42-day average training stress. A "
        "proxy for aerobic fitness/endurance built up over weeks. Rises slowly "
        "with consistent training; falls when you rest.",
        HIGHER),
    "atl": Info(
        "Fatigue (ATL)",
        "Acute Training Load — rolling 7-day average stress, i.e. recent fatigue. "
        "Not good or bad on its own: high after hard blocks, low when fresh.",
        CONTEXT),
    "tsb": Info(
        "Form (TSB)",
        "Training Stress Balance = Fitness − Fatigue. Positive = fresh/tapered "
        "(good for racing); mildly negative (−10 to −20) is normal and productive "
        "while building. Deeply negative for long = overreaching risk.",
        CONTEXT),
    "acwr": Info(
        "Acute:Chronic Ratio",
        "This week's load vs your recent 4-week norm. 0.8–1.3 is the injury-risk "
        "'sweet spot'. Above ~1.5 means you ramped too fast; well below 0.8 means "
        "detraining.",
        INRANGE),
    "vo2max": Info(
        "VO₂max",
        "Estimated maximal oxygen uptake (ml/kg/min) — the single best lab proxy "
        "for aerobic engine size. Garmin estimates it from pace-vs-HR. Higher = "
        "fitter.",
        HIGHER),
    "readiness": Info(
        "Training Readiness",
        "Garmin's 0–100 readiness from sleep, HRV, recovery time, stress and "
        "load. Higher = better primed for a hard session today.",
        HIGHER),
    "hrv": Info(
        "HRV (overnight)",
        "Heart-rate variability, ms (rMSSD-based). Reflects autonomic recovery. "
        "Higher relative to YOUR baseline = well recovered; a drop signals fatigue "
        "or illness. Compare to your own trend, not others.",
        HIGHER),
    "rhr": Info(
        "Resting HR",
        "Beats per minute at rest. Falls as aerobic fitness improves; a sudden "
        "rise can flag fatigue, illness or under-recovery.",
        LOWER),
    # Per-run metrics
    "pace": Info("Pace", "Time per kilometre. Lower = faster. Judge against the "
                 "run's purpose (easy vs workout), not in isolation.", CONTEXT),
    "ef": Info(
        "Efficiency Factor (EF)",
        "Speed per heartbeat (m/min ÷ avg HR) on aerobic runs. Rising over weeks "
        "at the same HR = improving aerobic efficiency. Higher is better.",
        HIGHER),
    "decoupling": Info(
        "Aerobic Decoupling (Pa:Hr)",
        "How much your pace-to-HR drifts from the 1st to 2nd half of a run. Under "
        "~5% = good aerobic durability. Higher means you faded — too hard, heat, "
        "fatigue or low fitness for the distance.",
        LOWER),
    "cadence": Info(
        "Cadence",
        "Steps per minute. Most runners are efficient around 170–185. Too low "
        "often means overstriding; very high isn't automatically better.",
        INRANGE),
    "vert_ratio": Info(
        "Vertical Ratio",
        "Vertical oscillation as a % of stride length — bounce per distance. Lower "
        "= less wasted vertical motion = more efficient. ~6–8% is excellent.",
        LOWER),
    "gct": Info(
        "Ground Contact Time",
        "Milliseconds each foot stays on the ground. Lower generally means a "
        "springier, faster stride. Elites are ~200ms; ~250–300ms is typical.",
        LOWER),
    "gct_balance": Info(
        "GCT Balance",
        "Left/right split of ground-contact time. Closer to 50/50 is better; a "
        "persistent imbalance can hint at asymmetry or niggles.",
        INRANGE),
    "step_len": Info(
        "Step Length",
        "Distance covered per step (mm). Driven by speed and mechanics; longer at "
        "a given cadence means more speed, but don't force it. Context-dependent.",
        CONTEXT),
    "load": Info(
        "Training Load",
        "Single-session training stress (Garmin load where available, else TRIMP). "
        "Drives the Fitness/Fatigue model. Higher = harder session.",
        CONTEXT),
    # Chart panels
    "chart_fitness_form": Info(
        "Fitness · Fatigue · Form",
        "Blue = Fitness (CTL, slow 42-day load), orange = Fatigue (ATL, fast "
        "7-day load), bars = Form (TSB = fitness − fatigue): green when fresh, red "
        "when fatigued. Build fitness while keeping fatigue manageable; aim for "
        "positive form before key races.",
        CONTEXT),
    "chart_acwr": Info(
        "Training-load ratio (ACWR)",
        "This week's load ÷ your 4-week norm, over time. Keep it inside the shaded "
        "0.8–1.3 band: spikes above raise injury risk, sustained lows mean "
        "detraining.",
        INRANGE),
    "chart_volume": Info(
        "Weekly volume",
        "Running distance (bars) and time (line) per week. Look for gradual, "
        "consistent progression — avoid large week-to-week jumps in volume.",
        CONTEXT),
    "chart_zones": Info(
        "HR-zone mix",
        "Share of running time in each heart-rate zone over the last 12 weeks. "
        "Most endurance plans favour lots of easy Z1–Z2 and relatively little "
        "middle Z3 ('polarized' / 80-20 training).",
        CONTEXT),
    "chart_ef": Info(
        "Aerobic efficiency (EF) trend",
        "Efficiency Factor on aerobic runs over time, with a rolling trend line. "
        "Rising = you're running faster at the same heart rate, i.e. aerobic "
        "fitness improving.",
        HIGHER),
    "chart_vo2": Info(
        "VO₂max trend",
        "Garmin's VO₂max estimate over time. An upward trend means improving "
        "aerobic capacity (engine size).",
        HIGHER),
}
