"""Offline tests for the parsing, storage and image layers.

No network. The HTML fixtures below are trimmed copies of the real markup -
enough structure to exercise the selectors, small enough to read.

Run from ``requests_scraper/``:

    python -m unittest discover tests
"""

from __future__ import annotations

import csv
import json
import logging
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from books_scraper import parsers, storage  # noqa: E402
from books_scraper.images import (  # noqa: E402
    _extension_for,
    download_image,
    existing_image_for,
    safe_stem,
)

LISTING_HTML = """
<html><body>
<section>
  <ol class="row">
    <li>
      <article class="product_pod">
        <div class="image_container">
          <a href="catalogue/a-light-in-the-attic_1000/index.html">
            <img class="thumbnail" src="media/cache/2c/da/thumb.jpg" alt="A Light in the Attic">
          </a>
        </div>
        <p class="star-rating Three"><i class="icon-star"></i></p>
        <h3><a href="catalogue/a-light-in-the-attic_1000/index.html"
               title="A Light in the Attic">A Light in the ...</a></h3>
        <div class="product_price">
          <p class="price_color">£51.77</p>
          <p class="instock availability"><i class="icon-ok"></i> In stock </p>
        </div>
      </article>
    </li>
    <li>
      <article class="product_pod">
        <h3><a>No link here</a></h3>
        <p class="price_color">£10.00</p>
      </article>
    </li>
  </ol>
  <ul class="pager"><li class="next"><a href="catalogue/page-2.html">next</a></li></ul>
</section>
</body></html>
"""

DETAIL_HTML = """
<html><body>
<ul class="breadcrumb">
  <li><a href="../../index.html">Home</a></li>
  <li><a href="../category/books_1/index.html">Books</a></li>
  <li><a href="../category/books/poetry_23/index.html">Poetry</a></li>
  <li class="active">A Light in the Attic</li>
</ul>
<div id="content_inner">
  <div id="product_gallery">
    <div class="thumbnail"><img src="../../media/cache/fe/72/full.jpg" alt="A Light in the Attic"></div>
  </div>
  <div class="col-sm-6 product_main">
    <h1>A Light in the Attic</h1>
    <p class="price_color">£51.77</p>
    <p class="instock availability"><i class="icon-ok"></i> In stock (22 available) </p>
    <p class="star-rating Three"><i class="icon-star"></i></p>
  </div>
</div>
<div id="product_description" class="sub-header"><h2>Product Description</h2></div>
<p>It's hard to imagine a world without A Light in It's hard to imagine a world
without A Light in the Attic. ...more</p>
<table class="table table-striped">
  <tr><th>UPC</th><td>a897fe39b1053632</td></tr>
  <tr><th>Product Type</th><td>Books</td></tr>
  <tr><th>Price (excl. tax)</th><td>£51.77</td></tr>
  <tr><th>Price (incl. tax)</th><td>£51.77</td></tr>
  <tr><th>Tax</th><td>£0.00</td></tr>
  <tr><th>Availability</th><td>In stock (22 available)</td></tr>
  <tr><th>Number of reviews</th><td>0</td></tr>
</table>
<!-- The recommendation strip below carries its own .availability nodes, which
     the detail selector must not pick up. -->
<div class="alert"><article class="product_pod">
  <p class="instock availability">In stock</p>
</article></div>
</body></html>
"""

def setUpModule() -> None:
    """Silence the modules' own warning logs; these tests assert on returns."""
    logging.disable(logging.CRITICAL)


def tearDownModule() -> None:
    logging.disable(logging.NOTSET)


LISTING_URL = "https://books.toscrape.com/index.html"
DETAIL_URL = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"


class ListingPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.books, self.next_url = parsers.parse_listing_page(LISTING_HTML, LISTING_URL)

    def test_skips_pods_without_a_detail_link(self) -> None:
        self.assertEqual(len(self.books), 1)

    def test_prefers_the_untruncated_title_attribute(self) -> None:
        self.assertEqual(self.books[0]["title"], "A Light in the Attic")

    def test_price_is_numeric_with_a_currency_code(self) -> None:
        self.assertEqual(self.books[0]["price"], 51.77)
        self.assertEqual(self.books[0]["currency"], "GBP")

    def test_rating_word_becomes_a_number(self) -> None:
        self.assertEqual(self.books[0]["rating"], 3)

    def test_urls_are_absolute(self) -> None:
        self.assertEqual(self.books[0]["product_url"], DETAIL_URL)
        self.assertEqual(
            self.books[0]["thumbnail_url"],
            "https://books.toscrape.com/media/cache/2c/da/thumb.jpg",
        )

    def test_next_page_is_resolved_against_the_current_page(self) -> None:
        self.assertEqual(self.next_url, "https://books.toscrape.com/catalogue/page-2.html")

    def test_last_page_reports_no_next_url(self) -> None:
        _, next_url = parsers.parse_listing_page(
            LISTING_HTML.replace('<li class="next">', "<li>"), LISTING_URL
        )
        self.assertIsNone(next_url)


class DetailPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = parsers.parse_detail_page(DETAIL_HTML, DETAIL_URL)

    def test_reads_the_product_information_table_by_header(self) -> None:
        self.assertEqual(self.record["upc"], "a897fe39b1053632")
        self.assertEqual(self.record["price"], 51.77)
        self.assertEqual(self.record["price_excl_tax"], 51.77)
        self.assertEqual(self.record["tax"], 0.0)
        self.assertEqual(self.record["review_count"], 0)

    def test_category_comes_from_the_last_breadcrumb_link(self) -> None:
        self.assertEqual(self.record["category"], "Poetry")

    def test_availability_ignores_the_recommendation_strip(self) -> None:
        self.assertEqual(self.record["availability"], "In stock (22 available)")
        self.assertEqual(self.record["stock_count"], 22)

    def test_description_teaser_is_removed(self) -> None:
        self.assertEqual(
            self.record["description"],
            "It's hard to imagine a world without A Light in the Attic.",
        )

    def test_image_url_is_the_full_size_gallery_image(self) -> None:
        self.assertEqual(
            self.record["image_url"],
            "https://books.toscrape.com/media/cache/fe/72/full.jpg",
        )

    def test_missing_description_block_yields_none(self) -> None:
        without = DETAIL_HTML.replace('id="product_description"', 'id="something_else"')
        self.assertIsNone(parsers.parse_detail_page(without, DETAIL_URL)["description"])


class MergeTests(unittest.TestCase):
    def test_detail_wins_and_listing_fills_the_gaps(self) -> None:
        listing, _ = parsers.parse_listing_page(LISTING_HTML, LISTING_URL)
        detail = parsers.parse_detail_page(DETAIL_HTML, DETAIL_URL)
        merged = parsers.merge_records(listing[0], detail)

        # Detail's availability carries the stock count the listing lacks.
        self.assertEqual(merged["availability"], "In stock (22 available)")
        # And the listing's thumbnail survives, because detail has no such key.
        self.assertEqual(
            merged["thumbnail_url"],
            "https://books.toscrape.com/media/cache/2c/da/thumb.jpg",
        )

    def test_listing_value_survives_a_null_detail_value(self) -> None:
        merged = parsers.merge_records({"title": "Kept"}, {"title": None})
        self.assertEqual(merged["title"], "Kept")


class SlugTests(unittest.TestCase):
    def test_index_html_urls(self) -> None:
        self.assertEqual(parsers.slug_from_product_url(DETAIL_URL), "a-light-in-the-attic_1000")

    def test_urls_without_index_html(self) -> None:
        self.assertEqual(
            parsers.slug_from_product_url("https://books.toscrape.com/catalogue/tipping_1/"),
            "tipping_1",
        )

    def test_empty_path(self) -> None:
        self.assertIsNone(parsers.slug_from_product_url("https://books.toscrape.com/"))


class ImageExtensionTests(unittest.TestCase):
    def test_content_type_decides(self) -> None:
        self.assertEqual(_extension_for("image/jpeg", "http://x/y"), ".jpg")
        self.assertEqual(_extension_for("image/png; charset=binary", "http://x/y"), ".png")

    def test_non_image_is_rejected(self) -> None:
        self.assertIsNone(_extension_for("text/html", "http://x/y.jpg"))

    def test_missing_content_type_falls_back_to_the_url(self) -> None:
        self.assertEqual(_extension_for(None, "http://x/cover.png"), ".png")
        self.assertEqual(_extension_for(None, "http://x/cover"), ".jpg")


class _FakeResponse:
    """The two attributes download_image reads off a response."""

    def __init__(self, content: bytes = b"\xff\xd8\xff-jpeg-bytes", content_type: str = "image/jpeg"):
        self.content = content
        self.headers = {"Content-Type": content_type} if content_type else {}


class _FakeSession:
    """Stands in for PoliteSession; records what it was asked for."""

    def __init__(self, response: object | None) -> None:
        self._response = response
        self.requested: list[str] = []

    def get(self, url: str) -> object | None:
        self.requested.append(url)
        return self._response


