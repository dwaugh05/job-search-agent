"""LinkedIn paging under throttling.

LinkedIn does not answer 429 when you go too fast. It answers 200 with an empty
body, which is byte-for-byte what "no more results" looks like. The old paging
treated the two as the same thing, so a throttled query ended early and the run
reported fewer hits with nothing to indicate why.

That distinction is the whole point of these tests, and it cannot be tested
against the live endpoint -- throttling is not reproducible on demand -- so they
drive a fake client instead. No network.

Run with:  python tests/test_throttle.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import careerops.sources.boards as boards  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, expected) -> None:
    if got != expected:
        FAILURES.append(f"{label}\n    expected: {expected!r}\n    got     : {got!r}")
        print(f"  FAIL  {label}")
    else:
        print(f"  ok    {label}")


# Sleeping is what makes these tests slow and what we are not testing. Stub it.
boards.time.sleep = lambda _s: None


def card(n: int) -> str:
    return (
        f"<li><h3>AI Enablement Manager {n}</h3>"
        f'<h4><a href="x">Company {n}</a></h4>'
        f'<a href="https://www.linkedin.com/jobs/view/role-{n}">x</a>'
        f'<time datetime="2026-08-20"></time>'
        f'<span class="job-search-card__location">United States</span></li>'
    )


class FakeResponse:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


class FakeClient:
    """Replays a scripted sequence of responses and records the calls."""

    def __init__(self, script: list) -> None:
        self.script = list(script)
        self.calls = 0

    def get(self, url: str) -> FakeResponse:
        self.calls += 1
        if not self.script:
            return FakeResponse(200, "")
        item = self.script.pop(0)
        if isinstance(item, int):          # a status code with no body
            return FakeResponse(item, "")
        return FakeResponse(200, item)     # a body


FULL = "".join(card(i) for i in range(10))


def page(offset: int) -> str:
    return "".join(card(offset + i) for i in range(10))


print("\nan empty body is a throttle, not the end")

# Page 2 comes back empty once, then full on retry. The old code stopped at the
# empty page and returned 10; it must now return 20.
client = FakeClient([page(0), "", page(10)])
budget = boards.ThrottleBudget()
leads = boards.search_linkedin(client, "q", max_pages=2, budget=budget)
check("retries past a single empty page", len(leads), 20)
check("and counts the throttle", budget.events, 1)

# Empty every time: after THROTTLE_RETRIES it gives up on the query, and does
# not spin forever.
client = FakeClient([page(0)] + [""] * 20)
budget = boards.ThrottleBudget()
leads = boards.search_linkedin(client, "q", max_pages=6, budget=budget)
check("gives up after the retry limit", len(leads), 10)
check("without unbounded requests",
      client.calls <= 1 + boards.THROTTLE_RETRIES, True)


print("\nreal ends of the result set are still detected")

# HTTP 400 means start >= 1000. Nothing beyond exists.
client = FakeClient([page(0), 400])
leads = boards.search_linkedin(client, "q", max_pages=8)
check("stops dead on HTTP 400", len(leads), 10)
check("and does not retry it", client.calls, 2)

# A short page is the natural end. Its cards must be NEW ones -- reusing ids
# from page one would trip the duplicate check instead and test the wrong thing.
short = "".join(card(100 + i) for i in range(3))
client = FakeClient([page(0), short, page(50)])
leads = boards.search_linkedin(client, "q", max_pages=8)
check("stops on a short page", len(leads), 13)

# A page of pure duplicates means the set has wrapped -- LinkedIn pads rather
# than ending cleanly, so this must not loop to max_pages.
client = FakeClient([page(0), page(0), page(0), page(0)])
leads = boards.search_linkedin(client, "q", max_pages=8)
check("stops when a page adds nothing new", len(leads), 10)
check("and stops promptly", client.calls, 2)

# start must never exceed the endpoint's hard wall.
client = FakeClient([FULL] * 400)
leads = boards.search_linkedin(client, "q", max_pages=200)
check("never pages past the 1000 wall",
      client.calls <= boards.MAX_START // boards.PAGE_SIZE, True)


print("\n429 is handled too, and the channel gives up before a block")

client = FakeClient([page(0), 429, 429, 429])
budget = boards.ThrottleBudget()
leads = boards.search_linkedin(client, "q", max_pages=4, budget=budget)
check("a rate-limited page ends the query", len(leads), 10)
check("and every 429 is counted", budget.events, 3)

budget = boards.ThrottleBudget(limit=2)
check("a fresh budget is not spent", budget.spent, False)
budget.hit("x")
budget.hit("x")
check("a spent budget stops the channel", budget.spent, True)


print("\nno budget passed is still safe")

client = FakeClient([page(0), "", page(10), ""])
leads = boards.search_linkedin(client, "q", max_pages=3)
check("throttle handling works without a budget object", len(leads), 20)


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):\n")
    for failure in FAILURES:
        print(f"  {failure}\n")
    raise SystemExit(1)
print("All throttle tests passed.")
