"""Text and price cleanup: raw page text in, typed values out (Part 1).

Kept out of the spider so the spider stays about traversal. Nothing here
imports Scrapy or hits the network, so it is testable on its own.

All three return None instead of raising when the input is missing or
unreadable - one bad page should not stop a crawl. All three are pure.

Doctests: from crawler/, run `python -m doctest bookscrawler/parsers.py`.
Silence means they passed.
"""

import re
from typing import Iterable, Optional, Tuple

# Prices render as "£51.77", sometimes with a stray "Â" in front from an
# encoding slip, so match the number and treat whatever precedes it as symbol.
_PRICE_RE = re.compile(r"(?P<symbol>[^\d\s]*)\s*(?P<amount>\d+(?:[.,]\d+)?)")

_CURRENCY_BY_SYMBOL = {
    "£": "GBP",
    "$": "USD",
    "€": "EUR",
}


def clean_text(parts: Iterable[Optional[str]]) -> Optional[str]:
    """Join text fragments and squash whitespace runs to single spaces.

    Returns None if nothing is left. "Absent" and "blank" both mean no value
    downstream, so they are not worth distinguishing.
    """
    joined = " ".join(part for part in parts if part)
    collapsed = re.sub(r"\s+", " ", joined).strip()
    return collapsed or None


def parse_price(raw: Optional[str]) -> Tuple[Optional[float], Optional[str]]:
    """Split a displayed price into a numeric amount and a currency code.

    >>> parse_price("£51.77")
    (51.77, 'GBP')
    >>> parse_price("")
    (None, None)

    Float rather than string so consumers can sort and total without
    re-parsing. Currency is kept so the number is not ambiguous.
    """
    if not raw:
        return None, None

    match = _PRICE_RE.search(raw)
    if not match:
        return None, None

    amount = match.group("amount").replace(",", ".")
    try:
        value = float(amount)
    except ValueError:  # pragma: no cover - guarded by the regex above
        return None, None

    symbol = match.group("symbol").strip()
    # Strip mojibake such as "Â£" so the symbol lookup still resolves.
    currency = next(
        (code for sym, code in _CURRENCY_BY_SYMBOL.items() if sym in symbol),
        None,
    )
    return value, currency


# Leading slice used to spot the repeated teaser below. Long enough to be
# unique to a description, short enough to exist in a short one.
_PREVIEW_SIGNATURE_LENGTH = 40


def strip_truncated_preview(text: Optional[str]) -> Optional[str]:
    """Drop the duplicated teaser books.toscrape.com puts in descriptions.

    Long descriptions sit in one <p> as: teaser cut mid-word, then the full
    text, then "...more". The teaser is a prefix of the full text, so the real
    description starts at the second occurrence of its own opening characters.

    >>> strip_truncated_preview("Hello world this is the whole thing, really "
    ...                         "Hello world this is the whole thing, really. ...more")
    'Hello world this is the whole thing, really.'

    Short descriptions have no teaser and pass through untouched.
    """
    if not text:
        return None

    body = text.removesuffix("...more").strip()

    signature = body[:_PREVIEW_SIGNATURE_LENGTH]
    if signature:
        repeat_at = body.find(signature, 1)
        if repeat_at != -1:
            body = body[repeat_at:]

    return body.strip() or None
