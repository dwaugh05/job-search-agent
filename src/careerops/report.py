"""Output rendering.

Two artifacts, deliberately different:

  * The terminal report is EXACTLY the eight fields Doran asked for. Scores and
    Block G detail stay out of it. The single exception is a Block G FLAG, which
    adds one warning line -- hiding a legitimacy concern would defeat the point
    of running the check.

  * The run report on disk carries the full audit trail: scores per dimension,
    Block G findings, and the funnel counts.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from . import commute as commute_mod
from . import comp as comp_mod
from . import config, store
from .models import WORK_REMOTE
from .normalize import age_days

FIELDS_NOTE = (
    "Fit Summary explains the match against Doran's actual proof points and names "
    "any gap."
)


def _salary_field(row: sqlite3.Row) -> str:
    listed = comp_mod.format_range(row["salary_min"], row["salary_max"])
    return listed or "Not listed"


def _flags(row: sqlite3.Row) -> list[str]:
    try:
        return json.loads(row["block_g_flags"] or "[]")
    except (json.JSONDecodeError, TypeError):
        return []


def _posted_field(row: sqlite3.Row) -> str:
    published = row["published_at"]
    if not published:
        return "Not stated"
    age = age_days(published)
    stamp = str(published)[:10]
    return f"{stamp} ({age:.0f} days ago)" if age is not None else stamp


def commute_field(row: sqlite3.Row) -> str | None:
    """One-line commute estimate, for hybrid and on-site roles only.

    Doran asked for this on 2026-08-15: a work model of "Hybrid" or "On-site"
    is not actionable on its own, because a San Carlos office and a San
    Francisco office are the same word and a 40-minute difference. Remote roles
    return None -- there is nothing to state.
    """
    if row["work_model"] == WORK_REMOTE:
        return None
    result = commute_mod.evaluate(row["city"], row["work_model"])
    if not result.known:
        city = row["city"] or row["location_raw"] or "this location"
        return (f"Estimated Commute: unknown for {city} - not in config/commute.yml, "
                "so this is unscored rather than assumed")
    return f"Estimated Commute: {result.minutes} min door-to-door from San Mateo 94403"


def aggregator_slugs() -> set[str]:
    """ATS slugs that belong to job boards reposting other companies' roles.

    Jobgether and its kind run a real Lever board, so structurally they look
    exactly like an employer. Nothing in the feed says otherwise -- only this
    list does.
    """
    listed = (config.profile().get("discovery") or {}).get("aggregator_slugs") or []
    return {str(slug).strip().lower() for slug in listed if str(slug).strip()}


def is_aggregator(row: sqlite3.Row) -> bool:
    try:
        slug = (row["source_slug"] or "").strip().lower()
    except (IndexError, KeyError, TypeError):
        return False
    # source_slug is "<slug>" on Lever/Greenhouse and "<slug>:<tenant>:<board>"
    # on Workday, so compare the leading segment.
    return slug.split(":")[0] in aggregator_slugs()


def _company_field(row: sqlite3.Row) -> str:
    """Who is hiring, as the first line of every posting block.

    Doran asked for this on 2026-08-25: a report of ten roles with titles, links
    and commutes but no employer names is unreadable at a glance -- he could not
    tell which company any of them was for without opening the link.

    Where the posting came through a reseller that hides its client, the reseller
    is named as the reseller rather than presented as the employer. The Block G
    warning line already says the employer is unnamed; this stops the top line
    from asserting something untrue.
    """
    name = (row["company"] or "").strip() or "Not stated"
    if is_aggregator(row):
        return f"{name} (job board - actual employer not named)"
    return name


def _connection_field(row: sqlite3.Row) -> str | None:
    """Say out loud that a score was raised by a personal connection.

    The bump is worth nothing if it is invisible: Doran needs to know a role
    ranked where it did partly because he knows someone there, otherwise the
    ranking looks arbitrary and he stops trusting it.
    """
    try:
        bonus = float(row["connection_bonus"] or 0)
    except (IndexError, KeyError, TypeError, ValueError):
        return None
    if not bonus:
        return None
    return (f"Connection: you know someone at {row['company']} - "
            f"score includes a +{bonus:.1f} bump for the warm intro")


def _tiebreak_field(row: sqlite3.Row) -> str | None:
    """Say out loud that a close call was settled by a holistic read.

    Same reasoning as the connection bump: an adjustment Doran cannot see is an
    adjustment he cannot argue with. A nudge is the one score movement in this
    system that came from judgement rather than from the rubric, so it is the
    one that most needs to be visible and challengeable.
    """
    try:
        adjustment = float(row["tiebreak_adjustment"] or 0)
    except (IndexError, KeyError, TypeError, ValueError):
        return None
    if not adjustment:
        return None
    try:
        note = str(row["tiebreak_note"] or "").strip()
    except (IndexError, KeyError):
        note = ""
    line = (f"Tiebreak: this was a close call and I moved it {adjustment:+.2f} "
            "after reading the full posting")
    return f"{line} - {note}" if note else line


def _named_stack(row: sqlite3.Row) -> str | None:
    """Third-party platforms an anonymized posting names, as an identity clue.

    Doran asked on 2026-08-26 for a way to sanity-check who is really hiring
    behind a reseller listing. Searching the web for a matching posting was the
    obvious idea and does not work: the reseller rewrites the text, its own site
    refuses scripted requests, and a title search on the live boards returns
    nothing. What the posting cannot hide is the stack it expects you to work in.
    "Salesforce, Seismic, Gong, Snowflake, Slack" alongside "seller feedback" is
    a sales-tech company and narrows the field a long way.

    Only shown on reseller listings -- on a named employer it is noise.
    """
    if not is_aggregator(row):
        return None
    listed = (config.profile().get("discovery") or {}).get("stack_tells") or []
    if not listed:
        return None
    import re as _re

    body = row["description"] or ""
    pattern = _re.compile(
        r"\b(" + "|".join(_re.escape(str(t)) for t in listed) + r")\b", _re.IGNORECASE
    )
    seen: dict[str, str] = {}
    for match in pattern.finditer(body):
        seen.setdefault(match.group(1).lower(), match.group(1))
    if len(seen) < 3:
        # One or two generic tools say nothing. Three is a stack.
        return None
    names = sorted(seen.values(), key=str.lower)
    return ("Stack named in the posting: " + ", ".join(names)
            + " - use this to work out who is actually hiring")


def _also_hiring_field(row: sqlite3.Row, rows: list[sqlite3.Row]) -> str | None:
    """Name the company's OTHER roles in this same report.

    Doran, 2026-08-26: "I might just read through the list sequentially and apply
    to the first one I see and not even take a chance to apply to the second one
    when it might have better fit." Three Coupa roles in one report is exactly
    that trap -- the second and third are easy to miss.
    """
    from .fingerprint import normalize_company

    me = normalize_company(row["company"])
    siblings = [
        other["title"] for other in rows
        if other["id"] != row["id"] and normalize_company(other["company"]) == me
    ]
    if not siblings:
        return None
    listed = "; ".join(f'"{title}"' for title in siblings)
    return (f"Also in this report from {row['company']}: {listed} "
            f"- read {'both' if len(siblings) == 1 else 'all'} before applying")


def _already_applied_field(row: sqlite3.Row,
                           prior: dict[str, list[tuple[str, str]]] | None) -> str | None:
    """Say when Doran already has an application in at this employer.

    Asked for on 2026-08-26: knowing there is an existing application, and which
    role it was, changes how he reads a new posting from the same company.
    """
    if not prior:
        return None
    from .fingerprint import normalize_company

    history = prior.get(normalize_company(row["company"]))
    if not history:
        return None
    # Never flag the posting against itself.
    others = [(when, title) for when, title in history if title != row["title"]]
    if not others:
        return None
    listed = "; ".join(f'"{title}" on {when}' for when, title in others[:3])
    more = f" (+{len(others) - 3} more)" if len(others) > 3 else ""
    return f"Already applied at {row['company']}: {listed}{more}"


def render_matches(rows: list[sqlite3.Row],
                   prior_applications: dict | None = None) -> str:
    """The match list Doran reads.

    Eight fields, plus a ninth on hybrid and on-site roles only: the estimated
    commute in minutes. Posted date was added at his request -- knowing a posting
    is 3 days old versus 28 changes how urgently he acts on it -- and the commute
    line for the same reason, on 2026-08-15. Company leads the block from
    2026-08-25: a list of ten roles with no employer names cannot be skimmed.
    """
    if not rows:
        return "No postings cleared the bar this run."

    blocks = []
    for row in rows:
        block = [
            f"Company: {_company_field(row)}",
            f"Job Title: {row['title']}",
            f"Link to Post: {row['url']}",
            f"City: {row['city'] or row['location_raw'] or 'Not stated'}",
            f"Salary Range: {_salary_field(row)}",
            f"Work Model: {row['work_model'] or 'Not stated'}",
        ]
        commute_line = commute_field(row)
        if commute_line:
            block.append(commute_line)
        block += [
            f"Posted: {_posted_field(row)}",
            f"Fit Summary: {(row['fit_summary'] or '').strip()}",
        ]
        connection_line = _connection_field(row)
        if connection_line:
            block.append(connection_line)
        tiebreak_line = _tiebreak_field(row)
        if tiebreak_line:
            block.append(tiebreak_line)
        # Both of these sit right under the Fit Summary on purpose: they change
        # what he does next, so they must not be below the warning line where a
        # long summary would push them out of sight.
        siblings = _also_hiring_field(row, rows)
        if siblings:
            block.append(siblings)
        applied_line = _already_applied_field(row, prior_applications)
        if applied_line:
            block.append(applied_line)
        stack_line = _named_stack(row)
        if stack_line:
            block.append(stack_line)
        if row["block_g_verdict"] == "FLAG":
            flags = _flags(row)
            block.append(
                "⚠ Legitimacy flag: " + ("; ".join(flags) if flags else "see run report")
            )
        blocks.append("\n".join(block))

    return "\n\n---\n\n".join(blocks)


BUCKET_HEADERS = {
    config.BUCKET_OVERLAP: (
        "LIST 1 - AI + MARKETING",
        "The sweet spot: an AI mandate inside a marketing or GTM org. Doran's "
        "proof points apply directly here, so this list has the most lenient bar.",
    ),
    config.BUCKET_AI: (
        "LIST 2 - AI ENABLEMENT",
        "AI enablement, strategy or builder capacity, wherever it sits. A little "
        "more lenient than the marketing bar.",
    ),
    config.BUCKET_MARKETING: (
        "LIST 3 - MARKETING",
        "Traditional growth, brand and web marketing with no AI mandate. Doran: "
        "\"I'm less interested in a pure traditional marketing role, however that "
        "doesn't mean I don't want it presented to me if it's a strong fit.\" "
        "Normal bar, no leniency.",
    ),
}

# Kept for the archived run report, which still labels by track.
# --------------------------------------------------- Fit Summary quality gate
#
# The Fit Summary exists so Doran does not have to read the posting. Doran,
# 2026-08-28: "the ultimate goal in writing this summary is really so that I
# don't need to read the entire job posting, so it's good to quote some
# sentences verbatim from the posting as evidence citations about the fit."
#
# The house style was written down in rubric/rubric-A-G.md and then drifted
# anyway, because prose guidance is not checkable. Run 25 produced summaries as
# thin as "Strong pay and a well-resourced team." with no quoted evidence at
# all, against run 14 summaries that quoted the posting twice and named the
# proof points. So the format is now checked mechanically, the same way the
# evidence cap checks block notes.
#
# This WARNS rather than blocks. A thin summary is a quality problem, not a
# correctness one, and refusing to record it would lose the score with it.

_SENTENCE_END = re.compile(r"[.!?](?:\s|$)")
# Straight and curly pairs both count as a citation.
_QUOTED = re.compile(r'"[^"]{12,}"|“[^”]{12,}”')

FIT_SUMMARY_MIN_QUOTES = 2
FIT_SUMMARY_MAX_SENTENCES = 6
FIT_SUMMARY_MIN_CHARS = 320


def fit_summary_issues(text: str | None) -> list[str]:
    """What is wrong with this Fit Summary, in plain terms. Empty list = fine."""
    body = (text or "").strip()
    problems: list[str] = []
    if not body:
        return ["no fit summary written"]

    paragraphs = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    if len(paragraphs) != 2:
        problems.append(
            f"{len(paragraphs)} paragraph(s), needs exactly 2 "
            "(what the role asks for, then how it fits him)")

    quotes = _QUOTED.findall(body)
    if len(quotes) < FIT_SUMMARY_MIN_QUOTES:
        problems.append(
            f"{len(quotes)} verbatim quote(s) from the posting, needs at least "
            f"{FIT_SUMMARY_MIN_QUOTES} - he reads this INSTEAD of the posting")

    sentences = len(_SENTENCE_END.findall(body))
    if sentences > FIT_SUMMARY_MAX_SENTENCES:
        problems.append(
            f"{sentences} sentences, cap is {FIT_SUMMARY_MAX_SENTENCES}")

    if len(body) < FIT_SUMMARY_MIN_CHARS:
        problems.append(
            f"{len(body)} characters, too thin to replace reading the posting")
    return problems


LIST_HEADERS = {
    "ai_enablement": ("LIST 1 - AI ENABLEMENT", ""),
    "growth_marketing": ("LIST 2 - GROWTH MARKETING (backup)", ""),
}


def render_bucket(bucket: str, bar: float, rows: list[sqlite3.Row],
                  prior_applications: dict | None = None) -> str:
    """One titled bucket list, stating the bar it was judged against.

    The bar is passed in rather than hardcoded: the three buckets have three
    different ones, and a header that says "4.0" under a list gated at 3.75 is
    simply a lie.
    """
    title, blurb = BUCKET_HEADERS.get(
        bucket, (config.bucket_label(bucket), ""))
    title = f"{title}  (bar {bar:.2f})"
    rule = "=" * max(len(title), 44)
    head = [rule, title, rule, ""]
    if blurb:
        head += [blurb, ""]
    if not rows:
        head.append(f"Nothing scored {bar:.2f} or higher this run.")
        return "\n".join(head)
    return "\n".join(head) + render_matches(rows, prior_applications)


def render_list(track: str, rows: list[sqlite3.Row],
                prior_applications: dict | None = None) -> str:
    """Legacy track-titled list, still used by the archived run report."""
    title, _blurb = LIST_HEADERS.get(track, (track.upper(), ""))
    rule = "=" * max(len(title), 44)
    head = [rule, title, rule, ""]
    if not rows:
        head.append("Nothing cleared the bar this run.")
        return "\n".join(head)
    return "\n".join(head) + render_matches(rows, prior_applications)


def render_worth_knowing(rows: list[sqlite3.Row],
                         bar: float = 4.0) -> str:
    """Sub-threshold roles that still deserve a mention, one line each.

    Doran, on a role that scored just under the bar: "I still would want to see
    this job and not completely filtered out... if you gave me a list of ten jobs
    and this was at the bottom then perhaps I wouldn't see it, but I don't want
    it hidden from me completely."

    So: never a full write-up, never mixed into the matches, and hard-capped --
    otherwise this quietly becomes the spray-and-pray list.
    """
    if not rows:
        return ""
    lines = ["", f"Worth knowing about (scored just under {bar:.2f} - not recommendations):"]
    for row in rows:
        model = row["work_model"] or "?"
        if row["work_model"] != WORK_REMOTE:
            result = commute_mod.evaluate(row["city"], row["work_model"])
            model += f" {result.minutes} min" if result.known else " commute unknown"
        # Same honesty rule as the match list: a reseller is named as a reseller,
        # never as the employer.
        who = row["company"]
        if is_aggregator(row):
            who = f"{who} (job board, employer not named)"
        lines.append(
            f"  - {row['weighted_score']:.2f}  {row['title']} @ {who}"
            f"  [{model}, posted {str(row['published_at'] or '')[:10]}]"
        )
        lines.append(f"      {row['url']}")
        summary = (row["fit_summary"] or "").strip()
        if summary:
            first = summary.split(". ")[0].rstrip(".")
            lines.append(f"      {first}.")
    return "\n".join(lines)


def render_near_misses(rows: list[sqlite3.Row]) -> str:
    """Targeted scans only: tell Doran a company he named came up dry."""
    if not rows:
        return ""
    lines = ["", "Near misses (companies you named, nothing cleared 4.0):"]
    for row in rows:
        lines.append(
            f"  - {row['company']} - {row['evaluated_count']} role(s) evaluated, "
            f"best was {row['best_score']:.1f} ({row['title']})"
        )
    return "\n".join(lines)


REPORTS_DIR = config.DATA_DIR / "reports"


def write_presented_report(text: str, *, run_id: int, stamp: str) -> Path:
    """Archive the terminal output verbatim to a timestamped markdown file.

    Doran asked for this on 2026-08-15: the report is the thing he actually
    re-reads, and until now it only existed in a chat session that scrolls away.
    The body is byte-for-byte what was printed -- no re-summarising, no
    reordering, no trimming -- so the file and the session can never disagree.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"results-{stamp}.md"
    day, _, clock = stamp.partition("_")
    pretty = f"{day} at {clock[:2]}:{clock[2:]}" if clock else day
    header = [
        f"# Career-Ops results - {pretty}",
        "",
        f"Run {run_id}. Verbatim copy of the report as presented.",
        "",
        "```",
    ]
    path.write_text("\n".join(header) + "\n" + text + "\n```\n", encoding="utf-8")
    return path


