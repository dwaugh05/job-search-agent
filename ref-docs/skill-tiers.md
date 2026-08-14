# Skill tiers

**Status: FIRST DRAFT — Doran to edit.** Move any line between tiers and the
scorer changes behaviour accordingly. Nothing here is settled.

---

## Why this file exists

Every scoring mistake caught in the run-11 feedback round was the same failure:
the rubric knew *whether* Doran had a skill but not *how deep it ran*, so it kept
treating a third-tier skill as if it were a headline one. Three separate learned
rules had to be written to patch three instances of one missing idea — SEO/AEO,
product marketing, and "engineer" in a title.

This file is the idea itself. It is loaded at scoring time alongside
`master-cv.md` and `voice-and-proof-points.md`.

**The test a role must pass is not "can Doran do this?" but "would a hiring
manager pick Doran over someone who does this all day?"** Tier A is where the
answer is yes. Tier C is where it is no, regardless of whether he *could* do the
job.

---

## How the scorer uses this

| Situation | Effect |
|---|---|
| The role's **core purpose** is a Tier A skill | Dimension 1 scores 4.5-5.0 |
| Core purpose is Tier A but shares the remit with a Tier B discipline | Dimension 1 scores 4.0 |
| Core purpose is **Tier B** | Dimension 1 caps at 3.5 |
| Core purpose is **Tier C** | Dimension 1 caps at 2.5 — the role stays below the 4.0 bar |
| Role demands **Tier C technical depth** (production engineering) | Dimension 2 scores 2.0 or below |
| Role is **Tier A work described with Tier C vocabulary** ("engineer", "DevOps") | Read the duties, not the title. Do **not** down-score dimension 2 |

Two structural rules ride on top:

- **Director or VP titles demand a specialist.** At that band Doran only clears
  the bar when the specialism is itself Tier A. A Director of a Tier B or C
  discipline is a weak-to-okay candidate no matter how good the rest looks.
- **A Tier A pillar does not rescue a Tier C core.** If AI enablement is 30% of
  the job and the other 70% is Tier C, it is an okay fit, not a strong one.

---

## Tier A — the headline. Direct evidence, he wins the interview on these.

These are the things he did at Cloudflare that nobody has to take on faith.

- **AI enablement and adoption for a business organisation** — setting the
  strategy for how a team works with AI, and driving the change through.
- **AI upskilling and training at scale** — training sessions up to 200
  attendees, in-office hackathons (~30 builders), office hours, follow-up
  enablement material.
- **The power-user / champion multiplication model** — recruiting champions who
  spend ~90% on their own role and ~10% building AI for their team of ~20,
  dotted-line to him. His signature and the strongest single signal in a posting.
- **Agentic workflow design** — specialist agents with clean handoffs and humans
  at the decision points; explicit human-in-the-loop conviction.
- **AI governance that makes the safe path the easy path** — repos of reusable,
  security-vetted skills and agents; an agent that builds agents.
- **Custom MCP servers and API integration** — he built the Contentful MCP.
- **LLM orchestration and prompt systems** — Claude, Gemini, ChatGPT, n8n.
- **Website growth marketing and CRO** — the *capture* half of the funnel:
  landing-page optimisation, A/B testing programmes, conversion strategy,
  quarterly website strategy. This is his pre-AI headline skill.
- **Homegrown internal tooling** — agentic slide-generation app, PPC/demand-gen
  campaign analysis tool, SEO-to-landing-page pipeline, a SaaS project tracker
  that replaced Monday.com.
- **ROI measurement of AI work** — hours saved, dollar impact, customer-facing
  work weighted above internal, presented as monthly QBRs to VPs.
- **Inventing the role** — greenfield, first-of-its-kind mandates. He pitched his
  own role to a VP two levels up and had it approved in five minutes.

## Tier B — real and usable, but not what he leads with.

Credible on the CV. Supports a Tier A role. **Not** enough to carry a role on its
own, and not enough to make him a strong candidate for a specialist seat.

- Traditional **SEO** — genuine, but one strand of a growth remit, not eight
  years of specialism.
- **Web development**: HTML, CSS, JavaScript, PHP, SQL.
- **Marketing operations** *as one component of a broader role* — viable and
  within his ability. Becomes Tier C the moment it is the primary mandate.
- **Marketing analytics** — Google Analytics, Adobe Analytics, experiment
  pre/post analysis.
- **Martech as a user** — Salesforce, Marketo, Contentful.
- **B2B enterprise marketing strategy** — 10+ years, SaaS and enterprise.
- **Project and programme management** — real experience running PM teams, but
  adjacent rather than central to what he wants next.
- **Cross-functional leadership and stakeholder management** — VP-level exposure,
  influence without authority.
- **People management** — he has done it and is open to it, but does not want it
  as the primary duty. A large direct-report org is a deduction, not a plus.
- **Sales and GTM enablement** — the mechanics transfer directly, but serving
  Sales means his evidence is argued by analogy, which costs him credibility.
- **Technical writing and process documentation.**

## Tier C — do not score these as strengths.

He may be able to do the work. He would not beat a specialist for the seat, and
in several cases he has said outright he would not qualify.

**Marketing disciplines that are not his:**
- **AEO / answer engine optimisation** as a specialism — *"maybe like 3rd tier
  skills for me."*
- **Product marketing** — positioning, messaging, launches, battlecards,
  competitive intelligence. *"very different than the history I've brought with
  my resume and I would not qualify for this."*
- **Demand generation / lead generation** as the core mandate — the *creation*
  half of the funnel. Campaign management in the qualifications is a negative
  signal, not a neutral one.
- **Paid media and performance marketing** — paid search, paid social,
  programmatic, CTV, audio, OOH, direct mail, affiliate.
- **Brand marketing, advocacy, PR, community and customer references.**
- **Events leadership.**
- **Field marketing.**
- **Martech stack administration as the primary mandate** — *"I would be a very
  weak candidate for this role."*

**Technical depth he does not have:**
- **Production software engineering** — distributed systems, contributing to a
  mature product codebase, code review as a core duty, Ruby/Go/Java/C++.
- **ML engineering** — model training, inference infrastructure, ML platform.
- **Infrastructure engineering** — Terraform, Kubernetes, CI/CD ownership,
  cloud architecture as the job rather than a line in the requirements.
- **Data and analytics engineering** — dbt, warehouse modelling, advanced SQL
  pipelines as the primary craft.
- **Enterprise systems architecture** — Salesforce Apex/SOQL, CPQ,
  quote-to-cash, iPaaS platform ownership.

**Domain specialisms outside marketing:**
- HR / People operations, Legal operations, Finance and Tax, Internal Audit,
  IT service management. AI enablement pointed at one of these is a real role,
  just one where he is arguing by analogy the whole way.

---

## Open questions for Doran

1. **Is traditional SEO Tier B or Tier C?** It is filed as B because the CV
   supports it, but the MongoDB and ServiceNow feedback suggests it behaves like
   C whenever the role is a *specialist* seat. It may be that SEO is B as a
   component and C as a headline — the same split that already exists for
   marketing operations.
2. **Is sales/GTM enablement really Tier B?** The mechanics are identical to what
   he does; only the audience differs. Brex scored well and read well.
3. **Is project/programme management Tier B or C?** The GitLab feedback —
   *"program management at its core... more of just an okay fit"* — points at C,
   but he has genuinely run PM teams.
4. **Are biotech and pharma commercial orgs in or out?** Several are inside the
   30-minute ring and hire large marketing teams, but none of his experience is
   life sciences.
