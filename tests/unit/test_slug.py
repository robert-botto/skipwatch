"""new-work --from: the engine derives the slug (run-engine.md stage 2, skill audit 3 fix 7)."""

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.errors import ExitCode
from skipwatch.slug import slug_for


@pytest.mark.parametrize(
    ("value", "slug"),
    [
        # the spec's own example
        ("https://www.youtube.com/watch?v=AbC_12", "youtube-com-abc-12"),
        # host without www. plus the last path segment
        ("https://youtu.be/XyZ-9", "youtu-be-xyz-9"),
        ("https://x.com/someone/status/1505892984658743300", "x-com-1505892984658743300"),
        ("https://example.com/a/b/", "example-com-b"),
        ("https://example.com", "example-com"),
        ("https://wwwfoo.com/clip", "wwwfoo-com-clip"),
        ("http://WWW.Vimeo.com/12345", "vimeo-com-12345"),
        # a URL without a scheme is still a URL
        ("youtube.com/watch?v=1", "youtube-com-1"),
        # cut to 40 for a URL, and the hyphen the cut leaves at the end goes
        ("https://example.com/" + "a" * 27 + "-bcd", "example-com-" + "a" * 27),
        ("https://example.com/" + "z" * 60, "example-com-" + "z" * 28),
    ],
)
def test_url_slugs(value, slug):
    assert slug_for(value) == slug


@pytest.mark.parametrize(
    ("value", "slug"),
    [
        ("/videos/tutorial-60s.mp4", "tutorial-60s"),
        ("/videos/My Tutorial (Final).MOV", "my-tutorial-final"),
        ("clips/--Odd__name--.webm", "odd-name"),
        ("/videos/café résumé.mp4", "caf-r-sum"),
        ("/videos/" + "b" * 79 + "-c.mp4", "b" * 79),
        ("/videos/" + "d" * 100 + ".mp4", "d" * 80),
        # nothing left: video
        ("/videos/!!!.mp4", "video"),
        ("/videos/日本.mp4", "video"),
    ],
)
def test_file_stem_slugs(value, slug):
    assert slug_for(value) == slug


def test_an_existing_file_named_like_a_host_is_a_file(tmp_path):
    clip = tmp_path / "example.com"
    clip.write_bytes(b"")
    assert slug_for("example.com", cwd=tmp_path) == "example"


def test_every_slug_passes_the_new_work_rule():
    from skipwatch.commands.new_work import SLUG_RE

    for value in ("https://example.com/" + "-" * 50, "/x/" + "-" * 90 + ".mp4", "https://a.io/?"):
        assert SLUG_RE.fullmatch(slug_for(value))


def new_work(*args):
    return CliRunner().invoke(app, ["new-work", *args])


def test_new_work_from_derives_the_slug(sw_home):
    r = new_work("--from", "https://www.youtube.com/watch?v=AbC_12", "--json")
    assert r.exit_code == 0, r.output
    work = Path(json.loads(r.stdout)["work"])
    assert re.fullmatch(r"youtube-com-abc-12-\d{8}-\d{6}", work.name)
    assert work.parent == sw_home.absolute() / "work"


def test_new_work_from_and_slug_are_mutually_exclusive(sw_home):
    r = new_work("--from", "https://youtu.be/x", "--slug", "demo")
    assert r.exit_code == ExitCode.USAGE
    assert "--from" in r.output and "--slug" in r.output
    assert not (sw_home / "work").exists()


def test_new_work_needs_from_or_slug(sw_home):
    r = new_work("--json")
    assert r.exit_code == ExitCode.USAGE
    assert not (sw_home / "work").exists()


def test_a_missing_bare_file_name_is_a_file_slug(tmp_path):
    # Ruling FU-R1: notes.md is a missing file, not https://notes.md.
    assert slug_for("notes.md", cwd=tmp_path) == "notes"
