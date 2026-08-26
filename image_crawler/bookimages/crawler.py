"""Crawl orchestration for both tasks."""

import logging

from . import config, parsers
from .downloader import ImageDownloader
from .http_client import HttpClient

log = logging.getLogger(__name__)


class BooksCrawler:
    """Walks categories -> listing pages -> product pages -> cover images."""

    def __init__(self, client=None, output_root=config.OUTPUT_DIR, overwrite=False):
        self.client = client or HttpClient()
        self.downloader = ImageDownloader(self.client, output_root / "images",
                                          overwrite=overwrite)

    # ---------------------------------------------------------------- discovery

    def list_categories(self):
        """Every category in the sidebar, in site order."""
        html = self.client.get_html(config.INDEX_URL)
        return parsers.parse_categories(html, config.INDEX_URL)

    def resolve_categories(self, wanted):
        """Match requested names against the site's categories (case-insensitive)."""
        available = self.list_categories()
        by_name = {c["name"].lower(): c for c in available}
        resolved, missing = [], []
        for name in wanted:
            match = by_name.get(name.strip().lower())
            (resolved.append(match) if match else missing.append(name))
        if missing:
            raise SystemExit(
                "Unknown category name(s): %s\nAvailable: %s"
                % (", ".join(missing), ", ".join(c["name"] for c in available))
            )
        return resolved

    def product_urls(self, category, limit=None):
        """Product page URLs for a category, following pagination as needed."""
        urls, page_url = [], category["url"]
        while page_url:
            page_products, page_url = parsers.parse_listing(
                self.client.get_html(page_url), page_url
            )
            urls.extend(page_products)
            if limit is not None and len(urls) >= limit:
                return urls[:limit]
        return urls

    # ----------------------------------------------------------------- crawling

    def crawl_category(self, category, limit=None):
        """Visit each product page in a category, then GET its cover image."""
        target = self.product_urls(category, limit=limit)
        log.info("[%s] %d product page(s) to visit", category["name"], len(target))

        books = []
        for index, url in enumerate(target, start=1):
            book = parsers.parse_product(self.client.get_html(url), url)
            # The image is fetched only after the product page has been visited,
            # because the full-size image URL lives on that page.
            result = self.downloader.download(book["image_url"],
                                              book["category"] or category["name"],
                                              book["title"])
            book["image_status"] = result["status"]
            book["image_path"] = result["path"]
            book["image_bytes"] = result.get("bytes")
            books.append(book)
            log.info("[%s] %d/%d %s", category["name"], index, len(target), book["title"])
        return books

    def crawl(self, categories, limit=None):
        """Crawl several categories; returns {category_name: [book, ...]}."""
        results = {}
        for category in categories:
            results[category["name"]] = self.crawl_category(category, limit=limit)
        return results

    def close(self):
        self.client.close()
