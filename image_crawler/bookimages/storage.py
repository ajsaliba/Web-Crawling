"""Persisting scraped records as JSON and CSV."""

import csv
import json
from pathlib import Path

CSV_FIELDS = [
    "category", "title", "upc", "price_incl_tax", "price_excl_tax", "tax",
    "rating", "availability", "stock_count", "num_reviews",
    "product_url", "image_url", "image_status", "image_path", "image_bytes",
]


def _flatten(results):
    rows = []
    for books in results.values():
        rows.extend(books)
    return rows


def save_json(results, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def save_csv(results, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(_flatten(results))
    return path


def build_summary(results, image_stats, requests_made):
    rows = _flatten(results)
    return {
        "categories_crawled": len(results),
        "books_scraped": len(rows),
        "images": image_stats,
        "http_requests": requests_made,
        "per_category": {
            name: {
                "books": len(books),
                "images_ok": sum(1 for b in books
                                 if b["image_status"] in ("downloaded", "skipped")),
            }
            for name, books in results.items()
        },
    }
