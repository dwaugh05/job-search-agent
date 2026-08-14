---
description: Show the saved/interested pipeline and anything still awaiting a verdict
---

Show Doran where every posting he has seen currently stands.

## 1. The active pipeline

```
python cli.py shortlist
```

Everything marked `interested`, `saved`, or `applied`, with score, link, and his own
note.

## 2. Still awaiting a verdict

```
python cli.py pending
```

These were presented but never ruled on. They are suppressed from future scans, so
they only surface here — worth flagging if the list is growing, since it means good
matches may be going stale.

## 3. Health check

```
python cli.py status
```

Report the counts. Two things worth calling out if you see them:

- A large `rejected_prefilter` count relative to `raw_postings` is normal and healthy
  — that is the funnel doing its job.
- Many rejections reading "unknown location" mean `config/commute.yml` is missing
  cities. Offer to add them; each missing city is a role silently dropped.

## Rules

- Read-only. Do not change any state.
- Never suggest applying on Doran's behalf.
