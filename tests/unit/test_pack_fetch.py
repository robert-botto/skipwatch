"""fetch_pack over the real SSRF guard in links.py: DNS answers and HTTP replies are faked
below the guard (socket.getaddrinfo and links._send_any), so every hop's address check runs
for real and no socket is ever opened."""

import socket
import types

import pytest

from skipwatch import pack as pack_mod
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.providers import links, pack_fetch
from skipwatch.providers.pack_fetch import fetch_pack

PUBLIC_IP = "93.184.215.14"
CHUNK = 65_536


class FakeRaw:
    def __init__(self, body: bytes | None, endless: bool = False):
        self.body = body or b""
        self.endless = endless
        self.reads = 0

    def read1(self, n: int, decode_content: bool = True) -> bytes:
        self.reads += 1
        if self.endless:
            return b"\0" * n
        chunk, self.body = self.body[:n], self.body[n:]
        return chunk


class FakeResponse:
    def __init__(self, url, status=200, headers=None, body=b"", endless=False):
        self.url = url
        self.status_code = status
        self.headers = headers or {}
        self.raw = FakeRaw(body, endless)
        self.closed = False

    def close(self):
        self.closed = True


@pytest.fixture
def net(monkeypatch):
    """dns: host -> addresses; routes: url -> FakeResponse; sent: (url, addresses) per hop."""
    dns: dict[str, list[str]] = {}
    routes: dict[str, FakeResponse] = {}
    sent: list[tuple[str, list[str]]] = []

    def getaddrinfo(host, port, *args, **kwargs):
        addresses = dns.get(host, [host])
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 0)) for a in addresses]

    def send_any(method, url, addresses, deadline):
        sent.append((url, addresses))
        return routes[url]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(links, "_send_any", send_any)
    return dns, routes, sent


def refused(url, dest, code):
    with pytest.raises(SkipwatchError) as err:
        fetch_pack(url, dest)
    assert err.value.code == code, err.value.message
    return err.value


def test_fetch_pack_writes_the_body_under_dest(tmp_path, net):
    dns, routes, sent = net
    dns["packs.example"] = [PUBLIC_IP]
    url = "https://packs.example/a/run-x.skillpack.zip"
    routes[url] = FakeResponse(url, body=b"PK pack bytes")
    got = fetch_pack(url, tmp_path)
    assert got == tmp_path / "run-x.skillpack.zip" and got.read_bytes() == b"PK pack bytes"
    assert sent == [(url, [PUBLIC_IP])] and routes[url].closed
    assert sorted(p.name for p in tmp_path.iterdir()) == ["run-x.skillpack.zip"]


def test_fetch_pack_odd_names_become_download(tmp_path, net):
    dns, routes, _ = net
    dns["packs.example"] = [PUBLIC_IP]
    for url in (
        "https://packs.example/get?id=7",
        "https://packs.example/..%2F..%2Fx.skillpack.zip",
    ):
        routes[url] = FakeResponse(url, body=b"PK")
        assert fetch_pack(url, tmp_path) == tmp_path / "download.skillpack.zip"


