"""Adapter registry, HTTP plumbing, and slug probing.

All network access for ATS feeds funnels through here so timeouts, retries,
user-agent, and concurrency are consistent -- and so there is exactly one place
to audit that we only ever read live feeds.
"""

from __future__ import annotations

import concurrent.futures
import json
import re
import threading
import time
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx

from .. import config
from ..models import Posting
from . import (apple, ashby, eightfold, google, greenhouse, lever,
               smartrecruiters, workable, workday)

ADAPTERS: dict[str, Any] = {
    greenhouse.NAME: greenhouse,
    ashby.NAME: ashby,
    lever.NAME: lever,
    smartrecruiters.NAME: smartrecruiters,
    workable.NAME: workable,
    workday.NAME: workday,
    eightfold.NAME: eightfold,
    apple.NAME: apple,
    google.NAME: google,
}

# Single-employer portals with no board endpoint. Neither publishes a feed that
# can be enumerated, so both are searched with the shared archetype query set
# and their results deduplicated -- see _fetch_portal.
PORTALS = {apple.NAME, google.NAME}

PROBE_ORDER = [greenhouse.NAME, ashby.NAME, lever.NAME,
               smartrecruiters.NAME, workable.NAME]
# workday is intentionally NOT in the probe order -- its slug is a
# tenant:instance:site triple discovered from robots.txt, not a guessable name.
# eightfold is out for the same reason: its slug packs subdomain and domain
# ("nvidia:nvidia.com"), and the search endpoint answers 422 without the domain,
# so a probe cannot be assembled from the company name alone.

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 careerops/0.1"
)
# Large boards are genuinely large: Greenhouse's content=true response for
# DoorDash is ~8 MB and OpenAI's Ashby board carries 700+ postings. A short read
# timeout here fails silently and is indistinguishable from "this company has no
# jobs", which quietly drops whole employers from every scan.
TIMEOUT = httpx.Timeout(90.0, connect=15.0)

# Probing is a different job from fetching. The 90s read timeout above exists so
# a genuinely huge board (DoorDash's Greenhouse payload is ~8MB) is never
# truncated. A PROBE only asks "does this slug exist?" and its answer is small,
# so it must fail fast: nine probes per ATS per company, serialised by the
# per-host throttle, turn a 90s timeout into thirteen minutes of dead waiting
# for one company when a provider stops responding.
PROBE_TIMEOUT = httpx.Timeout(12.0, connect=5.0)
MAX_WORKERS = 8
RETRIES = 2

# ---------------------------------------------------------------------------
# Politeness: per-host rate limiting and backoff.
#
# Getting blocked by Greenhouse, Ashby or Lever would break the entire workflow,
# and the block would outlast the run that caused it. So the defaults here are
# deliberately conservative: a scan is allowed to take hours. Nothing in this
# module needs to be fast, it needs to still work tomorrow.
#
# Every value is overridable from the `politeness` block in config/profile.yml.
_POLITENESS = dict(config.profile().get("politeness") or {})
MIN_INTERVAL = float(_POLITENESS.get("min_seconds_between_requests_per_host", 0.34))
BACKOFF_BASE = float(_POLITENESS.get("backoff_base_seconds", 2.0))
BACKOFF_MAX = float(_POLITENESS.get("backoff_max_seconds", 120.0))
RATE_LIMIT_RETRIES = int(_POLITENESS.get("rate_limit_retries", 5))
MAX_WORKERS = int(_POLITENESS.get("max_workers", MAX_WORKERS))

HOST_FAILURE_LIMIT = int(_POLITENESS.get("host_failure_limit", 3))

_host_lock = threading.Lock()
_next_allowed: dict[str, float] = {}
# Circuit breaker. A host that keeps timing out is dead for this process.
#
# Without this, one unresponsive provider stalls an entire scan: probing a
# company issues nine requests to each ATS, the per-host throttle serialises
# them, and nine 90-second read timeouts back to back is thirteen minutes for a
# SINGLE company. Observed live -- apply.workable.com accepted connections and
# never answered, and every one of the nine hanging probes was Workable.
_host_failures: dict[str, int] = {}
_host_down: set[str] = set()


def _host_of(url: str) -> str:
    try:
        return urlsplit(url).netloc.lower()
    except ValueError:
        return url


