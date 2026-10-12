"""Adversarial review REV6 item 2: every command that takes a work folder checks it first
(directly under the home's work/ or packs/, not a symlink, a stages.json that reads), so a
pre-approved engine call cannot write into, or delete from, any other folder."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.errors import ExitCode
from skipwatch.workdir import WorkDir

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _victim(root: Path) -> Path:
    """A folder that looks like a work folder (stages.json, frames/, staging/) but is not one."""
    WorkDir(root).ensure()
    for sub in ("frames", "staging/demo", "notes", "logs"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    (root / "frames" / "keep.txt").write_text("keep", encoding="utf-8")
    (root / "staging" / "demo" / "SKILL.md").write_text("---\nname: demo\n---\n", encoding="utf-8")
    return root


def _commands(work: Path) -> list[list[str]]:
    skill = str(work / "staging" / "demo")
    return [
        ["frames", "--work", str(work)],
        ["plan", "--work", str(work)],
        ["ingest", str(FIXTURES / "tutorial-60s.mp4"), "--work", str(work)],
        ["transcribe", "--work", str(work)],
        ["mark", "--work", str(work), "--stage", "read", "--status", "done"],
        ["merge-notes", "--work", str(work), "--batch", "1"],
        ["validate-notes", "--work", str(work)],
        ["validate-critique", "--work", str(work), "--skill", skill],
        ["validate-test", "--work", str(work)],
        ["copy-frames", "--work", str(work), "--to", f"{skill}/frames", "f000001"],
        ["check", skill, "--work", str(work)],
        ["check", skill],
        ["review", "--work", str(work), "--skill", skill],
        ["resume", str(work)],
    ]


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): (p.read_bytes() if p.is_file() else b"<dir>")
        for p in sorted(root.rglob("*"))
    }


def _assert_refused_and_untouched(target: Path, real: Path) -> None:
    before = _snapshot(real)
    for args in _commands(target):
        r = CliRunner().invoke(app, args)
        assert r.exit_code == ExitCode.USAGE, (args, r.output)
        assert _snapshot(real) == before, args


def test_a_folder_outside_the_home_is_refused_untouched(tmp_path, sw_home):
    victim = _victim(tmp_path / "elsewhere" / "demo-20261012-120000")
    _assert_refused_and_untouched(victim, victim)


def test_a_nested_folder_under_work_is_refused_untouched(sw_home):
    victim = _victim(sw_home / "work" / "a" / "demo-20261012-120000")
    _assert_refused_and_untouched(victim, victim)


def test_a_symlinked_work_folder_is_refused_untouched(tmp_path, sw_home):
    victim = _victim(tmp_path / "elsewhere" / "demo-20261012-120000")
    link = sw_home / "work" / "demo-20261012-120000"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(victim, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"cannot create symlinks here: {exc}")
    _assert_refused_and_untouched(link, victim)
