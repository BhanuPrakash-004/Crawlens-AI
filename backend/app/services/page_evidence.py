"""HTML observations used by page rules and cross-page comparisons."""
import re
from collections import Counter, defaultdict
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from backend.app.schemas import Check
from backend.app.services.url_safety import normalize_url


def headings(soup, page):
    raw = BeautifulSoup(page.raw_html, 'html5lib') if page.raw_html is not None else None

    def extract(tree):
        # Collapse source indentation and newlines; inline tags stay joined ("Desk<span>top</span>" is "Desktop").
        return [(tag.name.upper(), ' '.join(tag.get_text().split())) for tag in tree.find_all(['h1', 'h2', 'h3'])]

    items = extract(soup)
    original = extract(raw) if raw is not None else []
    remaining = Counter(original)
    duplicates = Counter(text.casefold() for _, text in items if text.strip())
    rows, problems = [], []
    previous = 0
    for position, (level, text) in enumerate(items, 1):
        n = int(level[1])
        source = 'Crawler snapshot (raw comparison unavailable)'
        if page.source_kind == 'http_full_html_fallback' or remaining[level, text]:
            source = 'Raw HTML'
            remaining[level, text] -= 1
        elif raw is not None:
            source = 'Rendered snapshot only'
        flags = []
        if not text.strip(): flags.append('Empty heading')
        if text and duplicates[text.casefold()] > 1: flags.append('Repeated heading text')
        if previous and n > previous + 1: flags.append('Skipped heading level')
        if text.casefold() in ('click here', 'untitled', 'heading'): flags.append('Generic heading')
        if flags: problems.append(f'{level} #{position}: {", ".join(flags)}')
        rows.append({'level': level, 'text': text, 'position': position, 'source': source, 'flags': flags})
        previous = n
    h1 = [text for level, text in items if level == 'H1']
    if len(h1) > 1: problems.append(f'{len(h1)} H1 headings; review the main page topic')
    all_levels = [int(tag.name[1]) for tag in soup.find_all(re.compile('^h[1-6]$'))]
    skipped = any(b > a + 1 for a, b in zip(all_levels, all_levels[1:]))
    if skipped and not any('Skipped' in msg for msg in problems): problems.append('Skipped heading level')
    return Check(passed=any(t.strip() for t in h1), observed=f'{len(h1)} H1 heading(s). ' + ('. '.join(problems) or ('No structural warnings.' if h1 else 'No main heading found.')),
                 expected='A descriptive main heading. One H1 and consecutive section levels are editorial conventions.',
                 details={'headings': rows, 'raw_headings': [{'level': l, 'text': t, 'position': i} for i, (l,t) in enumerate(original,1)],
                          'skipped_levels': skipped, 'warnings': problems,
                          **{tag.lower(): [t for l,t in items if l == tag] for tag in ('H1','H2','H3')}})


def resolve(base, href):
    try:
        return normalize_url(urljoin(base, str(href))) if href else None
    except ValueError:
        return None


def page_content(soup):
    root = soup.find('main') or soup.find('article') or soup.body or soup
    return ' '.join(str(s).strip() for s in root.find_all(string=True)
                    if s.strip() and s.parent.name not in ('script','style','head','title','noscript')
                    and not s.find_parent(['nav','header','footer','template']))


GENERIC_ALT = ('image', 'photo', 'picture', 'img', 'icon')


