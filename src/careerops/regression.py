"""Every job Doran applied to is a positive example. Nothing may break them.

The calibration anchors pin the rubric at eight hand-picked points. They are
deliberate and few, and they are scored from anchor DOCUMENTS -- they never touch
the deterministic gates at all. So a change to geography parsing, a title band, a
comp rule or a killer term can pass calibration cleanly while quietly making a
real job invisible.

Doran asked for this on 2026-08-26 after exactly that happened: the title gate was
rejecting GitLab's "AI Transformation Owner, CRO" -- a posting he applied to and a
pinned anchor scoring 4.53 -- because "CRO" there names the org the role sits in,
not the role's rank. Calibration was green the whole time.

So this is the other half of the safety net, and it asks two questions of every
applied posting:

  1. Would it still get through discovery to be scored at all?
  2. Did it still clear the presentation bar when it was scored?

Freshness is excluded on purpose. Every applied posting ages past the window
eventually, and that is the window working, not a regression.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import config, prefilter, store


@dataclass
class Result:
    posting_id: int
    company: str
    title: str
    score: float | None
    rubric_version: str | None
    gate_passed: bool
    gate_reason: str
    exempt_reason: str = ""
    tracks: str = ""

    @property
    def exempt(self) -> bool:
        """A miss that has been diagnosed and consciously accepted."""
        return bool(self.exempt_reason)

    @property
    def bucket(self) -> str:
        return config.bucket_of(self.tracks)

    @property
    def below_bar(self) -> bool:
        """Judged against THIS posting's bucket bar, not a flat 4.0.

        With three bars a flat comparison reports a false REGRESSION for an
        applied job sitting in a lenient bucket -- the alarm would lie about the
        very thing it exists to protect.
        """
        return (self.score is not None
                and self.score < config.bucket_threshold(self.bucket))

    @property
    def stale(self) -> bool:
        """Scored under an older rubric, so the number is not a live claim."""
        return str(self.rubric_version or "") != str(_current_version())


def _threshold() -> float:
    return float(config.profile().get("review", {}).get("min_score_to_present", 4.0))


def _current_version() -> str:
    return str(config.scoring().get("version", 1))


def _exemptions() -> dict[str, str]:
    """url -> reason, from config/profile.yml.

    An alarm is only worth having while it means something. A posting whose miss
    has been diagnosed and accepted is listed here so the check keeps reporting
    it without counting it as a failure -- see the block in profile.yml for the
    rules on when an entry is legitimate.
    """
    raw = config.profile().get("regression_exemptions") or []
    out: dict[str, str] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url") or "").strip()
        if url:
            out[url] = " ".join(str(entry.get("reason") or "").split())
    return out


def check_applied(conn: sqlite3.Connection) -> list[Result]:
    """Re-run the deterministic gates over every applied posting."""
    rows = conn.execute(
        """SELECT p.*,
                  -- The RUBRIC score, with any holistic tiebreak nudge removed.
                  -- A nudge is capped at 0.15 and this check exists to catch
                  -- rubric drift, so letting one lift an applied job back over
                  -- the bar would let the nudge hide the very thing being
                  -- watched for.
                  (SELECT weighted_score - COALESCE(tiebreak_adjustment, 0)
                     FROM evaluations
                    WHERE posting_id = p.id ORDER BY id DESC LIMIT 1) AS score,
                  (SELECT rubric_version FROM evaluations
                    WHERE posting_id = p.id ORDER BY id DESC LIMIT 1) AS rubric_version
           FROM postings p WHERE p.state = 'applied' ORDER BY p.company"""
    ).fetchall()

    exemptions = _exemptions()
    out: list[Result] = []
    for row in rows:
        verdict = prefilter.evaluate(
            row,
            suppressed=set(),
            posting_fingerprint=str(row["fingerprint"]),
            # Age is not a regression. Everything else is.
            enforce_freshness=False,
        )
        # Only an actual miss can be exempt. An exemption never suppresses a
        # posting that is passing, so a stale entry cannot hide a later break.
        reason = "" if verdict.passed else exemptions.get(str(row["url"] or ""), "")
        out.append(Result(
            posting_id=row["id"],
            company=row["company"],
            title=row["title"],
            score=row["score"],
            rubric_version=row["rubric_version"],
            gate_passed=verdict.passed,
            gate_reason=verdict.reason,
            exempt_reason=reason,
            tracks=str(row["tracks"] or ""),
        ))
    return out


def run(db_path=None) -> int:
    """Print the report. Non-zero exit if anything regressed."""
    with store.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        results = check_applied(conn)

    if not results:
        print("No applied postings yet - nothing to regression-test against.")
        print("This check gets stronger every time you mark something applied.")
        return 0

    bar = _threshold()
    # A miss that has been diagnosed and accepted is reported but does not fail
    # the check. An alarm is only worth having while it still means something.
    blocked = [r for r in results if not r.gate_passed and not r.exempt]
    known = [r for r in results if not r.gate_passed and r.exempt]
    under = [r for r in results if r.gate_passed and r.below_bar]
    stale = [r for r in results if r.stale]

    print(f"Applied-job regression check - {len(results)} job(s) you applied to\n")
    print(f"{'score':>6}  {'gates':<8}  company / role")
    print("-" * 78)
    for r in sorted(results, key=lambda x: (x.gate_passed, x.score or 0)):
        mark = "PASS" if r.gate_passed else ("KNOWN" if r.exempt else "BLOCKED")
        score = f"{r.score:.2f}" if r.score is not None else "  -  "
        print(f"{score:>6}  {mark:<8}  {r.company[:22]:24s} {r.title[:40]}")
        if not r.gate_passed:
            print(f"{'':>6}  {'':<8}  -> {r.gate_reason}")
            if r.exempt:
                # The full rationale lives in profile.yml; a paragraph dumped
                # into the table buries the other 21 rows.
                brief = r.exempt_reason
                if len(brief) > 150:
                    brief = brief[:150].rsplit(" ", 1)[0] + " ... (full reason in profile.yml)"
                print(f"{'':>6}  {'':<8}  -> accepted: {brief}")

    print()
    if blocked:
        print(f"REGRESSION: {len(blocked)} job you applied to would no longer reach "
              "scoring at all.")
        print("  A change to the gates has made a role you actually wanted invisible.")
    if under:
        print(f"REGRESSION: {len(under)} job you applied to now scores below its "
              "bucket's bar.")
        for r in under:
            print(f"  {r.company} {r.title[:40]} scored {r.score} against "
                  f"{config.bucket_threshold(r.bucket)} ({r.bucket})")
    if known:
        print(f"note: {len(known)} applied posting(s) marked KNOWN above are misses "
              "we diagnosed and accepted, listed in config/profile.yml under "
              "regression_exemptions. They are reported every run but do not fail "
              "this check.")
    if stale:
        print(f"note: {len(stale)} scored under an older rubric (current is "
              f"v{_current_version()}), so their scores are history, not a live claim. "
              "The gate result above is live either way.")

    if blocked or under:
        return 1
    # Never claim a clean sweep when some were waved through.
    passing = len(results) - len(known)
    if known:
        tail = ("1 is an accepted miss" if len(known) == 1
                else f"{len(known)} are accepted misses")
        print(f"PASSED - {passing} of {len(results)} clear the gates, and the other "
              f"{tail}. Every scored one is at or above {bar}.")
    else:
        print(f"PASSED - all {len(results)} still clear the gates, and every scored one "
              f"is at or above {bar}.")
    return 0
