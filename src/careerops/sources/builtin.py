"""Built In — a second role-first lead channel alongside the LinkedIn guest search.

Why this exists
---------------
`sources.yml` has carried a `browser_boards` block listing Built In SF, Built In
Remote and LinkedIn since the project started, every entry marked
`enabled: true` -- and no Python ever read it. It was inert configuration that
looked like a working feature. This module makes the Built In half real.

Why Built In is worth having
----------------------------
It is server-rendered plain HTML with no bot protection, and each job page
embeds a schema.org `JobPosting` object carrying a **full description, a real
salary range, and a real `datePosted`**. That is strictly better data than the
LinkedIn guest cards, which give a rendered "2 weeks ago" and no salary.

How it stays inside the no-cached-search rule
---------------------------------------------
Identically to `boards.py`: Built In supplies LEADS. The employer is resolved to
its own ATS and swept from the live feed wherever possible. Only when a company
has no reachable ATS is the posting read from Built In's own live page, fetched
at scan time -- never from a snapshot.
"""

from __future__ import annotations

import html
import json
import re
import time

import httpx

from ..comp import parse_salary
from ..models import Posting
from ..normalize import clean, parse_location, parse_work_model, strip_html
from .boards import POLITE_DELAY, Lead

NAME = "builtin"

# The listing page carries a schema.org ItemList of the jobs on it: name, url and
# a one-line description per entry. Cheaper and far more stable than scraping the
# card markup, which changes with every redesign.
_ITEMLIST = re.compile(r'"@type"\s*:\s*"ListItem".*?"name"\s*:\s*"(.*?)".*?"url"\s*:\s*"(.*?)"', re.S)
_JOB_URL = re.compile(r"https://builtin[a-z]*\.com/job/[^\"'\s]+")


def _match_object(text: str, start: int) -> dict | None:
    """Parse the JSON object beginning at `start`, brace-matched and string-aware.

    String-aware matching matters: the description field is HTML and is full of
    braces and escaped quotes that naive counting trips over.
    """
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, min(len(text), start + 600_000)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except ValueError:
                    return None
    return None


def _slice_json_object(text: str, anchor: int) -> dict | None:
    """Pull the JobPosting object containing `anchor` out of a larger document.

    Built In embeds its JobPosting as a bare object inside page JavaScript rather
    than in a <script type="application/ld+json"> tag, so it cannot be parsed out
    by tag.

    Walking back to the nearest opening brace is not enough: the nearest one
    belongs to a SIBLING sub-object (applicantLocationRequirements, say), which
    parses perfectly well and yields the wrong dict. So keep walking outwards and
    accept only an object that actually declares itself a JobPosting.
    """
    start = text.rfind("{", 0, anchor)
    attempts = 0
    while start > 0 and attempts < 40:
        attempts += 1
        parsed = _match_object(text, start)
        if isinstance(parsed, dict) and parsed.get("@type") == "JobPosting":
            return parsed
        start = text.rfind("{", 0, start)
    return None


# Raised 3 -> 8 on 2026-08-26. Measured against the four postings Doran
# forwarded from his Built In digest: the "AI enablement" search runs 190
# results over 8 pages and then dries up on its own, and two of his four sat on
# pages 5 and 6 -- past the old cutoff, so reading three pages found half of
# what he had already spotted by hand. Paging stops as soon as a page returns
# nothing, so a narrow search still costs only the pages it actually has.
MAX_PAGES = 8


def search(client: httpx.Client, url: str, max_pages: int = MAX_PAGES) -> list[Lead]:
    """Read one Built In listing URL and return leads."""
    leads: list[Lead] = []
    seen: set[str] = set()

    for page in range(max_pages):
        paged = url if page == 0 else f"{url}{'&' if '?' in url else '?'}page={page + 1}"
        try:
            response = client.get(paged)
        except httpx.HTTPError:
            break
        if response.status_code != 200:
            break
        body = response.text

        found = 0
        for name, job_url in _ITEMLIST.findall(body):
            job_url = job_url.replace("\\/", "/").strip()
            if not job_url or job_url in seen:
                continue
            seen.add(job_url)
            found += 1
            leads.append(Lead(
                company="",          # filled in from the job page's JobPosting
                title=html.unescape(name).strip(),
                url=job_url,
                board=NAME,
            ))
        if not found:
            break
        time.sleep(POLITE_DELAY)

    return leads


