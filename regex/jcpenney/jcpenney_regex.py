"""JCPenney URL regular expressions.

Six patterns for the URL classes in `links.txt`. Five are page types; the
sixth, `titles`, is a second reading of two of them:

    catalog   category / brand listing pages          www.jcpenney.com/g/...
    search    keyword search result pages             www.jcpenney.com/s?searchTerm=...
    product   product detail pages                    www.jcpenney.com/p/.../pprNNNN
    titles    the display title a /g/ or /p/ URL carries (capturing pattern)
    images    product images                          sc-images.jcpenney.com/JCPenney/...
    videos    product videos                          sc-videos.jcpenney.com/JCPenney/...

The same six expressions are in `regex.txt`, in the requested `name: regex`
form. This file is the runnable copy: each pattern is written out as a comment
exactly as it appears in the .txt, then compiled below it.

Run it to test a URL against a type:

    python jcpenney_regex.py catalog "https://www.jcpenney.com/g/shoes?id=dept20000018"
    PASS  catalog https://www.jcpenney.com/g/shoes?id=dept20000018
            catalog_id = dept20000018
            slug = shoes
            title = Shoes

Several cases at once, as <type> <url> pairs, or one "type url" per line on
stdin with `-`. A seventh type, `any`, answers "which patterns match this?"
rather than testing one. With no arguments it runs the bundled suite over
every URL in `links.txt`. Exit status is 0 only if every case passed.

Notes that apply to all six:

  * `https?` and an optional `www.` are accepted - the same page is reachable
    either way, and a crawler frontier normalises late.
  * `&amp;` is accepted wherever `&` is, because these URLs are read out of
    HTML attributes where the ampersand arrives escaped. Four of the sample
    URLs are in that escaped form.
  * Every pattern is anchored at both ends, so a longer URL that merely
    starts like a catalog page is not mistaken for one.
  * Groups are named, so a caller reads `m["brand"]` rather than `m[2]`.
"""

import re
import sys
from pathlib import Path
from urllib.parse import unquote_plus

# --- catalog ----------------------------------------------------------
#
# A listing page: /g/ then one or more slug segments, then a query that must
# carry id=cat<digits> or id=dept<digits>. That id is what makes it a catalog
# page - the path alone is not enough. `brand=` and any other parameter may
# appear before or after it, hence the loose surroundings rather than a fixed
# parameter order.
#
# catalog: ^https?://(?:www\.)?jcpenney\.com/g/(?:[a-z0-9\-]+/)*[a-z0-9\-]+\?(?:[^#]*?(?:&amp;|&))?id=(?P<catalog_id>(?:cat|dept)\d+)(?:(?:&amp;|&)[^#]*)?$

CATALOG_RE = re.compile(
    r"^https?://(?:www\.)?jcpenney\.com/g/(?:[a-z0-9\-]+/)*[a-z0-9\-]+"
    r"\?(?:[^#]*?(?:&amp;|&))?id=(?P<catalog_id>(?:cat|dept)\d+)"
    r"(?:(?:&amp;|&)[^#]*)?$"
)

# --- search -----------------------------------------------------------
#
# /s?searchTerm=<term>. The term is taken as "anything up to the next
# parameter or fragment" so that it survives percent-encoding and the `+`
# that stands in for a space: `my+name+is+%3D%3D%3F.%2F` matches as one term.
# Trailing parameters (sort, page, ...) are allowed.
#
# search: ^https?://(?:www\.)?jcpenney\.com/s\?(?:[^#]*?(?:&amp;|&))?searchTerm=(?P<term>[^&#]+)(?:(?:&amp;|&)[^#]*)?$

SEARCH_RE = re.compile(
    r"^https?://(?:www\.)?jcpenney\.com/s"
    r"\?(?:[^#]*?(?:&amp;|&))?searchTerm=(?P<term>[^&#]+)"
    r"(?:(?:&amp;|&)[^#]*)?$"
)