def _wait_turn(url: str) -> None:
    """Block until this host is allowed another request.

    Serialises per host across the worker threads, so raising MAX_WORKERS
    parallelises *across* boards without ever pointing more load at one of them.
    """
    host = _host_of(url)
    while True:
        with _host_lock:
            now = time.monotonic()
            ready_at = _next_allowed.get(host, 0.0)
            if now >= ready_at:
                _next_allowed[host] = now + MIN_INTERVAL
                return
            delay = ready_at - now
        time.sleep(delay)


def _penalise(url: str, seconds: float) -> None:
    """Push this host's next-allowed time out, so every thread backs off."""
    host = _host_of(url)
    with _host_lock:
        _next_allowed[host] = max(
            _next_allowed.get(host, 0.0), time.monotonic() + seconds
        )


def _host_is_down(url: str) -> bool:
    with _host_lock:
        return _host_of(url) in _host_down


def _record_failure(url: str) -> None:
    host = _host_of(url)
    with _host_lock:
        _host_failures[host] = _host_failures.get(host, 0) + 1
        if HOST_FAILURE_LIMIT and _host_failures[host] >= HOST_FAILURE_LIMIT:
            _host_down.add(host)


def _record_success(url: str) -> None:
    host = _host_of(url)
    with _host_lock:
        if _host_failures.get(host):
            _host_failures[host] = 0


def down_hosts() -> list[str]:
    """Hosts abandoned this run, so a scan can report them rather than hide it."""
    with _host_lock:
        return sorted(_host_down)


def _retry_after(response: httpx.Response, attempt: int) -> float:
    """Honour Retry-After when the server sends one, else exponential backoff."""
    raw = response.headers.get("Retry-After")
    if raw:
        try:
            return min(float(raw), BACKOFF_MAX)
        except ValueError:
            pass
    return min(BACKOFF_BASE * (2 ** attempt), BACKOFF_MAX)

# SmartRecruiters needs one extra request per posting for the description body.
# We cap that and report what we skipped rather than silently truncating.
SR_DETAIL_CAP = 60
_SR_WORTH_DETAIL = re.compile(
    r"(market|growth|brand|demand|gtm|go.to.market|content|web|digital|"
    r"communication|revenue|ai\b|artificial intelligence|automation|enablement|"
    r"technolog|operations|campaign|lifecycle|product marketing|"
    # Added 2026-08-25. This screen decides which SmartRecruiters and Workday
    # titles are worth a detail fetch, and "MarTech Engineer" cleared none of
    # the stems above -- "market" needs the k, "technolog" needs the o. A title
    # in Doran's own known_title_variants list was invisible on two whole ATS
    # platforms.
    r"martech|agentic|applied ai|solutions? architect|solutions? engineer|"
    r"revops|answer engine|aeo\b|llm|generative|copilot|prompt)",
    re.IGNORECASE,
)


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"},
    )


def _get_json(client: httpx.Client, url: str,
              timeout: httpx.Timeout | None = None,
              max_attempts: int | None = None) -> Any | None:
    """GET and decode JSON, retrying transient failures.

    Returns None both for "no such board" and for "the request failed", so
    callers that care about the difference should probe explicitly.
    """
    response = _get_response(client, url, timeout=timeout, max_attempts=max_attempts)
    if response is None:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _get_text(client: httpx.Client, url: str,
              timeout: httpx.Timeout | None = None,
              max_attempts: int | None = None) -> str | None:
    """GET an HTML page through the same rate limiting and backoff as a feed.

    Apple and Google serve their postings as server-rendered HTML rather than
    JSON. That is a difference in encoding, not in how carefully we are allowed
    to hit somebody else's servers, so it shares _get_response.
    """
    response = _get_response(client, url, timeout=timeout, max_attempts=max_attempts)
    return response.text if response is not None else None


