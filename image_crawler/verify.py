"""Independent verification that the crawl output meets the task requirements.

Re-fetches ground truth from books.toscrape.com and checks it against what is
on disk. Run:  python verify.py
"""

import json
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from bookimages import config, parsers
from bookimages.http_client import HttpClient

OUTPUT = config.OUTPUT_DIR
RESULTS_RE = re.compile(r"(\d+)\s+results?", re.I)
JPEG_MAGIC = b"\xff\xd8\xff"

checks = []


def check(name, passed, detail=""):
    checks.append((name, passed, detail))
    print("  [%s] %s%s" % ("PASS" if passed else "FAIL", name,
                           ("  -- " + detail) if detail else ""))
    return passed


def load(task):
    books = json.loads((OUTPUT / task / "books.json").read_text(encoding="utf-8"))
    summary = json.loads((OUTPUT / task / "summary.json").read_text(encoding="utf-8"))
    return books, summary


def site_category_totals(client):
    """{category name: (url, total books the site claims)} for all categories."""
    totals = {}
    for cat in parsers.parse_categories(client.get_html(config.INDEX_URL), config.INDEX_URL):
        soup = BeautifulSoup(client.get_html(cat["url"]), "html.parser")
        text = soup.select_one("form.form-horizontal").get_text(" ", strip=True)
        match = RESULTS_RE.search(text)
        totals[cat["name"]] = (cat["url"], int(match.group(1)) if match else None)
    return totals


def listing_thumbnails(client, category_url):
    """Thumbnail image URLs shown on a category listing page."""
    soup = BeautifulSoup(client.get_html(category_url), "html.parser")
    return {urljoin(category_url, img["src"])
            for img in soup.select("article.product_pod img")}


REQUIRED_FIELDS = ["title", "category", "upc", "price_incl_tax", "price_excl_tax",
                   "rating", "availability", "product_url", "image_url"]


def verify_records(task, books):
    rows = [b for bs in books.values() for b in bs]

    missing = [(b.get("title"), f) for b in rows
               for f in REQUIRED_FIELDS if b.get(f) in (None, "")]
    check("%s: every book has complete metadata (%d fields x %d books)"
          % (task, len(REQUIRED_FIELDS), len(rows)), not missing, str(missing[:3]))

    bad_status = [b["title"] for b in rows
                  if b["image_status"] not in ("downloaded", "skipped")]
    check("%s: no failed image downloads" % task, not bad_status, str(bad_status[:3]))

    off_site = [b["image_url"] for b in rows
                if "/media/cache/" not in (b["image_url"] or "")]
    check("%s: all image URLs are real cover URLs" % task, not off_site, str(off_site[:3]))

    missing_files, not_jpeg, size_mismatch = [], [], []
    for b in rows:
        p = Path(b["image_path"]) if b["image_path"] else None
        if not p or not p.exists():
            missing_files.append(b["title"])
            continue
        data = p.read_bytes()
        if not data.startswith(JPEG_MAGIC):
            not_jpeg.append(p.name)
        if b["image_bytes"] is not None and len(data) != b["image_bytes"]:
            size_mismatch.append(p.name)
    check("%s: every recorded image exists on disk (%d)" % (task, len(rows)),
          not missing_files, str(missing_files[:3]))
    check("%s: every image is a valid JPEG" % task, not not_jpeg, str(not_jpeg[:3]))
    check("%s: file sizes match recorded byte counts" % task, not size_mismatch,
          str(size_mismatch[:3]))

    on_disk = {str(p.resolve()) for p in (OUTPUT / task / "images").rglob("*.jpg")}
    recorded = {str(Path(b["image_path"]).resolve()) for b in rows if b["image_path"]}
    check("%s: no extra/orphan image files on disk (%d on disk, %d recorded)"
          % (task, len(on_disk), len(recorded)), on_disk == recorded,
          str(list(on_disk - recorded)[:3]))
    return rows


