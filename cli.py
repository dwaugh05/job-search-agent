#!/usr/bin/env python
"""careerops CLI - the deterministic half of the job search agent.

Discovery and evaluation only. There is deliberately no `apply` command and
there never will be (see CLAUDE.md).
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from careerops import applications, config, pipeline, report, resolve, store  # noqa: E402
from careerops import prefilter as prefilter_mod  # noqa: E402
from careerops.models import VERDICTS  # noqa: E402
from careerops.sources.registry import _client, probe  # noqa: E402


def _threshold() -> float:
    return float(config.profile().get("review", {}).get("min_score_to_present", 4.0))


def _is_connection(row) -> bool:
    """True if this posting is from a company where Doran knows someone.

    Matched on the resolved ATS board first and the normalized company name
    second, because neither alone is reliable -- a company can be listed before
    it has been resolved, and ATS company names drift from the common name.
    """
    if row is None:
        return False
    names, boards = config.connection_lookup()
    ats = str(row["ats"] or "").lower()
    slug = str(row["source_slug"] or "").lower()
    if ats and slug and (ats, slug) in boards:
        return True
    return config.normalize_company(row["company"]) in names


def _print_funnel(result: pipeline.DiscoveryResult) -> None:
    print(f"\nRun {result.run_id} ({result.mode})")
    for stage, count in result.funnel.items():
        print(f"  {stage:26} {count}")
    for note in result.notes:
        print(f"  note: {note}")
    if result.queue_path:
        print(f"\n  queue -> {result.queue_path}")
    else:
        print("\n  Nothing cleared the prefilter this run.")


# --------------------------------------------------------------------- commands


def cmd_init(args: argparse.Namespace) -> int:
    store.init_db()
    print(f"Database ready at {config.DB_PATH}")
    return 0


def cmd_verify_sources(args: argparse.Namespace) -> int:
    """Probe every configured slug; resolve any that are unknown; write back."""
    data = config.sources()
    entries = data.get("companies", []) or []
    live = dead = resolved = 0

    with _client() as client:
        for entry in entries:
            name = entry.get("name", "")
            if entry.get("ats") and entry.get("slug") and not args.force:
                ok, count = probe(entry["ats"], entry["slug"], client)
                entry["status"] = "live" if ok else "dead"
                if ok:
                    live += 1
                    print(f"  live  {name:32} {entry['ats']}/{entry['slug']}  ({count} jobs)")
                else:
                    dead += 1
                    print(f"  DEAD  {name:32} {entry['ats']}/{entry['slug']}")
                continue

            res = resolve.resolve(name, force=args.force)
            if res.ok:
                entry["ats"], entry["slug"], entry["status"] = res.ats, res.slug, "live"
                live += 1
                resolved += 1
                print(f"  live  {name:32} {res.ats}/{res.slug}  ({res.job_count} jobs)"
                      + (f"  [{res.note}]" if res.note else ""))
            else:
                entry["status"] = "dead"
                dead += 1
                print(f"  DEAD  {name:32} unresolved")

    config.save_sources(data)
    total = live + dead
    pct = (live / total * 100) if total else 0
    print(f"\n{live}/{total} live ({pct:.0f}%), {resolved} newly resolved. "
          f"sources.yml updated.")
    return 0 if pct >= 70 else 1


def cmd_resolve_company(args: argparse.Namespace) -> int:
    res = resolve.resolve(args.company, force=args.force)
    print(f"{res.company}: {res.status}")
    if res.ok:
        print(f"  ats  : {res.ats}")
        print(f"  slug : {res.slug}")
        print(f"  jobs : {res.job_count}")
        if res.note:
            print(f"  note : {res.note}")
        if len(res.all_hits) > 1:
            print("  other live boards: "
                  + ", ".join(f"{a}/{s} ({n})" for a, s, n in res.all_hits[1:]))
        if args.save:
            resolve.save_resolution(res, watch=args.watch)
            print("  cached into config/sources.yml")
        # A scan that gives up on a company tells Doran to run this command by
        # hand. Without clearing the row, it would keep telling him that after he
        # already did it -- a note that lies is worse than no note.
        store.init_db()
        with store.connect() as conn:
            store.clear_resolve_backlog(conn, [args.company, res.company])
    else:
        print(f"  {res.note}")
        print(f"  probes issued: {res.candidates_tried}")
    return 0 if res.ok else 1


def cmd_scan(args: argparse.Namespace) -> int:
    store.init_db()
    with store.connect() as conn:
        notes: list[str] = []
        if args.companies:
            names = [c.strip() for c in args.companies.split(",") if c.strip()]
            targets = pipeline.targeted_targets(names, watch=args.watch, notes=notes)
            mode = pipeline.MODE_TARGETED
            # Targeted mode looks at everything currently open by default: when
            # Doran names five companies he cares about, a 14-day filter would
            # usually return nothing. --fresh restores the window.
            enforce_freshness = args.fresh
        else:
            targets = pipeline.watch_targets()
            mode = pipeline.MODE_BROAD
            enforce_freshness = not args.all_open

        if not targets:
            print("No targets. Run `python cli.py verify-sources` first.")
            return 1

        # A connection company that never resolved has no board to sweep, so it
        # would silently never appear. Warn rather than resolve inline -- probing
        # mid-scan would slow every run for a one-off setup step.
        if mode == pipeline.MODE_BROAD:
            swept = {config.normalize_company(name) for _, _, name in targets}
            unswept = [
                entry.get("name")
                for entry in (config.connections().get("companies") or [])
                if config.normalize_company(entry.get("name")) not in swept
            ]
            if unswept:
                print("Not in this sweep (no live board yet): "
                      + ", ".join(str(n) for n in unswept))
                print("  These are companies you know someone at. "
                      "Run `python cli.py sync-connections` to add them.\n")

        result = pipeline.run_discovery(
            conn,
            mode=mode,
            targets=targets,
            enforce_freshness=enforce_freshness,
            freshness_days=args.days,
            check_liveness=not args.skip_liveness,
            notes=notes,
            # Board discovery is broad-scan only: a targeted scan is explicitly
            # scoped to the companies Doran named.
            use_boards=(mode == pipeline.MODE_BROAD and not args.no_boards),
        )
        _print_funnel(result)
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    from careerops import queue as queue_mod
    from careerops.models import STATE_PREFILTERED

    with store.connect() as conn:
        rows = store.postings_in_state(conn, STATE_PREFILTERED)
        if not rows:
            print("Nothing awaiting evaluation.")
            return 0
        run = store.latest_run(conn)
        run_id = args.run or (run["id"] if run else 0)
        path = queue_mod.render(conn, rows, run_id, "manual")
        print(f"{len(rows)} posting(s) queued -> {path}")
    return 0


def cmd_record_eval(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    # File-level track is now only a DEFAULT. Each evaluation may name its own,
    # because a queue mixes buckets and the rubric has to follow the posting:
    # a marketing-only role judged against scoring.yml cannot clear the bar,
    # since dimension 1 (weight 22) makes AI enablement the hard requirement.
    default_track = payload.get("track", args.track or config.TRACK_AI)

    @functools.lru_cache(maxsize=None)
    def _rubric_for(track: str):
        rubric = config.scoring(track)
        return (
            rubric,
            {str(d["id"]): float(d["weight"]) for d in rubric["dimensions"]},
            float(rubric.get("evidence", {}).get("cap_without_evidence", 3.0)),
        )
    connections_cfg = config.connections()
    conn_bump = float(connections_cfg.get("bump", 1.0))
    max_score = float(connections_cfg.get("max_score", 5.0))

    written = 0
    thin = 0
    with store.connect() as conn:
        for item in payload.get("evaluations", []):
            track = item.get("track") or default_track
            scoring, weights, cap = _rubric_for(track)
            raw_dims = item.get("dimension_scores") or {}
            # A dimension explicitly set to null is NOT scored -- its weight is
            # dropped from the denominator so it is genuinely neutral. This is
            # how an unpublished salary range is handled: Doran said it "shouldn't
            # make it rate lower", and any fixed placeholder score would be a
            # hidden penalty (or a hidden bonus).
            skipped = {str(k) for k, v in raw_dims.items() if v is None}
            dims = {str(k): float(v) for k, v in raw_dims.items() if v is not None}
            missing = set(weights) - set(dims) - skipped
            if missing:
                print(f"  posting {item.get('posting_id')}: missing dimensions "
                      f"{sorted(missing, key=int)} - skipped")
                continue
            if skipped:
                print(f"  posting {item.get('posting_id')}: dimension(s) "
                      f"{sorted(skipped, key=int)} not scored - weight redistributed")

            notes = item.get("block_notes") or {}
            # Evidence rule: a judgement dimension scored above the cap with no
            # quoted evidence gets capped. This is the main brake on score
            # inflation. Blocks D and E are exempt -- their inputs are parsed
            # structured fields, not prose, so there is nothing to quote.
            evidence_cfg = scoring.get("evidence", {})
            if evidence_cfg.get("required", True):
                gated = set(evidence_cfg.get("required_blocks") or ["A", "B", "C", "F"])
                for dim_id, score in list(dims.items()):
                    block = next(
                        (d["block"] for d in scoring["dimensions"]
                         if str(d["id"]) == dim_id), None
                    )
                    if block not in gated:
                        continue
                    evidence = str(notes.get(block, ""))
                    if score > cap and '"' not in evidence and "'" not in evidence:
                        dims[dim_id] = cap
                        print(f"  posting {item.get('posting_id')}: dimension {dim_id} "
                              f"capped at {cap} (no quoted evidence in block {block})")

            # The Director rule, enforced rather than remembered. A Director or
            # above scores full marks on seniority ONLY if the block B note
            # names one of the two disciplines Doran clears at that level: AI
            # enablement/transformation, or growth and web marketing. Written as
            # a rubric instruction twice and forgotten twice -- run 25 gave
            # Freshworks "Director, GTM Systems Architecture" a 5.0.
            posting_row = store.get_posting(conn, int(item["posting_id"]))
            title = (posting_row["title"] if posting_row else "") or ""
            seniority_limit = prefilter_mod.seniority_cap(
                title, str(notes.get("B", "")))
            if seniority_limit is not None and "3" in dims:
                if dims["3"] > seniority_limit:
                    dims["3"] = seniority_limit
                    print(f"  posting {item.get('posting_id')}: dimension 3 capped "
                          f"at {seniority_limit} - a senior title whose block B note "
                          "names no discipline Doran clears at that level")

            active = {k: w for k, w in weights.items() if k in dims}
            weighted = sum(dims[k] * active[k] for k in active) / sum(active.values())

            # Scope modifier: a non-marketing role still qualifies, it just
            # ranks slightly lower. Applied after averaging so the deduction is
            # explicit and auditable rather than smeared across dimensions.
            modifiers = dict(scoring.get("scope_modifiers", {}))
            modifiers.update(scoring.get("bonus_modifiers", {}) or {})
            scope = item.get("scope", "marketing_or_gtm")
            if scope not in modifiers:
                print(f"  posting {item.get('posting_id')}: unknown scope {scope!r} "
                      f"- treating as marketing_or_gtm (no adjustment)")
                scope = "marketing_or_gtm"
            adjustment = float(modifiers.get(scope, 0.0))
            bonus_key = item.get("bonus")
            if bonus_key:
                bonuses = scoring.get("bonus_modifiers", {}) or {}
                if bonus_key in bonuses:
                    adjustment += float(bonuses[bonus_key])
                else:
                    print(f"  posting {item.get('posting_id')}: unknown bonus "
                          f"{bonus_key!r} - ignored")
            if adjustment:
                weighted = max(1.0, weighted + adjustment)

            # Connection bump: a role at a company where Doran knows someone is
            # worth more of his time than the same role cold, because he can get
            # a referral instead of landing in the ATS pile. Kept OUT of
            # `adjustment` so the DB can still tell a scope deduction apart from
            # a relationship bonus, and hard-capped so it can never invent a
            # score above the top of the scale.
            # posting_row was already read above for the seniority cap.
            connection_bonus = conn_bump if _is_connection(posting_row) else 0.0
            weighted = min(max_score, weighted + connection_bonus)

            # The Fit Summary is what Doran reads INSTEAD of the posting, so a
            # thin one silently costs him the thing the report exists for.
            # Checked mechanically because the written house style drifted
            # anyway -- see report.fit_summary_issues.
            summary_problems = report.fit_summary_issues(item.get("fit_summary"))
            if summary_problems:
                thin += 1
                print(f"  posting {item.get('posting_id')}: FIT SUMMARY - "
                      + "; ".join(summary_problems))

            store.record_evaluation(
                conn,
                int(item["posting_id"]),
                run_id=payload.get("run_id"),
                rubric_version=str(payload.get("rubric_version", scoring.get("version"))),
                track=track,
                scope_modifier=adjustment,
                connection_bonus=connection_bonus,
                dimension_scores=dims,
                weighted_score=round(weighted, 3),
                block_g_verdict=item.get("block_g_verdict", "PASS"),
                block_g_flags=item.get("block_g_flags") or [],
                fit_summary=item.get("fit_summary", ""),
                block_notes=notes,
            )
            written += 1
            scope_note = f" scope={scope} {adjustment:+.2f}" if adjustment else ""
            conn_note = (f" connection {connection_bonus:+.2f}"
                         if connection_bonus else "")
            print(f"  posting {item['posting_id']}: {weighted:.2f}"
                  f"{scope_note}{conn_note} [G={item.get('block_g_verdict', 'PASS')}]")
    print(f"\nRecorded {written} evaluation(s).")
    if thin:
        print(f"WARNING: {thin} fit summary(ies) fall short of the house style. "
              "Doran reads these INSTEAD of the posting - see 'Writing the Fit "
              "Summary' in rubric/rubric-A-G.md and rewrite them before reporting.")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    with store.connect() as conn:
        review = config.profile().get("review", {})
        limit = int(review.get("max_results_per_report", 12))
        floor_gap = float(review.get("worth_knowing_gap", 0.30))
        cap = int(review.get("max_worth_knowing", 3))

        # THREE BUCKETS, THREE BARS. Doran, 2026-08-28: "there's the traditional
        # marketing role and then there's the AI role. And then there's a third
        # bucket of where they overlap. And so I want to know about all three of
        # these when you present the lists."
        #
        # No dedupe between the lists: bucket_of() returns exactly one bucket
        # per posting, so the three are disjoint by construction. The old
        # track-based routing needed a `shown` id filter because a both-tracks
        # posting appeared in each; an overlap posting now appears only under
        # overlap.
        sections: list[tuple[str, list, list]] = []
        for bucket in config.BUCKETS:
            bar = (args.threshold if args.threshold is not None
                   else config.bucket_threshold(bucket))
            rows = store.presentable(conn, bar, bucket=bucket)[:limit]
            # The near-miss floor is RELATIVE to this bucket's bar. A fixed 3.7
            # floor against the 3.75 overlap bar leaves a 0.05-wide band, which
            # would silently stop showing him near-misses in his best bucket.
            near_floor = max(0.0, bar - floor_gap)
            shown_ids = {r["id"] for r in rows}
            worth = [r for r in store.worth_knowing(
                conn, bar, near_floor, cap, bucket=bucket)
                if r["id"] not in shown_ids]
            sections.append((bucket, rows, worth))

        matches = [r for _b, rows, _w in sections for r in rows]

        near = []
        if args.companies:
            names = [c.strip() for c in args.companies.split(",") if c.strip()]
            seen_companies = {row["company"].lower() for row in matches}
            bar = args.threshold if args.threshold is not None else _threshold()
            near = [r for r in store.near_misses(conn, bar, names)
                    if r["company"].lower() not in seen_companies]

        # Built as one string, then printed AND archived, so the markdown file
        # is byte-for-byte what Doran saw rather than a second rendering of it.
        # Companies he already has an application in at, read once and passed to
        # every list so the note appears wherever the company does.
        prior = store.prior_applications(conn)
        parts: list[str] = []
        for bucket, rows, worth in sections:
            bar = (args.threshold if args.threshold is not None
                   else config.bucket_threshold(bucket))
            parts.append(report.render_bucket(bucket, bar, rows, prior))
            if worth:
                parts.append(report.render_worth_knowing(worth, bar))
            parts.append("\n")

        if near:
            parts.append(report.render_near_misses(near))

        presented = "\n".join(parts)
        print(presented)

        run = store.latest_run(conn)
        run_id = args.run or (run["id"] if run else 0)

        # A dry run must not leave an archive behind. data/reports/ is what Doran
        # re-reads weeks later, and a preview file is indistinguishable from a
        # real one once it is sitting in that folder -- it would look like he was
        # shown roles he never saw.
        if args.no_mark:
            print("\n[dry run: nothing marked as presented, no archive written]")
        else:
            stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
            archive = report.write_presented_report(presented, run_id=run_id, stamp=stamp)
            print(f"\n[saved verbatim: {archive}]")

        if matches or near:
            path = report.write_run_report(
                conn, run_id, matches, mode="report",
                funnel={"presented": len(matches), "near_misses": len(near)},
                near_miss_rows=near,
            )
            print(f"\n[detail: {path}]")

        # `matches` already spans all three buckets, which are disjoint, so there
        # is no second list to append. Before the buckets landed this read
        # `matches + backup`; `backup` no longer exists and the stale reference
        # raised NameError here AFTER the report had printed and archived, so a
        # run looked successful while marking nothing as presented.
        if matches and not args.no_mark:
            ids = [row["id"] for row in matches]
            store.mark_presented(conn, ids, run_id)
            print(f"[{len(ids)} posting(s) across both lists marked as presented - "
                  "they will never appear in a scan again]")
    return 0


def cmd_verdict(args: argparse.Namespace) -> int:
    if args.verdict not in VERDICTS:
        print(f"verdict must be one of: {', '.join(sorted(VERDICTS))}")
        return 1
    with store.connect() as conn:
        row = store.get_posting(conn, args.posting)
        if not row:
            print(f"No posting with id {args.posting}")
            return 1
        store.record_verdict(conn, args.posting, args.verdict, args.reason)
        print(f"{row['title']} @ {row['company']} -> {args.verdict}")
        if args.reason:
            print(f"  reason: {args.reason}")

        # Applying is the point of no return for the posting: companies take
        # them down, and our own copy is overwritten on the next scan. Snapshot
        # it now or lose it before the interview.
        if args.verdict == "applied":
            path = _archive_application(conn, row, applied_date=args.date,
                                        reason=args.reason)
            print(f"  archived: {path}")
            print(f"  index   : {applications.rebuild_index()}")
    return 0


def _archive_application(conn, row, *, applied_date: str | None = None,
                         reason: str | None = None):
    """Write one applied posting to the permanent archive."""
    latest = conn.execute(
        """SELECT weighted_score, fit_summary, connection_bonus FROM evaluations
           WHERE posting_id = ? ORDER BY id DESC LIMIT 1""",
        (row["id"],),
    ).fetchone()
    return applications.write_application(
        row,
        applied_date=applied_date or datetime.now().strftime("%Y-%m-%d"),
        reason=reason,
        score=latest["weighted_score"] if latest else None,
        connection_bonus=(latest["connection_bonus"] or 0.0) if latest else 0.0,
        fit_summary=latest["fit_summary"] if latest else None,
    )


def cmd_applied(args: argparse.Namespace) -> int:
    """List every role Doran applied to, with the path to its saved details."""
    with store.connect() as conn:
        rows = store.applied_postings(conn)
        if not rows:
            print("Nothing marked as applied yet.")
            return 0

        if args.backfill:
            written = 0
            for row in rows:
                applied_date = str(row["applied_at"] or "")[:10] or "unknown"
                path = _archive_application(conn, row, applied_date=applied_date,
                                            reason=row["reason"])
                sections = applications.extract_sections(row["description"])
                print(f"  {path.name}\n      captured via: {sections['via']}")
                written += 1
            print(f"\nArchived {written} application(s).")
            print(f"Index: {applications.rebuild_index()}")
            return 0

        print(f"{len(rows)} application(s), newest first:\n")
        for row in rows:
            applied_date = str(row["applied_at"] or "")[:10] or "date unknown"
            score = row["weighted_score"] or 0
            print(f"  {applied_date}  {score:.1f}  {row['title']} @ {row['company']}")
            path = applications.archive_path(row, applied_date)
            print(f"      details: {path if path.exists() else 'not archived yet - run `applied --backfill`'}")
            if row["reason"]:
                print(f"      note   : {row['reason']}")
    return 0


def cmd_sync_connections(args: argparse.Namespace) -> int:
    """Make sure every company Doran has a connection at is actually scanned.

    Without this the connection list is only a scoring rule -- a company that
    was never resolved has no board to sweep, so it could get a +1 bump on
    postings that never surface in the first place.
    """
    data = config.connections()
    entries = data.get("companies", []) or []
    if not entries:
        print("No companies in config/connections.yml yet.")
        return 0

    resolved = already = failed = 0
    for entry in entries:
        name = entry.get("name", "")
        if entry.get("ats") and entry.get("slug") and not args.force:
            print(f"  ok      {name:28} {entry['ats']}/{entry['slug']}")
            already += 1
            continue
        res = resolve.resolve(name, force=args.force)
        if res.ok:
            entry["ats"], entry["slug"] = res.ats, res.slug
            resolve.save_resolution(res, watch=True)
            print(f"  added   {name:28} {res.ats}/{res.slug}  ({res.job_count} jobs)")
            resolved += 1
        else:
            print(f"  NO BOARD {name:27} {res.note or 'could not resolve'}")
            failed += 1

    config.save_connections(data)
    print(f"\n{already} already set, {resolved} newly resolved, {failed} without a board.")
    if failed:
        print("Companies without a resolvable board still get the score bump if a "
              "posting turns up via a job board - they just cannot be swept directly.")
    return 0


def cmd_pending(args: argparse.Namespace) -> int:
    with store.connect() as conn:
        rows = store.awaiting_verdict(conn)
        if not rows:
            print("Nothing awaiting your verdict.")
            return 0
        print(f"{len(rows)} posting(s) shown to you but not yet ruled on:\n")
        for row in rows:
            score = row["weighted_score"]
            print(f"  [{row['id']:4}] {(score if score else 0):.1f}  "
                  f"{row['title'][:52]:52} {row['company']}")
            print(f"         {row['url']}")
    return 0


def cmd_shortlist(args: argparse.Namespace) -> int:
    with store.connect() as conn:
        rows = store.shortlist(conn)
        if not rows:
            print("Shortlist is empty.")
            return 0
        for row in rows:
            print(f"[{row['id']:4}] {row['verdict']:15} {(row['weighted_score'] or 0):.1f}  "
                  f"{row['title']} @ {row['company']}")
            print(f"       {row['url']}")
            if row["reason"]:
                print(f"       note: {row['reason']}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    with store.connect() as conn:
        data = store.stats(conn)
        print(f"Postings seen : {data['total_postings']}")
        print(f"Runs          : {data['runs']}")
        print(f"Learned rules : {data['learned_rules']}")
        print("By state:")
        for state, count in sorted(data["by_state"].items(), key=lambda kv: -kv[1]):
            print(f"  {state:22} {count}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    """Ingest browser-scraped postings (BuiltIn, LinkedIn, custom portals).

    Expects a JSON list of objects with at least: company, title, url,
    description. Everything else is optional and normalized here so browser
    sources go through exactly the same gates as ATS feeds.
    """
    from careerops.models import Posting
    from careerops.comp import mentions_bonus, mentions_equity, parse_salary
    from careerops.normalize import clean, parse_datetime, parse_location, parse_work_model

    records = json.loads(Path(args.file).read_text(encoding="utf-8"))
    if isinstance(records, dict):
        records = records.get("postings", [])

    store.init_db()
    added = 0
    with store.connect() as conn:
        run_id = store.start_run(conn, "ingest", {"file": args.file})
        for record in records:
            description = clean(record.get("description"))
            location_raw = clean(record.get("location"))
            city, region, country = parse_location(location_raw)
            salary_min, salary_max = parse_salary(
                record.get("salary") or description
            )
            published = parse_datetime(record.get("published_at"))
            posting = Posting(
                source_id=str(record.get("id") or record.get("url", ""))[:200],
                company=clean(record.get("company")),
                title=clean(record.get("title")),
                url=clean(record.get("url")),
                apply_url=clean(record.get("apply_url") or record.get("url")),
                ats=record.get("source", "browser"),
                source_slug=clean(record.get("board", "")),
                location_raw=location_raw,
                city=city, region=region, country=country,
                workplace_type=parse_work_model(
                    record.get("work_model"), record.get("is_remote"),
                    location_raw, description),
                salary_min=salary_min, salary_max=salary_max,
                salary_raw=clean(record.get("salary")) or None,
                equity_mentioned=mentions_equity(description),
                bonus_mentioned=mentions_bonus(description),
                published_at=published,
                date_confidence="high" if published else "low",
                description=description,
            )
            if not posting.title or not posting.url:
                continue
            store.upsert_posting(conn, posting, run_id)
            added += 1
        store.finish_run(conn, run_id, raw_count=added)
    print(f"Ingested {added} posting(s) from {args.file}. "
          "Run `python cli.py prefilter-pending` to gate them.")
    return 0


def cmd_prefilter_pending(args: argparse.Namespace) -> int:
    """Apply the gates to anything still in state 'new' (e.g. after ingest)."""
    from careerops import prefilter
    from careerops.fingerprint import fingerprint as fp
    from careerops.models import STATE_NEW, STATE_PREFILTERED, STATE_REJECTED_PREFILTER

    with store.connect() as conn:
        rows = store.postings_in_state(conn, STATE_NEW)
        suppressed = store.suppressed_fingerprints(conn)
        kept = 0
        for row in rows:
            class _Shim:
                title = row["title"]
                description = row["description"]
                published_at = row["published_at"]
                city = row["city"]
                workplace_type = row["work_model"]
                location_raw = row["location_raw"]
                salary_max = row["salary_max"]

            result = prefilter.evaluate(
                _Shim, suppressed=suppressed,
                posting_fingerprint=fp(row["company"], row["title"], row["description"]),
                enforce_freshness=not args.all_open,
                freshness_days=args.days,
                first_sighting=True,
            )
            if result.passed:
                store.set_state(conn, row["id"], STATE_PREFILTERED,
                                f"relevance {result.relevance:.1f}")
                # Persist the tracks, exactly as pipeline.py does. Without this
                # the whole ingest and browser-board path landed with tracks=''
                # and every such posting fell into the AI bucket by default --
                # which mattered the moment buckets became load-bearing.
                conn.execute(
                    "UPDATE postings SET tracks = ?, audience = ?, "
                    "ai_fluency_requested = ? WHERE id = ?",
                    (",".join(result.tracks), result.audience,
                     int(result.ai_fluency_requested), row["id"]),
                )
                kept += 1
            else:
                store.set_state(conn, row["id"], STATE_REJECTED_PREFILTER, result.reason)
        print(f"{kept}/{len(rows)} passed the prefilter.")
    return 0


def cmd_refresh_tokens(args: argparse.Namespace) -> int:
    """Rebuild the local index of ATS board slugs that actually exist.

    Resolution guesses slugs otherwise, which finds roughly a third of companies
    because a slug is not derivable from a name. Worth re-running every few
    months; the underlying datasets are updated upstream, not by us.
    """
    from careerops.sources import tokens

    counts = tokens.refresh(on_note=lambda note: print(f"  {note}"))
    if not counts:
        print("Could not download any slug lists - index left unchanged.")
        return 1
    print(f"\n  {tokens.size()} board slugs cached to {tokens.CACHE}")
    print(f"  {tokens.ATTRIBUTION}")
    return 0


def cmd_recompute_tracks(args: argparse.Namespace) -> int:
    """Re-derive which bucket each already-scored posting belongs to.

    `postings.tracks` decides which of the three lists a posting appears in, and
    it is written once, at scan time. So a change to the bucketing rules applies
    to everything scanned afterwards and silently misses everything already on
    record -- which is exactly what happened when the marketing-in-AI-clothing
    rule landed: Vercel and Apollo kept the overlap bucket they were assigned
    before the rule existed, and stayed on the lenient list the rule was written
    to move them off.

    Nothing here re-scores anything. It only re-answers "which list?".
    """
    changed = []
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM postings WHERE state IN ('evaluated', 'presented')"
        ).fetchall()
        for row in rows:
            result = prefilter_mod.evaluate(
                row, suppressed=set(),
                posting_fingerprint=str(row["fingerprint"]),
                enforce_freshness=False,
            )
            fresh = ",".join(result.tracks)
            if fresh == (row["tracks"] or ""):
                continue
            # A posting that now fails the gates outright keeps its tracks. It
            # was judged under the rules of its day and this command's job is
            # routing, not retroactive rejection.
            if not result.tracks:
                continue
            changed.append((row, fresh))
            if not args.dry_run:
                conn.execute("UPDATE postings SET tracks = ? WHERE id = ?",
                             (fresh, row["id"]))

    if not changed:
        print(f"All {len(rows)} scored postings are already in the right bucket.")
        return 0

    verb = "would move" if args.dry_run else "moved"
    print(f"{verb} {len(changed)} of {len(rows)} scored posting(s):\n")
    for row, fresh in changed:
        before = config.bucket_label(config.bucket_of(row["tracks"]))
        after = config.bucket_label(config.bucket_of(fresh))
        print(f"  {row['company'][:20]:22s} {row['title'][:38]:40s} "
              f"{before} -> {after}")
    if args.dry_run:
        print("\nDry run. Nothing was written.")
    return 0


def cmd_tiebreak(args: argparse.Namespace) -> int:
    """List the close calls a holistic read is allowed to touch.

    Python's whole job here is picking who is eligible. It writes a worksheet of
    postings sitting within the close-call band of their own bucket's bar, with
    the full posting body attached, and a template to answer in. The reading and
    the judgement are Claude's; `record-tiebreak` audits what comes back.
    """
    from careerops import tiebreak as tb

    with store.connect() as conn:
        # --limit may only tighten the cap, never raise it.
        limit = min(args.limit or tb.MAX_PER_RUN, tb.MAX_PER_RUN)
        rows = tb.candidates(conn, run_id=args.run, limit=limit)
        if not rows:
            scope = f"run {args.run}" if args.run else "the whole database"
            print(f"No close calls in {scope}. Nothing for the tiebreaker to do.")
            return 0

        run_dir = config.RUNS_DIR / str(args.run or "all")
        run_dir.mkdir(parents=True, exist_ok=True)

        lines = [
            f"# Tiebreaker worksheet - {len(rows)} close call(s)",
            "",
            f"Every posting here scored within {tb.BAND:.2f} of the bar for its own",
            f"bucket. Read the FULL posting body below - not the fit summary, not the",
            "block notes - and decide whether the score reads right against what the",
            "job actually is.",
            "",
            f"- A nudge may be at most {tb.MAX_ADJUSTMENT:+.2f}, in either direction.",
            f"- It needs {tb.MIN_QUOTES} verbatim quotes of {tb.MIN_QUOTE_CHARS}+ characters "
            "from the body, checked character by character on the way in.",
            "- Leaving a posting alone is a valid answer, and is the default.",
            "",
            "Answer in `tiebreak.json` beside this file, then apply it with:",
            "",
            "```",
            f"python cli.py record-tiebreak --file {run_dir.as_posix()}/tiebreak.json",
            "```",
            "",
            "---",
            "",
        ]
        template = []
        for i, row in enumerate(rows, start=1):
            bucket = config.bucket_of(row["tracks"])
            bar = config.bucket_threshold(bucket)
            base = tb.base_score(row)
            gap = base - bar
            lines += [
                f"### {i}. {row['title']} - {row['company']}",
                "",
                f"- **posting_id**: `{row['id']}`",
                f"- **bucket**: {config.bucket_label(bucket)}  |  bar {bar:.2f}",
                f"- **rubric score**: {base:.2f}  "
                f"({'clears by' if gap >= 0 else 'misses by'} {abs(gap):.2f})",
                f"- **URL**: {row['url']}",
                f"- **Location**: {row['location_raw'] or 'unstated'}"
                f"  |  work model: {row['work_model'] or 'unknown'}",
                "",
                "<details><summary>Full description</summary>",
                "",
                "```text",
                (row["description"] or "").strip(),
                "```",
                "",
                "</details>",
                "",
            ]
            template.append({
                "posting_id": row["id"],
                "company": row["company"],
                "title": row["title"],
                "adjustment": 0.0,
                "note": "",
                "quotes": [],
            })

        (run_dir / "tiebreak.md").write_text("\n".join(lines), encoding="utf-8")
        (run_dir / "tiebreak.json").write_text(
            json.dumps({"tiebreaks": template}, indent=2), encoding="utf-8"
        )
    print(f"{len(rows)} close call(s) written to {run_dir / 'tiebreak.md'}")
    print(f"Answer in {run_dir / 'tiebreak.json'}")
    return 0


def cmd_record_tiebreak(args: argparse.Namespace) -> int:
    """Apply holistic nudges, refusing every one that breaks the licence.

    This is the audit, and it is the whole reason the tiebreaker is safe to have
    at all. Nothing is trusted from the file: eligibility is recomputed from the
    database, the quotes are matched against the stored posting body, and the
    per-run cap is counted here rather than assumed.
    """
    from careerops import tiebreak as tb

    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    items = [i for i in payload.get("tiebreaks", []) if float(i.get("adjustment") or 0)]

    if len(items) > tb.MAX_PER_RUN:
        print(f"REFUSED: {len(items)} nudges exceeds the {tb.MAX_PER_RUN} per-run cap.")
        return 1

    applied = 0
    refused = 0
    with store.connect() as conn:
        max_score = float(config.connections().get("max_score", 5.0))
        for item in items:
            posting_id = int(item["posting_id"])
            posting = store.get_posting(conn, posting_id)
            evaluation = store.latest_evaluation(conn, posting_id)
            if not posting or not evaluation:
                print(f"  posting {posting_id}: REFUSED - no evaluation on record")
                refused += 1
                continue

            bucket = config.bucket_of(posting["tracks"])
            base = tb.base_score(evaluation)
            adjustment = float(item["adjustment"])
            quotes = [str(q) for q in (item.get("quotes") or [])]
            problems = tb.validate(
                adjustment, quotes, posting["description"] or "", base, bucket
            )
            if problems:
                refused += 1
                print(f"  posting {posting_id} ({posting['company']}): REFUSED")
                for problem in problems:
                    print(f"      - {problem}")
                continue

            final = store.apply_tiebreak(
                conn, int(evaluation["id"]),
                base_score=base, adjustment=adjustment,
                note=str(item.get("note", "")), quotes=quotes,
                max_score=max_score,
            )
            applied += 1
            bar = config.bucket_threshold(bucket)
            crossed = (base < bar <= final) or (final < bar <= base)
            print(f"  posting {posting_id} ({posting['company']}): "
                  f"{base:.2f} -> {final:.2f} ({adjustment:+.2f})"
                  + ("  [CROSSES THE BAR]" if crossed else ""))

    print(f"\nApplied {applied} nudge(s), refused {refused}.")
    return 1 if refused else 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    """Regression test the rubric against the anchors and the applied-job list."""
    from careerops import regression
    from careerops.calibrate import run_calibration

    if args.applied_only:
        return regression.run()

    rc = run_calibration(check_only=args.check)

    # The anchors are scored from documents and never touch the deterministic
    # gates, so they cannot catch a geography, title-band or comp change that
    # makes a real job invisible. The applied list can, and it is free to run.
    if args.check:
        print()
        rc = regression.run() or rc

        # Every holistic nudge standing today, listed beside the anchors. The
        # tiebreaker is the only place a score moves on judgement rather than on
        # the rubric, so it is the only one that needs re-reading periodically.
        from careerops import tiebreak as tb
        with store.connect() as conn:
            nudges = tb.audit(conn)
        print()
        if not nudges:
            print("Tiebreak audit - no holistic nudges are in force.")
        else:
            print(f"Tiebreak audit - {len(nudges)} holistic nudge(s) in force "
                  f"(each capped at {tb.MAX_ADJUSTMENT:+.2f}):")
            for row in nudges:
                bucket = config.bucket_of(row["tracks"])
                adjustment = float(row["tiebreak_adjustment"])
                base = float(row["weighted_score"]) - adjustment
                print(f"  {base:.2f} {adjustment:+.2f} -> {row['weighted_score']:.2f}  "
                      f"[{bucket}]  {row['company'][:22]} - {row['title'][:40]}")
                if row["tiebreak_note"]:
                    print(f"        {row['tiebreak_note'][:100]}")
    return rc


def cmd_add_rule(args: argparse.Namespace) -> int:
    from careerops.normalize import now_iso
    rules_path = config.RUBRIC_DIR / "learned-rules.md"
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = now_iso()[:10]
    entry = f"\n- **{stamp}** (dim {args.dimension or '-'}): {args.rule}\n"
    with rules_path.open("a", encoding="utf-8") as handle:
        handle.write(entry)
    with store.connect() as conn:
        store.add_learned_rule(conn, args.rule, args.dimension)
    print(f"Rule recorded in {rules_path}")
    return 0


# ------------------------------------------------------------------------ main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py", description="careerops - HITL job discovery and evaluation"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the database").set_defaults(func=cmd_init)

    p = sub.add_parser("verify-sources", help="probe/resolve every configured company")
    p.add_argument("--force", action="store_true", help="re-resolve even known slugs")
    p.set_defaults(func=cmd_verify_sources)

    p = sub.add_parser("resolve-company", help="find a company's live ATS board")
    p.add_argument("company")
    p.add_argument("--save", action="store_true", help="cache into sources.yml")
    p.add_argument("--watch", action="store_true", help="also add to the broad sweep")
    p.add_argument("--force", action="store_true", help="ignore the cache")
    p.set_defaults(func=cmd_resolve_company)

    p = sub.add_parser("scan", help="discover + prefilter (broad or targeted)")
    p.add_argument("--companies", help="comma-separated names -> targeted mode")
    p.add_argument("--fresh", action="store_true",
                   help="targeted mode: apply the 14-day window")
    p.add_argument("--all-open", action="store_true",
                   help="broad mode: ignore the freshness window")
    p.add_argument("--days", type=int, help="override the freshness window")
    p.add_argument("--watch", action="store_true",
                   help="targeted mode: add these companies to the broad sweep")
    p.add_argument("--skip-liveness", action="store_true")
    p.add_argument("--no-boards", action="store_true",
                   help="skip role-first board discovery (company sweep only)")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("queue", help="re-render the evaluation queue")
    p.add_argument("--run", type=int)
    p.set_defaults(func=cmd_queue)

    p = sub.add_parser("record-eval", help="write A-G scores back")
    p.add_argument("--file", required=True)
    p.add_argument("--run", type=int)
    p.add_argument("--track", choices=list(config.TRACKS),
                   help="which list these scores belong to (default: ai_enablement)")
    p.set_defaults(func=cmd_record_eval)

    p = sub.add_parser("recompute-tracks",
                       help="re-derive which list each scored posting belongs in")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_recompute_tracks)

    p = sub.add_parser("tiebreak", help="worksheet of close calls for a holistic read")
    p.add_argument("--run", type=int)
    p.add_argument("--limit", type=int, default=None,
                   help="cap the worksheet (never above the built-in per-run cap)")
    p.set_defaults(func=cmd_tiebreak)

    p = sub.add_parser("record-tiebreak", help="apply audited holistic nudges")
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_record_tiebreak)

    p = sub.add_parser("report", help="render the six-field match list")
    p.add_argument("--threshold", type=float)
    p.add_argument("--companies", help="add near-miss lines for these companies")
    p.add_argument("--run", type=int)
    p.add_argument("--no-mark", action="store_true",
                   help="preview without marking postings as presented")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("verdict", help="record Doran's verdict on a posting")
    p.add_argument("--posting", type=int, required=True)
    p.add_argument("--verdict", required=True,
                   help="interested | saved | not_interested | applied")
    p.add_argument("--reason")
    p.add_argument("--date", help="YYYY-MM-DD he actually applied (default: today)")
    p.set_defaults(func=cmd_verdict)

    p = sub.add_parser("applied", help="every role applied to + its saved details")
    p.add_argument("--backfill", action="store_true",
                   help="(re)write the archive file for every applied posting")
    p.set_defaults(func=cmd_applied)

    p = sub.add_parser("sync-connections",
                       help="resolve connection companies and force them into the sweep")
    p.add_argument("--force", action="store_true", help="re-resolve even known boards")
    p.set_defaults(func=cmd_sync_connections)

    sub.add_parser("pending", help="postings shown but not yet ruled on").set_defaults(
        func=cmd_pending)
    sub.add_parser("shortlist", help="saved / interested pipeline").set_defaults(
        func=cmd_shortlist)
    sub.add_parser("status", help="database summary").set_defaults(func=cmd_status)

    p = sub.add_parser("ingest", help="ingest browser-scraped postings from JSON")
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("prefilter-pending", help="gate anything still in state 'new'")
    p.add_argument("--all-open", action="store_true")
    p.add_argument("--days", type=int)
    p.set_defaults(func=cmd_prefilter_pending)

    p = sub.add_parser("calibrate", help="regression test the rubric")
    p.add_argument("--check", action="store_true",
                   help="verify recorded scores without re-queuing, then run the "
                        "applied-job regression check")
    p.add_argument("--applied-only", action="store_true",
                   help="skip the anchors and only check that every job you "
                        "applied to would still get through the gates and clear "
                        "the bar")
    p.set_defaults(func=cmd_calibrate)

    p = sub.add_parser(
        "refresh-tokens",
        help="download the local ATS slug index used to resolve companies cheaply")
    p.set_defaults(func=cmd_refresh_tokens)

    p = sub.add_parser("add-rule", help="append a learned rule")
    p.add_argument("rule")
    p.add_argument("--dimension")
    p.set_defaults(func=cmd_add_rule)

    return parser


def main() -> int:
    # Windows consoles default to cp1252, which cannot encode the Block G warning
    # glyph or the en dashes in salary ranges. Without this the report crashes
    # exactly when a legitimacy flag needs to be shown.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
