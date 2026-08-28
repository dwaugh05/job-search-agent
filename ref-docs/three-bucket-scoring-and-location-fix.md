# Three-bucket scoring and the location parsing fix

**Status:** Agreed, not yet built. No code has been changed.
**Written:** 2026-08-28
**Owner:** Doran Waugh
**Audience:** A fresh Claude Code session picking this up cold.

---

## Read this first

This document is a handoff. It captures a conversation on 2026-08-28 where Doran
asked why PlayStation jobs had never appeared in any report, and what came out of
investigating that. Two separate things surfaced: a real bug that was silently
throwing away good roles, and a gap in how the system thinks about what Doran is
looking for.

**Do not start coding from the summary alone.** Read the acceptance criteria at
the bottom. They are the definition of done.

---

## Goal

Make the job search reflect how Doran actually thinks about his own candidacy:
**two distinct role archetypes, plus the overlap between them, each surfaced
separately, each with its own bar for getting in.**

In his words:

> "I think of your job search workflow as you looking at me for two different
> roles That I could fit into. If they were overlap then that's great, but each
> of them separately is also suitable for me too."

And:

> "Maybe a better way to think of this as a three sets of buckets where there's
> the traditional marketing role and then there's the AI role. And then there's a
> third bucket of where they overlap. And so I want to know about all three of
> these when you present the lists."

---

## Problem statement

Two problems, unrelated in cause, both ending in the same result: real roles never
reach Doran.

### Problem 1: A location parsing bug is silently deleting local jobs

Some employers write their location country-first. Sony Interactive Entertainment
writes `United States, San Mateo, CA` where most companies write
`San Mateo, CA, United States`.

The normalizer takes the first comma-separated chunk as the city. So the city is
recorded as **"United States"**. That is then looked up in `config/commute.yml`,
which is a hand-curated table of driving minutes from Doran's home in San Mateo.
"United States" is not a city, so the lookup returns nothing, and the posting is
rejected with the reason `unknown location 'United States' - add it to
config/commute.yml`.

**This is not a judgement about the job. It is a parsing failure.**

There is a partial safety net already in place. `geo_allowed()` in
`src/careerops/prefilter.py` falls back to scanning the raw location string for
any city name it recognises. Verified live behaviour:

| Raw location string | Result |
|---|---|
| `United States, San Mateo, CA` | **Passes.** Falls back and finds "San Mateo" (~5 min) |
| `United States, San Diego, CA` | **Rejected** as unknown location |
| `United States, Austin, TX` | **Rejected** as unknown location |
| `United States, Los Angeles, CA` | **Rejected** as unknown location |

The safety net only works when the real city happens to be listed in
`commute.yml`. San Mateo is listed. San Diego, Austin and Los Angeles are not,
because they are correctly out of commute range.

**Two things are still wrong even where the net catches it:**

1. The stored `city` field is literally the string "United States" for these
   postings. Anything downstream that reads the city, including the commute
   dimension in the rubric, is working from garbage.
2. For genuinely far cities the rejection reason is misleading. It says "unknown
   location" when the honest answer is "too far to commute". That makes the
   reject pile impossible to audit.

**The real fix belongs in the normalizer**, so the city is parsed correctly at the
point of ingestion, not patched over downstream.

### Problem 2: There is no overlap bucket and no sliding scale

The system already runs two searches. This part is built and working:

- `TRACK_AI` (`ai_enablement`), scored against `config/scoring.yml`
- `TRACK_GROWTH` (`growth_marketing`), scored against `config/scoring-growth.yml`

Defined in `src/careerops/config.py` lines 36 to 42. A posting survives the
prefilter if it clears **either** track, and which track(s) it qualified for is
recorded on the posting.

What is missing:

1. **No third category.** A posting can carry both track labels, but nothing
   treats "qualifies for both" as its own thing. There is no overlap bucket.
2. **No sliding scale.** Both `config/scoring.yml` and `config/scoring-growth.yml`
   set `pass_threshold: 4.0`. Identical bars. Doran wants three different bars.
3. **The report does not label the bucket.** Doran cannot tell which list a match
   came from.

---

## What Doran wants, in his own words

On the three buckets and the leniency scale:

> "It's just that you should probably be more lenient in the scoring to let more
> stuff slip in to the cut line if it's in that bucket where it's AI plus
> marketing merged together. And then be slightly less lenient when it's only AI.
> And then don't really be too lenient at all in scoring when it's just pure
> traditional marketing, So that it's kind of a sliding scale on these three
> buckets for the role types I'm looking for."

On the size of that scale, after a first draft overstated it:

> "the 'How hard to get in' Would probably be more like: normal, A little bit
> lenient, A bit more lenient. like a scale of 0, +1, +2."

On why pure marketing roles must still be shown and not silently dropped:

> "I'm less interested in a pure traditional marketing role, However, that doesn't
> mean I don't want it presented to me if it's a strong fit from the scoring."

> "You're searching for roles where I'm a great fit in the AI enablement or
> strategy or builder capacity. And then the second role is really more about my
> traditional marketing capacity and skill set, which both of these fall into. So
> for that reason they should be scored and presented to me and not killed."

On the two specific PlayStation roles that triggered this:

> "postings number two and three are things that don't fit the AI half of what I'm
> looking for, but do fit the marketing area of my skill set."

---

## The agreed model

| Bucket | What it is | Leniency |
|---|---|---|
| **Marketing only** | Traditional growth, brand, product marketing. No AI mandate. | **0.** Normal bar, no help. |
| **AI only** | AI enablement, strategy, or builder capacity. | **+1.** A little lenient. |
| **AI + marketing overlap** | Needs both. Doran's sweet spot. | **+2.** A bit more lenient. |

All three appear in every report, clearly labelled, so Doran can see at a glance
which archetype a match came from.

**Open question, unresolved:** what "+1" and "+2" mean numerically. On the 1.0 to
5.0 scale the rubric uses, a literal +1.0 would be enormous, roughly the same size
as the connection bump for knowing someone at the company. The reading Doran
confirmed is a *nudge, not a shove*. Do not ask Doran for a number. Pick a
conservative size, then prove it with the calibration test before trusting it.

---

## Evidence: the PlayStation case

This is what prompted the whole thing. It is the best available test case.

**The net is working. The gates are the problem.**

- Sony Interactive Entertainment is configured live in `config/sources.yml`
  (around line 728): Greenhouse, slug `sonyinteractiveentertainmentglobal`.
- **241 Sony postings are in `data/jobs.db` right now.**
- **All 241 are in state `rejected_prefilter`.**
- **0 have ever been scored. 0 have ever been presented.**

The rubric has literally never looked at a PlayStation job. This was never a
scoring problem.

Rejection breakdown:

| Cause | Count | Verdict |
|---|---|---|
| Published outside the freshness window | Majority | Stale data, see below |
| `unknown location 'United States'` | 24 | **The bug.** All recent, most 5 min from home |
| Located outside the US (UK, Canada, Australia, Ireland, NL, Brazil) | ~25 | Correct rejection |
| Title out of domain (software engineering, IT support) | ~25 | Correct rejection |
| No track match | 4 | Correct rejection |
| Salary below floor | 1 | Correct rejection |

### The freshness rejections are stale data, not a bug

`config/profile.yml` line 72 sets `freshness_days: 60`. It was widened from 30 to
60 on 2026-08-25.

**But no broad scan has run since that change.** The last broad scan was run 14 at
`2026-08-25T16:11`. Every Sony freshness rejection is recorded as `published N
days ago (window 30)`, meaning it was gated under the old rule. Runs 19 through 23
on 2026-08-28 were `ingest` mode with 11 postings each, not broad scans.

So a meaningful number of the freshness rejections would survive today. They just
need the gates re-run.

### Five roles currently stuck in the reject pile

None of these have ever been scored. Rankings below are a human read, not rubric
output.

**1. Marketing Director, Brand Culture.** San Mateo hybrid, $212,000 to $318,000,
posted 2026-07-24. Killed by `published 32 days ago (window 30)`, two days over the
old limit. Reports to the SVP of Marketing, owns global youth culture strategy.
Strong on seniority, scope and comp. No AI component at all. Pure
**marketing-only** bucket.
https://job-boards.greenhouse.io/sonyinteractiveentertainmentglobal/jobs/6113807004

