import json
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch import share
from skipwatch.cli import app
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import Counts, Manifest, ManifestSource, ShareResult
from skipwatch.project import REPO_URL
from skipwatch.workdir import write_model

EM_DASH = "\u2014"
URL = "https://www.youtube.com/watch?v=abc123"


def manifest(
    title: str | None = "Ship an Astro site in 5 minutes",
    author: str | None = "@creator",
    platform: str = "youtube",
    url: str | None = "https://youtu.be/abc123",
    canonical_url: str | None = URL,
    steps: int = 6,
) -> Manifest:
    return Manifest(
        name="deploy-astro",
        description="Deploys an Astro site.",
        skipwatch_version="0.1.0",
        source=ManifestSource(
            platform=platform, url=url, canonical_url=canonical_url, author=author, title=title
        ),
        extracted_at="2026-10-09T12:00:00Z",
        counts=Counts(steps=steps, spoken=steps),
        confidence="medium",
        checks_passed=True,
    )


def test_share_exact_template():
    result = share.share_text(manifest())
    assert result.text == (
        'Thanks @creator for "Ship an Astro site in 5 minutes". I turned it into a Claude Code'
        " skill with SkipWatch: 6 steps, each traced to a moment in your video.\n"
        "\n"
        f"Try it: /skipwatch {URL}\n"
        f"{REPO_URL}"
    )
    assert result.install_line == f"/skipwatch {URL}"
    assert result.name == "deploy-astro"
    assert result.weighted_length == share.weighted_length(result.text)


def test_share_falls_back_to_url_without_canonical():
    result = share.share_text(manifest(canonical_url=None))
    assert result.install_line == "/skipwatch https://youtu.be/abc123"


def test_share_counts_urls_as_23():
    assert share.weighted_length("abc") == 3
    assert share.weighted_length("see https://example.com/" + "x" * 200) == 4 + 23
    assert share.weighted_length("http://a.b and https://c.d/e?f=g") == 23 + 5 + 23
    result = share.share_text(manifest())
    body = result.text.replace(URL, "").replace(REPO_URL, "")
    assert result.weighted_length == len(body) + 2 * 23


def test_share_weights_wide_characters_as_two():
    # X counts characters outside its Latin ranges (emoji, CJK) as 2; counting them as 1
    # would let an emoji-heavy title pass here and still overflow on X.
    assert share.weighted_length("\U0001f680") == 2
    assert share.weighted_length("日本") == 4
    assert share.weighted_length("café “q”") == 8


def test_share_long_title_fits_280():
    result = share.share_text(manifest(title="A" * 300))
    assert result.weighted_length <= share.LIMIT
    assert share.weighted_length(result.text) == result.weighted_length
    first = result.text.splitlines()[0]
    assert first.startswith('Thanks @creator for "AAA')
    assert '..."' in first
    # the shortened title uses the room there is: one more character would not fit
    assert result.weighted_length > share.LIMIT - 2


def test_share_long_emoji_title_fits_280():
    result = share.share_text(manifest(title="\U0001f680 launch " * 60))
    assert result.weighted_length <= share.LIMIT
    assert '..."' in result.text


def test_share_unicode_and_quotes_title():
    title = 'The "best" way \U0001f680 to ship ✨ café'
    result = share.share_text(manifest(title=title))
    assert f'"{title}"' in result.text
    assert EM_DASH not in result.text


def test_share_title_whitespace_is_collapsed():
    result = share.share_text(manifest(title="Line one\nline two\t end"))
    assert '"Line one line two end"' in result.text
    assert len(result.text.splitlines()) == 4


def test_share_missing_author():
    result = share.share_text(manifest(author=None))
    assert result.text.startswith(
        'Thanks to the creator of "Ship an Astro site in 5 minutes". I turned it into'
    )


def test_share_missing_title_and_author():
    result = share.share_text(manifest(author=None, title=None))
    assert result.text.startswith("Thanks to the creator of this video. I turned it into")
    result = share.share_text(manifest(title=None))
    assert result.text.startswith("Thanks @creator for this video. I turned it into")


def test_share_one_step_is_singular():
    assert "1 step, each traced" in share.share_text(manifest(steps=1)).text


def test_share_long_author_still_fits():
    result = share.share_text(manifest(author="@" + "b" * 400, title="T" * 300))
    assert result.weighted_length <= share.LIMIT


