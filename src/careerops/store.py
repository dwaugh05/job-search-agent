"""SQLite persistence. This database -- not the conversation -- is the source of truth.

It holds three things the agent could not otherwise remember between sessions:
  1. What Doran has already been shown, so nothing is ever repeated.
  2. What he thought of each posting, so the rubric can learn.
  3. Sighting history per fingerprint, which is what exposes perpetual reposts.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import config
from .fingerprint import (
    description_hash,
    fingerprint as compute_fingerprint,
    normalize_company,
    normalize_title,
)
from .models import (
    STATE_EVALUATED,
    STATE_NEW,
    STATE_PRESENTED,
    SUPPRESSED_STATES,
    Posting,
)
from .normalize import now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mode            TEXT NOT NULL,
    params          TEXT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    raw_count       INTEGER DEFAULT 0,
    prefilter_pass  INTEGER DEFAULT 0,
    evaluated_count INTEGER DEFAULT 0,
    presented_count INTEGER DEFAULT 0,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS postings (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint      TEXT NOT NULL,
    description_hash TEXT NOT NULL,
    source_id        TEXT NOT NULL,
    ats              TEXT NOT NULL,
    source_slug      TEXT NOT NULL DEFAULT '',
    company          TEXT NOT NULL,
    title            TEXT NOT NULL,
    url              TEXT NOT NULL,
    apply_url        TEXT,
    location_raw     TEXT,
    city             TEXT,
    region           TEXT,
    country          TEXT,
    work_model       TEXT,
    department       TEXT,
    team             TEXT,
    employment_type  TEXT,
    salary_min       INTEGER,
    salary_max       INTEGER,
    salary_raw       TEXT,
    equity_mentioned INTEGER DEFAULT 0,
    bonus_mentioned  INTEGER DEFAULT 0,
    published_at     TEXT,
    date_confidence  TEXT DEFAULT 'none',
    description      TEXT,
    first_seen       TEXT NOT NULL,
    last_seen        TEXT NOT NULL,
    last_live_check  TEXT,
    is_live          INTEGER DEFAULT 1,
    state            TEXT NOT NULL DEFAULT 'new',
    prefilter_reason TEXT,
    UNIQUE (ats, source_slug, source_id)
);

CREATE INDEX IF NOT EXISTS idx_postings_fingerprint ON postings (fingerprint);
CREATE INDEX IF NOT EXISTS idx_postings_state       ON postings (state);
CREATE INDEX IF NOT EXISTS idx_postings_company     ON postings (company);

CREATE TABLE IF NOT EXISTS sightings (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    posting_id            INTEGER NOT NULL REFERENCES postings (id),
    run_id                INTEGER REFERENCES runs (id),
    fingerprint           TEXT NOT NULL,
    seen_at               TEXT NOT NULL,
    published_at_reported TEXT
);

CREATE INDEX IF NOT EXISTS idx_sightings_fp ON sightings (fingerprint);

CREATE TABLE IF NOT EXISTS evaluations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    posting_id      INTEGER NOT NULL REFERENCES postings (id),
    run_id          INTEGER REFERENCES runs (id),
    rubric_version  TEXT,
    dimension_scores TEXT NOT NULL,
    block_notes     TEXT,
    weighted_score  REAL NOT NULL,
    block_g_verdict TEXT NOT NULL DEFAULT 'PASS',
    block_g_flags   TEXT,
    fit_summary     TEXT,
    evaluated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evaluations_posting ON evaluations (posting_id);

CREATE TABLE IF NOT EXISTS presentations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    posting_id INTEGER NOT NULL REFERENCES postings (id),
    run_id     INTEGER REFERENCES runs (id),
    shown_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verdicts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    posting_id INTEGER NOT NULL REFERENCES postings (id),
    verdict    TEXT NOT NULL,
    reason     TEXT,
    created_at TEXT NOT NULL
);

-- Companies a board search surfaced but that we ran out of resolve budget for.
-- Before this table existed the scan printed "they will be picked up next run"
-- and then forgot them: a company skipped here was only ever retried if it
-- happened to show up in a future search by luck. Now the next run drains this
-- first, so the budget carries over instead of resetting.
--
-- `company` holds the NORMALIZED name, not what the board printed. LinkedIn,
-- Built In and Hacker News each spell an employer differently -- "Databricks",
-- "databricks", "Databricks Inc." -- and keyed raw those are three rows, three
-- of the sixty cap slots, three resolution attempts at ~45 requests each in the
-- same run, and three separate attempt counters. `display` keeps a real name to
-- hand to the resolver and to print.
CREATE TABLE IF NOT EXISTS resolve_backlog (
    company     TEXT PRIMARY KEY,
    display     TEXT,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    times_seen  INTEGER DEFAULT 1,
    attempts    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS learned_rules (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_text  TEXT NOT NULL,
    dimension  TEXT,
    verdict_id INTEGER REFERENCES verdicts (id),
    created_at TEXT NOT NULL,
    active     INTEGER DEFAULT 1
);
"""


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    config.ensure_dirs()
    path = db_path or config.DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Columns added after the first release. Applied idempotently so an existing
