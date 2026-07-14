"""Manual profile edits (Settings) layer over Garmin's fetch and win over it.

The nightly pipeline re-fetches anthropometrics from Garmin (`save_profile`); the
athlete's edits live in a separate overrides file so a re-fetch never clobbers
them. See `profile.load_profile` / `save_overrides`.
"""
from __future__ import annotations

import json

import pytest

from garmin_coach import config
from garmin_coach import profile as prof


@pytest.fixture(autouse=True)
def prof_paths(monkeypatch):
    """profile.py binds its file paths at import; repoint them at the scratch dir."""
    monkeypatch.setattr(prof, "PROFILE_PATH", config.DATA_DIR / "profile.json")
    monkeypatch.setattr(prof, "OVERRIDES_PATH",
                        config.DATA_DIR / "profile_overrides.json")


def test_manual_edit_wins_over_garmin_refetch():
    prof.save_profile(prof.Profile(age=30, weight_kg=80.0, height_cm=180.0, sex="MALE"))
    assert prof.load_profile().weight_kg == 80.0

    # The athlete edits weight + resting HR in Settings (bogus/blank fields dropped).
    prof.save_overrides({"weight_kg": 74.5, "resting_hr": 48, "bogus": 1, "age": None})
    p = prof.load_profile()
    assert p.weight_kg == 74.5 and p.resting_hr == 48

    # A nightly Garmin re-fetch overwrites the base — the edit still wins, while a
    # field the athlete didn't touch tracks Garmin.
    prof.save_profile(prof.Profile(age=31, weight_kg=81.0, sex="MALE"))
    p = prof.load_profile()
    assert p.weight_kg == 74.5      # override
    assert p.age == 31              # from Garmin (never overridden)

    assert json.loads(prof.OVERRIDES_PATH.read_text()) == {
        "weight_kg": 74.5, "resting_hr": 48}   # unknown key + None dropped


def test_clearing_a_field_reverts_to_garmin():
    prof.save_profile(prof.Profile(weight_kg=80.0))
    prof.save_overrides({"weight_kg": 70.0})
    assert prof.load_profile().weight_kg == 70.0

    prof.save_overrides({"weight_kg": None})   # cleared in the UI
    assert prof.load_profile().weight_kg == 80.0
