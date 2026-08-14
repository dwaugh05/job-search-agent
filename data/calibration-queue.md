# Calibration queue

Score each anchor with the CURRENT rubric, exactly as you would a real
posting -- load `rubric/rubric-A-G.md` and `rubric/learned-rules.md` first,
and do not look at the expected band while scoring.

Write results to `data/calibration-scores.json`:

```json
{
  "rubric_version": "1",
  "scores": {
    "builtin_director_ai_gtm": {
      "weighted_score": 0.0,
      "dimension_scores": {}
    },
    "doordash_manager_marketing_ai_enablement": {
      "weighted_score": 0.0,
      "dimension_scores": {}
    },
    "plaid_ai_marketing_technologist_lead": {
      "weighted_score": 0.0,
      "dimension_scores": {}
    },
    "harvey_marketing_engineer": {
      "weighted_score": 0.0,
      "dimension_scores": {}
    },
    "jpmc_vp_role": {
      "weighted_score": 0.0,
      "dimension_scores": {}
    }
  }
}
```

Then run `python cli.py calibrate --check`.

---

## BuiltIn - Director, AI GTM Strategy & Enablement  (`builtin_director_ai_gtm`)

# Sr. Manager, AI GTM Strategy & Enablement - Reltio (an SAP Company)

**Doran's rating:** 95-100% - his highest-rated posting.

**Why this is the ceiling anchor:** Doran's note was that the salary is high, it is
remote, "everything about the duties and description really mirror what I did in my
recent role at Cloudflare", and it has high-level exposure through "Partner with
VP-level stakeholders". Nothing deducts. This is what a 4.7+ looks like.

**Two things this anchor teaches that nothing else does:**

1. **Title genuinely does not matter.** The URL slug says "director" but the real
   title is **Sr. Manager** - and this is the posting Doran rated highest of all.
   Combined with his statement in the Harvey interview that he does not "get stuck
   on things like that", any rubric that rewards a Director/Head title over a
   Manager title with bigger scope is scoring the wrong variable.

2. **The best-matching role in the whole calibration set was already closed.**
   Built In reports: *"Sorry, this job was removed at 11:10 a.m. (PST) on Wednesday,
   Jul 08, 2026."* Doran would have spent real time on an application that could
   never land. This is precisely what Block G's liveness check exists to prevent,
   and it is why the pipeline refuses to present anything it has not confirmed
   live in the current run.

**Related live posting:** Reltio's Greenhouse board (`greenhouse/reltio`) currently
carries a sibling role, *Senior Manager, GTM AI Business Partner*, at $117,000 -
$245,000, United States. Similar function, different framing - worth watching.

## Facts as the pipeline parses them

- **URL**: https://www.builtinsf.com/job/director-ai-gtm-strategy-enablement/9035176
- **Location**: Remote - Hiring Remotely in United States
- **Work model**: Remote
- **Salary**: $138,000 - $283,000 annually
- **Modeled TC**: base $239,500 + bonus $23,950 = **$263,450**
  (no equity mentioned in the listing)
- **Status**: REMOVED 2026-07-08 - retained for calibration only, never to be presented

## Mapping to Doran's proof points

| Posting requirement | Doran's matching evidence |
| --- | --- |
| "strategic owner of GTM's AI Operating Model" | Invented and pitched the AI enablement role at Cloudflare; built the org-wide AI strategy with his VP |
| "manage the backlog of AI use cases" | 50-person listening tour turned into a prioritized AI roadmap; homegrown SaaS tracker with weighted ROI scoring |
| "Partner with VP-level stakeholders... redesign them as 'Human-in-the-Loop' agentic workflows" | Reported to the VP of Global Marketing; built the SEO-to-landing-page pipeline with human sign-off gates |
| "presenting findings in quarterly business reviews (QBRs)" | Monthly QBRs to leadership tying every project to hours saved and dollar impact |
| "Govern the 'Source of Truth'... prevent hallucinations" | Repos of reusable skills/agents with security-protocol agents cross-checked against engineering standards |
| "drive the change management" | Trained 200-person global marketing org; hackathons, office hours, power-user program |

## Full posting text

