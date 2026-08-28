# Career-Ops — Command Reference

The operating manual for this repo. **Read this before running anything.** It is
the single place that says what each command does, what it changes, and which
step comes next.

Two layers:

- **Slash commands** (`.claude/commands/*.md`) — the workflows Doran invokes.
  Each one orchestrates several CLI calls plus the semantic scoring that only
  Claude can do.
- **`cli.py` subcommands** — the deterministic machinery. Python fetches,
  normalizes, gates, persists and renders. It never judges fit.

A slash command is the front door. Reach for a raw CLI subcommand only when you
are repairing state, debugging, or a workflow explicitly tells you to.

---

## Slash commands

| Command | What it does |
| --- | --- |
| `/scan` | Broad sweep of every live, watched company in `config/sources.yml`. Runs discovery → prefilter → A-G scoring → report. Presents only 4.0+; 3.7–4.0 gets a capped one-liner under "Worth knowing about". |
| `/scan-companies "Anthropic, Figma"` | Same pipeline, different candidate set — only the companies named. Skips the freshness window by default, and adds near-miss lines for any named company that came up dry. |
| `/feedback` | Takes two independent kinds of feedback: application intent (`verdict`) and scoring quality (`add-rule`). Explains itself and displays the ten-lever phrasebook on every run. Never asks Doran for a numeric score. |
| `/shortlist` | Read-only. The interested/saved/applied pipeline, plus anything still awaiting a verdict, plus a DB health check. |
| `/calibrate` | Two regression tests. Re-scores the anchor postings blind and checks each lands in its band, **and** confirms every job Doran has applied to still gets through the gates and still clears 4.0. Run after any change to the rubric, the weights, the gates, or `config/profile.yml`. |

---

## CLI subcommands

### Setup and sources

| Command | What it does |
| --- | --- |
| `python cli.py init` | Creates the SQLite database at `data/jobs.db`. Idempotent — every other command calls it implicitly where it matters. |
| `python cli.py verify-sources` | Probes every company in `config/sources.yml`, marks each `live`/`dead`, resolves unknown slugs, writes the file back. Exits **non-zero if under 70% live**. |
| `python cli.py resolve-company "DoorDash"` | Finds a company's live ATS board. Tries three routes in cost order: the local slug index, then ~45 blind slug probes, then reading the ATS link off the company's own careers page. Slugs are unguessable (DoorDash is `doordashusa`) — never hand-edit one. |
| `python cli.py sync-connections` | Resolves every company in `config/connections.yml` — the places Doran knows someone — and forces each into the broad sweep with `watch: true`. Run it after adding names to that file. Companies with no standard ATS (Meta, Apple) will report "NO BOARD"; they still get the score bump, they just cannot be swept directly. |
| `python cli.py refresh-tokens` | Rebuilds the local index of ~29,000 ATS board slugs that actually exist, from public Common Crawl datasets. Resolution consults it first, which is why it finds boards that guessing never could. Re-run every few months. |

Flags: `verify-sources --force` re-resolves even known slugs.
`resolve-company --save` caches into `sources.yml`, `--watch` also adds it to the
broad sweep, `--force` ignores the cache. `sync-connections --force` re-resolves
connection companies whose board is already known.

### Discovery

| Command | What it does |
| --- | --- |
| `python cli.py scan` | Discover **and** prefilter in one step, then write the evaluation queue to `data/runs/<run_id>/queue.md`. Prints the funnel counts. |
| `python cli.py queue` | Re-renders the evaluation queue from whatever currently sits in state `prefiltered`. Use it if the queue file was lost or clobbered. |
| `python cli.py ingest --file <json>` | Loads browser-scraped postings (Built In, LinkedIn, custom portals) through the same normalization as ATS feeds. Lands them in state `new`. |
| `python cli.py prefilter-pending` | Applies the deterministic gates to anything still in state `new`. This is the required follow-up to `ingest`. |

`scan` flags:

