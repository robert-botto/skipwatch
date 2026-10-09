"""The link transport against a local HTTP server (127.0.0.1 only; nothing external).

The autouse socket guard blocks every connection; `loopback` re-allows connections to
127.0.0.1 alone and installs a fake resolver, so these tests see exactly where SkipWatch
connects. A connection anywhere else raises NetworkBlocked, which the fetch logs and skips.
"""

import socket
import socketserver
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from skipwatch.models import ProviderCall
from skipwatch.providers import links

_REAL_CONNECT = socket.socket.connect  # captured at import, before the per-test guard
_REAL_GETADDRINFO = socket.getaddrinfo
PUBLIC_IP = "93.184.215.14"


class Handler(BaseHTTPRequestHandler):
    server: "LocalServer"

    def _serve(self, with_body: bool) -> None:
        self.server.hits.append((self.command, self.path, dict(self.headers)))
        route = self.server.routes.get(self.path, (200, {"Content-Type": "text/plain"}, b"ok"))
        status, headers, body = route
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not with_body:
            return
        if self.server.dribble_s:
            for byte in body:
                try:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                except OSError:
                    return
                time.sleep(self.server.dribble_s)
        else:
            self.wfile.write(body)

    def do_GET(self) -> None:
        self._serve(True)

    def do_HEAD(self) -> None:
        self._serve(False)

    def log_message(self, *args) -> None:
        pass


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    hits: list
    routes: dict
    dribble_s: float = 0.0


@pytest.fixture
def server():
    srv = LocalServer(("127.0.0.1", 0), Handler)
    srv.hits, srv.routes = [], {}
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def loopback(monkeypatch):
    """Connections only to 127.0.0.1; hostnames resolve through `answers` (a list per host,
    consumed in order, the last answer repeating); IP literals resolve to themselves."""
    answers: dict[str, list[str]] = {}
    asked: list[str] = []

    def connect(sock, address):
        if address[0] != "127.0.0.1":
            raise RuntimeError(f"blocked connection to {address[0]}")
        return _REAL_CONNECT(sock, address)

    def getaddrinfo(host, port, *args, **kwargs):
        asked.append(host)
        try:
            address = _REAL_GETADDRINFO(host, port, socket.AF_INET, socket.SOCK_STREAM, 0,
                                        socket.AI_NUMERICHOST)[0][4][0]  # fmt: skip
        except socket.gaierror:
            queue = answers[host]
            address = queue.pop(0) if len(queue) > 1 else queue[0]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port or 0))]

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    return answers, asked


def trust_loopback(monkeypatch):
    """Let 127.0.0.1 pass the public-address check, to test what happens after it."""
    real = links._is_public
    monkeypatch.setattr(links, "_is_public", lambda a: a == "127.0.0.1" or real(a))


# ---- DNS rebinding: the vetted address is the one connected to ----


def test_rebinding_after_the_check_never_reaches_the_local_server(server, loopback):
    answers, asked = loopback
    answers["rebind.test"] = [PUBLIC_IP, "127.0.0.1"]
    port = server.server_address[1]
    calls: list[ProviderCall] = []
    assert links.fetch_link(f"http://rebind.test:{port}/secret", calls) is None
    assert server.hits == []
    assert asked.count("rebind.test") == 1  # resolved once, by the check


def test_rebinding_on_a_redirect_hop_never_reaches_the_local_server(server, loopback, monkeypatch):
    answers, _ = loopback
    trust_loopback(monkeypatch)
    port = server.server_address[1]
    answers["start.test"] = ["127.0.0.1"]
    answers["evil.test"] = [PUBLIC_IP, "127.0.0.1"]
    server.routes["/start"] = (302, {"Location": f"http://evil.test:{port}/secret"}, b"")
    assert links.fetch_link(f"http://start.test:{port}/start") is None
    assert [path for _, path, _ in server.hits] == ["/start"]


def test_resolve_head_is_pinned_too(server, loopback):
    answers, _ = loopback
    answers["short.test"] = [PUBLIC_IP, "127.0.0.1"]
    port = server.server_address[1]
    assert links.resolve(f"http://short.test:{port}/abc") is None
    assert server.hits == []


def test_pinned_request_keeps_the_hostname_in_the_host_header(server, loopback, monkeypatch):
    answers, _ = loopback
    trust_loopback(monkeypatch)
    answers["docs.test"] = ["127.0.0.1"]
    port = server.server_address[1]
    server.routes["/readme"] = (200, {"Content-Type": "text/plain"}, b"hello docs")
    got = links.fetch_link(f"http://docs.test:{port}/readme")
    assert got is not None and got.text == "hello docs"
    assert server.hits[0][2]["Host"] == f"docs.test:{port}"