def _get_response(client: httpx.Client, url: str,
                  timeout: httpx.Timeout | None = None,
                  max_attempts: int | None = None) -> httpx.Response | None:
    """One polite GET: per-host throttle, backoff, circuit breaker.

    This is the single place where outbound read traffic is paced. Everything
    that talks to somebody else's server goes through here.
    """
    if _host_is_down(url):
        return None

    attempts = (max_attempts if max_attempts is not None
                else max(RETRIES, RATE_LIMIT_RETRIES) + 1)
    for attempt in range(attempts):
        if _host_is_down(url):
            return None
        _wait_turn(url)
        try:
            response = (client.get(url, timeout=timeout) if timeout is not None
                        else client.get(url))
        except (httpx.HTTPError, UnicodeError, ValueError):
            # Includes read and connect timeouts, which is how a hung host
            # presents. Count it: enough of these and we stop talking to this
            # host for the rest of the run.
            _record_failure(url)
            if attempt < RETRIES and not _host_is_down(url):
                time.sleep(min(BACKOFF_BASE * (2 ** attempt), BACKOFF_MAX))
                continue
            return None
        _record_success(url)
        if response.status_code == 404:
            return None
        if response.status_code == 429:
            # A genuine rate limit. Answering it with an immediate retry is how
            # you turn a throttle into a ban, so wait -- and hold the whole host
            # back with us, since every other worker is about to hit the same
            # wall.
            if attempt < attempts - 1:
                delay = _retry_after(response, attempt)
                _penalise(url, delay)
                time.sleep(delay)
                continue
            return None
        if response.status_code >= 500:
            # NOT a rate limit. Slug probing generates 5xx routinely -- it is
            # what several ATS platforms return for "no such board" -- so
            # treating these like 429s was catastrophic: six retries backing off
            # to 120s each, while _penalise froze every other probe queued for
            # that host. Thirty probes would finish in three seconds and the
            # remaining fifteen would hang for minutes. Retry briefly, never
            # penalise the host.
            if attempt < RETRIES:
                time.sleep(min(0.5 * (2 ** attempt), 2.0))
                continue
            return None
        if response.status_code != 200:
            return None
        return response
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

    # Eightfold identifies the employer by SUBDOMAIN, not in the payload: the
    # positions carry only title, department and location, so a text search for
    # "nvidia" fails on NVIDIA's own board. The slug is resolved once by hand
    # and stored, so trusting it is correct here and the text check is not.
    if ats == eightfold.NAME:
        return True

    # Apple and Google are single-employer portals: the host IS the employer,
    # so there is no wrong-company-behind-a-plausible-slug failure to guard
    # against, and the postings themselves rarely repeat the company name.
    if ats in PORTALS:
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
        elif ats in PORTALS:
            # These serve HTML, not JSON, and have no board to enumerate. A
            # live probe is "does an archetype search return any result at
            # all" -- enough to tell a working portal from a broken one.
            adapter = ADAPTERS[ats]
            payload = _get_text(
                client, adapter.build_url(query="AI enablement", page=1),
                timeout=PROBE_TIMEOUT, max_attempts=1,
            )
        else:
            # One attempt only. Retrying a probe is pointless -- a failure here
            # means "this slug is not it", and the caller has dozens more to
            # try. With retries, a single unresponsive provider cost 90 seconds
            # per probe and nine probes per company.
            payload = _get_json(client, adapter.build_url(slug),
                                timeout=PROBE_TIMEOUT, max_attempts=1)
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

        # Eightfold splits listing from description across two endpoints, the
        # same shape as Workday, so it needs the same list-then-detail handling
        # rather than the generic single GET.
        if ats == eightfold.NAME:
            return _fetch_eightfold(client, slug, company, on_note)

        # Apple and Google have no enumerable board, only a search box.
        if ats in PORTALS:
            return _fetch_portal(ats, client, slug, company, on_note)

        if ats == smartrecruiters.NAME:
            # The list endpoint caps at 100 per request and this code only ever
            # asked once, so every posting past the hundredth at any employer was
            # invisible -- Freshworks reports 163. The response states totalFound,
            # so paging stops as soon as we have them all.
            raw_jobs = []
            payload = None
            for page in range(smartrecruiters.MAX_PAGES):
                batch_payload = _get_json(
                    client,
                    adapter.build_url(slug, offset=page * smartrecruiters.PAGE_SIZE),
                )
                if batch_payload is None:
                    # A failure partway through leaves a partial board. Say so --
                    # silently returning half an employer's postings is the same
                    # class of bug as the 100-posting cap this pagination fixed.
                    if page and on_note:
                        on_note(
                            f"{company}: SmartRecruiters page {page + 1} failed, "
                            f"only the first {len(raw_jobs)} postings were read"
                        )
                    break
                payload = payload or batch_payload
                batch = adapter.extract_jobs(batch_payload)
                if not batch:
                    break
                raw_jobs.extend(batch)
                total = smartrecruiters.total_found(batch_payload)
                if total is not None and len(raw_jobs) >= total:
                    break
                if len(batch) < smartrecruiters.PAGE_SIZE:
                    break
            if payload is None:
                return []
        else:
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


PORTAL_DETAIL_CAP = 60


