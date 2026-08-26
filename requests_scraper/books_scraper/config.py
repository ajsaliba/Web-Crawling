"""Run settings for the scraper.

One frozen dataclass rather than module-level constants, so a test or a second
run in the same process can use different settings without mutating shared
state. Defaults are the values a plain ``python -m books_scraper`` uses; the
CLI overrides fields from flags.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Repository-relative default output root: requests_scraper/output.
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"

#: Identifies the client honestly instead of impersonating a browser. The site
#: is a public scraping sandbox, but the habit is what matters on real targets.
DEFAULT_USER_AGENT = (
    "books-scraper/1.0 (+https://books.toscrape.com; educational scraping exercise)"
)


@dataclass(frozen=True)
class Settings:
    """Everything one run needs to know.

    Attributes:
        base_url: Catalogue entry point. Every other URL is resolved against
            the page it was found on, so only this one is hard-coded.
        output_dir: Root for ``data/``, ``images/`` and ``logs/``.
        delay: Seconds to wait between requests. Politeness, not rate limiting -
            the scraper is single-threaded by design.
        timeout: Per-request timeout in seconds (connect and read).
        max_retries: Retries for transient failures (connection errors and
            5xx / 429 responses). Applied by urllib3, with backoff.
        max_pages: Stop after this many listing pages. ``None`` means "until
            the site stops offering a next link".
        max_books: Stop after this many books. ``None`` means no cap.
        download_images: Whether to fetch cover images.
        formats: Output formats to write. Supported: ``json``, ``csv``.
        user_agent: Sent on every request, including image downloads.
    """

    base_url: str = "https://books.toscrape.com/"
    output_dir: Path = DEFAULT_OUTPUT_DIR
    delay: float = 0.25
    timeout: float = 20.0
    max_retries: int = 3
    max_pages: int | None = None
    max_books: int | None = None
    download_images: bool = True
    formats: tuple[str, ...] = ("json", "csv")
    user_agent: str = DEFAULT_USER_AGENT

    # Derived paths. Kept as properties so overriding output_dir moves all of
    # them together and nothing can drift apart.

    @property
    def data_dir(self) -> Path:
        """Where books.json / books.csv / summary.json land."""
        return self.output_dir / "data"

    @property
    def images_dir(self) -> Path:
        """Where cover images land, one file per book."""
        return self.output_dir / "images"

    @property
    def logs_dir(self) -> Path:
        """Where the run log lands."""
        return self.output_dir / "logs"

    def ensure_directories(self) -> None:
        """Create the output tree. Safe to call repeatedly."""
        for directory in (self.data_dir, self.logs_dir):
            directory.mkdir(parents=True, exist_ok=True)
        if self.download_images:
            self.images_dir.mkdir(parents=True, exist_ok=True)
