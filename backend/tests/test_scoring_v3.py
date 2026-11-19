import gzip
from collections import Counter
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.app.config import Settings, WEIGHTS
from backend.app.schemas import AuditJob, CrawlPage, CrawlResult, SitemapAudit
from backend.app.services.audit_service import run_audit
from backend.app.services.firecrawl_client import normalize_documents
from backend.app.services.html_extractor import analyze_page
from backend.app.services.issue_builder import build_issues
from backend.app.services.page_evidence import contextual_checks
from backend.app.services.performance import read_performance
from backend.app.services.score_calculator import calculate_scores
from backend.app.services.site_checks import analyze_robots, inspect_sitemaps
from backend.app.services.url_safety import normalize_url

BASE = 'https://example.com'
NS = 'http://www.sitemaps.org/schemas/sitemap/0.9'


def xml(urls, index=False):
    root, element = ('sitemapindex','sitemap') if index else ('urlset','url')
    return f'<{root} xmlns="{NS}">' + ''.join(f'<{element}><loc>{u}</loc></{element}>' for u in urls) + f'</{root}>'


async def test_audit_scores_ten_metrics_with_nested_gzip_shared_links_and_partial_vitals(monkeypatch,good_html):
    config = Settings(_env_file=None,openai_api_key='',pagespeed_page_limit=1)
    first = good_html.replace('</head>','<link rel="canonical" href="/"></head>').replace('/pricing#plans','/gone#old')
    first = first.replace('</body>','<img alt="" role="presentation" src="/product.webp"></body>')
    rendered = first.replace('</body>','<h1>Delivery details</h1></body>')
    second = first.replace('A thoughtful workspace for modern teams','Delivery options for modern team workspaces').replace('Bring your projects','Bring your coworkers').replace('href="/"','href="/shipping"')
    pages = [CrawlPage(url=BASE+'/',html=rendered),CrawlPage(url=BASE+'/shipping',html=second)]
    monkeypatch.setattr('backend.app.services.audit_service.crawl_website',AsyncMock(return_value=CrawlResult(pages=pages)))
    async def resolve(url): return normalize_url(url),['93.184.216.34']
    monkeypatch.setattr('backend.app.services.url_safety.resolve_public',resolve)
    calls = Counter()
    def serve(req):
        path = req.url.path
        calls[req.method,req.url.scheme,path] += 1
        if req.url.host=='www.googleapis.com':
            return httpx.Response(200,json={'lighthouseResult':{'finalUrl':BASE+'/', 'audits':{
                'largest-contentful-paint':{'numericValue':2000}, 'cumulative-layout-shift':{'numericValue':0.2},
                'total-byte-weight':{'numericValue':450000}}}})
        if path=='/robots.txt':
            return httpx.Response(200,text=f'User-agent: *\nAllow: /\nSitemap: {BASE}/root.xml')
        if req.url.scheme=='http': return httpx.Response(301,headers={'location':BASE+path})
        if path=='/root.xml': return httpx.Response(200,text=xml([BASE+'/nested.xml'],True))
        if path=='/nested.xml': return httpx.Response(200,text=xml([BASE+'/pages.xml.gz'],True))
        if path=='/pages.xml.gz': return httpx.Response(200,content=gzip.compress(xml([BASE+'/',BASE+'/shipping']).encode()),headers={'content-type':'application/gzip'})
        if path=='/product.webp': return httpx.Response(200,headers={'content-type':'image/webp','content-length':'2000'})
        if path in ('/','/shipping'): return httpx.Response(200,text=first if path=='/' else second,headers={'content-type':'text/html'})
        return httpx.Response(404)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw: real_client(transport=httpx.MockTransport(serve),**kw))
    job = AuditJob(audit_id='scoring-v3',website=BASE+'/')
    await run_audit(job,config)
    assert job.status=='completed', job.error
    r=job.report
    assert set(r.metrics)==set(WEIGHTS) and sum(m.weight for m in r.metrics.values())==100
    assert r.coverage.measured_weight==100 and r.score_status=='partial'
    assert (r.metrics['performance'].passing,r.metrics['performance'].evaluated,r.metrics['performance'].unknown)==(1,2,4)
    assert r.overall_score==82  # 100 - 12 broken-link points - 6.5 performance points, rounded half up
    assert r.coverage.link_occurrences==2 and r.coverage.links_discovered==1
    link_issue=next(i for i in r.issues if i.metric=='broken_links')
    assert len(link_issue.evidence['references'])==2 and link_issue.affected_source_pages==2
    assert calls['GET','https','/gone']==1 and calls['HEAD','https','/product.webp']==1
    assert calls['GET','https','/']==1 and calls['GET','https','/robots.txt']==1
    warning=next(i for i in r.issues if i.metric=='headings')
    assert warning.outcome=='Warning' and warning.severity=='low'
    assert warning.evidence['headings'][-1]['text']=='Delivery details'
    assert warning.evidence['headings'][-1]['source']=='Rendered snapshot only'
    assert r.metrics['headings'].score==100
    site=r.site_checks.sitemap
    assert (site.declared,site.nested,site.visited,site.successful,site.failed,site.pending)==(1,2,3,3,0,0)
    assert site.complete and site.scanned_pages_listed==2
    assert r.site_checks.llms_txt['status']=='N/A' and r.site_checks.https['http_to_https']


