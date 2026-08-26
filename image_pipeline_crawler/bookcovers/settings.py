"""Scrapy settings for bookcovers.

Only what differs from Scrapy's defaults, with the reason. Loaded via
``image_pipeline_crawler/scrapy.cfg``.

Paths are anchored to this file rather than the shell's working directory, so
``downloaded_images/`` and ``output/`` always land inside the project folder
however the crawl was launched.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

BOT_NAME = "bookcovers"

SPIDER_MODULES = ["bookcovers.spiders"]
NEWSPIDER_MODULE = "bookcovers.spiders"

# Politeness
# Identify honestly rather than pretending to be a browser.
USER_AGENT = "bookcovers/1.0 (+technical assessment; contact: candidate@example.com)"

# The site serves no robots.txt, so this changes nothing here, but keeps the
# default safe if the spider is ever pointed elsewhere.
ROBOTSTXT_OBEY = True

# Every item costs a second request (the cover), so this crawl makes roughly
# twice the requests of a data-only one. Eight at a time with a short delay
# keeps it gentle; AutoThrottle backs off on its own if the site slows down.
CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 8
DOWNLOAD_DELAY = 0.25

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 0.25
AUTOTHROTTLE_MAX_DELAY = 10.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 8.0

# Reliability
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]

DOWNLOAD_TIMEOUT = 30

# Covers are ~50 KB each, well inside Scrapy's 1 GB warning threshold, but the
# body is held in memory until the pipeline writes it, so keep the cap honest.
DOWNLOAD_MAXSIZE = 8 * 1024 * 1024

# Pipelines
ITEM_PIPELINES = {
    "bookcovers.pipelines.CoverImagePipeline": 300,
}

# Where the custom pipeline writes. Overridable per run:
#   scrapy crawl book_spider -s COVERS_STORE=/tmp/covers
COVERS_STORE = str(PROJECT_ROOT / "downloaded_images")

# Re-runs skip covers already on disk. Set True to refetch everything.
COVERS_OVERWRITE = False

# Output
# The brief's command line carries no -o, so a default destination is set here
# and every plain run writes output/covers.json.
#
# The guard matters: Scrapy's -o/-O *adds* a feed rather than replacing FEEDS,
# so without it a run redirected elsewhere would still overwrite covers.json
# on the way past. Naming an output on the command line now means that file
# and only that file.
_OUTPUT_FLAGS = {"-o", "-O", "--output", "--overwrite-output"}

if not _OUTPUT_FLAGS.intersection(sys.argv):
    FEEDS = {
        PROJECT_ROOT / "output" / "covers.json": {
            "format": "json",
            "encoding": "utf-8",
            "indent": 2,
            "overwrite": True,
        },
    }

# The two fields the brief asks to output, and only those. The item also
# carries `category`, which the pipeline needs for the directory name and
# which this list deliberately leaves out of the exported file.
FEED_EXPORT_FIELDS = ["title", "image_url"]

# Keeps titles such as "Mesaerion: The Best Science Fiction Stories 1800-1849"
# and any accented characters readable instead of turning into \uXXXX escapes.
FEED_EXPORT_ENCODING = "utf-8"

# Misc
# The asyncio reactor is what lets the pipeline's `await` on a download work.
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
LOG_LEVEL = "INFO"
