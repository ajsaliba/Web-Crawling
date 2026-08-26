"""Spider for books.toscrape.com cover images.

Traversal is expressed as CrawlSpider rules rather than hand-written
``response.follow`` calls, because the brief is written as URL filtering
rules and that is what a ``LinkExtractor`` is.

Two optional arguments narrow the crawl:

    scrapy crawl book_spider -a category="Science" -a title_keyword="robot"

Both default to off, so with no arguments the spider walks the whole
catalogue. Run from ``image_pipeline_crawler/``, where ``scrapy.cfg`` lives.
"""

import re
from typing import Iterable, List, Optional

from scrapy.http import Request, Response
from scrapy.linkextractors import LinkExtractor
from scrapy.link import Link
from scrapy.spiders import CrawlSpider, Rule

from bookcovers.items import BookCoverItem
from bookcovers.naming import clean_text, slugify

# Category pages live at /catalogue/category/books/<slug>_<id>/, and their
# pagination at .../<slug>_<id>/page-2.html. The trailing id is the site's,
# not part of the name, so it is stripped before comparing.
_CATEGORY_PATH_RE = re.compile(r"/catalogue/category/books/(?P<slug>[^/]+)/")
_CATEGORY_ID_SUFFIX_RE = re.compile(r"_\d+$")


def category_slug_from_url(url: str) -> Optional[str]:
    """Return the category a catalogue URL belongs to, or None.

    Works for both a category index and its pagination, because the slug is a
    path segment both share. Returns None for the site-wide listing pages,
    which is what lets ``-a category=`` exclude them.
    """
    match = _CATEGORY_PATH_RE.search(url)
    if not match:
        return None
    return slugify(_CATEGORY_ID_SUFFIX_RE.sub("", match.group("slug")))


