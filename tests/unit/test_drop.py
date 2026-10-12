"""drop: remove one file from a run's draft and staging (skill audit 7 fix 1). Every path is
checked before anything is deleted; victims live in a fake $HOME under tmp_path."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.errors import ExitCode
from skipwatch.workdir import WorkDir

SECRET = "keep me\n"


@pytest.fixture
def fake_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "fakehome"
    (home / "docs").mkdir(parents=True)
    (home / "docs" / "a.zip").write_text(SECRET, encoding="utf-8")
    (home / ".zshrc").write_text(SECRET, encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def work(sw_home) -> Path:
    path = sw_home / "work" / "demo-20261012-120000"
    WorkDir(path).ensure()
    for sub in ("logs", "draft", "staging/fix-bugs"):
        (path / sub).mkdir(parents=True)
    return path


def put(path: Path, text: str = "x\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def link(at: Path, target: Path) -> None:
    try:
        at.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"cannot create symlinks here: {exc}")


def drop(work: Path, rel: str):
    return CliRunner().invoke(app, ["drop", "--work", str(work), "--path", rel])


def test_drop_deletes_the_draft_and_staging_copies(work):
    draft = put(work / "draft" / "assets" / "a.zip")
    staged = put(work / "staging" / "fix-bugs" / "assets" / "a.zip")
    keep = put(work / "draft" / "assets" / "b.md")
    r = drop(work, "assets/a.zip")
    assert r.exit_code == 0, r.output
    assert not draft.exists() and not staged.exists() and keep.exists()


def test_drop_is_0_when_neither_copy_exists(work):
    r = drop(work, "assets/none.zip")
    assert r.exit_code == 0, r.output


def test_drop_with_no_staging_folder_deletes_the_draft_copy(work):
    (work / "staging" / "fix-bugs").rmdir()
    draft = put(work / "draft" / "a.zip")
    assert drop(work, "a.zip").exit_code == 0
    assert not draft.exists()


def test_drop_uses_the_run_json_name_among_several_staging_folders(work):
    (work / "run.json").write_text(json.dumps({"name": "fix-bugs"}), encoding="utf-8")
    other = put(work / "staging" / "old-name" / "a.zip")
    staged = put(work / "staging" / "fix-bugs" / "a.zip")
    assert drop(work, "a.zip").exit_code == 0
    assert not staged.exists() and other.exists()


def test_drop_refuses_several_staging_folders_without_a_name(work):
    draft = put(work / "draft" / "a.zip")
    put(work / "staging" / "old-name" / "a.zip")
    assert drop(work, "a.zip").exit_code == ExitCode.USAGE
    assert draft.exists()


@pytest.mark.parametrize("name", ["../..", "a/b", "Bad", ""])
def test_drop_refuses_a_bad_run_json_name(work, name):
    (work / "run.json").write_text(json.dumps({"name": name}), encoding="utf-8")
    draft = put(work / "draft" / "a.zip")
    assert drop(work, "a.zip").exit_code == ExitCode.USAGE
    assert draft.exists()


@pytest.mark.parametrize(
    "rel",
    [
        "SKILL.md",
        "skipwatch.json",
        "../stages.json",
        "assets/../../stages.json",
        "/etc/hosts",
        "",
        ".",
        "assets\\..\\a.zip",
    ],
)
def test_drop_refuses_a_path_that_is_not_a_plain_relative_file(work, rel):
    skill = put(work / "draft" / "SKILL.md")
    staged = put(work / "staging" / "fix-bugs" / "SKILL.md")
    assert drop(work, rel).exit_code == ExitCode.USAGE
    assert skill.exists() and staged.exists() and (work / "stages.json").exists()


def test_drop_refuses_a_folder_and_deletes_nothing(work):
    draft = put(work / "draft" / "assets" / "a.zip")
    put(work / "staging" / "fix-bugs" / "assets" / "a.zip" / "inner.txt")
    assert drop(work, "assets/a.zip").exit_code == ExitCode.USAGE
    assert draft.exists()


def test_drop_refuses_a_symlinked_file_and_keeps_its_target(work, fake_home):
    draft = put(work / "draft" / "a.zip")
    link(work / "staging" / "fix-bugs" / "a.zip", fake_home / "docs" / "a.zip")
    assert drop(work, "a.zip").exit_code == ExitCode.USAGE
    assert draft.exists() and (work / "staging" / "fix-bugs" / "a.zip").is_symlink()
    assert (fake_home / "docs" / "a.zip").read_text(encoding="utf-8") == SECRET


def test_drop_refuses_a_symlinked_folder_on_the_way(work, fake_home):
    link(work / "draft" / "assets", fake_home / "docs")
    assert drop(work, "assets/a.zip").exit_code == ExitCode.USAGE
    assert (fake_home / "docs" / "a.zip").read_text(encoding="utf-8") == SECRET


def test_drop_refuses_a_symlinked_staging_folder(work, fake_home):
    (work / "staging" / "fix-bugs").rmdir()
    link(work / "staging" / "fix-bugs", fake_home / "docs")
    assert drop(work, "a.zip").exit_code == ExitCode.USAGE
    assert (fake_home / "docs" / "a.zip").read_text(encoding="utf-8") == SECRET


def test_drop_refuses_a_symlinked_draft_folder(work, fake_home):
    (work / "draft").rmdir()
    link(work / "draft", fake_home / "docs")
    assert drop(work, "a.zip").exit_code == ExitCode.USAGE
    assert (fake_home / "docs" / "a.zip").read_text(encoding="utf-8") == SECRET


def test_drop_refuses_a_work_folder_outside_the_home(tmp_path, sw_home):
    outside = tmp_path / "elsewhere" / "demo-20261012-120000"
    WorkDir(outside).ensure()
    draft = put(outside / "draft" / "a.zip")
    assert drop(outside, "a.zip").exit_code == ExitCode.USAGE
    assert draft.exists()
