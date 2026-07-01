"""Plan execution: anchor planned sessions to real dates, match completed runs.

The generated plan describes sessions by weekday only ("Thu easy 5k"). To know
what's actually *done* — even when a session is run on a different day than
planned — we:

  1. parse each week's date range ("Week 1 (Jun 23 – Jun 29)") into real dates,
  2. give every session a concrete date (its weekday within that range, or a
     user override from drag-to-reschedule),
  3. auto-match completed runs to the nearest compatible (non-rest) session in
     the same week, respecting manual done/skip overrides,
  4. derive a status per session (done / today / upcoming / missed / rest /
     skipped) and a human note for "done early/late".

Overrides (day moves + manual done/skip) live in plan["overrides"], keyed by
"<week_index>:<session_index>", and are persisted by coach.plan.
"""
from __future__ import annotations

import datetime as dt
import re

from garmin_coach.store import db

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEK_START = 6  # training weeks run Sunday -> Saturday (Mon=0 … Sun=6)


def _week_start(d: dt.date) -> dt.date:
    """The Sunday on or before d — the start of d's training week."""
    return d - dt.timedelta(days=(d.weekday() - WEEK_START) % 7)

_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
     "Nov", "Dec"], 1)}
_RANGE = re.compile(
    r"\(\s*([A-Za-z]{3,9})\s+(\d{1,2})\s*[–—-]\s*([A-Za-z]{3,9})\s+(\d{1,2})\s*\)")


def _iso(s: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(s) if s else None
    except (ValueError, TypeError):
        return None


def _run_date(start_time: str) -> dt.date:
    return dt.date.fromisoformat(start_time[:10])


def parse_week_range(week_str: str, base_year: int,
                     ref: dt.date | None = None) -> tuple[dt.date, dt.date] | None:
    """('Week 1 (Jun 23 – Jun 29)', 2026) -> (date(2026,6,23), date(2026,6,29))."""
    m = _RANGE.search(week_str or "")
    if not m:
        return None
    m1, d1, m2, d2 = m.group(1)[:3].title(), int(m.group(2)), m.group(3)[:3].title(), int(m.group(4))
    if m1 not in _MONTHS or m2 not in _MONTHS:
        return None
    start = dt.date(base_year, _MONTHS[m1], d1)
    end = dt.date(base_year, _MONTHS[m2], d2)
    if end < start:                      # range crosses new year
        end = dt.date(base_year + 1, _MONTHS[m2], d2)
    if ref and (ref - start).days > 60:  # plan year inferred wrong → next year
        start = dt.date(start.year + 1, start.month, start.day)
        end = dt.date(end.year + 1, end.month, end.day)
    return start, end


def _session_date(start: dt.date, end: dt.date, day_abbr: str) -> dt.date | None:
    """The actual date within [start, end] whose weekday matches day_abbr."""
    if day_abbr not in DAYS:
        return None
    target = DAYS.index(day_abbr)
    for i in range((end - start).days + 1):
        d = start + dt.timedelta(days=i)
        if d.weekday() == target:
            return d
    return None


def _runs_between(start: dt.date, end: dt.date) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT activity_id, start_time, distance_m, avg_pace_s_km, avg_hr, "
            "training_stress FROM activity_metrics WHERE sport LIKE '%running%' "
            "AND date(start_time) BETWEEN ? AND ? ORDER BY start_time",
            (start.isoformat(), end.isoformat())).fetchall()
    return [dict(r) for r in rows]


def _automatch(sessions: list[dict], runs: list[dict]) -> list[dict]:
    """Link completed runs to the planned sessions they satisfy.

    A run is anchored to the day it was *actually performed* (its real start
    date), never to the day it happened to be synced. Matching runs in two
    passes so a late-synced run can't drift onto a neighbouring day:

      1. Same-day — a run lands on the non-rest session planned for its own day.
         This holds even when the athlete already marked that day done/skipped:
         the run is *consumed* by its own day so it can never spill onto another
         session (the late-sync-matched-the-wrong-day bug).
      2. Nearest — a run with no session on its own day attaches to the closest
         still-open non-rest session in the week ("did the workout a day
         early/late"), preferring an upcoming session on a tie.

    Returns the runs that found no slot (genuine extras). Sessions the athlete
    manually marked done/skipped are never auto-matched over.
    """
    non_rest = [s for s in sessions if (s["type"] or "").lower() != "rest"]
    used: set[int] = set()
    leftover: list[dict] = []

    # Pass 1: anchor each run to a session on the exact day it was run.
    for run in runs:
        rdate = _run_date(run["start_time"])
        same_day = next((s for s in non_rest
                         if s["date"] == rdate and id(s) not in used), None)
        if same_day is None:
            leftover.append(run)
            continue
        used.add(id(same_day))
        # A manually done/skipped day still consumes its own run (no spill), but
        # the athlete's manual status is left untouched.
        if same_day.get("status_override") not in ("done", "skipped"):
            same_day["match"] = run
            same_day["match_date"] = rdate

    # Pass 2: runs with no same-day session attach to the nearest open session.
    slots = [s for s in non_rest
             if id(s) not in used
             and s.get("status_override") not in ("done", "skipped")]
    extras: list[dict] = []
    for run in leftover:
        rdate = _run_date(run["start_time"])
        cands = [s for s in slots if id(s) not in used]
        if not cands:
            extras.append(run)
            continue
        # Nearest session; on a tie prefer the upcoming one ("did it early")
        # over backfilling a past/missed session.
        best = min(cands, key=lambda s: (abs((s["date"] - rdate).days),
                                         0 if s["date"] >= rdate else 1))
        best["match"] = run
        best["match_date"] = rdate
        used.add(id(best))
    return extras


