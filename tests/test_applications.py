"""Regression tests for the connection bump and the application archive.

Both features are only as good as their matching. Every case below is taken
from a real posting or a real company-name variant that broke, or would have
broken, the naive version:

  * The archive has to find "what this job asks you to do" in a posting that
    never says "Responsibilities" -- of the thirteen roles Doran had applied to
    when this was written, only three used that word.
  * The connection bump has to fire on "Meta Platforms, Inc." when the config
    says "Meta", and must NOT fire on a company that merely looks similar.

Run with:  python tests/test_applications.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from careerops.applications import (  # noqa: E402
    classify_heading, extract_sections,
)
from careerops.config import normalize_company  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, expected) -> None:
    if got != expected:
        FAILURES.append(f"{label}\n    expected: {expected!r}\n    got     : {got!r}")
        print(f"  FAIL  {label}")
    else:
        print(f"  ok    {label}")


# ------------------------------------------------------------ heading matching

print("\nheading classification")

# Every one of these is the literal heading from a posting Doran applied to.
for heading in ("RESPONSIBILITIES", "WHAT YOU'LL DO", "What You’ll Do",
                "What you will do in this role:", "Key Responsibilities:",
                "As a Senior Marketing Manager, Web Growth, you'll:"):
    check(f"responsibilities: {heading!r}", classify_heading(heading), "responsibilities")

# The curly apostrophe is the whole point of the first two: GitLab and Box write
# the same heading with different quote characters.
check("straight and curly apostrophes agree",
      classify_heading("WHAT YOU'LL DO"), classify_heading("What You’ll Do"))

for heading in ("WHAT YOU HAVE", "WHO YOU ARE", "What You’ll Bring",
                "Requirements:", "Nice to have",
                "To be successful in this role, you will have"):
    check(f"requirements: {heading!r}", classify_heading(heading), "requirements")

# "What you'll do" and "What you'll bring" differ by one word and mean opposite
# things -- the requirements patterns are checked first for exactly this reason.
check("'What you'll need' is requirements, not responsibilities",
      classify_heading("What you'll need"), "requirements")

for heading in ("COMPENSATION", "Benefits", "Equal Opportunity", "WHY HARVEY",
                "Why Box needs you", "How GitLab will support you",
                "United States Salary Range"):
    check(f"stop: {heading!r}", classify_heading(heading), "stop")

# ServiceNow nests six of these inside its responsibilities list. Treating them
# as section breaks truncated the capture after one paragraph.
check("unknown sub-heading is not a section break",
      classify_heading("AI Governance, Risk & Responsible AI"), None)
check("bullet line is never a heading",
      classify_heading("- Lead enterprise AI transformation engagements"), None)
check("long prose line is never a heading",
      classify_heading("We are seeking a Director of AI Strategy to lead the "
                       "company's evolution into an AI-enabled organization."), None)

# ---------------------------------------------------------------- extraction

print("\nsection extraction")

POSTING = """WHY ACME
We are a great company.

ROLE OVERVIEW
Own AI enablement end to end.

WHAT YOU'LL DO
- Lead the programme
- Own the roadmap

WHAT YOU HAVE
- Ten years of experience

NICE TO HAVE
- A second language

COMPENSATION
$190,000 - $240,000
"""

sections = extract_sections(POSTING)
check("overview captured", sections["overview"], "Own AI enablement end to end.")
check("responsibilities captured", sections["responsibilities"],
      "- Lead the programme\n- Own the roadmap")
# "Nice to have" continues the requirements section rather than restarting it,
# so preferred quals are not silently dropped.
check("requirements absorb the follow-on section", sections["requirements"],
      "- Ten years of experience\n\nNICE TO HAVE\n- A second language")
check("company pitch is excluded", "great company" in str(sections["overview"]), False)
check("pay range is excluded", "190,000" in str(sections["responsibilities"]), False)
check("via names the heading", sections["via"], 'heading "WHAT YOU\'LL DO"')

# Natera's shape: one "About the role" label covering both the pitch and the
# actual duties, which are broken out under imperative sub-headings. Filing the
# duties under "overview" would bury the answer to the only question this file
# exists to answer.
NATERA = """About the role
We are building the future of diagnostics.

Find the leverage in your domain
- Map the workflows

Design the future-state workflow
- Draw the target state

What we're looking for
- Five years of experience
"""
split = extract_sections(NATERA)
check("imperative sub-heading starts the duties",
      split["responsibilities"].startswith("Find the leverage in your domain"), True)
check("the pitch stays in the overview", split["overview"],
      "We are building the future of diagnostics.")
check("both imperative sections are kept",
      "Design the future-state workflow" in str(split["responsibilities"]), True)
check("requirements still separate", split["requirements"], "- Five years of experience")
check("via explains the relabel", split["via"],
      'unlabelled duties under "About the role"')

# Fallback 1: no headings at all, but an action-verb bullet list. Losing the
# text entirely would defeat the point -- this file is his interview prep.
BULLETS = """We are hiring.

- Lead the marketing AI programme
- Own the enablement roadmap
- Partner with the CMO on adoption

Apply today.
"""
fallback = extract_sections(BULLETS)
check("unlabelled bullets are captured",
      fallback["responsibilities"].count("\n"), 2)
check("unlabelled bullets are labelled as such",
      "unlabelled" in str(fallback["via"]), True)

# Fallback 2: nothing recognisable at all -- keep the whole posting.
prose = extract_sections("A short posting with no structure whatsoever.")
check("full-text fallback keeps everything",
      prose["full"], "A short posting with no structure whatsoever.")
check("full-text fallback says so", "full-text fallback" in str(prose["via"]), True)

check("empty description is handled", extract_sections("")["via"],
      "no description stored")
check("None description is handled", extract_sections(None)["via"],
      "no description stored")

# ------------------------------------------------------- connection matching

print("\ncompany name matching")

check("plain name", normalize_company("Meta"), "meta")
check("case is ignored", normalize_company("META"), "meta")
check("legal suffix is dropped", normalize_company("Apple Inc."), "apple")
check("nested suffixes are dropped", normalize_company("Acme Holdings Corp"),
      normalize_company("Acme Holdings"))
check("punctuation is ignored", normalize_company("Ben & Jerry's"), "benjerrys")
check("distinct companies stay distinct",
      normalize_company("Meta") == normalize_company("Metabase"), False)
check("empty name is empty", normalize_company(None), "")

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):\n")
    for failure in FAILURES:
        print(f"  {failure}\n")
    raise SystemExit(1)
print("All application archive + connection tests passed.")
