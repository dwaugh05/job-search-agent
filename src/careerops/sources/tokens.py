"""A local index of known ATS board slugs, used to make resolution cheap.

The problem this solves
-----------------------
`resolve.resolve()` finds a company's board by GUESSING: it generates slug
variants from the company name and probes each one against every ATS -- roughly
45 HTTP requests per company. It works when the slug looks like the name and
fails completely otherwise, which is most of the time. Measured hit rate during
the run-11 follow-up was 9 of 30, and 26 of 62 on hand-picked local companies.

The reason it cannot do better is structural, not a bug: **no ATS offers a
discovery endpoint.** Greenhouse, Ashby and Lever are per-board by design, so
there is no way to ask "which companies are on this platform?" DoorDash is
`doordashusa`; nothing derived from the name would ever find it.

What this does instead
----------------------
Public Common Crawl-derived datasets enumerate the board slugs that actually
exist -- roughly 29,000 of them across Greenhouse, Lever, Ashby and Workday.
Held locally, that turns resolution from "guess 45 URLs" into "look the name up
in an index, then verify the one candidate it returns."

Why this is NOT added to the sweep
----------------------------------
Adding 29,000 companies to `sources.yml` would be the wrong move: every entry
there is swept on every future run, and at the deliberate ~3 requests/second/host
politeness limit that is days of traffic for a queue Doran would never read. So
the index is consulted on demand, during resolution, and nothing is added to the
sweep unless a real company was actually being looked for.

Licence: the upstream datasets are CC BY-NC 4.0 -- non-commercial use with
attribution, which covers Doran's personal job search. The code that built them
is MIT.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

from .. import config
from . import ashby, greenhouse, lever, workday

SOURCE = "https://raw.githubusercontent.com/Feashliaa/job-board-aggregator/main/data/"
ATTRIBUTION = (
    "ATS slug index derived from Common Crawl by github.com/Feashliaa/"
    "job-board-aggregator, CC BY-NC 4.0."
)

# Upstream filename -> our ATS name.
FILES: dict[str, str] = {
    "greenhouse_companies.json": greenhouse.NAME,
    "lever_companies.json": lever.NAME,
    "ashby_companies.json": ashby.NAME,
    "workday_companies.json": workday.NAME,
}

CACHE = config.DATA_DIR / "ats_tokens.json"

_INDEX: dict[str, list[tuple[str, str]]] | None = None


def _normalise(value: str) -> str:
    """Collapse a company name or slug to a comparable key."""
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def refresh(on_note=None) -> dict[str, int]:
    """Download the slug lists and cache them locally. Run occasionally."""
    from .registry import _client

    payload: dict[str, list[str]] = {}
    counts: dict[str, int] = {}
    with _client() as client:
        for filename, ats in FILES.items():
            try:
                response = client.get(SOURCE + filename)
                if response.status_code != 200:
                    continue
                slugs = response.json()
            except Exception:
                continue
            if not isinstance(slugs, list):
                continue
            clean = [str(s).strip() for s in slugs if str(s).strip()]
            payload[ats] = clean
            counts[ats] = len(clean)
            if on_note:
                on_note(f"tokens: {ats} {len(clean)} slugs")

    if payload:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        with io.open(CACHE, "w", encoding="utf-8") as handle:
            json.dump({"attribution": ATTRIBUTION, "slugs": payload}, handle)
        global _INDEX
        _INDEX = None
    return counts


def _load() -> dict[str, list[tuple[str, str]]]:
    """Build {normalised_key: [(ats, slug), ...]} from the cache."""
    global _INDEX
    if _INDEX is not None:
        return _INDEX

    index: dict[str, list[tuple[str, str]]] = {}
    if not CACHE.exists():
        _INDEX = index
        return index

    try:
        with io.open(CACHE, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        _INDEX = index
        return index

    for ats, slugs in (data.get("slugs") or {}).items():
        for slug in slugs:
            if ats == workday.NAME:
                # Upstream packs Workday as tenant|instance|site; this codebase
                # uses tenant:instance:site, and the tenant is what a company
                # name would ever match against.
                parts = str(slug).split("|")
                if len(parts) != 3:
                    continue
                key = _normalise(parts[0])
                value = (ats, ":".join(parts))
            else:
                key = _normalise(slug)
                value = (ats, str(slug))
            if not key:
                continue
            index.setdefault(key, []).append(value)

    _INDEX = index
    return index


def available() -> bool:
    return bool(_load())


def size() -> int:
    return sum(len(v) for v in _load().values())


def lookup(company: str, limit: int = 6) -> list[tuple[str, str]]:
    """Candidate (ats, slug) pairs for a company name, best first.

    Exact normalised match first, then a small number of prefix matches so
    "Guidewire Software" can still find the board slug "guidewire". Prefix
    matching is deliberately conservative -- a 3-character stem would match
    hundreds of unrelated boards and cost more probes than guessing.
    """
    index = _load()
    if not index:
        return []

    key = _normalise(company)
    if not key:
        return []

    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for pair in index.get(key, []):
        if pair not in seen:
            seen.add(pair)
            out.append(pair)

    # Prefix matching runs in ONE direction only: the board slug may be a
    # shortened form of the company name ("Guidewire Software" -> guidewire),
    # never an extension of it.
    #
    # Allowing the other direction produced a real false positive: "Qualys"
    # matched the slug "qualysoft", a different company entirely, and the
    # verifier's six-character fallback waved it through -- 80 of somebody
    # else's postings would have been ingested as Qualys. A wrong board is far
    # worse than no board, because nothing downstream would catch it.
    if len(key) >= 6:
        for candidate in sorted(index, key=len, reverse=True):
            if len(out) >= limit:
                break
            if candidate == key or len(candidate) < 6:
                continue
            # A slug that merely pluralises or lightly suffixes the name is
            # still the same company -- Zipline's board is "ziplines". Two
            # characters is the ceiling: "qualys" -> "qualysoft" is four, and
            # that is a different company.
            extends_slightly = (
                candidate.startswith(key) and len(candidate) - len(key) <= 2
            )
            if key.startswith(candidate) or extends_slightly:
                for pair in index[candidate]:
                    if pair not in seen:
                        seen.add(pair)
                        out.append(pair)

    return out[:limit]
