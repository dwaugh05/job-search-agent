"""Last-resort ATS discovery: read the board address off the company's own site.

`resolve.resolve()` finds a board by GUESSING slugs -- roughly 45 combinations of
ATS x slug variant. That works for companies whose board slug looks like their
name, and fails completely for everyone else: Workday tenants, bespoke career
sites, and anyone whose slug is unguessable (DoorDash is `doordashusa`).

This module does the obvious thing instead. It opens the company's careers page
and reads the real ATS link out of the HTML, the same way a person would.

Two passes, cheapest first:

1. **Static** -- fetch the page with httpx and regex the HTML. Costs a handful of
   requests and catches every site that renders its careers links server-side.
2. **Rendered** -- only if static found nothing AND a headless browser is
   available, render the page and scan again. This is what catches React-based
   careers pages that build their links in JavaScript.

Pass 2 degrades to a no-op when no browser library is installed, so the module is
always importable and the scan never crashes for want of an optional dependency.

Nothing here reads job postings. It only discovers WHERE the live feed lives --
the postings themselves are still fetched from the ATS by the normal adapters,
so CLAUDE.md's "no cached search results" rule is preserved.
"""

from __future__ import annotations

import re
from typing import Iterable

import httpx

from . import ashby, greenhouse, lever, smartrecruiters, workable, workday
from .registry import USER_AGENT, _wait_turn

# Deliberately short. Most of the URLs this module tries are GUESSES that do not
# resolve, and a guess that fails should cost almost nothing. With the default
# 20s/10s a single failed company took over five minutes -- across sixty unknown
# employers in one scan that is five hours before a single job is fetched.
TIMEOUT = httpx.Timeout(8.0, connect=3.0)

# Hard ceiling on how long one company may take, whatever happens. Bulk callers
# lower this further; see `budget_seconds` on sniff().
DEFAULT_BUDGET_SECONDS = 45.0

# Careers pages, in the order they are worth trying.
CAREERS_PATHS = (
    "/careers", "/careers/", "/jobs", "/jobs/", "/company/careers",
    "/about/careers", "/careers/open-positions", "/company/jobs", "/join-us", "/",
)

# Domain guesses derived from the company name. Cheap, and right often enough.
TLDS = (".com", ".ai", ".io", ".co", ".org", ".net")

# Each pattern must capture the slug in group 1.
_PATTERNS: tuple[tuple[str, str], ...] = (
    (greenhouse.NAME,
     r"(?:boards|job-boards|boards-api)\.greenhouse\.io/(?:embed/job_board\?for=)?([a-z0-9_\-]+)"),
    (ashby.NAME, r"jobs\.ashbyhq\.com/([a-z0-9_\-]+)"),
    (lever.NAME, r"jobs\.lever\.co/([a-z0-9_\-]+)"),
    (smartrecruiters.NAME, r"(?:careers|jobs)\.smartrecruiters\.com/([a-z0-9_\-]+)"),
    (workable.NAME, r"(?:apply|jobs)\.workable\.com/([a-z0-9_\-]+)"),
)
_COMPILED = tuple((ats, re.compile(rx, re.IGNORECASE)) for ats, rx in _PATTERNS)

# Workday packs three values into one slug: tenant:instance:site.
_WORKDAY_RE = re.compile(
    r"https?://([a-z0-9\-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:wday/cxs/[a-z0-9\-]+/)?([A-Za-z0-9_\-]+)",
    re.IGNORECASE,
)

# Slugs that belong to the ATS vendor itself, not to a customer.
_NOISE = {
    "embed", "job_board", "static", "assets", "www", "api", "v1", "search",
    "jobs", "careers", "company", "companies", "about", "privacy", "terms",
    "greenhouse", "ashby", "lever", "workable", "smartrecruiters",
}