# --- product ----------------------------------------------------------
#
# /p/<slug>/ppr<digits>. The ppr id is the stable identity; the slug is
# descriptive and the query string (pTmplType, searchTerm, ...) is
# incidental, so the query is not required at all.
#
# product: ^https?://(?:www\.)?jcpenney\.com/p/(?P<slug>[a-z0-9\-]+)/(?P<product_id>ppr\d+)(?:\?[^#]*)?$

PRODUCT_RE = re.compile(
    r"^https?://(?:www\.)?jcpenney\.com/p/(?P<slug>[a-z0-9\-]+)/"
    r"(?P<product_id>ppr\d+)(?:\?[^#]*)?$"
)

# --- titles -----------------------------------------------------------
#
# The human title a URL stands for. Both page types carry one, so this matches
# a listing page and a product page alike - it is not a URL class of its own,
# it is a second reading of URLs the other patterns already match.
#
# The title is never in the same place twice:
#
#   /g/shoes?brand=adidas              -> "adidas"  (the brand parameter wins
#                                         over the path segment: it is a shoes
#                                         page filtered to adidas)
#   /g/home-store/kitchen-dining/cooks -> "cooks"   (no brand: last segment)
#   /p/biltmore-mens-fedora/ppr...     -> "biltmore-mens-fedora" (product slug)
#
# So the pattern has one branch per page type and captures all three, and the
# caller takes the first that is present:
#
#     title = (m["brand"] or m["product_slug"] or m["slug"])
#     title = title.replace("-", " ").title()
#
# The three groups need distinct names because Python's `re` rejects a name
# reused across branches of an alternation.
#
# Two lookaheads do the work after the `?`. The first re-asserts the catalog
# id, so this only ever fires on a real listing page. The second captures
# `brand` wherever in the query it sits, without consuming anything:
# `(?=...brand=(?P<brand>...)|)` - an alternation whose second branch is
# empty, which is how you make a capture optional but not skippable. Writing
# it the obvious way, as an optional `(?:brand=(...))?` group in the main
# expression, silently misreads /g/shoes?brand=adidas as "shoes": the engine
# is free to skip the optional group and let `[^#]*$` swallow the brand.
#
# titles: ^https?://(?:www\.)?jcpenney\.com/(?:g/(?:[a-z0-9\-]+/)*(?P<slug>[a-z0-9\-]+)\?(?=[^#]*id=(?:cat|dept)\d+)(?=(?:[^#]*(?:&amp;|&))?brand=(?P<brand>[^&#]+)|)[^#]*|p/(?P<product_slug>[a-z0-9\-]+)/ppr\d+(?:\?[^#]*)?)$

TITLES_RE = re.compile(
    r"^https?://(?:www\.)?jcpenney\.com/(?:"
    r"g/(?:[a-z0-9\-]+/)*(?P<slug>[a-z0-9\-]+)"
    r"\?(?=[^#]*id=(?:cat|dept)\d+)"
    r"(?=(?:[^#]*(?:&amp;|&))?brand=(?P<brand>[^&#]+)|)[^#]*"
    r"|"
    r"p/(?P<product_slug>[a-z0-9\-]+)/ppr\d+(?:\?[^#]*)?"
    r")$"
)

# --- images -----------------------------------------------------------
#
# sc-images CDN. The path segment after /JCPenney/ is the asset id, in both
# shapes seen: DP0912202511211127M and DP68462246-20260710143622M. The query
# is only a rendering policy (impolicy/height/width), so it is optional -
# dropping it yields the same asset at its default size.
#
# The tail is `?<query>` OR a run of parameters with the `?` missing, as in
# .../DP0710202307351034Mwidth=550&amp;height=550. That URL is malformed - the
# parameters are sitting in the path - and requesting it verbatim would 404,
# but it turns up when a `?` is lost in extraction or string-joining, and the
# id in front of it is still unambiguous. Matching it lets a caller recover
# the id and rebuild a working URL, which beats dropping the image.
#
# Cutting the id at the parameters is what the `(?=[a-z][a-z_]*=)` lookahead
# does: a parameter name is lowercase, so the scan stops at `width=` and the
# trailing uppercase `M` stays with the id where it belongs. Allowing capitals
# in that lookahead would cut at `Mwidth=` and silently truncate the id.
#
# images: ^https?://sc-images\.jcpenney\.com/JCPenney/(?P<image_id>[A-Za-z0-9._\-]+?)(?:\?[^#]*|(?=[a-z][a-z_]*=)[^#]*)?$

