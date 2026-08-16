#!/usr/bin/env python
"""careerops CLI - the deterministic half of the job search agent.

Discovery and evaluation only. There is deliberately no `apply` command and
there never will be (see CLAUDE.md).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from careerops import config, pipeline, report, resolve, store  # noqa: E402
from careerops.models import VERDICTS  # noqa: E402
from careerops.sources.registry import _client, probe  # noqa: E402


def _threshold() -> float:
    return float(config.profile().get("review", {}).get("min_score_to_present", 4.0))


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
    track = payload.get("track", args.track or config.TRACK_AI)
    scoring = config.scoring(track)
    weights = {str(d["id"]): float(d["weight"]) for d in scoring["dimensions"]}
    cap = float(scoring.get("evidence", {}).get("cap_without_evidence", 3.0))
    total_weight = sum(weights.values())

    written = 0
    with store.connect() as conn:
        for item in payload.get("evaluations", []):
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

            store.record_evaluation(
                conn,
                int(item["posting_id"]),
                run_id=payload.get("run_id"),
                rubric_version=str(payload.get("rubric_version", scoring.get("version"))),
                track=track,
                scope_modifier=adjustment,
                dimension_scores=dims,
                weighted_score=round(weighted, 3),
                block_g_verdict=item.get("block_g_verdict", "PASS"),
                block_g_flags=item.get("block_g_flags") or [],
                fit_summary=item.get("fit_summary", ""),
                block_notes=notes,
            )
            written += 1
            scope_note = f" scope={scope} {adjustment:+.2f}" if adjustment else ""
            print(f"  posting {item['posting_id']}: {weighted:.2f}"
                  f"{scope_note} [G={item.get('block_g_verdict', 'PASS')}]")
    print(f"\nRecorded {written} evaluation(s).")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    threshold = args.threshold if args.threshold is not None else _threshold()
    with store.connect() as conn:
        review = config.profile().get("review", {})
        limit = int(review.get("max_results_per_report", 12))

        matches = store.presentable(conn, threshold, track=config.TRACK_AI)[:limit]

        # List 2: the growth-marketing backup track, deduped against list 1.
        growth_cfg = config.scoring(config.TRACK_GROWTH)
        growth_limit = int(growth_cfg.get("max_results", 5))
        growth_threshold = float(growth_cfg.get("pass_threshold", threshold))
        shown = {row["id"] for row in matches}
        backup = [r for r in store.presentable(conn, growth_threshold,
                                               track=config.TRACK_GROWTH)
                  if r["id"] not in shown][:growth_limit]

        near = []
        if args.companies:
            names = [c.strip() for c in args.companies.split(",") if c.strip()]
            shown = {row["company"].lower() for row in matches}
            near = [r for r in store.near_misses(conn, threshold, names)
                    if r["company"].lower() not in shown]

        # Built as one string, then printed AND archived, so the markdown file
        # is byte-for-byte what Doran saw rather than a second rendering of it.
        parts = [report.render_both_lists(matches, backup)]

        # Anything just under the bar gets a one-line mention rather than being
        # silently dropped -- Doran asked explicitly not to have near-misses
        # hidden from him.
        review = config.profile().get("review", {})
        floor = float(review.get("worth_knowing_floor", 3.7))
        cap = int(review.get("max_worth_knowing", 3))
        shown_ids = {row["id"] for row in matches}
        worth = [r for r in store.worth_knowing(conn, threshold, floor, cap)
                 if r["id"] not in shown_ids]
        if worth:
            parts.append(report.render_worth_knowing(worth))

        if near:
            parts.append(report.render_near_misses(near))

        presented = "\n".join(parts)
        print(presented)

        run = store.latest_run(conn)
        run_id = args.run or (run["id"] if run else 0)

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

        if (matches or backup) and not args.no_mark:
            ids = [row["id"] for row in matches] + [row["id"] for row in backup]
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


def cmd_calibrate(args: argparse.Namespace) -> int:
    """Regression test the rubric against the five anchors."""
    from careerops.calibrate import run_calibration
    return run_calibration(check_only=args.check)


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
    p.set_defaults(func=cmd_verdict)

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
                   help="verify recorded scores without re-queuing")
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
