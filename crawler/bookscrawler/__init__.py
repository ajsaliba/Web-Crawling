"""Scrapy project for books.toscrape.com (Part 1).

items.py      the exported fields
parsers.py    text and price cleanup, no Scrapy imports so it is testable alone
pipelines.py  dedup by UPC, plus a field-coverage report at the end of a run
settings.py   politeness, retries, feed export
spiders/      traversal and selectors

Split this way so a change lands in one place: selectors in spiders/, output
shape in items.py and settings.py, string handling in parsers.py.
"""
