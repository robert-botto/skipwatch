"""X adapter on recorded spike fixtures (tests/fixtures/recorded/x). No network: content_free and
the link helpers are faked."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch.adapters import x
from skipwatch.adapters.base import IngestOptions, NoMediaError
from skipwatch.adapters.registry import adapter_for
from skipwatch.cli import app
from skipwatch.detect import Detected
from skipwatch.errors import ExitCode
from skipwatch.models import LinkContext, MediaInfo, ProviderCall
from skipwatch.providers import content_free as cf
from skipwatch.providers import links
from skipwatch.workdir import WorkDir
from tests.unit._work import home_work

REC = Path(__file__).resolve().parents[1] / "fixtures" / "recorded"
G2_URL = "https://x.com/mattpocockuk/status/1505892984658743300"
LINKING_URL = "https://x.com/mattpocockuk/status/1505898799335628805"
# Where the two posts' t.co links point (one HEAD each, 2026-10-09; the old handle is X's).
T_CO = {
    "https://t.co/jgKkwTzSKL": "https://twitter.com/mpocock1/status/1505892984658743300/video/1",
    "https://t.co/rItbRmOjam": "https://twitter.com/mpocock1/status/1504802045794078723",
}
LINKED_URL = "https://x.com/i/status/1504802045794078723"


def recorded(name: str) -> dict:
    return json.loads((REC / "x" / f"{name}.info.json").read_text(encoding="utf-8"))


def linked_post_info() -> dict:
    """The post the "Previous tip:" reply links, derived from the recorded reply: yt-dlp gave the
    reply the linked post's video, so formats, media id and duration are the same."""
    info = recorded("link-to-video-post")
    return info | {
        "description": "TypeScript Tip #10: assertion functions. https://t.co/abcdefghij",
        "title": "Matt Pocock - TypeScript Tip #10: assertion functions.",
        "timestamp": 1647607680,
        "upload_date": "20220318",
        "webpage_url": "https://x.com/mattpocockuk/status/1504802045794078723",
    }


@pytest.fixture
def free_route(monkeypatch):
    """Fake yt-dlp (url -> info dict) and t.co; returns what was asked for."""
    seen: dict = {"extract": [], "resolve": [], "fetch": [], "download": 0}

    def install(infos: dict, fetched: dict | None = None):
        def extract(url, opts):
            seen["extract"].append(url)
            info = infos.get(url)
            if isinstance(info, Exception):
                raise info
            if info is None:
                raise cf.FreeRouteError("metadata", f"ERROR: [twitter] no fixture for {url}")
            return info

        def download(info_, work, opts, failed=None):
            seen["download"] += 1
            return MediaInfo(path="media/video.mp4", width=1280, height=720, has_audio=True)

        def resolve(url, calls=None, budget=None):
            seen["resolve"].append(url)
            seen.setdefault("budgets", []).append(budget)
            if calls is not None:
                calls.append(ProviderCall(provider="free", op="link.resolve", ok=True))
            return T_CO.get(url)

        def fetch_urls(urls, calls, budget=None):
            seen["fetch"].append(list(urls))
            seen.setdefault("budgets", []).append(budget)
            got = [(fetched or {}).get(u) for u in urls]
            return [link for link in got if link is not None]

        monkeypatch.setattr(cf, "extract", extract)
        monkeypatch.setattr(cf, "download", download)
        monkeypatch.setattr(links, "resolve", resolve)
        monkeypatch.setattr(links, "fetch_urls", fetch_urls)
        return seen

    return install


def build(url, tmp, opts=None):
    work = WorkDir(tmp)
    work.ensure()
    return x.ADAPTER.build(
        Detected(kind="url", platform="x", value=url), work, opts or IngestOptions()
    )


def test_x_adapter_is_registered():
    assert adapter_for("x") is x.ADAPTER


@pytest.mark.parametrize(
    ("url", "post_id"),
    [
        ("https://x.com/someone/status/123", "123"),
        ("https://twitter.com/someone/status/123/video/1", "123"),
        ("https://mobile.twitter.com/someone/statuses/123?s=20", "123"),
        ("https://x.com/i/status/123", "123"),
        ("https://x.com/i/web/status/123", "123"),
        ("https://x.com/someone", None),
        ("https://example.com/someone/status/123", None),
    ],
)
def test_post_id_comes_from_the_status_path(url, post_id):
    assert x.post_id(url) == post_id


