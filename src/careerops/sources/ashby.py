"""Ashby public job-board API.

    https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true

The query parameter is not optional for us: without it Ashby silently omits the
compensation block entirely, which is where Harvey's "$136K - $204K - Offers
Equity - Offers Bonus" comes from. Dropping it would blind dimension 4.
"""

from __future__ import annotations

from typing import Any

from ..comp import mentions_bonus, mentions_equity, parse_salary
from ..models import Posting
from ..normalize import clean, parse_datetime, parse_location, parse_work_model, strip_html

NAME = "ashby"
URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"


def build_url(slug: str) -> str:
    return URL.format(slug=slug)


def extract_jobs(payload: Any) -> list[dict]:
    if isinstance(payload, dict) and isinstance(payload.get("jobs"), list):
        return payload["jobs"]
    return []


def _compensation_text(job: dict) -> str:
    comp = job.get("compensation") or {}
    parts = [
        comp.get("compensationTierSummary"),
        comp.get("scrapeableCompensationSalarySummary"),
    ]
    for tier in comp.get("compensationTiers") or []:
        parts.append(tier.get("tierSummary"))
        parts.append(tier.get("additionalInformation"))
    return " ".join(clean(p) for p in parts if p)


def parse(job: dict, company: str, slug: str) -> Posting | None:
    if job.get("isListed") is False:
        return None

    description = clean(job.get("descriptionPlain")) or strip_html(job.get("descriptionHtml"))
    comp_text = _compensation_text(job)
    salary_min, salary_max = parse_salary(comp_text)
    if salary_min is None:
        salary_min, salary_max = parse_salary(description)

    location_raw = clean(job.get("location"))
    address = ((job.get("address") or {}).get("postalAddress")) or {}
    city, region, country = parse_location(location_raw)
    if not city and address.get("addressLocality"):
        city = clean(address["addressLocality"])
    if not region and address.get("addressRegion"):
        region = clean(address["addressRegion"])
    if not country and address.get("addressCountry"):
        country = clean(address["addressCountry"])

    work_model = parse_work_model(
        job.get("workplaceType"), job.get("isRemote"), location_raw, description
    )

    published = parse_datetime(job.get("publishedAt") or job.get("updatedAt"))

    return Posting(
        source_id=str(job.get("id") or ""),
        company=company,
        title=clean(job.get("title")),
        url=clean(job.get("jobUrl")),
        apply_url=clean(job.get("applyUrl")) or clean(job.get("jobUrl")),
        ats=NAME,
        source_slug=slug,
        location_raw=location_raw,
        city=city,
        region=region,
        country=country,
        workplace_type=work_model,
        is_remote=bool(job.get("isRemote")),
        department=clean(job.get("department")) or None,
        team=clean(job.get("team")) or None,
        employment_type=clean(job.get("employmentType")) or None,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_raw=comp_text or None,
        equity_mentioned=mentions_equity(comp_text, description),
        bonus_mentioned=mentions_bonus(comp_text, description),
        published_at=published,
        date_confidence="high" if published else "none",
        description=description,
    )