```text
Job Summary: Reltio is looking for a Sr. Manager, AI GTM Strategy & Enablement to serve as the functional AI Product Owner for Sales, Solutions Consulting, Value Consulting, Professional Services, Customer Success, Sales Operations, Sales Enablement, Customer Support, and Alliances. In this role, you will act as the decisive bridge between the GTM team and the Enterprise AI Hub, translating cutting-edge AI capabilities into a long-term operational advantage.
 You will be the strategic owner of GTM's AI Operating Model. You will ideate with business leaders on best uses of AI, manage the backlog of AI use cases, own the proprietary knowledge bases that power our internal agents, and drive the change management required to make Reltio's GTM team the most efficient in the industry. You will ensure that every AI initiative moves beyond "experimentation" to deliver measurable business outcomes (e.g., deal velocity, sales team efficiency, enablement speed, message compliance, skill scalability, speed to productivity of new hires, tool rationalization, ROI validation).
 Job Duties and Responsibilities: 
 - AI Product Ownership (GTM): Act as the Product Owner for the GTM function. You will define requirements for new agents (e.g., "The Deal Velocity Agent must use the version-controlled content from the official GTM Knowledge Base"), prioritizing the backlog based on business value before handing technical specs or POCs to the Enterprise AI Engineering team or fully building functional tools within our platform. Examples of possible priorities: 
 - Profitability & Pricing Intelligence
- Content Creation
- In-Call Analysis & Next Action
- Data Capture Automation
- Role Play Simulation
- Scaled Skill Development and Coaching
 - ROI, Portfolio Management & Governance: Drive strict KPI alignment by leveraging a standard value realization framework for every initiative. You will be responsible for validating hard cost avoidance and efficiency gains and presenting findings in quarterly business reviews (QBRs) to GTM leadership and CIO on the health of the AI portfolio.
- Context Stewardship & Information Architecture: Govern the "Source of Truth" that powers our internal GTM AI agents. Ensure product messaging, sales plays, and competitive intel are structured as a corporate asset to prevent hallucinations and feed the "Reltio Brain."
- Process Re-engineering: Partner with VP-level stakeholders to deconstruct complex workflows'such as customer-facing content creation, new hire enablement, sales event management, enablement content development, success planning 'and redesign them as "Human-in-the-Loop" agentic workflows. You will also partner closely with Sales Operations to ensure tight data integration across our systems.
- Existing Stack Optimization: Champion and maximize the AI capabilities embedded within existing tooling, and identify gaps. You will audit the current landscape to ensure we enhance existing investments, identify gaps to be filled, or move to leverage functionality that is not broadly being utilized in the AI tool stack.
- Organizational Change & Culture: Lead the cultural shift toward an "AI-First" GTM organization. You will design enablement programs that upskill the GTM team and foster a "builder" culture.
 Skills You Must Have: 
 - Bachelor's degree in Business, Analytics, or related field (MBA preferred).
- 10+ years of experience in B2B / SaaS revenue management, with significant experience in Sales Operations, Digital Transformation, or Product Strategy.
- Product & Builder Mindset: You possess an inherent curiosity for AI and a hands-on "tinkerer" mentality. You actively experiment with AI and have a track record of building tools/systems that solve systemic inefficiencies.
 Tolerance for Ambiguity: Demonstrated ability to handle a high degree of uncertainty, charting a course when the roadmap isn't fully defined. 
 - Strategic Leadership: Proven ability to influence C-level and VP-level stakeholders. You must be able to say "no" to low-value AI experiments and steer leadership toward high-impact structural changes.
- Business Analysis & Metrics: Experience quantifying the value of internal projects. You should be comfortable calculating "time saved" or "cost avoidance" and presenting these metrics to leadership.
- AI & Systems Fluency: Strong conceptual understanding of AI architectures (e.g., agents, context windows, and the strategic differences between models like Gemini vs. Claude). You do not need to be a developer, but you must be able to translate business needs into clear requirements for the Enterprise AI Engineering team.
- Operational Rigor & Change Management: Proven ability to drive process improvements, technology rollouts, or behavioral shifts across cross-functional teams. You excel at establishing and governing centralized documentation and "Sources of Truth" to maintain organizational alignment.
 Skills That Are Nice to Have: 
 - Experience with CRM and Customer Success Platforms and how data flows between GTM tools.
- Basic familiarity with Python or low-code automation tools (Zapier, Make) to prototype workflows before handing them to engineering.
- Experience in Knowledge Management or Information Architecture.
- Experience leading large-scale digital transformation initiatives across an enterprise function.
 At Reltio, we carefully consider a wide range of compensation factors to determine your personal top of market. We rely on market indicators to determine compensation and your specific job family, background, skills, and experience to get it right. These considerations can cause your compensation to vary and will also be dependent on your location. 
 Overall Market Range
 $138,000 ' $283,000 USD 

 Reltio is proud to be an equal opportunity workplace. We are committed to equal employment opportunity regardless of race, color, ancestry, religion, sex, national origin, sexual orientation, age, citizenship, marital status, disability, gender identit
```

