"""Turning page text into safe file and directory names.

Kept out of the pipeline so the pipeline stays about downloading. Nothing here
imports Scrapy or touches the disk, so it is testable on its own.

Every function returns a usable string rather than raising: a book with an
odd title should still get a file, not stop the crawl.

Doctests: from image_pipeline_crawler/, run
``python -m doctest bookcovers/naming.py``. Silence means they passed.
"""

import os
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

# Long enough for every title on the site (the longest is 148 characters), but
# short enough that category directory + filename stays under the 260-character
# path limit Windows still applies to most APIs.
MAX_SLUG_LENGTH = 120

# That limit is on the *whole* path, so a cap on the name alone is not enough:
# a deep enough COVERS_STORE blows the budget however short the title is
# trimmed. stem_budget() below works out what is actually left.
WINDOWS_MAX_PATH = 260

# Below this a name stops being recognisable, so we let the write fail loudly
# rather than pretend a 4-character stem identifies a book.
MIN_SLUG_LENGTH = 16

# Extensions we are willing to write. Anything else is stored as .jpg, which is
# what books.toscrape.com actually serves for every cover.
KNOWN_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"})

DEFAULT_IMAGE_SUFFIX = ".jpg"

# Windows refuses to create a file with one of these stems, whatever the
# extension. No book title slugifies to one today, but a two-line guard is
# cheaper than a crawl that dies on one item.
_RESERVED_STEMS = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{d}" for d in "123456789"}
    | {f"lpt{d}" for d in "123456789"}
)


def clean_text(parts: Iterable[Optional[str]]) -> Optional[str]:
    """Join text fragments and squash whitespace runs to single spaces.

    Returns None if nothing is left. "Absent" and "blank" both mean no value
    downstream, so they are not worth distinguishing.

    >>> clean_text(["  It's Only  the Himalayas "])
    "It's Only the Himalayas"
    >>> clean_text([None, "   "]) is None
    True
    """
    joined = " ".join(part for part in parts if part)
    collapsed = re.sub(r"\s+", " ", joined).strip()
    return collapsed or None


def slugify(
    text: Optional[str],
    fallback: str = "untitled",
    max_length: int = MAX_SLUG_LENGTH,
) -> str:
    """Reduce arbitrary text to lowercase ASCII words joined by hyphens.

    Used for both halves of the destination path, so a category and a title
    are named by the same rule. Accents are folded rather than dropped, so
    "Coup d'Etat" and "Coup d'État" do not become different files.

    >>> slugify("Historical Fiction")
    'historical-fiction'
    >>> slugify("Mesaerion: The Best Science Fiction Stories 1800-1849")
    'mesaerion-the-best-science-fiction-stories-1800-1849'
    >>> slugify("   ")
    'untitled'
    >>> slugify("The Grand Design", max_length=10)
    'the-grand'
    """
    if not text:
        return fallback

    # NFKD splits "é" into "e" + combining accent; encoding to ASCII then drops
    # the accent and leaves the letter.
    folded = unicodedata.normalize("NFKD", text)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()

    # Truncate on a hyphen where possible, so the name ends on a whole word.
    if len(slug) > max_length:
        slug = slug[:max_length].rsplit("-", 1)[0] or slug[:max_length]

    if not slug:
        return fallback
    if slug in _RESERVED_STEMS:
        return f"{slug}-book"
    return slug


def image_suffix(url: Optional[str]) -> str:
    """Return the file extension to save a cover under, from its URL.

    Query strings and fragments are ignored, and an unrecognised or missing
    extension falls back to .jpg rather than writing a file the OS cannot open.

    >>> image_suffix("https://books.toscrape.com/media/cache/fe/72/abc.jpg")
    '.jpg'
    >>> image_suffix("https://example.com/cover.PNG?v=2")
    '.png'
    >>> image_suffix("https://example.com/cover")
    '.jpg'
    """
    if not url:
        return DEFAULT_IMAGE_SUFFIX

    suffix = urlparse(url).path.rsplit("/", 1)[-1]
    dot = suffix.rfind(".")
    if dot == -1:
        return DEFAULT_IMAGE_SUFFIX

    candidate = suffix[dot:].lower()
    return candidate if candidate in KNOWN_IMAGE_SUFFIXES else DEFAULT_IMAGE_SUFFIX


def stem_budget(directory: Path, suffix: str, reserve: int = 3) -> int:
    """How many characters a filename stem may use inside ``directory``.

    Windows applies its 260-character limit to the whole path, so the budget
    depends on where the store is. ``reserve`` leaves room for the ``-2``,
    ``-3`` suffix a title collision adds.

    >>> stem_budget(Path("C:/covers/science"), ".jpg") == MAX_SLUG_LENGTH
    True
    >>> stem_budget(Path("C:/" + "d" * 100), ".jpg")   # room to spare
    120
    >>> stem_budget(Path("C:/" + "d" * 200), ".jpg")   # squeezed
    49
    >>> stem_budget(Path("C:/" + "d" * 250), ".jpg")   # past the limit
    16
    """
    used = len(str(directory)) + len(os.sep) + len(suffix) + reserve
    return max(MIN_SLUG_LENGTH, min(MAX_SLUG_LENGTH, WINDOWS_MAX_PATH - used))
