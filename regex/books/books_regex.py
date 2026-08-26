r"""Book listing page fields, extracted with `re` and nothing else.

Eight patterns for the parts of an `article.product_pod` block on a
books.toscrape.com listing page:

    block       one <article class="product_pod"> ... </article>
    title       the full title, from the <h3> link's title attribute
    price       the displayed price, e.g. "£51.77"
    image       the cover thumbnail's src, exactly as the page writes it
    rating      One / Two / Three / Four / Five, from the star-rating class
    detail      the product page URL, from the <h3> link's href
    record      all four requested fields in one pass (Part 2)
    high        the same, restricted to Three stars or better (Part 3)

plus `money`, which is what the redaction in Part 3 substitutes on.

The same expressions are in `regex.txt`, in `name: regex` form. This file is
the runnable copy: each pattern is written out as a comment exactly as it
appears in the .txt, then compiled below it. The self-test fails if the three
copies ever disagree, so `regex.txt` cannot silently drift.

No BeautifulSoup, no lxml, no html.parser - and no `html.unescape` either.
Titles arrive with entities in them ("Shakespeare&#39;s Sonnets"), so
`unescape_entities` below decodes them, itself written with `re`.

Run it against a saved page:

    python books_regex.py records
    python books_regex.py high-rated listing_category.html

With no arguments it runs the bundled suite over all three saved pages.
Exit status is 0 only if every check passed.

Two things every pattern here does deliberately:

  * Attribute order is not assumed. `<img src=... class=...>` and
    `<img class=... src=...>` both match, because the class is asserted with a
    lookahead and the value is then read from anywhere inside the same tag.
    Only `rating` depends on order, and only within one class attribute, where
    the site writes "star-rating Three" as a pair.

  * Whitespace is never counted. `\s*` sits between tags that the site happens
    to write on separate lines, and every attribute is read as
    `name\s*=\s*"value"`, so both a page reflowed onto one line and one
    pretty-printed with spaces around the equals sign parse the same.

    Single-quoted attributes are the one formatting variant deliberately not
    supported. Doing it properly needs a backreference to the opening quote -
    `(["'])(.*?)\1` - and Python's `re` forbids reusing a group name inside one
    pattern, so the composed `record` would need four separately named quote
    groups to gain nothing: this site, and almost every generated page, quotes
    with `"`.
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGES = ("listing_home.html", "listing_category.html", "listing_page2.html")
DEFAULT_PAGE = HERE / PAGES[0]

HIGH_RATINGS = ("Three", "Four", "Five")
ALL_RATINGS = ("One", "Two") + HIGH_RATINGS

# --- block ------------------------------------------------------------
#
# One product pod. Used to cut the page into 20 independent blocks before
# reading fields out of each, which is the safe way round: a field pattern
# that runs off the end of its block can only reach text that is not there.
#
# The class is matched as a word inside the attribute rather than as the whole
# attribute, so an extra class ("product_pod featured") still matches.
#
# block: <article\b[^>]*\bclass\s*=\s*"[^"]*\bproduct_pod\b[^"]*"[^>]*>(?P<block>.*?)</article>

BLOCK_RE = re.compile(
    r'<article\b[^>]*\bclass\s*=\s*"[^"]*\bproduct_pod\b[^"]*"[^>]*>'
    r"(?P<block>.*?)</article>",
    re.S,
)

# --- title ------------------------------------------------------------
#
# The anchor text is truncated on the page ("A Light in the ..."); the title
# attribute carries the whole string, so that is what is read. `[^"]*` stops
# at the closing quote, which is the only thing that can end an attribute
# value, so a title containing < or > is safe.
#
# title: <h3\b[^>]*>\s*<a\b[^>]*\btitle\s*=\s*"(?P<title>[^"]*)"

TITLE_RE = re.compile(
    r'<h3\b[^>]*>\s*<a\b[^>]*\btitle\s*=\s*"(?P<title>[^"]*)"',
    re.S,
)

# --- price ------------------------------------------------------------
#
# The lookahead asserts "this <p> carries the price_color class" without
# consuming anything, so the class may sit before or after any other
# attribute. `[^<]*?` then takes the text up to the closing tag - non-greedy
# and unable to cross a tag boundary, so it cannot swallow the next element.
#
# The \s* on both sides is what makes it survive reformatting: the site emits
# the price tight against its tags today, but a pretty-printer would not.
#
# price: <p\b(?=[^>]*\bclass\s*=\s*"[^"]*\bprice_color\b)[^>]*>\s*(?P<price>[^<]*?)\s*</p>

PRICE_RE = re.compile(
    r'<p\b(?=[^>]*\bclass\s*=\s*"[^"]*\bprice_color\b)[^>]*>\s*(?P<price>[^<]*?)\s*</p>',
    re.S,
)

# --- image ------------------------------------------------------------
#
# Same lookahead trick, on the thumbnail class. The src is returned exactly as
# written - "media/cache/..." on the home page, "../../../media/cache/..." on
# a category page - because resolving it needs the page URL, which a regex
# over the HTML does not have. `absolute_image_urls` does that separately.
#
# image: <img\b(?=[^>]*\bclass\s*=\s*"[^"]*\bthumbnail\b)[^>]*\bsrc\s*=\s*"(?P<image_url>[^"]+)"

IMAGE_RE = re.compile(
    r'<img\b(?=[^>]*\bclass\s*=\s*"[^"]*\bthumbnail\b)[^>]*\bsrc\s*=\s*"(?P<image_url>[^"]+)"',
    re.S,
)

# --- rating -----------------------------------------------------------
#
# The rating is a class name, not text: <p class="star-rating Three">. The
# five stars below it are identical <i> elements, so counting them tells you
# nothing - only the class does.
#
# The word must follow "star-rating" in the same attribute, which is the one
# ordering assumption in this file, and it is the site's own convention for
# paired classes. `\s+` rather than a single space, and `[^"]*` after, so
# extra or reordered classes around the pair still match.
#
# rating: <p\b[^>]*\bclass\s*=\s*"[^"]*\bstar-rating\s+(?P<rating>One|Two|Three|Four|Five)\b[^"]*"

RATING_RE = re.compile(
    r'<p\b[^>]*\bclass\s*=\s*"[^"]*\bstar-rating\s+(?P<rating>One|Two|Three|Four|Five)\b[^"]*"',
    re.S,
)

# --- detail -----------------------------------------------------------
#
# The product URL. Each pod holds this href twice - once on the cover image,
# once on the title - so anchoring on <h3> is what keeps the count at 20
# instead of 40.
#
# detail: <h3\b[^>]*>\s*<a\b[^>]*\bhref\s*=\s*"(?P<detail_url>[^"]+)"

DETAIL_RE = re.compile(
    r'<h3\b[^>]*>\s*<a\b[^>]*\bhref\s*=\s*"(?P<detail_url>[^"]+)"',
    re.S,
)

# --- the gap between fields -------------------------------------------
#
# A "tempered dot": any character, as long as we are not standing at the start
# of </article>. This is the whole trick behind `record` and `high`.
#
# Plain `.*?` is not enough. It is non-greedy, so it looks like it stops at the
# first match - but if a field is missing from this block, or a value is
# constrained (as the rating is in `high`), backtracking lets it run on into
# the *next* block to find one. The match then straddles two books and pairs
# one book's title with another's cover.
#
# That is not hypothetical: on the saved home page, the naive version of
# `high` pairs "Sharp Objects" with the previous book's image, and 3 of its 11
# records are wrong. The self-test asserts this, so the reason for the
# temper stays visible.

GAP = r"(?:(?!</article>).)*?"

# --- record -----------------------------------------------------------
#
# Part 2: title, price, stars and image in one pass. The fields are listed in
# the order the page writes them - image, rating, title, price - and reordered
# into the requested tuple by `records()`.
#
# href is deliberately not captured here. Requiring href before title would
# assume attribute order for no benefit, and the requested tuple does not
# include the detail URL. It has its own pattern above.
#
# record: <article\b[^>]*\bclass\s*=\s*"[^"]*\bproduct_pod\b[^"]*"[^>]*>(?:(?!</article>).)*?<img\b(?=[^>]*\bclass\s*=\s*"[^"]*\bthumbnail\b)[^>]*\bsrc\s*=\s*"(?P<image_url>[^"]+)"(?:(?!</article>).)*?<p\b[^>]*\bclass\s*=\s*"[^"]*\bstar-rating\s+(?P<rating>One|Two|Three|Four|Five)\b[^"]*"(?:(?!</article>).)*?<h3\b[^>]*>\s*<a\b[^>]*\btitle\s*=\s*"(?P<title>[^"]*)"(?:(?!</article>).)*?<p\b(?=[^>]*\bclass\s*=\s*"[^"]*\bprice_color\b)[^>]*>\s*(?P<price>[^<]*?)\s*</p>

RECORD_RE = re.compile(
    r'<article\b[^>]*\bclass\s*=\s*"[^"]*\bproduct_pod\b[^"]*"[^>]*>'
    + GAP + r'<img\b(?=[^>]*\bclass\s*=\s*"[^"]*\bthumbnail\b)[^>]*\bsrc\s*=\s*"(?P<image_url>[^"]+)"'
    + GAP + r'<p\b[^>]*\bclass\s*=\s*"[^"]*\bstar-rating\s+(?P<rating>One|Two|Three|Four|Five)\b[^"]*"'
    + GAP + r'<h3\b[^>]*>\s*<a\b[^>]*\btitle\s*=\s*"(?P<title>[^"]*)"'
    + GAP + r'<p\b(?=[^>]*\bclass\s*=\s*"[^"]*\bprice_color\b)[^>]*>\s*(?P<price>[^<]*?)\s*</p>',
    re.S,
)

# --- high -------------------------------------------------------------
#
# Part 3, task 8: the same record, with the rating alternation narrowed to the
# three ratings that count as high. The filtering happens inside the pattern,
# so a One-star block simply fails to match rather than being matched and then
# discarded.
#
# high: <article\b[^>]*\bclass\s*=\s*"[^"]*\bproduct_pod\b[^"]*"[^>]*>(?:(?!</article>).)*?<img\b(?=[^>]*\bclass\s*=\s*"[^"]*\bthumbnail\b)[^>]*\bsrc\s*=\s*"(?P<image_url>[^"]+)"(?:(?!</article>).)*?<p\b[^>]*\bclass\s*=\s*"[^"]*\bstar-rating\s+(?P<rating>Three|Four|Five)\b[^"]*"(?:(?!</article>).)*?<h3\b[^>]*>\s*<a\b[^>]*\btitle\s*=\s*"(?P<title>[^"]*)"(?:(?!</article>).)*?<p\b(?=[^>]*\bclass\s*=\s*"[^"]*\bprice_color\b)[^>]*>\s*(?P<price>[^<]*?)\s*</p>

HIGH_RE = re.compile(
    r'<article\b[^>]*\bclass\s*=\s*"[^"]*\bproduct_pod\b[^"]*"[^>]*>'
    + GAP + r'<img\b(?=[^>]*\bclass\s*=\s*"[^"]*\bthumbnail\b)[^>]*\bsrc\s*=\s*"(?P<image_url>[^"]+)"'
    + GAP + r'<p\b[^>]*\bclass\s*=\s*"[^"]*\bstar-rating\s+(?P<rating>Three|Four|Five)\b[^"]*"'
    + GAP + r'<h3\b[^>]*>\s*<a\b[^>]*\btitle\s*=\s*"(?P<title>[^"]*)"'
    + GAP + r'<p\b(?=[^>]*\bclass\s*=\s*"[^"]*\bprice_color\b)[^>]*>\s*(?P<price>[^<]*?)\s*</p>',
    re.S,
)

# --- money ------------------------------------------------------------
#
# Part 3, task 7: what redaction replaces. The optional "Â" catches the
# mojibake you get when a UTF-8 page is read as cp1252 - "Â£51.77" - so a
# mis-decoded page still redacts cleanly instead of leaving the price behind.
#
# Both , and . are accepted as the decimal mark, and the decimals are optional,
# so "£52" and "£1,50" redact too.
#
# money: Â?£\s*\d+(?:[.,]\d{1,2})?

MONEY_RE = re.compile(r"Â?£\s*\d+(?:[.,]\d{1,2})?")

REDACTION = "[REDACTED]"

PATTERNS = {
    "block": BLOCK_RE,
    "title": TITLE_RE,
    "price": PRICE_RE,
    "image": IMAGE_RE,
    "rating": RATING_RE,
    "detail": DETAIL_RE,
    "record": RECORD_RE,
    "high": HIGH_RE,
    "money": MONEY_RE,
}


# --- entity decoding, also with re ------------------------------------
#
# Titles carry entities: "Shakespeare&#39;s Sonnets". `html.unescape` would do
# this, but it lives in the HTML package the brief rules out, so here it is in
# 30 characters of regex and a lookup table. Only the entities the site
# actually emits are named; anything unrecognised is left exactly as it was
# rather than being guessed at or dropped.

_ENTITY_RE = re.compile(
    r"&(?:#x(?P<hex>[0-9a-fA-F]+)|#(?P<dec>\d+)|(?P<name>[A-Za-z][A-Za-z0-9]*));"
)

_NAMED_ENTITIES = {
    "amp": "&",
    "lt": "<",
    "gt": ">",
    "quot": '"',
    "apos": "'",
    "nbsp": " ",
}


def unescape_entities(text):
    """Decode the HTML entities that appear in listing-page attributes.

    >>> unescape_entities("Shakespeare&#39;s Sonnets")
    "Shakespeare's Sonnets"
    >>> unescape_entities("Tea &amp; Sympathy")
    'Tea & Sympathy'
    >>> unescape_entities("&unknownentity; stays")
    '&unknownentity; stays'
    """

    def replace(match):
        if match["hex"]:
            return chr(int(match["hex"], 16))
        if match["dec"]:
            return chr(int(match["dec"]))
        return _NAMED_ENTITIES.get(match["name"], match.group(0))

    return _ENTITY_RE.sub(replace, text)


# --- Part 1: one field at a time --------------------------------------


def blocks(html):
    """Return the inner HTML of every product pod on the page."""
    return [m["block"] for m in BLOCK_RE.finditer(html)]


def titles(html, decode=True):
    """Task 1. Every book title, in page order.

    `decode=False` returns them exactly as the attribute holds them, entities
    and all, which is what you want if you are diffing against the raw HTML.
    """
    found = [m["title"] for m in TITLE_RE.finditer(html)]
    return [unescape_entities(t) for t in found] if decode else found


def prices(html):
    """Task 2. Every displayed price, currency symbol included."""
    return [m["price"] for m in PRICE_RE.finditer(html)]


def image_urls(html):
    """Task 3. Every cover image src, exactly as the page writes it."""
    return [m["image_url"] for m in IMAGE_RE.finditer(html)]


def ratings(html):
    """Task 4. Every star rating, as the word the class carries."""
    return [m["rating"] for m in RATING_RE.finditer(html)]


def detail_urls(html):
    """Task 5. Every product page URL, one per book."""
    return [m["detail_url"] for m in DETAIL_RE.finditer(html)]


# --- Part 2: all four at once -----------------------------------------


def records(html, decode=True):
    """Task 6. (title, price, stars, image_url) per book, in page order.

    One pass over the page, one match per book, fields reordered from the
    order the page writes them into the order the brief asks for.
    """
    return [
        (
            unescape_entities(m["title"]) if decode else m["title"],
            m["price"],
            m["rating"],
            m["image_url"],
        )
        for m in RECORD_RE.finditer(html)
    ]


# --- Part 3: redaction and filtering ----------------------------------


def redact_prices(html):
    """Task 7. Replace every £xx.xx in the HTML with [REDACTED].

    Returns the whole document, not just the prices, so the result is still a
    page. Idempotent: running it twice changes nothing the second time,
    because [REDACTED] contains no price to find.
    """
    return MONEY_RE.sub(REDACTION, html)


def high_rated(html, decode=True):
    """Task 8. Only the books rated Three stars or better.

    The rating alternation inside HIGH_RE does the filtering, so a low-rated
    block never becomes a match in the first place.
    """
    return [
        (
            unescape_entities(m["title"]) if decode else m["title"],
            m["price"],
            m["rating"],
            m["image_url"],
        )
        for m in HIGH_RE.finditer(html)
    ]


# --- a convenience the brief does not ask for -------------------------


def absolute_image_urls(html, page_url):
    """Resolve the relative srcs against the URL the page was fetched from.

    Kept separate from `image_urls` because it needs something the HTML does
    not contain. Written with `re` rather than urljoin so the module keeps its
    one-import promise; it handles only the `../` and bare-relative forms the
    site actually emits.
    """
    base = re.sub(r"[^/]*$", "", page_url)
    out = []
    for src in image_urls(html):
        path, ups = src, 0
        while path.startswith("../"):
            path, ups = path[3:], ups + 1
        root = base
        for _ in range(ups):
            root = re.sub(r"[^/]+/$", "", root)
        out.append(root + path)
    return out


# --- the self-test ----------------------------------------------------

FIRST_TWO_HOME = [
    ("A Light in the Attic", "£51.77", "Three",
     "media/cache/2c/da/2cdad67c44b002e7ead0cc35693c0e8b.jpg"),
    ("Tipping the Velvet", "£53.74", "One",
     "media/cache/26/0c/260c6ae16bce31c8f8c95daddd9f4a1c.jpg"),
]

BOOKS_PER_PAGE = 20

failures = []


def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" - {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def _pattern_comments():
    """Read the `# name: regex` comments out of this file's own source."""
    source = Path(__file__).read_text(encoding="utf-8")
    return dict(re.findall(r"^# (\w+): (.+)$", source, re.M))


