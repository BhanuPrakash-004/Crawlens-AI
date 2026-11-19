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


class SiteNetwork:
    """A fake direct-request layer: every URL resolves to `final`, and a GET with a body returns `html`."""
    traces = {}
    def __init__(self, final, html):
        self.final, self.html = final, html
    async def request(self, client, method, url, **kwargs):
        return 200, {'content-type': 'text/html'}, self.html if kwargs.get('read_body') else '', self.final


def firecrawl_returning(monkeypatch, documents):
    """Mock only Firecrawl's HTTP layer; return the crawl requests that were sent."""
    from firecrawl.v2.utils import http_client
    import requests
    sent = []
    def response(payload):
        result = requests.Response(); result.status_code = 200; result._content = json.dumps(payload).encode(); return result
    def post(url, **kwargs):
        sent.append(kwargs['json'])
        return response({'success': True, 'id': 'crawl-fixture', 'url': 'https://api.firecrawl.dev/v2/crawl/crawl-fixture'})
    def get(url, **kwargs):
        if url.endswith('/errors'):
            return response({'errors': [], 'robotsBlocked': []})
        return response({'success': True, 'status': 'completed', 'total': len(documents), 'completed': len(documents), 'creditsUsed': 1,
                         'expiresAt': '2026-11-17T00:00:00Z', 'data': documents})
    monkeypatch.setattr(http_client.requests, 'post', post)
    monkeypatch.setattr(http_client.requests, 'get', get)
    return sent


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
    actions, _, problems = validate_recommendations({'recommendations':[action]}, report.issues)
    assert actions[0].metadata is None and any('Metadata' in p for p in problems)  # The proposal is removed; the action stays.


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
        calls.append(payload['messages'])
        actions = [action.model_dump() for action in fallback_recommendations(report.issues)]
        if not good_response: actions[0]['issue_ids'] = ['invented']
        plan = {'executive_summary': 'Two pages are hidden from search and several links are broken.', 'recommendations': actions}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(plan)}}]})
    calls = []
    monkeypatch.setattr('backend.app.services.ai_service.httpx.AsyncClient',lambda **kw: real_client(transport=httpx.MockTransport(handler),**kw))
    actions,source,note = await recommend(report,Settings(_env_file=None,openai_base_url='https://custom-provider.example/api/v1/',openai_api_key='test-key',openai_model='custom-model'))
    # A bad action is dropped and retried with feedback; the rest of the AI plan is kept, and the dropped
    # finding gets its rule-based action, so it does not disappear from the plan.
    assert source == 'ai' and len(calls) == (1 if good_response else 2)
    assert all('invented' not in a.issue_ids for a in actions)
    if not good_response:
        assert 'unsupported' in calls[1][-1]['content'] and 'rule-based action' in note
        assert any(a.source == 'rules' and a.priority == 'high' for a in actions)
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
    result = await crawl_website('https://example.com/',Settings(_env_file=None,firecrawl_api_key='test'),network=SiteNetwork('https://example.com/',good_html))
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


def test_llm_may_quote_measured_values_but_not_invent_them():
    from backend.app.services.ai_service import fit_summary
    report = sample_report()  # issue_1: "Title: 47 characters; description: 0 characters." on /features
    base = {'priority': 'medium', 'issue_ids': ['issue_1'], 'action': 'Add a meta description to the features page',
            'reason': 'Searchers see no summary of the page before they click.'}
    grounded = {**base, 'suggested_fix': 'The description has 0 characters; write one of 70–160 characters for https://northstar.example/features.'}
    invented = {**base, 'issue_ids': ['issue_2'], 'suggested_fix': 'This will raise clicks by 35% within 2 weeks.'}
    actions, _, problems = validate_recommendations({'executive_summary': 'Ok.', 'recommendations': [grounded, invented]}, report.issues)
    assert [a.issue_ids for a in actions] == [['issue_1']] and actions[0].source == 'ai'
    assert any('35' in p for p in problems)
    long = 'The site is in fair shape. ' * 30
    assert fit_summary(long).endswith('shape.') and len(fit_summary(long)) <= 500


