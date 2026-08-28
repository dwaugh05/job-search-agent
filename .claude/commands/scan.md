---
description: Sweep all watched companies for live postings from the last 60 days, score them A-G, and report matches in three buckets - AI+marketing, AI enablement, and marketing - each with its own bar
---

Run a broad job scan. Follow these steps exactly.

## 1. Discover

```
python cli.py scan
```

This sweeps every live, watched company in `config/sources.yml`, applies the
deterministic gates (60-day freshness, fingerprint suppression, geography, title
band, comp floor, content relevance, killer terms), confirms each survivor's apply
URL is live, and writes an evaluation queue.

Report the funnel counts to Doran. If nothing cleared the prefilter, say so plainly
and stop — do not lower the bar to produce results.

## 2. Optionally sweep the browser boards

If Doran asked for wider coverage, use the `claude-in-chrome` MCP to check the boards
listed under `browser_boards` in `config/sources.yml` (Built In SF, Built In Remote,
LinkedIn via his logged-in session). Extract postings to JSON with fields
`company, title, url, location, description, salary, published_at`, then:

```
python cli.py ingest --file <path>.json
python cli.py prefilter-pending
```

Never use a cached search API. Open the real page.

## 3. Evaluate

Read `data/runs/<run_id>/queue.md`. Before scoring, load:

- `rubric/rubric-A-G.md`
- `rubric/learned-rules.md`
- `ref-docs/voice-and-proof-points.md`
- `ref-docs/master-cv.md`

Score every queued posting across all 10 dimensions plus Block G. **Every block score
above 3.0 needs a quoted line from the posting in `block_notes`** — anything else gets
capped automatically.

Write `data/runs/<run_id>/scores.json` (a template is generated alongside the queue),
then:

```
python cli.py record-eval --run <run_id> --file data/runs/<run_id>/scores.json
```

**Do not add `--track`.** `scores.template.json` now carries a `track` per
posting, derived from its bucket, and `record-eval` resolves the rubric per item.
That matters: a marketing-only role judged against `scoring.yml` cannot clear the
bar, because dimension 1 (weight 22) makes AI enablement the hard requirement.
Before this was fixed every evaluation was filed as `ai_enablement` and the
marketing list was empty for the system's whole history. Keep the `track` values
the template generated.

## 3b. Resolve San Francisco offices — last step, finalists only

Do this **after** scoring and **only** for postings that both clear their
bucket's bar and
resolve to San Francisco. That is typically two or three per run, so it costs
almost nothing; running it during discovery would mean thousands of lookups and
is never correct.

SF is the one destination Doran takes the train to: 40 minutes door to the
Caltrain exit at 4th & King, leaving 10–20 minutes of last-mile budget inside his
60-minute ceiling. A SoMa office and a Marina office are a full scoring band
apart, and the flat `San Francisco: 55` fallback cannot tell them apart.

For each SF finalist, look for a neighborhood or street address in the posting
body first. Only if the body is silent, open the company's careers or contact
page with the `claude-in-chrome` MCP. Then re-score dimension 5 against the
neighborhood entry in `config/commute.yml` (SoMa 45, Financial District 52,
Mission 55, Marina 60, Richmond 66, and so on).

If no neighborhood can be established, keep the 55 fallback and say so in the Fit
Summary rather than guessing — guessing low flatters the role, guessing high
hides it.

## 3c. Settle the close calls — optional, and bounded

```
python cli.py tiebreak --run <run_id>
```

This writes `data/runs/<run_id>/tiebreak.md`: every posting whose score landed
within **0.20** of the bar for its own bucket, with the **full** posting body
attached. It changes nothing on its own.

Read those bodies — the whole body, not the fit summary you just wrote and not
the block notes — and ask one question: does the score read right against what
this job actually is? Agiloft's "Director, Global Campaigns" is why this step
exists. It was scored 3.0 on dimension 1 from a truncated excerpt, and Doran had
to correct it from the posting himself.

Then answer in `tiebreak.json` and apply:

```
python cli.py record-tiebreak --file data/runs/<run_id>/tiebreak.json
```

The licence is narrow on purpose and `record-tiebreak` enforces it rather than
trusting you: at most **±0.15** per posting, **two verbatim quotes** of 25+
characters checked against the stored body, **30 postings per run**. A nudge can
carry a posting across the bar; it can never overturn a score. Leaving every
posting alone is a valid and common answer — an adjustment with no quotable
reason is exactly what this must not become.

