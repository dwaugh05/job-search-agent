"""Re-pull every applied posting from its live ATS and refresh the archive.

The archive is normally snapshotted at verdict time. These thirteen predate the
feature, so their text came from whatever was last stored during a scan. This
re-fetches each one from the live board -- never a cache, never a search
snapshot -- so the saved copy is the posting as the company publishes it today,
and records which ones have already been taken down.

Read-only against the employer: it fetches the company's public job feed and
nothing else. There is no interaction with any application form.

Run with:  python scripts/refresh_applied_archive.py [--dry-run]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from careerops import applications, store  # noqa: E402
from careerops.sources.registry import _client, fetch_company  # noqa: E402

DRY_RUN = "--dry-run" in sys.argv


def main() -> int:
    with store.connect() as conn:
        rows = store.applied_postings(conn)
        if not rows:
            print("Nothing marked as applied.")
            return 0

        # One fetch per company board, not per posting -- Harvey and GitLab each
        # have two applications against the same board.
        boards: dict[tuple[str, str, str], list] = {}
        for row in rows:
            boards.setdefault((row["ats"], row["source_slug"], row["company"]), []).append(row)

        live_text: dict[str, str] = {}
        with _client() as client:
            for (ats, slug, company) in boards:
                if not ats or not slug:
                    print(f"  {company:18} no board on file - cannot re-fetch")
                    continue
                postings = fetch_company(ats, slug, company, client=client)
                for posting in postings:
                    if posting.source_id:
                        live_text[f"{ats}:{slug}:{posting.source_id}"] = posting.description
                print(f"  {company:18} {len(postings):4} live posting(s) on {ats}/{slug}")

        print()
        refreshed = gone = unchanged = 0
        for row in rows:
            key = f"{row['ats']}:{row['source_slug']}:{row['source_id']}"
            fresh = live_text.get(key)
            label = f"{row['company']} - {row['title']}"

            if not fresh:
                print(f"  TAKEN DOWN  {label}")
                print("              archive keeps the copy saved at scan time")
                gone += 1
                if not DRY_RUN:
                    conn.execute("UPDATE postings SET is_live = 0 WHERE id = ?", (row["id"],))
                continue

            changed = fresh.strip() != (row["description"] or "").strip()
            status = "UPDATED" if changed else "same as saved"
            print(f"  STILL LIVE  {label}  ({status})")
            if changed:
                refreshed += 1
                if not DRY_RUN:
                    conn.execute("UPDATE postings SET description = ? WHERE id = ?",
                                 (fresh, row["id"]))
            else:
                unchanged += 1

        if DRY_RUN:
            print("\n[dry run - nothing written]")
            return 0

        # Rewrite every archive file from the now-current descriptions.
        print()
        for row in store.applied_postings(conn):
            applied_date = str(row["applied_at"] or "")[:10] or "unknown"
            latest = conn.execute(
                """SELECT weighted_score, fit_summary, connection_bonus FROM evaluations
                   WHERE posting_id = ? ORDER BY id DESC LIMIT 1""",
                (row["id"],),
            ).fetchone()
            path = applications.write_application(
                row,
                applied_date=applied_date,
                reason=row["reason"],
                score=latest["weighted_score"] if latest else None,
                connection_bonus=(latest["connection_bonus"] or 0.0) if latest else 0.0,
                fit_summary=latest["fit_summary"] if latest else None,
            )
            sections = applications.extract_sections(row["description"])
            print(f"  {path.name}\n      captured via: {sections['via']}")

        print(f"\n{refreshed} refreshed from live, {unchanged} already current, "
              f"{gone} taken down.")
        print(f"Index: {applications.rebuild_index()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