IMAGES_RE = re.compile(
    r"^https?://sc-images\.jcpenney\.com/JCPenney/"
    r"(?P<image_id>[A-Za-z0-9._\-]+?)(?:\?[^#]*|(?=[a-z][a-z_]*=)[^#]*)?$"
)

# --- videos -----------------------------------------------------------
#
# sc-videos CDN, same shape as images but a different host and a noisier id
# charset: 9152867A_V_VA_5-1OZ, GOLF-leFLEUR-FRENCH-WALTZ. Underscores and
# mixed case are kept; the id is case-sensitive. Same tolerance for a missing
# `?` as images, since it is the same CDN family and the same failure mode.
#
# videos: ^https?://sc-videos\.jcpenney\.com/JCPenney/(?P<video_id>[A-Za-z0-9._\-]+?)(?:\?[^#]*|(?=[a-z][a-z_]*=)[^#]*)?$

VIDEOS_RE = re.compile(
    r"^https?://sc-videos\.jcpenney\.com/JCPenney/"
    r"(?P<video_id>[A-Za-z0-9._\-]+?)(?:\?[^#]*|(?=[a-z][a-z_]*=)[^#]*)?$"
)

PATTERNS = {
    "catalog": CATALOG_RE,
    "search": SEARCH_RE,
    "product": PRODUCT_RE,
    "titles": TITLES_RE,
    "images": IMAGES_RE,
    "videos": VIDEOS_RE,
}

SECTION_KIND = {
    "Search URLs": "search",
    "Catalog URLs": "catalog",
    "Product URLs": "product",
    "Image URLs": "images",
    "Video URLs": "videos",
}


def expected_kinds(section, url):
    """Which patterns must match this URL - everything else must reject it.

    Note that "Title URLs:" is not a kind. That section says "this URL carries
    a display title", which is a property of both listing and product pages,
    so its entries are classified by shape and get `titles` on top of whatever
    they already are. Reading it as a URL class of its own is what made an
    earlier version of `titles` miss product pages entirely.
    """
    kind = SECTION_KIND.get(section)
    if kind is None:
        kind = "catalog" if "/g/" in url else "product"
    kinds = {kind}
    if kind in ("catalog", "product"):
        kinds.add("titles")
    return kinds