def domain_candidates(company: str) -> list[str]:
    """Guess plausible domains for a company name."""
    base = re.sub(r"[^a-z0-9 ]", "", company.lower()).strip()
    if not base:
        return []
    words = base.split()
    stems: list[str] = []
    _EXTRA: list[str] = []   # already-complete domains, not stems needing a TLD

    def add(stem: str) -> None:
        if stem and stem not in stems:
            stems.append(stem)

    add("".join(words))
    add("-".join(words))
    # A trailing word that is itself a TLD is usually part of the domain, not a
    # suffix to strip: "C3 AI" is c3.ai, "Scale AI" is scale.ai. Guessing
    # c3ai.com instead is why C3 AI was undiscoverable.
    if len(words) > 1 and words[-1] in ("ai", "io", "co", "app", "dev", "sh"):
        stem_domain = "".join(words[:-1]) + "." + words[-1]
        if stem_domain not in _EXTRA:
            _EXTRA.append(stem_domain)
    # Drop common corporate suffixes: "Guidewire Software" -> "guidewire".
    trimmed = [w for w in words
               if w not in ("inc", "corp", "corporation", "company", "software",
                            "technologies", "technology", "labs", "systems",
                            "holdings", "group", "the", "io", "ai")]
    if trimmed and trimmed != words:
        add("".join(trimmed))
        add("-".join(trimmed))
    if len(words) > 1:
        add(words[0])
    return _EXTRA + [f"{stem}{tld}" for stem in stems[:4] for tld in TLDS]


def find_ats_links(html: str) -> list[tuple[str, str]]:
    """Extract every (ats, slug) pair referenced in a page's HTML."""
    found: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for ats, pattern in _COMPILED:
        for slug in pattern.findall(html or ""):
            slug = slug.strip().lower()
            if not slug or slug in _NOISE or len(slug) < 2:
                continue
            key = (ats, slug)
            if key not in seen:
                seen.add(key)
                found.append(key)

    for tenant, instance, site in _WORKDAY_RE.findall(html or ""):
        slug = f"{tenant.lower()}:{instance.lower()}:{site}"
        key = (workday.NAME, slug)
        if key not in seen:
            seen.add(key)
            found.append(key)

    return found


def _fetch(client: httpx.Client, url: str) -> str | None:
    _wait_turn(url)
    try:
        response = client.get(url)
    except (httpx.HTTPError, UnicodeError, ValueError):
        return None
    if response.status_code != 200:
        return None
    ctype = response.headers.get("content-type", "")
    if "html" not in ctype and "text" not in ctype:
        return None
    return response.text


def _chromium_executable() -> str | None:
    """Find a Chromium already on this machine, newest build first.

    Playwright pins an exact build number and offers to download it. That is a
    ~150MB download we do not need: any recent Chromium renders a careers page
    identically. Other tooling on this machine (the Node Playwright in the game
    project, the Chrome MCP servers) has already populated the shared cache, so
    we reuse whatever is there rather than adding another copy.

    Returns None if nothing suitable is installed, in which case the caller lets
    Playwright use its own default and download-prompt behaviour.
    """
    import os
    from pathlib import Path

    roots = [
        os.environ.get("PLAYWRIGHT_BROWSERS_PATH"),
        os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright"),
        os.path.expanduser("~/Library/Caches/ms-playwright"),
        os.path.expanduser("~/.cache/ms-playwright"),
    ]
    best: tuple[int, str] | None = None
    for root in roots:
        if not root:
            continue
        base = Path(root)
        if not base.is_dir():
            continue
        for entry in base.glob("chromium-*"):
            try:
                build = int(entry.name.rsplit("-", 1)[-1])
            except ValueError:
                continue
            for rel in ("chrome-win64/chrome.exe", "chrome-win/chrome.exe",
                        "chrome-linux/chrome",
                        "chrome-mac/Chromium.app/Contents/MacOS/Chromium"):
                exe = entry / rel
                if exe.exists() and (best is None or build > best[0]):
                    best = (build, str(exe))
    return best[1] if best else None


