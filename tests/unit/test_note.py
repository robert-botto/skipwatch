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


# ---- --critic-failed: stage 7's "failed twice" without a shell rm ----

CRITIC = "critic failed twice"


def test_critic_failed_records_once_and_deletes_the_critique(work):
    (work / "critique.json").write_text("{}", encoding="utf-8")
    for _ in range(2):
        r = note(work, "--critic-failed")
        assert r.exit_code == 0, r.output
        assert not (work / "critique.json").exists()
    assert recorded(work).degradations == [CRITIC]


def test_critic_failed_dedups_against_a_noted_degradation(work):
    assert note(work, "--degradation", CRITIC).exit_code == 0
    assert note(work, "--critic-failed").exit_code == 0
    assert recorded(work).degradations == [CRITIC]


def test_critic_failed_unlinks_a_critique_symlink_and_keeps_its_target(tmp_path, work):
    target = tmp_path / "keep.json"
    target.write_text("{}", encoding="utf-8")
    try:
        (work / "critique.json").symlink_to(target)
    except OSError as exc:
        pytest.skip(f"cannot create symlinks here: {exc}")
    assert note(work, "--critic-failed").exit_code == 0
    assert not (work / "critique.json").is_symlink() and target.is_file()


@pytest.mark.parametrize(
    "args",
    [
        ("--critic-failed", "--degradation", "x"),
        ("--critic-failed", "--unread", UNREAD),
    ],
)
def test_critic_failed_with_another_flag_is_exit_64_and_deletes_nothing(work, args):
    (work / "critique.json").write_text("{}", encoding="utf-8")
    r = note(work, *args)
    assert r.exit_code == ExitCode.USAGE
    assert (work / "critique.json").is_file()
    assert not (work / "degradations.json").exists()


def test_critic_failed_outside_a_work_folder_deletes_nothing(tmp_path, sw_home):
    elsewhere = tmp_path / "elsewhere" / "demo-20261012-120000"
    WorkDir(elsewhere).ensure()
    (elsewhere / "critique.json").write_text("{}", encoding="utf-8")
    r = note(elsewhere, "--critic-failed")
    assert r.exit_code == ExitCode.USAGE
    assert (elsewhere / "critique.json").is_file()


# ---- --clear: drop a fixed degradation without the skill rewriting the file ----


def test_clear_removes_every_line_with_the_prefix_and_keeps_the_rest(work):
    for line in ("no transcript: no captions", "no frames: audio", "no transcript: again"):
        assert note(work, "--degradation", line).exit_code == 0
    assert note(work, "--unread", "no transcript: (an unread line)").exit_code == 0
    r = note(work, "--clear", "no transcript:")
    assert r.exit_code == 0, r.output
    file = recorded(work)
    assert file.degradations == ["no frames: audio"]
    assert file.unread == ["no transcript: (an unread line)"]


def test_clear_is_an_exact_case_sensitive_prefix(work):
    assert note(work, "--degradation", "no transcript: x").exit_code == 0
    for prefix in ("No transcript:", "NO TRANSCRIPT:", "transcript:", " no transcript:"):
        assert note(work, "--clear", prefix).exit_code == 0
    assert recorded(work).degradations == ["no transcript: x"]


def test_clear_with_nothing_matching_is_exit_0(work):
    assert note(work, "--clear", "no transcript:").exit_code == 0
    assert not (work / "degradations.json").exists()


@pytest.mark.parametrize(
    "args",
    [
        ("--clear", "x", "--degradation", "y"),
        ("--clear", "x", "--unread", UNREAD),
        ("--clear", "x", "--critic-failed"),
        ("--clear", ""),
        ("--clear", "   "),
        ("--clear", "two\nlines"),
        ("--clear", "bidi‮flip"),
        ("--clear", "line separator"),
    ],
)
def test_clear_takes_one_printable_value_alone(work, args):
    assert note(work, "--degradation", "x keep").exit_code == 0
    r = note(work, *args)
    assert r.exit_code == ExitCode.USAGE
    assert recorded(work).degradations == ["x keep"]


def test_clear_outside_a_work_folder_is_exit_64(tmp_path, sw_home):
    elsewhere = tmp_path / "elsewhere" / "demo-20261012-120000"
    WorkDir(elsewhere).ensure()
    (elsewhere / "degradations.json").write_text("{}", encoding="utf-8")
    r = note(elsewhere, "--clear", "x")
    assert r.exit_code == ExitCode.USAGE
    assert (elsewhere / "degradations.json").read_text() == "{}"


def test_critic_failed_deletes_the_critique_even_with_a_corrupt_file(work):
    (work / "critique.json").write_text("{}", encoding="utf-8")
    (work / "degradations.json").write_text("{not json", encoding="utf-8")
    r = note(work, "--critic-failed")
    assert r.exit_code == ExitCode.NO_CONTENT
    assert not (work / "critique.json").exists()
    assert (work / "degradations.json").read_text() == "{not json"


# ---- pack test runs: stage 9b notes into a work folder under the home's packs/ ----


@pytest.fixture
def pack(sw_home) -> Path:
    path = sw_home / "packs" / "demo-20261012-120000"
    WorkDir(path).ensure()
    return path


def test_note_accepts_a_pack_work_folder(pack):
    r = note(pack, "--degradation", "test run failed twice")
    assert r.exit_code == 0, r.output
    assert recorded(pack).degradations == ["test run failed twice"]


def test_note_on_a_pack_respects_home(tmp_path, sw_home):
    home = tmp_path / "other-home"
    pack = home / "packs" / "demo-20261012-120000"
    WorkDir(pack).ensure()
    r = CliRunner().invoke(
        app,
        ["--home", str(home), "note", "--work", str(pack), "--degradation", "x"],
    )
    assert r.exit_code == 0, r.output
    assert recorded(pack).degradations == ["x"]


def test_note_refuses_bad_pack_folders(tmp_path, sw_home):
    nested = sw_home / "packs" / "a" / "demo-20261012-120000"
    WorkDir(nested).ensure()
    empty = sw_home / "packs" / "empty-20261012-120000"
    empty.mkdir(parents=True)
    (empty / "stages.json").write_text("", encoding="utf-8")
    real = tmp_path / "real" / "demo-20261012-120000"
    WorkDir(real).ensure()
    link = sw_home / "packs" / "link-20261012-120000"
    targets = [nested, empty, sw_home / "packs"]
    try:
        link.symlink_to(real, target_is_directory=True)
        targets.append(link)
    except OSError:
        pass
    for target in targets:
        r = note(target, "--critic-failed")
        assert r.exit_code == ExitCode.USAGE, target
        assert not (target / "degradations.json").exists(), target
    assert not (real / "degradations.json").exists()
