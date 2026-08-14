# Skill tiers

**Status: FIRST DRAFT — Doran to edit.** Move any line between tiers and the
scorer changes behaviour accordingly. Nothing here is settled.

Where a line carries a quotation it is Doran verbatim — from `verdicts.reason` in
the database, `rubric/learned-rules.md`, `ref-docs/voice-and-proof-points.md`, or
past session logs. Lines without a quotation are drawn from the experience
section of `master-cv.md` and are the ones most worth checking, since they record
what he has *done* rather than what he has *said about* what he does.

---

## Why this file exists

Every scoring mistake caught in the run-11 feedback round was the same failure:
the rubric knew *whether* Doran had a skill but not *how deep it ran*, so it kept
treating a third-tier skill as if it were a headline one. Three separate learned
rules had to be written to patch three instances of one missing idea — SEO/AEO,
product marketing, and "engineer" in a title.

This file is the idea itself. It is loaded at scoring time alongside
`master-cv.md` and `voice-and-proof-points.md`.

**The test is not "can Doran do this?" but "would a hiring manager pick Doran
over someone who does this all day?"** He draws that line himself, repeatedly:

> "I'm not saying I can't do it. And I could definitely apply for a job that has
> this as part of the responsibilities. But the issue with this role is that it's
> not just one small part of the responsibilities, but rather It is simply the
> core purpose of everything about what this job is."

**So tier is a property of the role's CORE PURPOSE, not of the skill in
isolation.** The same skill can be Tier B as a component and Tier C as a mandate.
Marketing operations and SEO/AEO both behave exactly this way.

---

## How the scorer uses this

| Situation | Effect |
|---|---|
| Role's **core purpose** is a Tier A skill | Dimension 1 scores 4.5-5.0 |
| Core purpose is Tier A, sharing the remit with a Tier B discipline | Dimension 1 scores 4.0 |
| Core purpose is **Tier B** | Dimension 1 caps at 3.5 |
| Core purpose is **Tier C** | Dimension 1 caps at 2.5 — stays below the 4.0 bar |
| A Tier B/C skill appears as **one duty among many** | Neutral. Do not deduct |
| Role demands **Tier C technical depth** | Dimension 2 scores 2.0 or below |
| **Tier A work described with Tier C vocabulary** ("engineer", "DevOps") | Read the duties, not the title. Do **not** down-score dimension 2 |

**Which track a Tier A role scores on.** Group A1 below is the `ai_enablement`
track and its dimension 1. Group A2 is the `growth_marketing` track in
`config/scoring-growth.yml` and *its* dimension 1. Both carry the same 4.0 bar,
and a role strong on either group belongs on a list — a growth role does not have
to mention AI to qualify, and an AI role does not have to sit in marketing.

### The trap this file must not create

**Doran has TWO headline skill sets, not one.** AI enablement is the first. The
second is **web growth marketing and conversion** — ten years of it, and the
thing he was hired for before he invented the AI role.

A role can be Tier A on the growth side with **zero AI content** and still be a
strong match. He applied to Webflow's Senior Marketing Manager, Website Growth on
exactly that basis: *"the extremely strong fit to my growth marketing experiences
for web and conversion rate optimization... makes me a strong candidate while
also letting me still grow my AI skill set."*

Never let the Tier C entries for demand generation, campaign management or paid
media suppress a growth role whose centre of gravity is the **website, CRO and
experimentation**. Those are different jobs. The dividing line is capture versus
creation, not "marketing" versus "AI".

Three structural rules ride on top:

- **Title ceiling.** Director or "Head" is the top of what he wants — a Director
  title is a *positive* for leadership visibility when the content matches. **VP
  and above is over-reach he has declined outright:** *"I wouldn't be comfortable
  going above a title that is director or 'head'. I do want to get into more of a
  leadership capacity, but this is reaching too far."*
- **At Director level the employer wants a specialist.** He clears that bar on
  only two angles: *"it won't really match me unless it's a director or VP level
  that is a perfect match to my growth marketing web experience or to my AI
  experience at Cloudflare. I think those are the only two angles I would
  probably get an interview for a director of VP level title."*
- **A Tier A pillar does not rescue a Tier C core.** If AI enablement is 30% of
  the job and the rest is Tier C, it is an okay fit, not a strong one.

---

## Tier A — the headline. He wins the interview on these.

Two distinct groups. **Either one alone is enough to make a role a strong
match** — a pure web growth role with no AI in it qualifies just as much as a
pure AI enablement role with no growth in it.

### A1 — AI enablement and building

- **AI enablement and adoption for a business organisation.** The hard
  requirement, and the builder hat is optional on top: *"it's the AI enablement
  part where I'm touching AI workflows (either through building or strategy or
  enablement training), that's the hard requirement I want to get out of this
  new role."*
