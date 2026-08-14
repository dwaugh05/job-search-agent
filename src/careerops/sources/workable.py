"""Workable public widget API.

    https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true

`details=true` inlines the description, which saves a second request per job.
"""

from __future__ import annotations

from typing import Any

from ..comp import mentions_bonus, mentions_equity, parse_salary
from ..models import Posting
from ..normalize import clean, parse_datetime, parse_location, parse_work_model, strip_html

NAME = "workable"
URL = "https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"


def build_url(slug: str) -> str:
    return URL.format(slug=slug)


def extract_jobs(payload: Any) -> list[dict]:
    if isinstance(payload, dict) and isinstance(payload.get("jobs"), list):
        return payload["jobs"]
    return []


def parse(job: dict, company: str, slug: str) -> Posting | None:
    description = "\n\n".join(
        part
        for part in (
            strip_html(job.get("description")),
            strip_html(job.get("requirements")),
            strip_html(job.get("benefits")),
        )
        if part
    )

    location_raw = clean(job.get("location") or job.get("city"))
    if isinstance(job.get("location"), dict):
        loc = job["location"]
        location_raw = ", ".join(
            clean(loc.get(k)) for k in ("city", "region", "country") if loc.get(k)
        )
    city, region, country = parse_location(location_raw)

    remote_flag = bool(job.get("telecommuting") or job.get("remote"))
    work_model = parse_work_model(
        "Remote" if remote_flag else None, remote_flag, location_raw, description
    )

    salary_min, salary_max = parse_salary(description)
    published = parse_datetime(job.get("published_on") or job.get("created_at"))

    url = clean(job.get("url") or job.get("application_url") or job.get("shortlink"))

    return Posting(
        source_id=str(job.get("id") or job.get("shortcode") or ""),
        company=company,
        title=clean(job.get("title")),
        url=url,
        apply_url=clean(job.get("application_url")) or url,
        ats=NAME,
        source_slug=slug,
        location_raw=location_raw,
        city=city,
        region=region,
        country=country,
        workplace_type=work_model,
        is_remote=remote_flag,
        department=clean(job.get("department")) or None,
        team=None,
        employment_type=clean(job.get("employment_type")) or None,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_raw=None,
        equity_mentioned=mentions_equity(description),
        bonus_mentioned=mentions_bonus(description),
        published_at=published,
        date_confidence="high" if published else "none",
        description=description,
    )