# jobs.db picks them up without a rebuild.
_MIGRATIONS = [
    ("postings", "tracks", "TEXT DEFAULT ''"),
    ("postings", "audience", "TEXT"),
    ("postings", "ai_fluency_requested", "INTEGER DEFAULT 0"),
    ("evaluations", "track", "TEXT DEFAULT 'ai_enablement'"),
    ("evaluations", "scope_modifier", "REAL DEFAULT 0"),
    ("evaluations", "connection_bonus", "REAL DEFAULT 0"),
    # Kept in their own columns, never smeared into weighted_score alone, so a
    # holistic nudge can always be told apart from a rubric judgement and can be
    # unwound. See tiebreak.py for why the licence is this narrow.
    ("evaluations", "tiebreak_adjustment", "REAL DEFAULT 0"),
    ("evaluations", "tiebreak_note", "TEXT"),
    ("evaluations", "tiebreak_quotes", "TEXT"),
    ("resolve_backlog", "display", "TEXT"),
]


def init_db(db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        for table, column, decl in _MIGRATIONS:
            existing = {
                row["name"] for row in conn.execute(f"PRAGMA table_info({table})")
            }
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


# ------------------------------------------------------- board resolve backlog


def backlog_key(company: str | None) -> str:
    """The identity a company is tracked under. See the table comment above."""
    return normalize_company(company)


def queue_resolve_backlog(conn: sqlite3.Connection, companies: list[str]) -> None:
    """Remember employers we found but had no resolve budget left for."""
    stamp = now_iso()
    for company in companies:
        name = (company or "").strip()
        key = backlog_key(name)
        if not name or not key:
            continue
        conn.execute(
            """INSERT INTO resolve_backlog (company, display, first_seen, last_seen)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(company) DO UPDATE SET
                   last_seen = excluded.last_seen,
                   times_seen = times_seen + 1""",
            (key, name, stamp, stamp),
        )


# Some companies have no ATS this system can find -- no standard board, or a
# careers page that only a browser can read. Retrying those forever costs ~45
# probes each, every run, and steals cap slots from companies that would
# actually resolve. After this many failures a company is parked rather than
# deleted, so `cli.py resolve-company` by hand still knows it was seen.
BACKLOG_MAX_ATTEMPTS = 3


def take_resolve_backlog(conn: sqlite3.Connection, limit: int) -> list[str]:
    """Oldest-first, so a company cannot be starved run after run.

    Ordering by attempts and then first_seen means anything untried goes ahead
    of anything already tried, and nothing sits at the back forever. Companies
    past BACKLOG_MAX_ATTEMPTS are skipped entirely -- see the constant above.
    """
    if limit <= 0:
        return []
    rows = conn.execute(
        """SELECT company, display FROM resolve_backlog
           WHERE attempts < ?
           ORDER BY attempts ASC, first_seen ASC, times_seen DESC
           LIMIT ?""",
        (BACKLOG_MAX_ATTEMPTS, limit),
    ).fetchall()
    # The resolver needs a real name, not the normalized key.
    return [row["display"] or row["company"] for row in rows]


def clear_resolve_backlog(conn: sqlite3.Connection, companies: list[str]) -> None:
    """Drop companies we have now resolved -- they live in sources.yml instead."""
    for company in companies:
        conn.execute("DELETE FROM resolve_backlog WHERE company = ?",
                     (backlog_key(company),))


def bump_resolve_attempts(conn: sqlite3.Connection, companies: list[str]) -> None:
    """Record a failed resolution attempt.

    Inserts as well as updates on purpose. A company found on a board this run
    and tried for the first time is not in the table yet, and before this it was
    simply forgotten -- so the next run re-probed it at ~45 requests, and the run
    after that, forever, while it also ate a slot under the resolve cap. Now the
    failure is remembered and counts toward BACKLOG_MAX_ATTEMPTS.
    """
    stamp = now_iso()
    for company in companies:
        name = (company or "").strip()
        if not name:
            continue
        key = backlog_key(name)
        if not key:
            continue
        conn.execute(
            """INSERT INTO resolve_backlog
                   (company, display, first_seen, last_seen, attempts)
               VALUES (?, ?, ?, ?, 1)
               ON CONFLICT(company) DO UPDATE SET
                   attempts = attempts + 1,
                   last_seen = excluded.last_seen""",
            (key, name, stamp, stamp),
        )


def resolve_backlog_size(conn: sqlite3.Connection) -> int:
    """How many companies are still worth retrying."""
    return int(conn.execute(
        "SELECT COUNT(*) AS n FROM resolve_backlog WHERE attempts < ?",
        (BACKLOG_MAX_ATTEMPTS,),
    ).fetchone()["n"])


def resolve_backlog_exhausted(conn: sqlite3.Connection) -> list[str]:
    """Companies we have given up resolving automatically.

    Kept rather than deleted: these are real employers with real postings that
    this system cannot find a board for, and `cli.py resolve-company "<name>"`
    tries much harder than a bulk run can afford to.
    """
    rows = conn.execute(
        """SELECT company, display FROM resolve_backlog
           WHERE attempts >= ? ORDER BY company""",
        (BACKLOG_MAX_ATTEMPTS,),
    ).fetchall()
    return [row["display"] or row["company"] for row in rows]


# ------------------------------------------------------------------------ runs


def start_run(conn: sqlite3.Connection, mode: str, params: dict | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO runs (mode, params, started_at) VALUES (?, ?, ?)",
        (mode, json.dumps(params or {}), now_iso()),
    )
    return int(cur.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, **counts: Any) -> None:
    fields = ", ".join(f"{k} = ?" for k in counts)
    values = list(counts.values())
    sql = "UPDATE runs SET finished_at = ?" + (f", {fields}" if fields else "") + " WHERE id = ?"
    conn.execute(sql, [now_iso(), *values, run_id])


def latest_run(conn: sqlite3.Connection, mode: str | None = None) -> sqlite3.Row | None:
    if mode:
        return conn.execute(
            "SELECT * FROM runs WHERE mode = ? ORDER BY id DESC LIMIT 1", (mode,)
        ).fetchone()
    return conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()


# -------------------------------------------------------------------- postings


def upsert_posting(
    conn: sqlite3.Connection, posting: Posting, run_id: int | None = None
) -> tuple[int, bool]:
    """Insert or refresh a posting. Returns (posting_id, is_new)."""
    fp = compute_fingerprint(posting.company, posting.title, posting.description)
    dhash = description_hash(posting.description)
    timestamp = now_iso()

    existing = conn.execute(
        "SELECT id, first_seen FROM postings WHERE ats = ? AND source_slug = ? AND source_id = ?",
        (posting.ats, posting.source_slug, posting.source_id),
    ).fetchone()

    if existing:
        posting_id = int(existing["id"])
        conn.execute(
            """
            UPDATE postings SET
                fingerprint = ?, description_hash = ?, company = ?, title = ?,
                url = ?, apply_url = ?, location_raw = ?, city = ?, region = ?,
                country = ?, work_model = ?, department = ?, team = ?,
                employment_type = ?, salary_min = ?, salary_max = ?, salary_raw = ?,
                equity_mentioned = ?, bonus_mentioned = ?, published_at = ?,
                date_confidence = ?, description = ?, last_seen = ?, is_live = 1
            WHERE id = ?
            """,
            (
                fp, dhash, posting.company, posting.title, posting.url,
                posting.apply_url, posting.location_raw, posting.city, posting.region,
                posting.country, posting.workplace_type, posting.department,
                posting.team, posting.employment_type, posting.salary_min,
                posting.salary_max, posting.salary_raw, int(posting.equity_mentioned),
                int(posting.bonus_mentioned), posting.published_at,
                posting.date_confidence, posting.description, timestamp, posting_id,
            ),
        )
        is_new = False
    else:
        cur = conn.execute(
            """
            INSERT INTO postings (
                fingerprint, description_hash, source_id, ats, source_slug, company,
                title, url, apply_url, location_raw, city, region, country,
                work_model, department, team, employment_type, salary_min, salary_max,
                salary_raw, equity_mentioned, bonus_mentioned, published_at,
                date_confidence, description, first_seen, last_seen, state
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                fp, dhash, posting.source_id, posting.ats, posting.source_slug,
                posting.company, posting.title, posting.url, posting.apply_url,
                posting.location_raw, posting.city, posting.region, posting.country,
                posting.workplace_type, posting.department, posting.team,
                posting.employment_type, posting.salary_min, posting.salary_max,
                posting.salary_raw, int(posting.equity_mentioned),
                int(posting.bonus_mentioned), posting.published_at,
                posting.date_confidence, posting.description, timestamp, timestamp,
                STATE_NEW,
            ),
        )
        posting_id = int(cur.lastrowid)
        is_new = True

    conn.execute(
        """INSERT INTO sightings (posting_id, run_id, fingerprint, seen_at,
                                  published_at_reported)
           VALUES (?, ?, ?, ?, ?)""",
        (posting_id, run_id, fp, timestamp, posting.published_at),
    )
    return posting_id, is_new


def get_posting(conn: sqlite3.Connection, posting_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM postings WHERE id = ?", (posting_id,)).fetchone()


def set_state(conn: sqlite3.Connection, posting_id: int, state: str,
              reason: str | None = None) -> None:
    if reason is None:
        conn.execute("UPDATE postings SET state = ? WHERE id = ?", (state, posting_id))
    else:
        conn.execute(
            "UPDATE postings SET state = ?, prefilter_reason = ? WHERE id = ?",
            (state, reason, posting_id),
        )


def mark_dead(conn: sqlite3.Connection, posting_id: int) -> None:
    conn.execute(
        "UPDATE postings SET is_live = 0, last_live_check = ? WHERE id = ?",
        (now_iso(), posting_id),
    )


def mark_live_checked(conn: sqlite3.Connection, posting_id: int, live: bool) -> None:
    conn.execute(
        "UPDATE postings SET is_live = ?, last_live_check = ? WHERE id = ?",
        (int(live), now_iso(), posting_id),
    )


def suppressed_fingerprints(conn: sqlite3.Connection) -> set[str]:
    """Every fingerprint Doran has already been shown, in any form.

    Queried by fingerprint rather than by posting id on purpose: that is what
    keeps a rejected role suppressed when it reappears next month under a fresh
    ATS id with a lightly edited description.
    """
    placeholders = ",".join("?" for _ in SUPPRESSED_STATES)
    rows = conn.execute(
        f"SELECT DISTINCT fingerprint FROM postings WHERE state IN ({placeholders})",
        tuple(SUPPRESSED_STATES),
    ).fetchall()
    return {row["fingerprint"] for row in rows}


# Sources where the posting body came off a board page rather than the employer's
# own feed. The two texts for one job differ enough that they fingerprint apart.
BOARD_SOURCES = ("linkedin", "builtin", "hn", "boards")


def suppressed_board_roles(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    """Roles already shown whose stored copy came from a board, by name.

    The fingerprint covers a repost of the same text. It cannot cover the same
    job arriving twice by two different routes: a company over the resolve cap
    gets its posting read off LinkedIn this run and swept from its own ATS the
    next, and those two bodies are written differently enough to hash apart. The
    result is Doran shown the same role twice, which is the one thing the
    suppression rule exists to prevent.

    Matched on normalized company and title rather than on text, because the
    text is exactly what differs. Restricted to roles whose stored copy is
    board-sourced so this cannot quietly suppress a genuinely separate opening
    that happens to share a title.
    """
    placeholders = ",".join("?" for _ in SUPPRESSED_STATES)
    boards = ",".join("?" for _ in BOARD_SOURCES)
    rows = conn.execute(
        f"""SELECT DISTINCT company, title FROM postings
            WHERE state IN ({placeholders}) AND ats IN ({boards})""",
        tuple(SUPPRESSED_STATES) + BOARD_SOURCES,
    ).fetchall()
    return {
        (normalize_company(row["company"]), normalize_title(row["title"]))
        for row in rows
    }


def already_evaluated(conn: sqlite3.Connection, rubric_version: str) -> set[str]:
    """Fingerprints already scored under the current rubric.

    Without this, every posting that scored below 4.0 gets re-queued on the next
    run and re-scored to the same number forever. Keyed on rubric version, so
    changing the rubric correctly re-opens everything for scoring.
    """
    rows = conn.execute(
        """SELECT DISTINCT p.fingerprint
           FROM postings p JOIN evaluations e ON e.posting_id = p.id
           WHERE e.rubric_version = ?""",
        (str(rubric_version),),
    ).fetchall()
    return {row["fingerprint"] for row in rows}


def postings_in_state(conn: sqlite3.Connection, state: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM postings WHERE state = ? ORDER BY id", (state,)
    ).fetchall()


def repost_signals(conn: sqlite3.Connection, fingerprint_value: str) -> dict[str, Any]:
    """Evidence for Block G's perpetual-repost check.

    A legitimate role is posted once. A ghost job gets taken down and relisted
    over and over -- which shows up here as several distinct ATS ids sharing one
    fingerprint, and/or a published_at that keeps resetting forward.
    """
    rows = conn.execute(
        """SELECT DISTINCT posting_id, published_at_reported
           FROM sightings WHERE fingerprint = ? ORDER BY seen_at""",
        (fingerprint_value,),
    ).fetchall()
    distinct_ids = {row["posting_id"] for row in rows}
    dates = sorted({row["published_at_reported"] for row in rows if row["published_at_reported"]})
    return {
        "distinct_posting_ids": len(distinct_ids),
        "distinct_published_dates": len(dates),
        "published_dates": dates,
        "perpetual_repost": len(distinct_ids) > 1 or len(dates) > 1,
    }


# ----------------------------------------------------------------- evaluations


def record_evaluation(
    conn: sqlite3.Connection,
    posting_id: int,
    *,
    run_id: int | None,
    rubric_version: str,
    dimension_scores: dict[str, float],
    weighted_score: float,
    block_g_verdict: str,
    block_g_flags: list[str] | None,
    fit_summary: str,
    block_notes: dict[str, str] | None = None,
    track: str = "ai_enablement",
    scope_modifier: float = 0.0,
    connection_bonus: float = 0.0,
) -> int:
    cur = conn.execute(
        """INSERT INTO evaluations (
               posting_id, run_id, rubric_version, dimension_scores, block_notes,
               weighted_score, block_g_verdict, block_g_flags, fit_summary,
               evaluated_at, track, scope_modifier, connection_bonus)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            posting_id, run_id, rubric_version, json.dumps(dimension_scores),
            json.dumps(block_notes or {}), weighted_score, block_g_verdict,
            json.dumps(block_g_flags or []), fit_summary, now_iso(),
            track, scope_modifier, connection_bonus,
        ),
    )
    # Only advance the state forward. Re-running record-eval after a report or a
    # verdict must NOT drag a posting back to `evaluated`: that would resurrect
    # something Doran has already seen (breaking the never-show-twice rule) and
    # silently drop it off /shortlist while its verdict row still exists.
    current = conn.execute(
        "SELECT state FROM postings WHERE id = ?", (posting_id,)
    ).fetchone()
    if not current or current[0] not in SUPPRESSED_STATES:
        set_state(conn, posting_id, STATE_EVALUATED)
    return int(cur.lastrowid)


