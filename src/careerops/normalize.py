"""Field normalization shared by every source adapter.

Everything that turns messy ATS output into the canonical Posting shape lives
here, so all sources -- API or browser-scraped -- agree on what "Hybrid" or
"San Francisco" means.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone

from .models import WORK_HYBRID, WORK_ONSITE, WORK_REMOTE

# ---------------------------------------------------------------- text hygiene

# Ashby (and others) serve UTF-8 that has already been decoded once as cp1252,
# so an en dash (U+2013, bytes E2 80 93) arrives as three stray characters.
# Left alone this leaks into salary strings and breaks range parsing.
#
# Two rules make this safe, both learned the hard way:
#   1. Markers must be the full multi-character sequences. A bare "â"
#      matches ordinary accented text and would trigger a bogus repair.
#   2. The re-encode must be STRICT. With errors="ignore", any character outside
#      the codec -- a real em dash, a curly quote -- is silently deleted. That
#      quietly erased the "$142,800 - $210,000" separator in DoorDash's posting
#      and blanked dimension 4 for it.
_MOJIBAKE_MARKERS = (
    "â€“",   # en dash
    "â€”",   # em dash
    "â€™",   # right single quote
    "â€œ",   # left double quote
    "â€˜",   # left single quote
    "â€¦",   # ellipsis
    "Ã©", "Ã¨", "Ã¼", "Ã¶", "Ã±",
)


# Direct repairs, used when a full codec round-trip is impossible because the
# string mixes genuine Unicode with mojibake.
_MOJIBAKE_REPLACEMENTS = {
    "â€“": "–",
    "â€”": "—",
    "â€™": "’",
    "â€œ": "“",
    "â€": "”",
    "â€˜": "‘",
    "â€¦": "…",
    "â€¢": "•",
    "Ã©": "é",
    "Ã¨": "è",
    "Ã¼": "ü",
    "Ã¶": "ö",
    "Ã±": "ñ",
}


def fix_mojibake(text: str | None) -> str:
    if not text:
        return ""
    if not any(marker in text for marker in _MOJIBAKE_MARKERS):
        return text
    for codec in ("cp1252", "latin-1"):
        try:
            return text.encode(codec).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    # A clean round-trip failed, which means the string mixes correctly-decoded
    # characters with mojibake. Repair the known sequences in place rather than
    # giving up -- the alternative leaves a broken dash inside a salary range.
    for broken, fixed in _MOJIBAKE_REPLACEMENTS.items():
        text = text.replace(broken, fixed)
    return text


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")
_BLANKS = re.compile(r"\n{3,}")


def strip_html(markup: str | None) -> str:
    # Parameter is `markup`, not `html` -- naming it `html` shadows the stdlib
    # module we call below.
    if not markup:
        return ""
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", markup)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|tr)>", "\n", text)
    text = re.sub(r"(?i)<li\b[^>]*>", "- ", text)
    text = _TAG.sub(" ", text)
    # Decode entities only after tags are gone, so an escaped "&lt;script&gt;"
    # can't turn back into a live tag. Must be a full unescape rather than a
    # handful of replacements: Greenhouse writes pay ranges as
    # "$142,800 &mdash; $210,000", and leaving &mdash; encoded means the salary
    # range never parses and dimension 4 silently scores as "not listed".
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = _WS.sub(" ", text)
    return _BLANKS.sub("\n\n", text).strip()


def clean(text: str | None) -> str:
    return fix_mojibake(text or "").strip()


# ------------------------------------------------------------------- location

_LOC_NOISE = re.compile(
    r"\b(hq|headquarters|office|campus|metro area|area|region)\b", re.IGNORECASE
)

_REMOTE_PAT = re.compile(
    r"\b(remote|work from home|wfh|distributed|anywhere)\b", re.IGNORECASE
)
_HYBRID_PAT = re.compile(r"\bhybrid\b", re.IGNORECASE)
_ONSITE_PAT = re.compile(r"\b(on.?site|in.?office|in.?person)\b", re.IGNORECASE)

# A leading work-model token followed by a separator, e.g. "Remote - Austin".
_WORK_PREFIX = re.compile(
    r"^(remote|hybrid|on.?site|in.?office|flexible)\s*(?:[-–—:|]|\bin\b)\s*",
    re.IGNORECASE,
)

# Phrases that unambiguously describe a hybrid WORK MODEL, safe to search across
# the whole posting body (unlike a bare "hybrid", which matches "hybrid cloud").
_HYBRID_WORK = re.compile(
    r"\bhybrid\s+(environment|work|working|schedule|role|position|model|setup|"
    r"arrangement|approach|policy|workplace)\b"
    r"|\bwe\s+are\s+(a\s+)?hybrid\b|\bhybrid\s+\(",
    re.IGNORECASE,
)

# "3+ days a week in the office", "two days per week onsite", and the day-name
# form -- Roblox writes "onsite Tuesday, Wednesday, and Thursday, with optional
# presence on Monday and Friday", which is hybrid but names no number.
_RTO_CADENCE = re.compile(
    r"\b(?:one|two|three|four|1|2|3|4)\s*\+?\s*days?\s+(?:a|per)\s+week\b"
    r"|\b(?:office|onsite|on-site|in-office)\b[^.]{0,40}"
    r"\b(?:one|two|three|four|1|2|3|4)\s*\+?\s*days?\b"
    r"|\b(?:onsite|on-site|in.office|in the office)\b[^.]{0,30}"
    r"\b(?:monday|tuesday|wednesday|thursday|friday)\b",
    re.IGNORECASE,
)

# A whole-country / nationwide scope with no city named.
_COUNTRY_ONLY = re.compile(
    r"^\s*(united states(?: of america)?|usa?|u\.s\.a?\.?|nationwide|"
    r"anywhere|multiple locations|various locations)\s*$",
    re.IGNORECASE,
)

_STATE_ABBR = {
    "california": "CA", "ca": "CA", "new york": "NY", "ny": "NY",
    "washington": "WA", "wa": "WA", "texas": "TX", "tx": "TX",
    "massachusetts": "MA", "ma": "MA", "illinois": "IL", "il": "IL",
    "colorado": "CO", "co": "CO", "oregon": "OR", "or": "OR",
    "georgia": "GA", "ga": "GA", "florida": "FL", "fl": "FL",
    "north carolina": "NC", "nc": "NC", "utah": "UT", "ut": "UT",
    "arizona": "AZ", "az": "AZ", "pennsylvania": "PA", "pa": "PA",
    "virginia": "VA", "va": "VA", "new jersey": "NJ", "nj": "NJ",
    "ohio": "OH", "oh": "OH", "michigan": "MI", "mi": "MI",
    "minnesota": "MN", "mn": "MN", "tennessee": "TN", "tn": "TN",
    "district of columbia": "DC", "dc": "DC",
}

# Some feeds (Snowflake and Stripe on Greenhouse, ZoomInfo) emit a hyphen-
# delimited internal location code with no commas at all: "US-CA-Menlo Park",
# "US-WA-Bellevue", "GB-London". Comma splitting leaves the entire code sitting
# in the city field, so "US-CA-Menlo Park" never matches the "Menlo Park" key in
# commute.yml -- a 25-minute commute silently reads as unknown location. Rewrite
# these into the comma form the rest of the parser already handles.
_ATS_CODE = re.compile(
    r"^(?P<country>[A-Z]{2})-(?:(?P<region>[A-Z]{2})-)?(?P<city>\S.*)$"
)

_COUNTRY_CODES = {
    "US": "United States", "GB": "United Kingdom", "UK": "United Kingdom",
    "CA": "Canada", "DE": "Germany", "FR": "France", "IN": "India",
    "AU": "Australia", "IE": "Ireland", "NL": "Netherlands",
    "SG": "Singapore", "JP": "Japan", "BR": "Brazil", "MX": "Mexico",
    "ES": "Spain", "PL": "Poland", "IL": "Israel", "CH": "Switzerland",
    "CN": "China", "SA": "Saudi Arabia", "KR": "South Korea",
    "IT": "Italy", "SE": "Sweden", "AE": "United Arab Emirates",
}

# Cities that ATS feeds spell inconsistently.
_CITY_ALIASES = {
    "sf": "San Francisco",
    "san francisco bay area": "San Francisco",
    "nyc": "New York",
    "new york city": "New York",
    "south san francisco": "South San Francisco",
    "mtv": "Mountain View",
    "redwood shores": "Redwood City",
}


def parse_location(raw: str | None) -> tuple[str | None, str | None, str | None]:
    """-> (city, region, country). Best effort; None where genuinely unknown."""
    text = clean(raw)
    if not text:
        return None, None, None

    text = _LOC_NOISE.sub(" ", text)

    # Multi-location postings list every site: "Bellevue, Washington; Chicago,
    # Illinois;". Take the first -- it is the primary site on every feed we read,
    # and without this the state lands on the wrong city entirely.
    if ";" in text:
        first = text.split(";")[0].strip()
        if first:
            text = first

    # Hyphen-delimited ATS codes carry no commas, so rewrite before splitting.
    if "," not in text:
        code = _ATS_CODE.match(text.strip())
        if code and code.group("country") in _COUNTRY_CODES:
            country_name = _COUNTRY_CODES[code.group("country")]
            pieces = [code.group("city").strip()]
            if code.group("region"):
                pieces.append(code.group("region"))
            pieces.append(country_name)
            text = ", ".join(pieces)

    text = re.sub(r"[|/]", ",", text)
    parts = [p.strip(" -–—\t") for p in text.split(",")]
    parts = [p for p in parts if p]
    if not parts:
        return None, None, None

    country = None
    region = None

    tail = parts[-1].lower()
    if tail in {"united states", "usa", "us", "u.s.", "u.s.a."}:
        country = "United States"
        parts = parts[:-1]
    elif tail in {"canada", "united kingdom", "uk", "germany", "france", "india",
                  "australia", "ireland", "netherlands", "singapore", "japan",
                  "brazil", "mexico", "spain", "poland", "israel",
                  # Kept in step with _COUNTRY_CODES so a rewritten ATS code
                  # round-trips instead of leaving the country on the city.
                  "switzerland", "china", "saudi arabia", "south korea",
                  "italy", "sweden", "united arab emirates"}:
        country = parts[-1]
        parts = parts[:-1]

    if parts:
        maybe_region = parts[-1].strip().lower()
        if maybe_region in _STATE_ABBR:
            region = _STATE_ABBR[maybe_region]
            country = country or "United States"
            parts = parts[:-1]

    city = None
    if parts:
        candidate = parts[0].strip()
        # Boards write work model and city in one field a dozen different ways:
        # "Remote", "Remote - Austin", "Hybrid: San Francisco", "Remote (US)".
        # Strip the work-model prefix so the city survives.
        candidate = _WORK_PREFIX.sub("", candidate).strip(" -–—:()")
        if not candidate and len(parts) > 1:
            candidate = parts[1].strip()
        if _REMOTE_PAT.fullmatch(candidate):
            candidate = parts[1].strip() if len(parts) > 1 else ""
        if candidate:
            city = _CITY_ALIASES.get(candidate.lower(), candidate.title()
                                     if candidate.islower() else candidate)
    return city or None, region, country


# Sentences that say where the role is BASED, as opposed to where it travels or
# where the company happens to have offices. Match Group's posting reads: "This
# role may travel to key hub cities including Dallas, LA, New York, Vancouver,
# and Paris; however will be based out of LA, Palo Alto, or San Francisco office"
# -- the travel list must not count, the basing list must.
_BASING = re.compile(
    r"[^.;]*\b(?:will be based|is based|based out of|based in|based at|"
    r"role is located|located in|will sit in|report(?:ing)? to (?:our|the) \w+ office)"
    r"\b[^.;]*",
    re.IGNORECASE,
)
_TRAVEL = re.compile(r"\b(travel|visit|hub cities|as needed)\b", re.IGNORECASE)


def basing_phrases(description: str | None) -> list[str]:
    """Clauses that state where a role is based. Travel clauses are excluded."""
    text = clean(description)
    if not text:
        return []
    out = []
    for match in _BASING.finditer(text):
        clause = match.group(0).strip()
        # Trim anything before a "however"/"but" pivot so a travel list that
        # shares the sentence does not leak in as a basing location.
        pivot = re.split(r"\b(?:however|but|although)\b", clause, flags=re.IGNORECASE)
        clause = pivot[-1] if len(pivot) > 1 else clause
        if _TRAVEL.search(clause) and "based" not in clause.lower():
            continue
        out.append(clause)
    return out


def parse_work_model(
    workplace_type: str | None,
    is_remote_flag: bool | None,
    location_raw: str | None,
    description: str | None = "",
) -> str:
    """Resolve Remote / Hybrid / On-site.

    Ashby's `isRemote` is NOT authoritative -- it is true on plenty of postings
    whose `workplaceType` is "Hybrid" (both the Plaid and Harvey calibration
    anchors are exactly this). Trusting it would mark SF hybrid roles as Remote,
    skip the commute penalty, and inflate their scores. So an explicit
    workplaceType always wins, and the flag is only a last resort.
    """
    explicit = clean(workplace_type).lower()
    if explicit:
        if "hybrid" in explicit:
            return WORK_HYBRID
        if "remote" in explicit:
            return WORK_REMOTE
        if any(k in explicit for k in ("onsite", "on-site", "on site", "office")):
            return WORK_ONSITE

    location = clean(location_raw)

    # The location field itself is more reliable than the description body,
    # so resolve it before falling back to prose.
    if _HYBRID_PAT.search(location):
        return WORK_HYBRID
    if _REMOTE_PAT.search(location):
        return WORK_REMOTE

    # A country-scoped posting with no city is a distributed role, not an
    # on-site one. Reltio advertises Doran's highest-rated match as plain
    # "United States"; defaulting that to On-site would give it an unknown-city
    # commute penalty and knock his best posting out of its calibration band.
    if _COUNTRY_ONLY.match(location):
        return WORK_REMOTE

    body = clean(description)
    haystack = f"{location} {body[:1500]}"
    # Work-model statements usually live near the END of a posting, under
    # "Where you'll work" or the benefits block, well past the first 1500
    # characters. Brex's "We are a hybrid environment" sits there and was being
    # reported as On-site. Scan the whole body, but only for phrases that
    # unambiguously describe the work model -- a bare "hybrid" also matches
    # "hybrid cloud" and would mislabel plenty of infrastructure postings.
    if _HYBRID_WORK.search(body):
        return WORK_HYBRID
    # An RTO cadence is hybrid even when the posting never says "hybrid".
    # Checkr writes "expected to work from the office 3+ days a week", which
    # otherwise reads as fully on-site and costs the role a whole point on
    # dimension 6.
    if _RTO_CADENCE.search(body):
        return WORK_HYBRID
    if _ONSITE_PAT.search(haystack):
        return WORK_ONSITE
    if is_remote_flag and _REMOTE_PAT.search(haystack):
        return WORK_REMOTE
    return WORK_ONSITE


# ----------------------------------------------------------------------- time


def parse_datetime(value) -> str | None:
    """Normalize an ATS timestamp to an ISO-8601 UTC string."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        # Lever uses epoch milliseconds.
        seconds = value / 1000 if value > 1e11 else value
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def age_days(published_at: str | None, *, reference: str | None = None) -> float | None:
    if not published_at:
        return None
    try:
        pub = datetime.fromisoformat(published_at)
    except ValueError:
        return None
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=timezone.utc)
    ref = datetime.now(timezone.utc)
    if reference:
        try:
            ref = datetime.fromisoformat(reference)
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return (ref - pub).total_seconds() / 86400.0


def days_ago_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
