import asyncio
import re
import time
import httpx
from urllib.parse import urlsplit
from backend.app.config import Settings
from backend.app.schemas import CrawlPage, CrawlResult, FetchFailure
from backend.app.services.url_safety import normalize_url, UnsafeURL, is_bot_challenge
from backend.app.services.verification import VerifiedNetwork
from bs4 import BeautifulSoup


class CrawlError(RuntimeError):
    pass


def as_dict(value) -> dict:
    return value.model_dump(by_alias=True, exclude_none=True) if hasattr(value, 'model_dump') else value if isinstance(value, dict) else {}


def normalize_documents(documents: list, hostname: str, config: Settings) -> CrawlResult:
    result = CrawlResult()
    seen = set()
    for document in documents:
        data = as_dict(document)
        metadata = as_dict(data.get('metadata', {}))
        raw_url = metadata.get('url') or metadata.get('sourceURL') or metadata.get('source_url') or data.get('url', '')
        try:
            url = normalize_url(raw_url)
        except (UnsafeURL, ValueError):
            result.failures.append(FetchFailure(url=raw_url or '(unknown page)', reason='Crawler returned an invalid or unsafe page URL.'))
            continue
        if urlsplit(url).hostname != hostname:
            result.failures.append(FetchFailure(url=url, reason='Page redirected outside the audited hostname; excluded.'))
            continue
        if url in seen:
            continue
        html = data.get('rawHtml') or data.get('raw_html') or ''
        content_type = metadata.get('contentType') or metadata.get('content_type') or ''
        code = metadata.get('statusCode', metadata.get('status_code'))
        error = metadata.get('error') or data.get('error')
        if error or not html or (content_type and 'html' not in content_type.lower()):
            result.failures.append(FetchFailure(url=url, reason='Crawler did not return usable HTML.' if not error else 'Provider reported a fetch failure.'))
            continue
        if is_bot_challenge(code, html):
            result.failures.append(FetchFailure(url=url, reason=f'The site answered the crawler with a bot-protection page (HTTP {code}); not analyzed.'))
            continue
        if len(html.encode('utf-8')) > config.max_html_bytes:
            result.failures.append(FetchFailure(url=url, reason='HTML exceeded the 2 MB page size limit.'))
            continue
        headers = next((value for value in (metadata.get('responseHeaders'), metadata.get('response_headers'), data.get('headers')) if isinstance(value, dict)), None)
        body = BeautifulSoup(html, 'html.parser').body
        incomplete = body is None or (len(body.get_text(' ',strip=True)) < 80 and not body.find('a',href=True) and not body.find('h1'))
        seen.add(url)
        result.pages.append(CrawlPage(url=url, html=html, status_code=code, original_status_code=code, headers=headers if isinstance(headers, dict) else None, source_kind='incomplete_html' if incomplete else 'firecrawl_rendered'))
        if len(result.pages) >= config.crawl_page_limit:
            break
    result.failures = list({f.url:f for f in result.failures if f.url not in seen}.values())
    result.complete = not result.failures
    return result


def add_provider_errors(result: CrawlResult, errors: dict, website: str) -> None:
    """Record pages Firecrawl failed or was not allowed to fetch; any such page makes the crawl incomplete."""
    for error in errors.get('errors', []):
        result.failures.append(FetchFailure(url=as_dict(error).get('url', website), reason='Firecrawl could not retrieve this page.'))
    for blocked in errors.get('robotsBlocked', errors.get('robots_blocked', [])):
        result.failures.append(FetchFailure(url=str(blocked), reason='Crawling disallowed by robots.txt.'))

    def key(value):
        try:
            return normalize_url(value)
        except ValueError:
            return value
    crawled = {page.url for page in result.pages}
    # A page that failed once but was later returned successfully is not a failure.
    result.failures = list({key(f.url): f for f in result.failures if key(f.url) not in crawled}.values())
    result.complete = result.complete and not result.failures


def utility_path_patterns(url: str, config: Settings) -> list[str]:
    """Cart, account and sign-in pages are not search landing pages. Excluding them keeps the page budget for
    pages a marketer cares about. Not applied when the audited URL itself is such a page."""
    segments = [s.lower() for s in config.excluded_path_segments if re.fullmatch(r'[A-Za-z0-9_-]+', s)]
    if not segments or set(urlsplit(url).path.lower().split('/')) & set(segments):
        return []
    return ['(^|/)(' + '|'.join(segments) + ')(/|$)']