---

## DoorDash - Manager, Marketing AI Enablement  (`doordash_manager_marketing_ai_enablement`)

# Manager, Marketing AI Enablement - DoorDash

**Doran's rating:** 90-95%

**Why this is a calibration anchor:** Near-perfect archetype match - 'lead AI enablement for Marketing' is literally what he did at Cloudflare. Remote. Compensation is 'ok' rather than exceptional.

## Facts as the pipeline parses them

- **URL**: https://job-boards.greenhouse.io/doordashusa/jobs/8027367
- **Location**: United States - Remote  (city: United States - Remote)
- **Work model**: Remote
- **Published**: 2026-06-26
- **Salary**: $142,800 - $210,000
- **Modeled TC**: base $189,840 + bonus $18,984 + equity $35,000 = **$243,824**
- **Equity mentioned**: yes  |  **Bonus mentioned**: no
- **Department / team**: 412 Growth Marketing / San Francisco

## Full posting text

```text
About the Team 

 DoorDash’s mission is to grow and empower local economies. Marketing helps bring that mission to life by connecting insights, creative, channels, and operations into customer experiences that drive impact. The Marketing AI Enablement role sits at the center of that work, helping the organization use AI in practical, scalable, and responsible ways.

 About the Role 

 We are looking for a strategic, highly collaborative, and execution-oriented operator to help shape how Marketing uses AI across the org. This role will lead AI enablement for Marketing, support the intake and prioritization of AI opportunities, and partner with teams to turn promising ideas into repeatable workflows, tools, and operating practices.

 This role is designed to help Marketing move from fragmented experimentation to a unified, workflow-aligned AI operating model that creates measurable business value. It is a blend of strategy, program management, change management, and hands-on enablement.

 You’re excited about this opportunity because you will… 

 
- Build and run the Marketing AI enablement motion, including intake, prioritization support, office hours, documentation, training, and cross-functional coordination.

- Help teams identify the highest-value AI use cases and shape them into clear briefs, success metrics, and implementation paths.

- Partner with all Marketing functions, as well as Analytics, Legal, Procurement, and other cross-functional teams to reduce duplication, remove friction, and keep AI work moving.

- Create and maintain a central view of Marketing AI initiatives, including tools, pilots, owners, status, and business impact.

- Develop lightweight governance and operating norms that help teams move quickly while staying aligned on privacy, compliance, brand standards, and data use.

- Lead education efforts across the org, including trainings, Lunch & Learns, playbooks, and reusable templates.

- Support teams in turning pilot work into scalable workflows, repeatable systems, and durable documentation.

- Surface insights, adoption trends, and case studies that show where AI is saving time, improving quality, or accelerating launch speed.

- Identify overlap across workstreams and recommend when work should be centralized, standardized, or self-serve.

- Help build an AI-confident Marketing org that can adopt new tools with clarity and consistency.

 
 We’re excited about you because you have… 

 
- 5+ years of experience in enablement, learning & development, marketing operations, program management, business operations, AI adoption, or a related field.

- Experience working across multiple marketing functions and translating business needs into structured plans and workflows.

- Strong written and verbal communication skills, with the ability to create clear documentation for different audiences.

- Comfort driving ambiguous, cross-functional work from idea to execution.

- Strong organizational skills and a bias toward action.

- Experience with AI tools, workflow automation, or MarTech platforms (direct build experience is a plus).

- The ability to simplify complexity, create alignment, and help teams move faster without adding unnecessary process.

- A collaborative style and a strong instinct for partnership, enablement, and follow-through.

- Curiosity about how AI can improve marketing productivity, quality, and speed.

- Experience building or supporting training programs, workshops, playbooks, or learning experiences is a plus.

 
 
We expect this position to be filled by 8/25/26.
 Compensation 

 The successful candidate’s starting pay will fall within the pay range listed below and is determined based on job-related factors including, but not limited to, skills, experience, qualifications, work location, and market conditions. Base salary is localized according to an employee’s work location. Ranges are market-dependent and may be modified in the future.

 In addition to base salary, the compensation for this role includes opportunities for equity grants. Talk to your recruiter for more information.

 DoorDash cares about you and your overall well-being. That’s why we offer a comprehensive benefits package to all regular employees, which includes a 401(k) plan with employer matching, 16 weeks of paid parental leave, wellness benefits, commuter benefits match, paid time off and paid sick leave in compliance with applicable laws (e.g. Colorado Healthy Families and Workplaces Act). DoorDash also offers medical, dental, and vision benefits, 11 paid holidays, disability and basic life insurance, family-forming assistance, and a mental health program, among others.

 To learn more about our benefits, visit our careers page here .

 See below for paid time off details:

 
- For salaried roles: flexible paid time off/vacation, plus 80 hours of paid sick time per year.

- For hourly roles: vacation accrued at about 1 hour for every 25.97 hours worked (e.g. about 6.7 hours/month if working 40 hours/week; about 3.4 hours/month if working 20 hours/week), and paid sick time accrued at 1 hour for every 30 hours worked (e.g. about 5.8 hours/month if working 40 hours/week; about 2.9 hours/month if working 20 hours/week).

 
 The national base pay range for this position within the United States, including Illinois and Colorado.
 $142,800 — $210,000 USD 

 About DoorDash

 At DoorDash, our mission to empower local economies shapes how our team members move quickly, learn, and reiterate in order to make impactful decisions that display empathy for our range of users—from Dashers to merchant partners to consumers. We are a technology and logistics company that started by enabling door-to-door delivery, and we are looking for team members who can help us go from a company that is known as the place you order food to a company that people turn to for any and all goods.

DoorDash is growing rapidly and changing constantly, which gives our team members the opportunity to share their unique perspectives, solve new challenges, and own their careers. We're committed to supporting employees’ happiness, healthiness, and overall well-being by providing comprehensive benefits and perks including premium healthcare, wellness expense reimbursement, paid parental leave and more.

 Our Commitment to Diversity and Inclusion

 We’re committed to growing and empowering a more inclusive community within our company, industry, and cities. That’s why we hire and cultivate diverse teams of people from all backgrounds, experiences, and perspectives. We believe that true innovation happens when everyone has room at the table and the tools, resources, and opportunity to excel.

 Statement of Non-Discrimination: In keeping with our beliefs and goals, no employee or applicant will face discrimination or harassment based on: race, color, ancestry, national origin, religion, age, gender, marital/domestic partner status, sexual orientation, gender identity or expression, disability status, or veteran status. Above and beyond discrimination and harassment based on “protected categories,” we also strive to prevent other subtler forms of inappropriate behavior (i.e., stereotyping) from ever gaining a foothold in our office. Whether blatant or hidden, barriers to success have no place at DoorDash. We value a diverse workforce – people who identify as women, non-binary or gender non-conforming, LGBTQIA+, American Indian or Native Alaskan, Black or African American, Hispanic or Latinx, Native Hawaiian or Other Pacific Islander, differently-abled, caretakers and parents, and veterans are strongly encouraged to apply. Thank you to the Level Playing Field Institute for this statement of non-discrimination.

 Pursuant to the San Francisco Fair Chance Ordinance, Los Angeles Fair Chance Initiative for Hiring Ordinance, and any other state or local hiring regulations, we will consider for employment any qualified applicant, including those with arrest and conviction records, in a manner consistent with the applicable regulation.

 If you need any accommodations, please inform your recruiting contact upon initial connection.

 

 Notice to Applicants for Jobs Located in NYC or Remote Jobs Associated With Office in NYC Only

 We used Covey as part of our hiring and/or promotional process for jobs in NYC and certain features may qualify it as an AEDT in NYC. As part of the hiring and/or promotion process, we provided Covey with job requirements and candidate submitted applications. We began using Covey Scout for Inbound from August 21, 2023, through December 21, 2023. We resumed using Covey Scout for Inbound again on June 29, 2024, and ceased using Covey Scout for Inbound on April 30, 2026.

 The Covey tool has been reviewed by an independent auditor. Results of the audit may be viewed here: https://getcovey.com/nyc-local-law-144 .
```

