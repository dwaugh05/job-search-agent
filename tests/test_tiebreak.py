"""The tiebreaker's licence, enforced.

Doran asked on 2026-08-28 for a holistic safety net: an agent that reads the
posting itself and settles close calls, with the if-then of when it applies
decided up front. He set the band at 0.20 and capped it at 30 postings per run.

Everything in this file is the "up front" half. A second judging agent is the
one component in this system that could quietly undo the evidence cap, the
seniority cap and the anchors, so its limits are tested the same way theirs are
rather than trusted to a prompt.

Run with:  python tests/test_tiebreak.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from careerops import config, queue, tiebreak  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, expected) -> None:
    if got != expected:
        FAILURES.append(f"{label}\n    expected: {expected!r}\n    got     : {got!r}")
        print(f"  FAIL  {label}")
    else:
        print(f"  ok    {label}")


BODY = (
    "You will shape how AI, automation, and data are embedded into marketing "
    "workflows, enabling the team to scale marketing impact while maintaining "
    "human judgment. You will also be responsible for coaching the team on AI "
    "fluency and modern marketing practices, and for owning the demand "
    "generation calendar across NAM and EMEA."
)

QUOTE_A = "shape how AI, automation, and data are embedded into marketing workflows"
QUOTE_B = "coaching the team on AI fluency and modern marketing practices"


print("\nthe limits Doran set")

check("band is 0.20", tiebreak.BAND, 0.20)
check("per-run cap is 30", tiebreak.MAX_PER_RUN, 30)
# The nudge must be strictly smaller than the band, or a tiebreaker could move a
# posting from clearly-out to clearly-in. It leans; it does not decide.
check("a nudge cannot span the band",
      tiebreak.MAX_ADJUSTMENT < tiebreak.BAND, True)


print("\neligibility: only close calls")

MARKETING_BAR = config.bucket_threshold(config.BUCKET_MARKETING)
low, high = tiebreak.band_for(config.BUCKET_MARKETING)
check("the band brackets the bar", (round(MARKETING_BAR - low, 4),
                                    round(high - MARKETING_BAR, 4)), (0.20, 0.20))

for label, score, expected in [
    ("exactly on the bar", MARKETING_BAR, True),
    ("just under the bar", MARKETING_BAR - 0.05, True),
    ("at the bottom edge", low, True),
    ("at the top edge", high, True),
    ("a hair below the band", low - 0.01, False),
    ("a hair above the band", high + 0.01, False),
    ("a clear pass", MARKETING_BAR + 1.0, False),
    ("a clear fail", MARKETING_BAR - 1.0, False),
]:
    check(f"{label} -> eligible={expected}",
          tiebreak.is_eligible(score, config.BUCKET_MARKETING), expected)

check("an unscored posting is never eligible",
      tiebreak.is_eligible(None, config.BUCKET_MARKETING), False)

# Each bucket carries its own bar, so the window has to move with it. An overlap
# posting at 3.70 is a close call; a marketing-only posting at 3.70 is not.
check("the window follows the bucket, not a global bar",
      (tiebreak.is_eligible(3.70, config.BUCKET_OVERLAP),
       tiebreak.is_eligible(3.70, config.BUCKET_MARKETING)),
      (True, False))


print("\nvalidation: what gets refused")


def problems(adjustment, quotes, body=BODY, base=MARKETING_BAR,
             bucket=config.BUCKET_MARKETING):
    return tiebreak.validate(adjustment, quotes, body, base, bucket)


check("a well-formed nudge is accepted",
      problems(-0.10, [QUOTE_A, QUOTE_B]), [])
check("the full nudge in either direction is accepted",
      (problems(0.15, [QUOTE_A, QUOTE_B]), problems(-0.15, [QUOTE_A, QUOTE_B])),
      ([], []))

check("a nudge over the limit is refused",
      any("exceeds" in p for p in problems(0.20, [QUOTE_A, QUOTE_B])), True)
check("so is an over-limit nudge downward",
      any("exceeds" in p for p in problems(-0.16, [QUOTE_A, QUOTE_B])), True)

check("one quote is not evidence",
      any("needs 2 quotes" in p for p in problems(-0.10, [QUOTE_A])), True)
check("no quotes at all is refused",
      any("needs 2 quotes" in p for p in problems(-0.10, [])), True)

# The whole point of the quote rule is that it is checked, not asked for. A
# plausible-sounding sentence that is not in the posting is exactly the
# unfalsifiable judgement this design exists to prevent.
check("an invented quote is caught",
      any("not found verbatim" in p for p in
          problems(-0.10, [QUOTE_A, "you will own the AI enablement roadmap"])),
      True)

# Postings arrive with wrapping and non-breaking spaces from a dozen different
# feeds, so matching has to survive re-wrapping without becoming loose enough to
# match anything.
wrapped = QUOTE_A.replace(", ", ",\n   ")
check("a re-wrapped quote still matches",
      any("not found verbatim" in p for p in problems(-0.10, [wrapped, QUOTE_B])),
      False)

check("a short fragment does not count as a quote",
      any("needs 2 quotes" in p for p in problems(-0.10, [QUOTE_A, "AI fluency"])),
      True)

check("a posting outside the band is refused even with perfect evidence",
      any("outside the close-call band" in p
          for p in problems(-0.10, [QUOTE_A, QUOTE_B], base=MARKETING_BAR - 1.0)),
      True)


print("\nthe queue no longer hides the evidence")

# The Agiloft failure, as a regression test. Its AI mandate sat at char 2,372,
# its "coaching the team on AI fluency" line at 10,122 and its named tools at
# 12,122 -- so under the old 7,000-char cap the two things Doran cited as proof
# the role fits were invisible, and it was scored 3.0 on dimension 1.
check("the cap clears the longest posting on record (20,055 chars)",
      queue.DESCRIPTION_CHARS > 20055, True)
check("Agiloft's AI fluency line is inside the cap",
      queue.DESCRIPTION_CHARS > 12122, True)

# When the cap does fire it must keep the end of the posting: responsibilities
# open a job ad and compensation closes it, and the old cut kept only the head.
long_body = "HEAD" + ("x" * (queue.DESCRIPTION_CHARS * 2)) + "TAIL"
row = {
    "description": long_body, "title": "T", "company": "C", "id": 1,
    "url": "u", "apply_url": None, "location_raw": "Remote", "city": "Remote",
    "work_model": "Remote", "salary_min": None, "salary_max": None,
    "equity_mentioned": 0, "bonus_mentioned": 0, "published_at": None,
    "date_confidence": "none", "department": None, "team": None,
    "ats": "greenhouse", "source_slug": "s", "source_id": "1",
    "fingerprint": "f",
}


class Row(dict):
    def __getitem__(self, key):
        return self.get(key)


class FakeConn:
    """repost_signals is the only DB read in a posting block."""

    def execute(self, *args, **kwargs):
        class _C:
            def fetchall(self_inner):
                return []

            def fetchone(self_inner):
                return None
        return _C()


block = queue._posting_block(FakeConn(), Row(row), 1)
check("an over-long posting keeps its head", "HEAD" in block, True)
check("and keeps its tail", "TAIL" in block, True)
check("and says how much was dropped", "omitted from the middle" in block, True)


print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s):\n")
    for failure in FAILURES:
        print(f"  - {failure}")
    sys.exit(1)
print("All tiebreak checks passed.")