def test_shared_content_and_metadata_have_per_page_evidence(good_page):
    cfg=Settings(_env_file=None,thin_word_limit=3)
    pages=[analyze_page(good_page.model_copy(update={'url':BASE+path}), 'example.com',cfg) for path in ('/a','/b')]
    contextual_checks(pages,cfg)
    assert pages[0].checks['canonical'].details['similar_pages']==[{'url':BASE+'/b','similarity':1.0}]
    assert pages[1].checks['metadata'].details['duplicate_title_urls']==[BASE+'/a']
    metrics,_,_=calculate_scores(pages+[pages[1]],[],config=cfg)
    assert metrics['metadata'].evaluated==2 and metrics['metadata'].passing==0


def test_field_inp_and_cls_units_are_url_specific(good_page):
    p=analyze_page(good_page,'example.com')
    cfg=Settings(_env_file=None)
    field={'id':p.url,'metrics':{'INTERACTION_TO_NEXT_PAINT':{'percentile':200},
                                  'CUMULATIVE_LAYOUT_SHIFT_SCORE':{'percentile':10}}}
    read_performance(p,{'loadingExperience':field},cfg)
    values=p.checks['performance'].details['vitals']
    assert values['CLS']['value']==.1 and values['INP']['passed'] and 'field' in values['INP']['source']
    field['id']=BASE+'/different'
    read_performance(p,{'loadingExperience':field},cfg)
    assert p.checks['performance'].details['vitals']=={} and p.checks['performance'].passed is None


def test_video_captions_and_image_context_are_distinct(good_page):
    good_page.html += '<img src="red.jpg"><img src="bg.png" alt="" role="presentation"><video title="Tour" src="tour.mp4"><track kind="captions" src="en.vtt"></video><video src="silent.mp4"></video>'
    page=analyze_page(good_page,'example.com')
    issue=next(i for i in build_issues([page],[]) if i.metric=='media')
    image,decoration,video,silent=issue.evidence['resources']
    assert image['url']==BASE+'/red.jpg' and image['failures'] and not decoration['failures'] and not decoration['reviews']
    assert video['captions']==[BASE+'/en.vtt'] and not video['reviews']
    assert any('captions' in msg for msg in silent['reviews'])


def test_normalization_preserves_distinct_slashes_queries_and_encoded_separators():
    assert normalize_url('HTTP://EXAMPLE.COM:80/a/../b/./%7E?q=1#top')=='http://example.com/b/~?q=1'
    variants=['/a','/a/','/a//','/a?x=1&x=2','/a?x=2&x=1','/a%2Fb']
    assert len({normalize_url(BASE+p) for p in variants})==len(variants)


