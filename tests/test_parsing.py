"""Regression tests for the parsing layer.

Every case here is one that actually bit during development. They are cheap to
run and they protect the two fields the rubric leans on hardest: compensation
(dimension 4, weight 14) and work model / location (dimensions 5-6, weight 18).

Run with:  python tests/test_parsing.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from careerops.comp import (  # noqa: E402
    model_total_comp, parse_salary, realistic_base, stated_bonus_rate,
)
from careerops.fingerprint import fingerprint  # noqa: E402
from careerops.normalize import (  # noqa: E402
    fix_mojibake, parse_location, parse_work_model, strip_html,
)
from careerops.prefilter import score_relevance  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, expected) -> None:
    if got != expected:
        FAILURES.append(f"{label}\n    expected: {expected!r}\n    got     : {got!r}")
        print(f"  FAIL  {label}")
    else:
        print(f"  ok    {label}")


# --------------------------------------------------------------- compensation

print("\ncompensation")

# DoorDash writes its range with an HTML em dash entity, and its benefits section
# separately mentions "For hourly roles". Both broke this at different times.
check(
    "annual range survives a distant 'hourly' mention",
    parse_salary(
        "For hourly roles: vacation accrued at about 1 hour for every 25.97 hours "
        "worked (e.g. about 6.7 hours/month). " + "filler " * 30 +
        "The national base pay range for this position within the United States, "
        "including Illinois and Colorado. $142,800 — $210,000 USD"
    ),
    (142800, 210000),
)
check("genuine hourly rate annualizes", parse_salary("$85 - $95 per hour"), (176800, 197600))
check("k-suffix range", parse_salary("$136K - $204K"), (136000, 204000))
check(
    "cp1252 mojibake en dash still parses",
    parse_salary("$136K â€“ $204K • Offers Equity"),
    (136000, 204000),
)
check("comma range", parse_salary("$170,400 - $223,200"), (170400, 223200))
check("funding is not salary", parse_salary("We raised a $200M Series C"), (None, None))
check(
    "single figure needs salary context",
    parse_salary("The base salary for this role is $185,000 per year"),
    (185000, 185000),
)
check("no figures", parse_salary("Competitive compensation"), (None, None))

# Geographic pay tiers: Doran is in the Bay Area and therefore always in the top
# tier. Natera published three bands and the first-match rule took the standard
# one, understating the role by $19,000 of base.
check(
    "multi-band posting takes the higher-cost-of-living tier",
    parse_salary(
        "The base salary range for standard cost of living areas is: "
        "$152,100-$190,100. Higher cost of living areas: $167,300 - $209,100. "
        "Lower cost of living areas: $136,900-$171,100."
    ),
    (167300, 209100),
)
check(
    "never settle for the low-COL band when another exists",
    parse_salary(
        "Lower cost of living areas: $136,900-$171,100. "
        "Standard areas: $152,100-$190,100."
    ),
    (152100, 190100),
)
check(
    "a lone low-COL band is still used",
    parse_salary("Lower cost of living areas: $136,900-$171,100"),
    (136900, 171100),
)

# Doran scores the TOP of a band, not a midpoint or an offer point: "I'd
# negotiate for that top end, so I'm not worried about the low end of the pay for
# any of these roles ever." Compensation must not push a good role down the list.
check("scores the top of the band", realistic_base(136000, 204000), 204000)
check("point value stays put", realistic_base(185000, 185000), 185000)
check("open-ended low end still uses the top", realistic_base(None, 220000), 220000)

harvey = model_total_comp(136000, 204000, equity=True)
check("Harvey modeled base is the band top", harvey["base"], 204000)
check("Harvey modeled bonus is 10%", harvey["bonus"], 20400)
check("Harvey modeled TC lands in the $200-300k target", 200000 <= harvey["tc"] <= 300000, True)

# The $170k floor is enforced as a hard gate on the band MAXIMUM, not as a
# scoring penalty -- see prefilter.evaluate and profile.yml min_base_salary_max.
check("a band topping out under the floor still scores its top",
      realistic_base(90000, 120000), 120000)

check("explicit bonus rate wins", stated_bonus_rate("plus a 20% annual bonus"), 0.20)
check("no bonus rate stated", stated_bonus_rate("competitive salary"), None)

# ------------------------------------------------------------------ text/html

print("\ntext and html")

check("entities decode", strip_html("<p>$142,800 &mdash; $210,000</p>"), "$142,800 — $210,000")
check("script content dropped", strip_html("<script>evil()</script><p>Hi</p>"), "Hi")
check("real em dash is left alone", fix_mojibake("$1 — $2"), "$1 — $2")
check(
    "cp1252 mojibake is repaired",
    fix_mojibake("$136K â€“ $204K"),
    "$136K – $204K",
)

# ------------------------------------------------------------------- location

print("\nlocation and work model")

check("HQ suffix stripped", parse_location("San Francisco HQ")[0], "San Francisco")
check("city/state", parse_location("San Mateo, CA"), ("San Mateo", "CA", "United States"))
check(
    "full US address",
    parse_location("San Francisco, California, United States"),
    ("San Francisco", "CA", "United States"),
)
check("remote prefix skipped", parse_location("Remote - Austin, TX")[0], "Austin")

# Snowflake and Stripe emit a hyphen-delimited internal code with no commas.
# Before this was handled, "US-CA-Menlo Park" landed in the city field whole and
# never matched the "Menlo Park" key in commute.yml -- so a 25-minute commute
# read as unknown location across 347 postings. Guard every shape of the code.
check("ATS code: country-state-city",
      parse_location("US-CA-Menlo Park"), ("Menlo Park", "CA", "United States"))
check("ATS code: out-of-state still resolves",
      parse_location("US-WA-Bellevue"), ("Bellevue", "WA", "United States"))
check("ATS code: two-part foreign",
      parse_location("GB-London"), ("London", None, "United Kingdom"))
check("ATS code: state-wide remote keeps the state",
      parse_location("US-CA-Remote"), (None, "CA", "United States"))
check("ATS code: multi-word city survives",
      parse_location("US-NY-New York")[0], "New York")
check("plain city is not mistaken for an ATS code",
      parse_location("San Mateo")[0], "San Mateo")

# Multi-site postings list every location; the first is the primary site. Okta's
# "Bellevue, Washington; Chicago, Illinois;" was resolving to the wrong state.
check("semicolon list takes the first site",
      parse_location("Bellevue, Washington; Chicago, Illinois;"),
      ("Bellevue", "WA", "United States"))

# The single most consequential normalization in the system: Ashby reports
# isRemote=true on both the Plaid and Harvey postings even though workplaceType
# is "Hybrid". Trusting the flag marks SF hybrid roles as Remote, skips the
# commute penalty, and inflates their scores past their calibration band.
check(
    "explicit Hybrid beats a true isRemote flag",
    parse_work_model("Hybrid", True, "San Francisco HQ", ""),
    "Hybrid",
)
check("explicit Remote", parse_work_model("Remote", True, "Remote - US", ""), "Remote")
check(
    "remote inferred from location when unstated",
    parse_work_model(None, True, "United States - Remote", ""),
    "Remote",
)
check("defaults to on-site", parse_work_model(None, None, "New York", ""), "On-site")

# ---------------------------------------------------------------- fingerprint

print("\nfingerprint")

base_desc = "Own the AI enablement strategy for the marketing organization. " * 12
check(
    "same role reposted under a new id keeps its fingerprint",
    fingerprint("Acme Inc", "AI Enablement Lead", base_desc)
    == fingerprint("Acme, Inc.", "AI Enablement Lead (Remote)", base_desc),
    True,
)
check(
    "a genuinely different role gets a different fingerprint",
    fingerprint("Acme", "AI Enablement Lead", base_desc)
    == fingerprint("Acme", "Backend Engineer", "Build distributed services. " * 12),
    False,
)

# ----------------------------------------------------------------- relevance

print("\nrelevance")

archetype = (
    "You will lead AI enablement for the marketing organization, building agentic "
    "workflows and upskilling our demand generation and product marketing teams. "
    "Partner with VP-level stakeholders on AI strategy. Human-in-the-loop by design."
)
noise = (
    "Design and build distributed backend services in Go. Own uptime for our "
    "payments platform and participate in the on-call rotation."
)
arch_score, _ = score_relevance("Marketing Engineer", archetype)
noise_score, _ = score_relevance("Senior Backend Engineer", noise)
check("archetype clears the floor", arch_score >= 40, True)
check("unrelated engineering role does not", noise_score < 40, True)
check("archetype scores well above noise", arch_score > noise_score * 3, True)

# ---------------------------------------------------------- config integrity

print("\nconfig integrity")

import yaml as _yaml  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_cfg = _Path(__file__).resolve().parents[1] / "config"
for _f in sorted(_cfg.glob("*.yml")):
    try:
        _yaml.safe_load(_f.read_text(encoding="utf-8"))
        check(f"{_f.name} parses", True, True)
    except Exception as _e:  # noqa: BLE001
        check(f"{_f.name} parses ({_e})", False, True)

# Both tracks must weight to 100 -- a drifting total silently rescales every
# score without failing anything visibly.
sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))
from careerops import config as _config  # noqa: E402

for _track in _config.TRACKS:
    _sc = _config.scoring(_track)
    check(f"{_track} weights sum to 100",
          sum(d["weight"] for d in _sc["dimensions"]), 100)
    check(f"{_track} has 10 dimensions", len(_sc["dimensions"]), 10)

# ---------------------------------------------------------------------------
# ATS link sniffing. This is the fallback that finds a board when slug guessing
# fails; it is the ONLY route to Workday employers, whose slug is a
# tenant:instance:site triple that cannot be guessed. A regression here silently
# returns whole companies to being undiscoverable.
from careerops.sources import sniff as _sniff  # noqa: E402

check("greenhouse link is extracted",
      _sniff.find_ats_links('<a href="https://boards.greenhouse.io/acme/jobs/1">x</a>'),
      [("greenhouse", "acme")])
check("job-boards.greenhouse.io variant is extracted",
      _sniff.find_ats_links('<a href="https://job-boards.greenhouse.io/acme">x</a>'),
      [("greenhouse", "acme")])
check("ashby link is extracted",
      _sniff.find_ats_links('href="https://jobs.ashbyhq.com/acme/abc"'),
      [("ashby", "acme")])
check("lever link is extracted",
      _sniff.find_ats_links('href="https://jobs.lever.co/acme"'),
      [("lever", "acme")])
check("smartrecruiters link is extracted",
      _sniff.find_ats_links('href="https://careers.smartrecruiters.com/Acme"'),
      [("smartrecruiters", "acme")])
check("workable link is extracted",
      _sniff.find_ats_links('href="https://apply.workable.com/acme/"'),
      [("workable", "acme")])
# Workday is the whole point of this module.
check("workday triple is packed as tenant:instance:site",
      _sniff.find_ats_links('href="https://qualys.wd5.myworkdayjobs.com/Careers"'),
      [("workday", "qualys:wd5:Careers")])
check("workday cxs URL form also parses",
      _sniff.find_ats_links(
          'https://gilead.wd1.myworkdayjobs.com/wday/cxs/gilead/gileadcareers/jobs'),
      [("workday", "gilead:wd1:gileadcareers")])
# A page with no ATS anywhere must return nothing rather than a bad guess.
check("page with no ATS link yields nothing",
      _sniff.find_ats_links("<html><body><p>We are hiring!</p></body></html>"), [])
# Vendor-owned paths are not customer slugs.
check("vendor noise slugs are rejected",
      _sniff.find_ats_links('href="https://boards.greenhouse.io/embed/job_board?for=acme"'),
      [("greenhouse", "acme")])
check("empty ashby slug is rejected",
      _sniff.find_ats_links('href="https://jobs.ashbyhq.com/"'), [])
# Domain guessing should strip corporate suffixes.
check("domain guess strips 'Software' suffix",
      "guidewire.com" in _sniff.domain_candidates("Guidewire Software"), True)
check("careers subdomains are generated",
      "metacareers.com" in _sniff.subdomain_candidates("Meta"), True)
check("careers link is followed cross-domain",
      _sniff.careers_links('<a href="https://metacareers.com/jobs">Careers</a>',
                           "https://meta.com/"),
      ["https://metacareers.com/jobs"])
check("non-careers links are ignored",
      _sniff.careers_links('<a href="/pricing">Pricing</a>', "https://acme.com/"), [])

# ---------------------------------------------------------------------------
# Built In adapter. Its JobPosting sits in page JavaScript, not an ld+json tag,
# so the brace matcher has to skip SIBLING objects to find the real one -- the
# first version silently returned {"@type":"Organization"} and parsed nothing.
from careerops.sources import builtin as _builtin  # noqa: E402

_SAMPLE = (
    'var x = {"@type":"Other","name":"decoy"}; '
    'window.job = {"@type":"JobPosting","title":"AI Enablement Lead",'
    '"applicantLocationRequirements":{"@type":"Country","name":"USA"},'
    '"hiringOrganization":{"@type":"Organization","name":"Acme"},'
    '"datePosted":"2026-08-01","description":"<p>Braces {like this} inside</p>"};'
)
_parsed = _builtin._slice_json_object(_SAMPLE, _SAMPLE.find("hiringOrganization"))
check("builtin finds the JobPosting, not a sibling object",
      isinstance(_parsed, dict) and _parsed.get("@type"), "JobPosting")
check("builtin reads the employer name",
      (_parsed or {}).get("hiringOrganization", {}).get("name"), "Acme")
check("builtin survives braces inside the HTML description",
      "{like this}" in str((_parsed or {}).get("description")), True)
check("builtin returns None when there is no JobPosting",
      _builtin._slice_json_object('{"@type":"Organization","name":"x"}', 5), None)

# ---------------------------------------------------------------------------
# Hacker News "Who is hiring" parsing. These posts are prose with no title
# field, so a regression here silently drops the highest-signal AI/startup
# channel entirely -- every lead would fail the archetype screen.
from careerops.sources.hn import parse_comment as _hn_parse  # noqa: E402
from careerops.pipeline import _lead_haystack as _hay  # noqa: E402
from careerops.pipeline import _LEAD_WORTH_RESOLVING as _screen  # noqa: E402

_hn_lead = _hn_parse(
    "<p>Acme AI | Head of AI Enablement | Remote (US) | Full Time</p>"
    "<p>We are building agentic workflows for marketing teams and need someone "
    "to drive adoption across the whole organisation.</p>", 123)
check("hn extracts the company", _hn_lead.company, "Acme AI")
check("hn extracts the role", _hn_lead.title, "Head of AI Enablement")
check("hn extracts the location", _hn_lead.location, "Remote (US)")
check("hn body is screened, not just the title",
      bool(_screen.search(_hay(_hn_lead))), True)
check("hn drops a too-short post",
      _hn_parse("<p>hiring</p>", 1), None)
check("hn drops a post with no pipe convention",
      _hn_parse("<p>" + ("we are hiring engineers in london " * 6) + "</p>", 2), None)
# A company name swallowed by its own tagline was the first parse bug.
_tagline = _hn_parse(
    "<p>Globex - we make widgets | Staff AI Solutions Engineer | Remote</p>"
    "<p>" + ("Build and ship agentic tooling for internal teams. " * 4) + "</p>", 3)
check("hn strips a trailing tagline from the company", _tagline.company, "Globex")

# ---------------------------------------------------------------------------
# Evergreen / repost detection. Greenhouse's own data puts 18-22% of ATS
# postings in the ghost category and Ashby ships evergreen reqs as a feature, so
# a feed claiming "3 days ago" about a req we have watched for 200 days must say
# so. Flags, never rejects -- an evergreen req is often still a real job.
from datetime import datetime as _dt, timedelta as _td, timezone as _tz  # noqa: E402
from careerops import prefilter as _pf  # noqa: E402
from careerops.models import Posting as _P  # noqa: E402

def _evergreen_flags(published_days: int, watched_days: int | None):
    now = _dt.now(_tz.utc)
    posting = _P(
        source_id="x", company="Acme", title="AI Enablement Lead", url="u",
        ats="greenhouse", is_remote=True, workplace_type="Remote",
        location_raw="Remote, United States", salary_min=200000, salary_max=250000,
        description=("Own AI enablement and adoption for the marketing organization. "
                     "Build agentic workflows, run training, upskill marketers, "
                     "human in the loop. ") * 8,
        published_at=(now - _td(days=published_days)).date().isoformat(),
    )
    seen = None if watched_days is None else (now - _td(days=watched_days)).isoformat()
    result = _pf.evaluate(posting, suppressed=set(), posting_fingerprint="fp",
                          first_sighting=watched_days is None, first_seen=seen)
    return result.passed, [f for f in result.flags if "evergreen" in f]

_passed, _flags = _evergreen_flags(3, 200)
check("evergreen: long-watched req is flagged", len(_flags), 1)
check("evergreen: flagged but NOT rejected", _passed, True)
_passed, _flags = _evergreen_flags(3, 5)
check("evergreen: genuinely new req is not flagged", _flags, [])
_passed, _flags = _evergreen_flags(3, None)
check("evergreen: first sighting is not flagged", _flags, [])

# ---------------------------------------------------------------------------
# ATS slug index. Guards the false positive found in testing: "Qualys" matched
# the slug "qualysoft" -- a different company -- and would have ingested 80 of
# somebody else's postings. A wrong board is worse than no board, because
# nothing downstream catches it.
from careerops.sources import tokens as _tok  # noqa: E402

_tok._INDEX = {
    "qualys": [("workday", "qualys:wd5:careers")],
    "qualysoft": [("lever", "qualysoft")],
    "guidewire": [("lever", "guidewire")],
    "ziplines": [("ashby", "ziplines")],
    "doordashusa": [("greenhouse", "doordashusa")],
}
check("index: exact match wins", _tok.lookup("Qualys"),
      [("workday", "qualys:wd5:careers")])
check("index: a longer different company is NOT matched",
      ("lever", "qualysoft") in _tok.lookup("Qualys"), False)
check("index: slug shortened from the name still matches",
      _tok.lookup("Guidewire Software"), [("lever", "guidewire")])
check("index: a one-character suffix still matches",
      _tok.lookup("Zipline"), [("ashby", "ziplines")])
check("index: unknown company returns nothing", _tok.lookup("Nonexistent Corp"), [])
check("index: empty name returns nothing", _tok.lookup(""), [])
_tok._INDEX = None  # let real lookups reload the cache

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):\n")
    for failure in FAILURES:
        print(f"  {failure}\n")
    raise SystemExit(1)
print("All parsing + config tests passed.")