---

## Plaid - AI Marketing Technologist Lead  (`plaid_ai_marketing_technologist_lead`)

# AI Marketing Technologist Lead - Plaid

**Doran's rating:** 90%

**Why this is a calibration anchor:** Strong match on responsibilities. Deduction is purely the commute: SF HQ hybrid is roughly a 55-minute door-to-door trip from San Mateo, above his 40-minute preference.

## Facts as the pipeline parses them

- **URL**: https://jobs.ashbyhq.com/plaid/ca8c19ad-2be8-4d4f-96af-e0a37ff76fb8
- **Location**: San Francisco HQ  (city: San Francisco)
- **Work model**: Hybrid
- **Published**: 2026-05-29
- **Salary**: $170,400 - $223,200
- **Modeled TC**: base $207,360 + bonus $20,736 + equity $35,000 = **$263,096**
- **Equity mentioned**: yes  |  **Bonus mentioned**: yes
- **Department / team**: All Departments / Growth Marketing

## Full posting text

```text
We believe that the way people interact with their finances will drastically improve in the next few years. We’re dedicated to empowering this transformation by building the tools and experiences that thousands of developers use to create their own products. Plaid powers the tools millions of people rely on to live a healthier financial life. We work with thousands of companies like Venmo, SoFi, several of the Fortune 500, and many of the largest banks to make it easy for people to connect their financial accounts to the apps and services they want to use. Plaid’s network covers 12,000 financial institutions across the US, Canada, UK and Europe. Founded in 2013, the company is headquartered in San Francisco with offices in New York, Washington D.C., London and Amsterdam.

The Marketing Operations (Ops) Team at Plaid builds the essential foundation that enables the Marketing function to operate efficiently, scale sustainably, and align with the company’s strategic goals. We focus on people, technology and process to drive operational excellence and optimize marketing performance.

Our team is focused on creating and executing impactful marketing strategies that resonate with our target audiences, drive sustainable growth through high-quality pipeline generation, and enhance marketing efficiency. By integrating innovative technologies, we strive for seamless workflows and data-driven decision-making. We also continuously strengthen the foundation of a high-performing marketing organization, ensuring that processes and systems are in place to support long-term success.



Responsibilities: 

 - Own the strategy and execution for integrating AI into marketing workflows, identifying high-impact opportunities to improve efficiency, scalability, and performance.

 - Design, build, and deploy AI-powered agents and automations that support marketing workflows.

 - Evaluate emerging AI tools and technologies, staying current on industry trends and translating new capabilities into practical marketing applications.

 - Partner cross-functionally across Marketing, BI, GTM Ops, and Web Engineering teams to implement and scale AI-enabled workflows and drive adoption.

 - Lead change management efforts by training teams, evolving workflows, and helping employees transition from manual execution to managing AI-assisted systems.

 - Partner with stakeholders on optimizing the marketing technology ecosystem, including AI tooling, APIs, data flows, Salesforce integrations, BI tooling, and marketing automation infrastructure.

 - Operates with a strong builder mentality, driving 0-to-1 development of scalable, secure, and automated marketing systems that improve operational velocity and reduce manual work.

Requirements: 

 - Bachelor’s degree in Marketing, Business, Information Systems, Computer Science, or a related field (or equivalent practical experience).

 - Hands-on experience designing and deploying AI-powered workflows, agentic systems, or marketing AI agents that improve operational efficiency and scalability.

 - Demonstrated success driving transformational change within an organization, including influencing teams to adopt new technologies, workflows, or operating models.

 - Strong experience working with LLMs, prompt engineering, AI automation platforms, and emerging AI technologies.

 - Deep understanding of marketing operations and experience with marketing automation platforms, including campaign creation, workflow management, testing, and optimization.

 - Proficiency with SQL, Tableau, and other BI/data visualization tools, with the ability to analyze large datasets and translate insights into actionable recommendations.

 - Strong analytical and systems-thinking mindset, with the ability to identify inefficiencies, solve complex operational problems, and design scalable solutions.

 - Excellent cross-functional communication and stakeholder management skills, with the ability to influence and collaborate across Marketing, Operations, BI, and Engineering teams.

 - Highly organized and execution-oriented, with strong attention to detail and the ability to manage multiple initiatives simultaneously in fast-paced environments.

 - Comfortable operating in ambiguity and rapid change, with a proactive, builder-oriented mindset and a strong drive for continuous improvement.

Our mission at Plaid is to unlock financial freedom for everyone. To support that mission, we seek to build a diverse team of driven individuals who care deeply about making the financial ecosystem more equitable. We recognize that strong qualifications can come from both prior work experiences and lived experiences. We encourage you to apply to a role even if your experience doesn't fully match the job description. We are always looking for team members that will bring something unique to Plaid!



Plaid is proud to be an equal opportunity employer and values diversity at our company. We do not discriminate based on race, color, national origin, ethnicity, religion or religious belief, sex (including pregnancy, childbirth, or related medical conditions), sexual orientation, gender, gender identity, gender expression, transgender status, sexual stereotypes, age, military or veteran status, disability, or other applicable legally protected characteristics. We also consider qualified applicants with criminal histories, consistent with applicable federal, state, and local laws. Plaid is committed to providing reasonable accommodations for candidates with disabilities in our recruiting process. If you need any assistance with your application or interviews due to a disability, please let us know at accommodations@plaid.com.



Please review our Candidate Privacy Notice here https://plaid.com/legal/#candidate-privacy-notice.


Additional compensation in the form(s) of equity and/or commission are dependent on the position offered. Plaid provides a comprehensive benefit plan, including medical, dental, vision, and 401(k). Pay is based on factors such as (but not limited to) scope and responsibilities of the position, candidate's work experience and skillset, and location. Pay and benefits are subject to change at any time, consistent with the terms of any applicable compensation or benefit plans.
```

