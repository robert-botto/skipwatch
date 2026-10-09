import json
from pathlib import Path

import pytest

from skipwatch.adapters.base import IngestOptions
from skipwatch.errors import ExitCode
from skipwatch.models import MediaInfo
from skipwatch.providers import content_free as cf
from skipwatch.workdir import WorkDir

REC = Path(__file__).resolve().parents[1] / "fixtures" / "recorded"


def test_r_ing_5_node_22_is_passed_explicitly(monkeypatch):
    monkeypatch.setattr(cf.shutil, "which", lambda n: "/usr/bin/node" if n == "node" else None)
    monkeypatch.setattr(cf, "_version_of", lambda path: "v25.4.0")
    assert cf.js_runtime() == {"node": {"path": "/usr/bin/node"}}


def test_r_ing_5_old_node_and_no_deno_means_no_runtime(monkeypatch):
    monkeypatch.setattr(cf.shutil, "which", lambda n: "/usr/bin/node" if n == "node" else None)
    monkeypatch.setattr(cf, "_version_of", lambda path: "v20.11.0")
    assert cf.js_runtime() == {}  # explicit empty dict: yt-dlp would otherwise default to deno


def test_r_ing_5_deno_when_node_is_too_old(monkeypatch):
    paths = {"node": "/usr/bin/node", "deno": "/opt/deno"}
    versions = {"/usr/bin/node": "v18.0.0", "/opt/deno": "deno 2.3.1 (stable, release)"}
    monkeypatch.setattr(cf.shutil, "which", paths.get)
    monkeypatch.setattr(cf, "_version_of", versions.get)
    assert cf.js_runtime() == {"deno": {"path": "/opt/deno"}}


def test_r_ing_5_deno_below_2_3_is_not_used(monkeypatch):
    monkeypatch.setattr(cf.shutil, "which", lambda n: "/opt/deno" if n == "deno" else None)
    monkeypatch.setattr(cf, "_version_of", lambda path: "deno 2.2.9")
    assert cf.js_runtime() == {}


def test_r_ing_5_unreadable_node_version_is_skipped(monkeypatch):
    monkeypatch.setattr(cf.shutil, "which", lambda n: "/usr/bin/node" if n == "node" else None)
    monkeypatch.setattr(cf, "_version_of", lambda path: None)
    assert cf.js_runtime() == {}


def test_r_ing_5_cookies_only_from_the_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(cf, "js_runtime", lambda: {})
    assert "cookiesfrombrowser" not in cf.ydl_params(tmp_path, IngestOptions(), download=False)
    p = cf.ydl_params(tmp_path, IngestOptions(cookies_from_browser="firefox"), download=False)
    assert p["cookiesfrombrowser"] == ("firefox",)
    assert "remote_components" not in p


def test_ydl_params_always_pass_js_runtimes_and_download_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(cf, "js_runtime", lambda: {})
    monkeypatch.setattr(
        cf.media, "ffmpeg_paths", lambda: (Path("/x/bin/ffmpeg"), Path("/x/bin/ffprobe"))
    )
    p = cf.ydl_params(tmp_path, IngestOptions(), download=False)
    assert p["js_runtimes"] == {} and p["noplaylist"] is True and "paths" not in p
    d = cf.ydl_params(tmp_path, IngestOptions(), download=True)
    assert d["paths"] == {"home": str(tmp_path / "media")} and d["outtmpl"] == "video.%(ext)s"
    assert d["ffmpeg_location"] == str(Path("/x/bin")) and d["merge_output_format"] == "mp4"


@pytest.mark.parametrize(
    "msg,code",
    [
        (
            "ERROR: [youtube] x: Private video. Sign in if you've been granted access to this "
            "video. Use --cookies-from-browser or --cookies for the authentication.",
            ExitCode.PRIVATE_CONTENT,
        ),
        (
            "ERROR: [twitter] 1: You are not authorized to view this protected tweet. "
            "Use --cookies, --cookies-from-browser, ...",
            ExitCode.PRIVATE_CONTENT,
        ),
        (
            "ERROR: [Instagram] abc: Requested content is not available, rate-limit reached or "
            "login required. Use --cookies-from-browser or --cookies for the authentication.",
            ExitCode.PRIVATE_CONTENT,
        ),
        ("ERROR: [youtube] x: This video is private", ExitCode.PRIVATE_CONTENT),
        ("ERROR: [twitter] 1: No video could be found in this tweet", ExitCode.NO_CONTENT),
        (
            "ERROR: unable to download video data: HTTP Error 403: Forbidden",
            ExitCode.DOWNLOAD_FAILED,
        ),
    ],
)
def test_r_ing_6_error_classification(msg, code):
    assert cf.classify_error(msg) == code


