"""The board-resolution backlog.

Resolving an unknown employer to its live ATS costs ~45 HTTP probes, so a scan
only does it for `board_resolve_cap` companies. Everything past that used to be
dropped on the floor while the log claimed "they will be picked up next run" --
there was no next-run memory of any kind. This table is that memory.

The guarantee under test: a company that runs out of budget must still be there
next run, and must not be starved forever by companies discovered after it.

Run with:  python tests/test_backlog.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from careerops import store  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, expected) -> None:
    if got != expected:
        FAILURES.append(f"{label}\n    expected: {expected!r}\n    got     : {got!r}")
        print(f"  FAIL  {label}")
    else:
        print(f"  ok    {label}")


with tempfile.TemporaryDirectory() as tmp:
    db = Path(tmp) / "jobs.db"
    store.init_db(db)

    with store.connect(db) as conn:
        print("\nqueueing and draining")

        store.queue_resolve_backlog(conn, ["Alpha", "Bravo", "Charlie"])
        check("three companies queued", store.resolve_backlog_size(conn), 3)

        check("an empty queue asks for nothing",
              store.take_resolve_backlog(conn, 0), [])
        check("drains oldest first",
              store.take_resolve_backlog(conn, 2), ["Alpha", "Bravo"])

        print("\nblank and duplicate handling")

        store.queue_resolve_backlog(conn, ["", "   ", "Alpha"])
        check("blank names are ignored", store.resolve_backlog_size(conn), 3)
        seen = conn.execute(
            "SELECT times_seen FROM resolve_backlog WHERE company = ?",
            (store.backlog_key("Alpha"),),
        ).fetchone()["times_seen"]
        check("re-queueing a known company bumps its sighting count", seen, 2)

        print("\none employer is one row, however it is spelled")

        # LinkedIn, Built In and Hacker News each render employer names their own
        # way. Keyed on the raw string these were three rows, three of the sixty
        # cap slots, and three resolution attempts at ~45 requests each -- in the
        # same run, for the same company.
        before = store.resolve_backlog_size(conn)
        store.queue_resolve_backlog(conn, ["Databricks Inc.", "databricks", "Databricks"])
        check("three spellings make one row", store.resolve_backlog_size(conn), before + 1)
        handed = store.take_resolve_backlog(conn, 50)
        check("and it is handed back as a real name, not the key",
              "Databricks Inc." in handed, True)
        check("only once", sum(1 for c in handed if "atabricks" in c), 1)

        # Resolution reports whatever name the ATS uses, which may be a fourth
        # spelling. Clearing has to match anyway or the row outlives the fix.
        store.clear_resolve_backlog(conn, ["DATABRICKS"])
        check("clearing matches on any spelling",
              any("atabricks" in c for c in store.take_resolve_backlog(conn, 50)), False)

        print("\nleaving the backlog")

        store.clear_resolve_backlog(conn, ["Bravo"])
        check("a resolved company is gone for good",
              store.resolve_backlog_size(conn), 2)
        check("and is not handed out again",
              "Bravo" in store.take_resolve_backlog(conn, 10), False)

        print("\nstarvation")

        # This is the whole point. Alpha failed to resolve once; it must not be
        # handed out ahead of everything else forever, and it must not vanish.
        store.bump_resolve_attempts(conn, ["Alpha"])
        store.queue_resolve_backlog(conn, ["Delta"])
        order = store.take_resolve_backlog(conn, 10)
        check("a company that failed goes behind untried ones",
              order.index("Alpha") > order.index("Charlie"), True)
        check("but it is still in the queue, not dropped", "Alpha" in order, True)

        # A company still waiting after a second budget-limited run stays put.
        store.queue_resolve_backlog(conn, ["Charlie"])
        check("re-queueing an already-waiting company does not duplicate it",
              store.resolve_backlog_size(conn), 3)

        print("\nfailures are remembered, not forgotten")

        # The leak this closes: a company found on a board and tried for the
        # first time was not in the table, so recording its failure updated
        # nothing and the next run re-probed it at ~45 requests. Forever.
        before = store.resolve_backlog_size(conn)
        store.bump_resolve_attempts(conn, ["NeverSeenBefore"])
        check("a first-time failure is inserted, not dropped",
              store.resolve_backlog_size(conn), before + 1)
        check("blank names are still ignored",
              store.bump_resolve_attempts(conn, ["", "  "]) or
              store.resolve_backlog_size(conn), before + 1)

        print("\ngiving up")

        # Three strikes and a company stops eating a slot under the resolve cap.
        for _ in range(store.BACKLOG_MAX_ATTEMPTS):
            store.bump_resolve_attempts(conn, ["Hopeless"])
        check("an exhausted company is no longer handed out",
              "Hopeless" in store.take_resolve_backlog(conn, 50), False)
        check("but it is not deleted -- it is still findable by hand",
              "Hopeless" in store.resolve_backlog_exhausted(conn), True)
        check("and it no longer counts toward the retryable backlog",
              "Hopeless" in store.take_resolve_backlog(conn, 50), False)

        # Resolving it later must still clear it, so a manual
        # `resolve-company` run is not undone by a stale row.
        store.clear_resolve_backlog(conn, ["Hopeless"])
        check("clearing an exhausted company works",
              store.resolve_backlog_exhausted(conn), [])

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):\n")
    for failure in FAILURES:
        print(f"  {failure}\n")
    raise SystemExit(1)
print("All resolve-backlog tests passed.")