def first_seen_of(conn: sqlite3.Connection, posting_id: int) -> str | None:
    """When this tool first saw this posting, regardless of what the feed claims.

    This is the one date nobody can rewrite. Greenhouse's own published figures
    put 18-22% of ATS postings in the ghost category, Ashby ships "evergreen"
    reqs as a feature, and reposting a job resets its visible publish date -- so
    a feed's `published_at` can say "3 days ago" about a req that has been open
    all year. Our own first sighting cannot lie about that.
    """
    row = conn.execute(
        "SELECT first_seen FROM postings WHERE id = ?", (posting_id,)
    ).fetchone()
    return row["first_seen"] if row else None


def latest_evaluation(conn: sqlite3.Connection, posting_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM evaluations WHERE posting_id = ? ORDER BY id DESC LIMIT 1",
        (posting_id,),
    ).fetchone()


def apply_tiebreak(conn: sqlite3.Connection, eval_id: int, *,
                   base_score: float, adjustment: float, note: str,
                   quotes: list[str], max_score: float = 5.0) -> float:
    """Write a bounded holistic nudge onto an existing evaluation.

    Rewrites `weighted_score` from the BASE score every time rather than adding
    to whatever is there, so re-running the tiebreaker replaces a previous nudge
    instead of stacking on it. The adjustment and its evidence stay in their own
    columns, which is what lets `calibrate` prove the anchors were not touched.
    """
    final = min(max_score, max(1.0, round(base_score + adjustment, 3)))
    conn.execute(
        """UPDATE evaluations
              SET weighted_score = ?, tiebreak_adjustment = ?,
                  tiebreak_note = ?, tiebreak_quotes = ?
            WHERE id = ?""",
        (final, round(adjustment, 3), note, json.dumps(quotes), eval_id),
    )
    return final


