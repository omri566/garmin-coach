"""Versioned knowledge base of cited endurance-science guidance.

Each build is a deep-research pass (see research.py) saved as kb_v{N}.json with a
`current.json` pointer, so recommendations are reproducible and the KB can be
refreshed every few months without losing history.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Any

from garmin_coach import config

KB_DIR = config.DATA_DIR / "knowledge"


def _ensure() -> None:
    KB_DIR.mkdir(parents=True, exist_ok=True)


def _next_version() -> int:
    _ensure()
    versions = [int(p.stem.split("_v")[1]) for p in KB_DIR.glob("kb_v*.json")
                if p.stem.split("_v")[-1].isdigit()]
    return (max(versions) + 1) if versions else 1


def save_kb(entries: list[dict[str, Any]], meta: dict | None = None) -> dict:
    _ensure()
    version = _next_version()
    doc = {
        "version": version,
        "built_at": dt.datetime.now().isoformat(timespec="seconds"),
        "meta": meta or {},
        "entries": entries,
    }
    (KB_DIR / f"kb_v{version}.json").write_text(json.dumps(doc, indent=2))
    (KB_DIR / "current.json").write_text(json.dumps({"version": version}))
    return doc


def load_kb() -> dict | None:
    cur = KB_DIR / "current.json"
    if not cur.exists():
        return None
    version = json.loads(cur.read_text())["version"]
    path = KB_DIR / f"kb_v{version}.json"
    return json.loads(path.read_text()) if path.exists() else None


def kb_context(metrics: list[str] | None = None, max_entries: int = 12,
               max_chars: int = 6000) -> str:
    """Condensed, citation-tagged KB text for grounding LLM prompts.

    If `metrics` is given, entries tagged with those metrics are prioritised so
    the recommendation engine retrieves only the relevant science.
    """
    kb = load_kb()
    if not kb:
        return ""
    entries = kb["entries"]
    if metrics:
        wanted = set(metrics)
        entries = sorted(
            entries,
            key=lambda e: len(wanted & set(e.get("metrics", []))),
            reverse=True,
        )
    out, used = [], 0
    for e in entries[:max_entries]:
        cites = "; ".join(
            f"{c.get('source','?')} ({c.get('year','')})"
            for c in e.get("citations", [])[:3]
        )
        guidance = " ".join(f"- {g}" for g in e.get("guidance", [])[:4])
        block = (f"## {e.get('topic')}\n{e.get('summary','')}\n{guidance}\n"
                 f"[sources: {cites}]\n")
        if used + len(block) > max_chars:
            break
        out.append(block)
        used += len(block)
    return "\n".join(out)
