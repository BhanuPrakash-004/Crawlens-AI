from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction

from backend.app.config import settings
from backend.app.schemas import Metric, SiteChecks
from backend.app.services.url_safety import normalize_url
from backend.app.services.page_evidence import GENERIC_ALT


def rounded(value):
    if isinstance(value, Fraction):
        return (2 * value.numerator + value.denominator) // (2 * value.denominator)
    return int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def observations(name, pages, links, site):
    def row(url, status, reason, rule=None):
        return {'url':url, 'status':status, 'observed':reason, 'rule':rule}

    if name == 'broken_links':
        for link in links:
            yield row(link.url, {'ok':'Passed','broken':'Failed','unknown':'Review'}[link.status],link.reason or f'HTTP {link.status_code}')
    elif name == 'site_health':
        for key, item in [('robots.txt',site.robots_txt),('sitemap',site.sitemap)]:
            status = {'passed':'Passed','error':'Failed','warning':'Warning','unknown':'Review'}[item.status]
            yield row(site.robots_txt.url if key=='robots.txt' else next((f.url for f in site.sitemap.files),''),status,item.summary,key)
    elif name == 'media':
        emitted = set()
        for page in pages:
            check = page.checks.get('media')
            if not check or check.details.get('unavailable') or page.status_code != 200 or page.source_kind == 'incomplete_html':
                yield row(page.url,'Review','Media observations are unavailable.')
                continue
            resources = check.details['resources']
            if not resources: yield row(page.url,'N/A','No image or video elements.')
            for position, asset in enumerate(resources, 1):
                url = asset['url'] or asset.get('source') or f'element {position}'
                if asset['kind']=='img':
                    if asset['decorative'] or asset.get('tracking_pixel_candidate'):
                        state = 'N/A'
                        reason = 'Decorative image (empty alt or presentation role).' if asset['decorative'] else '1×1 tracking pixel; not a content image.'
                    elif asset['alt'] is None:
                        state, reason = 'Failed','Missing alt attribute.'
                    elif asset['alt'].strip().lower() in GENERIC_ALT:
                        state, reason = 'Review','Generic alternative text; describe what the image shows.'
                    else:
                        state, reason = 'Passed', f"Alternative text: {asset['alt']}"
                    checks = [('Image alternative',state,reason)]
                else:
                    checks = [('Video label','Passed' if asset['label'] else 'Review',asset['label'] or 'No accessible label.'),
                              ('Captions','Passed' if asset['captions'] else 'Review','Caption track declared.' if asset['captions'] else 'Verify speech or embedded captions.')]
                for rule,state,reason in checks:
                    key = (page.url,url,rule,state,reason)
                    if key not in emitted:
                        emitted.add(key)
                        yield row(page.url,state,f'{url} · {reason}',rule)
                for target in dict.fromkeys([asset['url'], asset.get('poster'), *asset.get('sources',[]), *asset.get('captions',[])]):
                    if not target or ('resource',target) in emitted: continue
                    emitted.add(('resource',target))
                    request = asset.get('requests',{}).get(target,{})
                    state = {'ok':'Passed','broken':'Failed'}.get(request.get('status'),'Review')
                    yield row(page.url,state,f"{target} · " + (f"HTTP {request['http']}" if request.get('http') else 'Outside scope or unverified.'),'Resource availability')
                if not asset['url']: yield row(page.url,'Review',f'{url} has no resolvable main source.','Resource availability')
    else:
        for page in pages:
            check = page.checks.get(name)
            if check is None:
                yield row(page.url,'Review','No evidence available.')
                continue
            if name == 'performance':
                for vital in ('LCP','INP','CLS'):
                    if check.details.get('not_applicable'):
                        yield row(page.url,'N/A',check.observed,vital)
                        continue
                    item = check.details.get('vitals',{}).get(vital)
                    yield row(page.url,('Passed' if item['passed'] else 'Failed') if item else 'Review',
                              f"{item['value']} {item['unit']} ({item['source']}, limit {item['limit']})" if item else check.observed,vital)
                continue
            status = ('N/A' if check.details.get('not_applicable') else 'Failed' if check.passed is False else
                      'Passed' if check.passed is True else 'Warning' if check.details.get('warnings') else 'Review')
            yield row(page.url,status,check.observed)


def calculate_scores(pages, links, site=None, config=settings):
    site = site or SiteChecks()
    metrics, weighted, denominator = {}, Fraction(), 0
    pages = {normalize_url(p.url):p for p in pages}.values()
    links = {normalize_url(l.url):l for l in links}.values()
    for name, weight in config.metric_weights.items():
        evidence = list(observations(name,pages,links,site))
        counts = {key:sum(r['status']==key for r in evidence) for key in ('Passed','Failed','Review','Warning','N/A')}
        passing = counts['Passed']
        evaluated = passing + counts['Failed']
        rate = Fraction(passing, evaluated) if evaluated else None
        if evaluated:
            weighted += rate * weight
            denominator += weight
        metrics[name] = Metric(score=rounded(100*rate) if evaluated else None, weight=weight,
                               unit={'performance':'vitals','broken_links':'destinations','site_health':'site checks','media':'media checks'}.get(name,'pages'),
                               passing=passing, evaluated=evaluated, unknown=counts['Review'], warnings=counts['Warning'],
                               not_applicable=counts['N/A'], evidence=evidence, status='measured' if evaluated else 'unknown')
    score = rounded(100*weighted/denominator) if denominator else None
    label = 'Not enough data' if score is None else 'Excellent' if score >= config.excellent_score else 'Good' if score >= config.good_score else 'Needs improvement' if score >= config.improvement_score else 'Critical'
    return metrics, score, label
