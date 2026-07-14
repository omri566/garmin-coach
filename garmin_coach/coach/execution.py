"""A short AI 'how you did' read of a run — the coach's post-workout debrief.

The deterministic verdict (overview) judges the work segment vs the target; this
adds a coach's natural-language note that reasons over the whole shape of the run
(warm-up, reps, cool-down). It works for a planned session (structured or easy)
*and* for an unplanned run (no session). Cached per activity — a run's execution
never changes — so the LLM runs at most once per run.
"""
from __future__ import annotations

import datetime as dt
import json

from garmin_coach import config
from garmin_coach.analytics import segments
from garmin_coach.llm import get_provider

_DIR = config.DATA_DIR / "verdicts"

SYSTEM = (
    "You are an experienced running coach giving an honest, specific read of how "
    "an athlete's run went. If a planned workout is given, judge execution against "
    "it — and for a hard/structured session judge the work intervals, not the "
    "whole-run average, since the warm-up and cool-down drag the average pace well "
    "below rep pace. If no plan is given, judge the run on its own terms (easy vs "
    "hard, how it was paced, durability). Return a punchy one-line 'headline' "
    "verdict (max ~9 words, no numbers needed) and a 'detail' of 1-2 sentences with "
    "the specific pace/HR. Encouraging but truthful."
)

NOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string",
                     "description": "punchy one-line verdict, ~9 words max"},
        "detail": {"type": "string",
                   "description": "1-2 sentences with the specific rep numbers"},
    },
    "required": ["headline", "detail"],
}


def _pace(s) -> str:
    return f"{int(s // 60)}:{int(s % 60):02d}/km" if s else "—"


def _path(aid):
    return _DIR / f"{aid}.json"


def cached(aid) -> dict | None:
    p = _path(aid)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def make_note(session: dict | None, run: dict, streams, provider=None,
              model: str | None = None) -> dict:
    """Generate (and cache) the coach's post-workout read of a run.

    `session` is the matched planned session, or None for an unplanned run."""
    aid = run.get("activity_id")
    provider = provider or get_provider("claude")
    seg = segments.best_sustained(streams, 300)
    splits = segments.km_splits(streams)
    seg_txt = (f"fastest sustained {seg['minutes']} min at {_pace(seg['pace_s_km'])}"
               f" (HR {seg['hr'] and round(seg['hr'])})" if seg else "n/a")
    split_txt = " · ".join(_pace(s) for s in splits) if splits else "n/a"
    ran = (f"What they ran: {(run.get('distance_m') or 0) / 1000:.1f} km, "
           f"average {_pace(run.get('avg_pace_s_km'))}, avg HR "
           f"{run.get('avg_hr') and round(run['avg_hr'])}.\n"
           f"Hardest effort: {seg_txt}.\n"
           f"Per-km splits: {split_txt}.\n\n")
    if session:
        target = f"{session.get('target', '')} — {session.get('description', '')}".strip(" —")
        prompt = (
            f"Planned session ({session.get('type')}): {target}\n" + ran +
            "Give a short headline verdict + a 1-2 sentence detail on how well they "
            "executed THIS workout — reference the pace/HR, and (for a hard session) "
            "don't be fooled by the average."
        )
    else:
        target = ""
        decoup = run.get("decoupling_pct")
        prompt = (
            "This run was not part of the plan (an extra/unplanned run).\n" + ran +
            (f"Aerobic decoupling: {decoup:.1f}%.\n" if decoup is not None else "") +
            "Give a short headline verdict + a 1-2 sentence detail on how the run "
            "went on its own terms — pacing, effort, and durability."
        )
    res = provider.generate_json(prompt, NOTE_SCHEMA, system=SYSTEM, model=model)
    out = {"headline": (res.get("headline") or "").strip(),
           "detail": (res.get("detail") or "").strip()}
    _DIR.mkdir(parents=True, exist_ok=True)
    _path(aid).write_text(json.dumps({
        "activity_id": aid, **out, "target": target,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }, indent=2))
    return out


def ensure_note(run: dict, session: dict | None, streams, provider=None,
                model: str | None = None) -> dict | None:
    """The cached post-workout read for this run, generating it once if missing."""
    aid = run.get("activity_id")
    if aid is None:
        return None
    hit = cached(aid)
    if hit:
        return hit
    return make_note(session, run, streams, provider=provider, model=model)