def check_sources():
    """The compiled patterns, their comments and regex.txt must agree."""
    comments = _pattern_comments()
    txt = dict(
        re.findall(r"^(\w+): (.+)$", (HERE / "regex.txt").read_text(encoding="utf-8"), re.M)
    )
    for name, compiled in PATTERNS.items():
        check(f"{name}: comment matches the compiled pattern",
              comments.get(name) == compiled.pattern)
        check(f"{name}: regex.txt matches the compiled pattern",
              txt.get(name) == compiled.pattern)
    check("regex.txt lists every pattern and no others",
          set(txt) == set(PATTERNS), f"txt={sorted(txt)}")


def mangle_whitespace(html):
    """Reflow the HTML the way a formatter might, without changing meaning."""
    out = re.sub(r">\s+<", "><", html)                    # collapse between tags
    out = re.sub(r"<(\w+)\s+", r"<\1   ", out)            # widen the gap after a tag name
    out = re.sub(r'(\w)="', r'\1 = "', out)               # spaces around attribute =
    return out


def reorder_img_attributes(html):
    """Move class in front of src, to prove nothing depends on order."""
    return re.sub(
        r'<img src="([^"]+)" alt="([^"]*)" class="thumbnail">',
        r'<img class="thumbnail" alt="\2" src="\1">',
        html,
    )


