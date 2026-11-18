import asyncio
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit, urlunsplit
import httpx
from backend.app.config import Settings, settings
from backend.app.schemas import SiteChecks, RobotsAudit, SitemapAudit, SitemapFile, CrawlPermission, Issue
from backend.app.services.robots_policy import RobotsPolicy
from backend.app.services.social_links import summarize_social
from backend.app.services.url_safety import normalize_url, safe_request

NS = '{http://www.sitemaps.org/schemas/sitemap/0.9}'


def analyze_robots(url: str, code: int, content: str, page_urls: list[str], config=settings) -> RobotsAudit:
    report = RobotsAudit(url=url, status_code=code)
    if code in (404, 410):
        report.status = 'warning'
        report.summary = 'robots.txt was not found. No crawl restrictions are declared by this file; its absence does not block indexing.'
        return report
    if not 200 <= code < 300:
        report.summary = f'robots.txt returned HTTP {code}. Crawl permissions could not be confirmed.'
        return report
    if re.search(r'<(?:!doctype\s+html|html|body)\b', content, re.I):
        report.status, report.summary = 'error', 'The robots.txt URL returned HTML instead of a robots policy.'
        return report
    policy = RobotsPolicy(content)
    report.crawl_delay_seconds = policy.crawl_delay()
    report.content = content[:15000]
    report.content_truncated = len(content) > 15000
    report.rules, report.sitemap_urls, report.warnings = policy.rules, policy.sitemaps, policy.warnings
    for page in dict.fromkeys(page_urls):
        for agent in dict.fromkeys([*config.search_crawlers, *config.ai_crawlers, 'CrawlensBot']):
            allowed, matched = policy.permission(agent, page)
            report.permissions.append(CrawlPermission(page_url=page, agent=agent, allowed=allowed, matched_rule=matched))
    blocked = sum(not item.allowed and item.agent == 'Googlebot' for item in report.permissions)
    report.status = 'warning' if blocked or report.warnings else 'passed'
    report.summary = f'Googlebot is blocked on {blocked} checked URL(s). Confirm these restrictions are intentional.' if blocked else 'robots.txt is accessible. No checked URLs are blocked for Googlebot.'
    if report.warnings: report.summary += ' ' + ' '.join(report.warnings[:3])
    return report


def parse_sitemap(content: str) -> tuple[str, list[str], list[str]]:
    # Reject declarations before parsing; no DTD/entity resolution or expansion.
    if re.search(r'<!\s*(DOCTYPE|ENTITY)\b', content, re.I):
        raise ValueError('DTD and entity declarations are not allowed in a sitemap.')
    try:
        root = ET.fromstring(content)
    except (ET.ParseError, ValueError) as exc:
        raise ValueError('The response is not valid sitemap XML.') from exc
    if root.tag not in (NS + 'urlset', NS + 'sitemapindex'):
        raise ValueError('Expected a urlset or sitemapindex with the standard sitemap namespace.')
    kind = 'index' if root.tag == NS + 'sitemapindex' else 'urlset'
    entry_tag = NS + ('sitemap' if kind == 'index' else 'url')
    entries = root.findall(entry_tag)
    if not entries:
        raise ValueError('The sitemap contains no URL entries.')
    if len(entries) > 50000:
        raise ValueError('The sitemap exceeds 50,000 entries.')
    urls, warnings = [], []
    if any(child.tag != entry_tag and str(child.tag).startswith(NS) for child in root):
        warnings.append('Unexpected sitemap element in this file.')
    for entry in entries:
        locs = entry.findall(NS + 'loc')
        if len(locs) != 1 or not locs[0].text:
            warnings.append('An entry has a missing or repeated loc element.')
            continue
        value = locs[0].text.strip()
        try:
            if len(value) >= 2048 or not value.startswith(('https://', 'http://')):
                raise ValueError()
            urls.append(normalize_url(value))
        except ValueError:
            warnings.append('An entry contains an invalid, credentialed, or non-public URL.')
    if len(urls) != len(set(urls)):
        warnings.append('Duplicate loc entries were found.')
    return kind, list(dict.fromkeys(urls)), list(dict.fromkeys(warnings))


