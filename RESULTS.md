# Results

**Main audit:** Apple India, `https://www.apple.com/in/` (sections 1–4)
**Extra audit:** `rsgmgmt.com`, because this assignment was given by RSG Management (section 5)

## 1. The website I chose, and why

**Website:** `https://www.apple.com/in/`, Apple India

**What the site is.** Apple India is Apple's official website and online store for India. On it, customers can:
- explore and buy iPhone, iPad, Mac, Apple Watch, AirPods, HomePod and Apple TV, and their accessories;
- compare models and read full technical specifications;
- configure a Mac and order it online, with prices in rupees and free delivery;
- buy AppleCare protection plans;
- book free *Today at Apple* sessions at Apple's stores in India. The audit sample includes pages for Apple Koregaon Park (Pune) and Apple Saket (New Delhi).

The home page describes the site in its own words: *"Discover the innovative world of Apple and shop everything iPhone, iPad, Apple Watch, Mac, and Apple TV, plus explore accessories, entertainment, and expert device support."*

**Why I chose it:**
- **It is a product website, so it has rich structured data.** The shop pages carry Product data in JSON-LD: the product name, its price in rupees, the SKU, free shipping, breadcrumbs and an FAQ. Google uses this data to show prices in search results, which makes it the best test of my structured-data metric. Examples from the pages' JSON-LD:
  - MacBook Pro 14" (M5 Max, 36GB, 2TB): ₹4,99,900, SKU `MGDQ4HN/A`
  - Mac Studio: ₹2,79,900 to ₹35,95,700
  - HomePod mini 2: ₹18,900
- **It has many links.** 10 pages contain **2,812 internal links** that point to **285 different URLs**. Its sitemaps are huge: the first 40 sitemap files alone list **3,174 URLs**, and 719 more sitemap files were left unopened. This tests link checking at scale.
- **It is a hard, realistic test:**
  - the pages are built with JavaScript, so they must be rendered;
  - robots.txt blocks some shop paths (`Disallow: /*shop/browse/overlay/*`);
  - Apple rate-limits bots (HTTP 429);
  - some sitemaps point to other Apple hosts, such as `apple.com.cn`.
- **A marketing team cares about every page.** Every product launch in India sends shoppers from Google to these pages. The titles, descriptions and product data are what they see in the search results.
- **It is a fair, legal crawl.** The audited pages are allowed by robots.txt. The 4 pages that robots.txt blocks were skipped, not fetched.

## 2. The app's report

**Final audit:** `audit_ed177f49e1714f64bc3810af670793b0`, started 2026-11-19 06:16 UTC, page limit 10. All tables below are printed by `scripts/results_tables.py docs/results-audit.json` or read from that file; no number was typed by hand.

[Full report JSON](docs/results-audit.json)

### Audit summary

| Item | Value |
| --- | --- |
| Website | https://www.apple.com/in/ |
| Completed | 2026-11-19 06:18:15 UTC |
| Duration | 194.3 s |
| Rule version | 3.1 |
| Pages analyzed / failed / limit | 10 / 4 / 10 |
| Internal link destinations: found / verified / unverified | 285 / 280 / 5 |
| Overall SEO score | **90/100 · Excellent** |
| Score status · coverage | partial · 87% of weight measured |
| Action plan source | ai (AI-written plan based on the measured issues.) |

### The six metrics

| # | Metric | Weight | Score | Underlying checks (passed / evaluated) |
| --- | --- | ---: | ---: | --- |
| 1 | Title and meta description | 12% | 40 | metadata 4/10 |
| 2 | Broken internal links | 12% | 100 | broken_links 280/280 |
| 3 | Crawlability and indexability | 33% | 100 | indexability 9/9, site_health 1/1, canonical 9/9 |
| 4 | Mobile page performance | 13% | unmeasured | performance 0/0 |
| 5 | Content structure and rich results | 25% | 96 | headings 10/10, structured_data 8/9, media 77/77 |
| 6 | AI search readiness | 5% | 100 | geo 10/10 |

### Metric 1 · Title and meta description, per page

