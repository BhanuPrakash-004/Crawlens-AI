# SEO checklist: the exact rules

This page lists the rule behind each of the ten detailed checks. The checks are grouped into the six metrics described in the [README](../README.md#3-what-the-audit-checks), and the API returns that grouping as `metric_groups`. The dashboard's scoring guide shows the real numbers used for each saved report. Saved reports keep the score and rule version they were created with.

Every observation gets one of five results:
- **Passed** or **Failed**: these count toward the score.
- **Warning**: advice only.
- **Unverified (Review)**: the tool could not check it.
- **N/A**: the check does not apply.

## The ten checks

| Check | Weight | Rule |
| --- | ---: | --- |
| **Title and meta description** | 12% | One result per page. Pass: exactly one non-empty title of 30–60 characters and one description of 70–160 characters. Length is counted as displayed, with extra spaces and line breaks collapsed. Fail: missing, too short or long, more than one tag, or the same text on another analyzed page. |
| **Broken internal links** | 12% | One result per unique link, however many pages use it. The checker tries `HEAD`, then `GET`, and follows redirects. After a 429/503 it waits for `Retry-After` (up to 5 s) and retries once. A 500/502/504 is also retried once. Fail: 4xx/5xx after the retry. Unverified: login required (401), forbidden (403), still rate limited, a bot-protection page, a redirect loop, or a network error. Each result keeps every page that links to it, the link text and the redirect chain. |
| **Indexability and crawl access** | 16% | Pass: HTTP 200, no `noindex` in the HTML or `X-Robots-Tag` header, and robots.txt allows Googlebot and Bingbot. Fail: an error status, or a `noindex` or block on a URL listed in `REQUIRED_INDEX_URLS`. Unverified: other `noindex` or blocks, because they may be intended. N/A: cart, checkout, account, sign-in, wishlist and search pages. |
| **Core Web Vitals** | 13% | One result per vital for the sampled page. Pass: LCP ≤ 2,500 ms, INP ≤ 200 ms, CLS ≤ 0.1. Real-user data (CrUX) is used when Google has it for that URL, otherwise the mobile lab test (Lighthouse) for LCP and CLS. INP needs real-user data. Without `PAGESPEED_API_KEY`, Google often returns HTTP 429. The vitals are then unverified and the report warns that the score leaves out the speed weight. |
| **Headings** | 8% | Pass: the page has a non-empty H1. Warnings (not scored): more than one H1, repeated or generic heading text, empty headings, skipped levels (for example H2 then H4). |
| **robots.txt and sitemap** | 7% | Two site-level results. robots.txt fails if it returns HTML instead of rules. A missing robots.txt is only a warning. The sitemap fails on invalid XML or a declared sitemap that returns 404. Nested sitemaps and gzip files are followed, up to 40 files. Reaching that limit, blocked requests and loops are unverified. |
| **Canonical** | 10% | Pass: the declared canonical URL returns 200 and is indexable. Fail: it is broken, blocked, `noindex`, invalid, or there are two different canonicals. A missing canonical, a redirecting target and an external target are unverified. Pages that share a canonical or have nearly identical text are shown for review. |
| **Structured data** | 10% | JSON-LD must be valid JSON. A Product needs a name and an offer, review or rating. An offer needs a price of 0 or more and a three-letter currency. Breadcrumbs need named items with positions, and an Organization needs a name. Products nested inside the main product (such as "compatible with" lists) do not need their own offer. Pages without supported markup are N/A. |
| **Images and video** | 7% | One result per image or video. Fail: an image without an `alt` attribute, or a media file on the same site that returns an error. N/A: decorative images (`alt=""`, `role="presentation"`) and 1×1 tracking pixels. Unverified: generic alt text ("image", "photo"), an image without alt inside a link that already has text (needs `alt=""` or a short description), and videos without a label or caption track. Files on other domains (CDNs) are shown as unverified but do not raise an issue. |
| **AI search readiness (GEO)** | 5% | Pass: robots.txt allows OAI-SearchBot, PerplexityBot and Googlebot, and the page has readable text and an H1. Fail: one of these crawlers is blocked, or there is no readable text or heading. Also recorded, without scoring: schema types, tables, question-style headings and the description. |

## How the score is calculated

For each check, divide the passed results by the passed plus failed results. Multiply each rate by the check's weight, add them up, divide by the total weight of the checks that had at least one result, and multiply by 100. Round to the nearest whole number, with halves rounded up. If nothing could be measured, the score is "unknown", not zero.

*Example:* titles pass on 3 of 4 pages and links pass on 9 of 10, and nothing else is measured. The score is `100 × (3/4 × 12 + 9/10 × 12) ÷ 24 = 82.5`, shown as **83/100** with **24% coverage**.

A warning can appear next to a passed result, for example a second H1 on a page that has a good first H1. Unverified results give neither points nor a penalty.

## Settings

`.env.example` lists every setting: weights, title and description lengths, Core Web Vitals limits, score bands, crawler names, required URLs, skipped path segments, the duplicate-text threshold, request limits, and extra CDN or sitemap hosts to trust. Restart the backend after changing it.

## Other checks (reported, not scored)

- **HTTPS:** a valid certificate and a redirect from `http://` to `https://`.
- **Mixed content:** `http://` files loaded on an `https://` page.
- **Social profile links:** found in page links and in `sameAs` inside structured data.
- **Social sharing tags:** Open Graph and Twitter Card.
- **`llms.txt`:** whether the file exists and is readable.

The action list always refers to measured issue IDs, and Python sets the priorities. The LLM writes the summary, the concrete fix for each finding, and optional new titles and descriptions. An action is kept only if it cites real issues, keeps their priority, and quotes only numbers and URLs found in the evidence. A percentage must appear as a percentage. Findings the LLM does not cover get rule-based actions.
