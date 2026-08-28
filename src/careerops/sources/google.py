"""Google's own careers portal.

    GET https://www.google.com/about/careers/applications/jobs/results/?q={query}
    GET https://www.google.com/about/careers/applications/jobs/results/{id}-{slug}

## Why this adapter exists

Google was never in `config/sources.yml`, so no scan has ever looked at it. Its
Growth AI Transformation team is described in its own postings as "the central
marketing team driving Owned and Operated growth agentic innovation for all of
Google Marketing" -- squarely Doran's archetype, and entirely invisible.

## Shape

Server-rendered. A plain GET with a desktop User-Agent returns ~1.2 MB of HTML
containing every result as `jobs/results/{numeric-id}-{slug}`, and the detail
page carries the full description, qualifications, responsibilities, locations
and pay band in the raw markup. No login, no JS execution, no Cloudflare.

There is NO public JSON API. Both of these 404, confirmed 2026-08-27:

    careers.google.com/api/v3/search/
    /about/careers/applications/api/v3/search/

The page's own data comes from Google's internal batchexecute RPC, which is not
a stable scrape target and is not used here.

## Two gotchas that shape this file

**No posting dates, anywhere.** There is no datePosted field and no JSON-LD
block. `published_at` is therefore always None, which means the freshness gate
sees a first sighting, admits the posting once with a `no_publish_date` flag,
and rejects it on later runs. That is the correct behaviour: each Google role
gets exactly one evaluation, at the point we first see it.

**The `location=` parameter barely filters.** Identical result sets came back
for San Francisco, Mountain View and Sunnyvale, so location is parsed off each
detail page instead of trusted from the query.
"""

from __future__ import annotations

import html as html_mod
import re
from typing import Any

import httpx

from ..comp import mentions_bonus, mentions_equity, parse_salary
from ..models import Posting
from ..normalize import clean, parse_location, parse_work_model

NAME = "google"

BASE = "https://www.google.com/about/careers/applications/jobs/results/"
SEARCH = BASE + "?q={query}&page={page}"
DETAIL = BASE + "{job_id}-{slug}"

# Google paginates but the archetype queries are narrow enough that the useful
# hits are on the first page or two.
MAX_PAGES = 2

_RESULT = re.compile(r"jobs/results/(\d{6,})-([a-z0-9\-]+)")
_TITLE = re.compile(r"<title>(.*?)</title>", re.S)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
# Google's embedded JS payload escapes its markup as <b> rather than
# writing real tags, so tag-stripping alone leaves "<b>Raleigh, NC"
# sitting in what should be a clean location string.
_UNICODE_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})")

# The posting body sits between these two markers on every detail page. The
# tail marker is Google's boilerplate privacy paragraph, which is where the
# useful text stops and the equal-opportunity block begins.
_BODY_START = "Minimum qualifications:"
_BODY_END = "Information collected and processed as part of your Google Careers"

# "Note: By applying to this position you will have an opportunity to share your
# preferred working location from the following: San Francisco, CA, USA; ..."
_PREFERRED_LOCATIONS = re.compile(
    r"preferred working location from the following:\s*(.+?)\s*(?:\.|Minimum qualifications)",
    re.S,
)


def _text(markup: str) -> str:
    decoded = _UNICODE_ESCAPE.sub(
        lambda m: chr(int(m.group(1), 16)), markup or ""
    )
    return _WS.sub(" ", html_mod.unescape(_TAG.sub(" ", decoded))).strip()


def build_url(slug: str = "", query: str = "", page: int = 1) -> str:
    from urllib.parse import quote_plus
    return SEARCH.format(query=quote_plus(query or ""), page=max(1, page))


def detail_url(job_id: str, slug: str) -> str:
    return DETAIL.format(job_id=job_id, slug=slug) if job_id and slug else ""


def extract_jobs(payload: Any) -> list[dict]:
    """(id, slug) pairs from one results page, in page order, de-duplicated."""
    if not isinstance(payload, str):
        return []
    jobs: list[dict] = []
    seen: set[str] = set()
    for match in _RESULT.finditer(payload):
        job_id, slug = match.group(1), match.group(2)
        if job_id in seen:
            continue
        seen.add(job_id)
        jobs.append({"id": job_id, "slug": slug,
                     "title": slug.replace("-", " ").strip()})
    return jobs


