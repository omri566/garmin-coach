"""Parquet IO for dense per-second activity streams."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from garmin_coach import config


def streams_path(activity_id: int) -> Path:
    return config.STREAMS_DIR / f"{activity_id}.parquet"


def write_streams(activity_id: int, df: pd.DataFrame) -> Path:
    config.ensure_dirs()
    path = streams_path(activity_id)
    # Snappy-compressed parquet: dense, columnar, fast to scan for trends.
    df.to_parquet(path, engine="pyarrow", compression="snappy", index=False)
    return path


def read_streams(activity_id: int) -> pd.DataFrame:
    return pd.read_parquet(streams_path(activity_id), engine="pyarrow")