def presentable(conn: sqlite3.Connection, threshold: float,
                run_id: int | None = None,
                track: str | None = None,
                bucket: str | None = None) -> list[sqlite3.Row]:
    """Evaluated postings that clear the bar, pass Block G, are live, and are unseen.

    `track` selects which list by the track its SCORE was recorded under.

    `bucket` selects by which of the three buckets the POSTING belongs to,
    derived from postings.tracks. The two are different questions and must not
    be combined: a marketing-only posting's only evaluation is recorded under
    growth_marketing, so filtering on both would return nothing. When a bucket
    is given the track filter is deliberately dropped.

    The three buckets are disjoint by construction -- a posting has exactly one
    -- so bucket routing needs no dedupe between lists.
    """
    if bucket is not None:
        track = None
    sql = """
        SELECT p.*, e.weighted_score, e.fit_summary, e.block_g_verdict,
               e.block_g_flags, e.track, e.connection_bonus,
               e.tiebreak_adjustment, e.tiebreak_note
        FROM postings p
        JOIN evaluations e ON e.id = (
            SELECT id FROM evaluations
            WHERE posting_id = p.id AND (? IS NULL OR track = ?)
            ORDER BY id DESC LIMIT 1
        )
        WHERE p.state = ?
          AND p.is_live = 1
          AND e.weighted_score >= ?
          AND e.block_g_verdict != 'FAIL'
        ORDER BY e.weighted_score DESC
    """
    rows = conn.execute(sql, (track, track, STATE_EVALUATED, threshold)).fetchall()
    if bucket is None:
        return rows
    return [r for r in rows if config.bucket_of(r["tracks"]) == bucket]


