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

- **2026-08-28** (dim growth-1): The `campaign_creation_heavy` -0.35 modifier is MECHANICAL, not a judgement call, but it is GRADED so it discriminates rather than taxing the whole track. Count DISTINCT creation signals (paid search, paid social, programmatic, media buying, budget pacing, affiliate, influencer, field marketing, events, integrated campaigns, demand generation, ABM) against DISTINCT capture signals (CRO, landing page, A/B test, experimentation, web growth, SEO, website conversion, web analytics). Apply **-0.35 heavy** only when creation >= 3 AND creation >= 2x capture. Apply **-0.15 mixed** when creation merely exceeds capture. Apply nothing when capture leads. The threshold matters: a flat "creation >= capture" test fired on 6 of 6 growth postings ever scored 3.5+, which is a weight change pretending to be a rule. Measured 2026-08-26 on postings Doran declined that all cleared 4.0 with no modifier at all: Databricks Director Americas Field Marketing (3 creation, 0 capture, 4.38), OpenAI Growth Digital Marketing (6 creation, 1 capture, 4.34), Zapier Sr Manager Performance Marketing (5 creation including 9 ABM mentions, 1 capture, 4.75 -- and it took the +0.15 AI-fluency bonus on top). Doran: "that's not really my skill set, if you see my resume, where I don't really talk about account based marketing (ABM) or Paid Media as a strong suit of mine." ABM was invisible to the vocabulary until this date; it is now a creation signal.

- **2026-08-28** (dim 8): Dimension 8 (who the role serves): down-weight when an AI enablement or transformation mandate spans revenue operations, finance and sales rather than sitting in marketing. Doran's proof points become analogies rather than direct evidence and the screening risk is real, so this is a deduction, not a disqualifier. Recorded 2026-08-26 on the Jobgether 'Senior Director, Awareness to Revenue' posting (scored 4.45, declined). Doran: 'Seems not exactly like a fit for my skills when it's referring to these revenue parts. It's reaching into sales and finance and operations, which are more like adjacencies to my experience than what I've really done. And since it's a senior role and a director role, I don't see myself as a strong fit.' Note this compounds with seniority: a Senior Director title over a funnel-wide revenue mandate is a bigger stretch than the same scope at manager level.

- **2026-08-28** (dim 3): REINFORCEMENT of the 2026-08-14 Director/VP specialist rule, which was written correctly and then not applied. Databricks "Director, Americas Field Marketing" scored dim 3 at **5.0** -- full marks -- for a Director title whose named specialism is field marketing, which is neither of the two angles Doran clears (AI enablement/transformation, or growth and web marketing). Field marketing, events marketing, brand, product marketing, communications and ABM are all "neither" for this purpose. A Director title in a discipline he cannot claim should score dim 3 at 3.0-3.5, never above 4.0. Doran: "Simply not interested because of it being a director focused on field marketing. This should not score above the four point line. Since a director in this area would want a ton of experience in something I simply don't have a skill set for." Note the modifier alone could not fix this posting: -0.35 still left it at 4.04. The seniority dimension is where it belongs.

