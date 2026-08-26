"""A requests-based scraper for books.toscrape.com.

Collects one record per book - title, price, availability, rating, UPC,
category, description - and downloads each book's cover image.

The package splits along the lines of "what changes for what reason":

* :mod:`config`      run settings, one dataclass, no globals
* :mod:`http_client` the network: session, retries, backoff, politeness
* :mod:`parsers`     HTML in, typed values out; pure and offline-testable
* :mod:`images`      cover downloads to disk
* :mod:`storage`     JSON / CSV writers and the run summary
* :mod:`scraper`     the traversal that ties the above together
* :mod:`cli`         argument parsing and logging setup

Public entry point:

    from books_scraper import BooksScraper, Settings
"""

from books_scraper.config import Settings
from books_scraper.scraper import BooksScraper, ScrapeResult

__all__ = ["BooksScraper", "ScrapeResult", "Settings"]
__version__ = "1.0.0"
