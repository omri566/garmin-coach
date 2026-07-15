"""A run without a per-second stream file must not crash stream readers.

Ingest only writes a stream file when the FIT had per-second records, so some
activities (notably some Garmin structured workouts) have none. `read_streams`
must return an empty frame, not raise — otherwise the coach's read / verdict of
that run crashes. See `store/streams.read_streams`.
"""
from __future__ import annotations

import pandas as pd

from garmin_coach.store import streams


def test_read_streams_missing_returns_empty_frame():
    df = streams.read_streams(999999)          # never written
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_read_streams_roundtrips_when_present():
    streams.write_streams(1, pd.DataFrame(
        {"enhanced_speed": [3.0, 3.1], "distance": [0.0, 3.1]}))
    df = streams.read_streams(1)
    assert not df.empty
    assert set(df.columns) == {"enhanced_speed", "distance"}
