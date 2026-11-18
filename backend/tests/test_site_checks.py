import asyncio
import httpx
import pytest
from bs4 import BeautifulSoup
from backend.app.config import Settings
from backend.app.schemas import CrawlPage, SiteChecks, SitemapAudit, PageAnalysis
from backend.app.services.html_extractor import analyze_page
from backend.app.services.robots_policy import RobotsPolicy
from backend.app.services.site_checks import analyze_robots, parse_sitemap, inspect_sitemaps, audit_site, site_issues
from backend.app.services.social_links import extract_social_profiles, profile_url, summarize_social
from backend.app.services.audit_service import make_report
from backend.app.schemas import CrawlResult

BASE = 'https://example.com'


def sitemap(urls, index=False):
    root, item = ('sitemapindex', 'sitemap') if index else ('urlset', 'url')
    return f'<{root} xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(f'<{item}><loc>{url}</loc></{item}>' for url in urls) + f'</{root}>'


@pytest.mark.parametrize('path,allowed', [('/admin', False), ('/admin/public', True), ('/admin/public/private', False), ('/ADMIN', True), ('/report.pdf', False), ('/report.pdf?download=1', True), ('/products?a=1', False)])
def test_robots_longest_rule_wildcards_and_end_marker(path, allowed):
    policy = RobotsPolicy('User-agent: *\nDisallow: /admin\nAllow: /admin/public\nDisallow: /admin/public/private\nDisallow: /*.pdf$\nDisallow: /products?*')
    assert policy.permission('Googlebot', BASE + path)[0] is allowed


def test_robots_groups_and_allow_tie():
    policy = RobotsPolicy('User-agent: *\nDisallow: /\nUser-agent: Googlebot\nDisallow: /private\nUser-agent: Googlebot\nAllow: /private\nUser-agent: Bingbot\nUser-agent: CrawlensBot\nDisallow: /docs')
    assert policy.permission('Googlebot', BASE + '/private') == (True, 'Allow: /private')
    assert policy.permission('Googlebot', BASE + '/elsewhere')[0]
    assert not policy.permission('OtherBot', BASE + '/elsewhere')[0]
    assert not policy.permission('Bingbot', BASE + '/docs')[0]
    assert not policy.permission('CrawlensBot/1.0', BASE + '/docs')[0]


def test_robots_percent_and_unicode_paths():
    policy = RobotsPolicy('User-agent: *\nDisallow: /café\nDisallow: /~admin\nDisallow: /a%2Fb')
    assert not policy.permission('Googlebot', BASE + '/caf%C3%A9')[0]
    assert not policy.permission('Googlebot', BASE + '/%7eadmin')[0]
    assert not policy.permission('Googlebot', BASE + '/a%2fb')[0]
    assert policy.permission('Googlebot', BASE + '/a/b')[0]


def test_robots_missing_and_unavailable_are_distinct():
    missing = analyze_robots(BASE+'/robots.txt', 404, '', [BASE+'/'])
    denied = analyze_robots(BASE+'/robots.txt', 403, '', [BASE+'/'])
    assert missing.status == 'warning' and 'does not block indexing' in missing.summary
    assert denied.status == 'unknown' and not denied.permissions
    assert analyze_robots(BASE+'/robots.txt', 200, '<html>Not found</html>', []).status == 'error'


def test_robots_invalid_lines_and_noindex_are_disclosed():
    robots = analyze_robots(BASE+'/robots.txt', 200, 'Bad line\nUser-agent: *\nNoindex: /\nDisallow: /', [BASE+'/'])
    assert robots.status == 'warning'
    assert len(robots.warnings) == 2
    assert all(not item.allowed for item in robots.permissions)
    assert len(site_issues(SiteChecks(robots_txt=robots), BASE)) == 1


