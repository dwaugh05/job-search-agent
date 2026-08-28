"""Cross-company discovery -- the channel that finds employers we don't know about.

## The gap this closes

Every other source in this package is COMPANY-FIRST: we hold a list of employers
in sources.yml and sweep each one's ATS feed. That makes the seed list a hard
ceiling. A perfect remote role at a company nobody thought to add is invisible,
no matter how well it scores.

Doran caught this exactly: "a company that's remote that perfectly fits my needs
doesn't even show up in your search". He was right. Delinea's "AI Marketing
Solutions Engineer" -- US Remote, reusable prompt libraries, human-in-the-loop
guardrails, and a 4.45 on the rubric -- was never seen, purely because Delinea
was not in the list.

This module searches ROLE-FIRST instead: query live job boards for the archetype,
then work backwards to the employer.

## How this stays inside the no-cached-search rule

CLAUDE.md forbids sourcing postings from cached HTML or aggregator snapshots.
The rule is respected by using boards for LEADS ONLY:

  1. Search a live board page at scan time for candidate company + title pairs.
  2. Resolve the company to its real ATS and add it to sources.yml, so the
     posting itself is fetched from the live employer feed -- the source of
     truth -- on this run and every run after.
  3. Only when a company has no reachable ATS do we read the posting from the
     board's own live page, fetched at scan time, never from a snapshot.

The compounding effect matters more than any single find: every unknown employer
a search surfaces is permanently added to the sweep.
"""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass

import httpx

from ..normalize import clean, parse_datetime

NAME = "boards"

# LinkedIn's unauthenticated job-search endpoint. Public, live, and returns job
# cards as HTML fragments. f_TPR=r{seconds} bounds it to recent postings.
LINKEDIN_SEARCH = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    "?keywords={keywords}&location={location}&f_TPR=r{seconds}&start={start}"
)
LINKEDIN_JOB = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

PAGE_SIZE = 10
# Raised 4 -> 12 on 2026-08-25. The old cap was firing on every query -- the scan
# log for run 14 shows exactly 40 hits query after query, which is the ceiling,
# not the supply. Measured the same day: every query tried still returned real,
# on-archetype results at rank 990, so the supply is at least 1000 per query and
# LinkedIn ignores sortBy (also measured), which leaves depth as the only lever.
#
# 12 pages reaches rank 120, not 1000. That is a deliberate compromise, not the
# whole fix: 25 queries x 12 pages is already ~7.5 minutes of LinkedIn traffic,
# and this is the one host whose goodwill the entire role-first channel depends
# on. Widening the QUERY SET is the cheaper way to reach a role sitting at rank
# 400 -- a more specific query moves it up the list rather than paying to walk
# down to it. Raise this only alongside evidence that throttling stays quiet.
MAX_PAGES = 12
# start >= 1000 returns HTTP 400. Nothing above this exists to fetch. MAX_PAGES
# does not currently reach it; this is the guard for when it does.
MAX_START = 1000
POLITE_DELAY = 1.2  # seconds between board requests

# LinkedIn throttles by answering 200 with an empty body rather than 429, so a
# throttled page is indistinguishable from an exhausted one unless it is retried.
THROTTLE_RETRIES = 3
THROTTLE_BACKOFF = 4.0  # seconds, doubled per consecutive failure

# One dead channel for a run is recoverable; an IP block outlasts the run that
# caused it. Past this many throttle events the LinkedIn channel gives up.
THROTTLE_ABORT = 12

_CARD = re.compile(r"<li>(.*?)</li>", re.S)
_TITLE = re.compile(r"<h3[^>]*>(.*?)</h3>", re.S)
_COMPANY = re.compile(r"<h4[^>]*>.*?>([^<]+)</a>", re.S)
_URL = re.compile(r'href="(https://www\.linkedin\.com/jobs/view/[^"?]+)')
_DATE = re.compile(r'datetime="([\d-]+)"')
_LOCATION = re.compile(r'job-search-card__location[^>]*>([^<]+)<', re.S)
_JOB_ID = re.compile(r"-(\d+)(?:\?|$)")


@dataclass
class Lead:
    """A candidate posting seen on a board. Not yet a Posting."""
    company: str
    title: str
    url: str
    location: str = ""
    posted_at: str | None = None
    board: str = "linkedin"
    # Free-text body, when the source gives one up front. Hacker News hiring
    # posts are prose with no title field to screen on, so the archetype screen
    # reads this too -- see _LEAD_WORTH_RESOLVING in pipeline.py.
    text: str = ""

    @property
    def job_id(self) -> str:
        match = _JOB_ID.search(self.url)
        return match.group(1) if match else ""


