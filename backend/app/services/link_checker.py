import asyncio
from urllib.parse import urlsplit, urlunsplit
import re
from backend.app.services.robots_policy import RobotsPolicy
import httpx
from backend.app.config import Settings
from backend.app.schemas import LinkResult, PageAnalysis
from backend.app.services.url_safety import safe_request, UnsafeURL, RESTRICTED_CODES, is_bot_challenge

USER_AGENT = 'CrawlensBot/1.0'
ERROR_BODY_BYTES = 65_536  # Enough to recognise a bot-protection screen; larger error pages are truncated, not failed.
TEMPORARY_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_RETRY_WAIT = 1.0
MAX_RETRY_WAIT = 5.0  # A site asking us to wait longer stays "unverified" instead of stalling the audit.


def retry_wait(headers: dict | None) -> float | None:
    """Seconds to wait before the single retry, from Retry-After when given. None means do not retry."""
    value = (headers or {}).get('retry-after')
    if value is None:
        return DEFAULT_RETRY_WAIT
    try:
        seconds = float(value)
    except ValueError:
        return None  # An HTTP-date Retry-After usually means minutes; report the link as unverified instead.
    return seconds if 0 <= seconds <= MAX_RETRY_WAIT else None


def link_sources(pages: list[PageAnalysis]) -> dict[str, list[str]]:
    sources: dict[str, list[str]] = {}
    for page in pages:
        for url in page.links:
            if page.url not in sources.setdefault(url, []):
                sources[url].append(page.url)
    return sources


async def verify_link(client: httpx.AsyncClient, url: str, sources: list[str], request=safe_request) -> LinkResult:
    try:
        async def attempt(method, **options):
            try:
                return await request(client, method, url, **options)
            except (httpx.TimeoutException, httpx.ConnectError):
                return await request(client, method, url, **options)
        code, _, _, final = await attempt('HEAD')
        body, retried = '', False
        # Many otherwise healthy websites reject HEAD or apply different bot rules. Read the start of the GET body
        # so a bot-protection screen is not reported as a broken page.
        if code >= 400:
            code, headers, body, final = await attempt('GET', read_body=True, max_bytes=ERROR_BODY_BYTES, truncate=True)
            # A rate limit (429/503) or a temporary server error (500/502/504) does not prove the link is broken.
            # Wait as the site asks (Retry-After, capped) and try once more.
            wait = retry_wait(headers) if code in TEMPORARY_CODES else None
            if wait is not None:
                await asyncio.sleep(wait)
                code, headers, body, final = await attempt('GET', read_body=True, max_bytes=ERROR_BODY_BYTES, truncate=True)
                retried = True
        if is_bot_challenge(code, body):
            return LinkResult(url=url, source_pages=sources, status='unknown', status_code=code, final_url=final,
                              manual_review=True, reason=f'HTTP {code} with a bot-protection page; availability unverified.')
        if code in RESTRICTED_CODES:
            limited = 'rate limited, still limited after a retry' if retried and code in (429, 503) else 'access restricted or temporarily unavailable'
            return LinkResult(url=url, source_pages=sources, status='unknown', status_code=code, final_url=final,
                              manual_review=True, reason=f'HTTP {code}: {limited}. Check it in a browser.')
        if code < 200 or 300 <= code < 400:
            return LinkResult(url=url, source_pages=sources, status='unknown', status_code=code, reason='No conclusive final response.')
        attempts = 'two GET attempts' if retried else 'GET'
        return LinkResult(url=url, source_pages=sources, status='broken' if code >= 400 else 'ok', status_code=code,
                          final_url=final, reason=f'Confirmed HTTP {code} on {attempts}.' if code >= 400 else None)
    except (httpx.HTTPError, UnsafeURL, ValueError, TimeoutError) as exc:
        reason = str(exc) if isinstance(exc, (UnsafeURL, ValueError)) else 'Request timed out or the destination could not be reached.'
        return LinkResult(url=url, source_pages=sources, status='unknown', reason=reason)


async def check_links(pages: list[PageAnalysis], config: Settings, budget: float, request=None) -> list[LinkResult]:
    request = request or safe_request
    sources = link_sources(pages)
    urls = list(sources)
    results = {url: LinkResult(url=url, source_pages=sources[url], status='unknown', reason='Link check limit reached.' if i >= config.link_check_limit else 'Audit time limit reached.') for i, url in enumerate(urls)}
    semaphore = asyncio.Semaphore(config.link_concurrency)
    robots_cache: dict[str, RobotsPolicy | None] = {}
    robots_locks: dict[str, asyncio.Lock] = {}
    async with httpx.AsyncClient(timeout=config.request_timeout_seconds, trust_env=False, headers={'User-Agent': USER_AGENT}) as client:
        async def allowed(url):
            p = urlsplit(url)
            origin = urlunsplit((p.scheme, p.netloc, '', '', ''))
            async with robots_locks.setdefault(origin, asyncio.Lock()):
                if origin not in robots_cache:
                    try:
                        code, _, body, _ = await request(client, 'GET', origin + '/robots.txt', read_body=True)
                        if code == 200:
                            if re.search(r'<(?:!doctype\s+html|html|body)\b', body, re.I):
                                robots_cache[origin] = None
                                return False
                            parser = RobotsPolicy(body)
                        elif code in (404, 410):
                            parser = RobotsPolicy('')
                        else:
                            robots_cache[origin] = None
                            return False
                        robots_cache[origin] = parser
                    except (ValueError, httpx.HTTPError, TimeoutError):
                        robots_cache[origin] = None
            robot = robots_cache[origin]
            return robot is not None and robot.permission(USER_AGENT, url)[0]

        async def check(url):
            async with semaphore:
                if not await allowed(url):
                    results[url] = LinkResult(url=url, source_pages=sources[url], status='unknown', reason='Disallowed by robots.txt or robots policy could not be verified.')
                else:
                    results[url] = await verify_link(client, url, sources[url], request)

        try:
            await asyncio.wait_for(asyncio.gather(*(check(url) for url in urls[:config.link_check_limit])), timeout=max(0.1, budget))
        except TimeoutError:
            pass  # Completed checks survive; remaining entries explicitly stay unknown.
    for page in pages:
        for ref in page.supplemental.get('link_references', []):
            if ref['url'] in results: results[ref['url']].references.append(ref)
    return list(results.values())
