"""Content fingerprinting.

This is what makes suppression durable. A role Doran rejected in August that gets
taken down and reposted in October under a brand-new ATS id must still be
recognized as the same job -- otherwise "never show me this twice" silently fails
and the ghost-job / perpetual-repost detector has nothing to detect.

We deliberately fingerprint on company + title + the opening of the description
rather than on the full body, because employers routinely tweak a bullet or
refresh a benefits blurb on repost. The opening paragraphs are stable.
"""

from __future__ import annotations

import hashlib
import re

_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")

# Suffixes that show up inconsistently across ATS records for the same employer.
_COMPANY_NOISE = re.compile(
    r"\b(inc|llc|ltd|corp|corporation|co|company|holdings|group|technologies|"
    r"technology|labs|hq|usa|us)\b"
)

# Seniority/format decorations that get shuffled between reposts of one role.
_TITLE_NOISE = re.compile(
    r"\b(full.?time|part.?time|contract|remote|hybrid|on.?site|onsite|"
    r"us|usa|united states|new|urgent|hiring|open|f\/?m\/?d|m\/?f\/?d)\b"
)

DESC_PREFIX_CHARS = 400


def normalize_text(value: str | None) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    if not value:
        return ""
    out = _NON_ALNUM.sub(" ", value.lower())
    return _WS.sub(" ", out).strip()


def normalize_company(name: str | None) -> str:
    out = _COMPANY_NOISE.sub(" ", normalize_text(name))
    return _WS.sub(" ", out).strip()


def normalize_title(title: str | None) -> str:
    out = _TITLE_NOISE.sub(" ", normalize_text(title))
    # Drop bracketed/parenthetical decorations that reposts add and remove.
    out = _WS.sub(" ", out).strip()
    return out


def description_hash(description: str | None) -> str:
    """Hash of the full description -- used to detect *identical* reposts."""
    return hashlib.sha256(normalize_text(description).encode("utf-8")).hexdigest()


# Reseller boards repost one role once per country, changing nothing but the
# country name -- which sits in the opening sentence, inside the window
# fingerprint() hashes. Measured 2026-08-25: 25 rows titled "AWS Cloud Engineer"
# produced 25 distinct fingerprints; strip this preamble and all 25 collapse to
# one body. In run 14 that pattern cost 42 of 140 scoring slots -- 30% of the
# run -- with Claude re-reading text it had just read.
#
# This is used for a run-level duplicate check, NOT inside fingerprint() itself.
# fingerprint() feeds suppression -- the "never show me the same job twice"
# guarantee -- and changing it would orphan every fingerprint already stored,
# resurfacing postings Doran has already rejected.
_AGGREGATOR_PREAMBLE = re.compile(
    r"^this position is listed on behalf of a partner company.{0,200}?"
    r"\bbased in\b[a-z ]{0,40}?(?=\bthis is\b|\bthe role\b|\byou will\b|\bour\b)"
)


def clone_key(company: str, title: str, description: str | None) -> str:
    """Identity of a role with a reseller's per-country boilerplate removed.

    Deliberately separate from fingerprint(): this one is allowed to change
    whenever a new aggregator pattern is learned, because nothing durable is
    keyed on it. If the preamble does not match, this degrades to an ordinary
    full-body hash -- i.e. to the current behaviour, never to a wrong merge.
    """
    body = _AGGREGATOR_PREAMBLE.sub("", normalize_text(description))
    basis = "|".join((normalize_company(company), normalize_title(title), body))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def fingerprint(company: str, title: str, description: str | None) -> str:
    """Stable identity for a role across reposts and ATS id churn."""
    prefix = normalize_text(description)[:DESC_PREFIX_CHARS]
    basis = "|".join((normalize_company(company), normalize_title(title), prefix))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()
