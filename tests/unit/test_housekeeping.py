"""Work-folder housekeeping the skill used to run as shell (skill audit 4 fixes 1 and 4)."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.config import skipwatch_home
from skipwatch.errors import ExitCode
from skipwatch.workdir import STAGE_ORDER, WorkDir


@pytest.fixture(autouse=True)
def _in_project(tmp_path, monkeypatch):
    """The skill runs from the project <P>; its tester scratch is <P>/.skipwatch/test-run-*."""
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)


def invoke(*args: str):
    return CliRunner().invoke(app, list(args))


def work_folder(root: Path) -> Path:
    """A work folder under the engine's home, where the commands accept one."""
    del root  # the home is per test (conftest), so the folder never leaks between tests
    work = skipwatch_home() / "work" / "demo-20261012-120000"
    WorkDir(work).ensure()
    return work


def outside_folder(root: Path) -> Path:
    """A folder with a valid stages.json that is not under the home's work/."""
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


def test_snapshot_outside_a_work_folder_is_exit_64(tmp_path):
    write(tmp_path / "draft" / "SKILL.md")
    r = invoke("snapshot-draft", "--work", str(tmp_path))
    assert r.exit_code == ExitCode.USAGE
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


def test_cleanup_refuses_a_scratch_inside_the_work_folder(tmp_path):
    work = full_run(tmp_path)
    for inside in (work / "stages.json", work / "run.json", work / "logs", work / "staging"):
        r = invoke("cleanup", "--work", str(work), "--scratch", str(inside))
        assert r.exit_code == ExitCode.USAGE, inside
        assert inside.exists(), inside
    assert (work / "draft" / "SKILL.md").is_file()


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


def test_cleanup_outside_a_work_folder_is_exit_64(tmp_path):
    write(tmp_path / "draft" / "SKILL.md")
    r = invoke("cleanup", "--work", str(tmp_path))
    assert r.exit_code == ExitCode.USAGE
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


# ---- discard-work ----


def fresh_work(*home_args: str) -> Path:
    import json

    r = invoke(*home_args, "new-work", "--slug", "demo", "--json")
    assert r.exit_code == 0, r.output
    return Path(json.loads(r.stdout)["work"])


def test_discard_removes_a_fresh_work_folder(sw_home):
    work = fresh_work()
    r = invoke("discard-work", "--work", str(work))
    assert r.exit_code == 0, r.output
    assert not work.exists() and (sw_home / "work").is_dir()


def test_discard_allows_the_first_stage_done(sw_home):
    work = fresh_work()
    WorkDir(work).mark("detect", "done")
    WorkDir(work).mark("ingest", "running")
    assert invoke("discard-work", "--work", str(work)).exit_code == 0
    assert not work.exists()


def test_discard_with_home_option(tmp_path, sw_home):
    project_home = tmp_path / "project" / ".skipwatch"
    work = fresh_work("--home", str(project_home))
    assert work.parent == project_home.absolute() / "work"
    assert invoke("discard-work", "--work", str(work)).exit_code == ExitCode.USAGE
    r = invoke("--home", str(project_home), "discard-work", "--work", str(work))
    assert r.exit_code == 0, r.output
    assert not work.exists()


def test_discard_refuses_a_folder_with_later_stages_done(sw_home):
    work = fresh_work()
    WorkDir(work).mark("detect", "done")
    WorkDir(work).mark("ingest", "done")
    r = invoke("discard-work", "--work", str(work))
    assert r.exit_code == ExitCode.USAGE
    assert (work / "stages.json").is_file()


def test_discard_refuses_folders_not_directly_in_the_home_work_folder(tmp_path, sw_home):
    elsewhere = outside_folder(tmp_path / "elsewhere")
    nested = sw_home / "work" / "a" / "b"
    WorkDir(nested).ensure()
    no_stages = sw_home / "work" / "plain-20261012-120000"
    write(no_stages / "keep.txt")
    for work in (elsewhere, nested, no_stages, sw_home / "work", sw_home, tmp_path):
        r = invoke("discard-work", "--work", str(work))
        assert r.exit_code == ExitCode.USAGE, work
        assert work.is_dir(), work
    assert (elsewhere / "stages.json").is_file() and (no_stages / "keep.txt").is_file()


def test_discard_refuses_a_symlink_into_the_work_folder(tmp_path, sw_home):
    outside = outside_folder(tmp_path / "elsewhere")
    (sw_home / "work").mkdir(parents=True)
    link = sw_home / "work" / "demo-20261012-120000"
    symlink(link, outside)
    r = invoke("discard-work", "--work", str(link))
    assert r.exit_code == ExitCode.USAGE
    assert (outside / "stages.json").is_file()


# ---- review round: only a real work folder under the home is ever cleaned ----


def victim(path: Path, stages: str | None = "") -> Path:
    """A folder that looks like a work folder: notes, frames and media, plus stages.json."""
    for name in ("notes/keep.txt", "frames/keep.jpg", "media/keep.mp4", "draft/SKILL.md"):
        write(path / name)
    if stages is not None:
        write(path / "stages.json", stages)
    return path


