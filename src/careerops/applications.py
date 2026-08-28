"""Permanent archive of the roles Doran actually applied to.

The problem this solves: he applies to a lot of places, and by the time a
recruiter calls he no longer remembers which posting it was or what the job
was actually asking him to do. Companies routinely take the posting down, and
our own copy is not safe either -- `store.upsert_posting` overwrites
`postings.description` every time the same req reappears in a scan. So the
snapshot is taken at verdict time and written to disk, where nothing rewrites
it.

What gets saved is deliberately NOT the whole posting. It is the part that
answers "what does this job ask me to do" -- the overview, the
responsibilities, and the requirements -- captured verbatim, because a
paraphrase is useless for interview prep.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from . import comp as comp_mod
from . import config
from .normalize import fix_mojibake

ARCHIVE_DIR = config.DATA_DIR / "applications"
INDEX_PATH = ARCHIVE_DIR / "INDEX.md"

# --------------------------------------------------------------- section detect

# Postings almost never say "Responsibilities". Of the roles Doran had already
# applied to when this was written, three used that word and the rest used
# "WHAT YOU'LL DO", "What You'll Do", "What you will do in this role:" and
# "ROLE OVERVIEW". The phrasing is the hard part, not the parsing -- so the
# variants live here, in one list, and a new one is a one-line addition.
#
# Match is on a short standalone line, case-insensitive, punctuation-loose.

_OVERVIEW = [
    "role overview", "an overview of this role", "about the role", "about this role",
    "the role", "the opportunity", "position summary", "job summary", "role summary",
    "overview", "job description", "about the job", "the position", "your mission",
    "why this role", "role purpose", "purpose of the role",
]

_RESPONSIBILITIES = [
    "responsibilities", "key responsibilities", "core responsibilities",
    "primary responsibilities", "essential responsibilities", "duties",
    "duties and responsibilities", "essential duties",
    "what you'll do", "what you will do", "what youll do", "what you do",
    "what you'll be doing", "what you will be doing",
    "what you'll own", "what you will own", "what you'll drive",
    "what you'll work on", "what you will work on",
    "in this role you will", "in this role, you will", "in this role",
    "what you will do in this role", "what you'll do in this role",
    "your impact", "the impact you'll have", "how you'll make an impact",
    "how you will make an impact", "what success looks like",
    "your responsibilities", "you will", "you'll", "day to day", "day-to-day",
    "a day in the life", "what the job involves", "scope of the role",
    "what we're looking for you to do",
    # Jobgether rewrites every posting into its own house style and calls this
    # section "Accountabilities". Three of Doran's applications on 2026-08-26
    # archived with no responsibilities section at all because of it -- and the
    # archive is what he preps from once the posting is taken down.
    "accountabilities", "key accountabilities", "your accountabilities",
]

_REQUIREMENTS = [
    "requirements", "qualifications", "basic qualifications",
    "minimum qualifications", "preferred qualifications", "required qualifications",
    "what you have", "what you'll have", "what you'll bring", "what you will bring",
    "what you bring", "who you are", "about you", "what we're looking for",
    "what we are looking for", "skills and experience", "experience",
    "required skills", "preferred skills", "nice to have", "nice-to-have",
    "bonus points", "bonus points if", "to be successful in this role, you will have",
    "to be successful in this role you will have", "you might be a good fit if",
    "we're looking for", "desired qualifications", "your background",
    "skills & experience", "required experience", "preferred experience",
]

# Anything here ends a section. Without an explicit stop list the capture runs
# straight through the pay range and into the EEO boilerplate.
_STOP = [
    "compensation", "salary", "pay range", "salary range", "compensation range",
    "base pay", "base salary", "pay transparency", "benefits", "perks",
    "perks and benefits", "benefits and perks", "what we offer", "our offer",
    "equal opportunity", "equal employment opportunity", "eeo", "eeoc",
    "accommodations", "accommodation", "export control", "work personas",
    "privacy", "privacy notice", "e-verify", "our mission", "our solution",
    "our culture", "our culture & values", "our values", "about us",
    "about the company", "about the team", "the team", "who we are",
    "how we work", "our stack", "interview process", "hiring process",
    "next steps", "location", "travel", "disclaimer", "note",
]

# Some postings write the responsibilities heading as a sentence addressed to
# the candidate instead of a label -- Webflow opens with "As a Senior Marketing
# Manager, Web Growth, you'll:". No fixed phrase list can catch those.
_RESP_PATTERNS = [
    re.compile(r"^as\s+(a|an|the)\b.*\byou\W?ll\b", re.I),
    re.compile(r"^in\s+this\s+(role|position)\b.*\byou\b", re.I),
    re.compile(r"^you\W?ll\s+(be\s+)?(do|own|lead|driv|build|partner|work|help|focus)", re.I),
    re.compile(r"^(here\W?s\s+)?what\s+you\W?ll\b", re.I),
    re.compile(r"^what\s+you\s+will\b", re.I),
]

# Checked BEFORE the responsibilities patterns above, because "What you'll
# bring" and "What you'll do" differ by one word and mean opposite things.
_REQ_PATTERNS = [
    re.compile(r"^what\s+you\W?(ll\s+)?(bring|need|have|should\s+have)\b", re.I),
    re.compile(r"^(minimum|preferred|basic|required|desired)\b.*\bqualification", re.I),
    re.compile(r"^you\s+(might|may|could)\s+be\s+a\s+\w+\s+fit\b", re.I),
    re.compile(r"^(skills|experience|background)\s*(and|&|/)?\s*\w*\s*(required|preferred)?:?$", re.I),
]

# "WHY HARVEY", "WHY BOX NEEDS YOU", "How GitLab will support you" -- company
# pitch and benefits sections whose wording is company-specific.
_STOP_PATTERNS = [
    # GitLab heads its pay block "United States Salary Range", Box heads its
    # "Redwood City Pay Range" -- the location prefix makes a fixed phrase useless.
    re.compile(r".*\b(salary|pay|compensation)\s+range\b", re.I),
    re.compile(r"^why\s+\w+", re.I),
    re.compile(r"^how\s+\w+\s+(will\s+)?supports?\b", re.I),
    re.compile(r"^life\s+at\s+\w+", re.I),
    re.compile(r"^working\s+at\s+\w+", re.I),
    re.compile(r"^join\s+\w+", re.I),
]

_OVERVIEW_CAT, _RESP_CAT, _REQ_CAT, _STOP_CAT = "overview", "responsibilities", "requirements", "stop"

# Apostrophes are dropped rather than kept: GitLab writes "What You’ll Do" with
# a curly apostrophe and Box writes "WHAT YOU'LL DO" with a straight one, and
# both must normalize to the same key.
_PUNCT = re.compile(r"[^a-z0-9 ]+")
_MAX_HEADING_LEN = 90


def _normalize_heading(line: str) -> str:
    text = line.strip().strip("*#_").strip()
    text = _PUNCT.sub(" ", text.lower())
    return " ".join(text.split())


def _phrase_set(phrases: list[str]) -> set[str]:
    return {_normalize_heading(p) for p in phrases}


_CATEGORIES = [
    (_OVERVIEW_CAT, _phrase_set(_OVERVIEW)),
    (_RESP_CAT, _phrase_set(_RESPONSIBILITIES)),
    (_REQ_CAT, _phrase_set(_REQUIREMENTS)),
    (_STOP_CAT, _phrase_set(_STOP)),
]


def classify_heading(line: str) -> str | None:
    """Return the section category this line opens, or None if it is body text.

    Only short, standalone, non-bullet lines are considered. Unrecognised
    headings return None on purpose: a posting like ServiceNow's nests six
    sub-headings inside its responsibilities list, and treating those as
    section breaks would truncate the capture after one paragraph.
    """
    raw = line.strip()
    if not raw or len(raw) > _MAX_HEADING_LEN or raw.startswith(("-", "*", "•")):
        return None
    key = _normalize_heading(raw)
    if not key:
        return None
    for category, phrases in _CATEGORIES:
        if key in phrases:
            return category
    for pattern in _REQ_PATTERNS:
        if pattern.match(raw):
            return _REQ_CAT
    for pattern in _RESP_PATTERNS:
        if pattern.match(raw):
            return _RESP_CAT
    for pattern in _STOP_PATTERNS:
        if pattern.match(raw):
            return _STOP_CAT
    return None


# Unlabelled responsibility lists still look like responsibility lists: a run of
# bullets that start with an action verb. This is the first fallback when no
# heading matched at all.
_ACTION_VERBS = (
    "lead", "own", "build", "partner", "drive", "define", "manage", "develop",
    "collaborate", "design", "create", "deliver", "execute", "support", "run",
    "launch", "scale", "establish", "identify", "translate", "implement",
    "coordinate", "analyze", "analyse", "optimize", "optimise", "champion",
    "evangelize", "enable", "measure", "report", "work", "act", "serve",
    "oversee", "guide", "shape", "craft", "maintain", "monitor", "produce",
    "find", "turn", "make", "help", "ship", "grow", "improve", "automate",
)
_BULLET = re.compile(r"^[-*•]\s*(.+)$")


def _bullet_block(text: str) -> str:
    """The first run of 3+ action-verb bullets, as a fallback capture."""
    lines = text.split("\n")
    best: list[str] = []
    current: list[str] = []
    for line in lines:
        match = _BULLET.match(line.strip())
        if match:
            first = match.group(1).strip().split(" ")[0].lower().strip(",:;")
            if not current and first not in _ACTION_VERBS:
                continue
            current.append(line.strip())
            continue
        if current:
            if len(current) > len(best):
                best = current
            current = []
    if len(current) > len(best):
        best = current
    return "\n".join(best) if len(best) >= 3 else ""


def _first_imperative_heading(text: str) -> str | None:
    """The first short standalone line phrased as a command ("Build the thing").

    A heading in the imperative is a responsibilities heading whatever it is
    filed under -- it is the posting telling the candidate what to go and do.
    """
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or len(stripped) > _MAX_HEADING_LEN:
            continue
        if stripped.startswith(("-", "*", "•")) or stripped.endswith((".", ",", ";")):
            continue
        first = stripped.split(" ")[0].lower().strip(",:;")
        # Two words minimum: a bare "Build" is more likely a section label than
        # an instruction, and single words are too weak a signal to split on.
        if first in _ACTION_VERBS and len(stripped.split()) >= 3:
            return stripped
    return None


def extract_sections(description: str | None) -> dict[str, object]:
    """Pull the "what this job asks you to do" sections out of a posting.

    Returns the captured text per category plus `via`, a plain-language note on
    how it was found, so Doran can tell a clean capture from a fallback at a
    glance.
    """
    text = fix_mojibake(description or "").replace("\r\n", "\n")
    empty = {"overview": "", "responsibilities": "", "requirements": "",
             "full": "", "via": "no description stored"}
    if not text.strip():
        return empty

    captured: dict[str, list[str]] = {}
    headings: dict[str, str] = {}
    current: str | None = None

    for line in text.split("\n"):
        category = classify_heading(line)
        if category is not None:
            # Same category twice in a row (Requirements then Nice to have)
            # continues the section rather than restarting it.
            if category == _STOP_CAT:
                current = None
            elif category == current:
                captured.setdefault(current, []).append(line.strip())
            else:
                current = category
                captured.setdefault(category, [])
                headings.setdefault(category, line.strip())
            continue
        if current:
            captured[current].append(line)

    def joined(category: str) -> str:
        # strip_html leaves a stray leading space on converted <li> lines, which
        # renders as an indented sub-list in markdown. Flatten it back.
        body = "\n".join(
            re.sub(r"^\s+(?=[-*•]\s)", "", line) for line in captured.get(category, [])
        )
        return re.sub(r"\n{3,}", "\n\n", body).strip()

    overview, responsibilities, requirements = (
        joined(_OVERVIEW_CAT), joined(_RESP_CAT), joined(_REQ_CAT))

    if not responsibilities and overview:
        # Natera labels the whole thing "About the role" and then breaks the
        # actual work into imperative sub-headings ("Design the future-state
        # workflow", "Build and connect the systems"). The content is right
        # there; only the label is missing. Split the overview at the first
        # command-form sub-heading rather than filing the job's real duties
        # under a heading that reads like company blurb.
        split_at = _first_imperative_heading(overview)
        if split_at is not None:
            head, _, tail = overview.partition(split_at)
            if tail.strip():
                overview, responsibilities = head.strip(), (split_at + tail).strip()
                return {"overview": overview, "responsibilities": responsibilities,
                        "requirements": requirements, "full": "",
                        "via": f'unlabelled duties under "{headings[_OVERVIEW_CAT]}"'}

    if responsibilities:
        via = f'heading "{headings[_RESP_CAT]}"'
    elif overview or requirements:
        found = headings.get(_OVERVIEW_CAT) or headings.get(_REQ_CAT)
        via = f'no responsibilities heading found - captured "{found}" instead'
    else:
        bullets = _bullet_block(text)
        if bullets:
            return {"overview": "", "responsibilities": bullets, "requirements": "",
                    "full": "", "via": "unlabelled bullet list (no headings matched)"}
        return {"overview": "", "responsibilities": "", "requirements": "",
                "full": text.strip(),
                "via": "full-text fallback - no headings matched, whole posting saved"}

    return {"overview": overview, "responsibilities": responsibilities,
            "requirements": requirements, "full": "", "via": via}


# ------------------------------------------------------------------- archiving


_SLUG = re.compile(r"[^a-z0-9]+")


def _slugify(text: str, limit: int = 48) -> str:
    slug = _SLUG.sub("-", (text or "").lower()).strip("-")
    return slug[:limit].strip("-") or "role"


_POSTING_ID = re.compile(r"^_Posting id (\d+)\._$", re.M)


def archive_path(row: sqlite3.Row, applied_date: str) -> Path:
    """Where this application's file lives.

    Filenames are human-readable rather than id-based, because Doran browses
    this folder directly. Companies do repost the same role under two reqs
    though -- Harvey had one job listed twice -- so a name that is already taken
    by a *different* posting gets a numeric suffix instead of overwriting it.
    """
    base = f"{applied_date}-{_slugify(row['company'], 24)}-{_slugify(row['title'])}"
    candidate = ARCHIVE_DIR / f"{base}.md"
    suffix = 2
    while candidate.exists():
        match = _POSTING_ID.search(candidate.read_text(encoding="utf-8"))
        if match and int(match.group(1)) == int(row["id"]):
            return candidate
        candidate = ARCHIVE_DIR / f"{base}-{suffix}.md"
        suffix += 1
    return candidate


def _field(label: str, value: str | None) -> str | None:
    return f"- **{label}:** {value}" if value else None


def write_application(
    row: sqlite3.Row,
    *,
    applied_date: str,
    reason: str | None = None,
    score: float | None = None,
    connection_bonus: float = 0.0,
    fit_summary: str | None = None,
) -> Path:
    """Snapshot one applied posting to a permanent markdown file."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    sections = extract_sections(row["description"])

    score_text = None
    if score:
        score_text = f"{score:.1f}"
        if connection_bonus:
            score_text += f" (includes +{connection_bonus:.1f} connection bump)"

    salary = comp_mod.format_range(row["salary_min"], row["salary_max"]) or "Not listed"
    location = row["city"] or row["location_raw"] or "Not stated"
    work_model = row["work_model"] or ""
    if work_model and work_model.lower() not in location.lower():
        location = f"{location} - {work_model}"

    lines = [f"# {row['title']} - {row['company']}", ""]
    for field in (
        _field("Applied", applied_date),
        _field("Posted", str(row["published_at"])[:10] if row["published_at"] else "Not stated"),
        _field("Score", score_text),
        _field("Location", location),
        _field("Salary", salary),
        _field("Posting", f"{row['url']}"),
        _field("Why I applied", reason),
    ):
        if field:
            lines.append(field)

    lines += [
        "",
        "> The posting may be taken down. Everything below is a verbatim snapshot "
        "of it, saved on the day of application.",
        "",
        f"_Captured via: {sections['via']}._",
        "",
        f"_Posting id {row['id']}._",
        "",
    ]

    for heading, key in (
        ("Role overview (verbatim)", "overview"),
        ("What this job asks you to do (verbatim)", "responsibilities"),
        ("Requirements / qualifications (verbatim)", "requirements"),
        ("Full posting - no section headings found (verbatim)", "full"),
    ):
        body = str(sections.get(key) or "")
        if body:
            lines += [f"## {heading}", "", body, ""]

    if fit_summary:
        lines += ["## Fit summary at time of scan", "", fit_summary.strip(), ""]

    path = archive_path(row, applied_date)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


