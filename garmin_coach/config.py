"""Central paths and configuration."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Project root = parent of the garmin_coach package dir.
ROOT = Path(__file__).resolve().parent.parent


def _default_data_dir() -> Path:
    """Where the app keeps its DB, tokens and files.

    In the packaged .app, `__file__` lives inside the (possibly read-only) bundle,
    so writing next to it is wrong — use the standard macOS per-user location. In
    a source checkout, keep the repo-local `data/` dir for convenience.
    """
    if getattr(sys, "frozen", False):
        return Path.home() / "Library" / "Application Support" / "GarminCoach"
    return ROOT / "data"


DATA_DIR = Path(os.getenv("GC_DATA_DIR", _default_data_dir()))

DB_PATH = DATA_DIR / "garmin.db"
FIT_DIR = DATA_DIR / "fit"          # raw .fit files (source of truth)
STREAMS_DIR = DATA_DIR / "streams"  # per-second parquet, one file per activity
TOKENS_DIR = Path(os.getenv("GC_TOKENS_DIR", DATA_DIR / ".garth"))  # Garmin auth tokens

# Optional credentials (interactive prompt if absent).
GARMIN_EMAIL = os.getenv("GARMIN_EMAIL")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")


def ensure_dirs() -> None:
    for d in (DATA_DIR, FIT_DIR, STREAMS_DIR, TOKENS_DIR):
        d.mkdir(parents=True, exist_ok=True)
