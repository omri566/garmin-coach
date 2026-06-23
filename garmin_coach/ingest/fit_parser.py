"""Parse raw FIT files into dense per-second streams + laps + session summary.

We capture *every* field present on each message generically (via get_values),
so device-specific running-dynamics fields (vertical oscillation, vertical
ratio, ground contact time + balance, step length, running power, ...) are kept
without an explicit allow-list. Nothing is discarded.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from typing import Any

import pandas as pd
from fitparse import FitFile


@dataclass
class ParsedFit:
    records: pd.DataFrame      # per-second/per-record samples
    laps: pd.DataFrame         # per-lap summaries (splits)
    session: dict[str, Any]    # whole-activity summary from the FIT


def _messages(fit: FitFile, name: str) -> list[dict[str, Any]]:
    return [m.get_values() for m in fit.get_messages(name)]


def extract_fit_bytes(raw: bytes) -> bytes:
    """Garmin ORIGINAL downloads are a zip wrapping the .fit. Unwrap if needed."""
    if raw[:2] == b"PK":  # zip magic
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            fit_names = [n for n in zf.namelist() if n.lower().endswith(".fit")]
            if not fit_names:
                raise ValueError("Zip contained no .fit file")
            return zf.read(fit_names[0])
    return raw


def parse_fit(raw: bytes) -> ParsedFit:
    fit_bytes = extract_fit_bytes(raw)
    fit = FitFile(io.BytesIO(fit_bytes))
    fit.parse()

    records = pd.DataFrame(_messages(fit, "record"))
    laps = pd.DataFrame(_messages(fit, "lap"))
    sessions = _messages(fit, "session")
    session = sessions[0] if sessions else {}

    if not records.empty and "timestamp" in records.columns:
        records = records.sort_values("timestamp").reset_index(drop=True)

    return ParsedFit(records=records, laps=laps, session=session)
