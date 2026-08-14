"""Compensation parsing and Doran's total-comp math.

Two jobs:
  1. Pull a base-salary range out of structured ATS fields or free-text prose.
  2. Model total comp the way Doran actually evaluates an offer.

Doran's stated rules:
  - Target TC $200k-$300k; base floor $170k.
  - Assume a 10% bonus on base unless the posting says otherwise.
  - If equity/RSUs are mentioned at all, credit $20k-$50k/yr (model at $35k).
  - Ignore benefits and small perks entirely.
"""

from __future__ import annotations

import re

from .normalize import clean

BONUS_RATE = 0.10
EQUITY_CREDIT = 35_000
EQUITY_CREDIT_LOW = 20_000
EQUITY_CREDIT_HIGH = 50_000

# Where in a posted band to score.
#
# Doran, 2026-08-12: "$208 is acceptable and I'd negotiate for that top end, so
# I'm not worried about the low end of the pay for any of these roles ever."
#
# So score the TOP of the band, not a midpoint or a 70% offer point. He intends
# to negotiate there and does not want a wide band pushing a good role down the
# list. The floor still matters, but it is enforced as a hard gate on the band
# maximum (profile.yml: min_base_salary_max), not as a scoring penalty.
OFFER_POINT = 1.00

_MIN_PLAUSIBLE = 40_000
_MAX_PLAUSIBLE = 1_200_000

_EQUITY_PAT = re.compile(
    r"\b(equity|rsus?|restricted stock|stock options?|share options?|"
    r"offers equity|ownership stake)\b",
    re.IGNORECASE,
)
_BONUS_PAT = re.compile(
    r"\b(bonus|variable compensation|incentive compensation|commission)\b",
    re.IGNORECASE,
)
_HOURLY_PAT = re.compile(r"(per hour|/\s*hour|hourly|/\s*hr)\b", re.IGNORECASE)

# Geographic pay tiers. Doran is in the Bay Area, which is always the top tier,
# so a posting that publishes several bands should be read at the high one.
_HIGH_COL_PAT = re.compile(
    r"\b(high(?:er)?\s+cost\s+of\s+living|high\s+col|tier\s*1|"
    r"premium\s+(?:market|location)|sf\s+bay\s+area|san\s+francisco\s+bay)\b",
    re.IGNORECASE,
)
_LOW_COL_PAT = re.compile(
    r"\b(low(?:er)?\s+cost\s+of\s+living|low\s+col|tier\s*3)\b",
    re.IGNORECASE,
)

# "$136K", "$136,000", "$136k", "$159,780.00"
# The trailing (?:\.\d+)? on the comma-grouped branch matters: Included Health
# posts "$159,780.00 - $238,080.00", and without it the range never matches, so
# only the floor is read and the role scores as if it topped out at its minimum.
_MONEY = r"\$\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*([kKmM])?"
_RANGE_PAT = re.compile(
    _MONEY + r"\s*(?:-|--|to|through|–|—|and)\s*" + _MONEY
)
_SINGLE_PAT = re.compile(_MONEY)

# Prose that signals the number nearby is actually a salary, not ARR or funding.
_SALARY_CONTEXT = re.compile(
    r"(salary|base pay|base compensation|pay range|compensation range|"
    r"annual|per year|/\s*yr|/\s*year|on target earnings|ote|cash compensation)",
    re.IGNORECASE,
)


def _to_number(amount: str, suffix: str | None, *, hourly: bool = False) -> float | None:
    """Resolve a matched figure to annual dollars.

    Order matters here. An explicit k/m suffix is always annual. Otherwise a bare
    figure is ambiguous, and the hourly check has to come BEFORE the
    "under 1000 means thousands" shorthand -- resolving "$85 - $95 per hour" as
    $85k first and then annualizing it yields $176 million.
    """
    try:
        value = float(amount.replace(",", ""))
    except ValueError:
        return None
    if suffix and suffix.lower() == "k":
        return value * 1_000
    if suffix and suffix.lower() == "m":
        return value * 1_000_000
    if hourly and value < 500:
        return value * 2080
    if value < 1_000:
        # Bare "$136" in a salary context almost always means $136k.
        return value * 1_000
    return value


def _plausible(value: float | None) -> bool:
    return value is not None and _MIN_PLAUSIBLE <= value <= _MAX_PLAUSIBLE


