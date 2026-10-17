import json
import re
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch import cli
from skipwatch.cli import app
from skipwatch.errors import ExitCode
from skipwatch.models import RunFile, StagesFile
from skipwatch.resume import newest_incomplete
from skipwatch.workdir import read_model, write_model


def new_work(*args):
    return CliRunner().invoke(app, ["new-work", *args])


def test_new_work_creates_the_folder_under_skipwatch_home(sw_home):
    r = new_work("--slug", "youtube-com-abc-12", "--json")
    assert r.exit_code == 0, r.output
    work = Path(json.loads(r.stdout)["work"])
    assert work.is_absolute()
    assert work.parent == sw_home.absolute() / "work"
    assert re.fullmatch(r"youtube-com-abc-12-\d{8}-\d{6}", work.name)
    assert (work / "logs").is_dir() and (work / "draft").is_dir()
    read_model(work / "stages.json", StagesFile)  # the engine's own work-folder layout
    assert newest_incomplete(sw_home) is None  # no run.json yet: nothing to repeat
    run = RunFile(input="https://youtu.be/x", started_at="2026-10-09T12:00:00Z")
    write_model(work / "run.json", run)
    assert newest_incomplete(sw_home) == work  # resume finds it where new-work put it


def test_new_work_prints_only_the_path_without_json(sw_home):
    r = new_work("--slug", "demo")
    assert r.exit_code == 0
    assert Path(r.stdout.strip()).is_dir() and r.stdout.count("\n") == 1


def test_new_work_uses_home_when_skipwatch_home_is_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("SKIPWATCH_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Path.home() on Windows
    r = new_work("--slug", "demo", "--json")
    assert r.exit_code == 0, r.output
    work = Path(json.loads(r.stdout)["work"])
    assert work.parent == tmp_path / ".skipwatch" / "work"


def test_new_work_relative_home_is_made_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SKIPWATCH_HOME", "rel-home")
    r = new_work("--slug", "demo", "--json")
    work = Path(json.loads(r.stdout)["work"])
    assert work.is_absolute() and work.parent == tmp_path / "rel-home" / "work"


@pytest.mark.parametrize("slug", ["", "Has-Caps", "a/b", "../x", "-lead", "a b", "x" * 81, "abc\n"])
def test_new_work_bad_slug_is_usage_error(slug, sw_home, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["skipwatch", "new-work", "--slug", slug])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == ExitCode.USAGE
    assert not (sw_home / "work").exists()


def test_parallel_new_work_calls_get_distinct_complete_folders(sw_home):
    import os
    import subprocess

    cmd = [sys.executable, "-c", "from skipwatch.cli import main; main()"]
    cmd += ["new-work", "--slug", "demo", "--json"]
    env = {**os.environ, "SKIPWATCH_HOME": str(sw_home)}
    procs = [
        subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        for _ in range(6)
    ]
    results = [(p.wait(timeout=60), *p.communicate()) for p in procs]
    for code, _, err in results:
        assert code == 0, err
    works = [Path(json.loads(out)["work"]) for _, out, _ in results]
    assert len(set(works)) == 6  # never two runs in one folder
    for work in works:
        read_model(work / "stages.json", StagesFile)
        assert (work / "logs").is_dir() and (work / "draft").is_dir()
        assert re.fullmatch(r"demo-\d{8}-\d{6}", work.name)


def assert_one_line_exit_7(r):
    assert r.exit_code == 7
    assert "cannot create the work folder" in r.output
    assert isinstance(r.exception, SystemExit)  # no uncaught OSError traceback


def test_unwritable_home_is_one_line_exit_7(sw_home, monkeypatch):
    # OS-independent: chmod cannot make a directory read-only on Windows
    real_mkdir = Path.mkdir

    def denied(self, *args, **kwargs):
        if sw_home in self.parents:
            raise PermissionError(13, "Permission denied", str(self))
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", denied)
    assert_one_line_exit_7(new_work("--slug", "demo"))


@pytest.mark.skipif(sys.platform == "win32", reason="chmod does not make a folder read-only")
def test_read_only_work_folder_is_one_line_exit_7(sw_home):
    (sw_home / "work").mkdir(parents=True)
    (sw_home / "work").chmod(0o500)  # read-only work/: mkdir fails with PermissionError
    try:
        r = new_work("--slug", "demo")
    finally:
        (sw_home / "work").chmod(0o700)
    assert_one_line_exit_7(r)


def test_ensure_failure_is_one_line_exit_7(sw_home, monkeypatch):
    # the folder was claimed, but stages.json could not be written (disk full, quota)
    from skipwatch.commands import new_work as new_work_mod

    def full(self):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(new_work_mod.WorkDir, "ensure", full)
    assert_one_line_exit_7(new_work("--slug", "demo"))


def test_new_work_json_gives_started_at_in_utc_for_run_json(sw_home):
    from datetime import UTC, datetime, timedelta

    before = datetime.now(UTC).replace(microsecond=0)
    r = new_work("--slug", "demo", "--json")
    assert r.exit_code == 0, r.output
    started = json.loads(r.stdout)["started_at"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", started)
    when = datetime.fromisoformat(started.replace("Z", "+00:00"))
    assert before <= when <= datetime.now(UTC) + timedelta(seconds=1)
    RunFile(input="x", started_at=started)  # the skill copies it into run.json as is
