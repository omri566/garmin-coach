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
    """Per-second streams for an activity, or an empty frame if it has none.

    Not every activity has a stream file — ingest only writes one when the FIT had
    per-second records (see ingest.sync). A Garmin *structured workout* in
    particular can come through with none, so callers must not crash: return an
    empty DataFrame rather than raising FileNotFoundError. Consumers
    (segments.best_sustained / km_splits, the coach's read) already treat an empty
    frame as 'no per-second data'."""
    path = streams_path(activity_id)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path, engine="pyarrow")
