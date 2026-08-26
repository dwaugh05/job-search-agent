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
import time
from dataclasses import dataclass, field

from . import config, prefilter, queue, resolve, store
from .comp import parse_salary
from .fingerprint import clone_key, normalize_company, normalize_title
from .fingerprint import fingerprint as compute_fingerprint
from .models import STATE_PREFILTERED, STATE_REJECTED_PREFILTER, Posting
from .normalize import clean, parse_location, parse_work_model
from .sources.registry import _client, check_url_live, down_hosts, fetch_many

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
    # Must exist before the `if`: it is read unconditionally below, and
    # use_boards is False for every targeted scan and for `scan --no-boards`.
    # Without this, both raise NameError before fetching anything.
    board_postings: list[Posting] = []
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
    # Reseller boards list one role once per country, identical but for the
    # country name. Those are one job, and Claude was paying to read each copy:
    # in run 14, 42 of 140 queue slots went to duplicates. Collapsed AFTER the
    # gates on purpose -- geography runs first, so the US copy is the survivor
    # and the Dubai copy is the one dropped, never the other way round.
    clone_seen: dict[str, int] = {}
    clones_dropped = 0
    # Roles already shown whose stored copy was read off a board. A company over
    # the resolve cap gets its posting read from LinkedIn this run and swept from
    # its own ATS the next; the two bodies hash apart, so the fingerprint check
    # above would let the same job through a second time.
    shown_board_roles = store.suppressed_board_roles(conn)
    reshown = 0
    for posting in postings:
        posting_id, is_new = store.upsert_posting(conn, posting, run_id)
        fp = compute_fingerprint(posting.company, posting.title, posting.description)
        key = clone_key(posting.company, posting.title, posting.description)
        if fp in scored and fp not in suppressed:
            already_scored += 1
            # Claim the clone slot on the way past. A posting already scored in
            # an earlier run still represents its whole clone family, and if it
            # does not register here then next run the second copy finds an empty
            # slot and gets queued -- turning "42 duplicates dropped once" into
            # one duplicate leaking every run until the family is exhausted.
            clone_seen.setdefault(key, posting_id)
            continue

        role = (normalize_company(posting.company), normalize_title(posting.title))
        if role in shown_board_roles and fp not in scored:
            row = store.get_posting(conn, posting_id)
            if row and row["state"] in ("new", STATE_PREFILTERED,
                                        STATE_REJECTED_PREFILTER):
                store.set_state(
                    conn, posting_id, STATE_REJECTED_PREFILTER,
                    "already presented from a job board; this is the employer's "
                    "own copy of the same role",
                )
            reshown += 1
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
            twin = clone_seen.get(key)
            if twin is not None:
                row = store.get_posting(conn, posting_id)
                if row and row["state"] in ("new", STATE_PREFILTERED,
                                            STATE_REJECTED_PREFILTER):
                    store.set_state(
                        conn, posting_id, STATE_REJECTED_PREFILTER,
                        "same role already queued this run from the same board "
                        "(reposted per country, identical text)",
                    )
                clones_dropped += 1
                continue
            clone_seen[key] = posting_id
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
        "already_shown_via_board": reshown,
        "duplicate_reposts_collapsed": clones_dropped,
        "failed_liveness": dead,
        "queued_for_evaluation": len(survivors),
    }
    # A host abandoned mid-run used to be indistinguishable from an employer
    # with nothing open -- both printed "feed returned nothing". If a whole ATS
    # provider dropped out, the run is not the clean sweep it looks like.
    down = down_hosts()
    if down:
        notes.append(
            "WARNING: gave up on " + ", ".join(sorted(down))
            + " after repeated timeouts - every company on "
            + ("that host" if len(down) == 1 else "those hosts")
            + " was skipped this run, not found empty"
        )
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
    # "solutions?" -- ServiceNow titles theirs "Solution Architect - AI & Data",
    # singular, and the plural-only pattern missed a 4.07.
    r"ai solutions|solutions? architect|solutions? engineer|applied ai|"
    # Added 2026-08-25. This screen was measured against every posting the system
    # has ever scored 3.9 or better: 18 of 48 failed it, including the highest
    # score on record (ButterflyMX, "Director, AI Strategy & Transformation",
    # 4.86). All 18 reached scoring only because their employer was already in
    # sources.yml -- the same role at an unknown company was invisible, which is
    # the exact gap boards.py exists to close. The terms below are taken from
    # those 18 titles, not invented.
    r"ai strateg|ai adoption|agentic|ai automation|ai capabilit|ai foundation|"
    r"ai architect|ai business|ai innovation|ai productivity|ai transform|"
    r"martech|marketing technology|revops|revenue operations|"
    r"answer engine|aeo\b|field marketing|product marketing|performance marketing|"
    r"digital marketing|program manager, go.to.market|go.to.market)",
    re.IGNORECASE,
)


