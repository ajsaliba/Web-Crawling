# LAU Industrial Hub - Python / Web Crawler Technical Assessment

All five parts. The committed run produced 1,000 products, 0 duplicates, and every
required field populated except `description`, which two books on the source site do not
have.

Operating instructions, options and troubleshooting are in [`USAGE.md`](USAGE.md). This
file covers what was built and why.

## Deliverables

| Part | File | |
|---|---|---|
| 1 | [`crawler/`](crawler/) | Scrapy project |
| 1 | [`books.json`](books.json) | 1,000 products |
| 2 | [`extraction_challenge.py`](extraction_challenge.py) | Challenges A-D, with checks |
| 3 | [`site_report.md`](site_report.md) | Investigation of allbirds.com |
| 3 | [`investigate_site.py`](investigate_site.py) | The same investigation, in code |
| 4 | [`site_config.yaml`](site_config.yaml) | Config for a generic crawling engine |
| 5 | [`reasoning.md`](reasoning.md) | Scenarios 1-5 |
| extra | [`requests_scraper/`](requests_scraper/) | The same catalogue scraped with `requests` + BeautifulSoup, plus every cover image. Self-contained, with its own [README](requests_scraper/README.md) |
| extra | [`image_pipeline_crawler/`](image_pipeline_crawler/) | Scrapy spider with a custom image pipeline: covers saved to `downloaded_images/<category>/<title>.jpg`, with optional `-a category` and `-a title_keyword` filters. Self-contained, with its own [README](image_pipeline_crawler/README.md) |

```text
Web-Crawling/
├── README.md                    what was built and why
├── USAGE.md                     how to run it
├── requirements.txt             Scrapy and requests
├── books.json                   Part 1 output
├── extraction_challenge.py      Part 2
├── site_report.md               Part 3
├── investigate_site.py          Part 3
├── site_config.yaml             Part 4
├── reasoning.md                 Part 5
├── crawler/                     Part 1 - the Scrapy project
│   ├── scrapy.cfg
│   └── bookscrawler/
│       ├── items.py             the exported fields
│       ├── parsers.py           text and price cleanup, doctested
│       ├── pipelines.py         dedup, field-coverage report
│       ├── settings.py          politeness, retries, feed export
│       └── spiders/books.py     traversal and selectors
├── requests_scraper/            extra - requests + BeautifulSoup, data and cover images
│   ├── README.md                its own docs, schema and design notes
│   ├── books_scraper/           the package (config, http_client, parsers, images,
│   │                            storage, scraper, cli)
│   ├── tests/                   25 offline tests
│   └── output/                  books.json, books.csv, summary.json, images/, logs/
├── image_pipeline_crawler/      extra - Scrapy spider + custom image pipeline
│   ├── README.md                its own docs: filtering rules and pipeline design
│   ├── scrapy.cfg
│   └── bookcovers/              items, naming (doctested), pipelines, settings,
│                                spiders/book_spider.py
└── given/                       the original brief
```

## Python version

Built and tested on **Python 3.12.10**. The brief asks for 3.10+, which is what I target;
the code itself only needs 3.9 features (`str.removesuffix`, `list[...]` annotations).
Developed on Windows 11, works on macOS and Linux with the usual venv activation.

## Installation

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
```

## Running it

Part 1, from `crawler/` where `scrapy.cfg` lives. Takes about 5.5 minutes:

```bash
cd crawler
scrapy crawl books -O ../books.json
```

Part 2 (no dependencies) and Part 3 (about 10 seconds, needs network):

```bash
python extraction_challenge.py
python investigate_site.py
```

`-O` overwrites, `-o` appends. Running `-o` twice gives you every product duplicated.

The extra `requests` scraper, which also downloads the cover images, runs on its own from
[`requests_scraper/`](requests_scraper/) and is documented there:

```bash
cd requests_scraper
pip install -r requirements.txt
python -m books_scraper --limit 20      # drop --limit for all 1,000
```

The extra Scrapy image-pipeline spider runs from
[`image_pipeline_crawler/`](image_pipeline_crawler/) and is documented there. It writes
`downloaded_images/<category>/<title>.jpg` through a hand-written pipeline, and takes two
optional filters:

```bash
cd image_pipeline_crawler
scrapy crawl book_spider                                    # whole catalogue
scrapy crawl book_spider -a category="Science"              # one category
scrapy crawl book_spider -a category="Childrens" -a title_keyword="robot"
```

## How it works

Start at the home page, read the cheap fields off each `article.product_pod`, follow the
product to its detail page carrying those fields in `cb_kwargs`, add UPC, description,
category and the full-size image, then follow `li.next a` and repeat. One request per
product, and the page count is never hard-coded.

Each module owns one thing:

| File | Responsibility |
|---|---|
| [`spiders/books.py`](crawler/bookscrawler/spiders/books.py) | which pages to visit, which nodes hold the data |
| [`parsers.py`](crawler/bookscrawler/parsers.py) | turning raw strings into typed values |
| [`pipelines.py`](crawler/bookscrawler/pipelines.py) | dedup and coverage, which need the whole run |
| [`items.py`](crawler/bookscrawler/items.py) | the exported fields |
| [`settings.py`](crawler/bookscrawler/settings.py) | only what differs from Scrapy defaults |

Imports point one way: `parsers.py` imports nothing from the project, and `pipelines.py`
never sees the spider, so a selector change cannot break deduplication.

### How each rule is met

| Rule | How |
|---|---|
| Pagination, not hard-coded | Follows `li.next a` until it is gone. The log ends `No further pagination link found on .../page-50.html`, so the spider found the 50 pages rather than being told |
| Absolute URLs | `response.follow()` and `response.urljoin()` throughout, no concatenation. All 2,000 URLs start with `https://` |
| Missing data does not crash | Every selector uses `.get()`. The info table is read by row header, not row index, so a missing row cannot shift UPC into the wrong field. The 2 description-less books exported as `null` |
| No duplicates | Scrapy's URL dupefilter, plus `DuplicateBookPipeline` keyed on UPC with `product_url` as fallback. 1,000 unique UPCs |

