"""`note`: degradations and unread frames persist in the work folder so a resumed run
still shows them on the review screen (skill audit 4 fix 2)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.errors import ExitCode
from skipwatch.models import DegradationsFile
from skipwatch.workdir import WorkDir, read_model

UNREAD = "f006032 (reader failed twice)"


def note(work: Path, *args: str):
    return CliRunner().invoke(app, ["note", "--work", str(work), *args])


@pytest.fixture
def work(sw_home) -> Path:
    path = sw_home / "work" / "demo-20261012-120000"
    WorkDir(path).ensure()
    return path


def recorded(work: Path) -> DegradationsFile:
    return read_model(work / "degradations.json", DegradationsFile)


def test_note_appends_in_order_and_skips_repeats(work):
    for args in (
        ("--degradation", "critic failed twice"),
        ("--unread", UNREAD),
        ("--degradation", "no frames: audio-only file"),
        ("--degradation", "critic failed twice"),
        ("--unread", UNREAD),
    ):
        r = note(work, *args)
        assert r.exit_code == 0, r.output
    file = recorded(work)
    assert file.degradations == ["critic failed twice", "no frames: audio-only file"]
    assert file.unread == [UNREAD]
    assert json.loads((work / "degradations.json").read_text())["schema"] == (
        "skipwatch/degradations/1"
    )


@pytest.mark.parametrize(
    "args",
    [
        (),
        ("--degradation", "a", "--unread", UNREAD),
        ("--degradation", ""),
        ("--degradation", "   "),
        ("--unread", "two\nlines"),
        ("--degradation", "tab\there"),
        ("--degradation", "nul\x00byte"),
        ("--degradation", "zero\u200bwidth"),
        ("--degradation", "bidi\u202eflip"),
        ("--degradation", "private\ue000use"),
        ("--degradation", "unassigned\u0378"),
        ("--unread", "f000001 (escape\x1b[31m)"),
        ("--degradation", "line\u2028separator"),
        ("--degradation", "paragraph\u2029separator"),
    ],
)
def test_note_takes_exactly_one_single_line_value(work, args):
    r = note(work, *args)
    assert r.exit_code == ExitCode.USAGE
    assert not (work / "degradations.json").exists()


def test_note_outside_a_work_folder_is_exit_64(tmp_path, sw_home):
    elsewhere = tmp_path / "elsewhere" / "demo-20261012-120000"
    WorkDir(elsewhere).ensure()  # a valid stages.json, but not under the home's work/
    nested = sw_home / "work" / "a" / "demo-20261012-120000"
    WorkDir(nested).ensure()
    empty = sw_home / "work" / "empty-20261012-120000"
    empty.mkdir(parents=True)
    (empty / "stages.json").write_text("", encoding="utf-8")
    for target in (tmp_path, elsewhere, nested, empty):
        r = note(target, "--degradation", "x")
        assert r.exit_code == ExitCode.USAGE, target
        assert not (target / "degradations.json").exists(), target


def test_note_on_an_invalid_file_is_exit_7_and_leaves_it(work):
    (work / "degradations.json").write_text("{not json", encoding="utf-8")
    r = note(work, "--degradation", "x")
    assert r.exit_code == ExitCode.NO_CONTENT
    assert "delete" in r.stderr and "degradations.json" in r.stderr
    assert (work / "degradations.json").read_text() == "{not json"
