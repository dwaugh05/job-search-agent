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


def fingerprint(company: str, title: str, description: str | None) -> str:
    """Stable identity for a role across reposts and ATS id churn."""
    prefix = normalize_text(description)[:DESC_PREFIX_CHARS]
    basis = "|".join((normalize_company(company), normalize_title(title), prefix))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()
