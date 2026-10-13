"""First run: doctor reports it once per home, and the skill prints the wordmark for it."""

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch import firstrun
from skipwatch.cli import app

SKILL_MD = Path(__file__).resolve().parents[2] / "skills/skipwatch/SKILL.md"
WORDMARK = [
    " ┌─┐┬┌─┬┌─┐  ┬ ┬┌─┐┌┬┐┌─┐┬ ┬",
    " └─┐├┴┐│├─┘  │││├─┤ │ │  ├─┤",
    " └─┘┴ ┴┴┴    └┴┘┴ ┴ ┴ └─┘┴ ┴   paste a video, get a skill",
]


def test_claim_is_true_once_per_home(tmp_path):
    home = tmp_path / ".skipwatch"
    assert firstrun.claim(home) is True
    assert firstrun.claim(home) is False
    assert (home / firstrun.MARKER).is_file()


def test_doctor_reports_first_run_once(sw_home):
    first = CliRunner().invoke(app, ["doctor", "--json"])
    assert first.exit_code == 0, first.output
    assert first.stderr.startswith("Tier ")
    assert first.stderr.splitlines()[-1] == firstrun.WELCOME
    second = CliRunner().invoke(app, ["doctor", "--json"])
    assert second.exit_code == 0, second.output
    assert firstrun.WELCOME not in second.stderr


def test_marker_symlink_is_not_followed(tmp_path):
    home = tmp_path / ".skipwatch"
    home.mkdir()
    target = tmp_path / "outside.txt"
    try:
        (home / firstrun.MARKER).symlink_to(target)
    except OSError:
        pytest.skip("symlinks need privilege here")
    assert firstrun.claim(home) is False  # a dangling link counts as present
    assert not target.exists()  # and is never followed to create its target
    target.write_text("keep", encoding="utf-8")
    assert firstrun.claim(home) is False
    assert target.read_text(encoding="utf-8") == "keep"


def test_unwritable_home_never_fails_or_repeats(tmp_path):
    home = tmp_path / ".skipwatch"
    home.write_text("a file, not a folder", encoding="utf-8")
    assert firstrun.claim(home) is False


def test_skill_prints_the_agreed_wordmark_verbatim():
    text = SKILL_MD.read_text(encoding="utf-8")
    blocks = re.findall(r"^```\n(.*?)^```$", text, re.M | re.S)
    marks = [b.splitlines() for b in blocks if "┌─┐" in b]
    assert marks == [WORDMARK]  # exactly one copy, exactly these lines
    assert all(len(line) <= 60 for line in WORDMARK)
    section = text.split("\n## First run\n", 1)[1].split("\n## ", 1)[0]
    assert f"`{firstrun.WELCOME}`" in section and "verbatim" in section


def test_no_em_dash_in_first_run_sources():
    for path in (Path(firstrun.__file__), Path(__file__)):
        assert "\u2014" not in path.read_text(encoding="utf-8"), path
    assert "\u2014" not in firstrun.WELCOME
