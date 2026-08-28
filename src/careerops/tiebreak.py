"""The bounded tiebreaker: a holistic read, allowed to nudge, never to decide.

Doran's idea, 2026-08-28: "a separate agent that doesn't use any calculations or
scripts... simply is just kind of a safety net applied where it reads the posting
itself to understand what it's about and then decides things that are close call,
tiebreaker type things. The rule would come in place where we specifically decide
the if-then scenario of where and when to use the agent."

The idea is right and the danger is specific. Every other brake in this system is
mechanical -- the evidence cap, the seniority cap, the calibration anchors, the
applied-job regression check -- because written rules in this codebase have been
forgotten twice. A second judging agent with an open licence to "nudge" is the
one component that could quietly undo all of them, so its licence is defined
here, in code, rather than in a prompt:

1. **It only sees close calls.** A posting is eligible only if its rubric score
   lands within `BAND` of the bar for its own bucket. Outside that band the
   tiebreaker never runs and cannot be invoked.
2. **It cannot decide, only lean.** `MAX_ADJUSTMENT` is smaller than the band,
   so a nudge can move a posting across the bar but can never move one from
   clearly-in to clearly-out or the reverse.
3. **It must quote.** Two verbatim quotes from the posting body, checked against
   the stored description character by character. An unquotable judgement is
   exactly the unfalsifiable "vibe" this design exists to prevent.
4. **It is capped per run.** `MAX_PER_RUN` bounds the blast radius of a bad
   session, and bounds the token cost of a good one.
5. **It is logged.** The adjustment and its evidence are stored in their own
   columns, never smeared into the rubric score, so `calibrate` can prove the
   anchors were untouched and any nudge can be read back months later.

Nothing here judges fit. Python selects who is eligible and audits what comes
back; the reading and the judgement are Claude's.
"""

from __future__ import annotations

import re
import sqlite3

from . import config

# How close to its bucket's bar a posting must land to be eligible at all.
# Doran set this at 0.20 on 2026-08-28, up from the 0.15 first proposed.
BAND = 0.20

# The most a single nudge may move a score, in either direction. Deliberately
# smaller than BAND: the tiebreaker breaks ties, it does not overturn scores.
MAX_ADJUSTMENT = 0.15

# Ceiling on how many postings one run may nudge. Doran's cap, 2026-08-28.
MAX_PER_RUN = 30

# Quotes shorter than this are not evidence -- "AI" appears in every posting.
MIN_QUOTE_CHARS = 25
MIN_QUOTES = 2

_WS = re.compile(r"\s+")


def _flat(text: str) -> str:
    """Whitespace-insensitive form, so a quote survives re-wrapped HTML."""
    return _WS.sub(" ", (text or "")).strip().lower()


def band_for(bucket: str) -> tuple[float, float]:
    """The (low, high) score window that makes a posting a close call."""
    bar = config.bucket_threshold(bucket)
    return (round(bar - BAND, 4), round(bar + BAND, 4))


def is_eligible(score: float | None, bucket: str) -> bool:
    if score is None:
        return False
    low, high = band_for(bucket)
    return low <= float(score) <= high


def candidates(conn: sqlite3.Connection, run_id: int | None = None,
               limit: int = MAX_PER_RUN) -> list[sqlite3.Row]:
    """Close calls, nearest the bar first, hard-capped.

    Ordering matters: when more than `limit` postings qualify, the ones the
    tiebreaker can most plausibly change are the ones sitting closest to the
    bar, so those are the ones kept.
    """
    sql = """
        SELECT p.*, e.id AS eval_id, e.weighted_score, e.track,
               e.connection_bonus, e.tiebreak_adjustment, e.fit_summary
        FROM postings p
        JOIN evaluations e ON e.id = (
            SELECT id FROM evaluations WHERE posting_id = p.id
            ORDER BY id DESC LIMIT 1
        )
        WHERE p.is_live = 1
          AND e.block_g_verdict != 'FAIL'
          AND (? IS NULL OR e.run_id = ?)
    """
    rows = conn.execute(sql, (run_id, run_id)).fetchall()

    scored = []
    for row in rows:
        bucket = config.bucket_of(row["tracks"])
        # Judge eligibility on the RUBRIC score, not on a score a previous
        # tiebreak already moved. Without this, nudges would compound across
        # runs and a posting could walk itself across the bar 0.15 at a time.
        base = float(row["weighted_score"] or 0) - float(row["tiebreak_adjustment"] or 0)
        if not is_eligible(base, bucket):
            continue
        scored.append((abs(base - config.bucket_threshold(bucket)), row))

    scored.sort(key=lambda pair: pair[0])
    return [row for _, row in scored[:limit]]


def base_score(row: sqlite3.Row) -> float:
    """The rubric score with any previous nudge removed."""
    return round(
        float(row["weighted_score"] or 0) - float(row["tiebreak_adjustment"] or 0), 3
    )


def audit(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every nudge currently standing, newest first.

    Printed by `calibrate --check`. A judgement that nobody ever reads back is
    indistinguishable from score inflation, so the whole set stays visible next
    to the anchors rather than living only in the run folder it was written in.
    """
    return conn.execute(
        """SELECT p.company, p.title, p.tracks, p.url,
                  e.weighted_score, e.tiebreak_adjustment, e.tiebreak_note,
                  e.evaluated_at
             FROM evaluations e
             JOIN postings p ON p.id = e.posting_id
            WHERE e.id = (SELECT id FROM evaluations
                           WHERE posting_id = p.id ORDER BY id DESC LIMIT 1)
              AND COALESCE(e.tiebreak_adjustment, 0) != 0
            ORDER BY e.id DESC"""
    ).fetchall()


def validate(adjustment: float, quotes: list[str], description: str,
             base: float, bucket: str) -> list[str]:
    """Every reason this nudge must be refused. Empty list means accept."""
    problems: list[str] = []

    if not is_eligible(base, bucket):
        low, high = band_for(bucket)
        problems.append(
            f"score {base:.2f} is outside the close-call band {low:.2f}-{high:.2f} "
            f"for bucket {bucket} - the tiebreaker does not apply to this posting"
        )

    if abs(adjustment) > MAX_ADJUSTMENT + 1e-9:
        problems.append(
            f"adjustment {adjustment:+.2f} exceeds the "
            f"{MAX_ADJUSTMENT:+.2f} limit"
        )

    real = [q for q in quotes if len(q.strip()) >= MIN_QUOTE_CHARS]
    if len(real) < MIN_QUOTES:
        problems.append(
            f"needs {MIN_QUOTES} quotes of at least {MIN_QUOTE_CHARS} characters "
            f"from the posting body, got {len(real)}"
        )

    haystack = _flat(description)
    for quote in real:
        if _flat(quote) not in haystack:
            snippet = quote.strip()[:70]
            problems.append(f"quote not found verbatim in the posting: {snippet!r}")

    return problems
