"""treg content provider on the M3 spike's recorded responses (tests/fixtures/recorded/treg).

No treg process ever runs: a fake runner stands in for subprocess.run and serves each recorded
response by endpoint (argv[2]), with the stderr charge line the CLI prints.
"""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from skipwatch import ingest
from skipwatch.adapters.base import DownloadFailed, IngestOptions, NoMediaError
from skipwatch.detect import Detected
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import (
    Config,
    IngestBundle,
    IngestContext,
    LinkContext,
    MediaInfo,
    ProviderCall,
    Route,
    SourceInfo,
)
from skipwatch.providers import content_treg, links
from skipwatch.providers.content_treg import CATALOG_PRICES, TregClient, TregProvider
from skipwatch.transcribe import run_transcribe
from skipwatch.workdir import WorkDir, write_model

REC = Path(__file__).resolve().parents[1] / "fixtures" / "recorded" / "treg"
G2_URL = "https://x.com/i/status/1505892984658743300"
G2_ID = "1505892984658743300"
CALL_ID = "0123456789abcdef0123456789abcdef"
DOT = "·"


def recorded(endpoint: str) -> dict:
    return json.loads((REC / f"{endpoint}.json").read_text(encoding="utf-8"))


def charge_line(endpoint: str, n: int) -> str:
    cost = recorded(endpoint).get("costUsd") or 0.00045
    return f"treg: charged ${cost:g} {DOT} call id {CALL_ID[:-2]}{n:02d}\n"


class FakeRunner:
    """subprocess.run stand-in: `treg call <endpoint>` answers from the recorded fixtures (or
    an override), `treg review` and `treg balance` succeed. Every argv is kept."""

    def __init__(self, overrides: dict | None = None):
        self.argvs: list[list[str]] = []
        self.overrides: dict[str, Any] = overrides or {}

    def __call__(self, argv, **kwargs) -> subprocess.CompletedProcess:
        self.argvs.append(list(argv))
        if argv[1] == "review":
            return subprocess.CompletedProcess(argv, 0, stdout="received\n", stderr="")
        if argv[1] == "balance":
            return subprocess.CompletedProcess(argv, 0, stdout='{"balance_micro": 1}', stderr="")
        endpoint = argv[2]
        n = sum(1 for a in self.argvs if a[1] == "call")
        if endpoint in self.overrides:
            override = self.overrides[endpoint]
            if callable(override):
                return override(argv, n)
            return override
        stdout = json.dumps(recorded(endpoint))
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr=charge_line(endpoint, n))

    def calls(self) -> list[list[str]]:
        return [a for a in self.argvs if a[1] == "call"]

    def reviews(self) -> list[list[str]]:
        return [a for a in self.argvs if a[1] == "review"]


@pytest.fixture
def fake_runner():
    return FakeRunner()


def client(runner, cap: float = 0.05) -> TregClient:
    return TregClient(cap, runner=runner, exe="treg")


# ---- the client: call log, cost, cap, review (Task M4-A1) ----


def test_call_logs_cost_and_call_id_from_stderr(fake_runner):
    c = client(fake_runner)
    data = c.call("anyapi.twitter.thread", body={"url": G2_URL})
    assert data is not None and data["threadLength"] == 3  # output.data, not the envelope
    assert fake_runner.calls()[0] == [
        "treg",
        "call",
        "anyapi.twitter.thread",
        "--method",
        "POST",
        "--data",
        json.dumps({"url": G2_URL}),
    ]
    [call] = c.calls
    assert call.provider == "treg" and call.ok and call.endpoint == "anyapi.twitter.thread"
    assert call.cost_usd == pytest.approx(0.00375)
    assert call.call_id == f"{CALL_ID[:-2]}01"
    assert c.spent == pytest.approx(0.00375)


def test_routed_call_returns_output_and_sends_the_max_cost_header(fake_runner):
    c = client(fake_runner)
    data = c.call(
        "treg.x.post.comments",
        body={"tweet_id": G2_ID},
        headers={"X-Treg-Route-Max-Cost": "0.01"},
    )
    assert data is not None and len(data["comments"]) == 22  # routed: `output` itself
    argv = fake_runner.calls()[0]
    assert argv[argv.index("--header") + 1] == "X-Treg-Route-Max-Cost: 0.01"
    assert c.calls[0].cost_usd == pytest.approx(0.00045)


def test_same_request_twice_is_served_from_the_run_log(fake_runner):
    c = client(fake_runner)
    first = c.call("anyapi.twitter.thread", body={"url": G2_URL})
    second = c.call("anyapi.twitter.thread", body={"url": G2_URL})
    assert first == second
    assert len(fake_runner.calls()) == 1 and len(c.calls) == 1  # billed once