def worth_knowing(conn: sqlite3.Connection, threshold: float,
                  floor: float, limit: int = 3,
                  track: str | None = None,
                  bucket: str | None = None) -> list[sqlite3.Row]:
    """Evaluated postings just under the bar, so nothing good is silently hidden.

    Hard-capped and rendered as one line each -- this exists so a near-miss gets
    a mention, not so the report can quietly grow into a spray-and-pray list.

    `track` scopes this to one list's near-misses. Without it, a track with
    generally higher scores (e.g. growth) can fill the whole cap and silently
    crowd out near-misses from the other track -- exactly the hiding this
    function exists to prevent.
    """
    if bucket is not None:
        track = None
    sql = """
        SELECT p.*, e.weighted_score, e.fit_summary, e.block_g_verdict, e.block_g_flags
        FROM postings p
        JOIN evaluations e ON e.id = (
            SELECT id FROM evaluations
            WHERE posting_id = p.id AND (? IS NULL OR track = ?)
            ORDER BY id DESC LIMIT 1
        )
        WHERE p.state = ? AND p.is_live = 1
          AND e.weighted_score < ? AND e.weighted_score >= ?
          AND e.block_g_verdict != 'FAIL'
        ORDER BY e.weighted_score DESC
    """
    rows = conn.execute(
        sql, (track, track, STATE_EVALUATED, threshold, floor),
    ).fetchall()
    if bucket is not None:
        rows = [r for r in rows if config.bucket_of(r["tracks"]) == bucket]
    # LIMIT is applied here rather than in SQL so the cap counts rows in THIS
    # bucket. Applied in the query it would be spent on other buckets' rows and
    # silently return fewer than the cap allows.
    return rows[:limit]