- **AI upskilling and training at scale** — *"I would run training sessions to
  really upskill all of marketing up to 200 people."* Hackathons, office hours,
  follow-up enablement material.
- **The power-user / champion multiplication model** — *"if I can find power
  users that they have 90% of their job is their regular job, but 10% is this one
  side AI project for their team of 20 people... that's a way to multiply me."*
  His signature, and the strongest single signal a posting can carry.
- **AI builder work: agentic workflows, MCP servers, connector integrations** —
  *"it's more of an AI builder than a traditional engineer and that's the trap
  you need to avoid when you're giving a low score... MCP servers and connector
  integrations, Which is all in my skill set of AI builder role."*
- **AI governance that makes the safe path the easy path** — *"I created repos.
  I created reusable skills, reusable agents. I didn't want people rebuilding
  something and wasting time and effort and money and tokens."*
- **Homegrown internal tooling** — slide-generation app, PPC analysis tool,
  SEO-to-landing-page pipeline, a SaaS project tracker that replaced Monday.com.
- **ROI measurement of AI work** — hours saved and dollar impact, customer-facing
  work weighted above internal, presented as monthly QBRs to VPs.
- **Inventing the role** — greenfield, first-of-its-kind mandates. He pitched his
  own role to a VP two levels up and had it approved in five minutes.

### A2 — Web growth marketing and conversion

Ten years, and the reason he was at Cloudflare before the AI role existed. The
*capture* half of the funnel: *"I was about capturing those leads via the
website. Whereas most demand generation is about creating the traffic to the
website through campaigns."*

- **Conversion rate optimisation** — the discipline itself, end to end.
- **A/B testing and experimentation programmes** — running the programme, not
  just reading results; experiment pre/post analysis on web metrics.
- **Landing page optimisation** for UX, SEO and conversion together.
- **Website strategy ownership** — planning and executing quarterly website
  strategy for a large B2B SaaS property.
- **Website customer acquisition** for B2B, SaaS and enterprise audiences.
- **Web funnel and lead capture design** — turning arriving traffic into
  qualified leads, including the Salesforce lead-tracking path through the funnel
  and Marketo campaign integration at the point of capture.
- **Web analytics and metrics analysis** — Google Analytics and Adobe Analytics
  used to find the drop-off and prove the lift.
- **UX optimisation and web design judgement** — enough to direct the work and
  build it himself in HTML, CSS and JavaScript.
- **SEO applied to a web property** he owns — distinct from SEO as a specialist
  team-leading seat, which is Tier C.
- **Training and enablement programme design** — predates the AI role: he trained
  HTML and PHP content development, built PM training curricula, and authored
  operational business processes. The teaching hat is not new.

### His own technical ceiling, in his words

Useful as the Tier A/B boundary for anything technical. He endorsed this exact
requirements list as matching him:

> "Hands-on technical fluency. CLIs, APIs, webhooks, SQL, and Python scripting.
> Working knowledge of LLM and agent behavior — prompting, context, tool use,
> RAG, MCP, evals, failure modes. Be very comfortable with a cloud platform. But
> that's definitely my capacity of how I would word my technical skill set."

Anything at or below that line is Tier A/B. Anything beyond it is Tier C.

## Tier B — real and usable, but not what he leads with.

Supports a Tier A role. Not enough to carry one, and not enough to make him a
strong candidate for a *specialist* seat.

- **SEO and AEO as a component with a named partner** — resolved by the Webflow
  posting, which he applied to: *"I'm not exactly qualified to 100% run all
  aspects of AEO, But I'm comfortable working with someone else and handling the
  web aspects of it."* As a headline specialism this drops to Tier C.
- **Marketing operations as one component** — *"a role where marketing operations
  isn't the core emphasis is still a viable role for me and it is still within my
  abilities to do some of this."* As the mandate it drops to Tier C.
- **Sales and GTM enablement** — the mechanics transfer and he has applied on
  that basis: *"Cloudflare is the proof that I can still do this same role for
  sales teams."* Still costs credibility, because the evidence is argued by
  analogy rather than shown.
- **Programme and project management** — he applied to a Principal PM role but
  named the limit himself: *"it is about program management at its core. With AI
  maybe as 30% layered into it as a pillar only... more of just an okay fit."*
- **Web development** — HTML, CSS, JavaScript, PHP, SQL. Enough to build and
  debug his own pages, integrations and lightweight internal apps.
- **Martech as a user** — Salesforce, Marketo, Contentful, n8n.
- **B2B enterprise marketing strategy** — 10+ years across Cloudflare, Intuit and
  agency-side work. Comprehensive marketing strategy for SaaS and enterprise,
  including brand awareness and acquisition planning as part of a broader remit.
