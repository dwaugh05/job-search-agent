"""No-auto-apply audit.

The core guarantee in CLAUDE.md is that this codebase cannot submit a job
application. Historically that was enforced by banning every HTTP write verb.

Workday broke that simplification: its job SEARCH endpoint requires POST because
the query travels as a JSON body. That is semantically a read. Rather than
weaken the guarantee, the exception is made structural:

  * POST may appear ONLY in sources/workday.py.
  * Every Workday URL passes _assert_search_url, which refuses anything that is
    not a /wday/cxs/{tenant}/{site}/jobs search or job-detail path -- so an
    application endpoint is unreachable through that module by construction.

Run with:  python tests/test_safety.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FAILURES: list[str] = []

BANNED_SYMBOLS = re.compile(
    r"\b(submit_application|apply_to_job|auto_?apply|fill_application|"
    r"upload_resume|click_apply|post_application|send_application)\b", re.I)
HTTP_WRITE = re.compile(r"\.(post|put|patch|delete)\s*\(", re.I)

POST_ALLOWED = {"workday.py"}

files = sorted(list((ROOT / "src").rglob("*.py")) + [ROOT / "cli.py"])
print(f"auditing {len(files)} python files\n")

for path in files:
    text = path.read_text(encoding="utf-8")
    for match in BANNED_SYMBOLS.finditer(text):
        FAILURES.append(f"{path.name}: application-submission symbol {match.group(0)!r}")
    for match in HTTP_WRITE.finditer(text):
        line = text[:match.start()].count("\n") + 1
        if path.name in POST_ALLOWED:
            continue
        FAILURES.append(f"{path.name}:{line}: HTTP write {match.group(0)!r}")

# The allowed exception must still be genuinely constrained.
workday = (ROOT / "src" / "careerops" / "sources" / "workday.py").read_text(encoding="utf-8")
checks = [
    ("workday defines _assert_search_url", "_assert_search_url" in workday),
    ("workday asserts before POSTing", workday.index("_assert_search_url(url)")
     < workday.index("client.post(")),
    ("workday path regex is anchored to /wday/cxs and /jobs",
     "/wday/cxs/" in workday and "(jobs|job/.+)$" in workday),
]
for label, ok in checks:
    if not ok:
        FAILURES.append(f"safety invariant broken: {label}")
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")

# The assertion must actually reject an application-shaped URL.
from careerops.sources import workday as wd  # noqa: E402

for bad in [
    "https://gilead.wd1.myworkdayjobs.com/wday/cxs/gilead/gileadcareers/apply",
    "https://gilead.wd1.myworkdayjobs.com/gileadcareers/apply/autofillWithResume",
    "https://evil.example.com/wday/cxs/a/b/jobs",
]:
    try:
        wd._assert_search_url(bad)
        FAILURES.append(f"_assert_search_url accepted a non-search URL: {bad}")
        print(f"  FAIL rejects {bad[:64]}")
    except ValueError:
        print(f"  ok   rejects {bad[:64]}")

good = "https://gilead.wd1.myworkdayjobs.com/wday/cxs/gilead/gileadcareers/jobs"
try:
    wd._assert_search_url(good)
    print("  ok   accepts the real search endpoint")
except ValueError:
    FAILURES.append("_assert_search_url rejected the legitimate search endpoint")
    print("  FAIL accepts the real search endpoint")

print()
if FAILURES:
    print(f"{len(FAILURES)} SAFETY FAILURE(S):")
    for failure in FAILURES:
        print(f"  {failure}")
    raise SystemExit(1)
print("SAFETY AUDIT PASSED - no application-submission path exists.")
