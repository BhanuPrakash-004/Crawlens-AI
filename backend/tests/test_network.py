import asyncio
import socket
import httpx
import pytest
from backend.app.config import Settings
from backend.app.services.url_safety import normalize_url, resolve_public, safe_request, UnsafeURL
from backend.app.services.link_checker import verify_link, check_links
from backend.app.services.html_extractor import analyze_page


@pytest.mark.parametrize('url', ['http://localhost','http://127.0.0.1','http://10.0.0.1','http://169.254.169.254','http://[::1]','http://[::ffff:127.0.0.1]','http://192.168.1.2','http://0.0.0.0','ftp://example.com','https://user:pass@example.com','https://example.com:8080','https://example.com\\@127.0.0.1','http://service.internal'])
def test_unsafe_urls_rejected(url):
    with pytest.raises(UnsafeURL):
        normalize_url(url)


def test_public_normalization():
    assert normalize_url('HTTPS://EXAMPLE.com:443/a#fragment') == 'https://example.com/a'


async def test_private_dns_rejected(monkeypatch):
    async def resolve(*args, **kwargs):
        return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('10.0.0.1',443))]
    monkeypatch.setattr(asyncio.get_running_loop(),'getaddrinfo',resolve)
    with pytest.raises(UnsafeURL, match='private'):
        await resolve_public('https://example.com')


async def test_dns_rebinding_prevented_by_pinning(monkeypatch):
    async def resolve(url):
        return normalize_url(url), ['93.184.216.34']
    monkeypatch.setattr('backend.app.services.url_safety.resolve_public', resolve)
    def handle(request):
        assert request.url.host == '93.184.216.34'
        assert request.headers['host'] == 'example.com'
        assert request.extensions['sni_hostname'] == 'example.com'
        return httpx.Response(200)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        code, _, _, final = await safe_request(client,'HEAD','https://example.com/')
        assert code == 200 and final == 'https://example.com/'


async def test_private_redirect_blocked(monkeypatch):
    async def resolve(url):
        return normalize_url(url), ['93.184.216.34']
    monkeypatch.setattr('backend.app.services.url_safety.resolve_public', resolve)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(302,headers={'Location':'http://127.0.0.1/secret'}))) as client:
        with pytest.raises(UnsafeURL):
            await safe_request(client,'HEAD','https://example.com/')


@pytest.mark.parametrize('status',[404,500])
async def test_verified_http_failures(status):
    async def request(*args, **kwargs): return status, {}, '', 'https://example.com/broken'
    result = await verify_link(None,'https://example.com/broken',['https://example.com/'],request=request)
    assert result.status == 'broken' and result.status_code == status


async def test_head_falls_back_to_get():
    methods = []
    async def request(client, method, url, **kwargs):
        methods.append(method)
        return (405 if method == 'HEAD' else 200), {}, '', url
    result = await verify_link(None,'https://example.com/a',[],request=request)
    assert methods == ['HEAD','GET'] and result.status == 'ok'


async def test_timeout_is_unknown():
    async def request(*args, **kwargs): raise httpx.ReadTimeout('timeout')
    result = await verify_link(None,'https://example.com/a',[],request=request)
    assert result.status == 'unknown' and result.status_code is None


async def test_auth_failure_requires_manual_review():
    async def request(*args, **kwargs): return 403, {}, '', 'https://example.com/private'
    result = await verify_link(None,'https://example.com/private',[],request=request)
    assert result.status == 'unknown' and result.manual_review


async def test_robots_restriction_is_unknown(monkeypatch,good_page):
    async def request(client, method, url, **kwargs):
        assert url.endswith('/robots.txt')
        return 200, {}, 'User-agent: *\nDisallow: /', url
    monkeypatch.setattr('backend.app.services.link_checker.safe_request',request)
    results = await check_links([analyze_page(good_page,'example.com')],Settings(_env_file=None),3)
    assert results[0].status == 'unknown' and 'robots' in results[0].reason


async def test_response_size_cap(monkeypatch):
    async def resolve(url): return normalize_url(url), ['93.184.216.34']
    monkeypatch.setattr('backend.app.services.url_safety.resolve_public', resolve)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200,content=b'x'*200))) as client:
        with pytest.raises(ValueError,match='size limit'):
            await safe_request(client,'GET','https://example.com/',read_body=True,max_bytes=100)