def compare_sitemap(report, pages, discovered, config):
    rows = []
    for page in pages:
        url = normalize_url(page.url)
        check = page.checks.get('indexability')
        canonical = page.checks.get('canonical')
        targets = canonical.details.get('targets',[]) if canonical else []
        redirects = [r.get('url') for r in page.supplemental.get('http',{}).get('redirect_chain',[])]
        redirects.extend(page.supplemental.get('http',{}).get('aliases',[]))
        if url in discovered:
            status, reason = 'listed', 'Normalized final URL is listed.'
            if check and check.details.get('noindex'): reason += ' Listed URL declares noindex; review inclusion.'
            if targets and url not in targets: reason += ' Page declares a different canonical; review inclusion.'
        elif check and (check.details.get('noindex') or check.details.get('not_applicable') or check.details.get('robots_allowed') is False) or set(urlsplit(url).path.split('/')) & set(config.excluded_path_segments):
            status, reason = 'excluded', 'Search exclusion or configured utility path; confirm intent.'
        elif any(t in discovered for t in targets):
            status, reason = 'canonical listed', 'The declared canonical is listed: ' + next(t for t in targets if t in discovered)
        elif any(t in discovered for t in redirects):
            status, reason = 'redirect listed', 'A redirecting source URL is listed. Prefer the final canonical URL.'
        elif not report.complete:
            status, reason = 'unverified', 'Absent from inspected files. Incomplete traversal prevents a site-wide conclusion.'
        else:
            status, reason = 'unlisted', 'No normalized final URL, declared canonical or known redirect source matched.'
        rows.append({'url':url,'status':status,'reason':reason})
    report.page_coverage = rows
    report.scanned_pages_listed = sum(r['status']=='listed' for r in rows)
    report.scanned_pages_missing = [r['url'] for r in rows if r['status'] in ('unlisted','unverified','redirect listed')]


