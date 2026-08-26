# Book cover images - Scrapy spider with a custom image pipeline

Crawls [books.toscrape.com](https://books.toscrape.com/), outputs each book's **title** and
the **absolute URL of its cover**, and saves the cover itself to
`downloaded_images/<category>/<title>.jpg` through a hand-written Scrapy pipeline.

Self-contained: its own `scrapy.cfg`, its own project package, its own output directory.
It shares nothing with [`../crawler/`](../crawler/), which is a separate project.

```bash
cd image_pipeline_crawler
scrapy crawl book_spider -a category="Science" -a title_keyword="robot"
```

## Layout

```text
image_pipeline_crawler/
├── README.md                    this file
├── scrapy.cfg                   points Scrapy at bookcovers.settings
├── bookcovers/
│   ├── items.py                 the two exported fields, plus category for the pipeline
│   ├── naming.py                title/category -> safe file names, doctested
│   ├── pipelines.py             CoverImagePipeline - the custom image pipeline
│   ├── settings.py              politeness, paths, feed export
│   └── spiders/book_spider.py   traversal and the URL filtering rules
├── downloaded_images/           written at run time - <category>/<title>.jpg
│   └── science/the-grand-design.jpg
└── output/covers.json           written at run time - title + image_url
```

Both `downloaded_images/` and `output/covers.json` are committed, so the result of a full
run can be inspected without crawling the site again. Only `__pycache__/` is git-ignored.

## Running it

Needs Scrapy (`pip install -r ../requirements.txt`, pinned at 2.17.0) and Python 3.10+.
Run from this directory, where `scrapy.cfg` lives.

```bash
# Whole catalogue: 1,000 books, 1,000 covers
scrapy crawl book_spider

# One category
scrapy crawl book_spider -a category="Science"

# One category, titles containing a word
scrapy crawl book_spider -a category="Childrens" -a title_keyword="robot"

# Titles containing a word, anywhere in the catalogue
scrapy crawl book_spider -a title_keyword="girl"
```

Both arguments are optional and independent. Omitting both crawls everything.

### A note on the brief's example command

```bash
scrapy crawl book_spider -a category="Science" -a title_keyword="robot"
```

This runs correctly and exports zero items, because the site has exactly one book with
"robot" in the title - *The Wild Robot* - and it is filed under **Childrens**, not Science.
The two filters are ANDed, so the empty result is the right answer. Swap in
`-a category="Childrens"` to see the same command produce a row and a file:

```text
output/covers.json                       [ { "title": "The Wild Robot", "image_url": "https://..." } ]
downloaded_images/childrens/the-wild-robot.jpg
```

The end-of-run log line says which filter did the excluding, so an empty run is never a
mystery:

```text
[book_spider] INFO: Finished (finished): 0 books yielded, 34 skipped by
                    title_keyword='robot', category='Science'
```

## Output

`output/covers.json`, UTF-8, exactly the two fields the brief asks for:

```json
[
{
  "title": "Seven Brief Lessons on Physics",
  "image_url": "https://books.toscrape.com/media/cache/ae/f9/aef933758e39ba5e4327b2152478bb1a.jpg"
},
{
  "title": "The Selfish Gene",
  "image_url": "https://books.toscrape.com/media/cache/d7/63/d763b806d6f0fb6580f16d08e00bdba6.jpg"
}
]
```

Category is deliberately **not** in there. The pipeline needs it to pick a directory, so the
item carries it, but `FEED_EXPORT_FIELDS` in `settings.py` lists only `title` and
`image_url`. That is how the item can hold three fields while the output holds two.

Every run without `-o`/`-O` rewrites `output/covers.json`, so a filtered run replaces a
full one. Name your own destination to keep a run separate:

```bash
scrapy crawl book_spider -a category="Poetry" -O poetry.json
```

`settings.py` suppresses the default feed whenever the command line names an output. That
guard is deliberate: Scrapy's `-o`/`-O` *adds* a feed rather than replacing `FEEDS`, so
without it a redirected run would still overwrite `covers.json` on the way past.

## URL filtering

### Simple: only follow product pages

The rule from the brief, `/catalogue/.*\.html`, is used verbatim as the `allow` pattern of
the product `LinkExtractor`. On its own it is slightly too generous, because two kinds of
non-product URL also match it:

| URL | Matches `/catalogue/.*\.html`? | What it is |
|---|---|---|
| `/catalogue/the-grand-design_405/index.html` | yes | a product - wanted |
| `/catalogue/category/books/science_22/index.html` | yes | a category index |
| `/catalogue/page-2.html` | yes | site-wide listing page 2 |

So the product rule pairs the brief's pattern with a `deny` list of `/catalogue/category/`
and `/page-\d+\.html`. Without it the spider would parse a listing page as a book, find no
`<h1>`, and emit an item with a null title.

A second rule follows those same listing pages for links, with `follow=True` and no
callback. The two rules split the job cleanly: one decides what is a book, the other decides
what is worth walking.

Product pages are leaves. `follow` defaults to `False` when a `Rule` has a callback, so the
"you may also like" links at the bottom of a product page are never followed - which is what
stops a category-filtered crawl from wandering into neighbouring categories.

### Complex: `-a category` and `-a title_keyword`

**`category`** is enforced at two points, because one is not enough:

1. `process_links` on the navigation rule drops category and pagination links that do not
   belong to the requested category. Comparison is by slug, so `"Science Fiction"`,
   `"science fiction"` and `"science-fiction"` all reach the same pages, and the site's own
   `_22` id suffix is stripped before comparing.
2. `process_request` on the *product* rule drops product links found on a page outside the
   requested category. This is the one that is easy to miss: the start URL is the home page,
   whose listing shows the first 20 books of the whole catalogue. Those links match the
   product pattern and have nothing to do with navigation, so `-a category="Science"` would
   otherwise return 34 books - the 14 real ones plus those 20. `process_request` is the only
   rule hook that can see *which page a link was found on*, which is exactly what the
   decision needs.

The filter runs on links, not on scraped items, so `-a category="Science"` costs 31 requests
instead of roughly 2,000. Nothing outside the category is ever fetched.

**`title_keyword`** is a case-insensitive substring test applied in the spider callback, on
the product page's `<h1>`. Applying it there rather than in the pipeline means the exported
rows and the files on disk always describe the same set of books, and a filtered run does no
image downloads it will not keep. It cannot be pushed onto links, because the listing pages
truncate titles ("A Light in the ...") - the full title only exists on the product page.

## The custom image pipeline

`bookcovers/pipelines.py`. Scrapy ships `ImagesPipeline`, but it wants Pillow, it names files
after a SHA-1 of the URL, and it puts everything in one flat `full/` directory - none of
which the brief asks for. So this is written from scratch.

```text
downloaded_images/<slugified category>/<slugified title><extension>
```

**Non-blocking.** `process_item` is a coroutine that hands the image request to the engine's
downloader and awaits it:

```python
request = Request(image_url, callback=NO_CALLBACK)
response = await self.crawler.engine.download_async(request)
```

Calling `requests.get(...)` here instead would block the Twisted reactor and serialise the
entire crawl behind one image at a time. Going through the engine also means covers inherit
the project's delay, retries and downloader middlewares rather than bypassing them.
`TWISTED_REACTOR` is set to the asyncio reactor in `settings.py`, which is what makes the
`await` legal.

**Naming.** `naming.slugify` folds accents to ASCII, lowercases, and joins words with
hyphens, so *"Surely You're Joking, Mr. Feynman!: Adventures of a Curious Character"* becomes
`surely-you-re-joking-mr-feynman-adventures-of-a-curious-character.jpg`. The same function
names the directory, so a category and a title are named by one rule. Slugs are capped at 120
characters and truncated on a word boundary, which keeps the full path inside the
260-character limit Windows still applies to most APIs. Windows' reserved stems (`con`,
`nul`, `com1`...) are given a `-book` suffix rather than failing the write.

