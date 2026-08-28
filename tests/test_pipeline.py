"""Pipeline behaviour tests: suppression, freshness, ghost detection, state machine.

These cover the guarantees Doran asked for by name -- never show the same posting
twice, only show recent postings -- plus the ghost-job signals. They run against a
temporary database and make no network calls.

Run with:  python tests/test_pipeline.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from careerops import config, prefilter, store  # noqa: E402
from careerops.fingerprint import fingerprint  # noqa: E402
from careerops.models import (  # noqa: E402
    STATE_NOT_INTERESTED, STATE_PRESENTED, Posting,
)
from careerops.normalize import days_ago_iso  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, expected) -> None:
    if got != expected:
        FAILURES.append(f"{label}\n    expected: {expected!r}\n    got     : {got!r}")
        print(f"  FAIL  {label}")
    else:
        print(f"  ok    {label}")


ARCHETYPE_DESC = (
    "You will own AI enablement for the marketing organization. Lead AI strategy "
    "and build agentic workflows that automate campaign operations, and upskill our "
    "demand generation, product marketing, and content marketing teams to build "
    "their own AI agents. Partner with VP-level stakeholders on go-to-market AI "
    "adoption. We work human-in-the-loop by design: automation handles the "
    "groundwork, people keep the strategy. Experience with LLM tooling, prompt "
    "systems, MCP and workflow automation is valued. This is marketing operations "
    "meets AI transformation, a first role of its kind here."
)


def make_posting(**overrides) -> Posting:
    fields = dict(
        source_id="J-1",
        company="Acme",
        title="Marketing Engineer",
        url="https://example.com/jobs/1",
        ats="greenhouse",
        source_slug="acme",
        apply_url="https://example.com/jobs/1/apply",
        location_raw="Remote - US",
        city=None,
        workplace_type="Remote",
        published_at=days_ago_iso(3),
        date_confidence="high",
        description=ARCHETYPE_DESC,
        salary_min=180000,
        salary_max=230000,
    )
    fields.update(overrides)
    return Posting(**fields)


def fp_of(posting: Posting) -> str:
    return fingerprint(posting.company, posting.title, posting.description)


# ------------------------------------------------------------------ freshness

# The window is read from config/profile.yml, so this reads it too rather than
# hard-coding a number that goes stale the next time Doran widens it. It was 14,
# then 30, and 60 since 2026-08-25.
WINDOW = config.profile()["hard_gates"]["freshness_days"]
print(f"\nfreshness (Doran's {WINDOW}-day window)")

fresh = make_posting(published_at=days_ago_iso(3))
stale = make_posting(published_at=days_ago_iso(WINDOW + 5))
# The band the window was widened INTO. A 45-day-old posting was dropped under
# the old 30-day rule and must now survive -- that is the whole point of the
# change, and a regression here would silently undo it.
borderline = make_posting(published_at=days_ago_iso(45))

check(
    "3-day-old posting passes",
    prefilter.evaluate(fresh, suppressed=set(), posting_fingerprint=fp_of(fresh)).passed,
    True,
)
check(
    "45-day-old posting passes, which the old 30-day window rejected",
    prefilter.evaluate(
        borderline, suppressed=set(), posting_fingerprint=fp_of(borderline)
    ).passed,
    True,
)
res = prefilter.evaluate(stale, suppressed=set(), posting_fingerprint=fp_of(stale))
check("a posting past the window is dropped", res.passed, False)
check("...and says why", f"{WINDOW + 5} days ago" in res.reason, True)
check(
    "targeted mode ignores the window",
    prefilter.evaluate(
        stale, suppressed=set(), posting_fingerprint=fp_of(stale),
        enforce_freshness=False,
    ).passed,
    True,
)

undated = make_posting(published_at=None, date_confidence="none")
check(
    "undated posting allowed on first sighting",
    prefilter.evaluate(
        undated, suppressed=set(), posting_fingerprint=fp_of(undated),
        first_sighting=True,
    ).passed,
    True,
)
check(
    "undated posting rejected once already seen",
    prefilter.evaluate(
        undated, suppressed=set(), posting_fingerprint=fp_of(undated),
        first_sighting=False,
    ).passed,
    False,
)

# ---------------------------------------------------------------- hard gates

print("\nhard gates")

vp = make_posting(title="Martech Operations and AI Enablement Lead - Vice President")
res = prefilter.evaluate(vp, suppressed=set(), posting_fingerprint=fp_of(vp))
check("VP title rejected despite perfect content", res.passed, False)
check("...for the right reason", "above Doran's ceiling" in res.reason, True)

far = make_posting(workplace_type="On-site", location_raw="Wilmington, DE",
                   city="Wilmington")
res = prefilter.evaluate(far, suppressed=set(), posting_fingerprint=fp_of(far))
check("out-of-range commute rejected", res.passed, False)

near = make_posting(workplace_type="On-site", location_raw="Palo Alto, CA",
                    city="Palo Alto")
check(
    "Palo Alto on-site accepted",
    prefilter.evaluate(near, suppressed=set(), posting_fingerprint=fp_of(near)).passed,
    True,
)

lowpay = make_posting(salary_min=90000, salary_max=120000)
res = prefilter.evaluate(lowpay, suppressed=set(), posting_fingerprint=fp_of(lowpay))
check("band topping out below $150k rejected", res.passed, False)

# Harvey's band straddles the floor and must survive to be scored properly.
straddle = make_posting(salary_min=136000, salary_max=204000)
check(
    "wide band straddling the floor survives (the Harvey case)",
    prefilter.evaluate(
        straddle, suppressed=set(), posting_fingerprint=fp_of(straddle)
    ).passed,
    True,
)

offshore = make_posting(workplace_type="Remote", location_raw="Remote - India")
check(
    "non-US remote rejected",
    prefilter.evaluate(
        offshore, suppressed=set(), posting_fingerprint=fp_of(offshore)
    ).passed,
    False,
)

# --------------------------------------------------- suppression / state machine

print("\nsuppression (never show the same posting twice)")

with tempfile.TemporaryDirectory() as tmp:
    db = Path(tmp) / "test.db"
    store.init_db(db)

    with store.connect(db) as conn:
        run1 = store.start_run(conn, "broad")
        original = make_posting(source_id="J-100")
        pid, is_new = store.upsert_posting(conn, original, run1)
        check("first insert is new", is_new, True)

        check(
            "nothing suppressed before anything is shown",
            len(store.suppressed_fingerprints(conn)), 0,
        )

        store.mark_presented(conn, [pid], run1)
        suppressed = store.suppressed_fingerprints(conn)
        check("presenting adds the fingerprint to the suppression set",
              fp_of(original) in suppressed, True)

        check(
            "a presented posting is filtered out on the next run",
            prefilter.evaluate(
                original, suppressed=suppressed, posting_fingerprint=fp_of(original)
            ).passed,
            False,
        )

        # The real test: the same role reposted under a brand-new ATS id with a
        # lightly edited title. Id-level dedupe would miss this entirely.
        run2 = store.start_run(conn, "broad")
        repost = make_posting(
            source_id="J-999-NEW",
            title="Marketing Engineer (Remote)",
            url="https://example.com/jobs/999",
            published_at=days_ago_iso(1),
        )
        rid, r_new = store.upsert_posting(conn, repost, run2)
        check("repost is stored as a separate row", rid != pid, True)
        check("...and is recognised as a new ATS id", r_new, True)
        check(
            "...but shares the original's fingerprint",
            fp_of(repost) == fp_of(original), True,
        )
        check(
            "...so it is still suppressed",
            prefilter.evaluate(
                repost,
                suppressed=store.suppressed_fingerprints(conn),
                posting_fingerprint=fp_of(repost),
            ).passed,
            False,
        )

        # A rejection must stay rejected too, not just an un-ruled presentation.
        store.record_verdict(conn, pid, STATE_NOT_INTERESTED, "AI work sits in IT, not marketing")
        check(
            "a rejected posting stays suppressed",
            fp_of(original) in store.suppressed_fingerprints(conn), True,
        )
        row = store.get_posting(conn, pid)
        check("verdict updates the posting state", row["state"], STATE_NOT_INTERESTED)

        # ------------------------------------------------------ ghost signals
        print("\nghost-job signals")

        signals = store.repost_signals(conn, fp_of(original))
        check("two ATS ids share one fingerprint", signals["distinct_posting_ids"], 2)
        check("publish date reset across sightings",
              signals["distinct_published_dates"] >= 2, True)
        check("perpetual-repost signal fires", signals["perpetual_repost"], True)

        clean = make_posting(source_id="J-CLEAN", company="Cleanco",
                             url="https://example.com/jobs/clean")
        cid, _ = store.upsert_posting(conn, clean, run2)
        clean_signals = store.repost_signals(conn, fp_of(clean))
        check("a single sighting does not trip the signal",
              clean_signals["perpetual_repost"], False)

        # --------------------------------------------------- presentable gate
        print("\npresentation gate")

        store.record_evaluation(
            conn, cid, run_id=run2, rubric_version="1",
            dimension_scores={str(i): 4.5 for i in range(1, 11)},
            weighted_score=4.5, block_g_verdict="PASS", block_g_flags=[],
            fit_summary="Strong match.",
        )
        check("a 4.5 posting is presentable", len(store.presentable(conn, 4.0)), 1)

        low = make_posting(source_id="J-LOW", company="Lowco",
                           url="https://example.com/jobs/low")
        lid, _ = store.upsert_posting(conn, low, run2)
        store.record_evaluation(
            conn, lid, run_id=run2, rubric_version="1",
            dimension_scores={str(i): 3.5 for i in range(1, 11)},
            weighted_score=3.6, block_g_verdict="PASS", block_g_flags=[],
            fit_summary="Adjacent.",
        )
        check("a 3.6 posting is not presentable", len(store.presentable(conn, 4.0)), 1)

        # Block G FAIL must remove a high scorer entirely.
        fail = make_posting(source_id="J-DEAD", company="Deadco",
                            url="https://example.com/jobs/dead")
        fid, _ = store.upsert_posting(conn, fail, run2)
        store.record_evaluation(
            conn, fid, run_id=run2, rubric_version="1",
            dimension_scores={str(i): 4.8 for i in range(1, 11)},
            weighted_score=4.8, block_g_verdict="FAIL",
            block_g_flags=["apply URL dead"], fit_summary="Would be great, but closed.",
        )
        check("Block G FAIL removes a 4.8 posting", len(store.presentable(conn, 4.0)), 1)

        # A dead apply URL must also remove it, independent of Block G.
        alive = make_posting(source_id="J-ALIVE", company="Aliveco",
                             url="https://example.com/jobs/alive")
        aid, _ = store.upsert_posting(conn, alive, run2)
        store.record_evaluation(
            conn, aid, run_id=run2, rubric_version="1",
            dimension_scores={str(i): 4.6 for i in range(1, 11)},
            weighted_score=4.6, block_g_verdict="PASS", block_g_flags=[],
            fit_summary="Good.",
        )
        check("live posting presentable", len(store.presentable(conn, 4.0)), 2)
        store.mark_live_checked(conn, aid, False)
        check("posting marked dead drops out", len(store.presentable(conn, 4.0)), 1)

        # ------------------------------------------------------ three buckets
        #
        # Added 2026-08-28. Doran: "there's the traditional marketing role and
        # then there's the AI role. And then there's a third bucket of where
        # they overlap. And so I want to know about all three of these when you
        # present the lists." Each bucket gets its own bar, easiest for overlap.
        #
        # The bucket comes from postings.tracks, which the prefilter had always
        # computed and persisted and which nothing read until now.
        print("\nthree buckets")

        check("both tracks is the overlap bucket",
              config.bucket_of("ai_enablement,growth_marketing"),
              config.BUCKET_OVERLAP)
        check("AI alone is the AI bucket",
              config.bucket_of("ai_enablement"), config.BUCKET_AI)
        check("growth alone is the marketing bucket",
              config.bucket_of("growth_marketing"), config.BUCKET_MARKETING)
        check("a list works as well as a string",
              config.bucket_of(["growth_marketing", "ai_enablement"]),
              config.BUCKET_OVERLAP)
        # Every posting scored before buckets existed has tracks='' and was
        # treated as AI. That must stay true or their history reclassifies.
        check("no recorded track falls back to AI",
              config.bucket_of(""), config.BUCKET_AI)
        check("None falls back to AI", config.bucket_of(None), config.BUCKET_AI)

        # Bars ordered: overlap easiest, marketing hardest -- the 0/+1/+2 scale.
        overlap_bar = config.bucket_threshold(config.BUCKET_OVERLAP)
        ai_bar = config.bucket_threshold(config.BUCKET_AI)
        mkt_bar = config.bucket_threshold(config.BUCKET_MARKETING)
        check("overlap is the most lenient bar", overlap_bar < ai_bar, True)
        check("AI sits between the two", ai_bar < mkt_bar, True)
        check("marketing keeps the normal 4.0 bar", mkt_bar, 4.0)
        # A bar at or below the near-miss floor would empty that bucket's
        # near-miss band, silently hiding the roles he most wants to see.
        floor = float(config.profile()["review"]["worth_knowing_floor"])
        check("the most lenient bar still leaves a near-miss band",
              overlap_bar > floor, True)

        # A marketing-only posting MUST be judged on the growth rubric: under
        # scoring.yml, dimension 1 (weight 22) makes AI enablement the hard
        # requirement, so a pure marketing role cannot clear the bar there.
        check("marketing bucket is judged on the growth rubric",
              config.bucket_rubric(config.BUCKET_MARKETING), config.TRACK_GROWTH)
        check("overlap is judged on the AI rubric",
              config.bucket_rubric(config.BUCKET_OVERLAP), config.TRACK_AI)

        # Routing: the buckets are disjoint, so an overlap posting appears in
        # the overlap list ONLY and needs no dedupe between lists.
        both = make_posting(source_id="J-BOTH", company="Bothco",
                            url="https://example.com/jobs/both")
        bid, _ = store.upsert_posting(conn, both, run2)
        conn.execute("UPDATE postings SET tracks = ? WHERE id = ?",
                     ("ai_enablement,growth_marketing", bid))
        store.record_evaluation(
            conn, bid, run_id=run2, rubric_version="1",
            dimension_scores={str(i): 4.2 for i in range(1, 11)},
            weighted_score=4.2, block_g_verdict="PASS", block_g_flags=[],
            fit_summary="Both.", track="ai_enablement",
        )
        check("a both-tracks posting lands in overlap",
              bid in {r["id"] for r in store.presentable(
                  conn, 3.75, bucket=config.BUCKET_OVERLAP)}, True)
        check("...and not in the AI list",
              bid in {r["id"] for r in store.presentable(
                  conn, 3.85, bucket=config.BUCKET_AI)}, False)
        check("...and not in the marketing list",
              bid in {r["id"] for r in store.presentable(
                  conn, 4.0, bucket=config.BUCKET_MARKETING)}, False)

        # A marketing-only posting's only score is recorded under the growth
        # track. Filtering on bucket AND track would return nothing, so
        # presentable drops the track filter whenever a bucket is given.
        mkt = make_posting(source_id="J-MKT", company="Mktco",
                           url="https://example.com/jobs/mkt")
        mid, _ = store.upsert_posting(conn, mkt, run2)
        conn.execute("UPDATE postings SET tracks = ? WHERE id = ?",
                     ("growth_marketing", mid))
        store.record_evaluation(
            conn, mid, run_id=run2, rubric_version="1",
            dimension_scores={str(i): 4.3 for i in range(1, 11)},
            weighted_score=4.3, block_g_verdict="PASS", block_g_flags=[],
            fit_summary="Marketing.", track="growth_marketing",
        )
        check("a growth-scored posting is found by its bucket",
              mid in {r["id"] for r in store.presentable(
                  conn, 4.0, bucket=config.BUCKET_MARKETING)}, True)

        # ------------------------------------------------------- near misses
        print("\nnear misses (targeted mode only)")

        near_rows = store.near_misses(conn, 4.0, ["Lowco", "Cleanco"])
        names = {r["company"] for r in near_rows}
        check("sub-threshold company appears as a near miss", "Lowco" in names, True)
        check("a company that cleared the bar does not", "Cleanco" not in names, True)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):\n")
    for failure in FAILURES:
        print(f"  {failure}\n")
    raise SystemExit(1)
print("All pipeline tests passed.")
