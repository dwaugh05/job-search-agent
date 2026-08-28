"""Eightfold AI public careers API.

    GET https://{sub}.eightfold.ai/api/pcsx/search?domain={domain}&query=&start=0&num=10
    GET https://{sub}.eightfold.ai/api/apply/v2/jobs/{id}?domain={domain}

## Why this adapter exists

NVIDIA sat on the watch list marked "dead" for weeks. Its board is Eightfold,
which none of the five probed providers cover, so `verify-sources` resolved it
to nothing and every scan skipped it in silence. The only NVIDIA postings this
system has ever seen came through LinkedIn, and only because LinkedIn labels the
employer "NVIDIA AI" rather than "Nvidia".

Measured on 2026-08-27, NVIDIA's board carries ~2,695 live reqs, including
"Senior Architect, Agentic AI for Marketing" -- explicit human-in-the-loop
framing, field enablement, $224k-$356.5k, Santa Clara -- which no scan had seen.

Eightfold is multi-tenant, so this adapter is not NVIDIA-specific.

## Shape of the two endpoints

`/api/pcsx/search` is the LISTING. It returns titles, locations, a posted
timestamp and a job id, but NO description, so it cannot be scored from alone.
`domain` is mandatory: without it the endpoint answers 422. `num` is capped at
10 server-side regardless of what you ask for, so paging is 10 at a time.

`/api/apply/v2/jobs/{id}` is the DETAIL, and carries `job_description` as HTML.
Note the sibling path `/api/apply/v2/jobs` (no id) answers 403 "Not authorized
for PCSX" -- that is the tenant-wide search, which is closed. Do not chase it.

Both are GET and both work unauthenticated. A Referer header is not required
(verified 2026-08-27).

## Slug format

Packed as "subdomain:domain", e.g. "nvidia:nvidia.com", because the API needs
both and they are not derivable from one another. Same reasoning as Workday's
tenant:instance:site triple: not guessable, so it is resolved once and stored.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from ..comp import mentions_bonus, mentions_equity, parse_salary
from ..models import Posting
from ..normalize import (clean, parse_datetime, parse_location,
                         parse_work_model, strip_html)

NAME = "eightfold"

SEARCH = ("https://{sub}.eightfold.ai/api/pcsx/search"
          "?domain={domain}&query=&start={start}&num={num}")
DETAIL = "https://{sub}.eightfold.ai/api/apply/v2/jobs/{job_id}?domain={domain}"
CAREERS = "https://{sub}.eightfold.ai/careers/job/{job_id}"

# The server caps `num` at 10 whatever we ask for, so this is a statement of
# fact rather than a preference. Asking for 50 returned 10.
PAGE_SIZE = 10
# 2,695 reqs at NVIDIA / 10 per page is 270 requests for a full listing sweep.
# The listing is metadata only and cheap, and it is the only way to see every
# title, but it still needs a ceiling so one huge tenant cannot own a whole run.
MAX_PAGES = 300


# This is the only adapter that puts a slug into the HOSTNAME rather than the
# path, so a malformed slug here becomes a malformed DNS name. A label over 63
# characters makes httpx raise UnicodeError from the idna codec, which is not an
# httpx.HTTPError and therefore escaped every handler and killed a whole scan on
# 2026-08-28. Validated at the source as well as caught downstream.
_VALID_SUBDOMAIN = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)


def parse_slug(slug: str) -> tuple[str, str] | None:
    parts = (slug or "").split(":")
    if len(parts) != 2 or not all(parts):
        return None
    sub, domain = parts[0].strip(), parts[1].strip()
    if not _VALID_SUBDOMAIN.match(sub) or not domain:
        return None
    return sub, domain


def build_url(slug: str, start: int = 0) -> str:
    parsed = parse_slug(slug)
    if not parsed:
        return ""
    sub, domain = parsed
    return SEARCH.format(sub=sub, domain=domain, start=start, num=PAGE_SIZE)


def detail_url(slug: str, job_id: str | int) -> str:
    parsed = parse_slug(slug)
    if not parsed or job_id in (None, ""):
        return ""
    sub, domain = parsed
    return DETAIL.format(sub=sub, domain=domain, job_id=job_id)


def extract_jobs(payload: Any) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("positions"), list):
        return data["positions"]
    return []


def total_found(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("count"), int):
        return data["count"]
    return None


def board_name(payload: Any) -> str:
    """Eightfold does not name the employer in the payload; the caller knows."""
    return ""


def _job_url(slug: str, job: dict, detail_payload: dict | None) -> str:
    canonical = clean((detail_payload or {}).get("canonicalPositionUrl"))
    if canonical:
        return canonical
    parsed = parse_slug(slug)
    job_id = job.get("id") or (detail_payload or {}).get("id") or ""
    if parsed and job_id:
        return CAREERS.format(sub=parsed[0], job_id=job_id)
    path = clean(job.get("positionUrl"))
    if parsed and path:
        return f"https://{parsed[0]}.eightfold.ai{path}"
    return ""


def _location(job: dict, detail_payload: dict | None) -> str:
    """Prefer the standardized city-first form; the raw one also parses.

    Eightfold writes the raw field country-first ("US, CA, Santa Clara").
    This module used to reverse that itself, but parse_location handles
    country-first strings for every source as of 2026-08-28, so the local
    reverser was removed rather than left to drift from the shared one.
    """
    std = job.get("standardizedLocations")
    if isinstance(std, list) and std:
        return clean(std[0])
    for source in (job, detail_payload or {}):
        locations = source.get("locations")
        if isinstance(locations, list) and locations:
            return clean(locations[0])
        single = clean(source.get("location"))
        if single:
            return single
    return ""


def parse(job: dict, company: str, slug: str,
          detail_payload: dict | None = None) -> Posting | None:
    detail_payload = detail_payload or {}
    description = strip_html(detail_payload.get("job_description"))

    location_raw = _location(job, detail_payload)
    city, region, country = parse_location(location_raw)

    salary_min, salary_max = parse_salary(description)

    # postedTs is epoch seconds on the listing. t_create on the detail is the
    # req's creation, which can predate the posting by months, so it is only a
    # fallback and is marked low confidence when it is the one used.
    published, confidence = None, "none"
    posted_ts = job.get("postedTs")
    if isinstance(posted_ts, (int, float)) and posted_ts > 0:
        published, confidence = parse_datetime(int(posted_ts)), "high"
    if not published:
        created = detail_payload.get("t_create") or job.get("creationTs")
        if isinstance(created, (int, float)) and created > 0:
            published, confidence = parse_datetime(int(created)), "low"

    work_option = clean(job.get("workLocationOption")
                        or detail_payload.get("work_location_option")) or None
    work_model = parse_work_model(
        work_option, "remote" in location_raw.lower(), location_raw, description
    )

    custom = detail_payload.get("custom_JD")
    employment_type = None
    if isinstance(custom, dict):
        fields = custom.get("data_fields")
        if isinstance(fields, dict):
            time_type = fields.get("timeType")
            if isinstance(time_type, list) and time_type:
                employment_type = clean(time_type[0]) or None

    job_id = job.get("id") or detail_payload.get("id") or ""
    title = clean(job.get("name") or detail_payload.get("name")
                  or detail_payload.get("posting_name"))
    if not title:
        return None

    url = _job_url(slug, job, detail_payload)

    return Posting(
        source_id=str(clean(job.get("displayJobId")
                            or detail_payload.get("display_job_id")) or job_id),
        company=company,
        title=title,
        url=url,
        # Deliberately the public posting page, never `apply_redirect_url`,
        # which points straight at the employer's application form.
        apply_url=url,
        ats=NAME,
        source_slug=slug,
        location_raw=location_raw,
        city=city,
        region=region,
        country=country,
        workplace_type=work_model,
        is_remote=work_model == "Remote",
        department=clean(job.get("department")
                         or detail_payload.get("department")) or None,
        team=clean(detail_payload.get("business_unit")) or None,
        employment_type=employment_type,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_raw=None,
        equity_mentioned=mentions_equity(description),
        bonus_mentioned=mentions_bonus(description),
        published_at=published,
        date_confidence=confidence,
        description=description,
    )


def search(client: httpx.Client, slug: str, start: int = 0) -> dict | None:
    """One page of the listing. Kept here so the URL shape lives in one file."""
    url = build_url(slug, start)
    if not url:
        return None
    try:
        response = client.get(url, headers={"Accept": "application/json"})
    except (httpx.HTTPError, UnicodeError, ValueError):
        return None
    if response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def detail(client: httpx.Client, slug: str, job_id: str | int) -> dict | None:
    url = detail_url(slug, job_id)
    if not url:
        return None
    try:
        response = client.get(url, headers={"Accept": "application/json"})
    except (httpx.HTTPError, UnicodeError, ValueError):
        return None
    if response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None