---

## Harvey - Marketing Engineer  (`harvey_marketing_engineer`)

# Marketing Engineer - Harvey

**Doran's rating:** interviewed; 'super interested' despite a step down in seniority

**Why this is a calibration anchor:** THE FLOOR ANCHOR. Doran interviewed for this role and stayed very interested even though he called it 'slightly less of a senior role than what I was already doing' - an IC seat reporting into a future Head of Marketing Operations. Posted base band straddles his $170k floor, the commute is SF hybrid, and the scope looked confined to demand gen and marketing ops rather than the whole funnel. But it is greenfield ('first role of its kind'), AI-native, and high leverage. This must score 4.0-4.3: barely passing. A rubric that scores it 4.8 is inflating; one that scores it 3.4 is too strict.

## Facts as the pipeline parses them

- **URL**: https://jobs.ashbyhq.com/harvey/e736b822-3d24-4c72-bf70-b8f5b2c7fad8
- **Location**: San Francisco  (city: San Francisco)
- **Work model**: Hybrid
- **Published**: 2026-07-16
- **Salary**: $136,000 - $204,000
- **Modeled TC**: base $183,600 + bonus $18,360 + equity $35,000 = **$236,960**
- **Equity mentioned**: yes  |  **Bonus mentioned**: yes
- **Department / team**: Marketing / Marketing

