"""Command line entry point.

    python -m bookimages task1                 # 3 categories, every book
    python -m bookimages task2                 # all 50 categories, 4 images each
    python -m bookimages categories            # list what the site offers
"""

import argparse
import json
import logging
import sys
import time

from . import config, storage
from .crawler import BooksCrawler
from .http_client import HttpClient


def _configure_logging(verbose):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def _run(task_name, categories, limit, args):
    output_dir = config.OUTPUT_DIR / task_name
    client = HttpClient(delay=args.delay)
    crawler = BooksCrawler(client=client, output_root=output_dir,
                           overwrite=args.overwrite)
    started = time.monotonic()
    try:
        results = crawler.crawl(categories, limit=limit)
    finally:
        crawler.close()

    storage.save_json(results, output_dir / "books.json")
    storage.save_csv(results, output_dir / "books.csv")
    summary = storage.build_summary(results, crawler.downloader.stats(),
                                    client.request_count)
    summary["elapsed_seconds"] = round(time.monotonic() - started, 1)
    storage.save_json(summary, output_dir / "summary.json")

    print("\n=== %s complete ===" % task_name)
    print(json.dumps(summary, indent=2))
    print("Output: %s" % output_dir)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="bookimages", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--delay", type=float, default=config.REQUEST_DELAY,
                        help="seconds between HTTP requests (default: %(default)s)")
    parser.add_argument("--overwrite", action="store_true",
                        help="re-download images that are already on disk")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    task1 = sub.add_parser("task1", help="crawl three chosen categories in full")
    task1.add_argument("--categories", nargs="+", default=config.TASK1_CATEGORIES,
                       help="category names (default: %(default)s)")
    task1.add_argument("--limit", type=int, default=None,
                       help="cap books per category (default: all)")

    task2 = sub.add_parser("task2", help="4 images from every category on the site")
    task2.add_argument("--count", type=int, default=config.TASK2_IMAGES_PER_CATEGORY,
                       help="images per category (default: %(default)s)")

    sub.add_parser("categories", help="print every category the site lists")

    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    if args.command == "categories":
        crawler = BooksCrawler(client=HttpClient(delay=args.delay))
        try:
            for category in crawler.list_categories():
                print("%-20s %s" % (category["name"], category["url"]))
        finally:
            crawler.close()
        return 0

    probe = BooksCrawler(client=HttpClient(delay=args.delay))
    try:
        if args.command == "task1":
            categories = probe.resolve_categories(args.categories)
            limit = args.limit
        else:
            categories = probe.list_categories()
            limit = args.count
    finally:
        probe.close()

    _run(args.command, categories, limit, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
