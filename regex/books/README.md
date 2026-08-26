# Book listing pages, parsed with `re` alone

Nine regular expressions that pull every field out of an
`article.product_pod` block on a [books.toscrape.com](https://books.toscrape.com/)
listing page — titles, prices, cover URLs, star ratings and detail links —
compose them into one tuple per book, redact the prices, and filter to the
books rated three stars or better.

No BeautifulSoup, no lxml, no `html.parser`. `import re` and the standard
library's `pathlib`/`sys` for the CLI, nothing else.

| File | |
|---|---|
| [`books_regex.py`](books_regex.py) | the nine patterns, compiled, with a CLI and a 94-check self-test |
| [`regex.txt`](regex.txt) | the same nine, in `name: regex` form |
| [`listing_home.html`](listing_home.html) | `https://books.toscrape.com/` — the default page |
| [`listing_category.html`](listing_category.html) | `/catalogue/category/books_1/index.html` — same books, `../../../` image paths |
| [`listing_page2.html`](listing_page2.html) | `/catalogue/page-2.html` — a different 20 books |

Three pages, not one, because the interesting differences between them are
exactly what a brittle pattern trips over. Each writes its image `src` with a
different relative prefix — `media/cache/…` on the home page, `../media/cache/…`
on page 2, `../../../media/cache/…` on a category page. The home and category
pages list the same 20 books by design, which is what makes them a clean test
that the prefix is the only difference; page 2 brings a different 20, and a
different spread of ratings — the high-rated filter returns 11, 11 and 14.

Each pattern is written three times — compiled in the script, quoted in the
comment above it, and listed in `regex.txt`. The self-test fails if the three
ever disagree, so `regex.txt` cannot silently drift out of date.

## Running it

```bash
python books_regex.py <task> [page.html]
```

| Task | Part | |
|---|---|---|
| `titles` | 1.1 | every book title |
| `prices` | 1.2 | every price |
| `images` | 1.3 | every cover URL |
| `ratings` | 1.4 | every star rating |
| `urls` | 1.5 | every detail page URL |
| `records` | 2.6 | `(title, price, stars, image_url)` per book |
| `redact` | 3.7 | prices replaced with `[REDACTED]` |
| `high-rated` | 3.8 | only Three stars and up |

The page argument defaults to `listing_home.html`.

```console
$ python books_regex.py records
[
  ('A Light in the Attic', '£51.77', 'Three', 'media/cache/2c/da/2cdad67c44b002e7ead0cc35693c0e8b.jpg'),
  ('Tipping the Velvet', '£53.74', 'One', 'media/cache/26/0c/260c6ae16bce31c8f8c95daddd9f4a1c.jpg'),
  ('Soumission', '£50.10', 'One', 'media/cache/3e/ef/3eef99c9d9adef34639f510662022830.jpg'),
  ...
]

$ python books_regex.py high-rated listing_page2.html
[
  ('Foolproof Preserving: A Guide to Small Batch Jams, ...', '£30.52', 'Three', '../media/cache/9f/59/…'),
  ('Chase Me (Paris Nights #2)', '£25.27', 'Five', '../media/cache/9c/2e/…'),
  ...
]
```

With no arguments it runs the self-test over all three pages. Exit status is
`0` only if every check passed, so it drops into CI directly.

```console
$ python books_regex.py
9 patterns over 3 saved listing pages
...
Every pattern extracted what it should, on every saved page.
```

## Part 1 — one field at a time

```
title:  <h3\b[^>]*>\s*<a\b[^>]*\btitle\s*=\s*"(?P<title>[^"]*)"
price:  <p\b(?=[^>]*\bclass\s*=\s*"[^"]*\bprice_color\b)[^>]*>\s*(?P<price>[^<]*?)\s*</p>
image:  <img\b(?=[^>]*\bclass\s*=\s*"[^"]*\bthumbnail\b)[^>]*\bsrc\s*=\s*"(?P<image_url>[^"]+)"
rating: <p\b[^>]*\bclass\s*=\s*"[^"]*\bstar-rating\s+(?P<rating>One|Two|Three|Four|Five)\b[^"]*"
detail: <h3\b[^>]*>\s*<a\b[^>]*\bhref\s*=\s*"(?P<detail_url>[^"]+)"
```

Four decisions worth naming:

**The title comes from the attribute, not the text.** The anchor text on the
page is truncated — `A Light in the ...` — and only the `title` attribute
carries the whole string.

**The rating is a class, not content.** `<p class="star-rating Three">` is
followed by five identical `<i class="icon-star">` elements whether the book
scored one star or five, so counting them tells you nothing. Only the class
does.

**The detail URL is anchored on `<h3>`.** Each pod carries the same href twice,
once on the cover image and once on the title. Without the `<h3>` anchor the
pattern returns 40 URLs for 20 books.

**Class membership is asserted with a lookahead.**
`<p\b(?=[^>]*\bclass\s*=\s*"[^"]*\bprice_color\b)[^>]*>` says "a `<p>` whose
attributes include this class" without consuming anything, so the class may sit
before or after any other attribute. Matching `<p class="price_color">` as a
literal would break the moment an attribute is added or reordered. The `\b`
around the class name is what stops `price_color_old` matching.

## Part 2 — composing them

`record` captures all four requested fields in one pass. The page writes them
in the order image → rating → title → price, and `records()` reorders them into
the tuple the brief asks for.

The interesting part is what sits *between* the fields:

```
GAP = (?:(?!</article>).)*?
```

A tempered dot: any character, as long as we are not standing at the start of
`</article>`. Plain `.*?` is not enough, and this is the trap the exercise is
built around.

`.*?` is non-greedy, so it looks like it stops at the first match. But
non-greedy only means *try shorter first* — if the rest of the pattern cannot
be satisfied, the engine backtracks and lets it grow. When a field is missing
from a block, or a value is constrained the way the rating is in `high`, it
grows straight past `</article>` into the next book.

That is not hypothetical. On the saved home page, the naive version of `high`
mis-pairs **3 of its 11 records**:

```
naive .*?   ('Sharp Objects', '£47.82', 'Four', 'media/cache/26/0c/260c6ae1…')
tempered    ('Sharp Objects', '£47.82', 'Four', 'media/cache/32/51/3251cf3a…')
```

The title, price and rating are all correct. Only the image is wrong — it
belongs to a book two positions earlier. That is what makes this failure worth
a test rather than a comment: a spot-check of the first field or two reports
success, and the corruption only shows in the field nobody reads.

The self-test asserts both halves — that the tempered pattern is right *and*
that the naive one is wrong — so the reason for the temper cannot quietly
become obsolete.

## Part 3 — redaction and filtering

**Redaction** substitutes on

```
money: Â?£\s*\d+(?:[.,]\d{1,2})?
```

`redact_prices()` returns the whole document with every price replaced by
`[REDACTED]`, so the result is still a page. It is idempotent — `[REDACTED]`
contains no price to find — and the self-test checks that nothing outside the
prices moved, and that titles still extract cleanly from the redacted HTML.

The optional `Â` catches the mojibake you get when a UTF-8 page is read as
cp1252 (`Â£51.77`), so a mis-decoded page still redacts rather than leaking the
price.

**Filtering** narrows the rating alternation inside the pattern itself:

```
(?P<rating>Three|Four|Five)
```

so a one-star block never becomes a match in the first place, rather than being
matched and then discarded. It is also what makes the tempered gap load-bearing
— see above.

## Robustness

The brief asks for matches that survive whitespace and formatting changes, so
the self-test reformats each page and re-runs everything:

| Change | Handled by |
|---|---|
| tags reflowed onto one line | `\s*` between tags, `re.S` |
| extra space after a tag name | `<p\b[^>]*` rather than `<p ` |
| `title = "..."` with spaces around `=` | `\s*=\s*` in every attribute |
| `<img class=… src=…>` reordered | lookahead for the class, `src` read separately |
| extra classes on an element | `\b`-delimited class names inside `[^"]*` |

Single-quoted attributes are the one variant deliberately not supported. Doing
it properly needs a backreference to the opening quote — `(["'])(.*?)\1` — and
Python's `re` forbids reusing a group name within one pattern, so the composed
`record` would need four separately named quote groups to gain nothing against
a site that quotes with `"`.

The `\s*=\s*` in the table above is there because the self-test caught its
absence: the patterns passed everything else and failed only the reflow check.

## Two notes on the data

**Titles arrive with entities.** `Shakespeare&#39;s Sonnets`,
`Scott Pilgrim&#39;s Precious Little Life`. `html.unescape` would decode them
but lives in the package the brief rules out, so `unescape_entities()` does it
with `re` and a lookup table — numeric, hex and named forms, leaving anything
unrecognised untouched rather than guessing. Pass `decode=False` to any
extractor to get the raw attribute text instead.

**Image URLs are returned exactly as the page writes them,** because resolving
them needs the page URL, which the HTML does not contain. `absolute_image_urls(html, page_url)`
does that separately, and the self-test checks it against both a home page
(`media/cache/…`) and a category page (`../../../media/cache/…`), which resolve
to the same absolute URL.

This is also where the brief's sample output differs from the live site. Its
titles, prices and ratings match today's page exactly, but its image URLs carry
a `../../` prefix that no current page emits, and one of its two hashes does not
appear anywhere on the site now. The sample was taken from an older snapshot;
the values here are what the pages actually serve today.

## The self-test

94 checks. Beyond counting 20 of everything on each page, it verifies:

1. **Three independent extraction routes agree** — the composed `record`
   pattern, the five single-field patterns run over the whole page, and a
   block-split-then-extract pass. Any pattern straddling a block boundary
   makes them diverge.
2. **The tempered gap earns its place** — the naive `.*?` variant is asserted
   to be wrong, with a count.
3. **Redaction is contained** — nothing outside the prices changes, it is
   idempotent, and titles still extract afterwards.
4. **Reformatting changes nothing** — every result is recomputed on a reflowed,
   attribute-reordered copy of each page.
5. **The three copies of every pattern agree** — compiled, comment, `regex.txt`.

Adding a pattern means updating all three copies and `PATTERNS`; the drift check
fails if you miss one.