def _portal_queries() -> list[str]:
    """The archetype query set, shared with the role-first board channel.

    Reusing boards.py's list on purpose: two vocabularies for the same archetype
    would drift apart, and a term added for LinkedIn should reach Apple and
    Google on the same run.
    """
    from . import boards
    seen: set[str] = set()
    ordered: list[str] = []
    for query in list(boards.DEFAULT_QUERIES_AI) + list(boards.DEFAULT_QUERIES_GROWTH):
        key = query.strip().lower()
        if key and key not in seen:
            seen.add(key)
            ordered.append(query)
    return ordered


def _fetch_portal(ats, client, slug, company, on_note=None):
    """Search a single-employer portal for the archetype and read the hits.

    Apple and Google both answer a search box and neither exposes an
    enumerable board, so "sweep the company" means "run every archetype query
    and union the results". Both rank by relevance, so depth past the first
    couple of pages is noise rather than supply.
    """
    adapter = ADAPTERS[ats]
    found: dict[str, dict] = {}
    for query in _portal_queries():
        for page in range(1, adapter.MAX_PAGES + 1):
            payload = _get_text(client, adapter.build_url(query=query, page=page))
            if not payload:
                break
            batch = adapter.extract_jobs(payload)
            if not batch:
                break
            for job in batch:
                key = str(job.get("positionId") or job.get("id") or "")
                if key:
                    found.setdefault(key, job)

    if not found and on_note:
        on_note(f"{company}: {ats} search returned nothing")

    candidates = [
        job for job in found.values()
        if _SR_WORTH_DETAIL.search(str(job.get("postingTitle") or job.get("title") or ""))
    ]
    skipped = len(found) - len(candidates)
    if len(candidates) > PORTAL_DETAIL_CAP:
        skipped += len(candidates) - PORTAL_DETAIL_CAP
        candidates = candidates[:PORTAL_DETAIL_CAP]
    if skipped and on_note:
        on_note(
            f"{company}: fetched {len(candidates)} of {len(found)} {ats} postings "
            f"in detail ({skipped} skipped as clearly off-domain or over the cap)"
        )

    postings, failures = [], 0
    for job in candidates:
        try:
            if ats == apple.NAME:
                html = adapter.detail(client, job.get("positionId"))
            else:
                html = adapter.detail(client, job.get("id"), job.get("slug"))
            posting = adapter.parse(job, company, slug, detail_html=html)
        except Exception:
            failures += 1
            continue
        if posting and posting.title and posting.url:
            postings.append(posting)
    if failures and on_note:
        on_note(f"{company}: {failures}/{len(candidates)} {ats} postings failed to parse")
    return postings


EIGHTFOLD_DETAIL_CAP = 80


def _fetch_eightfold(client, slug, company, on_note=None):
    """Eightfold pages 10 at a time and hides descriptions behind a detail call.

    NVIDIA's board is ~2,695 reqs, so a full listing sweep is ~270 metadata
    requests. That is the cheap half. Pulling a description for all of them
    would be 2,695 more, so titles are screened first and only plausible roles
    are read in full -- the same trade Workday and SmartRecruiters make here.
    """
    listings: list[dict] = []
    for page in range(eightfold.MAX_PAGES):
        payload = eightfold.search(client, slug, start=page * eightfold.PAGE_SIZE)
        batch = eightfold.extract_jobs(payload)
        if not batch:
            break
        listings.extend(batch)
        total = eightfold.total_found(payload)
        if total is not None and len(listings) >= total:
            break

    if not listings and on_note:
        on_note(f"{company}: Eightfold listing returned nothing")

    candidates = [j for j in listings if _SR_WORTH_DETAIL.search(str(j.get("name") or ""))]
    skipped = len(listings) - len(candidates)
    if len(candidates) > EIGHTFOLD_DETAIL_CAP:
        skipped += len(candidates) - EIGHTFOLD_DETAIL_CAP
        candidates = candidates[:EIGHTFOLD_DETAIL_CAP]
    if skipped and on_note:
        on_note(
            f"{company}: fetched {len(candidates)} of {len(listings)} Eightfold "
            f"postings in detail ({skipped} skipped as clearly off-domain "
            "or over the detail cap)"
        )

    postings, failures = [], 0
    for job in candidates:
        try:
            detail = eightfold.detail(client, slug, job.get("id") or "")
            posting = eightfold.parse(job, company, slug, detail_payload=detail)
        except Exception:
            failures += 1
            continue
        if posting and posting.title and posting.url:
            postings.append(posting)
    if failures and on_note:
        on_note(f"{company}: {failures}/{len(candidates)} Eightfold postings failed to parse")
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
        except (httpx.HTTPError, UnicodeError, ValueError):
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
