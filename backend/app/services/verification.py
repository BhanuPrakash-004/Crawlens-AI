"""Bounded, robots-aware verification shared by page, link, and site checks."""
import asyncio
import time
import ssl
import re
from urllib.parse import urlsplit, urlunsplit
import httpx
from bs4 import BeautifulSoup
from backend.app.services.url_safety import safe_request, normalize_url, RESTRICTED_CODES, is_bot_challenge
from backend.app.services.robots_policy import RobotsPolicy


def origin(url):
    p=urlsplit(url)
    return urlunsplit((p.scheme,p.netloc,'','',''))


class VerifiedNetwork:
    def __init__(self):
        self.robots, self.policies, self.locks, self.gates, self.last, self.traces, self.cache = {},{},{},{},{},{},{}

    async def cached_hop(self, url, method, body, limit, sitemap, fetch):
        key = (url, method, body, limit if body else 0, sitemap)
        async with self.locks.setdefault(('request', url), asyncio.Lock()):
            if key in self.cache:
                return self.cache[key]
            if not body and (url, 'verified') in self.cache:
                return self.cache[url, 'verified']
            response = await fetch(url)
            if response[0] not in (408, 429, 500, 502, 503, 504):
                self.cache[key] = response
                if method == 'GET':
                    self.cache[url, 'verified'] = (response[0], response[1], '', response[3])
            return response

    async def wait(self,url):
        key=origin(url)
        async with self.gates.setdefault(key,asyncio.Lock()):
            policy=self.policies.get(key)
            delay=policy.crawl_delay() if policy else 0
            await asyncio.sleep(max(0,self.last.get(key,0)+delay-time.monotonic()))
            self.last[key]=time.monotonic()

    async def get_robots(self,client,url):
        key=origin(url)
        async with self.locks.setdefault(key,asyncio.Lock()):
            if key not in self.robots:
                response=await safe_request(client,'GET',key+'/robots.txt',read_body=True,max_bytes=500_000,before_request=self.wait)
                self.robots[key]=response
                code,_,body,_=response
                self.policies[key]=RobotsPolicy(body) if 200<=code<300 and not re.search(r'<(?:html|!doctype)',body,re.I) else RobotsPolicy('') if code in (404,410) else None
        return self.robots[key]

    async def request(self,client,method,url,**kwargs):
        if urlsplit(url).path=='/robots.txt': return await self.get_robots(client,url)
        await self.get_robots(client,url)
        policy=self.policies.get(origin(url))
        if policy is None: raise ValueError('Crawl permissions could not be verified.')
        if not policy.permission('CrawlensBot',url)[0]: raise ValueError('Disallowed by robots.txt for CrawlensBot.')
        async def before(hop):
            if hop != url:
                await self.get_robots(client, hop)
                hop_policy = self.policies.get(origin(hop))
                if not hop_policy or not hop_policy.permission('CrawlensBot', hop)[0]:
                    raise ValueError('Redirect destination blocked or its crawl policy is unknown.')
            await self.wait(hop)
        trace = []
        response = await safe_request(client, method, url, **kwargs, before_request=before, trace=trace, registry=self.cached_hop)
        self.traces[url] = trace
        return response