| Flag | Effect |
| --- | --- |
| `--companies "A,B,C"` | Switches to targeted mode (the `/scan-companies` path). |
| `--fresh` | Targeted mode only: re-applies the freshness window, which targeted mode drops by default. |
| `--all-open` | Broad mode only: ignores the freshness window entirely. |
| `--days N` | Overrides the window. Default comes from `hard_gates.freshness_days` in `config/profile.yml` (currently **60**). |
| `--watch` | Targeted mode: also add these companies to future broad sweeps. |
| `--skip-liveness` | Skips the apply-URL re-check. Debugging only — liveness is a hard rule. |
| `--no-boards` | Broad mode: skip role-first board discovery, sweep companies only. |

`ingest` expects a JSON list (or `{"postings": [...]}`) with at least
`company, title, url, description`. Optional: `location, salary, published_at,
apply_url, work_model, is_remote, source, board, id`.

Four things `scan` does that the funnel counts name but do not explain
(all added 2026-08-25):

- **The resolve backlog is real now.** Turning an unknown employer into a live
  ATS costs ~45 probes, so a run only does 60 of them. Everything past that used
  to be dropped while the log claimed it would be "picked up next run" — nothing
  remembered it. Over-cap employers are now saved to a `resolve_backlog` table,
  drained oldest-first at the start of the next run, **and** read from the
  board's own page in the same run so a real match is not lost to a budget
  ceiling. A company that fails to resolve goes to the back of the queue rather
  than to the front forever.
- **`duplicate_reposts_collapsed`** counts per-country clones. Reseller boards
  list one role once per country, identical but for the country name, and each
  copy used to cost a full Claude read — 42 of 140 queue slots in run 14. The
  collapse runs *after* the gates, so the US copy survives and the Dubai copy is
  the one dropped.
- **A dead ATS host is now stated.** If a provider times out repeatedly it is
  abandoned for the rest of the run; previously every company on it reported
  "feed returned nothing", which reads identically to an employer with no
  openings. The run now prints a WARNING naming the host.
- **LinkedIn throttling is no longer read as "no more results".** LinkedIn
  answers 200 with an empty body when you go too fast, which the old paging
  treated as the end of the result set — so queries ended early and silently.
  Pages are retried with backoff, and the whole LinkedIn channel gives up after
  repeated throttling rather than pushing on toward a block.

### Scoring and reporting

| Command | What it does |
| --- | --- |
| `python cli.py record-eval --file scores.json` | Writes A-G dimension scores back to SQLite. Applies the evidence cap, redistributes weight for null dimensions, applies scope/bonus modifiers, adds the connection bump, clamps to 5.0, then stores the weighted score. |
| `python cli.py tiebreak --run N` | Writes a worksheet of close calls — postings within 0.20 of the bar for their own bucket — with the **full** posting body attached. Read-only; changes nothing. |
| `python cli.py record-tiebreak --file tiebreak.json` | Applies holistic nudges, refusing every one that breaks the licence below. |
| `python cli.py report` | Renders the eight-field match list (Company first), the growth-marketing backup list, and the "Worth knowing about" tier. Adds an **Estimated Commute** line to hybrid and on-site postings, and archives the printed output verbatim to `data/reports/results-YYYY-MM-DD_HHMM.md`. |

`record-eval` flags: `--run N` tags the evaluations to a run,
`--track ai_enablement|growth_marketing` picks which list the scores belong to
(default `ai_enablement`).

Five behaviours in `record-eval` that are easy to trip over:

- **Connection bump.** A posting from a company in `config/connections.yml` —
  where Doran knows someone — gets a flat **+1.0**, stored separately in
  `evaluations.connection_bonus` so it is never confused with a scope
  adjustment. Matched on the resolved `(ats, slug)` first, then the normalized
  company name and any `aliases`. The report prints a `Connection:` line so the
  reason for the ranking is visible.
- **Hard 5.0 ceiling.** The final score is clamped to `max_score` in
  `connections.yml`. Before this existed a scope bonus could record 5.15 — the
  calibration anchors already asserted 5.0 as the top, so nothing else changes.
  Calibration is unaffected either way: it scores anchor documents through
  `data/calibration-scores.json`, never through this command.

