"""Central paths and configuration."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Project root = parent of the garmin_coach package dir.
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("GC_DATA_DIR", ROOT / "data"))

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
