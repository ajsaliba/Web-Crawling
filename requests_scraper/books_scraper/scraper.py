"""The crawl itself: listing pages, detail pages, covers, output.

Shape of a run:

    for each listing page (following the site's own "next" link)
        for each product pod on it
            fetch the detail page
            merge listing + detail into one record
            download the cover
    write books.json / books.csv / summary.json

Sequential on purpose. The catalogue is ~1,000 books and the site is a shared
sandbox; a thread pool would finish sooner and be ruder, and the politeness
delay in :class:`~books_scraper.http_client.PoliteSession` only means something
when one caller owns the schedule.

Records are deduplicated on UPC, which is the site's own unique product code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from books_scraper.config import Settings
from books_scraper.http_client import PoliteSession
from books_scraper.images import download_image, existing_image_for
from books_scraper.parsers import (
    merge_records,
    parse_detail_page,
    parse_listing_page,
    slug_from_product_url,
)
from books_scraper.storage import field_coverage, write_outputs, write_summary

logger = logging.getLogger(__name__)


@dataclass
class ScrapeResult:
    """What one run produced, for the caller and for summary.json."""

    records: list[dict[str, Any]] = field(default_factory=list)
    pages_visited: int = 0
    duplicates_skipped: int = 0
    images_downloaded: int = 0
    images_skipped_existing: int = 0
    images_failed: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: float = 0.0

    def as_summary(self) -> dict[str, Any]:
        """Render the run as the dictionary written to summary.json."""
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": round(self.duration_seconds, 1),
            "pages_visited": self.pages_visited,
            "books_scraped": len(self.records),
            "duplicates_skipped": self.duplicates_skipped,
            "images_downloaded": self.images_downloaded,
            "images_already_on_disk": self.images_skipped_existing,
            "images_failed": self.images_failed,
            "failed_requests": [
                {"url": url, "reason": reason} for url, reason in self.failures
            ],
            "field_coverage": field_coverage(self.records),
        }


class BooksScraper:
    """Crawl books.toscrape.com with a single requests session.

    Usage::

        result = BooksScraper(Settings()).run()
        print(len(result.records))
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.result = ScrapeResult()
        self._seen_upcs: set[str] = set()

    # -- traversal ---------------------------------------------------------

    def iter_listing_pages(self, session: PoliteSession) -> Iterator[tuple[list[dict], str]]:
        """Yield ``(listing records, page url)`` for each catalogue page.

        Stops at ``max_pages`` if set, otherwise when the site stops offering a
        next link. A page that fails to load ends the walk rather than silently
        skipping an unknown number of books - a partial run should be obvious.
        """
        url: Optional[str] = self.settings.base_url
        page_number = 0

        while url:
            if self.settings.max_pages is not None and page_number >= self.settings.max_pages:
                logger.info("Reached the --max-pages limit of %d", self.settings.max_pages)
                return

            logger.info("Listing page %d: %s", page_number + 1, url)
            html = session.get_text(url)
            if html is None:
                logger.error("Could not read listing page, stopping the walk: %s", url)
                return

            listing_records, next_url = parse_listing_page(html, url)
            logger.debug("Found %d products on %s", len(listing_records), url)

            page_number += 1
            self.result.pages_visited = page_number
            yield listing_records, url

            if next_url is None:
                logger.info("No further pagination link found on %s", url)
            url = next_url

    def scrape_book(self, session: PoliteSession, listing_record: dict) -> Optional[dict]:
        """Fetch and parse one detail page, merged with its listing fields.

        Returns None when the page could not be read, so the caller can count it
        as a loss and carry on.
        """
        product_url = listing_record["product_url"]
        html = session.get_text(product_url)
        if html is None:
            logger.warning("Skipping book, detail page unavailable: %s", product_url)
            return None

        record = merge_records(listing_record, parse_detail_page(html, product_url))
        record["slug"] = slug_from_product_url(product_url)
        record["scraped_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return record

    def _is_duplicate(self, record: dict) -> bool:
        """True if this UPC has already been recorded.

        Books with no UPC are let through: the alternative is dropping a real
        book because one field failed to parse.
        """
        upc = record.get("upc")
        if not upc:
            return False
        if upc in self._seen_upcs:
            return True
        self._seen_upcs.add(upc)
        return False

    # -- images ------------------------------------------------------------

    def fetch_cover(self, session: PoliteSession, record: dict) -> None:
        """Download the cover for one record and note the path on it.

        ``image_file`` is stored relative to the output directory so the data
        file stays portable - moving the output folder does not invalidate it.
        """
        record["image_file"] = None
        image_url = record.get("image_url") or record.get("thumbnail_url")
        slug = record.get("slug")

        if not image_url or not slug:
            self.result.images_failed += 1
            logger.warning("No cover URL for %r", record.get("title"))
            return

        # Checked before the call, because download_image returns the same path
        # whether it fetched the file or found it already there.
        already_there = existing_image_for(self.settings.images_dir, slug) is not None
        path = download_image(session, image_url, self.settings.images_dir, slug)

        if path is None:
            self.result.images_failed += 1
            return

        record["image_file"] = path.relative_to(self.settings.output_dir).as_posix()
        if already_there:
            self.result.images_skipped_existing += 1
        else:
            self.result.images_downloaded += 1

    # -- the run -----------------------------------------------------------

    def run(self) -> ScrapeResult:
        """Crawl, download, write. Returns the result and leaves output on disk."""
        settings = self.settings
        settings.ensure_directories()

        started = datetime.now(timezone.utc)
        self.result.started_at = started.isoformat(timespec="seconds")
        logger.info(
            "Starting crawl of %s (images %s, delay %.2fs)",
            settings.base_url,
            "on" if settings.download_images else "off",
            settings.delay,
        )

        with PoliteSession(settings) as session:
            for listing_records, page_url in self.iter_listing_pages(session):
                for listing_record in listing_records:
                    if (
                        settings.max_books is not None
                        and len(self.result.records) >= settings.max_books
                    ):
                        logger.info(
                            "Reached the --limit of %d books", settings.max_books
                        )
                        break

                    record = self.scrape_book(session, listing_record)
                    if record is None:
                        continue

                    if self._is_duplicate(record):
                        self.result.duplicates_skipped += 1
                        logger.debug("Duplicate UPC, skipping: %s", record.get("upc"))
                        continue

                    if settings.download_images:
                        self.fetch_cover(session, record)

                    self.result.records.append(record)
                    if len(self.result.records) % 50 == 0:
                        logger.info("... %d books so far", len(self.result.records))
                else:
                    # Only reached when the inner loop was not broken out of.
                    continue
                break  # the book limit was hit; stop paginating too

            self.result.failures = list(session.failures)

        finished = datetime.now(timezone.utc)
        self.result.finished_at = finished.isoformat(timespec="seconds")
        self.result.duration_seconds = (finished - started).total_seconds()

        write_outputs(self.result.records, settings.data_dir, settings.formats)
        write_summary(self.result.as_summary(), settings.data_dir / "summary.json")

        logger.info(
            "Done: %d books from %d pages in %.1fs (%d covers downloaded, "
            "%d already on disk, %d failed)",
            len(self.result.records),
            self.result.pages_visited,
            self.result.duration_seconds,
            self.result.images_downloaded,
            self.result.images_skipped_existing,
            self.result.images_failed,
        )
        return self.result