def test_x_fixture_builds_video_bundle_with_full_text(tmp_path, free_route):
    info = recorded("g2-deep-partials")
    seen = free_route({G2_URL: info})
    bundle = build(G2_URL, tmp_path / "w")
    assert bundle.source.kind == "video" and bundle.source.platform == "x"
    assert bundle.context.post_text == info["description"]  # full text, never the cut title
    assert bundle.source.author == "@mattpocockuk" and bundle.source.author_name == "Matt Pocock"
    # Decision 1: the post id from webpage_url, not yt-dlp's media id.
    assert bundle.source.canonical_url == "https://x.com/i/status/1505892984658743300"
    assert info["id"] not in bundle.source.canonical_url
    assert bundle.source.url == G2_URL
    assert bundle.media is not None and seen["download"] == 1
    assert bundle.route.context == "free" and bundle.route.media == "free"
    assert bundle.route.fallbacks == []
    assert bundle.context.thread == []
    # The t.co link was the post's own video: resolved, not fetched as a page, no second extract.
    assert seen["resolve"] == ["https://t.co/jgKkwTzSKL"]
    assert seen["extract"] == [G2_URL]
    assert all("twitter.com" not in u and "x.com" not in u for urls in seen["fetch"] for u in urls)


def test_x_links_are_fetched_and_capped(tmp_path, free_route):
    info = recorded("g2-deep-partials")
    page_urls = [f"https://docs{n}.example.com/guide" for n in range(7)]
    info["description"] = "Read these: " + " ".join(page_urls) + " https://t.co/jgKkwTzSKL"
    doc = LinkContext(url=page_urls[0], title="Guide", text="How to use it.")
    seen = free_route({G2_URL: info}, fetched={page_urls[0]: doc})
    bundle = build(G2_URL, tmp_path / "w")
    assert seen["fetch"] == [page_urls[:5]]  # at most 5 links per post (R-ING-1)
    assert bundle.context.links == [doc]
    assert bundle.context.post_text == info["description"]
    assert [c.op for c in bundle.provider_calls][0] == "yt-dlp.metadata"


def test_x_link_to_video_post_credits_the_linked_post(tmp_path, free_route):
    reply = recorded("link-to-video-post")
    linked = linked_post_info()
    seen = free_route({LINKING_URL: reply, LINKED_URL: linked})
    bundle = build(LINKING_URL, tmp_path / "w")
    # Decision 2: source describes the LINKED post, so its creator gets the credit.
    assert bundle.source.url == LINKED_URL and bundle.source.canonical_url == LINKED_URL
    assert bundle.source.author == "@mattpocockuk"
    assert bundle.source.title == linked["title"]
    assert bundle.source.posted_at == "2022-03-18T12:48:00Z"
    assert bundle.context.post_text == linked["description"]
    # The requested post's text is context, with its own URL.
    assert bundle.context.thread == [
        f"Requested post https://x.com/i/status/1505898799335628805: {reply['description']}"
    ]
    assert bundle.context.links[0].url == LINKED_URL
    assert bundle.context.links[0].text == linked["description"]
    # Decision 3 after the M5-A review: provenance notes live in bundle.notes, not fallbacks.
    assert bundle.notes == [f"video came from a linked post: {LINKED_URL}"]
    assert bundle.route.fallbacks == []
    assert seen["download"] == 1  # the media yt-dlp already gave the reply is the linked video
    assert [c.op for c in bundle.provider_calls].count("yt-dlp.metadata") == 2


def test_x_linked_post_with_a_different_video_keeps_the_requested_post(tmp_path, free_route):
    reply = recorded("link-to-video-post")
    other = linked_post_info() | {"duration": 300.0}
    free_route({LINKING_URL: reply, LINKED_URL: other})
    bundle = build(LINKING_URL, tmp_path / "w")
    assert bundle.source.canonical_url == "https://x.com/i/status/1505898799335628805"
    assert bundle.context.post_text == reply["description"] and bundle.context.thread == []
    assert bundle.route.fallbacks == [] and bundle.notes == []


