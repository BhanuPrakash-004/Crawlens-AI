import asyncio
import time
from urllib.parse import urlsplit
from backend.app.config import Settings
from backend.app.schemas import AuditJob, CrawlResult, Coverage, FetchFailure, LinkResult, Report, SiteChecks
from backend.app.services.firecrawl_client import crawl_website, CrawlError
from backend.app.services.html_extractor import analyze_page
from backend.app.services.link_checker import check_links, link_sources
from backend.app.services.score_calculator import calculate_scores
from backend.app.services.issue_builder import build_issues, PRIORITY
from backend.app.services.ai_service import recommend, fallback_recommendations
from backend.app.services.site_checks import audit_site, site_issues, inspect_llms
from backend.app.services.social_links import summarize_social
from backend.app.services.verification import VerifiedNetwork, verify_pages, verify_indexability, verify_https, verify_media, deduplicate_pages
from backend.app.services.performance import measure_performance
from backend.app.services.page_evidence import contextual_checks
from backend.app.services.url_safety import normalize_url


def make_report(website: str, crawl: CrawlResult, pages, links: list[LinkResult], config: Settings, site_checks: SiteChecks | None = None) -> Report:
    pages = list({normalize_url(p.url):p for p in pages}.values())
    links = list({normalize_url(l.url):l for l in links}.values())
    checks = site_checks or SiteChecks(social=summarize_social(pages))
    metrics, score, classification = calculate_scores(pages, links, checks, config)
    warnings = list(crawl.warnings)
    headers = sum(page.headers_available for page in pages)
    unknown = sum(link.status == 'unknown' for link in links)
    if headers < len(pages):
        warnings.append('Response headers were unavailable for some pages. X-Robots-Tag indexability checks are partial.')
    if unknown:
        warnings.append(f'{unknown} internal destination(s) could not be verified and are excluded from the link score.')
    if not links:
        warnings.append('No internal links were available to verify. The link metric is excluded from the overall score.')
    if len(pages) >= config.crawl_page_limit:
        warnings.append('The page limit was reached. This report describes the scanned pages, not necessarily the entire website.')
    if not pages:
        warnings.append('No pages were available to analyze.')
    if any(page.checks['performance'].details.get('quota_limited') for page in pages):
        # The score leaves the speed weight out, so it is not comparable with a run where speed was measured.
        warnings.append(f"Core Web Vitals were not measured: Google PageSpeed returned HTTP 429 (quota exceeded). The score leaves out the "
                        f"{config.metric_weights['performance']}% speed weight, so it can differ from a run where speed was measured. Add PAGESPEED_API_KEY in .env.")
    partial = bool(warnings or crawl.failures or not crawl.complete or any(metric.unknown or metric.review_required or metric.score is None and not metric.not_applicable for metric in metrics.values()))
    issues = build_issues(pages, links) + site_issues(checks, website)
    issues.sort(key=lambda issue: PRIORITY[issue.severity])
    measured_weight = sum(metric.weight for metric in metrics.values() if metric.evaluated)
    summary = (f'{classification} across {len(pages)} unique pages. ' +
               (f'First priority: {issues[0].title.lower()}.' if issues else 'No confirmed issues in the measured scope.'))
    return Report(classification_bands=[config.excellent_score,config.good_score,config.improvement_score], rule_version='3.1', executive_summary=summary, website=website, pages_crawled=len(pages), overall_score=score, classification=classification,
                  score_status='partial' if partial else 'complete', metrics=metrics, issues=issues, pages=pages, links=links,
                  recommendations=fallback_recommendations(issues), site_checks=checks,
                  coverage=Coverage(measured_weight=measured_weight,link_occurrences=sum(len(p.supplemental.get('link_references',p.links)) for p in pages),page_limit=config.crawl_page_limit, pages_analyzed=len(pages), pages_failed=len(crawl.failures),
                                    links_discovered=len(links), links_verified=len(links)-unknown, links_unknown=unknown,
                                    headers_checked=headers, crawl_complete=crawl.complete, failures=crawl.failures, warnings=warnings))


