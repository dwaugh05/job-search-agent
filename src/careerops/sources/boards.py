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
MAX_PAGES = 4
POLITE_DELAY = 1.2  # seconds between board requests

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
]
DEFAULT_QUERIES_GROWTH = [
    "growth marketing manager",
    "conversion rate optimization manager",
    "website growth marketing",
    "web growth manager",
]


def _text(fragment: str, pattern: re.Pattern[str]) -> str:
    match = pattern.search(fragment)
    return html.unescape(match.group(1)).strip() if match else ""


def search_linkedin(
    client: httpx.Client,
    keywords: str,
    location: str = "United States",
    days: int = 30,
    max_pages: int = MAX_PAGES,
) -> list[Lead]:
    """One live search against LinkedIn's public guest endpoint."""
    leads: list[Lead] = []
    seen: set[str] = set()
    seconds = max(1, days) * 86400

    for page in range(max_pages):
        url = LINKEDIN_SEARCH.format(
            keywords=httpx.QueryParams({"k": keywords})["k"].replace(" ", "%20"),
            location=location.replace(" ", "%20"),
            seconds=seconds,
            start=page * PAGE_SIZE,
        )
        try:
            response = client.get(url)
        except httpx.HTTPError:
            break
        if response.status_code != 200:
            break

        cards = _CARD.findall(response.text)
        if not cards:
            break

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

        if len(cards) < PAGE_SIZE:
            break
        time.sleep(POLITE_DELAY)

    return leads


def fetch_lead_description(client: httpx.Client, lead: Lead) -> str:
    """Read one posting's body from the board's live page.

    Only used when a company has no reachable ATS feed -- otherwise the employer
    feed is the source of truth and this is skipped entirely.
    """
    if not lead.job_id:
        return ""
    try:
        response = client.get(LINKEDIN_JOB.format(job_id=lead.job_id))
    except httpx.HTTPError:
        return ""
    if response.status_code != 200:
        return ""

    match = re.search(
        r'(?is)<div[^>]*description__text[^>]*>(.*?)</div>\s*</div>', response.text
    )
    body = match.group(1) if match else response.text
    body = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", body)
    body = re.sub(r"(?i)<br\s*/?>", "\n", body)
    body = re.sub(r"(?i)</(p|li|ul|div)>", "\n", body)
    body = re.sub(r"(?i)<li[^>]*>", "- ", body)
    body = re.sub(r"<[^>]+>", " ", body)
    body = html.unescape(body)
    body = re.sub(r"[ \t]+", " ", body)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def salary_from_card(client: httpx.Client, lead: Lead) -> str:
    """LinkedIn shows an employer-provided range on the job page when present."""
    if not lead.job_id:
        return ""
    try:
        response = client.get(LINKEDIN_JOB.format(job_id=lead.job_id))
    except httpx.HTTPError:
        return ""
    if response.status_code != 200:
        return ""
    match = re.search(r"salary__range[^>]*>\s*([^<]+)<", response.text)
    return clean(match.group(1)) if match else ""


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
    for query in queries:
        found = search_linkedin(client, query, location=location, days=days)
        fresh = [lead for lead in found if lead.url not in seen]
        seen.update(lead.url for lead in fresh)
        out.extend(fresh)
        if on_note:
            on_note(f'board query "{query}": {len(found)} hits, {len(fresh)} new')
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
