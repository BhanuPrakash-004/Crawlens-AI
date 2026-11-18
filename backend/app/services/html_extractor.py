import json
import re
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
from backend.app.config import settings
from backend.app.services.page_evidence import headings, media_check, resolve, page_content
from backend.app.schemas import Check, CrawlPage, PageAnalysis
from backend.app.services.url_safety import normalize_url
from backend.app.services.social_links import extract_social_profiles

VALUED_DIRECTIVES = {'max-snippet', 'max-image-preview', 'max-video-preview', 'unavailable_after'}


def visible_text(value) -> str:
    """Collapse whitespace the way browsers and search snippets display it, so lengths match what people see."""
    return ' '.join(str(value).split())


def metadata_check(soup: BeautifulSoup, config=settings) -> Check:
    titles = soup.find_all('title')
    descriptions = soup.find_all('meta', attrs={'name': re.compile('^description$', re.I)})
    title = visible_text(titles[0].get_text()) if titles else ''
    meta = descriptions[0] if descriptions else None
    description = visible_text(meta.get('content', '')) if meta else ''
    title_pass = config.title_min <= len(title) <= config.title_max
    description_pass = config.description_min <= len(description) <= config.description_max
    return Check(passed=title_pass and description_pass and len(titles)==1 and len(descriptions)==1,
                 observed=f'Title: {len(title)} characters ({len(titles)} tags); description: {len(description)} characters ({len(descriptions)} tags).',
                 expected=f'One title of {config.title_min}–{config.title_max} characters and one description of {config.description_min}–{config.description_max} characters (project limits).',
                 details={'title': title, 'description': description, 'title_length': len(title), 'description_length': len(description), 'title_pass': title_pass, 'description_pass': description_pass,
                          'title_present': bool(titles), 'description_present': bool(descriptions), 'title_count': len(titles), 'description_count': len(descriptions),
                          'all_titles':[visible_text(t.get_text()) for t in titles], 'all_descriptions':[visible_text(t.get('content','')) for t in descriptions]})


def indexability_check(soup: BeautifulSoup, page: CrawlPage, config=settings) -> Check:
    directives = []
    for meta in soup.find_all('meta'):
        if str(meta.get('name', '')).lower() in {'robots', *(a.lower() for a in config.search_crawlers)}:
            directives.append(str(meta.get('content', '')).lower())
    headers = {k.lower(): v.lower() for k, v in (page.headers or {}).items()}
    # A bot-scoped header ("googlebot: noindex") applies only to that agent; unscoped directives apply to all.
    # Some directives also contain a colon ("max-image-preview:large") and must not be read as an agent name.
    current_agent = None
    for item in headers.get('x-robots-tag', '').split(','):
        name, colon, rest = item.partition(':')
        name = name.strip()
        if colon and name not in VALUED_DIRECTIVES and re.fullmatch(r'[\w-]+', name):
            current_agent, item = name, rest
        if current_agent in {None, '*', *(a.lower() for a in config.search_crawlers)}:
            directives.append(item.strip())
    blocked = any(re.search(r'\b(noindex|none)\b', directive) for directive in directives)
    canonical = canonical_evidence(soup, page)
    passed = None if blocked else False if page.status_code is not None and page.status_code != 200 else True if page.status_code == 200 and page.headers is not None else None
    return Check(passed=passed, observed=f'HTTP {page.status_code or "unknown"}; ' + ('noindex detected.' if blocked else 'no noindex detected.'),
                 expected='HTTP 200 with verified crawl access and indexing directives for intended search landing pages.',
                 details={'directives': directives, 'noindex': blocked, 'headers_checked': page.headers is not None, 'partial': page.headers is None, 'review_required':blocked, 'canonical':canonical})


def canonical_evidence(soup, page):
    raw = [str(tag.get('href','')).strip() for tag in soup.find_all('link', rel=lambda value: value and 'canonical' in (value.lower().split() if isinstance(value,str) else value))]
    headers = {k.lower():v for k,v in (page.headers or {}).items()}
    raw += re.findall(r'<([^>]*)>\s*;\s*rel\s*=\s*[\"\']?canonical\b', headers.get('link',''), re.I)
    targets, invalid = [], []
    base = soup.find('base',href=True)
    for value in raw:
        try:
            if not value or value.startswith('#'): raise ValueError()
            targets.append(normalize_url(urljoin(urljoin(page.url,base['href']) if base else page.url,value)))
        except ValueError: invalid.append(value)
    targets = list(dict.fromkeys(targets))
    return {'raw_targets':raw, 'targets':targets, 'invalid':invalid,
            'status':'invalid' if invalid else 'conflicting' if len(targets)>1 else 'declared' if targets else 'missing',
            'note':'A missing self-canonical is contextual and does not fail this check.' if not raw else 'Declared targets require network verification.'}