## Full posting text

```text
WHY HARVEY

At Harvey, we’re transforming how legal and professional services operate. By combining frontier agentic AI, an enterprise-grade platform, and deep domain expertise, we’re reshaping how critical knowledge work gets done for decades to come.

This is a rare chance to help build a generational company at a true inflection point. We have strong product-market fit and world-class investor support. We’re scaling fast and defining a new category in real time. The work is ambitious, the bar is high, and the opportunity for growth — personal, professional, and financial — is unmatched.

Our team moves fast, takes ownership, and is deeply committed to the mission — operating with intensity, staying close to our customers, and pushing each other for excellence. We live by three values: Decisiveness, Simplicity, and Job's Not Finished. We act quickly on clear judgment over perfect information, we believe simplicity is what scales, and we're never satisfied with where we are. If you want to do the best work of your career alongside people who share that drive, we'd love to build with you.

At Harvey, the future of professional services is being written today — and we’re just getting started.




ROLE OVERVIEW

This is the first role of its kind at Harvey — and one of the highest-leverage seats in the company. The Marketing Engineer sits at the exact point where growth strategy meets world-class AI execution: you'll take the ideas marketing bets on and turn them into shipped, compounding systems.

You'll partner directly with marketing leadership, demand gen, digital marketing, brand, product marketing, and marketing operations to spot the highest-leverage AI opportunities and ship them. Owning everything from the automation running behind the scenes to the experiments running live on harvey.ai http://harvey.ai. It's a rare opportunity to sit at the intersection of engineering and marketing at a category-defining legal AI company.







WHAT YOU'LL DO




 - Own the identification, scoping, and implementation of AI and automation use cases that improve demand generation velocity, campaign operations, pipeline conversion and more.

 - Build and maintain AI workflows from automated content creation to intelligent audience targeting and personalization at scale.

 - Design and deploy automation workflows (e.g., Claude, Clay, n8n, or equivalent) that eliminate manual work across the demand gen stack, integrating with Marketo, Salesforce, web CMS, and digital platforms.

 - Build and run experimentation infrastructure: A/B tests, landing pages, and conversion-flow changes, directly on harvey.ai http://harvey.ai and campaign surfaces, not just backend automation.

 - Manage the cost and efficiency of automated workflows.

 - Collaborate with Marketing Operations, Content, and Performance Marketing to translate strategic marketing needs into technical solutions.

 - Continuously evaluate emerging AI capabilities, including new models, agent frameworks, and MCP integrations, and prototype applications that give Harvey's marketing team a competitive edge.
   
   





WHAT YOU HAVE

 - 4+ years of experience in growth engineering, marketing engineering, GTM engineering, or a technical role within a marketing/growth function at a B2B SaaS company.

 - Hands-on experience building with AI — you use tools like Claude Code, Cursor, or equivalent as part of your daily workflow, not just as something you build on top of.

 - Experience working with LLM APIs or AI-powered tools to generate content, automate workflows, or optimize marketing performance.

 - Familiarity with marketing automation platforms (e.g., Marketo, HubSpot), CRMs (e.g., Salesforce), workflow/automation tools (e.g., Clay, n8n, Zapier, Make), and analytics/experimentation tooling (e.g., Amplitude, Mixpanel, Segment, PostHog, GA4).

 - A builder mentality, comfortable operating in ambiguity, shipping iteratively, and taking ownership of 0→1 projects.

 - Strong analytical skills with the ability to design experiments, own attribution, and translate data into decisions.

 - Cross-functional collaboration: work closely with internal teams across data science, marketing operations, performance marketing, product marketing, and sales to ensure campaign success. Drive alignment on priorities and share insights to refine strategies.






NICE TO HAVE 

 - Experience with data warehouses/BI tools

 - Strong programming skills

 - Experience building on a marketing site or product surface (landing pages, onboarding, referral or lifecycle systems).

 - Background at a high-growth B2B SaaS or AI-native company.







COMPENSATION

$136,000-204,000 USD




DEPENDING ON YOUR LOCATION, AN APPLICANT PRIVACY NOTICE MAY APPLY TO YOU. YOU CAN FIND ALL OF OUR APPLICANT PRIVACY NOTICES [HERE https://www.notion.so/harveyai/Harvey-Candidate-Privacy-Policies-319ac3fcdd7a803bb807d5094f249922].

#LI-BG1

Harvey is an equal opportunity employer and does not discriminate on the basis of race, gender, sexual orientation, gender identity/expression, national origin, disability, age, genetic information, veteran status, marital status, pregnancy or related condition, or any other basis protected by law.

We are committed to providing reasonable accommodations to applicants with disabilities, and requests can be made by emailing accommodations@harvey.ai
```