def assert_untouched(path: Path) -> None:
    for name in ("notes/keep.txt", "frames/keep.jpg", "media/keep.mp4", "draft/SKILL.md"):
        assert (path / name).is_file(), name
    assert not (path / "draft-pre-critic").exists()


@pytest.mark.parametrize("command", ["cleanup", "snapshot-draft"])
def test_an_arbitrary_folder_with_a_stages_json_is_refused(command, tmp_path):
    valid = (outside_folder(tmp_path) / "stages.json").read_text()
    for target in (
        victim(tmp_path / "anywhere", stages=""),
        victim(tmp_path / "valid-elsewhere", stages=valid),
        victim(skipwatch_home() / "work" / "empty-20261012-120000", stages=""),
        victim(skipwatch_home() / "work" / "a" / "nested-20261012-120000", stages=valid),
    ):
        r = invoke(command, "--work", str(target))
        assert r.exit_code == ExitCode.USAGE, (target, r.output)
        assert_untouched(target)


@pytest.mark.parametrize("command", ["cleanup", "snapshot-draft"])
def test_a_symlink_in_the_home_work_folder_is_refused(command, tmp_path):
    real = work_folder(tmp_path)
    victim(real, stages=None)
    link = skipwatch_home() / "work" / "link-20261012-120000"
    symlink(link, real)
    r = invoke(command, "--work", str(link))
    assert r.exit_code == ExitCode.USAGE
    assert_untouched(real)


def test_the_home_option_moves_the_accepted_work_root(tmp_path):
    project_home = tmp_path / "project" / ".skipwatch"
    work = project_home / "work" / "demo-20261012-120000"
    WorkDir(work).ensure()
    victim(work, stages=None)
    assert invoke("cleanup", "--work", str(work)).exit_code == ExitCode.USAGE
    assert_untouched(work)
    r = invoke("--home", str(project_home), "cleanup", "--work", str(work))
    assert r.exit_code == 0, r.output
    assert not (work / "notes").exists()


# ---- review round: --scratch is only this project's tester folder ----


def test_another_projects_tester_folder_is_refused(tmp_path):
    work = full_run(tmp_path)
    other = scratch_dir(tmp_path / "other")
    r = invoke("cleanup", "--work", str(work), "--scratch", str(other))
    assert r.exit_code == ExitCode.USAGE
    assert (other / "SKILL.md").is_file()
    assert (work / "draft" / "SKILL.md").is_file()


def test_a_scratch_symlink_to_a_matching_folder_is_refused(tmp_path):
    work = full_run(tmp_path)
    real = scratch_dir(tmp_path, "real")
    link = real.parent / "test-run-link"
    symlink(link, real)
    r = invoke("cleanup", "--work", str(work), "--scratch", str(link))
    assert r.exit_code == ExitCode.USAGE
    assert (real / "SKILL.md").is_file() and link.is_symlink()


def test_a_scratch_holding_the_work_folder_is_refused(tmp_path):
    scratch = tmp_path / "project" / ".skipwatch" / "test-run-home"
    home = scratch / ".skipwatch"
    work = home / "work" / "demo-20261012-120000"
    WorkDir(work).ensure()
    write(work / "draft" / "SKILL.md")
    r = invoke("--home", str(home), "cleanup", "--work", str(work), "--scratch", str(scratch))
    assert r.exit_code == ExitCode.USAGE
    assert (work / "draft" / "SKILL.md").is_file() and (work / "stages.json").is_file()


def test_discard_refuses_a_symlink_to_a_sibling_work_folder(sw_home):
    real = fresh_work()
    link = real.parent / "link-20261012-120000"
    symlink(link, real)
    r = invoke("discard-work", "--work", str(link))
    assert r.exit_code == ExitCode.USAGE
    assert (real / "stages.json").is_file() and link.is_symlink()


# ---- discard-pack: remove a pack work folder after install or cancel ----


def pack_folder(home: Path | None = None, name: str = "demo-20261012-120000") -> Path:
    """A pack work folder as unpack makes one: staging, ingest.json and stages.json."""
    work = (home or skipwatch_home()) / "packs" / name
    WorkDir(work).ensure()
    write(work / "staging" / "demo" / "SKILL.md")
    write(work / "ingest.json", "{}")
    return work


def test_discard_pack_removes_the_pack_and_this_projects_scratch(tmp_path):
    work = pack_folder()
    scratch = scratch_dir(tmp_path)
    r = invoke("discard-pack", "--work", str(work), "--scratch", str(scratch))
    assert r.exit_code == 0, r.output
    assert not work.exists() and not scratch.exists()
    assert (skipwatch_home() / "packs").is_dir()
    assert (tmp_path / "project" / ".skipwatch").is_dir()