async def verify_pages(crawl,config,network,budget):
    async def work():
        async with httpx.AsyncClient(timeout=config.request_timeout_seconds,trust_env=False,headers={'User-Agent':'CrawlensBot/1.0'}) as client:
            for page in crawl.pages:
                try:
                    original_url=page.url
                    code,headers,html,final=await network.request(client,'GET',page.url,read_body=True,max_bytes=config.max_html_bytes)
                    if (code in RESTRICTED_CODES or is_bot_challenge(code, html)) and page.status_code == 200:
                        # Bot protection refused our direct request, but the crawler did receive the page. Keep the
                        # crawler's evidence; the refusal page's status and headers say nothing about the real page.
                        page.source_notes.append(f'Direct verification was refused (HTTP {code}); crawler evidence retained and response headers are unverified.')
                        continue
                    if urlsplit(final).hostname!=urlsplit(page.url).hostname:
                        page.source_notes.append('Direct verification redirected outside the selected hostname; original crawler evidence retained.')
                        continue
                    page.headers=headers
                    page.url=normalize_url(final)
                    if 'html' in headers.get('content-type','').lower() and code == 200:
                        page.raw_html=html
                    page.redirect_chain=network.traces.get(original_url,[])
                    if page.status_code!=code:
                        page.source_notes.append(f'Crawler reported HTTP {page.status_code}; direct verification returned HTTP {code}.')
                    page.status_code=code
                    rendered,raw=BeautifulSoup(page.html,'html.parser'),BeautifulSoup(html,'html.parser')
                    body=rendered.body
                    incomplete=not body or (len(body.get_text(' ',strip=True))<80 and not body.find('a',href=True) and not body.find('h1'))
                    if incomplete and raw.body and (len(raw.body.get_text(' ',strip=True))>=80 or raw.body.find('h1') or raw.body.find('a',href=True)) and 'html' in headers.get('content-type','').lower():
                        page.html=html
                        page.source_kind='http_full_html_fallback'
                        page.source_notes.append('Crawler body was missing or near-empty. Complete direct HTML was used; JavaScript-only content may remain unverified.')
                    elif incomplete:
                        page.source_notes.append('Incomplete HTML body; body-dependent checks are unknown, not failed.')
                        page.source_kind='incomplete_html'
                except (ValueError,httpx.HTTPError,TimeoutError):
                    page.source_notes.append('Direct HTML/header verification was unavailable; crawler evidence retained.')
    try: await asyncio.wait_for(work(),max(.1,budget))
    except TimeoutError: crawl.warnings.append('Direct page verification reached its time budget; remaining headers/source completeness are unverified.')