def write_run_report(
    conn: sqlite3.Connection,
    run_id: int,
    matches: list[sqlite3.Row],
    *,
    mode: str,
    funnel: dict[str, int],
    near_miss_rows: list[sqlite3.Row] | None = None,
    notes: list[str] | None = None,
) -> Path:
    run_dir = config.RUNS_DIR / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Run {run_id} - {mode}",
        "",
        "## Funnel",
        "",
        "| stage | count |",
        "| --- | --- |",
    ]
    for stage, count in funnel.items():
        lines.append(f"| {stage} | {count} |")

    lines += ["", "## Matches (>= 4.0)", ""]
    if not matches:
        lines.append("_None._")
    for row in matches:
        evaluation = store.latest_evaluation(conn, row["id"])
        dims = {}
        if evaluation:
            try:
                dims = json.loads(evaluation["dimension_scores"] or "{}")
            except json.JSONDecodeError:
                dims = {}
        lines += [
            f"### {row['title']} - {row['company']}  ({row['weighted_score']:.2f})",
            "",
            f"- URL: {row['url']}",
            f"- Location: {row['city'] or row['location_raw']} / {row['work_model']}",
            f"- Salary: {_salary_field(row)}",
            f"- Block G: **{row['block_g_verdict']}**"
            + (f" - {'; '.join(_flags(row))}" if _flags(row) else ""),
            f"- Dimension scores: {json.dumps(dims)}",
            "",
            f"{(row['fit_summary'] or '').strip()}",
            "",
        ]

    if near_miss_rows:
        lines += ["## Near misses", ""]
        for row in near_miss_rows:
            lines.append(
                f"- **{row['company']}** - {row['evaluated_count']} evaluated, "
                f"best {row['best_score']:.1f} ({row['title']})"
            )
        lines.append("")

    if notes:
        lines += ["## Notes", ""] + [f"- {n}" for n in notes] + [""]

    path = run_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
