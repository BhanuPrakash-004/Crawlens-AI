# Crawlens AI: SEO audit for product websites

Crawlens is a small web app for a marketing team. You enter a website URL, and it crawls up to 20 pages of the site, checks how well the site is set up for search, gives it an overall SEO score, and uses an LLM to write a short list of fixes the team can do this week.

All numbers in the report (lengths, status codes, scores) are measured by the crawler and calculated in Python. The LLM writes the audit summary and says what to change on which page. It can also draft a new title and description. The backend checks every action before showing it: the LLM may quote a measured value, but never invent one.

| Document | What it covers |
| --- | --- |
| [RESULTS.md](RESULTS.md) | The website I audited, why I chose it, and the report |
| [DECISIONS.md](DECISIONS.md) | My assumptions, the unclear parts of the brief, and what I would revisit |
| [AI_USAGE.md](AI_USAGE.md) | Which AI tools I used, where they were wrong, and how I caught it |
| [docs/SEO_CHECKLIST.md](docs/SEO_CHECKLIST.md) | The exact rule behind every check |

---

## 1. Setup

You need **Python 3.11 or newer** (I used 3.13.2) and **Node.js 22.12 or newer**. Run every command from the project folder.

**Windows (PowerShell)**

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock.txt
npm ci --legacy-peer-deps
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

**macOS / Linux**

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock.txt
npm ci --legacy-peer-deps
test -f .env || cp .env.example .env
```

Then put your keys in `.env`. Keys stay on the backend and are never sent to the browser.

| Setting | Required? | What it is for |
| --- | --- | --- |
| `FIRECRAWL_API_KEY` | **Yes**, for a live audit | Firecrawl loads the pages in a real browser, so pages built with JavaScript are seen correctly. |
| `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL` | Optional | Any OpenAI-compatible chat API. I use the free **Groq** tier: `https://api.groq.com/openai/v1` with the model `openai/gpt-oss-20b`. AWS Bedrock works with `https://bedrock-runtime.<region>.amazonaws.com/openai/v1` (the `/openai/v1` part is required), and so does a local Ollama server (`http://localhost:11434/v1`). Slow reasoning models can need 45+ seconds per answer, so raise `AI_TIMEOUT_SECONDS` (and `AUDIT_TIMEOUT_SECONDS`) for them. Without a key, the action list is built from rules. |
| `PAGESPEED_API_KEY` | **Strongly recommended** | Google PageSpeed Insights measures page speed (Core Web Vitals). Without a key, Google allows very few requests. Repeated testing soon gets HTTP 429 ("too many requests"), speed is then *not measured*, and the score changes (see below). |

