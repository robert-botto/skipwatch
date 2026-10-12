"""The treg media fallback download against a local HTTP server (127.0.0.1 only).

Provider media URLs expire (TikTok, Instagram) and CDNs cut connections, so every way a body
can fail must end as a logged fallback failure (ingest then exits 3 listing the routes), never
as an exception, and must never leave a partial file in media/.
"""

import json
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from skipwatch.adapters.base import IngestOptions
from skipwatch.models import IngestBundle, Route, SourceInfo
from skipwatch.providers import content_treg, links
from skipwatch.workdir import WorkDir
from tests.unit.test_links_transport import loopback, trust_loopback  # noqa: F401

DOT = "·"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: "Server"

    def log_message(self, *args) -> None:
        pass

    def _head(self, status: int, headers: dict[str, str]) -> None:
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()

    def do_GET(self) -> None:
        self.server.hits.append(self.path)
        port = self.server.server_address[1]
        video = {"Content-Type": "video/mp4"}
        try:
            if self.path == "/ok":
                self._head(200, video | {"Content-Length": "1000"})
                self.wfile.write(b"x" * 1000)
            elif self.path == "/redir-metadata":
                self._head(
                    302, {"Location": "http://169.254.169.254/latest", "Content-Length": "0"}
                )
            elif self.path == "/redir-localhost":
                location = f"http://localhost:{port}/ok"
                self._head(302, {"Location": location, "Content-Length": "0"})
            elif self.path == "/expired":
                self._head(403, {"Content-Length": "0"})
            elif self.path == "/big":
                self._head(200, video | {"Content-Length": "5000"})
                self.wfile.write(b"b" * 5000)
            elif self.path == "/truncated":
                self._head(200, video | {"Content-Length": "100000"})
                self.wfile.write(b"y" * 10)
                self.wfile.flush()
                self.connection.shutdown(socket.SHUT_RDWR)
            elif self.path == "/stall":
                self._head(200, video | {"Content-Length": "100000"})
                self.wfile.write(b"q" * 50)
                self.wfile.flush()
                time.sleep(3)
            elif self.path == "/trickle":
                self._head(200, video | {"Transfer-Encoding": "chunked"})
                for _ in range(30):
                    self.wfile.write(b"1\r\nz\r\n")
                    self.wfile.flush()
                    time.sleep(0.1)
                self.wfile.write(b"0\r\n\r\n")
        except OSError:
            pass


class Server(ThreadingHTTPServer):
    daemon_threads = True
    hits: list


@pytest.fixture
def media_server(loopback, monkeypatch):  # noqa: F811
    trust_loopback(monkeypatch)
    srv = Server(("127.0.0.1", 0), Handler)
    srv.hits = []
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def tiktok_runner(media_url: str):
    def runner(argv, **kwargs):
        body = {"output": {"found": True, "data": {"videoUrl": media_url}}, "costUsd": 0.0008}
        stderr = f"treg: charged $0.0008 {DOT} call id 0123456789abcdef\n"
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(body), stderr=stderr)

    return runner


def fallback(tmp_path, monkeypatch, media_url: str, deadline_s: float = 5.0):
    monkeypatch.setattr(content_treg, "_max_cost", lambda: 0.05)
    monkeypatch.setattr(content_treg, "MEDIA_DEADLINE_S", deadline_s)
    work = WorkDir(tmp_path / "w")
    work.ensure()
    bundle = IngestBundle(
        source=SourceInfo(kind="video", platform="tiktok", url="https://www.tiktok.com/@a/video/1"),
        route=Route(context="free"),
    )
    provider = content_treg.TregProvider(runner=tiktok_runner(media_url))
    got = provider.fetch_media(bundle, work, IngestOptions())
    return got, provider._client(work), work


@pytest.mark.parametrize(
    ("path", "deadline_s", "error"),
    [
        ("/truncated", 5.0, "ProtocolError"),
        ("/stall", 1.0, "over the media download deadline"),
        ("/trickle", 1.0, "over the media download deadline"),
    ],
)
def test_broken_bodies_are_a_logged_fallback_failure(
    tmp_path, monkeypatch, media_server, path, deadline_s, error
):
    got, client, work = fallback(tmp_path, monkeypatch, media_server + path, deadline_s)
    assert got is None
    get = next(c for c in client.calls if c.op == "media.get")
    assert not get.ok and get.error is not None and error in get.error
    assert [c.endpoint for c in client.calls if c.op != "media.get"] == [
        "anyapi.tiktok.video_download"
    ]  # the billed call is in the log
    assert list((work.path / "media").glob("*")) == []  # no partial file


# ---- download_media through the real vetted transport (review item 6) ----


def download(url: str, tmp_path) -> None:
    content_treg.download_media(url, tmp_path / "media" / "video.mp4")


def nothing_left(tmp_path) -> bool:
    media = tmp_path / "media"
    return not media.exists() or list(media.iterdir()) == []


def trust_first_check_only(monkeypatch):
    """127.0.0.1 passes the address check once (the URL treg returned), then the real check
    applies, so a redirect to localhost is judged as it would be in production."""
    real = links._is_public
    first = {"left": 1}

    def is_public(address):
        if address == "127.0.0.1" and first["left"]:
            first["left"] -= 1
            return True
        return real(address)

    monkeypatch.setattr(links, "_is_public", is_public)


def test_download_media_fetches_a_plain_video(tmp_path, media_server):
    download(media_server + "/ok", tmp_path)
    assert (tmp_path / "media" / "video.mp4").read_bytes() == b"x" * 1000
    assert not (tmp_path / "media" / "video.mp4.part").exists()


def test_redirect_to_the_metadata_address_is_refused(tmp_path, media_server):
    with pytest.raises(links.Refused, match="private or local"):
        download(media_server + "/redir-metadata", tmp_path)
    assert nothing_left(tmp_path)


def test_redirect_to_localhost_is_refused(tmp_path, loopback, monkeypatch):  # noqa: F811
    answers, _ = loopback
    answers["localhost"] = ["127.0.0.1"]
    srv = Server(("127.0.0.1", 0), Handler)
    srv.hits = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        trust_first_check_only(monkeypatch)
        with pytest.raises(links.Refused, match="private or local"):
            download(f"http://127.0.0.1:{srv.server_address[1]}/redir-localhost", tmp_path)
        assert srv.hits == ["/redir-localhost"]  # the redirect target was never fetched
    finally:
        srv.shutdown()
        srv.server_close()
    assert nothing_left(tmp_path)


def test_expired_url_403_is_refused(tmp_path, media_server):
    with pytest.raises(links.Refused, match="HTTP 403"):
        download(media_server + "/expired", tmp_path)
    assert nothing_left(tmp_path)


def test_size_cap_through_the_real_transport(tmp_path, media_server, monkeypatch):
    monkeypatch.setattr(content_treg, "MEDIA_MAX_BYTES", 1000)
    with pytest.raises(links.Refused, match="cap"):
        download(media_server + "/big", tmp_path)
    assert nothing_left(tmp_path)


def test_deadline_through_the_real_transport(tmp_path, media_server, monkeypatch):
    monkeypatch.setattr(content_treg, "MEDIA_DEADLINE_S", 1.0)
    started = time.monotonic()
    with pytest.raises(links.Refused, match="deadline"):
        download(media_server + "/trickle", tmp_path)
    assert time.monotonic() - started < 3
    assert nothing_left(tmp_path)