def naive_high_pattern():
    """HIGH_RE with a plain .*? in place of the tempered gap."""
    return re.compile(HIGH_RE.pattern.replace(GAP, ".*?"), re.S)


def self_test():
    print(f"{len(PATTERNS)} patterns over {len(PAGES)} saved listing pages\n")

    print("Sources agree")
    check_sources()

    pages = {}
    for name in PAGES:
        path = HERE / name
        if not path.exists():
            check(f"{name} is present", False, "fixture missing")
            continue
        pages[name] = path.read_text(encoding="utf-8")

    for name, html in pages.items():
        print(f"\n{name}")
        field_counts = {
            "titles": titles(html),
            "prices": prices(html),
            "images": image_urls(html),
            "ratings": ratings(html),
            "detail URLs": detail_urls(html),
        }
        for label, values in field_counts.items():
            check(f"{label}: {BOOKS_PER_PAGE} found",
                  len(values) == BOOKS_PER_PAGE, f"got {len(values)}")

        check(f"blocks: {BOOKS_PER_PAGE} product pods",
              len(blocks(html)) == BOOKS_PER_PAGE, f"got {len(blocks(html))}")

        # The composed pattern and the one-field-at-a-time patterns are two
        # independent routes to the same answer. If they disagree, one of them
        # is straddling a block boundary.
        composed = records(html)
        check("record: one per book", len(composed) == BOOKS_PER_PAGE, f"got {len(composed)}")
        check("record agrees with the single-field patterns",
              [r[0] for r in composed] == titles(html)
              and [r[1] for r in composed] == prices(html)
              and [r[2] for r in composed] == ratings(html)
              and [r[3] for r in composed] == image_urls(html))

        # A third route: split into blocks first, then read one field from each.
        per_block = [
            (
                unescape_entities(TITLE_RE.search(b)["title"]),
                PRICE_RE.search(b)["price"],
                RATING_RE.search(b)["rating"],
                IMAGE_RE.search(b)["image_url"],
            )
            for b in blocks(html)
        ]
        check("record agrees with block-by-block extraction", per_block == composed)

        check("every rating is one of the five words",
              set(ratings(html)) <= set(ALL_RATINGS), f"saw {sorted(set(ratings(html)))}")
        check("every price carries the currency symbol",
              all(p.startswith("£") for p in prices(html)))
        check("every detail URL ends in .html",
              all(u.endswith(".html") for u in detail_urls(html)))
        check("no title still holds an entity",
              not any("&" in t and ";" in t for t in titles(html)))

        # Part 3, task 8
        high = high_rated(html)
        expected_high = [r for r in composed if r[2] in HIGH_RATINGS]
        check("high-rated matches filtering the full record list",
              high == expected_high, f"{len(high)} of {len(composed)}")
        check("high-rated contains no low ratings",
              all(r[2] in HIGH_RATINGS for r in high))

        # The reason GAP exists.
        naive = [
            (unescape_entities(m["title"]), m["price"], m["rating"], m["image_url"])
            for m in naive_high_pattern().finditer(html)
        ]
        wrong = sum(1 for a, b in zip(naive, expected_high) if a != b)
        check("tempered gap fixes what a plain .*? gets wrong",
              high == expected_high and wrong > 0,
              f"naive .*? mis-pairs {wrong} of {len(expected_high)} records")

        # Part 3, task 7
        redacted = redact_prices(html)
        check("redaction leaves no price behind", "£" not in redacted)
        check(f"redaction wrote {BOOKS_PER_PAGE} markers",
              redacted.count(REDACTION) == BOOKS_PER_PAGE,
              f"got {redacted.count(REDACTION)}")
        check("redaction changed nothing but the prices",
              MONEY_RE.sub("", html) == redacted.replace(REDACTION, ""))
        check("redaction is idempotent", redact_prices(redacted) == redacted)
        check("redaction leaves the titles readable",
              titles(redacted) == titles(html))

        # Robustness the brief asks for explicitly.
        reflowed = mangle_whitespace(html)
        check("survives reflowed whitespace",
              records(reflowed) == composed and detail_urls(reflowed) == detail_urls(html))
        reordered = reorder_img_attributes(html)
        check("survives reordered img attributes", records(reordered) == composed)

    if "listing_home.html" in pages:
        print("\nKnown values")
        home = pages["listing_home.html"]
        check("first two records are the expected tuples",
              records(home)[:2] == FIRST_TWO_HOME, f"got {records(home)[:2]}")
        check("mojibake prices redact too",
              redact_prices("Â£51.77") == REDACTION)
        check("entity decoding", unescape_entities("Shakespeare&#39;s Sonnets")
              == "Shakespeare's Sonnets")
        check("relative srcs resolve against the page URL",
              absolute_image_urls(home, "https://books.toscrape.com/")[0]
              == "https://books.toscrape.com/media/cache/2c/da/"
                 "2cdad67c44b002e7ead0cc35693c0e8b.jpg")

    if "listing_category.html" in pages:
        cat = pages["listing_category.html"]
        check("a category page's ../../../ srcs resolve too",
              absolute_image_urls(
                  cat, "https://books.toscrape.com/catalogue/category/books_1/index.html")[0]
              == "https://books.toscrape.com/media/cache/2c/da/"
                 "2cdad67c44b002e7ead0cc35693c0e8b.jpg")
        check("the same records come off a category page",
              [r[:3] for r in records(cat)] == [r[:3] for r in records(pages["listing_home.html"])])

    print("\n" + "=" * 62)
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Every pattern extracted what it should, on every saved page.")
    return 0