def test_good_duplicate_replaces_provider_failure(good_html):
    docs=[{'metadata':{'url':BASE+'/p#old'}},{'rawHtml':good_html,'metadata':{'url':BASE+'/p'}}]
    result=normalize_documents(docs,'example.com',Settings(_env_file=None))
    assert len(result.pages)==1 and result.complete and not result.failures


async def test_partial_sitemap_never_implies_missing_indexable_page(good_page):
    robots=analyze_robots(BASE+'/robots.txt',200,'Sitemap: '+BASE+'/index.xml',[])
    async def request(client,method,url,**kwargs):
        return 200,{},xml([BASE+'/part1',BASE+'/part2'],True) if url.endswith('index.xml') else xml([BASE+'/elsewhere','https://other.example/x']),url
    report=await inspect_sitemaps(BASE,robots,[analyze_page(good_page,'example.com')],None,request,SitemapAudit(file_limit=2))
    assert report.pending==1 and not report.complete and report.status=='unknown'
    assert report.page_coverage[0]['status']=='unverified' and report.external_hosts=={'other.example':1}


def test_empty_duplicate_and_skipped_headings_show_exact_document_positions(good_page):
    good_page.html='<h1></h1><h3>Same</h3><h2>Same</h2><h2>Desk<span>top</span></h2>'
    check=analyze_page(good_page,'example.com').checks['headings']
    assert check.passed is False
    rows=check.details['headings']
    assert rows[3]['text']=='Desktop' and rows[3]['position']==4
    assert 'Repeated heading text' in rows[2]['flags'] and 'Skipped heading level' in rows[1]['flags']


def test_configurable_weights_and_lengths(good_page):
    cfg=Settings(_env_file=None,title_min=5,title_max=10,metric_weights={k:100 if k=='metadata' else 0 for k in WEIGHTS})
    p=analyze_page(good_page,'example.com',cfg)
    metrics,score,_=calculate_scores([p],[],config=cfg)
    assert metrics['metadata'].score==score==0 and '5–10' in p.checks['metadata'].expected
    with pytest.raises(ValueError): Settings(_env_file=None,metric_weights={'metadata':100})


def test_browser_attribute_parsing_preserves_query_and_tracks_small_image_purpose(good_page):
    good_page.html += '<a href="/offers?lang=en&region=in">Offers</a><img width="1" height="1" src="/pixel"><img width="1" height="40" src="/diagram">'
    p = analyze_page(good_page,'example.com')
    assert BASE+'/offers?lang=en&region=in' in p.links
    pixel, diagram = p.checks['media'].details['resources']
    assert not pixel['failures'] and pixel['tracking_pixel_candidate']
    assert diagram['failures'] == ['Missing alt attribute.']


def test_breadcrumb_name_inside_item_and_local_offer_reference(good_page):
    good_page.html = """<script type="application/ld+json">{"@context":"https://schema.org","@graph":[
      {"@type":"Product","name":"Desk","offers":{"@id":"#offer"}},
      {"@type":"Offer","@id":"#offer","price":"20","priceCurrency":"USD"},
      {"@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":1,"item":{"name":"Home"}}]}
    ]}</script><h1>Desk</h1>"""
    check=analyze_page(good_page,'example.com').checks['structured_data']
    assert check.passed, check.observed


async def test_scoped_landing_page_exclusions_do_not_mask_required_failures(good_page):
    from backend.app.services.robots_policy import RobotsPolicy
    from backend.app.services.verification import verify_indexability, VerifiedNetwork
    cfg=Settings(_env_file=None,required_index_urls=[BASE+'/offer'])
    good_page.html += '<meta name="robots" content="noindex,nofollow">'
    private, required = [analyze_page(good_page.model_copy(update={'url':BASE+path}),'example.com',cfg) for path in ('/checkout','/offer')]
    network=VerifiedNetwork()
    network.policies[BASE]=RobotsPolicy('User-agent: *\nAllow: /')
    await verify_indexability([private,required],None,cfg,network,1)
    assert private.checks['indexability'].details['not_applicable']
    assert required.checks['indexability'].passed is False
    issue=next(i for i in build_issues([private,required],[]) if i.metric=='indexability')
    assert issue.severity=='critical' and issue.page_url==required.url


