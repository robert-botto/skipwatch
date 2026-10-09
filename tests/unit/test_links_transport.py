"""The link transport against a local HTTP server (127.0.0.1 only; nothing external).

The autouse socket guard blocks every connection; `loopback` re-allows connections to
127.0.0.1 alone and installs a fake resolver, so these tests see exactly where SkipWatch
connects. A connection anywhere else raises NetworkBlocked, which the fetch logs and skips.
"""

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
