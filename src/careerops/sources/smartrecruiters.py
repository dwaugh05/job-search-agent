"""SmartRecruiters public postings API.

    https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100

The list endpoint returns summaries only, so descriptions require a second call
per posting. We fetch detail lazily -- see registry.fetch_company.
"""

from __future__ import annotations

from typing import Any

from ..comp import mentions_bonus, mentions_equity, parse_salary
from ..models import Posting
from ..normalize import clean, parse_datetime, parse_location, parse_work_model, strip_html

NAME = "smartrecruiters"
URL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit={limit}&offset={offset}"
DETAIL_URL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings/{posting_id}"

# The API's own maximum per request.
PAGE_SIZE = 100
# Enough for the largest employer on the watch list, with headroom. The response
# carries totalFound, so paging stops on its own well before this in every normal
# case -- this only bounds a pathological board.
MAX_PAGES = 12


def build_url(slug: str, offset: int = 0, limit: int = PAGE_SIZE) -> str:
    return URL.format(slug=slug, limit=limit, offset=offset)


def total_found(payload: Any) -> int | None:
    """How many postings the employer actually has, per the API itself."""
    if isinstance(payload, dict) and isinstance(payload.get("totalFound"), int):
        return payload["totalFound"]
    return None


def detail_url(slug: str, posting_id: str) -> str:
    return DETAIL_URL.format(slug=slug, posting_id=posting_id)


def extract_jobs(payload: Any) -> list[dict]:
    if isinstance(payload, dict) and isinstance(payload.get("content"), list):
        return payload["content"]
    return []


def _description_from_detail(detail: dict) -> str:
    sections = ((detail.get("jobAd") or {}).get("sections")) or {}
    chunks = []
    for key in ("companyDescription", "jobDescription", "qualifications", "additionalInformation"):
        section = sections.get(key) or {}
        text = strip_html(section.get("text"))
        if text:
            chunks.append(text)
    return "\n\n".join(chunks)


def parse(job: dict, company: str, slug: str, detail: dict | None = None) -> Posting | None:
    detail = detail or {}
    description = _description_from_detail(detail)

    location = job.get("location") or {}
    location_bits = [location.get("city"), location.get("region"), location.get("country")]
    location_raw = ", ".join(clean(b) for b in location_bits if b)
    city, region, country = parse_location(location_raw)

    remote_flag = bool(location.get("remote"))
    work_model = parse_work_model(
        "Remote" if remote_flag else None, remote_flag, location_raw, description
    )

    salary_min, salary_max = parse_salary(description)
    published = parse_datetime(job.get("releasedDate") or job.get("createdOn"))

    posting_id = str(job.get("id") or "")
    # `ref` is a plain API URL string here, not the {"jobAd": ...} object the
    # shape of the rest of this payload suggests. The detail response carries the
    # real candidate-facing link as `applyUrl`.
    url = clean(detail.get("applyUrl")) or (
        f"https://jobs.smartrecruiters.com/{slug}/{posting_id}"
    )

    return Posting(
        source_id=posting_id,
        company=company,
        title=clean(job.get("name")),
        url=url,
        apply_url=url,
        ats=NAME,
        source_slug=slug,
        location_raw=location_raw,
        city=city,
        region=region,
        country=country,
        workplace_type=work_model,
        is_remote=remote_flag,
        department=clean((job.get("department") or {}).get("label")) or None,
        team=clean((job.get("function") or {}).get("label")) or None,
        employment_type=clean((job.get("typeOfEmployment") or {}).get("label")) or None,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_raw=None,
        equity_mentioned=mentions_equity(description),
        bonus_mentioned=mentions_bonus(description),
        published_at=published,
        date_confidence="high" if published else "none",
        description=description,
    )