async def run_audit(job: AuditJob, config: Settings):
    started = time.monotonic()
    job.status, job.stage = 'running', 'crawling'

    async def work():
        network = VerifiedNetwork()
        crawl = await crawl_website(job.website, config)
        job.stage = 'verifying_pages'
        available = max(1, config.audit_timeout_seconds - (time.monotonic()-started) - config.ai_timeout_seconds - 3)
        async def isolated(label, task, default=None):
            try: return await task
            except Exception:
                crawl.warnings.append(f'{label} was incomplete. Completed evidence is retained.')
                return default
        await isolated('Direct page verification', verify_pages(crawl, config, network, available * .30))
        job.stage = 'analyzing'
        pages = []
        for page in deduplicate_pages(crawl.pages):
            try:
                pages.append(analyze_page(page, urlsplit(job.website).hostname, config))
            except (ValueError,TypeError,RecursionError,AttributeError):
                crawl.failures.append(FetchFailure(url=page.url,reason='Could not parse this HTML snapshot.'))
        if not pages: raise CrawlError('No usable page evidence could be analyzed.')
        job.stage = 'verifying_links'
        budget = max(.1, config.audit_timeout_seconds - (time.monotonic()-started) - min(config.ai_timeout_seconds,config.audit_timeout_seconds*.2) - 2)
        # Establish indexing intent before comparing canonical and excluded URLs with sitemap contents.
        await isolated('Canonical and crawler verification', verify_indexability(pages,None,config,network,budget*.25))
        contextual_checks(pages, config)
        budget *= .72
        links, site_checks, https, llms, _, _ = await asyncio.gather(
            isolated('Link verification', check_links(pages,config,budget,request=network.request)),
            isolated('Site inspection',audit_site(job.website,pages,config,budget,request=network.request),SiteChecks()),
            isolated('HTTPS verification',asyncio.wait_for(verify_https(job.website,config,network),min(25,budget)),{'status':'unknown','summary':'Secure transport verification was incomplete.'}),
            isolated('llms.txt inspection',inspect_llms(job.website,config,network,budget),{'status':'Review','summary':'Optional file unavailable.'}),
            isolated('Media verification',verify_media(pages,config,network,budget)),
            isolated('PageSpeed',measure_performance(pages,config,budget)))
        if links is None:
            links = [LinkResult(url=url,source_pages=sources,status='unknown',reason='Link verification was incomplete.') for url,sources in link_sources(pages).items()]
        for link in links: link.redirect_chain = network.traces.get(link.url,[])
        site_checks.https, site_checks.llms_txt = https, llms
        job.report = make_report(job.website, crawl, pages, links, config, site_checks)
        job.stage = 'generating_recommendations'
        summaries = []
        actions, source, note = await recommend(job.report, config, summaries)
        if summaries and summaries[0]: job.report.executive_summary = summaries[0]
        job.report.recommendations, job.report.recommendation_source, job.report.recommendation_note = actions, source, note

    try:
        await asyncio.wait_for(work(), timeout=config.audit_timeout_seconds)
        job.status, job.stage = 'completed', 'completed'
    except TimeoutError:
        if job.report:
            job.report.recommendation_note = 'The audit time limit was reached. Measured findings and rule-based actions are preserved.'
            job.status, job.stage = 'completed', 'completed'
        else:
            job.status, job.stage, job.error = 'failed', 'failed', 'The audit timed out before a report could be recovered. Try a smaller site or adjust the audit timeout.'
    except CrawlError as exc:
        job.status, job.stage, job.error = 'failed', 'failed', str(exc)
    except Exception:
        if job.report:
            job.report.recommendations = fallback_recommendations(job.report.issues)
            job.report.recommendation_source = 'rules'
            job.report.recommendation_note = 'Recommendations could not be generated. Measured findings and rule-based actions are preserved.'
            job.status, job.stage = 'completed', 'completed'
        else:
            job.status, job.stage, job.error = 'failed', 'failed', 'The audit could not be completed. Check your provider configuration and try again.'
    finally:
        if job.report:
            job.report.duration_seconds = round(time.monotonic() - started, 1)
