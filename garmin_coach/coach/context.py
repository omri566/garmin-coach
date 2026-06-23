"""Assemble the athlete's current state into a compact brief for the coach LLM.

Only computed summaries/trends go in — never raw per-second rows — so the prompt
stays small and grounded. Returns both a dict (for code) and a markdown rendering
(for the prompt).
"""
from __future__ import annotations

import datetime as dt

from garmin_coach import profile as prof
from garmin_coach.analytics import load, trends
from garmin_coach.store import db


def _fmt_pace(s):
    return f"{int(s // 60)}:{int(s % 60):02d}/km" if s else "—"


def _recent_runs(n: int = 6) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT start_time, distance_m, avg_pace_s_km, avg_hr, ef, "
            "decoupling_pct, training_stress, avg_cadence_spm, avg_vert_ratio "
            "FROM activity_metrics WHERE sport LIKE '%running%' "
            "ORDER BY start_time DESC LIMIT ?", (n,)).fetchall()
    return [dict(r) for r in rows]


def _recovery() -> dict:
    cutoff = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    with db.connect() as conn:
        latest = conn.execute(
            "SELECT day, hrv_overnight, hrv_status, resting_hr, sleep_score, "
            "readiness_score, body_battery_high FROM health_daily "
            "WHERE hrv_overnight IS NOT NULL OR readiness_score IS NOT NULL "
            "ORDER BY day DESC LIMIT 1").fetchone()
        avgs = conn.execute(
            "SELECT AVG(hrv_overnight), AVG(resting_hr), AVG(sleep_score), "
            "AVG(readiness_score) FROM health_daily WHERE day >= ?",
            (cutoff,)).fetchone()
    return {
        "latest": dict(latest) if latest else {},
        "hrv_7d": avgs[0], "rhr_7d": avgs[1], "sleep_7d": avgs[2], "readiness_7d": avgs[3],
    }


def athlete_brief() -> dict:
    p = prof.load_profile()
    state = load.current_state()
    wv = trends.weekly_volume().tail(4)
    zones = trends.zone_distribution()
    ef = trends.efficiency_trend()
    ef_now = ef["rolling"].dropna().iloc[-1] if not ef.empty and ef["rolling"].notna().any() else None
    ef_90 = ef[ef["date"] >= (dt.datetime.now() - dt.timedelta(days=90))]["ef"].mean() if not ef.empty else None

    return {
        "profile": {
            "age": p.age, "sex": p.sex, "weight_kg": p.weight_kg,
            "hr_max": p.hr_max, "lthr": p.lthr, "resting_hr": p.resting_hr,
            "vo2max": p.vo2max, "threshold_pace": _fmt_pace(p.threshold_pace_s_per_km),
            "hr_zone_floors": p.hr_zone_floors,
        },
        "load": state,
        "weekly_volume": [
            {"week": str(r["date"].date()), "km": round(r["distance_km"], 1),
             "hours": round(r["hours"], 1), "runs": int(r["runs"])}
            for _, r in wv.iterrows()
        ],
        "zone_distribution_12wk": {r["zone"]: round(r["pct"]) for _, r in zones.iterrows()},
        "efficiency": {"ef_rolling_now": round(ef_now, 2) if ef_now else None,
                       "ef_90d_avg": round(ef_90, 2) if ef_90 else None},
        "recovery": _recovery(),
        "recent_runs": _recent_runs(),
    }


def brief_text(brief: dict | None = None) -> str:
    b = brief or athlete_brief()
    p, ld, rec = b["profile"], b["load"], b["recovery"]
    lat = rec.get("latest", {})

    lines = ["# Athlete snapshot", ""]
    lines.append(
        f"Profile: {p['age']}y {p['sex']}, {p['weight_kg']}kg, VO2max {p['vo2max']}, "
        f"HRmax {p['hr_max']}, LTHR {p['lthr']}, resting HR {p['resting_hr']}, "
        f"threshold pace {p['threshold_pace']}.")
    lines.append(
        f"\nTraining load: Fitness(CTL) {ld.get('ctl')}, Fatigue(ATL) {ld.get('atl')}, "
        f"Form(TSB) {ld.get('tsb')}, ACWR {ld.get('acwr')}, ramp {ld.get('ramp')}.")
    vol = ", ".join(f"{w['week']}: {w['km']}km/{w['runs']}r" for w in b["weekly_volume"])
    lines.append(f"\nWeekly volume (last 4): {vol}.")
    zd = ", ".join(f"{k} {v}%" for k, v in b["zone_distribution_12wk"].items())
    lines.append(f"\nHR-zone mix (12wk): {zd}.")
    eff = b["efficiency"]
    lines.append(f"\nAerobic efficiency: EF rolling {eff['ef_rolling_now']} "
                 f"(90d avg {eff['ef_90d_avg']}).")
    lines.append(
        f"\nRecovery (latest {lat.get('day','?')}): HRV {lat.get('hrv_overnight')} "
        f"({lat.get('hrv_status')}), resting HR {lat.get('resting_hr')}, "
        f"sleep {lat.get('sleep_score')}, readiness {lat.get('readiness_score')}. "
        f"7-day avgs: HRV {rec.get('hrv_7d') and round(rec['hrv_7d'])}, "
        f"RHR {rec.get('rhr_7d') and round(rec['rhr_7d'])}, "
        f"readiness {rec.get('readiness_7d') and round(rec['readiness_7d'])}.")
    lines.append("\nRecent runs:")
    for r in b["recent_runs"]:
        lines.append(
            f"  - {r['start_time'][:10]}: {(r['distance_m'] or 0)/1000:.1f}km @ "
            f"{_fmt_pace(r['avg_pace_s_km'])}, HR {r['avg_hr'] and round(r['avg_hr'])}, "
            f"EF {r['ef'] and round(r['ef'],2)}, decoupling "
            f"{r['decoupling_pct'] and round(r['decoupling_pct'],1)}%, "
            f"load {r['training_stress'] and round(r['training_stress'])}.")
    return "\n".join(lines)