def near_misses(conn: sqlite3.Connection, threshold: float,
                companies: Iterable[str]) -> list[sqlite3.Row]:
    """Best sub-threshold role per named company. Targeted scans only."""
    names = [c.strip().lower() for c in companies if c and c.strip()]
    if not names:
        return []
    placeholders = ",".join("?" for _ in names)
    sql = f"""
        SELECT p.company, p.title, MAX(e.weighted_score) AS best_score,
               COUNT(*) AS evaluated_count
        FROM postings p
        JOIN evaluations e ON e.posting_id = p.id
        WHERE LOWER(p.company) IN ({placeholders})
          AND e.weighted_score < ?
          AND p.state = ?
        GROUP BY LOWER(p.company)
        ORDER BY best_score DESC
    """
    return conn.execute(sql, (*names, threshold, STATE_EVALUATED)).fetchall()


# --------------------------------------------------------- presenting/verdicts


def mark_presented(conn: sqlite3.Connection, posting_ids: Iterable[int],
                   run_id: int | None = None) -> int:
    timestamp = now_iso()
    count = 0
    for posting_id in posting_ids:
        conn.execute(
            "INSERT INTO presentations (posting_id, run_id, shown_at) VALUES (?,?,?)",
            (posting_id, run_id, timestamp),
        )
        set_state(conn, posting_id, STATE_PRESENTED)
        count += 1
    return count


