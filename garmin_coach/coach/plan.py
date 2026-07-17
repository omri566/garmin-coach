"""Goal-driven adaptive training plan.

Assesses current state (coach/context) + science (knowledge/kb) and proposes a
3-month macro plan plus a detailed next month. You-in-the-loop: it's a proposal;
regenerating after new data adapts it to actual completed load and recovery.

Usage:
    python -m garmin_coach.coach.plan --goal "sub-50 10k" --date 2026-10-15
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging

from garmin_coach import config
from garmin_coach.coach import context
from garmin_coach.knowledge import kb
from garmin_coach.llm import get_provider

log = logging.getLogger(__name__)

PLAN_DIR = config.DATA_DIR / "plans"

SYSTEM = (
    "You are an evidence-based endurance running coach building a periodized "
    "plan. Respect the athlete's CURRENT fitness, fatigue, recovery and injury "
    "risk — progress gradually (ACWR-aware), favour a polarized 80/20 intensity "
    "distribution, and tie phases to the goal. Use the knowledge base to justify "
    "structure. Be specific and realistic; this will be reviewed by the athlete."
)

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "goal": {"type": "string"},
        "assessment": {"type": "string",
                       "description": "current readiness for this goal, grounded in the data"},
        "macro": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "phase": {"type": "string", "description": "e.g. Base, Build, Peak, Taper"},
                "weeks": {"type": "string", "description": "e.g. 'weeks 1-4'"},
                "focus": {"type": "string"},
                "weekly_volume_km": {"type": "string", "description": "target range"},
                "key_workouts": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["phase", "weeks", "focus"],
        }},
        "next_month": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "week": {"type": "string",
                         "description": "e.g. 'Week 1 (Jun 28 – Jul 4)'. Each "
                         "training week runs Sunday→Saturday: start on a Sunday, "
                         "end the following Saturday."},
                "theme": {"type": "string"},
                "target_volume_km": {"type": "string"},
                "sessions": {"type": "array", "items": {
                    "type": "object",
                    "properties": {
                        "day": {"type": "string",
                                "description": "weekday abbr (Sun, Mon … Sat); "
                                "list sessions Sunday→Saturday"},
                        "type": {"type": "string",
                                 "description": "easy / long / tempo / intervals / rest / cross"},
                        "description": {"type": "string"},
                        "target": {"type": "string",
                                   "description": "pace/HR-zone/duration target"},
                    },
                    "required": ["day", "type", "description"],
                }},
            },
            "required": ["week", "theme", "sessions"],
        }},
        "adaptation_notes": {"type": "array", "items": {"type": "string"},
                             "description": "how the plan should change based on recovery/adherence"},
    },
    "required": ["goal", "assessment", "macro", "next_month", "adaptation_notes"],
}


# The next phase's detailed weeks reuse the exact next_month week shape, plus a
# short debrief of the phase just finished (congrats + what to improve next).
ADVANCE_SCHEMA = {
    "type": "object",
    "properties": {
        "weeks": PLAN_SCHEMA["properties"]["next_month"],
        "debrief": {
            "type": "object",
            "properties": {
                "headline": {"type": "string",
                             "description": "one-line congratulations on the phase just finished"},
                "improve": {"type": "array", "items": {"type": "string"},
                            "description": "2-3 specific things to do better in the next phase, from the data"},
            },
            "required": ["headline", "improve"],
        },
    },
    "required": ["weeks", "debrief"],
}


def make_plan(goal: str, goal_date: str | None = None, provider=None,
              model: str | None = None,
              preferred_days: list[str] | None = None) -> dict:
    provider = provider or get_provider("claude")
    brief = context.brief_text()
    science = kb.kb_context(metrics=["periodization", "polarization", "acwr",
                                     "threshold", "vo2max"]) or "(use established models.)"
    date_line = f" Target date: {goal_date}." if goal_date else ""
    days_line = ""
    if preferred_days:
        days_line = (f"\n\nThe athlete prefers to run on: {', '.join(preferred_days)}. "
                     "Place running sessions on these weekdays and rest on the "
                     "others, unless sound training principles require otherwise.")
    prompt = (
        f"{brief}\n\nGOAL: {goal}.{date_line}{days_line}\n\n"
        f"# Evidence base (cite where relevant)\n{science}\n\n"
        "Design a ~3-month periodized macro plan and a detailed next-month plan "
        "(specific weekly sessions). Start from the athlete's CURRENT volume and "
        "fitness — do not jump load. Favour 80/20 polarized intensity. "
        "Training weeks run Sunday→Saturday: label each next-month week with its "
        "Sunday-start and Saturday-end dates, and order its sessions Sun→Sat."
    )
    plan = provider.generate_json(prompt, PLAN_SCHEMA, system=SYSTEM, model=model)
    plan["goal_date"] = goal_date
    plan["preferred_days"] = preferred_days or []
    plan["generated_at"] = dt.datetime.now().isoformat(timespec="seconds")
    plan["kb_version"] = (kb.load_kb() or {}).get("version")
    if preferred_days:
        apply_preferred_days(plan, preferred_days)   # honour the days exactly
    _save(plan)
    return plan


_WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def apply_preferred_days(plan: dict, preferred_days: list[str]) -> dict:
    """Re-lay out each next-month week's running sessions onto the preferred
    weekdays (spread evenly across them), so the existing plan reflects the
    athlete's chosen days without regenerating. Date moves are cleared (the new
    days take effect); done/skipped history is kept. Manual drags afterwards
    still override per session. Persists in place via save_latest."""
    pref = [d for d in _WEEKDAYS if d in set(preferred_days)]
    if not pref:
        return plan
    for wk in plan.get("next_month", []):
        runs = [s for s in wk.get("sessions", [])
                if (s.get("type") or "").lower() != "rest"]
        k = len(runs)
        if not k:
            continue
        if k <= len(pref):
            idxs = [0] if k == 1 else [round(j * (len(pref) - 1) / (k - 1))
                                       for j in range(k)]
            chosen = [pref[i] for i in idxs]
        else:                              # more runs than preferred days
            chosen = pref + [r.get("day") for r in runs[len(pref):]]
        for s, day in zip(runs, chosen):
            s["day"] = day
    # Clear prior date moves so the new default days show; keep done/skipped.
    overrides = plan.get("overrides", {})
    for key in list(overrides):
        overrides[key].pop("date", None)
        if not overrides[key]:
            overrides.pop(key)
    plan["preferred_days"] = pref
    save_latest(plan)
    return plan


def phase_status(plan: dict | None, today: dt.date | None = None) -> dict:
    """Where the athlete is in the macro plan: has the current detailed block
    finished, and is there a next phase to advance into.

    `block_finished` — today is past the last `next_month` week's Saturday.
    `current_phase` / `next_phase` — from `macro[phase_index]` and the one after.
    """
    from garmin_coach.coach import schedule
    today = today or dt.date.today()
    macro = (plan or {}).get("macro") or []
    idx = (plan or {}).get("phase_index", 0)
    current_phase = macro[idx] if 0 <= idx < len(macro) else None
    next_phase = macro[idx + 1] if idx + 1 < len(macro) else None
    weeks = schedule.build_schedule(plan, today).get("weeks") if plan else []
    last_end = max((w["end"] for w in weeks), default=None)
    block_finished = bool(last_end and today > last_end)
    return {"block_finished": block_finished, "current_phase": current_phase,
            "next_phase": next_phase, "next_index": (idx + 1) if next_phase else None,
            "is_last": block_finished and next_phase is None}


def advance_phase(plan: dict | None = None, provider=None,
                  model: str | None = None) -> dict | None:
    """Generate the next macro phase's detailed 4-week block once the current block
    is finished, plus a debrief of the phase just completed. Idempotent: if the
    block isn't finished (or there's no next phase), returns the plan unchanged.
    """
    from garmin_coach.coach import context, schedule
    plan = plan if plan is not None else load_latest()
    if plan is None:
        return None
    status = phase_status(plan)
    if not status["block_finished"] or not status["next_phase"]:
        return plan

    cur, nxt = status["current_phase"] or {}, status["next_phase"]
    weeks = schedule.build_schedule(plan)["weeks"]
    next_start = max(w["end"] for w in weeks) + dt.timedelta(days=1)  # the next Sunday
    provider = provider or get_provider("claude")
    prompt = (
        f"{context.brief_text()}\n\nGOAL: {plan.get('goal', '')}.\n\n"
        f"The athlete just finished the '{cur.get('phase', '')}' phase and is moving "
        f"into '{nxt.get('phase', '')}' — focus: {nxt.get('focus', '')}; target volume: "
        f"{nxt.get('weekly_volume_km', '')}; key workouts: "
        f"{', '.join(nxt.get('key_workouts', []) or [])}.\n\n"
        f"# How the finished block actually went\n{schedule.execution_summary_text(plan)}\n\n"
        f"Design the DETAILED next 4 training weeks for the '{nxt.get('phase', '')}' phase, "
        f"continuing the progression from current fitness — do NOT restart from base. The "
        f"first week starts Sunday {next_start.isoformat()}; label each week with its "
        f"Sunday-start and Saturday-end dates and order sessions Sun→Sat. Also give a short "
        f"debrief of the phase just finished: a one-line headline congratulating the athlete, "
        f"and 2-3 specific things to do better in this next phase, grounded in the data above."
    )
    # Cap under the web server's request timeout so a slow/hung claude surfaces a
    # retryable error instead of the worker being killed mid-request.
    res = provider.generate_json(prompt, ADVANCE_SCHEMA, system=SYSTEM, model=model,
                                 timeout=150)
    debrief = res.get("debrief") or {}
    plan["next_month"] = res.get("weeks") or []
    plan["phase_index"] = status["next_index"]
    plan["phase_debrief"] = {
        "finished_phase": cur.get("phase", ""),
        "phase_index": status["next_index"],
        "headline": (debrief.get("headline") or "").strip(),
        "improve": [s for s in (debrief.get("improve") or []) if s],
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    plan["overrides"] = {}              # old block's "<week>:<session>" keys are stale
    plan.pop("congrats_ack", None)      # let the congrats show for the new phase
    if plan.get("preferred_days"):
        apply_preferred_days(plan, plan["preferred_days"])
    else:
        save_latest(plan)
    return plan


_PREFS_PATH = PLAN_DIR / "preferences.json"


def load_prefs() -> dict:
    """Athlete scheduling preferences (e.g. preferred running weekdays)."""
    return json.loads(_PREFS_PATH.read_text()) if _PREFS_PATH.exists() else {}


def save_prefs(prefs: dict) -> None:
    PLAN_DIR.mkdir(parents=True, exist_ok=True)
    _PREFS_PATH.write_text(json.dumps(prefs, indent=2))


def _save(plan: dict) -> None:
    PLAN_DIR.mkdir(parents=True, exist_ok=True)
    stamp = plan["generated_at"].replace(":", "").replace("-", "")
    (PLAN_DIR / f"plan_{stamp}.json").write_text(json.dumps(plan, indent=2))
    (PLAN_DIR / "latest.json").write_text(json.dumps(plan, indent=2))


def load_latest() -> dict | None:
    path = PLAN_DIR / "latest.json"
    return json.loads(path.read_text()) if path.exists() else None


def save_latest(plan: dict) -> None:
    """Persist edits to the active plan in place (no new timestamped snapshot).

    Used by the dashboard for athlete tweaks — rescheduling a session (drag) or
    marking it done/skipped — so the generated plan history stays intact.
    """
    PLAN_DIR.mkdir(parents=True, exist_ok=True)
    (PLAN_DIR / "latest.json").write_text(json.dumps(plan, indent=2))


def set_override(key: str, patch: dict | None) -> dict | None:
    """Merge an override for session `key` ("<week>:<session>") and persist.

    `patch` keys: 'date' (ISO, from drag-reschedule) and/or 'status'
    ('done'/'skipped', manual). A falsy field clears that field; an empty patch
    clears the whole override.
    """
    plan = load_latest()
    if plan is None:
        return None
    overrides = plan.setdefault("overrides", {})
    cur = dict(overrides.get(key, {}))
    for field in ("date", "status"):
        if patch and field in patch:
            if patch[field]:
                cur[field] = patch[field]
            else:
                cur.pop(field, None)
    if cur:
        overrides[key] = cur
    else:
        overrides.pop(key, None)
    save_latest(plan)
    return plan


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description="Generate a goal-driven training plan.")
    p.add_argument("--goal", required=True)
    p.add_argument("--date", help="Goal/race date YYYY-MM-DD.")
    p.add_argument("--model")
    args = p.parse_args()
    log.info("Building plan for: %s", args.goal)
    plan = make_plan(args.goal, goal_date=args.date, model=args.model)
    log.info("\n=== ASSESSMENT ===\n%s", plan["assessment"])
    log.info("\n=== MACRO ===")
    for ph in plan["macro"]:
        log.info("  [%s] %s — %s (vol %s)", ph["weeks"], ph["phase"], ph["focus"],
                 ph.get("weekly_volume_km", "—"))
    log.info("\n=== NEXT MONTH ===")
    for wk in plan["next_month"]:
        log.info("  %s — %s (%s)", wk["week"], wk["theme"], wk.get("target_volume_km", ""))
        for s in wk["sessions"]:
            log.info("     %s: %s — %s [%s]", s["day"], s["type"], s["description"],
                     s.get("target", ""))


if __name__ == "__main__":
    main()
