"""Bounded robots parsing with grouped agents, wildcards, and longest-match rules."""
import re
from urllib.parse import quote, urlsplit
from backend.app.schemas import RobotsRule


def path_octets(value: str) -> str:
    unreserved = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~'
    value = re.sub(r'%([0-9a-fA-F]{2})', lambda m: chr(int(m[1], 16)) if chr(int(m[1], 16)) in unreserved else '%' + m[1].upper(), value)
    return quote(value, safe='/%*?$&=;:+,@!()[]~.-_')


class RobotsPolicy:
    def __init__(self, content: str):
        self.groups: list[tuple[list[str], list[RobotsRule]]] = []
        self.sitemaps: list[str] = []
        self.warnings: list[str] = []
        self.delays = []
        has_directive = False
        agents, rules = [], []
        for number, raw in enumerate(content.lstrip('\ufeff').splitlines(), 1):
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            if ':' not in line:
                self.warnings.append(f'Line {number}: missing colon; ignored.')
                continue
            field, value = (part.strip() for part in line.split(':', 1))
            field = field.lower()
            if field == 'sitemap':
                if value and value not in self.sitemaps:
                    self.sitemaps.append(value)
                continue
            if field == 'user-agent':
                if rules or has_directive:
                    self.groups.append((agents, rules))
                    agents, rules = [], []
                    has_directive = False
                if value:
                    agents.append(value.lower())
                else:
                    self.warnings.append(f'Line {number}: empty user-agent; ignored.')
            elif field == 'crawl-delay':
                has_directive = True
                try:
                    from math import isfinite
                    delay = float(value)
                    if not agents or not isfinite(delay) or delay < 0: raise ValueError()
                    self.delays.append((agents.copy(), delay))
                except ValueError:
                    self.warnings.append(f'Line {number}: invalid Crawl-delay; ignored.')
            elif field in ('allow', 'disallow'):
                if not agents:
                    self.warnings.append(f'Line {number}: rule has no user-agent; ignored.')
                elif value and not value.startswith('/'):
                    self.warnings.append(f'Line {number}: rule must start with /; ignored.')
                else:
                    rules.append(RobotsRule(directive=field, value=value, agents=agents.copy(), line=number))
            elif field == 'noindex':
                self.warnings.append(f'Line {number}: noindex in robots.txt is not an indexing directive. Use a robots meta tag or X-Robots-Tag.')
        if agents:
            self.groups.append((agents, rules))

    @property
    def rules(self):
        return [rule for _, rules in self.groups for rule in rules]

    def crawl_delay(self, agent='CrawlensBot'):
        matches = [(max((len(a) for a in agents if a!='*' and a in agent.lower()),default=0), delay) for agents,delay in self.delays if '*' in agents or any(a in agent.lower() for a in agents)]
        specificity = max((score for score,_ in matches),default=0)
        return max((delay for score,delay in matches if score==specificity),default=0)

    def permission(self, agent: str, url: str) -> tuple[bool, str | None]:
        specific = [(max((len(a) for a in agents if a != '*' and a in agent.lower()), default=0), rules) for agents, rules in self.groups]
        specificity = max((length for length, _ in specific), default=0)
        applicable = [rule for length, rules in specific if length == specificity and specificity > 0 for rule in rules]
        if not specificity:
            applicable = [rule for agents, rules in self.groups if '*' in agents for rule in rules]
        parsed = urlsplit(url)
        path = path_octets((parsed.path or '/') + ('?' + parsed.query if parsed.query else ''))
        matches = []
        for rule in applicable:
            if not rule.value:
                continue
            value = path_octets(rule.value)
            if rule_matches(value, path):
                matches.append(rule)
        if not matches:
            return True, None
        winner = max(matches, key=lambda rule: (len(path_octets(rule.value).replace('*', '').removesuffix('$')), rule.directive == 'allow'))
        return winner.directive == 'allow', f'{winner.directive.title()}: {winner.value}'


def rule_matches(value: str, path: str) -> bool:
    """Match only robots wildcards, without regex backtracking on untrusted rules."""
    anchored = value.endswith('$')
    value = value[:-1] if anchored else value
    if '*' not in value:
        return path == value if anchored else path.startswith(value)
    parts = value.split('*')
    if not path.startswith(parts[0]):
        return False
    cursor = len(parts[0])
    for part in parts[1:-1]:
        found = path.find(part, cursor)
        if found < 0:
            return False
        cursor = found + len(part)
    if anchored:
        return path.endswith(parts[-1]) and len(path) - len(parts[-1]) >= cursor
    return path.find(parts[-1], cursor) >= 0