**How to get a free PageSpeed Insights API key:**
1. Open the [Google Cloud Console](https://console.cloud.google.com/) and create or choose a project.
2. Go to **APIs & Services → Library**, search for **PageSpeed Insights API**, and click **Enable**.
3. Go to **APIs & Services → Credentials → Create credentials → API key**.
4. Recommended: edit the key, choose **Restrict key**, and allow only the **PageSpeed Insights API**.
5. Paste it into `.env` as `PAGESPEED_API_KEY=your-key` and restart the backend.
6. Check that it works: open <http://127.0.0.1:8000/api/health>. It should show `"pagespeed_configured": true`.

You can also test the key directly with Google. Replace `YOUR_KEY` with your key. The command prints a status code: `200` means the key works, `400` means the key is wrong, and `403` means the PageSpeed Insights API is not enabled for that project. On Windows, type `curl.exe` instead of `curl`.

```sh
curl -s -o psi.json -w "%{http_code}\n" "https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=https://example.com&strategy=mobile&category=performance&key=YOUR_KEY"
```

**Why the key matters for the score:** when speed cannot be measured, the score is calculated from the other checks only, without the 13% speed weight. So the same website can get a different score just because Google's quota ran out. I found this while testing (see AI_USAGE.md, case 2). The report now shows a warning when it happens.

Every limit and threshold (title lengths, speed limits, page cap, score weights) is also in `.env.example`, so it can be changed without touching code.

## 2. Run the app

```sh
npm run dev
```

- Web app: <http://127.0.0.1:5173>. Enter a URL and click **Analyze website**.
- API documentation (Swagger): <http://127.0.0.1:8000/docs>

For a production build, run `npm run build` and then `npm start`. The app and API are then both served on port 8000.

To turn a saved audit into the tables used in RESULTS.md without copying numbers by hand, run `.venv/Scripts/python.exe scripts/results_tables.py <audit.json>`.

### API

A full audit takes 30 seconds to 3 minutes, which is too long to keep one HTTP request open. So the API starts the audit, immediately returns an ID, and the client asks for the result with that ID.

| Request | What it does | Success response |
| --- | --- | --- |
| `POST /api/audits` with body `{"url": "https://example.com"}` | Starts an audit | `202` with `{"audit_id": "audit_…", "status": "queued"}` |
| `GET /api/audits/{audit_id}` | Returns the progress, and the full report when it is done | `200` |
| `GET /api/audits?q=&limit=&offset=` | Searches saved audits | `200` |
| `GET /api/health` | Shows whether the crawler and LLM are configured (never the keys) | `200` |

```sh
curl -X POST http://127.0.0.1:8000/api/audits -H "Content-Type: application/json" -d '{"url":"https://example.com"}'
curl http://127.0.0.1:8000/api/audits/<audit_id>
```

The finished report is JSON. The main fields are:
- `overall_score` and `classification`.
- `metric_groups`: the six metrics below.
- `metrics`: the ten detailed checks, with every observation.
- `pages`: the title and description of each page, with their lengths.
- `links`: every broken link, with the pages that link to it.
- `issues` and `recommendations`.
- `coverage`: what could and could not be measured.

**Error responses.** Invalid requests get a clear message:

| Status | When | Example message |
| --- | --- | --- |
| `422` | The URL is missing, empty or not a URL | `Enter a valid website URL, such as https://example.com.` |
| `400` | Private or local address, non-HTTP scheme, password in the URL, unusual port | `Private, loopback, link-local and reserved addresses are not allowed.` |
| `404` | Unknown audit ID | `Audit not found in this workspace.` |
| `409` | That website is already being audited | `This website already has an audit running. Wait for it to finish.` |
| `413` / `403` | Request body over 8 KB, or a request from another website's page | `Request body is too large.` |
| `429` | Two audits are already running (the response includes `Retry-After`) | `All audit slots are busy. Please try again shortly.` |

If the crawl itself fails, for example because the site blocks crawlers, `GET` still returns `200` with `status: "failed"` and a readable `error`.

---

## 3. What the audit checks

The brief requires the first two metrics. I chose three more SEO metrics by asking three questions: can customers **find** the page, does it **load** well on a phone, and does it **stand out** in search results? I added **AI search readiness** as a sixth signal, because more product research now starts in ChatGPT, Perplexity and Google AI Overviews. DECISIONS.md explains why it is a separate sixth metric.

Behind the six metrics are ten detailed checks. Each check belongs to exactly one metric.

| # | Metric · weight | Why it matters | How I measure it | Good / bad |
| --- | --- | --- | --- | --- |
| 1 | **Title and meta description** · 12% *(required)* | The title and description are what people read in Google before they decide to click. | For every page: is there a `<title>` and a `<meta name="description">`, what do they say, and how long are they? Length is counted as people see it, so line breaks and extra spaces in the HTML are not counted. | **Good:** one title of 30–60 characters and one description of 70–160. **Bad:** missing, too short or too long, two tags, or the same text on another page (stricter than the brief; see DECISIONS.md). |
| 2 | **Broken internal links** · 12% *(required)* | A broken link on the way to a product or support page loses the visitor. | Every link to the same website is checked once, even if many pages use it. The checker tries a light `HEAD` request first, then a normal `GET` if that fails, and follows redirects. If the site says "too many requests" (429) or has a temporary server error (5xx), it waits and tries again. Each broken link lists **every page it appears on**. | **Good:** no broken links. **Bad:** a link that returns 4xx/5xx even after the retry. Links blocked by the site's bot protection (401, 403, 429, or a "robot check" page) are marked **unverified**, not broken. |
| 3 | **Crawlability and indexability** · 33% *(indexability 16, robots.txt and sitemap 7, canonical 10)* | If Google cannot read or index a page, it cannot show it in results, however good the page is. | For each page: the HTTP status, any `noindex` instruction (in the HTML or the `X-Robots-Tag` header), and whether robots.txt allows Googlebot and Bingbot. For the site: whether **robots.txt** is valid and whether the **XML sitemap** is valid (including nested sitemaps, up to 40 files). The page's **canonical** link is also checked. | **Good:** status 200, indexable, allowed, valid sitemap, canonical points to a working page. **Bad:** page error, invalid sitemap, canonical pointing to a broken or blocked page. A deliberate `noindex` is marked for review, because it may be intended. Cart, checkout and account pages are skipped. |
| 4 | **Website loading speed (Core Web Vitals)** · 13% | Slow loading, laggy taps and a jumping layout make shoppers leave. These three numbers are Google's own page experience measures. | Google PageSpeed Insights, mobile, for one sample page per audit. It uses real-user data (CrUX) when Google has it, otherwise a lab test (Lighthouse). | **Good:** LCP ≤ 2.5 s (main content appears), INP ≤ 200 ms (page reacts to taps), CLS ≤ 0.1 (layout stays still). **Bad:** above the limit. |
| 5 | **Content structure and rich results** · 25% *(headings 8, structured data 10, images and video 7)* | Headings tell people and search engines what the page sells. **Structured data** (Schema.org JSON-LD) lets Google show price and availability in results. Image alt text helps image search and screen-reader users. | Headings H1–H3 in order. JSON-LD is read and Product, Offer, Review, Breadcrumb and Organization are validated. Every image and video is checked for alt text, labels and captions. | **Good:** one clear H1, valid markup, alt text on content images. **Bad:** no H1, broken JSON-LD, a Product without a name or without an offer, review or rating, an offer without a price, an image without an `alt` attribute. Decorative images (`alt=""`) and 1×1 tracking pixels are skipped. An image inside a link that already has text (an icon next to "Connect with Us") is a low-priority review, not a failure. |
| 6 | **AI search readiness (GEO)** · 5% *(AI signal)* | ChatGPT, Perplexity and Google AI Overviews can only quote a page their crawlers are allowed to read. GEO means *Generative Engine Optimization*: making a site easy for AI answer engines to use. | For each page: does robots.txt allow **OAI-SearchBot, PerplexityBot and Googlebot**, is there readable text, and is there a main heading? I also fetch `/llms.txt` and record the schema types, tables and question-style headings. | **Good:** the AI crawlers are allowed and the page has readable text and a heading. **Bad:** an AI crawler is blocked, or the page has no readable text or heading. `llms.txt` is reported but **earns no points**, because it is still a proposal that these engines do not document using. |

**Other checks I report but don't score.** These are shown in the **Site essentials** view and are useful to a marketer, but they are not strong SEO signals on their own:
- **HTTPS**: a valid certificate, and `http://` redirecting to `https://`.
- **Mixed content**: insecure `http://` files on a secure page.
- **Social profile links**: links to the brand's LinkedIn, Instagram, X and other accounts, found in page links and in `sameAs` inside structured data. They help Google and AI tools connect the website to the brand's official accounts.
- **Social sharing cards**: Open Graph and Twitter Card tags, which control how a shared link looks.
- **`llms.txt`**: whether the file exists and is readable.

### Overall SEO score

```
pass rate of a check = passed ÷ (passed + failed)             "unverified" and "not applicable" are left out
overall score        = 100 × Σ(pass rate × weight) ÷ Σ(weight of the checks that could be measured)
```

The score is rounded to the nearest whole number. **90+ is Excellent, 75+ Good, 50+ Needs improvement, and below 50 Critical.**

*Example:* titles pass on 3 of 4 pages, links pass on 9 of 10, and nothing else could be measured. Then the score is `100 × (0.75×12 + 0.9×12) ÷ 24 = 82.5`, which is shown as **83**, with **24% coverage**.

I leave out checks that could not be measured, instead of counting them as zero. If Google's speed API is busy, or a site blocks my bot, that is a limit of my tool, not a fault of the website. To stay honest, every report shows its coverage (`coverage.measured_weight`) and is marked `partial` when something was missing.

---

## 4. How it works

```
 Browser (React)                       Backend (Python, FastAPI)
 ───────────────                       ───────────────────────────────────────────────────────────────
 Enter URL ── POST /api/audits ──────► check the URL ─► block private/local addresses ─► 202 + audit_id
 Poll      ◄─ GET /api/audits/{id} ──  the audit runs in the background and is saved to SQLite every second
                                         │
                                         ▼
           ┌───────────── 1 CRAWL ───────────────┐   Firecrawl: same website only, respects robots.txt,
           │ crawl_website()  firecrawl_client   │   uses the sitemap, runs JavaScript, max 20 pages,
           └─────────────────┬───────────────────┘   skips cart/checkout/account/sign-in pages
                             ▼
           ┌───────────── 2 VERIFY PAGES ────────┐   Fetch each page directly to read its real status
           │ verify_pages()   verification       │   code and headers; detect bot-protection screens
           └─────────────────┬───────────────────┘
                             ▼
           ┌───────────── 3 EXTRACT ─────────────┐   BeautifulSoup reads the title, description,
           │ analyze_page()   html_extractor     │   headings, JSON-LD, canonical, images, links
           └─────────────────┬───────────────────┘
                             ▼
           ┌───────────── 4 MEASURE (in parallel, inside one time budget) ───────────────────┐
           │ links           robots.txt + sitemap   canonical   images   speed     llms.txt   │
           │ ≤300 + retry    ≤40 sitemap files      targets     ≤80      1 page    + HTTPS    │
           └─────────────────┬────────────────────────────────────────────────────────────────┘
                             ▼
           ┌───────────── 5 SCORE ───────────────┐   Plain Python rules, same input gives the same
           │ calculate_scores()  build_issues()  │   result: 10 checks → 6 metrics → score → issues
           └─────────────────┬───────────────────┘
                             ▼
           ┌───────────── 6 EXPLAIN ─────────────┐   The LLM writes a summary and says what to change on which
           │ recommend()      ai_service         │   page. Python checks each action: real issue IDs, the rule
           └─────────────────┬───────────────────┘   priority, only numbers/URLs found in the evidence. One retry
                             ▼                       names the problems; gaps get rule-based actions
                     SQLite (data/crawlens.sqlite3): audit history survives a restart
```

### Limits, rate limits and bot protection

I set these limits to stay inside free plans and to avoid overloading the website being audited. All of them can be changed in `.env`.

| Limit | Default | Why |
| --- | --- | --- |
| Pages crawled | **20** (maximum) | Firecrawl charges per page. 20 pages cover the home page and the main product and category templates. Cart, checkout, account, sign-in, wishlist and search pages are not crawled, so the budget goes to pages people find in search. |
| Links checked | 300 unique | Each link is checked once. A footer link on 20 pages is one request, but all 20 pages are kept as sources. |
| Requests to the site at the same time | 5 | The checker also waits the `Crawl-delay` the site asks for in robots.txt. |
| Retry after "too many requests" | 1 retry, waiting up to 5 s | For 429/503 the checker waits as long as the site's `Retry-After` header asks (up to 5 s). A temporary 500/502/504 also gets one retry. A link is only "broken" if it fails twice. |
| Sitemap files / images / speed tests | 40 / 80 / 1 | One PageSpeed test per audit saves quota. A test takes 10–30 seconds. |
| Audits at once / time per audit / LLM time | 2 / 180 s / 40 s | The LLM gives at most two answers (one retry with feedback), and the prompt holds at most 40 issues. On Groq's free tier the limit is tokens per minute, so the prompt is kept compact, and a 429 waits for `Retry-After` when it fits the budget. |

Other things the backend does on every request:
- **Caching:** a page fetched once (for example, a canonical target) is not fetched again.
- **robots.txt:** every request is checked against it for my bot, `CrawlensBot/1.0`.
- **SSRF protection:** every request is pinned to a public IP address, so a crafted link cannot reach the server's own network or `localhost`.
- **Bot protection:** many big sites answer bots with a "robot check" page, sometimes with a fake 404. These are recognised and marked **unverified** instead of broken.
- **Moved domains:** before crawling, the entered URL's redirects are followed. If `rsgmgmt.com` now redirects to `renovuscapital.com`, the new address is audited, and the report says so. Before this fix, every page was thrown away as "outside the website".
- **Landing-page fallback:** if Firecrawl returns no usable pages (blocked, out of credits, or an error), the landing page is fetched directly and audited on its own, instead of failing the whole audit. JavaScript is not run in that case, and the report says so.
- **Template problems are reported once:** when the same problem appears on several pages (for example, a theme that makes the logo an H1 on every page), it is shown as one issue that lists every affected page, with the advice to fix it once in the shared template. Before, renovuscapital.com showed the same two findings 10 times each.
- **Nothing passes silently:** anything not checked within the time budget is shown as **unverified**.

**If a link is marked broken but works in your browser,** request it the way the tool does and read the status and the body:
```sh
curl -s -o page.html -w "%{http_code}\n" -A "CrawlensBot/1.0" "<link>"
```
- A body that says "automated access", "captcha" or "robot check" means the site is blocking bots, not that the page is broken.
- A `Retry-After` header means you were rate limited.

### Code organisation

```
backend/app/
  main.py               API routes, request checks (size, origin), background jobs
  config.py             all limits, thresholds and weights (.env can change them), and the 6 metric groups
  schemas.py            data models: the shape of the API, including Report.metric_groups
  storage.py            SQLite audit history
  services/
    audit_service.py    runs the 6 steps in order and shares the time budget
    firecrawl_client.py step 1: crawl, skip utility pages, detect bot screens
    verification.py     steps 2 and 4: direct page checks, canonical, images, HTTPS, request cache
    url_safety.py       URL cleanup, SSRF protection, bot-screen detection
    html_extractor.py   step 3: title, description, indexability, structured data
    page_evidence.py    headings, images and video, duplicate titles across pages
    link_checker.py     broken links, with retry for rate limits
    site_checks.py      robots.txt, sitemap, llms.txt
    robots_policy.py    robots.txt rules (user agents, wildcards, longest match wins)
    performance.py      Core Web Vitals from PageSpeed
    score_calculator.py step 5: the score
    issue_builder.py    issues, priorities and plain-language impact
    ai_service.py       step 6: LLM action list, output checks, rule-based fallback
    social_links.py     social profile links (reported, not scored)
backend/tests/          170 pytest tests
frontend/src/           React 19 + TypeScript + Vite: App.tsx, components/, lib.ts (API calls, CSV/JSON export)
frontend/e2e/           Playwright browser tests (desktop and mobile)
```

**Why this stack:**
- **FastAPI** checks request data and gives free API docs.
- **Firecrawl** runs JavaScript and is blocked less often than a plain script (see DECISIONS.md).
- **BeautifulSoup** with `html5lib` reads HTML the way a browser does.
- **HTTPX** is async and lets me control redirects.
- **SQLite** needs no database server.
- The LLM can be any OpenAI-compatible provider, so a free one works.

---

## 5. Tests

The tests need no API keys. The crawler, the LLM and the network are replaced with test data.

```sh
npm test                        # backend (pytest) and frontend (Vitest)
npx playwright install chromium
npm run test:e2e                # browser tests on desktop and mobile
npm run build                   # TypeScript check and production build
```

| Suite | Tests | Examples |
| --- | --- | --- |
| Backend (pytest) | **170** | See the table below |
| Frontend (Vitest) | 8 | Open a saved audit, filter findings, open evidence, export, safe CSV export |
| Browser (Playwright) | 6 scenarios, each on desktop and mobile | Start an audit, follow progress, recover from an error, layout on small screens |

The brief asks for valid inputs, invalid inputs and edge cases. Here is where they are tested (all in `backend/tests/`):

| Type | Tests |
| --- | --- |
| **Valid input** | `test_valid_audit_async_contract`: a valid URL gives 202 and then a full report. `test_all_page_rules_pass`: a well-built page passes every rule. |
| **Invalid input** | `test_invalid_request_is_422` (empty, missing, `not a url`, `https://`). `test_private_url_is_400`. `test_unsafe_urls_rejected` (13 cases, such as `localhost`, `10.0.0.1`, `169.254.169.254`, `ftp://`, a password in the URL, port 8080). `test_unknown_audit_is_404`. `test_oversize_request_and_foreign_origin_rejected`. |
| **Exact limits** | `test_metadata_inclusive_boundaries`: titles of 29, 30, 60 and 61 characters, and descriptions of 69, 70, 160 and 161. |
| **Edge cases** | `test_rate_limited_or_temporary_errors_are_retried_before_judging`. `test_pagespeed_key_is_sent_and_quota_errors_explain_the_score_impact`. `test_bot_protection_404_is_not_a_broken_link`. `test_head_falls_back_to_get`. `test_broken_links_preserve_every_source`. `test_x_robots_tag_directives_containing_colons`. `test_all_unknown_is_null_not_zero`. `test_dns_rebinding_prevented_by_pinning`. `test_compatibility_products_do_not_need_their_own_offer`. |
| **The LLM cannot change facts** | `test_ai_cannot_invent_evidence_or_priorities`. `test_llm_may_quote_measured_values_but_not_invent_them`. `test_retry_names_the_problem_and_uses_the_fixed_answer`. `test_ai_rejects_an_unmeasured_score_or_url_in_narrative`. `test_fallback_without_ai_key`. |
| **Score maths** | `test_weighted_score_uses_unrounded_rates`. `test_reported_metric_groups_cover_every_check_once_and_match_the_overall_score`. |

---

## 6. What works and what doesn't

**Works:**
- The full flow: enter a URL, crawl, measure, score, AI action list, history and export.
- The API with clear errors.
- Fair handling of rate limits and bot protection.
- Tests that need no keys.

**Limits:**
- **It audits a sample, not the whole site.** It checks at most 20 pages and 300 links. The report always says how much it covered.
- **Speed needs a PageSpeed API key.** Without `PAGESPEED_API_KEY`, Core Web Vitals are often not measured (HTTP 429), and the score is then calculated without them.
- **Sites with heavy bot protection, such as Amazon,** give many *unverified* results. Firecrawl gets blocked less often than a plain script, but it is not fully unblockable.
- **The dashboard still lists the ten detailed checks.** The six-metric grouping is currently only in the API.
- **Pages behind a login are not audited.** The crawler only sees what a visitor without an account sees, so dashboards, customer portals and member pages are out of reach. It also never types in passwords. Adding this is planned (see AI_USAGE.md, "With one more day").
- **It is a single-user tool.** Audits run in one process. Several users would need a job queue and logins.
- **AI search readiness measures whether a page *can* be quoted by AI tools,** not whether it actually *is* quoted.
