"""Regression tests for the three portals added on 2026-08-27.

Every case here comes from a real miss.

Meta, Google and Apple were never in `config/sources.yml` at all, and NVIDIA sat
in it marked "dead" with no board, so four of the six companies Doran asked
about had never been scanned once. NVIDIA was invisible twice over: its board
runs on Eightfold, which no adapter spoke, AND the role-first LinkedIn channel
discarded any lead whose employer was already named in sources.yml -- dead
entries included.

Run with:  python tests/test_new_sources.py
"""

from __future__ import annotations

import pathlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from careerops.comp import parse_salary  # noqa: E402
from careerops.sources import apple, eightfold, google  # noqa: E402
from careerops.sources import registry  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, expected) -> None:
    if got != expected:
        FAILURES.append(f"{label}\n    expected: {expected!r}\n    got     : {got!r}")
        print(f"  FAIL  {label}")
    else:
        print(f"  ok    {label}")


# ------------------------------------------------------- salary, trailing USD
#
# NVIDIA writes "The base salary range is 292,000 USD - 442,750 USD" with no
# dollar sign. The $-anchored pattern could not see it, so every posting on that
# board would have arrived with no salary and scored compensation as unpublished.

print("\nsalary: currency after the figure")
check("NVIDIA trailing-USD range",
      parse_salary("The base salary range is 292,000 USD - 442,750 USD"),
      (292000, 442750))
check("NVIDIA agentic-AI-for-marketing band",
      parse_salary("The base salary range is 224,000 USD - 356,500 USD"),
      (224000, 356500))
check("levelled band takes the first range",
      parse_salary("116,000 USD - 184,000 USD for Level 3, and "
                   "136,000 USD - 224,250 USD for Level 4"),
      (116000, 184000))
check("dollar-anchored ranges still win",
      parse_salary("$136,000 - $204,000"), (136000, 204000))
check("Google's unpunctuated band still parses",
      parse_salary("US: $186000 - $269000 (USD) + 20% bonus target"),
      (186000, 269000))
# The trailing-currency form must not turn funding or ARR into a paycheck.
check("funding is not a salary",
      parse_salary("we raised 50M USD in Series C funding"), (None, None))
check("ARR is not a salary",
      parse_salary("Our ARR grew from 10 USD to 100 USD"), (None, None))


# ------------------------------------------------------------------ eightfold

print("\neightfold: slug packing and listing shape")
check("slug splits into subdomain and domain",
      eightfold.parse_slug("nvidia:nvidia.com"), ("nvidia", "nvidia.com"))
check("a bare slug is rejected rather than half-built",
      eightfold.parse_slug("nvidia"), None)
check("empty slug is rejected", eightfold.parse_slug(""), None)
check("build_url refuses an unpackable slug", eightfold.build_url("nvidia"), "")
# domain is mandatory: the endpoint answers 422 without it.
check("search URL carries the domain parameter",
      "domain=nvidia.com" in eightfold.build_url("nvidia:nvidia.com"), True)
check("paging is by start offset",
      "start=20" in eightfold.build_url("nvidia:nvidia.com", start=20), True)
check("detail URL is the read-only jobs path",
      eightfold.detail_url("nvidia:nvidia.com", 893392478748),
      "https://nvidia.eightfold.ai/api/apply/v2/jobs/893392478748?domain=nvidia.com")

_payload = {"data": {"count": 2695, "positions": [
    {"id": 893397308806,
     "name": "Senior Architect, Agentic AI for Marketing",
     "locations": ["US, CA, Santa Clara"],
     "standardizedLocations": ["Santa Clara, CA, US"],
     "postedTs": 1785888000,
     "department": "Mktg",
     "displayJobId": "JR2010101",
     "positionUrl": "/careers/job/893397308806"},
]}}
check("extract_jobs reads data.positions", len(eightfold.extract_jobs(_payload)), 1)
check("total_found reads data.count", eightfold.total_found(_payload), 2695)
check("a non-dict payload yields nothing", eightfold.extract_jobs("nope"), [])
check("a payload with no data key yields nothing", eightfold.extract_jobs({}), [])