| Page | Title (chars) | Description (chars) | Pass |
| --- | ---: | ---: | :---: |
| https://www.apple.com/in/ | 13 | 172 | Fail |
| https://www.apple.com/in/applecare/?filter=watch | 22 | 86 | Fail |
| https://www.apple.com/in/today/calendar/koregaonpark/?sn=R788 | 54 | 120 | Pass |
| https://www.apple.com/in/today/camp/saket/ | 48 | 139 | Pass |
| https://www.apple.com/in/shop/sorry/message_generic | 18 | 5 | Fail |
| https://www.apple.com/in/iphone-16/specs/ | 49 | 48 | Fail |
| https://www.apple.com/in/shop/buy-mac/macbook-pro/14-inch-silver-standard-display-apple-m5-max-chip-18-core-cpu-32-core-gpu-36gb-memory-2tb-storage | 124 | 138 | Fail |
| https://www.apple.com/in/shop/buy-homepod/homepod-mini | 31 | 113 | Pass |
| https://www.apple.com/in/shop/buy-mac/mac-studio | 27 | 149 | Fail |
| https://www.apple.com/in/airpods/compare/ | 37 | 103 | Pass |

### Metric 2 · Broken internal links

No confirmed broken internal links among 280 verified destinations.

### Prioritised action list

1. **[high] Verify whether https://www.apple.com/in/shop/sorry/message_generic should stay noindexed or be restored for indexing.** Confirm indexing intent for https://www.apple.com/in/shop/sorry/message_generic with the page owner. If it is an intentional error or excluded page, keep the noindex and record the decision; if it should be indexed, remove the noindex directive, then verify the response status and robots directives again.
2. **[medium] Rewrite the homepage title (13 characters) and description (172 characters) on https://www.apple.com/in/.** Update the title and meta description in the head of the homepage template using the attached proposal, which is built only from the page's existing text. Then re-measure both tags against the 30–60 title and 70–160 description project limits.
3. **[medium] Shorten the 124-character title on the MacBook Pro (M5 Max, 36GB, 2TB) buy page.** In the head of https://www.apple.com/in/shop/buy-mac/macbook-pro/14-inch-silver-standard-display-apple-m5-max-chip-18-core-cpu-32-core-gpu-36gb-memory-2tb-storage replace the title tag with the attached proposal, which keeps the page's existing product wording within the 30–60 project limit. Keep the current description, which is already within the 70–160 limit, or reuse the attached text.
4. **[medium] Lengthen the 27-character title on https://www.apple.com/in/shop/buy-mac/mac-studio.** Replace the title tag in the head of https://www.apple.com/in/shop/buy-mac/mac-studio with the attached proposal, built from the page's existing wording ("Mac Studio", "M5 Max or M5 Ultra", "Apple (IN)"). Keep the current description, which already meets the 70–160 limit, then re-measure both tags.
5. **[medium] Verify ownership of external sitemap hosts and recheck the 719 uninspected sitemap files.** Confirm ownership of www.apple.com.cn with the team that manages that host (for example via the respective Search Console accounts) and verify that https://www.apple.com.cn/shop/sitemap-index.xml is intended to serve in-scope URLs. Then inspect the outstanding indexes so the 719 remaining files are covered, and recheck coverage before changing any published URLs.

### Coverage notes

- 5 internal destination(s) could not be verified and are excluded from the link score.
- The page limit was reached. This report describes the scanned pages, not necessarily the entire website.
- Core Web Vitals were not measured: Google PageSpeed returned HTTP 429 (quota exceeded). The score leaves out the 13% speed weight, so it can differ from a run where speed was measured. Add PAGESPEED_API_KEY in .env.
- Not analyzed: https://www.apple.com/in/shop/browse/overlay/mac/software (Crawling disallowed by robots.txt.)
- Not analyzed: https://www.apple.com/in/shop/browse/overlay/affordability/mac (Crawling disallowed by robots.txt.)
- Not analyzed: https://www.apple.com/in/shop/browse/overlay/homepod/siri_ai (Crawling disallowed by robots.txt.)
- Not analyzed: https://www.apple.com/in/shop/browse/overlay/store/step_1/personal_setup (Crawling disallowed by robots.txt.)

