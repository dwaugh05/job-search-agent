"""Workday CXS public job API.

    POST https://{tenant}.{instance}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
         {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}

Workday hosts a large share of big local employers -- Genentech, Gilead, HP,
Broadcom/VMware, Visa, Franklin Templeton -- none of which expose a
Greenhouse/Ashby/Lever feed. Without this adapter they are invisible to the scan.

## Why this file contains the only POST in the codebase

Every other adapter reads with GET, and the no-auto-apply audit greps for HTTP
write verbs as a safety guarantee. Workday's *search* endpoint requires POST
because the query is a JSON body -- it is semantically a read, and it returns a
job list. That is a legitimate exception, but it must stay a narrow one, so:

  * `_assert_search_url` refuses any URL that is not a `/wday/cxs/.../jobs`
    search or job-detail path. An application endpoint can never be reached
    through this module.
  * The request body is built here and never accepts caller-supplied fields.
  * The audit in the test suite allows POST *only* in this file, and only on
    lines guarded by that assertion.

Discovery of tenant/site is done from robots.txt, which lists each site's
sitemap -- the site slug is not guessable ("gileadcareers", "External_Career",
"Primary-External-1", "roche-ext" are all real).
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from ..comp import mentions_bonus, mentions_equity, parse_salary
from ..models import Posting
from ..normalize import clean, parse_datetime, parse_location, parse_work_model, strip_html

NAME = "workday"

# tenant/instance/site are packed into the slug as "tenant:instance:site".
URL = "https://{tenant}.{instance}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
BASE = "https://{tenant}.{instance}.myworkdayjobs.com"

_SEARCH_PATH = re.compile(
    r"^https://[a-z0-9\-]+\.wd\d+\.myworkdayjobs\.com/wday/cxs/"
    r"[A-Za-z0-9_\-]+/[A-Za-z0-9_\-]+/(jobs|job/.+)$"
)
PAGE_SIZE = 20
MAX_PAGES = 10


def _assert_search_url(url: str) -> None:
    """Hard guarantee: this module can only ever reach a job SEARCH endpoint.

    Any URL that is not a Workday CXS jobs-search or job-detail path raises,
    which makes it structurally impossible for the one POST in this codebase to
    hit an application-submission route.
    """
    if not _SEARCH_PATH.match(url):
        raise ValueError(f"refusing non-search Workday URL: {url}")


def parse_slug(slug: str) -> tuple[str, str, str] | None:
    parts = (slug or "").split(":")
    if len(parts) != 3 or not all(parts):
        return None
    return parts[0], parts[1], parts[2]


def build_url(slug: str) -> str:
    parsed = parse_slug(slug)
    if not parsed:
        return ""
    tenant, instance, site = parsed
    return URL.format(tenant=tenant, instance=instance, site=site)


def search(client: httpx.Client, slug: str, offset: int = 0) -> dict | None:
    """One page of the job list. POST is the search verb here, not a write."""
    url = build_url(slug)
    if not url:
        return None
    _assert_search_url(url)
    try:
        response = client.post(
            url,
            json={"appliedFacets": {}, "limit": PAGE_SIZE,
                  "offset": offset, "searchText": ""},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def extract_jobs(payload: Any) -> list[dict]:
    if isinstance(payload, dict) and isinstance(payload.get("jobPostings"), list):
        return payload["jobPostings"]
    return []


def detail(client: httpx.Client, slug: str, external_path: str) -> dict | None:
    """Full posting, including the description body."""
    parsed = parse_slug(slug)
    if not parsed or not external_path:
        return None
    tenant, instance, site = parsed
    # externalPath already begins with "/job/..." -- prepending another "job"
    # produced ".../gileadcareers/job/job/..." and a silent 404 on every detail
    # fetch, which looked exactly like "this employer has no relevant roles".
    path = external_path if external_path.startswith("/") else "/" + external_path
    url = BASE.format(tenant=tenant, instance=instance) + f"/wday/cxs/{tenant}/{site}{path}"
    _assert_search_url(url)
    try:
        response = client.get(url, headers={"Accept": "application/json"})
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None


_POSTED_RE = re.compile(r"(\d+)\+?\s*days?\s+ago", re.IGNORECASE)


def _published(job: dict, info: dict) -> tuple[str | None, str]:
    """Workday reports 'Posted 5 Days Ago' rather than a date."""
    explicit = parse_datetime(info.get("startDate") or info.get("postedOn"))
    if explicit:
        return explicit, "high"
    text = clean(job.get("postedOn") or info.get("postedOn"))
    if "today" in text.lower():
        from ..normalize import days_ago_iso
        return days_ago_iso(0), "high"
    match = _POSTED_RE.search(text)
    if match:
        from ..normalize import days_ago_iso
        return days_ago_iso(int(match.group(1))), "high"
    return None, "none"


def parse(job: dict, company: str, slug: str, detail_payload: dict | None = None) -> Posting | None:
    info = ((detail_payload or {}).get("jobPostingInfo")) or {}
    description = strip_html(info.get("jobDescription"))

    location_raw = clean(info.get("location") or job.get("locationsText"))
    city, region, country = parse_location(location_raw)

    salary_min, salary_max = parse_salary(description)
    published, confidence = _published(job, info)

    parsed_slug = parse_slug(slug)
    external = clean(job.get("externalPath"))
    if parsed_slug:
        tenant, instance, site = parsed_slug
        url = (BASE.format(tenant=tenant, instance=instance) + f"/{site}{external}")
    else:
        url = clean(info.get("externalUrl"))

    remote_flag = bool(info.get("remoteType")) or "remote" in location_raw.lower()
    work_model = parse_work_model(
        clean(info.get("remoteType")) or None, remote_flag, location_raw, description
    )

    return Posting(
        source_id=clean(job.get("bulletFields", [""])[0] if job.get("bulletFields") else "")
        or external.strip("/").split("/")[-1],
        company=company,
        title=clean(job.get("title") or info.get("jobPostingTitle")),
        url=url,
        apply_url=url,
        ats=NAME,
        source_slug=slug,
        location_raw=location_raw,
        city=city,
        region=region,
        country=country,
        workplace_type=work_model,
        is_remote=work_model == "Remote",
        department=None,
        team=None,
        employment_type=clean(info.get("timeType")) or None,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_raw=None,
        equity_mentioned=mentions_equity(description),
        bonus_mentioned=mentions_bonus(description),
        published_at=published,
        date_confidence=confidence,
        description=description,
    )
