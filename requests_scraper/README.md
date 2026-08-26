# books.toscrape.com scraper (requests)

A `requests`-based scraper for [books.toscrape.com](https://books.toscrape.com). It walks
the catalogue, records 18 fields per book, and downloads every book's cover image.

Self-contained: it shares nothing with the Scrapy project in [`../crawler/`](../crawler/),
so the two can be read, run and broken independently.

```bash
cd requests_scraper
pip install -r requirements.txt
python -m books_scraper                 # full catalogue: 1,000 books + 1,000 covers
```

## The committed run

1,000 books, 1,000 covers, 0 duplicates, 0 failed requests, 11m 49s on a home connection
at the default 0.25 s delay. Every field is populated on all 1,000 records except
`description`, which is `null` for the two books the source site genuinely has none for
(*The Bridge to Consciousness* and *Alice in Wonderland*). Full counts in
[`output/data/summary.json`](output/data/summary.json).

The covers total 42 MB across 1,000 JPEGs. If that is unwelcome in version control, add
`requests_scraper/output/images/` to `.gitignore` - `python -m books_scraper` rebuilds them
from `books.json`'s `image_url` values.

## Layout

```text
requests_scraper/
├── README.md                 this file
├── requirements.txt          requests + beautifulsoup4
├── books_scraper/            the package
│   ├── __init__.py           public entry point: BooksScraper, Settings
│   ├── __main__.py           enables `python -m books_scraper`
│   ├── cli.py                flags, logging setup, exit codes
│   ├── config.py             Settings dataclass; every path derives from output_dir
│   ├── http_client.py        session, retries, backoff, politeness, encoding fix
│   ├── parsers.py            HTML -> typed values; pure, no I/O, doctested
│   ├── images.py             cover downloads, atomic writes, resume-friendly
│   ├── scraper.py            the traversal that ties it together
│   └── storage.py            books.json / books.csv / summary.json writers
├── tests/
│   └── test_parsers.py       25 offline tests, no network
└── output/                   produced by a run, not by hand
    ├── data/
    │   ├── books.json        one object per book
    │   ├── books.csv         same records, same column order
    │   └── summary.json      counts, timings, per-field coverage, failures
    ├── images/               one cover per book, <slug>.jpg
    └── logs/scrape.log       DEBUG-level log of the last run
```

The module split follows what changes for what reason. When the site's markup moves, only
`parsers.py` moves with it. When the politeness policy changes, only `http_client.py` does.
`parsers.py` touches neither the network nor the disk, which is why its tests need neither.

## Output schema

One record per book, in this order in both JSON and CSV:

| Field | Type | Source | Notes |
|---|---|---|---|
| `title` | str | detail `h1`, listing `title` attr | The listing anchor text is truncated ("A Light in the ..."); the `title` attribute is not |
| `upc` | str | Product Information table | The site's unique product code; the deduplication key |
| `category` | str | breadcrumb | Last anchor in the trail; "Product Type" in the table is always "Books" |
| `price` | float | table, "Price (incl. tax)" | Number, not string, so it sorts and totals without re-parsing |
| `price_excl_tax` | float | table | |
| `tax` | float | table | |
| `currency` | str | price symbol | ISO code, so the number is not ambiguous |
| `rating` | int 1-5 | `class="star-rating Three"` | The word in the CSS class is the only place the rating lives |
| `availability` | str | detail `.product_main` | e.g. "In stock (22 available)" |
| `stock_count` | int | parsed from the above | The listing page omits the count; the detail page has it |
| `review_count` | int | table | |
| `description` | str \| null | `#product_description` sibling | `null` for the two books that genuinely have none |
| `product_url` | str | — | Absolute |
| `image_url` | str | `#product_gallery img` | Full-size cover, absolute |
| `thumbnail_url` | str | listing `img` | The small listing image, absolute |
| `image_file` | str \| null | downloader | Path relative to `output/`, e.g. `images/sharp-objects_997.jpg`. `null` if the cover could not be fetched |
| `slug` | str | product URL | e.g. `sharp-objects_997`. The image filename, trimmed to 100 characters where the slug is longer |
| `scraped_at` | str | — | UTC ISO 8601 |

`image_file` is stored relative to `output/` on purpose: moving or zipping the output
folder does not invalidate it.

## Usage

```bash
python -m books_scraper --help
```

| Flag | Default | What it does |
|---|---|---|
| `--output-dir PATH` | `output/` | Root for `data/`, `images/`, `logs/` |
| `--limit N` | all | Stop after N books |
| `--max-pages N` | all | Stop after N listing pages |
| `--no-images` | off | Skip covers. Roughly halves the request count |
| `--delay SECONDS` | `0.25` | Politeness delay between requests |
| `--timeout SECONDS` | `20` | Per-request timeout |
| `--retries N` | `3` | Retries for connection errors and 429/5xx |
| `--formats json,csv` | both | Comma-separated: `json`, `csv` |
| `--log-level LEVEL` | `INFO` | Console verbosity; the log file always gets DEBUG |
| `--base-url URL` | the catalogue root | Entry point |

```bash
python -m books_scraper --limit 20                  # quick smoke run
python -m books_scraper --no-images --formats json  # data only, ~1 minute
python -m books_scraper --delay 0 --log-level DEBUG # as fast as it goes, verbose
```

As a library:

```python
from books_scraper import BooksScraper, Settings

result = BooksScraper(Settings(max_books=10, download_images=False)).run()
print(len(result.records), result.duration_seconds)
```

## Design notes

**Why `requests` plus BeautifulSoup, sequentially.** The brief asks for `requests`. The
catalogue is ~1,000 books behind a plain server-rendered HTML site with no JavaScript, no
API and no authentication, so a session, a parser and a loop cover it. A thread pool would
finish sooner and be ruder to a shared sandbox; the politeness delay only means something
when one caller owns the schedule.

**The encoding trap.** The server sends `Content-Type: text/html` with no charset while
serving UTF-8. `requests` follows the HTTP spec and falls back to ISO-8859-1, which turns
`£51.77` into `Â£51.77` and mangles every accented title. `PoliteSession.get_text` overrides
the declared encoding with the sniffed one. The price regex tolerates the mojibake anyway,
so a slip degrades to a right answer rather than a wrong one.

**Failure is per-page, not per-run.** Connection errors and 429/5xx responses are retried
with exponential backoff by urllib3. Anything still failing after that is logged, counted
in `summary.json` under `failed_requests`, and skipped. One unreachable detail page costs
one book. A listing page that cannot be read stops the walk, because silently skipping an
unknown number of books is worse than a visibly short run.

**Both halves of each book, one request each.** Listing pages carry title, price, rating and
thumbnail; detail pages carry UPC, category, description, stock count and the full-size
cover. The listing fields ride along in memory while the detail page is fetched, so each
book costs one detail request, and `merge_records` combines them with the detail page
winning any contested field.

**Deduplication on UPC.** The site's own product code, which stays unique where titles do
not. A book whose UPC failed to parse is kept rather than dropped — losing a real book to a
failed field is the worse error.

**Writes are atomic.** JSON, CSV and each image are written to a `.part` file and renamed
into place. A run interrupted halfway leaves the previous good output intact rather than a
truncated file, and cannot leave a half-written JPEG that the next run would skip as
"already downloaded".

**Re-runs are cheap.** Covers already on disk are not re-fetched, so re-running to fix a
parsing bug costs the HTML requests only. Delete `output/images/` to force a full refetch.

**Image filenames are bounded at 100 characters.** Slugs come from the site's own URLs and
one of them - the *At the Existentialist Café* subtitle, in full - runs to 200 characters,
which puts the path past the 260-character limit Windows applies by default. `safe_stem()`
truncates the descriptive part while keeping the trailing product id, which is the only
part guaranteed unique, so two books with a long shared prefix still get different files.
The first full run found this the hard way, 560 books in; a write failure now costs one
cover instead of the crawl.

**Pagination is not counted.** The walk follows the site's own `li.next` link until there
isn't one, so nothing breaks if the catalogue changes size. `--max-pages` is for testing.

## Tests

```bash
cd requests_scraper
python -m unittest discover tests -v                       # 36 offline tests, no network
python -m doctest books_scraper/parsers.py books_scraper/images.py   # silence = passed
```

(Don't glob `books_scraper/*.py` into doctest: the `__main__.py` in there makes doctest
test itself, and reports a failure that has nothing to do with this code.)

The tests run against trimmed HTML fixtures held in the test file, so they are fast, and
they still fail for the right reason if a selector breaks. They cover the parsing edge
cases the site actually contains: the truncated listing title, the duplicated description
teaser, the recommendation strip below each product that carries its own `.availability`
node, a product pod with no detail link, and the last page having no "next". The
downloader is tested against a stubbed session: the 200-character slug, a re-run skipping
what is already on disk, an HTML error page served where an image was expected, an empty
body, and a zero-length leftover from an interrupted run.

Beyond the tests, `summary.json` carries a per-field count for every run. A field that sat
at 1,000 and reads 0 after a site change is a broken selector, not an empty catalogue.

## Requirements

Python 3.9+ (`str.removesuffix`, `dict[str, ...]` annotations via `from __future__ import
annotations`). Built and tested on 3.12.10, Windows 11.

```text
requests>=2.31
beautifulsoup4>=4.12
```

## Politeness and scope

Scrapes books.toscrape.com, a sandbox published for exactly this purpose. The default
0.25 s delay, the identifying User-Agent and the single-threaded traversal are habits worth
keeping on sites where they matter. `robots.txt` is not fetched: the site publishes none,
and honouring one would be the first thing to add before pointing this at anything else.