# --- CLI --------------------------------------------------------------

OUTPUT_DIR = HERE / "output"


def format_tuples(rows):
    """Render tuples in the shape the brief's Output block shows.

    Double quotes and no trailing comma, which `repr` gives neither of. Any
    quote inside a value is escaped, so the block stays readable if a title
    ever contains one.
    """
    lines = ["["]
    for i, row in enumerate(rows):
        fields = ", ".join('"' + f.replace('"', '\\"') + '"' for f in row)
        comma = "," if i < len(rows) - 1 else ""
        lines.append(f"  ({fields}){comma}")
    lines.append("]")
    return "\n".join(lines) + "\n"


def write_outputs():
    """Run all eight tasks over every saved page and write the results.

    One directory per page under output/, so the three prefix variants stay
    distinguishable. Committed alongside the code, so the answers can be read
    without running anything.
    """
    written = []
    for page in PAGES:
        html = (HERE / page).read_text(encoding="utf-8")
        target = OUTPUT_DIR / page.removesuffix(".html")
        target.mkdir(parents=True, exist_ok=True)

        files = {
            "titles.txt": "\n".join(titles(html)) + "\n",
            "prices.txt": "\n".join(prices(html)) + "\n",
            "image_urls.txt": "\n".join(image_urls(html)) + "\n",
            "ratings.txt": "\n".join(ratings(html)) + "\n",
            "detail_urls.txt": "\n".join(detail_urls(html)) + "\n",
            "records.txt": format_tuples(records(html)),
            "high_rated.txt": format_tuples(high_rated(html)),
            "redacted.html": redact_prices(html),
        }
        for name, body in files.items():
            (target / name).write_text(body, encoding="utf-8", newline="\n")
            written.append(target / name)
    return written