# Built In has no bot protection at all, which makes it the easiest source here
# to get blocked from by being greedy. These throttle the job-page reads that the
# widened URL list generates -- see the loop in discover_via_boards. Sized from a
# live measurement on 2026-08-25: eight URLs at two pages each returned 372 leads
# of which 174 were on-archetype, so a cap under ~250 would routinely discard the
# very roles the widening was for.
BUILTIN_DETAIL_CAP = int(
    (config.profile().get("politeness") or {}).get("builtin_detail_cap", 250)
)
BUILTIN_DETAIL_DELAY = 0.4

# How many postings one scan may read directly off a board page. Each costs one
# request plus POLITE_DELAY, and they go to linkedin.com -- the one host whose
# goodwill this whole channel depends on. 200 is roughly six minutes.
BOARD_READ_CAP = int(
    (config.profile().get("politeness") or {}).get("board_read_cap", 200)
)

# When the cap does bite, it must drop the weakest leads, not whichever ones
# happen to be last in the URL list. Without this the keyword sweeps lose every
# time, because boards.discover() appends them after the category pages -- and
# the keyword sweeps are the half that reach outside Built In's category tree.
_HIGH_SIGNAL_TITLE = re.compile(
    r"(ai enablement|enablement.*ai|marketing ai|ai marketing|ai gtm|"
    r"marketing engineer|gtm engineer|marketing technolog|ai transformation|"
    r"ai adoption|ai solutions|ai operations|ai program)",
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
        #
        # Widening Built In from two URLs to eight on 2026-08-25 took this loop
        # from ~25 fetches to ~174, back to back with no gap. Built In has no bot
        # protection, which is exactly why it must not be leaned on -- a block
        # would outlast the run that caused it. So: a small delay, plus a cap and
        # a priority order, in the spirit of the SmartRecruiters and Workday
        # detail caps in registry.py.
        wanted = [
            lead for lead in leads
            if lead.board == builtin.NAME and not lead.company
            and _LEAD_WORTH_RESOLVING.search(_lead_haystack(lead))
        ]
        # Stable sort: high-signal titles first, everything else in discovery
        # order behind them.
        wanted.sort(key=lambda l: 0 if _HIGH_SIGNAL_TITLE.search(l.title or "") else 1)
        if len(wanted) > BUILTIN_DETAIL_CAP:
            notes.append(
                f"builtin: {len(wanted)} on-archetype leads, fetching the first "
                f"{BUILTIN_DETAIL_CAP} in detail ({len(wanted) - BUILTIN_DETAIL_CAP} "
                "over the cap, not read this run)"
            )
            wanted = wanted[:BUILTIN_DETAIL_CAP]
        for lead in wanted:
            posting = builtin.posting_from_lead(client, lead)
            if posting:
                lead.company = posting.company
                prebuilt[lead.url] = posting
            time.sleep(BUILTIN_DETAIL_DELAY)

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

    # Which companies get this run's expensive ATS resolution.
    #
    # Two things used to go wrong here. The order was whatever order the boards
    # happened to return, and boards.discover() appends LinkedIn first, then
    # Built In, then Hacker News -- so on a big run LinkedIn could spend the
    # entire budget before the other two channels were reached at all. And
    # anything past the cap was dropped outright: not resolved, not read, not
    # remembered, while the log said "they will be picked up next run", which
    # was not true of anything.
    #
    # So: drain the persisted backlog first, then this run's leads with the
    # strongest titles, then the rest -- and whatever is left over is written to
    # the backlog AND still read from the board's own page below, which costs
    # one or two requests against the ~45 a full resolution costs.
    carried = store.take_resolve_backlog(conn, resolve_cap)
    # Compared on the normalized key, not the raw string: the backlog may have
    # stored "Databricks Inc." while this run's board lead says "databricks",
    # and treating those as two companies is what the normalized key exists to
    # prevent.
    carried_set = {store.backlog_key(c) for c in carried}
    # Companies we have already failed to resolve BACKLOG_MAX_ATTEMPTS times.
    # take_resolve_backlog will not hand these back, but they keep turning up in
    # board results, and without this they would be re-probed at ~45 requests
    # every single run forever while stealing slots from companies that would
    # actually resolve. Their postings are still read from the board below --
    # giving up on finding the ATS is not giving up on the job.
    exhausted = {store.backlog_key(c) for c in store.resolve_backlog_exhausted(conn)}
    fresh = [
        c for c in by_company
        if store.backlog_key(c) not in carried_set
        and store.backlog_key(c) not in exhausted
    ]
    fresh.sort(
        key=lambda c: 0 if _HIGH_SIGNAL_TITLE.search(
            getattr(by_company[c], "title", "") or "") else 1
    )
    # Backlogged companies are retried whether or not they turned up on a board
    # again this run. That is the point of the queue: resolving one adds it to
    # sources.yml with watch=true, so every future scan reads its own feed and
    # it stops depending on a search happening to surface it.
    ordered = carried + fresh
    if carried:
        notes.append(
            f"boards: {len(carried)} employer(s) carried over from the resolve "
            f"backlog go first this run"
        )

    new_targets: list[tuple[str, str, str]] = []
    unresolved: list[object] = []
    resolved_keys: list[str] = []
    failed: list[str] = []
    attempted = 0
    for company in ordered[:resolve_cap]:
        attempted += 1
        # deep=False: skip the headless-browser render during bulk resolution.
        # It is the slowest part of a FAILED lookup and this loop can run sixty
        # times in one scan. A single `resolve-company` at the CLI still tries
        # everything.
        res = resolve.resolve(company, deep=False)
        if res.ok and res.ats and res.slug:
            resolve.save_resolution(res, watch=True)
            new_targets.append((res.ats, res.slug, res.company))
            resolved_keys.append(company)
        else:
            # A backlog company that did not reappear on a board this run has no
            # lead to read, so there is nothing to queue -- it just stays in the
            # backlog with one more attempt against it.
            if company in by_company:
                unresolved.append(by_company[company])
            failed.append(company)

    # Over the cap: remember them for next run, and still read their postings
    # from the board this run so a real match is not lost to a budget ceiling.
    deferred = ordered[resolve_cap:]
    if deferred:
        store.queue_resolve_backlog(conn, deferred)
        unresolved.extend(
            by_company[company] for company in deferred if company in by_company
        )

    # Employers we have stopped trying to resolve still have live postings on
    # the board. Read those the same way -- the alternative is that giving up on
    # finding a company's ATS quietly means never seeing its jobs again.
    unresolved.extend(
        lead for company, lead in by_company.items()
        if store.backlog_key(company) in exhausted
    )

    # Only companies we actually resolved leave the backlog -- they live in
    # sources.yml from here on. A carried company that ran out of budget again
    # this run must stay queued, which is exactly the bug this table exists to
    # fix, so clearing on `carried` rather than on success would reintroduce it.
    store.clear_resolve_backlog(conn, resolved_keys)
    store.bump_resolve_attempts(conn, failed)

    # Companies this system has given up finding a board for. They are still
    # real employers with real postings -- worth saying out loud, because
    # `cli.py resolve-company "<name>"` tries far harder than a bulk run can.
    stuck = store.resolve_backlog_exhausted(conn)
    if stuck:
        notes.append(
            f"boards: {len(stuck)} employer(s) have failed resolution "
            f"{store.BACKLOG_MAX_ATTEMPTS} times and are no longer retried "
            f"automatically: {', '.join(stuck[:8])}"
            + (f" and {len(stuck) - 8} more" if len(stuck) > 8 else "")
            + ". Run `python cli.py resolve-company \"<name>\"` to try one by hand."
        )

    notes.append(
        f"boards: resolved {len(new_targets)}/{attempted} new employers to a live "
        f"ATS and added them to the sweep"
        + (f"; {len(deferred)} over the per-run cap were saved to the resolve "
           f"backlog (now {store.resolve_backlog_size(conn)} deep) and are still "
           "read from the board below" if deferred else "")
    )

    # Companies with no reachable ATS used to be dropped here, silently. That is
    # the crack Doran identified: "a job that is a good potential gets lost in
    # the cracks." Read those postings from the board's own live page instead --
    # still fetched at scan time, never from a snapshot, so the no-cached-search
    # rule holds. The employer feed is always preferred when one exists.
    #
    # This list used to hold only failed resolutions -- a handful. It now also
    # carries every over-cap and every given-up-on employer, so it is the longest
    # unbroken run of board requests in the scan and needs the same cap every
    # other source has. Strongest titles first, so if the cap bites it drops the
    # weakest leads rather than whichever came back last.
    unresolved.sort(
        key=lambda l: 0 if _HIGH_SIGNAL_TITLE.search(
            getattr(l, "title", "") or "") else 1
    )
    if len(unresolved) > BOARD_READ_CAP:
        notes.append(
            f"boards: {len(unresolved)} postings to read from board pages, "
            f"reading the {BOARD_READ_CAP} strongest "
            f"({len(unresolved) - BOARD_READ_CAP} not read this run)"
        )
        unresolved = unresolved[:BOARD_READ_CAP]
    orphans = _postings_from_leads(unresolved, notes, prebuilt)
    return new_targets, len(leads), orphans


def _postings_from_leads(leads: list, notes: list[str],
                         prebuilt: dict[str, Posting] | None = None) -> list[Posting]:
    """Build Postings from board leads whose employer has no reachable ATS."""
    from .sources import boards

    prebuilt = prebuilt or {}
    out: list[Posting] = []
    thin = 0
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
            salary_raw = ""
            if not description:
                # One request for body and salary together. This loop now also
                # carries every company that ran out of resolve budget, so it is
                # the longest run of back-to-back LinkedIn requests in the whole
                # scan -- it has to be paced, and it must not fetch the same page
                # twice.
                description, salary_raw = boards.fetch_lead_page(client, lead)
                time.sleep(boards.POLITE_DELAY)
            if not description or len(description) < 200:
                # No usable body means nothing to score against. Better to drop
                # it than to queue a posting the rubric cannot read.
                thin += 1
                continue
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
        f"their employer has no reachable ATS or was over the resolve cap "
        f"({len(leads)} attempted)"
        # A body too short to score is usually LinkedIn throttling us, not a
        # genuinely empty posting -- it answers 200 with an empty page rather
        # than 429. Silently dropping those made a throttled run look like a
        # quiet one, so the count is stated.
        + (f"; {thin} dropped with no readable body, which usually means the "
           "board was rate-limiting this run" if thin else "")
    )
    return out
