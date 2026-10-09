"""TikTok, Instagram and Facebook adapters on the free route (Task M3-C1).

Bundles come from the M3 spike's recorded fixtures with content_free's network calls
monkeypatched; the CLI tests fake yt_dlp itself so the real extract and error mapping run.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch.adapters.base import IngestOptions
from skipwatch.adapters.registry import adapter_for
from skipwatch.cli import app
from skipwatch.detect import Detected, detect
from skipwatch.errors import ExitCode
from skipwatch.models import MediaInfo
from skipwatch.providers import content_free as cf
from skipwatch.workdir import WorkDir

REC = Path(__file__).resolve().parents[1] / "fixtures" / "recorded"

# platform, fixture, the URL it was recorded from, expected author, expected author_name
SOCIAL = [
    (
        "tiktok",
        "tiktok/g3-copilot-cli",
        "https://www.tiktok.com/@github/video/7624273546776153377",
        "@github",
        "GitHub",
    ),
    (
        "instagram",
        "instagram/g4-gh-secure",
        "https://www.instagram.com/reel/Dd-rJlkE_Z5/",
        "@github",
        "GitHub",
    ),
    (
        "facebook",
        "facebook/govsg-haze",
        "https://www.facebook.com/gov.sg/videos/10154383743583686/",
        "gov.sg",
        "gov.sg",
    ),
]
IDS = [row[0] for row in SOCIAL]


def recorded(name: str) -> dict:
    return json.loads((REC / f"{name}.info.json").read_text(encoding="utf-8"))


def short_side(info: dict, spec: str) -> int:
    by_id = {f["format_id"]: f for f in info["formats"]}
    video = by_id[spec.split("+")[0]]
    return min(video["width"], video["height"])


@pytest.fixture
def free_route(monkeypatch):
    """Replace content_free's network calls; returns what they were asked."""
    seen: dict = {"downloads": 0, "captions": 0}

    def install(info):
        monkeypatch.setattr(cf, "extract", lambda url, opts: info)

        def captions(*args, **kwargs):
            seen["captions"] += 1
            return None

        def download(info_, work, opts, failed=None):
            seen["downloads"] += 1
            return MediaInfo(path="media/video.mp4", width=720, height=1280, has_audio=True)

        monkeypatch.setattr(cf, "download_captions", captions)
        monkeypatch.setattr(cf, "download", download)
        return seen

    return install


def build(platform: str, url: str, tmp: Path, opts: IngestOptions | None = None):
    work = WorkDir(tmp)
    work.ensure()
    adapter = adapter_for(platform)
    assert adapter is not None, f"no adapter registered for {platform}"
    return adapter.build(
        Detected(kind="url", platform=platform, value=url), work, opts or IngestOptions()
    )


@pytest.mark.parametrize(("platform", "fixture", "url", "author", "author_name"), SOCIAL, ids=IDS)
def test_recorded_fixture_builds_a_video_bundle(
    tmp_path, free_route, platform, fixture, url, author, author_name
):
    info = recorded(fixture)
    seen = free_route(info)
    bundle = build(platform, url, tmp_path / "w")
    assert bundle.source.kind == "video" and bundle.source.platform == platform
    assert bundle.source.canonical_url == info["webpage_url"]
    assert bundle.context.post_text == info["description"]  # the caption is the post text
    assert bundle.context.captions_available is False and seen["captions"] == 0
    assert bundle.media is not None and seen["downloads"] == 1
    assert bundle.route.context == "free" and bundle.route.media == "free"
    assert bundle.fetched_with_cookies is False
    assert [c.op for c in bundle.provider_calls] == ["yt-dlp.metadata", "yt-dlp.download"]


@pytest.mark.parametrize(("platform", "fixture"), [(r[0], r[1]) for r in SOCIAL], ids=IDS)
def test_r_ing_4_format_choice_on_recorded_formats(platform, fixture):
    info = recorded(fixture)
    assert 720 <= short_side(info, cf.select_format(info)) <= 1080


def test_tiktok_h265_only_720_is_still_chosen():
    """Orchestrator decision 6: TikTok's 720p and 1080p renditions are h265 (bytevc1) only."""
    info = recorded("tiktok/g3-copilot-cli")
    spec = cf.select_format(info)
    chosen = next(f for f in info["formats"] if f["format_id"] == spec)
    assert chosen["vcodec"] == "h265" and (chosen["width"], chosen["height"]) == (720, 1280)
    assert "+" not in spec  # progressive: TikTok renditions carry their own audio
    # load-bearing: drop the h265 renditions and only the h264 576p ones are left
    h264 = dict(info, formats=[f for f in info["formats"] if f.get("vcodec") != "h265"])
    assert short_side(h264, cf.select_format(h264)) == 576


def test_instagram_null_duration_still_picks_720(tmp_path, free_route):
    """Logged out, Instagram reports duration null and no sizes; nothing may crash on it."""
    info = recorded("instagram/g4-gh-secure")
    assert info["duration"] is None
    spec = cf.select_format(info)
    assert short_side(info, spec) == 720 and spec.endswith("+dash-18630246724054910a")
    free_route(info)
    bundle = build("instagram", "https://www.instagram.com/reel/Dd-rJlkE_Z5/", tmp_path / "w")
    assert bundle.source.duration_s is None


