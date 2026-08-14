"""Greenhouse public job-board API.

    https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true

`content=true` is mandatory here. Without it Greenhouse returns titles and
locations but no description body at all, and since our prefilter matches on
description content rather than job title, an empty body means every Greenhouse
company silently contributes zero candidates.

Slugs are not derivable from company names -- DoorDash is `doordashusa`.
"""

from __future__ import annotations

import html
from typing import Any

from ..comp import mentions_bonus, mentions_equity, parse_salary
from ..models import Posting
from ..normalize import clean, parse_datetime, parse_location, parse_work_model, strip_html

NAME = "greenhouse"
URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


def build_url(slug: str) -> str:
    return URL.format(slug=slug)


def extract_jobs(payload: Any) -> list[dict]:
    if isinstance(payload, dict) and isinstance(payload.get("jobs"), list):
        return payload["jobs"]
    return []


def _metadata_text(job: dict) -> str:
    chunks = []
    for item in job.get("metadata") or []:
        value = item.get("value")
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        if value:
            chunks.append(f"{item.get('name')}: {value}")
    return " | ".join(chunks)


def parse(job: dict, company: str, slug: str) -> Posting | None:
    # Greenhouse double-encodes the content field.
    description = strip_html(html.unescape(job.get("content") or ""))
    if not description:
        description = clean(job.get("content"))

    location_raw = clean((job.get("location") or {}).get("name"))
    city, region, country = parse_location(location_raw)

    pay = job.get("pay_input_ranges") or []
    salary_min = salary_max = None
    if pay:
        lows = [p.get("min_cents") for p in pay if p.get("min_cents")]
        highs = [p.get("max_cents") for p in pay if p.get("max_cents")]
        if lows and highs:
            salary_min, salary_max = int(min(lows) / 100), int(max(highs) / 100)
    if salary_min is None:
        salary_min, salary_max = parse_salary(description)

    meta = _metadata_text(job)
    work_model = parse_work_model(None, None, location_raw, description)
    published = parse_datetime(job.get("first_published") or job.get("updated_at"))

    departments = job.get("departments") or []
    offices = job.get("offices") or []

    return Posting(
        source_id=str(job.get("id") or ""),
        company=company,
        title=clean(job.get("title")),
        url=clean(job.get("absolute_url")),
        apply_url=clean(job.get("absolute_url")),
        ats=NAME,
        source_slug=slug,
        location_raw=location_raw,
        city=city,
        region=region,
        country=country,
        workplace_type=work_model,
        is_remote=work_model == "Remote",
        department=clean(departments[0].get("name")) if departments else None,
        team=clean(offices[0].get("name")) if offices else None,
        employment_type=None,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_raw=meta or None,
        equity_mentioned=mentions_equity(description, meta),
        bonus_mentioned=mentions_bonus(description, meta),
        published_at=published,
        date_confidence="high" if published else "none",
        description=description,
    )