def test_transport_works_after_yt_dlp_patched_requests(server, loopback, monkeypatch):
    """yt-dlp replaces requests.adapters.select_proxy on import (ingest always imports it);
    its version needs a proxies dict, so the transport must always pass one."""
    import yt_dlp.networking._requests  # noqa: F401

    answers, _ = loopback
    trust_loopback(monkeypatch)
    answers["docs.test"] = ["127.0.0.1"]
    port = server.server_address[1]
    got = links.fetch_link(f"http://docs.test:{port}/readme")
    assert got is not None and got.text == "ok"


# ---- no credentials, proxies or cookies from the user's environment ----


def test_netrc_and_proxy_env_never_reach_a_linked_host(server, loopback, monkeypatch, tmp_path):
    answers, _ = loopback
    trust_loopback(monkeypatch)
    answers["docs.test"] = ["127.0.0.1"]
    port = server.server_address[1]
    netrc = tmp_path / ".netrc"
    netrc.write_text("machine docs.test login someone password hunter2\n", encoding="utf-8")
    netrc.chmod(0o600)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("NETRC", str(netrc))
    monkeypatch.setenv("HTTP_PROXY", "http://10.0.0.1:3128")
    monkeypatch.setenv("http_proxy", "http://10.0.0.1:3128")
    got = links.fetch_link(f"http://docs.test:{port}/readme")
    assert got is not None  # went direct: the proxy address would have been blocked
    assert links.resolve(f"http://docs.test:{port}/readme") is None  # a 200, not a redirect
    assert len(server.hits) == 2
    for _, _, headers in server.hits:
        lowered = {k.lower() for k in headers}
        assert "authorization" not in lowered and "cookie" not in lowered
        assert "proxy-authorization" not in lowered


# ---- wall-clock limits: a server dribbling bytes cannot hold a run ----


def test_slow_server_is_cut_off_at_the_link_deadline(server, loopback, monkeypatch):
    answers, _ = loopback
    trust_loopback(monkeypatch)
    monkeypatch.setattr(links, "LINK_DEADLINE_S", 1.0)
    answers["slow.test"] = ["127.0.0.1"]
    server.dribble_s = 0.5  # one byte every half second; each read beats the socket timeout
    server.routes["/slow"] = (200, {"Content-Type": "text/plain"}, b"x" * 40)
    port = server.server_address[1]
    calls: list[ProviderCall] = []
    started = time.monotonic()
    assert links.fetch_link(f"http://slow.test:{port}/slow", calls) is None
    assert time.monotonic() - started < 3
    assert calls[0].error and "deadline" in calls[0].error


def test_post_budget_spans_every_link_and_head(server, loopback, monkeypatch):
    answers, _ = loopback
    trust_loopback(monkeypatch)
    monkeypatch.setattr(links, "LINK_DEADLINE_S", 1.0)
    monkeypatch.setattr(links, "POST_BUDGET_S", 1.5)
    server.dribble_s = 0.5
    port = server.server_address[1]
    for n in range(4):
        answers[f"s{n}.test"] = ["127.0.0.1"]
        server.routes[f"/{n}"] = (200, {"Content-Type": "text/plain"}, b"x" * 40)
    text = " ".join(f"http://s{n}.test:{port}/{n}" for n in range(4))
    calls: list[ProviderCall] = []
    started = time.monotonic()
    assert links.fetch_all(text, calls) == []
    assert time.monotonic() - started < 3.5
    assert len(calls) == 4 and not any(c.ok for c in calls)
    assert "budget" in (calls[-1].error or "")
    assert len(server.hits) <= 2


def test_requests_send_a_generic_user_agent(server, loopback, monkeypatch):
    answers, _ = loopback
    trust_loopback(monkeypatch)
    answers["docs.test"] = ["127.0.0.1"]
    port = server.server_address[1]
    assert links.fetch_link(f"http://docs.test:{port}/readme") is not None
    links.resolve(f"http://docs.test:{port}/readme")
    agents = {headers.get("User-Agent") for _, _, headers in server.hits}
    assert agents == {"Mozilla/5.0 (compatible; SkipWatch link reader)"}


def test_a_cookie_set_on_a_redirect_is_never_sent_back(server, loopback, monkeypatch):
    answers, _ = loopback
    trust_loopback(monkeypatch)
    answers["docs.test"] = ["127.0.0.1"]
    port = server.server_address[1]
    server.routes["/start"] = (302, {"Location": "/readme", "Set-Cookie": "sid=abc; Path=/"}, b"")
    assert links.fetch_link(f"http://docs.test:{port}/start") is not None
    assert links.fetch_link(f"http://docs.test:{port}/readme") is not None
    assert [path for _, path, _ in server.hits] == ["/start", "/readme", "/readme"]
    assert all("Cookie" not in headers for _, _, headers in server.hits)