@pytest.mark.parametrize(("platform", "fixture", "url"), [r[:3] for r in SOCIAL], ids=IDS)
def test_cookies_flag_sets_fetched_with_cookies(tmp_path, monkeypatch, platform, fixture, url):
    """The flag reaches yt-dlp's params and the bundle records it (R-ING-5)."""
    info = recorded(fixture)
    params: list[dict] = []
    real_params = cf.ydl_params

    def spy(work, opts, *, download):
        built = real_params(work, opts, download=download)
        params.append(built)
        return built

    class DL:
        def __init__(self, p):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url_, download=False):
            return info

        @staticmethod
        def sanitize_info(i):
            return i

    monkeypatch.setattr(cf, "ydl_params", spy)
    monkeypatch.setattr(cf, "js_runtime", lambda: {})
    monkeypatch.setattr(cf.yt_dlp, "YoutubeDL", DL)
    monkeypatch.setattr(
        cf,
        "download",
        lambda *a, **k: MediaInfo(path="media/video.mp4", width=720, height=1280, has_audio=True),
    )
    bundle = build(platform, url, tmp_path / "w", IngestOptions(cookies_from_browser="firefox"))
    assert params and params[0]["cookiesfrombrowser"] == ("firefox",)
    assert bundle.fetched_with_cookies is True


# ---- login walls through the CLI (R-ING-6): exit 4 naming the cookie flag ----


def login_error(extractor: str, reason: str | None = None) -> str:
    """The message yt-dlp's own raise_login_required builds for this extractor, with the
    `ERROR: [<ie>] <id>: ` prefix DownloadError carries."""
    module = __import__(f"yt_dlp.extractor.{extractor.lower()}", fromlist=["x"])
    ie = getattr(module, f"{extractor}IE")(cf.yt_dlp.YoutubeDL({"quiet": True}))
    try:
        ie.raise_login_required(*([reason] if reason else []))
    except Exception as exc:  # ExtractorError
        return f"ERROR: [{extractor.lower()}] post1: {exc}"
    raise AssertionError("raise_login_required did not raise")


# Instagram's anonymous rate-limit redirect, its private-account wall, and Facebook's default.
IG_RATE = login_error(
    "Instagram",
    "The webpage request was redirected to the login page. "
    "You have exceeded the rate-limit for accessing posts anonymously",
)
IG_PRIVATE = login_error(
    "Instagram", "This content is only available for registered users who follow this account"
)
FB_LOGIN = login_error("Facebook")


def fake_ytdlp(monkeypatch, error: str):
    class DL:
        def __init__(self, params):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False):
            raise cf.DownloadError(error)

    monkeypatch.setattr(cf.yt_dlp, "YoutubeDL", DL)
    monkeypatch.setattr(cf, "js_runtime", lambda: {})


@pytest.mark.parametrize(
    ("url", "error", "site"),
    [
        ("https://www.instagram.com/reel/Dd-rJlkE_Z5/", IG_RATE, "Instagram"),
        ("https://www.instagram.com/p/Dd-rJlkE_Z5/", IG_PRIVATE, "Instagram"),
        ("https://www.facebook.com/gov.sg/videos/10154383743583686/", FB_LOGIN, "Facebook"),
    ],
    ids=["instagram-rate-limit", "instagram-private", "facebook"],
)
def test_login_wall_is_exit_4_naming_cookie_flag(tmp_path, monkeypatch, sw_home, url, error, site):
    fake_ytdlp(monkeypatch, error)
    r = CliRunner().invoke(
        app, ["ingest", url, "--work", str(tmp_path / "w"), "--provider", "free"]
    )
    assert r.exit_code == ExitCode.PRIVATE_CONTENT, r.output
    assert "--cookies-from-browser" in r.output


def test_probe_instagram_null_duration_reports_unknown(monkeypatch, sw_home):
    info = recorded("instagram/g4-gh-secure")
    monkeypatch.setattr(cf, "extract", lambda url, opts: info)
    r = CliRunner().invoke(app, ["probe", "https://www.instagram.com/reel/Dd-rJlkE_Z5/", "--json"])
    assert r.exit_code == 0, r.output
    result = json.loads(r.stdout)
    assert result["platform"] == "instagram" and result["duration_s"] is None
    assert result["long_video"] is False and result["estimated_run_s"] is None


# ---- registration and detection ----


@pytest.mark.parametrize("platform", IDS)
def test_platform_registers_itself(platform):
    adapter = adapter_for(platform)
    assert adapter is not None and type(adapter).__module__ == f"skipwatch.adapters.{platform}"


@pytest.mark.parametrize(
    ("url", "platform"),
    [
        ("https://www.instagram.com/reel/Dd-rJlkE_Z5/", "instagram"),
        ("https://www.instagram.com/p/Dd-rJlkE_Z5/", "instagram"),
        ("https://www.instagram.com/tv/Dd-rJlkE_Z5/", "instagram"),
        ("https://www.tiktok.com/@github/video/7624273546776153377", "tiktok"),
        ("https://vm.tiktok.com/ZMabc123/", "tiktok"),
        ("https://vt.tiktok.com/ZSabc123/", "tiktok"),
        ("https://www.facebook.com/watch/?v=10154383743583686", "facebook"),
        ("https://www.facebook.com/reel/1234567890", "facebook"),
        ("https://www.facebook.com/gov.sg/videos/10154383743583686/", "facebook"),
        ("https://fb.watch/abcDEF123/", "facebook"),
        ("https://m.facebook.com/watch/?v=1", "facebook"),
    ],
)
def test_detect_maps_social_url_shapes(url, platform):
    assert detect(url).platform == platform