---

## JPMorgan Chase - VP role  (`jpmc_vp_role`)

# Martech Operations and AI Enablement Lead - Vice President - JPMorgan Chase

**Doran's rating:** Reject.

**Doran's own words:** "I'm not willing to relocate out of the San Mateo area and
looking only for a forty minute commute. But this position is on the other side of
the country and in office only. This also is a very senior leadership role as a VP
title and I wouldn't be comfortable going above a title that is director or 'head'.
I do want to get into more of a leadership capacity, but this is reaching too far."

**Why this is the most valuable anti-example in the set:** the *content* is a strong
archetype match. The title is literally "AI Enablement Lead", it sits in the
Marketing team, the category is "Marketing Strategy", and the duties cover AI
enablement, workflow modernization, and adoption plans. A relevance-only matcher
would rank this near the top of every scan.

It must still fail, on three independent hard gates:

1. **Title band** - "Vice President" exceeds Doran's stated ceiling of Director or
   Head. This is over-reach, not ambition.
2. **Geography** - Wilmington, Delaware is across the country from San Mateo.
3. **Work model** - in-office, which combined with the location means relocation.

So this anchor tests something the four golden examples cannot: that the hard gates
fire *even when relevance is high*. If this posting ever scores above 3.0, the gates
have stopped working and every scan after that is untrustworthy.