### Why both Scrapy and requests

Scrapy runs the crawler: 1,051 pages needs a scheduler, dupe filter, retries and
throttling, and building that on `requests` means writing a worse Scrapy. `requests` runs
the Part 3 investigation, which is a handful of calls read by hand, and which the brief
says to do with "curl or Python requests".

They never mix. Scrapy runs on Twisted's event loop, so a blocking `requests.get()` in a
callback holds up every other request in flight. `grep -rn "requests" crawler/` returns
nothing.

### Two things the first version got wrong

Both came out of reading the output, not the code.

**Availability picked up the wrong text.** A page-wide `p.availability` selector also
matched the six "you may also like" tiles, so the field read
`"In stock (19 available) In stock In stock..."`. Scoping to `.product_main` fixed it.

**Descriptions came out doubled.** Long descriptions sit in one `<p>` holding a truncated
teaser, then the full text, then `...more`. The teaser is a prefix of the full text, so
the real description starts at the second occurrence of its own opening characters, which
is what `strip_truncated_preview()` looks for.

### Decisions worth calling out

**`price` is a float with `currency` beside it.** Shipping `"£51.77"` as a string makes
every consumer parse it again. All eight required fields are there; `currency` is the one
extra so the number is not ambiguous alone.

**`category` comes from the breadcrumb.** The table's "Product Type" row says `Books` for
all 1,000 products. The breadcrumb gives the real category, 50 of them.

**Missing fields warn rather than drop.** Dropping them would hide the thing worth
watching: if `description` goes from 2 missing to 900, a selector broke.

**Honest User-Agent, `ROBOTSTXT_OBEY = True`, AutoThrottle on.** The site serves no
robots.txt, so it changes nothing here, but keeps the default safe elsewhere.

## Output

```json
{
  "title": "It's Only the Himalayas",
  "price": 45.17,
  "currency": "GBP",
  "availability": "In stock (19 available)",
  "category": "Travel",
  "upc": "a22124811bfa8350",
  "description": "“Wherever you go, whatever you do, just . . . don't do anything stupid.” ...",
  "product_url": "https://books.toscrape.com/catalogue/its-only-the-himalayas_981/index.html",
  "image_url": "https://books.toscrape.com/media/cache/6d/41/6d418a73cc7d4ecfd75ca11d854041db.jpg"
}
```

Field types are in [`USAGE.md`](USAGE.md#5-output-format-reference). End of the run that
produced this file:

```text
[bookscrawler.pipelines] WARNING: Field coverage over 1000 items - missing values: {'description': 2}
[bookscrawler.pipelines] INFO: Duplicate check: 1000 unique products, 0 duplicates dropped
[books] INFO: No further pagination link found on https://books.toscrape.com/catalogue/page-50.html

'downloader/request_count': 1051,
'item_scraped_count': 1000,
'elapsed_time_seconds': 323.30,
'finish_reason': 'finished',
```

Checked afterwards: 1,000 items, 1,000 unique UPCs and URLs, 50 categories, all URLs
absolute, all prices positive floats between £10.00 and £59.99, and `description` on 998.
The commands are in [`USAGE.md`](USAGE.md#7-verifying-the-submission).

## Assumptions

The home page listing reaches every product, so category pages are not crawled
separately; they would only produce duplicates. The 0 duplicates dropped bears that out.

UPC is unique across all 1,000 books, which makes it the right dedup key.

`availability` keeps the site's own wording rather than being split into a boolean and a
count. The brief asks for availability, and the number is easy to recover if wanted.

`image_url` is the detail page's full-size image, falling back to the listing thumbnail.
On this site both resolve to the same asset.

`description` drops the `...more` marker and the duplicated teaser, since both are
presentation rather than content.

## Known limitations

**2 books have `"description": null`.** That is the source, not a bug: those pages have no
`#product_description` element at all. The crawler exports them cleanly instead of
crashing, which is what Requirement 5 asks for.

**Star rating is not extracted.** It is available, but it is not in the requested field
list and I would rather not widen the schema past the spec.

**`strip_truncated_preview()` is specific to this site.** It relies on the teaser being a
prefix of the full text, which is a workaround for this markup rather than a general rule.

**Selectors are class-based**, so a markup change breaks them. That is inherent to HTML
scraping. Where a site offers structured data I would use it instead, which is the
argument in [`site_report.md`](site_report.md) section B.

**Live figures in `site_report.md` drift** as the store changes stock. Every command is
quoted inline so they can be re-checked; the structural findings do not move.

**No test suite** beyond the doctests in `parsers.py` and the checks in
`extraction_challenge.py`. For production I would add HTML fixtures and regression tests,
per Scenario 5 of [`reasoning.md`](reasoning.md).

## Scope note (Part 3)

The investigation used plain public `GET` requests at a low rate. Nothing was probed or
bypassed, and no crawler was built for that site, as the brief instructs.