- **2026-08-28** (dim 1): 2026-08-28 (prefilter vocabulary): A posting must be rejected for what the JOB is, never for which words it happened to use. Google's 'Program Manager, AI and Gemini App Marketing' scored 36.5 against the 40.0 relevance floor and was never read, despite stating the archetype outright: 'your main objective is to equip marketers with the tools and processes to move with greater agility and velocity.' It scored nothing because the highest-weighted terms are buzzwords ('ai enablement' 6.0, 'marketing ai' 5.5) that the posting simply does not use, and its title earned no bonus because 'and Gemini App' sits between the words AI and Marketing. Doran: 'this is a good example of a role that can point out phrases we should add to our scoring points system, so that it does pass. I know the pay is low, but that's the only reason why it should get knocked.' Three additions, each sized from a measurement over 28,812 stored postings rather than from intuition: (1) a verb-family pattern for equip/enable/empower/upskill + marketers/marketing team, worth 5.0, because the literal variants are each near-zero frequency while the family appears in 0.18 percent of postings; (2) a 4.0 title bonus when a title names both AI and marketing non-adjacently, awarded only when no literal title term already fired so nothing is paid twice; (3) AI-side synonyms for the four angles Doran named as most important - AI strategy (ai roadmap, ai vision, ai council, ai opportunities), AI builder (agent-powered, ai-powered workflow, internal ai, automate workflows) and AI architect (ai architect, applied ai, ai deployment, ai implementation). The architect terms are deliberately held to 3.0 and 2.5 rather than the 9-12x lift they measured, because at full weight they pulled 145 postings over the floor and the top of that list was almost entirely customer-facing solutions-architect roles at AI vendors, which the 2026-08-12 rule already says are not the archetype. Function-naming terms (gtm enablement, marketing enablement) went on the CONTEXT side, never the AI side, so a pure sales-enablement posting cannot use them to pass as AI enablement.

- **2026-08-28** (dim 1): 2026-08-28 (prefilter gate): SALES IS AN ADJACENT ORG, NOT A BLOCKER. The both-sides gate required an AI signal plus a business-context signal, and the context side only recognised marketing or company-wide language. Apple's 'Agentic AI Product Manager, Platform - Sales' scored 48.0, well clear of the 40.0 floor and the strongest agentic-enablement content in the Meta/Google/Airbnb/NVIDIA/Apple/OpenAI sweep, and was blocked outright because it says 'sales' five times and 'marketing' zero. Doran: 'the fact that it's sales only isn't necessarily a hard blocker, but rather, maybe it should make the scoring system slightly hurt to lose a point or points. But a blocker is too harsh because marketing and sales are still somewhat adjacent roles. And if the rest of the job description is heavy on my archetype but it's just in an adjacent org structure of sales instead of marketing then I still want to have it make the cut to show it to me.' Fix: sales/revenue/field org vocabulary now satisfies the context side of the gate but is deliberately worth ZERO points. The deduction he asked for already exists downstream as the sales_field scope modifier (-0.30), which is the correct place because it prices how strong a candidate he is rather than how relevant the posting is. Scored at even 2.0 these terms admitted 109 extra postings, nearly all ordinary sales jobs; at zero they admit 2. SECOND RULE, same conversation: TEACHING NON-TECHNICAL PEOPLE TO BUILD AGENTS IS A HEADLINE SIGNAL. Doran: 'A key thing I'm looking for is teaching non-technical people to build agents. The fact that it says teams across our worldwide sales organization build, run, and scale AI agents, is exactly why it's a strong fit for my skill set and archetype.' This is the power-user multiplication model stated as a duty rather than as a buzzword and no term in the vocabulary caught it. Added as a pattern worth 4.5 on the AI side, requiring the AI or agent context in the same sentence so ordinary self-serve BI language does not qualify: 67 of 28,812 postings match.