# ---- the deadline covers the connection itself: headers trickled byte by byte ----


class TrickleHeaders(socketserver.BaseRequestHandler):
    """Sends a status line and endless header bytes, one every 0.2 s (review-m3b/slow.py)."""

    def handle(self):
        sock = self.request
        sock.recv(4096)
        try:
            for byte in b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nX-Pad: " + b"a" * 40:
                sock.sendall(bytes([byte]))
                time.sleep(0.2)
        except OSError:
            pass


@pytest.fixture
def trickle():
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), TrickleHeaders)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def short_deadline(loopback, monkeypatch):
    answers, _ = loopback
    trust_loopback(monkeypatch)
    monkeypatch.setattr(links, "LINK_DEADLINE_S", 1.0)
    for host in ("hdr.test", "h0.test", "h1.test", "h2.test"):
        answers[host] = ["127.0.0.1"]


def test_header_trickle_is_cut_at_the_link_deadline(trickle, short_deadline):
    calls: list[ProviderCall] = []
    started = time.monotonic()
    assert links.fetch_link(f"http://hdr.test:{trickle}/", calls) is None
    assert time.monotonic() - started < 2.5
    assert calls[0].error and "deadline" in calls[0].error


def test_resolve_head_with_trickled_headers_is_cut_at_the_deadline(trickle, short_deadline):
    calls: list[ProviderCall] = []
    started = time.monotonic()
    assert links.resolve(f"http://hdr.test:{trickle}/", calls) is None
    assert time.monotonic() - started < 2.5
    assert calls[0].error and "deadline" in calls[0].error


def test_post_budget_holds_against_three_header_trickles(trickle, short_deadline, monkeypatch):
    monkeypatch.setattr(links, "POST_BUDGET_S", 1.5)
    urls = [f"http://h{n}.test:{trickle}/" for n in range(3)]
    calls: list[ProviderCall] = []
    started = time.monotonic()
    assert links.fetch_urls(urls, calls) == []
    assert time.monotonic() - started < 3
    assert "budget" in (calls[-1].error or "")


def test_every_pinned_adapter_is_closed(server, loopback, monkeypatch):
    """Each request's adapter and its pool are closed: on success, on a redirect hop, on a
    HEAD, on an error status and on a skipped content type."""
    answers, _ = loopback
    trust_loopback(monkeypatch)
    answers["docs.test"] = ["127.0.0.1"]
    port = server.server_address[1]
    server.routes["/hop"] = (302, {"Location": "/readme"}, b"")
    server.routes["/gone"] = (404, {"Content-Type": "text/plain"}, b"no")
    server.routes["/img"] = (200, {"Content-Type": "image/png"}, b"\x89PNG")
    opened, closed = [], []
    real_init, real_close = links._PinnedAdapter.__init__, links._PinnedAdapter.close

    def init(self, *args, **kwargs):
        opened.append(self)
        real_init(self, *args, **kwargs)

    def close(self):
        closed.append(self)
        real_close(self)

    monkeypatch.setattr(links._PinnedAdapter, "__init__", init)
    monkeypatch.setattr(links._PinnedAdapter, "close", close)
    base = f"http://docs.test:{port}"
    assert links.fetch_link(f"{base}/hop") is not None
    assert links.resolve(f"{base}/hop") == f"{base}/readme"
    assert links.fetch_link(f"{base}/gone") is None
    assert links.fetch_link(f"{base}/img") is None
    assert len(opened) == 5
    assert {id(a) for a in opened} <= {id(a) for a in closed}


V6_PUBLIC = "2606:2800:21f:cb07:6820:80da:af6b:8b2c"


@pytest.fixture
def dual_stack(monkeypatch):
    """dual.test resolves to [a public IPv6, 127.0.0.1]; IPv6 refuses to connect, as on a
    v4-only network. Connections go to 127.0.0.1 only."""
    connected: list[str] = []

    def connect(sock, address):
        connected.append(address[0])
        if address[0] != "127.0.0.1":
            raise ConnectionRefusedError(61, "Connection refused")
        return _REAL_CONNECT(sock, address)

    def getaddrinfo(host, port, *args, **kwargs):
        if host == "dual.test":
            return [
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", (V6_PUBLIC, port or 0, 0, 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port or 0)),
            ]
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        sockaddr = (host, port or 0, 0, 0) if family == socket.AF_INET6 else (host, port or 0)
        return [(family, socket.SOCK_STREAM, 6, "", sockaddr)]

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    trust_loopback(monkeypatch)
    return connected