### Structured data, per page

| Page | JSON-LD blocks | Invalid blocks | Schema types found | Result |
| --- | ---: | ---: | --- | :---: |
| `/` | 2 | 0 | Organization, WebPage | Pass |
| `/applecare/?filter=watch` | 3 | 1 | BuyAction, Organization, Product | Fail (Product 1: requires offers, review, or aggregateRating) |
| `/today/calendar/koregaonpark/?sn=R788` | 1 | 0 | Organization | Pass |
| `/today/camp/saket/` | 1 | 0 | Organization | Pass |
| `/shop/sorry/message_generic` | 0 | 0 | — | N/A |
| `/iphone-16/specs/` | 1 | 0 | Organization | Pass |
| `/shop/buy-mac/macbook-pro/14-inch-silver-s…` | 3 | 0 | BreadcrumbList, FAQPage, Offer, Product | Pass |
| `/shop/buy-homepod/homepod-mini` | 2 | 0 | BreadcrumbList, Offer, Product | Pass |
| `/shop/buy-mac/mac-studio` | 3 | 0 | AggregateOffer, BreadcrumbList, FAQPage, Product | Pass |
| `/airpods/compare/` | 1 | 0 | Organization | Pass |

## 3. What the report means for a marketer

- **Biggest problem: titles and meta descriptions. Only 4 of 10 pages pass.**
  - **Home page:** the title *"Apple (India)"* has only 13 characters. The description has 172, so Google cuts off the end. The AI's proposal, built only from words already on the page: *"Apple (India) - iPhone, iPad, Apple Watch, Mac and Apple TV"* (59 characters), and a 148-character description.
  - **MacBook Pro configuration page:** the title has **124 characters**. Google shows only about the first 60, so the details that make this configuration different (36GB memory, 2TB storage) are cut off. AI proposal: *"Buy MacBook Pro 14" M5 Max Chip - Apple (IN)"* (44 characters).
  - **Mac Studio:** the title has 27 characters. AI proposal: *"Buy Mac Studio with M5 Max or M5 Ultra - Apple (IN)"* (51 characters).
  - **iPhone 16 specifications:** the description *"View all technical specifications for iPhone 16."* has 48 characters, which wastes the search snippet.
  - *Note:* 30–60 and 70–160 characters are this project's limits, not Google rules. For a brand as strong as Apple, the short home title may be a deliberate choice. The long product titles and the short descriptions are the ones worth fixing.
- **A real structured-data bug on the AppleCare page.**
  - Its FAQ block is **invalid JSON**: one answer's text begins with a raw line break, which JSON does not allow. Search engines and AI tools that read JSON-LD therefore cannot read that FAQ at all.
  - Its Product block (*"AppleCare"*) has no price, rating or reviews, so it cannot get a product rich result.
  - Fix: remove the line break (or write it as `\n`) in the template that builds the FAQ. Then either add an offer with the price or stop marking the page as a Product.
- **Already strong: the product data on the shop pages.** The MacBook Pro, Mac Studio and HomePod mini pages have complete Product data: name, price in rupees, SKU, free shipping and breadcrumbs, plus an FAQ on the Mac pages. This is what Google needs to show a price in search results.
- **No broken links.** All 280 verified link destinations work. The 5 unverified ones are not errors:
  - 4 are blocked by robots.txt, so they were not checked;
  - `/in/esim/` redirects to `support.apple.com`, which answered "429: rate limited".
- **Ignore the one "high" action.** The AI's first action, *"verify the noindex on `/shop/sorry/message_generic`"*, points to Apple's error page (title *"Sorry"*, heading *"Please enable JavaScript."*). Its noindex is correct, so nothing needs to be done.
- **Also good:**
  - HTTPS, with a redirect from `http://`;
  - a canonical tag on every page that should be indexed;
  - one H1 per page;
  - Googlebot and AI search crawlers (`OAI-SearchBot`, `PerplexityBot`) allowed;
  - Facebook, LinkedIn, X and YouTube profiles linked.
