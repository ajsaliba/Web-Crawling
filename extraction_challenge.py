"""Part 2 - Extraction Challenge.

    A. Largest product image   parse srcset, pick the widest descriptor
    B. Embedded product JSON   find the object, then read it by path
    C. Video extraction        match on file extension, not attribute name
    D. Pagination counters     one regex, two capture groups

Each function takes raw HTML and returns the value, or None if it is not
there. None of them raise on bad input; in a crawler an odd page is normal.

Challenge B parses the JSON rather than pattern-matching into it, so the
thumbnail is never a candidate. Regex only finds where the object starts.

No dependencies - json and re are enough. Run it with:

    python extraction_challenge.py

Exits non-zero if any case fails.
"""

import json
import re
from typing import Dict, Optional, Tuple

# Challenge A - Largest product image

# srcset attribute, either quote style.
_SRCSET_RE = re.compile(r"""srcset\s*=\s*(["'])(?P<value>.*?)\1""", re.DOTALL)

# One srcset candidate: "<url> <number><unit>", where the unit is w (width) or
# x (pixel density). The descriptor is optional so a bare URL still parses.
_SRCSET_CANDIDATE_RE = re.compile(
    r"""
    (?P<url>\S+)                 # the URL - any run of non-space characters
    (?:\s+(?P<size>\d+(?:\.\d+)?)(?P<unit>[wx]))?   # optional 300w / 2x descriptor
    """,
    re.VERBOSE,
)

# Fallback for markup that has no srcset: the plain src attribute.
_SRC_RE = re.compile(r"""\bsrc\s*=\s*(["'])(?P<value>.*?)\1""", re.DOTALL)


def extract_largest_image(html: str) -> Optional[str]:
    """Return the highest-resolution image URL an <img> tag offers.

    Compares width descriptors numerically rather than taking the last entry.
    srcset is usually ordered smallest-first, but nothing guarantees it.
    Falls back to src when there is no srcset.
    """
    match = _SRCSET_RE.search(html)
    if not match:
        fallback = _SRC_RE.search(html)
        return fallback.group("value").strip() if fallback else None

    candidates: list[Tuple[float, str]] = []
    for entry in match.group("value").split(","):
        entry = entry.strip()
        if not entry:
            continue
        parsed = _SRCSET_CANDIDATE_RE.match(entry)
        if not parsed:
            continue
        # No descriptor means the 1x default; treat as smallest so a
        # described candidate wins.
        size = float(parsed.group("size")) if parsed.group("size") else 0.0
        candidates.append((size, parsed.group("url")))

    if not candidates:
        return None

    return max(candidates, key=lambda candidate: candidate[0])[1]


# Challenge B - Embedded product JSON

# Finds the assignment only. The object end is found by counting braces,
# because a regex cannot match nested ones reliably.
_PRODUCT_DATA_RE = re.compile(r"window\.PRODUCT_DATA\s*=\s*(?P<json>\{)")


def _extract_balanced_object(text: str, start: int) -> Optional[str]:
    """Return the JSON object starting at `start`, matching braces.

    Tracks string literals so a brace inside a value, or an escaped quote,
    cannot end the object early.
    """
    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return None  # unbalanced - truncated or malformed page


def extract_primary_image(html: str) -> Optional[str]:
    """Return ``media.primary.url`` from the embedded ``window.PRODUCT_DATA``.

    The thumbnail never gets a chance to win here. The JSON is parsed into a
    dict and read by path, so ``thumbnail`` is not a candidate at all. Note that
    a pattern like ``https://\\S+\\.jpg`` would have matched the thumbnail first,
    since it appears earlier in the object.
    """
    match = _PRODUCT_DATA_RE.search(html)
    if not match:
        return None

    raw_object = _extract_balanced_object(html, match.start("json"))
    if raw_object is None:
        return None

    try:
        data = json.loads(raw_object)
    except json.JSONDecodeError:
        # Real stores sometimes emit JS object literals - unquoted keys,
        # trailing commas - which are not valid JSON. Better to report
        # nothing than crash on one page.
        return None

    if not isinstance(data, dict):
        return None

    media = data.get("media")
    if not isinstance(media, dict):
        return None

    primary = media.get("primary")
    if not isinstance(primary, dict):
        return None

    url = primary.get("url")
    return url if isinstance(url, str) else None


# Challenge C - Video extraction