- **Multi-channel campaign execution as a contributor** — social, email, SEO/SEM
  and content, from the Intuit years. He has genuinely done this; it is simply
  not what he leads with, and *owning* campaign management is Tier C.
- **Content and web governance at enterprise scale** — an enterprise content
  delivery site for 5,000+ users, a 1,000+ page reference library, and an
  authored web governance process.
- **Product, sales and design partnership** — leading cross-functional teams
  across sales, product marketing, product and design.
- **Cross-functional leadership and VP-level stakeholder management.**
- **Process development, quality management and technical writing** — authored
  and tested internal operational processes, ran internal QA review programmes.
- **People management** — done it, open to it, does not want it as the primary
  duty: *"I'm not looking to have direct reports as a people manager, but I'm
  open to it. And that's why a dotted line structure would be preferable."* He
  has managed website design and development engineers and a team of project
  managers.

### Explicitly neutral — neither credit nor deduction

> "I am neutral on 'Own budget and vendor management', As it's not that complex
> and is easy to pick up and learn, so it's not a pro or a con regarding my skill
> sets."

## Tier C — do not score these as strengths.

He may be able to do the work. He would not beat a specialist for the seat, and
in most of these he has said outright he would not qualify.

**Marketing disciplines that are not his:**
- **Marketing operations / martech administration as the core purpose** —
  *"something that would be on the very, very weak end of my skill set"* and
  *"I would be a very weak candidate for this role."*
- **AEO or SEO as a specialist headline** — *"Those are maybe like 3rd tier
  skills for me."*
- **Product marketing** — *"product marketing is very different than the history
  I've brought with my resume and I would not qualify for this."*
- **Demand generation and lead generation as the core mandate** — *"lead
  generation, which isn't my skill set."* The *creation* half of the funnel.
- **Campaign management** — a negative signal in qualifications, not a neutral
  one: *"it's talking about qualifications of campaign management, which isn't a
  strong suit of mine."*
- **Paid media and performance marketing** — paid search, paid social,
  programmatic, CTV, audio, OOH, direct mail, affiliate.
- **Brand marketing, advocacy, PR, community and customer references** — *"This
  about AEO and brand and not my skill set Of growth marketing or AI
  enablement."*
- **Events leadership** and **field marketing.**
- **Leading a large global marketing organisation** — *"'15+ years leading B2B
  marketing organizations' and '7+ years leading global teams'... is where I am
  weak."*

**Technical depth he does not have** — *"I wouldn't describe myself as an
engineer because I haven't done years of coding with complex languages... really
haven't done a ton of c coding in the last decade":*
- Production software engineering — distributed systems, mature product
  codebases, code review as a core duty, Ruby/Go/Java/C++.
- ML engineering — model training, inference infrastructure, ML platform.
- Infrastructure engineering — Terraform, Kubernetes, CI/CD ownership as the job.
- Data and analytics engineering — dbt, warehouse modelling, advanced SQL
  pipelines as the primary craft.
- Enterprise systems architecture — Salesforce Apex/SOQL, CPQ, quote-to-cash,
  iPaaS platform ownership.

**Domain specialisms outside marketing:** HR/People operations, Legal operations,
Finance and Tax, Internal Audit, IT service management. AI enablement pointed at
one of these is a real role, just one where he argues by analogy the whole way.

---

## Industry scope

**Biotech and pharma commercial organisations are IN** — confirmed by Doran on
2026-08-14. Roughly a dozen sit inside the 30-minute commute ring (Gilead,
Genentech, Vaxcyte, Iovance, Twist Bioscience, Veracyte, Corcept, Denali,
Sangamo, Eikon) and they run large commercial and marketing teams. Keep sweeping
them.

Industry is **not** a scoring dimension. A biotech marketing or AI enablement
role is scored on exactly the same tiers as a SaaS one — no domain-knowledge
deduction for life sciences, since none of the roles above require a science
background to run marketing or AI enablement for the commercial org. What still
applies normally is the Tier C entry for *serving* a single non-marketing
function: an AI enablement role scoped to Regulatory or Clinical alone is narrow
for the same reason a Legal-only one is.

## Open questions for Doran

None outstanding on scope. Three placement calls in this draft are inferred from
the CV rather than quoted, and are the ones worth checking:

1. **"Training and enablement programme design" placed in A2** rather than A1,
   on the grounds that the HitBridge PM-training and HTML/PHP teaching work
   predates the AI role.
2. **"Multi-channel campaign execution as a contributor" in Tier B**, split from
   "campaign management" in Tier C on the basis of ownership rather than task.
3. **SEO in two tiers** — A2 when applied to a property he owns, C as a
   specialist team-leading seat.
