"""The three screens that decide whether a role is ever looked at.

Each of these was measured against the postings this system has actually scored,
and each was silently discarding real matches:

  * the board lead screen threw away 18 of the 48 best postings on record,
    including the highest score ever (ButterflyMX, 4.86) -- they only ever
    reached scoring because their employer happened to be on the watch list;
  * the geography gate read a parsed city field and never the raw location
    string, so "San Mateo - Bovet" -- five minutes from Doran's house -- was
    rejected as an unknown location;
  * the title-band gate treated "CRO" as Chief Revenue Officer even in
    "Growth Marketing Manager, Web & CRO", where it means conversion rate
    optimization and is track B's core vocabulary.

These are regression tests for widening, so they assert what must now PASS as
carefully as what must still be rejected. A screen that lets everything through
is not a fix.

Run with:  python tests/test_discovery_width.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from careerops.pipeline import _LEAD_WORTH_RESOLVING  # noqa: E402
from careerops.prefilter import (  # noqa: E402
    TITLE_BONUS_TERMS, _title_band_rejected, geo_allowed, reachable_cities_in,
)
from careerops.sources.registry import _SR_WORTH_DETAIL  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, expected) -> None:
    if got != expected:
        FAILURES.append(f"{label}\n    expected: {expected!r}\n    got     : {got!r}")
        print(f"  FAIL  {label}")
    else:
        print(f"  ok    {label}")


# ------------------------------------------------------- board lead screen

print("\nboard lead screen (which unknown employers are worth resolving)")

# Real titles, taken from postings this system scored 3.9 or better.
MUST_PASS = [
    "Director, AI Strategy & Transformation",
    "Principal Product Manager - AI Foundations",
    "MarTech Engineer - AI & Automation",
    "Principal Program Manager, Go-To-Market",
    "Director, Americas Field Marketing",
    "Growth - Digital Marketing (Consumer)",
    "Sr. Manager, Performance Marketing",
    "Solution Architect - AI & Data",
    "Answer Engine Optimization (AEO) Lead",
    "AI Business Automation Engineer",
    "Director, SEO & AEO",
    "AI Enablement Manager",
    "Marketing Engineer",
    "GTM Engineer",
]
for title in MUST_PASS:
    check(f"resolves: {title}", bool(_LEAD_WORTH_RESOLVING.search(title)), True)

# The screen exists to keep resolution cost down. If these pass, it is not a
# screen any more -- it is an open door, and every scan pays ~45 HTTP probes per
# unrelated company.
MUST_NOT_PASS = [
    "Registered Nurse, ICU",
    "Senior Backend Engineer, Payments",
    "Warehouse Associate",
    "Staff Accountant",
    "Line Cook",
    "Clinical Research Coordinator",
]
for title in MUST_NOT_PASS:
    check(f"skips: {title}", bool(_LEAD_WORTH_RESOLVING.search(title)), False)


# ------------------------------------------ SmartRecruiters / Workday screen

print("\nATS detail screen (which titles earn a detail fetch)")

check("MarTech Engineer is worth a detail fetch",
      bool(_SR_WORTH_DETAIL.search("MarTech Engineer")), True)
check("so is an agentic role",
      bool(_SR_WORTH_DETAIL.search("Agentic Workflow Lead")), True)
check("a nursing role is not",
      bool(_SR_WORTH_DETAIL.search("Registered Nurse, ICU")), False)


# ---------------------------------------------------------------- geography

print("\ngeography (the raw location string is read, not just the parsed city)")

check("a building code does not hide the city",
      reachable_cities_in("San Mateo - Bovet"), [("San Mateo", 5)])
check("reversed order is handled",
      [c for c, _ in reachable_cities_in("CA - San Francisco")], ["San Francisco"])
check("a region name resolves to its city",
      [c for c, _ in reachable_cities_in("San Francisco Bay Area")], ["San Francisco"])
check("a multi-city string finds the Bay Area office even when it is last",
      [c for c, _ in reachable_cities_in(
          "Denver, CO; New York City, NY; San Francisco, CA")], ["San Francisco"])

# Nearest-first ordering matters: the commute drives dimension 5, so picking the
# wrong office out of a list would misscore the role.
ordered = reachable_cities_in("Offices in San Francisco, Palo Alto and San Mateo")
check("nearest office wins", ordered[0][0], "San Mateo")

for raw in ["San Mateo - Bovet", "CA - San Francisco", "San Francisco Bay Area"]:
    check(f"accepted on-site: {raw}", geo_allowed(None, "On-site", raw, "")[0], True)

# Substring collisions are the obvious way to break this. "Sanford" contains
# "San" and "ford"; neither is a city, and a word-boundary-free match would let
# a Maine role through as if it were San Mateo.
for raw in ["Sanford, ME", "Austin, TX", "London, UK", "Remote - India"]:
    check(f"still rejected: {raw}", geo_allowed(None, "On-site", raw, "")[0], False)

# Homonyms are the harder failure and the one that actually bit: these city
# names are real Bay Area suburbs AND real places in other states. Every one of
# these was correctly rejected before the raw-string scan existed, and reading
# the location more eagerly must not turn a Texas job into a ten-minute commute.
HOMONYMS = [
    "Austin, TX (Belmont Campus)",
    "Boston, MA - Belmont St",
    "Chicago, IL; Newark, NJ",
    "Dallas, TX / Union City, NJ",
    "Newark, NJ",
    "Belmont, MA",
    "Belmont, North Carolina",
    "Richmond, VA",
    "Dublin, OH",
    "Concord, NH",
]
for raw in HOMONYMS:
    check(f"homonym rejected: {raw}", geo_allowed(None, "On-site", raw, "")[0], False)

# Half the two-letter state codes are ordinary English words -- IN, OR, ME, OK,
# HI, LA, DE, ID, CO, PA. Matching them outside the "City, ST" position would
# read "Offices in San Francisco" as a posting in Indiana and reject it.
check(
    "a state code that is also an English word does not reject a real match",
    geo_allowed(None, "On-site", "Offices in San Francisco, Palo Alto and San Mateo", "")[0],
    True,
)

# Gong's "GTM AI Architect", which Doran applied to on 2026-08-26 and which the
# scan had rejected. A pipe-separated office list naming San Francisco outright.
# An earlier version of this check threw the whole string away because "New York"
# appeared in it -- but a New York office is a different office, not evidence
# against the San Francisco one. Cities are judged one at a time for this reason.
MULTI_OFFICE = "Austin | Chicago | New York City | Salt Lake City | San Francisco"
check("a multi-office list is judged per city, not thrown away wholesale",
      geo_allowed("Austin", "On-site", MULTI_OFFICE, "")[0], True)
check("...and resolves to the Bay Area office",
      [c for c, _ in reachable_cities_in(MULTI_OFFICE)], ["San Francisco"])
check("a city followed by nothing at all still counts",
      [c for c, _ in reachable_cities_in("Chicago | San Francisco")], ["San Francisco"])
check("a city followed by a harmless word still counts",
      geo_allowed(None, "On-site", "San Francisco or Remote", "")[0], True)
check(
    "and it still finds the nearest of them",
    reachable_cities_in("Offices in San Francisco, Palo Alto and San Mateo")[0][0],
    "San Mateo",
)


# ------------------------------------------------------------- CRO collision

print("\nCRO means two different jobs")

check("conversion-rate CRO survives",
      _title_band_rejected("Growth Marketing Manager, Web & CRO"), None)
check("so does an experimentation seat",
      _title_band_rejected("Manager, CRO & Experimentation"), None)
check("a bare CRO is still the C-suite", _title_band_rejected("CRO"), "cro")
check("and so is CRO alongside other executive scope",
      _title_band_rejected("CRO and Head of Sales"), "cro")
check("Chief Revenue Officer is unaffected",
      _title_band_rejected("Chief Revenue Officer"), "chief")
check("VP is unaffected", _title_band_rejected("VP, Marketing"), "vp")


# --------------------------------------------------------- title relevance

print("\ntitle bonuses (lift a real archetype over the floor without moving it)")

for term in ["ai transformation", "ai strategy", "martech", "agentic"]:
    check(f"{term!r} carries a bonus", term in TITLE_BONUS_TERMS, True)
check("no term is worth more than the strongest existing one",
      max(TITLE_BONUS_TERMS.values()), 6.0)


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):\n")
    for failure in FAILURES:
        print(f"  {failure}\n")
    raise SystemExit(1)
print("All discovery-width tests passed.")