# Any attribute whose value ends in .mp4. Matching on syntax rather than
# attribute name copes with "source", "src", "data-video" and the like; the
# extension keeps the .jpg poster and .vtt captions out.
_MP4_ATTRIBUTE_RE = re.compile(
    r"""
    [\w:-]+                      # attribute name
    \s*=\s*
    (["'])                       # opening quote
    (?P<url>[^"']*?\.mp4(?:\?[^"']*)?)   # URL ending in .mp4, query string allowed
    \1                           # matching closing quote
    """,
    re.VERBOSE | re.IGNORECASE,
)


def extract_video_url(html: str) -> Optional[str]:
    """Return the first .mp4 URL in the markup.

    The element carries three URLs - poster, video, captions - so the
    extension is what distinguishes them. Query strings are allowed, so a
    signed CDN URL still matches.
    """
    match = _MP4_ATTRIBUTE_RE.search(html)
    return match.group("url") if match else None


# Challenge D - Pagination

# Two independent capture groups; \s+ absorbs the newlines and indentation that
# the markup puts between "Page", the numbers and "of".
_PAGINATION_RE = re.compile(
    r"Page\s+(?P<current>\d+)\s+of\s+(?P<total>\d+)",
    re.IGNORECASE,
)


def extract_pagination(html: str) -> Optional[Dict[str, int]]:
    """Return {"current_page": int, "total_pages": int}.

    Captured independently, and returned as ints so "is there a next page?"
    is a comparison rather than another parse.
    """
    match = _PAGINATION_RE.search(html)
    if not match:
        return None

    return {
        "current_page": int(match.group("current")),
        "total_pages": int(match.group("total")),
    }


# Sample inputs, exactly as given in the assessment

CHALLENGE_A_HTML = """
<img
    class="main-product-image"
    src="https://cdn.sample-store.com/items/X51_300.jpg"
    srcset="
        https://cdn.sample-store.com/items/X51_300.jpg 300w,
        https://cdn.sample-store.com/items/X51_700.jpg 700w,
        https://cdn.sample-store.com/items/X51_1400.jpg 1400w
    ">
"""

CHALLENGE_B_HTML = """
<script>window.PRODUCT_DATA = {
    "sku": "LAU-9034",
    "thumbnail": "https://media.example.com/thumb/9034.jpg",
    "media": {
        "primary": {
            "url": "https://media.example.com/full/9034.jpg"
        }
    },
    "price": "85.00"
};</script>
"""

CHALLENGE_C_HTML = """
<product-video
    poster="https://cdn.example.com/video/item77-poster.jpg"
    source="https://cdn.example.com/video/item77-main.mp4"
    captions="https://cdn.example.com/video/item77-en.vtt">
</product-video>
"""

CHALLENGE_D_HTML = """
<div class="pagination-status">
    Page 6 of 24
</div>
"""


def _run_checks() -> None:
    """Assert each challenge against its expected answer and print the result."""
    checks = [
        (
            "A - largest product image",
            extract_largest_image(CHALLENGE_A_HTML),
            "https://cdn.sample-store.com/items/X51_1400.jpg",
        ),
        (
            "B - primary full-size image",
            extract_primary_image(CHALLENGE_B_HTML),
            "https://media.example.com/full/9034.jpg",
        ),
        (
            "C - video URL",
            extract_video_url(CHALLENGE_C_HTML),
            "https://cdn.example.com/video/item77-main.mp4",
        ),
        (
            "D - pagination",
            extract_pagination(CHALLENGE_D_HTML),
            {"current_page": 6, "total_pages": 24},
        ),
    ]

    for label, actual, expected in checks:
        status = "PASS" if actual == expected else "FAIL"
        print(f"[{status}] {label}")
        print(f"        got:      {actual}")
        if actual != expected:
            print(f"        expected: {expected}")

    # Edge cases: nothing here should raise, everything should report "not found".
    assert extract_largest_image("<div>no image at all</div>") is None
    assert extract_primary_image("<script>window.OTHER = {};</script>") is None
    assert extract_video_url('<video poster="a.jpg"></video>') is None
    assert extract_pagination("<div>no pagination</div>") is None

    # A plain <img> with no srcset must still yield its src.
    assert (
        extract_largest_image('<img src="https://cdn.example.com/only.jpg">')
        == "https://cdn.example.com/only.jpg"
    )
    print("\n[PASS] edge cases: missing data returns None instead of raising")

    failed = [label for label, actual, expected in checks if actual != expected]
    if failed:
        raise SystemExit(f"Failing challenges: {', '.join(failed)}")
    print("[PASS] all four challenges produce the expected values")


if __name__ == "__main__":
    _run_checks()
