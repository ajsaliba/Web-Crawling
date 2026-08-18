"""Scrapy settings for bookscrawler (Part 1).

Only what differs from Scrapy defaults, with the reason. The output path is
not set here - it is passed per run, so a test run cannot overwrite books.json
by accident. Loaded via crawler/scrapy.cfg.
"""

BOT_NAME = "bookscrawler"

SPIDER_MODULES = ["bookscrawler.spiders"]
NEWSPIDER_MODULE = "bookscrawler.spiders"

# Politeness
# Identify honestly rather than pretending to be a browser.
USER_AGENT = "bookscrawler/1.0 (+technical assessment; contact: candidate@example.com)"

# The site serves no robots.txt, so this changes nothing here, but keeps the
# default safe if the spider is pointed elsewhere.
ROBOTSTXT_OBEY = True

# 8 concurrent requests with a short delay gets the full catalogue in about
# five and a half minutes, which is fast enough and stays gentle on the server.
# AutoThrottle backs off on its own if the site starts responding slowly.
CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 8
DOWNLOAD_DELAY = 0.25

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 0.25
AUTOTHROTTLE_MAX_DELAY = 10.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 8.0

# Reliability
# Retry transient failures; the defaults cover fewer status codes than this.
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]

DOWNLOAD_TIMEOUT = 30

# Pipelines: dedup first, so coverage numbers describe what was exported.
ITEM_PIPELINES = {
    "bookscrawler.pipelines.DuplicateBookPipeline": 100,
    "bookscrawler.pipelines.RequiredFieldsPipeline": 200,
}

# Output
# UTF-8 with unescaped non-ASCII keeps titles such as "Mesaerion: The Best
# Science Fiction Stories 1800-1849" and any accented characters readable in
# the exported JSON instead of turning them into \uXXXX escapes.
FEED_EXPORT_ENCODING = "utf-8"
FEED_EXPORT_INDENT = 2

# Fixed key order, so diffs between runs stay readable.
FEED_EXPORT_FIELDS = [
    "title",
    "price",
    "currency",
    "availability",
    "category",
    "upc",
    "description",
    "product_url",
    "image_url",
]

# Misc
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
LOG_LEVEL = "INFO"