Note the freshness contrast too - this was posted 2026-08-06 and is genuinely
current, while Doran's best-matching golden example (Reltio) was already closed.
Recency and quality are independent; the pipeline has to check both.

## Facts as the pipeline parses them

- **URL**: https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/210776632
- **Location**: Wilmington, DE, United States
- **Work model**: On-site
- **Published**: 2026-08-06
- **Category**: Marketing Strategy
- **Salary**: not listed
- **Expected hard-gate rejections**: title band `vice president`; commute far
  beyond the 60-minute limit

## Full posting text

```text
Join the Marketing team!
 As the Martech Operations and AI Enablement Lead in the Marketing team, you will lead a role that is intentionally balanced between Channel Execution and Operations and technology transformation. Approximately half of the role is focused on operating discipline, team enablement, execution quality, controls, capacity, service delivery, and continuous improvement across marketing operations. The remaining focus is on operationalizing Martech platforms, AI-enabled capabilities, workflow modernization, and process efficiency in partnership with Product, Technology, Data, Controls, Channel Execution, and business teams. The role requires working knowledge of Martech tools and platforms, experience running or enabling Martech operations teams, and the ability to connect technology delivery to measurable marketing impact.
 Job responsibilities 
 - Lead Martech operations transformation initiatives while maintaining a strong operating focus across Channel Execution, service delivery, execution quality, controls, and speed to market.
- Operationalize technology capabilities by defining use cases, operating routines, process changes, controls, adoption plans, and measurable outcomes.
- Partner with Product and Technology teams to translate marketing needs into platform requirements, backlog priorities, release readiness, and adoption plans.
- Assess current Martech tools, workflows, data handoffs, and execution processes to identify opportunities for simplification, automation, and efficiency.
- Drive AI enablement opportunities that support productivity, quality assurance, decision support, content or workflow acceleration, and human-in-the-loop controls.
- Lead cross-functional change management across Marketing, Channel Execution, Data, Controls, Risk, Legal, Compliance, Product, and Technology partners.
- Establish governance routines and performance measures to monitor adoption, operational impact, process adherence, and continuous improvement.
- Guide Martech operations and channel execution teams through process transformation, operating model changes, role clarity, training, adoption, and post-launch stabilization.
- Create executive-ready updates that clearly communicate business impact, risks, dependencies, decisions, and next steps.
- Build scalable playbooks, documentation, operating models, and readiness materials that help teams sustain new Martech and AI capabilities.
 
 Required qualifications, capabilities, and skills 
 - Bachelor’s degree in Data Science, Statistics, Information Systems, Marketing, Business, or related field.
- Experience leading Martech operations, marketing technology implementation, digital transformation, campaign operations, workflow automation, or AI enablement initiatives.
- Working knowledge of Martech tools and platforms, including campaign management, workflow, CRM, data activation, decisioning, personalization, marketing automation, Adobe, Segment, Tableau, Excel, SQL, or Python.
- Proven experience in data analytics, customer segmentation, audience strategy, measurement, or data-driven marketing execution.
- Experience improving and operationalizing technology capabilities that impact marketing execution, controls, productivity, operational efficiency, and business outcomes.
- Experience running, supporting, or transforming Martech operations or channel execution teams, including operating routines, service delivery, controls, capacity, quality, and performance management.
- Strong understanding of digital marketing principles, process transformation, change management, operating models, adoption planning, controls, and operational efficiency levers.
- Ability to translate business requirements into technical specifications and distill complex technical problems for non-technical business partners.
- Ability to connect platform capabilities to practical business use cases, process changes, training needs, and measurable impact.
- Team player with ability to build strong cross-business relationships across Product, Technology, Data, Operations, Controls, Risk, Legal, Compliance, and business stakeholders.
- Strong communication skills with the ability to influence, manage, and clearly articulate priorities, risks, decisions, and outcomes to project stakeholders and senior management.
 
 Preferred qualifications, capabilities, and skills 
 - Experience with enterprise marketing platforms, campaign workflow tools, customer data platforms, Salesforce Marketing Cloud or similar marketing automation tools.
- Understanding of responsible AI practices, automation design, governance, data controls, and human oversight in marketing use cases.
- Experience with Agile delivery, product backlog management, release readiness, user acceptance testing, and platform adoption.
- Experience in financial services, regulated industries, or environments with rigorous control and documentation expectations.
- Experience building transformation roadmaps, business cases, executive materials, and operating model recommendations.
```

---
