# Doran in his own words

Distilled from the Harvey hiring-manager interview transcript
(`interview with hiring manager for Harvey as Marketing Engineer.txt`).

This is the most important calibration document in the project. A resume lists what
someone did; this shows how Doran thinks about the work, which is what makes semantic
matching accurate and Fit Summaries specific instead of generic. **Load this before
scoring anything.**

---

## The three hats

Doran describes his Cloudflare role as three jobs at once. A posting that covers all
three is the archetype; a posting covering one is adjacent.

> "I wore the 3 hats... The builder hat, the strategy hat, and the enablement
> teaching hat."

**Builder.** He personally built anything high-touch and high-visibility:
> "I built any high touch, high visibility workflow or homegrown app or automation."

**Enablement teacher.** Training at scale, and he is candid that it is partly a
selling job:
> "I would run training sessions to really upskill all of marketing up to 200 people...
> I kind of felt like a YouTuber, where I was selling this AI enablement to all of my peers."

**Strategist.** Defining what an AI-native marketing org even is:
> "What does a AI native workforce look like instead of a content writer? Is he or she
> an orchestrator that's running these agents to be the human in the loop of that flow."

## The multiplication model - his signature

This is the single most distinctive thing about how Doran works, and the strongest
positive signal in any posting.

> "I'm only one person. And sure, I can impact all 200 marketers to a certain degree,
> but if I can find power users that they have 90% of their job is their regular job,
> but 10% is this one side AI project for their team of 20 people or whatever. Then
> that's a way to multiply me and multiply my impact... teach a person how to fish
> instead of just coming to one of my training sessions."

Work triage rule he applied:
> "If it was more mid-range or like it impacted a team of 20 or so users, then I would
> have one of my power users build it and I would consult on the project."

**Scoring implication:** postings that mention champions, power users, communities of
practice, train-the-trainer, or dotted-line enablement structures score high on
dimension 7. Postings requiring a large direct-report org score lower - he is open to
management but does not want it.

## How he architects

> "Agents I've always built as thinking them as a specialist. Like, if I hired a team
> of people to create a webpage, I would break that job up into different people. So
> each one's a specialist. Each agent was a specialist in that handoff."

The flagship pipeline, in his own sequencing: SEO agent researches Google Trends and
in-house SEO tooling, proposes topics -> **human picks one** -> research agents scrape
internal site content and competitor thought leadership -> draft grounded in internal
developer documentation -> **human approves** -> publishes via a custom MCP he built
around Contentful into componentized templates.

> "We built an MCP around that to plug in and solve all those issues."

## Human-in-the-loop is a conviction, not a buzzword

> "You want to 10X your people but have them part of the strategy and the leadership
> of the execution and the forward thinking of where it goes."

And on what went wrong at Cloudflare:
> "We kind of AI ourselves out of a job... they cut the entire marketing department
> except for about five or six people."

**Scoring implication:** explicit human-in-the-loop framing is a strong positive
(dimension 10). A posting that reads as "replace the marketing team with agents"
should be treated with suspicion, not enthusiasm.

## Governance - make the safe path the easy path

> "I created repos. I created reusable skills, reusable agents. I didn't want people
> rebuilding something and wasting time and effort and money and tokens... whenever the
> blah blah blah agent runs, it already pulls from my repo the security protocols agent
> that our engineering team has already signed off on."

> "An agent to build agents is a silly one, but a simple one... if they knew that my
> repo had an agent to build agents, then they would use that. It would be simpler than
> them just going off and doing it on their own. So you have to incentivize people."

## How he measures

> "Track KPIs like hours saved or estimated impact of internal or external... If it's a
> workflow that has an external impact to our customers, that would be valued higher as
> a weighted score versus internal."

> "The main one that my VPs cared about, and I think most VPs are always going to care
> about is trying to tie a dollar impact to that."

He built his own tooling to do it:
> "I was left on my own devices, so I built a homegrown SaaS tool to manage all my
> project, fed everything to AI to prioritize my projects, created a presentation for my
> VPs, road showed it to them."

## Why the role existed at all - the marketer-not-engineer insight

This is his core differentiator and it should be read as a *positive* signal, not a
gap. Companies where engineering is driving AI adoption into marketing are exactly
his opportunity.

> "It's an engineer mindset coming to AI, not a marketing first mindset... It was the
> engineering team coming down and saying just jargon that went over all of my
> colleagues' heads - rag this, Claude that... you could see my colleagues eyes glazing
> over."

> "I felt like in order for AI enablement to happen... we needed a marketer mindset.
> And within the first 5 minutes, he said, you had me at hello, where were you 3 months
> ago?"

---

## Scoring rules that come directly from this transcript

### 1. Title is not the constraint. Scope is.

> "I don't want to sell it or come off as if I'm looking for a role that as a director,
> head title necessarily. I don't get stuck on things like that. I'm just more about the
> responsibilities and the impact."

He raised the seniority question about Harvey honestly:
> "It's slightly less of a senior role than what I was already doing... if I was still at
> Cloudflare, it would hypothetically be a bit of a step down because I was kind of at a
> head level or a director level."

...and then stayed enthusiastic anyway. Corroborating evidence: his **highest-rated**
posting of all (Reltio, 95-100%) carries a **Sr. Manager** title.

**Therefore:** never penalize an IC, Lead, or Manager title when scope and ownership
are real. Penalize only VP+ over-reach and genuinely narrow execution-only seats.

### 2. Funnel breadth is a separate concern from title.

His one reservation about Harvey:
> "It seems confined to look at it from a strategy of demand gen and marketing
> operations and not like I touch sales, I touched all the parts of the lead funnel and
> to product marketing and things like that."

**Therefore:** dimension 8 scores how far a role reaches across the org, independent
of seniority.

### 3. Tooling latitude matters.

> "I hate reinventing the wheel when there's already an obvious answer for that."

> "It would take me like three months to onboard a new software from Google, which we
> already use for a vendor... I was stuck with these handcuffs of always having to build
> stuff basically from scratch."

**Therefore:** freedom to choose tools is a genuine positive (dimension 10); heavy
procurement/security red tape is a mild negative.

### 4. Both AI-native and AI-transforming companies work.

He engaged warmly with Harvey being AI-native ("resource is less of a constraint"),
and his Cloudflare success came from transforming a traditional org. What fails is AI
as branding with no budget or mandate behind it (dimension 9).

### 5. Greenfield is attractive.

He invented his own role once already. "First role of its kind", newly created
functions, and undefined scope are positives, not risks.

### 6. Growth trajectory counts.

He probed hard on where the role goes:
> "I guess it's checking that what I've said about the strategy and growth of this role,
> about the multiplication of its powers to other users so that it can become successful."

**Therefore:** a smaller role at a fast-growing company with room to expand can
outscore a bigger static one.

---

## Vocabulary he uses (useful for semantic matching)

power users - dotted line - multiply my impact - three hats - listening tour -
low-hanging fruit - agentic workflow - specialist agents - human in the loop -
orchestrator - AI native - upskill - enablement - hours saved - ROI weighted score -
QBR - roadmap - guardrails - reusable skills - homegrown app - MCP - change management
