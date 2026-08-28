"""The applied-job regression harness.

Every job Doran applied to is a positive example the pipeline must keep able to
find. The calibration anchors cannot cover this: they are scored from anchor
documents and never touch the deterministic gates, so a change to geography, a
title band, the comp floor or a killer term can pass calibration cleanly while
making a real job invisible.

That is not hypothetical. On 2026-08-26 the title gate was rejecting GitLab's
"AI Transformation Owner, CRO" -- a posting Doran applied to and a pinned anchor
scoring 4.53 -- because "CRO" there names the org the role sits inside rather
than the role's own rank. Calibration was green throughout.

Run with:  python tests/test_applied_regression.py
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from careerops import prefilter, regression, store  # noqa: E402
from careerops.models import Posting  # noqa: E402
from careerops.normalize import days_ago_iso  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, expected) -> None:
    if got != expected:
        FAILURES.append(f"{label}\n    expected: {expected!r}\n    got     : {got!r}")
        print(f"  FAIL  {label}")
    else:
        print(f"  ok    {label}")


ARCHETYPE = (
    "You will own AI enablement for the marketing organization. Lead AI strategy "
    "and build agentic workflows that automate campaign operations, and upskill our "
    "demand generation, product marketing and content marketing teams to build their "
    "own AI agents. Partner with VP-level stakeholders on go-to-market AI adoption. "
    "We work human-in-the-loop by design. Experience with LLM tooling, prompt "
    "systems, MCP and workflow automation is valued. This is marketing operations "
    "meets AI transformation, a first role of its kind here."
)


def posting(**over):
    fields = dict(
        source_id="J1", company="Acme", title="Marketing Engineer",
        url="https://x/1", ats="greenhouse", source_slug="acme",
        apply_url="https://x/1", location_raw="Remote - US", city=None,
        workplace_type="Remote",
        # Deliberately older than the freshness window: an applied posting always
        # ages out, and that must never read as a regression.
        published_at=days_ago_iso(200), date_confidence="high",
        description=ARCHETYPE, salary_min=180000, salary_max=230000,
    )
    fields.update(over)
    return Posting(**fields)


print("\nthe title gate must not eat an org-scope acronym")

# The exact regression that prompted this harness.
check("'AI Transformation Owner, CRO' reaches scoring",
      prefilter._title_band_rejected("AI Transformation Owner, CRO"), None)
check("...and so does a CTO-org role",
      prefilter._title_band_rejected("Head of AI Enablement, CTO org"), None)

# The anti-example must still fail, or the gate is simply off.
check("JPMorgan's spelled-out VP title is still rejected",
      prefilter._title_band_rejected(
          "Martech Operations and AI Enablement Lead - Vice President") is not None,
      True)
check("a bare CRO is still the C-suite",
      prefilter._title_band_rejected("CRO"), "cro")
check("and a VP prefix is still a VP",
      prefilter._title_band_rejected("VP, Marketing"), "vp")


print("\nthe harness itself")

with tempfile.TemporaryDirectory() as tmp:
    db = Path(tmp) / "t.db"
    store.init_db(db)
    with store.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        check("no applied jobs means nothing to check",
              regression.check_applied(conn), [])

        run = store.start_run(conn, "broad")
        good_id, _ = store.upsert_posting(conn, posting(), run)
        store.record_verdict(conn, good_id, "applied", "applied")

        results = regression.check_applied(conn)
        check("an applied posting is picked up", len(results), 1)
        check("and it clears the gates", results[0].gate_passed, True)
        check("age alone is never a regression", results[0].gate_reason, "")

        # A posting that the gates would now reject is the failure this exists
        # to surface.
        bad_id, _ = store.upsert_posting(conn, posting(
            source_id="J2", title="Martech Lead - Vice President"), run)
        store.record_verdict(conn, bad_id, "applied", "applied")

        results = regression.check_applied(conn)
        blocked = [r for r in results if not r.gate_passed]
        check("a now-blocked applied posting is caught", len(blocked), 1)
        check("...and says why", "ceiling" in blocked[0].gate_reason, True)

        # A score below the bar is the other failure mode.
        scored = [r for r in results if r.score is not None]
        check("an unscored posting reports no score rather than zero",
              all(r.score is None for r in results), True)
        check("and an unscored posting is not counted as below the bar",
              any(r.below_bar for r in results), False)


print("\nexemptions: an accepted miss must not keep crying wolf")

# `calibrate --applied-only` exits non-zero so it can gate a change. That is
# only useful while a red line means something, so a miss that has been
# diagnosed and accepted is reported as KNOWN rather than counted as a failure.
#
# Added 2026-08-28: Google posted "Program Manager, AI and Gemini App Marketing"
# twice at two levels. Doran applied to the 5-year req, which scores 34.0
# against the 40.0 floor because its description omits "agentic" and "AI agent";
# the 3-year twin scores 48.5 and passes, so the ROLE is surfaced either way.
# Doran: "if this one is a one off edge case, I don't want to try to do heavy
# work to our workflow just to fit this one specific job into it either."

_real_exemptions = regression._exemptions

with tempfile.TemporaryDirectory() as tmp:
    db = Path(tmp) / "e.db"
    store.init_db(db)
    with store.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        run = store.start_run(conn, "broad")
        ok_id, _ = store.upsert_posting(conn, posting(url="https://x/ok"), run)
        store.record_verdict(conn, ok_id, "applied", "applied")
        miss_id, _ = store.upsert_posting(conn, posting(
            source_id="J9", url="https://x/miss",
            title="Martech Lead - Vice President"), run)
        store.record_verdict(conn, miss_id, "applied", "applied")

        # Without an exemption the miss is a hard failure.
        regression._exemptions = lambda: {}
        res = regression.check_applied(conn)
        miss = [r for r in res if not r.gate_passed]
        check("an un-exempted miss is still a failure", len(miss), 1)
        check("and is not marked exempt", miss[0].exempt, False)

        # With one, it is reported but no longer fails.
        regression._exemptions = lambda: {"https://x/miss": "known thin duplicate"}
        res = regression.check_applied(conn)
        miss = [r for r in res if not r.gate_passed]
        check("an exempted miss is still listed", len(miss), 1)
        check("...marked exempt", miss[0].exempt, True)
        check("...and carries its reason", miss[0].exempt_reason, "known thin duplicate")
        check("the real gate reason is kept alongside it",
              "ceiling" in miss[0].gate_reason, True)

        # The safety property: an exemption may never silence a PASSING posting,
        # so a stale entry cannot hide a break that appears later.
        regression._exemptions = lambda: {"https://x/ok": "should have no effect"}
        res = regression.check_applied(conn)
        passing = [r for r in res if r.gate_passed]
        check("an exemption on a passing posting is inert",
              any(r.exempt for r in passing), False)
        check("and that posting still passes", len(passing), 1)

regression._exemptions = _real_exemptions

# The entry shipped in config/profile.yml must actually parse and be reachable.
_live = regression._exemptions()
check("the configured exemption list loads", isinstance(_live, dict), True)
check("every configured exemption carries a reason",
      all(bool(v.strip()) for v in _live.values()), True)


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):\n")
    for failure in FAILURES:
        print(f"  {failure}\n")
    raise SystemExit(1)
print("All applied-regression tests passed.")
