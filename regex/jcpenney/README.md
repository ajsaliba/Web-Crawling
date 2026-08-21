# JCPenney URL Regular Expressions

Six regular expressions for jcpenney.com URLs — five page types plus `titles`,
which reads two of them for the name they carry — and a script that tests any
URL against any of them.

| File | |
|---|---|
| [`regex.txt`](regex.txt) | the six expressions, in `name: regex` form |
| [`jcpenney_regex.py`](jcpenney_regex.py) | the same six as comments, compiled, with a CLI and a test suite |
| [`links.txt`](links.txt) | the source URLs the patterns were derived from |

Each pattern is written three times — compiled in the script, quoted in the
comment above it, and listed in `regex.txt`. The script fails if the three ever
disagree, so `regex.txt` cannot silently drift out of date.

Standard library only, no dependencies. Run on Python 3.12; nothing in it
requires newer than 3.7, though that is unverified here.

## Testing a URL

```
python jcpenney_regex.py <type> <url>
```

`<type>` is one of `catalog`, `search`, `product`, `titles`, `images`,
`videos`, or `any`.

```console
$ python jcpenney_regex.py catalog "https://www.jcpenney.com/g/shoes?brand=adidas&id=dept20000018"
PASS  catalog https://www.jcpenney.com/g/shoes?brand=adidas&id=dept20000018
        catalog_id = dept20000018
        slug = shoes
        brand = adidas
        title = Adidas
```

A pass prints what the pattern captured, not just the verdict. A pattern that
matches but extracts the wrong brand or a truncated id has still failed at its
job, and that is invisible from `PASS` alone.

**Quote the URL.** An unquoted `&` backgrounds the command in bash and is a
parse error in PowerShell.

### Reading a failure

A failure says whether any *other* pattern matched, which is the difference
between a misfiled URL and a pattern that does not generalize:

```console
$ python jcpenney_regex.py images "https://www.jcpenney.com/p/biltmore-mens-fedora/ppr5008442615"
FAIL  images  https://www.jcpenney.com/p/biltmore-mens-fedora/ppr5008442615
        no match, but it matches product

$ python jcpenney_regex.py images "https://sc-images.jcpenney.com/Other/DP0912202511211127M"
FAIL  images  https://sc-images.jcpenney.com/Other/DP0912202511211127M
        no match, and no other pattern matched it either
```

The first is a labelling problem. The second is a URL shape no pattern covers —
the one to look at if you are testing whether the expressions generalize.

### `any` — which patterns match this?

Give a URL without committing to a type:

```console
$ python jcpenney_regex.py any "https://sc-videos.jcpenney.com/JCPenney/9152867A_V_VA_5-1OZ"
PASS  any     https://sc-videos.jcpenney.com/JCPenney/9152867A_V_VA_5-1OZ
        video_id = 9152867A_V_VA_5-1OZ
        matched by: videos
```

It passes if at least one pattern matched. Useful for classifying a URL shape
you have not filed yet.

### Several at once

Pairs on the command line:

```console
$ python jcpenney_regex.py search "https://www.jcpenney.com/s?searchTerm=red+pants" images "https://www.jcpenney.com/p/x/ppr1"
PASS  search  https://www.jcpenney.com/s?searchTerm=red+pants
        term = red+pants
        decoded_term = red pants
FAIL  images  https://www.jcpenney.com/p/x/ppr1
        no match, but it matches product

1/2 passed
```

Or one `type url` per line on stdin, with `-`. Blank lines and `#` comments are
skipped:

```console
$ cat cases.txt
# product pages
product https://www.jcpenney.com/p/biltmore-mens-fedora/ppr5008442615
videos  https://sc-videos.jcpenney.com/JCPenney/GOLF-leFLEUR-FRENCH-WALTZ

$ python jcpenney_regex.py - < cases.txt
```

### Exit status

| | |
|---|---|
| `0` | every case passed |
| `1` | at least one case failed |
| `2` | bad usage — unknown type, or an odd number of arguments |

So it drops into a script or CI step directly:

```bash
python jcpenney_regex.py images "$url" || echo "unrecognised image URL: $url"
```

## The self-test

With no arguments — or `--self-test` — it runs the bundled suite instead:

```console
$ python jcpenney_regex.py
6 patterns x 30 URLs from links.txt, plus 18 edge cases
...
All patterns matched what they should and rejected everything else.
```

It checks four things:

1. Every URL in `links.txt` matches the patterns it should, **and is rejected
   by every other pattern**. Cross-rejection is what catches a pattern that has
   grown too loose. Which patterns *should* match is decided per URL by
   `expected_kinds()`, not per section — the "Title URLs" section holds both
   listing and product URLs, so each entry is classified by shape and then
   given `titles` on top.
2. The extracted values are right, not merely present — titles against the
   names annotated in `links.txt` (`... for Alfred Dunner`), search terms
   against the decoded term in parentheses.
3. Eighteen edge cases: URLs that must be rejected (wrong host, wrong CDN
   folder, extra path segment, `id=` that is neither `cat` nor `dept`) and
   awkward ones that must be accepted.
4. That the compiled patterns, their comments, and `regex.txt` are identical.

Exit status is `0` only if all of it passes.

## Using the patterns in code

```python
from jcpenney_regex import PATTERNS, PRODUCT_RE, title_of

match = PRODUCT_RE.match(url)
if match:
    product_id = match["product_id"]      # ppr5008539456
    slug = match["slug"]                  # biltmore-mens-fedora

title = title_of(url)                     # "Adidas" / "Biltmore Mens Fedora",
                                          # or None if the URL carries no title
```

Groups are named, so a caller reads `match["brand"]` rather than `match[2]`.

| Pattern | Captures |
|---|---|
| `CATALOG_RE` | `catalog_id` |
| `SEARCH_RE` | `term` (raw; `urllib.parse.unquote_plus` to decode) |
| `PRODUCT_RE` | `slug`, `product_id` |
| `TITLES_RE` | `slug`, `brand`, `product_slug` |
| `IMAGES_RE` | `image_id` |
| `VIDEOS_RE` | `video_id` |

`PATTERNS` maps each type name to its compiled pattern; `PRIMARY` maps each to
the one capture that is its identity.

## Design notes

**Titles are not a URL class.** "Title URLs" says *this URL carries a display
title*, which is true of listing pages and product pages alike — so `titles`
overlaps `catalog` and `product` on purpose, and the script does not report that
overlap as a problem. Treating the section as a synonym for "listing pages" is
exactly the mistake that made `titles` reject product URLs in an earlier
version.

The title is never in the same place twice:

| URL | Title | From |
|---|---|---|
| `/g/shoes?brand=adidas&id=…` | *adidas* | the `brand` parameter, which wins over the path |
| `/g/home-store/kitchen-dining/cooks?id=…` | *cooks* | the last path segment |
| `/p/biltmore-mens-fedora/ppr…` | *biltmore-mens-fedora* | the product slug |

`TITLES_RE` has one branch per page type, captures all three, and the caller
takes the first that is present:

```python
raw = match["brand"] or match["product_slug"] or match["slug"]
title = raw.replace("-", " ").title()
```

The three groups need distinct names because Python's `re` rejects a name reused
across branches of an alternation.

**`&amp;` is accepted wherever `&` is,** because these URLs are read out of HTML
attributes where the ampersand arrives escaped — four of the sample URLs are in
that form.

**The CDN patterns tolerate a missing `?`.** A URL like
`.../DP0710202307351034Mwidth=550&amp;height=550` is malformed — the parameters
are in the path, and requesting it verbatim would 404 — but it turns up when a
`?` is lost in extraction, and the id in front of it is unambiguous. Matching it
lets a caller recover the id and rebuild a working URL instead of dropping the
image. The lookahead that cuts the id there is deliberately lowercase-only:
parameter names are lowercase, so the scan stops at `width=` and the trailing
uppercase `M` stays on the id. Allowing capitals would stop at `Mwidth=` and
return a truncated id that looks plausible and fetches nothing.

**Everything is anchored at both ends,** so `https://www.jcpenney.com.evil.com/g/shoes?id=cat1`
and `/p/foo/ppr123/extra` are rejected rather than matched loosely.

## Adding a pattern

1. Add the comment and the compiled pattern to `jcpenney_regex.py`, keeping the
   comment text identical to the pattern.
2. Add it to `PATTERNS`, `EXPECTED`, `EXPECTED_OVERLAP`, and `PRIMARY`.
3. Add the same line to `regex.txt`.
4. Run `python jcpenney_regex.py` — the drift check fails if steps 1 and 3
   disagree, and the cross-rejection check fails if the new pattern claims URLs
   that belong to another type.
