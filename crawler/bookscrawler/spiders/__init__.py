"""Spider package. Scrapy imports every module here to find spiders.

books.py -> BooksSpider (name: "books"), the full books.toscrape.com crawl.

Spiders do traversal and selection only. Value cleanup belongs in
bookscrawler.parsers, anything spanning items in bookscrawler.pipelines.
"""