**Collisions.** Two books can share a title inside one category. Destinations are reserved in
a set before the first `await`, so concurrent items cannot claim the same path, and a second
book with the same title is written as `<title>-2.jpg` instead of silently overwriting the
first.

**Failures are counted, not raised.** A 404 cover, a timeout, an empty body: each is logged,
tallied, and the item is still returned, so one bad image never costs the other 999 rows. A
book whose page has no cover at all is exported with `"image_url": null` rather than dropped -
a visible null is a bug report, a missing row just looks like a shorter crawl. The run ends
with the tally:

```text
[bookcovers.pipelines] INFO: Covers: 14 saved, 0 already on disk, 0 failed,
                             0 items had no URL. Stored under ...\downloaded_images
```

**Re-runs are cheap.** A cover already on disk is skipped, so an interrupted crawl is safe to
restart. `-s COVERS_OVERWRITE=True` forces a refetch, and `-s COVERS_STORE=...` moves the
store.

## Which image

`#product_gallery img::attr(src)` on the product page - the full-size cover (~50 KB), not the
listing thumbnail. The site serves it as a relative `../../media/cache/...` path, so the
spider resolves it with `response.urljoin` to produce the absolute URL the brief asks for.

## Tests

`naming.py` is pure and doctested - no network, no Scrapy, no disk:

```bash
python -m doctest bookcovers/naming.py    # silence means they passed
```
