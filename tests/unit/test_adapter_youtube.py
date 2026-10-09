import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch.adapters.base import DownloadFailed, IngestOptions
from skipwatch.adapters.registry import adapter_for
from skipwatch.adapters.youtube import ADAPTER
from skipwatch.adapters.ytdlp_common import choose_caption_track
from skipwatch.cli import app
from skipwatch.detect import Detected
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import MediaInfo
from skipwatch.providers import content_free as cf
from skipwatch.workdir import WorkDir


def test_caption_choice_prefers_manual_then_orig():
    info = {
        "language": "de",
        "subtitles": {"live_chat": [{}], "de": [{"ext": "vtt"}]},
        "automatic_captions": {"en": [{}], "de-orig": [{}], "ab": [{}]},
    }
    assert choose_caption_track(info) == ("de", "manual")
    info["subtitles"] = {}
    assert choose_caption_track(info) == ("de-orig", "auto")
    assert (
        choose_caption_track(
            {"language": None, "subtitles": {}, "automatic_captions": {"ab": [{}]}}
        )
        is None
    )


def test_caption_choice_manual_english_region_beats_original_language():
    info = {"language": "de", "subtitles": {"de": [{}], "en-US": [{}]}, "automatic_captions": {}}
    assert choose_caption_track(info) == ("en-US", "manual")


def test_caption_choice_manual_other_language_as_last_manual_resort():
    info = {"language": None, "subtitles": {"fr": [{}], "es": [{}]}, "automatic_captions": {}}
    assert choose_caption_track(info) == ("fr", "manual")


def test_caption_choice_live_chat_alone_is_not_a_caption_track():
    info = {
        "language": "en",
        "subtitles": {"live_chat": [{}]},
        "automatic_captions": {"en-orig": [{}]},
    }
    assert choose_caption_track(info) == ("en-orig", "auto")


def test_caption_choice_auto_english_source_without_orig_uses_english():
    info = {"language": "en", "subtitles": {}, "automatic_captions": {"en": [{}], "de": [{}]}}
    assert choose_caption_track(info) == ("en", "auto")


def test_caption_choice_never_takes_a_machine_translation():
    info = {"language": "ja", "subtitles": {}, "automatic_captions": {"en": [{}], "de": [{}]}}
    assert choose_caption_track(info) is None


def test_caption_choice_unknown_language_takes_the_single_orig_track():
    info = {
        "language": None,
        "subtitles": {},
        "automatic_captions": {"en": [{}], "de-orig": [{}], "de": [{}]},
    }
    assert choose_caption_track(info) == ("de-orig", "auto")


def test_caption_choice_unknown_language_with_several_orig_tracks_prefers_english():
    auto = {"en": [{}], "en-orig": [{}], "de-orig": [{}]}
    assert choose_caption_track(
        {"language": None, "subtitles": {}, "automatic_captions": auto}
    ) == (
        "en-orig",
        "auto",
    )


# ---- bundles from recorded fixtures (no network: content_free is monkeypatched) ----

REC = Path(__file__).resolve().parents[1] / "fixtures" / "recorded" / "youtube"
URL = "https://www.youtube.com/watch?v=rE2zRhZdjFU"


def recorded(name: str) -> dict:
    return json.loads((REC / f"{name}.info.json").read_text())


@pytest.fixture
def free_route(monkeypatch):
    """Replace the three content_free network calls; returns the call log."""
    seen: dict = {"captions": [], "download": 0}

    def install(info, media=None, captions_error=None):
        monkeypatch.setattr(cf, "extract", lambda url, opts: info)

        def captions(info_, work, opts, track, failed=None):
            seen["captions"].append(track)
            if captions_error:
                raise cf.FreeRouteError("captions", captions_error)
            lang, kind = track
            return f"captions/x.{lang}.json3", lang, kind

        def download(info_, work, opts, failed=None):
            seen["download"] += 1
            return media or MediaInfo(
                path="media/video.mp4", width=1280, height=720, has_audio=True
            )

        monkeypatch.setattr(cf, "download_captions", captions)
        monkeypatch.setattr(cf, "download", download)
        return seen

    return install