def schema_context(value) -> bool:
    if isinstance(value, str):
        return value.rstrip('/') in ('https://schema.org', 'http://schema.org')
    if isinstance(value, list):
        return any(schema_context(item) for item in value)
    return isinstance(value, dict) and schema_context(value.get('@vocab'))


def structured_data_check(soup: BeautifulSoup) -> Check:
    types, nodes, subjects, malformed = [], [], [], 0

    def inspect(node, inherited=False, subject=True):
        if isinstance(node, list):
            for item in node:
                inspect(item, inherited, subject)
        elif isinstance(node, dict):
            context = schema_context(node['@context']) if '@context' in node else inherited
            value = node.get('@type', [])
            values = value if isinstance(value, list) else [value]
            if context:
                types.extend(t.strip() for t in values if isinstance(t, str) and t.strip())
                nodes.append(node)
                if subject: subjects.append(node)
            for key, child in node.items():
                if key != '@context' and isinstance(child, (dict, list)):
                    inspect(child, context, subject and key in ('@graph','mainEntity'))

    scripts = soup.find_all('script', attrs={'type': re.compile(r'^application/ld\+json$', re.I)})
    for script in scripts:
        try:
            data = json.loads(script.string or script.get_text(), parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
            if not isinstance(data, (dict,list)): raise ValueError('Expected object or array')
            inspect(data)
        except (ValueError, RecursionError):
            malformed += 1
    products = [node for node in subjects if 'Product' in (node.get('@type') if isinstance(node.get('@type'),list) else [node.get('@type')])]
    product_hint = soup.find('meta', attrs={'property':re.compile('^og:type$',re.I), 'content':re.compile('^(product|og:product)$',re.I)}) is not None
    product_hint = product_hint or bool(soup.find(attrs={'itemtype':re.compile(r'^https?://schema\.org/Product/?$')}))
    by_id = {node['@id']:node for node in nodes if isinstance(node.get('@id'),str) and node.get('@type')}
    errors = []
    reviews = []
    def number(value, minimum=0):
        try:
            from math import isfinite
            return not isinstance(value,bool) and isfinite(float(value)) and float(value)>=minimum
        except (ValueError,TypeError): return False
    for index, product in enumerate(products):
        prefix = f'Product {index+1}: '
        if not isinstance(product.get('name'),str) or not product['name'].strip(): errors.append(prefix+'missing name')
        if not any(product.get(key) for key in ('offers','review','aggregateRating')): errors.append(prefix+'requires offers, review, or aggregateRating')
        for key in ('offers','review','aggregateRating'):
            values = product.get(key, [])
            for value in values if isinstance(values,list) else [values]:
                if not isinstance(value,dict): errors.append(prefix+f'invalid {key} object'); continue
                if '@id' in value and len(value)==1:
                    linked = by_id.get(value['@id']) if isinstance(value['@id'],str) else None
                    if not linked:
                        reviews.append(f'{prefix}{key} reference could not be resolved in the page graph.')
                        continue
                    value = linked
                if key=='offers':
                    price = value.get('lowPrice') if value.get('@type')=='AggregateOffer' else value.get('price')
                    if not number(price) or not re.fullmatch('[A-Z]{3}', str(value.get('priceCurrency',''))): errors.append(prefix+'offer requires a nonnegative price and three-letter priceCurrency')
                elif key=='aggregateRating':
                    if not number(value.get('ratingValue')) or not number(value.get('ratingCount',value.get('reviewCount')),1): errors.append(prefix+'aggregateRating requires ratingValue and a positive ratingCount/reviewCount')
                else:
                    author=value.get('author',{})
                    if not isinstance(author,dict) or not author.get('name') or not isinstance(value.get('reviewRating'),dict) or not number(value['reviewRating'].get('ratingValue')): errors.append(prefix+'review requires author.name and reviewRating.ratingValue')
    suggestions = []
    visible = page_content(soup).casefold()
    for product in products:
        if isinstance(product.get('name'), str) and product['name'].strip().casefold() not in visible:
            suggestions.append('Product name could not be matched to visible page text.')
        if not product.get('image'): suggestions.append('Consider a representative Product image.')
    subject_types = set()
    for node in subjects:
        kinds = node.get('@type', [])
        kinds = kinds if isinstance(kinds, list) else [kinds]
        subject_types.update(kind for kind in kinds if isinstance(kind,str))
        if 'AggregateRating' in kinds and (not number(node.get('ratingValue')) or not number(node.get('ratingCount',node.get('reviewCount')),1)):
            errors.append('AggregateRating requires a rating value and a positive count.')
        if 'Review' in kinds and (not isinstance(node.get('reviewRating'), dict) or not number(node['reviewRating'].get('ratingValue')) or not node.get('author')):
            errors.append('Review requires an author and a review rating.')
        if 'BreadcrumbList' in kinds:
            items = node.get('itemListElement')
            if not isinstance(items, list) or not items or any(not isinstance(item, dict) or not (item.get('name') or isinstance(item.get('item'),dict) and item['item'].get('name')) or not number(item.get('position'),1) for item in items):
                errors.append('BreadcrumbList requires named list items with positive positions.')
        if 'Organization' in kinds and not node.get('name'): errors.append('Organization has no name.')
        if 'Offer' in kinds and (not number(node.get('price')) or not re.fullmatch('[A-Z]{3}', str(node.get('priceCurrency','')))):
            errors.append('Offer requires price and priceCurrency.')
    eligible = bool(products) or product_hint or bool(subject_types & {'BreadcrumbList','Organization','Offer','Review','AggregateRating'})
    if product_hint and not products: errors.append('Product page has no supported Schema.org Product JSON-LD.')
    passed = False if malformed or errors else None if reviews else True if eligible else None
    primary_ids = {id(product) for product in products}
    return Check(passed=passed, observed=f'{len(scripts)} JSON-LD block(s); {len(products)} primary Product object(s); {malformed} malformed.' + (' ' + '; '.join(dict.fromkeys(errors + reviews)) if errors or reviews else ' Not applicable: no supported product-page evidence.' if not eligible else ''),
                 expected='Valid JSON-LD and applicable fields for supported entities. Product pages need a name and offers, review or aggregateRating.',
                 details={'types':sorted(set(types)), 'malformed':malformed, 'blocks':len(scripts), 'eligible':eligible, 'primary_products':len(products), 'nested_products':sum(node.get('@type')=='Product' for node in nodes if id(node) not in primary_ids), 'not_applicable':not eligible and not malformed, 'validation_errors':list(dict.fromkeys(errors)), 'review_required':bool(reviews), 'suggestions':suggestions, 'review_reasons':reviews})


def inspect_html_rule(name, inspect, defaults):
    try:
        return inspect()
    except (ValueError, TypeError, RecursionError, KeyError, AttributeError, OverflowError):
        return Check(passed=None, observed=f'{name} analysis could not interpret the returned HTML.',
                     expected='A complete observation from this page.', details={**defaults,'unavailable':True})


def analyze_page(page: CrawlPage, hostname: str, config=settings) -> PageAnalysis:
    soup = BeautifulSoup(page.html, 'html5lib')
    base_tag = soup.find('base', href=True)
    base = (resolve(page.url, base_tag['href']) if base_tag else None) or page.url
    references = []
    for anchor in soup.find_all('a', href=True):
        href = str(anchor['href']).strip()
        url = resolve(base, href)
        if url and not href.startswith('#') and urlsplit(url).hostname == hostname:
            image = anchor.find('img', alt=True)
            name = anchor.get('aria-label') or anchor.get_text(' ', strip=True) or (image and image['alt']) or anchor.get('title','')
            references.append({'page_url': page.url, 'href': href, 'url': url, 'text': name})
    indexability = indexability_check(soup, page, config)
    if indexability.passed is True:
        indexability.passed = None
        indexability.observed += ' Crawler policy pending.'
    canonical = indexability.details['canonical']
    checks = {'metadata': inspect_html_rule('Metadata',lambda:metadata_check(soup,config),{'title':'','description':''}), 'indexability': indexability,
              'headings': inspect_html_rule('Heading',lambda:headings(soup,page),{'headings':[],'h1':[],'skipped_levels':False}),
              'structured_data': inspect_html_rule('Structured data',lambda:structured_data_check(soup),{'types':[],'malformed':None}),
              'canonical': Check(passed=False if canonical['status'] in ('invalid','conflicting') else None,
                                 observed=f"Canonical declaration: {canonical['status']}.",
                                 expected='Consistent, accessible, indexable preferred URL.', details=canonical),
              'media': inspect_html_rule('Media',lambda:media_check(soup,base),{'resources':[]}),
              'performance': Check(passed=None, observed='No URL-level performance measurement available.',
                                   expected=f'LCP ≤ {config.lcp_ms:g} ms, INP ≤ {config.inp_ms:g} ms, CLS ≤ {config.cls_limit:g}.',
                                   details={'snapshot_html_bytes':len(page.html.encode()), 'raw_html_bytes':len(page.raw_html.encode()) if page.raw_html is not None else None, 'vitals':{}}),
              'geo': Check(passed=None, observed='Crawler permissions pending.', expected='Extractable main text, a descriptive heading and accessible content for configured AI crawlers.',
                           details={'agents':config.ai_crawlers})}
    if canonical['status']=='missing':
        checks['canonical'].details.update(review_required=True, optional=True)
    words = re.findall(r"\w+", page_content(soup).casefold())
    content = {'word_count': len(words), 'specification_tables':len(soup.find_all(['table','dl'])),
               'question_headings':sum(h['text'].rstrip().endswith('?') for h in checks['headings'].details['headings']),
               'product_description':checks['metadata'].details['description'], 'schema_types':checks['structured_data'].details['types'],
               'url_path':urlsplit(page.url).path, 'url_query':urlsplit(page.url).query}
    checks['geo'].details.update(content)
    checks['headings'].details['content'] = content
    if len(words) < config.thin_word_limit: content['editorial_review'] = 'Short main text. Review topic coverage against page purpose.'
    title = checks['metadata'].details['title']
    if title.strip().lower() in ('untitled','home page','document','new page'):
        checks['metadata'].details['warnings']=['Generic title text. Review topic relevance.']
    content['numeric_url_segments'] = [segment for segment in urlsplit(page.url).path.split('/') if segment.isdigit()]
    content['topic_terms_in_heading'] = sorted(set(re.findall(r'\w+', title.casefold())) & set(re.findall(r'\w+', ' '.join(checks['headings'].details['h1']).casefold())))
    checks['geo'].details.update(content)
    if page.source_kind == 'incomplete_html':
        for key in ('headings','structured_data','media','geo'):
            checks[key].passed=None
            checks[key].details.update(not_applicable=False, review_required=True, warnings=[])
            checks[key].observed='Incomplete HTML body; this check could not be verified.'
    if page.status_code is not None and page.status_code != 200:
        for key, check in checks.items():
            if key != 'indexability':
                check.passed = None
                check.details.update(review_required=False, not_applicable=False, warnings=[])
                check.observed = f'HTTP {page.status_code}; the intended page content could not be verified.'
    diagnostics = list(page.source_notes)
    if page.headers is None:
        diagnostics.append('X-Robots-Tag headers unavailable; indexability is partially checked.')
    if checks['headings'].details['skipped_levels']:
        diagnostics.append('Skipped heading levels detected; this diagnostic does not affect the score.')
    if checks['structured_data'].details['malformed']:
        diagnostics.append('Malformed JSON-LD found; invalid syntax fails the structured-data check.')
    images = [img for img in soup.find_all('img') if str(img.get('role','')).lower() not in ('presentation','none') and str(img.get('aria-hidden','')).lower()!='true' and img.get('width')!='1' and img.get('height')!='1']
    missing_alt = [str(img.get('src','')) for img in images if not img.has_attr('alt')]
    viewport = soup.find('meta',attrs={'name':re.compile('^viewport$',re.I)})
    supplemental = {'_tokens':words, 'link_references':references,
                    'social_metadata':{key: str(tag.get('content','')) if (tag:=soup.find('meta',attrs={'property':key}) or soup.find('meta',attrs={'name':key})) else None
                                       for key in ('og:title','og:description','og:image','og:url','twitter:card','twitter:title','twitter:description','twitter:image')},
                    'mixed_content':[t.get('src') or t.get('href') for t in soup.select('img[src], video[src], source[src], script[src], iframe[src], link[rel~=stylesheet][href]') if page.url.startswith('https:') and str(t.get('src') or t.get('href')).lower().startswith('http:')],
                    'images':{'checked':len(images), 'missing_alt':missing_alt, 'empty_alt_review':[str(img.get('src','')) for img in images if img.has_attr('alt') and not str(img['alt']).strip()], 'note':'Explicit presentation/hidden/1px images are excluded. Empty alt may be intentional decoration; review context.'},
                    'viewport':{'present':viewport is not None, 'content':str(viewport.get('content','')) if viewport else ''}, 'http':{'aliases':page.redirect_aliases,'status_code':page.status_code, 'original_crawler_status':page.original_status_code, 'redirect_chain':page.redirect_chain}}
    return PageAnalysis(url=page.url, status_code=page.status_code, checks=checks,
                        links=sorted({ref['url'] for ref in references}), diagnostics=diagnostics, headers_available=page.headers is not None,
                        social_profiles=extract_social_profiles(soup, page.url), supplemental=supplemental, source_kind=page.source_kind)
