"""Adapter registry, HTTP plumbing, and slug probing.

All network access for ATS feeds funnels through here so timeouts, retries,
user-agent, and concurrency are consistent -- and so there is exactly one place
to audit that we only ever read live feeds.
"""

from __future__ import annotations

import concurrent.futures
import json
import re
from typing import Any, Callable

import httpx

from ..models import Posting
from . import ashby, greenhouse, lever, smartrecruiters, workable, workday

ADAPTERS: dict[str, Any] = {
    greenhouse.NAME: greenhouse,
    ashby.NAME: ashby,
    lever.NAME: lever,
    smartrecruiters.NAME: smartrecruiters,
    workable.NAME: workable,
    workday.NAME: workday,
}

PROBE_ORDER = [greenhouse.NAME, ashby.NAME, lever.NAME,
               smartrecruiters.NAME, workable.NAME]
# workday is intentionally NOT in the probe order -- its slug is a
# tenant:instance:site triple discovered from robots.txt, not a guessable name.

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 careerops/0.1"
)
# Large boards are genuinely large: Greenhouse's content=true response for
# DoorDash is ~8 MB and OpenAI's Ashby board carries 700+ postings. A short read
# timeout here fails silently and is indistinguishable from "this company has no
# jobs", which quietly drops whole employers from every scan.
TIMEOUT = httpx.Timeout(90.0, connect=15.0)
MAX_WORKERS = 8
RETRIES = 2

# SmartRecruiters needs one extra request per posting for the description body.
# We cap that and report what we skipped rather than silently truncating.
SR_DETAIL_CAP = 60
_SR_WORTH_DETAIL = re.compile(
    r"(market|growth|brand|demand|gtm|go.to.market|content|web|digital|"
    r"communication|revenue|ai\b|artificial intelligence|automation|enablement|"
    r"technolog|operations|campaign|lifecycle|product marketing)",
    re.IGNORECASE,
)


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"},
    )


def _get_json(client: httpx.Client, url: str) -> Any | None:
    """GET and decode JSON, retrying transient failures.

    Returns None both for "no such board" and for "the request failed", so
    callers that care about the difference should probe explicitly.
    """
    for attempt in range(RETRIES + 1):
        try:
            response = client.get(url)
        except httpx.HTTPError:
            if attempt < RETRIES:
                continue
            return None
        if response.status_code == 404:
            return None
        if response.status_code >= 500 or response.status_code == 429:
            if attempt < RETRIES:
                continue
            return None
        if response.status_code != 200:
            return None
        try:
            return response.json()
        except ValueError:
            return None
    return None


_URL_RE = re.compile(r"https?://\S+")


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _company_matches(company: str, ats: str, jobs: list, payload: Any) -> bool:
    """Does this board plausibly belong to `company`?

    Checked against the posting *text*, with URLs stripped first. Without that
    strip the check is meaningless: every payload echoes its own slug inside
    jobUrl/absolute_url, so searching the raw JSON for "gong" always succeeds
    even when the board belongs to somebody else entirely.
    """
    wanted = _squash(company)
    if not wanted:
        return True

    # SmartRecruiters is the only one of the five that states the employer
    # outright. When it does, that is the authoritative answer.
    if ats == smartrecruiters.NAME:
        for job in jobs[:5]:
            name = (job.get("company") or {})
            name = name.get("name") if isinstance(name, dict) else name
            if name:
                declared = _squash(str(name))
                return wanted in declared or declared in wanted

    blob = _squash(_URL_RE.sub(" ", json.dumps(payload)[:400_000]))
    if wanted in blob:
        return True
    # Allow a distinctive leading fragment so "Weights & Biases" still matches a
    # board whose prose says "W&B" or "wandb".
    return len(wanted) > 5 and wanted[:6] in blob


def probe(
    ats: str,
    slug: str,
    client: httpx.Client | None = None,
    company: str | None = None,
) -> tuple[bool, int]:
    """Is this (ats, slug) a real, populated job board? -> (ok, job_count)."""
    ok, count, _ = probe_detailed(ats, slug, client, company)
    return ok, count


def probe_detailed(
    ats: str,
    slug: str,
    client: httpx.Client | None = None,
    company: str | None = None,
) -> tuple[bool, int, bool]:
    """-> (ok, job_count, name_verified).

    `name_verified` guards against a plausible slug belonging to a *different*
    employer. Probing "gong" on SmartRecruiters returns a live board full of
    NYC social-media internships that has nothing to do with the revenue
    intelligence company. Without this check that board's postings would enter
    the pipeline under the wrong company name.
    """
    adapter = ADAPTERS.get(ats)
    if not adapter or not slug:
        return False, 0, False

    owns_client = client is None
    client = client or _client()
    try:
        if ats == workday.NAME:
            payload = workday.search(client, slug, offset=0)
        else:
            payload = _get_json(client, adapter.build_url(slug))
        if payload is None:
            return False, 0, False
        jobs = adapter.extract_jobs(payload)
        if not jobs:
            return False, 0, False

        verified = True
        if company:
            verified = _company_matches(company, ats, jobs, payload)
        return True, len(jobs), verified
    finally:
        if owns_client:
            client.close()


