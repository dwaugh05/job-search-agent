"""Canonical posting shape. Every source adapter must produce this."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# Posting lifecycle. Anything at PRESENTED or beyond is permanently suppressed
# from future scan reports -- that is the "never show me the same job twice" rule.
STATE_NEW = "new"
STATE_PREFILTERED = "prefiltered"
STATE_REJECTED_PREFILTER = "rejected_prefilter"
STATE_EVALUATED = "evaluated"
STATE_PRESENTED = "presented"
STATE_INTERESTED = "interested"
STATE_SAVED = "saved"
STATE_NOT_INTERESTED = "not_interested"
STATE_APPLIED = "applied"

# States that mean "Doran has already laid eyes on this".
SUPPRESSED_STATES = frozenset(
    {
        STATE_PRESENTED,
        STATE_INTERESTED,
        STATE_SAVED,
        STATE_NOT_INTERESTED,
        STATE_APPLIED,
    }
)

VERDICTS = frozenset(
    {STATE_INTERESTED, STATE_SAVED, STATE_NOT_INTERESTED, STATE_APPLIED}
)

WORK_REMOTE = "Remote"
WORK_HYBRID = "Hybrid"
WORK_ONSITE = "On-site"


@dataclass
class Posting:
    """One job posting, normalized. Source-agnostic."""

    source_id: str
    company: str
    title: str
    url: str
    ats: str
    source_slug: str = ""
    apply_url: str = ""
    location_raw: str = ""
    city: str | None = None
    region: str | None = None
    country: str | None = None
    workplace_type: str | None = None
    is_remote: bool = False
    department: str | None = None
    team: str | None = None
    employment_type: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_raw: str | None = None
    equity_mentioned: bool = False
    bonus_mentioned: bool = False
    published_at: str | None = None
    date_confidence: str = "none"  # high | low | none
    description: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
