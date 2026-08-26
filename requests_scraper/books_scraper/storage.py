"""Writing results to disk: books.json, books.csv, summary.json.

Field order is declared once, here, so the JSON keys and the CSV columns cannot
drift apart. Both writers go through a temporary file and a rename, so a run
that dies mid-write leaves the previous good output in place rather than a
truncated file.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, Iterable, Sequence

logger = logging.getLogger(__name__)

#: The exported schema, in output order. Anything a record carries that is not
#: listed here is dropped on write, which keeps stray internal keys out of the
#: deliverable.
FIELD_ORDER: tuple[str, ...] = (
    "title",
    "upc",
    "category",
    "price",
    "price_excl_tax",
    "tax",
    "currency",
    "rating",
    "availability",
    "stock_count",
    "review_count",
    "description",
    "product_url",
    "image_url",
    "thumbnail_url",
    "image_file",
    "slug",
    "scraped_at",
)


def order_record(record: dict[str, Any]) -> dict[str, Any]:
    """Project one record onto FIELD_ORDER, filling absent fields with None."""
    return {field: record.get(field) for field in FIELD_ORDER}


def _write_atomically(path: Path, write: Any) -> None:
    """Run ``write(temporary_path)`` then move the result over ``path``."""
    temporary = path.with_suffix(path.suffix + ".part")
    write(temporary)
    temporary.replace(path)


def write_json(records: Sequence[dict[str, Any]], path: Path) -> Path:
    """Write records as a UTF-8 JSON array, one object per book.

    ``ensure_ascii=False`` keeps titles with accented characters readable in the
    file instead of escaping them to \\uXXXX.
    """

    def write(target: Path) -> None:
        target.write_text(
            json.dumps([order_record(r) for r in records], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    _write_atomically(path, write)
    logger.info("Wrote %d records to %s", len(records), path)
    return path


def write_csv(records: Sequence[dict[str, Any]], path: Path) -> Path:
    """Write records as UTF-8 CSV with a header row.

    ``newline=""`` is required on Windows, or the csv module's own line endings
    get doubled. The BOM-less utf-8 encoding is the interoperable choice; open
    it in Excel via Data > From Text if the accents matter.
    """

    def write(target: Path) -> None:
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(FIELD_ORDER))
            writer.writeheader()
            for record in records:
                writer.writerow(order_record(record))

    _write_atomically(path, write)
    logger.info("Wrote %d rows to %s", len(records), path)
    return path


def field_coverage(records: Sequence[dict[str, Any]]) -> dict[str, int]:
    """Count how many records carry a non-empty value for each field.

    Cheap way to notice that a selector broke: a field that used to be at 1,000
    and is suddenly at 0 is a changed page, not a changed catalogue.
    """
    return {
        field: sum(1 for record in records if record.get(field) not in (None, "", []))
        for field in FIELD_ORDER
    }


def write_summary(summary: dict[str, Any], path: Path) -> Path:
    """Write the run summary as JSON."""

    def write(target: Path) -> None:
        target.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    _write_atomically(path, write)
    logger.info("Wrote run summary to %s", path)
    return path


def write_outputs(
    records: Sequence[dict[str, Any]],
    data_dir: Path,
    formats: Iterable[str],
) -> list[Path]:
    """Write every requested format and return the paths written."""
    writers = {"json": (write_json, "books.json"), "csv": (write_csv, "books.csv")}
    written: list[Path] = []

    for name in formats:
        key = name.strip().lower()
        if key not in writers:
            logger.warning("Unknown output format %r, skipping", name)
            continue
        writer, filename = writers[key]
        written.append(writer(records, data_dir / filename))

    return written
