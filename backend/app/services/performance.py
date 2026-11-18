"""Mobile Lighthouse diagnostics and URL-scoped CrUX field percentiles."""
import asyncio
import math

import httpx

from backend.app.services.url_safety import normalize_url

ENDPOINT = 'https://www.googleapis.com/pagespeedonline/v5/runPagespeed'


def read_performance(page, payload, config):
    check = page.checks['performance']
    lab = payload.get('lighthouseResult', {})
    field = payload.get('loadingExperience', {})
    if lab.get('runtimeError') or normalize_url(lab.get('finalDisplayedUrl') or lab.get('finalUrl') or page.url) != page.url:
        lab = {}
    if field.get('origin_fallback') or field.get('originFallback') or field.get('id') != page.url:
        field = {}
    audits = lab.get('audits', {})
    vitals = {}
    for name, field_key, lab_key, limit in (
        ('LCP', 'LARGEST_CONTENTFUL_PAINT_MS', 'largest-contentful-paint', config.lcp_ms),
        ('INP', 'INTERACTION_TO_NEXT_PAINT', None, config.inp_ms),
        ('CLS', 'CUMULATIVE_LAYOUT_SHIFT_SCORE', 'cumulative-layout-shift', config.cls_limit),
    ):
        value = field.get('metrics', {}).get(field_key, {}).get('percentile')
        source = 'CrUX URL field p75'
        if value is None:
            source = 'Lighthouse mobile lab'
            audit = audits.get(lab_key, {}) if lab_key else {}
            value = None if audit.get('scoreDisplayMode') in ('error','notApplicable') else audit.get('numericValue')
        elif name == 'CLS':
            value = value / 100
        if type(value) not in (int,float) or not math.isfinite(value) or value < 0:
            continue
        vitals[name] = {'value':value, 'source':source, 'limit':limit, 'passed':value <= limit,
                        'unit':'ms' if name != 'CLS' else 'unitless'}
    resources = audits.get('network-requests', {}).get('details', {}).get('items', [])
    check.details.update(vitals=vitals, lighthouse_version=lab.get('lighthouseVersion'), fetch_time=lab.get('fetchTime'),
                         transferred_bytes=audits.get('total-byte-weight',{}).get('numericValue'),
                         fully_loaded_ms=(audits.get('metrics',{}).get('details',{}).get('items') or [{}])[0].get('observedLoad'),
                         large_resources=[{'url':r.get('url'),'bytes':r['transferSize'],'type':r.get('resourceType')} for r in resources
                                          if isinstance(r.get('transferSize'),(float,int)) and r['transferSize'] >= config.large_resource_bytes])
    check.passed = False if any(not v['passed'] for v in vitals.values()) else True if len(vitals)==3 else None
    readings = [f"{k} {v['value']:g} {v['unit']} ({v['source']})" for k,v in vitals.items()]
    missing = [key for key in ('LCP','INP','CLS') if key not in vitals]
    if missing: readings.append('Unavailable: '+', '.join(missing))
    check.observed = '. '.join(readings)


def pagespeed_hint(code: int, has_key: bool) -> str:
    """Explain a PageSpeed error in words a user can act on. The key itself is never included."""
    if code == 429:
        return ('Google quota exceeded for this API key; try again later.' if has_key else
                'Without PAGESPEED_API_KEY, Google allows very few requests, and repeated testing uses them up. Add a key in .env.')
    if code == 400 and has_key:
        return 'Google rejected the request; check that PAGESPEED_API_KEY is correct, or the page may be unreachable for Google.'
    if code == 403:
        return 'Enable the PageSpeed Insights API for the key\'s Google Cloud project, and check the key restrictions.'
    return ''


async def measure_performance(pages, config, budget):
    eligible = [p for p in pages if p.status_code == 200 and not p.checks['indexability'].details.get('noindex') and not p.checks['indexability'].details.get('not_applicable')]
    for page in pages:
        if page.checks['indexability'].details.get('not_applicable'):
            page.checks['performance'].details['not_applicable'] = True
        page.checks['performance'].observed = 'Outside the configured PageSpeed sample or unavailable for this page.'
    async with httpx.AsyncClient(timeout=max(.1,budget),trust_env=False) as client:
        async def measure(page):
            check = page.checks['performance']
            check.observed = 'PageSpeed measurement did not finish within the audit budget.'
            params = {'url':page.url,'category':'performance','strategy':'mobile'}
            if config.pagespeed_api_key: params['key'] = config.pagespeed_api_key
            check.details['api_key_used'] = bool(config.pagespeed_api_key)
            try:
                response = await client.get(ENDPOINT,params=params)
                response.raise_for_status()
                read_performance(page,response.json(),config)
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                check.details['quota_limited'] = code == 429
                check.observed = f'PageSpeed returned HTTP {code}. No measured vitals available. ' + pagespeed_hint(code, bool(config.pagespeed_api_key))
            except (httpx.HTTPError,ValueError,TypeError,AttributeError,IndexError):
                check.observed = 'PageSpeed measurements were unavailable or unusable.'
        try:
            await asyncio.wait_for(asyncio.gather(*(measure(p) for p in eligible[:config.pagespeed_page_limit])),max(.1,budget))
        except TimeoutError:
            pass
