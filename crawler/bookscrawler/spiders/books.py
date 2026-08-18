"""Spider for books.toscrape.com (Part 1).

Reads each listing page, follows every product to its detail page, and merges
both halves into one item. Listing fields ride along in ``cb_kwargs`` so each
product costs one request. Pagination stops when the site stops offering a
"next" link, so the page count is never hard-coded.

Run from ``crawler/``:  scrapy crawl books -O ../books.json
"""

from typing import Any, Dict, Iterable

import scrapy
from scrapy.http import Response

from bookscrawler.items import BookItem
from bookscrawler.parsers import clean_text, parse_price, strip_truncated_preview


class BooksSpider(scrapy.Spider):
    """Crawl every book in the catalogue, listing pages plus detail pages."""

    name = "books"
    allowed_domains = ["books.toscrape.com"]
    start_urls = ["https://books.toscrape.com/"]

    def parse(self, response: Response) -> Iterable[scrapy.Request]:
        """Queue every product on this listing page, then the next page."""
        products = response.css("article.product_pod")
        self.logger.debug("Found %d products on %s", len(products), response.url)

        for product in products:
            listing_fields = self._parse_listing_entry(product, response)
            detail_href = product.css("h3 a::attr(href)").get()

            if not detail_href:
                # No detail URL means no UPC and no dedup key, so skip rather
                # than emit something that looks complete but is not.
                self.logger.warning(
                    "Product pod without a detail link on %s: %r",
                    response.url,
                    listing_fields.get("title"),
                )
                continue

            # follow() resolves the relative href for us, and behaves the same
            # on the home page ("catalogue/page-2.html") as inside /catalogue/.
            yield response.follow(
                detail_href,
                callback=self.parse_product,
                cb_kwargs={"listing_fields": listing_fields},
            )

        next_page = response.css("li.next a::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)
        else:
            self.logger.info("No further pagination link found on %s", response.url)

    def _parse_listing_entry(
        self, product: scrapy.Selector, response: Response
    ) -> Dict[str, Any]:
        """Pull the listing-page half of an item out of one product pod.

        Everything uses .get(), so a malformed pod yields empty fields rather
        than raising.
        """
        # Anchor text is truncated ("A Light in the ..."); the title attribute
        # has the full string.
        title = product.css("h3 a::attr(title)").get() or clean_text(
            product.css("h3 a::text").getall()
        )

        price, currency = parse_price(product.css(".price_color::text").get())

        return {
            "title": clean_text([title]),
            "price": price,
            "currency": currency,
            "availability": clean_text(product.css(".availability::text").getall()),
            "image_url": response.urljoin(product.css("img::attr(src)").get() or "")
            or None,
        }

    def parse_product(
        self, response: Response, listing_fields: Dict[str, Any]
    ) -> Iterable[BookItem]:
        """Merge the listing fields with the detail-page fields into one item."""
        product_info = self._parse_product_information_table(response)

        item = BookItem()
        item.update(listing_fields)

        item["product_url"] = response.url
        item["upc"] = product_info.get("UPC")
        item["category"] = self._parse_category(response)
        item["description"] = self._parse_description(response)

        # Detail page wins here: it has the stock count the listing omits.
        # Scoping to .product_main matters, because the "you may also like"
        # tiles below carry their own .availability nodes.
        detail_availability = clean_text(
            response.css(".product_main p.availability::text").getall()
        )
        if detail_availability:
            item["availability"] = detail_availability

        # Full-size gallery image, falling back to the listing thumbnail.
        full_size = response.css("#product_gallery img::attr(src)").get()
        if full_size:
            item["image_url"] = response.urljoin(full_size)

        if item.get("price") is None:
            price, currency = parse_price(
                response.css(".price_color::text").get()
                or product_info.get("Price (incl. tax)")
            )
            item["price"] = price
            item["currency"] = currency

        if not item.get("title"):
            item["title"] = clean_text(response.css("div.product_main h1::text").getall())

        yield item

    @staticmethod
    def _parse_product_information_table(response: Response) -> Dict[str, str]:
        """Read the Product Information table into {header: value}.

        Keyed on the row header, not row position, so an extra or reordered
        row cannot put the wrong value into UPC.
        """
        table: Dict[str, str] = {}
        for row in response.css("table.table-striped tr"):
            header = clean_text(row.css("th::text").getall())
            if header:
                table[header] = clean_text(row.css("td::text").getall())
        return table

    @staticmethod
    def _parse_category(response: Response) -> str:
        """Return the breadcrumb category, or None if it is missing.

        Breadcrumb runs Home > Books > Category > Title, and the title is not
        a link, so the category is the last anchor. The table's "Product Type"
        row is always "Books", so it is no use here.
        """
        links = response.css("ul.breadcrumb li a::text").getall()
        if len(links) < 3:
            return None
        return clean_text([links[-1]])

    @staticmethod
    def _parse_description(response: Response) -> str:
        """Return the description paragraph, or None if the page has none."""
        paragraph = response.css("#product_description ~ p::text").get()
        return strip_truncated_preview(clean_text([paragraph]))
