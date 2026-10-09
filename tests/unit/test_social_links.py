"""R-ING-1 on TikTok, Instagram and Facebook: links in the post text are fetched as context.

The recorded captions hold no URL, so each fixture gets one appended; content_free and the
link fetch are faked (no network)."""

import json
from pathlib import Path

import pytest

from skipwatch import media
from skipwatch.adapters.base import IngestOptions
from skipwatch.adapters.registry import adapter_for
from skipwatch.detect import Detected
from skipwatch.models import LinkContext, MediaInfo, ProviderCall
from skipwatch.providers import content_free as cf
from skipwatch.providers import links
from skipwatch.workdir import WorkDir

REC = Path(__file__).resolve().parents[1] / "fixtures" / "recorded"
FIXTURES = {
    "tiktok": "tiktok/g3-copilot-cli",
    "instagram": "instagram/g4-gh-secure",
    "facebook": "facebook/govsg-haze",
}
REPO = "https://github.com/o/r"


@pytest.fixture
def fakes(monkeypatch):
    fetched: list[str] = []

    def fetch_link(url, calls=None, budget=None):
        fetched.append(url)
        if calls is not None:
            calls.append(ProviderCall(provider="free", op="link.get", ok=True, endpoint="x"))
        return LinkContext(url=url, title="r", text="# r\n\nInstall: run it.")

    monkeypatch.setattr(links, "fetch_link", fetch_link)
    monkeypatch.setattr(cf, "download_captions", lambda *a, **k: None)
    monkeypatch.setattr(
        cf, "download", lambda *a, **k: MediaInfo(path="media/video.mp4", width=720, height=1280)
    )
    monkeypatch.setattr(media, "probe", lambda p: {"format": {"duration": "30"}, "streams": []})
    return fetched


@pytest.mark.parametrize("platform", sorted(FIXTURES))
def test_r_ing_1_social_post_links_are_fetched(tmp_path, monkeypatch, fakes, platform):
    info = json.loads((REC / f"{FIXTURES[platform]}.info.json").read_text(encoding="utf-8"))
    info["description"] = (info["description"] or "") + f" Code: {REPO}"
    monkeypatch.setattr(cf, "extract", lambda url, opts: info)
    work = WorkDir(tmp_path / "w")
    work.ensure()
    adapter = adapter_for(platform)
    assert adapter is not None
    bundle = adapter.build(
        Detected(kind="url", platform=platform, value="https://example.com/p"),
        work,
        IngestOptions(),
    )
    assert fakes == [REPO]
    assert [link.url for link in bundle.context.links] == [REPO]
    assert bundle.context.post_text == info["description"]
    assert [c.op for c in bundle.provider_calls][-1] == "link.get"


@pytest.mark.parametrize("platform", sorted(FIXTURES))
def test_social_post_without_links_fetches_nothing(tmp_path, monkeypatch, fakes, platform):
    info = json.loads((REC / f"{FIXTURES[platform]}.info.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(cf, "extract", lambda url, opts: info)
    work = WorkDir(tmp_path / "w")
    work.ensure()
    bundle = adapter_for(platform).build(  # type: ignore[union-attr]
        Detected(kind="url", platform=platform, value="https://example.com/p"),
        work,
        IngestOptions(),
    )
    assert fakes == [] and bundle.context.links == []
    assert all(c.op != "link.get" for c in bundle.provider_calls)