_posting = eightfold.parse(
    _payload["data"]["positions"][0], "Nvidia", "nvidia:nvidia.com",
    detail_payload={"job_description":
                    "<p>Translate marketing needs into human-in-the-loop workflows.</p>"
                    "<p>The base salary range is 224,000 USD - 356,500 USD.</p>",
                    "canonicalPositionUrl":
                    "https://jobs.nvidia.com/careers/job/893397308806"},
)
check("title comes off the listing",
      _posting.title, "Senior Architect, Agentic AI for Marketing")
# The raw `location` field is country-first ("US, CA, Santa Clara"), which
# parse_location reads backwards and files the country as the city.
check("standardizedLocations is preferred over the country-first form",
      _posting.city, "Santa Clara")
check("region parses from the standardized form", _posting.region, "CA")
check("salary is read out of the description body",
      (_posting.salary_min, _posting.salary_max), (224000, 356500))
check("postedTs becomes a high-confidence date", _posting.date_confidence, "high")
check("posted date is August 2026", _posting.published_at[:7], "2026-08")
check("description is de-HTMLed",
      "human-in-the-loop" in _posting.description and "<p>" not in _posting.description,
      True)
# apply_redirect_url points at the employer's application form. It must never
# become apply_url -- see the no-auto-apply rule in CLAUDE.md.
check("apply_url is the public posting, never the application form",
      _posting.apply_url, "https://jobs.nvidia.com/careers/job/893397308806")
check("a listing with no title is dropped rather than stored blank",
      eightfold.parse({"id": 1}, "Nvidia", "nvidia:nvidia.com", {}), None)


# --------------------------------- a malformed URL must not kill a whole scan
#
# Added 2026-08-28, after a broad scan died mid-run on:
#   UnicodeEncodeError: 'idna' codec can't encode characters in position 0-74:
#   label too long
#
# A DNS label over 63 characters makes httpx raise UnicodeError from the idna
# codec. That is NOT an httpx.HTTPError, so it escaped every `except
# httpx.HTTPError` in the package and aborted a multi-hour sweep over one bad
# URL. Two defences, because either alone is thin: reject it at the source, and
# survive it at the network layer.

print("\nmalformed URLs")

check("a valid packed slug still parses",
      eightfold.parse_slug("nvidia:nvidia.com"), ("nvidia", "nvidia.com"))
# eightfold is the ONLY adapter that puts a slug in the hostname rather than
# the path, which is why the guard lives there.
check("an over-long subdomain is refused",
      eightfold.parse_slug("x" * 75 + ":nvidia.com"), None)
check("...and builds no URL at all",
      eightfold.build_url("x" * 75 + ":nvidia.com"), "")
check("a 63-character label is still allowed",
      eightfold.parse_slug("x" * 63 + ":nvidia.com") is not None, True)
check("a subdomain with a space is refused",
      eightfold.parse_slug("has space:nvidia.com"), None)
check("an empty domain half is refused",
      eightfold.parse_slug("nvidia:"), None)

# Every network handler must survive a malformed URL, not just this adapter.
_sources = pathlib.Path(__file__).resolve().parents[1] / "src" / "careerops" / "sources"
_narrow = [
    path.name for path in sorted(_sources.glob("*.py"))
    if "except httpx.HTTPError" in path.read_text(encoding="utf-8")
]
check("no handler catches httpx.HTTPError alone", _narrow, [])
_widened = sum(
    path.read_text(encoding="utf-8").count(
        "except (httpx.HTTPError, UnicodeError, ValueError)")
    for path in sorted(_sources.glob("*.py"))
)
check("every network handler also catches UnicodeError and ValueError",
      _widened >= 11, True)

# ---------------------------------------------------------------------- apple

