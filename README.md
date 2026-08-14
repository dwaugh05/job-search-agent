# Career-Ops

A local, human-in-the-loop job discovery and evaluation agent. It sweeps live ATS
feeds, scores postings against a weighted rubric built from your resume and your
own ratings, and surfaces only strong matches for you to review manually.

**It never applies to anything.** Discovery and evaluation only.

## Setup

```
uv venv
uv pip install pyyaml httpx
python cli.py init
python cli.py verify-sources     # resolve + probe every company (takes a few minutes)
```

## Daily use

| You type | What happens |
| --- | --- |
| `/scan` | Sweep every watched company for postings from the last 14 days, score them, report matches ≥ 4.0 |
| `/scan-companies Anthropic, Figma, Ramp` | Same pipeline, but only the companies you name, and with no freshness window |
| `/feedback` | Rule on what you were shown; your reasons become durable scoring rules |
| `/shortlist` | Everything you marked interested or saved, plus anything awaiting a verdict |
| `/calibrate` | Regression-test the rubric against your five known examples |

## The two rules that shape everything

**You never see the same posting twice.** Once a posting is shown it is
permanently suppressed — and suppression works on a content fingerprint, not an
ATS id, so a role you rejected in August stays gone when it is relisted in October
under a new id and a tweaked title.

**Only live postings.** Every posting comes from an ATS feed fetched at scan time,
and its apply URL is re-checked before it reaches you. This matters more than it
sounds: the best-matching posting in the calibration set (Reltio) had already been
taken down while still being publicly listed.

## How scoring works

Ten weighted dimensions, scored 1.0–5.0, grouped into blocks A–F. Block G runs
separately and checks legitimacy and liveness. Pass threshold is 4.0.

| # | Dimension | Weight |
| --- | --- | ---: |
| 1 | Role archetype fit | 22 |
| 4 | Compensation | 14 |
| 2 | Build-vs-engineer balance | 12 |
| 5 | Location and commute | 12 |
| 7 | Leadership, influence and multiplication | 9 |
| 8 | Marketing domain proximity and funnel breadth | 9 |
| 3 | Seniority and scope band | 8 |
| 6 | Work model flexibility | 6 |
| 9 | Company AI maturity and mandate | 5 |
| 10 | Autonomy, tooling latitude and human-in-the-loop | 3 |

Judgement scores above 3.0 require a quoted line from the posting, or they are
capped automatically. That is the brake on score inflation.

**Discovery matches on description content, never on job title.** The four roles
you rated highest are titled *Sr. Manager, AI GTM Strategy & Enablement*,
*Manager, Marketing AI Enablement*, *AI Marketing Technologist Lead*, and
*Marketing Engineer*. Title is used only to filter VP+ roles out.

## Configuration

Everything tunable lives in `config/`:

- `profile.yml` — who you are, hard gates, compensation math
- `scoring.yml` — the ten weights, per-dimension anchors, calibration bands
- `commute.yml` — door-to-door minutes from San Mateo 94403; edit any number you
  disagree with and every future scan changes with it
- `sources.yml` — companies and their resolved ATS boards; repairs itself via
  `verify-sources`

The rubric itself is `rubric/rubric-A-G.md`, and `rubric/learned-rules.md` grows
every time you give feedback.

## Tests

```
python tests/test_parsing.py     # 34 checks: comp parsing, work model, fingerprints
python tests/test_pipeline.py    # 34 checks: freshness, suppression, ghost signals
python cli.py calibrate --check  # 5 anchors must land in their expected bands
```

## Full CLI

```
python cli.py verify-sources                    # probe/resolve every company
python cli.py resolve-company "DoorDash" --save # name -> ATS + slug
python cli.py scan [--companies A,B] [--fresh] [--all-open] [--days N] [--watch]
python cli.py queue                             # re-render the evaluation queue
python cli.py record-eval --run N --file scores.json
python cli.py report [--companies A,B] [--no-mark]
python cli.py verdict --posting ID --verdict interested --reason "..."
python cli.py pending | shortlist | status
python cli.py ingest --file scraped.json        # browser-sourced postings
python cli.py prefilter-pending
python cli.py add-rule "..." --dimension 8
python cli.py calibrate [--check]
```
