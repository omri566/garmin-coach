"""Recommendation engine: science-backed guidance over the athlete's real data.

Combines the athlete snapshot (coach/context) with the cited knowledge base
(knowledge/kb) and asks the LLM for specific, prioritised, cited recommendations.
You-in-the-loop: this proposes; the dashboard presents it for review. Results are
saved (timestamped + latest) so the UI reads them without re-running the LLM.

Usage:
    python -m garmin_coach.coach.recommend
    python -m garmin_coach.coach.recommend --goal "sub-50 10k in October"
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

REC_DIR = config.DATA_DIR / "recommendations"

SYSTEM = (
    "You are an evidence-based endurance running coach. Use ONLY the athlete's "
    "data and the provided knowledge base. Give specific, personal, actionable "
    "guidance — not generic tips. Cite the knowledge-base sources that justify "
    "each recommendation. Be honest about uncertainty and flag risks. You are "
    "advising a human who will review and approve — propose, don't dictate."
)

REC_SCHEMA = {
    "type": "object",
    "properties": {
        "assessment": {"type": "string",
                       "description": "2-4 sentence read of current fitness, fatigue, recovery and trajectory"},
        "flags": {"type": "array", "items": {"type": "string"},
                  "description": "specific warnings grounded in the data (e.g. high decoupling, ACWR, low HRV)"},
        "recommendations": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                "horizon": {"type": "string", "enum": ["today", "this_week", "this_block"]},
                "rationale": {"type": "string", "description": "why, tied to the athlete's numbers"},
                "action": {"type": "string", "description": "the concrete thing to do"},
                "citations": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "priority", "horizon", "rationale", "action"],
        }},
    },
    "required": ["assessment", "flags", "recommendations"],
}


def recommend(goal: str | None = None, provider=None, model: str | None = None) -> dict:
    provider = provider or get_provider("claude")
    brief = context.brief_text()
    science = kb.kb_context() or "(knowledge base not built yet — rely on established models.)"

    goal_line = f"\nAthlete's stated goal: {goal}\n" if goal else ""
    prompt = (
        f"{brief}\n{goal_line}\n"
        f"# Evidence base (cite these by source name)\n{science}\n\n"
        "Assess this athlete's current state and give prioritised, cited "
        "recommendations. Ground every point in their actual numbers above, and "
        "reference the evidence base where it applies."
    )
    result = provider.generate_json(prompt, REC_SCHEMA, system=SYSTEM, model=model)
    result["generated_at"] = dt.datetime.now().isoformat(timespec="seconds")
    result["goal"] = goal
    result["kb_version"] = (kb.load_kb() or {}).get("version")
    _save(result)
    return result


def _save(result: dict) -> None:
    REC_DIR.mkdir(parents=True, exist_ok=True)
    stamp = result["generated_at"].replace(":", "").replace("-", "")
    (REC_DIR / f"rec_{stamp}.json").write_text(json.dumps(result, indent=2))
    (REC_DIR / "latest.json").write_text(json.dumps(result, indent=2))


def load_latest() -> dict | None:
    path = REC_DIR / "latest.json"
    return json.loads(path.read_text()) if path.exists() else None


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description="Generate coaching recommendations.")
    p.add_argument("--goal", type=str, help="Optional training goal to tailor advice.")
    p.add_argument("--model", type=str, help="Model override.")
    args = p.parse_args()
    log.info("Generating recommendations…")
    res = recommend(goal=args.goal, model=args.model)
    log.info("\n=== ASSESSMENT ===\n%s", res["assessment"])
    log.info("\n=== FLAGS ===\n%s", "\n".join(f"⚠ {f}" for f in res["flags"]))
    log.info("\n=== RECOMMENDATIONS ===")
    for r in res["recommendations"]:
        log.info("\n[%s · %s] %s\n  → %s\n  why: %s\n  cite: %s",
                 r["priority"].upper(), r["horizon"], r["title"], r["action"],
                 r["rationale"], "; ".join(r.get("citations", [])))


if __name__ == "__main__":
    main()
