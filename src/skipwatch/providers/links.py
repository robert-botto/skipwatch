"""Link fetching for post context (R-ING-1): the READMEs, gists and docs pages a post links.

Plain GETs with a generic User-Agent, through one requests session that ignores the
environment (no ~/.netrc logins, no proxy variables) and keeps no cookies. Only http and https
URLs that urllib3 (the parser requests uses) reads the same way, with no userinfo and no
backslash. A host is fetched only when every address it resolves to is public, and the socket
then goes to that vetted address, so neither a second DNS answer (rebinding) nor a redirect
(re-checked at each of at most 3 hops) can reach localhost, the LAN or a cloud metadata
address. Each link gets 15 s of wall clock and each post 40 s in all; at most 2 MB is read per
page. HTML becomes text through htmltext; markdown and plain text stay as they are; anything
else is skipped. Text is capped at 20 000 characters, links at 5 per post.
"""

import errno
import ipaddress
import logging
import re
import socket
import threading
import time
from urllib.parse import urljoin, urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import ConnectTimeoutError, LocationParseError, NewConnectionError
from urllib3.util import parse_url

from skipwatch.htmltext import html_to_text
from skipwatch.models import IngestBundle, LinkContext, ProviderCall

MAX_LINKS = 5
MAX_CHARS = 20_000
MAX_BYTES = 2_000_000
MAX_REDIRECTS = 3
TIMEOUT_S = 10  # per socket operation
CA_BUNDLE: str | bool = True  # certificate verification: requests' CA bundle (tests: a test CA)
USER_AGENT = "Mozilla/5.0 (compatible; SkipWatch link reader)"  # generic, nothing personal
LINK_DEADLINE_S = 15.0  # wall clock per link, redirects and body included
POST_BUDGET_S = 40.0  # wall clock for every fetch and HEAD one post makes
CHUNK = 65_536
REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
TEXT_TYPES = frozenset({"text/plain", "text/markdown", "text/x-markdown"})

log = logging.getLogger(__name__)
_URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_TRAILING = ".,;:!?'\"*"
_CLOSERS = {")": "(", "]": "[", "}": "{"}
_GITHUB_REPO = re.compile(r"^/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")
_GIST = re.compile(r"^/([\w.-]+)/([0-9a-f]+)/?$", re.IGNORECASE)


class Refused(Exception):
    """A link SkipWatch will not fetch, or a fetch that produced no usable text."""


class Budget:
    """The wall-clock budget one post's link traffic shares (fetches and short-link HEADs)."""

    def __init__(self, seconds: float | None = None):
        self.deadline = time.monotonic() + (POST_BUDGET_S if seconds is None else seconds)


def _deadline(budget: Budget | None) -> float:
    deadline = time.monotonic() + LINK_DEADLINE_S
    if budget is not None:
        if budget.deadline <= time.monotonic():
            raise Refused("post link budget spent")
        deadline = min(deadline, budget.deadline)
    return deadline


def _deadline_message() -> str:
    return f"over the {LINK_DEADLINE_S:g} s link deadline"


def _timeout(deadline: float) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise Refused(_deadline_message())
    return min(TIMEOUT_S, left)


def _failure(exc: Exception, deadline: float | None) -> str:
    """A failure past the deadline is the watchdog's doing: say so, not "ConnectionError"."""
    if deadline is not None and time.monotonic() >= deadline - 0.05:  # timer granularity
        return _deadline_message()
    return type(exc).__name__


