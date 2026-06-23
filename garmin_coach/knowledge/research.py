"""Deep-research pass that builds the cited knowledge base.

Runs the web-enabled LLM provider once per topic to extract evidence-based
guidance with citations, then saves a new versioned KB. This is the slow,
periodic job (every few months) — recommendations read the cached KB, never
trigger research themselves.

Usage:
    python -m garmin_coach.knowledge.research                 # full build
    python -m garmin_coach.knowledge.research --topics 2      # quick validate
"""
from __future__ import annotations

import argparse
import logging

from garmin_coach.knowledge import kb
from garmin_coach.llm import get_provider

log = logging.getLogger(__name__)

# Metric keys the KB can tag entries with (match our analytics).
METRIC_KEYS = [
    "ctl", "atl", "tsb", "acwr", "vo2max", "ef", "decoupling", "cadence",
    "vert_ratio", "gct", "gct_balance", "hrv", "resting_hr", "readiness",
    "threshold", "polarization", "periodization",
]

TOPICS = [
    "Polarized vs threshold training intensity distribution (80/20 rule) for distance runners",
    "Acute:chronic workload ratio (ACWR) and running injury risk; safe load progression",
    "Fitness-Fatigue model (CTL/ATL/TSB) interpretation, form, and race tapering",
    "HRV-guided training and autonomic recovery monitoring for endurance athletes",
    "Running economy and technique: cadence, vertical oscillation/ratio, ground contact time",
    "Aerobic decoupling (Pa:Hr) as a marker of durability and aerobic fitness",
    "Periodization for a goal race: base, build, peak, and taper phases",
    "Developing lactate threshold and VO2max in distance runners",
    "Easy-run intensity, aerobic base building, and the cost of the 'grey zone'",
    "Recovery monitoring with sleep, resting heart rate, and readiness for runners",
]

ENTRY_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "summary": {"type": "string",
                    "description": "2-4 sentence evidence-based principle"},
        "guidance": {"type": "array", "items": {"type": "string"},
                     "description": "3-6 concrete, actionable coaching bullets"},
        "metrics": {"type": "array", "items": {"type": "string"},
                    "description": f"relevant keys from: {METRIC_KEYS}"},
        "citations": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "url": {"type": "string"},
                "year": {"type": "integer"},
                "finding": {"type": "string"},
            },
            "required": ["source", "finding"],
        }},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["topic", "summary", "guidance", "citations", "confidence"],
}

SYSTEM = (
    "You are a sports scientist building a citable knowledge base for an "
    "endurance-running coach. Prefer peer-reviewed studies and well-established "
    "physiologists/coaches (e.g. Seiler, Coggan, Daniels, Laursen, Gabbett). Be "
    "precise and evidence-based; include real citations with sources/years. Do "
    "not invent references."
)


def research_topic(provider, topic: str, model: str | None = None) -> dict:
    prompt = (
        f"Research the current sport-science evidence on: {topic}.\n\n"
        "Use web search to find authoritative sources, then distil the practical, "
        "evidence-based guidance an endurance coach should apply. Tag the entry "
        f"with any relevant metric keys from this list: {METRIC_KEYS}."
    )
    entry = provider.generate_json(prompt, ENTRY_SCHEMA, system=SYSTEM,
                                   model=model, allow_web=True, timeout=600)
    entry.setdefault("topic", topic)
    return entry


def build_kb(topics: list[str] | None = None, provider=None,
             model: str | None = None) -> dict:
    provider = provider or get_provider("claude")
    topics = topics or TOPICS
    entries = []
    for i, topic in enumerate(topics, 1):
        log.info("[%d/%d] researching: %s", i, len(topics), topic)
        try:
            entries.append(research_topic(provider, topic, model=model))
        except Exception as exc:  # noqa: BLE001
            log.warning("  topic failed: %s", exc)
    doc = kb.save_kb(entries, meta={"model": model or "default",
                                    "n_topics": len(topics)})
    log.info("saved KB v%d with %d entries", doc["version"], len(entries))
    return doc


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description="Build the cited knowledge base.")
    p.add_argument("--topics", type=int, help="Limit to first N topics (testing).")
    p.add_argument("--model", type=str, help="Model override (e.g. opus, sonnet).")
    args = p.parse_args()
    topics = TOPICS[: args.topics] if args.topics else TOPICS
    build_kb(topics=topics, model=args.model)


if __name__ == "__main__":
    main()
