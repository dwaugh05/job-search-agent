"""Reseller per-country clones.

Jobgether lists one role once per country, changing nothing but the country name
in the opening sentence. Because fingerprint() hashes the first 400 characters,
those clones each got a distinct identity and each cost Claude a full read: in
run 14, 42 of 140 scoring slots went to text that had already been read.

`clone_key` collapses them. The two things it must never do are collapse two
genuinely different roles, and interfere with `fingerprint`, which carries the
"never show me the same job twice" guarantee and must keep its own behaviour.

Run with:  python tests/test_clones.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from careerops.fingerprint import clone_key, fingerprint  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, expected) -> None:
    if got != expected:
        FAILURES.append(f"{label}\n    expected: {expected!r}\n    got     : {got!r}")
        print(f"  FAIL  {label}")
    else:
        print(f"  ok    {label}")


PREAMBLE = (
    "This position is listed on behalf of a partner company, who manages all "
    "applications and next steps. Our partner is looking for an AWS Cloud "
    "Engineer based in {country}. "
)
BODY = (
    "This is a mid-level cloud engineering role focused on designing and "
    "operating AWS infrastructure. You will own provisioning, monitoring and "
    "cost control across a multi-account estate, and partner with platform "
    "teams on reliability."
)


def clone(country: str) -> str:
    return PREAMBLE.format(country=country) + BODY


print("\nper-country clones collapse")

keys = {
    clone_key("Jobgether", "AWS Cloud Engineer", clone(c))
    for c in ("Italy", "Brazil", "Netherlands", "United Arab Emirates", "Spain")
}
check("five countries, one role", len(keys), 1)

prints = {
    fingerprint("Jobgether", "AWS Cloud Engineer", clone(c))
    for c in ("Italy", "Brazil", "Netherlands", "United Arab Emirates", "Spain")
}
check("fingerprint is deliberately left alone and still sees five", len(prints), 5)


print("\nwhat must NOT collapse")

# Same reseller, same preamble shape, genuinely different job.
other_role = (
    "This position is listed on behalf of a partner company, who manages all "
    "applications and next steps. Our partner is looking for a Marketing "
    "Engineer based in Italy. This is a senior role building the automation "
    "backbone of an AI-powered marketing organization, owning lifecycle "
    "workflows and the integration layer beneath them."
)
check(
    "a different role at the same reseller stays separate",
    clone_key("Jobgether", "Marketing Engineer", other_role)
    == clone_key("Jobgether", "AWS Cloud Engineer", clone("Italy")),
    False,
)
check(
    "the same text at a different employer stays separate",
    clone_key("Acme", "AWS Cloud Engineer", clone("Italy"))
    == clone_key("Jobgether", "AWS Cloud Engineer", clone("Italy")),
    False,
)

# The preamble strip must not reach into the body. Two postings that share the
# aggregator intro but diverge afterwards are two jobs.
a = PREAMBLE.format(country="Italy") + BODY
b = PREAMBLE.format(country="Italy") + BODY.replace("mid-level", "principal-level")
check("a changed body is a different role", clone_key("J", "T", a) == clone_key("J", "T", b), False)


print("\nordinary postings are untouched")

plain = (
    "We are hiring a Marketing Engineer to own AI enablement across the "
    "marketing organization, building agentic workflows and upskilling the team."
)
check(
    "no preamble means no change in behaviour",
    clone_key("Acme", "Marketing Engineer", plain)
    == clone_key("Acme", "Marketing Engineer", plain),
    True,
)
check(
    "two different ordinary postings stay separate",
    clone_key("Acme", "Marketing Engineer", plain)
    == clone_key("Acme", "Marketing Engineer", plain + " Also, equity."),
    False,
)
check("an empty description does not crash", isinstance(clone_key("A", "T", None), str), True)


print("\nthe same job arriving twice by two different routes")

# A company over the per-run resolve cap has its posting read off LinkedIn this
# run, then swept from its own ATS once the backlog resolves it. The two bodies
# are written differently, so they fingerprint apart and the ordinary
# suppression check lets the second one through -- Doran shown the same role
# twice, which is the one thing suppression exists to prevent.
import tempfile  # noqa: E402
from careerops import store  # noqa: E402
from careerops.models import Posting  # noqa: E402
from careerops.normalize import days_ago_iso  # noqa: E402


def posting(**overrides) -> Posting:
    fields = dict(
        source_id="J1", company="Delinea",
        title="AI Marketing Solutions Engineer", url="u", ats="linkedin",
        source_slug="linkedin", apply_url="u", location_raw="Remote - US",
        workplace_type="Remote", published_at=days_ago_iso(3),
        date_confidence="low", description="x" * 500,
    )
    fields.update(overrides)
    return Posting(**fields)


with tempfile.TemporaryDirectory() as tmp:
    db = Path(tmp) / "t.db"
    store.init_db(db)
    with store.connect(db) as conn:
        run = store.start_run(conn, "broad")

        check("nothing suppressed before anything is shown",
              store.suppressed_board_roles(conn), set())

        board_id, _ = store.upsert_posting(conn, posting(), run)
        store.mark_presented(conn, [board_id], run)
        shown = store.suppressed_board_roles(conn)
        check("a presented board posting registers its role",
              ("delinea", "ai marketing solutions engineer") in shown, True)

        # The employer's own copy, different id, different ats, different body.
        ats_copy = posting(source_id="G9", ats="greenhouse",
                           source_slug="delinea", description="y" * 500)
        from careerops.fingerprint import fingerprint  # noqa: E402
        check(
            "the two copies genuinely fingerprint apart, which is why this check exists",
            fingerprint("Delinea", "AI Marketing Solutions Engineer", "x" * 500)
            == fingerprint("Delinea", "AI Marketing Solutions Engineer", "y" * 500),
            False,
        )
        check(
            "but the role matches, so the second copy is caught",
            (store.normalize_company(ats_copy.company),
             store.normalize_title(ats_copy.title)) in shown,
            True,
        )

        # An ATS-sourced posting that was presented must NOT enter this set --
        # otherwise a genuinely separate second opening at the same company
        # would be suppressed on title alone.
        other_id, _ = store.upsert_posting(
            conn, posting(source_id="G7", ats="greenhouse", source_slug="acme",
                          company="Acme", title="Marketing Engineer"), run)
        store.mark_presented(conn, [other_id], run)
        check("an ATS-sourced role does not join the board suppression set",
              ("acme", "marketing engineer") in store.suppressed_board_roles(conn),
              False)


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):\n")
    for failure in FAILURES:
        print(f"  {failure}\n")
    raise SystemExit(1)
print("All clone-collapse tests passed.")