TASKS = {
    "titles": ("1", lambda h: titles(h)),
    "prices": ("2", lambda h: prices(h)),
    "images": ("3", lambda h: image_urls(h)),
    "ratings": ("4", lambda h: ratings(h)),
    "urls": ("5", lambda h: detail_urls(h)),
    "records": ("6", lambda h: records(h)),
    "redact": ("7", lambda h: redact_prices(h)),
    "high-rated": ("8", lambda h: high_rated(h)),
}

USAGE = f"""usage: python books_regex.py [<task>] [<page.html>]

  tasks: {', '.join(TASKS)}
  page:  defaults to {PAGES[0]}

  emit          run every task over every saved page into output/
  (no task)     run the self-test over all saved pages"""


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    if not argv or argv[0] == "--self-test":
        return self_test()

    if argv[0] == "emit":
        for path in write_outputs():
            print(path.relative_to(HERE))
        return 0

    task = argv[0]
    if task not in TASKS:
        print(f"unknown task {task!r}\n\n{USAGE}", file=sys.stderr)
        return 2

    page = HERE / argv[1] if len(argv) > 1 else DEFAULT_PAGE
    if not page.exists():
        print(f"no such page: {page}", file=sys.stderr)
        return 2

    part, run = TASKS[task]
    result = run(page.read_text(encoding="utf-8"))

    if task == "redact":
        # The whole document is the answer; show the lines that changed.
        for line in result.splitlines():
            if REDACTION in line:
                print(line.strip())
        return 0

    if task in ("records", "high-rated"):
        print("[")
        for row in result:
            print(f"  {row!r},")
        print("]")
        return 0

    for value in result:
        print(value)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
