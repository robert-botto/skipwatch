"""Link fetching for post context (R-ING-1). No sockets: requests.get and getaddrinfo are faked."""

import ipaddress
import socket
import time

import pytest

from skipwatch import htmltext
from skipwatch.models import ProviderCall
from skipwatch.providers import links

PUBLIC_IP = "93.184.215.14"


class FakeResponse:
    def __init__(self, status=200, body=b"", content_type="text/html", location=None):
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        if location is not None:
            self.headers["Location"] = location
        self._body = body
        self.closed = False
        self.raw = self
        self._at = 0
        self.reads: list[int] = []

    def read1(self, amt, decode_content=None):
        chunk = self._body[self._at : self._at + amt]
        self._at += len(chunk)
        self.reads.append(len(chunk))
        return chunk

    def close(self):
        self.closed = True


@pytest.fixture
def net(monkeypatch):
    """Fake DNS (host -> address) and HTTP (url -> FakeResponse); records every request."""
    state = {"dns": {}, "pages": {}, "requested": [], "kwargs": []}

    def getaddrinfo(host, port, *args, **kwargs):
        try:
            address = str(ipaddress.ip_address(host))  # a literal resolves to itself
        except ValueError:
            address = state["dns"].get(host, PUBLIC_IP)
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (address, port or 0))]

    def send(method, url, address, deadline):
        state["requested"].append(url)
        state["kwargs"].append({"method": method, "address": address, "deadline": deadline})
        page = state["pages"].get(url)
        return page if page is not None else FakeResponse(404, b"", "text/html")

    monkeypatch.setattr(links.socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(links, "_send", send)
    return state


def html(body: str, title: str = "Doc") -> bytes:
    return f"<html><head><title>{title}</title></head><body>{body}</body></html>".encode()


def test_r_ing_1_link_text_capped_at_20k(net):
    net["pages"]["https://docs.example.com/big"] = FakeResponse(body=html("<p>" + "a" * 50_000))
    got = links.fetch_link("https://docs.example.com/big")
    assert got is not None and got.title == "Doc"
    assert len(got.text) == 20_000


def test_links_skip_private_hosts_and_binary(net):
    net["dns"]["router.example.com"] = "192.168.1.2"
    net["pages"]["https://example.com/logo.png"] = FakeResponse(
        body=b"\x89PNG", content_type="image/png"
    )
    for url in ("http://127.0.0.1/", "http://10.0.0.5/", "http://router.example.com/admin"):
        assert links.fetch_link(url) is None
    assert net["requested"] == []  # refused before any request
    assert links.fetch_link("https://example.com/logo.png") is None
    assert net["requested"] == ["https://example.com/logo.png"]


@pytest.mark.parametrize(
    "url",
    [
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata, link-local
        "http://[::ffff:127.0.0.1]/",  # IPv4-mapped loopback
        "http://0.0.0.0/",
        "http://224.0.0.1/",  # multicast
        "ftp://example.com/file.txt",
        "file:///etc/passwd",
        "javascript:alert(1)",
    ],
)
def test_links_refuse_non_public_and_non_http(net, url):
    assert links.fetch_link(url) is None
    assert net["requested"] == []


def test_links_refuse_host_with_any_private_address(net, monkeypatch):
    def getaddrinfo(host, port, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
        ]

    monkeypatch.setattr(links.socket, "getaddrinfo", getaddrinfo)
    assert links.fetch_link("https://mixed.example.com/") is None
    assert net["requested"] == []


def test_links_unresolvable_host_is_skipped(net, monkeypatch):
    def getaddrinfo(host, port, *args, **kwargs):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(links.socket, "getaddrinfo", getaddrinfo)
    assert links.fetch_link("https://nowhere.example.com/") is None
    assert net["requested"] == []


def test_redirect_to_private_host_is_refused(net):
    net["pages"]["https://short.example.com/x"] = FakeResponse(302, location="http://localhost/")
    net["dns"]["localhost"] = "127.0.0.1"
    assert links.fetch_link("https://short.example.com/x") is None
    assert net["requested"] == ["https://short.example.com/x"]


def test_redirects_followed_at_most_three_times(net):
    for n in range(4):
        net["pages"][f"https://a.example.com/{n}"] = FakeResponse(
            301, location=f"https://a.example.com/{n + 1}"
        )
    net["pages"]["https://a.example.com/3"] = FakeResponse(body=html("<p>three hops</p>"))
    got = links.fetch_link("https://a.example.com/0")
    assert got is not None and "three hops" in got.text
    net["pages"]["https://a.example.com/3"] = FakeResponse(301, location="https://a.example.com/4")
    net["pages"]["https://a.example.com/4"] = FakeResponse(body=html("<p>four hops</p>"))
    net["requested"].clear()
    assert links.fetch_link("https://a.example.com/0") is None
    assert "https://a.example.com/4" not in net["requested"]


def test_relative_redirect_is_resolved_against_the_current_url(net):
    net["pages"]["https://b.example.com/old"] = FakeResponse(301, location="/new")
    net["pages"]["https://b.example.com/new"] = FakeResponse(body=html("<p>moved</p>"))
    got = links.fetch_link("https://b.example.com/old")
    assert got is not None and got.url == "https://b.example.com/old" and "moved" in got.text


def test_requests_go_to_the_vetted_address_within_the_link_deadline(net):
    net["pages"]["https://c.example.com/"] = FakeResponse(body=html("<p>hi</p>"))
    started = time.monotonic()
    links.fetch_link("https://c.example.com/")
    [sent] = net["kwargs"]
    assert sent["method"] == "GET" and sent["address"] == PUBLIC_IP
    assert started < sent["deadline"] <= time.monotonic() + links.LINK_DEADLINE_S


def test_github_repo_url_fetches_readme(net):
    readme = "https://raw.githubusercontent.com/o/r/HEAD/README.md"
    net["pages"][readme] = FakeResponse(body=b"# r\n\nUsage: run it.", content_type="text/plain")
    got = links.fetch_link("https://github.com/o/r")
    assert net["requested"] == [readme]
    assert got is not None and got.url == "https://github.com/o/r"
    assert got.text.startswith("# r") and "Usage: run it." in got.text


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/o/r/", "https://raw.githubusercontent.com/o/r/HEAD/README.md"),
        ("https://github.com/o/r.git", "https://raw.githubusercontent.com/o/r/HEAD/README.md"),
        ("https://www.github.com/o/r", "https://raw.githubusercontent.com/o/r/HEAD/README.md"),
        ("https://github.com/o/r/blob/main/x.py", "https://github.com/o/r/blob/main/x.py"),
        ("https://github.com/o", "https://github.com/o"),
        ("https://gist.github.com/u/abc123", "https://gist.github.com/u/abc123/raw"),
        ("https://gist.github.com/u/abc123/raw", "https://gist.github.com/u/abc123/raw"),
        ("https://docs.example.com/guide", "https://docs.example.com/guide"),
    ],
)
def test_fetch_url_rewrites_github_and_gist(url, expected):
    assert links.fetch_url(url) == expected