- **2026-08-28** (dim 1): 2026-08-28 (three buckets): Postings are now routed into three lists, each with its own presentation bar - AI+marketing overlap 3.75, AI-only 3.85, marketing-only 4.0. Doran: 'there is the traditional marketing role and then there is the AI role. And then there is a third bucket of where they overlap. And so I want to know about all three of these when you present the lists.' On the size: 'like a scale of 0, +1, +2.' THE LENIENCY IS A PRESENTATION BAR, NEVER A SCORE BONUS. Anchors assert scores against bands, so moving a bar cannot move a score; all eight anchors were unchanged when this landed. Adding points to a bucket instead would have moved every anchor at once and is not an acceptable implementation. The bucket is derived from postings.tracks, which the prefilter had always computed and persisted and which nothing read until now. Overlap is 3.75 rather than 3.70 because worth_knowing_floor is 3.70 and the near-miss tier selects score < bar AND >= floor - a 3.70 bar would have left the overlap bucket with an empty near-miss band, silently hiding the roles he called his sweet spot. SECOND FINDING, larger than the bucket work: record-eval was invoked with no --track in the normal scan flow, so EVERY evaluation was filed as ai_enablement and the marketing list had never been populated in the system's history. Measured 2026-08-28: 318 evaluations ai_enablement against 7 growth_marketing. A marketing role judged under scoring.yml cannot clear the bar because dimension 1 (weight 22) makes AI enablement the hard requirement, so this was not a routing cosmetic - it was marketing roles being judged by AI rules. queue.py now emits the correct track per posting and record-eval resolves the rubric per item rather than per file. Re-scoring the strongest 25 of that backlog against the growth rubric surfaced six roles that clear their bar, led by Life360 'Director, DTC Growth and Web Experience' (4.34, remote, 156k-231k, owns end-to-end conversion strategy and experimentation) and Neo4j 'Senior Manager, Web' (4.38).

- **2026-08-28** (dim 1): 2026-08-28 (bucketing): A MARKETING ROLE WEARING AI VOCABULARY BELONGS ON THE MARKETING LIST. Vercel's 'Growth Marketing Manager, Discoverability' says 'agent' fourteen times and says enablement, upskill and train exactly zero times - those agents are the AUDIENCE (AI assistants that might recommend Vercel), not something the job builds. It cleared the AI track on vocabulary alone. Doran: 'your scoring or checks are getting confused by some of the AI key phrases in here without understanding what the job really is about at its core, which is AEO, not AI that I am interested in. This falls under the marketing list.' Implemented in prefilter.evaluate: when growth relevance is at least 1.6x the AI relevance, the AI track is dropped and the posting is routed to the marketing bucket, where the bar is the full 4.0 rather than 3.75. This never hides a posting - it moves it to a harder list. The threshold was set from his own verdicts, not chosen: MongoDB 'Answer Engine Optimization Lead' 2.6x (declined), Vercel 2.1x ('the marketing list'), Apollo 'Partner Growth Manager' 1.8x ('should score less'), Agiloft 'Director, Global Campaigns' 1.2x (he asked to KEEP it), Freshworks 'GTM Engineer' 0.6x (a great fit). 1.6 sits in the gap between the roles he rejects and the one he defended. Effect: 11 of 33 overlap postings reclassify; Vercel (3.83) and Apollo (3.77) now fail the 4.0 marketing bar while Agiloft and OpenAI Lifecycle are untouched.

- **2026-08-28** (dim 3): 2026-08-28 (dim 3): THE DIRECTOR RULE IS NOW A CAP, NOT A REMINDER. Doran, 2026-08-14: 'if the title is director or VP, then they are definitely going to want you to specialize... it won't really match me unless it's a director or VP level that is a perfect match to my growth marketing web experience or to my AI experience at Cloudflare. I think those are the only two angles I would probably get an interview for a director or VP level title.' That was written as a rubric instruction, reinforced on 2026-08-28 after the Databricks field-marketing miss, and STILL not applied: run 25 scored Freshworks 'Director, GTM Systems Architecture' at a full 5.0 on seniority. Meanwhile Gilead (3.0), Agiloft (3.5) and Life360 (4.5, correctly, because growth and web IS his) were scored right. So the rule works when remembered and fails when not. Doran, 2026-08-28: 'you should look at your past attempts so that you can figure out the proper way to make this stick.' The rules that hold in this codebase are the mechanical ones - the evidence cap and the fit-summary check - so this became prefilter.seniority_cap(), applied by record-eval: a title containing director, head of, VP, SVP, EVP or chief is capped at 3.5 on dimension 3 UNLESS the block B note names one of the two disciplines he clears (AI enablement, AI transformation, AI strategy, AI adoption, growth, web, website, conversion, CRO). Below Director the cap never fires, because he is explicit that he does not get stuck on titles and rates an IC seat highly.
