"""The one pipeline.

Broad scans and targeted company scans differ ONLY in how `assemble_targets`
builds the candidate list. Everything after that -- upsert, fingerprint,
prefilter, liveness, queue -- runs through `run_discovery` for both. If the two
modes could ever score the same posting differently, the pipeline has forked and
that is a bug (see CLAUDE.md).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from . import config, prefilter, queue, resolve, store
from .fingerprint import fingerprint as compute_fingerprint
from .models import STATE_PREFILTERED, STATE_REJECTED_PREFILTER
from .sources.registry import _client, check_url_live, fetch_many

MODE_BROAD = "broad"
MODE_TARGETED = "targeted"


@dataclass
class DiscoveryResult:
    run_id: int
    mode: str
    funnel: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    survivors: list[sqlite3.Row] = field(default_factory=list)
    queue_path: str | None = None


def watch_targets() -> list[tuple[str, str, str]]:
    """Every resolved, live, watched company from sources.yml."""
    data = config.sources()
    targets = []
    for entry in data.get("companies", []) or []:
        if not entry.get("watch", False):
            continue
        if entry.get("status") != "live":
            continue
        if entry.get("ats") and entry.get("slug"):
            targets.append((entry["ats"], entry["slug"], entry["name"]))
    return targets


def targeted_targets(
    companies: list[str], *, watch: bool = False, notes: list[str] | None = None
) -> list[tuple[str, str, str]]:
    """Resolve names Doran typed into live ATS boards, caching each result."""
    targets = []
    for name in companies:
        res = resolve.resolve(name)
        if res.ok and res.ats and res.slug:
            resolve.save_resolution(res, watch=watch or None)
            targets.append((res.ats, res.slug, res.company))
            if notes is not None:
                detail = res.note or f"{res.ats}/{res.slug}"
                notes.append(f"{name} -> {res.ats}/{res.slug} ({detail})")
        elif notes is not None:
            notes.append(f"{name} -> UNRESOLVED. {res.note}")
    return targets


def run_discovery(
    conn: sqlite3.Connection,
    *,
    mode: str,
    targets: list[tuple[str, str, str]],
    enforce_freshness: bool,
    freshness_days: int | None = None,
    check_liveness: bool = True,
    notes: list[str] | None = None,
    use_boards: bool = False,
) -> DiscoveryResult:
    notes = notes if notes is not None else []
    params = {
        "companies": [t[2] for t in targets],
        "enforce_freshness": enforce_freshness,
        "freshness_days": freshness_days,
    }
    run_id = store.start_run(conn, mode, params)

    # Role-first board discovery runs BEFORE the sweep so anything it finds is
    # swept from the employer's own feed in this same run -- one scan, one
    # output. Broad mode only; a targeted scan is explicitly company-scoped.
    board_added = 0
    if use_boards:
        window = freshness_days if freshness_days is not None else (
            config.profile().get("hard_gates", {}).get("freshness_days", 30))
        new_targets, _leads = discover_via_boards(
            conn, run_id, days=window, notes=notes)
        known_slugs = {(a, s) for a, s, _ in targets}
        for target in new_targets:
            if (target[0], target[1]) not in known_slugs:
                targets.append(target)
                board_added += 1

    postings, per_company = fetch_many(targets, on_note=notes.append)
    raw_count = len(postings)

    rubric_version = str(config.scoring().get("version", 1))
    # Skip anything Doran has already seen, and anything already scored under the
    # current rubric -- re-scoring a known 3.6 to 3.6 again is pure waste.
    suppressed = store.suppressed_fingerprints(conn)
    scored = store.already_evaluated(conn, rubric_version)
    skip = suppressed | scored

    survivor_ids: list[int] = []
    rejected = 0
    already_scored = 0
    for posting in postings:
        posting_id, is_new = store.upsert_posting(conn, posting, run_id)
        fp = compute_fingerprint(posting.company, posting.title, posting.description)
        if fp in scored and fp not in suppressed:
            already_scored += 1
            continue
        result = prefilter.evaluate(
            posting,
            suppressed=skip,
            posting_fingerprint=fp,
            enforce_freshness=enforce_freshness,
            freshness_days=freshness_days,
            first_sighting=is_new,
        )
        if result.passed:
            store.set_state(conn, posting_id, STATE_PREFILTERED,
                            f"ai {result.relevance:.0f} / growth {result.growth_relevance:.0f}")
            # Record which list(s) this is a candidate for so the report can
            # route it without re-running the vocabularies.
            conn.execute(
                "UPDATE postings SET tracks = ?, audience = ?, "
                "ai_fluency_requested = ? WHERE id = ?",
                (",".join(result.tracks), result.audience,
                 int(result.ai_fluency_requested), posting_id),
            )
            survivor_ids.append(posting_id)
        else:
            # Don't clobber a state Doran already moved past.
            row = store.get_posting(conn, posting_id)
            if row and row["state"] in ("new", STATE_PREFILTERED, STATE_REJECTED_PREFILTER):
                store.set_state(conn, posting_id, STATE_REJECTED_PREFILTER, result.reason)
            rejected += 1

    # Liveness: hitting the live feed already proves the posting exists, but a
    # stale feed can still advertise a closed role, so confirm the apply URL
    # resolves. Read-only -- we never touch the application form itself.
    dead = 0
    if check_liveness and survivor_ids:
        with _client() as client:
            for posting_id in list(survivor_ids):
                row = store.get_posting(conn, posting_id)
                if not row:
                    continue
                url = row["apply_url"] or row["url"]
                alive = check_url_live(url, client)
                store.mark_live_checked(conn, posting_id, alive)
                if not alive:
                    survivor_ids.remove(posting_id)
                    store.set_state(conn, posting_id, STATE_REJECTED_PREFILTER,
                                    "apply URL is dead or closed")
                    dead += 1

    survivors = [
        row for row in (store.get_posting(conn, pid) for pid in survivor_ids) if row
    ]
    survivors.sort(key=lambda r: r["company"])

    funnel = {
        "companies_swept": len(targets),
        "companies_added_by_boards": board_added,
        "raw_postings": raw_count,
        "already_scored_skipped": already_scored,
        "rejected_by_prefilter": rejected,
        "failed_liveness": dead,
        "queued_for_evaluation": len(survivors),
    }
    store.finish_run(
        conn, run_id,
        raw_count=raw_count,
        prefilter_pass=len(survivors),
    )

    result = DiscoveryResult(
        run_id=run_id, mode=mode, funnel=funnel, notes=notes,
        companies=[t[2] for t in targets], survivors=survivors,
    )
    if survivors:
        result.queue_path = str(queue.render(conn, survivors, run_id, mode))

    empty = [name for name, count in per_company.items() if count == 0]
    if empty:
        notes.append(
            f"{len(empty)} company feed(s) returned nothing: {', '.join(sorted(empty)[:8])}"
            + (" ..." if len(empty) > 8 else "")
        )
    return result


# --------------------------------------------------------- board discovery
#
# Company-first sweeping makes sources.yml a hard ceiling: an employer nobody
# added is invisible. This channel searches boards ROLE-first, then resolves
# each unknown employer to its real ATS and adds it to the sweep permanently.

BOARD_RESOLVE_CAP = 30

# Cheap title screen applied BEFORE any resolution work. Resolving a company
# costs dozens of HTTP probes, so we only spend that on leads whose title
# already looks like one of Doran's archetypes.
_LEAD_WORTH_RESOLVING = re.compile(
    r"(ai enablement|enablement|marketing ai|ai marketing|marketing engineer|"
    r"gtm engineer|marketing technolog|ai transformation|growth marketing|"
    r"demand gen|conversion|web growth|website growth|marketing operations|"
    r"ai operations|ai program)",
    re.IGNORECASE,
)


def discover_via_boards(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    days: int,
    notes: list[str],
    resolve_cap: int = BOARD_RESOLVE_CAP,
) -> tuple[list[tuple[str, str, str]], int]:
    """Search boards for the archetype and expand the source map.

    Returns (new_targets, leads_seen). `new_targets` are companies resolved to a
    live ATS this run -- their postings are then fetched from the employer feed,
    which keeps the ATS as the source of truth per CLAUDE.md.
    """
    from .sources import boards

    known = {
        (entry.get("name") or "").strip().lower()
        for entry in (config.sources().get("companies") or [])
    }

    with _client() as client:
        leads = boards.discover(client, days=days, on_note=notes.append)

    relevant = [
        lead for lead in leads
        if _LEAD_WORTH_RESOLVING.search(lead.title)
        and lead.company.strip().lower() not in known
    ]
    notes.append(
        f"boards: {len(leads)} leads, {len(relevant)} from unknown companies "
        f"with an on-archetype title"
    )

    # De-duplicate by company -- one resolution serves every lead from it.
    by_company: dict[str, object] = {}
    for lead in relevant:
        by_company.setdefault(lead.company.strip(), lead)

    new_targets: list[tuple[str, str, str]] = []
    attempted = 0
    for company in list(by_company)[:resolve_cap]:
        attempted += 1
        res = resolve.resolve(company)
        if res.ok and res.ats and res.slug:
            resolve.save_resolution(res, watch=True)
            new_targets.append((res.ats, res.slug, res.company))

    skipped = max(0, len(by_company) - resolve_cap)
    notes.append(
        f"boards: resolved {len(new_targets)}/{attempted} new employers to a live "
        f"ATS and added them to the sweep"
        + (f"; {skipped} over the per-run cap, they will be picked up next run"
           if skipped else "")
    )
    return new_targets, len(leads)