## 4. Report

```
python cli.py report --run <run_id>
```

Print the output exactly as rendered. Eight fields per posting — **Company**, Job
Title, Link, City, Salary Range, Work Model, **Posted date**, Fit Summary — plus
the "Worth knowing about" tier beneath. Postings are marked as presented at this point and
will never appear in a future scan.

**Estimated Commute is an eighth field, and it appears on hybrid and on-site
postings only.** `cli.py report` adds it automatically from `config/commute.yml`,
so it is already in the rendered output — do not strip it and do not add it by
hand to a remote role. Doran asked for this on 2026-08-15: "Hybrid" or "On-site"
on its own is not actionable, because San Carlos and San Francisco are both a
word until one of them is 14 minutes and the other is 55. If a city is missing
from `commute.yml` the line says so rather than guessing; add the city to the
file and re-run rather than estimating in prose.

**The report is also archived verbatim.** `cli.py report` writes the exact
printed output to `data/reports/results-YYYY-MM-DD_HHMM.md` and prints the path.
This is not optional and not a substitute for showing him the report — Doran
asked on 2026-08-15 for it in **both** places, the session and the file, because
the session scrolls away and the report is the thing he re-reads. Two rules:

- **Show him the full report in the session as well.** The file is an archive,
  not a hand-off. Never reply with just a path.
- **Never hand-write the markdown file.** It comes out of `cli.py report`, so the
  file and what he read cannot drift apart. If you need to regenerate it for a
  run whose postings were already marked as presented, reset them first rather
  than re-typing the report:

  ```
  python cli.py report --run <run_id>        # normal path, writes the archive
  ```

Give him the archive path when you present the results.

Then tell Doran he can respond with `/feedback` to rule on what he just saw.

## Fit Summary style — this is the part he cares most about

**This summary replaces the posting.** Doran, 2026-08-28: *"the ultimate goal in
writing this summary is really so that I don't need to read the entire job
posting."* If he has to open the link to learn what the job is, it failed.

**The format is checked.** `record-eval` prints a `FIT SUMMARY` warning for any
summary that misses these, and a warning means rewrite it before you report:

- **Exactly 2 paragraphs.**
- **At least 2 verbatim quotes** from the posting — these are the evidence.
- **6 sentences maximum**, both paragraphs combined.
- **320 characters minimum.**

Doran confirmed this format works, so do not drift from it. Two paragraphs:

1. **What the role is, and what maps to him.** Plain terms first, then *named*
   proof points — the 50-marketer listening tour, the 200-person upskilling
   programme, the Contentful MCP, the reusable-agent repo, the ROI-weighted QBR
   tracker. Quote the posting where a phrase carries real weight.
2. **What to weigh against it.** Commute in minutes and days per week, where the
   compensation top-end lands, seniority band, coding bar, distance from
   marketing. Plainly, no hedging. State the commute in minutes here too on any
   hybrid or on-site role — the Estimated Commute field gives him the number, and
   this paragraph tells him what it costs him.

Write to him in the second person. Full guidance in `rubric/rubric-A-G.md`.

## Rules

- **Three buckets, three bars.** `cli.py report` routes every posting into
  exactly one of them and applies the right bar automatically, so do not filter
  by hand and do not assume 4.0:

  | Bucket | Bar | What it is |
  | --- | --- | --- |
  | AI + marketing overlap | **3.75** | Doran's sweet spot, most lenient |
  | AI enablement only | **3.85** | AI strategy, enablement or builder |
  | Marketing only | **4.00** | Traditional growth and web, normal bar |

  The bars live in `config/profile.yml` under `review.bucket_thresholds`. The
  leniency is a presentation bar, never a score bonus, which is why no anchor
  moves when it changes.
- Never pad a list. The bucket bar is the bar.
- Anything within 0.30 of its bucket's bar appears only as a capped one-line mention under "Worth
  knowing about" — never a full write-up, never mixed into the matches. He asked
  not to have near-misses hidden, not to have the bar lowered.
- Never build, suggest, or run anything that submits an application.
- If a posting carries a Block G FLAG, the warning line stays in the output.
