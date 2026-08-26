"""HTML in, typed values out.

Nothing here touches the network or the filesystem, so every function can be
exercised on a saved page - which is what ``tests/test_parsers.py`` does. The
scraper module keeps the traversal; this module keeps the selectors.

Two conventions hold throughout:

* A missing or unreadable value returns ``None`` rather than raising. One
  malformed page should cost one field, not the run.
* Anything numeric comes back as a number, so consumers can sort and total
  without re-parsing.

Doctests: ``python -m doctest books_scraper/parsers.py`` (silence = passed).
"""

from __future__ import annotations

import re
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

#: Parser used everywhere. stdlib, so there is no lxml build to install.
HTML_PARSER = "html.parser"

# Prices render as "GBP 51.77" with a symbol; the symbol may arrive as mojibake
# if an encoding slipped upstream, so match the number and treat whatever
# precedes it as the symbol.
_PRICE_RE = re.compile(r"(?P<symbol>[^\d\s]*)\s*(?P<amount>\d+(?:[.,]\d+)?)")

_CURRENCY_BY_SYMBOL = {"£": "GBP", "$": "USD", "€": "EUR"}

# "In stock (22 available)" -> 22
_STOCK_COUNT_RE = re.compile(r"(\d+)\s+available", re.IGNORECASE)

# The star rating is encoded in a CSS class: <p class="star-rating Three">.
_RATING_BY_WORD = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

# Leading slice used to spot the repeated teaser in long descriptions. Long
# enough to be unique to a description, short enough to exist in a short one.
_PREVIEW_SIGNATURE_LENGTH = 40


def make_soup(html: str) -> BeautifulSoup:
    """Parse a page once, so callers are not tempted to re-parse per field."""
    return BeautifulSoup(html, HTML_PARSER)


def clean_text(parts: Iterable[Optional[str]]) -> Optional[str]:
    """Join text fragments and squash whitespace runs to single spaces.

    >>> clean_text(["  In stock\\n", "  (22 available)  "])
    'In stock (22 available)'
    >>> clean_text(["", None]) is None
    True

    Returns None when nothing is left: "absent" and "blank" mean the same thing
    downstream, so they are not worth distinguishing.
    """
    joined = " ".join(part for part in parts if part)
    collapsed = re.sub(r"\s+", " ", joined).strip()
    return collapsed or None


def parse_price(raw: Optional[str]) -> tuple[Optional[float], Optional[str]]:
    """Split a displayed price into a numeric amount and an ISO currency code.

    >>> parse_price("£51.77")
    (51.77, 'GBP')
    >>> parse_price("Â£51.77")
    (51.77, 'GBP')
    >>> parse_price("")
    (None, None)
    """
    if not raw:
        return None, None

    match = _PRICE_RE.search(raw)
    if not match:
        return None, None

    try:
        value = float(match.group("amount").replace(",", "."))
    except ValueError:  # pragma: no cover - the regex already constrains this
        return None, None

    symbol = match.group("symbol").strip()
    currency = next(
        (code for sym, code in _CURRENCY_BY_SYMBOL.items() if sym in symbol), None
    )
    return value, currency


def parse_stock_count(availability: Optional[str]) -> Optional[int]:
    """Pull the stock count out of an availability string.

    >>> parse_stock_count("In stock (22 available)")
    22
    >>> parse_stock_count("In stock") is None
    True
    """
    if not availability:
        return None
    match = _STOCK_COUNT_RE.search(availability)
    return int(match.group(1)) if match else None


def parse_rating(node: Optional[Tag]) -> Optional[int]:
    """Turn a ``<p class="star-rating Three">`` element into ``3``.

    The word in the class is the only place the rating lives - the stars
    themselves are identical ``<i>`` elements - so an unrecognised class means
    no rating rather than a guess.
    """
    if node is None:
        return None
    for css_class in node.get("class", []):
        if css_class in _RATING_BY_WORD:
            return _RATING_BY_WORD[css_class]
    return None


