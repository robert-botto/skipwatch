"""rename-staging: move the one staging folder to a new skill name and record it in run.json
(skill audit 7 fix 2). Victims live in a fake $HOME under tmp_path."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.errors import ExitCode
from skipwatch.workdir import WorkDir

RUN = {"schema": "skipwatch/run/1", "input": "https://x.test/v", "flags": ["--no-frames"]}


@pytest.fixture
def fake_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "fakehome"
    (home / "docs").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def work(sw_home) -> Path:
    path = sw_home / "work" / "demo-20261012-120000"
    WorkDir(path).ensure()
    frames = path / "staging" / "fix-bugs" / "assets" / "frames"
    frames.mkdir(parents=True)
    (frames / "f1.jpg").write_bytes(b"jpg")
    (path / "staging" / "fix-bugs" / "SKILL.md").write_text("name: fix-bugs\n", encoding="utf-8")
    (path / "draft").mkdir()
    (path / "draft" / "SKILL.md").write_text("name: fix-bugs\n", encoding="utf-8")
    (path / "run.json").write_text(json.dumps(RUN), encoding="utf-8")
    return path


def link(at: Path, target: Path) -> None:
    try:
        at.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"cannot create symlinks here: {exc}")


def rename(work: Path, to: str):
    return CliRunner().invoke(app, ["rename-staging", "--work", str(work), "--to", to])


def run_json(work: Path) -> dict:
    return json.loads((work / "run.json").read_text(encoding="utf-8"))


def test_rename_moves_the_folder_with_its_frames_and_records_the_name(work):
    r = rename(work, "debug-flaky-tests")
    assert r.exit_code == 0, r.output
    new = work / "staging" / "debug-flaky-tests"
    assert not (work / "staging" / "fix-bugs").exists()
    assert (new / "assets" / "frames" / "f1.jpg").read_bytes() == b"jpg"
    assert (new / "SKILL.md").is_file()
    assert run_json(work) == {**RUN, "name": "debug-flaky-tests"}
    assert (work / "draft" / "SKILL.md").is_file()  # the draft is name-agnostic


def test_rename_replaces_an_existing_run_json_name(work):
    (work / "run.json").write_text(json.dumps({**RUN, "name": "fix-bugs"}), encoding="utf-8")
    assert rename(work, "new-name").exit_code == 0
    assert run_json(work) == {**RUN, "name": "new-name"}


@pytest.mark.parametrize("to", ["Bad-Name", "a--b", "../x", "a/b", "-a", "x" * 65, ""])
def test_rename_refuses_a_bad_skill_name(work, to):
    assert rename(work, to).exit_code == ExitCode.USAGE
    assert (work / "staging" / "fix-bugs" / "SKILL.md").is_file()
    assert run_json(work) == RUN


def test_rename_refuses_an_existing_target_with_6(work):
    (work / "staging" / "taken").mkdir()
    (work / "run.json").write_text(json.dumps({**RUN, "name": "fix-bugs"}), encoding="utf-8")
    assert rename(work, "taken").exit_code == ExitCode.TARGET_EXISTS
    assert (work / "staging" / "fix-bugs" / "SKILL.md").is_file()


def test_rename_refuses_a_target_that_is_a_dangling_symlink_with_6(work, fake_home):
    (work / "run.json").write_text(json.dumps({**RUN, "name": "fix-bugs"}), encoding="utf-8")
    link(work / "staging" / "taken", fake_home / "nosuch")
    assert rename(work, "taken").exit_code == ExitCode.TARGET_EXISTS
    assert (work / "staging" / "fix-bugs" / "SKILL.md").is_file()
    assert not (fake_home / "nosuch").exists()


def test_rename_refuses_several_staging_folders_without_a_name(work):
    (work / "staging" / "other").mkdir()
    assert rename(work, "new-name").exit_code == ExitCode.USAGE
    assert (work / "staging" / "fix-bugs").is_dir() and run_json(work) == RUN


def test_rename_refuses_no_staging_folder(work):
    (work / "staging" / "fix-bugs" / "SKILL.md").unlink()
    (work / "staging" / "fix-bugs" / "assets" / "frames" / "f1.jpg").unlink()
    for sub in ("assets/frames", "assets", ""):
        (work / "staging" / "fix-bugs" / sub).rmdir()
    assert rename(work, "new-name").exit_code == ExitCode.USAGE
    assert run_json(work) == RUN


def test_rename_refuses_a_symlinked_staging_folder(work, fake_home):
    old = work / "staging" / "fix-bugs"
    old.rename(fake_home / "docs" / "fix-bugs")
    link(old, fake_home / "docs" / "fix-bugs")
    assert rename(work, "new-name").exit_code == ExitCode.USAGE
    assert (fake_home / "docs" / "fix-bugs" / "SKILL.md").is_file()
    assert not (work / "staging" / "new-name").exists()


def test_rename_refuses_a_symlinked_staging_root(work, fake_home):
    (work / "staging").rename(fake_home / "docs" / "staging")
    link(work / "staging", fake_home / "docs" / "staging")
    assert rename(work, "new-name").exit_code == ExitCode.USAGE
    assert (fake_home / "docs" / "staging" / "fix-bugs" / "SKILL.md").is_file()


def test_rename_refuses_a_symlinked_run_json(work, fake_home):
    victim = fake_home / "docs" / "run.json"
    victim.write_text(json.dumps(RUN), encoding="utf-8")
    (work / "run.json").unlink()
    (work / "run.json").symlink_to(victim)
    assert rename(work, "new-name").exit_code == ExitCode.USAGE
    assert json.loads(victim.read_text(encoding="utf-8")) == RUN
    assert (work / "staging" / "fix-bugs").is_dir()


@pytest.mark.parametrize("content", [None, "not json", "[1, 2]"])
def test_rename_refuses_a_missing_or_unreadable_run_json(work, content):
    if content is None:
        (work / "run.json").unlink()
    else:
        (work / "run.json").write_text(content, encoding="utf-8")
    assert rename(work, "new-name").exit_code == ExitCode.USAGE
    assert (work / "staging" / "fix-bugs").is_dir()


def test_rename_refuses_a_work_folder_outside_the_home(tmp_path, sw_home):
    outside = tmp_path / "elsewhere" / "demo-20261012-120000"
    WorkDir(outside).ensure()
    (outside / "staging" / "fix-bugs").mkdir(parents=True)
    (outside / "run.json").write_text(json.dumps(RUN), encoding="utf-8")
    assert rename(outside, "new-name").exit_code == ExitCode.USAGE
    assert (outside / "staging" / "fix-bugs").is_dir()