print("\napple: doubly-escaped JSON in server-rendered HTML")
_apple_record = (
    'x\\"positionId\\":\\"200671933\\",\\"postingDate\\":\\"Aug 05, 2026\\",'
    '\\"postingTitle\\":\\"Agentic AI Product Manager, Platform - Sales \\",'
    '\\"postDateInGMT\\":\\"2026-08-05T16:49:55.229+00:00\\",'
    '\\"transformedPostingTitle\\":\\"agentic-ai-product-manager\\",'
)
_jobs = apple.extract_jobs(_apple_record)
check("one record is recovered from the escaped blob", len(_jobs), 1)
check("position id is read", _jobs[0]["positionId"], "200671933")
check("title is read", _jobs[0]["postingTitle"].strip(),
      "Agentic AI Product Manager, Platform - Sales")
check("a non-string payload yields nothing", apple.extract_jobs(None), [])

# Apple repeats key names: "description" appears in a page-meta block near the
# top of the document AND in the job record. Reading the first gave every Apple
# posting an identical, wrong body.
_apple_detail = (
    '\\"description\\":\\"PAGE META, NOT THE JOB\\",'
    'x' * 500 +
    '\\"postingTitle\\":\\"Agentic AI Product Manager\\",'
    '\\"jobSummary\\":\\"Owns the agentic AI platform for worldwide sales.\\",'
    '\\"description\\":\\"THE REAL JOB BODY\\",'
    '\\"minimumQualifications\\":\\"8 years of product management.\\",'
    '\\"preferredQualifications\\":\\"Experience with MCP.\\",'
    '\\"locations\\":[{\\"id\\":\\"postLocation-AST\\",\\"city\\":\\"Austin\\",'
    '\\"stateProvince\\":\\"Texas\\"},{\\"id\\":\\"postLocation-CUP\\",'
    '\\"city\\":\\"Cupertino\\",\\"stateProvince\\":\\"California\\"}],'
    '\\"homeOffice\\":false,'
    '\\"postingFooters\\":[{\\"content\\":\\"base pay between $207,400 and $311,700.\\"}]'
)
_ap = apple.parse({"positionId": "200671933",
                   "postingTitle": "Agentic AI Product Manager",
                   "postDateInGMT": "2026-08-05T16:49:55.229+00:00"},
                  "Apple", detail_html=_apple_detail)
check("the job body wins over the page-meta description",
      "THE REAL JOB BODY" in _ap.description, True)
check("the page-meta description is not used",
      "PAGE META" in _ap.description, False)
check("qualifications are folded into the body",
      "MCP" in _ap.description and "8 years" in _ap.description, True)
# Austin is listed FIRST on this req; taking it would fail the commute gate on
# a role Doran could actually take in Cupertino.
check("California is preferred over the first-listed location",
      _ap.location_raw, "Cupertino, California")
check("pay band is read out of postingFooters",
      (_ap.salary_min, _ap.salary_max), (207400, 311700))
check("posting date is kept", _ap.published_at[:10], "2026-08-05")
check("url is the public detail page",
      _ap.url, "https://jobs.apple.com/en-us/details/200671933")
check("a record with no id is dropped",
      apple.parse({"postingTitle": "x"}, "Apple", detail_html=_apple_detail), None)


# --------------------------------------------------------------------- google

print("\ngoogle: server-rendered HTML, no posting dates")
_g_results = (
    '<a href="./jobs/results/137435049938035398-principal-lead-gotomarket-ai-tools'
    '?q=AI">x</a>'
    '<a href="./jobs/results/137435049938035398-principal-lead-gotomarket-ai-tools">y</a>'
    '<a href="./jobs/results/106281886908588742-program-manager-ai-and-gemini-app-marketing">z</a>'
)
_g_jobs = google.extract_jobs(_g_results)
check("two distinct results are found", len(_g_jobs), 2)
check("the repeated id is de-duplicated",
      [j["id"] for j in _g_jobs],
      ["137435049938035398", "106281886908588742"])

