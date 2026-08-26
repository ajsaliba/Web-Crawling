"""HTML parsing for books.toscrape.com — categories, listings, product pages."""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

RATING_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
PRICE_RE = re.compile(r"[\d.]+")
STOCK_RE = re.compile(r"\((\d+) available\)")


def _soup(html):
    return BeautifulSoup(html, "html.parser")


def parse_categories(html, page_url):
    """Return [{'name', 'url'}] for every category in the sidebar."""
    categories = []
    for link in _soup(html).select("div.side_categories ul li ul li a"):
        categories.append({
            "name": link.get_text(strip=True),
            "url": urljoin(page_url, link["href"]),
        })
    return categories


def parse_listing(html, page_url):
    """Return (product_urls, next_page_url) for one category listing page."""
    soup = _soup(html)
    product_urls = [
        urljoin(page_url, a["href"])
        for a in soup.select("article.product_pod h3 a")
    ]
    next_link = soup.select_one("li.next a")
    next_url = urljoin(page_url, next_link["href"]) if next_link else None
    return product_urls, next_url


def _product_table(soup):
    """The 'Product Information' table as a {label: value} dict."""
    table = {}
    for row in soup.select("table.table-striped tr"):
        if row.th and row.td:
            table[row.th.get_text(strip=True)] = row.td.get_text(strip=True)
    return table


def _to_float(text):
    match = PRICE_RE.search(text or "")
    return float(match.group()) if match else None


def parse_product(html, page_url):
    """Extract book details, including the absolute cover image URL."""
    soup = _soup(html)
    table = _product_table(soup)

    rating_tag = soup.select_one("p.star-rating")
    rating_class = [c for c in rating_tag["class"] if c != "star-rating"] if rating_tag else []

    description_tag = soup.select_one("#product_description ~ p")

    image_tag = soup.select_one("#product_gallery img")
    image_url = urljoin(page_url, image_tag["src"]) if image_tag else None

    breadcrumbs = [li.get_text(strip=True) for li in soup.select("ul.breadcrumb li")]
    category = breadcrumbs[2] if len(breadcrumbs) > 2 else None

    availability = table.get("Availability", "")
    stock_match = STOCK_RE.search(availability)

    return {
        "title": soup.select_one("div.product_main h1").get_text(strip=True),
        "category": category,
        "upc": table.get("UPC"),
        "price_excl_tax": _to_float(table.get("Price (excl. tax)")),
        "price_incl_tax": _to_float(table.get("Price (incl. tax)")),
        "tax": _to_float(table.get("Tax")),
        "availability": availability,
        "stock_count": int(stock_match.group(1)) if stock_match else 0,
        "num_reviews": int(table.get("Number of reviews", 0) or 0),
        "rating": RATING_WORDS.get(rating_class[0]) if rating_class else None,
        "description": description_tag.get_text(strip=True) if description_tag else None,
        "product_url": page_url,
        "image_url": image_url,
    }
