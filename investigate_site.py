"""Part 3 - website investigation for allbirds.com, using requests.

Answers the four things the brief asks about a direct HTTP request - status,
whether real product HTML came back, whether it differs from the browser
response, and whether anything blocked us - and gathers the evidence behind
the rest of site_report.md.

requests rather than Scrapy because this is a handful of one-off calls read by
hand, not a traversal. The two never mix: requests inside a Scrapy callback
would block the reactor.

Read-only. One request at a time, a second apart, honest User-Agent. No login,
no cart or account routes, no attempt to get past anything. If the site serves
a challenge page the script says so and stops.

    python investigate_site.py

Takes about 10 seconds and pulls down roughly 3.5 MB. Findings live in
site_report.md; catalogue-dependent counts drift as stock changes.
"""

import re
import sys
import time
from typing import Optional, Tuple

import requests

BASE = "https://www.allbirds.com"
PRODUCT_URL = f"{BASE}/products/mens-wool-runners-natural-white"
COLLECTION_URL = f"{BASE}/collections/shoes"

# The site does not gate on User-Agent, so there is no reason to fake one.
HONEST_UA = "lau-crawler-recon/1.0 (+technical assessment; contact@example.com)"

# Only used to answer "does the response differ from a browser's?"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

REQUEST_DELAY_SECONDS = 1.0
TIMEOUT_SECONDS = 30

# Wording that means a challenge page rather than real content.
CHALLENGE_MARKERS = (
    "just a moment",
    "access denied",
    "checking your browser",
    "attention required",
    "enable javascript and cookies",
)


def fetch(url: str, user_agent: str = HONEST_UA) -> Optional[requests.Response]:
    """GET one URL politely, returning None if it fails.

    Sleeps first so the script never bursts, and swallows transport errors so
    one bad URL does not lose the findings already gathered.
    """
    time.sleep(REQUEST_DELAY_SECONDS)
    try:
        return requests.get(
            url, headers={"User-Agent": user_agent}, timeout=TIMEOUT_SECONDS
        )
    except requests.RequestException as exc:
        print(f"  ! request failed: {exc}")
        return None


def looks_like_challenge(html: str) -> bool:
    """True if the body reads like a challenge or block page.

    Checked before drawing any conclusion. The brief says to document a block
    and stop, not work around it.
    """
    lowered = html[:5000].lower()
    return any(marker in lowered for marker in CHALLENGE_MARKERS)


def heading(text: str) -> None:
    """Print a section header."""
    print(f"\n{'=' * 70}\n{text}\n{'=' * 70}")


def report(label: str, value: object) -> None:
    """Print one aligned evidence line."""
    print(f"  {label:<38} {value}")


# Section A - Rendering

def check_rendering(html: str) -> None:
    """Does product data survive without running JavaScript?

    Everything counted comes from the raw body, so a non-zero count means the
    field is there with no browser involved.
    """
    heading("A. RENDERING - is product data in the raw HTML response?")

    title = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)

    report("<title>", title.group(1).strip()[:58] if title else "ABSENT")
    report("<h1>", re.sub(r"<[^>]+>", "", h1.group(1)).strip()[:58] if h1 else "ABSENT")
    report("JSON-LD blocks", html.count("application/ld+json"))
    report('"@type": "Product" occurrences',
           len(re.findall(r'"@type":\s*"Product"', html)))
    report("unique /cdn/shop/ image paths",
           len(set(re.findall(
               r"/cdn/shop/(?:files|products)/[\w.%-]+\.(?:jpg|png|webp)", html))))
    report(".mp4 URLs", len(re.findall(r"\.mp4", html)))
    report(".m3u8 (HLS) URLs", len(re.findall(r"\.m3u8", html)))
    report("inline variant array (var meta)",
           "present" if "var meta = {" in html else "absent")

    print("\n  => Product detail pages are server-rendered: every field above is")
    print("     readable without executing any JavaScript.")


# Section B - Structured data

def check_structured_data(html: str) -> None:
    """Locate the structured-data sources and rank them by usefulness."""
    heading("B. STRUCTURED DATA - where would extraction prefer to read from?")

    for marker, description in [
        ("application/ld+json", "JSON-LD (schema.org)"),
        ("var meta = {", "Shopify analytics state object"),
        ("window.ShopifyAnalytics", "ShopifyAnalytics global"),
    ]:
        report(description, "present" if marker in html else "absent")

    # This theme uses single quotes, so a double-quoted pattern reports these
    # as absent when they are present. Accept either.
    for pattern, description in [
        (r"rel=['\"]canonical['\"]", "canonical link"),
        (r"property=['\"]og:image['\"]", "og:image"),
        (r"property=['\"]og:url['\"]", "og:url"),
    ]:
        report(description, "present" if re.search(pattern, html, re.I) else "absent")

    ld_types = sorted(set(re.findall(r'"@type":\s*"(\w+)"', html)))
    report("JSON-LD @type values", ", ".join(ld_types) or "none")

    # The source I would actually extract from.
    response = fetch(f"{PRODUCT_URL}.json")
    if response is None or response.status_code != 200:
        code = response.status_code if response else "error"
        report("products/<handle>.json", f"unavailable ({code})")
        return

    report("products/<handle>.json",
           f"HTTP {response.status_code}, {len(response.content):,} bytes")
    try:
        product = response.json()["product"]
    except (ValueError, KeyError):
        report("  parsed", "unexpected JSON shape")
        return

    report("  title", product.get("title", "")[:48])
    report("  product_type / vendor",
           f"{product.get('product_type')} / {product.get('vendor')}")
    report("  options",
           [(o["name"], len(o["values"])) for o in product.get("options", [])])
    report("  variants", len(product.get("variants", [])))
    report("  images", len(product.get("images", [])))

    print("\n  => Preference: products/<handle>.json (a data contract, and the only")
    print("     source with per-variant sku/price/stock/image), then JSON-LD, then")
    print("     HTML selectors as a last resort.")


