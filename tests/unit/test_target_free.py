"""target-free: say whether an install target is free in one stdout line, so the skill never
reads `test -e` exit codes (live finding). Read-only; HOME is a fake under tmp_path."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.errors import ExitCode


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "fakehome"
    (home / ".claude" / "skills").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    return home


def free(*args: str):
    return CliRunner().invoke(app, ["target-free", *args])


def test_a_missing_target_is_free_and_nothing_is_created(home):
    skills = home / ".claude" / "skills"
    r = free("--to", str(skills), "--name", "fix-bugs")
    assert r.exit_code == 0, r.output
    assert r.stdout == f"target free: {skills / 'fix-bugs'}\n"
    assert not (skills / "fix-bugs").exists()


@pytest.mark.parametrize(
    "to", ["~/.claude/skills", "$HOME/.claude/skills", "${HOME}/.claude/skills"]
)
def test_tilde_and_home_are_resolved(home, to):
    r = free("--to", to, "--name", "fix-bugs")
    assert r.stdout == f"target free: {home / '.claude' / 'skills' / 'fix-bugs'}\n"


def test_an_existing_folder_exists(home):
    target = home / ".claude" / "skills" / "fix-bugs"
    target.mkdir()
    r = free("--to", "~/.claude/skills", "--name", "fix-bugs")
    assert r.exit_code == 0 and r.stdout == f"target exists: {target}\n"


def test_an_existing_file_exists(home):
    target = home / ".claude" / "skills" / "fix-bugs"
    target.write_text("x", encoding="utf-8")
    r = free("--target", str(target))
    assert r.exit_code == 0 and r.stdout == f"target exists: {target}\n"
    assert target.read_text(encoding="utf-8") == "x"


def test_a_dangling_symlink_exists(home):
    target = home / ".claude" / "skills" / "fix-bugs"
    try:
        target.symlink_to(home / "nosuch")
    except OSError as exc:
        pytest.skip(f"cannot create symlinks here: {exc}")
    r = free("--to", "~/.claude/skills", "--name", "fix-bugs")
    assert r.exit_code == 0 and r.stdout == f"target exists: {target}\n"
    assert free("--target", str(target)).exit_code == ExitCode.USAGE
    assert target.is_symlink() and not (home / "nosuch").exists()


@pytest.mark.parametrize("name", ["Bad", "a--b", "../x", "a/b", "", "x" * 65])
def test_an_invalid_name_is_64(home, name):
    r = free("--to", "~/.claude/skills", "--name", name)
    assert r.exit_code == ExitCode.USAGE and r.stdout == ""


@pytest.mark.parametrize(
    "args",
    [
        (),
        ("--to", "~/.claude/skills"),
        ("--name", "fix-bugs"),
        ("--target", "relative/fix-bugs"),
        ("--target", "~/x", "--name", "fix-bugs"),
    ],
)
def test_a_bad_combination_is_64(home, args):
    r = free(*args)
    assert r.exit_code == ExitCode.USAGE and r.stdout == ""