def test_markdown_and_plain_text_kept_as_is(net):
    net["pages"]["https://d.example.com/a.md"] = FakeResponse(
        body=b"# Title\n\n  indented code\n", content_type="text/markdown; charset=utf-8"
    )
    got = links.fetch_link("https://d.example.com/a.md")
    assert got is not None and got.text == "# Title\n\n  indented code\n"


def test_body_read_stops_at_two_megabytes(net):
    body = b"x" * (5 * 1024 * 1024)
    net["pages"]["https://e.example.com/huge.txt"] = FakeResponse(
        body=body, content_type="text/plain"
    )
    page = net["pages"]["https://e.example.com/huge.txt"]
    got = links.fetch_link("https://e.example.com/huge.txt")
    assert got is not None and len(got.text) == 20_000
    assert sum(page.reads) <= 2_000_000 + 65_536
    assert page.closed


def test_http_error_status_is_none(net):
    assert links.fetch_link("https://f.example.com/missing") is None


def test_request_exception_is_none(net, monkeypatch):
    def boom(*args, **kwargs):
        raise links.requests.ConnectionError("refused")

    monkeypatch.setattr(links, "_send", boom)
    assert links.fetch_link("https://g.example.com/") is None


def test_extract_urls_order_dedup_punctuation_and_cap():
    text = (
        "See https://a.example.com/x. Also (https://b.example.com/y), "
        "https://a.example.com/x again, https://en.wikipedia.org/wiki/Foo_(bar)! "
        "and http://c.example.com, https://d.example.com/z; https://e.example.com/ "
        "https://f.example.com/"
    )
    assert links.extract_urls(text) == [
        "https://a.example.com/x",
        "https://b.example.com/y",
        "https://en.wikipedia.org/wiki/Foo_(bar)",
        "http://c.example.com",
        "https://d.example.com/z",
    ]


