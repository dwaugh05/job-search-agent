# Why 4 BuiltIn postings never reached you — gap analysis

Doran forwarded 4 postings from his BuiltIn weekly email digest (2026-08-25) that
never appeared in a scan. This checks each one against the pipeline and proposes
fixes. **Analysis only — nothing in the pipeline was changed.**

## Verdict per posting

| # | Posting | Should it have shown up? | Why it didn't |
|---|---|---|---|
| 1 | Trustly — Staff AI Enablement Engineer (SF, in-office, $250k-$350k) | **Yes** | Never discovered. Not a tracked company; excluded from both automated sources (see below). |
| 2 | Replicant — AI Enablement Engineer (Remote) | **Partially — it did, mislabeled** | The real employer isn't tracked, but this exact posting was found and scored (4.60, run 14) via a reseller — Jobgether — that hides the employer name. You saw it as an anonymous "unnamed client" role, not as Replicant. |
| 3 | ALTEN Technology USA — TPM, Operations & AI Enablement (Foster City hybrid, $110k-$130k) | **No — correctly excluded** | Band tops out at $130k, below your $150k comp floor. Content is also mostly Jira/budget administration for a hardware team with AI as one bullet, not the archetype. Even if it had reached scoring it would land near 2.0-2.5 on dimension 1. |
| 4 | ClearView Healthcare Partners — AI Enablement Manager (Boston/NY/SF, in-office, salary TBD) | **Yes** | Never discovered. Not a tracked company; excluded from both automated sources. On content, this is a strong match — portfolio prioritization, workflow design, training and adoption metrics is close to your three-hats archetype. |

**Bottom line: 3 of 4 were real misses. 1 (ALTEN) was a correct exclusion — the pipeline worked as intended there.**

## Root causes (verified against the code, not guessed)

### 1. BuiltIn scraping is scoped to two hand-picked URLs, not your account feed
`config/sources.yml` points the automated BuiltIn scraper at exactly two URLs:

- `builtinsf.com/jobs/hybrid/remote/dev-engineering/marketing` — SF/hybrid/remote only, dev-engineering + marketing categories only
- `builtin.com/jobs/remote/marketing` — remote only, marketing category only

Your weekly email digest comes from BuiltIn's own personalization on your saved
preferences — a much wider net across categories (engineering, operations,
consulting) and work models. All 3 real misses fall outside what those two fixed
URLs can ever return:

- Trustly is **in-office** — excluded by the `hybrid/remote` in the SF URL.
- Replicant is filed under an **engineering/IT** category, not marketing — excluded by both URLs' category filter.
- ClearView is **in-office**, three non-SF-primary cities, and a **consulting** category — excluded by both.

This is a structural ceiling, not a bug: the two URLs do exactly what they were built to do, they just cover a narrower slice than your actual BuiltIn account does.

### 2. The cross-company LinkedIn search caps at 40 results per phrase, ranked by LinkedIn's relevance sort
`src/careerops/sources/boards.py`: each of the 9 "AI enablement"-family search
phrases pages through LinkedIn's public job search **4 pages × 10 results = 40
hits, hard stop** (`MAX_PAGES = 4`, `PAGE_SIZE = 10`). The scan log for run 14
shows exactly 40 hits for query after query — that's the cap firing, not "40 is
all there was." Results are ordered by LinkedIn's own relevance ranking, not
date or fit, so a real match can simply rank 41st and never be seen.

### 3. Even a found lead can be dropped by the per-run "new employer" budget
When a board search does surface an unknown company, resolving it to a live ATS
costs real HTTP traffic, so `pipeline.py` caps that work at **60 companies per
run** (`board_resolve_cap`, `config/profile.yml`). Run 14's log: *"boards: 831
leads, 186 from unknown companies... resolved 15/60 new employers... 95 over the
per-run cap, they will be picked up next run."*

Two things compound this:
- The 60-slot budget is spent in a **fixed order** — every LinkedIn-sourced lead
  from all 9 queries is queued before BuiltIn leads and Hacker News leads even
  get a turn, since `boards.discover()` appends LinkedIn results first, then
  BuiltIn, then HN. On a query set this size, LinkedIn alone can plausibly fill
  60 slots before BuiltIn companies are ever attempted.
- "Picked up next run" isn't actually tracked — there is no persisted backlog.
  A company skipped this run is only retried if it happens to appear again in a
  *future* board search, with no memory of the skip and no priority boost.

### 4. Your salary-gate instinct was directional but the mechanism you flagged isn't a double-filter
You asked whether salary is one of the filters that shouldn't apply twice.
Checked directly: compensation is used exactly once as a hard, independent gate
(`prefilter.py`: reject if a *stated* band tops out under $150k) — it only fires
when a range is actually published. When no range is listed, that gate never
runs and dimension 4 is scored `null`/neutral downstream, per the existing rule
that an unpublished range should never hurt a score. These don't stack against
the same posting. ALTEN's exclusion is this one gate working correctly, not a
double-penalty bug. No change indicated here.

## Proposed follow-ups, in priority order

1. **Point BuiltIn scraping at Doran's actual authenticated feed**, the way
   LinkedIn already uses his logged-in session, instead of two fixed
   category/work-model-filtered URLs. This directly closes the gap that caused
   3 of these 4 misses and is the single highest-leverage fix.
2. **Break the LinkedIn 40-per-query cap's blind spot** — either raise
   `MAX_PAGES`, or diversify beyond LinkedIn's relevance sort (e.g. add a
   date-sorted pass, `f_SB2` / sort-by-recency parameter) so a real match
   ranked 41st+ isn't structurally invisible.
3. **Persist the board-resolution backlog** so "95 over the per-run cap" is a
   real queue carried into the next run (with priority, not just re-discovery
   by luck) instead of a number printed and forgotten. This also implies giving
   BuiltIn/HN leads a fair turn against the resolve-cap rather than always
   queuing after all LinkedIn leads.
4. **De-anonymize aggregator reposts** (Jobgether and similar "posted on
   behalf of a partner" boards) by matching their description text against
   postings already resolved from named-company ATS feeds. Confirmed on
   Replicant: the anonymous Jobgether "AI Enablement Engineer" (scored 4.60,
   FLAG) and the real Replicant posting are the same content, word for word.
   Where a match is found, replace the FLAG-and-hide-the-employer treatment
   with the real company name and drop to PASS. Lower priority than 1-3 since
   the current FLAG behavior at least surfaces the role; this just improves
   labeling and trust.

None of the above resolved ALTEN's exclusion, because none should — that one is a
correct, working gate.
