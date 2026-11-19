from collections import Counter, defaultdict
from backend.app.schemas import Issue

RULES = {
    'performance': ('high','Improve measured page performance','Start with the failing vital on the affected URL. Inspect the largest transferred resource, optimize it, and rerun the same mobile measurement.'),
    'canonical': ('medium','Clarify the preferred URL','Verify the declared destination is indexable and returns HTTP 200. Point equivalent pages to the intended final URL.'),
    'media': ('medium','Improve image and video accessibility','Repair the specific media URL, describe informative images, keep decorative alternatives empty, and review captions and labels on affected videos.'),
    'geo': ('low','Improve AI crawler access and readability','Confirm the intended crawler policy, then expose the main topic and factual product details in readable HTML.'),
    'robots_txt': ('high', 'Review crawler access rules', 'Inspect robots.txt evidence and confirm that important public pages are intentionally accessible to search crawlers.'),
    'sitemap': ('high', 'Improve sitemap discovery', 'Resolve sitemap file errors and publish important canonical URLs in valid sitemap XML. Declare the sitemap location in robots.txt.'),
    'metadata': ('medium', 'Improve page title & description', 'Write unique page-specific titles and descriptions within the measured project limits.'),
    'indexability': ('high', 'Review page indexability', 'Confirm indexing intent for this URL. Restore access to public landing pages and verify their response status and robots directives.'),
    'headings': ('medium', 'Give the page one clear H1', 'Use one descriptive, nonempty H1 and organize supporting sections with H2 and H3 headings.'),
    'structured_data': ('low', 'Review structured data opportunities', 'Where appropriate, add valid Schema.org JSON-LD that accurately describes the page. Validate syntax and use an applicable type.'),
    'broken_links': ('high', 'Repair broken internal links', 'Update the source link to a working destination or restore the missing page. Check restricted responses manually before changing links.'),
}


IMPACT = {
    'metadata':'Unclear or repeated snippets make it harder for customers to choose the right search result.',
    'broken_links':'Visitors and crawlers following these links cannot reach the intended content.',
    'indexability':'Access and indexing directives determine whether search engines can retrieve and index a landing page.',
    'canonical':'Conflicting preferred URLs can split discovery and indexing signals across equivalent pages.',
    'headings':'A clear main heading and ordered sections help readers and assistive technology navigate the content.',
    'performance':'Slow loading, delayed interaction or layout shifts can interrupt visitors before they finish a task.',
    'media':'Inaccessible media can hide product details from visitors who rely on captions or alternative text.',
    'structured_data':'Invalid or inconsistent markup can limit how search engines interpret product and business details.',
    'geo':'Crawler access and extractable HTML help systems retrieve and interpret the page.',
    'robots_txt':'Crawl directives influence which pages a crawler can retrieve.',
    'sitemap':'Discovery files help search engines find the intended canonical landing pages.'
}
PRIORITY = {'critical':0, 'high':1, 'medium':2, 'low':3}


def media_fix(resources):
    steps = []
    if any(r['kind']=='img' and r.get('alt') is None and not r.get('link_text') and not r.get('tracking_pixel_candidate') and not r.get('decorative') for r in resources):
        steps.append('Write descriptive alt text for the identified informative images.')
    if any(r['kind']=='img' and r.get('link_text') and r.get('alt') is None for r in resources):
        steps.append('For images inside links that already have text, add alt="" if the image only repeats the link, '
                     'or a short description (for a team photo, the name of the person) if it adds something.')
    if any(r['kind']=='img' and any('Generic' in m for m in r['reviews']) for r in resources):
        steps.append('Replace generic alternative text such as "image" with a short description of what the image shows.')
    if any(r['kind']=='video' and r['reviews'] for r in resources):
        steps.append('Check accessible labels and caption needs for the identified videos.')
    if any(r.get('resource_status')=='broken' for r in resources):
        steps.append('Repair the listed broken media URLs.')
    return ' '.join(steps) or 'Review the purpose and alternative text of the flagged media.'


