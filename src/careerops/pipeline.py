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
from .comp import parse_salary
from .fingerprint import fingerprint as compute_fingerprint
from .models import STATE_PREFILTERED, STATE_REJECTED_PREFILTER, Posting
from .normalize import clean, parse_location, parse_work_model
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
        new_targets, _leads, board_postings = discover_via_boards(
            conn, run_id, days=window, notes=notes)
        known_slugs = {(a, s) for a, s, _ in targets}
        for target in new_targets:
            if (target[0], target[1]) not in known_slugs:
                targets.append(target)
                board_added += 1

    postings, per_company = fetch_many(targets, on_note=notes.append)
    # Board-sourced postings join the same pipeline as ATS ones: identical
    # prefilter gates, identical fingerprinting, identical scoring. The only
    # difference is where the body came from.
    if board_postings:
        swept = {(p.company.strip().lower(), p.title.strip().lower())
                 for p in postings}
        postings.extend(
            p for p in board_postings
            if (p.company.strip().lower(), p.title.strip().lower()) not in swept
        )
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
            # Our own first sighting, which no feed can rewrite by reposting.
            first_seen=None if is_new else store.first_seen_of(conn, posting_id),
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

# Tunable from config/profile.yml -> politeness.board_resolve_cap. Each unknown
# employer costs up to ~45 probe requests to resolve, and once added it is swept
# on every future run, so this caps permanent queue growth as much as traffic.
BOARD_RESOLVE_CAP = int(
    (config.profile().get("politeness") or {}).get("board_resolve_cap", 60)
)

# Cheap title screen applied BEFORE any resolution work. Resolving a company
# costs dozens of HTTP probes, so we only spend that on leads whose title
# already looks like one of Doran's archetypes.
_LEAD_WORTH_RESOLVING = re.compile(
    r"(ai enablement|enablement|marketing ai|ai marketing|marketing engineer|"
    r"gtm engineer|marketing technolog|ai transformation|growth marketing|"
    r"demand gen|conversion|web growth|website growth|marketing operations|"
    r"ai operations|ai program|"
    # Added 2026-08-14 alongside the new board queries. Without these terms the
    # new "AI solutions" searches would return leads that this screen then threw
    # away before resolution -- the keyword change alone would have done nothing.
    r"ai solutions|solutions architect|solutions engineer|applied ai)",
    re.IGNORECASE,
)


def _lead_haystack(lead) -> str:
    """What the archetype screen reads.

    Most boards give a clean title. Hacker News hiring posts are prose with no
    title field at all -- the role is buried in a pipe-delimited header whose
    order varies by poster -- so the body has to be screened too or every HN lead
    is discarded before it is ever looked at.
    """
    return f"{getattr(lead, 'title', '')} {getattr(lead, 'text', '')}"


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

    from .sources import builtin

    prebuilt: dict[str, Posting] = {}
    with _client() as client:
        leads = boards.discover(client, days=days, on_note=notes.append)

        # Built In listing pages give a title and URL but not the employer -- the
        # company only appears in the JobPosting on the job page itself. Screen on
        # title FIRST (free), then fetch only the survivors, so an on-archetype
        # title costs one request and everything else costs nothing.
        for lead in leads:
            if lead.board != builtin.NAME or lead.company:
                continue
            if not _LEAD_WORTH_RESOLVING.search(_lead_haystack(lead)):
                continue
            posting = builtin.posting_from_lead(client, lead)
            if posting:
                lead.company = posting.company
                prebuilt[lead.url] = posting

    relevant = [
        lead for lead in leads
        if _LEAD_WORTH_RESOLVING.search(_lead_haystack(lead))
        and lead.company.strip()
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
    unresolved: list[object] = []
    attempted = 0
    for company in list(by_company)[:resolve_cap]:
        attempted += 1
        # deep=False: skip the headless-browser render during bulk resolution.
        # It is the slowest part of a FAILED lookup and this loop can run sixty
        # times in one scan. A single `resolve-company` at the CLI still tries
        # everything.
        res = resolve.resolve(company, deep=False)
        if res.ok and res.ats and res.slug:
            resolve.save_resolution(res, watch=True)
            new_targets.append((res.ats, res.slug, res.company))
        else:
            unresolved.append(by_company[company])

    skipped = max(0, len(by_company) - resolve_cap)
    notes.append(
        f"boards: resolved {len(new_targets)}/{attempted} new employers to a live "
        f"ATS and added them to the sweep"
        + (f"; {skipped} over the per-run cap, they will be picked up next run"
           if skipped else "")
    )

    # Companies with no reachable ATS used to be dropped here, silently. That is
    # the crack Doran identified: "a job that is a good potential gets lost in
    # the cracks." Read those postings from the board's own live page instead --
    # still fetched at scan time, never from a snapshot, so the no-cached-search
    # rule holds. The employer feed is always preferred when one exists.
    orphans = _postings_from_leads(unresolved, notes, prebuilt)
    return new_targets, len(leads), orphans


def _postings_from_leads(leads: list, notes: list[str],
                         prebuilt: dict[str, Posting] | None = None) -> list[Posting]:
    """Build Postings from board leads whose employer has no reachable ATS."""
    from .sources import boards

    prebuilt = prebuilt or {}
    out: list[Posting] = []
    if not leads:
        return out

    with _client() as client:
        for lead in leads:
            # Built In postings were already parsed in full while discovering the
            # employer name, so there is nothing left to fetch.
            ready = prebuilt.get(lead.url)
            if ready is not None:
                out.append(ready)
                continue
            # Hacker News posts ARE the description -- there is no separate page
            # to fetch, so use the body already carried on the lead.
            description = (getattr(lead, "text", "") or "").strip()
            if not description:
                description = boards.fetch_lead_description(client, lead)
            if not description or len(description) < 200:
                # No usable body means nothing to score against. Better to drop
                # it than to queue a posting the rubric cannot read.
                continue
            salary_raw = boards.salary_from_card(client, lead)
            smin, smax = parse_salary(salary_raw) if salary_raw else (None, None)
            city, region, country = parse_location(lead.location)
            out.append(Posting(
                source_id=f"{lead.board}:{lead.job_id or lead.url}",
                company=clean(lead.company),
                title=clean(lead.title),
                url=lead.url,
                apply_url=lead.url,
                ats=lead.board,
                source_slug=lead.board,
                location_raw=lead.location or "",
                city=city,
                region=region,
                country=country,
                workplace_type=parse_work_model(None, None, lead.location, description),
                published_at=lead.posted_at,
                # The board states a date on the card, but it is a relative
                # "2 weeks ago" rendered to a date, so it is weaker than an ATS
                # timestamp. Block G surfaces low confidence to Doran.
                date_confidence="low" if lead.posted_at else "none",
                description=description,
                salary_raw=salary_raw or None,
                salary_min=smin,
                salary_max=smax,
            ))

    notes.append(
        f"boards: {len(out)} posting(s) read from the board's live page because "
        f"their employer has no reachable ATS ({len(leads)} attempted)"
    )
    return out
