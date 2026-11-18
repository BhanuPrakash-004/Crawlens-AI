import json
import pytest
from bs4 import BeautifulSoup
from backend.app.schemas import CrawlPage, CrawlResult, LinkResult
from backend.app.config import Settings
from backend.app.services.html_extractor import analyze_page, metadata_check, structured_data_check
from backend.app.services.score_calculator import calculate_scores, rounded
from backend.app.services.issue_builder import build_issues
from backend.app.services.audit_service import make_report
from backend.app.services.firecrawl_client import normalize_documents


def test_all_page_rules_pass(good_page):
    result = analyze_page(good_page, 'example.com')
    assert all(result.checks[key].passed for key in ('metadata','headings','structured_data'))
    assert result.checks['indexability'].passed is None
    assert result.checks['media'].details['not_applicable']
    assert result.checks['performance'].passed is None
    assert result.links == ['https://example.com/pricing']


@pytest.mark.parametrize('title,description,expected', [(30,70,True),(60,160,True),(29,70,False),(61,70,False),(30,69,False),(30,161,False),(0,0,False)])
def test_metadata_inclusive_boundaries(title, description, expected):
    soup = BeautifulSoup(f'<title>  {"x"*title}  </title><meta name="description" content="  {"y"*description}  ">', 'html.parser')
    assert metadata_check(soup).passed is expected


def test_missing_metadata_and_heading():
    result = analyze_page(CrawlPage(url='https://example.com/', html='<p>Hello</p>', status_code=200), 'example.com')
    assert result.checks['metadata'].passed is False
    assert result.checks['headings'].passed is False
    assert result.headers_available is False
    assert 'partially checked' in result.diagnostics[0]


@pytest.mark.parametrize('directive', ['noindex', 'NOINDEX, follow', 'none'])
def test_robot_meta_blocks_indexability(good_page, directive):
    good_page.html += f'<meta name="googlebot" content="{directive}">'
    assert analyze_page(good_page, 'example.com').checks['indexability'].passed is None


@pytest.mark.parametrize('header,expected', [('noindex',None),('googlebot: noindex',None),('otherbot: noindex',None),('otherbot: follow, googlebot: noindex',None)])
def test_scoped_robot_headers(good_page, header, expected):
    good_page.headers = {'X-Robots-Tag':header}
    assert analyze_page(good_page, 'example.com').checks['indexability'].passed is expected


def test_unknown_http_status_is_not_a_pass(good_page):
    good_page.status_code = None
    assert analyze_page(good_page, 'example.com').checks['indexability'].passed is None


def test_heading_diagnostics_do_not_change_primary_rule(good_page):
    good_page.html += '<h4>Skipped level</h4>'
    result = analyze_page(good_page, 'example.com')
    assert result.checks['headings'].passed
    assert result.checks['headings'].details['skipped_levels']


@pytest.mark.parametrize('markup,expected', [({'@context':'https://schema.org','@graph':[{'@type':'Product'}]},False),([{'@context':{'@vocab':'https://schema.org/'},'@type':['Organization']}],False),({'@context':'https://not-schema.org','@type':'Product'},None),({'@context':'https://schema.org','@type':''},None),({'@context':'https://schema.org','@graph':[{'@context':'https://elsewhere.test','@type':'Thing'}]},None)])
def test_structured_data_context_and_graph(markup, expected):
    soup = BeautifulSoup(f'<script type="application/ld+json">{json.dumps(markup)}</script>','html.parser')
    assert structured_data_check(soup).passed is expected


def test_malformed_json_ld():
    result = structured_data_check(BeautifulSoup('<script type="application/ld+json">{"broken":</script>','html.parser'))
    assert not result.passed and result.details['malformed'] == 1


def test_link_normalization_and_deduplication(good_page):
    good_page.html += '<a href="/pricing#two">Same</a><a href="#top">Skip</a><a href="mailto:a@b.com">Skip</a><a href="https://external.com/a">Skip</a><a href="//example.com/pricing">Same</a>'
    assert analyze_page(good_page, 'example.com').links == ['https://example.com/pricing']


def test_weighted_score_uses_unrounded_rates(good_page):
    pages = [analyze_page(good_page.model_copy(update={'url':f'https://example.com/p{i}'}), 'example.com') for i in range(3)]
    pages[0].checks['metadata'].passed = False
    pages[0].checks['structured_data'].passed = False
    links = [LinkResult(url='https://example.com/a',source_pages=[good_page.url],status='ok',status_code=200),LinkResult(url='https://example.com/b',source_pages=[good_page.url],status='broken',status_code=404)]
    metrics, score, _ = calculate_scores(pages, links)
    assert metrics['metadata'].score == 67
    assert score == 68  # 100 * (2/3*12 + .5*12 + 8 + 2/3*10) / 42
    assert rounded(78.5) == 79


def test_all_unknown_is_null_not_zero():
    metrics, score, classification = calculate_scores([], [])
    assert score is None and classification == 'Not enough data'
    assert all(metric.status == 'unknown' for metric in metrics.values())


def test_unknown_links_excluded_and_partial_disclosed(good_page):
    pages = [analyze_page(good_page, 'example.com')]
    links = [LinkResult(url='https://example.com/a',source_pages=[good_page.url],status='unknown',reason='Timeout')]
    report = make_report(good_page.url, CrawlResult(pages=[good_page]), pages, links, Settings(_env_file=None))
    assert report.overall_score == 100
    assert report.metrics['broken_links'].score is None
    assert report.score_status == 'partial'
    assert report.coverage.links_unknown == 1
    assert not report.issues


