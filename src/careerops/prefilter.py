"""Deterministic gates, applied before any semantic evaluation happens.

This is what keeps the expensive work small: thousands of raw postings in, ~15-40
candidates out. Everything here is mechanical and explainable -- no judgement
calls, and every rejection records a reason so `cli.py status` can show what was
dropped and why.

Order matters: cheapest and most decisive checks first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from . import commute as commute_mod
from . import config
from .models import WORK_REMOTE
from .normalize import age_days, basing_phrases, clean

# --------------------------------------------------------------- vocabularies

# Doran's archetype has no stable job title -- his four highest-rated postings
# were "AI Marketing Technologist Lead", "Director, AI GTM Strategy &
# Enablement", "Manager, Marketing AI Enablement" and "Marketing Engineer". So
# relevance is scored over the description body, and title is used only to
# exclude.

AI_ENABLEMENT_TERMS: dict[str, float] = {
    "ai enablement": 6.0,
    "ai adoption": 5.0,
    "ai transformation": 4.5,
    "ai strategy": 4.5,
    "marketing ai": 5.5,
    "ai for marketing": 5.5,
    "gtm ai": 5.0,
    "ai operations": 4.0,
    "agentic": 5.0,
    "ai agent": 4.0,
    "ai workflow": 4.0,
    "ai native": 3.0,
    "ai literacy": 4.0,
    "ai champion": 4.0,
    "ai upskilling": 5.0,
    "upskill": 3.0,
    "enablement": 2.0,
    "power user": 3.5,
    "ai tooling": 3.0,
    "ai use case": 3.0,
    "artificial intelligence": 1.5,
    "generative ai": 3.0,
    "genai": 3.0,
    # ---------------------------------------------------------------------
    # Added 2026-08-28, at Doran's request, after the Google "Program Manager,
    # AI and Gemini App Marketing" miss. His instruction: "think about the
    # synonym phrases that would help capture the AI builder or AI architect or
    # AI enablement and AI strategy angles. Since those are worth the most
    # points because they're the most important to me."
    #
    # Every weight below was set from a measurement over 28,812 stored postings:
    # how often the phrase appears corpus-wide, against how often it appears in
    # the 30-40 point near-miss band whose titles are on-archetype. The ratio of
    # those two ("lift") is what separates a real synonym from boilerplate.
    #
    # AI STRATEGY angle. Rare, and strongly concentrated in near misses.
    "ai roadmap": 4.5,          # 0.28% of corpus, 10.9x lift
    "ai vision": 4.0,           # 0.10% of corpus, 16.9x lift
    "ai council": 4.0,          # 0.02% of corpus, 32.7x lift
    "ai opportunities": 3.5,    # 0.13% of corpus, 7.9x lift
    # AI BUILDER angle. "agent-powered" is the rarest and cleanest signal here.
    "agent-powered": 4.5,       # 0.09% of corpus, 43.1x lift
    "ai-powered workflow": 4.0, # 0.95% of corpus, 5.0x lift
    "internal ai": 3.5,         # 0.64% of corpus, 4.8x lift
    "automate workflows": 3.0,
    "automating workflows": 3.0,
    #
    # AI ARCHITECT angle, deliberately held to 3.0 and 2.5 rather than the 4.5+
    # their lift alone would justify.
    #
    # "applied ai" (9.1x lift) and "ai architect" (12.0x) are genuinely Doran's
    # vocabulary, but measured at full weight they pulled 145 new postings over
    # the floor and the top of that list was almost entirely customer-facing
    # solutions-architect roles at AI vendors: OpenAI, Anthropic, Cohere,
    # Snorkel. The 2026-08-12 learned rule already says those are NOT the
    # archetype ("they help the vendor's customers adopt AI rather than enabling
    # an internal organization") and that the prefilter cannot tell them apart.
    # At these weights the same change admits 97, of which two thirds are
    # internal roles -- Chime "Software Engineer, AI Enablement", iFIT "Director
    # of AI, Operations", Match Group "Principal, Applied AI Enablement" -- and
    # a vendor SA role now needs corroborating signal rather than clearing the
    # floor on its job title alone.
    "ai architect": 3.0,
    "applied ai": 3.0,
    "ai deployment": 2.5,
    "ai implementation": 2.5,
}

MARKETING_CONTEXT_TERMS: dict[str, float] = {
    "marketing": 3.0,
    "go-to-market": 3.0,
    "go to market": 3.0,
    "gtm": 2.5,
    "demand generation": 3.0,
    "demand gen": 3.0,
    "growth marketing": 3.0,
    "product marketing": 2.5,
    "brand": 1.5,
    "campaign": 2.0,
    "lifecycle marketing": 2.5,
    "marketing operations": 3.5,
    "marketing ops": 3.5,
    "mops": 2.5,
    "content marketing": 2.0,
    "seo": 1.5,
    "crm": 1.5,
    "marketo": 2.0,
    "hubspot": 1.5,
    "salesforce": 1.0,
    "sales enablement": 2.0,
    "funnel": 1.5,
    "pipeline": 1.0,
    # Added 2026-08-28. Deliberately on the CONTEXT side, not the AI side: these
    # name the function being enabled, and plenty of postings that use them are
    # ordinary sales enablement with no AI in them. Putting them here means they
    # can help a posting clear the floor but can never, on their own, convince
    # _has_both_sides that a role is AI enablement.
    "marketing enablement": 3.5,
    "gtm enablement": 3.0,
    "go-to-market enablement": 3.0,
}

BUILD_TERMS: dict[str, float] = {
    "mcp": 3.0,
    "llm": 2.5,
    "prompt": 2.0,
    "workflow automation": 3.0,
    "automation": 1.5,
    "api": 1.0,
    "integration": 1.0,
    "no-code": 1.5,
    "low-code": 1.5,
    "n8n": 2.5,
    "zapier": 1.5,
    "orchestration": 2.0,
    "human-in-the-loop": 3.5,
    "human in the loop": 3.5,
}

# Company-wide AI enablement roles qualify too -- they just rank slightly lower
# via the scope modifier. Without these terms the prefilter demanded marketing
# context and such roles never reached scoring at all, so the modifier would
# have had nothing to act on. Kept deliberately narrow: these are phrases about
# serving the whole business, not generic corporate filler like
# "cross-functional", which appears in nearly every posting.
ENTERPRISE_CONTEXT_TERMS: dict[str, float] = {
    "company-wide": 3.0,
    "companywide": 3.0,
    "organization-wide": 3.0,
    "across the organization": 3.0,
    "across the company": 3.0,
    "across the business": 2.5,
    "enterprise ai": 3.0,
    "center of excellence": 3.0,
    "business functions": 2.5,
    "every function": 2.5,
    "all functions": 2.5,
    "firm-wide": 3.0,
    "field organization": 2.5,
    "business units": 2.0,
    "functional teams": 2.0,
}

# ------------------------------------------------- TRACK B: growth marketing
#
# The backup list, calibrated on Doran's pre-AI history (Cloudflare Senior
# Growth Marketing Manager, Intuit Senior Marketing Manager). These terms must
# stand on their own -- a growth role with zero AI content is a full track-B
# match, so this vocabulary deliberately shares nothing with the AI side.

# CAPTURE vs CREATION -- the distinction Doran drew on 2026-08-12, and the single
# most important thing to get right in track B:
#
#   "My growth strengths where I would be a strong candidate were more tied
#   towards companies that are looking at web growth for the website channel as a
#   part of the funnel and less about paid campaigns or media or webinars.
#   Usually that stuff in my history was another person managing it, and then the
#   leads from those would hit the website and I was in charge of the
#   optimization of the website to get that traffic to turn into leads. So I was
#   about CAPTURING those leads via the website. Whereas most demand generation
#   is about CREATING the traffic to the website through campaigns."
#
# He owns the conversion half of the funnel, not the traffic half. Weight capture
# terms heavily; keep creation terms low so a pure paid/campaign role cannot
# clear the floor on channel vocabulary alone.

GROWTH_CAPTURE_TERMS: dict[str, float] = {
    "conversion rate optimization": 7.0,
    "conversion optimization": 6.5,
    "website optimization": 6.5,
    "web growth": 6.5,
    "landing page": 6.0,
    "a/b test": 6.0,
    "ab test": 5.0,
    "experimentation": 5.5,
    "cro": 5.0,
    "conversion rate": 4.5,
    "lead capture": 5.0,
    "funnel conversion": 5.0,
    "on-site": 3.0,
    "personalization": 3.5,
    "user experience": 3.0,
    "web analytics": 4.0,
    "site performance": 3.5,
    "seo": 4.0,
    "answer engine": 4.5,
    "aeo": 4.0,
}

GROWTH_CORE_TERMS: dict[str, float] = {
    "growth marketing": 5.0,
    "growth strategy": 4.0,
    "funnel": 4.0,
    "customer acquisition": 3.5,
    "product-led growth": 4.0,
    "plg": 3.5,
    "lifecycle marketing": 3.0,
    "retention": 2.5,
    "activation": 2.5,
}

# Traffic CREATION -- real growth vocabulary, but not where Doran's proof lives.
# Deliberately low weights so a pure campaign/paid seat needs capture signal too.
GROWTH_CREATION_TERMS: dict[str, float] = {
    "demand generation": 2.5,
    "demand gen": 2.5,
    "paid media": 1.5,
    "paid acquisition": 1.5,
    "paid search": 1.5,
    "paid social": 1.5,
    "performance marketing": 2.0,
    "media buying": 1.0,
    "campaign management": 1.0,
    "programmatic": 1.0,
    "webinar": 0.5,
    "field marketing": 1.0,
    "events": 0.5,
    "sem": 1.5,
    "pipeline generation": 2.0,
    # Added 2026-08-26. Zapier's "Sr. Manager, Performance Marketing" mentioned
    # account-based marketing nine times and the system saw none of them, so a
    # role built on ABM and paid media scored 4.75. Doran: "I don't really talk
    # about account based marketing (ABM) or Paid Media as a strong suit."
    "account-based marketing": 1.5,
    "account based marketing": 1.5,
}

# Signals that a role is predominantly traffic creation rather than capture.
CREATION_HEAVY = re.compile(
    r"\b(paid search|paid social|programmatic|media buying|ad platforms?|"
    r"campaign management|campaign workflows?|media spend|digital media|"
    r"budget pacing|multi-?channel budgets?|ad formats?|affiliate|influencer|"
    r"webinars?|field marketing|events? marketing|channel strategy|"
    r"demand generation|demand gen|integrated campaigns?|"
    # ABM is traffic creation by another name: outbound target-account
    # campaigns, not the website conversion work Doran owns.
    r"account.based marketing|abm)\b",
    re.IGNORECASE,
)
CAPTURE_SIGNALS = re.compile(
    r"\b(conversion rate optimi[sz]ation|website optimi[sz]ation|landing page|"
    r"a/b test|ab test|experimentation|web growth|on-?site experience|"
    r"funnel conversion|lead capture|site performance|answer engine|"
    r"web pages?|webpages?|website conversion|organic search|\bseo\b|"
    r"conversion flow|conversion logic|website analytics)\b",
    re.IGNORECASE,
)

# The title is a strong prior. "Director of Demand Generation" is definitionally
# traffic creation; "Senior Marketing Manager, Website Growth" is capture.
CREATION_TITLE = re.compile(
    r"\b(demand gen\w*|performance marketing|paid|media|campaign|"
    r"field marketing|acquisition marketing|events?)\b", re.IGNORECASE)
CAPTURE_TITLE = re.compile(
    r"\b(web|website|conversion|optimi[sz]ation|experimentation|cro|seo)\b",
    re.IGNORECASE)

GROWTH_MEASUREMENT_TERMS: dict[str, float] = {
    "conversion rate": 3.0,
    "attribution": 3.0,
    "analytics": 2.0,
    "cac": 2.5,
    "ltv": 2.5,
    "roas": 2.5,
    "pipeline": 2.0,
    "mql": 2.5,
    "sql": 1.0,
    "cohort": 2.0,
    "dashboard": 1.5,
    "marketo": 3.0,
    "hubspot": 2.5,
    "salesforce": 2.0,
    "google analytics": 3.0,
    "adobe analytics": 3.0,
    "optimizely": 3.0,
    "segment": 1.5,
}

# B2B SaaS is where Doran's proof lives; B2C/DTC is transferable but not direct.
# Detected here so the scorer can apply the right candidate-strength modifier.
B2B_SIGNALS = re.compile(
    r"\b(b2b|saas|enterprise|mid-?market|smb|abm|account.based|"
    r"sales.qualified|pipeline|demand gen|mql|sdr|crm|salesforce|marketo)\b",
    re.IGNORECASE,
)
B2C_SIGNALS = re.compile(
    r"\b(b2c|d2c|dtc|direct.to.consumer|e-?commerce|ecommerce|shopify|"
    r"subscription box|consumer brand|retail|merchandis\w+|shopper)\b",
    re.IGNORECASE,
)
# A growth role that asks for AI fluency does not become a better ROLE, but it
# does make Doran a stronger CANDIDATE -- his distinction, scored as a bonus.
AI_FLUENCY_REQUESTED = re.compile(
    r"\b(ai.fluen\w+|ai.literate|ai.literacy|comfortable with ai|"
    r"experience with ai|ai.powered|ai tools|leverage ai|using ai|"
    r"generative ai|genai|llm|prompt)\b",
    re.IGNORECASE,
)

GROWTH_TITLE_BONUS: dict[str, float] = {
    "growth marketing": 6.0,
    "demand generation": 6.0,
    "growth manager": 5.0,
    "growth lead": 5.0,
    "performance marketing": 5.0,
    "lifecycle marketing": 4.5,
    "web growth": 5.0,
    "acquisition": 4.0,
    "marketing manager": 2.5,
    "digital marketing": 3.5,
}

# Calibrated against 15,460 live postings. Growth vocabulary is far more common
# than AI-enablement vocabulary -- nearly every marketing posting mentions
# "funnel" or "analytics" -- so this floor sits much higher than track A's.
# In that corpus the growth scores run: median 46, p75 63, max 106, with the
# clearly-relevant roles (OpenAI Paid & Demand Channels 106, Roblox Growth
# Marketing Lead 101, Webflow Website Growth 97) all well above 80. A floor of
# 65 keeps roughly the top quartile and holds the backup queue to a size worth
# reading, which matters because track B only ever surfaces 5 results.
GROWTH_RELEVANCE_FLOOR = 65.0


TITLE_BONUS_TERMS: dict[str, float] = {
    "marketing engineer": 6.0,
    "marketing technologist": 6.0,
    "gtm engineer": 5.0,
    "ai enablement": 6.0,
    "marketing ai": 6.0,
    "ai marketing": 6.0,
    "growth engineer": 3.0,
    "marketing technology": 4.0,
    "ai operations": 4.0,
    "ai program": 3.0,
    # Added 2026-08-25. These lift a genuine archetype title over the relevance
    # floor without moving the floor itself, which is the safer of the two ways
    # to recover a near-miss. "Director, AI Transformation" scored 39.0 against
    # a floor of 40.0 and was dropped for one point.
    "ai transformation": 5.0,
    "ai strategy": 5.0,
    "ai adoption": 5.0,
    "ai solutions": 4.0,
    "martech": 5.0,
    "ai capabilities": 4.0,
    "agentic": 4.0,
}

# Calibrated against 2,033 live postings from six companies. That corpus has a
# median relevance of 8 and a p90 of 25, while Doran's four golden postings score
# 64 (Plaid), 80 (DoorDash), 92 (Harvey) and 94 (Figma's live Marketing
# Engineer). A floor of 40 sits well above the noise while leaving 24 points of
# headroom under the weakest golden -- a false negative here silently discards a
# good job, so we err permissive and let the rubric do the fine judgement.
RELEVANCE_FLOOR = 40.0

# ------------------------------- a marketing role wearing AI vocabulary
#
# Vercel's "Growth Marketing Manager, Discoverability" says "agent" fourteen
# times and says enablement, upskill and train exactly zero times. Those agents
# are the AUDIENCE -- AI assistants that might recommend Vercel -- not something
# the job builds. It cleared the AI track on vocabulary alone.
#
# Doran, 2026-08-28: "your scoring or checks are getting confused by some of the
# AI key phrases in here without understanding what the job really is about at
# its core, which is AEO, not AI that I am interested in... This falls under the
# marketing list."
#
# The separator is how much MARKETING vocabulary a posting carries relative to
# its AI vocabulary. Measured against his own verdicts:
#
#   MongoDB "Answer Engine Optimization Lead"  2.6x  -- he declined it
#   Vercel  "Discoverability"                  2.1x  -- "the marketing list"
#   Apollo  "Partner Growth Manager"           1.8x  -- "should score less"
#   Agiloft "Director, Global Campaigns"       1.2x  -- he asked to KEEP it
#   Freshworks "GTM Engineer"                  0.6x  -- a great fit
#
# So 1.6 sits in the gap between the roles he rejects and the one he defended.
# A posting over it keeps its growth track and loses its AI track, which lands
# it in the marketing bucket where the bar is the full 4.0 rather than 3.75.
# This never removes a posting from the report -- it moves it to a harder list.
MARKETING_IN_AI_CLOTHING = 1.6


# ---------------------------- the Director rule, made mechanical
#
# Doran, 2026-08-14: "if the title is director or VP, then they are definitely
# going to want you to specialize. So it won't really match me unless it's a
# director or VP level that is a perfect match to my growth marketing web
# experience or to my AI experience at Cloudflare. I think those are the only
# two angles I would probably get an interview for a director or VP level title."
#
# That was written as a rubric instruction in August 2026 and reinforced two
# weeks later, and it was still not applied: run 25 scored Freshworks "Director,
# GTM Systems Architecture" at a FULL 5.0 on seniority -- a Director title in a
# discipline he cannot claim. Meanwhile Gilead (3.0), Agiloft (3.5) and Life360
# (4.5, correctly, because growth and web IS his) were all scored right.
#
# So the rule works when it is remembered and fails when it is not. The rules
# that hold in this codebase are the mechanical ones -- the evidence cap and the
# fit-summary check -- so this becomes a cap rather than a reminder.
#
# Doran, 2026-08-28, on why: "you should look at your past attempts so that you
# can figure out the proper way to make this stick."
SENIOR_TITLE = re.compile(
    r"\b(director|head of|head,|vice president|vp|svp|evp|chief)\b", re.IGNORECASE)

# The only two disciplines he clears at that level. The block note has to name
# one of them, in the same spirit as quoting the posting for the evidence cap.
CLAIMABLE_SPECIALISMS = re.compile(
    r"(ai enablement|ai transformation|ai strategy|ai adoption|"
    # "growth and web" is how the two are usually written together, so match
    # each word rather than a fixed phrase. A Director note for a discipline he
    # cannot claim -- field marketing, brand, demand generation, systems
    # architecture -- contains neither word, which is the point.
    r"\bgrowth\b|\bweb\b|website|conversion|\bcro\b)", re.IGNORECASE)

SENIORITY_CAP_WITHOUT_SPECIALISM = 3.5


def seniority_cap(title: str, block_b_note: str) -> float | None:
    """Cap for dimension 3 when a senior title names no claimable specialism.

    Returns None when no cap applies.
    """
    if not SENIOR_TITLE.search(title or ""):
        return None
    if CLAIMABLE_SPECIALISMS.search(block_b_note or ""):
        return None
    return SENIORITY_CAP_WITHOUT_SPECIALISM

# ------------------------------------------------- the archetype as a sentence
#
# Added 2026-08-28, from Google's "Program Manager, AI and Gemini App Marketing".
# It scored 36.5 against the 40.0 floor and was never read, despite its stated
# objective being: "your main objective is to equip marketers with the tools and
# processes to move with greater agility and velocity." That IS the archetype.
# It scored nothing because the vocabulary above matches phrases, and the highest
# scoring ones -- "ai enablement" 6.0, "marketing ai" 5.5, "ai adoption" 5.0 --
# are buzzwords this posting simply does not use.
#
# Doran, on being shown why: "this is a good example of a role that can point out
# phrases we should add to our scoring points system, so that it does pass. I
# know the pay is low, but that's the only reason why it should get knocked."
# The principle: a posting should be rejected for what the JOB is, never for
# which words it happened to choose.
#
# A regex rather than more dict entries because the literal variants are each
# vanishingly rare -- "equip marketers" appears once in 28,812 postings, "enable
# marketers" twice -- while the FAMILY (equip/enable/empower/upskill + the
# marketing org) appears 52 times, which is 0.18% and high precision.
EQUIPS_MARKETERS = re.compile(
    r"\b(equip|enabl|empower|upskill)\w*\s+(our\s+|the\s+|their\s+|your\s+)?"
    r"(marketers|marketing team|marketing org\w*|marketing organi[sz]ation|"
    r"gtm team|go-to-market team)",
    re.IGNORECASE,
)
EQUIPS_MARKETERS_WEIGHT = 5.0
EQUIPS_MARKETERS_MARK = "equips-marketers"

# A title can name both AI and marketing without ever forming a phrase the
# literal list contains. "Program Manager, AI and Gemini App Marketing" holds
# both words, but "and Gemini App" sits between them, so "ai marketing" never
# appears and the title earned a bonus of zero. 108 of 28,812 titles match both
# tokens (0.37%), and they include two of Doran's own golden postings.
#
# Awarded ONLY when no literal title term fired, so "AI Marketing Technologist
# Lead" keeps its existing 6.0 rather than collecting this on top.
TITLE_AI_TOKEN = re.compile(
    r"(?:^|[^a-z])(ai|a\.i\.|artificial intelligence|genai|generative ai|"
    r"agentic|llm)(?:[^a-z]|$)",
    re.IGNORECASE,
)
TITLE_MARKETING_TOKEN = re.compile(r"\b(marketing|go.to.market|gtm)\b", re.IGNORECASE)
TITLE_SPLIT_WEIGHT = 4.0
TITLE_SPLIT_MARK = "title:ai+marketing"

# ------------------------------------------------ teaching non-builders to build
#
# Added 2026-08-28. Doran named this outright as the thing he is looking for,
# on Apple's "Agentic AI Product Manager, Platform - Sales":
#
#   "A key thing I'm looking for is teaching non-technical people to build
#   agents. The fact that it says 'teams across our worldwide sales organization
#   build, run, and scale AI agents', is exactly why it's a strong fit for my
#   skill set and archetype that I'm looking for."
#
# This is the power-user multiplication model stated as a duty rather than as a
# buzzword, and no term in the vocabulary above caught it. Requires the AI or
# agent context in the same sentence, so ordinary "enable non-technical users to
# self-serve reports" does not qualify: 67 of 28,812 postings match (0.23%).
NONTECHNICAL_BUILDER = re.compile(
    r"(non.?technical|business users?|citizen developers?)[^.]{0,200}"
    r"\b(build|create|ship|deploy|run|scale|author)\w*\b[^.]{0,80}"
    r"(agent|ai|automation|workflow)"
    r"|(agent|ai|automation|workflow)[^.]{0,120}"
    r"\b(build|create|ship|deploy|run|scale|author)\w*\b[^.]{0,120}"
    r"(non.?technical|business users?|citizen developers?)",
    re.IGNORECASE,
)
NONTECHNICAL_BUILDER_WEIGHT = 4.5
NONTECHNICAL_BUILDER_MARK = "teaches-nontechnical-to-build"

# ------------------------------------------------------- sales as a business org
#
# Added 2026-08-28. _has_both_sides demands an AI signal AND a business-context
# signal, and the context side only ever recognised marketing or company-wide
# language. A role serving the SALES org named neither, so Apple's posting --
# 48.0 points, well clear of the 40.0 floor, and the strongest agentic-enablement
# content in the set -- was blocked outright rather than ranked lower.
#
# Doran: "the fact that it's sales only isn't necessarily a hard blocker, but
# rather, maybe it should make the scoring system slightly hurt to lose a point
# or points. But a blocker is too harsh because marketing and sales are still
# somewhat adjacent roles."
#
# So this UNBLOCKS the gate and is deliberately worth ZERO points. The deduction
# he asked for already exists downstream as the `sales_field` scope modifier
# (-0.30 in config/scoring.yml), which is the right place for it: it prices how
# strong a candidate he is, not how relevant the posting is.
#
# Worth nothing on purpose. Scored at even 2.0 these terms admitted 109 extra
# postings, nearly all of them ordinary sales jobs -- Channel Sales Director,
# Sales Operations Analyst -- because the sales vocabulary itself was pushing
# marginal roles over the floor. At zero, the same change admits 2, and a sales
# role still has to earn the floor on genuine AI-enablement content.
SALES_CONTEXT = re.compile(
    r"\b(sales organi[sz]ation|sales org|worldwide sales|channel sales|"
    r"revenue organi[sz]ation|revenue team|sales team|field team|sellers|"
    r"commercial team|field organi[sz]ation)\b",
    re.IGNORECASE,
)
SALES_CONTEXT_MARK = "sales-context"

# --------------------------------------------------------------- title filters

# Engineering disciplines Doran is not a fit for. Deliberately specific: a bare
# "engineer" must NOT be excluded, because "Marketing Engineer" is one of his
# best-rated roles.
IRRELEVANT_TITLE = re.compile(
    r"\b("
    r"software engineer|backend engineer|back-end engineer|frontend engineer|"
    r"front-end engineer|full.?stack engineer|data engineer|ml engineer|"
    r"machine learning engineer|infrastructure engineer|platform engineer|"
    r"security engineer|network engineer|qa engineer|test engineer|"
    r"site reliability|devops|hardware|firmware|embedded|silicon|asic|"
    r"research scientist|data scientist|"
    # Consumer-product engineering hits growth vocabulary ("retention",
    # "activation", "growth") hard enough to clear track B's floor. Perplexity's
    # "Member of Technical Staff (Android Engineer)" scored 68.
    r"member of technical staff|android engineer|ios engineer|mobile engineer|"
    r"computer vision|systems engineer, |engineer, computer|"
    r"nurse|physician|therapist|clinician|pharmacist|dental|"
    r"driver|warehouse|forklift|technician|custodian|janitor|"
    r"barista|cook|chef|server|bartender|cashier|retail associate|"
    r"attorney|paralegal|counsel|accountant|auditor|bookkeeper|"
    r"account executive|sales development|sdr|bdr|account manager|"
    r"customer success manager|support specialist|"
    r"intern|internship|apprentice|contractor|temporary"
    r")\b",
    re.IGNORECASE,
)

# High-precision description killers. Kept short on purpose -- a false negative
# here silently discards a good job, which is worse than one extra evaluation.
KILLER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("requires_phd", re.compile(r"\bph\.?\s?d\.?\b[^.]{0,60}\b(required|require)\b", re.I)),
    ("phd_in_field", re.compile(r"\bph\.?\s?d\.?\s+in\s+(computer science|machine learning|statistics|physics|mathematics)", re.I)),
    ("trains_models", re.compile(r"\b(train|training|pretrain|fine.?tun\w+)\s+(foundation|large language|deep learning)\s+models?\b", re.I)),
    ("publishes_research", re.compile(r"\bpublish(ing|ed)?\s+(research|papers?)\b|\bneurips\b|\bicml\b", re.I)),
    ("distributed_systems", re.compile(r"\bdistributed systems at scale\b|\bkubernetes\b[^.]{0,40}\brequired\b", re.I)),
    ("carries_quota", re.compile(r"\b(sales quota|carry a quota|quota.carrying|book of business|close deals)\b", re.I)),
    ("relocation_required", re.compile(r"\b(relocation is required|must relocate|required to relocate)\b", re.I)),
    ("oncall", re.compile(r"\bon.?call rotation\b", re.I)),
    # NOTE: killers with a false-positive guard are listed in KILLER_EXEMPTIONS
    # below. Add the guard there rather than weakening the pattern here.
]

# A PhD named as ONE OPTION among lower degrees is not a PhD requirement.
#
# NVIDIA's "Senior Architect, Agentic AI for Marketing" -- Santa Clara,
# $224k-$356.5k, explicit human-in-the-loop framing, the single closest role to
# Doran's archetype found on 2026-08-27 -- opens its requirements with "A BS,
# MS, or PhD in Computer Science, AI/ML, Electrical Engineering, Data Science, a
# related technical field, or equivalent experience." A bachelor's satisfies
# that, and "or equivalent experience" satisfies it without a degree at all, but
# phd_in_field fired on the phrase and threw the posting out before scoring.
#
# The guard looks for a lower degree, or an equivalent-experience escape hatch,
# in the same sentence. A genuine "PhD in Machine Learning required" has
# neither, so the killer still fires on it.
_DEGREE_ALTERNATIVES = re.compile(
    r"\b(b\.?s\.?c?|b\.?a\.?|m\.?s\.?c?|m\.?a\.?|bachelor\w*|master\w*|"
    r"undergraduate)\b[^.]{0,120}?\bph\.?\s?d",
    re.IGNORECASE,
)
_EQUIVALENT_EXPERIENCE = re.compile(
    r"\bph\.?\s?d\b[^.]{0,160}\b(or\s+)?equivalent\s+(practical\s+)?experience\b",
    re.IGNORECASE,
)


# A PhD listed under "preferred", "nice to have" or "a plus" is not a
# requirement either. Bounded to the same sentence so a "required" clause
# elsewhere in the posting cannot be excused by a "preferred" one.
_PHD_PREFERRED = re.compile(
    r"\bph\.?\s?d\b[^.]{0,120}\b(preferred|a plus|nice.to.have|desirable|"
    r"advantageous|bonus)\b"
    r"|\b(preferred|nice.to.have|desirable)\b[^.]{0,120}\bph\.?\s?d\b",
    re.IGNORECASE,
)


def _phd_is_optional(description: str) -> bool:
    """True when the PhD is an alternative or a preference, not a requirement."""
    return bool(_DEGREE_ALTERNATIVES.search(description)
                or _EQUIVALENT_EXPERIENCE.search(description)
                or _PHD_PREFERRED.search(description))


# name -> predicate. A killer whose name appears here is skipped when its
# predicate says the match is a false positive.
KILLER_EXEMPTIONS: dict[str, Callable[[str], bool]] = {
    "phd_in_field": _phd_is_optional,
    "requires_phd": _phd_is_optional,
}

_NON_US = re.compile(
    r"\b(india|united kingdom|london|dublin|ireland|germany|berlin|munich|"
    r"france|paris|spain|madrid|barcelona|netherlands|amsterdam|poland|"
    r"krakow|warsaw|singapore|japan|tokyo|australia|sydney|melbourne|"
    r"canada|toronto|vancouver|montreal|brazil|sao paulo|mexico|israel|"
    r"tel aviv|emea|apac|latam|philippines|manila|romania|bucharest|"
    r"portugal|lisbon|sweden|stockholm|switzerland|zurich|italy|milan)\b",
    re.IGNORECASE,
)
_US_MARKER = re.compile(
    r"\b(united states|usa|u\.s\.|\bus\b|remote.{0,10}us|nationwide|"
    r"anywhere in the us)\b",
    re.IGNORECASE,
)


@dataclass
class PrefilterResult:
    passed: bool
    reason: str = ""
    relevance: float = 0.0
    matched_terms: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    # Which list(s) this posting is a candidate for. A posting can qualify for
    # both; the report shows it once, in track A.
    tracks: list[str] = field(default_factory=list)
    growth_relevance: float = 0.0
    audience: str = ""            # b2b_saas_enterprise | b2c_dtc_ecommerce | ...
    ai_fluency_requested: bool = False


def score_growth_relevance(title: str, description: str) -> tuple[float, list[str]]:
    """Track B relevance. Deliberately independent of any AI vocabulary."""
    body = clean(description).lower()
    title_l = clean(title).lower()
    total = 0.0
    matched: list[str] = []

    for terms in (GROWTH_CAPTURE_TERMS, GROWTH_CORE_TERMS,
                  GROWTH_CREATION_TERMS, GROWTH_MEASUREMENT_TERMS):
        for term, weight in terms.items():
            count = body.count(term)
            if count:
                total += weight * min(count, 3)
                matched.append(term)

    for term, weight in GROWTH_TITLE_BONUS.items():
        if term in title_l:
            total += weight
            matched.append(f"title:{term}")

    return total, matched


def classify_audience(title: str, description: str) -> str:
    """B2B SaaS is direct proof for Doran; B2C/DTC is transferable only."""
    text = f"{clean(title)} {clean(description)}"
    b2b = len(B2B_SIGNALS.findall(text))
    b2c = len(B2C_SIGNALS.findall(text))
    if b2c > b2b and b2c >= 2:
        return "b2c_dtc_ecommerce"
    if b2b:
        return "b2b_saas_enterprise"
    return "b2b_other"


def _has_growth_core(matched: list[str]) -> bool:
    """Require a real growth signal, not just analytics vocabulary."""
    core = (set(GROWTH_CAPTURE_TERMS) | set(GROWTH_CORE_TERMS)
            | set(GROWTH_CREATION_TERMS)
            | {f"title:{t}" for t in GROWTH_TITLE_BONUS})
    return bool(set(matched) & core)


def classify_funnel_side(description: str, title: str = "") -> str:
    """Is this role about CAPTURING leads on the website, or CREATING traffic?

    Doran owns capture -- CRO, landing pages, A/B testing, turning arriving
    traffic into leads. Campaign, paid and media management is the creation half
    and was somebody else's job in his history. Returns the modifier key.

    Calibrated against his own numbers: Twilio "Director of Demand Generation"
    must land heavy (he said "maybe like 4"), Roblox "Growth Marketing Manager
    Lead" must land mixed (he said 4.62 was "slightly too high"), and Linear,
    which owns web pages and search alongside paid, must stay balanced.
    """
    text = clean(description)
    # DISTINCT signals, not occurrences. One capture word repeated three times
    # ("experimentation") was outweighing two genuinely different campaign duties
    # in Roblox's posting and hiding a real deduction Doran cares about.
    creation = len({m.lower() for m in CREATION_HEAVY.findall(text)})
    capture = len({m.lower() for m in CAPTURE_SIGNALS.findall(text)})

    # A creation-side title with no capture counterpart shifts the verdict one
    # level toward creation -- the title states the job's centre of gravity more
    # reliably than a body-text keyword count.
    title_creation = bool(CREATION_TITLE.search(title or ""))
    title_capture = bool(CAPTURE_TITLE.search(title or ""))
    if title_creation and not title_capture:
        creation += 2

    if creation >= 4 and creation > capture:
        return "campaign_creation_heavy"
    if creation >= 2 and creation > capture:
        return "campaign_creation_mixed"
    return "capture_balanced"


def _field(posting, name, default=None):
    """Read a field from either a Posting dataclass or a sqlite3.Row.

    Rows expose columns by subscript, not attribute, so a bare getattr silently
    returned the default for every field and made the whole prefilter pass on
    empty strings. The Posting model calls the work-model field
    ; the database column is .
    """
    value = getattr(posting, name, None)
    if value is not None:
        return value
    try:
        return posting[name]
    except (TypeError, KeyError, IndexError):
        return default


def _reject_bands(track: str | None = None) -> list[str]:
    profile = config.profile()
    if track:
        override = (profile.get("track_overrides", {}) or {}).get(track, {})
        if override.get("reject_title_bands"):
            return override["reject_title_bands"]
    return profile.get("hard_gates", {}).get("reject_title_bands", [])


# "CRO" is two different jobs. As a title band it means Chief Revenue Officer,
# which is over-reach. In a marketing title it means conversion rate
# optimization, which is track B's core capture vocabulary -- prefilter scores
# "cro" at 5.0 under GROWTH_CAPTURE_TERMS. The band check killed Cresta's
# "Growth Marketing Manager, Web & CRO", exactly the archetype it was meant to
# protect. When the title carries conversion vocabulary, CRO is not a C-suite.
_CRO_IS_CONVERSION = re.compile(
    r"(conversion|optimi[sz]ation|\bweb\b|website|landing page|experimentation|"
    r"a/b test|growth marketing)",
    re.IGNORECASE,
)


# A bare C-suite acronym in a trailing comma clause names the ORG the role
# serves, not the role's own rank: "AI Transformation Owner, CRO" is an owner
# inside the Chief Revenue Officer's organization. That posting is a calibration
# anchor scoring 4.53 AND one Doran applied to, and the title gate was throwing
# it out before it could be scored.
#
# Only the acronyms, and only spelled exactly, and only in the trailing clause.
# A spelled-out band is always a band -- JPMorgan's "Martech Operations and AI
# Enablement Lead - Vice President" is the anti-example this must never let in.
_ORG_SUFFIX = re.compile(
    r"^(cro|cmo|cto|coo|cio)( org| organi[sz]ation| office| team)?$",
    re.IGNORECASE,
)


def _band_is_org_scope(title: str, band: str) -> bool:
    if band.lower() not in {"cro", "cmo", "cto", "coo", "cio"}:
        return False
    head, sep, tail = title.rpartition(",")
    if not sep or not _ORG_SUFFIX.match(tail.strip()):
        return False
    # Only when the part before the comma is not itself a rejected band --
    # "VP, CMO" is still a VP.
    return _title_band_rejected(head, _NO_RECURSION) is None


_NO_RECURSION = "__scope_check__"


def _title_band_rejected(title: str, track: str | None = None) -> str | None:
    cleaned = clean(title)
    lowered = f" {cleaned.lower()} "
    for band in _reject_bands(None if track == _NO_RECURSION else track):
        name = str(band).lower()
        if not re.search(rf"\b{re.escape(name)}\b", lowered):
            continue
        if name == "cro" and _CRO_IS_CONVERSION.search(cleaned):
            continue
        if track != _NO_RECURSION and _band_is_org_scope(cleaned, name):
            continue
        return str(band)
    return None


def _growth_title_rejected(title: str) -> str | None:
    """Track B has a narrower ceiling: Senior Manager to Director, no Head-of."""
    return _title_band_rejected(title, config.TRACK_GROWTH)


def score_relevance(title: str, description: str) -> tuple[float, list[str]]:
    """Content-based relevance. Title contributes a bonus but is never the gate."""
    body = f"{clean(description)}".lower()
    title_l = clean(title).lower()
    total = 0.0
    matched: list[str] = []

    def tally(terms: dict[str, float], haystack: str, cap: int = 3) -> None:
        nonlocal total
        for term, weight in terms.items():
            count = haystack.count(term)
            if count:
                total += weight * min(count, cap)
                matched.append(term)

    tally(AI_ENABLEMENT_TERMS, body)
    tally(MARKETING_CONTEXT_TERMS, body)
    tally(ENTERPRISE_CONTEXT_TERMS, body)
    tally(BUILD_TERMS, body)

    # The archetype stated as a sentence rather than as a keyword.
    if EQUIPS_MARKETERS.search(body):
        total += EQUIPS_MARKETERS_WEIGHT
        matched.append(EQUIPS_MARKETERS_MARK)
    if NONTECHNICAL_BUILDER.search(body):
        total += NONTECHNICAL_BUILDER_WEIGHT
        matched.append(NONTECHNICAL_BUILDER_MARK)
    # Recorded, never scored -- it exists to satisfy the both-sides gate only.
    if SALES_CONTEXT.search(body):
        matched.append(SALES_CONTEXT_MARK)

    for term, weight in TITLE_BONUS_TERMS.items():
        if term in title_l:
            total += weight
            matched.append(f"title:{term}")

    # A split AI-and-marketing title, awarded only when no literal title term
    # already fired, so a title is never paid twice for the same fact.
    if (not any(m.startswith("title:") for m in matched)
            and TITLE_AI_TOKEN.search(title_l)
            and TITLE_MARKETING_TOKEN.search(title_l)):
        total += TITLE_SPLIT_WEIGHT
        matched.append(TITLE_SPLIT_MARK)

    return total, matched


def _has_both_sides(matched: list[str]) -> bool:
    """Require a genuine AI-enablement signal AND a business-context signal.

    The business context can be marketing (the ideal) or company-wide enablement.
    Requiring marketing specifically would filter out generalized AI enablement
    roles before they were ever scored -- but those still qualify for Doran, just
    at a slightly lower rank via the scope modifier.
    """
    ai_side = (set(AI_ENABLEMENT_TERMS)
               | {f"title:{t}" for t in TITLE_BONUS_TERMS}
               # Both added 2026-08-28. "equip marketers with the tools" is an
               # AI-enablement statement even when the word "AI" is elsewhere in
               # the posting, and a title naming both AI and marketing is the
               # same signal the literal title terms carry.
               | {EQUIPS_MARKETERS_MARK, TITLE_SPLIT_MARK,
                  # Teaching non-technical people to build agents is an
                  # AI-enablement duty whatever org it sits in.
                  NONTECHNICAL_BUILDER_MARK})
    # Sales counts as a business audience. It is scored at zero and ranked down
    # later by the sales_field scope modifier, but it is no longer a blocker.
    context_side = (set(MARKETING_CONTEXT_TERMS) | set(ENTERPRISE_CONTEXT_TERMS)
                    | {SALES_CONTEXT_MARK})
    hits = set(matched)
    return bool(hits & ai_side) and bool(
        (hits & context_side)
        or any(m.startswith("title:") and "marketing" in m for m in hits)
    )


# Bay Area city names are not unique. Belmont is also in Massachusetts,
# Newark in New Jersey, Richmond in Virginia, Dublin in Ohio, Concord in New
# Hampshire. So a bare city name is not enough -- what follows it decides.
#
# Judged per city rather than per string. An earlier version bailed out of the
# whole string whenever it saw any non-California state, which killed Gong's
# 'GTM AI Architect' -- listed as 'Austin | Chicago | New York City | Salt Lake
# City | San Francisco'. That posting names San Francisco outright; the New
# York in the same list is a different office, not evidence against it.
_CA_AFTER = r'^[,]?\s*(ca|calif|california)\b'
# A state directly after the city means the city belongs to that state.
# Two-letter codes only count after a comma -- IN, OR, ME, OK, HI, LA, DE, ID,
# CO and PA are all ordinary English words.
_STATE_AFTER = re.compile(
    r'^,\s*(?:al|ak|az|ar|co|ct|de|fl|ga|hi|id|il|in|ia|ks|ky|la|me|md|ma|mi|mn|ms|mo|mt|ne|nv|nh|nj|nm|ny|nc|nd|oh|ok|or|pa|ri|sc|sd|tn|tx|ut|vt|va|wa|wv|wi|wy|dc)\b|^[,]?\s*(?:alabama|alaska|arizona|arkansas|colorado|connecticut|delaware|florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|massachusetts|michigan|minnesota|mississippi|missouri|montana|nebraska|nevada|new hampshire|new jersey|new mexico|new york|north carolina|north dakota|ohio|oklahoma|oregon|pennsylvania|rhode island|south carolina|south dakota|tennessee|texas|utah|vermont|virginia|washington|west virginia|wisconsin|wyoming)\b',
    re.IGNORECASE,
)
_CA_MARKER = re.compile(_CA_AFTER, re.IGNORECASE)
# Punctuation after a city means the next thing is a separate item -- another
# office, a site code, a note. The city stands on its own.
_SEPARATOR_AFTER = re.compile(r'^[\s]*($|[|;/,)(\-])')
# Words that can follow a city without changing which city it is.
_HARMLESS_AFTER = re.compile(
    r'^\s*(bay area|area|metro|region|office|offices|hq|headquarters|usa|us|united states|remote|hybrid|or|and)\b',
    re.IGNORECASE,
)


def reachable_cities_in(text: str | None) -> list[tuple[str, int]]:
    """Every commutable city named anywhere in `text`, nearest first.

    ATS location strings are not addresses, they are decorated free text:
    "CA - San Francisco" (reversed), "San Mateo - Bovet" (a building code),
    "San Francisco Bay Area" (a region), "Denver, CO; New York City, NY;
    San Francisco, CA" (a list whose Bay Area office is last). `parse_location`
    picks one city out of that and is wrong often enough to matter -- an Asurion
    role five minutes from Doran's house was rejected as "unknown location"
    because the raw string was "San Mateo - Bovet".

    So the raw string gets read for city names directly, the same way
    alternate_base_cities already reads the posting body.

    Bay Area city names are NOT unique, which is the trap here: there is a
    Belmont in Massachusetts, a Newark in New Jersey, a Richmond in Virginia and
    a Dublin in Ohio. Matching on the name alone turns "Austin, TX (Belmont
    Campus)" into a ten-minute commute. So a match is dropped when the string
    puts it in a state that is not California -- either right after the city, or
    anywhere in a string that never mentions California at all.
    """
    known = (config.commute_table().get("cities", {}) or {})
    limit = config.profile().get("hard_gates", {}).get("max_commute_minutes", 60)
    lowered = (text or "").lower()
    if not lowered:
        return []

    found: dict[str, int] = {}
    for city, minutes in known.items():
        if minutes > limit:
            continue
        name = city.lower()
        match = re.search(rf"\b{re.escape(name)}\b", lowered)
        if not match:
            continue
        after = lowered[match.end():match.end() + 40]
        # "San Francisco, CA" -- settled, keep it.
        if _CA_MARKER.match(after):
            found[city] = minutes
            continue
        # "Newark, NJ" is the New Jersey one even when a California office is
        # named elsewhere in the same string.
        if _STATE_AFTER.match(after):
            continue
        # A separator or a harmless word means the city stands alone. Anything
        # else is a noun attached to it -- "(Belmont Campus)" in an Austin
        # posting, "Belmont St" in a Boston one -- and is not the city at all.
        if _SEPARATOR_AFTER.match(after) or _HARMLESS_AFTER.match(after):
            found[city] = minutes
    return sorted(found.items(), key=lambda kv: kv[1])


def alternate_base_cities(description: str | None) -> list[tuple[str, int]]:
    """Reachable cities named in the posting's basing clauses, nearest first.

    ATS location fields carry ONE city, and it is often not the closest option.
    Match Group's "Principal AI Learning & Enablement Partner" is filed under
    "Los Angeles, California" but the body says it "will be based out of LA,
    Palo Alto, or San Francisco office" -- Palo Alto is 28 minutes from San
    Mateo. Reading only the structured field hard-fails that role on geography.
    """
    known = (config.commute_table().get("cities", {}) or {})
    limit = config.profile().get("hard_gates", {}).get("max_commute_minutes", 60)
    found: dict[str, int] = {}
    for clause in basing_phrases(description):
        lowered = clause.lower()
        for city, minutes in known.items():
            if minutes > limit:
                continue
            if re.search(rf"\b{re.escape(city.lower())}\b", lowered):
                found[city] = minutes
    return sorted(found.items(), key=lambda kv: kv[1])


def geo_allowed(city: str | None, work_model: str | None,
                location_raw: str | None,
                description: str | None = "") -> tuple[bool, str]:
    raw = clean(location_raw)
    if work_model == WORK_REMOTE:
        if _NON_US.search(raw) and not _US_MARKER.search(raw):
            return False, f"remote but scoped outside the US ({raw})"
        return True, ""
    if _NON_US.search(raw) and not _US_MARKER.search(raw):
        return False, f"located outside the US ({raw})"

    limit = config.profile().get("hard_gates", {}).get("max_commute_minutes", 60)
    minutes = commute_mod.lookup_minutes(city)
    if minutes is not None and minutes <= limit:
        return True, ""

    # The listed city is unknown or too far. Before rejecting, read the raw
    # location string and then the posting body for a reachable office -- in
    # that order, because the raw string is the employer stating where the job
    # is, while the body is only inference.
    in_raw = reachable_cities_in(raw)
    if in_raw:
        best, best_minutes = in_raw[0]
        if minutes is None or best_minutes < minutes:
            return True, (f"parsed as {city or raw!r} but the posting's location "
                          f"names {best} (~{best_minutes} min)")

    alternates = alternate_base_cities(description)
    if alternates:
        best, best_minutes = alternates[0]
        return True, f"listed as {city or raw!r} but also based in {best} (~{best_minutes} min)"

    if minutes is None:
        return False, f"unknown location {city or raw!r} - add it to config/commute.yml"
    return False, f"{city} is ~{minutes} min from San Mateo (limit {limit})"


def evaluate(
    posting,
    *,
    suppressed: set[str],
    posting_fingerprint: str,
    enforce_freshness: bool = True,
    freshness_days: int | None = None,
    first_sighting: bool = True,
    first_seen: str | None = None,
) -> PrefilterResult:
    """Run every gate. `posting` is a Posting dataclass OR a sqlite3.Row."""
    gates = config.profile().get("hard_gates", {})
    title = _field(posting, "title") or ""
    description = _field(posting, "description") or ""
    flags: list[str] = []

    # 1. Suppression -- cheapest, and the rule Doran cares most about.
    if posting_fingerprint in suppressed:
        return PrefilterResult(False, "already presented (fingerprint suppressed)")

    # 2. Freshness.
    published = _field(posting, "published_at")
    if enforce_freshness:
        window = freshness_days if freshness_days is not None else gates.get("freshness_days", 60)
        age = age_days(published)
        if age is None:
            if not first_sighting:
                return PrefilterResult(False, "no publish date and not a first sighting")
            flags.append("no_publish_date")
        elif age > window:
            return PrefilterResult(False, f"published {age:.0f} days ago (window {window})")

        # Evergreen / repost detection. A feed can claim a posting is days old
        # while we have been watching the identical req for months -- reposting
        # resets the visible publish date, and Ashby's "evergreen" reqs never
        # close at all. Our own first sighting is the one date that cannot be
        # rewritten, so when the two disagree badly, say so. This FLAGS rather
        # than rejects: an evergreen req is often still a real job, it just is
        # not the fresh opening the date implies.
        evergreen_after = gates.get("evergreen_days", 75)
        watched = age_days(first_seen)
        if watched is not None and evergreen_after and watched > evergreen_after:
            if age is not None and watched - age > evergreen_after / 2:
                flags.append(
                    f"evergreen_or_reposted (first seen {watched:.0f} days ago, "
                    f"feed claims {age:.0f})"
                )

    # 3. Title band -- VP+ is over-reach, per profile.yml.
    band = _title_band_rejected(title)
    if band:
        return PrefilterResult(False, f"title band '{band}' is above Doran's ceiling")

    if IRRELEVANT_TITLE.search(title):
        return PrefilterResult(False, f"title is out of domain: {title!r}")

    # 4. Geography.
    ok, reason = geo_allowed(
        _field(posting, "city"),
        _field(posting, "workplace_type") or _field(posting, "work_model"),
        _field(posting, "location_raw"),
        description,
    )
    if not ok:
        return PrefilterResult(False, reason)
    if reason:
        flags.append(reason)

    # 5. Compensation floor -- tested against the TOP of the band, so wide
    #    ranges like Harvey's $136k-$204k survive to be scored properly.
    salary_max = _field(posting, "salary_max")
    floor = gates.get("min_base_salary_max", 150_000)
    if salary_max is not None and salary_max < floor:
        return PrefilterResult(False, f"stated max base ${salary_max:,} is below ${floor:,}")

    # 6. Killer terms.
    for name, pattern in KILLER_PATTERNS:
        if not pattern.search(description):
            continue
        exempt = KILLER_EXEMPTIONS.get(name)
        if exempt and exempt(description):
            continue
        return PrefilterResult(False, f"disqualifying requirement: {name}")

    # 7. Content relevance, evaluated against BOTH tracks. A posting survives if
    #    it clears either one -- track A is the AI-enablement list, track B the
    #    growth-marketing backup. Which track(s) it qualified for is recorded so
    #    the report can route it to the right list.
    relevance, matched = score_relevance(title, description)
    track_a = _has_both_sides(matched) and relevance >= RELEVANCE_FLOOR

    growth_rel, growth_matched = score_growth_relevance(title, description)
    track_b = _has_growth_core(growth_matched) and growth_rel >= GROWTH_RELEVANCE_FLOOR
    growth_title_block = _growth_title_rejected(title) if track_b else None
    if growth_title_block:
        track_b = False

    # A posting whose marketing vocabulary dwarfs its AI vocabulary is a
    # marketing role using AI words, not an AI role. Dropping the AI track
    # routes it to the marketing list and its stricter bar.
    if (track_a and track_b and relevance
            and growth_rel / relevance >= MARKETING_IN_AI_CLOTHING):
        track_a = False

    tracks = []
    if track_a:
        tracks.append(config.TRACK_AI)
    if track_b:
        tracks.append(config.TRACK_GROWTH)

    if tracks:
        return PrefilterResult(
            True, "", relevance=relevance, matched_terms=matched, flags=flags,
            tracks=tracks, growth_relevance=growth_rel,
            audience=classify_audience(title, description),
            ai_fluency_requested=bool(AI_FLUENCY_REQUESTED.search(description)),
        )

    # Neither track cleared -- report whichever miss is more informative.
    if growth_title_block:
        return PrefilterResult(
            False,
            f"growth match ({growth_rel:.1f}) but title band "
            f"'{growth_title_block}' is above track B's Senior Manager-Director ceiling",
            relevance=relevance, matched_terms=matched, growth_relevance=growth_rel,
        )
    if not _has_both_sides(matched):
        reason = (
            f"no track match (AI side incomplete; growth relevance "
            f"{growth_rel:.1f} below floor {GROWTH_RELEVANCE_FLOOR})"
        )
    else:
        reason = (
            f"no track match (AI relevance {relevance:.1f} below "
            f"{RELEVANCE_FLOOR}; growth {growth_rel:.1f} below "
            f"{GROWTH_RELEVANCE_FLOOR})"
        )
    return PrefilterResult(
        False, reason, relevance=relevance, matched_terms=matched,
        growth_relevance=growth_rel,
    )
