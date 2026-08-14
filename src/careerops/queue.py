"""Renders the evaluation queue that Claude reads to apply the A-G rubric.

Python's job ends here. Everything in this file is presentation of already-
gathered facts -- it makes no judgement about fit. The queue deliberately
includes the derived facts an evaluator would otherwise have to recompute
(commute minutes, modeled total comp, posting age, repost history) so scoring
stays consistent between runs.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import commute as commute_mod
from . import comp as comp_mod
from . import config, store
from .normalize import age_days

DESCRIPTION_CHARS = 7000


def _posting_block(conn: sqlite3.Connection, row: sqlite3.Row, index: int) -> str:
    age = age_days(row["published_at"])
    commute = commute_mod.evaluate(row["city"], row["work_model"])
    tc = comp_mod.model_total_comp(
        row["salary_min"], row["salary_max"], equity=bool(row["equity_mentioned"])
    )
    reposts = store.repost_signals(conn, row["fingerprint"])

    salary_line = comp_mod.format_range(row["salary_min"], row["salary_max"]) or "not listed"
    if tc["tc"]:
        salary_line += (
            f"  ->  modeled: base ${tc['base']:,} + bonus ${tc['bonus']:,}"
            f" + equity ${tc['equity']:,} = TC ${tc['tc']:,}"
        )

    description = (row["description"] or "").strip()
    truncated = len(description) > DESCRIPTION_CHARS
    if truncated:
        description = description[:DESCRIPTION_CHARS] + "\n\n[...truncated...]"

    lines = [
        f"### {index}. {row['title']} - {row['company']}",
        "",
        f"- **posting_id**: `{row['id']}`  (use this in scores.json)",
        f"- **URL**: {row['url']}",
        f"- **Apply URL**: {row['apply_url'] or '(same)'}",
        f"- **Location**: {row['location_raw'] or 'unstated'}"
        f"  |  city: {row['city'] or 'unknown'}"
        f"  |  work model: **{row['work_model'] or 'unknown'}**",
        f"- **Commute**: {commute.note}"
        f"  (dimension 5 raw score {commute.score})"
        + ("  **[UNKNOWN CITY - resolve before scoring]**" if not commute.known else ""),
        f"- **Salary**: {salary_line}",
        f"- **Equity mentioned**: {'yes' if row['equity_mentioned'] else 'no'}"
        f"  |  **Bonus mentioned**: {'yes' if row['bonus_mentioned'] else 'no'}",
        f"- **Published**: {(row['published_at'] or 'unknown')[:10]}"
        f"  ({f'{age:.0f} days ago' if age is not None else 'age unknown'})"
        f"  |  date confidence: {row['date_confidence']}",
        f"- **Department / team**: {row['department'] or '-'} / {row['team'] or '-'}",
        f"- **Source**: {row['ats']}/{row['source_slug']}  id={row['source_id']}",
        f"- **Repost history**: {reposts['distinct_posting_ids']} distinct ATS id(s), "
        f"{reposts['distinct_published_dates']} distinct publish date(s)"
        + ("  **[PERPETUAL REPOST SIGNAL]**" if reposts["perpetual_repost"] else ""),
        "",
        "<details><summary>Full description</summary>",
        "",
        "```text",
        description,
        "```",
        "",
        "</details>",
        "",
    ]
    return "\n".join(lines)


def render(conn: sqlite3.Connection, rows: list[sqlite3.Row], run_id: int,
           mode: str) -> Path:
    """Write data/runs/<run_id>/queue.md and return its path."""
    run_dir = config.RUNS_DIR / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    header = [
        f"# Evaluation queue - run {run_id} ({mode})",
        "",
        f"{len(rows)} posting(s) cleared the deterministic prefilter and need A-G scoring.",
        "",
        "Score each one against `rubric/rubric-A-G.md` and `config/scoring.yml`,",
        "loading `rubric/learned-rules.md` first. Write results to",
        f"`data/runs/{run_id}/scores.json` and apply them with:",
        "",
        "```",
        f"python cli.py record-eval --run {run_id} --file data/runs/{run_id}/scores.json",
        "```",
        "",
        "---",
        "",
    ]
    body = [_posting_block(conn, row, i) for i, row in enumerate(rows, start=1)]

    path = run_dir / "queue.md"
    path.write_text("\n".join(header + body), encoding="utf-8")

    # A machine-readable companion so scores.json can be assembled reliably.
    skeleton = {
        "run_id": run_id,
        "rubric_version": str(config.scoring().get("version", 1)),
        "evaluations": [
            {
                "posting_id": row["id"],
                "company": row["company"],
                "title": row["title"],
                "dimension_scores": {},
                "block_notes": {},
                "block_g_verdict": "PASS",
                "block_g_flags": [],
                "fit_summary": "",
            }
            for row in rows
        ],
    }
    (run_dir / "scores.template.json").write_text(
        json.dumps(skeleton, indent=2), encoding="utf-8"
    )
    return path