def test_discard_pack_without_scratch_or_with_a_missing_scratch(tmp_path):
    work = pack_folder()
    assert invoke("discard-pack", "--work", str(work)).exit_code == 0
    assert not work.exists()
    work = pack_folder()
    missing = tmp_path / "project" / ".skipwatch" / "test-run-never"
    assert invoke("discard-pack", "--work", str(work), "--scratch", str(missing)).exit_code == 0
    assert not work.exists()


def test_discard_pack_accepts_any_stage_state():
    work = pack_folder()
    for stage in STAGE_ORDER:
        WorkDir(work).mark(stage, "done")
    assert invoke("discard-pack", "--work", str(work)).exit_code == 0
    assert not work.exists()


def test_discard_pack_with_home_option(tmp_path):
    project_home = tmp_path / "project" / ".skipwatch"
    work = pack_folder(project_home)
    assert invoke("discard-pack", "--work", str(work)).exit_code == ExitCode.USAGE
    assert (work / "stages.json").is_file()
    r = invoke("--home", str(project_home), "discard-pack", "--work", str(work))
    assert r.exit_code == 0, r.output
    assert not work.exists()


def test_discard_pack_refuses_anything_but_a_pack_folder(tmp_path):
    valid = (outside_folder(tmp_path) / "stages.json").read_text()
    home = skipwatch_home()
    run = work_folder(tmp_path)
    targets = (
        run,  # a run work folder under work/, valid stages.json
        victim(tmp_path / "anywhere", stages=valid),  # a planted stages.json elsewhere
        victim(tmp_path / "packs" / "demo-20261012-120000", stages=valid),  # a lookalike packs/
        victim(home / "packs" / "a" / "nested-20261012-120000", stages=valid),
        victim(home / "packs" / "empty-20261012-120000", stages=""),
        victim(home / "packs" / "none-20261012-120000", stages=None),
        victim(home / "PACKS" / "case-20261012-120000", stages=valid),
        victim(home / "work" / "packs" / "deep-20261012-120000", stages=valid),
    )
    for target in targets:
        r = invoke("discard-pack", "--work", str(target))
        assert r.exit_code == ExitCode.USAGE, (target, r.output)
        assert target.is_dir(), target
    for target in targets[1:]:
        assert_untouched(target)
    for target in (home / "packs", home, tmp_path):
        assert invoke("discard-pack", "--work", str(target)).exit_code == ExitCode.USAGE
        assert target.is_dir()
    assert (run / "stages.json").is_file()


def test_discard_pack_refuses_a_symlinked_pack_folder(tmp_path):
    real = pack_folder()
    outside = victim(tmp_path / "elsewhere", stages=(real / "stages.json").read_text())
    for name, target in (("link-a", real), ("link-b", outside)):
        link = real.parent / name
        symlink(link, target)
        r = invoke("discard-pack", "--work", str(link))
        assert r.exit_code == ExitCode.USAGE
        assert link.is_symlink()
    assert (real / "staging" / "demo" / "SKILL.md").is_file()
    assert_untouched(outside)


def test_discard_pack_refuses_a_bad_scratch_and_deletes_nothing(tmp_path):
    work = pack_folder()
    real = scratch_dir(tmp_path, "real")
    link = real.parent / "test-run-link"
    symlink(link, real)
    upper = real.parent / "TEST-RUN-upper"
    write(upper / "SKILL.md")
    for scratch in (
        scratch_dir(tmp_path / "other"),  # another project's tester folder
        link,  # a symlink to a matching folder
        upper,  # a case variant of the prefix
        tmp_path / "project" / ".SKIPWATCH" / "test-run-real",  # a case variant of the folder
        real.parent / "test-run-",  # the prefix alone
        real.parent,
        tmp_path / "project",
        work,
    ):
        r = invoke("discard-pack", "--work", str(work), "--scratch", str(scratch))
        assert r.exit_code == ExitCode.USAGE, (scratch, r.output)
        assert (work / "staging" / "demo" / "SKILL.md").is_file()
    assert (real / "SKILL.md").is_file() and link.is_symlink()
    assert (upper / "SKILL.md").is_file()
    assert (scratch_dir(tmp_path / "other") / "SKILL.md").is_file()


def test_discard_pack_refuses_a_scratch_holding_the_pack_folder(tmp_path):
    scratch = tmp_path / "project" / ".skipwatch" / "test-run-home"
    home = scratch / ".skipwatch"
    work = pack_folder(home)
    r = invoke("--home", str(home), "discard-pack", "--work", str(work), "--scratch", str(scratch))
    assert r.exit_code == ExitCode.USAGE
    assert (work / "staging" / "demo" / "SKILL.md").is_file()
    assert (work / "stages.json").is_file()


def test_discard_pack_refuses_a_bad_work_and_keeps_the_scratch(tmp_path):
    run = work_folder(tmp_path)
    scratch = scratch_dir(tmp_path)
    r = invoke("discard-pack", "--work", str(run), "--scratch", str(scratch))
    assert r.exit_code == ExitCode.USAGE
    assert (scratch / "SKILL.md").is_file() and (run / "stages.json").is_file()
