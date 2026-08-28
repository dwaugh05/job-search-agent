# Career-Ops — Project Instructions

A local, human-in-the-loop job discovery and evaluation agent for Doran Waugh.
It finds live postings, scores them against a weighted rubric, and presents only
strong matches for **manual** review.

## Read this first

**Before running any command in this repo, read `.claude/README.md`.** It is the
full command reference — every slash command and every `cli.py` subcommand, with
flags, the canonical run sequences, and the gotchas that cost a run when missed.
The command list further down this file is a summary, not the reference.

## How to talk to Doran

He is a senior marketer, not a Python developer. Every rule below came from him
correcting a response in this repo.

**Lead with the answer.** First sentence is the recommendation or the result. No
preamble, no restating his question, no throat-clearing.

**One recommendation, not a menu.** If a real decision is his to make, ask one
short direct question. Do not lay out three options and let him pick.

**Do the thing he asked.** Make the change, then report it. Do not pad the task
with adjacent suggestions, and do not ask permission for work he already
requested.

**Plain language for anything technical.** Never explain by naming a function,
table, config key, or code path unless he asked how it works. Say what changes
for him, not what changed in the code. "The system thinks the old scores are
still good and won't redo them" — not "`already_evaluated` is keyed on
rubric_version."

**Full depth on job-posting content.** The simplification rule is about
implementation, never about judgement. He reads postings with real precision —
responsibility ordering, qualifying phrases like "in partnership with", the gap
between a stated title and the actual mandate — and he expects that same
precision back. Do not water down analysis of a role.

**Never ask him for a number.** Scores are an internal mechanism. Ask what was
wrong with the judgement in his words and translate it yourself. See
`ref-docs/calibration-phrasebook.md`.

**Keep it short.** More than a few sentences means a table or bullets. Long
prose blocks get skimmed and the point gets lost.

**If he says he did not follow, restate it simpler.** Do not re-explain with
more detail or more context — that is what caused the problem. Cut length,
remove jargon, give him the next action.

## Hard rules — never violate these

1. **NO AUTO-APPLY.** Never write, generate, or run code that submits a job
   application, fills an application form, uploads a resume to an ATS, or clicks
   an "Apply" / "Submit" control. The entire point of this system is to protect
   Doran's profile from ATS spam penalties. Discovery and evaluation only.
   Reading an apply URL to confirm it returns a real form is allowed;
   interacting with that form is not.

2. **NO CACHED SEARCH RESULTS.** Never source postings from general search-engine
   APIs, cached HTML, or aggregator snapshots. Every posting must come from a
   live ATS feed, a live job-board page, or a live company portal fetched at scan
   time. This doubles as the liveness check — we only evaluate jobs that are
   actually accepting applications.

3. **NO SPRAY AND PRAY.** Only postings that clear **their bucket's bar** are
   ever presented as matches. Doran's application time is the scarce resource.
   Never pad a report.

   The bars live in `config/profile.yml` under `review.bucket_thresholds` and
   are, as of 2026-08-28: **marketing-only 4.0, AI-only 3.85, AI+marketing
   overlap 3.75.** This replaced a flat 4.0 at Doran's request: "be more lenient
   ... if it's in that bucket where it's AI plus marketing merged together. And
   then be slightly less lenient when it's only AI. And then don't really be too
   lenient at all in scoring when it's just pure traditional marketing."

   The leniency is a **presentation bar, never a score bonus.** Nothing in it can
   move a score, which is why no calibration anchor drifted when it landed.
   Adding points to a bucket instead would have moved every anchor at once, and
   is not an acceptable way to implement this.

4. **NO CREDENTIAL STORAGE.** Browser work uses Doran's own logged-in Chrome via
   the `claude-in-chrome` MCP. Never store, request, or hardcode credentials.

## Architecture invariant

There is exactly **one** scoring pipeline. Broad scans (`/scan`) and targeted
company scans (`/scan-companies`) differ **only** in how the candidate set is
assembled. Everything downstream — normalize -> fingerprint -> prefilter ->
A-G rubric -> store -> report — is shared code. If the two modes could ever
produce different scores for the same posting, that is a bug.

## Division of labor

- **Python** does deterministic work only: fetch, normalize, dedupe, apply
  mechanical gates, persist, render. It never judges fit.
- **Claude (in-session)** does the semantic A-G evaluation on the small prefiltered
  queue, then writes scores back to SQLite via `cli.py record-eval`.
