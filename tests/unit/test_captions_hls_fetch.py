"""download_captions on an HLS caption playlist (X): recorded fixtures, fully offline."""

import io
import socket
from pathlib import Path

import pytest

from skipwatch.adapters.base import IngestOptions
from skipwatch.captions import parse_file
from skipwatch.providers import content_free as cf
from skipwatch.providers import links
from skipwatch.workdir import WorkDir

REC = Path(__file__).resolve().parents[1] / "fixtures" / "recorded" / "x"
PLAYLIST_URL = "https://video.twimg.com/amplify_video/2100714561389129730/pl/s0/DMUX4.m3u8"
SEGMENT_URL = (
    "https://video.twimg.com/subtitles/amplify_video/2100714561389129730/0/JWjpF_z1GMS3dPwx.vtt"
)
INFO = {
    "id": "2100714561389129730",
    "subtitles": {"en": [{"url": PLAYLIST_URL, "ext": "vtt", "protocol": "m3u8_native"}]},
}


class _Resp:
    def __init__(self, body: bytes, url: str):
        self._body, self.url = body, url

    def read(self):
        return self._body


def _ydl_serving(body: bytes, url: str):
    class DL:
        def __init__(self, params):
            self.params = params

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def urlopen(self, request):
            assert request.url == PLAYLIST_URL
            return _Resp(body, url)

    return DL


class _Raw:
    def __init__(self, body: bytes):
        self._io = io.BytesIO(body)

    def read1(self, n, decode_content=True):
        return self._io.read(n)


class _Vetted:
    def __init__(self, body: bytes, status: int = 200):
        self.status_code, self.raw, self.headers = status, _Raw(body), {}
        self.closed = False

    def close(self):
        self.closed = True


@pytest.fixture
def x_playlist(monkeypatch):
    playlist = (REC / "captions-hls.m3u8").read_bytes()
    monkeypatch.setattr(cf.yt_dlp, "YoutubeDL", _ydl_serving(playlist, PLAYLIST_URL))
    monkeypatch.setattr(cf, "js_runtime", lambda: {})


def _serve_segments(monkeypatch, bodies: dict[str, _Vetted]) -> list[str]:
    fetched: list[str] = []

    def get_vetted(url, deadline):
        fetched.append(url)
        return bodies[url]

    monkeypatch.setattr(links, "get_vetted", get_vetted)
    return fetched


def test_an_x_caption_playlist_is_resolved_into_parseable_webvtt(tmp_path, monkeypatch, x_playlist):
    segment = _Vetted((REC / "captions-hls.segment.vtt").read_bytes())
    fetched = _serve_segments(monkeypatch, {SEGMENT_URL: segment})
    work = WorkDir(tmp_path / "w")
    work.ensure()
    got = cf.download_captions(INFO, work, IngestOptions(), ("en", "manual"))
    assert got == ("captions/2100714561389129730.en.vtt", "en", "manual")
    assert fetched == [SEGMENT_URL]  # the segment went through the vetted transport
    assert segment.closed
    segs = parse_file(work.path / got[0])
    assert len(segs) == 6
    assert (segs[0].start, segs[0].text) == (0.12, "Yesterday")


def test_segment_urls_resolve_against_the_url_the_playlist_came_from(tmp_path, monkeypatch):
    # After a redirect, a relative segment path belongs to the final playlist URL.
    moved = "https://cdn2.example/subs/pl/index.m3u8"
    playlist = b"#EXTM3U\n#EXTINF:6,\nseg0.vtt\n#EXT-X-ENDLIST\n"
    monkeypatch.setattr(cf.yt_dlp, "YoutubeDL", _ydl_serving(playlist, moved))
    monkeypatch.setattr(cf, "js_runtime", lambda: {})
    body = b"WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhi\n"
    fetched = _serve_segments(monkeypatch, {"https://cdn2.example/subs/pl/seg0.vtt": _Vetted(body)})
    cf.download_captions(INFO, WorkDir(tmp_path), IngestOptions(), ("en", "manual"))
    assert fetched == ["https://cdn2.example/subs/pl/seg0.vtt"]


def test_a_segment_on_a_private_address_is_refused(tmp_path, monkeypatch, x_playlist):
    # The real guard: video.twimg.com "resolving" to loopback is never fetched.
    def resolve(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr(links.socket, "getaddrinfo", resolve)
    with pytest.raises(cf.FreeRouteError, match="private or local address") as e:
        cf.download_captions(INFO, WorkDir(tmp_path), IngestOptions(), ("en", "manual"))
    assert e.value.op == "captions"
    assert not (tmp_path / "captions").exists()


def test_segments_over_the_size_cap_are_refused(tmp_path, monkeypatch, x_playlist):
    monkeypatch.setattr(cf, "MAX_CAPTION_BYTES", 100)
    segment = _Vetted((REC / "captions-hls.segment.vtt").read_bytes())
    _serve_segments(monkeypatch, {SEGMENT_URL: segment})
    with pytest.raises(cf.FreeRouteError, match="cap"):
        cf.download_captions(INFO, WorkDir(tmp_path), IngestOptions(), ("en", "manual"))
    assert segment.closed


def test_a_failed_segment_is_a_captions_error(tmp_path, monkeypatch, x_playlist):
    _serve_segments(monkeypatch, {SEGMENT_URL: _Vetted(b"gone", status=404)})
    with pytest.raises(cf.FreeRouteError, match="HTTP 404"):
        cf.download_captions(INFO, WorkDir(tmp_path), IngestOptions(), ("en", "manual"))


def test_a_master_playlist_is_a_captions_error(tmp_path, monkeypatch):
    playlist = b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nvideo.m3u8\n"
    monkeypatch.setattr(cf.yt_dlp, "YoutubeDL", _ydl_serving(playlist, PLAYLIST_URL))
    monkeypatch.setattr(cf, "js_runtime", lambda: {})
    with pytest.raises(cf.FreeRouteError, match="master playlist"):
        cf.download_captions(INFO, WorkDir(tmp_path), IngestOptions(), ("en", "manual"))
