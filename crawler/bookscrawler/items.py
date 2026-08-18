"""The fields the crawler exports (Part 1).

One item per book, listing-page and detail-page fields merged before it is
yielded. Key order in books.json comes from FEED_EXPORT_FIELDS in settings.py.
"""

import scrapy


class BookItem(scrapy.Item):
    """One book. Eight fields the brief asks for, plus currency."""

    # From the listing page
    title = scrapy.Field()          # full title, from the link's title attribute
    price = scrapy.Field()          # float, currency symbol stripped
    currency = scrapy.Field()       # ISO code derived from the symbol
    availability = scrapy.Field()   # e.g. "In stock (22 available)"
    product_url = scrapy.Field()    # absolute URL of the detail page
    image_url = scrapy.Field()      # absolute, full-size where available

    # From the detail page
    upc = scrapy.Field()            # unique product code, used as the dedup key
    category = scrapy.Field()       # from the breadcrumb, e.g. "Poetry"
    description = scrapy.Field()    # null for the 2 books that have none
