"""Public-only URL validation and DNS-pinned HTTP requests.

Firecrawl is responsible for network isolation in its remote crawler. Local
verification never connects to an address other than one validated here.
"""
import asyncio
import ipaddress
import socket
import re
import gzip
from io import BytesIO
from urllib.parse import urlsplit, urlunsplit, urljoin
import httpx


# Responses that mean "access refused or temporarily unavailable", not "this page is broken".
RESTRICTED_CODES = frozenset({401, 403, 407, 408, 429, 503})
# Text found on bot-protection screens. Amazon, for example, answers bots with a 404 "Page Not Found" that
# says "To discuss automated access to Amazon data...", which is not evidence that the page is missing.
BOT_CHALLENGE_MARKERS = ('automated access', 'captcha', 'robot check', 'are you a robot', 'unusual traffic',
                         'cf-chl', 'challenge-platform')


def is_bot_challenge(code: int | None, body: str) -> bool:
    """True when an error response is a bot-protection screen rather than the site's real answer."""
    return bool(code and code >= 400 and any(marker in body[:20000].lower() for marker in BOT_CHALLENGE_MARKERS))


class UnsafeURL(ValueError):
    pass


def normalize_url(value: str) -> str:
    if len(value) > 2048 or any(ord(c) < 33 for c in value) or '\\' in value:
        raise UnsafeURL('The URL contains invalid characters or is too long.')
    try:
        p = urlsplit(value)
        host = (p.hostname or '').rstrip('.').encode('idna').decode().lower()
        port = p.port
    except (ValueError, UnicodeError) as exc:
        raise UnsafeURL('The website URL is invalid.') from exc
    if p.scheme.lower() not in ('http', 'https'):
        raise UnsafeURL('Only HTTP and HTTPS websites are supported.')
    if p.username is not None or p.password is not None:
        raise UnsafeURL('URLs containing credentials are not allowed.')
    if not host or host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
        raise UnsafeURL('Enter a public website. Local and private addresses are not allowed.')
    if port not in (None, 80, 443):
        raise UnsafeURL('Only standard web ports (80 and 443) are supported.')
    try:
        address = ipaddress.ip_address(host)
        if not address.is_global:
            raise UnsafeURL('Private, loopback, link-local and reserved addresses are not allowed.')
    except ValueError as exc:
        if isinstance(exc, UnsafeURL):
            raise
    authority = f'[{host}]' if ':' in host else host
    if port and port != (443 if p.scheme.lower() == 'https' else 80):
        authority += f':{port}'
    path = re.sub(r'%[0-9a-fA-F]{2}', lambda m: chr(int(m[0][1:], 16)) if
                  re.fullmatch(r'[A-Za-z0-9_~.-]', chr(int(m[0][1:], 16))) else m[0].upper(), p.path or '/')
    segments = []
    for segment in path.split('/')[1:]:
        if segment == '..':
            if segments: segments.pop()
        elif segment != '.':
            segments.append(segment)
    if path.endswith(('/.', '/..')): segments.append('')
    return urlunsplit((p.scheme.lower(), authority, '/' + '/'.join(segments), p.query, ''))


async def resolve_public(url: str) -> tuple[str, list[str]]:
    normalized = normalize_url(url)
    p = urlsplit(normalized)
    try:
        records = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(p.hostname, p.port or (443 if p.scheme == 'https' else 80), type=socket.SOCK_STREAM),
            timeout=5,
        )
    except (socket.gaierror, TimeoutError) as exc:
        raise UnsafeURL('The website hostname could not be resolved. Check the URL and try again.') from exc
    addresses = list(dict.fromkeys(record[4][0] for record in records))
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise UnsafeURL('The hostname resolves to a private or restricted network address.')
    return normalized, addresses


async def safe_request(client: httpx.AsyncClient, method: str, url: str, *, read_body: bool = False,
                       max_bytes: int = 512_000, before_request=None, trace=None, registry=None,
                       sitemap_body=False, truncate=False) -> tuple[int, dict, str, str]:
    """truncate=True keeps the first max_bytes of a large body instead of failing (enough to classify an error page)."""
    current = normalize_url(url)
    visited = set()

    async def fetch(hop):
        _, addresses = await resolve_public(hop)
        if before_request:
            await before_request(hop)
        p = urlsplit(hop)
        ip = addresses[0]
        authority = f'[{ip}]' if ':' in ip else ip
        if p.port: authority += f':{p.port}'
        pinned = urlunsplit((p.scheme, authority, p.path, p.query, ''))
        async with client.stream(method, pinned, headers={'Host': p.netloc},
                                 extensions={'sni_hostname': p.hostname}, follow_redirects=False) as response:
            body = bytearray()
            if read_body and not response.is_redirect:
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        if truncate:
                            del body[max_bytes:]
                            break
                        raise ValueError('Response exceeded the size limit.')
            if sitemap_body and body.startswith(bytes([31, 139])):
                try:
                    with gzip.GzipFile(fileobj=BytesIO(body)) as archive:
                        body = archive.read(max_bytes + 1)
                except (OSError, EOFError) as exc:
                    raise ValueError('Invalid gzip sitemap.') from exc
                if len(body) > max_bytes:
                    raise ValueError('Decompressed sitemap exceeded the size limit.')
            return response.status_code, dict(response.headers), body.decode('utf-8', errors='replace'), hop

    for _ in range(6):
        if current in visited:
            raise ValueError('Redirect loop detected.')
        visited.add(current)
        response = await registry(current, method, read_body, max_bytes, sitemap_body, fetch) if registry else await fetch(current)
        code, headers, _, _ = response
        location = headers.get('location')
        if trace is not None:
            trace.append({'url': current, 'status_code': code, 'location': location})
        if code not in (301, 302, 303, 307, 308):
            return response
        if not location:
            raise ValueError('Redirect did not include a destination.')
        current = normalize_url(urljoin(current, location))
    raise ValueError('The destination exceeded the redirect limit.')
