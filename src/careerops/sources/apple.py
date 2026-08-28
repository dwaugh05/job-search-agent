"""Apple's own careers portal.

    GET https://jobs.apple.com/en-us/search?search={query}&sort=relevance
        &location=united-states-USA&page={n}
    GET https://jobs.apple.com/en-us/details/{position_id}

## Why this adapter exists

Apple was never in `config/sources.yml` at all -- not dead, not unresolved,
simply absent -- so no scan has ever looked at it. It is also one of the
companies in `config/connections.yml`, meaning Doran knows someone there and any
posting earns the +1.0 relationship bump. The two companies where he has an edge
(Apple and Meta) were the two the scanner could not see.

## There is no JSON API, but the HTML carries JSON

Both dead ends, confirmed 2026-08-27, so that nobody re-tries them:

  * POST /api/role/search   -> 301 to apple.com/pagenotfound
  * GET  /api/v1/search     -> 401 "User Unauthorized"

What does work is the ordinary search page. It is server-rendered and embeds
its result records as a DOUBLY escaped JSON blob (\\\\" in the raw bytes), 20
per page. The detail page embeds the same way and carries jobSummary,
description, minimumQualifications, preferredQualifications, homeOffice,
locations and the pay band. No login, no JS execution, no sitemap
(jobs.apple.com/sitemap.xml is a 404 and /en-us/sitemap.xml redirects to sign-in).

## Why this is query-driven rather than a full board sweep

Apple's search treats a multi-word query as OR-ish: `search=AI enablement`
returns ~2,998 of roughly 3,000 total reqs, so "everything matching" is
"everything". `sort=relevance` is what actually does the work, and `sort=newest`
returns noise. So this adapter runs the shared archetype query set and keeps the
top few relevance-ranked pages per query, rather than paging 150 times to
reconstruct a board that would then be title-screened anyway.

`totalRecords` is therefore meaningless as a filter signal. Do not use it.
"""

from __future__ import annotations

import html as html_mod
import re
from typing import Any

import httpx

from ..comp import mentions_bonus, mentions_equity, parse_salary
from ..models import Posting
from ..normalize import (clean, parse_datetime, parse_location,
                         parse_work_model, strip_html)

NAME = "apple"

SEARCH = ("https://jobs.apple.com/en-us/search?search={query}&sort=relevance"
          "&location=united-states-USA&page={page}")
DETAIL = "https://jobs.apple.com/en-us/details/{position_id}"

PAGE_SIZE = 20
# Relevance ranking means the useful hits are at the top. Past three pages the
# OR-ish matching has long since drifted off-archetype.
MAX_PAGES = 3

_POSITION_ID = re.compile(r'"positionId":"(\d+)"')
_TITLE = re.compile(r'"postingTitle":"((?:[^"\\]|\\.)*)"')
_POSTED = re.compile(r'"postDateInGMT":"([^"]+)"')
_SLUG = re.compile(r'"transformedPostingTitle":"([^"]*)"')
_HOME_OFFICE = re.compile(r'"homeOffice":(true|false)')
# Record fields sit within a few hundred characters of their positionId; 4000
# is slack, not a measurement, and only bounds how far a malformed record can
# reach into its neighbour.
_RECORD_WINDOW = 4000

# Once the double escaping is undone, the field values contain bare quotes and
# bare backslashes, so there is no escaping convention left to parse against.
# A regex alternation over escaped characters silently matches nothing on real
# Apple pages. Instead a value is read up to the next JSON field boundary --
# `","`, `"}` or `"]` -- which is the one sequence that cannot occur inside a
# value that has already been unescaped.
_VALUE_END = re.compile(r'","|"\}|"\]')


def unescape(markup: str) -> str:
    """Undo Apple's double escaping so the embedded JSON is readable.

    The blob arrives as \\\\" inside the HTML. One pass turns that into \\",
    the second into a plain quote. The \\uXXXX pairs Apple uses most are done
    explicitly because the surrounding text is not valid JSON on its own, so
    json.loads cannot be used to do it.
    """
    text = markup.replace('\\\\"', '"').replace('\\"', '"')
    for escaped, plain in (("\\u0026", "&"), ("\\u002F", "/"), ("\\u003C", "<"),
                           ("\\u003E", ">"), ("\\/", "/"), ("\\n", "\n"),
                           ("\\\\n", "\n"), ("\\t", " ")):
        text = text.replace(escaped, plain)
    return text


def _field(text: str, key: str, start: int = 0) -> str:
    """Read one string field out of the unescaped blob.

    `start` lets a caller anchor the read past an earlier marker, which matters
    because Apple's pages repeat keys: "description" appears once in a page-meta
    block and again in the job record, and the first is not the job.
    """
    marker = f'"{key}":"'
    index = text.find(marker, start)
    if index < 0:
        return ""
    index += len(marker)
    end = _VALUE_END.search(text, index)
    value = text[index:end.start()] if end else text[index:index + 20_000]
    return html_mod.unescape(value)


