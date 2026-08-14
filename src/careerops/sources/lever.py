"""Lever public postings API.

    https://api.lever.co/v0/postings/{slug}?mode=json

Returns a bare list rather than an object, and stamps createdAt as epoch
milliseconds.
"""

from __future__ import annotations

from typing import Any

from ..comp import mentions_bonus, mentions_equity, parse_salary
from ..models import Posting
from ..normalize import clean, parse_datetime, parse_location, parse_work_model, strip_html

NAME = "lever"
URL = "https://api.lever.co/v0/postings/{slug}?mode=json"


def build_url(slug: str) -> str:
    return URL.format(slug=slug)


def extract_jobs(payload: Any) -> list[dict]:
    return payload if isinstance(payload, list) else []


def parse(job: dict, company: str, slug: str) -> Posting | None:
    parts = [
        clean(job.get("descriptionPlain")) or strip_html(job.get("description")),
        clean(job.get("additionalPlain")) or strip_html(job.get("additional")),
    ]
    for section in job.get("lists") or []:
        text = strip_html(section.get("content"))
        if text:
            parts.append(f"{clean(section.get('text'))}\n{text}")
    description = "\n\n".join(p for p in parts if p)

    categories = job.get("categories") or {}
    location_raw = clean(categories.get("location"))
    city, region, country = parse_location(location_raw)

    salary_range = job.get("salaryRange") or {}
    salary_min = salary_range.get("min")
    salary_max = salary_range.get("max")
    if salary_min is None:
        salary_min, salary_max = parse_salary(description)

    commitment = clean(categories.get("commitment"))
    workplace = clean(job.get("workplaceType"))
    work_model = parse_work_model(workplace, None, location_raw, description)
    published = parse_datetime(job.get("createdAt"))

    return Posting(
        source_id=str(job.get("id") or ""),
        company=company,
        title=clean(job.get("text")),
        url=clean(job.get("hostedUrl")),
        apply_url=clean(job.get("applyUrl")) or clean(job.get("hostedUrl")),
        ats=NAME,
        source_slug=slug,
        location_raw=location_raw,
        city=city,
        region=region,
        country=country,
        workplace_type=work_model,
        is_remote=work_model == "Remote",
        department=clean(categories.get("department")) or None,
        team=clean(categories.get("team")) or None,
        employment_type=commitment or None,
        salary_min=int(salary_min) if salary_min else None,
        salary_max=int(salary_max) if salary_max else None,
        salary_raw=None,
        equity_mentioned=mentions_equity(description),
        bonus_mentioned=mentions_bonus(description),
        published_at=published,
        date_confidence="high" if published else "none",
        description=description,
    )