- **What the score does not cover:**
  - Speed: Google PageSpeed returned HTTP 429, so the score covers 87% of the weight.
  - Only 10 pages were analyzed, out of at least 3,174 URLs in the sitemaps.
  - Only 40 of 759 sitemap files were opened, so the sitemap result is *unknown* and not scored.

## 4. How I checked that the app was right

On 2026-11-19 I downloaded each page myself the way the app does: `curl --compressed -A "CrawlensBot/1.0" <page>`. I then counted the characters and parsed the JSON-LD with a short Python script (BeautifulSoup and `json.loads`).

| What I checked | The app said | I found by hand | Match? |
| --- | --- | --- | :---: |
| Home page title | 13 characters | `Apple (India)` = 13 | Yes |
| Home page description | 172 characters | 172. The tag is written `name="Description"` with a capital D, and the app still found it. | Yes |
| AppleCare title and description | 22 and 86 characters | 22 and 86 | Yes |
| AppleCare JSON-LD | 3 blocks, 1 malformed; the Product has no offers, review or rating | 3 blocks. `json.loads` fails on the FAQ block: *"Invalid control character at line 36"* (a raw line break inside an answer). The Product *"AppleCare"* has no `offers`, `review` or `aggregateRating`. | Yes |
| MacBook Pro title | 124 characters | 124 | Yes |
| MacBook Pro product data | Pass: a Product with offers | `Offer`: price 499900, currency INR, SKU `MGDQ4HN/A`, shipping 0 | Yes |
| Mac Studio title | 27 characters | 27; `AggregateOffer` from 279900 to 3595700 INR | Yes |
| iPhone 16 specs description | 48 characters | 48 | Yes |
| `/shop/sorry/message_generic` | noindex | `<meta name="robots" content="noindex, nofollow">` on an error page | Yes |
| 4 pages "not analyzed" | Disallowed by robots.txt | robots.txt, `User-agent: *`: `Disallow: /*shop/browse/overlay/*` | Yes |
| Unverified link `/in/esim/` | HTTP 429, still limited after a retry | `301` to `support.apple.com/en-in/119606`, which answered `429` again: a rate limit, not a broken link | Yes |
| HTTP → HTTPS | Passed | `http://www.apple.com/in/` → `301` → `https://www.apple.com/in/` | Yes |

Every value I checked matched.

**Where the app fell short on Apple:**
- **Wrong priority.** The AI marked the noindex on the error page as *high*. The rule flags every noindex page. It should recognise an error page (title "Sorry", no canonical) and skip it.
- **A wasted sample slot.** Apple's error page was 1 of the 10 sampled pages. It also counts as a failed title and description.
- **Sitemap too large to inspect.** With 759 sitemap files and a limit of 40, the sitemap result stays *unknown*.

## 5. Extra audit: rsgmgmt.com (RSG Management)

I also audited `https://rsgmgmt.com/`, because this assignment was given by RSG Management. The domain **permanently redirects (301) to `http://renovuscapital.com`**, the site of Renovus Capital, *"a private equity firm focused on companies in the education, healthcare services, technology services, and professional services sectors."* It is a WordPress company site, not a shop, so it tests different things than Apple:
- a domain that moved;
- shared templates that repeat one problem on many pages;
- team and portfolio pages.

The first version of my tool failed completely on this site (AI_USAGE.md, case 5). After the fix, the app audits the new address and says so in the report.

### At a glance: Apple India vs rsgmgmt.com

| | Apple India (main) | rsgmgmt.com (extra) |
| --- | --- | --- |
| Type of site | Product website and online store | Company website (private equity firm) |
| Overall score | 90/100 · Excellent | **87/100 · Good** |
| Coverage | 87% (speed not measured) | 87% (speed not measured) |
| Pages analyzed | 10 (+ 4 skipped by robots.txt) | 10 |
| URLs in the sitemaps | 3,174 in the first 40 of 759 sitemap files | 273, all files read (160 posts, 55 portfolio companies, 52 team members, 6 pages) |
| Link destinations checked | 285 (280 verified) | 112 (all verified) |
| Broken internal links | 0 | **1 real 404** |
| Title + description pass | 4 of 10 | **1 of 10** |
| Structured data pass | 8 of 9 | 10 of 10 |
| HTTP → HTTPS redirect | Yes | **No** (`http://` answers 200) |
| Main finding | Long or short titles; broken AppleCare JSON-LD | A 404 on a founder's profile; short titles; one-line team descriptions |

