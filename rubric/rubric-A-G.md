# A-G Evaluation Rubric

The scoring contract. Blocks A-F produce a weighted 1.0-5.0 score. Block G runs
independently and is never folded into that number.

**Before scoring anything, read:**
1. `ref-docs/voice-and-proof-points.md` - how Doran actually thinks about the work
2. `ref-docs/master-cv.md` - the proof points to map against
3. `rubric/learned-rules.md` - everything learned from his feedback so far
4. `config/scoring.yml` - weights and per-dimension anchors

---

## The evidence rule

**Every judgement score above 3.0 requires a quoted line from the posting.** Put
the quote in `block_notes` for that block. `record-eval` enforces this: a
dimension scored above 3.0 whose block note contains no quotation gets capped at
3.0 automatically.

This applies to **blocks A, B, C and F** — the ones where the score is an
interpretation of prose. **Blocks D and E are exempt**: compensation, location and
work model come from structured ATS fields that the queue has already parsed and
displayed, so there is no sentence to quote. Still write the reasoning in the
block note; it just is not gated.

This exists because the failure mode of an LLM scorer is not being wrong, it is
being agreeable. Quoting forces the score to be anchored in what the posting
actually says rather than what it seems to be about.

If a posting genuinely does not address a dimension, score it 3.0 and say so.
Absence of evidence is a 3.0, not a 4.0.

---

## Block A - Role archetype and responsibilities
**Dimensions 1 (weight 22), 8 (weight 9), 10 (weight 3)**

The heaviest block. Answer three questions:

**Dimension 1 - Is this the archetype?** The archetype is *owning AI enablement for a
marketing or GTM organization*: setting strategy, building agentic workflows, and
upskilling other people to build their own. Look for all three of Doran's hats
(builder, strategist, teacher). All three present and central = 5.0. One or two = 4.0.
AI as a minor component of a marketing role, or marketing as a minor component of an
AI role = 3.0.

Do **not** match on job title. The four postings Doran rated highest are titled
"Sr. Manager, AI GTM Strategy & Enablement", "Manager, Marketing AI Enablement",
"AI Marketing Technologist Lead", and "Marketing Engineer". Read the duties.

**Dimension 8 - How far does it reach?** Reach only, not department. A role
touching many named functions - or the full marketing funnel - scores 5.0; two or
three functions score 4.0; a single function scores 3.0. This is the dimension
that captures Doran's reservation about Harvey looking "confined to demand gen
and marketing operations".

Which organization it serves is handled separately by the **scope modifier**
(below). Do not mark a non-marketing role down here as well - that double penalty
is exactly what used to sink good company-wide AI enablement roles.

**Dimension 10 - Autonomy, tooling latitude, human-in-the-loop.** Explicit
human-in-the-loop framing, freedom to choose tools, and greenfield ownership all
score up. Rigid, approval-gated environments score down - his stated Cloudflare
friction was three-month vendor onboarding.

## Block B - Seniority, scope and leadership structure
**Dimensions 3 (weight 8), 7 (weight 9)**

**Dimension 3 - Score scope, not title.** This is the easiest dimension to get wrong.
Doran said plainly he does not "get stuck on" titles, interviewed happily for an IC
seat he called a step down, and rated a Sr. Manager posting as his best match of all.
An IC / Lead / Manager title with real ownership scores **4.0 or higher**. Penalize
only (a) VP+ over-reach, which is a hard gate anyway, and (b) genuinely narrow
execution-only seats with no strategy component.

**Dimension 7 - Influence and multiplication.** VP or CMO-level stakeholder exposure
scores up. An explicit champion / power-user / community-of-practice / train-the-
trainer model is the strongest possible signal here - it is Doran's signature way of
working. A requirement to manage a large direct-report org is a mild negative: he is
open to management but does not want it as the primary duty.

## Block C - Technical demand vs. capability profile
**Dimension 2 (weight 12)**

Doran builds real systems - agentic workflows, homegrown apps, a custom MCP server
around Contentful - using HTML, CSS, JavaScript, PHP, SQL and heavy LLM orchestration.
He is not a career software engineer and has not written systems code in a decade.

- Wants workflow building, API/MCP integration, prompt systems, light code: **5.0**
- Technical builder expected, no production-engineering bar: **4.0**
- "Engineer" in the title but the substance is workflow building: **3.0** and note it
  as likely negotiable. Do not down-score "Marketing Engineer" for its title alone.
- Real SWE expectations - production services, code review as a core duty: **2.0**
- ML engineering, model training, research, distributed systems: **1.0**

## Block D - Compensation
**Dimension 4 (weight 14)**

Apply Doran's math exactly:

1. **Base = the realistic offer point, 70% up the posted band**, not the midpoint.
   Someone with 10+ years and this exact background does not land at the middle of a
   wide range. Harvey's $136k-$204k gives a $183,600 offer point, which clears his
   $170k floor - scoring the $170k midpoint would wrongly read as borderline.
2. **Bonus = 10% of base** unless the posting states its own figure, in which case
   use theirs.
3. **Equity = $35,000** modeled if equity or RSUs are mentioned at all. $0 if not
   mentioned. Never guess a figure from a private company's valuation.
4. **Ignore benefits entirely.** Medical, dental, and perks do not count.

Target: base >= $170k, TC $200k-$300k. No range listed = 3.2 plus a Block G flag if
the role sits in a pay-transparency state.

## Block E - Geography, commute and work model
**Dimensions 5 (weight 12), 6 (weight 6)**

**Dimension 5** comes straight from `config/commute.yml` - the queue already shows
the computed minutes and the resulting score. Use it. Remote = 5.0. San Francisco is
~55 minutes and scores 3.5: a real deduction that still passes, which is what makes
Plaid land at 90% rather than 100%. Over 60 minutes is a hard gate that should have
fired in the prefilter.

If the queue flags an unknown city, say so in the block note rather than guessing.

**Dimension 6** is the work model itself: fully remote 5.0, 1-2 day hybrid 4.5,
unspecified hybrid 4.0, 3+ day hybrid 3.0, full on-site 2.0.

Be careful with remote claims. Ashby reports `isRemote: true` on postings whose
workplace type is "Hybrid" - the pipeline already corrects for this, so trust the
`work model` field in the queue over any "remote" language in the body.

## Block F - Company context and AI maturity
**Dimension 9 (weight 5)**

Both ends of the spectrum work. An AI-native company where resources are not the
constraint (Harvey) and a traditional org with a funded, executive-backed
transformation mandate (Cloudflare) are both 4.0-5.0. What fails is AI as branding
with no evidence of budget, mandate, or executive sponsorship.

Signals of a real mandate: named executive sponsor, a dedicated AI function,
"first role of its kind", stated investment, or a clear existing initiative to join.

---

## The scope modifier

After the ten dimensions are averaged, apply one flat adjustment for which
organization the role serves. Set `"scope"` on the evaluation object.

| `scope` | Adjustment | Use when |
| --- | ---: | --- |
| `marketing` | 0.00 | Marketing or growth; his proof points apply directly |
| `gtm_marketing_adjacent` | -0.10 | GTM including content, messaging, campaigns (Reltio) |
| `sales_field` | -0.30 | Sales enablement, field, revenue ops (GitLab ATO, Brex) |
| `company_wide` | -0.35 | Generalized AI enablement across all business functions |
| `single_other_function` | -0.60 | One non-marketing function: Legal, Finance, HR |
| `it_internal_only` | -0.90 | IT/ITSM serving internal technology operations only |

**This measures how strong a candidate Doran would be, not how good the role is.**
That framing is his, and it matters. On company-wide scope he said: *"I'm very,
very okay with the role being company wide or not company wide. The real hurdle
here is showing the adjacency as proof ... where I want to make sure I'm a strong
candidate that wouldn't get passed over."* On the sales-side GitLab role: *"it
doesn't exactly fit into the marketing niche where I would be an extremely strong
candidate."*

So the deduction prices screening-out risk. The further from marketing, the more
his evidence has to be argued by analogy rather than shown outright.

**Classify by who the role serves, not by its reporting line.** A role reporting
into IT that embeds with Finance, Legal, People and GTM is `company_wide`, not
`it_internal_only`.

**Never let this filter a role away.** Doran was explicit that a discounted role
should rank lower but stay visible: *"I still would want to see this job and not
completely filtered out."* Anything landing between 3.7 and 4.0 gets a one-line
mention in the "Worth knowing about" tier.

---

## Block G - Legitimacy and liveness
**Independent. Never folded into the 1.0-5.0 score.**

Emit exactly one of `PASS`, `FLAG`, or `FAIL`, plus a list of specific findings.

**FAIL** - drop the posting entirely:
- The apply URL is dead, redirects away, or the page says the role is closed.
  (Doran's best-matching golden example, Reltio, was removed on 2026-07-08 while
  still being listed. This is not hypothetical.)
- The same fingerprint has been seen under 3+ distinct ATS ids, or its publish date
  has reset 3+ times - a perpetually reposted ghost listing.
- The application flow asks for SSN, date of birth, or bank details before an offer.
- The employer entity cannot be identified at all.

**FLAG** - present it, with the warning line shown:
- Posted in a pay-transparency state (CA, WA, NY, CO) with no salary range. Under
  California SB 1162 a range is legally required, so its absence is a genuine signal
  rather than an oversight.
