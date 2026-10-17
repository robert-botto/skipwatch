"""One retry for transient yt-dlp failures (HTTP 403, 429, connection reset)."""

import socket
from pathlib import Path

import pytest

from skipwatch.adapters.base import DownloadFailed, IngestOptions
from skipwatch.adapters.youtube import ADAPTER
from skipwatch.detect import Detected
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.providers import content_free as cf
from skipwatch.providers import links
from skipwatch.workdir import WorkDir

FORBIDDEN = "ERROR: unable to download video data: HTTP Error 403: Forbidden"
BOT = (
    "ERROR: [youtube] x: Sign in to confirm you're not a bot. Use --cookies-from-browser or "
    "--cookies for the authentication."
)
INFO = {
    "id": "abc",
    "title": "T",
    "duration": 10,
    "formats": [
        {"format_id": "22", "width": 1280, "height": 720, "vcodec": "avc1", "acodec": "mp4a",
         "filesize": 1},
    ],
    "subtitles": {"en": [{"ext": "vtt", "url": "https://c.example.com/vtt"}]},
}  # fmt: skip


class Script:
    """A fake yt_dlp.YoutubeDL and caption fetch that fail with the queued errors first."""

    def __init__(self, failures: list[str]):
        self.failures = list(failures)
        self.downloads = 0
        self.fetches = 0
        script = self

        class DL:
            def __init__(self, params):
                self.params = params

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def process_ie_result(self, info, download=True):
                script.downloads += 1
                if script.failures:
                    raise cf.DownloadError(script.failures.pop(0))
                out = Path(self.params["paths"]["home"]) / "video.mp4"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(b"x")
                return dict(info, requested_downloads=[{"filepath": str(out)}])

        self.cls = DL

    def fetch_track(self, url: str) -> tuple[bytes, str]:
        """Stands in for cf.fetch_track (the vetted caption fetch)."""
        self.fetches += 1
        if self.failures:
            raise cf.FreeRouteError("captions", self.failures.pop(0))
        return b"WEBVTT\n\n00:00.000 --> 00:01.000\nhi\n", url