def test_an_unreachable_first_address_falls_back_to_the_next_vetted_one(server, dual_stack):
    port = server.server_address[1]
    got = links.fetch_link(f"http://dual.test:{port}/readme")
    assert got is not None and got.text == "ok"
    assert dual_stack == [V6_PUBLIC, "127.0.0.1"]
    assert links.resolve(f"http://dual.test:{port}/readme") is None  # a 200: no redirect
    assert len(server.hits) == 2


def test_every_address_is_vetted_before_any_fallback(server, dual_stack, monkeypatch):
    """A host is fetched only when ALL its addresses are public; the fallback never widens
    that to a private second address."""
    monkeypatch.setattr(links, "_is_public", lambda a: a == V6_PUBLIC)
    port = server.server_address[1]
    assert links.fetch_link(f"http://dual.test:{port}/readme") is None
    assert dual_stack == [] and server.hits == []


# ---- HTTPS: the same watchdog after urllib3 wraps (and detaches) the socket ----

TLS = Path(__file__).resolve().parents[1] / "fixtures" / "tls"
TLS_CERT = str(TLS / "tls-test.crt")  # self-signed for tls.test, test use only


class TlsServer(socketserver.BaseRequestHandler):
    """mode "ok": a normal HTTPS answer; "hdr": full TLS, then headers one byte every 0.2 s;
    "hs": a TLS record header and junk one byte every 0.2 s, so the handshake never ends."""

    def handle(self):
        sock, mode = self.request, self.server.mode  # type: ignore[attr-defined]
        try:
            if mode == "hs":
                sock.recv(4096)
                for byte in b"\x16\x03\x03\x40\x00" + b"\x02" * 60:
                    sock.sendall(bytes([byte]))
                    time.sleep(0.2)
                return
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(TLS_CERT, str(TLS / "tls-test.key"))
            tls = context.wrap_socket(sock, server_side=True)
            tls.recv(4096)
            if mode == "ok":
                tls.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 8\r\n"
                    b"Connection: close\r\n\r\nover tls"
                )
                return
            for byte in b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nX-Pad: " + b"a" * 60:
                tls.sendall(bytes([byte]))
                time.sleep(0.2)
        except (OSError, ssl.SSLError):
            pass


@pytest.fixture
def tls_server(loopback, monkeypatch):
    answers, _ = loopback
    trust_loopback(monkeypatch)
    answers["tls.test"] = ["127.0.0.1"]
    monkeypatch.setattr(links, "CA_BUNDLE", TLS_CERT)  # trust the test CA for this test only
    monkeypatch.setattr(links, "LINK_DEADLINE_S", 1.0)
    servers = []

    def start(mode: str) -> int:
        srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), TlsServer)
        srv.daemon_threads = True
        srv.mode = mode  # type: ignore[attr-defined]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return srv.server_address[1]

    yield start
    for srv in servers:
        srv.shutdown()
        srv.server_close()


def test_https_works_through_the_pinned_transport_with_verification(tls_server, monkeypatch):
    port = tls_server("ok")
    got = links.fetch_link(f"https://tls.test:{port}/")
    assert got is not None and got.text == "over tls"
    monkeypatch.setattr(links, "CA_BUNDLE", True)  # default trust: the test CA is unknown
    calls: list[ProviderCall] = []
    assert links.fetch_link(f"https://tls.test:{tls_server('ok')}/", calls) is None
    assert calls[0].error == "SSLError"


def test_https_header_trickle_is_cut_at_the_deadline(tls_server, caplog):
    port = tls_server("hdr")
    for call in (links.fetch_link, links.resolve):
        calls: list[ProviderCall] = []
        started = time.monotonic()
        assert call(f"https://tls.test:{port}/", calls) is None
        assert time.monotonic() - started < 2.5, call.__name__
        assert calls[0].error and "deadline" in calls[0].error
    assert not [r for r in caplog.records if r.name == links.__name__]


def test_tls_handshake_trickle_is_cut_by_the_watchdog(tls_server, monkeypatch):
    """Socket timeouts are held at the full 10 s here (CPython bounds a whole handshake by
    it), far above the 1 s deadline, so only the watchdog can end the handshake on time."""

    def full_socket_timeout(deadline):
        if deadline <= time.monotonic():
            raise links.Refused(links._deadline_message())
        return links.TIMEOUT_S

    monkeypatch.setattr(links, "_timeout", full_socket_timeout)
    port = tls_server("hs")
    for call in (links.fetch_link, links.resolve):
        calls: list[ProviderCall] = []
        started = time.monotonic()
        assert call(f"https://tls.test:{port}/", calls) is None
        assert time.monotonic() - started < 2.5, call.__name__
        assert calls[0].error and "deadline" in calls[0].error