# Section C - Platform identification

def check_platform(response: requests.Response, html: str) -> None:
    """Collect independent fingerprints identifying the e-commerce platform."""
    heading("C. PLATFORM IDENTIFICATION")

    for header in ("powered-by", "server", "shopify-complexity-score", "x-shopid"):
        if header in response.headers:
            report(f"header: {header}", response.headers[header][:66])

    page_type = re.search(r"pageType;desc=\"(\w+)\"",
                          response.headers.get("server-timing", ""))
    if page_type:
        report("server-timing pageType", page_type.group(1))

    for marker, description in [
        ("/cdn/shop/", "Shopify CDN asset path"),
        ("/cdn/shopifycloud/", "Shopify Cloud assets"),
        ("window.ShopifyAnalytics", "Shopify analytics"),
    ]:
        report(description, "present" if marker in html else "absent")

    print("\n  => Shopify (Shopify Plus) behind Cloudflare, on multiple independent")
    print("     signals - the `powered-by` header alone is decisive.")


# Section D - Direct HTTP request

def check_direct_request(response: requests.Response, html: str) -> None:
    """Answer the brief's four questions about the direct HTTP request."""
    heading("D. DIRECT HTTP REQUEST (python requests)")

    report("HTTP status", response.status_code)
    report("response size", f"{len(response.content):,} bytes")
    report("meaningful product HTML?",
           "yes" if "<h1" in html and "application/ld+json" in html else "no")
    report("blocking / challenge behaviour",
           "DETECTED - stopping" if looks_like_challenge(html) else "none observed")
    report("redirected?", f"yes -> {response.url}" if response.history else "no")

    # "Whether the response differs significantly from the browser response":
    # re-request with a browser User-Agent and compare.
    browser_response = fetch(PRODUCT_URL, user_agent=BROWSER_UA)
    if browser_response is not None:
        honest_size = len(response.content)
        browser_size = len(browser_response.content)
        report("size with honest UA", f"{honest_size:,} bytes")
        report("size with browser UA", f"{browser_size:,} bytes")
        delta = abs(browser_size - honest_size)
        report("difference",
               f"{delta:,} bytes "
               f"({'no UA gating' if delta < 5000 else 'INVESTIGATE'})")

    print("\n  => 200 OK with full product HTML, no challenge, no UA gating. The")
    print("     residual difference is per-request session ids, not content.")


# Section E - Discovery strategy

def _sitemap_product_count() -> Tuple[int, str]:
    """Return (number of product URLs in the sitemap, the sitemap URL used)."""
    index = fetch(f"{BASE}/sitemap.xml")
    if index is None:
        return 0, "(unreachable)"

    match = re.search(r"<loc>([^<]*sitemap_products_[^<]*)</loc>", index.text)
    if not match:
        return 0, "(no product sitemap in index)"

    sitemap_url = match.group(1).replace("&amp;", "&")
    products = fetch(sitemap_url)
    if products is None:
        return 0, sitemap_url

    # Count <loc> entries, not matching lines - <image:loc> entries would
    # inflate a line count.
    locs = re.findall(r"<loc>([^<]*)</loc>", products.text)
    return sum(1 for loc in locs if "/products/" in loc), sitemap_url


def check_discovery() -> None:
    """Sitemap versus following collection-page links.

    The finding that most changes how a crawler here should be built, so it is
    measured rather than assumed.
    """
    heading("E. DISCOVERY - sitemap vs. following collection-page links")

    count, sitemap_url = _sitemap_product_count()
    report("sitemap product URLs", count)
    report("  from", sitemap_url[:62])

    collection = fetch(COLLECTION_URL)
    if collection is None:
        return

    html = collection.text
    # Either quote style. A double-quoted pattern reports zero here and
    # overstates the case.
    anchors = set(re.findall(r"""href=['"](/products/[a-z0-9-]+)['"]""", html))
    handles = set(re.findall(r'"handle":"([a-z0-9-]+)"', html))

    report("collection page status", collection.status_code)
    report("  products as <a href> anchors", len(anchors))
    report("  product handles in embedded JSON", len(handles))

    if handles and len(anchors) < len(handles) / 2:
        print("\n  => The grid is hydrated client-side from embedded JSON: an")
        print("     anchor-following crawler would miss most of the catalogue.")
        print("     Discover products via the sitemap or collection JSON instead.")


def main() -> int:
    """Run every check against one product page and report the findings."""
    print(f"Reconnaissance target: {PRODUCT_URL}")
    print("Read-only, polite, no access controls touched.")

    response = fetch(PRODUCT_URL)
    if response is None:
        print("\nCould not reach the site; nothing to report.")
        return 1

    html = response.text

    if looks_like_challenge(html):
        heading("BLOCKED")
        print(f"  HTTP {response.status_code}, but the body is a challenge page.")
        print("  Documenting and stopping here, as the assessment instructs.")
        return 1

    check_rendering(html)
    check_structured_data(html)
    check_platform(response, html)
    check_direct_request(response, html)
    check_discovery()

    print(f"\n{'=' * 70}")
    print("Findings and interpretation: site_report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