- **Evidence cap.** A dimension in a gated block (A, B, C, F) scored above 3.0
  with no quoted string in `block_notes` is silently clamped to 3.0. This is the
  main brake on score inflation — quote the posting.
- **Null means unscored.** A dimension explicitly set to `null` is dropped from
  the denominator, not scored as zero. That is how an unpublished salary range is
  handled without it becoming a hidden penalty.
- **Missing dimensions skip the posting.** Every dimension must be present as a
  number or an explicit `null`, or the whole evaluation is dropped with a warning.

### The tiebreaker — when it runs, and what it may do

Doran's idea, 2026-08-28: a safety net that "reads the posting itself to
understand what it's about and then decides things that are close call,
tiebreaker type things", with "the if-then scenario of where and when to use the
agent" fixed in advance. This is that if-then. It is enforced in
`src/careerops/tiebreak.py`, not trusted to a prompt, because the rules in this
repo that stuck are the mechanical ones.

**When it runs.** Between `record-eval` and `report`, and only then. It is
optional — skipping it is always valid, and most runs will not need it.

**Who is eligible.** A posting whose *rubric* score lands within **0.20** of the
bar for its own bucket. Nothing outside that window can be nudged, and a posting
already carrying a nudge is re-judged on its rubric score, so nudges cannot
compound across runs.

**What a nudge may do.** At most **±0.15**, deliberately smaller than the 0.20
band: a tiebreaker may move a posting across the bar, but can never move one
from clearly-in to clearly-out or the reverse. It leans; it does not decide.

**What it must show.** Two verbatim quotes of 25+ characters from the posting
body, matched against the stored description character by character (whitespace
normalized, so re-wrapping is fine). A judgement that cannot be quoted is the
unfalsifiable "vibe" this whole design exists to prevent.

**How much.** 30 postings per run, maximum. `--limit` can only tighten that.

**Where it shows up.** In `evaluations.tiebreak_adjustment` / `tiebreak_note` /
`tiebreak_quotes`, never smeared into the rubric score, so it can be read back
and unwound. The report prints a `Tiebreak:` line, `calibrate --check` lists
every nudge in force, and the applied-job regression check deliberately reads
the score with the nudge *removed* — otherwise a nudge could hide the rubric
drift that check exists to catch.

```
python cli.py tiebreak --run <run_id>       # worksheet + template, changes nothing
# read data/runs/<run_id>/tiebreak.md, answer in tiebreak.json
python cli.py record-tiebreak --file data/runs/<run_id>/tiebreak.json
```

`report` flags: `--threshold N` overrides the 4.0 bar, `--companies "A,B"` adds
near-miss lines for those companies, `--run N` tags the written report file,
`--no-mark` previews **without** marking postings as presented.

> **`report` is destructive to the candidate pool.** Everything it prints across
> both lists is marked presented and will never appear in a future scan again.
> Use `--no-mark` for a dry run.

Two things `report` does that were added on 2026-08-15 at Doran's request:

- **Estimated Commute**, an eighth field, on hybrid and on-site postings only.
  Pulled from `config/commute.yml` via `report.commute_field()`. A city missing
  from that file prints "unknown … not in config/commute.yml" rather than a
  guess — add the city and re-run. Remote postings get no line.
- **Verbatim archive.** The exact printed output is written to
  `data/reports/results-YYYY-MM-DD_HHMM.md` and the path is printed. Doran wants
  results in both the session and a file he can go back to, so still show him the
  full report — the archive is not a hand-off. Never hand-write that file; if it
  and the session ever disagree, the process has failed.

To regenerate a report for postings already marked presented, reset them first —
`report` skips anything in state `presented`:

```
python -c "import sys; sys.path.insert(0,'src'); from careerops import store; \
  conn=store.connect(); ids=[r[0] for r in conn.execute( \
  'SELECT posting_id FROM presentations WHERE run_id=?', (RUN,)).fetchall()]; \
  [store.set_state(conn,i,'evaluated') for i in ids]; \
  conn.execute('DELETE FROM presentations WHERE run_id=?', (RUN,)); conn.commit()"
```

### Verdicts and learning