@pytest.mark.parametrize('xml', ['<html>404</html>', '<urlset/>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>', '<broken', '<!DOCTYPE x [<!ENTITY x "boom">]><x/>'])
def test_sitemap_rejects_invalid_xml_namespace_and_entities(xml):
    with pytest.raises(ValueError):
        parse_sitemap(xml)


def test_sitemap_validates_and_deduplicates_urls():
    kind, urls, warnings = parse_sitemap(sitemap([BASE+'/', BASE+'/', 'http://127.0.0.1/private', '/relative', 'https://user:password@example.com/']))
    assert kind == 'urlset' and urls == [BASE+'/']
    assert len(warnings) == 2


async def test_sitemap_index_following_and_scanned_coverage():
    responses = {BASE+'/sitemap.xml': sitemap([BASE+'/pages.xml'], True), BASE+'/pages.xml': sitemap([BASE+'/', BASE+'/about'])}
    async def request(client, method, url, **kwargs):
        return 200, {}, responses[url], url
    pages = [PageAnalysis(url=BASE+path, status_code=200, links=[], checks={}) for path in ('/', '/missing')]
    report = await inspect_sitemaps(BASE, analyze_robots(BASE+'/robots.txt', 404, '', []), pages, None, request)
    assert report.status == 'passed' and report.complete
    assert report.urls_discovered == 2 and len(report.files) == 2
    assert report.scanned_pages_listed == 1 and report.scanned_pages_missing == [BASE+'/missing']


async def test_external_sitemap_and_robots_disallow_are_not_fetched():
    robots = analyze_robots(BASE+'/robots.txt', 200, 'User-agent: *\nDisallow: /hidden.xml\nSitemap: https://elsewhere.example/sitemap.xml\nSitemap: https://example.com/hidden.xml', [])
    async def request(*args, **kwargs):
        raise AssertionError('Out-of-scope and disallowed files must not be fetched')
    report = await inspect_sitemaps(BASE, robots, [], None, request)
    assert report.status == 'unknown' and not report.complete
    assert len(report.files) == 2 and all(file.status == 'unknown' for file in report.files)


@pytest.mark.parametrize('code,status', [(404,'warning'), (403,'unknown'), (503,'unknown')])
async def test_sitemap_missing_and_request_failures(code, status):
    async def request(client, method, url, **kwargs):
        return code, {}, '', url
    report = await inspect_sitemaps(BASE, analyze_robots(BASE+'/robots.txt',404,'',[]), [], None, request)
    assert report.status == status and not report.complete


async def test_sitemap_file_limit_and_cycles():
    robots = analyze_robots(BASE+'/robots.txt', 404, '', [])
    async def cycle(client, method, url, **kwargs):
        return 200, {}, sitemap([url], True), url
    report = await inspect_sitemaps(BASE, robots, [], None, cycle)
    assert len(report.files) == 1 and report.status == 'unknown' and not report.complete
    async def many(client, method, url, **kwargs):
        return 200, {}, sitemap([BASE+f'/part{i}.xml' for i in range(10)], True) if url.endswith('/sitemap.xml') else sitemap([BASE+'/']), url
    report = await inspect_sitemaps(BASE, robots, [], None, many, report=SitemapAudit(file_limit=5))
    assert len(report.files) == 5 and report.status == 'unknown' and report.warnings


async def test_site_audit_failure_preserves_social_evidence(good_page):
    async def request(*args, **kwargs):
        raise httpx.ConnectError('unavailable')
    result = await audit_site(BASE, [analyze_page(good_page, 'example.com')], Settings(_env_file=None), 5, request)
    assert result.robots_txt.status == result.sitemap.status == 'unknown'
    assert result.social.pages_checked == 1


async def test_site_audit_timeout_preserves_completed_files():
    async def request(client, method, url, **kwargs):
        if url.endswith('/robots.txt'):
            return 404, {}, '', url
        if url.endswith('/sitemap.xml'):
            return 200, {}, sitemap([BASE+'/pages.xml', BASE+'/slow.xml'], True), url
        if url.endswith('/pages.xml'):
            return 200, {}, sitemap([BASE+'/']), url
        await asyncio.sleep(1)
    result = await audit_site(BASE, [], Settings(_env_file=None), .2, request)
    assert result.sitemap.urls_discovered == 1 and len(result.sitemap.files) == 3
    assert result.sitemap.status == 'unknown' and not result.sitemap.complete
    assert result.sitemap.warnings


