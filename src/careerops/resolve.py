"""Company name -> live ATS board.

Naming a company tells you nothing about where its jobs live. There is no
registry to look this up in, and slugs are genuinely unguessable in both
directions: DoorDash is `doordashusa` on Greenhouse (not `doordash`), Weights &
Biases is `wandb`. So we generate plausible slug variants and probe the real ATS
APIs concurrently, keeping whatever actually answers.

Every resolution is written back into sources.yml, so a company is only ever
resolved once and the source map gets better every time Doran names a new one.
"""

from __future__ import annotations

import concurrent.futures
import re
from dataclasses import dataclass, field

from . import config
from .sources import sniff, tokens
from .sources.registry import (
    ADAPTERS, PROBE_ORDER, _client, _squash, fetch_company, probe_detailed,
)

# Slugs that no naming rule would ever produce.
ALIASES: dict[str, list[str]] = {
    "doordash": ["doordashusa"],
    "weights & biases": ["wandb"],
    "weights and biases": ["wandb"],
    "block": ["square", "block"],
    "alphabet": ["google"],
    "meta": ["facebook"],
    "x": ["twitter"],
    "electronic arts": ["ea", "electronicarts"],
    "sony interactive entertainment": ["sonyinteractiveentertainment", "playstation"],
    "hugging face": ["huggingface"],
    "scale ai": ["scaleai", "scale"],
    "apollo.io": ["apolloio", "apollo"],
    "customer.io": ["customerio"],
    "grafana labs": ["grafanalabs", "grafana"],
    "mistral ai": ["mistralai", "mistral"],
    "together ai": ["togetherai", "together"],
    "abnormal security": ["abnormalsecurity", "abnormal"],
    "included health": ["includedhealth"],
    "omada health": ["omadahealth", "omada"],
    "hinge health": ["hingehealth"],
    "color health": ["colorhealth", "color"],
    "guardant health": ["guardanthealth", "guardant"],
    "gilead sciences": ["gilead"],
    "franklin templeton": ["franklintempleton"],
    "sofi": ["sofi", "socialfinance"],
    "servicenow": ["servicenow"],
    "life360": ["life360"],
    # Name collisions. Two unrelated real employers share a name, so no
    # name-matching heuristic can pick the right one -- it has to be pinned.
    # "gong" on SmartRecruiters is GONG!, an NYC media startup, not Gong.io.
    "gong": ["gongio"],
    "gong.io": ["gongio"],
}

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")
# Suffixes worth trying both with and without.
_TRAILING = ("ai", "io", "labs", "inc", "hq", "technologies", "software", "health")


@dataclass
class Resolution:
    company: str
    ats: str | None = None
    slug: str | None = None
    job_count: int = 0
    status: str = "dead"
    candidates_tried: int = 0
    verified: bool = False
    all_hits: list[tuple[str, str, int]] = field(default_factory=list)
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "live"


def slug_candidates(company: str) -> list[str]:
    """Ordered most-specific-first. Order is the tie-breaker when several hit."""
    name = _WS.sub(" ", _PUNCT.sub(" ", company.lower())).strip()
    if not name:
        return []

    out: list[str] = []

    def add(value: str) -> None:
        value = value.strip("-")
        if value and value not in out:
            out.append(value)

    for alias in ALIASES.get(name, []):
        add(alias)

    joined = name.replace(" ", "")
    hyphen = name.replace(" ", "-")
    add(joined)
    add(hyphen)

    # "DoorDash" -> "doordashusa"; the pattern that already caught us out.
    for suffix in ("usa", "us", "inc", "careers", "jobs", "global"):
        add(joined + suffix)

    words = name.split()
    if len(words) > 1:
        # Drop a trailing descriptor: "Scale AI" -> "scale", "Grafana Labs" -> "grafana"
        if words[-1] in _TRAILING:
            add("".join(words[:-1]))
            add("-".join(words[:-1]))
        # First word alone is a common shortening, but least specific -- last.
        add(words[0])

    return out[:10]