def build(url=URL, opts=None, tmp=None):
    work = WorkDir(tmp)
    work.ensure()
    return ADAPTER.build(
        Detected(kind="url", platform="youtube", value=url), work, opts or IngestOptions()
    )


def test_recorded_manual_fixture_builds_a_bundle(tmp_path, free_route):
    info = recorded("manual-captions")
    seen = free_route(info)
    bundle = build(tmp=tmp_path / "w")
    assert bundle.source.platform == "youtube" and bundle.source.kind == "video"
    assert bundle.source.author_name == info["uploader"]
    assert bundle.source.author == "@GitHub"  # uploader_id already carries the @
    assert bundle.source.title == info["title"] and bundle.source.duration_s == 868
    assert bundle.source.posted_at == "2024-06-10T13:00:57Z"
    assert bundle.source.url == URL
    assert bundle.context.captions_kind == "manual" and bundle.context.captions_lang == "en-US"
    assert (
        bundle.context.captions_available
        and bundle.context.captions_path == "captions/x.en-US.json3"
    )
    assert bundle.context.post_text == info["description"]  # full, never truncated (R-ING-1)
    assert len(bundle.context.post_text) > 1000
    assert bundle.route.context == "free" and bundle.route.media == "free"
    assert bundle.fetched_with_cookies is False
    assert [c.op for c in bundle.provider_calls] == [
        "yt-dlp.metadata",
        "yt-dlp.captions",
        "yt-dlp.download",
    ]
    assert all(c.provider == "free" and c.ok and c.cost_usd == 0 for c in bundle.provider_calls)
    assert bundle.media is not None and bundle.media.path == "media/video.mp4"
    assert seen["captions"] == [("en-US", "manual")]


def test_recorded_auto_only_fixture_takes_the_original_language_track(tmp_path, free_route):
    seen = free_route(recorded("auto-only-nonenglish"))
    bundle = build(tmp=tmp_path / "w")
    assert seen["captions"] == [("de-orig", "auto")]
    assert bundle.context.captions_kind == "auto" and bundle.context.captions_lang == "de"


def test_cookies_flag_sets_fetched_with_cookies(tmp_path, free_route):
    free_route(recorded("manual-captions"))
    bundle = build(opts=IngestOptions(cookies_from_browser="firefox"), tmp=tmp_path / "w")
    assert bundle.fetched_with_cookies is True


def test_caption_failure_is_logged_and_ingest_continues(tmp_path, free_route):
    free_route(
        recorded("manual-captions"), captions_error="ERROR: HTTP Error 429: Too Many Requests"
    )
    bundle = build(tmp=tmp_path / "w")
    assert bundle.context.captions_available is False and bundle.media is not None
    failed = [c for c in bundle.provider_calls if not c.ok]
    assert [c.op for c in failed] == ["yt-dlp.captions"]
    assert failed[0].error == "HTTP Error 429: Too Many Requests"


def test_audio_only_source_is_kind_audio(tmp_path, free_route):
    info = dict(recorded("manual-captions"))
    info["formats"] = [f for f in info["formats"] if f["vcodec"] == "none" and f["acodec"]]
    free_route(info, media=MediaInfo(path="media/video.m4a", has_audio=True))
    assert build(tmp=tmp_path / "w").source.kind == "audio"


def test_download_failure_carries_the_partial_bundle(tmp_path, monkeypatch, free_route):
    free_route(recorded("manual-captions"))

    def fail(info, work, opts, failed=None):
        raise cf.FreeRouteError(
            "download", "ERROR: unable to download video data: HTTP Error 403: Forbidden"
        )

    monkeypatch.setattr(cf, "download", fail)
    with pytest.raises(DownloadFailed) as e:
        build(tmp=tmp_path / "w")
    assert e.value.attempts == [
        "free.yt-dlp.download: unable to download video data: HTTP Error 403: Forbidden"
    ]
    assert e.value.bundle is not None and e.value.bundle.context.captions_available
    assert [c.op for c in e.value.bundle.provider_calls][-1] == "yt-dlp.download"


