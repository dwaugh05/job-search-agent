# Learned rules

Rules distilled from Doran's feedback on real postings. **Loaded into every
evaluation**, alongside `rubric-A-G.md`.

Each entry records the date, the dimension it affects, and the direction. Rules are
appended by `/feedback` (or `python cli.py add-rule`), never rewritten silently, so
the reasoning history stays auditable.

After adding a rule, run `/calibrate`. If an anchor leaves its band, the new rule has
over-corrected and needs narrowing before the next scan.

---

## Seed rules (from the calibration set, before any live feedback)

- **2026-08-12** (dim 3): Never penalize an IC, Lead, or Manager title when scope and
  ownership are real. Doran's highest-rated posting (Reltio, 95-100%) is a
  *Sr. Manager*, and he interviewed enthusiastically for an IC seat at Harvey that he
  himself called a step down. Penalize only VP+ over-reach and execution-only seats.

- **2026-08-12** (dim 8): Score funnel breadth separately from seniority. Doran's only
  reservation about the Harvey role was that it looked "confined to demand gen and
  marketing operations" versus his Cloudflare scope across the whole lead funnel and
  product marketing.

- **2026-08-12** (dim 1 / dim 8 / scope) — **SUPERSEDED by the 2026-08-12 rule below.**
  ~~"AI enablement" sitting in an IT, ITSM, or shared-services org is not the archetype
  regardless of how well the duties read. The role has to sit in marketing or GTM.~~
  This was too absolute and cost real matches.

- **2026-08-12** (scope modifier): A role that does **not** sit in marketing still
  qualifies when it is a generalized AI enablement role across the company — it is
  simply ranked slightly lower. Doran: "a role can still qualify if it doesn't sit
  in marketing and is more generalized across the company, but it would not be rated
  as strongly as a match, so you would need to slightly rank it lower (i.e. like 4.8
  becomes 4.5 if not in marketing)." Implemented as a flat `-0.30` for
  `company_wide`, `-0.60` for a single non-marketing function, `-0.90` for IT-internal
  only, and `0.00` for marketing/GTM/revenue/field.
  **Why a flat modifier rather than dimension scores:** encoding this inside
  dimensions 1 and 8 penalized the same fact twice — a company-wide role lost points
  for "not marketing" in the archetype dimension *and* again in the domain dimension,
  which pushed genuinely strong roles well below the bar. Dimension 1 now scores the
  shape of the role, dimension 8 scores reach, and department is priced exactly once.
  **How to apply:** classify by who the role serves, not by its reporting line — a
  role reporting into IT that embeds with Finance, Legal, People and GTM is
  `company_wide`, not `it_internal_only`.

- **2026-08-12** (dim 2): Do not down-score a role for the word "Engineer" in its
  title. "Marketing Engineer" is one of Doran's best-fitting archetypes. Down-score
  only for genuine production-engineering requirements in the body.

- **2026-08-12** (dim 4): Score the realistic offer point at 70% up a posted band, not
  the midpoint. Harvey's $136k-$204k reads as borderline at the midpoint and as a
  clear pass at the offer point, and Doran's actual reaction was enthusiasm.

- **2026-08-12** (dim 10): Explicit human-in-the-loop framing is a strong positive. A
  posting that reads as "replace the marketing team with agents" should be treated
  with suspicion - Doran watched exactly that happen at Cloudflare and lost his role
  to it.

- **2026-08-12** (Block G): A posting can be a perfect content match and still be
  dead. The single best match in the calibration set (Reltio) was removed on
  2026-07-08 while still publicly listed. Liveness is not a formality.

- **2026-08-12** (dim 1): Customer-facing AI transformation and solutions-architect roles at AI vendors (Writer, ServiceNow, Klaviyo, Cohere) are NOT the archetype - they help the vendor's customers adopt AI rather than enabling an internal organization. Score dim 1 at 2.5-3.0. The relevance prefilter cannot tell the two apart, so this distinction has to be made in Block A.

---

## From Doran's ratings of Checkr and GitLab (2026-08-12)

- **2026-08-12** (dim 4): **Score the TOP of a posted band, not an offer point.**
  Doran: *"$208 is acceptable and I'd negotiate for that top end, so I'm not worried
  about the low end of the pay for any of these roles ever."* Compensation should
  never push an otherwise-strong role down the list. The $170k floor stays, but as a
  hard gate on the band maximum, not as a scoring deduction. `OFFER_POINT` moved from
  0.70 to 1.00.