def _location(text: str, body_start: int) -> str:
    """Location from the RENDERED job header, favouring California.

    Two traps here, both found on live pages on 2026-08-27.

    A detail page embeds a JavaScript payload carrying OTHER jobs as well as
    this one. Searching the whole document for "preferred working location"
    picked up a note belonging to a different req: "AI GTM Practice Lead" is
    based in Tokyo, but the first such note in its payload reads Raleigh and
    Durham. So the search is bounded to the text BEFORE the qualifications
    marker, which is this job's own header.

    Google also lists one req against many cities, and the order is not
    preference order. California is chosen when it is offered, because that is
    the one Doran can take; the first listed city is the fallback.
    """
    header = text[:body_start] if body_start > 0 else text
    # The header repeats site navigation, so only the block nearest the body
    # belongs to this posting.
    window = header[-2500:]

    options: list[str] = []
    match = _PREFERRED_LOCATIONS.search(window)
    if match:
        options = [clean(part) for part in match.group(1).split(";") if clean(part)]
    if not options:
        marker = window.rfind("place ")
        if marker >= 0:
            # "place San Francisco, CA, USA ; Atlanta, GA, USA ; +5 more"
            tail = window[marker + len("place "):]
            tail = re.split(r"\bbar_chart\b|\+\d+\s+more", tail)[0]
            options = [clean(part) for part in tail.split(";") if clean(part)]
    options = [o for o in options if o and len(o) < 80]
    if not options:
        return ""
    for option in options:
        if re.search(r",\s*CA\b", option):
            return option
    return options[0]


def parse(job: dict, company: str, slug: str = "",
          detail_html: str | None = None) -> Posting | None:
    job_id = str(job.get("id") or "")
    if not job_id or not detail_html:
        return None

    title_match = _TITLE.search(detail_html)
    title = clean(html_mod.unescape(title_match.group(1))) if title_match else ""
    # Every page titles itself "<Role> — Google Careers".
    for suffix in (" — Google Careers", " - Google Careers", "— Google Careers"):
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
    if not title or title.lower().startswith("google careers"):
        return None

    text = _text(detail_html)
    start = text.find(_BODY_START)
    end = text.find(_BODY_END)
    if start < 0:
        return None
    description = text[start: end if end > start else start + 12_000].strip()

    location_raw = _location(text, start)
    # Shared parser rather than a local split: it knows country-first
    # strings, ATS codes and city aliases, and a private parts[0] here
    # would drift from it.
    city, region, _country = parse_location(location_raw)

    salary_min, salary_max = parse_salary(description)
    work_model = parse_work_model(None, False, location_raw, description)

    url = detail_url(job_id, str(job.get("slug") or ""))
    return Posting(
        source_id=job_id,
        company=company,
        title=title,
        url=url,
        apply_url=url,
        ats=NAME,
        source_slug=slug or NAME,
        location_raw=location_raw,
        city=city,
        region=region,
        country="United States" if location_raw else None,
        workplace_type=work_model,
        is_remote=work_model == "Remote",
        department=None,
        team=None,
        employment_type=None,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_raw=None,
        equity_mentioned=mentions_equity(description),
        bonus_mentioned=mentions_bonus(description),
        # Google publishes no posting date. Stated explicitly rather than
        # guessed -- see the module docstring.
        published_at=None,
        date_confidence="none",
        description=description,
    )


def _get_text(client: httpx.Client, url: str) -> str | None:
    try:
        response = client.get(url, headers={"Accept": "text/html,*/*"})
    except (httpx.HTTPError, UnicodeError, ValueError):
        return None
    if response.status_code != 200:
        return None
    return response.text


def search(client: httpx.Client, query: str, page: int = 1) -> str | None:
    return _get_text(client, build_url(query=query, page=page))


def detail(client: httpx.Client, job_id: str, slug: str) -> str | None:
    return _get_text(client, detail_url(job_id, slug))
