"""Tunable settings for the books.toscrape.com image crawler."""

from pathlib import Path

BASE_URL = "https://books.toscrape.com/"
INDEX_URL = BASE_URL + "index.html"

# Task 1: three distinct categories covering different topics.
TASK1_CATEGORIES = ["Fiction", "Science", "Travel"]

# Task 2: how many images to pull from every category on the site.
TASK2_IMAGES_PER_CATEGORY = 4

# Politeness / robustness.
REQUEST_DELAY = 0.25          # seconds between requests
TIMEOUT = 20                  # seconds per request
MAX_RETRIES = 3
RETRY_BACKOFF = 1.5           # seconds, multiplied by attempt number
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "bookimages-crawler/1.0 (educational scraping exercise)"
)

# Output layout.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
