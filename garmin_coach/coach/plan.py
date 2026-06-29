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
