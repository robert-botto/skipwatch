"""`nudge`: the star line, once per SkipWatch home (skill audit 4 fix 1)."""

from typer.testing import CliRunner

from skipwatch.cli import app

STAR = (
    "If this saved you an hour, a star helps others find it: "
    "https://github.com/robert-botto/skipwatch\n"
)


def nudge(*home_args: str):
    return CliRunner().invoke(app, [*home_args, "nudge"])


def test_nudge_prints_once_per_home(sw_home):
    first = nudge()
    assert first.exit_code == 0 and first.stdout == STAR
    assert (sw_home / ".star-nudged").is_file()
    second = nudge()
    assert second.exit_code == 0 and second.stdout == ""


def test_nudge_follows_the_home_option(tmp_path, sw_home):
    project_home = tmp_path / "project" / ".skipwatch"
    assert nudge().stdout == STAR
    assert nudge("--home", str(project_home)).stdout == STAR
    assert (project_home / ".star-nudged").is_file()
    assert nudge("--home", str(project_home)).stdout == ""


def test_nudge_exits_0_when_the_marker_cannot_be_written(tmp_path, monkeypatch):
    blocked = tmp_path / "home-is-a-file"
    blocked.write_text("x", encoding="utf-8")
    monkeypatch.setenv("SKIPWATCH_HOME", str(blocked))
    r = nudge()
    assert r.exit_code == 0
