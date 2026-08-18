"""Item pipelines: things that need the whole run, not one page (Part 1).

DuplicateBookPipeline (100) drops products already seen, keyed on UPC.
RequiredFieldsPipeline (200) counts missing values and reports at the end.
Order is set in settings.py: dedup first, so coverage describes what shipped.

Why dedup here when Scrapy already has RFPDupeFilter? That filter stops the
same URL being fetched twice. It does not stop the same product arriving via
two different URLs.

Neither class takes a spider argument - Scrapy 2.17 warns that signature is
deprecated - so both log through a module logger.
"""

import logging

from scrapy.exceptions import DropItem

logger = logging.getLogger(__name__)


class DuplicateBookPipeline:
    """Drop books already seen in this crawl.

    Keyed on UPC, the site's own product code. Falls back to product_url when
    UPC is missing, so UPC-less items do not all collapse into one.
    """

    def __init__(self):
        self.seen_keys = set()
        self.duplicates_dropped = 0

    def process_item(self, item):
        """Return the item, or raise DropItem if its key was already seen."""
        key = item.get("upc") or item.get("product_url")

        if key is None:
            # Nothing to identify it by. Let it through and let the next
            # pipeline flag it, rather than quietly dropping data.
            logger.warning("Item without UPC or product_url: %r", item.get("title"))
            return item

        if key in self.seen_keys:
            self.duplicates_dropped += 1
            raise DropItem(f"Duplicate product: {key}")

        self.seen_keys.add(key)
        return item

    def close_spider(self):
        """Log the unique and duplicate tallies when the crawl finishes."""
        logger.info(
            "Duplicate check: %d unique products, %d duplicates dropped",
            len(self.seen_keys),
            self.duplicates_dropped,
        )


class RequiredFieldsPipeline:
    """Count items missing any required field and report at the end.

    Warns rather than drops. A book with no description is still useful, and
    dropping it would hide the problem. The end-of-run counts are the signal:
    if description jumps from 2 missing to 900, a selector has broken.
    """

    REQUIRED_FIELDS = (
        "title",
        "price",
        "availability",
        "category",
        "upc",
        "description",
        "product_url",
        "image_url",
    )

    def __init__(self):
        self.missing_counts = {field: 0 for field in self.REQUIRED_FIELDS}
        self.items_seen = 0

    def process_item(self, item):
        """Count missing required fields and return the item unchanged."""
        self.items_seen += 1
        missing = [f for f in self.REQUIRED_FIELDS if item.get(f) in (None, "")]

        for field in missing:
            self.missing_counts[field] += 1

        if missing:
            logger.warning(
                "Incomplete item (%s missing) at %s",
                ", ".join(missing),
                item.get("product_url"),
            )
        return item

    def close_spider(self):
        """Report per-field coverage when the crawl finishes."""
        problems = {f: c for f, c in self.missing_counts.items() if c}
        if problems:
            logger.warning(
                "Field coverage over %d items - missing values: %s",
                self.items_seen,
                problems,
            )
        else:
            logger.info(
                "Field coverage: all %d items have every required field.",
                self.items_seen,
            )