**2. Contract Senior Organic Growth Specialist.** San Mateo on-site, $155,209 to
$232,793, posted 2026-08-17. **Killed by the location bug.** Owns organic
discoverability across "Search and AI-powered experiences", pairing classic SEO
with Generative Engine Optimisation, meaning getting PlayStation to surface inside
AI Overviews and LLM answer engines. Works across Editorial, Product Marketing,
Analytics, MarTech and Engineering. This is the closest thing PlayStation has to
the **overlap** bucket. Caveats: it is a contract role, and the title says
"Specialist" while the mandate is a staff-level owner.
https://job-boards.greenhouse.io/sonyinteractiveentertainmentglobal/jobs/6136862004

**3. Brand Manager, Games Marketing.** San Mateo or LA hybrid, west coast remote
considered, $165,100 to $247,700, posted 2026-08-19. **Killed by the location
bug.** Global go-to-market for PlayStation Studios exclusive titles. Reports into a
Senior Staff Manager, so it sits a level below the Senior Staff Brand Manager
version of the same role. **Marketing-only** bucket.
https://job-boards.greenhouse.io/sonyinteractiveentertainmentglobal/jobs/6145343004

**4. Commercial Manager, D2C Change and Go-To-Market.** San Mateo hybrid, $131,400
to $197,200, posted 2026-08-05. **Killed by the location bug.** Owns end-to-end GTM
lifecycle for PlayStation's direct-to-consumer e-commerce. Heavily analytical,
partners with Product, Engineering, Data Science and MarTech. **Marketing-only**
bucket, comp band tops out below the others.
https://job-boards.greenhouse.io/sonyinteractiveentertainmentglobal/jobs/6122462004

**5. Product Marketing Manager, Platform Audience Planning.** San Mateo hybrid,
$138,200 to $207,400, posted 2026-06-26. Killed by freshness at 60 days. Connects
self-reported consumer research with first-party behavioural data. Weakest of the
five: "support" appears repeatedly in the responsibilities and it reports into a
Director, so real authority is lower than the title suggests. May also be a ghost
posting at this age.
https://job-boards.greenhouse.io/sonyinteractiveentertainmentglobal/jobs/6102750004

**Note for whoever picks this up:** roles 2 and 3 are the ones Doran specifically
pointed at as "should be scored and presented to me and not killed". Neither of
them died on track logic or scoring. Both died on the location bug, several steps
earlier. **Fixing the buckets alone would not have saved them.** The two work items
are independent and both are needed.

---

## Correction on the record

An earlier claim in this conversation was wrong and should not be repeated.

**Claim made:** the marketing track has a title ceiling that might block the
Marketing Director, Brand Culture role.

**Reality:** it does not. The `growth_marketing` reject list in
`config/profile.yml` under `track_overrides` blocks vp, vice president, svp, senior
vice president, evp, chief, cmo, cto, ceo, coo, cro, president, board member, "head
of", and "head,". **Director is not on that list and is allowed.**

That role died on the freshness window, at 32 days against a 30 day limit. Nothing
to do with its title.

The "head of" and "head," entries are the only additions the marketing track makes
over the global reject list. There is a note in `config/profile.yml` saying those
two can be deleted if Doran wants "Head of Growth" titles back, which at small
startups are sometimes Director-scoped. **That has not been asked for and is not
part of this work.**

---

## Work items

Do these in order. Item 1 is independent of items 2 and 3.

### 1. Fix the location parsing bug

Parse country-first location strings correctly at normalization time, so `United
States, San Mateo, CA` yields city "San Mateo", not "United States".

Must hold true afterwards:

- The stored `city` field is a real city, never a country name.
- Postings genuinely too far to commute are rejected with a distance reason, not
  "unknown location".
- The existing raw-string fallback in `geo_allowed()` still works as a backstop and
  is not relied on as the primary path.

### 2. Add the third bucket and the sliding scale

- Introduce an overlap category for postings qualifying for both tracks.
- Give each bucket its own pass bar, following 0 / +1 / +2 as described above.
- Keep the change small enough that it is a nudge, not a shove.

### 3. Label the buckets in the report

Every presented match states which bucket it came from: marketing only, AI only, or
overlap. Doran should never have to guess.

### 4. Re-run the gates over the existing reject pile