- **2026-08-12** (scope modifier — **reframed**): The scope deduction measures **how
  strong a candidate Doran would be**, not how good the role is. He is explicit that
  role scope is not the concern: *"I'm very, very okay with the role being company
  wide or not company wide. The real hurdle here is showing the adjacency as proof
  ... where I want to make sure I'm a strong candidate that wouldn't get passed
  over."* And on the sales-side GitLab role: *"it doesn't exactly fit into the
  marketing niche where I would be an extremely strong candidate."*
  The further from marketing, the more his proof points must be argued by analogy
  rather than shown, and the higher the screening-out risk. Gradient now:
  marketing 0.00 / GTM-marketing-adjacent -0.10 / sales-field -0.30 /
  company-wide -0.35 / single other function -0.60 / IT-internal -0.90.

- **2026-08-12** (reporting): **Never hide a near-miss.** Doran: *"I still would want
  to see this job and not completely filtered out... if you gave me a list of ten jobs
  and this was at the bottom then perhaps I wouldn't see it, but I don't want it
  hidden from me completely."* Roles scoring 3.7-4.0 now get a capped, one-line
  "Worth knowing about" mention below the matches. Never a full write-up, never mixed
  into the recommendations.

- **2026-08-12** (reporting): **Fit Summary house style — he confirmed this format
  works.** Two paragraphs, not one blob. First paragraph: what the role actually is,
  what it would have him doing, and the specific proof points it maps to (named
  concretely — the 50-marketer listening tour, the 200-person upskilling programme,
  the Contentful MCP, the reusable-agent repo, the ROI-weighted QBR tracker). Second
  paragraph: what to weigh against it — seniority, commute, compensation, coding bar,
  org placement — stated plainly, no hedging. Always include the **posted date**; he
  called that out as useful. Quote the posting directly where a phrase is doing real
  work. He said this style was "spot on and perfect in helping me understand what
  they're about and your ratings and why I would fit them or not."

---

## The builder-hat inversion (2026-08-12) — most important correction so far

- **(dim 1) The hard requirement is AI ENABLEMENT, not the builder hat.** Doran,
  correcting a score of 4.04 he felt was too low: *"I don't have the builder hat as a
  requirement, but more of a capability that I can tie into if the job needs it. So
  it's an upsell that I would use to make myself qualified. Like a checklist item that
  I check off for them, but not necessarily for me... it's the AI enablement part
  where I'm touching AI workflows (either through building or strategy or enablement
  training), that's the hard requirement I want to get out of this new role."*

  The three hats describe **what he offers**, not what a role must contain. A pure
  strategy-and-adoption role with zero hands-on building is a full 5.0 on dimension 1.
  I had this exactly backwards and was deducting for roles that "only" did strategy
  and enablement.

- **(dim 2) Reframed to measure mismatch risk only.** It asks "does this role demand
  more engineering than Doran has?" — never "does this role offer enough building?"
  A role with no build component scores 5.0 here, because there is no risk.

- **(dim 4) An unpublished salary range is TRULY neutral.** Doran: *"The fact that the
  salary isn't published shouldn't make it rate lower."* Dimension 4 is set to `null`
  and its weight is dropped from the denominator, so it neither helps nor hurts. The
  old fixed 3.2 was a hidden ~0.25 penalty. Block G still flags a missing range in a
  pay-transparency state — that is a legitimacy signal, not a pay judgement.

- **(geography) Southern California is a hard exclusion, same as the East Coast.**
  Confirmed on the PIMCO posting in Newport Beach. Added the full SoCal metro set to
  `commute.yml` so these fail fast and legibly rather than as "unknown location".

- **(geography — bug)** ATS location fields carry ONE city and it is often not the
  nearest option. Match Group's posting is filed under "Los Angeles, California" but
  reads *"will be based out of LA, Palo Alto, or San Francisco office"* — Palo Alto is
  28 minutes away. The pipeline now parses basing clauses for reachable alternates and
  ignores travel lists ("may travel to key hub cities including Dallas, LA, New York").

- **Content and location are independent judgements.** On PIMCO, whose content he
  rated 90-95% purely hypothetically: *"If you were to pretend hypothetically that it
  was remote or closer to my commute, then I would rate this as 90-95%."* The
  geography gate is what kills it, not the fit. Worth saying so explicitly in a Fit
  Summary rather than implying the role itself was weak.

- **2026-08-12** (dim growth-1): CAPTURE vs CREATION - the defining distinction for track B. Doran owns the conversion half of the funnel, not the traffic half: 'I was about capturing those leads via the website. Whereas most demand generation is about creating the traffic to the website through campaigns.' Paid, media, campaign and webinar management was someone else's job in his history. Score website/CRO/experimentation ownership at 5.0 on growth dim 1; score demand generation as traffic creation at 3.5. Apply campaign_creation_heavy -0.35 or _mixed -0.15.

