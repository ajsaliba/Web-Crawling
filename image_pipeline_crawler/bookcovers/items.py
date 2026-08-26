"""The fields this crawler carries.

The brief asks for two things in the output - title and absolute cover URL -
so those are the only two fields ``FEED_EXPORT_FIELDS`` exports.

``category`` is a third field because the pipeline needs it to build
``downloaded_images/<category>/``, and the breadcrumb that holds it only
exists on the product page. Carrying it on the item is how the spider hands
it to the pipeline; keeping it out of ``FEED_EXPORT_FIELDS`` is how the
exported file still contains only the two fields asked for.
"""

import scrapy


class BookCoverItem(scrapy.Item):
    """One book's cover: what to output, plus what the pipeline needs."""

    # Exported.
    title = scrapy.Field()      # full title, from the product page's <h1>
    image_url = scrapy.Field()  # absolute URL of the full-size cover

    # Not exported - used by CoverImagePipeline to pick the directory.
    category = scrapy.Field()   # from the breadcrumb, e.g. "Science"
