"""Hacker News "Ask HN: Who is hiring?" — a third lead channel.

Why this one
------------
It has the best signal density of any free source for Doran's archetype: AI and
startup roles, posted directly by the people doing the hiring. It needs no API
key, no account and no scraping of a protected site, and the monthly thread
format means staleness is bounded by construction -- an August thread is August
jobs, so the ghost-posting problem that plagues aggregators barely applies.

The convention, not a schema
----------------------------
Posts follow a community habit rather than a format:

    Company | Role | Location | Full Time | $range
    <prose describing the role>

So parsing is best-effort. The company name is the part worth getting right,
because it feeds the existing resolve-then-sweep path -- once resolved, the
posting itself comes from the employer's live ATS and the parse quality of the
comment stops mattering at all.

There is no title field to screen on, so the whole comment travels on the Lead
as `text` and the archetype screen reads that too.
"""

from __future__ import annotations

import html
import re

import httpx

from ..normalize import clean
from .boards import Lead

NAME = "hn"

USER_URL = "https://hacker-news.firebaseio.com/v0/user/whoishiring.json"
ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
ALGOLIA_URL = "https://hn.algolia.com/api/v1/items/{item_id}"
COMMENT_URL = "https://news.ycombinator.com/item?id={item_id}"

_TAG = re.compile(r"<[^>]+>")
_URL_IN_TEXT = re.compile(r"https?://\S+")
_WS = re.compile(r"\s+")


def _plain(text: str) -> str:
    """HN comment bodies are HTML fragments with entity-encoded URLs."""
    body = _TAG.sub(" ", text or "")
    body = html.unescape(body)
    return _WS.sub(" ", body).strip()


def hiring_threads(client: httpx.Client, limit: int = 2) -> list[int]:
    """Most recent 'Who is hiring?' thread ids, newest first.

    The whoishiring account alternates between "Who is hiring?", "Who wants to be
    hired?" and "Freelancer?" threads, so the titles have to be checked rather
    than assuming every other submission.
    """
    try:
        response = client.get(USER_URL)
        submitted = (response.json() or {}).get("submitted", [])
    except (httpx.HTTPError, ValueError, AttributeError):
        return []

    found: list[int] = []
    for item_id in submitted[:8]:
        try:
            item = client.get(ITEM_URL.format(item_id=item_id)).json() or {}
        except (httpx.HTTPError, ValueError):
            continue
        title = str(item.get("title") or "").lower()
        if "who is hiring" in title:
            found.append(int(item_id))
            if len(found) >= limit:
                break
    return found


def parse_comment(text: str, comment_id: int) -> Lead | None:
    """Best-effort extraction of company, role and location from one post."""
    plain = _plain(text)
    if len(plain) < 80:
        return None

    # Only the opening chunk follows the pipe convention; the prose after it
    # frequently contains pipes of its own.
    first = plain[:400]
    parts = [p.strip() for p in first.split("|")]
    if len(parts) < 2:
        return None

    company = _URL_IN_TEXT.sub("", parts[0])
    company = re.sub(r"[\(\)\[\]]", " ", company)
    company = clean(_WS.sub(" ", company))
    # Strip a trailing tagline: "Acme - we build X" -> "Acme".
    company = re.split(r"\s+[-–—]\s+", company)[0].strip()
    if not company or len(company) > 60 or len(company) < 2:
        return None

    title = clean(_URL_IN_TEXT.sub("", parts[1]))[:120]
    location = ""
    for part in parts[2:5]:
        if re.search(r"remote|onsite|on-site|hybrid|[A-Z]{2}\b|,", part or ""):
            location = clean(part)[:80]
            break

    return Lead(
        company=company,
        title=title or "(see posting)",
        url=COMMENT_URL.format(item_id=comment_id),
        location=location,
        board=NAME,
        text=plain,
    )


def search(client: httpx.Client, months: int = 1, on_note=None) -> list[Lead]:
    """Read the most recent hiring thread(s) and return one Lead per post."""
    leads: list[Lead] = []
    for thread_id in hiring_threads(client, limit=max(1, months)):
        try:
            payload = client.get(ALGOLIA_URL.format(item_id=thread_id)).json() or {}
        except (httpx.HTTPError, ValueError):
            continue
        children = payload.get("children") or []
        parsed = 0
        for child in children:
            if not isinstance(child, dict) or not child.get("text"):
                continue
            lead = parse_comment(child["text"], int(child.get("id") or thread_id))
            if lead:
                leads.append(lead)
                parsed += 1
        if on_note:
            on_note(f'board "HN who-is-hiring {thread_id}": '
                    f"{len(children)} posts, {parsed} parsed")
    return leads
