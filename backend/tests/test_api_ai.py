import json
from unittest.mock import AsyncMock
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.config import Settings
from backend.tests.fixtures import sample_report
from backend.app.schemas import AuditJob, CrawlResult
from backend.app.services.ai_service import recommend, fallback_recommendations, validate_recommendations
from backend.app.services.audit_service import run_audit
from backend.app.services.firecrawl_client import crawl_website


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr('backend.app.main.settings.database_path', str(tmp_path / 'audits.sqlite3'))
    with TestClient(app) as client:
        yield client


def test_health_hides_secrets(client):
    response = client.get('/api/health')
    assert response.status_code == 200
    assert 'api_key' not in response.text
    assert isinstance(response.json()['crawler_configured'], bool)
    assert isinstance(response.json()['pagespeed_configured'], bool)


@pytest.mark.parametrize('body', [{},{'url':''},{'url':'not a url'},{'url':'https://'}])
def test_invalid_request_is_422(client,body):
    assert client.post('/api/audits', json=body).status_code == 422


def test_private_url_is_400(client):
    assert client.post('/api/audits',json={'url':'http://127.0.0.1'}).status_code == 400


def test_unknown_audit_is_404(client):
    assert client.get('/api/audits/missing').status_code == 404


def test_oversize_request_and_foreign_origin_rejected(client):
    assert client.post('/api/audits',content='x'*9000).status_code == 413
    assert client.post('/api/audits',json={'url':'https://example.com'},headers={'Origin':'https://hostile.example'}).status_code == 403


def test_valid_audit_async_contract(client,monkeypatch):
    async def resolve(url): return url, ['93.184.216.34']
    async def work(job,config):
        job.status = 'completed'; job.stage = 'completed'; job.report = sample_report()
    monkeypatch.setattr('backend.app.main.resolve_public',resolve)
    monkeypatch.setattr('backend.app.main.run_audit',work)
    response = client.post('/api/audits',json={'url':'https://example.com/'})
    assert response.status_code == 202
    data = response.json()
    assert data['status'] == 'queued'
    result = client.get('/api/audits/' + data['audit_id'])
    assert result.status_code == 200
    assert result.json()['status'] == 'completed'
    assert result.json()['report']['overall_score'] == 78


def test_duplicate_and_capacity_limits(client,monkeypatch):
    async def resolve(url): return url, ['93.184.216.34']
    monkeypatch.setattr('backend.app.main.resolve_public',resolve)
    app.state.jobs['one'] = AuditJob(audit_id='one',website='https://example.com/',status='running')
    assert client.post('/api/audits',json={'url':'https://example.com/'}).status_code == 409
    app.state.jobs['two'] = AuditJob(audit_id='two',website='https://other.com/',status='running')
    assert client.post('/api/audits',json={'url':'https://third.com/'}).status_code == 429


async def test_provider_failure_visible_in_job():
    job = AuditJob(audit_id='test',website='https://example.com/')
    await run_audit(job,Settings(_env_file=None,firecrawl_api_key=''))
    assert job.status == 'failed'
    assert 'FIRECRAWL_API_KEY' in job.error


async def test_fallback_without_ai_key():
    report = sample_report()
    actions, source, note = await recommend(report,Settings(_env_file=None,openai_api_key=''))
    assert source == 'rules' and len(actions) == 5
    assert actions[0].priority == 'high'
    assert all(i in {issue.id for issue in report.issues} for action in actions for i in action.issue_ids)


def test_ai_cannot_invent_evidence_or_priorities():
    report = sample_report()
    action = fallback_recommendations(report.issues)[0].model_dump()
    action['issue_ids'] = ['invented_issue']
    with pytest.raises(ValueError,match='unsupported'):
        validate_recommendations({'recommendations':[action]}, report.issues)
    action = fallback_recommendations(report.issues)[0].model_dump()
    action['priority'] = 'low'
    with pytest.raises(ValueError,match='priority'):
        validate_recommendations({'recommendations':[action]}, report.issues)


def test_ai_metadata_cannot_reference_unmeasured_page():
    report = sample_report()
    action = fallback_recommendations(report.issues)[0].model_dump()
    action['metadata'] = {'page_url':'https://invented.example/','title':'A thoughtful workspace for modern teams','description':'Bring your projects and people together in one thoughtful workspace. Plan your next chapter with more clarity.'}
    with pytest.raises(ValueError,match='Metadata'):
        validate_recommendations({'recommendations':[action]}, report.issues)


@pytest.mark.parametrize('good_response',[True,False])
async def test_custom_openai_url_and_response_validation(monkeypatch,good_response):
    report = sample_report()
    measured = report.model_dump()
    real_client = httpx.AsyncClient
    def handler(request):
        assert str(request.url) == 'https://custom-provider.example/api/v1/chat/completions'
        assert request.headers['Authorization'] == 'Bearer test-key'
        payload = json.loads(request.content)
        assert payload['model'] == 'custom-model'
        assert payload['response_format'] == {'type':'json_object'}
        actions = [action.model_dump() for action in fallback_recommendations(report.issues)]
        if not good_response: actions[0]['issue_ids'] = ['invented']
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'recommendations':actions})}}]})
    monkeypatch.setattr('backend.app.services.ai_service.httpx.AsyncClient',lambda **kw: real_client(transport=httpx.MockTransport(handler),**kw))
    actions,source,note = await recommend(report,Settings(_env_file=None,openai_base_url='https://custom-provider.example/api/v1/',openai_api_key='test-key',openai_model='custom-model'))
    assert source == ('ai' if good_response else 'rules')
    assert actions
    assert report.model_dump() == measured