async def resolve_start_url(url: str, config: Settings, network) -> str:
    """Follow the entered URL's redirects, so a site that moved (rsgmgmt.com -> renovuscapital.com, or
    example.com -> www.example.com) is crawled at its real address instead of being discarded as off-site."""
    try:
        async with httpx.AsyncClient(timeout=config.request_timeout_seconds, trust_env=False, headers={'User-Agent': 'CrawlensBot/1.0'}) as client:
            code, _, _, final = await network.request(client, 'GET', url)
        return normalize_url(final) if code < 400 else url
    except (ValueError, httpx.HTTPError, TimeoutError):
        return url


async def landing_page(url: str, config: Settings, network) -> CrawlPage | None:
    """Fetch only the landing page directly (robots.txt respected, no JavaScript). Used when Firecrawl gives nothing."""
    try:
        async with httpx.AsyncClient(timeout=config.request_timeout_seconds, trust_env=False, headers={'User-Agent': 'CrawlensBot/1.0'}) as client:
            code, headers, html, final = await network.request(client, 'GET', url, read_body=True, max_bytes=config.max_html_bytes)
    except (ValueError, httpx.HTTPError, TimeoutError):
        return None
    if code != 200 or 'html' not in headers.get('content-type', '').lower() or is_bot_challenge(code, html)             or urlsplit(final).hostname != urlsplit(url).hostname:
        return None
    return CrawlPage(url=normalize_url(final), html=html, raw_html=html, status_code=code, original_status_code=code, headers=headers,
                     source_kind='http_full_html_fallback', source_notes=['Fetched directly because Firecrawl returned no usable pages; JavaScript was not run.'])


async def crawl_website(url: str, config: Settings, network=None) -> CrawlResult:
    """Crawl the site with Firecrawl. Follows a moved domain first, and if Firecrawl returns nothing usable,
    audits the landing page alone instead of failing the whole audit."""
    if not config.firecrawl_api_key:
        raise CrawlError('Firecrawl is not configured. Add FIRECRAWL_API_KEY to .env and restart the backend.')
    network = network or VerifiedNetwork()
    start = await resolve_start_url(url, config, network)
    try:
        result = await firecrawl_pages(start, config)
    except CrawlError:
        page = await landing_page(start, config, network)
        if page is None:
            raise
        result = CrawlResult(pages=[page], complete=False, warnings=[
            'Firecrawl could not provide usable pages, so only the landing page was analyzed. It was fetched directly, without running JavaScript.'])
    result.start_url = start
    return result


async def firecrawl_pages(url: str, config: Settings) -> CrawlResult:
    from firecrawl import Firecrawl
    # The synchronous SDK runs outside the event loop; each SDK request is bounded.
    client = Firecrawl(api_key=config.firecrawl_api_key, api_url=config.firecrawl_api_url, timeout=15, max_retries=0)
    job_id = None
    documents = []
    completed = False
    deadline = time.monotonic() + config.audit_timeout_seconds * 0.55
    try:
        started = await asyncio.to_thread(client.start_crawl, url, limit=config.crawl_page_limit,
                                        allow_external_links=False, allow_subdomains=False, ignore_robots_txt=False, sitemap='include',
                                        exclude_paths=utility_path_patterns(url, config),
                                        scrape_options={'formats': ['rawHtml'], 'only_main_content': False, 'timeout': 20000, 'wait_for':1000})
        job_id = as_dict(started).get('id')
        if not job_id:
            raise CrawlError('Firecrawl did not return an audit job. Check your provider configuration.')
        while time.monotonic() < deadline:
            status = as_dict(await asyncio.to_thread(client.get_crawl_status, job_id, request_timeout=15))
            documents = status.get('data', []) or documents
            state = status.get('status')
            if state in ('completed', 'failed', 'cancelled'):
                completed = state == 'completed'
                break
            await asyncio.sleep(2)
        result = normalize_documents(documents, urlsplit(url).hostname, config)
        if not completed:
            result.complete = False
            result.warnings.append('The crawl did not finish within its budget; recovered pages are included.')
        try:
            add_provider_errors(result, as_dict(await asyncio.to_thread(client.get_crawl_errors, job_id)), url)
        except Exception:
            result.warnings.append('Provider error details were unavailable; failed-page coverage may be incomplete.')
        if not result.pages:
            raise CrawlError('No usable HTML pages were returned. The site may block crawlers, require sign-in, or be unavailable.')
        return result
    except CrawlError:
        raise
    except Exception as exc:
        if documents:
            result = normalize_documents(documents, urlsplit(url).hostname, config)
            if result.pages:
                result.complete = False
                result.warnings.append('The crawler connection ended early. Recovered pages are included.')
                return result
        # Never relay SDK exception bodies: they may contain credentials or provider internals.
        raise CrawlError('Firecrawl could not complete the request. Check the API key, credit balance, provider URL, and website access.') from exc
    finally:
        if job_id and not completed:
            try:
                await asyncio.wait_for(asyncio.to_thread(client.cancel_crawl, job_id), timeout=5)
            except Exception:
                pass
