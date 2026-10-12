"""Work-folder housekeeping the skill used to run as shell (skill audit 4 fixes 1 and 4)."""

from pathlib import Path

import pytest
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


def symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError as exc:  # Windows without the symlink privilege
        pytest.skip(f"cannot create symlinks here: {exc}")


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


# ---- cleanup ----

DRAFT_FILES = (
    "draft/SKILL.md",
    "draft-pre-critic/SKILL.md",
    "test-run/out.txt",
    "notes/batch-01.json",
    "frames/f000001.jpg",
    "outline.md",
    "critique.json",
    "transcript.json",
    "ingest.json",
    "logs/probe.json",
)
KEPT_FILES = (
    "stages.json",
    "run.json",
    "logs/probe.log",
    "check-report.json",
    "staging/x/SKILL.md",
)


def full_run(root: Path) -> Path:
    work = work_folder(root)
    for name in (*DRAFT_FILES, *KEPT_FILES[1:], "media/video.mp4"):
        write(work / name)
    return work


def scratch_dir(root: Path, name: str = "demo") -> Path:
    scratch = root / "project" / ".skipwatch" / f"test-run-{name}"
    write(scratch / "SKILL.md")
    return scratch


def test_cleanup_removes_media_drafts_and_raw_text_and_keeps_the_record(tmp_path, monkeypatch):
    monkeypatch.delenv("SKIPWATCH_KEEP_DRAFTS", raising=False)
    work = full_run(tmp_path)
    scratch = scratch_dir(tmp_path)
    r = invoke("cleanup", "--work", str(work), "--scratch", str(scratch))
    assert r.exit_code == 0, r.output
    for name in (*DRAFT_FILES, "media/video.mp4"):
        assert not (work / name).exists(), name
    for name in ("draft", "draft-pre-critic", "test-run", "notes", "frames", "media"):
        assert not (work / name).exists(), name
    for name in KEPT_FILES:
        assert (work / name).is_file(), name
    assert not scratch.exists() and scratch.parent.is_dir()


def test_cleanup_keep_media_keeps_media(tmp_path, monkeypatch):
    monkeypatch.delenv("SKIPWATCH_KEEP_DRAFTS", raising=False)
    work = full_run(tmp_path)
    r = invoke("cleanup", "--work", str(work), "--keep-media")
    assert r.exit_code == 0, r.output
    assert (work / "media" / "video.mp4").is_file()
    assert not (work / "draft").exists()


def test_cleanup_keep_drafts_env_keeps_drafts_and_scratch_but_not_media(tmp_path, monkeypatch):
    monkeypatch.setenv("SKIPWATCH_KEEP_DRAFTS", "1")
    work = full_run(tmp_path)
    scratch = scratch_dir(tmp_path)
    r = invoke("cleanup", "--work", str(work), "--scratch", str(scratch))
    assert r.exit_code == 0, r.output
    for name in DRAFT_FILES:
        assert (work / name).is_file(), name
    assert scratch.is_dir()
    assert not (work / "media").exists()


def test_cleanup_twice_is_harmless(tmp_path):
    work = full_run(tmp_path)
    assert invoke("cleanup", "--work", str(work)).exit_code == 0
    r = invoke("cleanup", "--work", str(work))
    assert r.exit_code == 0, r.output


def test_cleanup_scratch_under_the_work_folder_is_allowed(tmp_path):
    work = full_run(tmp_path)
    scratch = write(work / "scratch-here" / "a.txt").parent
    r = invoke("cleanup", "--work", str(work), "--scratch", str(scratch))
    assert r.exit_code == 0, r.output
    assert not scratch.exists()


def test_cleanup_refuses_a_scratch_outside_the_pattern_and_deletes_nothing(tmp_path):
    work = full_run(tmp_path)
    for bad in (
        tmp_path / "project",
        tmp_path / "project" / ".skipwatch",
        tmp_path / "project" / ".skipwatch" / "test-run-",
        tmp_path / "project" / ".skipwatch" / "work",
        tmp_path / "project" / "test-run-demo",
        work,
        tmp_path,
    ):
        bad.mkdir(parents=True, exist_ok=True)
        r = invoke("cleanup", "--work", str(work), "--scratch", str(bad))
        assert r.exit_code == ExitCode.USAGE, bad
        assert bad.is_dir(), bad
        assert (work / "draft" / "SKILL.md").is_file()
        assert (work / "media" / "video.mp4").is_file()


def test_cleanup_refuses_a_scratch_symlink_that_leads_elsewhere(tmp_path):
    work = full_run(tmp_path)
    outside = write(tmp_path / "precious" / "keep.txt").parent
    link = tmp_path / "project" / ".skipwatch" / "test-run-demo"
    link.parent.mkdir(parents=True)
    symlink(link, outside)
    r = invoke("cleanup", "--work", str(work), "--scratch", str(link))
    assert r.exit_code == ExitCode.USAGE
    assert (outside / "keep.txt").is_file()


def test_cleanup_never_follows_a_symlink_out_of_the_work_folder(tmp_path):
    work = work_folder(tmp_path)
    outside = tmp_path / "precious"
    write(outside / "notes" / "keep.txt")
    write(outside / "logs" / "probe.json")
    write(outside / "outline.md")
    symlink(work / "notes", outside / "notes")
    symlink(work / "logs", outside / "logs")
    symlink(work / "outline.md", outside / "outline.md")
    r = invoke("cleanup", "--work", str(work))
    assert r.exit_code == 0, r.output
    assert (outside / "notes" / "keep.txt").is_file()
    assert (outside / "logs" / "probe.json").is_file()
    assert (outside / "outline.md").is_file()
    assert not (work / "notes").exists() and not (work / "outline.md").exists()


def test_cleanup_outside_a_work_folder_is_exit_2(tmp_path):
    write(tmp_path / "draft" / "SKILL.md")
    r = invoke("cleanup", "--work", str(tmp_path))
    assert r.exit_code == ExitCode.UNSUPPORTED_SOURCE
    assert (tmp_path / "draft" / "SKILL.md").is_file()


def test_resume_still_reads_a_cleaned_finished_run(tmp_path):
    import json

    from skipwatch.models import RunFile
    from skipwatch.workdir import STAGE_ORDER, write_model

    work = full_run(tmp_path)
    write_model(
        work / "run.json", RunFile(input="https://youtu.be/x", started_at="2026-10-12T00:00:00Z")
    )
    for stage in STAGE_ORDER[:-1]:
        WorkDir(work).mark(stage, "done")
    assert invoke("cleanup", "--work", str(work)).exit_code == 0
    r = invoke("resume", str(work), "--json")
    assert r.exit_code == 0, r.output
    result = json.loads(r.stdout)
    assert result["next_stage"] is None and result["run"]["input"] == "https://youtu.be/x"
    assert invoke("list").exit_code == 0
