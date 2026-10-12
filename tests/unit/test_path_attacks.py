"""Adversarial review REV6: a path that names a symlink through `..` (or a symlink the guard
never saw) must not let --log, redact or probe read or write outside the work folder.
Victims live in a fake $HOME under tmp_path, never in real dotfiles."""

import os
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch import cli, stagelog
from skipwatch.cli import app
from skipwatch.errors import ExitCode
from skipwatch.workdir import WorkDir, write_bytes_atomic

ZSHRC = "export PATH=keep\n"
KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nsecret\n"


@pytest.fixture
def fake_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "fakehome"
    (home / ".ssh").mkdir(parents=True)
    (home / ".zshrc").write_text(ZSHRC, encoding="utf-8")
    (home / ".ssh" / "id_rsa").write_text(KEY, encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def work(sw_home) -> Path:
    path = sw_home / "work" / "demo-20261012-120000"
    WorkDir(path).ensure()
    for sub in ("logs", "draft", "staging"):
        (path / sub).mkdir()
    return path


def link(at: Path, target: Path) -> None:
    try:
        at.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"cannot create symlinks here: {exc}")


def _run_main(monkeypatch, args) -> int:
    monkeypatch.setattr(sys, "argv", ["skipwatch", *args])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    return int(exc.value.code)


def test_log_through_dotdot_to_a_symlink_is_refused(monkeypatch, capsys, fake_home, work):
    link(work / "logs" / "lnk", fake_home / ".zshrc")
    log = work / "logs" / "nosuch" / ".." / "lnk"
    code = _run_main(monkeypatch, ["--log", str(log), "note", "--work", str(work), "--clear", "x"])
    assert code == ExitCode.USAGE
    assert (fake_home / ".zshrc").read_text(encoding="utf-8") == ZSHRC


def test_any_dotdot_in_log_is_refused(monkeypatch, capsys, work):
    log = work / "logs" / "a" / ".." / "ok.log"
    code = _run_main(monkeypatch, ["--log", str(log), "note", "--work", str(work), "--clear", "x"])
    assert code == ExitCode.USAGE
    assert not (work / "logs" / "ok.log").exists()


def redact(*args: str):
    return CliRunner().invoke(app, ["redact", *args])


def test_redact_in_through_dotdot_to_a_symlinked_key_is_refused(fake_home, work):
    link(work / "draft" / "key", fake_home / ".ssh" / "id_rsa")
    src = work / "draft" / "nosuch" / ".." / "key"
    out = work / "staging" / "demo" / "key.md"
    r = redact("--work", str(work), "--in", str(src), "--out", str(out))
    assert r.exit_code == ExitCode.USAGE
    assert not out.exists()


def test_redact_out_through_dotdot_to_a_symlink_is_refused(fake_home, work):
    (work / "draft" / "a.md").write_text("hello\n", encoding="utf-8")
    link(work / "staging" / "zl", fake_home / ".zshrc")
    out = work / "staging" / "nosuch" / ".." / "zl"
    r = redact("--work", str(work), "--in", str(work / "draft" / "a.md"), "--out", str(out))
    assert r.exit_code == ExitCode.USAGE
    assert (fake_home / ".zshrc").read_text(encoding="utf-8") == ZSHRC


def test_probe_out_through_dotdot_to_a_symlink_is_refused(fake_home, work):
    link(work / "logs" / "p", fake_home / ".zshrc")
    out = work / "logs" / "nosuch" / ".." / "p"
    r = CliRunner().invoke(app, ["probe", "x", "--work", str(work), "--out", str(out)])
    assert r.exit_code == ExitCode.USAGE
    assert (fake_home / ".zshrc").read_text(encoding="utf-8") == ZSHRC


def test_symlinked_folder_inside_the_area_is_refused(fake_home, work):
    (work / "draft" / "a.md").write_text("hello\n", encoding="utf-8")
    inner = work / "staging" / "real"
    inner.mkdir()
    link(work / "staging" / "alias", inner)
    out = work / "staging" / "alias" / "a.md"
    r = redact("--work", str(work), "--in", str(work / "draft" / "a.md"), "--out", str(out))
    assert r.exit_code == ExitCode.USAGE
    assert not (inner / "a.md").exists()


# ---- the openers themselves never follow a final symlink (a swap after the check) ----


def test_stagelog_start_does_not_follow_a_symlink(fake_home, tmp_path):
    lnk = tmp_path / "run.log"
    link(lnk, fake_home / ".zshrc")
    with pytest.raises(OSError):
        stagelog.start(lnk)
    stagelog.stop()
    assert (fake_home / ".zshrc").read_text(encoding="utf-8") == ZSHRC


def test_atomic_write_replaces_a_symlink_and_ignores_a_planted_temp(fake_home, tmp_path):
    out = tmp_path / "out.json"
    link(out, fake_home / ".zshrc")
    link(tmp_path / "out.json.tmp", fake_home / ".zshrc")
    write_bytes_atomic(out, b"new\n")
    assert out.read_bytes() == b"new\n" and not out.is_symlink()
    assert (fake_home / ".zshrc").read_text(encoding="utf-8") == ZSHRC


def test_redact_reads_in_without_following_a_swapped_symlink(fake_home, work, monkeypatch):
    from skipwatch.commands import redact as redact_module

    src = work / "draft" / "a.md"
    link(src, fake_home / ".ssh" / "id_rsa")
    monkeypatch.setattr(redact_module, "path_under", lambda w, sub, p, flag: p)
    out = work / "staging" / "a.md"
    r = redact("--work", str(work), "--in", str(src), "--out", str(out))
    assert r.exit_code != 0
    assert not out.exists() or "secret" not in out.read_text(encoding="utf-8")
    assert os.path.exists(fake_home / ".ssh" / "id_rsa")
