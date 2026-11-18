import json
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.schemas import AuditJob, CrawlPage, CrawlResult, SiteChecks
from backend.app.config import Settings
from backend.app.services.html_extractor import analyze_page
from backend.app.services.verification import VerifiedNetwork, verify_pages, verify_indexability
from backend.app.services.robots_policy import RobotsPolicy


def test_sqlite_history_survives_restart_and_search_is_literal(tmp_path, monkeypatch):
    path=str(tmp_path / 'history.sqlite3')
    monkeypatch.setattr('backend.app.main.settings.database_path',path)
    with TestClient(app) as client:
        app.state.store.save(AuditJob(audit_id='saved',website='https://example.com/',status='failed',error='Provider unavailable'))
        app.state.store.save(AuditJob(audit_id='interrupted',website='https://other.example/',status='running'))
        assert client.get('/api/audits?q=EXAMPLE.COM').json()['total']==1
        assert client.get('/api/audits?q=%').json()['total']==0
        assert len(client.get('/api/audits?limit=1&offset=1').json()['items'])==1
    with TestClient(app) as client:
        assert client.get('/api/audits/saved').json()['error']=='Provider unavailable'
        interrupted=client.get('/api/audits/interrupted').json()
        assert interrupted['status']=='failed' and interrupted['stage']=='interrupted'
        assert client.get('/api/audits').json()['total']==2


def test_duplicate_metadata_conflicting_canonical_and_optional_diagnostics(good_page):
    good_page.html+='<meta name="description" content="Duplicate"><link rel="canonical" href="/a"><link rel="canonical" href="/b"><img src="meaningful.png"><img role="presentation" src="decorative.png"><meta name="viewport" content="width=device-width">'
    page=analyze_page(good_page,'example.com')
    assert page.checks['metadata'].details['description_count']==2
    assert page.checks['metadata'].passed is False
    assert page.checks['indexability'].details['canonical']['status']=='conflicting'
    assert page.checks['indexability'].passed is None  # Pending crawler access.
    assert page.checks['canonical'].passed is False
    assert page.supplemental['images']['missing_alt']==['meaningful.png']
    assert page.supplemental['viewport']['present']


def test_named_organization_passes_and_incomplete_product_fails(good_page):
    good_page.html='<html><head><script type="application/ld+json">'+json.dumps({'@context':'https://schema.org','@type':'Organization','name':'College'})+'</script></head><body><h1>College</h1></body></html>'
    check=analyze_page(good_page,'example.com').checks['structured_data']
    assert check.passed is True and not check.details['not_applicable']
    good_page.html=good_page.html.replace('Organization','Product')
    check=analyze_page(good_page,'example.com').checks['structured_data']
    assert check.passed is False and check.details['validation_errors']


async def test_incomplete_crawler_html_uses_verified_full_source(good_html,monkeypatch):
    network=VerifiedNetwork()
    async def request(client,method,url,**kwargs):
        return 200,{'content-type':'text/html'},good_html,url
    monkeypatch.setattr(network,'request',request)
    crawl=CrawlResult(pages=[CrawlPage(url='https://example.com/',html='<html><head><title>Only head</title></head></html>',source_kind='incomplete_html')])
    await verify_pages(crawl,Settings(_env_file=None),network,2)
    page=crawl.pages[0]
    assert page.source_kind=='http_full_html_fallback'
    assert page.headers is not None
    assert analyze_page(page,'example.com').checks['headings'].passed is True


async def test_broken_canonical_and_intentional_exclusion(good_page,monkeypatch):
    good_page.html+='<link rel="canonical" href="/missing">'
    page=analyze_page(good_page,'example.com')
    network=VerifiedNetwork();network.policies['https://example.com']=RobotsPolicy('User-agent: *\nAllow: /')
    async def request(client,method,url,**kwargs): return 404,{},'',url
    monkeypatch.setattr(network,'request',request)
    await verify_indexability([page],SiteChecks(),Settings(_env_file=None),network,2)
    assert page.checks['indexability'].passed is True
    assert page.checks['canonical'].passed is False
    assert page.checks['indexability'].details['canonical']['status']=='broken'
    good_page.html+='<meta name="robots" content="noindex">'
    page=analyze_page(good_page,'example.com')
    await verify_indexability([page],SiteChecks(),Settings(_env_file=None),network,2)
    assert page.checks['indexability'].passed is None
    assert page.checks['indexability'].details['review_required']


async def test_bot_protection_refusal_keeps_the_crawlers_page_evidence(good_html, monkeypatch):
    network = VerifiedNetwork()
    async def refused(client, method, url, **kwargs):
        return 403, {'content-type': 'text/html', 'x-robots-tag': 'noindex'}, '<html><body>Access denied</body></html>', url
    monkeypatch.setattr(network, 'request', refused)
    crawl = CrawlResult(pages=[CrawlPage(url='https://example.com/', html=good_html, status_code=200)])
    await verify_pages(crawl, Settings(_env_file=None), network, 2)
    page = analyze_page(crawl.pages[0], 'example.com')
    # The refusal page's 403 and noindex header must not replace what the crawler actually received.
    assert crawl.pages[0].status_code == 200 and crawl.pages[0].headers is None
    assert page.checks['metadata'].passed is True and page.checks['indexability'].details['noindex'] is False
    assert any('refused (HTTP 403)' in note for note in crawl.pages[0].source_notes)
