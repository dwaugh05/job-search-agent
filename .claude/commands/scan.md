---
description: Sweep all watched companies for live postings from the last 30 days, score them A-G, and report matches scoring 4.0+
---

Run a broad job scan. Follow these steps exactly.

## 1. Discover

```
python cli.py scan
```

This sweeps every live, watched company in `config/sources.yml`, applies the
deterministic gates (14-day freshness, fingerprint suppression, geography, title
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

## 3b. Resolve San Francisco offices — last step, finalists only

Do this **after** scoring and **only** for postings that both clear 4.0 and
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

## 4. Report

```
python cli.py report --run <run_id>
```

Print the output exactly as rendered. Seven fields per posting — Job Title, Link,
City, Salary Range, Work Model, **Posted date**, Fit Summary — plus the "Worth
knowing about" tier beneath. Postings are marked as presented at this point and
will never appear in a future scan.

Then tell Doran he can respond with `/feedback` to rule on what he just saw.

## Fit Summary style — this is the part he cares most about

Doran confirmed this format works, so do not drift from it. Two paragraphs:

1. **What the role is, and what maps to him.** Plain terms first, then *named*
   proof points — the 50-marketer listening tour, the 200-person upskilling
   programme, the Contentful MCP, the reusable-agent repo, the ROI-weighted QBR
   tracker. Quote the posting where a phrase carries real weight.
2. **What to weigh against it.** Commute in minutes and days per week, where the
   compensation top-end lands, seniority band, coding bar, distance from
   marketing. Plainly, no hedging.

Write to him in the second person. Full guidance in `rubric/rubric-A-G.md`.

## Rules

- Present only postings scoring 4.0 or higher as matches. Never pad the list.
- Anything scoring 3.7–4.0 appears only as a capped one-line mention under "Worth
  knowing about" — never a full write-up, never mixed into the matches. He asked
  not to have near-misses hidden, not to have the bar lowered.
- Never build, suggest, or run anything that submits an application.
- If a posting carries a Block G FLAG, the warning line stays in the output.