def build_url(slug: str = "", query: str = "", page: int = 1) -> str:
    """`slug` is unused -- Apple is a single employer -- but keeps the interface."""
    from urllib.parse import quote_plus
    return SEARCH.format(query=quote_plus(query or ""), page=max(1, page))


def detail_url(position_id: str | int) -> str:
    return DETAIL.format(position_id=position_id) if position_id else ""


def extract_jobs(payload: Any) -> list[dict]:
    """Pull the result records out of one search page's HTML.

    Deliberately tolerant: a record that does not yield a title is skipped
    rather than raised on, because the detail fetch is where the authoritative
    data comes from and a missed title only costs one candidate.
    """
    if not isinstance(payload, str):
        return []
    text = unescape(payload)
    jobs: list[dict] = []
    seen: set[str] = set()
    for match in _POSITION_ID.finditer(text):
        position_id = match.group(1)
        if position_id in seen:
            continue
        window = text[match.end():match.end() + _RECORD_WINDOW]
        title_match = _TITLE.search(window)
        if not title_match:
            continue
        seen.add(position_id)
        posted = _POSTED.search(window)
        slug_match = _SLUG.search(window)
        jobs.append({
            "positionId": position_id,
            "postingTitle": html_mod.unescape(title_match.group(1)),
            "postDateInGMT": posted.group(1) if posted else "",
            "transformedPostingTitle": slug_match.group(1) if slug_match else "",
        })
    return jobs


def _locations(text: str, start: int = 0) -> str:
    """Best location entry, rendered "City, State".

    Apple lists one req against several sites, and the array order is not
    preference order: "Agentic AI Product Manager, Platform - Sales" lists
    Austin first and Cupertino second. Taking the first entry put a Cupertino
    role in Texas, where the commute gate rejects it outright. California wins
    when it is on the list, because that is the one Doran can actually take.
    """
    block = re.search(r'"locations":\[(.*?)\]', text[start:], re.S)
    if not block:
        return ""
    entries = [chunk for chunk in block.group(1).split('{"id":"') if chunk.strip()]
    rendered: list[str] = []
    for entry in entries:
        city = _field(entry, "city") or _field(entry, "name")
        state = _field(entry, "stateProvince")
        if city:
            rendered.append(", ".join(part for part in (city, state) if part))
    if not rendered:
        return ""
    for candidate in rendered:
        if "California" in candidate:
            return candidate
    return rendered[0]


def parse(job: dict, company: str, slug: str = "",
          detail_html: str | None = None) -> Posting | None:
    position_id = str(job.get("positionId") or "")
    text = unescape(detail_html or "")

    # Anchor every read to the job record. "description" also appears in a
    # page-meta block near the top of the document, and reading that one gave
    # every Apple posting an identical, wrong body.
    anchor = text.find('"jobSummary":"')
    if anchor < 0:
        anchor = 0

    # postingTitle sits just BEFORE jobSummary in the record, so it is found by
    # walking back from the anchor rather than forward from it.
    title = clean(job.get("postingTitle"))
    if not title:
        back = text.rfind('"postingTitle":"', 0, anchor) if anchor else -1
        title = clean(_field(text, "postingTitle", back if back >= 0 else 0))
    if not position_id or not title:
        return None

    summary = strip_html(_field(text, "jobSummary", anchor))
    body = strip_html(_field(text, "description", anchor))
    minimum = strip_html(_field(text, "minimumQualifications", anchor))
    preferred = strip_html(_field(text, "preferredQualifications", anchor))
    # The pay band lives in a postingFooters localization block rather than in a
    # numeric field, so it is folded into the description and read by the same
    # salary parser every other adapter uses.
    footer = ""
    footer_match = re.search(r'"postingFooters":\[(.*?)\}\]', text, re.S)
    if footer_match:
        footer = strip_html(footer_match.group(1))
    description = "\n\n".join(p for p in (summary, body, minimum, preferred, footer) if p)

    location_raw = _locations(text, anchor)
    # Shared parser rather than a local split -- see the note in
    # sources/google.py.
    city, state, _country = parse_location(location_raw)

    salary_min, salary_max = parse_salary(description)

    published = parse_datetime(job.get("postDateInGMT")
                               or _field(text, "postDateInGMT") or None)

    # homeOffice is Apple's own remote flag and is the only structured signal
    # here; everything else is prose, so the shared resolver does the rest.
    home_office = _HOME_OFFICE.search(text)
    remote_flag = bool(home_office and home_office.group(1) == "true")
    work_model = parse_work_model(
        None, remote_flag, location_raw, description
    )

    url = detail_url(position_id)
    return Posting(
        source_id=position_id,
        company=company,
        title=title,
        url=url,
        apply_url=url,
        ats=NAME,
        source_slug=slug or NAME,
        location_raw=location_raw,
        city=city,
        region=state,
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
        published_at=published,
        date_confidence="high" if published else "none",
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


def detail(client: httpx.Client, position_id: str | int) -> str | None:
    return _get_text(client, detail_url(position_id))
