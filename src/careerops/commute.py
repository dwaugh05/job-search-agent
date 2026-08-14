"""Commute lookup from San Mateo 94403.

Deliberately a curated table rather than a Maps API call: no key, no quota, no
network in the hot path, and Doran can correct any number he disagrees with and
immediately change how every future scan scores.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import config
from .models import WORK_REMOTE


@dataclass
class CommuteResult:
    minutes: int | None
    score: float
    known: bool
    note: str


def _thresholds() -> list[dict]:
    for dim in config.scoring().get("dimensions", []):
        if dim.get("key") == "location_commute":
            return dim.get("commute_thresholds", [])
    return []


def _dim5() -> dict:
    for dim in config.scoring().get("dimensions", []):
        if dim.get("key") == "location_commute":
            return dim
    return {}


def lookup_minutes(city: str | None) -> int | None:
    if not city:
        return None
    cities = config.commute_table().get("cities", {}) or {}
    if city in cities:
        return cities[city]
    lowered = {k.lower(): v for k, v in cities.items()}
    return lowered.get(city.strip().lower())


def score_for_minutes(minutes: int) -> float:
    for band in _thresholds():
        if minutes <= band.get("max_minutes", 0):
            return float(band.get("score", 1.0))
    return 1.0


def evaluate(city: str | None, work_model: str | None) -> CommuteResult:
    dim = _dim5()
    if work_model == WORK_REMOTE:
        return CommuteResult(
            minutes=0,
            score=float(dim.get("remote_score", 5.0)),
            known=True,
            note="Fully remote - no commute.",
        )

    minutes = lookup_minutes(city)
    if minutes is None:
        return CommuteResult(
            minutes=None,
            score=float(dim.get("unknown_city_score", 3.0)),
            known=False,
            note=(
                f"Commute time unknown for {city!r}. Add it to config/commute.yml "
                "to score this location properly."
            ),
        )

    return CommuteResult(
        minutes=minutes,
        score=score_for_minutes(minutes),
        known=True,
        note=f"{minutes} min door-to-door from San Mateo 94403.",
    )


def exceeds_hard_gate(city: str | None, work_model: str | None) -> bool:
    """True when the commute alone disqualifies the role."""
    if work_model == WORK_REMOTE:
        return False
    limit = config.profile().get("hard_gates", {}).get("max_commute_minutes", 60)
    minutes = lookup_minutes(city)
    if minutes is None:
        # Unknown city is never auto-failed here -- geo prefiltering handles it,
        # and a silent drop would hide roles worth a manual look.
        return False
    return minutes > limit