def test_broken_links_preserve_every_source():
    links = [LinkResult(url='https://example.com/missing', source_pages=['https://example.com/','https://example.com/pricing'], status='broken',status_code=404)]
    issues = build_issues([], links)
    assert len(issues) == 1
    assert issues[0].evidence['source_pages'] == links[0].source_pages
    assert all(issue.affected_source_pages == 2 for issue in issues)


def test_crawler_normalization_rejects_other_hosts_and_missing_html(good_html):
    documents = [{'rawHtml':good_html,'metadata':{'sourceURL':'https://example.com/','statusCode':200}}, {'raw_html':good_html,'metadata':{'source_url':'https://other.com/','status_code':200}}, {'metadata':{'sourceURL':'https://example.com/blocked','statusCode':403}}]
    result = normalize_documents(documents,'example.com',Settings(_env_file=None))
    assert len(result.pages) == 1 and len(result.failures) == 2
    assert result.pages[0].headers is None
    assert not result.complete


def test_crawl_page_limit_is_disclosed(good_page):
    config = Settings(_env_file=None, crawl_page_limit=1)
    pages = [analyze_page(good_page, 'example.com')]
    report = make_report(good_page.url,CrawlResult(pages=[good_page]),pages,[],config)
    assert report.score_status == 'partial'
    assert any('page limit' in warning for warning in report.coverage.warnings)


def test_empty_but_available_headers_remain_known(good_html):
    result = normalize_documents([{'rawHtml':good_html,'metadata':{'sourceURL':'https://example.com/','statusCode':200,'responseHeaders':{}}}], 'example.com', Settings(_env_file=None))
    assert result.pages[0].headers == {}


def test_reported_metric_groups_cover_every_check_once_and_match_the_overall_score(good_page):
    from fractions import Fraction
    from backend.app.config import METRIC_GROUPS, WEIGHTS
    from backend.app.schemas import Report
    pages = [analyze_page(good_page.model_copy(update={'url':f'https://example.com/p{i}'}), 'example.com') for i in range(3)]
    pages[0].checks['metadata'].passed = False
    pages[0].checks['structured_data'].passed = False
    links = [LinkResult(url='https://example.com/a',source_pages=[good_page.url],status='ok',status_code=200),
             LinkResult(url='https://example.com/b',source_pages=[good_page.url],status='broken',status_code=404)]
    report = make_report('https://example.com/', CrawlResult(), pages, links, Settings(_env_file=None))
    groups = {g['key']: g for g in report.metric_groups}
    # Two mandated metrics, three chosen SEO metrics and one AI-search signal; every scored check appears exactly once.
    assert [g['kind'] for g in report.metric_groups] == ['mandatory', 'mandatory', 'seo', 'seo', 'seo', 'ai']
    assert sorted(c for g in report.metric_groups for c in g['checks']) == sorted(WEIGHTS)
    assert sum(g['weight'] for g in report.metric_groups) == 100
    assert groups['title_meta']['score'] == report.metrics['metadata'].score == 67
    assert groups['broken_links']['score'] == 50
    # Recombining the groups by their measured weight reproduces the overall score.
    measured = [g for g in report.metric_groups if g['measured_weight']]
    exact = sum(Fraction(p.passing, p.evaluated) * p.weight for p in report.metrics.values() if p.evaluated)
    assert sum(g['measured_weight'] for g in measured) == report.coverage.measured_weight
    assert rounded(100 * exact / report.coverage.measured_weight) == report.overall_score
    # Groups are part of the API JSON and survive a save/load round trip.
    assert Report.model_validate_json(report.model_dump_json()).metric_groups == report.metric_groups
    assert len(METRIC_GROUPS) == 6


@pytest.mark.parametrize('header,noindex', [
    ('max-image-preview:large, noindex', True),          # a colon-valued directive is not an agent name
    ('googlebot: max-snippet:-1, noindex', True),
    ('unavailable_after: Friday, 25-Jun-10 15:00:00 PST', False),  # a date with a comma must not start an agent group
    ('otherbot: noindex', False),
])
def test_x_robots_tag_directives_containing_colons(good_page, header, noindex):
    good_page.headers = {'X-Robots-Tag': header}
    assert analyze_page(good_page, 'example.com').checks['indexability'].details['noindex'] is noindex


def test_metadata_length_counts_visible_text_not_source_whitespace():
    soup = BeautifulSoup('<title>\n   A thoughtful workspace\n        for modern teams  </title>'
                         '<meta name="description" content="  Plan   your projects \n with people.  ">', 'html.parser')
    details = metadata_check(soup).details
    assert details['title'] == 'A thoughtful workspace for modern teams' and details['title_length'] == 39
    assert details['description'] == 'Plan your projects with people.'


def test_heading_text_is_whitespace_normalized(good_page):
    good_page.html = '<h1>\n   Clarity for teams\n</h1><h2>Plan</h2><h2>  Plan </h2>'
    check = analyze_page(good_page, 'example.com').checks['headings']
    assert check.details['h1'] == ['Clarity for teams']
    assert 'Repeated heading text' in check.details['headings'][2]['flags']