async def inspect_sitemaps(website, robots, pages, client, request=safe_request, report=None, policy=None, config=settings):
    from collections import deque, Counter
    origin = urlunsplit((*urlsplit(website)[:2], '', '', ''))
    hostname = urlsplit(website).hostname
    report = report if report is not None else SitemapAudit(file_limit=config.sitemap_file_limit)
    def key(url):
        try: return normalize_url(url)
        except ValueError: return url
    roots = list(dict.fromkeys(key(u) for u in robots.sitemap_urls))
    report.declared = len(roots)
    queue = deque(roots or [origin+'/sitemap.xml'])
    fallbacks = deque([origin+'/sitemap_index.xml', origin+'/sitemap-index.xml'] if not roots else [])
    scheduled, nested, discovered = set(queue), set(), set()
    hosts = {hostname, *(host.lower() for host in config.sitemap_hosts)}
    trusted = set(roots)
    external = Counter()
    graph = {}
    if policy is None and robots.status_code == 200 and not robots.content_truncated:
        policy = RobotsPolicy(robots.content)
    try:
        while queue and len(report.files) < report.file_limit:
            raw = queue.popleft()
            file = SitemapFile(url=raw, message='Inspection did not finish within the audit budget.')
            report.files.append(file)
            try:
                url = normalize_url(raw)
                if urlsplit(url).hostname not in hosts:
                    file.message = 'External sitemap declaration outside the audited host. Cross-site ownership remains unverified.'
                    continue
                if policy and not policy.permission('CrawlensBot',url)[0]:
                    file.message = 'Sitemap disallowed by robots.txt for CrawlensBot.'
                    continue
                report.visited += 1
                code, headers, content, final = await request(client,'GET',url,read_body=True,max_bytes=config.sitemap_bytes,sitemap_body=True)
                file.status_code = code
                if urlsplit(final).hostname not in hosts:
                    file.message = 'Sitemap redirected outside the audited hostname.'
                    continue
                if code in (404,410):
                    file.status = 'error' if roots or url in nested else 'warning'
                    file.message = f'Sitemap not found (HTTP {code}).'
                    if not queue and fallbacks: queue.append(fallbacks.popleft())
                    continue
                if code != 200:
                    file.message = f'HTTP {code}; sitemap contents unverified.'
                    continue
                if 'gzip' in headers.get('content-type','') and not content.lstrip().startswith('<'):
                    file.message = 'Compressed response did not yield readable sitemap XML.'
                    continue
                kind, urls, warnings = parse_sitemap(content)
                file.kind, file.entries = kind, len(urls)
                invalid = any('Duplicate' not in w for w in warnings)
                if kind == 'index':
                    graph[url] = urls
                    nested.update(urls)
                    for child in urls:
                        if url in trusted and urlsplit(url).hostname == urlsplit(child).hostname:
                            trusted.add(child)
                        if child not in scheduled:
                            scheduled.add(child)
                            queue.append(child)
                else:
                    for item in urls:
                        host = urlsplit(item).hostname
                        if host == hostname: discovered.add(item)
                        else: external[host] += 1
                    other = sorted({urlsplit(u).hostname for u in urls} - {hostname})
                    if urlsplit(final).hostname != hostname and url not in trusted:
                        warnings.append('Cross-site sitemap lacks a verified robots declaration from the audited host.')
                    if other: warnings.append('Outside-scope hosts: '+', '.join(other)+'. Cross-site ownership needs confirmation from the listed hosts.')
                file.status = 'error' if invalid else 'warning' if warnings else 'passed'
                file.message = ' '.join(warnings) or f'Valid {kind} with {len(urls)} entries.'
            except ValueError as exc:
                file.message = str(exc)
                file.status = 'unknown' if any(t in str(exc).lower() for t in ('limit','permission','disallowed','resolved','redirect loop')) else 'error'
            except (httpx.HTTPError,TimeoutError):
                file.message = 'Request timed out or the file was inaccessible.'
        if queue: report.warnings.append(f'{len(queue)} file(s) remain after the {report.file_limit}-file inspection limit.')
        def cycle(url, ancestors):
            if url in ancestors: return True
            if url in finished: return False
            finished.add(url)
            return any(cycle(child, ancestors | {url}) for child in graph.get(url,[]) if child in graph)
        finished = set()
        if any(cycle(root,set()) for root in graph): report.warnings.append('A sitemap index cycle was detected.')
        missed_probes = [f for f in report.files if not roots and f.status_code in (404,410) and f.url not in nested]
        applicable = [f for f in report.files if f not in missed_probes]
        report.complete = bool(discovered) and not report.warnings and all(f.status == 'passed' for f in applicable)
        reasons = [f'{f.url}: {f.message}' for f in applicable if f.status != 'passed']
        if report.warnings or any(f.status=='unknown' for f in applicable): report.status = 'unknown'
        elif any(f.status=='error' for f in applicable): report.status = 'error'
        elif report.complete: report.status = 'passed'
        elif not applicable: report.status = 'warning'
        else: report.status = 'unknown'
        report.summary = f'{len(discovered)} unique in-scope URLs. ' + ('All discovered files checked.' if report.complete else
            ' '.join(report.warnings + reasons[:2]) or 'No sitemap found at the checked locations.')
    finally:
        report.nested, report.pending = len(nested), len(queue)
        report.successful = sum(f.status=='passed' for f in report.files)
        report.failed = sum(f.status=='error' for f in report.files)
        report.urls_discovered, report.url_sample = len(discovered), sorted(discovered)[:50]
        report.external_hosts = dict(external)
        compare_sitemap(report,pages,discovered,config)
    return report


async def audit_site(website, pages, config: Settings, budget: float, request=None) -> SiteChecks:
    request = request or safe_request
    origin = urlunsplit((*urlsplit(website)[:2], '', '', ''))
    result = SiteChecks(social=summarize_social(pages), robots_txt=RobotsAudit(url=origin + '/robots.txt'))

    async def work():
        async with httpx.AsyncClient(timeout=config.request_timeout_seconds, trust_env=False, headers={'User-Agent': 'CrawlensBot/1.0'}) as client:
            policy = None
            result.sitemap.file_limit = config.sitemap_file_limit
            try:
                code, _, content, _ = await request(client, 'GET', result.robots_txt.url, read_body=True, max_bytes=500_000)
                result.robots_txt = analyze_robots(result.robots_txt.url, code, content, [website] + [page.url for page in pages], config)
                if 200 <= code < 300 and result.robots_txt.status != 'error':
                    policy = RobotsPolicy(content)
            except (httpx.HTTPError, ValueError, TimeoutError):
                result.robots_txt.summary = 'robots.txt could not be retrieved within the request or size limits.'
            if result.robots_txt.status == 'unknown' or result.robots_txt.status == 'error':
                result.sitemap.summary = 'Sitemap requests were skipped because a reliable robots policy could not be established.'
            else:
                result.sitemap = await inspect_sitemaps(website, result.robots_txt, pages, client, request, result.sitemap, policy, config)
    try:
        await asyncio.wait_for(work(), timeout=max(0.1, min(budget, 30)))
    except TimeoutError:
        result.sitemap.status = 'unknown'
        result.sitemap.complete = False
        result.sitemap.summary = 'Sitemap inspection did not finish within the time limit. Completed file evidence is preserved; coverage is incomplete.'
        result.sitemap.warnings.append('The site-file time budget was reached; coverage is incomplete.')
    return result