def record_verdict(conn: sqlite3.Connection, posting_id: int, verdict: str,
                   reason: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO verdicts (posting_id, verdict, reason, created_at) VALUES (?,?,?,?)",
        (posting_id, verdict, reason, now_iso()),
    )
    set_state(conn, posting_id, verdict)
    return int(cur.lastrowid)


def awaiting_verdict(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT p.*, e.weighted_score, e.fit_summary
           FROM postings p
           LEFT JOIN evaluations e ON e.id = (
               SELECT id FROM evaluations WHERE posting_id = p.id ORDER BY id DESC LIMIT 1
           )
           WHERE p.state = ?
           ORDER BY e.weighted_score DESC""",
        (STATE_PRESENTED,),
    ).fetchall()


def shortlist(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT p.*, e.weighted_score, e.fit_summary, v.verdict, v.reason
           FROM postings p
           LEFT JOIN evaluations e ON e.id = (
               SELECT id FROM evaluations WHERE posting_id = p.id ORDER BY id DESC LIMIT 1
           )
           LEFT JOIN verdicts v ON v.id = (
               SELECT id FROM verdicts WHERE posting_id = p.id ORDER BY id DESC LIMIT 1
           )
           WHERE p.state IN ('interested', 'saved', 'applied')
           ORDER BY e.weighted_score DESC""",
    ).fetchall()