def template_signature(issue):
    """What a problem looks like independent of the page, so the same template mistake can be recognised on many pages."""
    d = issue.evidence
    if issue.metric == 'media':
        problems = frozenset((r.get('url') or r.get('source') or '', m) for r in d.get('resources', []) for m in r['failures'] + r['reviews'])
        return problems or None
    if issue.metric == 'headings' and issue.outcome == 'Warning':
        rows = d.get('headings', [])
        repeated = frozenset(t for t, n in Counter(r['text'].casefold() for r in rows if r['level'] == 'H1' and r['text']).items() if n > 1)
        return (len(d.get('h1', [])), repeated, frozenset(f for r in rows for f in r['flags']))
    return None


def group_template_issues(issues):
    """Report a problem that repeats on several pages once, with every affected page. The same missing alt text or the
    same extra H1 on ten pages almost always comes from one shared template, and it is fixed once, not ten times."""
    groups = defaultdict(list)
    for issue in issues:
        signature = template_signature(issue)
        groups[(issue.metric, issue.outcome, issue.severity, signature) if signature else issue.id].append(issue)
    result = []
    for key, members in groups.items():
        first = members[0]
        if len(members) == 1:
            result.append(first)
            continue
        pages = [issue.page_url for issue in members]
        signature = key[3]
        if first.metric == 'media':
            detail = '; '.join(f'{url}: {message}' for url, message in sorted(signature))[:700]
        else:
            count, repeated, flags = signature
            detail = f"{count} H1 headings" + (f"; repeated H1 text: {', '.join(sorted(repeated))}" if repeated else '') +                      (f"; {', '.join(sorted(flags)).lower()}" if flags else '')
        result.append(first.model_copy(update={
            'title': f'{first.title} (same on {len(pages)} pages)', 'affected_source_pages': len(pages),
            'observed': f'The same problem appears on {len(pages)} pages, so it most likely comes from a shared template '
                        f'(header, footer or theme). {detail}',
            'suggested_action': first.suggested_action + ' Fix it once in the shared template, and it is fixed on every page.',
            'evidence': {**first.evidence, 'source_pages': pages, 'template': True}}))
    return result


def build_issues(pages, links):
    issues = []
    for page in pages:
        for metric, check in page.checks.items():
            d = check.details
            if d.get('not_applicable'): continue
            outcome = ('Failed' if check.passed is False else 'Warning' if d.get('warnings') else
                       'Review' if d.get('review_required') and not d.get('optional') else None)
            if not outcome: continue
            severity, title, action = RULES[metric]
            if metric=='indexability' and outcome=='Failed': severity = 'critical'
            if outcome=='Warning': severity = 'low'
            if metric=='media': action = media_fix(d.get('resources',[]))
            if metric=='media' and outcome=='Review': severity = 'low'  # Verification or small markup tasks, not failures.
            if metric=='headings': title = 'Review heading structure' if outcome=='Warning' else 'Missing descriptive main heading'
            issues.append(Issue(id=f'issue_{len(issues)+1}', metric=metric,severity=severity,page_url=page.url,
                                outcome=outcome, title=title,observed=check.observed,expected=check.expected,
                                evidence=d,impact=IMPACT[metric],suggested_action=action))
    issues = group_template_issues(issues)
    for link in links:
        if link.status!='broken': continue
        issues.append(Issue(id=f'issue_{len(issues)+1}',metric='broken_links',severity='high',page_url=next(iter(link.source_pages),link.url),
                            title='Broken internal destination', observed=f'HTTP {link.status_code} at {link.final_url or link.url}.',
                            expected='Internal destinations resolve without HTTP errors.',suggested_action=RULES['broken_links'][2],
                            target_url=link.url,status_code=link.status_code,affected_source_pages=len(set(link.source_pages)),
                            evidence=link.model_dump(),impact=IMPACT['broken_links']))
    return sorted(issues,key=lambda item:PRIORITY[item.severity])