def resolve(company: str, *, force: bool = False, deep: bool = True) -> Resolution:
    """Find a live board for `company`. Checks the cache unless force=True.

    `deep` controls how hard the last-resort careers-page read tries. Reading a
    careers page is cheap when it succeeds and expensive when it does not --
    a dozen URL guesses, then a headless browser render for each plausible page.
    That is fine for one company at the command line, and ruinous in a scan
    resolving sixty unknown employers, where it measured out at minutes each.
    So bulk callers pass deep=False: same lookup, no browser, fewer guesses.
    """
    data = config.sources()
    entries = data.get("companies", []) or []

    if not force:
        for entry in entries:
            if entry.get("name", "").strip().lower() == company.strip().lower():
                if entry.get("status") == "live" and entry.get("ats") and entry.get("slug"):
                    return Resolution(
                        company=entry["name"],
                        ats=entry["ats"],
                        slug=entry["slug"],
                        status="live",
                        note="cache hit (no probes issued)",
                    )

    # Cheapest route first: a local index of ~29k board slugs that actually
    # exist, derived from Common Crawl. Guessing costs ~45 requests and finds
    # roughly a third of companies, because a slug is not derivable from a name
    # -- DoorDash is `doordashusa`, Zipline is `ziplines`. A lookup costs one
    # probe per candidate and finds them outright.
    indexed = tokens.lookup(company)
    if indexed:
        with _client() as client:
            for ats, slug in indexed:
                if ats not in ADAPTERS:
                    continue
                try:
                    ok, count, verified = probe_detailed(ats, slug, client, company)
                except Exception:
                    continue
                if ok and verified:
                    return Resolution(
                        company=company, ats=ats, slug=slug, status="live",
                        job_count=count, verified=True, candidates_tried=1,
                        note="matched a known board slug from the local ATS index",
                    )

    candidates = slug_candidates(company)
    probe_order = data.get("ats_probe_order") or PROBE_ORDER
    probe_order = [a for a in probe_order if a in ADAPTERS]

    pairs = [
        (ats, slug, slug_rank, probe_order.index(ats))
        for slug_rank, slug in enumerate(candidates)
        for ats in probe_order
    ]

    hits: list[tuple[int, int, int, str, str, int]] = []
    with _client() as client:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = {
                pool.submit(probe_detailed, ats, slug, client, company):
                    (ats, slug, slug_rank, ats_rank)
                for ats, slug, slug_rank, ats_rank in pairs
            }
            for future in concurrent.futures.as_completed(futures):
                ats, slug, slug_rank, ats_rank = futures[future]
                try:
                    ok, count, verified = future.result()
                except Exception:
                    continue
                if ok:
                    # 0 sorts before 1, so verified boards win outright.
                    hits.append((0 if verified else 1, slug_rank, ats_rank,
                                 ats, slug, count))

    result = Resolution(company=company, candidates_tried=len(pairs))
    if not hits:
        # Slug guessing has failed. Before giving up, read the board address off
        # the company's own careers page. This is the only route to Workday
        # employers at all -- their slug is a tenant:instance:site triple that is
        # discovered, never guessed, so they are invisible to the probe loop.
        sniffed = sniff.sniff(
            company,
            use_browser=deep,
            max_pages=12 if deep else 6,
            # One company at the CLI can afford to be thorough. Sixty of them in
            # a scan cannot: unbounded, this phase took over five minutes per
            # failed company and dominated the entire run.
            budget_seconds=60.0 if deep else 12.0,
        )
        if sniffed:
            ats, slug = sniffed
            postings = []
            try:
                postings = fetch_company(ats, slug, company)
            except Exception:
                postings = []
            if postings:
                result.ats = ats
                result.slug = slug
                result.job_count = len(postings)
                result.all_hits = [(ats, slug, len(postings))]
                # Same verification bar the probe path uses. A careers page can
                # link to a PARENT company's board -- Imperva's links to Thales
                # -- and accepting that unchecked would ingest thousands of
                # someone else's postings under this company's name.
                blob = _squash(" ".join(
                    f"{p.company} {p.title} {(p.description or '')[:400]}"
                    for p in postings[:40]
                ))
                wanted = _squash(company)
                result.verified = bool(
                    wanted and (wanted in blob
                                or (len(wanted) > 5 and wanted[:6] in blob))
                )
                if result.verified:
                    result.status = "live"
                    result.note = (
                        "slug probing failed; found this board linked from the "
                        "company's own careers page, and its postings name "
                        f"{company}"
                    )
                else:
                    result.status = "unverified"
                    result.note = (
                        f"careers page links to {ats}/{slug}, which returns "
                        f"{len(postings)} postings, but none of them mention "
                        f"'{company}'. This is probably a parent or sister "
                        "company's board - confirm before trusting it."
                    )
                return result

        result.status = "dead"
        result.note = (
            f"No live board found across {len(probe_order)} ATS x "
            f"{len(candidates)} slug variants, and no ATS link was readable on "
            "the company's careers page (it may be JavaScript-rendered)."
        )
        return result

    # Rank by: does the board actually mention this company, then most specific
    # slug variant, then ATS probe order. Sorting by job count instead would let
    # a short variant like "gong" win with a board belonging to someone else.
    hits.sort(key=lambda h: (h[0], h[1], h[2]))
    verified_flag, slug_rank, ats_rank, ats, slug, count = hits[0]

    result.ats = ats
    result.slug = slug
    result.job_count = count
    result.verified = verified_flag == 0
    result.all_hits = [(h[3], h[4], h[5]) for h in hits]

    if not result.verified:
        # Every live board we found looks like a different employer. Better to
        # report this than to silently ingest another company's postings.
        result.status = "unverified"
        result.note = (
            f"found a live board at {ats}/{slug} but '{company}' does not appear "
            "anywhere in its postings - this is probably a different employer. "
            "Confirm the careers page before trusting it."
        )
        return result

    result.status = "live"
    if len(hits) > 1:
        others = ", ".join(f"{a}/{s}" for a, s, _ in result.all_hits[1:4])
        result.note = f"picked most specific verified match; also live: {others}"
    return result


def save_resolution(res: Resolution, *, watch: bool | None = None) -> None:
    """Cache a resolution back into sources.yml."""
    data = config.sources()
    entries = data.setdefault("companies", [])

    for entry in entries:
        if entry.get("name", "").strip().lower() == res.company.strip().lower():
            entry["ats"] = res.ats
            entry["slug"] = res.slug
            entry["status"] = res.status
            if watch is not None:
                entry["watch"] = watch
            config.save_sources(data)
            return

    entries.append(
        {
            "name": res.company,
            "ats": res.ats,
            "slug": res.slug,
            "status": res.status,
            "watch": bool(watch),
        }
    )
    config.save_sources(data)


def resolve_many(companies: list[str], *, force: bool = False) -> list[Resolution]:
    results: list[Resolution] = []
    for company in companies:
        results.append(resolve(company, force=force))
    return results
