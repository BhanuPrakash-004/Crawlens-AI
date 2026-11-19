# AI usage

## How I worked

1. **I analysed the brief myself.** Who uses the tool (a marketing manager), what a useful SEO audit must show them, and which parts of the brief were unclear (see DECISIONS.md).
2. **I chose the SEO features myself.**
   - The two required metrics.
   - Crawlability and indexability: robots.txt, XML sitemap, canonical, `noindex`.
   - Core Web Vitals.
   - Content: headings, structured data, image alt text.
   - AI search readiness.
   - HTTPS, social profile links and `llms.txt`, reported but not scored.

   I also set the weights and the request limits.
3. **Claude structured my plan into a PRD.** I gave Claude my idea, workflow, features, rules and limits. It turned them into a detailed project description: API contract, data model, the rule for each check, the score formula and test cases. Claude organised my decisions; it did not choose them.
4. **Antigravity with Gemini 3.8 Flash implemented the PRD** (FastAPI backend, React frontend) **and wrote the tests.**
5. **I tested the app on real sites** (an Apple product page, a college site, amazon.in) and checked the results by hand. The problems I found are below.

Inside the app, **Groq `openai/gpt-oss-20b`** writes the audit summary and the fix for each finding. It never produces a score or a measurement.

## Where AI was wrong, and how I caught it

**1. Links shown as broken that worked in my browser (rate limits and bot protection).**
- **What I saw:** on amazon.in, the app reported "Broken internal destination: HTTP 404" for links like `/discover/`. In my browser they loaded.
- **How I checked:** I requested the link the way my tool does, with `curl -A "CrawlensBot/1.0" <link>`. It returned 404, but the page said *"To discuss automated access to Amazon data…"*, so Amazon was blocking my bot. The generated checker also never retried a 429, and it called a temporary 500/502/504 broken after one try.
- **Fix:** bot-protection pages are now *unverified*. After a 429 or 503, the checker waits for `Retry-After` (up to 5 s) and retries. A 500/502/504 also gets one retry, so "broken" means it failed twice. Account and sign-in pages, which filled that sample, are no longer crawled.

**2. The score changed between runs because of Google's PageSpeed quota (found by me, not by the AI).**
- **What I saw:** after testing the same pages many times, my final audit scored lower than the earlier runs, although the site had not changed.
- **How I checked:** the evidence said *"PageSpeed returned HTTP 429"*. The generated code called PageSpeed Insights **without an API key**, and my own testing had used up the small keyless quota. So speed was not measured, and the score was calculated without its 13% weight.
- **Fix:** I enabled the PageSpeed Insights API in Google Cloud and added `PAGESPEED_API_KEY`. The report now warns when a score was calculated without speed. **Lesson:** read a score together with its coverage.

**3. The check on the LLM's answer was too strict, so users almost never saw the LLM's plan.**
- **How I checked:** I logged Groq's raw answer. It was a good plan, but it was thrown away: once for "667 sitemap entries" (the check banned *every* digit, even measured ones), and once for a summary slightly over 500 characters. Groq's free tokens-per-minute limit (429) also caused fallbacks.
- **Fix:** the LLM may quote numbers and URLs only if they appear in the evidence, so an invented "+40% traffic" is still rejected. Each action is checked on its own, and the retry says exactly what was wrong. The prompt is 45% smaller, and a 429 waits for `Retry-After`. The live plan is now AI-written, with concrete fixes and drafted titles.

**4. A structured-data rule failed a correct Apple page.** It treated every `Product` in the JSON-LD as the item for sale, so 83 "compatible device" entries without prices failed the page. The page source showed that only the top-level product is for sale.

**5. A real site failed completely: "No usable HTML pages were returned" (found by me).** I audited `rsgmgmt.com`, and the error suggested a login or blocking. I checked the response myself: `rsgmgmt.com` **permanently redirects (301) to another domain, `renovuscapital.com`**. The generated crawler followed the redirect and then threw away every page as "outside the website". Now the entered URL's redirects are resolved first, so the new domain is audited, and the report says so. If Firecrawl ever returns nothing, the landing page is audited on its own. The same site then gave a full report: 10 pages, 133 links, one broken link and an AI-written plan.

Every fix has a regression test in `backend/tests/`.

## What I decided without AI, and why

**The SEO features, their weights, and the request limits.** These are product and cost decisions. An AI does not know my free-plan quotas or what a marketer will act on this week.
- **Weights:** I asked which problems stop a customer *finding* a page (crawlability, 33%), *staying* on it (speed, 13%) and *choosing* it in results (titles, content). AI readiness got 5% because its signals are still new.
- **Limits:** 20 pages (Firecrawl charges per page), 300 unique links, 5 parallel requests plus the site's `Crawl-delay`, 1 PageSpeed test, 2 audits at once, and at most 2 LLM answers.

## With one more day

1. **A Playwright crawler that starts from the sitemap,** so the sample is product and category pages, with my own rate limits.
2. **Audits of pages behind a login** (customer portals, member areas). Two steps:
   - **How it would log in:** the user enters a test account (user ID and password) or a session cookie for an audit. Firecrawl can then log in before crawling, either by sending the cookie in its `headers` option or by filling in the login form with its `actions` option (type the user ID, type the password, click "Sign in"). A Playwright crawler could do the same with a saved login session.
   - **Safety:** credentials would be used only for that audit, never saved in reports or logs, and only for websites the user owns. Public SEO scores would still be measured without logging in, because search engines cannot log in.
3. **Real AI visibility:** ask Perplexity's and OpenAI's search APIs fixed buyer questions and count how often the site is **quoted**, not just whether it *can* be.
4. **Markdown versions of pages for AI agents:** check whether each page offers a clean `.md` version that AI agents can read without the menus, scripts and ads. That means a `page.md` next to the page (the convention from the `llms.txt` proposal), a `<link rel="alternate" type="text/markdown">` tag, or a Markdown answer when asked with `Accept: text/markdown`. I would also check that `llms.txt` links to those files.
5. **Week-over-week comparison** of what is new, fixed or worse. This needs every run to measure the same checks, which is another reason for the PageSpeed key.
6. **Internal link map:** clicks from the home page, pages nothing links to, and weak link text.
7. **Title preview by pixel width** (Google cuts titles by width), and **hreflang** checks for multi-country sites.