async def verify_indexability(pages,checks,config,network,budget):
    indexed = {page.url:page for page in pages}
    for page in pages:
        access = page.checks['indexability']
        policy = network.policies.get(origin(page.url))
        permissions = {agent:policy.permission(agent,page.url)[0] if policy else None for agent in config.search_crawlers}
        access.details['permissions'] = permissions
        allowed = all(permissions.values()) if policy else None
        access.details['robots_allowed'] = allowed
        excluded = bool(set(urlsplit(page.url).path.lower().split('/')) & set(config.excluded_path_segments))
        access.details['not_applicable'] = excluded
        if page.url in config.required_index_urls and (access.details['noindex'] or allowed is False):
            access.passed = False
            access.details.update(review_required=False, not_applicable=False)
            access.observed += ' This URL is configured as required for search indexing.'
        elif excluded:
            access.passed = None
            access.details['review_required'] = False
            access.observed += ' Outside the configured search landing-page scope.'
        elif page.status_code in RESTRICTED_CODES or access.details['noindex'] or allowed is False:
            access.passed = None
            access.details['review_required'] = True
            access.observed += ' Restricted access or an explicit exclusion. Verify indexing intent.'
        elif page.status_code == 200:
            access.passed = True if allowed is True and page.headers_available else None
        access.observed = access.observed.replace(' Crawler policy pending.', '')
        access.observed += ' ' + ', '.join(f'{agent}: ' + ('unverified' if value is None else 'allowed' if value else 'blocked') for agent,value in permissions.items()) + '.'
        geo = page.checks['geo']
        agents = {agent:policy.permission(agent,page.url)[0] if policy else None for agent in config.ai_crawlers}
        geo.details['permissions'] = agents
        if excluded:
            geo.details['not_applicable'] = True
        elif policy and page.source_kind != 'incomplete_html' and page.status_code == 200 and not page.checks['headings'].details.get('unavailable'):
            geo.passed = bool(all(agents.values()) and geo.details['word_count'] and any(page.checks['headings'].details['h1']))
        geo.observed = f"{geo.details['word_count']} extractable words. " + ', '.join(f'{k}: ' + ('unknown' if v is None else 'allowed' if v else 'blocked') for k,v in agents.items())
    async def inspect(page, client):
        check = page.checks['canonical']
        d = check.details
        if d['status'] != 'declared' or page.status_code != 200: return
        target = d['targets'][0]
        if urlsplit(target).hostname != urlsplit(page.url).hostname:
            d['status'] = 'external'
        else:
            try:
                code, headers, body, final = await network.request(client,'GET',target,read_body=True,max_bytes=config.max_html_bytes)
                d.update(status_code=code, final_url=final, redirect_chain=network.traces.get(target,[]))
                policy = network.policies.get(origin(target))
                if code in RESTRICTED_CODES or is_bot_challenge(code, body): d['status'] = 'restricted'
                elif code >= 400: d['status'] = 'broken'
                elif normalize_url(final) != target: d['status'] = 'redirecting'
                elif code == 200:
                    # Respect scoped indexing directives using the same parser as crawled pages.
                    from backend.app.services.html_extractor import indexability_check
                    from backend.app.schemas import CrawlPage
                    target_access = indexed[target].checks['indexability'] if target in indexed else indexability_check(
                        BeautifulSoup(body, 'html.parser'), CrawlPage(url=target,html=body,headers=headers,status_code=code), config)
                    if target_access.details['noindex'] or policy and any(not policy.permission(agent,target)[0] for agent in config.search_crawlers):
                        d['status'] = 'blocked'
                    else:
                        d['status'] = 'valid' if policy and ('html' in headers.get('content-type','').lower() or target in indexed) else 'unknown'
                else: d['status'] = 'unknown'
            except (ValueError,httpx.HTTPError,TimeoutError):
                d['status'] = 'unknown'
        check.passed = True if d['status'] == 'valid' else False if d['status'] in ('broken','blocked') else None
        d['review_required'] = check.passed is None
        if d['status']=='redirecting': d['warnings']=['Canonical target redirects. Prefer its final destination.']
        check.observed = f"Canonical {target}: {d['status']}" + (f" (HTTP {d['status_code']})." if 'status_code' in d else '.')
        page.checks['indexability'].details['canonical'] = dict(d)
    async with httpx.AsyncClient(timeout=config.request_timeout_seconds,trust_env=False,headers={'User-Agent':'CrawlensBot/1.0'}) as client:
        try:
            await asyncio.wait_for(asyncio.gather(*(inspect(page,client) for page in pages)),max(.1,budget))
        except TimeoutError:
            for page in pages:
                check = page.checks['canonical']
                if check.details['status']=='declared':
                    check.details.update(status='unknown',review_required=True)
                    check.observed += ' Target verification exceeded the time budget.'

    for page in pages:
        geo = page.checks['geo']
        schema = page.checks['structured_data']
        geo.details.update(
            canonical_access=page.checks['canonical'].details['status'],
            structured_data_status='Verified' if schema.passed else 'Invalid' if schema.passed is False else 'Unmeasured',
            product_information_review=schema.details.get('suggestions', []),
            has_product_description=bool(geo.details.get('product_description')),
        )


def deduplicate_pages(pages):
    # A rendered final URL and a redirecting crawl entry can refer to the same document.
    unique, aliases = {}, {}
    for page in pages:
        key = normalize_url(page.url)
        sources = aliases.setdefault(key, {})
        for hop in page.redirect_chain:
            sources[hop['url']] = hop
        if key not in unique or unique[key].source_kind == 'incomplete_html':
            unique[key] = page
    for key, page in unique.items():
        page.redirect_aliases = sorted(url for url in aliases[key] if url != key)
    return list(unique.values())