def posting_from_lead(client: httpx.Client, lead: Lead) -> Posting | None:
    """Fetch one Built In job page and build a Posting from its JobPosting data."""
    try:
        response = client.get(lead.url)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None

    body = response.text
    anchor = body.find('"JobPosting"')
    if anchor == -1:
        anchor = body.find("hiringOrganization")
    if anchor == -1:
        return None
    data = _slice_json_object(body, anchor)
    if not isinstance(data, dict):
        return None

    org = data.get("hiringOrganization") or {}
    company = clean(org.get("name") if isinstance(org, dict) else str(org))
    title = clean(data.get("title") or lead.title)
    if not company or not title:
        return None

    description = strip_html(str(data.get("description") or ""))
    if len(description) < 200:
        return None

    # Salary comes structured here, which is better than parsing prose.
    salary_raw = ""
    smin = smax = None
    base = data.get("baseSalary")
    if isinstance(base, dict):
        value = base.get("value")
        if isinstance(value, dict):
            smin = value.get("minValue")
            smax = value.get("maxValue")
            smin = int(smin) if isinstance(smin, (int, float)) else None
            smax = int(smax) if isinstance(smax, (int, float)) else None
            if smin or smax:
                salary_raw = f"{base.get('currency', 'USD')} {smin or ''} - {smax or ''}".strip()
    if smin is None and smax is None and salary_raw:
        smin, smax = parse_salary(salary_raw)

    # schema.org allows jobLocation to be a single Place OR a list of them, and
    # Built In uses both. Reading only the dict form left multi-office postings
    # with an empty location, which the geography gate then rejected as "unknown
    # location" -- a true rejection reached by a false route. ClearView's "AI
    # Enablement Manager" is filed at Newton, Massachusetts and should be turned
    # down for being in Massachusetts, not for having no address at all.
    places = data.get("jobLocation")
    if isinstance(places, dict):
        places = [places]
    parts = []
    for place in places or []:
        if not isinstance(place, dict):
            continue
        address = place.get("address") or {}
        if not isinstance(address, dict):
            continue
        # A country with no city is not a location, it is an eligibility note --
        # a remote role open across the US and Canada lists {"addressCountry":
        # "USA"} and nothing else. Keeping those would produce "CAN / USA",
        # which reads as an unknown city and rejects a perfectly good remote job.
        if not address.get("addressLocality"):
            continue
        one = ", ".join(
            str(address.get(k)) for k in
            ("addressLocality", "addressRegion", "addressCountry")
            if address.get(k)
        )
        if one and one not in parts:
            parts.append(one)
    # Every office, so a posting listing Boston, New York AND San Francisco is
    # judged on the San Francisco one rather than on whichever came first.
    location_raw = " / ".join(parts)
    # Built In sets jobLocationType=TELECOMMUTE on postings that also carry a
    # physical address -- observed on Santa Ana, Warren and Louisville roles that
    # are plainly not fully remote. This is the same trap Ashby's `isRemote`
    # sets, and trusting it would mark hybrid Bay Area roles as Remote, skip the
    # commute penalty entirely, and inflate their scores. So the flag is passed
    # as a HINT only; parse_work_model weighs it against the stated location and
    # the description, exactly as it does for every other source.
    remote_flag = str(data.get("jobLocationType") or "").upper() == "TELECOMMUTE"
    if remote_flag and not location_raw:
        location_raw = "Remote"

    city, region, country = parse_location(location_raw)
    workplace_type = parse_work_model(None, remote_flag, location_raw, description)
    posted = str(data.get("datePosted") or "")[:10] or None

    return Posting(
        source_id=f"{NAME}:{lead.url.rsplit('/', 1)[-1]}",
        company=company,
        title=title,
        url=lead.url,
        apply_url=lead.url,
        ats=NAME,
        source_slug=NAME,
        location_raw=location_raw,
        city=city,
        region=region,
        country=country,
        is_remote=(workplace_type == "Remote"),
        workplace_type=workplace_type,
        employment_type=clean(str(data.get("employmentType") or "")) or None,
        salary_raw=salary_raw or None,
        salary_min=smin,
        salary_max=smax,
        published_at=posted,
        # Built In publishes a real ISO date in the JobPosting, unlike the
        # LinkedIn cards' rendered "2 weeks ago", so this is trustworthy.
        date_confidence="high" if posted else "none",
        description=description,
        extra={"validThrough": data.get("validThrough") or ""},
    )


def enabled_urls() -> list[tuple[str, str]]:
    """(label, url) for every enabled Built In entry in sources.yml."""
    from .. import config

    out: list[tuple[str, str]] = []
    for entry in (config.sources().get("browser_boards") or []):
        if not entry.get("enabled"):
            continue
        key = str(entry.get("key") or "")
        url = str(entry.get("url") or "")
        # LinkedIn in that config block needs an authenticated browser session;
        # the guest search in boards.py already covers it without one.
        if key.startswith("builtin") and url:
            out.append((str(entry.get("label") or key), url))
    return out