The 60 day freshness window has never actually been applied to a broad scan. Once
items 1 through 3 are in, the existing rejects need re-gating so the backlog
benefits from all of it.

---

## Acceptance criteria

This work is done when every one of these is true and has been demonstrated, not
assumed.

**Location fix**

- [ ] A posting with location `United States, San Mateo, CA` stores city "San
      Mateo" and passes the geo gate on the primary path, not the fallback.
- [ ] A posting with location `United States, San Diego, CA` stores city "San
      Diego" and is rejected for **distance**, with the minutes named, not for
      "unknown location".
- [ ] Zero postings in `data/jobs.db` are rejected with the reason `unknown
      location 'United States'`.
- [ ] No posting in the database has a country name stored in its `city` field.

**Three buckets**

- [ ] Every posting that clears the prefilter is classified into exactly one of
      three buckets: marketing only, AI only, or overlap.
- [ ] The three buckets have three different pass bars, ordered so that overlap is
      easiest to clear, AI only is next, and marketing only is hardest.
- [ ] A posting qualifying for both tracks is identifiable as overlap in the
      database, not just as two labels in a list.

**Report**

- [ ] `python cli.py report` shows the bucket for every match.
- [ ] Matches are grouped or otherwise separated by bucket so all three lists are
      visible in one pass.

**Calibration, the non-negotiable gate**

- [ ] `/calibrate` passes. Every anchor in `config/scoring.yml` under
      `calibration_anchors` stays inside its expected band. The anchors and their
      bands are listed in `CLAUDE.md`.
- [ ] Specifically, the floor anchor still behaves as a floor: **Harvey Marketing
      Engineer, expected 4.0 to 4.4, must still barely pass.** If the new leniency
      pushes it comfortably clear, the nudge is too big.
- [ ] Specifically, the hard fail still hard fails: **JPMorgan Chase VP role,
      expected 1.0 to 3.0.** No bucket leniency may rescue it.
- [ ] The applied-jobs regression still passes. Nothing Doran has actually applied
      to may become invisible.

**The PlayStation proof**

- [ ] After a fresh broad scan, Sony Interactive Entertainment postings reach the
      scoring stage. The count of Sony postings with an evaluation is greater than
      zero, where today it is exactly zero.
- [ ] Contract Senior Organic Growth Specialist and Brand Manager, Games Marketing
      both survive the prefilter and get scored. Whether they then score above the
      cut line is a legitimate judgement call and either outcome is acceptable.
      **Being killed before scoring is not.**

**Honesty check**

- [ ] Report to Doran what actually happened, including anything that did not work.
      If an anchor drifted, say so with the numbers. Do not claim done until the
      calibration output has been run and read.

---

## Things a fresh session should not do

- **Do not widen the buckets by loosening the hard gates.** Salary floor, US-only,
  commute limit and killer terms are deliberate. The leniency scale applies to
  scoring, not to the mechanical gates.
- **Do not remove the "head of" entries** from the marketing track reject list. Not
  asked for, not in scope.
- **Do not ask Doran for a number.** Scores are an internal mechanism. If
  calibration is off, ask what was wrong with the judgement in plain words and
  translate it. See `ref-docs/calibration-phrasebook.md`.
- **Do not skip `/calibrate`.** A rubric change that has not been calibration tested
  is not finished, it is just untested.

---

## Reference

Relevant files, for orientation only. Verify they still look like this before
relying on any line number.

| File | What it holds |
|---|---|
| `src/careerops/normalize.py` | Where location parsing happens. Home of bug 1. |
| `src/careerops/prefilter.py` | `geo_allowed()`, track assignment, relevance floors |
| `src/careerops/config.py` | `TRACK_AI`, `TRACK_GROWTH`, rubric file mapping |
| `config/profile.yml` | Hard gates, `freshness_days`, `track_overrides` |
| `config/scoring.yml` | AI track rubric, `pass_threshold`, calibration anchors |
| `config/scoring-growth.yml` | Marketing track rubric, `pass_threshold` |
| `config/commute.yml` | Hand-curated drive times from San Mateo 94403 |
| `config/sources.yml` | Watched companies, including Sony around line 728 |
| `.claude/README.md` | Full command reference. Read before running anything. |