def media_check(soup, base):
    resources = []
    for tag in soup.find_all(['img', 'video']):
        video = tag.name == 'video'
        nested = tag.find('source', src=True) if video else None
        src = tag.get('src') or (nested and nested['src']) or tag.get('data-src')
        if not src and tag.get('srcset'):
            candidates = str(tag['srcset']).strip().split(',')
            if candidates and candidates[0].split(): src = candidates[0].split()[0]
        row = {'kind': tag.name, 'source': src, 'url': resolve(base, src), 'failures': [], 'reviews': []}
        if video:
            label = tag.get('aria-label') or tag.get('title') or ' '.join(
                el.get_text(' ', strip=True) for key in tag.get('aria-labelledby','').split()
                if (el := soup.find(id=key)))
            tracks = [resolve(base,t.get('src')) for t in tag.find_all('track') if t.get('kind','').lower() in ('captions','subtitles') and t.get('src')]
            transcript = tag.find_parent('figure') or tag.parent
            row.update(label=label, captions=tracks, poster=resolve(base, tag.get('poster')),
                       transcript_links=[a.get('href') for a in transcript.find_all('a', href=True) if 'transcript' in a.get_text(' ',strip=True).lower()],
                       sources=[resolve(base,s.get('src')) for s in tag.find_all('source',src=True)])
            if not tracks: row['reviews'].append('No captions or subtitles track. Verify whether the video has speech or embedded captions.')
            if not label: row['reviews'].append('No accessible video title or label found.')
        else:
            alt = tag.get('alt')
            one_pixel = str(tag.get('width','')).strip() == str(tag.get('height','')).strip() == '1'
            # alt="" is the HTML-standard way to mark an image as decorative, like role="presentation".
            decorative = (tag.get('role','').lower() in ('none','presentation') or tag.get('aria-hidden','').lower() == 'true'
                          or (alt is not None and not alt.strip()))
            row['tracking_pixel_candidate'] = one_pixel  # 1×1 analytics beacons are not content images.
            row.update(alt=alt, decorative=decorative, width=tag.get('width'), height=tag.get('height'),
                       loading=tag.get('loading'), srcset=tag.get('srcset'), sizes=tag.get('sizes'),
                       explicit_dimensions=bool(tag.get('width') and tag.get('height')), lazy_loaded=tag.get('loading')=='lazy',
                       responsive=bool(tag.get('srcset') or tag.find_parent('picture')),
                       picture=bool(tag.find_parent('picture')), format=urlsplit(row['url'] or '').path.split('.')[-1])
            # An image inside a link or button that already has text ("Connect with Us", a person's name) is named by
            # that text for screen readers. It needs alt="" or a short extra description: a small fix, not a failure.
            holder = tag.find_parent(['a', 'button'])
            row['link_text'] = holder.get_text(' ', strip=True)[:120] if holder else ''
            if not decorative and not one_pixel and alt is None and row['link_text']:
                row['reviews'].append(f'Image inside a link that already says "{row["link_text"][:40]}". Add alt="" if it only repeats '
                                      'the link, or a short description if it shows something more (this also helps image search).')
            elif not decorative and not one_pixel and alt is None: row['failures'].append('Missing alt attribute.')
            elif not decorative and not one_pixel and alt.strip().lower() in GENERIC_ALT:
                row['reviews'].append('Generic alternative text; describe what the image shows.')
        resources.append(row)
    check = Check(passed=None, observed='', expected='Informative images have alternative text. Media files resolve and videos have accessible context.',
                  details={'resources': resources})
    update_media(check)
    return check


def update_media(check):
    rows = check.details['resources']
    problems = [(row['url'] or row['source'] or '(inline media)', msg) for row in rows
                for msg in row['failures'] + row['reviews']]
    outstanding = sum(r.get('resource_status') not in ('ok','broken') for r in rows)
    failed = any(r['failures'] for r in rows)
    check.passed = False if failed else None if not rows or outstanding or problems else True
    # Only content problems (alt text, video context) need a person. Media we could not fetch, for example
    # images on a CDN outside the audited host, stays visible as "unverified" but is not raised as an issue.
    check.details.update(not_applicable=not rows, review_required=bool(problems) and not failed, unverified=outstanding)
    check.observed = f'{len(rows)} media element(s), {outstanding} source(s) unverified. ' + ' '.join(f'{url}: {message}' for url,message in problems)


def contextual_checks(pages, config):
    grouped = defaultdict(list)
    tokens = {}
    preferred = defaultdict(list)
    for page in pages:
        words = page.supplemental.pop('_tokens', [])
        if page.source_kind == 'incomplete_html' or page.status_code != 200: continue
        targets = page.checks['canonical'].details.get('targets',[])
        if len(targets)==1: preferred[targets[0]].append(page)
        for key in ('title','description'):
            value = page.checks['metadata'].details[key].strip().casefold()
            if value: grouped[key,value].append(page)
        if len(words) >= config.thin_word_limit:
            tokens[page.url] = set(zip(words, words[1:], words[2:]))
    for matches in preferred.values():
        if len(matches)>1:
            for page in matches:
                page.checks['canonical'].details['pages_sharing_target']=[p.url for p in matches if p.url != page.url]
    for (key,_), matches in grouped.items():
        if len(matches) < 2: continue
        for page in matches:
            check = page.checks['metadata']
            check.details[f'duplicate_{key}_urls'] = [p.url for p in matches if p.url != page.url]
            check.observed += f' Identical {key} across {len(matches)} pages.'
            check.passed = False
    for i, page in enumerate(pages):
        left = tokens.get(page.url)
        if not left: continue
        for other in pages[i+1:]:
            right = tokens.get(other.url)
            if not right: continue
            similarity = len(left & right) / len(left | right)
            if similarity >= config.similarity_threshold:
                for first, second in ((page, other), (other, page)):
                    check = first.checks['canonical']
                    check.details.setdefault('similar_pages', []).append({'url': second.url, 'similarity': round(similarity,4)})
                    check.details.setdefault('warnings', []).append('Similar main content; confirm the preferred URL.')
                    check.observed += f' Main text similarity {similarity:.1%} with {second.url}.'