async def inspect_llms(website, config, network, budget):
    url = urlunsplit((*urlsplit(website)[:2],'/llms.txt','',''))
    result = {'url':url,'status':'Review','summary':'Optional file could not be inspected.'}
    try:
        async with httpx.AsyncClient(timeout=config.request_timeout_seconds,trust_env=False,headers={'User-Agent':'CrawlensBot/1.0'}) as client:
            code, headers, body, final = await asyncio.wait_for(network.request(client,'GET',url,read_body=True,max_bytes=100_000),budget)
        result.update(http_status=code,final_url=final)
        if code in (404,410):
            result.update(status='N/A',summary='Optional llms.txt is absent.')
        elif code==200 and body.strip() and not re.search(r'<(?:html|!doctype)',body,re.I):
            heading = re.search(r'^# (.+)',body,re.M)
            result.update(status='Passed' if heading else 'Warning',summary='Readable Markdown with a title.' if heading else 'Readable text without a Markdown title.',preview=body[:1500])
        else: result['summary'] = f'HTTP {code}; no readable llms.txt verified.'
    except (ValueError,httpx.HTTPError,TimeoutError): pass
    return result


def site_issues(checks: SiteChecks, website: str) -> list[Issue]:
    issues = []
    robots = checks.robots_txt
    blocked = [item for item in robots.permissions if item.agent == 'Googlebot' and not item.allowed]
    if robots.status == 'error' or blocked:
        issues.append(Issue(id='site_robots', metric='robots_txt', severity='high', page_url=website, target_url=robots.url,
                            outcome='Failed' if robots.status=='error' else 'Review', title='Review search crawler access', observed=robots.summary,
                            expected='An accessible robots policy with intentional crawl permissions.',
                            suggested_action='Review the matched Disallow rules and allow important public pages where appropriate. Robots.txt controls crawling, not removal from search.'))
    elif robots.status == 'warning' and robots.status_code in (404, 410):
        issues.append(Issue(id='site_robots', metric='robots_txt', severity='low', page_url=website, target_url=robots.url,
                            outcome='Warning', title='Consider an explicit robots policy', observed=robots.summary,
                            expected='An intentional crawl policy and sitemap declaration where needed.',
                            suggested_action='If your site needs crawl restrictions, publish robots.txt at the origin root and include an absolute Sitemap URL. A missing file is not an indexing failure.'))
    elif robots.warnings:
        issues.append(Issue(id='site_robots',metric='robots_txt',severity='low',outcome='Warning',page_url=website,target_url=robots.url,
                            title='Review robots.txt syntax',observed=' '.join(robots.warnings),expected='Recognizable directives in applicable user-agent groups.',
                            suggested_action='Correct the indicated lines, then recheck the crawler permissions.',evidence={'warnings':robots.warnings}))
    sitemap = checks.sitemap
    if sitemap.status in ('error', 'warning') or sitemap.files and sitemap.status == 'unknown':
        issues.append(Issue(id='site_sitemap', metric='sitemap', severity='high' if sitemap.status == 'error' else 'medium', page_url=website,
                            target_url=next((f.url for f in sitemap.files if f.status!='passed'),None), title='Review sitemap discovery',
                            outcome='Failed' if sitemap.status=='error' else 'Review' if sitemap.status=='unknown' else 'Warning', evidence={'files':[f.model_dump() for f in sitemap.files if f.status!='passed']}, observed=sitemap.summary, expected='An accessible, valid sitemap or sitemap index for important canonical URLs.',
                            suggested_action=('Correct the listed XML or HTTP errors and recheck the affected files.' if sitemap.status=='error' else
                                'Inspect the outstanding indexes and confirm ownership for external sitemap hosts. Recheck coverage before changing published URLs.' if sitemap.status=='unknown' else
                                'Locate the intended sitemap and declare its absolute URL in robots.txt.')))
    from backend.app.services.issue_builder import IMPACT
    for issue in issues: issue.impact = IMPACT[issue.metric]
    return issues