def main():
    client = HttpClient()
    print("Fetching ground truth from books.toscrape.com ...")
    totals = site_category_totals(client)
    print("  %d categories found on the site\n" % len(totals))

    # ---------------------------------------------------------------- TASK 1
    print("TASK 1 -- three distinct categories, all books, images after product page")
    t1, s1 = load("task1")
    names = list(t1)

    check("task1: exactly three categories crawled", len(names) == 3, str(names))
    check("task1: the three are distinct", len(set(names)) == 3, str(names))
    check("task1: all three exist on the site",
          all(n in totals for n in names),
          str([n for n in names if n not in totals]))

    wrong = {n: (len(t1[n]), totals[n][1]) for n in names if len(t1[n]) != totals[n][1]}
    check("task1: every book in each category was crawled (%s)"
          % {n: len(t1[n]) for n in names}, not wrong, str(wrong))

    check("task1: pagination followed (a category exceeds one 20-book page)",
          any(len(t1[n]) > 20 for n in names),
          "largest category = %d books" % max(len(t1[n]) for n in names))

    rows1 = verify_records("task1", t1)

    mismatch = [b["title"] for n in names for b in t1[n] if b["category"] != n]
    check("task1: each book's breadcrumb category matches its crawl category",
          not mismatch, str(mismatch[:3]))

    # KEY REQUIREMENT: images come from the product page, not the listing page.
    thumb_urls = set()
    for n in names:
        thumb_urls |= listing_thumbnails(client, totals[n][0])
    overlap = [b["image_url"] for b in rows1 if b["image_url"] in thumb_urls]
    check("task1: images came from the PRODUCT page, not listing thumbnails "
          "(%d listing thumbs compared)" % len(thumb_urls), not overlap, str(overlap[:3]))

    sample = rows1[:3]
    bad = []
    for b in sample:
        page = parsers.parse_product(client.get_html(b["product_url"]), b["product_url"])
        if page["image_url"] != b["image_url"]:
            bad.append(b["title"])
    check("task1: re-fetching the product page yields the same image URL (%d sampled)"
          % len(sample), not bad, str(bad))

    bad = []
    for b in sample:
        fresh = client.get(b["image_url"]).content
        if fresh != Path(b["image_path"]).read_bytes():
            bad.append(b["title"])
    check("task1: saved bytes match a fresh GET of the image URL (%d sampled)"
          % len(sample), not bad, str(bad))

    check("task1: summary totals agree with records (%d books)" % s1["books_scraped"],
          s1["books_scraped"] == len(rows1) and s1["images"]["failed"] == 0)

    # ---------------------------------------------------------------- TASK 2
    print("\nTASK 2 -- 4 images from every category on the site")
    t2, s2 = load("task2")

    check("task2: all %d site categories are covered" % len(totals),
          set(t2) == set(totals), str(set(totals) - set(t2)))

    over = {n: len(bs) for n, bs in t2.items() if len(bs) > 4}
    check("task2: no category exceeds 4 books", not over, str(over))

    wrong = {n: (len(bs), totals[n][1]) for n, bs in t2.items()
             if len(bs) != min(4, totals[n][1])}
    check("task2: each category has exactly min(4, books available on site)",
          not wrong, str(wrong))

    short = {n: totals[n][1] for n in t2 if totals[n][1] < 4}
    print("       (%d categories genuinely hold fewer than 4 books: %s)"
          % (len(short), short))

    rows2 = verify_records("task2", t2)

    dupes = {n: len(bs) for n, bs in t2.items()
             if len({b["image_url"] for b in bs}) != len(bs)}
    check("task2: no duplicate images within a category", not dupes, str(dupes))

    expected = sum(min(4, totals[n][1]) for n in totals)
    check("task2: total image count is the site maximum (%d)" % expected,
          len(rows2) == expected, "got %d" % len(rows2))

    check("task2: summary totals agree with records (%d books)" % s2["books_scraped"],
          s2["books_scraped"] == len(rows2) and s2["images"]["failed"] == 0)

    client.close()

    # ---------------------------------------------------------------- VERDICT
    failed = [n for n, ok, _ in checks if not ok]
    print("\n" + "=" * 70)
    print("%d/%d checks passed" % (len(checks) - len(failed), len(checks)))
    if failed:
        print("FAILED:")
        for n in failed:
            print("  - " + n)
    else:
        print("All requirements verified.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