def _render(url: str) -> str | None:
    """Render `url` in a headless browser. Returns None if none is available."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return None
    exe = _chromium_executable()
    try:
        with sync_playwright() as p:
            kwargs = {"headless": True}
            if exe:
                kwargs["executable_path"] = exe
            browser = p.chromium.launch(**kwargs)
            try:
                page = browser.new_page(user_agent=USER_AGENT)
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                return page.content()
            finally:
                browser.close()
    except Exception:
        return None


def browser_available() -> bool:
    try:
        import playwright.sync_api  # type: ignore  # noqa: F401
    except ImportError:
        return False
    return True


def candidate_urls(company: str, domains: Iterable[str] | None = None) -> list[str]:
    urls: list[str] = []
    for domain in (domains if domains is not None else domain_candidates(company)):
        for path in CAREERS_PATHS:
            urls.append(f"https://{domain}{path}")
    return urls


# Careers sites very often live somewhere other than the marketing domain --
# metacareers.com, careers.walmart.com, jobs.netflix.com. Guessing paths under
# the main domain never reaches those, which is why the first version of this
# module only managed 4 hits out of 21. So: read the homepage and FOLLOW its
# careers link wherever it points, including to another domain entirely.
_CAREERS_LINK_RE = re.compile(
    r"""<a\b[^>]*href\s*=\s*["']([^"']+)["'][^>]*>(.{0,120}?)</a>""",
    re.IGNORECASE | re.DOTALL,
)
_CAREERS_WORD_RE = re.compile(r"career|jobs?\b|join.?us|work.with.us|openings",
                              re.IGNORECASE)


def careers_links(html: str, base_url: str) -> list[str]:
    """Pull plausible careers-page links out of a homepage."""
    from urllib.parse import urljoin, urlsplit

    out: list[str] = []
    seen: set[str] = set()
    for href, text in _CAREERS_LINK_RE.findall(html or ""):
        blob = f"{href} {re.sub(r'<[^>]+>', ' ', text)}"
        if not _CAREERS_WORD_RE.search(blob):
            continue
        url = urljoin(base_url, href.strip())
        if not url.startswith("http"):
            continue
        # An ATS link right here is the jackpot; keep it at the front.
        split = urlsplit(url)
        key = f"{split.netloc}{split.path}".rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(url)
    return out


def subdomain_candidates(company: str) -> list[str]:
    """careers.acme.com / jobs.acme.com / acmecareers.com style hosts."""
    base = re.sub(r"[^a-z0-9 ]", "", company.lower()).strip()
    words = [w for w in base.split()
             if w not in ("inc", "corp", "corporation", "company", "software",
                          "technologies", "technology", "labs", "systems",
                          "holdings", "group", "the")]
    stem = "".join(words) or base.replace(" ", "")
    if not stem:
        return []
    return [
        f"careers.{stem}.com", f"jobs.{stem}.com",
        f"{stem}careers.com", f"careers.{stem}.ai", f"jobs.{stem}.ai",
    ]


def sniff(company: str, *, use_browser: bool = True,
          max_pages: int = 12,
          budget_seconds: float = DEFAULT_BUDGET_SECONDS) -> tuple[str, str] | None:
    """Find (ats, slug) for `company` by reading its careers page.

    Returns None when nothing is found, which the caller should treat exactly
    like a failed slug probe.

    `budget_seconds` bounds the whole attempt. Without it the cost of a MISS is
    unbounded -- every dead domain guess costs a connect timeout, and a scan
    resolving sixty unknown employers inherits all of it.
    """
    import time as _time

    deadline = _time.monotonic() + max(1.0, budget_seconds)
    urls = candidate_urls(company)[:max_pages] + [
        f"https://{host}/" for host in subdomain_candidates(company)
    ]
    rendered_targets: list[str] = []
    followed = 0

    with httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": USER_AGENT}) as client:
        queue = list(urls)
        visited: set[str] = set()
        while queue:
            if _time.monotonic() > deadline:
                return None
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            html = _fetch(client, url)
            if html is None:
                continue
            hits = find_ats_links(html)
            if hits:
                return hits[0]
            # No ATS link in the raw HTML. Two possibilities: the real careers
            # page is elsewhere (follow the link), or this page builds its links
            # in JavaScript (render it later).
            if followed < 4:
                for link in careers_links(html, url)[:4]:
                    if link not in visited:
                        queue.append(link)
                        followed += 1
            rendered_targets.append(url)

    if use_browser and rendered_targets and browser_available():
        for url in rendered_targets[:3]:
            if _time.monotonic() > deadline:
                return None
            html = _render(url)
            if not html:
                continue
            hits = find_ats_links(html)
            if hits:
                return hits[0]

    return None