def parse_salary(text: str | None) -> tuple[int | None, int | None]:
    """Extract a (min, max) base-salary range from any string. (None, None) if absent."""
    raw = clean(text)
    if not raw:
        return None, None

    def _is_hourly(start: int, end: int) -> bool:
        """Check for hourly wording NEAR the figure, never across the whole doc.

        A global check reads DoorDash's benefits line -- "For hourly roles:
        vacation accrued at about 1 hour for every 25.97 hours worked" -- and
        concludes the annual $142,800-$210,000 band is an hourly rate, multiplies
        it by 2080, and throws it away as implausible.
        """
        window = raw[max(0, start - 60) : end + 30]
        return bool(_HOURLY_PAT.search(window))

    # Employers that publish geographic bands list several ranges in one posting.
    # Taking the first understates Doran, who is in the Bay Area and therefore
    # always in the highest tier -- Natera published a standard band of
    # $152,100-$190,100 and a higher-cost-of-living band of $167,300-$209,100,
    # and the first-match rule cost the role $19,000 of base.
    candidates: list[tuple[int, int, str]] = []
    previous_end = 0
    for match in _RANGE_PAT.finditer(raw):
        hourly = _is_hourly(match.start(), match.end())
        low = _to_number(match.group(1), match.group(2), hourly=hourly)
        high = _to_number(match.group(3), match.group(4), hourly=hourly)
        if _plausible(low) and _plausible(high) and high >= low:
            # Stop the lookback at the previous range, or a band listed right
            # after the low-cost one inherits its label and wins by mistake.
            label_window = raw[max(previous_end, match.start() - 90) : match.start()]
            if _HIGH_COL_PAT.search(label_window):
                tier = "high"
            elif _LOW_COL_PAT.search(label_window):
                tier = "low"
            else:
                tier = "standard"
            candidates.append((int(low), int(high), tier))
            previous_end = match.end()

    if candidates:
        high_tier = [c for c in candidates if c[2] == "high"]
        if high_tier:
            best = max(high_tier, key=lambda c: c[1])
            return best[0], best[1]
        # No high-COL band published: never settle for one explicitly marked as
        # the low-cost-of-living tier when another range is available.
        non_low = [c for c in candidates if c[2] != "low"]
        best = (non_low or candidates)[0]
        return best[0], best[1]

    # No range -- fall back to a single figure, but only near salary language,
    # otherwise "$50M Series C" gets read as a paycheck.
    for match in _SINGLE_PAT.finditer(raw):
        window = raw[max(0, match.start() - 120) : match.end() + 120]
        if not _SALARY_CONTEXT.search(window):
            continue
        value = _to_number(
            match.group(1), match.group(2),
            hourly=_is_hourly(match.start(), match.end()),
        )
        if _plausible(value):
            return int(value), int(value)

    return None, None


def mentions_equity(*texts: str | None) -> bool:
    return any(_EQUITY_PAT.search(clean(t)) for t in texts if t)


def mentions_bonus(*texts: str | None) -> bool:
    return any(_BONUS_PAT.search(clean(t)) for t in texts if t)


def stated_bonus_rate(text: str | None) -> float | None:
    """Pick up an explicit bonus percentage so we don't override it with our 10%."""
    raw = clean(text)
    if not raw:
        return None
    match = re.search(
        r"(\d{1,2}(?:\.\d)?)\s*%\s*(?:annual\s+|target\s+|performance\s+)*bonus",
        raw,
        re.IGNORECASE,
    )
    if not match:
        match = re.search(
            r"bonus\s*(?:target\s*)?(?:of\s*)?(?:up to\s*)?(\d{1,2}(?:\.\d)?)\s*%",
            raw,
            re.IGNORECASE,
        )
    if match:
        try:
            return float(match.group(1)) / 100.0
        except ValueError:
            return None
    return None


def realistic_base(salary_min: int | None, salary_max: int | None) -> int | None:
    """Where Doran would realistically land in a posted band."""
    if salary_min is None and salary_max is None:
        return None
    if salary_min is None:
        return salary_max
    if salary_max is None:
        return salary_min
    return int(salary_min + OFFER_POINT * (salary_max - salary_min))


def model_total_comp(
    salary_min: int | None,
    salary_max: int | None,
    *,
    equity: bool = False,
    bonus_rate: float | None = None,
) -> dict[str, int | None]:
    """Doran's TC model. Returns base/bonus/equity components and a TC range."""
    base = realistic_base(salary_min, salary_max)
    if base is None:
        return {
            "base": None, "bonus": None, "equity": None,
            "tc": None, "tc_low": None, "tc_high": None,
        }

    rate = BONUS_RATE if bonus_rate is None else bonus_rate
    bonus = int(round(base * rate))
    equity_value = EQUITY_CREDIT if equity else 0
    equity_low = EQUITY_CREDIT_LOW if equity else 0
    equity_high = EQUITY_CREDIT_HIGH if equity else 0

    return {
        "base": base,
        "bonus": bonus,
        "equity": equity_value,
        "tc": base + bonus + equity_value,
        "tc_low": base + bonus + equity_low,
        "tc_high": base + bonus + equity_high,
    }


def format_range(salary_min: int | None, salary_max: int | None) -> str | None:
    if salary_min is None and salary_max is None:
        return None
    if salary_min == salary_max:
        return f"${salary_min:,.0f}"
    return f"${salary_min:,.0f} - ${salary_max:,.0f}"
