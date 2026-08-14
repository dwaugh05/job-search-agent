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
| `/calibrate` | Re-scores the five anchor postings blind against the current rubric and checks each lands in its band. Run after any rubric or weight change. |

---

## CLI subcommands

### Setup and sources

| Command | What it does |
| --- | --- |
| `python cli.py init` | Creates the SQLite database at `data/jobs.db`. Idempotent — every other command calls it implicitly where it matters. |
| `python cli.py verify-sources` | Probes every company in `config/sources.yml`, marks each `live`/`dead`, resolves unknown slugs, writes the file back. Exits **non-zero if under 70% live**. |
| `python cli.py resolve-company "DoorDash"` | Finds a company's live ATS board by probing real APIs with slug variants. Slugs are unguessable (DoorDash is `doordashusa` on Greenhouse) — never hand-edit one. |

Flags: `verify-sources --force` re-resolves even known slugs.
`resolve-company --save` caches into `sources.yml`, `--watch` also adds it to the
broad sweep, `--force` ignores the cache.

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
| `--days N` | Overrides the window. Default comes from `hard_gates.freshness_days` in `config/profile.yml` (currently **30**). |
| `--watch` | Targeted mode: also add these companies to future broad sweeps. |
| `--skip-liveness` | Skips the apply-URL re-check. Debugging only — liveness is a hard rule. |
| `--no-boards` | Broad mode: skip role-first board discovery, sweep companies only. |

`ingest` expects a JSON list (or `{"postings": [...]}`) with at least
`company, title, url, description`. Optional: `location, salary, published_at,
apply_url, work_model, is_remote, source, board, id`.

### Scoring and reporting

| Command | What it does |
| --- | --- |
| `python cli.py record-eval --file scores.json` | Writes A-G dimension scores back to SQLite. Applies the evidence cap, redistributes weight for null dimensions, applies scope/bonus modifiers, then stores the weighted score. |
| `python cli.py report` | Renders the seven-field match list, the growth-marketing backup list, and the "Worth knowing about" tier. |

`record-eval` flags: `--run N` tags the evaluations to a run,
`--track ai_enablement|growth_marketing` picks which list the scores belong to
(default `ai_enablement`).

Three behaviours in `record-eval` that are easy to trip over:

- **Evidence cap.** A dimension in a gated block (A, B, C, F) scored above 3.0
  with no quoted string in `block_notes` is silently clamped to 3.0. This is the
  main brake on score inflation — quote the posting.
- **Null means unscored.** A dimension explicitly set to `null` is dropped from
  the denominator, not scored as zero. That is how an unpublished salary range is
  handled without it becoming a hidden penalty.
- **Missing dimensions skip the posting.** Every dimension must be present as a
  number or an explicit `null`, or the whole evaluation is dropped with a warning.

`report` flags: `--threshold N` overrides the 4.0 bar, `--companies "A,B"` adds
near-miss lines for those companies, `--run N` tags the written report file,
`--no-mark` previews **without** marking postings as presented.

> **`report` is destructive to the candidate pool.** Everything it prints across
> both lists is marked presented and will never appear in a future scan again.
> Use `--no-mark` for a dry run.

### Verdicts and learning

| Command | What it does |
| --- | --- |
| `python cli.py verdict --posting <id> --verdict <v> --reason "..."` | Records Doran's ruling. Verdicts: `interested`, `saved`, `not_interested`, `applied`. Capture his reasoning verbatim — the reason is the valuable part. |
| `python cli.py pending` | Lists postings shown but never ruled on. They are suppressed from scans, so this is the only place they surface. |
| `python cli.py shortlist` | The interested/saved/applied pipeline with scores, links and notes. |
| `python cli.py status` | Database summary: totals, run count, learned rules, breakdown by state. |
| `python cli.py add-rule "<rule>" --dimension <n>` | Appends a durable learned rule to `rubric/learned-rules.md` and the DB. |
| `python cli.py calibrate` | Builds `data/calibration-queue.md` with all five anchors for blind scoring. |
| `python cli.py calibrate --check` | Verifies already-recorded anchor scores against their bands without re-queuing. |

Never mark a posting `applied` unless Doran says he applied.

---

## The canonical sequences

**Broad scan**

```
python cli.py scan
# read data/runs/<run_id>/queue.md, score it, write scores.json
python cli.py record-eval --run <run_id> --file data/runs/<run_id>/scores.json
python cli.py report --run <run_id>
```

**Targeted scan**

```
python cli.py scan --companies "Anthropic, Figma"
python cli.py record-eval --run <run_id> --file data/runs/<run_id>/scores.json
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
python cli.py calibrate --check  # every anchor must land in band
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
