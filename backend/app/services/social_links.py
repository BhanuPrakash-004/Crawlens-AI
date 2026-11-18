"""Discover profile references; do not infer ownership or call social providers."""
import json
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit
from bs4 import BeautifulSoup
from backend.app.schemas import SocialAudit, SocialProfile

PLATFORMS = {
    'linkedin.com': 'LinkedIn', 'instagram.com': 'Instagram',
    'facebook.com': 'Facebook', 'x.com': 'X', 'twitter.com': 'X',
    'youtube.com': 'YouTube', 'tiktok.com': 'TikTok', 'pinterest.com': 'Pinterest',
    'threads.net': 'Threads', 'threads.com': 'Threads', 'bsky.app': 'Bluesky',
    'github.com': 'GitHub',
}
NON_PROFILES = {'share', 'sharing', 'sharer', 'sharer.php', 'intent', 'login', 'signup', 'register', 'search', 'hashtag', 'explore', 'watch', 'reel', 'reels', 'shorts', 'p', 'stories', 'home', 'help', 'privacy', 'policy', 'terms', 'i', 'dialog', 'plugins', 'pin', 'status'}


def profile_url(value: str, source: str) -> tuple[str, str] | None:
    try:
        parsed = urlsplit(urljoin(source, value))
        if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or parsed.port not in (None, 80, 443):
            return None
        host = (parsed.hostname or '').lower()
        domain = next((domain for domain in PLATFORMS if host == domain or host.endswith('.' + domain)), None)
        parts = [part for part in parsed.path.split('/') if part]
        if not domain or not parts or parts[0].lower() in NON_PROFILES:
            return None
        platform = PLATFORMS[domain]
        if platform == 'YouTube' and not (parts[0].startswith('@') and len(parts) == 1 or parts[0] in ('channel', 'c', 'user') and len(parts) == 2):
            return None
        if platform == 'LinkedIn' and not (parts[0] in ('in', 'company', 'school') and len(parts) == 2):
            return None
        if platform in ('X', 'Instagram', 'Pinterest', 'GitHub', 'Threads') and len(parts) != 1:
            return None
        if platform == 'TikTok' and not (len(parts) == 1 and parts[0].startswith('@')):
            return None
        if platform == 'Bluesky' and not (len(parts) == 2 and parts[0] == 'profile'):
            return None
        if platform == 'Facebook' and len(parts) != 1 and not (parts[0] in ('pages', 'people') and len(parts) <= 3):
            return None
        query = ''
        if platform == 'Facebook' and parts[0] == 'profile.php':
            identifier = parse_qs(parsed.query).get('id', [''])[0]
            if not identifier.isdigit():
                return None
            query = urlencode({'id': identifier})
        domain = 'x.com' if platform == 'X' else 'threads.net' if platform == 'Threads' else domain
        return platform, urlunsplit(('https', domain, '/' + '/'.join(parts), query, ''))
    except (ValueError, TypeError):
        return None


def extract_social_profiles(soup: BeautifulSoup, source: str) -> list[SocialProfile]:
    found: dict[str, SocialProfile] = {}

    def add(value, kind):
        if not isinstance(value, str):
            return
        normalized = profile_url(value, source)
        if normalized:
            platform, url = normalized
            profile = found.setdefault(url, SocialProfile(platform=platform, url=url, source_pages=[source]))
            if kind not in profile.evidence_types:
                profile.evidence_types.append(kind)

    for anchor in soup.find_all('a', href=True):
        add(str(anchor['href']).strip(), 'HTML link')

    def visit(node, depth=0):
        if depth > 30:
            return
        if isinstance(node, dict):
            same_as = node.get('sameAs', [])
            for value in same_as if isinstance(same_as, list) else [same_as]:
                add(value, 'JSON-LD sameAs')
            for value in node.values():
                if isinstance(value, (dict, list)):
                    visit(value, depth + 1)
        elif isinstance(node, list):
            for value in node:
                visit(value, depth + 1)

    for script in soup.find_all('script', attrs={'type': 'application/ld+json'}):
        try:
            visit(json.loads(script.string or script.get_text()))
        except (ValueError, RecursionError):
            continue
    return sorted(found.values(), key=lambda profile: (profile.platform, profile.url))


def summarize_social(pages) -> SocialAudit:
    profiles: dict[str, SocialProfile] = {}
    for page in pages:
        for item in page.social_profiles:
            profile = profiles.setdefault(item.url, SocialProfile(platform=item.platform, url=item.url))
            profile.source_pages = sorted(set(profile.source_pages + item.source_pages))
            profile.evidence_types = sorted(set(profile.evidence_types + item.evidence_types))
    return SocialAudit(status='found' if profiles else 'not_found' if pages else 'unknown',
                       profiles=sorted(profiles.values(), key=lambda p: (p.platform, p.url)),
                       pages_checked=len(pages), pages_with_profiles=sum(bool(p.social_profiles) for p in pages),
                       summary='Profiles referenced by scanned pages. Account ownership and destination availability are not verified.' if profiles else 'No supported social profile links were found in the scanned pages. This does not prove that the website has no social accounts.')