def strip_truncated_preview(text: Optional[str]) -> Optional[str]:
    """Drop the duplicated teaser books.toscrape.com puts in descriptions.

    Long descriptions sit in one <p> as: teaser cut mid-word, then the full
    text, then "...more". The teaser is a prefix of the full text, so the real
    description starts at the second occurrence of its own opening characters.

    >>> strip_truncated_preview("Hello world this is the whole thing, really "
    ...                         "Hello world this is the whole thing, really. ...more")
    'Hello world this is the whole thing, really.'

    Short descriptions carry no teaser and pass through untouched.

    >>> strip_truncated_preview("Short and complete.")
    'Short and complete.'
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


def slug_from_product_url(url: str) -> Optional[str]:
    """Derive a stable per-book identifier from its detail URL.

    >>> slug_from_product_url("https://books.toscrape.com/catalogue/sharp-objects_997/index.html")
    'sharp-objects_997'

    The trailing number is the site's own product id, which keeps the slug
    unique even where two books share a title. It is used as the image
    filename, so a re-run overwrites the same file instead of accumulating
    copies.
    """
    parts = [part for part in urlparse(url).path.split("/") if part]
    if not parts:
        return None
    # ".../<slug>/index.html" normally; tolerate ".../<slug>.html" too.
    if parts[-1].endswith(".html") and len(parts) >= 2:
        candidate = parts[-2]
    else:
        candidate = parts[-1]
    candidate = candidate.removesuffix(".html")
    return candidate or None


def parse_listing_page(html: str, page_url: str) -> tuple[list[dict], Optional[str]]:
    """Read one catalogue page.

    Returns the per-book fields visible on the listing, plus the absolute URL of
    the next page (None on the last one). Pagination follows the site's own
    "next" link rather than counting to 50, so the crawl adapts if the
    catalogue changes size.
    """
    soup = make_soup(html)
    books: list[dict] = []

    for pod in soup.select("article.product_pod"):
        link = pod.select_one("h3 a")
        if link is None or not link.get("href"):
            # No detail URL means no UPC and no dedup key. Skip it rather than
            # emit a record that looks complete and is not.
            continue

        # Anchor text is truncated ("A Light in the ..."); the title attribute
        # carries the full string.
        title = link.get("title") or clean_text([link.get_text()])
        price, currency = parse_price(
            clean_text([node.get_text() for node in pod.select(".price_color")])
        )
        thumbnail = pod.select_one("img")

        books.append(
            {
                "title": clean_text([title]),
                "price": price,
                "currency": currency,
                "rating": parse_rating(pod.select_one("p.star-rating")),
                "availability": clean_text(
                    [node.get_text() for node in pod.select(".availability")]
                ),
                "product_url": urljoin(page_url, link["href"]),
                "thumbnail_url": (
                    urljoin(page_url, thumbnail["src"])
                    if thumbnail and thumbnail.get("src")
                    else None
                ),
            }
        )

    next_link = soup.select_one("li.next a")
    next_url = urljoin(page_url, next_link["href"]) if next_link else None
    return books, next_url


def parse_product_information(soup: BeautifulSoup) -> dict[str, Optional[str]]:
    """Read the Product Information table into ``{header: value}``.

    Keyed on the row header rather than row position, so an added or reordered
    row cannot quietly put the wrong value into UPC.
    """
    table: dict[str, Optional[str]] = {}
    for row in soup.select("table.table-striped tr"):
        header = clean_text([node.get_text() for node in row.select("th")])
        if header:
            table[header] = clean_text([node.get_text() for node in row.select("td")])
    return table


def parse_category(soup: BeautifulSoup) -> Optional[str]:
    """Return the breadcrumb category.

    The breadcrumb runs Home > Books > Category > Title and the title is not a
    link, so the category is the last anchor. The table's "Product Type" row is
    always "Books", so it is no use here.
    """
    links = [node.get_text() for node in soup.select("ul.breadcrumb li a")]
    if len(links) < 3:
        return None
    return clean_text([links[-1]])


def parse_description(soup: BeautifulSoup) -> Optional[str]:
    """Return the description paragraph, or None for the books that have none."""
    heading = soup.select_one("#product_description")
    if heading is None:
        return None
    paragraph = heading.find_next("p")
    if paragraph is None:
        return None
    return strip_truncated_preview(clean_text([paragraph.get_text()]))


def parse_detail_page(html: str, page_url: str) -> dict:
    """Read one product page into the detail half of a book record.

    Availability is re-read here because the detail page carries the stock count
    the listing omits. The selector is scoped to ``.product_main`` on purpose:
    the "you may also like" tiles below carry their own ``.availability`` nodes.
    """
    soup = make_soup(html)
    info = parse_product_information(soup)

    availability = clean_text(
        [node.get_text() for node in soup.select(".product_main p.availability")]
    )
    price_incl, currency = parse_price(info.get("Price (incl. tax)"))
    price_excl, _ = parse_price(info.get("Price (excl. tax)"))
    tax, _ = parse_price(info.get("Tax"))

    gallery_image = soup.select_one("#product_gallery img")
    reviews = info.get("Number of reviews")

    return {
        "title": clean_text(
            [node.get_text() for node in soup.select("div.product_main h1")]
        ),
        "upc": info.get("UPC"),
        "category": parse_category(soup),
        "description": parse_description(soup),
        "price": price_incl,
        "price_excl_tax": price_excl,
        "tax": tax,
        "currency": currency,
        "rating": parse_rating(soup.select_one(".product_main p.star-rating")),
        "availability": availability,
        "stock_count": parse_stock_count(availability or info.get("Availability")),
        "review_count": int(reviews) if reviews and reviews.isdigit() else None,
        "product_url": page_url,
        # Full-size cover, not the listing thumbnail.
        "image_url": (
            urljoin(page_url, gallery_image["src"])
            if gallery_image and gallery_image.get("src")
            else None
        ),
    }


def merge_records(listing: dict, detail: dict) -> dict:
    """Combine the listing and detail halves into one book record.

    The detail page wins wherever both hold a value - it is the authoritative
    one, and it is the only side with a stock count and a full-size cover. The
    listing fills the gaps and contributes the thumbnail URL.
    """
    merged = dict(listing)
    for key, value in detail.items():
        if value is not None or key not in merged:
            merged[key] = value
    return merged
