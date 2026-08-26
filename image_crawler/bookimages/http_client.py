"""A thin, polite HTTP layer: one shared session, retries, throttling."""

import logging
import time

import requests

from . import config

log = logging.getLogger(__name__)


class HttpClient:
    """Wraps requests.Session with a delay between calls and bounded retries."""

    def __init__(self, delay=config.REQUEST_DELAY, timeout=config.TIMEOUT,
                 max_retries=config.MAX_RETRIES):
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.USER_AGENT})
        self._last_request = 0.0
        self.request_count = 0

    def _throttle(self):
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request = time.monotonic()

    def get(self, url, stream=False):
        """GET a URL, retrying transient failures. Returns a Response."""
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                response = self.session.get(url, timeout=self.timeout, stream=stream)
                self.request_count += 1
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                log.warning("GET failed (%s/%s) %s -> %s",
                            attempt, self.max_retries, url, exc)
                if attempt < self.max_retries:
                    time.sleep(config.RETRY_BACKOFF * attempt)
        raise RuntimeError("giving up on %s: %s" % (url, last_error))

    def get_html(self, url):
        """GET a page and return its decoded HTML."""
        response = self.get(url)
        response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
