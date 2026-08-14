---
description: Record Doran's verdicts on postings he was shown, and calibrate scoring quality using the plain-language phrasebook
---

Two different kinds of feedback flow through this command. They are independent —
Doran can give either one without the other, and forcing him to pick an
application verdict before he can correct a score is a bug, not a workflow.

## 0. Explain yourself first — every run, before asking for anything

Doran does not use this command often enough to remember its shape. Open by
telling him what it accepts. Keep it short, and put it in his terms:

> This command takes two kinds of feedback, and you can give either or both:
>
> **1. What you want to do with a job** — `interested`, `saved`,
> `not_interested`, or `applied`. This is your pipeline; it does not change how
> anything is scored.
>
> **2. Whether the system judged it well** — anything from "this shouldn't have
> been my top result" to "the commute penalty is too soft." This is what makes
> future scans sharper. **No numbers needed** — say it however it comes out.

Then display the ten-lever table from `ref-docs/calibration-phrasebook.md`
**verbatim**, introduced as "here's what's actually adjustable." Do not paraphrase
it, do not collapse it into prose, and do not skip it because it appeared earlier
in the conversation — the reminder is the point of the command.

**Never ask Doran for a numeric score.** The scores are an internal mechanism. If
he offers one, use it; if he does not, translating his words into a dimension and
a direction is your job. Read the full phrasebook before proposing any rule.

## 1. Show what is on the table

```
python cli.py pending
```

If that is empty, it does not mean nothing is awaiting feedback — a report
rendered with `--no-mark` leaves postings in state `evaluated` and out of
`pending` entirely. Check the most recent `data/runs/<run_id>/report.md` and offer
those postings by id instead. List them with score, title, company, and link.

## 2. Application intent -> `verdict`

Only for postings Doran actually rules on. Never infer intent from a scoring
comment, and never mark `applied` unless he says he applied.

```
python cli.py verdict --posting <id> --verdict <verdict> --reason "<his words>"
```

Capture his reasoning **verbatim** in `--reason`. The reason is the valuable part.
Note that recording a verdict also moves the posting's state, which is what puts
it on `/shortlist`.

## 3. Result quality -> `add-rule`

This needs no verdict at all. Take what Doran said, map it to a dimension using
the phrasebook, and **show him the proposed wording before writing anything**:

```
python cli.py add-rule "<rule>" --dimension <n>
```

Not every comment deserves a rule. "The commute is too long" is already encoded.
Look for what the rubric does not yet know: a company type, an org placement, a
responsibility pattern, a phrase that signals something real. One rule per lesson
— never batch unrelated observations into one.

If his feedback implies a **structural** change rather than a rule — a cap, a
modifier, a weight in `config/scoring.yml` — that is not `add-rule`. Show him the
diff and wait. A weight change reshapes every future score and he should see it
coming.

If he says a posting should be pinned permanently, propose a new calibration
anchor (an entry in `calibration_anchors` plus a doc under `ref-docs/golden/` or
`ref-docs/anti-examples/`) rather than a rule.

## 4. Re-check calibration after any rule lands

```
python cli.py calibrate --check
```

If an anchor has left its band, the rule over-corrected. Tell Doran which anchor
moved and in which direction, and propose a narrower wording rather than leaving
the rubric drifting.

## Rules

- Explain both feedback types and show the phrasebook table before asking for anything.
- Never ask for a numeric score. Never write a rule Doran has not seen.
- Record his reasoning in his own words, not a paraphrase.
- Never mark a posting as applied unless Doran says he applied.
- Scoring feedback never requires an application verdict.