def test_fetch_pack_caps_bytes_and_refuses_private_hosts(tmp_path, net, monkeypatch):
    dns, routes, sent = net
    for host in ("127.0.0.1", "10.0.0.5"):
        err = refused(f"https://{host}/a.skillpack.zip", tmp_path, ExitCode.DOWNLOAD_FAILED)
        assert "private or local address" in err.message
    dns["lan.example"] = ["192.168.1.2"]
    err = refused("https://lan.example/a.skillpack.zip", tmp_path, ExitCode.DOWNLOAD_FAILED)
    assert "private or local address" in err.message
    assert sent == []  # nothing was ever sent to a private address

    dns["hop.example"] = [PUBLIC_IP]
    dns["localhost"] = ["127.0.0.1"]
    hop = "https://hop.example/a.skillpack.zip"
    routes[hop] = FakeResponse(hop, status=302, headers={"Location": "http://localhost/"})
    err = refused(hop, tmp_path, ExitCode.DOWNLOAD_FAILED)
    assert "private or local address" in err.message
    assert [url for url, _ in sent] == [hop] and routes[hop].raw.reads == 0

    endless = "https://hop.example/endless.skillpack.zip"
    routes[endless] = FakeResponse(endless, endless=True)
    monkeypatch.setattr(pack_mod, "MAX_PACK_BYTES", 10 * CHUNK)
    err = refused(endless, tmp_path, ExitCode.PACK_INTEGRITY)
    assert "too large" in err.message
    assert routes[endless].raw.reads <= 11 and routes[endless].closed
    assert list(tmp_path.iterdir()) == []  # no partial file is left

    big = "https://hop.example/big.skillpack.zip"
    routes[big] = FakeResponse(big, headers={"Content-Length": str(11 * CHUNK)})
    assert "too large" in refused(big, tmp_path, ExitCode.PACK_INTEGRITY).message
    assert routes[big].raw.reads == 0


def test_fetch_pack_stops_a_trickling_body_at_the_deadline(tmp_path, net, monkeypatch):
    dns, routes, _ = net
    dns["slow.example"] = [PUBLIC_IP]
    url = "https://slow.example/slow.skillpack.zip"
    clock = [0.0]

    class Trickle(FakeRaw):
        def read1(self, n: int, decode_content: bool = True) -> bytes:
            self.reads += 1
            clock[0] += 50.0  # each byte takes 50 s
            return b"x"

    routes[url] = FakeResponse(url)
    routes[url].raw = Trickle(None)
    monkeypatch.setattr(pack_fetch, "time", types.SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(pack_mod, "MAX_PACK_BYTES", 10)  # without the deadline: too large
    err = refused(url, tmp_path, ExitCode.DOWNLOAD_FAILED)
    assert "deadline" in err.message
    assert clock[0] <= pack_fetch.DEADLINE_S + 50.0 and routes[url].closed
    assert list(tmp_path.iterdir()) == []  # no .part file is left


def test_fetch_pack_refuses_a_redirect_off_https(tmp_path, net):
    dns, routes, _ = net
    dns["hop.example"] = [PUBLIC_IP]
    dns["plain.example"] = [PUBLIC_IP]
    hop = "https://hop.example/a.skillpack.zip"
    plain = "http://plain.example/a.skillpack.zip"
    routes[hop] = FakeResponse(hop, status=301, headers={"Location": plain})
    routes[plain] = FakeResponse(plain, body=b"PK")
    err = refused(hop, tmp_path, ExitCode.DOWNLOAD_FAILED)
    assert "https" in err.message and routes[plain].raw.reads == 0


def test_fetch_pack_github_blob_becomes_raw(tmp_path, net):
    dns, routes, sent = net
    dns["raw.githubusercontent.com"] = [PUBLIC_IP]
    raw = "https://raw.githubusercontent.com/someone/skills/main/packs/run-x.skillpack.zip"
    routes[raw] = FakeResponse(raw, body=b"PK")
    got = fetch_pack(
        "https://github.com/someone/skills/blob/main/packs/run-x.skillpack.zip", tmp_path
    )
    assert [url for url, _ in sent] == [raw] and got.name == "run-x.skillpack.zip"


def test_fetch_pack_http_status_is_exit_3(tmp_path, net):
    dns, routes, _ = net
    dns["packs.example"] = [PUBLIC_IP]
    url = "https://packs.example/gone.skillpack.zip"
    routes[url] = FakeResponse(url, status=404)
    assert "404" in refused(url, tmp_path, ExitCode.DOWNLOAD_FAILED).message
    assert routes[url].closed


def test_fetch_pack_http_scheme_is_exit_2(tmp_path, net):
    _, _, sent = net
    for url in ("http://packs.example/a.skillpack.zip", "file:///etc/passwd", "ftp://x/a"):
        assert "https" in refused(url, tmp_path, ExitCode.UNSUPPORTED_SOURCE).message
    assert sent == []