async def test_link_cap_preserves_unchecked_destinations(monkeypatch,good_page):
    from backend.app.schemas import LinkResult
    good_page.html += '<a href="/another">Another</a>'
    async def robots(client,method,url,**kwargs): return 404,{},'',url
    calls = []
    async def verify(client,url,sources,request=None):
        calls.append(url)
        return LinkResult(url=url,source_pages=sources,status='ok',status_code=200)
    monkeypatch.setattr('backend.app.services.link_checker.safe_request',robots)
    monkeypatch.setattr('backend.app.services.link_checker.verify_link',verify)
    results = await check_links([analyze_page(good_page,'example.com')],Settings(_env_file=None,link_check_limit=1),3)
    assert len(calls) == 1 and len(results) == 2
    assert sum(result.status == 'unknown' for result in results) == 1
    assert any(result.reason == 'Link check limit reached.' for result in results)


async def test_bot_protection_404_is_not_a_broken_link():
    # Amazon answers bots with HTTP 404 "Page Not Found ... To discuss automated access to Amazon data ...".
    bot_page = '<html><title>Page Not Found</title><!-- To discuss automated access to Amazon data please contact us --></html>'
    async def request(client, method, url, **kwargs):
        return 404, {}, bot_page if kwargs.get('read_body') else '', url
    result = await verify_link(None, 'https://example.com/discover/', ['https://example.com/'], request=request)
    assert result.status == 'unknown' and result.manual_review and 'bot-protection' in result.reason
    async def real_404(client, method, url, **kwargs):
        return 404, {}, '<html><h1>Sorry, this page does not exist</h1></html>', url
    assert (await verify_link(None, 'https://example.com/gone', [], request=real_404)).status == 'broken'


def test_crawler_bot_protection_page_is_not_analyzed(good_html):
    from backend.app.config import Settings
    from backend.app.services.firecrawl_client import normalize_documents
    docs = [{'rawHtml': '<html><body>Robot Check. Enter the characters you see below (captcha)</body></html>', 'metadata': {'sourceURL': 'https://example.com/account-area', 'statusCode': 403}},
            {'rawHtml': good_html, 'metadata': {'sourceURL': 'https://example.com/', 'statusCode': 200}}]
    result = normalize_documents(docs, 'example.com', Settings(_env_file=None))
    assert [p.url for p in result.pages] == ['https://example.com/']
    assert 'bot-protection' in result.failures[0].reason and result.complete is False


def test_utility_paths_are_excluded_from_the_crawl_unless_audited_directly():
    from backend.app.config import Settings
    from backend.app.services.firecrawl_client import utility_path_patterns
    import re
    [pattern] = utility_path_patterns('https://example.com/', Settings(_env_file=None))
    assert re.search(pattern, '/gp/cart') and re.search(pattern, '/hz/wishlist/intro') and re.search(pattern, 'ap/signin')
    assert not re.search(pattern, '/cartier-watches') and not re.search(pattern, '/electronics/b')
    assert utility_path_patterns('https://example.com/account/orders', Settings(_env_file=None)) == []


def responses(*answers):
    """A fake site that returns the given (status, headers) answers in order, one per request."""
    queue = list(answers)
    async def request(client, method, url, **kwargs):
        code, headers = queue.pop(0) if len(queue) > 1 else queue[0]
        return code, headers, '', url
    return request


@pytest.mark.parametrize('first', [429, 503, 502, 504])
async def test_rate_limited_or_temporary_errors_are_retried_before_judging(first):
    # HEAD and the first GET are refused; the link works on the polite retry.
    site = responses((first, {'retry-after': '0'}), (first, {'retry-after': '0'}), (200, {}))
    assert (await verify_link(None, 'https://example.com/a', [], request=site)).status == 'ok'


async def test_server_error_twice_is_broken_and_long_rate_limit_stays_unverified(monkeypatch):
    monkeypatch.setattr('backend.app.services.link_checker.DEFAULT_RETRY_WAIT', 0)
    broken = await verify_link(None, 'https://example.com/a', [], request=responses((500, {})))
    assert broken.status == 'broken' and 'two GET attempts' in broken.reason
    limited = await verify_link(None, 'https://example.com/b', [], request=responses((429, {'retry-after': '120'})))
    assert limited.status == 'unknown' and limited.manual_review and 'Check it in a browser' in limited.reason