| Command | What it does |
| --- | --- |
| `python cli.py verdict --posting <id> --verdict <v> --reason "..."` | Records Doran's ruling. Verdicts: `interested`, `saved`, `not_interested`, `applied`. Capture his reasoning verbatim — the reason is the valuable part. `applied` also writes the archive file (below). `--date YYYY-MM-DD` for an application he made earlier. |
| `python cli.py pending` | Lists postings shown but never ruled on. They are suppressed from scans, so this is the only place they surface. |
| `python cli.py shortlist` | The interested/saved/applied pipeline with scores, links and notes. |
| `python cli.py applied` | Every role he applied to, newest first, each with the path to its saved write-up. |
| `python cli.py applied --backfill` | Rewrites the archive file for every applied posting. Use after adding a heading variant to `applications.py`. |
| `python cli.py status` | Database summary: totals, run count, learned rules, breakdown by state. |
| `python cli.py add-rule "<rule>" --dimension <n>` | Appends a durable learned rule to `rubric/learned-rules.md` and the DB. |
| `python cli.py calibrate` | Builds `data/calibration-queue.md` with all five anchors for blind scoring. |
| `python cli.py calibrate --check` | Verifies recorded anchor scores against their bands, **then** runs the applied-job regression check. |
| `python cli.py calibrate --applied-only` | Just the applied-job check: re-runs the deterministic gates over every job Doran applied to and confirms each still reaches scoring and still clears 4.0. Exits non-zero on a regression. Reach for this after touching a gate, `config/profile.yml`, or `src/careerops/prefilter.py` — the anchors are scored from documents and cannot catch those. |

Never mark a posting `applied` unless Doran says he applied.

**Accepted misses: `regression_exemptions` in `config/profile.yml`.** The applied-job
check exits non-zero so it can gate a change, which is only useful while a red line
still means something. A posting listed there is reported every run as `KNOWN`
rather than `BLOCKED`, with its reason printed underneath, and does not fail the
check. Two guardrails: an exemption is ignored unless the posting actually fails a
gate, so a stale entry can never silence a break that appears later; and the summary
says "21 of 22 clear the gates, and the other 1 is an accepted miss" rather than
claiming a clean sweep.

Add an entry only after the miss has been diagnosed and consciously accepted, never
to turn a red check green. The one entry as of 2026-08-28 is Google's "Program
Manager, AI and Gemini App Marketing": Google posted the same job at two levels, the
5-year req Doran applied to scores 34.0 because its description omits "agentic" and
"AI agent", and its 3-year twin scores 48.5 and passes — so a scan surfaces the role
through the other advert.

### The application archive

An `applied` verdict snapshots the posting to
`data/applications/<date>-<company>-<title>.md` and refreshes `INDEX.md`. Each
file holds the role overview, what the job asks him to do, and the requirements
— **verbatim**, never paraphrased — because postings get taken down and he
prepares for interviews weeks later from this file, not the dead link.

Postings almost never say "Responsibilities": the wording variants live in
`_OVERVIEW` / `_RESPONSIBILITIES` / `_REQUIREMENTS` in
`src/careerops/applications.py`. Every file records how it was captured on a
`Captured via:` line. If that line says `full-text fallback` or `no
responsibilities heading found`, add the posting's wording to the right list and
re-run `python cli.py applied --backfill`.

The snapshot is taken at verdict time on purpose — `upsert_posting` overwrites
`postings.description` on every rescan, so reading it back later is not safe.

---

## The canonical sequences

**Broad scan**

```
python cli.py scan
# read data/runs/<run_id>/queue.md, score it, write scores.json
python cli.py record-eval --run <run_id> --file data/runs/<run_id>/scores.json
python cli.py tiebreak --run <run_id>       # optional: close calls only, see above
python cli.py report --run <run_id>
```

**Targeted scan**

```
python cli.py scan --companies "Anthropic, Figma"
python cli.py record-eval --run <run_id> --file data/runs/<run_id>/scores.json
python cli.py tiebreak --run <run_id>       # optional: close calls only, see above
python cli.py report --run <run_id> --companies "Anthropic, Figma"
```

**Browser-sourced postings** (merges into the same pipeline)