class SafeStemTests(unittest.TestCase):
    def test_short_slugs_pass_through(self) -> None:
        self.assertEqual(safe_stem("sharp-objects_997"), "sharp-objects_997")

    def test_long_slugs_are_truncated_but_keep_the_product_id(self) -> None:
        # The real slug that overran Windows' 260-character path limit.
        slug = (
            "at-the-existentialist-cafe-freedom-being-and-apricot-cocktails-with-"
            "jean-paul-sartre-simone-de-beauvoir-albert-camus-martin-heidegger-"
            "edmund-husserl-karl-jaspers-maurice-merleau-ponty-and-others_459"
        )
        stem = safe_stem(slug)
        self.assertLessEqual(len(stem), 100)
        self.assertTrue(stem.endswith("_459"))
        self.assertTrue(stem.startswith("at-the-existentialist-cafe"))

    def test_two_long_slugs_sharing_a_prefix_stay_distinct(self) -> None:
        prefix = "the-same-opening-words-repeated-at-length-" * 4
        self.assertNotEqual(safe_stem(prefix + "_1"), safe_stem(prefix + "_2"))

    def test_illegal_characters_are_replaced(self) -> None:
        self.assertEqual(safe_stem('a:b*c?_1'), "a-b-c-_1")


class DownloadImageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_writes_the_file_and_returns_its_path(self) -> None:
        session = _FakeSession(_FakeResponse())
        path = download_image(session, "http://x/cover.jpg", self.dir, "sharp-objects_997")
        self.assertEqual(path, self.dir / "sharp-objects_997.jpg")
        self.assertTrue(path.read_bytes())

    def test_second_call_skips_the_network(self) -> None:
        session = _FakeSession(_FakeResponse())
        download_image(session, "http://x/cover.jpg", self.dir, "sharp-objects_997")
        download_image(session, "http://x/cover.jpg", self.dir, "sharp-objects_997")
        self.assertEqual(len(session.requested), 1)

    def test_a_long_slug_still_lands_on_disk(self) -> None:
        slug = "x" * 200 + "_459"
        session = _FakeSession(_FakeResponse())
        path = download_image(session, "http://x/cover.jpg", self.dir, slug)
        self.assertIsNotNone(path)
        self.assertTrue(path.is_file())
        self.assertIsNotNone(existing_image_for(self.dir, slug))

    def test_a_non_image_response_writes_nothing(self) -> None:
        session = _FakeSession(_FakeResponse(b"<html>404</html>", "text/html"))
        self.assertIsNone(download_image(session, "http://x/cover.jpg", self.dir, "s_1"))
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_an_empty_body_writes_nothing(self) -> None:
        session = _FakeSession(_FakeResponse(b""))
        self.assertIsNone(download_image(session, "http://x/cover.jpg", self.dir, "s_1"))
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_a_failed_request_is_not_an_exception(self) -> None:
        self.assertIsNone(download_image(_FakeSession(None), "http://x/c.jpg", self.dir, "s_1"))

    def test_a_zero_length_leftover_is_not_treated_as_downloaded(self) -> None:
        (self.dir / "s_1.jpg").touch()
        session = _FakeSession(_FakeResponse())
        download_image(session, "http://x/cover.jpg", self.dir, "s_1")
        self.assertEqual(len(session.requested), 1)
        self.assertTrue((self.dir / "s_1.jpg").stat().st_size > 0)


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.records = [
            {"title": "Café Noir", "upc": "1", "price": 51.77, "stray_key": "dropped"},
            {"title": "Second", "upc": "2"},
        ]
        self.addCleanup(self._tmp.cleanup)

    def test_json_keeps_the_declared_schema_and_drops_extras(self) -> None:
        path = storage.write_json(self.records, self.dir / "books.json")
        written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(list(written[0]), list(storage.FIELD_ORDER))
        self.assertNotIn("stray_key", written[0])
        self.assertEqual(written[0]["title"], "Café Noir")
        self.assertIsNone(written[1]["price"])

    def test_csv_columns_match_the_json_keys(self) -> None:
        path = storage.write_csv(self.records, self.dir / "books.csv")
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(list(rows[0]), list(storage.FIELD_ORDER))
        self.assertEqual(rows[0]["price"], "51.77")

    def test_no_part_files_are_left_behind(self) -> None:
        storage.write_json(self.records, self.dir / "books.json")
        storage.write_csv(self.records, self.dir / "books.csv")
        self.assertEqual(list(self.dir.glob("*.part")), [])

    def test_field_coverage_counts_populated_values_only(self) -> None:
        coverage = storage.field_coverage(self.records)
        self.assertEqual(coverage["title"], 2)
        self.assertEqual(coverage["price"], 1)
        self.assertEqual(coverage["description"], 0)


if __name__ == "__main__":
    unittest.main()