_g_detail = (
    "<title>Principal Lead, Go-To-Market AI Tools — Google Careers</title>"
    "<body>Note: By applying to this position you will have an opportunity to "
    "share your preferred working location from the following: Atlanta, GA, USA; "
    "San Francisco, CA, USA; New York, NY, USA . "
    "Minimum qualifications: Bachelor's degree. "
    "Responsibilities Lead the team's AI innovation agenda. "
    "US: $186000 - $269000 (USD) + 20% bonus target + equity + benefits "
    "Information collected and processed as part of your Google Careers profile"
    "</body>"
)
_g = google.parse({"id": "137435049938035398",
                   "slug": "principal-lead-gotomarket-ai-tools"},
                  "Google", detail_html=_g_detail)
check("title drops the Google Careers suffix",
      _g.title, "Principal Lead, Go-To-Market AI Tools")
# Atlanta is listed first. San Francisco is the one Doran can take.
check("California is preferred over the first-listed location",
      _g.location_raw, "San Francisco, CA, USA")
check("salary parses from Google's unpunctuated band",
      (_g.salary_min, _g.salary_max), (186000, 269000))
check("body starts at the qualifications marker",
      _g.description.startswith("Minimum qualifications:"), True)
check("Google's privacy boilerplate is cut off",
      "Information collected" in _g.description, False)
# Google publishes no date anywhere. Saying so is what lets the freshness gate
# admit the posting once as a first sighting instead of guessing an age.
check("no posting date is invented", _g.published_at, None)
check("date confidence says none", _g.date_confidence, "none")
check("a page with no qualifications marker is dropped",
      google.parse({"id": "1", "slug": "x"}, "Google",
                   detail_html="<title>Whatever — Google Careers</title>"), None)
check("a detail page that never loaded is dropped",
      google.parse({"id": "1", "slug": "x"}, "Google", detail_html=None), None)


# -------------------------------------------------------------- registry wiring

print("\nregistry: the new sources are reachable")
for name in ("eightfold", "apple", "google"):
    check(f"{name} is registered as an adapter", name in registry.ADAPTERS, True)
check("apple and google are marked as portals",
      registry.PORTALS, {"apple", "google"})
# Neither can be probed by guessing a slug, so neither belongs in the probe
# order: eightfold needs a domain the name does not give you, and the portals
# are single-employer.
for name in ("eightfold", "apple", "google"):
    check(f"{name} is not blind-probed", name in registry.PROBE_ORDER, False)
check("the archetype query set is shared, not duplicated",
      len(registry._portal_queries()) > 10, True)
check("query set carries the AI enablement term",
      "AI enablement" in registry._portal_queries(), True)


# --------------------------------------- the dead-company blind spot in boards

print("\npipeline: a dead sources.yml entry no longer hides a company")
# This is the bug that made NVIDIA invisible. discover_via_boards built its
# "already covered" set from every name in sources.yml, so a company listed
# with status "dead" and no board was skipped by the ATS sweep (nothing to
# fetch) AND skipped by the board channel (looked covered).
_entries = [
    {"name": "Airbnb", "status": "live", "ats": "greenhouse", "slug": "airbnb"},
    {"name": "Nvidia", "status": "dead"},
    {"name": "Adobe", "status": "dead"},
    {"name": "Halfdone", "status": "live"},          # live but never resolved
    {"name": "Slugless", "status": "live", "ats": "greenhouse"},
]
covered = {
    (e.get("name") or "").strip().lower()
    for e in _entries
    if e.get("status") == "live" and e.get("ats") and e.get("slug")
}
check("a fetchable company counts as covered", "airbnb" in covered, True)
check("a dead entry does not hide the company", "nvidia" in covered, False)
check("another dead entry does not hide it either", "adobe" in covered, False)
check("live but unresolved does not count as covered", "halfdone" in covered, False)
check("live with no slug does not count as covered", "slugless" in covered, False)

_source = (Path(__file__).resolve().parents[1]
           / "src" / "careerops" / "pipeline.py").read_text(encoding="utf-8")
check("pipeline filters the known set on a readable board",
      'if entry.get("status") == "live" and entry.get("ats") and entry.get("slug")'
      in _source, True)


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):\n")
    for failure in FAILURES:
        print(f"  {failure}\n")
    raise SystemExit(1)
print("All new-source tests passed.")