# Queries are the archetype stated the way employers title it. Track A first,
# then the growth-marketing backup track.
DEFAULT_QUERIES_AI = [
    "AI enablement marketing",
    "marketing AI enablement",
    "AI marketing technologist",
    "marketing engineer",
    "GTM engineer",
    "AI transformation marketing",
    "AI enablement",
    # Added 2026-08-14. Two of Doran's 4.0+ matches in run 11 -- Checkr and
    # Included Health, both "Staff AI Solutions Engineer" -- were found ONLY
    # because those companies were already on the watch list. No query here
    # would have surfaced them, so the same title at an unknown employer was
    # invisible. Doran: "I think you need to add other keywords to your search."
    "AI solutions engineer",
    "AI solutions architect",
    "staff AI solutions",
    "AI solutions",
    "AI program enablement",
    # Added 2026-08-25, from titles this system has already scored 4.0+ but only
    # ever found because the employer was already on the watch list. Note "AI
    # transformation" bare: it existed only inside "AI transformation marketing",
    # and the highest-scoring posting on record -- ButterflyMX, "Director, AI
    # Strategy & Transformation", 4.86 -- matches neither that compound phrase
    # nor any other query here.
    "AI transformation",
    "AI strategy",
    "AI adoption",
    "MarTech",
    "agentic AI go to market",
    "AI automation marketing",
    "AI center of excellence",
    "revenue operations AI",
]
DEFAULT_QUERIES_GROWTH = [
    "growth marketing manager",
    "conversion rate optimization manager",
    "website growth marketing",
    "web growth manager",
    # Doran's capture half of the funnel has a new name as search moves to
    # answer engines; MongoDB's "Answer Engine Optimization (AEO) Lead" and
    # ServiceNow's "Director, SEO & AEO" both scored track B but were only seen
    # because those companies were already watched.
    "answer engine optimization",
]


def _text(fragment: str, pattern: re.Pattern[str]) -> str:
    match = pattern.search(fragment)
    return html.unescape(match.group(1)).strip() if match else ""


class ThrottleBudget:
    """Counts how often LinkedIn pushed back during one scan.

    Kept per-scan rather than per-query: the signal that matters is "this run is
    being throttled", and that only shows up across queries.
    """

    def __init__(self, limit: int = THROTTLE_ABORT) -> None:
        self.limit = limit
        self.events = 0

    @property
    def spent(self) -> bool:
        return self.events >= self.limit

    def hit(self, note: str) -> None:
        self.events += 1


def _throttled(budget, reason: str) -> None:
    if budget is not None:
        budget.hit(reason)


def search_linkedin(
    client: httpx.Client,
    keywords: str,
    location: str = "United States",
    days: int = 30,
    max_pages: int = MAX_PAGES,
    budget: "ThrottleBudget | None" = None,
) -> list[Lead]:
    """One live search against LinkedIn's public guest endpoint."""
    leads: list[Lead] = []
    seen: set[str] = set()
    seconds = max(1, days) * 86400

    for page in range(max_pages):
        start = page * PAGE_SIZE
        if start >= MAX_START:
            break
        url = LINKEDIN_SEARCH.format(
            keywords=httpx.QueryParams({"k": keywords})["k"].replace(" ", "%20"),
            location=location.replace(" ", "%20"),
            seconds=seconds,
            start=start,
        )

        cards: list[str] = []
        for attempt in range(THROTTLE_RETRIES):
            try:
                response = client.get(url)
            except (httpx.HTTPError, UnicodeError, ValueError):
                break
            if response.status_code == 400:
                # start >= 1000. This is the real end of the endpoint, measured.
                return leads
            if response.status_code in (429, 500, 502, 503):
                _throttled(budget, f"HTTP {response.status_code}")
                time.sleep(THROTTLE_BACKOFF * (2 ** attempt))
                continue
            if response.status_code != 200:
                break
            cards = _CARD.findall(response.text)
            if cards:
                break
            # 200 with an empty body is LinkedIn's soft throttle, NOT the end of
            # the results. Measured 2026-08-25: pages that returned nothing at
            # ~1s spacing returned a full ten on retry a few seconds later, and
            # real results run to rank 990 on every query tried. Reading this as
            # "no more results" is why queries have been quietly ending early.
            _throttled(budget, "empty body")
            time.sleep(THROTTLE_BACKOFF * (2 ** attempt))

        if not cards:
            break

        before = len(leads)
        for card in cards:
            job_url = _text(card, _URL)
            title = _text(card, _TITLE)
            company = _text(card, _COMPANY)
            if not (job_url and title and company) or job_url in seen:
                continue
            seen.add(job_url)
            leads.append(Lead(
                company=company,
                title=title,
                url=job_url,
                location=_text(card, _LOCATION),
                posted_at=parse_datetime(_text(card, _DATE)),
            ))

        # A page of pure duplicates means the result set has wrapped or dried up.
        # Stop on that as well as on a short page -- LinkedIn pads rather than
        # ending cleanly.
        if len(leads) == before or len(cards) < PAGE_SIZE:
            break
        time.sleep(POLITE_DELAY)

    return leads