async def verify_media(pages, config, network, budget):
    from backend.app.services.link_checker import verify_link
    from backend.app.services.page_evidence import update_media
    destinations = {}
    for page in pages:
        check = page.checks['media']
        if page.source_kind == 'incomplete_html' or page.status_code != 200: continue
        for row in check.details['resources']:
            if row.get('tracking_pixel_candidate'): continue  # Not a content image; no request needed.
            for url in dict.fromkeys([row['url'], row.get('poster'), *row.get('captions',[]), *row.get('sources',[])]):
                if url and urlsplit(url).hostname in {urlsplit(page.url).hostname, *config.media_hosts}:
                    destinations.setdefault(url,[]).append(row)
                elif url: row.setdefault('unchecked',[]).append(url)
    sem = asyncio.Semaphore(config.link_concurrency)
    async with httpx.AsyncClient(timeout=config.request_timeout_seconds,trust_env=False,headers={'User-Agent':'CrawlensBot/1.0'}) as client:
        async def inspect(url):
            async with sem:
                result = await verify_link(client,url,[],network.request)
                headers = network.cache.get((url,'HEAD',False,0,False),network.cache.get((url,'verified'),(0,{})))[1]
                for row in destinations[url]:
                    row.setdefault('requests',{})[url] = {'status':result.status,'http':result.status_code,'reason':result.reason,
                                                          'bytes':headers.get('content-length'),'content_type':headers.get('content-type')}
                    if row['url']==url: row['resource_status'] = result.status
                    if result.status=='broken': row['failures'].append(f'{url} returned HTTP {result.status_code}.')
                    if result.status=='unknown': row.setdefault('availability',[]).append(f'{url}: {result.reason}')
        try:
            await asyncio.wait_for(asyncio.gather(*(inspect(u) for u in list(destinations)[:config.media_check_limit])),max(.1,budget))
        except TimeoutError: pass
    for page in pages:
        if page.source_kind != 'incomplete_html' and page.status_code == 200:
            check = page.checks['media']
            for row in check.details['resources']:
                for url in set([row.get('poster'), *row.get('sources',[]), *row.get('captions',[])]) - {None}:
                    if url not in row.get('requests',{}): row.setdefault('availability',[]).append(f'{url}: outside verification scope or budget.')
            if not check.details.get('unavailable'): update_media(check)


async def verify_https(website,config,network):
    host=urlsplit(website).netloc
    result={'status':'unknown','summary':'HTTPS and upgrade redirect could not be fully verified.'}
    try:
        async with httpx.AsyncClient(timeout=config.request_timeout_seconds,trust_env=False,headers={'User-Agent':'CrawlensBot/1.0'}) as client:
            secure='https://'+host+'/'
            code,_,_,final=await network.request(client,'HEAD',secure)
            if code in (403,405,501): code,_,_,final=await network.request(client,'GET',secure)
            result.update(https_status=code,https_final_url=final,certificate_valid=True)
            plain='http://'+host+'/'
            http_code,_,_,http_final=await network.request(client,'HEAD',plain)
            if http_code in (403,405,501): http_code,_,_,http_final=await network.request(client,'GET',plain)
            chain=network.traces.get(plain,[])
            upgrade=bool(chain and chain[0]['status_code'] in (301,302,303,307,308) and urlsplit(http_final).scheme=='https')
            result.update(http_status=http_code,http_final_url=http_final,redirect_chain=chain,http_to_https=upgrade,status='passed' if code==200 and urlsplit(final).scheme=='https' and upgrade else 'warning',summary='Valid TLS access and HTTP-to-HTTPS redirect verified.' if upgrade and code==200 else 'Review secure access or the HTTP-to-HTTPS redirect.')
    except (ValueError,httpx.HTTPError,TimeoutError) as exc:
        cause = exc
        while cause is not None and not isinstance(cause,ssl.SSLCertVerificationError):
            cause = cause.__cause__
        if cause is not None:
            result.update(status='error',certificate_valid=False,summary='TLS certificate validation failed: '+str(cause.verify_message))
        else:
            result['summary']='Secure transport verification was incomplete ('+type(exc).__name__+').'
    return result
