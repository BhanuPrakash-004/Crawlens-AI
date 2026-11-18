# AI usage

## Tools I used

- **OpenAI Codex** wrote most of the code (FastAPI backend, React frontend, test setup) from the brief, my metrics and my limits. I reviewed and corrected it.
- **Claude Code** reviewed every backend file, found bugs, added a test for each fix, added the six-metric grouping to the API, and helped rewrite these documents.
- **Groq `openai/gpt-oss-20b`** runs inside the app and only words the weekly action list. It never calculates a score.

## Where AI was wrong, and how I caught it

**1. Links shown as broken that worked in my browser (rate limits and bot protection).**
- **What I saw:** testing on amazon.in, the app reported "Broken internal destination: HTTP 404" for links like `/discover/`. In my browser they loaded normally.
- **How I checked:** I requested the link the way my tool does, with `curl -A "CrawlensBot/1.0" <link>`. It returned 404, but the page said *"To discuss automated access to Amazon data please contact…"*. Amazon was blocking my bot; the page was not missing. The AI-written link checker also never retried a 429 "Too Many Requests", and it called a temporary 500/502/504 broken after one try.
- **Fix:** bot-protection pages are now *unverified*. After a 429 or 503, the checker waits as long as `Retry-After` asks (up to 5 s) and retries. A 500/502/504 also gets one retry, so "broken" means it failed twice. The same audit had spent most of its 20 pages on account and sign-in pages, so those paths are no longer crawled.
- **Tests:** `test_bot_protection_404_is_not_a_broken_link`, `test_rate_limited_or_temporary_errors_are_retried_before_judging`.

**2. The score changed between runs because of Google's PageSpeed quota (found by me, not by the AI).**
- **What I saw:** while testing, I ran audits on the same pages many times. When I ran my final audit, its score was lower than in my earlier runs, although the website had not changed.
- **How I checked:** the page evidence said *"PageSpeed returned HTTP 429"*. The AI-written code called Google's PageSpeed Insights API **without an API key**. Keyless requests get a very small quota, and my own testing had used it up. So Core Web Vitals were not measured, and the score was calculated without the 13% speed weight. The AI never mentioned that the key was effectively required, or that a missing measurement would make scores impossible to compare.
- **Fix:** I enabled the PageSpeed Insights API in Google Cloud and added the key to `.env` as `PAGESPEED_API_KEY`. The report now warns when speed was skipped because of the quota and says the score is not comparable. The error message explains what to do, and `/api/health` shows whether a key is set.
- **Lesson:** always read a score together with its coverage.
- **Test:** `test_pagespeed_key_is_sent_and_quota_errors_explain_the_score_impact`.

**3. A wrong Firecrawl SDK argument.** It passed `request_timeout` to `start_crawl`. The installed SDK's method signatures showed that only `get_crawl_status` accepts it. `test_firecrawl_sdk_real_signature_and_payload` now runs the real SDK.

**4. A structured-data rule that failed a correct Apple page.** It treated every `Product` in the JSON-LD as the item for sale, so 83 "compatible device" entries without prices failed the page. The page source showed that only the top-level product is for sale.

**5. LLM advice the evidence did not support.** On the Apple page (19 images, no video), the model's media action described problems that were not measured. My output check replaced it with rule-based wording. It also rejects unknown issue IDs, changed priorities, and numbers or URLs in the LLM's text.

## What I decided without AI, and why

**The metrics, weights and request limits.** These are product and cost decisions, and an AI does not know my free-plan quotas or what a marketer will act on.
- **Metrics:** which problems stop a customer *finding* a page (crawlability, 33%), *staying* on it (speed, 13%) and *choosing* it in results (titles, content). AI readiness got 5% because its signals are still new.
- **Limits:**
  - 20 pages (Firecrawl charges per page).
  - 300 unique links.
  - 5 parallel requests plus the site's `Crawl-delay`.
  - 1 PageSpeed test per audit.
  - 2 audits at once.
  - 1 LLM call plus 1 retry.

## With one more day

1. **Real AI visibility:** ask Perplexity's and OpenAI's search APIs fixed buyer questions and count how often the site is **quoted**, not just whether it *can* be.
2. **A Playwright crawler that starts from the sitemap,** so the sample is product and category pages, with my own rate limits.
3. **Week-over-week comparison:** what is new, fixed or worse since the last audit. This only works if every run measures the same checks, which is another reason the PageSpeed key matters.
4. **Internal link map:** clicks from the home page, pages nothing links to, and weak link text like "click here".
5. **Title preview by pixel width** (Google cuts titles by width), and **hreflang** checks for multi-country sites.