@pytest.mark.parametrize(
    "kwargs",
    [
        {"platform": "local", "url": None, "canonical_url": None},
        {"platform": "local", "url": "file:///tmp/x.mp4", "canonical_url": None},
        {"platform": "youtube", "url": None, "canonical_url": None},
    ],
)
def test_share_local_file_raises_unsupported(kwargs):
    with pytest.raises(SkipwatchError) as exc:
        share.share_text(manifest(**kwargs))
    assert exc.value.code == ExitCode.UNSUPPORTED_SOURCE
    assert "local file" in exc.value.message


# ---- command ----


@pytest.fixture
def skill(tmp_path, monkeypatch, sw_home) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.chdir(tmp_path)
    folder = home / ".claude" / "skills" / "deploy-astro"
    folder.mkdir(parents=True)
    write_model(folder / "skipwatch.json", manifest())
    return folder


def run_share(*args: str):
    return CliRunner().invoke(app, ["share", *args])


def test_share_cli_by_name_prints_post_on_stderr(skill):
    r = run_share("deploy-astro")
    assert r.exit_code == 0, r.stderr
    assert r.stdout == ""
    assert r.stderr == share.share_text(manifest()).text + "\n"


def test_share_json_validates(skill):
    r = run_share(str(skill), "--json")
    assert r.exit_code == 0, r.stderr
    result = ShareResult.model_validate_json(r.stdout)
    assert result == share.share_text(manifest())
    assert json.loads(r.stdout)["schema"] == "skipwatch/share/1"


def test_share_local_file_is_exit_2(skill):
    write_model(
        skill / "skipwatch.json",
        manifest(platform="local", url=None, canonical_url=None),
    )
    r = run_share("deploy-astro")
    assert r.exit_code == ExitCode.UNSUPPORTED_SOURCE
    assert "local file" in r.stderr
    assert r.stdout == ""


def test_share_unknown_skill_is_exit_2(skill):
    r = run_share("nope")
    assert r.exit_code == ExitCode.UNSUPPORTED_SOURCE
    assert "no installed SkipWatch skill named nope" in r.stderr


def test_share_unreadable_manifest_is_exit_2(skill):
    (skill / "skipwatch.json").write_text("{}", encoding="utf-8")
    r = run_share(str(skill))
    assert r.exit_code == ExitCode.UNSUPPORTED_SOURCE
    assert "skipwatch.json" in r.stderr


def test_share_cookie_skill_is_exit_4():
    cookie = manifest().model_copy(update={"fetched_with_cookies": True})
    with pytest.raises(SkipwatchError) as exc:
        share.share_text(cookie)
    assert exc.value.code == ExitCode.PRIVATE_CONTENT
    assert "browser cookies, so it cannot be shared" in exc.value.message
    # cookies win over the local-file refusal: the more specific reason comes first
    local = manifest(platform="local", url=None, canonical_url=None)
    with pytest.raises(SkipwatchError) as exc:
        share.share_text(local.model_copy(update={"fetched_with_cookies": True}))
    assert exc.value.code == ExitCode.PRIVATE_CONTENT


def test_share_url_trailing_punctuation_counts_as_text():
    # X stops a link before closing punctuation, so those characters count on their own
    assert share.weighted_length("see https://a.co/x.") == 4 + 23 + 1
    assert share.weighted_length('("https://a.co/x"),') == 2 + 23 + 3
    assert share.weighted_length("https://a.co/x?!") == 23 + 2


def test_share_counts_bare_domains_as_at_least_23():
    # X links bare domains (x.ai, github.com/foo) and counts each as 23
    assert share.weighted_length("x.ai") == 23
    assert share.weighted_length('"x.ai".') == 1 + 23 + 2
    assert share.weighted_length("try github.com/foo now") == 4 + 23 + 4
    assert share.weighted_length("日本.jp") == 23
    # a dotted word X might not link still never counts below its own length
    long_word = "notes." + "b" * 40
    assert share.weighted_length(long_word) == len(long_word)
    # dotted numbers and abbreviations are plain text
    assert share.weighted_length("v1.2 e.g. U.S.") == 14


def test_share_title_of_bare_domains_fits_280():
    result = share.share_text(manifest(title="x.ai " * 80))
    assert result.weighted_length <= share.LIMIT
    assert '..."' in result.text


def test_share_huge_title_is_fast():
    start = time.perf_counter()
    result = share.share_text(manifest(title="word " * 20_000))
    assert time.perf_counter() - start < 2
    assert result.weighted_length <= share.LIMIT
