"""target-free: say whether an install target is free in one stdout line, so the skill never
reads `test -e` exit codes (live finding). Read-only; HOME is a fake under tmp_path."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.errors import ExitCode
from skipwatch.install import scope_target


@pytest.fixture
def home(tmp_path, monkeypatch, sw_home) -> Path:
    """sw_home, as install's tests use: the default test home maps work/ onto tmp_path."""
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
        ("--target", "relative/fix-bugs"),
        ("--target", "~/x", "--name", "fix-bugs"),
    ],
)
def test_a_bad_combination_is_64(home, args):
    r = free(*args)
    assert r.exit_code == ExitCode.USAGE and r.stdout == ""


@pytest.fixture
def cwd(tmp_path, monkeypatch, sw_home) -> Path:
    cwd = tmp_path / "project dir"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    return cwd


def test_name_alone_uses_the_config_default_scope_like_install(home, cwd, sw_home):
    sw_home.mkdir(parents=True, exist_ok=True)
    (sw_home / "config.toml").write_text('[install]\nscope = "agents"\n', encoding="utf-8")
    r = free("--name", "fix-bugs")
    expected, _ = scope_target(None, "fix-bugs", cwd, home)
    assert expected == cwd / ".agents" / "skills" / "fix-bugs"
    assert r.exit_code == 0 and r.stdout == f"target free: {expected}\n"


def test_name_alone_without_config_is_the_user_scope(home, cwd):
    r = free("--name", "fix-bugs")
    assert r.stdout == f"target free: {home / '.claude' / 'skills' / 'fix-bugs'}\n"


@pytest.mark.parametrize("scope", ["user", "project", "agents"])
def test_each_scope_prints_the_path_install_would_use(home, cwd, scope):
    expected, _ = scope_target(scope, "fix-bugs", cwd, home)
    expected.mkdir(parents=True)
    r = free("--name", "fix-bugs", "--scope", scope)
    assert r.exit_code == 0 and r.stdout == f"target exists: {expected}\n"


@pytest.mark.parametrize(
    "args",
    [
        ("--scope", "user", "--to", "~/.claude/skills", "--name", "fix-bugs"),
        ("--scope", "user", "--target", "/abs/fix-bugs"),
        ("--scope", "user"),
        ("--scope", "project", "--name", "Bad"),
    ],
)
def test_a_bad_scope_combination_is_64(home, cwd, args):
    r = free(*args)
    assert r.exit_code == ExitCode.USAGE and r.stdout == ""


def test_an_unknown_scope_is_a_parse_error(home, cwd):
    r = free("--scope", "nosuch", "--name", "fix-bugs")
    assert r.exit_code == 2 and r.stdout == ""  # 64 through cli.main


def test_a_symlinked_to_is_64_like_install(home, cwd):
    link = home / "linked"
    try:
        link.symlink_to(home / ".claude" / "skills")
    except OSError as exc:
        pytest.skip(f"cannot create symlinks here: {exc}")
    r = free("--to", str(link), "--name", "fix-bugs")
    assert r.exit_code == ExitCode.USAGE and r.stdout == ""


@pytest.mark.parametrize("area", ["work", "packs"])
def test_a_to_inside_the_home_work_or_packs_is_64_like_install(home, cwd, sw_home, area):
    inside = sw_home / area / "run"
    inside.mkdir(parents=True)
    r = free("--to", str(inside), "--name", "fix-bugs")
    assert r.exit_code == ExitCode.USAGE and r.stdout == ""
