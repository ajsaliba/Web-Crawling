# books.toscrape.com image crawler

A self-contained crawler that walks category listings, visits each product page,
and then issues a **GET request to the cover image URL** found on that page to
download the image.

Built with `requests` + `BeautifulSoup` only — no framework.

## Install

```bash
pip install -r requirements.txt
```

## Usage

Run from this directory (`image_crawler/`):

```bash
python -m bookimages task1        # Task 1 — three chosen categories, every book
python -m bookimages task2        # Task 2 — 4 images from every category
python -m bookimages categories   # list the 50 categories the site offers
```

Useful flags (accepted before the subcommand):

| Flag | Meaning |
| --- | --- |
| `--delay 0.5` | seconds between HTTP requests (default `0.25`) |
| `--overwrite` | re-download images already on disk instead of skipping them |
| `-v` | debug-level logging |

Task-specific flags:

```bash
python -m bookimages task1 --categories Mystery Poetry History
python -m bookimages task1 --limit 5      # cap books per category
python -m bookimages task2 --count 10     # images per category
```

## Task 1 — three distinct categories

Default selection covers three different topic areas: **Fiction**, **Science**,
**Travel**. Every book in each category is crawled, following listing pagination
where a category runs past one page (Fiction is 4 pages).

Result of the recorded run:

| Category | Books | Images |
| --- | --- | --- |
| Fiction | 65 | 65 |
| Science | 14 | 14 |
| Travel | 11 | 11 |
| **Total** | **90** | **90 saved, 0 failed** |

186 HTTP requests, ~48 seconds on the first run. (A re-run reports the
images as `skipped` rather than `downloaded`, since they are already on disk.)

## Task 2 — 4 images from every category

All 50 categories, capped at 4 books each: **165 images, 0 failed**, 380 requests,
~97 seconds.

Fewer than 50 × 4 = 200 because 14 categories do not contain 4 books in total on
the site (Academic, Suspense, Novels, Crime, Cultural, Erotica, Paranormal,
Parenting, Adult Fiction and Short Stories have only 1 book each; Historical has
2; Contemporary, Christian and Politics have 3). The crawler takes everything
available in those categories.

## Output layout

```
output/
  task1/
    books.json          # {category: [book, ...]} with full metadata
    books.csv           # flat table of the same records
    summary.json        # counts, per-category totals, timing
    images/
      fiction/<book-slug>_<hash>.jpg
      science/...
      travel/...
  task2/
    ... same structure, one image folder per category
```

Image filenames are `<title-slug>_<8-char-hash-of-image-url>.<ext>`; the hash
suffix keeps two books with the same title from overwriting each other.

Each book record contains: `title`, `category`, `upc`, `price_incl_tax`,
`price_excl_tax`, `tax`, `rating` (1–5), `availability`, `stock_count`,
`num_reviews`, `description`, `product_url`, `image_url`, plus the download
outcome (`image_status`, `image_path`, `image_bytes`).

## How it works

```
index.html
   └─ sidebar → 50 category URLs                 parsers.parse_categories
        └─ category listing (+ "next" pages)     parsers.parse_listing
             └─ product page                     parsers.parse_product
                  └─ GET image_url → disk        downloader.ImageDownloader
```

The image URL is only known after the product page has been fetched, so the
download always happens *after* visiting the product page, as required.

## Verifying the results

`verify.py` re-fetches ground truth from the live site and checks it against
what is on disk — it does not trust the crawler's own logs:

```bash
python verify.py      # 30 checks, exit code 0 when all pass
```

It confirms, among other things, that each category's book count equals the
total the site itself advertises, that every recorded image exists on disk as a
valid JPEG of the recorded size with no orphan files, that saved bytes are
byte-identical to a fresh GET of the image URL, and — the key requirement —
that the downloaded images are the **product-page** images and not the smaller
listing-page thumbnails (the two are different files in the site's media cache).

Last run: **30/30 checks passed**.

## Modules

| File | Responsibility |
| --- | --- |
| `config.py` | URLs, category defaults, delays, output paths |
| `http_client.py` | shared `requests.Session`, throttling, 3 retries with backoff |
| `parsers.py` | all BeautifulSoup selectors, in one place |
| `downloader.py` | image GET, filename slugging, skip-if-present |
| `crawler.py` | orchestration: categories → listings → products → images |
| `storage.py` | JSON / CSV writers and the run summary |
| `cli.py` | argparse entry point |
| `../verify.py` | independent post-run verification against the live site |

## Notes

- Requests are throttled and retried; a failed image is recorded as
  `image_status: "failed"` rather than aborting the run.
- Re-running skips images already on disk unless `--overwrite` is passed.
- All results are tracked in git, including the 255 downloaded cover images.