def test_treg_not_found_and_bad_json_fall_through():
    not_found = subprocess.CompletedProcess(
        [], 0, stdout='{"output": {"found": false, "data": null}, "costUsd": 0}', stderr=""
    )
    oops = subprocess.CompletedProcess([], 0, stdout="oops", stderr="")
    failed = subprocess.CompletedProcess(
        [], 1, stdout="", stderr="treg: HTTP 502 bad gateway at https://h/x?token=secret\nmore\n"
    )
    runner = FakeRunner(
        {
            "anyapi.twitter.thread": not_found,
            "anyapi.twitter.tweet_transcript": oops,
            "anyapi.tiktok.video_download": failed,
        }
    )
    c = client(runner)
    assert c.call("anyapi.twitter.thread", body={"url": G2_URL}) is None
    assert c.call("anyapi.twitter.tweet_transcript", body={"url": G2_URL}) is None
    assert c.call("anyapi.tiktok.video_download", body={"url": "https://t/v"}) is None
    assert [call.ok for call in c.calls] == [False, False, False]
    assert c.calls[0].error == "not found"
    assert c.calls[1].error == "not JSON"
    assert c.calls[2].error == "treg: HTTP 502 bad gateway at https://h/x?"  # first line, cut
    assert "secret" not in json.dumps([call.model_dump() for call in c.calls])


def test_timeout_counts_the_estimate_against_the_cap():
    def slow(argv, n):
        raise subprocess.TimeoutExpired(argv, 60)

    c = client(FakeRunner({"anyapi.twitter.thread": slow}))
    assert c.call("anyapi.twitter.thread", body={"url": G2_URL}) is None
    assert c.calls[0].error == "timeout" and not c.calls[0].ok
    assert c.spent == pytest.approx(CATALOG_PRICES["anyapi.twitter.thread"])


def test_treg_cost_cap_stops_calls(fake_runner):
    c = client(fake_runner, cap=0.004)
    assert c.call("anyapi.twitter.thread", body={"url": G2_URL}) is not None  # 0.00375
    refused = c.call(
        "treg.x.post.comments", body={"tweet_id": G2_ID}, headers={"X-Treg-Route-Max-Cost": "0.01"}
    )
    assert refused is None
    assert [a[2] for a in fake_runner.calls()] == ["anyapi.twitter.thread"]  # never ran
    assert c.calls[-1].error == "cost cap" and not c.calls[-1].ok
    assert sum(call.cost_usd for call in c.calls) <= 0.004
    assert c.capped


def test_unknown_endpoint_is_never_called(fake_runner):
    with pytest.raises(ValueError, match="no catalog price"):
        client(fake_runner).call("anyapi.anything.else", body={})
    assert fake_runner.calls() == []


def test_r_ing_3_every_used_call_is_reviewed(fake_runner):
    c = client(fake_runner)
    c.call("anyapi.twitter.thread", body={"url": G2_URL})
    c.call("anyapi.twitter.tweet_transcript", body={"url": G2_URL})
    c.use("anyapi.twitter.thread")
    c.review_all()
    reviews = fake_runner.reviews()
    assert [r[2] for r in reviews] == [call.call_id for call in c.calls]  # one per logged id
    assert [r[3] for r in reviews] == ["useful", "not_sure"]  # unused gets not_sure
    for argv in reviews:
        reason = argv[argv.index("--reason") + 1]
        assert 0 < len(reason) < 200
    assert [call.review for call in c.calls] == ["useful", "not_sure"]
    c.review_all()  # a second pass reviews nothing again
    assert len(fake_runner.reviews()) == 2


def test_review_is_skipped_without_call_id_and_failure_leaves_review_unset():
    no_id = subprocess.CompletedProcess([], 0, stdout=json.dumps(recorded("anyapi.twitter.thread")))
    runner = FakeRunner({"anyapi.twitter.thread": no_id})
    c = client(runner)
    c.call("anyapi.twitter.thread", body={"url": G2_URL})
    c.review_all()
    assert runner.reviews() == []
    assert c.calls[0].review is None


def test_failed_call_with_an_id_is_reviewed_not_useful():
    stdout = '{"output": {"found": false, "data": null}}'
    stderr = f"treg: charged $0 {DOT} call id {CALL_ID}\n"
    runner = FakeRunner(
        {"anyapi.twitter.thread": subprocess.CompletedProcess([], 0, stdout, stderr)}
    )
    c = client(runner)
    c.call("anyapi.twitter.thread", body={"url": G2_URL})
    c.review_all()
    assert runner.reviews()[0][2:4] == [CALL_ID, "not_useful"]


