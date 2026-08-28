"""The two context lines that stop Doran applying to the wrong role.

Both were asked for on 2026-08-26, and both exist because the report is read
top to bottom and acted on immediately:

  * "Also in this report from X" -- three Coupa roles appeared in one report and
    he could apply to the first and never reach the third. In his words: "I might
    just read through the list sequentially and apply to the first one I see and
    not even take a chance to apply to the second one when it might have better
    fit."
  * "Already applied at X" -- a new posting from a company he already has an
    application in reads differently, and he needs to know which role it was.

Run with:  python tests/test_report_context.py
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from careerops import report, store  # noqa: E402
from careerops.models import Posting  # noqa: E402
from careerops.normalize import days_ago_iso  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, expected) -> None:
    if got != expected:
        FAILURES.append(f"{label}\n    expected: {expected!r}\n    got     : {got!r}")
        print(f"  FAIL  {label}")
    else:
        print(f"  ok    {label}")


class Row(dict):
    """Minimal stand-in for sqlite3.Row -- indexable by column name."""

    def __getitem__(self, key):
        return self.get(key)


def row(pid, company, title, **over):
    base = dict(
        id=pid, company=company, title=title, url=f"https://x/{pid}",
        city="Remote", location_raw="Remote - US", work_model="Remote",
        salary_min=None, salary_max=None, published_at=days_ago_iso(3),
        fit_summary="Summary.", block_g_verdict="PASS", block_g_flags="[]",
        connection_bonus=0.0, source_slug="acme", weighted_score=4.5,
    )
    base.update(over)
    return Row(base)


print("\nsiblings in the same report")

three = [
    row(1, "Coupa Software", "Principal PM - AI Foundations"),
    row(2, "Coupa Software", "Principal PM - GTM & RevOps"),
    row(3, "Coupa Software", "Principal PM - HR & Marketing"),
]
out = report.render_matches(three)
check("every Coupa block names the other two",
      out.count("Also in this report from Coupa Software:"), 3)
check("and the first block names the third role",
      'Principal PM - HR & Marketing"' in out.split("---")[0], True)
check("two roles reads 'both'", "read both before applying" in
      report.render_matches(three[:2]), True)
check("three roles reads 'all'", "read all before applying" in out, True)

# A lone posting must not carry the line at all -- noise on every block would
# make it invisible on the blocks that matter.
check("a single posting gets no sibling line",
      "Also in this report" in report.render_matches([three[0]]), False)

# Different companies are not siblings, however similar the titles.
mixed = [row(1, "Acme", "AI Enablement Lead"), row(2, "Globex", "AI Enablement Lead")]
check("different companies are not siblings",
      "Also in this report" in report.render_matches(mixed), False)

# Matching is on the normalized company name, which strips legal suffixes but
# not descriptive words. "Coupa Software Inc." and "Coupa Software" are one
# company; "Coupa" alone is not, because dropping a word like "Software" would
# also merge "Apple" with "Apple Bank". In practice both strings come from the
# same ATS feed, so they agree.
drifted = [row(1, "Coupa Software", "Role A"), row(2, "Coupa Software Inc.", "Role B")]
check("a legal suffix does not split one company in two",
      report.render_matches(drifted).count("Also in this report"), 2)
check("but a shorter name is left alone rather than guessed at",
      "Also in this report" in report.render_matches(
          [row(1, "Coupa", "Role A"), row(2, "Coupa Software", "Role B")]),
      False)


print("\nprior applications")

prior = {"acme": [("2026-08-20", "AI Enablement Manager")]}
one = [row(1, "Acme", "AI Enablement Engineer")]
check("a new role at a company he applied to is flagged",
      "Already applied at Acme:" in report.render_matches(one, prior), True)
check("...naming the role and the date",
      '"AI Enablement Manager" on 2026-08-20' in report.render_matches(one, prior), True)

# The posting must never flag itself.
same = [row(1, "Acme", "AI Enablement Manager")]
check("a posting does not flag itself",
      "Already applied" in report.render_matches(same, prior), False)

check("no history means no line",
      "Already applied" in report.render_matches(one, {"globex": [("2026-01-01", "X")]}),
      False)
check("passing no history at all is safe",
      "Already applied" in report.render_matches(one, None), False)

many = {"acme": [(f"2026-08-0{i}", f"Role {i}") for i in range(1, 6)]}
rendered = report.render_matches([row(9, "Acme", "New Role")], many)
check("a long history is truncated", "(+2 more)" in rendered, True)


print("\nreading it back out of the database")

with tempfile.TemporaryDirectory() as tmp:
    db = Path(tmp) / "t.db"
    store.init_db(db)
    with store.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        run = store.start_run(conn, "broad")
        pid, _ = store.upsert_posting(conn, Posting(
            source_id="A1", company="Coupa Software", title="Principal PM",
            url="u", ats="lever", source_slug="coupa", apply_url="u",
            location_raw="Remote - US", workplace_type="Remote",
            published_at=days_ago_iso(3), date_confidence="high",
            description="x" * 400,
        ), run)
        check("nothing applied yet", store.prior_applications(conn), {})

        store.record_verdict(conn, pid, "applied", "applied today")
        got = store.prior_applications(conn)
        check("the company is keyed normalized", list(got), ["coupa software"])
        check("and carries the role title", got["coupa software"][0][1], "Principal PM")


print()

# ------------------------------------------------- the Fit Summary gate
#
# The Fit Summary is what Doran reads INSTEAD of the posting. Doran,
# 2026-08-28: "the ultimate goal in writing this summary is really so that I
# don't need to read the entire job posting, so it's good to quote some
# sentences verbatim from the posting as evidence citations."
#
# The house style was written down and drifted anyway: 43 of run 25's 45
# summaries carried no quoted evidence at all, against run 14 summaries that
# quoted the posting twice. Prose guidance is not checkable, so it is checked.

print("\nfit summary house style")

from careerops.report import fit_summary_issues  # noqa: E402

_GOOD = (
    'The job is to "build the agents, automations, and intelligence systems '
    'that help our frontline teams operate more effectively". They want '
    '"a GTM operator who is also a hands-on builder".\n\n'
    "That maps onto the Contentful MCP server and the reusable-agent repo. "
    "Against it, the seat sits in Revenue Operations rather than Marketing, "
    "so sellers are the first audience."
)
check("a house-style summary passes", fit_summary_issues(_GOOD), [])

# Each failure mode, one at a time.
check("an empty summary is caught",
      fit_summary_issues(""), ["no fit summary written"])
_no_quotes = ("Strong pay and a well-resourced team, remote, and the mandate is broad "
              "enough to be interesting across several functions here.\n\n"
              "Against it, the role is consumer rather than the B2B SaaS where his "
              "proof lives, and the band tops out below his floor by some margin.")
check("a summary with no quoted evidence is caught",
      any("verbatim quote" in i for i in fit_summary_issues(_no_quotes)), True)
_one_para = ('It asks you to "own the automation and AI layer that powers critical '
             'marketing workflows" and to "translate operational challenges into '
             'scalable technical solutions", which is the archetype stated plainly '
             'and maps onto the Cloudflare marketing org work he already did.')
check("a single-paragraph summary is caught",
      any("paragraph" in i for i in fit_summary_issues(_one_para)), True)
_rambling = _GOOD + " One. Two. Three. Four. Five."
check("an over-long summary is caught",
      any("sentences" in i for i in fit_summary_issues(_rambling)), True)

# record-eval is where the check runs, so the wiring must stay connected.
_cli = (Path(__file__).resolve().parents[1] / "cli.py").read_text(encoding="utf-8")
check("record-eval runs the fit summary check",
      "report.fit_summary_issues(item.get(\"fit_summary\"))" in _cli, True)

# ---------------------------------------------- cmd_report has no stale names
#
# The three-bucket rewrite left a reference to `backup`, a variable that no
# longer existed. Python short-circuited past it on the --no-mark path, so the
# report printed and archived normally and then raised NameError at the very
# end -- a run looked successful while marking nothing as presented.
import ast  # noqa: E402
import builtins  # noqa: E402

_tree = ast.parse(_cli)
_fn = [n for n in ast.walk(_tree)
       if isinstance(n, ast.FunctionDef) and n.name == "cmd_report"][0]
_assigned = {t.id for t in ast.walk(_fn)
             if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store)}
# Parameters are bound too, but appear only in the arguments node.
_assigned |= {a.arg for a in _fn.args.args + _fn.args.kwonlyargs}
_module_level = {"store", "config", "report", "json", "Path", "datetime",
                 "argparse", "_threshold"}
_used = {t.id for t in ast.walk(_fn)
         if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Load)}
_unbound = sorted(_used - _assigned - set(dir(builtins)) - _module_level)
check("cmd_report references no undefined names", _unbound, [])

if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):\n")
    for failure in FAILURES:
        print(f"  {failure}\n")
    raise SystemExit(1)
print("All report-context tests passed.")