def test_x_linked_post_that_fails_to_load_keeps_the_requested_post(tmp_path, free_route):
    reply = recorded("link-to-video-post")
    failure = cf.FreeRouteError("metadata", "ERROR: [twitter] 1: something broke")
    free_route({LINKING_URL: reply, LINKED_URL: failure})
    bundle = build(LINKING_URL, tmp_path / "w")
    assert bundle.source.canonical_url == "https://x.com/i/status/1505898799335628805"
    assert bundle.route.fallbacks == []
    failed = [c for c in bundle.provider_calls if not c.ok]
    assert failed and failed[-1].op == "yt-dlp.metadata"


def test_x_text_only_post_raises_no_media(tmp_path, free_route):
    error = json.loads((REC / "text" / "text-only-reply.error.json").read_text(encoding="utf-8"))
    free_route({error["url"]: cf.FreeRouteError("metadata", error["message"])})
    with pytest.raises(NoMediaError):
        build(error["url"], tmp_path / "w")


def test_x_text_only_free_route_is_exit_7_naming_treg(tmp_path, free_route, sw_home):
    error = json.loads((REC / "text" / "text-only-reply.error.json").read_text(encoding="utf-8"))
    free_route({error["url"]: cf.FreeRouteError("metadata", error["message"])})
    r = CliRunner().invoke(
        app, ["ingest", error["url"], "--work", str(home_work("w")), "--provider", "free"]
    )
    assert r.exit_code == ExitCode.NO_CONTENT, r.output
    assert "This post has no video. Enable treg (Tier 3) to read text posts." in r.output


def test_x_protected_post_is_exit_4(tmp_path, free_route, sw_home):
    message = "ERROR: [twitter] 1: You are not authorized to view this protected tweet"
    free_route({G2_URL: cf.FreeRouteError("metadata", message)})
    r = CliRunner().invoke(
        app, ["ingest", G2_URL, "--work", str(home_work("w")), "--provider", "free"]
    )
    assert r.exit_code == ExitCode.PRIVATE_CONTENT
    assert "--cookies-from-browser" in r.output


def test_x_post_with_own_video_and_a_post_link_keeps_its_own_video(tmp_path, free_route):
    """yt-dlp follows a linked post only when the post has no media of its own."""
    info = recorded("g2-deep-partials")
    info["description"] = "Previous tip: https://t.co/rItbRmOjam " + info["description"]
    seen = free_route({G2_URL: info, LINKED_URL: linked_post_info() | {"duration": 114.13}})
    bundle = build(G2_URL, tmp_path / "w")
    assert bundle.source.canonical_url == "https://x.com/i/status/1505892984658743300"
    assert bundle.route.fallbacks == [] and bundle.context.thread == []
    assert seen["extract"] == [G2_URL]


def test_x_login_error_names_x(tmp_path, free_route, sw_home):
    message = "ERROR: [twitter] 1: NSFW tweet requires authentication. Use --cookies, ..."
    free_route({G2_URL: cf.FreeRouteError("metadata", message)})
    r = CliRunner().invoke(
        app, ["ingest", G2_URL, "--work", str(home_work("w")), "--provider", "free"]
    )
    assert r.exit_code == ExitCode.PRIVATE_CONTENT
    assert "X says this needs a login" in r.output


def test_x_author_is_the_handle_never_the_display_name(tmp_path, free_route):
    """AUTHOR_FIELDS["x"]: uploader_id is the handle, uploader the display name. With no handle
    the author stays empty rather than passing the display name off as an @handle."""
    info = recorded("g2-deep-partials")
    del info["uploader_id"]
    free_route({G2_URL: info})
    bundle = build(G2_URL, tmp_path / "w")
    assert bundle.source.author is None and bundle.source.author_name == "Matt Pocock"


def test_x_linked_post_author_uses_the_x_fields(tmp_path, free_route):
    reply = recorded("link-to-video-post")
    linked = linked_post_info() | {"uploader_id": None, "uploader": "Someone Else"}
    free_route({LINKING_URL: reply, LINKED_URL: linked})
    bundle = build(LINKING_URL, tmp_path / "w")
    assert bundle.source.author is None and bundle.source.author_name == "Someone Else"


def test_x_short_links_and_pages_share_one_post_budget(tmp_path, free_route):
    info = recorded("g2-deep-partials")
    info["description"] += " https://docs.example.com/guide"
    seen = free_route({G2_URL: info})
    build(G2_URL, tmp_path / "w")
    budgets = seen["budgets"]
    assert len(budgets) == 2 and budgets[0] is not None and budgets[0] is budgets[1]
