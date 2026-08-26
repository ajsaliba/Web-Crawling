"""The network layer: one requests.Session, used for every fetch.

Why a session rather than bare ``requests.get``: it keeps the TCP connection to
books.toscrape.com alive across ~2,000 requests, and it is the only place an
adapter-level retry policy can be installed.

Three things this module handles that a naive ``requests.get`` does not:

1. **Retries with backoff** for connection errors and 429 / 5xx responses, so a
   single hiccup does not abort a ten-minute crawl.
2. **Encoding.** The server declares ``ISO-8859-1`` while actually serving
   UTF-8, which turns "£51.77" into "Â£51.77". We override the declared value.
3. **Politeness.** A fixed delay between requests, measured from the end of the
   previous one, so a slow response does not stack a delay on top of it.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from books_scraper.config import Settings

logger = logging.getLogger(__name__)

#: Retried automatically. 429 is included so a rate limit backs off rather than
#: being recorded as a permanent failure.
_RETRY_STATUS = (429, 500, 502, 503, 504)


class PoliteSession:
    """A requests.Session with retries, a timeout, and a delay between calls.

    Not thread-safe, deliberately: the crawl is sequential, and a shared
    "time of last request" only means anything for one caller.

    Use it as a context manager so the underlying connection pool is closed::

        with PoliteSession(settings) as session:
            html = session.get_text(settings.base_url)
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session = self._build_session(settings)
        self._last_request_at: float = 0.0
        #: Requests that failed after exhausting retries. Reported in the run
        #: summary so a partial crawl is visibly partial.
        self.failures: list[tuple[str, str]] = []

    @staticmethod
    def _build_session(settings: Settings) -> requests.Session:
        """Create the session and mount the retrying adapter on both schemes."""
        retry = Retry(
            total=settings.max_retries,
            connect=settings.max_retries,
            read=settings.max_retries,
            status=settings.max_retries,
            status_forcelist=_RETRY_STATUS,
            allowed_methods=frozenset(["GET", "HEAD"]),
            # 0.5s, 1s, 2s ... enough to ride out a blip without stalling a run.
            backoff_factor=0.5,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)

        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update(
            {
                "User-Agent": settings.user_agent,
                "Accept-Language": "en-GB,en;q=0.9",
            }
        )
        return session

    def _wait_turn(self) -> None:
        """Sleep out whatever is left of the politeness delay."""
        if self._settings.delay <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = self._settings.delay - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def get(self, url: str) -> Optional[requests.Response]:
        """Fetch ``url``. Returns None instead of raising on failure.

        One unreachable page should cost one book, not the whole run, so
        failures are logged and recorded rather than propagated. Callers decide
        what a missing response means for them.
        """
        self._wait_turn()
        try:
            response = self._session.get(url, timeout=self._settings.timeout)
        except requests.RequestException as exc:
            logger.warning("Request failed: %s (%s)", url, exc)
            self.failures.append((url, str(exc)))
            return None
        finally:
            self._last_request_at = time.monotonic()

        if response.status_code >= 400:
            logger.warning("HTTP %s for %s", response.status_code, url)
            self.failures.append((url, f"HTTP {response.status_code}"))
            return None

        return response

    def get_text(self, url: str) -> Optional[str]:
        """Fetch ``url`` and return decoded HTML, or None on failure.

        The encoding override is the point of this method: books.toscrape.com
        sends no charset for HTML, so requests falls back to the HTTP default of
        ISO-8859-1 and mojibakes every "£". The pages are UTF-8.
        """
        response = self.get(url)
        if response is None:
            return None

        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    def close(self) -> None:
        """Release the connection pool."""
        self._session.close()

    def __enter__(self) -> "PoliteSession":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