def test_ai_rejects_an_unmeasured_score_or_url_in_narrative():
    from backend.tests.fixtures import sample_report
    from backend.app.services.ai_service import validate_recommendations, fallback_recommendations
    issues=sample_report().issues
    action=fallback_recommendations(issues)[0].model_dump()
    for text in ('Your SEO score is 99.', 'Visit https://invented.example.'):
        actions, summary, problems = validate_recommendations({'executive_summary':text,'recommendations':[action]},issues)
        assert summary == '' and any('Unverified' in p for p in problems) and actions  # Summary dropped, action kept.


async def test_redirect_aliases_share_one_analysis_and_preserve_source(good_page):
    from backend.app.services.verification import deduplicate_pages, verify_pages, VerifiedNetwork
    network=VerifiedNetwork()
    network.traces[BASE+'/old']=[{'url':BASE+'/old','status_code':301,'location':'/new'},{'url':BASE+'/new','status_code':200}]
    network.request=AsyncMock(return_value=(200,{'content-type':'text/html'},good_page.html,BASE+'/new'))
    crawl=CrawlResult(pages=[good_page.model_copy(update={'url':BASE+path}) for path in ('/old','/new')])
    await verify_pages(crawl,Settings(_env_file=None),network,1)
    unique=deduplicate_pages(crawl.pages)
    assert len(unique)==1 and unique[0].url==BASE+'/new' and unique[0].redirect_aliases==[BASE+'/old']


def test_compatibility_products_do_not_need_their_own_offer(good_page):
    good_page.html=good_page.html.replace('"offers":','"isAccessoryOrSparePartFor":[{"@type":"Product","name":"Compatible laptop"}],"offers":')
    check=analyze_page(good_page,'example.com').checks['structured_data']
    assert check.passed and check.details['primary_products']==1 and check.details['nested_products']==1


def test_structured_data_parser_failure_preserves_other_page_evidence(monkeypatch,good_page):
    def unavailable(_): raise RecursionError('fixture oversized graph')
    monkeypatch.setattr('backend.app.services.html_extractor.structured_data_check',unavailable)
    page=analyze_page(good_page,'example.com')
    assert page.checks['structured_data'].outcome=='Review'
    assert page.checks['metadata'].passed and page.checks['headings'].passed


def test_ai_video_advice_is_replaced_when_only_images_were_observed(good_page):
    from backend.app.services.ai_service import scope_media_wording, fallback_recommendations
    good_page.html += '<img src="/photo.png" alt="image">'
    issues=build_issues([analyze_page(good_page,'example.com')],[])
    actions=fallback_recommendations(issues)
    action=next(a for a in actions if any(i.metric=='media' and i.id in a.issue_ids for i in issues))
    action.action='Add video captions to the page'
    assert scope_media_wording(actions,issues)
    assert 'video' not in action.action and 'generic alternative text' in action.suggested_fix


def test_marketer_facing_media_noise_is_excluded(good_page):
    # Empty alt (decorative by the HTML standard), a 1x1 beacon and a CDN image we cannot verify are not issues;
    # a genuinely missing alt still fails.
    good_page.html += ('<img src="https://cdn.example.net/sprite.png" alt="">'
                       '<img src="/beacon" width="1" height="1">'
                       '<img src="https://cdn.example.net/hero.jpg" alt="Blue running shoe, side view">')
    page = analyze_page(good_page, 'example.com')
    assert page.checks['media'].details['review_required'] is False
    assert not [i for i in build_issues([page], []) if i.metric == 'media']
    rows = [r for r in calculate_scores([page], [])[0]['media'].evidence if r['rule'] == 'Image alternative']
    assert [r['status'] for r in rows] == ['N/A', 'N/A', 'Passed']
    good_page.html += '<img src="/loading.gif">'
    assert [i.outcome for i in build_issues([analyze_page(good_page, 'example.com')], []) if i.metric == 'media'] == ['Failed']