def test_no_personal_data_in_argv(fake_runner):
    c = client(fake_runner)
    c.call("anyapi.twitter.thread", body={"url": G2_URL})
    c.call(
        "treg.x.post.comments", body={"tweet_id": G2_ID}, headers={"X-Treg-Route-Max-Cost": "0.01"}
    )
    c.use("anyapi.twitter.thread")
    c.review_all()
    allowed = {
        "treg",
        "call",
        "review",
        "--method",
        "POST",
        "--data",
        "--header",
        "--reason",
        "X-Treg-Route-Max-Cost: 0.01",
        "useful",
        "not_sure",
        json.dumps({"url": G2_URL}),
        json.dumps({"tweet_id": G2_ID}),
        *CATALOG_PRICES,
        *(call.call_id for call in c.calls),
        *content_treg.REVIEW_REASONS.values(),
    }
    for argv in fake_runner.argvs:
        assert set(argv) <= allowed, argv


# ---- login and availability ----


def test_logged_in_false_without_binary(monkeypatch, fake_runner):
    monkeypatch.setattr(content_treg, "_treg_path", lambda: None)
    assert content_treg.logged_in(fake_runner) is False
    assert content_treg.TregProvider(runner=fake_runner).available() is False
    assert fake_runner.argvs == []


def test_logged_in_runs_the_free_balance_command(monkeypatch, fake_runner):
    monkeypatch.setattr(content_treg, "_treg_path", lambda: "/bin/treg")
    assert content_treg.logged_in(fake_runner) is True
    assert fake_runner.argvs == [["/bin/treg", "balance", "--json", "--limit", "1"]]


@pytest.mark.parametrize(
    "result",
    [
        subprocess.CompletedProcess([], 1, stdout="", stderr="not logged in"),
        subprocess.CompletedProcess([], 0, stdout="Balance: $3", stderr=""),
        OSError("gone"),
        subprocess.TimeoutExpired([], 10),
    ],
)
def test_logged_in_false_on_any_failure(monkeypatch, result):
    monkeypatch.setattr(content_treg, "_treg_path", lambda: "/bin/treg")

    def runner(argv, **kwargs):
        if isinstance(result, BaseException):
            raise result
        return result

    assert content_treg.logged_in(runner) is False


def test_provider_is_registered_under_its_name():
    from skipwatch.providers.registry import content_providers

    assert [p.name for p in content_providers()] == ["treg"]
    assert content_treg.PROVIDER.name == "treg"


def test_unit_tests_never_reach_a_real_treg():
    """tests/conftest.py hides the treg binary from every non-live test."""
    assert content_treg._treg_path() is None
    assert content_treg.PROVIDER.available() is False


# ---- enrichment and media fallback per platform (Task M4-A2) ----

G2_TEXT = recorded("anyapi.twitter.thread")["output"]["data"]["tweets"][0]["text"]
TIKTOK_URL = "https://www.tiktok.com/@github/video/7624273546776153377"
INSTAGRAM_URL = "https://www.instagram.com/reel/Dd-rJlkE_Z5/"
FACEBOOK_URL = "https://www.facebook.com/gov.sg/videos/10154383743583686/"
YOUTUBE_URL = "https://www.youtube.com/watch?v=abcdefghijk"


def work(tmp_path) -> WorkDir:
    w = WorkDir(tmp_path / "w")
    w.ensure()
    return w


def video_bundle(platform: str, url: str, **context) -> IngestBundle:
    canonical = G2_URL if platform == "x" else url
    author = {"x": "@mattpocockuk", "tiktok": "@github", "instagram": "@github"}.get(platform)
    return IngestBundle(
        source=SourceInfo(
            kind="video", platform=platform, url=url, canonical_url=canonical, author=author
        ),
        context=IngestContext(**({"post_text": G2_TEXT} if platform == "x" else {}) | context),
        media=MediaInfo(path="media/video.mp4", width=1280, height=720, has_audio=True),
        provider_calls=[ProviderCall(provider="free", op="yt-dlp.metadata", ok=True)],
        route=Route(context="free", media="free"),
    )


@pytest.fixture
def treg_on(monkeypatch):
    """treg 'installed' with a fake runner; t.co, link fetches, media GET and probe faked."""
    seen: dict = {"resolve": [], "fetch": [], "get": []}
    monkeypatch.setattr(content_treg, "_treg_path", lambda: "treg")
    monkeypatch.setattr(content_treg, "_max_cost", lambda: 0.05)

    def resolve(url, calls=None, budget=None):
        seen["resolve"].append(url)
        return {"https://t.co/gh": "https://github.com/someorg/somerepo"}.get(
            url, "https://twitter.com/mpocock1/status/1"
        )

    def fetch_urls(urls, calls, budget=None):
        seen["fetch"].append(list(urls))
        return [LinkContext(url=u, title="README", text="readme text") for u in urls]

    def download_media(url, dest):
        seen["get"].append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\0" * 16)

    def probe_media(work_, path):
        return MediaInfo(path="media/video.mp4", width=720, height=1280, has_audio=True)

    monkeypatch.setattr(links, "resolve", resolve)
    monkeypatch.setattr(links, "fetch_urls", fetch_urls)
    monkeypatch.setattr(content_treg, "download_media", download_media)
    monkeypatch.setattr(content_treg, "_probe_media", probe_media)
    return seen


