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
}

# Signals that a role is predominantly traffic creation rather than capture.
CREATION_HEAVY = re.compile(
    r"\b(paid search|paid social|programmatic|media buying|ad platforms?|"
    r"campaign management|campaign workflows?|media spend|digital media|"
    r"budget pacing|multi-?channel budgets?|ad formats?|affiliate|influencer|"
    r"webinars?|field marketing|events? marketing|channel strategy|"
    r"demand generation|demand gen|integrated campaigns?)\b",
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
}

# Calibrated against 2,033 live postings from six companies. That corpus has a
# median relevance of 8 and a p90 of 25, while Doran's four golden postings score
# 64 (Plaid), 80 (DoorDash), 92 (Harvey) and 94 (Figma's live Marketing
# Engineer). A floor of 40 sits well above the noise while leaving 24 points of
# headroom under the weakest golden -- a false negative here silently discards a
# good job, so we err permissive and let the rubric do the fine judgement.
RELEVANCE_FLOOR = 40.0

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
]

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


def _title_band_rejected(title: str, track: str | None = None) -> str | None:
    lowered = f" {clean(title).lower()} "
    for band in _reject_bands(track):
        if re.search(rf"\b{re.escape(str(band).lower())}\b", lowered):
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

    for term, weight in TITLE_BONUS_TERMS.items():
        if term in title_l:
            total += weight
            matched.append(f"title:{term}")

    return total, matched


def _has_both_sides(matched: list[str]) -> bool:
    """Require a genuine AI-enablement signal AND a business-context signal.

    The business context can be marketing (the ideal) or company-wide enablement.
    Requiring marketing specifically would filter out generalized AI enablement
    roles before they were ever scored -- but those still qualify for Doran, just
    at a slightly lower rank via the scope modifier.
    """
    ai_side = set(AI_ENABLEMENT_TERMS) | {f"title:{t}" for t in TITLE_BONUS_TERMS}
    context_side = set(MARKETING_CONTEXT_TERMS) | set(ENTERPRISE_CONTEXT_TERMS)
    hits = set(matched)
    return bool(hits & ai_side) and bool(
        (hits & context_side)
        or any(m.startswith("title:") and "marketing" in m for m in hits)
    )


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

    # The listed city is unknown or too far -- check whether the posting names a
    # reachable alternate office before rejecting it.
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
        window = freshness_days if freshness_days is not None else gates.get("freshness_days", 14)
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
        if pattern.search(description):
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