def test_first_heading_below_h1_is_reported_once_as_missing_main_heading(good_page):
    good_page.html = '<h2>Skip to</h2><h3>Save time</h3>'
    check = analyze_page(good_page, 'example.com').checks['headings']
    assert check.passed is False and check.details['headings'][0]['flags'] == []
    assert 'No main heading found' in check.observed


async def test_pagespeed_key_is_sent_and_quota_errors_explain_the_score_impact(monkeypatch, good_page):
    from backend.app.services.performance import measure_performance
    from backend.app.services.audit_service import make_report
    from backend.app.schemas import CrawlResult
    seen = []
    def google(request):
        seen.append(request.url.params.get('key'))
        return httpx.Response(429, json={'error': {'code': 429, 'message': 'Quota exceeded'}})
    real_client = httpx.AsyncClient
    monkeypatch.setattr('backend.app.services.performance.httpx.AsyncClient',
                        lambda **kwargs: real_client(transport=httpx.MockTransport(google), **kwargs))
    for key in ('test-key', ''):
        page = analyze_page(good_page, 'example.com')
        await measure_performance([page], Settings(_env_file=None, pagespeed_api_key=key), 5)
        check = page.checks['performance']
        assert check.details['quota_limited'] and check.details['api_key_used'] is bool(key)
        assert ('try again later' if key else 'Add a key in .env') in check.observed and 'test-key' not in check.observed
    assert seen == ['test-key', None]
    report = make_report(BASE + '/', CrawlResult(), [page], [], Settings(_env_file=None))
    assert any('leaves out the 13% speed weight' in w for w in report.coverage.warnings)


def test_template_problem_on_many_pages_is_reported_once_with_every_page(good_page):
    # Like renovuscapital.com: the theme puts a LinkedIn icon without alt in a labelled link, and the logo text in two H1s.
    template = ('<header><h1>Brand</h1></header><a href="https://linkedin.com/company/x">Connect with Us <img src="/licon.png"></a>'
                '<footer><h1>Brand</h1></footer>')
    pages = [analyze_page(good_page.model_copy(update={'url': f'{BASE}/p{i}', 'html': f'<h1>Page {i}</h1>{template}'}), 'example.com') for i in range(3)]
    team = analyze_page(good_page.model_copy(update={'url': f'{BASE}/team', 'html': f'<h1>Team</h1><img src="/jane.jpg">{template}'}), 'example.com')
    issues = build_issues(pages + [team], [])
    media = [i for i in issues if i.metric == 'media']
    headings = [i for i in issues if i.metric == 'headings']
    grouped = next(i for i in media if i.evidence.get('template'))
    assert grouped.affected_source_pages == 3 and grouped.evidence['source_pages'] == [p.url for p in pages]
    assert '(same on 3 pages)' in grouped.title and 'shared template' in grouped.suggested_action
    assert grouped.outcome == 'Review' and grouped.severity == 'low'           # an icon in a labelled link is not a failure
    assert [i.outcome for i in media if not i.evidence.get('template')] == ['Failed']  # the headshot without alt still fails
    assert len(headings) == 1 and headings[0].affected_source_pages == 4 and 'repeated H1 text: brand' in headings[0].observed


def test_icon_inside_a_labelled_link_is_reviewed_not_failed(good_page):
    good_page.html += '<a href="/contact">Contact us <img src="/arrow.png"></a><a href="/x"><img src="/logo.png"></a>'
    page = analyze_page(good_page, 'example.com')
    rows = [r for r in calculate_scores([page], [])[0]['media'].evidence if r['rule'] == 'Image alternative']
    assert [r['status'] for r in rows] == ['Review', 'Failed']   # a link with only an image still needs real alt text
