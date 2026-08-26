"""The custom image pipeline: fetch each cover and write it to disk.

Built rather than borrowed. Scrapy ships ``ImagesPipeline``, but it needs
Pillow, it names files after a SHA-1 of the URL, and it stores everything in
one flat ``full/`` directory - none of which is what the brief asks for. This
one downloads the bytes and writes them to
``downloaded_images/<category>/<title>.jpg``.

``process_item`` is a coroutine and awaits the engine's own downloader, so
the crawl keeps running while a cover is in flight, and covers inherit the
project's delay, retries and downloader middlewares. Fetching with
``requests.get`` instead would block the reactor and serialise the whole
crawl behind one image at a time.

Failures are logged and counted, never raised: one 404 cover should not cost
the other 999 rows of output. The item is returned either way, so a book with
an unreachable cover still appears in the exported file.
"""

import logging
from pathlib import Path
from typing import Set

from scrapy import Request
from scrapy.http.request import NO_CALLBACK

from bookcovers.naming import image_suffix, slugify, stem_budget

logger = logging.getLogger(__name__)


class CoverImagePipeline:
    """Save each item's cover under ``<store>/<category>/<title><ext>``."""

    def __init__(self, crawler):
        settings = crawler.settings

        # The engine is what gives us a non-blocking download that still goes
        # through the project's downloader middlewares, delay and retries.
        self.crawler = crawler

        # Resolved, because the filename budget below is measured against
        # the absolute path the OS will actually see.
        self.store = Path(settings.get("COVERS_STORE", "downloaded_images")).resolve()
        self.overwrite = settings.getbool("COVERS_OVERWRITE", False)

        # Destinations already handed out this run. Two different books can
        # share a title inside one category; without this the second would
        # overwrite the first and the run would silently lose an image.
        self.claimed_paths: Set[Path] = set()

        self.saved = 0
        self.already_present = 0
        self.failed = 0
        self.no_url = 0

    @classmethod
    def from_crawler(cls, crawler):
        """Scrapy's hook for a pipeline that needs the crawler itself."""
        return cls(crawler)

    async def process_item(self, item):
        """Download one cover and write it, then return the item unchanged.

        Returning the item rather than a modified copy keeps the exported
        fields exactly the two the brief asks for.
        """
        image_url = item.get("image_url")
        if not image_url:
            self.no_url += 1
            logger.warning("No image URL for %r - nothing to download", item.get("title"))
            return item

        destination = self._claim_destination(item, image_url)

        # Skipping what is already on disk makes a re-run cheap, and makes an
        # interrupted crawl safe to restart. -s COVERS_OVERWRITE=True forces a
        # refetch.
        if destination.exists() and not self.overwrite:
            self.already_present += 1
            logger.debug("Already downloaded: %s", destination)
            return item

        # NO_CALLBACK tells Scrapy this response is consumed here and never
        # reaches a spider callback.
        request = Request(image_url, callback=NO_CALLBACK)

        try:
            response = await self.crawler.engine.download_async(request)
        except Exception as exc:  # noqa: BLE001 - any transport error is the same to us
            self.failed += 1
            logger.warning("Could not fetch %s: %s", image_url, exc)
            return item

        if response.status != 200 or not response.body:
            self.failed += 1
            logger.warning(
                "Unexpected response for %s: HTTP %s, %d bytes",
                image_url,
                response.status,
                len(response.body),
            )
            return item

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(response.body)
        except OSError as exc:
            # A path the OS refuses is a failure like any other: count it and
            # let the item through, so the row still reaches the output.
            # Letting this escape would lose the row as well as the file.
            self.failed += 1
            logger.warning("Could not write %s: %s", destination, exc)
            return item

        self.saved += 1
        logger.debug("Saved %s (%d bytes)", destination, len(response.body))
        return item

    def _claim_destination(self, item, image_url: str) -> Path:
        """Work out where this cover goes, and reserve the path.

        The whole method runs before the first ``await`` in ``process_item``,
        so no two concurrent items can claim the same path even though many
        are in flight at once.

        A book with no breadcrumb lands in ``uncategorised/`` rather than at
        the store root, so the directory layout stays uniform.
        """
        category_dir = slugify(item.get("category"), fallback="uncategorised")
        directory = self.store / category_dir
        suffix = image_suffix(image_url)

        # The title cap has to account for where the store is: Windows applies
        # its 260-character limit to the whole path, so a deep COVERS_STORE
        # leaves less room for the name than the default one does.
        stem = slugify(
            item.get("title"),
            fallback="untitled",
            max_length=stem_budget(directory, suffix),
        )

        destination = directory / f"{stem}{suffix}"

        # On a title collision, number the later ones rather than clobbering.
        duplicate_index = 2
        while destination in self.claimed_paths:
            destination = directory / f"{stem}-{duplicate_index}{suffix}"
            duplicate_index += 1

        self.claimed_paths.add(destination)
        return destination

    def close_spider(self):
        """Report the download tallies when the crawl finishes."""
        logger.info(
            "Covers: %d saved, %d already on disk, %d failed, %d items had no URL. "
            "Stored under %s",
            self.saved,
            self.already_present,
            self.failed,
            self.no_url,
            self.store,
        )
