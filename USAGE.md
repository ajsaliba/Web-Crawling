# Usage Guide

Practical instructions for running everything in this submission.

`README.md` covers what was built and why. This one covers running it.

**Contents**

1. [Prerequisites](#1-prerequisites)
2. [Setup](#2-setup)
3. [Part 1 - running the crawler](#3-part-1--running-the-crawler)
4. [Part 2 - extraction challenges](#4-part-2--extraction-challenges)
5. [Part 3 - site investigation](#5-part-3--site-investigation)
6. [Output format reference](#6-output-format-reference)
7. [Common tasks](#7-common-tasks)
8. [Verifying the submission](#8-verifying-the-submission)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Prerequisites

| Requirement | Version | Notes |
| --- | --- | --- |
| Python | 3.10 or newer | Built and tested on 3.12.10. The brief asks for 3.10+; the code itself only needs 3.9 features (`str.removesuffix`, builtin generics). |
| pip | any recent | Ships with Python. |
| Internet access | - | The crawler fetches `books.toscrape.com`; the Part 3 script fetches `allbirds.com`. |
| Disk space | ~90 MB | Almost all of it the virtual environment. |

Check your Python version before starting:

```bash
python --version
```

If that reports anything below 3.10, or "Python was not found", install a current
Python from [python.org](https://www.python.org/downloads/) and re-check. On Windows,
try `py --version` as well.

---

## 2. Setup

Run once, from the folder containing this file.

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it:

```bash
# Windows - PowerShell
.venv\Scripts\Activate.ps1

# Windows - cmd.exe
.venv\Scripts\activate.bat

# macOS / Linux
source .venv/bin/activate
```

Your prompt should now start with `(.venv)`. It has to stay active for every command
below, so re-run that line in each new terminal.

If PowerShell blocks the activation script, run
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal first.
`-Scope Process` keeps the change to that window.

Install:

```bash
pip install -r requirements.txt
```

Check both libraries landed:

```bash
scrapy version
python -c "import requests; print('requests', requests.__version__)"
```

Expect `Scrapy 2.17.0` and `requests 2.34.2` or newer.

---

## 3. Part 1 - running the crawler

Scrapy has to run from the directory holding `scrapy.cfg`, which is `crawler/`:

```bash
cd crawler
scrapy crawl books -O ../books.json
```

That is all 50 listing pages and all 1,000 detail pages, written to `books.json` at the
repository root. Expect about 5.5 minutes - `DOWNLOAD_DELAY` and AutoThrottle in
`settings.py` keep it polite rather than fast.

### `-O` vs `-o`

One character, and it matters:

| Flag | Behaviour | Use when |
| --- | --- | --- |
| `-O` (capital) | **Overwrites** the file | Normal - what you want almost always |
| `-o` (lowercase) | **Appends** to the file | You actually want to merge several runs |

Running `-o` twice gives 2,000 entries: 1,000 products and 1,000 duplicates. If
`books.json` is twice the size you expected, that is why.

### Keeping a run log

```bash
cd crawler
scrapy crawl books -O ../books.json --logfile ../crawl.log --loglevel INFO
```

Without `--logfile` the log goes to the terminal. Worth keeping for any run you intend
to rely on: it is the only record of what was fetched, what failed, and why it stopped.

### While it runs

Scrapy prints a progress line each minute:

```text
[scrapy.extensions.logstats] INFO: Crawled 386 pages (at 192 pages/min), scraped 340 items (at 171 items/min)
```

At the end, two lines from the pipelines:

```text
[bookscrawler.pipelines] WARNING: Field coverage over 1000 items - missing values: {'description': 2}
[bookscrawler.pipelines] INFO: Duplicate check: 1000 unique products, 0 duplicates dropped
```

The `description: 2` warning is expected. Two books have no description on the site.

Then check `finish_reason`:

```text
'finish_reason': 'finished',
```

`finished` means pagination ran out on its own. Anything else means the crawl stopped
early and the output is incomplete.

### Options

Any setting can be overridden per run with `-s`:

```bash
# Quick smoke test - stop after ~10 items (finishes in seconds)
scrapy crawl books -s CLOSESPIDER_ITEMCOUNT=10 -O ../sample.json

# Stop after 60 seconds instead
scrapy crawl books -s CLOSESPIDER_TIMEOUT=60 -O ../sample.json

# Quieter output - warnings and errors only
scrapy crawl books -O ../books.json --loglevel WARNING

# Slower and gentler on the server
scrapy crawl books -s DOWNLOAD_DELAY=1.0 -s CONCURRENT_REQUESTS=2 -O ../books.json

# Export CSV instead of JSON (field order follows FEED_EXPORT_FIELDS)
scrapy crawl books -O ../books.csv
```

`CLOSESPIDER_ITEMCOUNT` is a floor, not an exact count. Requests already in flight still
finish, so asking for 10 usually gives you somewhere between 10 and 18.

### Trying selectors

Against a live page:

```bash
cd crawler
scrapy shell "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
```

Then, at the prompt:

```python
response.css("div.product_main h1::text").get()
response.css("table.table-striped tr th::text").getall()
response.css("#product_gallery img::attr(src)").get()
```

Fastest way to check a selector before changing the spider.

---

## 4. Part 2 - extraction challenges

From the repository root. No dependencies, so this runs even without the venv active:

```bash
python extraction_challenge.py
```

Expected output:

```text
[PASS] A - largest product image
        got:      https://cdn.sample-store.com/items/X51_1400.jpg
[PASS] B - primary full-size image
        got:      https://media.example.com/full/9034.jpg
[PASS] C - video URL
        got:      https://cdn.example.com/video/item77-main.mp4
[PASS] D - pagination
        got:      {'current_page': 6, 'total_pages': 24}

[PASS] edge cases: missing data returns None instead of raising
[PASS] all four challenges produce the expected values
```

Exits 0 on success, non-zero if any case fails.

### On your own input

Each one is an ordinary function taking an HTML string:

```python
from extraction_challenge import (
    extract_largest_image,
    extract_primary_image,
    extract_video_url,
    extract_pagination,
)

extract_largest_image('<img srcset="a_300.jpg 300w, a_900.jpg 900w">')
# 'a_900.jpg'

extract_pagination("Page 3 of 17")
# {'current_page': 3, 'total_pages': 17}

extract_video_url("<div>nothing here</div>")
# None
```

All four return `None` rather than raising when the value is not there.

---

## 5. Part 3 - site investigation

Findings are in `site_report.md`. To re-derive them from live responses:

```bash
python investigate_site.py
```

Takes about 10 seconds and pulls down roughly 3.5 MB, most of it the two large HTML
pages. One section per report heading, A to E.

Read-only. One `GET` at a time, a second apart, honest User-Agent. No login, no cart or
account routes, no attempt to get past anything. If the site serves a challenge page the
script says so and stops.

Numbers may differ from the report. Catalogue-dependent counts drift as stock changes;
the report records what was there on 18 August 2026. The structural findings do not move.

---

## 6. Output format reference

A JSON array of 1,000 objects. Key order is fixed by `FEED_EXPORT_FIELDS` in
`settings.py`, so diffs between runs stay readable.

| Field | Type | Example | Notes |
| --- | --- | --- | --- |
| `title` | string | `"It's Only the Himalayas"` | Full title, from the link's `title` attribute - not the truncated visible text |
| `price` | float | `45.17` | Numeric, so it sorts and aggregates without re-parsing |
| `currency` | string | `"GBP"` | Derived from the `£` symbol; keeps `price` unambiguous |
| `availability` | string | `"In stock (19 available)"` | The site's own wording, including the stock count |
| `category` | string | `"Travel"` | From the breadcrumb - 50 distinct values |
| `upc` | string | `"a22124811bfa8350"` | Unique per book; used as the deduplication key |
| `description` | string \| null | `"…"` | `null` for the 2 books with no description on the site |
| `product_url` | string | `"https://books.toscrape.com/catalogue/…"` | Always absolute |
| `image_url` | string | `"https://books.toscrape.com/media/cache/…"` | Always absolute; full-size image from the detail page |

A single record:

```json
{
  "title": "It's Only the Himalayas",
  "price": 45.17,
  "currency": "GBP",
  "availability": "In stock (19 available)",
  "category": "Travel",
  "upc": "a22124811bfa8350",
  "description": "“Wherever you go, whatever you do, just . . . don’t do anything stupid.” -My Mother…",
  "product_url": "https://books.toscrape.com/catalogue/its-only-the-himalayas_981/index.html",
  "image_url": "https://books.toscrape.com/media/cache/6d/41/6d418a73cc7d4ecfd75ca11d854041db.jpg"
}
```

### Loading the data

```python
import json

with open("books.json", encoding="utf-8") as handle:
    books = json.load(handle)

print(len(books))                                            # 1000
print(sorted({b["category"] for b in books})[:5])            # first 5 categories
print(max(books, key=lambda b: b["price"])["title"])         # priciest book

in_stock = [b for b in books if "In stock" in b["availability"]]
print(f"{len(in_stock)} in stock")
```

Always pass `encoding="utf-8"`. Titles and descriptions contain non-ASCII characters,
and the Windows default will mangle them.

---

## 7. Common tasks

### Change the crawl rate

Edit the politeness block in `settings.py`, or override per run with `-s`:
`DOWNLOAD_DELAY`, `CONCURRENT_REQUESTS`, `AUTOTHROTTLE_*`.

### Add a field to the output

1. Declare it in `crawler/bookscrawler/items.py`.
2. Populate it in `crawler/bookscrawler/spiders/books.py`.
3. Add it to `FEED_EXPORT_FIELDS` in `settings.py`. Fields missing from that list are
   silently dropped from the export, which is the usual reason a new field does not
   show up.
4. If it is mandatory, add it to `REQUIRED_FIELDS` in `pipelines.py`.

### Re-run part of a crawl

There is no resume. For a subset, use `scrapy shell` on the URL, or put a temporary
filter in `parse()`.

### Export a different format

Scrapy infers the format from the file extension: `.json`, `.jsonl`, `.csv`, `.xml`.

```bash
scrapy crawl books -O ../books.csv
scrapy crawl books -O ../books.jsonl
```

`.jsonl` is better for large crawls: one object per line, so it streams.

---

## 8. Verifying the submission

Each is independent. From the repository root unless noted.

```bash
# Exported data is complete and free of duplicates
python -c "import json; d=json.load(open('books.json',encoding='utf-8')); print(len(d), 'items;', len({x['upc'] for x in d}), 'unique UPCs')"
# -> 1000 items; 1000 unique UPCs

# All four extraction challenges, plus edge cases
python extraction_challenge.py

# Doctests for the parsing helpers (no output = every example passed)
cd crawler && python -m doctest bookscrawler/parsers.py && cd ..

# The spider is registered and discoverable
cd crawler && scrapy list && cd ..
# -> books

# Every URL in the output is absolute
python -c "import json; d=json.load(open('books.json',encoding='utf-8')); print('all absolute:', all(b['product_url'].startswith('https://') and b['image_url'].startswith('https://') for b in d))"

# Part 3 - re-derive the site-report evidence from live responses (~10s, network)
python investigate_site.py

# requests is never called from inside the Scrapy project (returns nothing)
grep -rn "import requests" crawler/
```

---

## 9. Troubleshooting

### `scrapy: command not found` / `'scrapy' is not recognized`

The venv is not active. Re-run the activation line from [Setup](#2-setup), and confirm
with `pip show scrapy`.

### `Unknown command: crawl` - "use 'scrapy' with a project"

You are not inside `crawler/`. Scrapy finds the project by looking for `scrapy.cfg` in
the working directory:

```bash
cd crawler
scrapy crawl books -O ../books.json
```

### `ModuleNotFoundError: No module named 'bookscrawler'`

Same cause. Run from `crawler/`, not the repository root or `crawler/bookscrawler/`.

### The crawl produced far fewer than 1,000 items

Check `finish_reason` at the end of the log:

* `closespider_itemcount` / `closespider_timeout` - a `-s CLOSESPIDER_*` limit was left
  in the command. Remove it.
* `finished` but with a low count - look for HTTP errors in the log
  (`response_status_count/4xx` or `5xx`) and for the line
  `No further pagination link found on …`. If that names a page other than `page-50`,
  pagination broke early.

Scenario 3 of `reasoning.md` in practice: never treat a low count as a success.

### `books.json` contains ~2,000 entries

You used `-o` instead of `-O`. Delete the file and re-run with `-O`.

### Mojibake such as `Â£51.77` or `â€œ` in the output

Something read the file with the wrong encoding. The file is UTF-8: pass
`encoding="utf-8"` when opening it, and set `PYTHONIOENCODING=utf-8` if you are printing
to a Windows terminal.

### `investigate_site.py` fails or reports a challenge

Network failures are reported per request and the script carries on. A `BLOCKED` section
means the site served a challenge page instead of content; the script stops there on
purpose. Do not try to work around it.

### Connection errors or timeouts during the crawl

The spider retries 408, 429, 500, 502, 503 and 504 three times. On a flaky connection,
lower the load:

```bash
scrapy crawl books -s CONCURRENT_REQUESTS=2 -s DOWNLOAD_DELAY=1.0 -O ../books.json
```
