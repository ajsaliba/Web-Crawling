"""Downloading cover images: a plain GET to the image URL, saved to disk."""

import hashlib
import logging
import mimetypes
import re
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger(__name__)

SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text, max_length=60):
    slug = SLUG_RE.sub("-", (text or "").lower()).strip("-")
    return slug[:max_length].strip("-") or "untitled"


def _extension(image_url, content_type):
    suffix = Path(urlparse(image_url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return suffix
    guessed = mimetypes.guess_extension((content_type or "").split(";")[0].strip())
    return guessed or ".jpg"


class ImageDownloader:
    """Saves images under <root>/<category-slug>/<book-slug>.<ext>."""

    def __init__(self, client, root, overwrite=False):
        self.client = client
        self.root = Path(root)
        self.overwrite = overwrite
        self.downloaded = 0
        self.skipped = 0
        self.failed = 0

    def download(self, image_url, category, title):
        """GET the image URL and write the bytes. Returns a result dict."""
        if not image_url:
            self.failed += 1
            return {"status": "failed", "reason": "no image url", "path": None}

        folder = self.root / slugify(category or "uncategorised")
        folder.mkdir(parents=True, exist_ok=True)
        # Hash suffix keeps two books with the same title from colliding.
        stem = "%s_%s" % (slugify(title), hashlib.md5(image_url.encode()).hexdigest()[:8])

        existing = next(folder.glob(stem + ".*"), None)
        if existing and not self.overwrite:
            self.skipped += 1
            log.info("skip (already saved) %s", existing.name)
            return {"status": "skipped", "path": str(existing), "bytes": existing.stat().st_size}

        try:
            response = self.client.get(image_url, stream=True)
            payload = response.content
        except RuntimeError as exc:
            self.failed += 1
            log.error("image download failed %s -> %s", image_url, exc)
            return {"status": "failed", "reason": str(exc), "path": None}

        path = folder / (stem + _extension(image_url, response.headers.get("Content-Type")))
        path.write_bytes(payload)
        self.downloaded += 1
        log.info("saved %s (%d bytes)", path.relative_to(self.root), len(payload))
        return {"status": "downloaded", "path": str(path), "bytes": len(payload)}

    def stats(self):
        return {
            "downloaded": self.downloaded,
            "skipped": self.skipped,
            "failed": self.failed,
        }