# Cases links.txt does not cover: URLs that must be rejected, and awkward ones
# that must be accepted. (kind, url, should_match, expected capture or None).
EDGE_CASES = [
    # A `?` lost somewhere upstream: match anyway, and keep the whole id. The
    # second entry is the truncation this is easy to get wrong - the id ends
    # with M, and the parameter that follows must not eat it.
    ("images", "https://sc-images.jcpenney.com/JCPenney/DP0710202307351034Mwidth=550&amp;height=550&amp;impolicy=product_detail", True, "DP0710202307351034M"),
    ("images", "https://sc-images.jcpenney.com/JCPenney/DP68462246-20260710143622Mimpolicy=product_detail", True, "DP68462246-20260710143622M"),
    ("images", "https://sc-images.jcpenney.com/JCPenney/DP0912202511211127M", True, "DP0912202511211127M"),
    ("videos", "https://sc-videos.jcpenney.com/JCPenney/9152867A_V_VA_5-1OZwidth=550", True, "9152867A_V_VA_5-1OZ"),
    # Wrong host, wrong folder, extra path segment: still rejected.
    ("images", "https://sc-images.jcpenney.com/Other/DP0912202511211127M", False, None),
    ("images", "https://sc-images.jcpenney.com.evil.com/JCPenney/DP0912202511211127M", False, None),
    ("videos", "https://sc-videos.jcpenney.com/JCPenney/9150231A_V_VA_VOYAGE/extra", False, None),
    ("catalog", "https://www.jcpenney.com/g/shoes", False, None),
    ("catalog", "https://www.jcpenney.com/g/shoes?id=xyz123", False, None),
    ("product", "https://www.jcpenney.com/p/foo-bar", False, None),
    ("product", "https://www.jcpenney.com/p/foo-bar/ppr123/extra", False, None),
    ("search", "https://www.jcpenney.com/s?searchTerm=", False, None),
    # brand wins over the path segment, wherever it sits in the query; a
    # parameter merely ending in "brand" does not count.
    ("titles", "https://www.jcpenney.com/g/shoes?id=dept20000018&brand=adidas", True, "adidas"),
    ("titles", "https://www.jcpenney.com/g/shoes?xbrand=nope&id=dept20000018", True, "shoes"),
    # A product page carries a title too - its slug. Reading "Title URLs" as a
    # synonym for "listing pages" is what made this fail once.
    ("titles", "https://www.jcpenney.com/p/st-johns-bay-womens-mid-rise-bootcut-jean/ppr5008655264?pTmplType=regular", True, "st-johns-bay-womens-mid-rise-bootcut-jean"),
    ("titles", "https://www.jcpenney.com/p/biltmore-mens-fedora/ppr5008442615", True, "biltmore-mens-fedora"),
    # ...but only a well-formed one. No ppr id, or a trailing segment, and
    # there is no product page to take a title from.
    ("titles", "https://www.jcpenney.com/p/biltmore-mens-fedora", False, None),
    ("titles", "https://www.jcpenney.com/p/foo-bar/ppr123/extra", False, None),
]

# The one capture that matters per pattern - the identity a crawler keys on.
PRIMARY = {
    "catalog": lambda m: m["catalog_id"],
    "search": lambda m: m["term"],
    "product": lambda m: m["product_id"],
    "titles": lambda m: m["brand"] or m["product_slug"] or m["slug"],
    "images": lambda m: m["image_id"],
    "videos": lambda m: m["video_id"],
}


# A URL matching two patterns usually means one of them is too loose - except
# for `titles`, which reads a listing or product URL for its display name and
# so is meant to overlap both.
EXPECTED_OVERLAP = {
    "catalog": {"titles"},
    "product": {"titles"},
    "titles": {"catalog", "product"},
    "search": set(),
    "images": set(),
    "videos": set(),
}

_URL_RE = re.compile(r"https?://\S+")

# links.txt annotates most catalog URLs with "... for Alfred Dunner", which is
# the expected title. The four under "Title URLs:" carry no annotation, so
# their expected titles are spelled out here.
_ANNOTATION_RE = re.compile(r"\bfor\s+(?:\((?P<paren>[^)]*)\)|(?P<plain>.+?))\s*(?:search)?$")

TITLE_CHECKS = {
    "https://www.jcpenney.com/g/home-store/kitchen-dining/cooks?id=cat11100007010": "Cooks",
    "https://www.jcpenney.com/g/juniors?brand=arizona&amp;id=dept20023450025": "Arizona",
    "https://www.jcpenney.com/g/brands/ninja?id=cat11100025927": "Ninja",
    "https://www.jcpenney.com/g/men/workout-clothes?brand=adidas&amp;id=cat100290088": "Adidas",
    "https://www.jcpenney.com/p/linden-street-terra-pumpkin-4-pc-stoneware-dinner-plate/ppr5008499707?pTmplType=regular":
        "Linden Street Terra Pumpkin 4 Pc Stoneware Dinner Plate",
}