def test_playlist_url_is_exit_2(tmp_path, free_route):
    free_route({"_type": "playlist", "id": "PL1", "entries": []})
    with pytest.raises(SkipwatchError) as e:
        build(url="https://www.youtube.com/playlist?list=PL1", tmp=tmp_path / "w")
    assert e.value.code == ExitCode.UNSUPPORTED_SOURCE


def test_live_stream_is_exit_2(tmp_path, free_route):
    free_route(dict(recorded("manual-captions"), is_live=True))
    with pytest.raises(SkipwatchError) as e:
        build(tmp=tmp_path / "w")
    assert e.value.code == ExitCode.UNSUPPORTED_SOURCE and "live" in e.value.message


def test_youtube_registers_itself():
    assert adapter_for("youtube") is ADAPTER


# ---- through the CLI: yt_dlp itself is faked, so the real extract and mapping run ----


def fake_ytdlp(monkeypatch, error: str):
    class DL:
        def __init__(self, params):
            self.params = params

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False):
            raise cf.DownloadError(error)

    monkeypatch.setattr(cf.yt_dlp, "YoutubeDL", DL)
    monkeypatch.setattr(cf, "js_runtime", lambda: {})


AGE = (
    "ERROR: [youtube] x: Sign in to confirm your age. This video may be inappropriate for some "
    "users. Use --cookies-from-browser or --cookies for the authentication. See  "
    "https://github.com/yt-dlp/yt-dlp/wiki/FAQ  for how to manually pass cookies"
)


def test_r_ing_6_login_required_is_exit_4_naming_the_flag(tmp_path, monkeypatch, sw_home):
    fake_ytdlp(monkeypatch, AGE)
    r = CliRunner().invoke(
        app,
        [
            "ingest",
            "https://www.youtube.com/watch?v=x",
            "--work",
            str(tmp_path / "w"),
            "--provider",
            "free",
        ],
    )
    assert r.exit_code == ExitCode.PRIVATE_CONTENT
    assert "--cookies-from-browser" in r.output and "YouTube" in r.output


def test_r_ing_6_still_private_with_cookies_says_so(tmp_path, monkeypatch, sw_home):
    fake_ytdlp(monkeypatch, AGE)
    r = CliRunner().invoke(
        app,
        [
            "ingest",
            "https://www.youtube.com/watch?v=x",
            "--work",
            str(tmp_path / "w"),
            "--provider",
            "free",
            "--cookies-from-browser",
            "chrome",
        ],
    )
    assert r.exit_code == ExitCode.PRIVATE_CONTENT
    assert "chrome" in r.output and "--cookies-from-browser" in r.output


def test_metadata_network_failure_is_exit_3_listing_the_route(tmp_path, monkeypatch, sw_home):
    fake_ytdlp(monkeypatch, "ERROR: [youtube] x: Unable to download API page: HTTP Error 500")
    r = CliRunner().invoke(
        app,
        [
            "ingest",
            "https://www.youtube.com/watch?v=x",
            "--work",
            str(tmp_path / "w"),
            "--provider",
            "free",
        ],
    )
    assert r.exit_code == ExitCode.DOWNLOAD_FAILED
    assert (
        "free.yt-dlp.metadata: [youtube] x: Unable to download API page: HTTP Error 500" in r.output
    )


def test_bot_check_is_named_as_such_with_both_ways_out(tmp_path, monkeypatch, sw_home):
    fake_ytdlp(
        monkeypatch,
        "ERROR: [youtube] x: Sign in to confirm you're not a bot. Use --cookies-from-browser or "
        "--cookies for the authentication.",
    )
    r = CliRunner().invoke(
        app, ["ingest", "https://www.youtube.com/watch?v=x", "--work", str(tmp_path / "w")]
    )
    assert r.exit_code == ExitCode.PRIVATE_CONTENT
    assert "bot check" in r.output and "--cookies-from-browser" in r.output
    assert "home connection" in r.output