- **SQLite (`data/jobs.db`) is the source of truth**, not the conversation.

## How to communicate with Doran

**He will not read a long message. Assume he reads the first few lines and the
bold bits.** Do not build later messages on the assumption that he absorbed an
earlier one — he told me directly, 2026-08-14: *"Don't recall that exactly When
you're expecting me to read everything, which I just don't do."*

Rules:

1. **Lead with the decision he has to make**, not the reasoning that produced it.
   Reasoning goes below, or nowhere.
2. **One question at a time.** If several are open, ask the most important and
   hold the rest. A list of four questions gets zero answered.
3. **Never refer back to a previous message by name** ("the fallback I mentioned",
   "as discussed above"). Re-explain in one sentence, every time, from scratch.
4. **No jargon without a plain-English gloss on the same line.** "Per-run cap",
   "resolution fallback" and "scope modifier" all failed this test.
5. **Say what it costs him** — his time, his tokens, his money — whenever
   proposing work. He is actively conscious of Anthropic token spend and prefers
   a programmatic (Python) solution over a Claude-in-the-loop one wherever both
   would work.
6. Long output is fine when he asked for a *document* (a report, a rubric, a
   file). It is not fine in conversation.

## Server management

**NEVER run `taskkill`, `kill`, or any process-killing command.** If a server
needs restarting, ask Doran to stop it manually first.

## Key commands

Summary only — the full reference with flags is `.claude/README.md`.

```
python cli.py verify-sources                 # probe every ATS slug, mark live/dead
python cli.py scan [--companies A,B,C]       # sweep live sources AND apply the gates
python cli.py queue                          # re-render the eval queue for Claude
python cli.py record-eval --file scores.json # write A-G scores back
python cli.py report                         # strict 7-field output (marks as presented)
python cli.py verdict --posting <id> --verdict not_interested --reason "..."
python cli.py sync-connections               # force connection companies into the sweep
python cli.py applied                        # every role applied to + its saved write-up
python cli.py resolve-company "DoorDash"     # name -> ATS + slug (caches result)
python cli.py ingest --file scraped.json     # browser-sourced postings
python cli.py prefilter-pending              # gate anything still in state 'new'
python cli.py calibrate                      # rubric regression test vs 5 anchors
```

There is **no** `discover` and **no** `prefilter` command — `scan` does both in
one step. `prefilter-pending` is the standalone gate, and it only applies to
postings in state `new`, i.e. after `ingest`.

## Two rules that sit outside the rubric

**Connection bump.** Companies in `config/connections.yml` are places Doran
knows someone. Every posting from one gets a flat **+1.0**, hard-capped at 5.0.
It is stored separately from the rubric score and printed as a `Connection:`
line in the report — it is a relationship advantage, not a judgement about the
role, and it must never be mistaken for rubric drift. Adding a company is one
line in that file plus `python cli.py sync-connections`.

**Application archive.** An `applied` verdict writes
`data/applications/<date>-<company>-<title>.md` holding what the job asks him to
do, verbatim. Postings get taken down and he interviews weeks later; this file
is what he prepares from. Always tell him the path after recording the verdict.

## Calibration anchors — the rubric must keep hitting these

| Anchor | Expected | Role |
|---|---|---|
| Reltio — Sr. Manager, AI GTM Strategy & Enablement | 4.7 - 5.0 | ceiling |
| DoorDash — Manager, Marketing AI Enablement | 4.4 - 5.0 | strong |
| GitLab — AI Transformation Owner, CRO | 4.35 - 4.6 | sales/field adjacency |
| Plaid — AI Marketing Technologist Lead | 4.2 - 4.6 | SF hybrid penalty |
| Match Group — Principal AI Learning & Enablement | 4.2 - 4.5 | enablement without building |
| Harvey — Marketing Engineer | 4.0 - 4.4 | **floor: must barely pass** |
| Checkr — Staff AI Solutions Engineer | 3.9 - 4.2 | company-wide floor |
| JPMorgan Chase — VP role | 1.0 - 3.0 | hard fail |

The anchor list is defined in `config/scoring.yml` under `calibration_anchors`
and grows as Doran pins new examples — treat that file as authoritative if this
table and it ever disagree.

Run `/calibrate` after any rubric or weight change. If an anchor leaves its band,
the rubric is drifting — fix it before trusting any scan.
