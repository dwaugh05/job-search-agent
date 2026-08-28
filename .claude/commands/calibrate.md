---
description: Regression-test the rubric against the calibration anchors AND every job Doran has applied to, so no change can quietly make a real match invisible
---

Verify the rubric still scores Doran's known examples the way he rated them. Run this
after any change to `config/scoring.yml`, `rubric/rubric-A-G.md`,
`rubric/learned-rules.md`, `config/profile.yml`, or `src/careerops/prefilter.py` —
and always before trusting the first scan of a session.

**There are two halves and they catch different failures.** The anchors are scored
from documents and never touch the deterministic gates, so they cannot notice a
geography, title-band, comp or killer-term change that stops a real job reaching the
rubric at all. The applied-job check is the half that can. Run both.

## 1. Build the queue

```
python cli.py calibrate
```

This writes `data/calibration-queue.md` containing all five anchors.

## 2. Score them blind

Read the queue and score each anchor with the **current** rubric, exactly as you
would a real posting. Load `rubric/rubric-A-G.md`, `rubric/learned-rules.md`,
`ref-docs/voice-and-proof-points.md`, and `ref-docs/master-cv.md` first.

**Do not look at the expected band while scoring.** The point is to find out what the
rubric actually produces, not to reverse-engineer a passing number. If you catch
yourself adjusting a dimension to hit a target, stop — that defeats the entire test.

Write `data/calibration-scores.json`:

```json
{
  "rubric_version": "1",
  "scores": {
    "builtin_director_ai_gtm": {"weighted_score": 0.0, "dimension_scores": {}},
    "doordash_manager_marketing_ai_enablement": {"weighted_score": 0.0, "dimension_scores": {}},
    "plaid_ai_marketing_technologist_lead": {"weighted_score": 0.0, "dimension_scores": {}},
    "harvey_marketing_engineer": {"weighted_score": 0.0, "dimension_scores": {}},
    "jpmc_vp_role": {"weighted_score": 0.0, "dimension_scores": {}}
  }
}
```

## 3. Check the bands

```
python cli.py calibrate --check
```

| Anchor | Band | What it guards |
| --- | --- | --- |
| Reltio — Sr. Manager, AI GTM Strategy & Enablement | 4.7 – 5.0 | the ceiling |
| DoorDash — Manager, Marketing AI Enablement | 4.4 – 5.0 | remote, exact archetype |
| Plaid — AI Marketing Technologist Lead | 4.2 – 4.6 | the SF hybrid commute penalty |
| Harvey — Marketing Engineer | **4.0 – 4.3** | **the floor: must barely pass** |
| JPMC — Martech Ops & AI Enablement Lead, VP | 1.0 – 3.0 | hard gates fire despite high relevance |

## 4. If an anchor drifts

Report which anchor moved and in which direction, then diagnose:

- **Harvey too high** → the rubric is inflating. Usually dimension 3 rewarding scope
  it does not have, or dimension 4 scoring the top of the band instead of the offer
  point.
- **Harvey too low** → too strict. Usually penalizing the IC-level title, which the
  learned rules explicitly forbid.
- **Plaid at 5.0** → the SF commute penalty is not being applied. Check that the work
  model resolved to Hybrid rather than Remote.
- **JPMC above 3.0** → the hard gates are broken. This is the serious one: it means
  high content relevance is overriding the title band and geography checks, and no
  scan output can be trusted until it is fixed.

Fix the rubric, not the scores. Re-run until every anchor lands in band.

## 5. The applied-job regression check

```
python cli.py calibrate --applied-only
```

`calibrate --check` already runs this automatically; the flag above is for running
it alone, which is the fast one to reach for after touching a gate.

**Every job Doran applied to is a positive example that must keep working.** For each
one this re-runs the deterministic gates and re-reads the recorded score, and asks:

1. Would it still get through discovery to be scored at all?
2. Did it still clear the 4.0 bar when it was scored?

Freshness is excluded on purpose — every applied posting ages out eventually, and
that is the window working, not a regression.

**A `BLOCKED` line is the serious one.** It means a change to the gates has made a
role Doran actually wanted invisible, and no scan can be trusted until it is fixed.
The check exits non-zero so it can gate a change.

This was added on 2026-08-26 after exactly that: the title gate was throwing out
GitLab's "AI Transformation Owner, CRO" — a posting Doran applied to *and* a pinned
anchor scoring 4.53 — because "CRO" there names the org the role sits inside rather
than the role's own rank. Calibration was green the entire time.

When a `BLOCKED` line appears, the fix is almost never to loosen the gate wholesale.
Ask what distinction the gate is failing to draw, and encode that instead: a bare
C-suite acronym in a trailing clause names an org, while a spelled-out "Vice
President" is a rank, and JPMorgan's anti-example still has to fail.

A `note:` about older rubric versions is not a failure. It means those scores are
history rather than a live claim; the gate result on the same line is live either
way, and it is the gate result that matters here.

The check gets stronger every time Doran marks something applied, so it is worth
recording verdicts even for roles he has already heard back on.