def _status(s: dict, today: dt.date) -> tuple[str, str | None]:
    if s.get("status_override") == "skipped":
        return "skipped", None
    if s.get("status_override") == "done" or s.get("match"):
        note = None
        md = s.get("match_date")
        if md and md != s["date"]:
            note = f"ran {md:%a %-d} (planned {s['date']:%a})"
        return "done", note
    if (s["type"] or "").lower() == "rest":
        return "rest", None
    if s["date"] < today:
        return "missed", None
    if s["date"] == today:
        return "today", None
    return "upcoming", None


def build_schedule(plan: dict, today: dt.date | None = None) -> dict:
    """Full execution view of the plan's next_month, by real dates."""
    today = today or dt.date.today()
    base_year = _iso((plan.get("generated_at") or "")[:10])
    base_year = base_year.year if base_year else today.year
    overrides = plan.get("overrides", {})

    parsed = []
    for wi, wk in enumerate(plan.get("next_month", [])):
        rng = parse_week_range(wk.get("week", ""), base_year, today)
        if not rng:                       # fallback: 7-day block from generation
            anchor = _iso((plan.get("generated_at") or "")[:10]) or today
            rng = (anchor + dt.timedelta(days=7 * wi), None)
        # Snap to a Sunday→Saturday window so the week reads Sun-first.
        start = _week_start(rng[0])
        end = start + dt.timedelta(days=6)
        parsed.append((wi, wk, start, end))

    # Current week = first week whose end is today or later (else the last one).
    cur = next((wi for wi, _, _, e in parsed if e >= today),
               parsed[-1][0] if parsed else 0)

    weeks_out = []
    for wi, wk, start, end in parsed:
        editable = wi in (cur, cur + 1)
        sessions = []
        for si, s in enumerate(wk.get("sessions", [])):
            key = f"{wi}:{si}"
            ov = overrides.get(key, {})
            default = _session_date(start, end, s.get("day"))
            eff = _iso(ov.get("date")) or default or start
            sessions.append({
                "key": key, "week_index": wi,
                "type": s.get("type", ""), "description": s.get("description", ""),
                "target": s.get("target", ""), "day": s.get("day"),
                "date": eff, "status_override": ov.get("status"),
            })
        extras = _automatch(sessions, _runs_between(start, end))
        for s in sessions:
            s["status"], s["note"] = _status(s, today)

        days = []
        for i in range((end - start).days + 1):
            d = start + dt.timedelta(days=i)
            days.append({
                "date": d, "is_today": d == today, "is_past": d < today,
                "sessions": [s for s in sessions if s["date"] == d],
            })
        done = sum(1 for s in sessions
                   if s["status"] == "done" and (s["type"] or "").lower() != "rest")
        total = sum(1 for s in sessions if (s["type"] or "").lower() != "rest")
        base_label = (wk.get("week") or f"Week {wi + 1}").split("(")[0].strip()
        label = f"{base_label or f'Week {wi + 1}'} ({start:%b %-d} – {end:%b %-d})"
        weeks_out.append({
            "week_index": wi, "label": label,
            "theme": wk.get("theme", ""), "target_volume": wk.get("target_volume_km", ""),
            "start": start, "end": end, "editable": editable,
            "is_current": wi == cur, "days": days, "sessions": sessions,
            "done": done, "total": total, "extras": extras,
        })
    return {"weeks": weeks_out, "current_index": cur, "today": today}


def execution_summary_text(plan: dict, today: dt.date | None = None) -> str:
    """Date-anchored 'what's actually done vs left' block for the coach LLM."""
    sched = build_schedule(plan, today)
    today = sched["today"]
    cur = sched["current_index"]
    lines = [f"# Plan execution (real dates; today is {today:%a %Y-%m-%d})",
             "Treat DONE sessions as the planned session completed — do NOT "
             "re-recommend them or count their run as an extra/unplanned session."]
    for wk in sched["weeks"]:
        if wk["week_index"] not in (cur, cur + 1):
            continue
        tag = "THIS WEEK" if wk["is_current"] else "NEXT WEEK"
        lines.append(f"\n## {tag} — {wk['label']} · {wk['theme']} "
                     f"({wk['done']}/{wk['total']} key sessions done)")
        for s in wk["sessions"]:
            st = s["status"].upper()
            extra = f" [{s['note']}]" if s.get("note") else ""
            tgt = f" — {s['target']}" if s.get("target") else ""
            lines.append(f"  - {s['date']:%a %b %-d}: {s['type']} · "
                         f"{s['description']}{tgt} → {st}{extra}")
        if wk["extras"]:
            ex = "; ".join(f"{_run_date(r['start_time']):%b %-d} "
                           f"{(r['distance_m'] or 0) / 1000:.1f}km" for r in wk["extras"])
            lines.append(f"  Extra runs this week not in the plan: {ex}.")
    return "\n".join(lines)