def enrich_run(provider, bundle, w, opts=None) -> IngestBundle:
    """enrich, then the end-of-run hook ingest calls: the run's treg calls, reviewed."""
    got = provider.enrich(bundle, w, opts or IngestOptions())
    finished, _ = ingest._finish([provider], w, got)
    assert finished is not None
    return finished


def with_author_link_reply() -> dict:
    """The recorded comments plus one more author reply that links a repository."""
    body = recorded("treg.x.post.comments")
    extra = dict(body["output"]["comments"][0])
    extra.update(id="1507000000000000000", text="@replier9 The code: https://t.co/gh")
    body["output"]["comments"].append(extra)
    return body


def stdout_of(body: dict, n: int = 1) -> subprocess.CompletedProcess:
    stderr = f"treg: charged $0.00045 {DOT} call id {CALL_ID[:-2]}{n:02d}\n"
    return subprocess.CompletedProcess([], 0, stdout=json.dumps(body), stderr=stderr)


def test_m4_x_enrich_fills_thread_replies_links_and_hint(tmp_path, treg_on):
    runner = FakeRunner({"treg.x.post.comments": stdout_of(with_author_link_reply(), 2)})
    provider = TregProvider(runner=runner)
    w = work(tmp_path)
    got = enrich_run(provider, video_bundle("x", G2_URL), w)
    assert got.context.thread == [
        "Previous tip:\n\nhttps://x.com/mpocock1/status/1504802045794078723",
        "Next tip:\n\nhttps://x.com/mpocock1/status/1506607945445949446",
    ]
    # the author's own replies to others, the address prefix dropped; continuations not repeated
    assert got.context.author_replies[:2] == [
        "Yep, getting there",
        "Absolutely, or ts-toolbelt etc",
    ]
    assert len(got.context.author_replies) == 7
    assert not any("@" in reply for reply in got.context.author_replies)
    assert not any("replier" in reply.lower() for reply in got.context.author_replies)
    # only the non-X page is fetched; x.com status links are a JavaScript shell
    assert treg_on["fetch"] == [["https://github.com/someorg/somerepo"]]
    assert [link.url for link in got.context.links] == ["https://github.com/someorg/somerepo"]
    assert got.transcript_hint.origin == "treg:anyapi.twitter.tweet_transcript"
    assert (got.transcript_hint.text or "").startswith("Deep partials are incredibly useful")
    treg_calls = [c for c in got.provider_calls if c.provider == "treg"]
    assert [c.endpoint for c in treg_calls] == [
        "anyapi.twitter.thread",
        "treg.x.post.comments",
        "anyapi.twitter.tweet_transcript",
    ]
    assert all(c.review == "useful" for c in treg_calls)  # every call reviewed after use
    assert got.provider_calls[0].provider == "free"  # the free route's log is kept
    assert got.media == video_bundle("x", G2_URL).media  # enrichment never touches media


def test_x_replies_never_include_other_people(tmp_path, treg_on):
    provider = TregProvider(runner=FakeRunner())
    got = provider.enrich(video_bundle("x", G2_URL), work(tmp_path), IngestOptions())
    others = [
        c["text"]
        for c in recorded("treg.x.post.comments")["output"]["comments"]
        if c["authorHandle"] != "mattpocockuk"
    ]
    blob = json.dumps(got.model_dump())
    assert others and not any(text in blob for text in others)


def test_treg_cost_cap_records_the_fallback(tmp_path, treg_on, monkeypatch):
    monkeypatch.setattr(content_treg, "_max_cost", lambda: 0.004)
    runner = FakeRunner()
    got = enrich_run(TregProvider(runner=runner), video_bundle("x", G2_URL), work(tmp_path))
    assert [a[2] for a in runner.calls()] == ["anyapi.twitter.thread"]
    assert got.route.fallbacks.count(content_treg.CAP_REACHED) == 1
    assert sum(c.cost_usd for c in got.provider_calls) <= 0.004
    assert len(got.context.thread) == 2  # what was paid for is still used


