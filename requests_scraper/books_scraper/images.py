"""Cover-image downloads.

One file per book, named after the book's slug (``sharp-objects_997.jpg``), so
the name is stable across runs and unique even where two books share a title.

Downloads are skipped when the file already exists. A crawl of 1,000 covers is
the slow half of the run, and re-running to fix a parsing bug should not mean
re-fetching every image.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

from books_scraper.http_client import PoliteSession

logger = logging.getLogger(__name__)

#: Only these are written to disk. An unexpected content type means the URL did
#: not resolve to an image, and saving it would put an HTML error page on disk
#: under a .jpg name.
_EXTENSION_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

#: Fallback when the server sends no usable Content-Type. Every cover on
#: books.toscrape.com is a JPEG.
_DEFAULT_EXTENSION = ".jpg"

#: Longest filename stem we will write, extension excluded.
#:
#: Slugs come from the site's own URLs and some are long - one book's runs to
#: 200 characters. Windows caps a full path at 260 by default, so an untrimmed
#: slug under a moderately deep output directory fails to open, which is how
#: this limit was found. 100 leaves room for the extension, the ".part" suffix
#: and a reasonably nested output directory.
_MAX_FILENAME_STEM = 100

#: Trailing "_1000" in a slug: the site's own product id, and the part that
#: makes the name unique. Preserved when the rest is truncated.
_ID_SUFFIX_RE = re.compile(r"_\d+$")

#: Characters no Windows filename may contain. Slugs from this site have none,
#: but a slug is URL-derived and this is the layer that writes files.
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_stem(slug: str, max_length: int = _MAX_FILENAME_STEM) -> str:
    """Turn a slug into a filename stem that is legal and short enough.

    >>> safe_stem("sharp-objects_997")
    'sharp-objects_997'
    >>> safe_stem("a-very-long-title-indeed_459", max_length=12)
    'a-very-l_459'

    Truncation keeps the trailing product id, so two books whose titles share a
    long prefix still get different filenames - the id is the only part
    guaranteed unique, and it is the part a plain slice would throw away.
    """
    cleaned = _INVALID_FILENAME_CHARS.sub("-", slug).strip(" .")
    if len(cleaned) <= max_length:
        return cleaned

    match = _ID_SUFFIX_RE.search(cleaned)
    tail = match.group(0) if match else ""
    head = cleaned[: max(1, max_length - len(tail))].rstrip("-_")
    return f"{head}{tail}"


def _extension_for(content_type: Optional[str], url: str) -> Optional[str]:
    """Choose a file extension from the response type, falling back to the URL.

    Returns None when the response is definitely not an image, which the caller
    treats as a failed download.
    """
    if content_type:
        media_type = content_type.split(";")[0].strip().lower()
        if media_type in _EXTENSION_BY_CONTENT_TYPE:
            return _EXTENSION_BY_CONTENT_TYPE[media_type]
        if media_type.startswith("image/"):
            # An image we do not have a mapping for: keep it, using the URL's
            # own suffix if it looks sane.
            suffix = Path(unquote(urlparse(url).path)).suffix.lower()
            return suffix if suffix else _DEFAULT_EXTENSION
        return None

    suffix = Path(unquote(urlparse(url).path)).suffix.lower()
    return suffix if suffix in set(_EXTENSION_BY_CONTENT_TYPE.values()) else _DEFAULT_EXTENSION


def existing_image_for(images_dir: Path, slug: str) -> Optional[Path]:
    """Return an already-downloaded cover for ``slug``, if there is one.

    The extension is not known before the request, so every extension we would
    write is tried. Tried by name rather than by glob, because a slug is
    URL-derived and a "[" in one would make a glob pattern mean something else.
    A zero-length file does not count: it is the debris of an interrupted run.
    """
    stem = safe_stem(slug)
    for extension in dict.fromkeys(_EXTENSION_BY_CONTENT_TYPE.values()):
        candidate = images_dir / f"{stem}{extension}"
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None


def download_image(
    session: PoliteSession,
    url: str,
    images_dir: Path,
    slug: str,
    *,
    overwrite: bool = False,
) -> Optional[Path]:
    """Download one cover image and return the path written.

    Returns None when the download failed or the response was not an image; the
    book record then carries ``image_file: null``, which the run summary counts.

    The write goes to a temporary file first and is renamed into place, so an
    interrupted run cannot leave a half-written JPEG that a later run would
    happily skip as "already downloaded".
    """
    if not url:
        return None

    if not overwrite:
        existing = existing_image_for(images_dir, slug)
        if existing is not None:
            logger.debug("Cover already on disk, skipping: %s", existing.name)
            return existing

    response = session.get(url)
    if response is None:
        return None

    extension = _extension_for(response.headers.get("Content-Type"), url)
    if extension is None:
        logger.warning(
            "Not an image (%s): %s", response.headers.get("Content-Type"), url
        )
        return None

    if not response.content:
        logger.warning("Empty image body: %s", url)
        return None

    destination = images_dir / f"{safe_stem(slug)}{extension}"
    temporary = destination.with_name(destination.name + ".part")
    try:
        temporary.write_bytes(response.content)
        temporary.replace(destination)
    except OSError as exc:
        # A path too long for the filesystem, a permission problem, a full
        # disk. Costs one cover; the book itself is still worth keeping.
        logger.warning("Could not write %s: %s", destination.name, exc)
        temporary.unlink(missing_ok=True)
        return None

    logger.debug("Saved cover %s (%d bytes)", destination.name, len(response.content))
    return destination