@pytest.fixture
def ytdlp(monkeypatch):
    sleeps: list[float] = []

    def install(failures: list[str]) -> Script:
        script = Script(failures)
        monkeypatch.setattr(cf.yt_dlp, "YoutubeDL", script.cls)
        monkeypatch.setattr(cf, "fetch_track", script.fetch_track)
        return script

    monkeypatch.setattr(cf, "js_runtime", lambda: {})
    monkeypatch.setattr(cf.time, "sleep", sleeps.append)
    # caption fetches are vetted (links.get_vetted): resolve hosts to a public address
    monkeypatch.setattr(
        links.socket,
        "getaddrinfo",
        lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    monkeypatch.setattr(cf.media, "ffmpeg_paths", lambda: (Path("/x/ffmpeg"), Path("/x/ffprobe")))
    monkeypatch.setattr(
        cf.media,
        "probe",
        lambda p: {
            "format": {"duration": "10"},
            "streams": [{"codec_type": "video", "width": 1280, "height": 720}],
        },
    )
    install.sleeps = sleeps  # type: ignore[attr-defined]
    return install


def work(tmp_path) -> WorkDir:
    w = WorkDir(tmp_path / "w")
    w.ensure()
    return w


def test_download_403_once_then_success_retries_after_a_pause(tmp_path, ytdlp, capsys):
    script = ytdlp([FORBIDDEN])
    failed: list = []
    got = cf.download(INFO, work(tmp_path), IngestOptions(), failed)
    assert got.path == "media/video.mp4" and script.downloads == 2
    assert ytdlp.sleeps == [cf.RETRY_DELAY_S] and cf.RETRY_DELAY_S == 2.0
    assert [(c.op, c.ok, c.error) for c in failed] == [
        ("yt-dlp.download", False, "unable to download video data: HTTP Error 403: Forbidden")
    ]
    assert "retrying after a transient 403" in capsys.readouterr().err


@pytest.mark.parametrize(
    "message,label",
    [
        ("ERROR: unable to download video data: HTTP Error 429: Too Many Requests", "429"),
        ("ERROR: [Errno 54] Connection reset by peer", "connection reset"),
    ],
)
def test_download_429_and_connection_reset_are_retried(tmp_path, ytdlp, capsys, message, label):
    script = ytdlp([message])
    cf.download(INFO, work(tmp_path), IngestOptions())
    assert script.downloads == 2
    assert f"retrying after a transient {label}" in capsys.readouterr().err


def test_download_403_twice_fails_after_exactly_one_retry(tmp_path, ytdlp):
    script = ytdlp([FORBIDDEN, FORBIDDEN, FORBIDDEN])
    failed: list = []
    with pytest.raises(cf.FreeRouteError) as e:
        cf.download(INFO, work(tmp_path), IngestOptions(), failed)
    assert script.downloads == 2 and e.value.code == ExitCode.DOWNLOAD_FAILED
    assert len(failed) == 1  # the caller logs the final failure


@pytest.mark.parametrize("message", [BOT, "ERROR: [youtube] x: Private video. Use --cookies"])
def test_login_private_and_bot_errors_are_never_retried(tmp_path, ytdlp, message):
    script = ytdlp([message])
    with pytest.raises(cf.FreeRouteError) as e:
        cf.download(INFO, work(tmp_path), IngestOptions())
    assert script.downloads == 1 and ytdlp.sleeps == []
    assert e.value.code == ExitCode.PRIVATE_CONTENT


def test_other_errors_are_not_retried(tmp_path, ytdlp):
    script = ytdlp(["ERROR: Requested format is not available"])
    with pytest.raises(cf.FreeRouteError):
        cf.download(INFO, work(tmp_path), IngestOptions())
    assert script.downloads == 1


def test_bundle_records_both_download_attempts(tmp_path, ytdlp, monkeypatch):
    ytdlp([FORBIDDEN])
    monkeypatch.setattr(cf, "extract", lambda url, opts: INFO)
    monkeypatch.setattr(cf, "download_captions", lambda *a: None)
    detected = Detected(kind="url", platform="youtube", value="https://youtu.be/abc")
    bundle = ADAPTER.build(detected, work(tmp_path), IngestOptions())
    downloads = [(c.op, c.ok) for c in bundle.provider_calls if c.op == "yt-dlp.download"]
    assert downloads == [("yt-dlp.download", False), ("yt-dlp.download", True)]


def test_bundle_after_two_403s_is_download_failed_with_both_attempts(tmp_path, ytdlp, monkeypatch):
    ytdlp([FORBIDDEN, FORBIDDEN])
    monkeypatch.setattr(cf, "extract", lambda url, opts: INFO)
    monkeypatch.setattr(cf, "download_captions", lambda *a: None)
    detected = Detected(kind="url", platform="youtube", value="https://youtu.be/abc")
    with pytest.raises(DownloadFailed) as e:
        ADAPTER.build(detected, work(tmp_path), IngestOptions())
    assert e.value.bundle is not None
    ops = [(c.op, c.ok) for c in e.value.bundle.provider_calls if c.op == "yt-dlp.download"]
    assert ops == [("yt-dlp.download", False), ("yt-dlp.download", False)]


def test_bot_check_through_the_adapter_stays_exit_4(tmp_path, ytdlp, monkeypatch):
    script = ytdlp([BOT])
    monkeypatch.setattr(cf, "extract", lambda url, opts: INFO)
    monkeypatch.setattr(cf, "download_captions", lambda *a: None)
    detected = Detected(kind="url", platform="youtube", value="https://youtu.be/abc")
    with pytest.raises(SkipwatchError) as e:
        ADAPTER.build(detected, work(tmp_path), IngestOptions())
    assert e.value.code == ExitCode.PRIVATE_CONTENT and script.downloads == 1


def test_captions_403_once_is_retried_and_logged(tmp_path, ytdlp, capsys):
    script = ytdlp(["HTTP Error 403: Forbidden"])
    failed: list = []
    got = cf.download_captions(INFO, work(tmp_path), IngestOptions(), ("en", "manual"), failed)
    assert got == ("captions/abc.en.vtt", "en", "manual") and script.fetches == 2
    assert [(c.op, c.ok) for c in failed] == [("yt-dlp.captions", False)]
    assert "retrying after a transient 403" in capsys.readouterr().err


def test_bundle_records_both_caption_attempts(tmp_path, ytdlp, monkeypatch):
    ytdlp(["HTTP Error 429: Too Many Requests"])
    monkeypatch.setattr(cf, "extract", lambda url, opts: INFO)
    detected = Detected(kind="url", platform="youtube", value="https://youtu.be/abc")
    bundle = ADAPTER.build(detected, work(tmp_path), IngestOptions())
    captions = [(c.op, c.ok) for c in bundle.provider_calls if c.op == "yt-dlp.captions"]
    assert captions == [("yt-dlp.captions", False), ("yt-dlp.captions", True)]
    assert bundle.context.captions_available


def _exit_3_message(tmp_path, monkeypatch, attempt: str) -> str:
    from skipwatch.config import load_config
    from skipwatch.ingest import build_bundle

    class Failing:
        def build(self, detected, work, opts):
            raise DownloadFailed([attempt])

    monkeypatch.setattr("skipwatch.ingest.adapter_for", lambda p: Failing())
    with pytest.raises(SkipwatchError) as e:
        build_bundle("https://youtu.be/abc", work(tmp_path), IngestOptions(provider="free"),
                     load_config(tmp_path / "none.toml"))  # fmt: skip
    assert e.value.code == ExitCode.DOWNLOAD_FAILED
    return e.value.message


def test_exit_3_after_a_403_says_rerun_first(tmp_path, monkeypatch):
    message = _exit_3_message(
        tmp_path, monkeypatch, "free.yt-dlp.download: unable to download: HTTP Error 403: Forbidden"
    )
    assert "A 403 can be transient" in message
    rerun = message.index("run the same command again")
    assert rerun < message.index("If it fails again") < message.index("--cookies-from-browser")


def test_exit_3_without_a_transient_error_keeps_the_plain_hint(tmp_path, monkeypatch):
    message = _exit_3_message(
        tmp_path, monkeypatch, "free.yt-dlp.download: Requested format is not available"
    )
    assert "transient" not in message and "--cookies-from-browser" in message