def fetch_company(
    ats: str,
    slug: str,
    company: str,
    client: httpx.Client | None = None,
    on_note: Callable[[str], None] | None = None,
) -> list[Posting]:
    """Pull every live posting for one company. Returns [] on any failure."""
    adapter = ADAPTERS.get(ats)
    if not adapter or not slug:
        return []

    owns_client = client is None
    client = client or _client()
    try:
        # Workday must be handled BEFORE the generic GET: its endpoint is
        # POST-only, so _get_json returns None and every Workday employer looked
        # like it had zero openings.
        if ats == workday.NAME:
            return _fetch_workday(client, slug, company, on_note)

        payload = _get_json(client, adapter.build_url(slug))
        if payload is None:
            return []
        raw_jobs = adapter.extract_jobs(payload)

        postings: list[Posting] = []
        if ats == smartrecruiters.NAME:
            candidates = [
                job for job in raw_jobs
                if _SR_WORTH_DETAIL.search(
                    " ".join(
                        str(job.get(k) or "") if not isinstance(job.get(k), dict)
                        else str((job.get(k) or {}).get("label") or "")
                        for k in ("name", "department", "function")
                    )
                )
            ]
            skipped = len(raw_jobs) - len(candidates)
            if len(candidates) > SR_DETAIL_CAP:
                skipped += len(candidates) - SR_DETAIL_CAP
                candidates = candidates[:SR_DETAIL_CAP]
            if skipped and on_note:
                on_note(
                    f"{company}: fetched {len(candidates)} of {len(raw_jobs)} "
                    f"SmartRecruiters postings in detail ({skipped} skipped as "
                    "clearly off-domain or over the detail cap)"
                )
            sr_failures = 0
            for job in candidates:
                try:
                    detail = _get_json(
                        client,
                        smartrecruiters.detail_url(slug, str(job.get("id") or "")),
                    )
                    posting = adapter.parse(job, company, slug, detail=detail)
                except Exception:
                    sr_failures += 1
                    continue
                if posting and posting.source_id:
                    postings.append(posting)
            if sr_failures and on_note:
                on_note(
                    f"{company}: {sr_failures}/{len(candidates)} SmartRecruiters "
                    "postings failed to parse - investigate, this usually means a bug"
                )
        else:
            parse_failures = 0
            for job in raw_jobs:
                try:
                    posting = adapter.parse(job, company, slug)
                except Exception:  # one malformed record must not kill the sweep
                    parse_failures += 1
                    continue
                if posting and posting.source_id and posting.title:
                    postings.append(posting)
            # Never swallow this silently. A parse bug fails every record
            # identically and is otherwise indistinguishable from an employer
            # with no open roles.
            if parse_failures and on_note:
                on_note(
                    f"{company}: {parse_failures}/{len(raw_jobs)} postings failed to "
                    f"parse ({ats}) - investigate, this usually means a code bug"
                )
        return postings
    finally:
        if owns_client:
            client.close()


def fetch_many(
    targets: list[tuple[str, str, str]],
    on_note: Callable[[str], None] | None = None,
) -> tuple[list[Posting], dict[str, int]]:
    """Fetch many companies concurrently. targets = [(ats, slug, company), ...]"""
    results: list[Posting] = []
    per_company: dict[str, int] = {}

    with _client() as client:
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(fetch_company, ats, slug, company, client, on_note): company
                for ats, slug, company in targets
            }
            for future in concurrent.futures.as_completed(futures):
                company = futures[future]
                try:
                    postings = future.result()
                except Exception as exc:
                    # Report rather than swallow. A crashed adapter and an
                    # employer with no openings both yield zero postings, and
                    # confusing the two hides bugs for weeks.
                    postings = []
                    if on_note:
                        on_note(
                            f"{company}: fetch raised {type(exc).__name__}: {exc} "
                            "- treated as zero postings"
                        )
                per_company[company] = len(postings)
                results.extend(postings)

    return results, per_company


WORKDAY_DETAIL_CAP = 80


def _fetch_workday(client, slug, company, on_note=None):
    """Workday paginates 20 at a time and hides descriptions behind a detail call.

    We page through the list, screen titles cheaply, and only pull detail for
    plausible roles -- a 700-posting board would otherwise cost 700 requests.
    """
    listings = []
    for page in range(workday.MAX_PAGES):
        payload = workday.search(client, slug, offset=page * workday.PAGE_SIZE)
        batch = workday.extract_jobs(payload)
        if not batch:
            break
        listings.extend(batch)
        total = (payload or {}).get("total", 0)
        if len(listings) >= total:
            break

    candidates = [j for j in listings if _SR_WORTH_DETAIL.search(str(j.get("title") or ""))]
    skipped = len(listings) - len(candidates)
    if len(candidates) > WORKDAY_DETAIL_CAP:
        skipped += len(candidates) - WORKDAY_DETAIL_CAP
        candidates = candidates[:WORKDAY_DETAIL_CAP]
    if skipped and on_note:
        on_note(
            f"{company}: fetched {len(candidates)} of {len(listings)} Workday "
            f"postings in detail ({skipped} skipped as clearly off-domain "
            "or over the detail cap)"
        )

    postings, failures = [], 0
    for job in candidates:
        try:
            detail = workday.detail(client, slug, str(job.get("externalPath") or ""))
            posting = workday.parse(job, company, slug, detail_payload=detail)
        except Exception:
            failures += 1
            continue
        if posting and posting.title and posting.url:
            postings.append(posting)
    if failures and on_note:
        on_note(f"{company}: {failures}/{len(candidates)} Workday postings failed to parse")
    return postings


def check_url_live(url: str, client: httpx.Client | None = None) -> bool:
    """Liveness check: does this apply URL still resolve to a real page?

    Read-only. We never interact with the application form -- see CLAUDE.md.
    """
    if not url:
        return False
    owns_client = client is None
    client = client or _client()
    try:
        try:
            response = client.get(url)
        except httpx.HTTPError:
            return False
        if response.status_code >= 400:
            return False
        body = response.text.lower()
        dead_markers = (
            "no longer accepting applications",
            "this job is no longer available",
            "position has been filled",
            "job not found",
            "posting is closed",
            "we are no longer accepting",
        )
        return not any(marker in body for marker in dead_markers)
    finally:
        if owns_client:
            client.close()