def test_text_only_x_post_via_treg(tmp_path, treg_on, monkeypatch):
    runner = FakeRunner()
    provider = TregProvider(runner=runner)
    monkeypatch.setattr(ingest, "content_providers", lambda: [provider])

    class NoVideo:
        def build(self, detected, work_, opts):
            raise NoMediaError(detected.value, "No video could be found in this tweet")

    real_adapter_for = ingest.adapter_for
    monkeypatch.setattr(
        ingest, "adapter_for", lambda p: NoVideo() if p == "x" else real_adapter_for(p)
    )
    detected = Detected(kind="url", platform="x", value=G2_URL)
    got = ingest._build(detected, work(tmp_path), IngestOptions(provider="treg"), Config())
    assert got.source.kind == "text" and got.media is None
    assert got.source.author == "@mattpocockuk"
    assert got.source.canonical_url == G2_URL
    assert got.context.post_text == G2_TEXT
    assert len(got.context.thread) == 2 and len(got.context.author_replies) == 6
    assert got.route.context == "treg"
    endpoints = [a[2] for a in runner.calls()]
    assert endpoints.count("anyapi.twitter.thread") == 1  # build and enrich share one call
    assert "anyapi.twitter.tweet_transcript" not in endpoints  # no video, no transcript
    treg_calls = [c for c in got.provider_calls if c.provider == "treg"]
    assert len(treg_calls) == len(endpoints)  # each call logged once
    assert all(c.review is not None for c in treg_calls)


def test_text_only_x_post_not_in_thread_is_none(tmp_path, treg_on):
    detected = Detected(kind="url", platform="x", value="https://x.com/a/status/42")
    provider = TregProvider(runner=FakeRunner())
    assert provider.build_text_x(detected, work(tmp_path), IngestOptions()) is None


def test_m4_free_route_unchanged_when_disabled(tmp_path, treg_on, monkeypatch):
    runner = FakeRunner()
    monkeypatch.setattr(ingest, "content_providers", lambda: [TregProvider(runner=runner)])
    fixed = video_bundle("x", G2_URL)

    class Fixed:
        def build(self, detected, work_, opts):
            return fixed

    monkeypatch.setattr(ingest, "adapter_for", lambda p: Fixed())
    detected = Detected(kind="url", platform="x", value=G2_URL)
    got = ingest._build(detected, work(tmp_path), IngestOptions(provider="free"), Config())
    assert runner.argvs == []
    assert got.model_dump_json(by_alias=True) == fixed.model_dump_json(by_alias=True)


def blocked(platform: str, url: str):
    partial = video_bundle(platform, url).model_copy(
        update={"media": None, "route": Route(context="free")}
    )

    class Blocked:
        def build(self, detected, work_, opts):
            raise DownloadFailed(
                ["free.yt-dlp.download: ERROR: HTTP Error 403: Forbidden"], partial
            )

    return Blocked()


@pytest.mark.parametrize(
    ("platform", "url", "endpoint", "media_url"),
    [
        ("tiktok", TIKTOK_URL, "anyapi.tiktok.video_download", "https://v16m.tiktokcdn-us.com"),
        (
            "instagram",
            INSTAGRAM_URL,
            "anyapi.instagram.post.detail",
            "https://scontent-scrubbed.cdninstagram.com",
        ),
        ("x", G2_URL, "anyapi.twitter.thread", "https://video.twimg.com"),
    ],
)
def test_treg_media_fallback_when_ytdlp_blocked(
    tmp_path, treg_on, monkeypatch, platform, url, endpoint, media_url
):
    runner = FakeRunner()
    monkeypatch.setattr(ingest, "content_providers", lambda: [TregProvider(runner=runner)])
    monkeypatch.setattr(ingest, "adapter_for", lambda p: blocked(platform, url))
    detected = Detected(kind="url", platform=platform, value=url)
    got = ingest._build(detected, work(tmp_path), IngestOptions(provider="treg"), Config())
    assert got.route.media == "treg"
    assert "free.yt-dlp.download: ERROR: HTTP Error 403: Forbidden" in got.route.fallbacks
    assert got.media is not None and got.media.path == "media/video.mp4"
    assert treg_on["get"] == [media_url]  # downloaded right after the call: URLs expire
    endpoints = [a[2] for a in runner.calls()]
    assert endpoints.count(endpoint) == 1  # the media call is never repeated by enrichment
    media_call = next(c for c in got.provider_calls if c.endpoint == endpoint)
    assert media_call.review == "useful"


def test_tiktok_media_prefers_the_clean_url(tmp_path, treg_on):
    body = recorded("anyapi.tiktok.video_download")
    body["output"]["data"]["watermarkedUrl"] = "https://watermarked.example"
    runner = FakeRunner({"anyapi.tiktok.video_download": stdout_of(body)})
    got = TregProvider(runner=runner).fetch_media(
        video_bundle("tiktok", TIKTOK_URL), work(tmp_path), IngestOptions()
    )
    assert got is not None and treg_on["get"] == ["https://v16m.tiktokcdn-us.com"]