async def test_retry_names_the_problem_and_uses_the_fixed_answer(monkeypatch):
    report = sample_report()
    actions = [a.model_dump() for a in fallback_recommendations(report.issues)]
    answers = [{'executive_summary': 'Fixing these issues will add 40% more traffic.', 'recommendations': actions},
               {'executive_summary': 'Two pages are hidden from search, and broken links stop visitors on three pages.', 'recommendations': actions}]
    sent = []
    def handler(request):
        sent.append(json.loads(request.content)['messages'])
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(answers[len(sent) - 1])}}]})
    real_client = httpx.AsyncClient
    monkeypatch.setattr('backend.app.services.ai_service.httpx.AsyncClient', lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    summaries = []
    plan, source, note = await recommend(report, Settings(_env_file=None, openai_api_key='test'), summaries)
    assert len(sent) == 2 and '40' in sent[1][-1]['content']          # the retry says exactly what was wrong
    assert summaries == [answers[1]['executive_summary']] and source == 'ai' and 'rule-based' not in note
    assert all(a.source == 'ai' for a in plan)


async def test_provider_rate_limit_waits_for_retry_after_then_uses_the_ai_plan(monkeypatch):
    report = sample_report()
    actions = [a.model_dump() for a in fallback_recommendations(report.issues)]
    plan = {'executive_summary': 'Two pages are hidden from search and several internal links are broken.', 'recommendations': actions}
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        if len(calls) == 1:  # Groq-style per-minute limit on the first call
            return httpx.Response(429, headers={'retry-after': '0'}, json={'error': {'message': 'Rate limit reached'}})
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(plan)}}]})
    real_client = httpx.AsyncClient
    monkeypatch.setattr('backend.app.services.ai_service.httpx.AsyncClient', lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    result, source, note = await recommend(report, Settings(_env_file=None, openai_api_key='test'))
    assert len(calls) == 2 and source == 'ai' and all(a.source == 'ai' for a in result)
    # The prompt is compact: shared text once per metric, at most 40 issues, no per-issue rule text repeated.
    prompt = calls[0]['messages'][1]['content']
    evidence = json.loads(prompt)
    assert set(evidence['rules']) == {i.metric for i in report.issues} and 'suggested_action' not in prompt
    assert len(evidence['issues']) == len(report.issues) <= 40 and len(prompt) < 7000


async def test_invalid_json_from_provider_is_retried_with_feedback(monkeypatch):
    report = sample_report()
    plan = {'executive_summary': 'Two pages are hidden from search.', 'recommendations': [a.model_dump() for a in fallback_recommendations(report.issues)]}
    sent = []
    def handler(request):
        sent.append(json.loads(request.content)['messages'])
        if len(sent) == 1:  # Groq rejects a non-JSON answer in JSON mode with HTTP 400.
            return httpx.Response(400, json={'error': {'code': 'json_validate_failed', 'message': 'Failed to validate JSON.'}})
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(plan)}}]})
    real_client = httpx.AsyncClient
    monkeypatch.setattr('backend.app.services.ai_service.httpx.AsyncClient', lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    _, source, _ = await recommend(report, Settings(_env_file=None, openai_api_key='test'))
    assert source == 'ai' and len(sent) == 2 and 'not valid JSON' in sent[1][-1]['content']
    example = sent[0][0]['content'].split('example: ', 1)[1].split(' priority is', 1)[0]
    assert json.loads(example)['recommendations'][0]['metadata'] is None  # the example in the prompt is real JSON


def test_feedback_names_the_field_and_standard_values_are_allowed():
    report = sample_report()  # issue_15: broken link, "HTTP 404"; indexability issues expect "HTTP 200"
    too_long = {'priority': 'high', 'issue_ids': ['issue_15'], 'action': 'x' * 200, 'reason': 'r', 'suggested_fix': 'f'}
    standard = {'priority': 'high', 'issue_ids': ['issue_15'], 'action': 'Fix the broken link on the home page',
                'reason': 'Visitors hit an HTTP 404 page.', 'suggested_fix': 'Point it to a page that returns HTTP 200.'}
    actions, _, problems = validate_recommendations({'executive_summary': 'Ok.', 'recommendations': [too_long, standard]}, report.issues)
    assert len(actions) == 1 and problems == ['Recommendation 1: action: String should have at most 180 characters.']


async def test_moved_domain_is_crawled_at_its_new_address(monkeypatch, good_html):
    # rsgmgmt.com answers with a 301 to renovuscapital.com. Before, every page was discarded as "off-site".
    new_home = 'https://renovus.example/'
    sent = firecrawl_returning(monkeypatch, [{'rawHtml': good_html, 'metadata': {'sourceURL': new_home, 'statusCode': 200}}])
    result = await crawl_website('https://old-brand.example/', Settings(_env_file=None, firecrawl_api_key='test'),
                                 network=SiteNetwork(new_home, good_html))
    assert sent[0]['url'] == new_home and result.start_url == new_home
    assert [page.url for page in result.pages] == [new_home] and not result.failures


async def test_landing_page_is_audited_when_firecrawl_returns_nothing(monkeypatch, good_html):
    firecrawl_returning(monkeypatch, [])
    result = await crawl_website('https://example.com/', Settings(_env_file=None, firecrawl_api_key='test'),
                                 network=SiteNetwork('https://example.com/', good_html))
    assert [page.url for page in result.pages] == ['https://example.com/'] and result.pages[0].source_kind == 'http_full_html_fallback'
    assert result.complete is False and 'only the landing page was analyzed' in result.warnings[0]
    # If even the landing page is unusable (here: a bot-protection screen), the audit fails with a clear message.
    blocked = SiteNetwork('https://example.com/', '<html><body>Robot Check: enter the captcha</body></html>')
    async def refused(client, method, url, **kwargs):
        return 403, {'content-type': 'text/html'}, blocked.html if kwargs.get('read_body') else '', url
    blocked.request = refused
    with pytest.raises(Exception, match='No usable HTML pages'):
        await crawl_website('https://example.com/', Settings(_env_file=None, firecrawl_api_key='test'), network=blocked)


async def test_report_says_when_the_entered_url_redirected_to_another_site(monkeypatch, good_page):
    from backend.app.schemas import SiteChecks
    moved = good_page.model_copy(update={'url': 'https://renovus.example/'})
    monkeypatch.setattr('backend.app.services.audit_service.crawl_website',
                        AsyncMock(return_value=CrawlResult(pages=[moved], start_url='https://renovus.example/')))
    for name in ('verify_pages', 'verify_indexability', 'measure_performance'):
        monkeypatch.setattr(f'backend.app.services.audit_service.{name}', AsyncMock())
    monkeypatch.setattr('backend.app.services.audit_service.check_links', AsyncMock(return_value=[]))
    monkeypatch.setattr('backend.app.services.audit_service.audit_site', AsyncMock(return_value=SiteChecks()))
    monkeypatch.setattr('backend.app.services.audit_service.inspect_llms', AsyncMock(return_value={}))
    monkeypatch.setattr('backend.app.services.audit_service.verify_https', AsyncMock(return_value={'status': 'unknown'}))
    job = AuditJob(audit_id='moved', website='https://old-brand.example/')
    await run_audit(job, Settings(_env_file=None, openai_api_key=''))
    assert job.status == 'completed' and job.report.website == 'https://renovus.example/'
    assert job.report.requested_url == 'https://old-brand.example/'
    assert job.report.coverage.warnings[0] == 'https://old-brand.example/ redirects to https://renovus.example/, so this report audits https://renovus.example/.'


async def test_wrong_provider_path_gives_a_clear_configuration_message(monkeypatch):
    # AWS Bedrock without the /openai/v1 prefix answers HTTP 200 with a non-chat body.
    calls = []
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={'Output': {'__type': 'com.amazon.coral.service#UnknownOperationException'}, 'Version': '1.0'})
    real_client = httpx.AsyncClient
    monkeypatch.setattr('backend.app.services.ai_service.httpx.AsyncClient', lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    actions, source, note = await recommend(sample_report(), Settings(_env_file=None, openai_api_key='test', openai_base_url='https://bedrock-runtime.us-east-1.amazonaws.com'))
    assert source == 'rules' and actions and len(calls) == 1      # no pointless retry
    assert 'OPENAI_BASE_URL' in note and '/openai/v1' in note
