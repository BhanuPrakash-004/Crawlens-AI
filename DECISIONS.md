# Decisions

## 1. Assumptions

- **The user is a marketing manager,** so each finding names the page, the problem and the fix in plain words.
- **Public websites only, and robots.txt is respected.** Private and local addresses are blocked, so the server cannot be used to reach an internal network (SSRF).
- **Many product pages are built with JavaScript,** so I crawl with a real browser (Firecrawl).
- **A 20-page sample is enough for a weekly plan.** Problems repeat across page templates, and each page costs credits.
- **Free plans only** (Firecrawl credits, Groq, and a free PageSpeed Insights API key). This is why the request limits exist.

## 2. What was unclear in the brief, and what I decided

| Question | My decision |
| --- | --- |
| "Top 5 SEO metrics", but AI-search signals are welcome. Is AI one of the five? | **5 SEO metrics plus AI search readiness as a separate 6th**, at 5% weight. Being quoted by ChatGPT is a different goal from ranking on Google, and its rules are still unclear. |
| How much of the site to crawl? | Same domain, starting from the sitemap, at most 20 pages. Cart, account and sign-in pages are skipped, because on amazon.in they filled the sample. |
| How are title characters counted? | As people see them, with extra spaces and line breaks collapsed. I also fail a title or description **repeated on another page**, which the brief does not ask for. The pure length result is shown separately. |
| When is a link "broken"? | Only when it returns 4xx/5xx **twice**. After a 429 or 503 the checker waits for `Retry-After` and retries. Bot-protection pages are *unverified*, because amazon.in returns 404 to bots for pages that exist. |
| There is no score formula. | A weighted pass rate over the checks that could be measured. Unmeasured checks are left out, not counted as zero, and coverage % is shown beside the score. |
| "An endpoint that returns the audit", but it takes up to 3 minutes. | `POST` returns an ID at once; `GET` returns the report when ready. |
| How do I keep the LLM away from the numbers? | It only receives measured issues and must answer in JSON that cites issue IDs. Python rejects unknown IDs, changed priorities and any number or URL in its text, then falls back to rule-based actions. |

## 3. Main technical choices

**Firecrawl now, Playwright later.** Firecrawl runs pages in a real browser and is blocked less often than a plain script, so I could focus on the SEO rules. But it does not beat bot detection completely (Amazon still blocked pages), it charges per page, and I cannot control its crawl order or speed. My own **Playwright** crawler would let me crawl sitemap product pages first, with my own rate limits and no per-page cost.

**SEO features I considered:**

| Feature | Scored? | Why |
| --- | --- | --- |
| Indexability and crawl access, robots.txt, XML sitemap, canonical | Yes, 33% | If Google cannot crawl and index a page, nothing else matters. |
| Core Web Vitals (loading speed) | Yes, 13% | Google uses them, and slow pages lose shoppers. |
| Headings, structured data, image alt text | Yes, 25% | How a page is understood and how it looks in results. |
| AI search readiness (GEO) | Yes, 5% | AI crawler access and readable content. A new area. |
| HTTPS, mixed content | Reported | Nearly every site passes, and HTTPS is a very small ranking signal. |
| Social profile links, sharing cards, `llms.txt` | Reported | Useful brand signals, but no direct effect on ranking. |

## 4. Three choices I would most want to revisit

1. **Leaving unmeasured checks out of the score.** It is fair to the site, but it gave **100/100 at only 87% coverage** on my Apple test, and a marketer may read only the big number. I would hide the score below a minimum coverage.
2. **Firecrawl as the crawler.** A Playwright crawler would give me control over page selection, rate limits and cost.
3. **Weights from judgment, not data.** I gave crawlability 33%, but I cannot prove that order. With Search Console data, I would weight issues by the traffic of the affected pages.