def test_facebook_is_never_a_treg_media_fallback(tmp_path, treg_on):
    runner = FakeRunner()
    got = TregProvider(runner=runner).fetch_media(
        video_bundle("facebook", FACEBOOK_URL), work(tmp_path), IngestOptions()
    )
    assert got is None and runner.argvs == [] and treg_on["get"] == []


def test_failed_media_download_returns_none_and_is_logged(tmp_path, treg_on, monkeypatch):
    def refuse(url, dest):
        raise links.Refused("HTTP 403")

    monkeypatch.setattr(content_treg, "download_media", refuse)
    provider = TregProvider(runner=FakeRunner())
    w = work(tmp_path)
    bundle = video_bundle("tiktok", TIKTOK_URL)
    assert provider.fetch_media(bundle, w, IngestOptions()) is None
    got = enrich_run(provider, bundle, w)
    get = next(c for c in got.provider_calls if c.op == "media.get")
    assert not get.ok and get.error == "HTTP 403" and get.endpoint == "v16m.tiktokcdn-us.com"
    assert not (w.path / "media" / "video.mp4").exists()


def test_instagram_text_never_comes_from_treg(tmp_path, treg_on):
    runner = FakeRunner()
    bundle = video_bundle("instagram", INSTAGRAM_URL)
    got = TregProvider(runner=runner).enrich(bundle, work(tmp_path), IngestOptions())
    assert runner.calls() == []  # no instagram enrichment call at all
    assert got.context == bundle.context


def test_facebook_post_text_only_when_the_free_route_had_none(tmp_path, treg_on):
    runner = FakeRunner()
    provider = TregProvider(runner=runner)
    got = provider.enrich(video_bundle("facebook", FACEBOOK_URL), work(tmp_path), IngestOptions())
    assert (got.context.post_text or "").startswith("Worried about the haze?")
    has_text = video_bundle("facebook", FACEBOOK_URL, post_text="from yt-dlp")
    runner2 = FakeRunner()
    got2 = TregProvider(runner=runner2).enrich(has_text, work(tmp_path), IngestOptions())
    assert got2.context.post_text == "from yt-dlp" and runner2.calls() == []


def test_youtube_transcript_hint_only_without_captions(tmp_path, treg_on):
    runner = FakeRunner()
    with_captions = video_bundle("youtube", YOUTUBE_URL, captions_available=True)
    got = TregProvider(runner=runner).enrich(with_captions, work(tmp_path), IngestOptions())
    assert runner.calls() == [] and got.transcript_hint.text is None
    got = TregProvider(runner=runner).enrich(
        video_bundle("youtube", YOUTUBE_URL), work(tmp_path), IngestOptions()
    )
    assert got.transcript_hint.origin == "treg:anyapi.youtube.video_transcript_full"
    segments = recorded("anyapi.youtube.video_transcript_full")["output"]["data"]["segments"]
    assert got.transcript_hint.text == " ".join(s["text"].strip() for s in segments)
    assert json.loads(runner.calls()[0][6]) == {"url": YOUTUBE_URL, "captionKind": "any"}


def test_tiktok_transcript_hint(tmp_path, treg_on):
    body = {
        "costUsd": 0.0085,
        "output": {
            "found": True,
            "data": {"segments": [{"text": " one "}, {"text": "two"}], "transcript": "x"},
        },
    }
    runner = FakeRunner({"anyapi.tiktok.video_transcript_full": stdout_of(body)})
    got = TregProvider(runner=runner).enrich(
        video_bundle("tiktok", TIKTOK_URL), work(tmp_path), IngestOptions()
    )
    assert got.transcript_hint.origin == "treg:anyapi.tiktok.video_transcript_full"
    assert got.transcript_hint.text == "one two"


def test_r_ing_2_provider_transcript_never_primary(tmp_path, treg_on):
    w = work(tmp_path)
    (w.path / "captions").mkdir()
    vtt = "WEBVTT\n\n00:00:00.000 --> 00:00:04.000\nthe captions say this\n"
    (w.path / "captions" / "post.en.vtt").write_text(vtt, encoding="utf-8")
    bundle = video_bundle(
        "x", G2_URL, captions_available=True, captions_path="captions/post.en.vtt"
    )
    got = TregProvider(runner=FakeRunner()).enrich(bundle, w, IngestOptions())
    assert got.transcript_hint.text  # the provider transcript is a hint
    write_model(w.file("ingest.json"), got)
    transcript = run_transcribe(w, "auto", None)
    assert transcript.origin == "captions"
    assert all("Deep partials" not in s.text for s in transcript.segments)


