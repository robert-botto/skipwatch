import json
import re
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch import cli
from skipwatch.cli import app
from skipwatch.errors import ExitCode
from skipwatch.models import StagesFile
from skipwatch.resume import newest_incomplete
from skipwatch.workdir import read_model


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
    assert newest_incomplete(sw_home) == work  # resume finds it where new-work put it


def test_new_work_prints_only_the_path_without_json(sw_home):
    r = new_work("--slug", "demo")
    assert r.exit_code == 0
    assert Path(r.stdout.strip()).is_dir() and r.stdout.count("\n") == 1


def test_new_work_uses_home_when_skipwatch_home_is_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("SKIPWATCH_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
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


@pytest.mark.parametrize("slug", ["", "Has-Caps", "a/b", "../x", "-lead", "a b", "x" * 81])
def test_new_work_bad_slug_is_usage_error(slug, sw_home, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["skipwatch", "new-work", "--slug", slug])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == ExitCode.USAGE
    assert not (sw_home / "work").exists()