_TITLE = re.compile(r"^#\s+(.*?)\s*$", re.M)


def rebuild_index() -> Path:
    """Regenerate INDEX.md from whatever is on disk, newest first."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in ARCHIVE_DIR.glob("*.md"):
        if path.name == "INDEX.md":
            continue
        text = path.read_text(encoding="utf-8")
        match = _TITLE.search(text)
        title = match.group(1) if match else path.stem
        date = path.name[:10]
        applied = re.search(r"^- \*\*Applied:\*\* (.+)$", text, re.M)
        if applied:
            date = applied.group(1).strip()
        score = re.search(r"^- \*\*Score:\*\* ([0-9.]+)", text, re.M)
        rows.append((date, title, path.name, score.group(1) if score else None))

    rows.sort(reverse=True)
    lines = [
        "# Applications",
        "",
        "Every role Doran applied to, newest first. Each file holds a verbatim",
        "snapshot of what the job asked for, taken the day he applied -- so it",
        "survives the posting being taken down.",
        "",
    ]
    for date, title, filename, score in rows:
        suffix = f" - scored {score}" if score else ""
        lines.append(f"- {date} - [{title}]({filename}){suffix}")
    if not rows:
        lines.append("_Nothing archived yet._")

    INDEX_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return INDEX_PATH