@pytest.mark.parametrize('value', ['https://facebook.com/sharer.php?u=x', 'https://twitter.com/intent/tweet', 'https://x.com/name/status/123', 'https://instagram.com/p/123', 'https://youtube.com/watch?v=123', 'https://youtube.com/@name/videos', 'https://linkedin.com.evil.example/company/name', 'javascript:alert(1)', 'https://github.com/user/repo'])
def test_social_excludes_shares_posts_spoofed_hosts_and_nonprofiles(value):
    assert profile_url(value, BASE) is None


def test_social_normalizes_profiles_and_preserves_source_evidence():
    html = '<a href="https://twitter.com/example/?utm_source=x">X</a><script type="application/ld+json">{"@graph":[{"sameAs":["https://x.com/example", "https://linkedin.com/company/example/"]}]}</script>'
    profiles = extract_social_profiles(BeautifulSoup(html, 'html.parser'), BASE+'/')
    assert len(profiles) == 2
    x = next(profile for profile in profiles if profile.platform == 'X')
    assert x.url == 'https://x.com/example'
    assert set(x.evidence_types) == {'HTML link', 'JSON-LD sameAs'}
    pages = [analyze_page(CrawlPage(url=BASE+path, html=html, status_code=200), 'example.com') for path in ('/', '/about')]
    summary = summarize_social(pages)
    assert summary.status == 'found' and len(summary.profiles) == 2
    assert summary.pages_with_profiles == 2 and all(len(p.source_pages) == 2 for p in summary.profiles)
    assert summarize_social([]).status == 'unknown'


def test_site_health_failure_is_scored_once_and_access_intent_is_reviewed(good_page):
    pages = [analyze_page(good_page, 'example.com')]
    checks = SiteChecks(robots_txt=analyze_robots(BASE+'/robots.txt', 200, 'User-agent: *\nDisallow: /', [BASE+'/']), sitemap=SitemapAudit(status='error',summary='Invalid sitemap XML'))
    report = make_report(BASE, CrawlResult(pages=[good_page]), pages, [], Settings(_env_file=None), checks)
    assert report.metrics['site_health'].evaluated == 1 and report.metrics['site_health'].score == 0
    assert report.overall_score == 81
    assert {issue.metric for issue in report.issues} == {'robots_txt', 'sitemap'}
    assert len(report.recommendations) == 2 and all(item.priority == 'high' for item in report.recommendations)


@pytest.mark.parametrize('mode', ['size_limit', 'gzip'])
async def test_uninspected_sitemap_content_stays_unknown(mode):
    async def request(client, method, url, **kwargs):
        if mode == 'size_limit':
            raise ValueError('Response exceeded the size limit.')
        return 200, {'content-type':'application/gzip'}, 'compressed bytes', url
    report = await inspect_sitemaps(BASE, analyze_robots(BASE+'/robots.txt',404,'',[]), [], None, request)
    assert report.status == 'unknown' and report.files[0].status == 'unknown'
    assert not report.complete


async def test_robots_preview_truncation_does_not_truncate_policy_evaluation():
    body = '# padding\n' * 2000 + '\nUser-agent: *\nDisallow: /sitemap.xml\n'
    async def request(client, method, url, **kwargs):
        assert url.endswith('/robots.txt'), 'The sitemap is disallowed by the complete robots policy'
        return 200, {}, body, url
    result = await audit_site(BASE, [], Settings(_env_file=None), 5, request)
    assert result.robots_txt.content_truncated
    assert result.sitemap.status == 'unknown' and 'disallowed' in result.sitemap.files[0].message