- **2026-08-12** (dim growth-1): Campaign management in the qualifications is a negative signal, not a neutral one. Doran flagged it on both Roblox and Twilio unprompted: 'it's talking about qualifications of campaign management, which isn't a strong suit of mine.'

- **2026-08-12** (dim growth-7): People management plus campaign focus COMPOUND. Twilio scored 4.75 on scope and comp alone; Doran put it at 'maybe like 4 - it barely would make the list for those two reasons combined.' Neither alone would sink a role, but together they do.

---

## Track B: capture vs creation (2026-08-12)

- **The defining distinction for growth roles.** Doran owns the *conversion* half
  of the funnel, not the *traffic* half:

  > "My growth strengths where I would be a strong candidate were more tied towards
  > companies that are looking at web growth for the website channel as a part of the
  > funnel and less about paid campaigns or media or webinars. Usually that stuff in my
  > history was another person managing it, and then the leads from those would hit the
  > website and I was in charge of the optimization of the website to get that traffic
  > to turn into leads. So I was about **capturing** those leads via the website.
  > Whereas most demand generation is about **creating** the traffic to the website
  > through campaigns."

  Growth dimension 1 now scores website/CRO/experimentation ownership at 5.0 and
  demand generation as traffic creation at 3.5. A `campaign_creation_heavy` modifier
  (-0.35) or `_mixed` (-0.15) applies on top. The growth vocabulary was rebalanced so
  capture terms (CRO, landing page, A/B test, web growth, SEO) outweigh creation terms
  (paid media, programmatic, webinars, field marketing) roughly three to one.

- **Campaign management in the qualifications is a negative**, not a neutral. He
  raised it unprompted on both Roblox and Twilio.

- **People management and campaign focus compound.** Twilio scored 4.75 on scope and
  compensation alone; he put it at "maybe like 4 - it barely would make the list for
  those two reasons combined." Either alone is a deduction; together they are
  disqualifying-adjacent.

- **Classification detail:** count DISTINCT capture and creation signals, not
  occurrences. "Experimentation" repeated three times in the Roblox posting was
  outweighing two genuinely different campaign duties and hiding a real deduction.

- **2026-08-13** (dim 1): Marketing operations / martech administration as the CORE PURPOSE of a role is a strong negative -- score dim 1 at 2.0-2.5, not a mild deduction. Doran: "I would be a very weak candidate for this role." The same duties as ONE COMPONENT of a broader role are neutral: "a role where marketing operations isn't the core emphasis is still a viable role for me and it is still within my abilities to do some of this. I just don't want to be in a role where this is the primary and sole responsibility of it." Test: is owning the martech stack the primary mandate, or one of many responsibilities? Rejected on this basis: Exa "Own the marketing tech stack end to end", Harvey Head of Marketing Ops & Analytics, and LangChain "You'll own our marketing tech stack end to end". Watch for the synonyms too -- lead scoring, MQL/PQL definitions, lead routing/enrichment, attribution tooling, campaign QA.

- **2026-08-13** (dim -): THE ORDER OF A RESPONSIBILITIES LIST ENCODES EMPLOYER PRIORITY. The top two or three items are the real mandate; weight them accordingly when scoring dim 1, and cross-check against how much column space the posting gives each theme. Doran: "when I look at a job posting and I see a list of responsibilities, I know that whoever wrote this is probably putting the more important responsibilities that they care the most about as the top two or three in this list... the order of a responsibilities list does matter in your interpretation of how much that company cares about certain aspects of this role." He applied this himself to discount "Own budget and vendor management" as neutral precisely because it sat far down Harvey's list in one or two sentences.

- **2026-08-13** (dim 1): An explicit mandate to LEAD AI and automation adoption is a strong dim 1 positive -- the phrasing to look for is Harvey's "Lead AI and automation adoption - identify and ship agentic workflows and automation that remove manual work across the funnel; go beyond piloting tools to running them in production." Doran: "I do have a strong preference for a role that is leading for AI automation and adoption." But it does NOT rescue a role whose core purpose is martech administration: that exact posting carried this line and was still rejected. His words: "a big plus way down by the Martech operations administration as a big minus." Big pro, bigger con -- present it, but low on the list.

