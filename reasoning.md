# Part 5 - Engineering Reasoning

## Scenario 1 - HTTP 200 with a maintenance or challenge page

**No.** 200 means the server answered, not that it answered with what you asked for.
Challenge pages, maintenance notices and soft 404s are routinely served as 200, sometimes
on purpose, so a crawler that trusts the status keeps believing it works.

I hit this in Part 3: a stale Allbirds product handle 301s to a collection page and the
final response is a clean `200 OK`. Status alone would have stored a category listing as
a product.

What I would check, cheapest first:

1. **Content.** Does the body contain the fields that define a product page - a title, a
   price, a JSON-LD `Product` block? This is the real test.
2. **Response size.** A challenge page is a few KB against a normal page's hundreds. A
   sudden drop in mean response size across a run is the fastest warning.
3. **Final URL after redirects.** `/products/...` ending on `/collections/...` is a soft
   404 whatever the status says.
4. **Challenge fingerprints.** `cf-mitigated` headers, "Just a moment", "Checking your
   browser", an unexpected challenge cookie, a body that is almost entirely JavaScript.
5. **How many.** Every URL returning a small 200 is a block. One URL doing it is a
   delisted product.

A failed content check is a retryable failure, not a success. Back off and retry, and
never let the empty result overwrite good stored data. The dangerous outcome is not a
crash, it is a run that "succeeds" and wipes 2,000 products. If the challenge persists,
log it and stop.

## Scenario 2 - 45/50 products fine, the 5 with colour variants have no images

The clustering is the clue. The failures line up with a structural difference, not a
random one, which rules out flakiness and rate limiting - those do not pick out variant
products.

**First thing I would do:** fetch one failing and one working product and diff the raw
HTML. Same site, same template family, so the diff is small and points straight at it.

Likely causes, in the order I would test them:

1. **Variant products use different markup.** A single-variant product may render a
   static `<img>` while a multi-variant one renders a colour-switching gallery whose
   images live in a JS structure keyed by variant.
2. **Images are bound per variant, not per product.** On Shopify that is
   `variants[].image_id -> images[].id`. An extractor reading only a product-level list
   gets nothing when that list is populated lazily.
3. **The selector is too specific.** Something like `.product-gallery > img:first-child`
   breaks as soon as a variant picker wraps the gallery in another element.
4. **Lazy loading.** The real URL is in `data-src`, and `src` holds a placeholder, so
   every extracted URL is a 1x1 GIF.

Then fix it, re-run the 45 that already worked to be sure nothing regressed, and add an
assertion that every product has at least one image so this fails loudly next time
instead of leaving 5 quiet blanks.

## Scenario 3 - usually ~2,000 products, sometimes 300, fine ten minutes later

Intermittent, self-healing, and an 85% loss rather than 5%. That points at discovery
breaking, not extraction, which would degrade fields rather than counts.

1. **Rate limiting or soft blocking.** Sustained concurrency trips a threshold, the site
   starts returning 429s or challenge pages mid-run, and recovers when the window resets.
   Ten minutes is a very typical cool-off. **My first hypothesis** - nothing else fits the
   self-healing timing as well.
2. **Silent pagination failure.** One listing page times out, the "next" link is never
   found, and the crawl ends believing it finished. A crawler that treats "no next link"
   as success cannot tell finished from broken.
3. **Partial upstream outage.** A CDN node or category service is briefly unhealthy, so
   listing pages render with a fraction of their products and still return 200.
4. **Swallowed errors.** Failures caught and logged at DEBUG, exit code 0, and the missing
   1,700 products are invisible. Worth checking whether the run even recorded its non-200
   counts.
5. **A/B tests or personalisation.** Some sessions get a different layout whose selectors
   do not match, so most pages parse to zero.
6. **Dedup over-firing.** If the key is derived from something unstable, a collision
   discards real products. Check the dropped count before blaming the network.

Rather than guessing: make every run emit stats - items, requests by status, retries,
exceptions, pages paginated, mean response size - and diff a bad run against a good one.
That identifies the cause immediately where an item count never can. Then enforce a floor,
so a run returning under 80% of expected is a failed run and cannot overwrite the last
good dataset.

## Scenario 4 - full product HTML from a normal request. Add Playwright?

**No.** If the data is in the response, a browser buys nothing and costs a lot.

The costs, in the order they bite:

- **Time.** A browser fetches the document, then the scripts, then runs them, then waits
  for the page to settle. That is seconds where a plain request is fractions of one. I
  have not benchmarked it here so I will not put a multiplier on it, but the gap is large
  enough to change how you size a crawl.
- **Memory.** One HTTP worker is a socket and a buffer. One browser worker is a browser,
  so parallelism gets expensive fast.
- **Requests per page.** One request becomes dozens once every script, font, image and
  tracker is fetched. That is load on someone else's server, so it is a politeness
  question too.
- **Failure modes.** Plain HTTP fails with HTTP errors. A browser adds timeouts, races
  against unrendered elements, renderer crashes, and breakage when the browser version
  moves under you.

Part 3 is the concrete case: the product page gave up everything from one `curl`, and the
same data was available as an 8 KB JSON endpoint. A browser would have fetched the whole
asset tree to reach output I already had.

Use the lightest transport that returns the data - JSON endpoint, then plain HTTP, then a
browser. I would reconsider only if the data genuinely is not in any static response, and
even then I would look for the XHR call the page itself makes, since calling that directly
is usually cheaper and more stable than driving a browser. If a browser is truly needed, I
would scope it to the pages that need it rather than routing the whole crawl through it.

## Scenario 5 - works on five test products. What else before calling it reliable?

Five products prove the code runs. They prove very little about coverage, because they are
almost certainly five ordinary products, and crawlers break on the unusual ones.

1. **Scale and breadth.** Run a few hundred products across every category and measure
   **field-level coverage**: what percentage has a title, a price, an image, variants? A
   field at 92% is a bug affecting 8% of the catalogue that five samples would never show.
   My pipeline does exactly this and surfaced one book in 1,000 with an empty description.
2. **Awkward products on purpose.** Out of stock, on sale (two prices - did I take the
   right one?), many variants, one variant, no image, video present, empty description,
   non-ASCII title, bundles, gift cards.
3. **Types and sanity, not just presence.** Is `price` a number, positive, plausible? Are
   URLs absolute and on the expected domain? A price of `0.0`, or `11000` because cents
   were read as pounds, passes a "field exists" check and is still wrong.
4. **Cross-source agreement.** Where two sources exist - JSON-LD against the product JSON,
   listing price against detail price - compare them on a sample. Disagreement means a
   selector points at the wrong thing, and it is the cheapest correctness check available.
5. **Duplicates and completeness.** Are UPCs unique? Does the count match an independent
   expectation, like the sitemap's 291 URLs or the site's own result count? Extraction can
   be perfect while discovery quietly misses half the catalogue.
6. **Run it twice and diff.** Fields that change between runs without the site changing -
   ordering, session-tagged URLs, timestamps in image URLs - mean unstable extraction, and
   they will wreck any change detection built on top.
7. **Regression tests on saved HTML.** Keep a dozen representative pages as fixtures and
   assert the expected output. This is what keeps the crawler reliable: when the site
   changes, the fixtures say which field broke, without touching the network.
8. **Monitoring.** Reliability is not a one-time verdict. Track coverage and counts per run
   and alert on drift. The site will change without telling you, and the crawler will not
   announce that it started returning empty strings.