class FakeResponse:
    def __init__(self, status=200, ctype="video/mp4", body=b"x" * 10, length=None):
        self.status_code = status
        self.headers = {"Content-Type": ctype}
        if length is not None:
            self.headers["Content-Length"] = str(length)
        self._chunks = [body[i : i + 4] for i in range(0, len(body), 4)]
        self.raw = self
        self.closed = False

    def read1(self, n, decode_content=False):
        return self._chunks.pop(0) if self._chunks else b""


@pytest.fixture
def fake_get(monkeypatch):
    seen: dict = {"urls": [], "closed": 0}

    def install(response):
        def get(url, deadline):
            seen["urls"].append(url)
            return response

        monkeypatch.setattr(links, "_get", get)
        monkeypatch.setattr(
            links, "_close", lambda r: seen.__setitem__("closed", seen["closed"] + 1)
        )
        return seen

    return install


def test_download_media_goes_through_the_vetted_transport(tmp_path, fake_get):
    seen = fake_get(FakeResponse(body=b"0123456789"))
    dest = tmp_path / "media" / "video.mp4"
    content_treg.download_media("https://video.twimg.com/v.mp4", dest)
    assert dest.read_bytes() == b"0123456789"
    assert seen["urls"] == ["https://video.twimg.com/v.mp4"] and seen["closed"] == 1
    assert not (tmp_path / "media" / "video.mp4.part").exists()


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (FakeResponse(status=403), "HTTP 403"),
        (FakeResponse(ctype="text/html"), "not a video: text/html"),
        (FakeResponse(length=2_000_000_000), "over the 1 GB media cap"),
    ],
)
def test_download_media_refuses_bad_answers(tmp_path, fake_get, response, message):
    seen = fake_get(response)
    dest = tmp_path / "media" / "video.mp4"
    with pytest.raises(links.Refused, match=message):
        content_treg.download_media("https://cdn.example/v", dest)
    assert not dest.exists() and seen["closed"] == 1


def test_download_media_stops_at_the_size_cap_while_streaming(tmp_path, fake_get, monkeypatch):
    monkeypatch.setattr(content_treg, "MEDIA_MAX_BYTES", 6)
    fake_get(FakeResponse(body=b"0123456789"))  # no Content-Length: the stream is counted
    dest = tmp_path / "media" / "video.mp4"
    with pytest.raises(links.Refused, match="cap"):
        content_treg.download_media("https://cdn.example/v", dest)
    assert not dest.exists() and not dest.with_name("video.mp4.part").exists()


def test_unknown_author_stores_no_replies_and_no_continuations(tmp_path, treg_on):
    """Without a known author handle nothing can be attributed: a comment or a thread post
    with no authorHandle is a stranger's text as far as SkipWatch can tell."""
    thread = {
        "costUsd": 0.00375,
        "output": {
            "found": True,
            "data": {"tweets": [{"id": G2_ID, "text": "root"}, {"id": "2", "text": "later"}]},
        },
    }
    comments = {
        "output": {
            "comments": [
                {"id": "9", "text": "@x I am a stranger", "authorHandle": None},
                {"id": "8", "text": "stranger two"},
            ]
        }
    }
    runner = FakeRunner(
        {"anyapi.twitter.thread": stdout_of(thread), "treg.x.post.comments": stdout_of(comments)}
    )
    bundle = video_bundle("x", G2_URL)
    bundle = bundle.model_copy(update={"source": bundle.source.model_copy(update={"author": None})})
    got = TregProvider(runner=runner).enrich(bundle, work(tmp_path), IngestOptions())
    assert got.context.author_replies == []
    assert got.context.thread == []


# ---- the end-of-run hook: every billed call logged and reviewed on every exit path ----


def calls_json(w: WorkDir) -> list[dict]:
    return json.loads(w.file("calls.json").read_text(encoding="utf-8"))["calls"]


class NoVideo:
    def build(self, detected, work_, opts):
        raise NoMediaError(detected.value, "No video could be found in this tweet")


def adapters(monkeypatch, **by_platform):
    real = ingest.adapter_for
    monkeypatch.setattr(ingest, "adapter_for", lambda p: by_platform.get(p) or real(p))


def run(url: str, w: WorkDir, provider: TregProvider, monkeypatch):
    monkeypatch.setattr(ingest, "content_providers", lambda: [provider])
    return ingest.run_ingest(url, w, IngestOptions(provider="treg"), cfg=Config())


