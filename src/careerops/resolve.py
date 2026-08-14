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
from .sources.registry import ADAPTERS, PROBE_ORDER, _client, probe_detailed

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


def resolve(company: str, *, force: bool = False) -> Resolution:
    """Find a live board for `company`. Checks the cache unless force=True."""
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
        result.status = "dead"
        result.note = (
            f"No live board found across {len(probe_order)} ATS x "
            f"{len(candidates)} slug variants. Try the Chrome fallback "
            "(open the careers page and read the ATS off the URL)."
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