class FakeDL:
    """Stands in for yt_dlp.YoutubeDL; records the params it was built with."""

    instances: list["FakeDL"] = []
    info: dict = {}
    error: str | None = None

    def __init__(self, params):
        self.params = params
        FakeDL.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        if FakeDL.error:
            raise cf.yt_dlp.utils.DownloadError(FakeDL.error)
        assert download is False
        return dict(FakeDL.info, original_url=url)

    @staticmethod
    def sanitize_info(info):
        return info


@pytest.fixture
def fake_dl(monkeypatch):
    FakeDL.instances, FakeDL.info, FakeDL.error = [], {}, None
    monkeypatch.setattr(cf.yt_dlp, "YoutubeDL", FakeDL)
    monkeypatch.setattr(cf, "js_runtime", lambda: {})
    return FakeDL


def test_extract_returns_the_info_without_downloading(fake_dl):
    fake_dl.info = {"id": "abc", "title": "T"}
    info = cf.extract("https://www.youtube.com/watch?v=abc", IngestOptions())
    assert info["title"] == "T"
    assert fake_dl.instances[0].params["skip_download"] is True


def test_extract_error_carries_the_class_and_first_line(fake_dl):
    fake_dl.error = "ERROR: [youtube] x: Private video. Use --cookies-from-browser\nmore detail"
    with pytest.raises(cf.FreeRouteError) as e:
        cf.extract("https://www.youtube.com/watch?v=x", IngestOptions())
    assert e.value.code == ExitCode.PRIVATE_CONTENT
    assert e.value.first_line == "[youtube] x: Private video. Use --cookies-from-browser"


def test_call_log_is_free_and_timed():
    call = cf.call_log("yt-dlp.metadata", False, 0.0, error="boom")
    assert call.provider == "free" and call.cost_usd == 0 and call.ok is False
    assert call.error == "boom" and call.ms >= 0


def test_r_cli_1_existing_download_with_matching_duration_is_reused(tmp_path, monkeypatch):
    work = WorkDir(tmp_path / "w")
    (work.path / "media").mkdir(parents=True)
    (work.path / "media" / "video.mp4").write_bytes(b"x")
    monkeypatch.setattr(
        cf.media,
        "probe",
        lambda p: {
            "format": {"duration": "600.4"},
            "streams": [
                {"codec_type": "video", "width": 1280, "height": 720, "r_frame_rate": "30/1"},
                {"codec_type": "audio"},
            ],
        },
    )

    def boom(params):
        raise AssertionError("must not download again")

    monkeypatch.setattr(cf.yt_dlp, "YoutubeDL", boom)
    info = {
        "duration": 600,
        "formats": [
            {
                "format_id": "18",
                "width": 640,
                "height": 360,
                "vcodec": "avc1",
                "acodec": "mp4a",
                "filesize": 1,
            }
        ],
    }
    got = cf.download(info, work, IngestOptions())
    assert got == MediaInfo(
        path="media/video.mp4", width=1280, height=720, fps=30.0, has_audio=True
    )


def test_download_runs_process_ie_result_with_the_chosen_format(tmp_path, monkeypatch):
    work = WorkDir(tmp_path / "w")
    work.ensure()
    seen = {}

    class DL(FakeDL):
        def process_ie_result(self, info, download=True):
            seen["format"], seen["download"] = self.params["format"], download
            out = Path(self.params["paths"]["home"]) / "video.mp4"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"x")
            return dict(info, requested_downloads=[{"filepath": str(out)}])

    monkeypatch.setattr(cf.yt_dlp, "YoutubeDL", DL)
    monkeypatch.setattr(cf, "js_runtime", lambda: {})
    monkeypatch.setattr(cf.media, "ffmpeg_paths", lambda: (Path("/x/ffmpeg"), Path("/x/ffprobe")))
    monkeypatch.setattr(
        cf.media,
        "probe",
        lambda p: {
            "format": {"duration": "10"},
            "streams": [
                {"codec_type": "video", "width": 1280, "height": 720, "r_frame_rate": "25/1"}
            ],
        },
    )
    info = {
        "duration": 10,
        "formats": [
            {
                "format_id": "22",
                "width": 1280,
                "height": 720,
                "vcodec": "avc1",
                "acodec": "mp4a",
                "filesize": 1,
            }
        ],
    }
    got = cf.download(info, work, IngestOptions())
    assert seen == {"format": "22", "download": True}
    assert got.path == "media/video.mp4" and got.height == 720 and got.has_audio is False