async def test_ai_network_failure_preserves_report(monkeypatch):
    report = sample_report()
    real_client = httpx.AsyncClient
    def handler(request): raise httpx.ConnectError('offline')
    monkeypatch.setattr('backend.app.services.ai_service.httpx.AsyncClient',lambda **kw: real_client(transport=httpx.MockTransport(handler),**kw))
    actions, source, note = await recommend(report,Settings(_env_file=None,openai_api_key='test'))
    assert actions and source == 'rules' and 'unavailable' in note


async def test_firecrawl_sdk_real_signature_and_payload(monkeypatch,good_html):
    """Use the installed SDK; mock only HTTP at the provider boundary."""
    from firecrawl.v2.utils import http_client
    import requests
    calls = []
    def response(payload):
        result = requests.Response(); result.status_code = 200; result._content = json.dumps(payload).encode(); return result
    def post(url,**kwargs):
        calls.append(kwargs['json'])
        return response({'success':True,'id':'crawl-fixture','url':'https://api.firecrawl.dev/v2/crawl/crawl-fixture'})
    def get(url,**kwargs):
        if url.endswith('/errors'):
            return response({'errors':[],'robotsBlocked':[]})
        return response({'success':True,'status':'completed','total':1,'completed':1,'creditsUsed':1,'expiresAt':'2026-11-17T00:00:00Z','data':[{'rawHtml':good_html,'metadata':{'sourceURL':'https://example.com/','statusCode':200}}]})
    monkeypatch.setattr(http_client.requests,'post',post)
    monkeypatch.setattr(http_client.requests,'get',get)
    result = await crawl_website('https://example.com/',Settings(_env_file=None,firecrawl_api_key='test'))
    assert len(result.pages) == 1
    assert calls[0]['limit'] == 20
    assert calls[0]['sitemap'] == 'include'
    assert calls[0]['allowExternalLinks'] is False
    assert calls[0]['allowSubdomains'] is False
    assert calls[0]['scrapeOptions']['waitFor'] == 1000
    assert calls[0]['scrapeOptions']['formats'] == ['rawHtml']
    assert calls[0]['scrapeOptions']['onlyMainContent'] is False
    assert calls[0].get('ignoreRobotsTxt',False) is False
    assert calls[0]['excludePaths'] == ['(^|/)(cart|basket|checkout|account|my-account|login|logout|signin|sign-in|register|wishlist|search)(/|$)']


def test_sample_is_reproducible_and_explicit():
    a,b = sample_report(),sample_report()
    assert a.model_dump() == b.model_dump()
    assert a.is_sample and '.example' in a.website
    assert a.overall_score == 78 and len(a.issues) == 17


async def test_unexpected_ai_failure_keeps_measured_report(monkeypatch,good_page):
    from backend.app.schemas import SiteChecks
    monkeypatch.setattr('backend.app.services.audit_service.crawl_website',AsyncMock(return_value=CrawlResult(pages=[good_page])))
    monkeypatch.setattr('backend.app.services.audit_service.check_links',AsyncMock(return_value=[]))
    monkeypatch.setattr('backend.app.services.audit_service.audit_site',AsyncMock(return_value=SiteChecks()))
    monkeypatch.setattr('backend.app.services.audit_service.inspect_llms',AsyncMock(return_value={}))
    monkeypatch.setattr('backend.app.services.audit_service.measure_performance',AsyncMock())
    monkeypatch.setattr('backend.app.services.audit_service.verify_pages',AsyncMock())
    monkeypatch.setattr('backend.app.services.audit_service.verify_indexability',AsyncMock())
    monkeypatch.setattr('backend.app.services.audit_service.verify_https',AsyncMock(return_value={'status':'unknown'}))
    monkeypatch.setattr('backend.app.services.audit_service.recommend',AsyncMock(side_effect=RuntimeError('Unexpected provider failure')))
    job = AuditJob(audit_id='test-preserved',website=good_page.url)
    await run_audit(job,Settings(_env_file=None))
    assert job.status == 'completed' and job.report.overall_score == 100
    assert job.report.recommendation_source == 'rules'
    assert 'preserved' in job.report.recommendation_note


def test_provider_errors_make_the_crawl_incomplete_but_ignore_recovered_pages(good_html):
    from backend.app.schemas import CrawlPage
    from backend.app.services.firecrawl_client import add_provider_errors
    result = CrawlResult(pages=[CrawlPage(url='https://example.com/', html=good_html, status_code=200)])
    add_provider_errors(result, {'errors': [{'url': 'https://example.com/'}, {'url': 'https://example.com/gone'}],
                                 'robotsBlocked': ['https://example.com/private']}, 'https://example.com/')
    assert sorted(f.url for f in result.failures) == ['https://example.com/gone', 'https://example.com/private']
    assert result.complete is False


def test_fenced_model_json_is_accepted():
    from backend.app.services.ai_service import strip_code_fence
    assert json.loads(strip_code_fence('```json\n{"recommendations": []}\n```')) == {'recommendations': []}
    assert strip_code_fence('{"a": 1}') == '{"a": 1}'
