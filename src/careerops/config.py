"""Config loading. One place that knows where the YAML lives."""

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RUNS_DIR = DATA_DIR / "runs"
REF_DIR = ROOT / "ref-docs"
RUBRIC_DIR = ROOT / "rubric"
DB_PATH = DATA_DIR / "jobs.db"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


@functools.lru_cache(maxsize=None)
def profile() -> dict[str, Any]:
    return _load(CONFIG_DIR / "profile.yml")


# Track A is the AI-enablement list; track B is the growth-marketing backup list.
# They share one scoring engine and differ only by config file -- see the
# architecture invariant in CLAUDE.md.
TRACK_AI = "ai_enablement"
TRACK_GROWTH = "growth_marketing"
TRACKS = (TRACK_AI, TRACK_GROWTH)

_TRACK_FILES = {
    TRACK_AI: "scoring.yml",
    TRACK_GROWTH: "scoring-growth.yml",
}


@functools.lru_cache(maxsize=None)
def scoring(track: str = TRACK_AI) -> dict[str, Any]:
    filename = _TRACK_FILES.get(track)
    if filename is None:
        raise ValueError(f"Unknown track {track!r}; expected one of {TRACKS}")
    return _load(CONFIG_DIR / filename)


def track_label(track: str) -> str:
    return str(scoring(track).get("label", track))


# --------------------------------------------------------------- the buckets
#
# Doran, 2026-08-28: "I think of your job search workflow as you looking at me
# for two different roles that I could fit into. If they were overlap then
# that's great, but each of them separately is also suitable for me too...
# there's the traditional marketing role and then there's the AI role. And then
# there's a third bucket of where they overlap. And so I want to know about all
# three of these when you present the lists."
#
# The bucket is derived from postings.tracks, which the prefilter has always
# computed and persisted and which nothing read until now.
BUCKET_MARKETING = "marketing_only"
BUCKET_AI = "ai_only"
BUCKET_OVERLAP = "overlap"
BUCKETS = (BUCKET_OVERLAP, BUCKET_AI, BUCKET_MARKETING)

_BUCKET_LABELS = {
    BUCKET_OVERLAP: "AI + MARKETING",
    BUCKET_AI: "AI ENABLEMENT",
    BUCKET_MARKETING: "MARKETING",
}

# Which rubric a bucket is scored against. An overlap posting is scored on the
# AI rubric because that is the half with the higher ceiling for Doran; a
# marketing-only posting MUST use the growth rubric, because scoring.yml
# dimension 1 (weight 22) makes AI enablement the hard requirement and a pure
# marketing role cannot mathematically clear the bar under it.
_BUCKET_RUBRIC = {
    BUCKET_OVERLAP: TRACK_AI,
    BUCKET_AI: TRACK_AI,
    BUCKET_MARKETING: TRACK_GROWTH,
}


def bucket_of(tracks: Any) -> str:
    """Which of the three buckets a posting belongs to.

    Accepts the comma-joined string stored on postings.tracks, or a list.
    A posting with no recorded track is treated as AI-only, which is what the
    system assumed for its whole history before buckets existed.
    """
    if isinstance(tracks, str):
        names = {t.strip() for t in tracks.split(",") if t.strip()}
    else:
        names = {str(t).strip() for t in (tracks or []) if str(t).strip()}
    has_ai = TRACK_AI in names
    has_growth = TRACK_GROWTH in names
    if has_ai and has_growth:
        return BUCKET_OVERLAP
    if has_growth:
        return BUCKET_MARKETING
    return BUCKET_AI


def bucket_label(bucket: str) -> str:
    return _BUCKET_LABELS.get(bucket, bucket.replace("_", " ").upper())


def bucket_rubric(bucket: str) -> str:
    """The track whose rubric this bucket is scored against."""
    return _BUCKET_RUBRIC.get(bucket, TRACK_AI)


def bucket_threshold(bucket: str) -> float:
    """The presentation bar for one bucket.

    THE LENIENCY IS A BAR, NEVER A SCORE BONUS. That is what keeps the
    calibration anchors safe: they assert scores against bands, and moving a bar
    cannot move a score. Adding points instead would have moved every anchor.
    """
    review = profile().get("review", {}) or {}
    bars = review.get("bucket_thresholds", {}) or {}
    default = float(review.get("min_score_to_present", 4.0))
    return float(bars.get(bucket, default))


@functools.lru_cache(maxsize=None)
def commute_table() -> dict[str, Any]:
    return _load(CONFIG_DIR / "commute.yml")


def sources() -> dict[str, Any]:
    """Not cached -- verify-sources and resolve-company rewrite this at runtime."""
    return _load(CONFIG_DIR / "sources.yml")


def save_sources(data: dict[str, Any]) -> None:
    """Write sources.yml back, preserving readable formatting."""
    path = CONFIG_DIR / "sources.yml"
    header_lines: list[str] = []
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("#") or not line.strip():
                    header_lines.append(line)
                else:
                    break
    with path.open("w", encoding="utf-8") as handle:
        handle.writelines(header_lines)
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True, width=100)


def connections() -> dict[str, Any]:
    """Companies where Doran has a personal connection.

    Not cached, for the same reason sources() is not: sync-connections rewrites
    this file at runtime to cache resolved ATS slugs.
    """
    path = CONFIG_DIR / "connections.yml"
    if not path.exists():
        return {"bump": 1.0, "max_score": 5.0, "companies": []}
    return _load(path)


def save_connections(data: dict[str, Any]) -> None:
    """Write connections.yml back, preserving the leading comment block."""
    path = CONFIG_DIR / "connections.yml"
    header_lines: list[str] = []
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("#") or not line.strip():
                    header_lines.append(line)
                else:
                    break
    with path.open("w", encoding="utf-8") as handle:
        handle.writelines(header_lines)
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True, width=100)


# Legal suffixes and punctuation that differ between how Doran names a company
# and how its ATS does ("Meta" vs "Meta Platforms, Inc.").
_COMPANY_NOISE = re.compile(r"[^a-z0-9]+")
_COMPANY_SUFFIXES = ("inc", "incorporated", "llc", "ltd", "limited", "corp",
                     "corporation", "co", "company", "plc", "gmbh", "sa", "ag")


def normalize_company(name: str | None) -> str:
    """Collapse a company name to a comparable key."""
    if not name:
        return ""
    key = _COMPANY_NOISE.sub(" ", str(name).lower()).strip()
    parts = key.split()
    while parts and parts[-1] in _COMPANY_SUFFIXES:
        parts.pop()
    return "".join(parts)


def connection_lookup() -> tuple[set[str], set[tuple[str, str]]]:
    """Return (normalized names incl. aliases, (ats, slug) pairs).

    Two keys because neither alone is reliable: a company can be matched by
    name before it has been resolved, and by board once it has -- and ATS
    company names drift from the common name often enough to need both.
    """
    names: set[str] = set()
    boards: set[tuple[str, str]] = set()
    for entry in connections().get("companies", []) or []:
        if not isinstance(entry, dict):
            entry = {"name": entry}
        key = normalize_company(entry.get("name"))
        if key:
            names.add(key)
        for alias in entry.get("aliases") or []:
            alias_key = normalize_company(alias)
            if alias_key:
                names.add(alias_key)
        ats, slug = entry.get("ats"), entry.get("slug")
        if ats and slug:
            boards.add((str(ats).lower(), str(slug).lower()))
    return names, boards


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