def test_download_error_is_a_free_route_error(tmp_path, monkeypatch):
    class DL(FakeDL):
        def process_ie_result(self, info, download=True):
            raise cf.yt_dlp.utils.DownloadError(
                "ERROR: unable to download video data: HTTP Error 403: Forbidden"
            )

    monkeypatch.setattr(cf.yt_dlp, "YoutubeDL", DL)
    monkeypatch.setattr(cf, "js_runtime", lambda: {})
    monkeypatch.setattr(cf.media, "ffmpeg_paths", lambda: (Path("/x/ffmpeg"), Path("/x/ffprobe")))
    info = {
        "duration": 10,
        "formats": [
            {
                "format_id": "22",
                "width": 1280,
                "height": 720,
                "vcodec": "avc1",
                "acodec": "mp4a",
                "filesize": 1,
            }
        ],
    }
    with pytest.raises(cf.FreeRouteError) as e:
        cf.download(info, WorkDir(tmp_path / "w"), IngestOptions())
    assert e.value.code == ExitCode.DOWNLOAD_FAILED and "HTTP Error 403" in e.value.first_line


def test_download_captions_prefers_json3_and_writes_under_captions(tmp_path, monkeypatch):
    work = WorkDir(tmp_path / "w")
    work.ensure()
    fetched = []

    class DL(FakeDL):
        def urlopen(self, req):
            fetched.append(req.url)

            class Resp:
                def read(self):
                    return b'{"events": []}'

            return Resp()

    monkeypatch.setattr(cf.yt_dlp, "YoutubeDL", DL)
    monkeypatch.setattr(cf, "js_runtime", lambda: {})
    info = {
        "id": "abc",
        "subtitles": {
            "en": [
                {"ext": "vtt", "url": "https://c/vtt"},
                {"ext": "json3", "url": "https://c/json3"},
            ]
        },
    }
    got = cf.download_captions(info, work, IngestOptions(), ("en", "manual"))
    assert got == ("captions/abc.en.json3", "en", "manual")
    assert fetched == ["https://c/json3"]
    assert (work.path / "captions" / "abc.en.json3").read_text() == '{"events": []}'


def test_download_captions_without_a_parseable_format_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(cf, "js_runtime", lambda: {})
    info = {"id": "abc", "automatic_captions": {"en": [{"ext": "ttml", "url": "https://c/t"}]}}
    assert cf.download_captions(info, WorkDir(tmp_path), IngestOptions(), ("en", "auto")) is None


def test_recorded_fixtures_hold_only_scrubbed_urls():
    for path in REC.rglob("*.info.json"):
        info = json.loads(path.read_text())
        for fmt in info.get("formats", []):
            assert "?" not in (fmt.get("url") or ""), path


# ---- R-CLI-1 reuse: only the final merged file, with the right length and streams ----

VIDEO_STREAMS = [
    {"codec_type": "video", "width": 1280, "height": 720, "r_frame_rate": "30/1"},
    {"codec_type": "audio"},
]
AUDIO_STREAMS = [{"codec_type": "audio"}]
INFO = {
    "duration": 600,
    "formats": [
        {"format_id": "398", "width": 1280, "height": 720, "vcodec": "av01", "acodec": "none",
         "filesize": 2},
        {"format_id": "251", "vcodec": "none", "acodec": "opus", "filesize": 1},
    ],
}  # fmt: skip


def media_dir(tmp_path, files: dict[str, tuple[float, list]]):
    work = WorkDir(tmp_path / "w")
    (work.path / "media").mkdir(parents=True)
    for name in files:
        (work.path / "media" / name).write_bytes(b"x")
    return work


def fake_probe(monkeypatch, files):
    def probe(path):
        duration, streams = files[path.name]
        return {"format": {"duration": str(duration)}, "streams": streams}

    monkeypatch.setattr(cf.media, "probe", probe)


def downloader(monkeypatch, calls):
    class DL(FakeDL):
        def process_ie_result(self, info, download=True):
            calls.append(self.params["format"])
            out = Path(self.params["paths"]["home"]) / "video.mp4"
            out.write_bytes(b"new")
            return dict(info, requested_downloads=[{"filepath": str(out)}])

    monkeypatch.setattr(cf.yt_dlp, "YoutubeDL", DL)
    monkeypatch.setattr(cf, "js_runtime", lambda: {})
    monkeypatch.setattr(cf.media, "ffmpeg_paths", lambda: (Path("/x/ffmpeg"), Path("/x/ffprobe")))