### rsgmgmt.com: the app's report

**Audit:** `audit_b4e0d2224e904a68b7e6ad8bcd70982c`, started 2026-11-19 06:53 UTC, page limit 10. All tables below are printed by `scripts/results_tables.py docs/rsgmgmt-audit.json`.

[Full report JSON](docs/rsgmgmt-audit.json)

#### Audit summary

| Item | Value |
| --- | --- |
| Website | http://renovuscapital.com/ |
| Completed | 2026-11-19 06:54:22 UTC |
| Duration | 124.9 s |
| Rule version | 3.1 |
| Pages analyzed / failed / limit | 10 / 0 / 10 |
| Internal link destinations: found / verified / unverified | 112 / 112 / 0 |
| Overall SEO score | **87/100 · Good** |
| Score status · coverage | partial · 87% of weight measured |
| Action plan source | ai (AI-written plan based on the measured issues.) |

#### The six metrics

| # | Metric | Weight | Score | Underlying checks (passed / evaluated) |
| --- | --- | ---: | ---: | --- |
| 1 | Title and meta description | 12% | 10 | metadata 1/10 |
| 2 | Broken internal links | 12% | 99 | broken_links 111/112 |
| 3 | Crawlability and indexability | 33% | 100 | indexability 10/10, site_health 2/2, canonical 10/10 |
| 4 | Mobile page performance | 13% | unmeasured | performance 0/0 |
| 5 | Content structure and rich results | 25% | 100 | headings 10/10, structured_data 10/10, media 141/141 |
| 6 | AI search readiness | 5% | 100 | geo 10/10 |

#### Metric 1 · Title and meta description, per page

| Page | Title (chars) | Description (chars) | Pass |
| --- | ---: | ---: | :---: |
| http://renovuscapital.com/ | 51 | 137 | Pass |
| https://renovuscapital.com/team-member/kevin-spear/ | 41 | 47 | Fail |
| https://renovuscapital.com/our-team/ | 26 | 115 | Fail |
| https://renovuscapital.com/team-member/alec-shah/ | 46 | 52 | Fail |
| https://renovuscapital.com/company/cloudfirst/ | 28 | 88 | Fail |
| https://renovuscapital.com/team-member/harrison-kelly/ | 45 | 51 | Fail |
| https://renovuscapital.com/team-member/agastya-goel/ | 40 | 46 | Fail |
| https://renovuscapital.com/team-member/jesse-serventi/ | 51 | 57 | Fail |
| https://renovuscapital.com/company/harbor/ | 24 | 86 | Fail |
| https://renovuscapital.com/team-member/daniel-shub/ | 41 | 47 | Fail |

#### Metric 2 · Broken internal links

| Broken URL | HTTP | Found on |
| --- | ---: | --- |
| https://renovuscapital.com/?post_type=company&p=2736 | 404 | https://renovuscapital.com/team-member/jesse-serventi/ |

#### Prioritised action list