def test_fetch_all_logs_one_call_per_link_and_caps_at_five(net):
    for n in range(7):
        net["pages"][f"https://h{n}.example.com/"] = FakeResponse(body=html(f"<p>page {n}</p>"))
    net["dns"]["h1.example.com"] = "10.1.1.1"
    text = " ".join(f"https://h{n}.example.com/" for n in range(7))
    calls: list[ProviderCall] = []
    got = links.fetch_all(text, calls)
    assert [c.url for c in got] == [f"https://h{n}.example.com/" for n in (0, 2, 3, 4)]
    assert len(calls) == 5
    assert [c.ok for c in calls] == [True, False, True, True, True]
    assert all(c.provider == "free" and c.op == "link.get" for c in calls)
    assert calls[0].endpoint == "h0.example.com" and calls[0].cost_usd == 0
    assert calls[1].error and "private" in calls[1].error


def test_resolve_follows_one_redirect_with_head(net):
    net["pages"]["https://t.co/abc"] = FakeResponse(
        301, location="https://twitter.com/someone/status/123"
    )
    calls: list[ProviderCall] = []
    assert links.resolve("https://t.co/abc", calls) == "https://twitter.com/someone/status/123"
    assert net["requested"] == ["https://t.co/abc"]
    assert net["kwargs"][0]["method"] == "HEAD"
    assert [(c.op, c.ok, c.endpoint) for c in calls] == [("link.resolve", True, "t.co")]


def test_resolve_refuses_private_and_reports_failure(net):
    net["dns"]["t.co"] = "127.0.0.1"
    calls: list[ProviderCall] = []
    assert links.resolve("https://t.co/abc", calls) is None
    assert net["requested"] == [] and calls[0].ok is False


def test_html_to_text_drops_scripts_and_keeps_headings():
    page = """<html><head><title> My  Guide </title><style>p{color:red}</style></head>
    <body><nav>Home | Docs</nav><script>var secret = 1;</script><noscript>enable js</noscript>
    <h1>Install</h1><p>Run   the
    installer.</p><h2>Usage</h2><ul><li>first</li><li>second</li></ul>
    <pre>  def f():
      return 1</pre><p>Tom &amp; Jerry</p><footer>(c) 2026</footer></body></html>"""
    title, text = htmltext.html_to_text(page)
    assert title == "My Guide"
    assert "secret" not in text and "color" not in text and "Home" not in text
    assert "enable js" not in text and "(c) 2026" not in text
    assert "# Install" in text and "## Usage" in text
    assert "Run the installer." in text
    assert "- first\n- second" in text
    assert "  def f():\n      return 1" in text
    assert "Tom & Jerry" in text
    assert "\n\n\n" not in text and text == text.strip()


def test_html_to_text_without_title():
    assert htmltext.html_to_text("<p>just text</p>") == (None, "just text")


def test_link_fetching_never_raises(net, monkeypatch):
    """Links are best-effort context: any failure is logged and the link left out."""

    def boom(*args, **kwargs):
        raise RuntimeError("anything at all")

    monkeypatch.setattr(links.socket, "getaddrinfo", boom)
    calls: list[ProviderCall] = []
    assert links.fetch_link("https://i.example.com/", calls) is None
    assert links.resolve("https://t.co/abc", calls) is None
    assert [(c.ok, c.error) for c in calls] == [(False, "RuntimeError"), (False, "RuntimeError")]


# ---- parser mismatch: the host SkipWatch checks must be the host requests connects to ----