def load_links(path):
    """Read links.txt into {section heading: [(url, annotation or None), ...]}."""
    sections, current = {}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or set(stripped) <= set("=-"):
            continue
        found = _URL_RE.search(stripped)
        if found:
            if current is None:
                continue
            trailing = stripped[found.end():].strip()
            note = _ANNOTATION_RE.match(trailing) if trailing else None
            annotation = (note["paren"] or note["plain"]).strip() if note else None
            sections[current].append((found.group(0), annotation))
        else:
            current = stripped
            sections.setdefault(current, [])
    return sections


def title_of(url):
    """The display title a URL carries, or None if it carries none."""
    match = TITLES_RE.match(url)
    if match is None:
        return None
    raw = match["brand"] or match["product_slug"] or match["slug"]
    return raw.replace("-", " ").replace("+", " ").title()


def check_sources():
    """Each pattern is written three times - compiled here, quoted in the
    comment above it, and listed in regex.txt. Report any that have drifted."""
    source = Path(__file__).read_text(encoding="utf-8")
    commented = dict(re.findall(r"^# (\w+): (.+)$", source, re.M))
    listed = dict(
        line.split(": ", 1)
        for line in Path(__file__).with_name("regex.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    problems = []
    for name, pattern in PATTERNS.items():
        for where, copy in (("comment", commented.get(name)), ("regex.txt", listed.get(name))):
            if copy != pattern.pattern:
                problems.append(f"{name}: compiled pattern differs from its {where} copy")
    return problems


def check(kind, url):
    """Test one URL against one pattern.

    Returns (passed, extracted, also_matched):
      passed        did PATTERNS[kind] match the whole URL
      extracted     the named groups it captured, plus the resolved title or
                    decoded search term where those apply
      also_matched  the other patterns that matched, which is the useful hint
                    when a URL is misfiled or a pattern is too loose
    """
    url = url.strip()
    if kind == "any":
        hits = [n for n, p in PATTERNS.items() if p.match(url)]
        return bool(hits), extraction(url), hits

    match = PATTERNS[kind].match(url)
    others = [n for n, p in PATTERNS.items() if n != kind and p.match(url)]
    return match is not None, extraction(url) if match else {}, others


def extraction(url):
    """Everything the patterns can pull out of a URL, for display."""
    values = {}
    for name, pattern in PATTERNS.items():
        match = pattern.match(url)
        if match:
            values.update({k: v for k, v in match.groupdict().items() if v is not None})
    title = title_of(url)
    if title:
        values["title"] = title
    search = SEARCH_RE.match(url)
    if search:
        values["decoded_term"] = unquote_plus(search["term"])
    return values


def report(kind, url, passed, extracted, also_matched):
    """Print one PASS/FAIL line, plus what was captured or what went wrong."""
    print(f"{'PASS' if passed else 'FAIL'}  {kind:<8}{url}")
    if passed:
        for key, value in extracted.items():
            print(f"        {key} = {value}")
        if kind == "any":
            print(f"        matched by: {', '.join(also_matched)}")
        else:
            # catalog and titles are the same URLs read two ways, so their
            # overlap is expected and not worth reporting. Any other overlap is.
            unexpected = [n for n in also_matched if n not in EXPECTED_OVERLAP[kind]]
            if unexpected:
                print(f"        note: also matches {', '.join(unexpected)}")
    else:
        if kind == "any":
            print("        no pattern matched this URL")
        elif also_matched:
            print(f"        no match, but it matches {', '.join(also_matched)}")
        else:
            print("        no match, and no other pattern matched it either")


def parse_cases(argv):
    """Read <type> <url> pairs from the command line, or from stdin when the
    only argument is '-'. Stdin takes one 'type url' case per line."""
    if argv == ["-"]:
        cases = []
        for line in sys.stdin:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                raise ValueError(f"expected 'type url', got: {line}")
            cases.append((parts[0], parts[1].strip()))
        return cases

    if len(argv) % 2:
        raise ValueError("arguments come in <type> <url> pairs")
    return list(zip(argv[::2], argv[1::2]))


def self_test():
    links = Path(__file__).with_name("links.txt")
    sections = load_links(links)
    failures = check_sources()

    for section, entries in sections.items():
        for url, _ in entries:
            should = expected_kinds(section, url)
            for name, pattern in PATTERNS.items():
                matched = pattern.match(url) is not None
                if matched != (name in should):
                    verb = "did not match" if name in should else "wrongly matched"
                    failures.append(f"{name}: {verb} [{section}] {url}")

    # The titles pattern has to yield the right title, not merely match. This
    # is the check that catches a brand read as its parent category, or a
    # product page yielding no title at all.
    for section, entries in sections.items():
        for url, annotation in entries:
            if "titles" not in expected_kinds(section, url):
                continue
            expected = TITLE_CHECKS.get(url, annotation)
            actual = title_of(url)
            if actual is None:
                failures.append(f"titles: no title extracted from {url}")
            elif expected and actual.casefold() != expected.casefold():
                failures.append(
                    f"titles: got {actual!r}, expected {expected!r} from {url}"
                )

    # The search term is the other extracted value worth checking, against the
    # decoded term links.txt records in parentheses.
    for url, annotation in sections.get("Search URLs", []):
        if not annotation:
            continue
        term = unquote_plus(SEARCH_RE.match(url)["term"])
        if term != annotation:
            failures.append(f"search: got {term!r}, expected {annotation!r} from {url}")

    for kind, url, should_match, expected in EDGE_CASES:
        match = PATTERNS[kind].match(url)
        if (match is not None) != should_match:
            verb = "did not match" if should_match else "wrongly matched"
            failures.append(f"{kind}: edge case {verb} {url}")
        elif match and expected is not None and PRIMARY[kind](match) != expected:
            failures.append(
                f"{kind}: edge case captured {PRIMARY[kind](match)!r}, "
                f"expected {expected!r} from {url}"
            )

    total = sum(len(e) for e in sections.values())
    print(f"{len(PATTERNS)} patterns x {total} URLs from {links.name}"
          f", plus {len(EDGE_CASES)} edge cases\n")
    for section, entries in sections.items():
        print(section)
        for url, _ in entries:
            hits = [n for n, p in PATTERNS.items() if p.match(url)]
            extracted = title_of(url)
            if extracted is None and SEARCH_RE.match(url):
                extracted = unquote_plus(SEARCH_RE.match(url)["term"])
            suffix = f"  -> {extracted}" if extracted else ""
            print(f"  {', '.join(hits) or '(no match)':<18}{url}{suffix}")
        print()

    if failures:
        print("FAILED")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("All patterns matched what they should and rejected everything else.")
    return 0


USAGE = f"""Usage:
  python {Path(__file__).name} <type> <url> [<type> <url> ...]
  python {Path(__file__).name} -            read 'type url' cases from stdin
  python {Path(__file__).name} --self-test  run the bundled links.txt suite

  <type> is one of: {', '.join(PATTERNS)}, any

Exit status is 0 only if every case passed."""


def main(argv):
    if not argv or argv[0] in ("--self-test", "--selftest"):
        return self_test()
    if argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0

    try:
        cases = parse_cases(argv)
    except ValueError as error:
        print(f"{error}\n\n{USAGE}", file=sys.stderr)
        return 2

    valid = set(PATTERNS) | {"any"}
    unknown = sorted({kind for kind, _ in cases if kind not in valid})
    if unknown:
        print(
            f"unknown type(s): {', '.join(unknown)}\nvalid types: {', '.join(sorted(valid))}",
            file=sys.stderr,
        )
        return 2

    passed = 0
    for kind, url in cases:
        result, extracted, also = check(kind, url)
        report(kind, url, result, extracted, also)
        passed += result

    if len(cases) > 1:
        print(f"\n{passed}/{len(cases)} passed")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
