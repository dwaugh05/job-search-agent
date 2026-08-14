---
description: Regression-test the rubric by re-scoring the five calibration anchors and checking each lands in its expected band
---

Verify the rubric still scores Doran's known examples the way he rated them. Run this
after any change to `config/scoring.yml`, `rubric/rubric-A-G.md`, or
`rubric/learned-rules.md` — and always before trusting the first scan of a session.

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