1. **[high] Fix the broken internal link on https://renovuscapital.com/team-member/jesse-serventi/ that points to https://renovuscapital.com/?post_type=company&p=2736.** On https://renovuscapital.com/team-member/jesse-serventi/, find the link targeting https://renovuscapital.com/?post_type=company&p=2736 (observed returning HTTP 404). Confirm which portfolio company it should point to, then either update the link to that company's current working page or restore the missing page. If the destination only fails because of access restrictions, check the restricted response manually before changing the link.
2. **[medium] Rewrite the short titles on https://renovuscapital.com/our-team/, https://renovuscapital.com/company/cloudfirst/ and https://renovuscapital.com/company/harbor/.** Update the title tag on each of the three pages using wording already on the page, keeping the existing descriptions. For https://renovuscapital.com/our-team/, use the proposal in the metadata object. For the company pages, extend each title with the wording already in its description: on https://renovuscapital.com/company/cloudfirst/ build on "CloudFirst" and "Technology Services portfolio company", and on https://renovuscapital.com/company/harbor/ build on "Harbor" and "Professional Services portfolio company". Do not add claims beyond the existing page text.
3. **[medium] Expand the short meta descriptions on the flagged team-member pages, e.g. https://renovuscapital.com/team-member/kevin-spear/.** Keep each existing title. Rewrite each description using only the page's current wording (the "Meet Name, Role at Renovus Capital." sentence) by adding a second sentence built from the same words, as shown in the metadata proposal for https://renovuscapital.com/team-member/jesse-serventi/. Apply the same pattern to https://renovuscapital.com/team-member/kevin-spear/, https://renovuscapital.com/team-member/alec-shah/, https://renovuscapital.com/team-member/harrison-kelly/, https://renovuscapital.com/team-member/agastya-goel/ and https://renovuscapital.com/team-member/daniel-shub/. Do not invent roles, capabilities or biographical details.
4. **[low] Review the shared template that produces 3 H1 headings with repeated H1 text "renovus capital" on affected pages.** In the shared template, keep a single descriptive H1 per page and demote the repeated "renovus capital" headings to non-heading text or H2 elements, then check that section levels run consecutively. Fix it once in the template and verify on the homepage and on https://renovuscapital.com/company/cloudfirst/ that the change applies everywhere the pattern was observed.
5. **[low] Review alt text on template and team images, including licon.png and Cassidy-Baird-2023.png, adding alt="" where images repeat link text.** In the shared template, give https://renovuscapital.com/wp-content/themes/renovus/assets/img/licon.png alt="" since it only repeats the "Connect with Us" link text. On https://renovuscapital.com/our-team/, review each team photo inside a text link: add alt="" where the image only repeats the link, or a short description such as the person's name where it adds something. Verify the remaining media elements on the page manually to confirm none need additional context.

#### Coverage notes

- https://rsgmgmt.com/ redirects to http://renovuscapital.com/, so this report audits http://renovuscapital.com/.
- The page limit was reached. This report describes the scanned pages, not necessarily the entire website.
- Core Web Vitals were not measured: Google PageSpeed returned HTTP 429 (quota exceeded). The score leaves out the 13% speed weight, so it can differ from a run where speed was measured. Add PAGESPEED_API_KEY in .env.

### rsgmgmt.com: what it means for the marketing team

- **Fix this week: the broken link on the founding partner's profile.** `/team-member/jesse-serventi/` links to `/?post_type=company&p=2736`, which returns *"Page not found"*. The link has no text (it wraps an image), so it is most likely the logo of a portfolio company whose page was removed. Point it to the company's current page, or remove it.
- **Biggest problem: titles and descriptions. 9 of 10 pages fail; only the home page passes.** Both causes come from templates, so each fix applies to many pages at once:
  - Short titles: *"Our Team - Renovus Capital"* (26 characters), *"CloudFirst - Renovus Capital"* (28) and *"Harbor - Renovus Capital"* (24). They name the page but say nothing about the firm.
  - All 6 team profiles in the sample have a one-sentence description, such as *"Meet Kevin Spear, Associate at Renovus Capital."* (46–57 characters). The sitemap lists 52 profiles, so the profile template probably needs one fix in the SEO plugin.
- **Quick win: the shared header.** Every page has 3 H1 headings, two of them the logo text *"Renovus Capital"*. One theme edit fixes this on all 10 pages. On `/our-team/`, 54 of the 55 images have no `alt` attribute, most of them team photos. Adding each person's name helps image search.
- **Small technical fix:** `rsgmgmt.com` redirects to `http://` instead of `https://`, and `http://renovuscapital.com/` answers 200 instead of redirecting to HTTPS. The impact is small, because the canonical tag points to HTTPS and the HTTPS site sends an HSTS header. The fix is a single redirect rule.
- **Already good:**
  - 111 of 112 link destinations work;
  - every page is indexable, with a correct canonical tag;
  - every page has valid structured data (Organization, WebSite, WebPage, BreadcrumbList);
  - the sitemap is valid (273 URLs, all files read);
  - the AI-search checks pass.