class BookSpider(CrawlSpider):
    """Crawl product pages and yield one cover per book."""

    name = "book_spider"
    allowed_domains = ["books.toscrape.com"]
    start_urls = ["https://books.toscrape.com/"]

    # The simple filtering rule from the brief, used verbatim.
    PRODUCT_URL_PATTERN = r"/catalogue/.*\.html"

    # ...and the two things that pattern also matches but which are not
    # products: category index pages, and any listing page N. Without these
    # the spider would parse a listing page as a book and find no <h1>.
    NOT_A_PRODUCT_PATTERNS = [r"/catalogue/category/", r"/page-\d+\.html"]

    # Pages worth walking for links: category indexes and site-wide paging.
    NAVIGATION_PATTERNS = [r"/catalogue/category/books/", r"/catalogue/page-\d+\.html"]

    rules = (
        # Products are leaves: follow defaults to False when a callback is
        # given, so the "you may also like" links on a product page are not
        # followed. process_request then drops product links found on a page
        # outside -a category - the home page's own listing being the case
        # that makes it necessary.
        Rule(
            LinkExtractor(
                allow=PRODUCT_URL_PATTERN,
                deny=NOT_A_PRODUCT_PATTERNS,
            ),
            callback="parse_book",
            process_request="only_from_requested_category",
        ),
        # Navigation carries no callback, only follow=True.
        Rule(
            LinkExtractor(allow=NAVIGATION_PATTERNS),
            process_links="keep_requested_category",
            follow=True,
        ),
    )

    def __init__(
        self,
        category: Optional[str] = None,
        title_keyword: Optional[str] = None,
        *args,
        **kwargs,
    ):
        """Accept the two optional filters Scrapy passes through from ``-a``.

        Both arrive as strings, and an empty one means "not given" rather than
        "match nothing" - ``-a category=`` should not silently crawl zero
        pages.
        """
        super().__init__(*args, **kwargs)

        self.category = (category or "").strip() or None
        self.title_keyword = (title_keyword or "").strip() or None

        # Compared as slugs, so -a category="Science Fiction", "science
        # fiction" and "science-fiction" all reach the same pages.
        self.wanted_category_slug = slugify(self.category) if self.category else None
        # Casefold, not lower: correct for non-ASCII, and the brief's example
        # ("robot" against "Robot") only needs case-insensitivity.
        self.wanted_keyword = self.title_keyword.casefold() if self.title_keyword else None

        self.books_seen = 0
        self.books_filtered_out = 0

    def keep_requested_category(self, links: List[Link]) -> List[Link]:
        """Drop navigation links outside the requested category.

        Called by the navigation rule for every page of links it extracts.
        With no ``-a category`` this is a pass-through and the whole catalogue
        is crawled.

        Filtering here rather than in the callback is the point of the
        exercise: the pages are never requested at all, so ``-a
        category="Science"`` costs a handful of requests instead of a thousand.
        """
        if self.wanted_category_slug is None:
            return links

        return [
            link
            for link in links
            if category_slug_from_url(link.url) == self.wanted_category_slug
        ]

    def only_from_requested_category(
        self, request: Request, response: Response
    ) -> Optional[Request]:
        """Drop product links found on a page outside the requested category.

        ``keep_requested_category`` narrows navigation, but that is not enough
        on its own: the home page is the start URL, and its listing shows the
        first 20 books of the whole catalogue. Those links match the product
        pattern and would be crawled regardless of ``-a category``.

        ``process_request`` is the hook that can see *where a link was found*,
        which is what the decision needs. Returning None drops the request.
        """
        if self.wanted_category_slug is None:
            return request
        if category_slug_from_url(response.url) == self.wanted_category_slug:
            return request
        return None

    def parse_book(self, response: Response) -> Iterable[BookCoverItem]:
        """Yield the title and absolute cover URL for one product page."""
        title = clean_text(response.css("div.product_main h1::text").getall())

        if not self._title_matches(title):
            self.books_filtered_out += 1
            return

        self.books_seen += 1

        # #product_gallery holds the full-size cover (~50 KB). The listing
        # pages carry a separate, downscaled rendition of the same artwork, so
        # the URL has to come from the product page, not the pod we arrived
        # from.
        image_src = response.css("#product_gallery img::attr(src)").get()
        if not image_src:
            # Yield anyway rather than dropping it. A book with no cover is a
            # visible null in the output; a book quietly missing from the
            # output looks like the crawl was simply shorter.
            self.logger.warning("No cover image found on %s", response.url)

        yield BookCoverItem(
            title=title,
            # The site serves relative srcs ("../../media/cache/..."), and the
            # brief asks for absolute. urljoin resolves against the page URL.
            image_url=response.urljoin(image_src) if image_src else None,
            category=self._parse_category(response),
        )

    def _title_matches(self, title: Optional[str]) -> bool:
        """Return whether this book passes the ``-a title_keyword`` filter.

        The filter is applied here, not in the pipeline, so the exported rows
        and the files on disk always describe the same set of books. It also
        means a filtered run does no image downloads it will not keep.
        """
        if self.wanted_keyword is None:
            return True
        if not title:
            return False
        return self.wanted_keyword in title.casefold()

    @staticmethod
    def _parse_category(response: Response) -> Optional[str]:
        """Return the breadcrumb category, or None if it is missing.

        The breadcrumb runs Home > Books > Category > Title, and the title is
        not a link, so the category is the last anchor. The Product
        Information table is no help: its "Product Type" row is always "Books".
        """
        links = response.css("ul.breadcrumb li a::text").getall()
        if len(links) < 3:
            return None
        return clean_text([links[-1]])

    def closed(self, reason: str) -> None:
        """Report what the filters did, so an empty run explains itself."""
        self.logger.info(
            "Finished (%s): %d books yielded, %d skipped by title_keyword=%r, "
            "category=%r",
            reason,
            self.books_seen,
            self.books_filtered_out,
            self.title_keyword,
            self.category,
        )