def test_finish_on_success_logs_and_reviews_every_call(tmp_path, treg_on, monkeypatch, sw_home):
    fixed = video_bundle("x", G2_URL)

    class Fixed:
        def build(self, detected, work_, opts):
            return fixed

    adapters(monkeypatch, x=Fixed())
    provider = TregProvider(runner=FakeRunner())
    w = work(tmp_path)
    run(G2_URL, w, provider, monkeypatch)
    treg = [c for c in calls_json(w) if c["provider"] == "treg"]
    assert len(treg) == 3 and all(c["review"] == "useful" for c in treg)
    assert provider._runs == {}


def test_text_only_x_cache_hit_never_rebills_the_thread(tmp_path, treg_on, monkeypatch, sw_home):
    adapters(monkeypatch, x=NoVideo())
    runner = FakeRunner()
    provider = TregProvider(runner=runner)
    first = work(tmp_path / "1")
    run(G2_URL, first, provider, monkeypatch)
    billed = len(runner.calls())
    second = work(tmp_path / "2")
    got = run(G2_URL, second, provider, monkeypatch)
    assert got.from_cache and got.context.post_text == G2_TEXT
    assert len(runner.calls()) == billed  # nothing billed twice within the cache window
    assert calls_json(second) == []
    assert provider._runs == {}


def test_cache_hit_after_a_media_fallback_still_logs_the_billed_call(
    tmp_path, treg_on, monkeypatch, sw_home
):
    adapters(monkeypatch, tiktok=blocked("tiktok", TIKTOK_URL))
    runner = FakeRunner(
        {
            "anyapi.tiktok.video_transcript_full": stdout_of(
                {"costUsd": 0.0176, "output": {"found": True, "data": {"transcript": "words"}}}
            )
        }
    )
    provider = TregProvider(runner=runner)
    run(TIKTOK_URL, work(tmp_path / "1"), provider, monkeypatch)
    second = work(tmp_path / "2")
    got = run(TIKTOK_URL, second, provider, monkeypatch)
    assert got.from_cache and got.route.media == "treg"
    logged = calls_json(second)
    assert [c["endpoint"] for c in logged if c["op"] != "media.get"] == [
        "anyapi.tiktok.video_download"
    ]
    assert logged[0]["review"] == "useful"


def test_exit_3_still_logs_and_reviews_the_billed_call(tmp_path, treg_on, monkeypatch, sw_home):
    def refuse(url, dest):
        raise links.Refused("HTTP 403")

    monkeypatch.setattr(content_treg, "download_media", refuse)
    adapters(monkeypatch, tiktok=blocked("tiktok", TIKTOK_URL))
    provider = TregProvider(runner=FakeRunner())
    w = work(tmp_path)
    with pytest.raises(SkipwatchError) as raised:
        run(TIKTOK_URL, w, provider, monkeypatch)
    assert raised.value.code == ExitCode.DOWNLOAD_FAILED
    logged = calls_json(w)
    assert [c["op"] for c in logged] == ["tiktok.download", "media.get"]
    assert logged[0]["review"] == "not_sure" and logged[0]["cost_usd"] > 0
    assert provider._runs == {}


def test_text_x_not_found_still_logs_the_billed_thread(tmp_path, treg_on, monkeypatch, sw_home):
    adapters(monkeypatch, x=NoVideo())
    provider = TregProvider(runner=FakeRunner())
    w = work(tmp_path)
    with pytest.raises(SkipwatchError) as raised:
        run("https://x.com/a/status/42", w, provider, monkeypatch)
    assert raised.value.code == ExitCode.NO_CONTENT
    [logged] = calls_json(w)
    assert logged["endpoint"] == "anyapi.twitter.thread" and logged["review"] == "not_sure"
    assert provider._runs == {}


def test_an_exception_mid_enrich_still_logs_the_calls(tmp_path, treg_on, monkeypatch, sw_home):
    def boom(urls, calls, budget=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(links, "fetch_urls", boom)
    runner = FakeRunner({"treg.x.post.comments": stdout_of(with_author_link_reply(), 2)})
    fixed = video_bundle("x", G2_URL)

    class Fixed:
        def build(self, detected, work_, opts):
            return fixed

    adapters(monkeypatch, x=Fixed())
    provider = TregProvider(runner=runner)
    w = work(tmp_path)
    with pytest.raises(RuntimeError):
        run(G2_URL, w, provider, monkeypatch)
    assert [c["op"] for c in calls_json(w)] == ["x.thread", "x.comments"]
    assert provider._runs == {}


def test_availability_is_checked_once_per_run(tmp_path, treg_on, monkeypatch, sw_home):
    adapters(monkeypatch, x=NoVideo())
    runner = FakeRunner()
    run(G2_URL, work(tmp_path), TregProvider(runner=runner), monkeypatch)
    assert [a[1] for a in runner.argvs].count("balance") == 1