- The queue reports a perpetual-repost signal at a lower level (2 ids or 2 dates).
- Boilerplate vagueness: no named team, no concrete deliverables, no reporting line.
- A staffing agency posting an unnamed client's role.
- The careers domain does not match the company's own domain.
- Publish date is missing or low-confidence.

**PASS** - none of the above.

---

## Output format

Write `data/runs/<run_id>/scores.json`:

```json
{
  "run_id": 12,
  "rubric_version": "1",
  "evaluations": [
    {
      "posting_id": 431,
      "dimension_scores": {
        "1": 4.5, "2": 4.0, "3": 4.0, "4": 4.5, "5": 3.5,
        "6": 4.5, "7": 5.0, "8": 4.0, "9": 4.5, "10": 4.5
      },
      "block_notes": {
        "A": "\"lead AI enablement for Marketing\" and \"train and upskill marketers to build their own agents\" - all three hats present.",
        "B": "\"partner with VP-level stakeholders\"; no direct reports required.",
        "C": "\"comfortable with APIs and prompt engineering\" - no production-engineering bar.",
        "D": "\"$180,000 - $220,000\" -> offer point $208,000, +10% bonus, equity mentioned.",
        "E": "Hybrid, San Francisco - 55 min door-to-door from San Mateo.",
        "F": "\"our CMO has made AI adoption a top-three priority this year\" - funded mandate.",
        "G": "Apply URL live; salary range present; single sighting."
      },
      "block_g_verdict": "PASS",
      "block_g_flags": [],
      "fit_summary": "Three to four sentences. Map the role to Doran's specific proof points by name - the 50-person listening tour, the 200-person upskilling program, the Contentful MCP, the power-user model - not to generic strengths. State any gap plainly in the final sentence."
    }
  ]
}
```

Then: `python cli.py record-eval --run <id> --file data/runs/<id>/scores.json`

## Writing the Fit Summary

**House style, confirmed by Doran on 2026-08-12** after he read summaries in this
format: *"spot on and perfect in helping me understand what they're about and your
ratings and why I would fit them or not."* Match it.

**The job of this summary is to replace the posting.** Doran, 2026-08-28: *"the
ultimate goal in writing this summary is really so that I don't need to read the
entire job posting, so it's good to quote some sentences verbatim from the
posting as evidence citations about the fit."* If he still has to open the link
to know what the job is, the summary failed.

### The format, and it is checked

`cli.py record-eval` runs `report.fit_summary_issues()` over every summary and
prints a FIT SUMMARY warning for any that misses this. It warns rather than
blocks, so a warning is a rewrite instruction, not a suggestion.

| Rule | Why |
| --- | --- |
| **Exactly 2 paragraphs** | What the job asks for, then how it fits him. Never one blob. |
| **At least 2 verbatim quotes** from the posting | These are the evidence citations. He is reading them instead of the posting. |
| **6 sentences maximum, both paragraphs combined** | It is a tl;dr. Run 14's best summaries ran 5-6. |
| **320 characters minimum** | Below that it cannot carry the job's actual content. |

**Two paragraphs, not one blob.**

**Paragraph one - what the posting is ASKING FOR, in its own words.** Lead with
the most prevalent thing the posting says the job actually does, and quote it.
Weight what the posting itself weights: the top two or three responsibilities
are the real mandate, and the amount of column space a theme gets tells you how
much the employer cares about it. Open with what he'd
actually be doing day to day, in plain terms. Then map it to **named, specific**
proof points: the 50-marketer listening tour that became the AI roadmap, the
200-person upskilling programme, the office hours and hackathons, the power-user
model, the custom Contentful MCP, the repo of security-vetted reusable agents, the
homegrown ROI tracker behind his monthly QBRs, the SEO-to-landing-page pipeline.
"He ran a 50-person listening tour that became Cloudflare's AI roadmap" beats "he
has strategy experience." **Quote the posting** where a phrase is doing real work -
a line like *"AI is the mechanism; enablement is the domain"* tells him more than
any paraphrase.

**Paragraph two - what to weigh against it.** State the deductions plainly and in
his terms: commute in minutes and days per week, where the compensation top-end
lands, the seniority or title band, the coding bar, and how far the org sits from
marketing. No hedging and no softening. If a posting wants something he lacks, say
so - that is more useful to him than a clean-looking summary. Never claim
experience the CV does not support.

Write to him in the second person where it reads naturally. He is the reader, not
a third party being briefed about a candidate.

The report also carries the **posted date** on every entry; he called that out
specifically as useful, because a 3-day-old posting and a 28-day-old one call for
different urgency.
