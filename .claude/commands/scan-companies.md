---
description: Scan specific companies by name for matching roles, using the same scoring pipeline as a broad scan
argument-hint: "Anthropic, Figma, Notion, Ramp"
---

Scan the companies Doran named: **$ARGUMENTS**

This is the same pipeline as `/scan` with a different candidate set. Scoring,
suppression, and liveness are identical — only the input differs.

## 1. Resolve and discover

```
python cli.py scan --companies "$ARGUMENTS"
```

For each name this resolves the company to a live ATS board by probing the real APIs
with slug variants, caching the answer back into `config/sources.yml` so it is only
ever resolved once. Slugs are genuinely unguessable — DoorDash is `doordashusa` on
Greenhouse — so never hand-edit one.

Two behavioural differences from a broad scan, both deliberate:

- **No freshness window by default.** When Doran names specific companies he wants to
  know what is open there now, and a freshness filter would usually return nothing.
  Add `--fresh` if he asks for recent postings only.
- **Suppression and liveness still apply.** He still never sees a repeat, and never
  sees a dead posting.

If a company fails to resolve, report it and offer to find its careers page with the
`claude-in-chrome` MCP — some employers use custom portals rather than a standard ATS.

Add `--watch` if Doran wants these companies included in future broad sweeps.

## 2. Evaluate

Read `data/runs/<run_id>/queue.md`. Load `rubric/rubric-A-G.md`,
`rubric/learned-rules.md`, `ref-docs/voice-and-proof-points.md`, and
`ref-docs/master-cv.md` first.

Score all 10 dimensions plus Block G, with a quoted line of evidence per block. Write
`data/runs/<run_id>/scores.json` and apply it:

```
python cli.py record-eval --run <run_id> --file data/runs/<run_id>/scores.json
```

## 2b. Resolve San Francisco offices — last step, finalists only

Same rule as a broad scan. **After** scoring, and **only** for postings that
clear 4.0 and resolve to San Francisco, find the neighborhood or street address
in the posting body (or, failing that, the company's careers page via the
`claude-in-chrome` MCP) and re-score dimension 5 against the neighborhood entries
in `config/commute.yml`. Doran trains to SF — 40 minutes to the 4th & King exit
plus last-mile — so SoMa (45) and the Marina (60) are a full band apart. Keep the
flat `San Francisco: 55` fallback when the neighborhood cannot be established,
and say so rather than guessing.

## 3. Report, including near misses

```
python cli.py report --run <run_id> --companies "$ARGUMENTS"
```

Print the eight-field list for anything scoring 4.0+ — including the **posted
date**, which he asked for specifically.

Two things `cli.py report` now does for you, both added on Doran's instruction on
2026-08-15. Do not strip either, and do not reproduce either by hand:

- **Estimated Commute**, an eighth field on hybrid and on-site postings only,
  taken from `config/commute.yml`. A work model without a number is not
  actionable to him. Remote roles do not get the line.
- **A verbatim archive** at `data/reports/results-YYYY-MM-DD_HHMM.md`, with the
  path printed at the end of the run. He wants the results in **both** places —
  the session and the file — so still print the full report here, and give him
  the path alongside it. Never reply with just the path, and never hand-write the
  file.

Then the "Worth knowing about" tier (3.7–4.0), then the near-miss lines. The
near-miss section is unique to targeted scans: if a company Doran named has nothing
above 4.0, he gets one line saying what was there and why it fell short. Knowing a
company is dry is useful; silence is not. Never promote either tier into the match
list.

## Fit Summary style

Two paragraphs — what the role is and the named proof points it maps to, then what
to weigh against it (commute, comp top-end, seniority, coding bar, distance from
marketing). Second person, no hedging, quote the posting where it earns its place.
Full guidance in `rubric/rubric-A-G.md`.

## Rules

- Only 4.0+ postings appear as matches, exactly as in a broad scan.
- Never build, suggest, or run anything that submits an application.
