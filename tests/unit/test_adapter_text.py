"""Text adapter: a page with no video becomes a text source when it has 200+ words (8.2)."""

import pytest
from typer.testing import CliRunner

from skipwatch.adapters import text
from skipwatch.adapters.base import IngestOptions
from skipwatch.adapters.registry import adapter_for
from skipwatch.cli import app
from skipwatch.detect import Detected
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import IngestBundle, LinkContext, ProviderCall, Route, SourceInfo
from skipwatch.providers import content_free as cf
from skipwatch.providers import links
from skipwatch.workdir import WorkDir

PAGE = "https://blog.example.com/how-i-ship"
X_TEXT_POST = "https://x.com/someone/status/1506032263359864843"


def words(n: int) -> str:
    return " ".join(f"word{i}" for i in range(n))


@pytest.fixture
def pages(monkeypatch):
    """Fake links.fetch_link and links.fetch_all; returns the request log."""
    seen: dict = {"link": [], "all": []}

    def install(page: LinkContext | None, linked: list[LinkContext] | None = None):
        def fetch_link(url, calls=None):
            seen["link"].append(url)
            if calls is not None:
                calls.append(ProviderCall(provider="free", op="link.get", ok=page is not None))
            return page

        def fetch_all(text_, calls):
            seen["all"].append(text_)
            return linked or []

        monkeypatch.setattr(links, "fetch_link", fetch_link)
        monkeypatch.setattr(links, "fetch_all", fetch_all)
        return seen

    return install


def build(url, tmp, platform="generic", opts=None):
    work = WorkDir(tmp)
    work.ensure()
    detected = Detected(kind="url", platform=platform, value=url)
    return text.ADAPTER.build(detected, work, opts or IngestOptions(provider="free"))


def test_text_adapter_is_registered():
    assert adapter_for("text") is text.ADAPTER


def test_text_page_over_200_words_becomes_text_kind(tmp_path, pages):
    body = words(250) + " see https://github.com/o/r"
    readme = LinkContext(url="https://github.com/o/r", text="# r")
    seen = pages(LinkContext(url=PAGE, title="How I ship", text=body), [readme])
    bundle = build(PAGE, tmp_path / "w")
    assert bundle.source.kind == "text" and bundle.source.platform == "generic"
    assert bundle.source.url == PAGE and bundle.source.title == "How I ship"
    assert bundle.context.post_text == body
    assert bundle.context.links == [readme]
    assert bundle.media is None
    assert bundle.route == Route(context="free", media=None)
    assert seen["link"] == [PAGE] and seen["all"] == [body]
    assert [c.op for c in bundle.provider_calls] == ["link.get"]


def test_text_page_under_200_words_is_exit_7(tmp_path, pages):
    pages(LinkContext(url=PAGE, title="Short", text=words(199)))
    with pytest.raises(SkipwatchError) as e:
        build(PAGE, tmp_path / "w")
    assert e.value.code == ExitCode.NO_CONTENT
    assert e.value.message == f"no video and under 200 words of text at {PAGE}"


def test_text_page_that_cannot_be_fetched_is_exit_7(tmp_path, pages):
    pages(None)
    with pytest.raises(SkipwatchError) as e:
        build(PAGE, tmp_path / "w")
    assert e.value.code == ExitCode.NO_CONTENT and PAGE in e.value.message


def test_unsupported_page_via_cli_becomes_a_text_bundle(tmp_path, monkeypatch, pages, sw_home):
    def extract(url, opts):
        raise cf.FreeRouteError("metadata", f"ERROR: Unsupported URL: {url}")

    monkeypatch.setattr(cf, "extract", extract)
    pages(LinkContext(url=PAGE, title="How I ship", text=words(300)))
    r = CliRunner().invoke(
        app, ["ingest", PAGE, "--work", str(tmp_path / "w"), "--provider", "free", "--json"]
    )
    assert r.exit_code == 0, r.output
    bundle = IngestBundle.model_validate_json(r.stdout)
    assert bundle.source.kind == "text" and bundle.media is None


def test_x_text_post_without_providers_is_exit_7_naming_treg(tmp_path, pages):
    seen = pages(LinkContext(url=X_TEXT_POST, text=words(500)))
    with pytest.raises(SkipwatchError) as e:
        build(X_TEXT_POST, tmp_path / "w", platform="x")
    assert e.value.code == ExitCode.NO_CONTENT
    assert e.value.message == "This post has no video. Enable treg (Tier 3) to read text posts."
    assert seen["link"] == []  # x.com pages are a JavaScript shell: never fetched as text


class FakeProvider:
    name = "fake"

    def __init__(self, bundle):
        self.bundle = bundle
        self.asked = []

    def available(self):
        return True

    def build_text_x(self, detected, work, opts):
        self.asked.append(detected.value)
        return self.bundle


def test_x_text_post_asks_enabled_providers_with_build_text_x(tmp_path, monkeypatch, pages):
    from skipwatch import ingest

    made = IngestBundle(
        source=SourceInfo(kind="text", platform="x", url=X_TEXT_POST),
        route=Route(context="fake"),
    )
    none, some = FakeProvider(None), FakeProvider(made)
    monkeypatch.setattr(ingest, "content_providers", lambda: [none, some])
    pages(None)
    bundle = build(X_TEXT_POST, tmp_path / "w", platform="x", opts=IngestOptions())
    assert bundle is made
    assert none.asked == [X_TEXT_POST] and some.asked == [X_TEXT_POST]


def test_x_text_post_with_provider_free_never_asks_providers(tmp_path, monkeypatch, pages):
    from skipwatch import ingest

    provider = FakeProvider(None)
    monkeypatch.setattr(ingest, "content_providers", lambda: [provider])
    pages(None)
    with pytest.raises(SkipwatchError):
        build(X_TEXT_POST, tmp_path / "w", platform="x", opts=IngestOptions(provider="free"))
    assert provider.asked == []
