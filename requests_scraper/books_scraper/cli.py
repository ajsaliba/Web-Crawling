"""Command line entry point: flags in, :class:`Settings` out, crawl, exit code.

    python -m books_scraper --help

Kept separate from :mod:`books_scraper.scraper` so the scraper can be driven
from a notebook or a test without argparse in the way.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, Sequence

from books_scraper.config import DEFAULT_OUTPUT_DIR, Settings
from books_scraper.scraper import BooksScraper

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)-24s %(message)s"


def build_parser() -> argparse.ArgumentParser:
    """Define the flags. Defaults mirror :class:`Settings`."""
    parser = argparse.ArgumentParser(
        prog="python -m books_scraper",
        description=(
            "Scrape book data and cover images from books.toscrape.com using "
            "requests. Writes books.json, books.csv and summary.json under "
            "output/data, and one cover per book under output/images."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m books_scraper                      full catalogue with covers\n"
            "  python -m books_scraper --limit 20           a quick smoke run\n"
            "  python -m books_scraper --no-images          data only, much faster\n"
            "  python -m books_scraper --formats json       skip the CSV\n"
        ),
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Root for data/, images/ and logs/.",
    )
    parser.add_argument(
        "--base-url",
        default=Settings.base_url,
        help="Catalogue entry point.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Stop after N books. Default: the whole catalogue.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        metavar="N",
        help="Stop after N listing pages. Default: follow every next link.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=Settings.delay,
        metavar="SECONDS",
        help="Politeness delay between requests.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=Settings.timeout,
        metavar="SECONDS",
        help="Per-request timeout.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=Settings.max_retries,
        metavar="N",
        help="Retries for connection errors and 429/5xx responses.",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip cover downloads. Roughly halves the request count.",
    )
    parser.add_argument(
        "--formats",
        default=",".join(Settings.formats),
        help="Comma-separated output formats: json, csv.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Console verbosity. The log file always gets DEBUG.",
    )
    return parser


def settings_from_args(args: argparse.Namespace) -> Settings:
    """Translate parsed flags into the frozen settings object."""
    return Settings(
        base_url=args.base_url,
        output_dir=args.output_dir,
        delay=args.delay,
        timeout=args.timeout,
        max_retries=args.retries,
        max_pages=args.max_pages,
        max_books=args.limit,
        download_images=not args.no_images,
        formats=tuple(part.strip() for part in args.formats.split(",") if part.strip()),
    )


def configure_logging(settings: Settings, console_level: str) -> Path:
    """Log to the console at the chosen level and to a file at DEBUG.

    The file is the reason the console can stay quiet: everything skipped,
    retried or failed is on disk afterwards, whatever was shown at the time.
    """
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = settings.logs_dir / "scrape.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    # Reconfigure cleanly if this is the second run in one process.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(getattr(logging, console_level))
    console.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(console)

    to_file = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    to_file.setLevel(logging.DEBUG)
    to_file.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(to_file)

    # urllib3 logs a line per connection at DEBUG, which drowns out our own.
    logging.getLogger("urllib3").setLevel(logging.INFO)
    return log_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run a crawl. Returns a shell exit code.

    0 = books were scraped, 1 = nothing was scraped or the user interrupted.
    Requests that failed after retries do not fail the run; they are counted in
    summary.json, because a crawl that lost three pages out of fifty is still
    worth its output.
    """
    args = build_parser().parse_args(argv)
    settings = settings_from_args(args)
    log_path = configure_logging(settings, args.log_level)

    try:
        result = BooksScraper(settings).run()
    except KeyboardInterrupt:
        logging.getLogger(__name__).warning("Interrupted; no output written.")
        return 1

    print(f"\n{len(result.records)} books -> {settings.data_dir}")
    if settings.download_images:
        print(
            f"{result.images_downloaded} covers downloaded "
            f"({result.images_skipped_existing} already on disk, "
            f"{result.images_failed} failed) -> {settings.images_dir}"
        )
    if result.failures:
        print(f"{len(result.failures)} requests failed; see {log_path}")

    return 0 if result.records else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
