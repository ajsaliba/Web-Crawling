# Part 3 - Website Investigation

**Site:** `https://www.allbirds.com`
**Product page used:** `/products/mens-wool-runners-natural-white`
**Date:** 18 August 2026
**Tools:** Python `requests` (`investigate_site.py`), `curl`, `grep`, View Source, DevTools

No CAPTCHA, login or access control was hit, and none was probed. Every request below is
a plain public `GET` at a low rate. Run `python investigate_site.py` to re-derive the
figures; catalogue-dependent counts drift as stock changes.

---

## A. Rendering

**Product pages are server-rendered. Collection and search grids are not.** The split
decides the discovery strategy, so it matters more than a yes/no.

One `curl`, no JavaScript engine, 687,170 bytes back:

| Signal | In the raw HTML |
|---|---|
| `<title>` / `<h1>` | both present, correct product name |
| JSON-LD blocks | 2 (`ProductGroup`, `aggregateRating`) |
| `"@type": "Product"` | 29 occurrences |
| `/cdn/shop/` image paths | 35 unique |
| `.mp4` / `.m3u8` URLs | 3 each |
| `var meta = {...}` | present, with id/price/sku per variant |

If the page needed JS for product data, the response would be an empty container plus a
bundle URL. Instead the markup is finished and the data is embedded alongside it.

The collection grid is different:

```bash
curl -s "https://www.allbirds.com/collections/shoes" -o c2.html   # 200, 1,941,096 bytes
grep -oE '/products/[a-z0-9-]+' c2.html | sort -u | wc -l          # -> 5
grep -oE '"handle":"[a-z0-9-]+"' c2.html | sort -u | wc -l         # -> 218
```

Five real anchors, 218 product handles in embedded JSON. The grid is built client-side
from data already in the response, so a crawler can read the JSON and skip the browser.
`/search?q=` behaves the same way: 200, 4.4 MB, 13 anchors for far more results.

No headless browser is needed anywhere here, but a link-following crawler would find
almost nothing. See section E.

---

## B. Structured data

Four sources, ranked by how I would use them.

**1. `/products/<handle>.json` - what I would extract from.** HTTP 200, 8,127 bytes:

```text
title        : "Men's Wool Runner - Natural White (Cream Sole)"
product_type : "Shoes"    vendor: "Allbirds"
options      : [("Size", 7)]
variants     : 7  - id, sku, price, option1..3, image_id, inventory_quantity
images       : 4  - full CDN URLs
```

The store's own data contract rather than a rendering of it. 8 KB against 687 KB, no
selectors to break on a redesign, and the only source with a full variant matrix
including per-variant SKU, price, stock and image binding.

**2. JSON-LD** - `ProductGroup` with `name`, `image`, `offers` (price 110 USD, InStock)
and `variesBy` [size, color]. Standardised and portable, but its 28 `hasVariant` entries
hold only `{"@type", "url"}`. Fine for title, description, images and price; not enough
for variants.

**3. `var meta = {...}`** - Shopify's analytics object. Has `id`/`price`/`sku` per
variant, but prices are in **cents** (`11000` = $110.00). Useful as a cross-check only.

**4. HTML selectors** - `h1`, `.price`, gallery `img`. Works, and is the first thing a
theme update breaks.

Order: product JSON, then JSON-LD, then selectors for anything neither carries. Each step
down is more fragile but more likely to exist on an arbitrary store.

---

## C. Platform

**Shopify (Plus) behind Cloudflare.** Five independent signals:

| # | Evidence |
|---|---|
| 1 | `powered-by: Shopify` response header - decisive on its own |
| 2 | `shopify-complexity-score` and `x-redirect-reason: shop_redirect` headers |
| 3 | `server-timing: ... pageType;desc="product", theme;desc="130450260048"` |
| 4 | URL scheme: `/products/<handle>`, `/collections/<handle>`, `/cdn/shop/...` |
| 5 | `/products/<handle>.json` returns the standard Shopify product schema |