def prior_applications(conn: sqlite3.Connection) -> dict[str, list[tuple[str, str]]]:
    """Every company Doran has already applied to -> [(date, title), ...].

    Keyed on the normalized company name so "Coupa" and "Coupa Software" are the
    same employer. Doran, 2026-08-26: reading a new posting he wants to know he
    already has an application in at that company, and which role it was, so the
    two do not collide.
    """
    out: dict[str, list[tuple[str, str]]] = {}
    rows = conn.execute(
        """SELECT p.company, p.title, v.created_at
           FROM postings p JOIN verdicts v ON v.posting_id = p.id
           WHERE v.verdict = 'applied'
           ORDER BY v.created_at DESC"""
    ).fetchall()
    for row in rows:
        key = normalize_company(row["company"])
        if not key:
            continue
        entry = (str(row["created_at"] or "")[:10], row["title"])
        if entry not in out.setdefault(key, []):
            out[key].append(entry)
    return out


def applied_postings(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Everything Doran applied to, newest application first.

    Joined to the verdict row rather than the posting, because the date he
    applied is the date he said so -- `postings` has no such field.
    """
    return conn.execute(
        """SELECT p.*, e.weighted_score, e.fit_summary, e.connection_bonus,
                  v.reason, v.created_at AS applied_at
           FROM postings p
           LEFT JOIN evaluations e ON e.id = (
               SELECT id FROM evaluations WHERE posting_id = p.id ORDER BY id DESC LIMIT 1
           )
           LEFT JOIN verdicts v ON v.id = (
               SELECT id FROM verdicts WHERE posting_id = p.id AND verdict = 'applied'
               ORDER BY id DESC LIMIT 1
           )
           WHERE p.state = 'applied'
           ORDER BY v.created_at DESC""",
    ).fetchall()


def add_learned_rule(conn: sqlite3.Connection, rule_text: str,
                     dimension: str | None = None,
                     verdict_id: int | None = None) -> int:
    cur = conn.execute(
        """INSERT INTO learned_rules (rule_text, dimension, verdict_id, created_at)
           VALUES (?,?,?,?)""",
        (rule_text, dimension, verdict_id, now_iso()),
    )
    return int(cur.lastrowid)


def stats(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT state, COUNT(*) AS n FROM postings GROUP BY state"
    ).fetchall()
    by_state = {row["state"]: row["n"] for row in rows}
    total = conn.execute("SELECT COUNT(*) AS n FROM postings").fetchone()["n"]
    runs = conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"]
    rules = conn.execute(
        "SELECT COUNT(*) AS n FROM learned_rules WHERE active = 1"
    ).fetchone()["n"]
    return {"total_postings": total, "by_state": by_state, "runs": runs,
            "learned_rules": rules}