- **2026-08-13** (dim 5): COMMUTE TOLERANCE IS CONDITIONAL AND COMPOUNDS WITH FIT. A 55-60 minute commute is acceptable only when something pays for it: high compensation, high archetype fit, or 3 or fewer days on-site. Five days on-site combined with weak fit is a rejection regardless of other strengths. Doran on Exa: "I'd accept that commute time for something that I had high pay for or had a high fit for in matching my skill set. If it was just three days a week. But I definitely am not going to drive or take the train for a one hour commute, roughly when it's five days a week for a job I'm not that qualified for." Neither the commute nor the weak fit alone would sink a role; together they do.

- **2026-08-13** (dim 2): When a responsibility Doran only partly covers is EXPLICITLY SHARED with a named owner, do not treat it as a gap. Webflow asks him to "Own the web-side execution of AEO" but qualifies it "in partnership with the AEO lead" -- he flagged the qualifier himself as the reason it is not a concern: "I don't have to actually do 100% of AEO... I'm comfortable working with someone else and handling the web aspects of it." Look for "in partnership with", "alongside the X lead", "supporting the X team" before scoring a specialty as a mismatch risk.

- **2026-08-13** (dim 4): When a posting lists SEVERAL GEOGRAPHIC SALARY BANDS, use the higher-cost-of-living band. Doran is in the Bay Area, which always qualifies: "The Bay Area is definitely always considered a higher cost of living area." Natera published standard $152,100-$190,100 and higher-COL $167,300-$209,100; the parser took the standard band and understated the role by $19,000 of base. Combined with the existing rule to score the TOP of a band, the figure to use here is $209,100.

- **2026-08-14** (dim 3): A Director or VP title means the employer wants a SPECIALIST in that title's discipline, and Doran clears that bar on only two angles: AI enablement/transformation, or growth and web marketing. Down-weight dim 3 when the title is Director or VP and the named specialism is neither of those -- he is competing against people whose entire career is that discipline. Doran on ServiceNow Director SEO & AEO: "if the title is director or VP, then they are definitely going to want you to specialize. So it won't really match me unless it's a director or VP level that is a perfect match to my growth marketing web experience or to my AI experience at Cloudflare. I think those are the only two angles I would probably get an interview for a director of VP level title." Keep the deduction modest -- he still wants these visible above 4.0 when pay and remoteness carry them.

- **2026-08-14** (dim 1): SEO and AEO are THIRD-TIER skills for Doran, not headline ones. Do not score an SEO- or AEO-specialist role as a strong archetype match, and critically: the SEO-to-landing-page pipeline is evidence of AGENTIC WORKFLOW BUILDING, not of SEO expertise. Citing it as SEO credibility overstates him in the Fit Summary. Doran on MongoDB AEO Lead: "that was more about my understanding of building agented workflows. And not specifically about my strong skillset of SEO or AEO. Those are maybe like 3rd tier skills for me."

- **2026-08-14** (dim 1): Product marketing as the CORE PURPOSE of a role -- positioning, messaging, launches, battlecards, competitive intelligence -- is not the archetype and should score dim 1 at 2.0-2.5, keeping the role below the 4.0 bar. An AI company is not the same thing as an AI role. Doran on the Anthropic PMM posting: "This is a product marketer rule. Just because it's marketing in an AI company doesn't mean AI would fit it well, so this should be not rated above a 4 score, Since product marketing is very different than the history I've brought with my resume and I would not qualify for this."

- **2026-08-14** (dim 1): When AI enablement is only ONE PILLAR of a broader remit, check what the REST of the remit is. If that core discipline is itself outside Doran's skill set -- program management, demand generation, lead generation -- score dim 1 nearer 3.5 than 4.0: an okay fit, not a strong one. The 4.0 anchor assumes the surrounding remit is adjacent to him. Doran on the GitLab Principal Program Manager role: "it is about program management at its core. With AI maybe as 30% layered into it as a pillar only. If it was website growth marketing with AI layered into it as a pillar, then I would understand ranking it this high."

- **2026-08-14** (dim 2): DO NOT DOWN-SCORE A ROLE FOR THE WORD "ENGINEER" WHEN THE SUBSTANCE IS AI BUILDER WORK. MCP servers, connector and API integrations, agentic workflows, LLM orchestration and prompt systems are all squarely inside Doran's skill set -- he built a custom MCP server around Contentful. Read the duties, not the title or the boilerplate qualifications bar. Reserve dim 2 scores of 2.0 or below for GENUINE production software engineering: distributed systems, contributing to a mature product codebase, ML engineering, model training. A DevOps or infrastructure-as-code line in the requirements is not by itself disqualifying. Doran on Harvey Sr. AI Enablement Engineer, which this rule cost 0.36 points: "Harvey uses the term engineer, but that's a bit of a misnomer because if you read the job description it's more of an AI builder than a traditional engineer and that's the trap you need to avoid when you're giving a low score."