- **What the score does not cover:** speed, because PageSpeed returned HTTP 429 (87% of the weight is measured). Also, only 10 of 273 pages were analyzed.

### rsgmgmt.com: how I checked it by hand

| What I checked | The app said | I found by hand | Match? |
| --- | --- | --- | :---: |
| Where `https://rsgmgmt.com/` goes | Redirects to `http://renovuscapital.com/` | `301 Moved Permanently`, `Location: http://renovuscapital.com` | Yes |
| Home page title and description | 51 and 137 characters | 51 and 137 | Yes |
| Title and description of `/our-team/` | 26 and 115 characters | `Our Team - Renovus Capital` = 26; description 115 | Yes |
| Title and description of `/company/cloudfirst/` | 28 and 88 characters | `CloudFirst - Renovus Capital` = 28; description 88 | Yes |
| Title and description of `/company/harbor/` | 24 and 86 characters | `Harbor - Renovus Capital` = 24; description 86 | Yes |
| Description of `/team-member/kevin-spear/` | 47 characters | `Meet Kevin Spear, Associate at Renovus Capital.` = 47 | Yes |
| Description of `/team-member/daniel-shub/` | 47 characters | `Meet Daniel Shub, Associate at Renovus Capital.` = 47 | Yes |
| Description of `/team-member/jesse-serventi/` | 57 characters | `Meet Jesse Serventi, Founding Partner at Renovus Capital.` = 57 | Yes |
| H1s on the home page | 3 H1s, repeated text "Renovus Capital" | `Renovus Capital`, `Investing in Knowledge and Talent`, `Renovus Capital` | Yes |
| Images on `/our-team/` | 55 media elements; team photos have no alt | 55 `<img>`, 54 without an `alt` attribute | Yes |
| Broken link `/?post_type=company&p=2736` on `/team-member/jesse-serventi/` | HTTP 404 | 404 with my crawler's user agent **and** a browser user agent. The page title is *"Page not found - Renovus Capital"*, so it is a real 404, not a block or rate limit. The link is still on the page. | Yes |
| HTTP → HTTPS | Warning: `http://` answers 200, no redirect | `http://renovuscapital.com/` → `200 OK`, no `Location`; `https://` sends `Strict-Transport-Security` | Yes |

Every value I checked matched.

**Where the app fell short on rsgmgmt.com:**
- **The plan leaves out the HTTPS problem.** HTTPS is reported on its own card but is not scored, so it never reaches the action list. A marketer who reads only the plan would miss it.
- **Internal wording leaks into one action.** Action 2 says *"use the proposal in the metadata object"*. A marketer would not know what a "metadata object" is.
- **The sample leans on one template.** 6 of the 10 pages are team profiles, so the title and description score mostly reflects one template. Menu pages such as About Us and Contact were not in the sample.

## 6. Earlier test audits, and what I learned from them

**amazon.in: tested, but not chosen.**
- Amazon answers bots with 403 or 404 "automated access" pages, even for pages that exist.
- Its home page HTML gives a crawler almost no product links, so the sample filled up with account and sign-in pages.
- Its robots.txt blocks OpenAI's and Perplexity's crawlers (`OAI-SearchBot`, `ChatGPT-User`, `PerplexityBot`).

This test exposed real weaknesses in my tool, which I fixed (AI_USAGE.md, case 1). Its real product pages still gave useful findings: a **189-character title** and a **249-character description**, far longer than Google shows.

**An Apple India product page** (one page): **100/100, but with only 87% coverage**, because PageSpeed returned HTTP 429 and speed could not be measured. This test exposed the structured-data bug in AI_USAGE.md (case 4). [Report JSON](docs/apple-product-audit.json)

**KITSW college website** (17 pages, an older version of the rules): this test showed why coverage matters.
- Its robots.txt asks for a 10-second `Crawl-delay`, so only 1 of 674 links could be checked in time. The other 673 were shown as *unverified*, not as passed.
- The home page title (60 characters) and description (148 characters) were within range. But the page has **two** meta descriptions, so it correctly failed.