CONFUSED = [
    "http://169.254.169.254\\@example.com/",  # urlsplit: example.com; urllib3: 169.254.169.254
    "http://example.com\\@169.254.169.254/",
    "http://user:pass@example.com/",  # userinfo is refused outright
    "http://example.com@169.254.169.254/",
    "http://169.254.169.254\\example.com/",
]


@pytest.mark.parametrize("url", CONFUSED)
def test_urls_the_parsers_disagree_on_are_refused(net, url):
    assert links.fetch_link(url) is None
    assert net["requested"] == []


@pytest.mark.parametrize("location", CONFUSED)
def test_redirect_to_a_confusing_url_is_refused(net, location):
    net["pages"]["https://hop.example.com/"] = FakeResponse(302, location=location)
    assert links.fetch_link("https://hop.example.com/") is None
    assert net["requested"] == ["https://hop.example.com/"]


def test_resolve_refuses_a_confusing_url(net):
    assert links.resolve(CONFUSED[0]) is None
    assert net["requested"] == []


@pytest.mark.parametrize(
    "address",
    [
        "::127.0.0.1",  # IPv4-compatible loopback
        "::a00:5",  # IPv4-compatible 10.0.0.5
        "64:ff9b::7f00:1",  # NAT64 of 127.0.0.1
        "64:ff9b::a9fe:a9fe",  # NAT64 of 169.254.169.254
        "64:ff9b::c0a8:102",  # NAT64 of 192.168.1.2
        "2002:7f00:1::",  # 6to4 wrapping 127.0.0.1
    ],
)
def test_ipv6_wrapping_a_private_ipv4_is_refused(net, address):
    assert links.fetch_link(f"http://[{address}]/") is None
    assert net["requested"] == []


def test_nat64_of_a_public_ipv4_is_allowed():
    assert links._is_public("64:ff9b::5db8:d70e")  # 93.184.215.14


@pytest.mark.parametrize(
    "host",
    [
        "0177.0.0.1",  # octal to glibc (127.0.0.1), decimal 177.0.0.1 to macOS
        "2130706433",  # 127.0.0.1 as one integer
        "0x7f000001",
        "0x7f.0.0.1",
        "127.1",  # short form
        "010.0.0.1",
    ],
)
def test_ambiguous_numeric_hosts_are_refused_before_resolving(net, monkeypatch, host):
    """Resolvers disagree on these forms, so the address checked might not be the address
    another parser means. From review-m3b/ssrf.py: 0177.0.0.1 was allowed on macOS."""
    asked = []

    def getaddrinfo(name, *args, **kwargs):
        asked.append(name)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, 0))]

    monkeypatch.setattr(links.socket, "getaddrinfo", getaddrinfo)
    assert links.fetch_link(f"http://{host}/") is None
    assert net["requested"] == [] and asked == []


def test_a_numeric_looking_domain_name_is_still_a_name(net):
    net["pages"]["https://123.example.com/"] = FakeResponse(body=b"<p>ok</p>")
    assert links.fetch_link("https://123.example.com/") is not None


def _broken_reads():
    from urllib3.exceptions import DecodeError, IncompleteRead, ProtocolError, ReadTimeoutError

    return [
        ProtocolError("Connection broken", IncompleteRead(8, 992)),
        ReadTimeoutError(None, "/", "Read timed out."),  # pyright: ignore[reportArgumentType]
        DecodeError("Received response with content-encoding: gzip, but failed to decode it."),
    ]


class _BrokenPage:
    status_code = 200
    headers = {"Content-Type": "text/html"}

    def __init__(self, error: Exception):
        error_to_raise = error

        class Raw:
            def read1(self, n, decode_content=True):
                raise error_to_raise

        self.raw = Raw()

    def close(self):
        pass


@pytest.mark.parametrize("error", _broken_reads(), ids=["short-body", "stall", "bad-gzip"])
def test_a_broken_page_body_is_refused_not_raised(monkeypatch, error):
    # urllib3's own read errors are a Refused with the error's name, like requests' errors
    monkeypatch.setattr(links, "get_vetted", lambda url, deadline: _BrokenPage(error))
    with pytest.raises(links.Refused, match=type(error).__name__):
        links._fetch("https://example.com/", time.monotonic() + 10)
