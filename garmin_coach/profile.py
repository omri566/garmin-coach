"""Athlete profile — the physiological anchors every zone-based metric needs.

Pulled from Garmin where authoritative (max HR, lactate-threshold HR, HR zones,
VO2max, anthropometrics) and derived from our own data where Garmin has no value
(resting HR baseline, threshold pace). Persisted to data/profile.json so the
analytics layer reads it without hitting Garmin, and re-fetchable as fitness
changes.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import asdict, dataclass, field, fields
from typing import Any

from garmin_coach import config
from garmin_coach.store import db

log = logging.getLogger(__name__)

PROFILE_PATH = config.DATA_DIR / "profile.json"
# Manual edits (from Settings) live in a separate file layered *on top* of the
# Garmin-fetched base, so a nightly profile re-fetch (save_profile) never clobbers
# what the athlete typed. Only these fields may be overridden by hand.
OVERRIDES_PATH = config.DATA_DIR / "profile_overrides.json"
EDITABLE_FIELDS = ("age", "sex", "height_cm", "weight_kg", "resting_hr",
                   "hr_max", "lthr", "vo2max")


@dataclass
class Profile:
    fetched_at: str = ""
    age: int | None = None
    sex: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    hr_max: float | None = None
    lthr: float | None = None              # lactate-threshold HR
    hr_zone_floors: dict[str, float] = field(default_factory=dict)  # z1..z5
    resting_hr: float | None = None        # derived: recent baseline
    vo2max: float | None = None
    threshold_pace_s_per_km: float | None = None  # derived from hard efforts
    ftp_w: float | None = None

    def zone_of_hr(self, hr: float) -> int:
        """1..5 zone for a heart rate using Garmin's LTHR-based floors."""
        floors = self.hr_zone_floors
        z = 1
        for i, key in enumerate(["z1", "z2", "z3", "z4", "z5"], start=1):
            if floors.get(key) is not None and hr >= floors[key]:
                z = i
        return z


def _derive_resting_hr(days: int = 90) -> float | None:
    """Median resting HR over the recent window (robust to one-off readings)."""
    cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    with db.connect() as conn:
        vals = [r[0] for r in conn.execute(
            "SELECT resting_hr FROM health_daily WHERE day >= ? AND resting_hr IS NOT NULL",
            (cutoff,),
        ).fetchall()]
    if not vals:
        return None
    vals.sort()
    return float(vals[len(vals) // 2])


def _derive_threshold_pace(lthr: float | None, days: int = 540) -> float | None:
    """Pace (s/km) at threshold via a pace-vs-HR regression over steady runs.

    Athletes rarely *average* their LTHR over a whole run, so matching runs near
    LTHR is fragile. Instead we fit avg-pace (s/km) ~ avg-HR across steady runs
    and evaluate the line at LTHR. Guards: enough runs, positive slope, and a
    prediction that stays within the observed pace range.
    """
    if lthr is None:
        return None
    import numpy as np

    cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT distance_m, duration_s, avg_hr FROM activities "
            "WHERE sport LIKE '%running%' AND avg_hr IS NOT NULL "
            "AND duration_s >= 1200 AND distance_m > 2000 AND start_time >= ?",
            (cutoff,),
        ).fetchall()
    if len(rows) < 20:
        return None
    hr = np.array([r[2] for r in rows], dtype=float)
    pace = np.array([r[1] / (r[0] / 1000.0) for r in rows], dtype=float)
    slope, intercept = np.polyfit(hr, pace, 1)
    if slope >= 0:  # s/km should fall as HR rises; non-negative slope = noise
        return None
    pred = slope * lthr + intercept
    # Don't extrapolate past the fastest observed steady pace.
    return float(max(pred, pace.min()))


def fetch_profile(client) -> Profile:
    """Build a Profile from Garmin + our DB. `client` is a logged-in Garmin."""
    info = client.connectapi("/userprofile-service/userprofile/personal-information")
    ui = info.get("userInfo", {})
    bp = info.get("biometricProfile", {})

    zones_raw = client.connectapi("/biometric-service/heartRateZones")
    default_zone = next(
        (z for z in zones_raw if z.get("sport") == "DEFAULT"),
        zones_raw[0] if zones_raw else {},
    )
    hr_max = default_zone.get("maxHeartRateUsed")
    floors = {
        f"z{i}": default_zone.get(f"zone{i}Floor")
        for i in range(1, 6)
    }

    weight_g = bp.get("weight")
    p = Profile(
        fetched_at=dt.datetime.now().isoformat(timespec="seconds"),
        age=ui.get("age"),
        sex=ui.get("genderType"),
        height_cm=bp.get("height"),
        weight_kg=(weight_g / 1000.0) if weight_g else None,
        hr_max=hr_max,
        lthr=bp.get("lactateThresholdHeartRate"),
        hr_zone_floors={k: v for k, v in floors.items() if v is not None},
        vo2max=bp.get("vo2Max"),
        ftp_w=bp.get("functionalThresholdPower"),
    )
    p.resting_hr = _derive_resting_hr()
    p.threshold_pace_s_per_km = _derive_threshold_pace(p.lthr)
    return p


def save_profile(p: Profile) -> None:
    config.ensure_dirs()
    PROFILE_PATH.write_text(json.dumps(asdict(p), indent=2))


def load_overrides() -> dict[str, Any]:
    """Manual profile edits (Settings), or {} if none saved yet."""
    if not OVERRIDES_PATH.exists():
        return {}
    try:
        return json.loads(OVERRIDES_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_overrides(overrides: dict[str, Any]) -> None:
    """Persist manual edits, keeping only recognised editable fields with a value.
    Fields set to None/'' are dropped, so clearing a field reverts it to Garmin's."""
    config.ensure_dirs()
    clean = {k: v for k, v in overrides.items()
             if k in EDITABLE_FIELDS and v not in (None, "")}
    OVERRIDES_PATH.write_text(json.dumps(clean, indent=2))


_PROFILE_FIELDS = {f.name for f in fields(Profile)}


def load_profile() -> Profile:
    base: dict[str, Any] = (json.loads(PROFILE_PATH.read_text())
                            if PROFILE_PATH.exists() else {})
    overrides = {k: v for k, v in load_overrides().items()
                 if k in EDITABLE_FIELDS and v not in (None, "")}
    if not base and not overrides:
        raise FileNotFoundError(
            f"No profile at {PROFILE_PATH}. Run: python -m garmin_coach.profile"
        )
    merged = {**base, **overrides}
    return Profile(**{k: v for k, v in merged.items() if k in _PROFILE_FIELDS})


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from garmin_coach.ingest.client import get_client

    p = fetch_profile(get_client())
    save_profile(p)
    log.info("Saved athlete profile to %s:\n%s", PROFILE_PATH,
             json.dumps(asdict(p), indent=2))


if __name__ == "__main__":
    main()
