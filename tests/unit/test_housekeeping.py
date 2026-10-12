"""Work-folder housekeeping the skill used to run as shell (skill audit 4 fixes 1 and 4)."""

from pathlib import Path

from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.errors import ExitCode
from skipwatch.workdir import WorkDir


def invoke(*args: str):
    return CliRunner().invoke(app, list(args))


def work_folder(root: Path) -> Path:
    work = root / "work" / "demo-20261012-120000"
    WorkDir(work).ensure()
    return work


def write(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---- snapshot-draft ----


def test_snapshot_copies_the_draft(tmp_path):
    work = work_folder(tmp_path)
    write(work / "draft" / "SKILL.md", "draft one")
    write(work / "draft" / "assets" / "a.txt", "asset")
    r = invoke("snapshot-draft", "--work", str(work))
    assert r.exit_code == 0, r.output
    assert (work / "draft-pre-critic" / "SKILL.md").read_text() == "draft one"
    assert (work / "draft-pre-critic" / "assets" / "a.txt").read_text() == "asset"
    assert (work / "draft" / "SKILL.md").is_file()  # the draft itself stays


def test_snapshot_replaces_an_older_snapshot(tmp_path):
    work = work_folder(tmp_path)
    write(work / "draft" / "SKILL.md", "new")
    write(work / "draft-pre-critic" / "SKILL.md", "old")
    write(work / "draft-pre-critic" / "stale.txt")
    r = invoke("snapshot-draft", "--work", str(work))
    assert r.exit_code == 0, r.output
    assert (work / "draft-pre-critic" / "SKILL.md").read_text() == "new"
    assert not (work / "draft-pre-critic" / "stale.txt").exists()


def test_snapshot_without_a_draft_is_exit_7(tmp_path):
    work = work_folder(tmp_path)
    write(work / "draft-pre-critic" / "SKILL.md", "old")
    r = invoke("snapshot-draft", "--work", str(work))
    assert r.exit_code == ExitCode.NO_CONTENT
    assert "draft" in r.stderr
    assert (work / "draft-pre-critic" / "SKILL.md").read_text() == "old"  # nothing removed


def test_snapshot_outside_a_work_folder_is_exit_2(tmp_path):
    write(tmp_path / "draft" / "SKILL.md")
    r = invoke("snapshot-draft", "--work", str(tmp_path))
    assert r.exit_code == ExitCode.UNSUPPORTED_SOURCE
    assert not (tmp_path / "draft-pre-critic").exists()