def test_r_cli_1_merged_file_wins_over_format_intermediates(tmp_path, monkeypatch):
    files = {
        "video.f251.webm": (600.0, AUDIO_STREAMS),
        "video.f398.mp4": (600.0, VIDEO_STREAMS[:1]),
        "video.mp4": (600.2, VIDEO_STREAMS),
    }
    work = media_dir(tmp_path, files)
    fake_probe(monkeypatch, files)
    downloader(monkeypatch, calls := [])
    assert cf.download(INFO, work, IngestOptions()).path == "media/video.mp4"
    assert calls == []


def test_r_cli_1_intermediates_alone_are_downloaded_again(tmp_path, monkeypatch):
    files = {
        "video.f251.webm": (600.0, AUDIO_STREAMS),
        "video.f398.mp4": (600.0, VIDEO_STREAMS[:1]),
    }
    work = media_dir(tmp_path, files)
    files["video.mp4"] = (600.0, VIDEO_STREAMS)
    fake_probe(monkeypatch, files)
    downloader(monkeypatch, calls := [])
    assert cf.download(INFO, work, IngestOptions()).path == "media/video.mp4"
    assert calls == ["398+251"]


def test_r_cli_1_length_mismatch_is_downloaded_again(tmp_path, monkeypatch):
    work = media_dir(tmp_path, {"video.mp4": (0, [])})

    def probe(path):  # the stale file is 5 minutes long, the new download 10
        duration = "300" if path.read_bytes() == b"x" else "600"
        return {"format": {"duration": duration}, "streams": VIDEO_STREAMS}

    monkeypatch.setattr(cf.media, "probe", probe)
    downloader(monkeypatch, calls := [])
    cf.download(INFO, work, IngestOptions())
    assert calls == ["398+251"]


def test_r_cli_1_audio_only_file_is_not_reused_for_a_video_source(tmp_path, monkeypatch):
    files = {"video.webm": (600.0, AUDIO_STREAMS)}
    work = media_dir(tmp_path, files)
    files["video.mp4"] = (600.0, VIDEO_STREAMS)
    fake_probe(monkeypatch, files)
    downloader(monkeypatch, calls := [])
    cf.download(INFO, work, IngestOptions())
    assert calls == ["398+251"]


def test_r_cli_1_audio_only_file_is_reused_for_an_audio_source(tmp_path, monkeypatch):
    files = {"video.webm": (600.0, AUDIO_STREAMS)}
    work = media_dir(tmp_path, files)
    fake_probe(monkeypatch, files)
    downloader(monkeypatch, calls := [])
    audio = {"duration": 600, "formats": [INFO["formats"][1]]}
    assert cf.download(audio, work, IngestOptions()).path == "media/video.webm"
    assert calls == []


def test_metadata_never_resolves_playlist_entries(tmp_path, monkeypatch, fake_dl):
    monkeypatch.setattr(cf.media, "ffmpeg_paths", lambda: (Path("/x/ffmpeg"), Path("/x/ffprobe")))
    assert cf.ydl_params(tmp_path, IngestOptions(), download=False)["extract_flat"] == "in_playlist"
    assert "extract_flat" not in cf.ydl_params(tmp_path, IngestOptions(), download=True)
    cf.extract("https://www.youtube.com/playlist?list=PL1", IngestOptions())
    assert fake_dl.instances[-1].params["extract_flat"] == "in_playlist"


# ---- session continuity: the site's guest cookies from extract reach the download ----

GUEST_VALUE = "v1%3A1700000000000000"


def _guest_cookie():
    from http.cookiejar import Cookie

    return Cookie(
        0, "guest_id", GUEST_VALUE, None, False, ".x.com", True, True, "/", True, True,
        None, False, None, None, {},
    )  # fmt: skip


class SessionDL(FakeDL):
    """extract_info gets a guest cookie from the site, as X's guest-token flow does; the
    download only works when that cookie is in its own jar."""

    seen_in_download: list[list[str]] = []

    def __init__(self, params):
        super().__init__(params)
        from http.cookiejar import CookieJar

        self.cookiejar = CookieJar()

    def extract_info(self, url, download=False):
        self.cookiejar.set_cookie(_guest_cookie())
        return dict(FakeDL.info, original_url=url, webpage_url=url)

    def process_ie_result(self, info, download=True):
        names = [c.name for c in self.cookiejar]
        SessionDL.seen_in_download.append(names)
        if "guest_id" not in names:
            raise cf.yt_dlp.utils.DownloadError("ERROR: unable to download: HTTP Error 404")
        out = Path(self.params["paths"]["home"]) / "video.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x")
        return dict(info, requested_downloads=[{"filepath": str(out)}])