Also `window.ShopifyAnalytics` (12 references), `server: cloudflare` and `cf-ray`
headers, and the store id `11044168` in `robots.txt` (`Disallow: /11044168/checkouts`).

---

## D. Direct HTTP request

| Question | Finding |
|---|---|
| HTTP status | `200 OK` |
| Meaningful product HTML? | Yes - 687,170 bytes with `h1`, JSON-LD, variants, 35 images, 3 videos |
| Differs from the browser? | Not materially |
| Blocking or challenge? | None - no CAPTCHA, no JS challenge, no rate limit, no cookie wall |

Repeating the request with curl's default `User-Agent: curl/8.21.0` returned the same
687,170 bytes. Diffing the two gives 35 changed lines, all of it per-request noise:
`__st` session ids, and third-party app blocks injected in a different order. No product
content differs, so there is no reason to spoof a User-Agent.

**One behaviour worth knowing about.** A stale product handle does not 404. It returns a
`301` to `/collections/mens` with `x-redirect-reason: shop_redirect`, and the final
response is `200 OK` on a non-product page. A crawler checking only `status == 200` would
store a collection page as a product. This is Scenario 1 of Part 5, live. The defence is
to assert `__st.rtyp == "product"`, or that JSON-LD `@type` is `Product`/`ProductGroup`,
before accepting a response, and to treat a redirect that changes the path type as a
soft 404.

`robots.txt` disallows `/cart`, `/checkout`, `/account`, `/orders` and faceted collection
URLs. It does not disallow `/products/` or plain `/collections/`, so the plan below stays
inside the allowed paths.

---

## E. Extraction strategy

**Find products via the sitemap, not the grid.** The collection HTML exposes 5 of 218
products as links. Two better routes:

1. `/sitemap.xml` -> `/sitemap_products_1.xml` - 291 product URLs with `<lastmod>`, so
   incremental re-crawls are cheap. My primary route.
2. `/collections/<handle>/products.json?limit=250` (`&page=N`) - full product objects,
   one request per 250.

| Field | Primary (product JSON) | Fallback |
|---|---|---|
| Title | `product.title` | JSON-LD `name`, then `h1` |
| Main image | `product.images[0].src` | JSON-LD `image[0]`, then `og:image` |
| Extra images | `product.images[*].src` | JSON-LD `image[*]`, deduped by CDN path |
| Variants | `product.variants[*]`: `sku`, `price`, `option1..3` zipped with `product.options[*].name`, `image_id` looked up in `images[*].id` | `var meta` (price in cents); JSON-LD gives URLs only |
| Videos | not in product JSON | regex the HTML for `/cdn/shop/videos/...mp4`, prefer `.mp4` over the `.m3u8` variant |
| Product URL | built from `product.handle` | `<link rel='canonical'>` |

Three things I would get right up front:

**Attribute quoting.** This theme uses single quotes (`rel='canonical'`,
`href='/products/...'`). A double-quoted pattern reports those tags as missing and the
extractor quietly falls through to a worse source. It caught me twice here: a grep for
`property="og:..."` returned 0 where the real count is 9, and the same mistake made me
record 0 search anchors where there are 13. Both figures above are corrected. Match
`['\"]` in any attribute regex, or use a parser, which does not care.

**Image URLs.** Shopify appends `?v=<timestamp>&width=<n>`. Strip the query string, or
the same asset gets stored many times over.

**Variant images.** The binding is `variants[].image_id -> images[].id`. Skipping it is
what makes colour variants all share the gallery's first picture, which is Scenario 2 of
Part 5.

Before trusting a run: check `__st.rtyp == "product"`, require a title and at least one
image, and compare the crawled count against the sitemap's 291. A large shortfall means
discovery broke, not extraction.

**Transport: plain HTTP.** Every field above comes out of a static response, most from an
8 KB JSON endpoint. A headless browser buys nothing here.
