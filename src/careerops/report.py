"""Output rendering.

Two artifacts, deliberately different:

  * The terminal report is EXACTLY the six fields Doran asked for. Scores and
    Block G detail stay out of it. The single exception is a Block G FLAG, which
    adds one warning line -- hiding a legitimacy concern would defeat the point
    of running the check.

  * The run report on disk carries the full audit trail: scores per dimension,
    Block G findings, and the funnel counts.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import comp as comp_mod
from . import config, store
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


def render_matches(rows: list[sqlite3.Row]) -> str:
    """The match list Doran reads.

    Seven fields. Posted date was added at his request -- knowing a posting is 3
    days old versus 28 changes how urgently he acts on it.
    """
    if not rows:
        return "No postings scored 4.0 or higher this run."

    blocks = []
    for row in rows:
        block = [
            f"Job Title: {row['title']}",
            f"Link to Post: {row['url']}",
            f"City: {row['city'] or row['location_raw'] or 'Not stated'}",
            f"Salary Range: {_salary_field(row)}",
            f"Work Model: {row['work_model'] or 'Not stated'}",
            f"Posted: {_posted_field(row)}",
            f"Fit Summary: {(row['fit_summary'] or '').strip()}",
        ]
        if row["block_g_verdict"] == "FLAG":
            flags = _flags(row)
            block.append(
                "⚠ Legitimacy flag: " + ("; ".join(flags) if flags else "see run report")
            )
        blocks.append("\n".join(block))

    return "\n\n---\n\n".join(blocks)


LIST_HEADERS = {
    "ai_enablement": (
        "LIST 1 - AI ENABLEMENT",
        "The primary target: owning AI enablement for a marketing, GTM or business org.",
    ),
    "growth_marketing": (
        "LIST 2 - GROWTH MARKETING (backup)",
        "Scored on the pre-AI background: SaaS acquisition, CRO, demand gen, web funnel. "
        "Same 4.0 bar - a backup still has to be worth an application.",
    ),
}


def render_list(track: str, rows: list[sqlite3.Row]) -> str:
    """One titled list. Both tracks use the identical seven-field format."""
    title, blurb = LIST_HEADERS.get(track, (track.upper(), ""))
    rule = "=" * max(len(title), 44)
    head = [rule, title, rule, ""]
    if blurb:
        head += [blurb, ""]
    if not rows:
        head.append("Nothing scored 4.0 or higher this run.")
        return "\n".join(head)
    return "\n".join(head) + render_matches(rows)


def render_both_lists(primary: list[sqlite3.Row],
                      backup: list[sqlite3.Row]) -> str:
    """Both lists in one report.

    A posting that qualifies for both tracks appears ONLY in list 1 -- deduped by
    posting id before rendering, so list 2 stays genuinely a set of alternatives
    rather than a restatement of the same roles.
    """
    shown = {row["id"] for row in primary}
    backup = [row for row in backup if row["id"] not in shown]
    return (render_list("ai_enablement", primary) + "\n\n\n"
            + render_list("growth_marketing", backup))


def render_worth_knowing(rows: list[sqlite3.Row]) -> str:
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
    lines = ["", "Worth knowing about (scored just under 4.0 - not recommendations):"]
    for row in rows:
        lines.append(
            f"  - {row['weighted_score']:.2f}  {row['title']} @ {row['company']}"
            f"  [{row['work_model'] or '?'}, posted {str(row['published_at'] or '')[:10]}]"
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