def _shut(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError as exc:
        if exc.errno != errno.ENOTCONN:  # ENOTCONN: the peer already hung up, nothing to cut
            log.warning("link watchdog could not shut the socket: %s", exc)


# ---- finding links ----


def _trim(url: str) -> str:
    """Drop trailing punctuation, and a closing bracket the URL never opened."""
    while url:
        last = url[-1]
        unopened = last in _CLOSERS and url.count(last) > url.count(_CLOSERS[last])
        if last in _TRAILING or unopened:
            url = url[:-1]
        else:
            break
    return url


def extract_urls(text: str) -> list[str]:
    """http(s) URLs in order of appearance, de-duplicated, at most 5."""
    found: list[str] = []
    for match in _URL_RE.finditer(text or ""):
        url = _trim(match.group(0))
        if url and url not in found:
            found.append(url)
        if len(found) == MAX_LINKS:
            break
    return found


def fetch_url(url: str) -> str:
    """The URL actually fetched: a GitHub repo's raw README, a gist's raw text, else url."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host in ("github.com", "www.github.com"):
        repo = _GITHUB_REPO.match(parts.path)
        if repo:
            owner, name = repo.groups()
            return f"https://raw.githubusercontent.com/{owner}/{name}/HEAD/README.md"
    if host == "gist.github.com" and _GIST.match(parts.path):
        return f"https://gist.github.com{parts.path.rstrip('/')}/raw"
    return url


# ---- the SSRF guard ----


NAT64 = ipaddress.IPv6Network("64:ff9b::/96")
IPV4_COMPATIBLE = ipaddress.IPv6Network("::/96")


def _embedded_ipv4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """The IPv4 address an IPv6 one carries: mapped, compatible (::a.b.c.d), NAT64, 6to4."""
    if ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    if ip in NAT64 or (ip in IPV4_COMPATIBLE and int(ip) > 1):  # :: and ::1 stay IPv6
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip.sixtofour


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])  # drop an IPv6 zone id
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = _embedded_ipv4(ip)
        if embedded is not None:
            return _is_public(str(embedded))
    return ip.is_global and not ip.is_multicast


# Every label a number (decimal, octal or hex): an IPv4 literal in some resolver's eyes.
_NUMERIC_HOST = re.compile(r"^(?:0x[0-9a-f]*|\d+)(?:\.(?:0x[0-9a-f]*|\d+))*\.?$", re.IGNORECASE)


def _is_dotted_quad(host: str) -> bool:
    try:
        ipaddress.IPv4Address(host)  # four decimal parts, no leading zeros
    except ValueError:
        return False
    return True


def _check(url: str) -> list[str]:
    """The addresses to connect to, in resolver order, or Refused unless url is http(s) on a
    host whose every address is public.

    The host is read with urllib3's parse_url, the parser requests itself uses, so the host
    checked is the host connected to. A backslash or userinfo (`user@`) anywhere is refused:
    parsers disagree on both (`http://169.254.169.254\\@example.com/`).
    """
    if "\\" in url:
        raise Refused("refused: backslash in URL")
    try:
        parts = parse_url(url)
    except LocationParseError as exc:
        raise Refused("not a valid URL") from exc
    if (parts.scheme or "").lower() not in ("http", "https"):
        raise Refused(f"refused: scheme {parts.scheme or '(none)'}")
    if parts.auth is not None or "@" in (parts.netloc or ""):
        raise Refused("refused: credentials in URL")
    host = (parts.host or "").strip("[]")
    if not host:
        raise Refused("refused: no host")
    if _NUMERIC_HOST.match(host) and not _is_dotted_quad(host):
        # 0177.0.0.1, 2130706433, 0x7f000001, 127.1: resolvers read these differently
        raise Refused(f"refused: ambiguous numeric host {host}")
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError) as exc:
        raise Refused(f"cannot resolve {host}") from exc
    addresses = {str(info[4][0]) for info in infos}
    try:
        public = bool(addresses) and all(_is_public(a) for a in addresses)
    except ValueError as exc:
        raise Refused(f"cannot resolve {host}") from exc
    if not public:
        raise Refused(f"refused: {host} resolves to a private or local address")
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


# ---- the pinned transport ----


def _pinned(base: type[HTTPConnection], address: str, deadline: float) -> type[HTTPConnection]:
    """A connection class that opens its socket to `address`, the one SkipWatch vetted, so a
    second DNS answer (rebinding) is never used. The Host header, TLS SNI and certificate
    check still use the URL's hostname: only the socket's destination changes.

    Socket timeouts are per read, so a server trickling its TLS handshake or headers a byte at
    a time would never trip them. A watchdog shuts the socket down at the deadline instead."""

    class Pinned(base):
        _watchdog: threading.Timer | None = None
        _watched: socket.socket | None = None

        def _new_conn(self):
            hostname = self._dns_host
            self._dns_host = address
            try:
                sock = super()._new_conn()
            finally:
                self._dns_host = hostname
            # For HTTPS, urllib3's wrap_socket detach()es `sock` (its fileno becomes -1), so
            # the watchdog holds a dup: shutting the dup down ends the shared connection.
            self._watched = sock.dup()
            left = max(0.0, deadline - time.monotonic())
            self._watchdog = threading.Timer(left, _shut, (self._watched,))
            self._watchdog.daemon = True
            self._watchdog.start()
            return sock

        def close(self):
            if self._watchdog is not None:
                self._watchdog.cancel()
            if self._watched is not None:
                self._watched.close()
                self._watched = None
            super().close()

    return Pinned


class _PinnedAdapter(HTTPAdapter):
    def __init__(self, address: str, deadline: float):
        self.address = address  # both read by init_poolmanager, which __init__ calls
        self.deadline = deadline
        super().__init__(max_retries=0)

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)
        http = _pinned(HTTPConnection, self.address, self.deadline)
        https = _pinned(HTTPSConnection, self.address, self.deadline)
        self.poolmanager.pool_classes_by_scheme = {
            "http": type("PinnedHTTPPool", (HTTPConnectionPool,), {"ConnectionCls": http}),
            "https": type("PinnedHTTPSPool", (HTTPSConnectionPool,), {"ConnectionCls": https}),
        }


_SESSION: requests.Session | None = None


def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        # trust_env=False: never ~/.netrc credentials or proxy settings from the environment,
        # so a host a post names can never receive the user's logins. No auth, no cookies:
        # responses go through the adapter directly, so nothing fills the session's jar.
        _SESSION = requests.Session()
        _SESSION.trust_env = False
        _SESSION.headers["User-Agent"] = USER_AGENT
    return _SESSION


def _send(method: str, url: str, address: str, deadline: float) -> requests.Response:
    """One request to `url` over a socket to `address`, cut off at `deadline` however slowly
    the server answers; redirects are never followed here."""
    timeout = _timeout(deadline)
    adapter = _PinnedAdapter(address, deadline)
    try:
        prepared = _session().prepare_request(requests.Request(method, url))
        # proxies={} also suits yt-dlp's select_proxy, which replaces requests' on import
        return adapter.send(prepared, stream=True, timeout=timeout, proxies={}, verify=CA_BUNDLE)
    except BaseException:
        adapter.close()
        raise


def _connect_failed(exc: requests.ConnectionError) -> bool:
    """True when no socket was ever established (refused, unreachable, connect timeout)."""
    reason = getattr(exc.args[0], "reason", None) if exc.args else None
    return isinstance(reason, NewConnectionError | ConnectTimeoutError)


def _send_any(method: str, url: str, addresses: list[str], deadline: float) -> requests.Response:
    """Try each vetted address in turn (IPv6 first on a v4-only network fails to connect),
    every attempt pinned to its address; any failure after connecting is final."""
    for n, address in enumerate(addresses):
        try:
            return _send(method, url, address, deadline)
        except requests.ConnectionError as exc:
            if n == len(addresses) - 1 or not _connect_failed(exc):
                raise
    raise Refused("no address to connect to")


def _close(response: requests.Response) -> None:
    """Close the response and its per-request _PinnedAdapter with its pool: requests sets
    response.connection to the adapter that sent it."""
    response.close()
    connection = getattr(response, "connection", None)
    if connection is not None:
        connection.close()


# ---- fetching ----


def _get(url: str, deadline: float) -> requests.Response:
    """GET with redirects followed by hand; every hop is re-checked and pinned; at most 3."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        response = _send_any("GET", current, _check(current), deadline)
        location = response.headers.get("Location")
        if response.status_code not in REDIRECT_CODES or not location:
            return response
        _close(response)
        current = urljoin(current, location)
    raise Refused(f"more than {MAX_REDIRECTS} redirects")


def _charset(content_type: str) -> str:
    match = re.search(r"charset=[\"']?([\w-]+)", content_type, re.IGNORECASE)
    return match.group(1) if match else "utf-8"


def _read(response: requests.Response, deadline: float) -> bytes:
    """At most 2 MB, and never past the deadline: read1 returns whatever has arrived, so a
    server sending one byte at a time is cut off on time."""
    body = bytearray()
    while len(body) < MAX_BYTES:
        _timeout(deadline)
        chunk = response.raw.read1(CHUNK, decode_content=True)
        if not chunk:
            break
        body.extend(chunk)
    return bytes(body[:MAX_BYTES])


def _fetch(url: str, deadline: float) -> LinkContext:
    try:
        response = _get(fetch_url(url), deadline)
    except requests.RequestException as exc:
        raise Refused(_failure(exc, deadline)) from exc
    try:
        if response.status_code != 200:
            raise Refused(f"HTTP {response.status_code}")
        content_type = response.headers.get("Content-Type") or ""
        mime = content_type.split(";")[0].strip().lower()
        if mime not in HTML_TYPES and mime not in TEXT_TYPES:
            raise Refused(f"skipped content type {mime or '(none)'}")
        try:
            body = _read(response, deadline)
        except requests.RequestException as exc:
            raise Refused(_failure(exc, deadline)) from exc
    finally:
        _close(response)
    try:
        decoded = body.decode(_charset(content_type), errors="replace")
    except LookupError:
        decoded = body.decode("utf-8", errors="replace")
    title, text = html_to_text(decoded) if mime in HTML_TYPES else (None, decoded)
    return LinkContext(url=url, title=title, text=text[:MAX_CHARS])


def _log(calls: list[ProviderCall] | None, op: str, url: str, started: float, error: str | None):
    if calls is None:
        return
    try:
        host = urlsplit(url).hostname
    except ValueError:
        host = None
    ms = max(0, int((time.monotonic() - started) * 1000))
    calls.append(
        ProviderCall(
            provider="free", op=op, ok=error is None, cost_usd=0, ms=ms, endpoint=host, error=error
        )
    )


def fetch_link(
    url: str, calls: list[ProviderCall] | None = None, budget: Budget | None = None
) -> LinkContext | None:
    """The page's text, or None when it is refused, unreachable, slow or not text. Never
    raises. At most 15 s, and never past the post's budget when one is given."""
    started = time.monotonic()
    deadline = None
    try:
        deadline = _deadline(budget)
        got = _fetch(url, deadline)
    except Refused as exc:
        _log(calls, "link.get", url, started, str(exc))
        return None
    except Exception as exc:  # best-effort context: no link failure ever ends ingest
        _log(calls, "link.get", url, started, _failure(exc, deadline))
        return None
    _log(calls, "link.get", url, started, None)
    return got


def fetch_urls(
    urls: list[str], calls: list[ProviderCall], budget: Budget | None = None
) -> list[LinkContext]:
    """Fetch at most 5 URLs, one ProviderCall each, within one post budget (40 s unless the
    caller shares its own); failures are logged and left out."""
    budget = budget or Budget()
    fetched = (fetch_link(url, calls, budget) for url in urls[:MAX_LINKS])
    return [link for link in fetched if link is not None]


def fetch_all(
    text: str, calls: list[ProviderCall], budget: Budget | None = None
) -> list[LinkContext]:
    return fetch_urls(extract_urls(text), calls, budget)


def with_post_links(bundle: IngestBundle) -> IngestBundle:
    """The bundle with the links in its post text fetched into context.links (R-ING-1)."""
    calls = list(bundle.provider_calls)
    found = fetch_all(bundle.context.post_text or "", calls)
    context = bundle.context.model_copy(update={"links": [*bundle.context.links, *found]})
    return bundle.model_copy(update={"context": context, "provider_calls": calls})


def resolve(
    url: str, calls: list[ProviderCall] | None = None, budget: Budget | None = None
) -> str | None:
    """Where a short link (t.co) points: one HEAD, no cookies, the Location not followed."""
    started = time.monotonic()
    deadline = None
    try:
        deadline = _deadline(budget)
        response = _send_any("HEAD", url, _check(url), deadline)
        _close(response)
    except Refused as exc:
        _log(calls, "link.resolve", url, started, str(exc))
        return None
    except Exception as exc:  # best-effort, as fetch_link
        _log(calls, "link.resolve", url, started, _failure(exc, deadline))
        return None
    location = response.headers.get("Location")
    if response.status_code not in REDIRECT_CODES or not location:
        _log(calls, "link.resolve", url, started, f"HTTP {response.status_code}, no redirect")
        return None
    _log(calls, "link.resolve", url, started, None)
    return urljoin(url, location)