```
python cli.py ingest --file scraped.json
python cli.py prefilter-pending
python cli.py queue
```

**After any rubric or weight change**

```
python cli.py calibrate          # then score the anchors blind
python cli.py calibrate --check  # anchors in band AND applied jobs still visible
```

---

## Before scoring anything, load these

Scoring without them produces drift, not judgement:

- `rubric/rubric-A-G.md` — the dimensions, anchors and Fit Summary guidance
- `rubric/learned-rules.md` — everything Doran's feedback has taught the system
- `ref-docs/voice-and-proof-points.md` — the named proof points a Fit Summary draws on
- `ref-docs/master-cv.md` — what he has actually done

And before asking Doran for any feedback on scoring quality:

- `ref-docs/calibration-phrasebook.md` — the ten levers in plain language, plus
  how to turn what he says into a rule. **Never ask him for a numeric score.**

---

## Gotchas

- **There is no `discover` and no `prefilter` command.** `scan` does both.
  The standalone gate command is `prefilter-pending`, and it only touches
  postings in state `new` (i.e. after `ingest`).
- **Suppression is permanent and content-based.** It fingerprints company +
  title + description, so a relisted role under a new ATS id stays gone.
- **Targeted scans drop the freshness window on purpose.** Naming five companies
  means "what is open there now"; a 30-day filter would usually return nothing.
- **Two tracks, two lists.** `ai_enablement` (`config/scoring.yml`) is the
  primary list; `growth_marketing` (`config/scoring-growth.yml`, capped at 5
  results) is the backup list, deduped against the primary.
- **Thresholds live in config, not in code.** `min_score_to_present: 4.0`,
  `worth_knowing_floor: 3.7`, `max_worth_knowing: 3`,
  `max_results_per_report: 12` — all in the `review` block of
  `config/profile.yml`.
- **A missing city in `config/commute.yml` silently drops a role.** If `status`
  shows many "unknown location" rejections, that is the cause.
- **Never run `taskkill`, `kill`, or any process-killing command.** Ask Doran to
  stop a server manually.
- **Board discovery runs three channels, all automatic in a broad scan.** LinkedIn's
  public guest search, Built In (via `browser_boards` in `sources.yml`), and the
  monthly Hacker News "Who is hiring" thread. All three produce *leads*; the
  posting itself still comes from the employer's live ATS wherever one is
  reachable. `--no-boards` disables all three.
- **A lead whose employer has no reachable ATS is no longer dropped.** Its body is
  read from the board's own live page at scan time. Never from a snapshot.
- **Scans are deliberately slow.** `politeness` in `profile.yml` caps requests at
  ~3/second/host with exponential backoff on 429s. Getting blocked by Greenhouse
  would outlast the run that caused it, so raise
  `min_seconds_between_requests_per_host` first if a provider ever complains.
- **An "evergreen_or_reposted" flag is not a bug.** Greenhouse's own data puts
  18-22% of ATS postings in the ghost category and reposting resets the visible
  date, so a posting we have watched for longer than `evergreen_days` is flagged
  even when its feed claims to be fresh. It flags, never rejects.
- **There is no `apply` command and there never will be.** See the hard rules in
  `CLAUDE.md`.

---

## Where things live

| Path | What it holds |
| --- | --- |
| `config/profile.yml` | Who Doran is, hard gates, comp math, report thresholds |
| `config/scoring.yml` | The ten weights, per-dimension anchors, calibration bands |
| `config/scoring-growth.yml` | The backup growth-marketing track |
| `config/commute.yml` | Door-to-door minutes from San Mateo 94403 |
| `config/sources.yml` | Companies and their resolved ATS boards; self-repairing |
| `rubric/` | `rubric-A-G.md` and the growing `learned-rules.md` |
| `ref-docs/calibration-phrasebook.md` | The ten levers in Doran's language; shown on every `/feedback` run |
| `data/jobs.db` | **Source of truth.** Not the conversation. |
| `data/runs/<run_id>/` | Per-run `queue.md`, `scores.json`, report output |
| `tests/` | `test_parsing.py` (34 checks), `test_pipeline.py` (34 checks) |