def fetch_lead_page(client: httpx.Client, lead: Lead) -> tuple[str, str]:
    """Read one posting's body AND its salary range in a single request.

    These used to be two functions issuing two GETs to the identical URL, which
    doubled this project's LinkedIn traffic for nothing. LinkedIn soft-throttles
    by answering 200 with an empty body, so halving the request count is not a
    tidiness change -- it directly halves how fast we walk into the throttle.
    """
    if not lead.job_id:
        return "", ""
    try:
        response = client.get(LINKEDIN_JOB.format(job_id=lead.job_id))
    except (httpx.HTTPError, UnicodeError, ValueError):
        return "", ""
    if response.status_code != 200:
        return "", ""
    return _parse_description(response.text), _parse_salary(response.text)


def _parse_salary(page: str) -> str:
    match = re.search(r"salary__range[^>]*>\s*([^<]+)<", page)
    return clean(match.group(1)) if match else ""


def _parse_description(page: str) -> str:
    match = re.search(
        r'(?is)<div[^>]*description__text[^>]*>(.*?)</div>\s*</div>', page
    )
    body = match.group(1) if match else page
    body = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", body)
    body = re.sub(r"(?i)<br\s*/?>", "\n", body)
    body = re.sub(r"(?i)</(p|li|ul|div)>", "\n", body)
    body = re.sub(r"(?i)<li[^>]*>", "- ", body)
    body = re.sub(r"<[^>]+>", " ", body)
    body = html.unescape(body)
    body = re.sub(r"[ \t]+", " ", body)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def fetch_lead_description(client: httpx.Client, lead: Lead) -> str:
    """Body only. Prefer fetch_lead_page when the salary is wanted too."""
    return fetch_lead_page(client, lead)[0]


def salary_from_card(client: httpx.Client, lead: Lead) -> str:
    """LinkedIn shows an employer-provided range on the job page when present."""
    return fetch_lead_page(client, lead)[1]


def discover(
    client: httpx.Client,
    queries: list[str] | None = None,
    location: str = "United States",
    days: int = 30,
    on_note=None,
) -> list[Lead]:
    """Run every query and return de-duplicated leads."""
    queries = queries or (DEFAULT_QUERIES_AI + DEFAULT_QUERIES_GROWTH)
    seen: set[str] = set()
    out: list[Lead] = []
    budget = ThrottleBudget()
    for query in queries:
        if budget.spent:
            # Stop asking. Getting blocked by LinkedIn would outlast this run,
            # and the other two channels below still work.
            if on_note:
                on_note(
                    f"linkedin: stopped after {budget.events} throttle responses "
                    f"- {len(queries) - queries.index(query)} queries not run this "
                    "run. Built In and Hacker News are unaffected."
                )
            break
        found = search_linkedin(client, query, location=location, days=days,
                                budget=budget)
        fresh = [lead for lead in found if lead.url not in seen]
        seen.update(lead.url for lead in fresh)
        out.extend(fresh)
        if on_note:
            # "40 hits" used to be ambiguous between "that is all there was" and
            # "that is where the page cap stopped us". Saying how deep the query
            # actually went makes the difference visible.
            depth = -(-len(found) // PAGE_SIZE)
            on_note(f'board query "{query}": {len(found)} hits over {depth} page(s), '
                    f'{len(fresh)} new')
        time.sleep(POLITE_DELAY)

    # Second channel. Built In is server-rendered with no bot protection and each
    # job page carries a full schema.org JobPosting -- a real description, a real
    # salary range and a real ISO datePosted, all better than a LinkedIn card.
    from . import builtin

    for label, url in builtin.enabled_urls():
        found = builtin.search(client, url)
        fresh = [lead for lead in found if lead.url not in seen]
        seen.update(lead.url for lead in fresh)
        out.extend(fresh)
        if on_note:
            on_note(f'board "{label}": {len(found)} hits, {len(fresh)} new')
        time.sleep(POLITE_DELAY)

    # Third channel. Highest signal density for the AI/startup archetype, free,
    # no key, and inherently fresh -- a monthly thread cannot carry a year-old
    # ghost posting the way an aggregator index can.
    from . import hn

    found = hn.search(client, months=1, on_note=on_note)
    fresh = [lead for lead in found if lead.url not in seen]
    seen.update(lead.url for lead in fresh)
    out.extend(fresh)

    return out
