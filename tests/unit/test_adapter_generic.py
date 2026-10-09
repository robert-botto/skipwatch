import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch.adapters.base import IngestOptions, NoMediaError
from skipwatch.adapters.generic import ADAPTER
from skipwatch.adapters.registry import adapter_for
from skipwatch.cli import app
from skipwatch.detect import Detected
from skipwatch.errors import ExitCode
from skipwatch.models import MediaInfo
from skipwatch.providers import content_free as cf
from skipwatch.workdir import WorkDir

REC = Path(__file__).resolve().parents[1] / "fixtures" / "recorded" / "generic"
PAGE = "https://example.com/post"


def raise_from_ytdlp(monkeypatch, message: str):
    def extract(url, opts):
        raise cf.FreeRouteError("metadata", message)

    monkeypatch.setattr(cf, "extract", extract)


def build(tmp, url=PAGE):
    work = WorkDir(tmp)
    work.ensure()
    return ADAPTER.build(Detected(kind="url", platform="generic", value=url), work, IngestOptions())


def test_generic_unsupported_url_raises_no_media(tmp_path, monkeypatch):
    raise_from_ytdlp(monkeypatch, f"ERROR: Unsupported URL: {PAGE}")
    with pytest.raises(NoMediaError) as e:
        build(tmp_path / "w")
    assert e.value.url == PAGE


def test_generic_info_without_formats_raises_no_media(tmp_path, monkeypatch):
    monkeypatch.setattr(
        cf, "extract", lambda url, opts: {"id": "p", "title": "A page", "formats": []}
    )
    with pytest.raises(NoMediaError):
        build(tmp_path / "w")


def test_generic_unsupported_url_via_cli_is_exit_7_naming_the_url(tmp_path, monkeypatch, sw_home):
    raise_from_ytdlp(monkeypatch, f"ERROR: Unsupported URL: {PAGE}")
    r = CliRunner().invoke(
        app, ["ingest", PAGE, "--work", str(tmp_path / "w"), "--provider", "free"]
    )
    assert r.exit_code == ExitCode.NO_CONTENT
    assert PAGE in r.output


def test_generic_login_wall_names_the_host(tmp_path, monkeypatch, sw_home):
    raise_from_ytdlp(
        monkeypatch,
        "ERROR: [vimeo] 1: The web client only works when logged-in. Use --cookies, ...",
    )
    r = CliRunner().invoke(
        app, ["ingest", "https://vimeo.com/1", "--work", str(tmp_path / "w"), "--provider", "free"]
    )
    assert r.exit_code == ExitCode.PRIVATE_CONTENT
    assert "vimeo.com" in r.output and "--cookies-from-browser" in r.output


@pytest.mark.parametrize("name,kind", [("wikimedia-commons", "manual"), ("archive-org", None)])
def test_recorded_generic_fixtures_build_bundles(tmp_path, monkeypatch, name, kind):
    info = json.loads((REC / f"{name}.info.json").read_text())
    monkeypatch.setattr(cf, "extract", lambda url, opts: info)
    monkeypatch.setattr(
        cf, "download_captions", lambda i, w, o, track: (f"captions/x.{track[0]}.vtt", *track)
    )
    monkeypatch.setattr(
        cf,
        "download",
        lambda i, w, o, failed=None: MediaInfo(path="media/video.mp4", width=1280, height=720),
    )
    bundle = build(tmp_path / "w", url=info["webpage_url"])
    assert bundle.source.platform == "generic" and bundle.source.kind == "video"
    assert bundle.source.author_name == info["uploader"] and bundle.source.title == info["title"]
    assert bundle.source.canonical_url == info["webpage_url"]
    assert bundle.context.captions_kind == kind
    assert bundle.context.post_text == info["description"]


def test_generic_registers_itself():
    assert adapter_for("generic") is ADAPTER