@pytest.fixture
def session_dl(monkeypatch):
    FakeDL.instances, FakeDL.error = [], None
    FakeDL.info = {
        "id": "media1",
        "duration": 10,
        "formats": [
            {"format_id": "v", "width": 1280, "height": 720, "vcodec": "avc1", "acodec": "none",
             "filesize": 2},
            {"format_id": "a", "vcodec": "none", "acodec": None, "filesize": 1},
        ],
    }  # fmt: skip
    SessionDL.seen_in_download = []
    monkeypatch.setattr(cf.yt_dlp, "YoutubeDL", SessionDL)
    monkeypatch.setattr(cf, "js_runtime", lambda: {})
    monkeypatch.setattr(cf.media, "ffmpeg_paths", lambda: (Path("/x/ffmpeg"), Path("/x/ffprobe")))
    monkeypatch.setattr(
        cf.media,
        "probe",
        lambda p: {
            "format": {"duration": "10"},
            "streams": [
                {"codec_type": "video", "width": 1280, "height": 720, "r_frame_rate": "25/1"},
                {"codec_type": "audio"},
            ],
        },
    )
    return SessionDL


def test_download_carries_the_extract_session_cookies(tmp_path, session_dl):
    url = "https://x.com/someone/status/1"
    info = cf.extract(url, IngestOptions())
    json.dumps(info)  # the info stays plain JSON: no jar rides along in it
    work = WorkDir(tmp_path / "w")
    work.ensure()
    got = cf.download(info, work, IngestOptions())
    assert got.path == "media/video.mp4"
    assert session_dl.seen_in_download == [["guest_id"]]
    params = session_dl.instances[-1].params
    assert "cookiefile" not in params and "cookiesfrombrowser" not in params


def test_session_cookies_are_never_persisted_and_not_user_cookies(tmp_path, session_dl, sw_home):
    from typer.testing import CliRunner

    from skipwatch.cli import app
    from skipwatch.models import IngestBundle

    url = "https://x.com/someone/status/1"
    work = tmp_path / "w"
    r = CliRunner().invoke(
        app, ["ingest", url, "--work", str(work), "--provider", "free", "--json"]
    )
    assert r.exit_code == 0, r.output
    assert IngestBundle.model_validate_json(r.stdout).fetched_with_cookies is False
    assert session_dl.seen_in_download == [["guest_id"]]
    for root in (work, sw_home):
        for path in root.rglob("*"):
            if path.is_file() and path.suffix != ".mp4":
                text = path.read_text(encoding="utf-8", errors="replace")
                assert "guest_id" not in text and GUEST_VALUE not in text, path
    assert "guest_id" not in r.output


G4 = Path(__file__).resolve().parents[1] / "fixtures" / "recorded" / "instagram"
G4_SPEC = "dash-18630250069054910v+dash-18630246724054910a"


def g4_info() -> dict:
    info = json.loads((G4 / "g4-gh-secure.info.json").read_text(encoding="utf-8"))
    assert info["duration"] is None  # Instagram gives no duration
    return info


def test_r_cli_1_without_a_duration_a_merged_file_with_video_and_audio_is_reused(
    tmp_path, monkeypatch
):
    files = {"video.mp4": (31.0, VIDEO_STREAMS)}
    work = media_dir(tmp_path, files)
    fake_probe(monkeypatch, files)
    downloader(monkeypatch, calls := [])
    assert cf.download(g4_info(), work, IngestOptions()).path == "media/video.mp4"
    assert calls == []


def test_r_cli_1_without_a_duration_a_silent_or_partial_file_is_downloaded_again(
    tmp_path, monkeypatch
):
    files = {"video.mp4": (31.0, VIDEO_STREAMS[:1]), "video.f1.mp4": (31.0, VIDEO_STREAMS)}
    work = media_dir(tmp_path, files)
    fake_probe(monkeypatch, files)
    downloader(monkeypatch, calls := [])
    cf.download(g4_info(), work, IngestOptions())
    assert calls == [G4_SPEC]  # no audio in the merged file, and intermediates never count


def test_r_cli_1_without_a_duration_a_silent_source_reuses_its_video_only_file(
    tmp_path, monkeypatch
):
    """A silent source (no format with an audio codec, the video's acodec left out) must not
    be downloaded again on every run just because its file has no audio."""
    files = {"video.mp4": (31.0, VIDEO_STREAMS[:1])}
    work = media_dir(tmp_path, files)
    fake_probe(monkeypatch, files)
    downloader(monkeypatch, calls := [])
    silent = {
        "duration": None,
        "formats": [{"format_id": "v", "width": 1280, "height": 720, "vcodec": "avc1"}],
    }
    assert cf.download(silent, work, IngestOptions()).path == "media/video.mp4"
    assert calls == []
