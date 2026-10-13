"""scripts/skipwatch: runs the synced venv's engine directly, syncing with uv only when stale."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts/skipwatch"
SYSTEM_PATH = "/usr/bin:/bin"  # sh, cat, cmp, dirname; never uv

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX sh wrapper")


def make_plugin(tmp_path: Path, *, venv: bool = True, fresh: bool = True) -> Path:
    """A fake plugin root with the real wrapper, a lock file and a fake engine."""
    root = tmp_path / "plugin root"  # a space, like real install paths can have
    (root / "scripts").mkdir(parents=True)
    shutil.copy(WRAPPER, root / "scripts/skipwatch")
    (root / "uv.lock").write_text("lock v1\n")
    (root / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    if venv:
        engine = root / ".venv/bin/skipwatch"
        engine.parent.mkdir(parents=True)
        engine.write_text('#!/bin/sh\necho "engine ran: $*"\necho "root=$CLAUDE_PLUGIN_ROOT"\n')
        engine.chmod(0o755)
        if fresh:
            stamp = (root / "uv.lock").read_text() + (root / "pyproject.toml").read_text()
            (root / ".venv/.skipwatch-synced").write_text(stamp)
    return root


def fake_uv(tmp_path: Path, *, ok: bool = True) -> tuple[Path, Path]:
    """A uv on PATH that records its arguments and succeeds or fails."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    log = tmp_path / "uv-calls.log"
    uv = bin_dir / "uv"
    uv.write_text(
        f'#!/bin/sh\necho "$*" >> "{log}"\n' + ("exit 0\n" if ok else "echo boom >&2\nexit 2\n")
    )
    uv.chmod(0o755)
    return bin_dir, log


def run(root: Path, *args: str, path: str = SYSTEM_PATH, **env: str):
    clean = {"PATH": path, "HOME": os.environ.get("HOME", "/tmp"), **env}
    return subprocess.run(
        ["sh", str(root / "scripts/skipwatch"), *args],
        capture_output=True,
        text=True,
        env=clean,
        timeout=30,
    )


def test_fast_path_execs_engine_without_uv(tmp_path):
    root = make_plugin(tmp_path)
    bin_dir, log = fake_uv(tmp_path)
    r = run(root, "doctor", "--json", path=f"{bin_dir}:{SYSTEM_PATH}")
    assert r.returncode == 0, r.stderr
    assert "engine ran: doctor --json" in r.stdout
    assert not log.exists()  # uv never called on the fast path


def test_stale_stamp_runs_uv_sync_locked(tmp_path):
    root = make_plugin(tmp_path, fresh=False)
    bin_dir, log = fake_uv(tmp_path)
    r = run(root, "plan", path=f"{bin_dir}:{SYSTEM_PATH}")
    assert r.returncode == 0, r.stderr
    calls = log.read_text()
    assert "sync" in calls and "--locked" in calls and "--inexact" in calls and str(root) in calls
    assert "engine ran: plan" in r.stdout
    assert (root / ".venv/.skipwatch-synced").exists()  # next call takes the fast path


def test_no_uv_and_no_venv_exits_127(tmp_path):
    root = make_plugin(tmp_path, venv=False)
    r = run(root, "doctor")
    assert r.returncode == 127
    assert "uv is not installed" in r.stderr


def test_sync_failure_with_existing_venv_falls_back(tmp_path):
    root = make_plugin(tmp_path, fresh=False)
    bin_dir, log = fake_uv(tmp_path, ok=False)
    r = run(root, "frames", path=f"{bin_dir}:{SYSTEM_PATH}")
    assert r.returncode == 0, r.stderr
    assert "could not refresh the environment (boom)" in r.stderr  # uv's first line
    assert "sandboxed?" not in r.stderr
    assert "engine ran: frames" in r.stdout


def test_sync_failure_without_venv_names_the_fix(tmp_path):
    root = make_plugin(tmp_path, venv=False)
    bin_dir, _ = fake_uv(tmp_path, ok=False)
    r = run(root, "doctor", path=f"{bin_dir}:{SYSTEM_PATH}")
    assert r.returncode == 78  # EX_CONFIG: the wrapper failed, the engine never ran
    assert "could not create the Python environment" in r.stderr and "uv sync" in r.stderr


def test_sync_only_exits_0_without_running_engine(tmp_path):
    root = make_plugin(tmp_path, fresh=False)
    bin_dir, log = fake_uv(tmp_path)
    r = run(root, path=f"{bin_dir}:{SYSTEM_PATH}", SKIPWATCH_SYNC_ONLY="1")
    assert r.returncode == 0, r.stderr
    assert "engine ran" not in r.stdout
    assert "sync" in log.read_text()


def test_exports_plugin_root_for_engine_advice(tmp_path):
    root = make_plugin(tmp_path)
    r = run(root, "doctor", CLAUDE_PLUGIN_ROOT="/wrong/place")
    assert r.returncode == 0, r.stderr
    assert f"root={root}" in r.stdout


def test_marketplace_install_syncs_without_dev_tools(tmp_path):
    root = make_plugin(tmp_path, fresh=False)  # no .git: a marketplace install
    bin_dir, log = fake_uv(tmp_path)
    assert run(root, "plan", path=f"{bin_dir}:{SYSTEM_PATH}").returncode == 0
    assert "--no-dev" in log.read_text()


def test_git_checkout_keeps_dev_tools(tmp_path):
    root = make_plugin(tmp_path, fresh=False)
    (root / ".git").mkdir()
    bin_dir, log = fake_uv(tmp_path)
    assert run(root, "plan", path=f"{bin_dir}:{SYSTEM_PATH}").returncode == 0
    calls = log.read_text()
    assert "--no-dev" not in calls and "--inexact" in calls


def test_sync_only_never_fails_without_uv(tmp_path):
    # a SessionStart hook must not fail in projects that never use SkipWatch
    root = make_plugin(tmp_path, venv=False)
    r = run(root, SKIPWATCH_SYNC_ONLY="1")
    assert r.returncode == 0
    assert "uv is not installed" in r.stderr


def test_sync_only_never_fails_when_sync_fails(tmp_path):
    root = make_plugin(tmp_path, venv=False)
    bin_dir, _ = fake_uv(tmp_path, ok=False)
    r = run(root, path=f"{bin_dir}:{SYSTEM_PATH}", SKIPWATCH_SYNC_ONLY="1")
    assert r.returncode == 0
    assert "could not create the Python environment" in r.stderr


def test_stamp_written_atomically(tmp_path):
    root = make_plugin(tmp_path, fresh=False)
    bin_dir, _ = fake_uv(tmp_path)
    assert run(root, "plan", path=f"{bin_dir}:{SYSTEM_PATH}").returncode == 0
    assert not list((root / ".venv").glob(".skipwatch-synced.tmp*"))
    assert '"$stamp.tmp.$$"' in WRAPPER.read_text()


def test_gitattributes_keeps_lf_for_shell_scripts():
    text = (ROOT / ".gitattributes").read_text()
    assert "scripts/skipwatch text eol=lf" in text
    assert "*.sh text eol=lf" in text


def test_git_worktree_keeps_dev_tools(tmp_path):
    root = make_plugin(tmp_path, fresh=False)
    (root / ".git").write_text("gitdir: /elsewhere\n")  # a worktree's .git is a file
    bin_dir, log = fake_uv(tmp_path)
    assert run(root, "plan", path=f"{bin_dir}:{SYSTEM_PATH}").returncode == 0
    assert "--no-dev" not in log.read_text()


def fake_uname(tmp_path: Path, system: str) -> Path:
    """A `uname` on PATH that reports another OS, so every install hint is testable here."""
    bin_dir = tmp_path / f"uname-{system}"
    bin_dir.mkdir()
    uname = bin_dir / "uname"
    uname.write_text(f'#!/bin/sh\necho "{system}"\n')
    uname.chmod(0o755)
    return bin_dir


CURL_INSTALL = "curl -LsSf https://astral.sh/uv/install.sh | sh"
PS_INSTALL = 'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'


@pytest.mark.parametrize(
    ("system", "expected", "absent"),
    [
        ("Darwin", ["brew install uv", CURL_INSTALL], [PS_INSTALL]),
        ("Linux", [CURL_INSTALL], ["brew install uv", PS_INSTALL]),
        ("MINGW64_NT-10.0-19045", [PS_INSTALL], [CURL_INSTALL, "brew install uv"]),
        ("MSYS_NT-10.0-19045", [PS_INSTALL], [CURL_INSTALL]),
        ("CYGWIN_NT-10.0-19045", [PS_INSTALL], [CURL_INSTALL]),
    ],
)
def test_no_uv_names_the_install_command_for_this_os(tmp_path, system, expected, absent):
    root = make_plugin(tmp_path, venv=False)
    path = f"{fake_uname(tmp_path, system)}:{SYSTEM_PATH}"
    for env in ({}, {"SKIPWATCH_SYNC_ONLY": "1"}):
        r = run(root, "doctor", path=path, **env)
        assert r.returncode == (0 if env else 127)
        assert "Traceback" not in r.stderr
        for command in expected:
            assert command in r.stderr, (system, env, r.stderr)
        for command in absent:
            assert command not in r.stderr, (system, env, r.stderr)


def test_no_uv_hook_mode_keeps_stdout_empty(tmp_path):
    # SessionStart stdout becomes Claude's context in every project; stderr on exit 0 is
    # never shown, so a missing uv costs the session nothing.
    root = make_plugin(tmp_path, venv=False)
    r = run(root, SKIPWATCH_SYNC_ONLY="1")
    assert r.returncode == 0 and r.stdout == ""
    assert "uv is not installed" in r.stderr


def test_no_uv_message_never_runs_an_installer(tmp_path):
    root = make_plugin(tmp_path, venv=False)
    bin_dir = tmp_path / "trap"
    bin_dir.mkdir()
    log = tmp_path / "trap.log"
    for tool in ("curl", "brew", "powershell", "wget"):
        (bin_dir / tool).write_text(f'#!/bin/sh\necho {tool} >> "{log}"\n')
        (bin_dir / tool).chmod(0o755)
    r = run(root, "doctor", path=f"{bin_dir}:{SYSTEM_PATH}")
    assert r.returncode == 127
    assert not log.exists()


@pytest.mark.parametrize("bin_dir", [".local/bin", ".cargo/bin"])
def test_finds_uv_the_installer_just_put_off_path(tmp_path, bin_dir):
    # The curl/PowerShell installer puts uv in ~/.local/bin (older ones ~/.cargo/bin) and
    # only new shells see it; Claude Code keeps its PATH, so "then retry" must still work.
    root = make_plugin(tmp_path, fresh=False)
    home = tmp_path / "home"
    fake_bin, log = fake_uv(tmp_path)
    (home / bin_dir).mkdir(parents=True)
    shutil.copy(fake_bin / "uv", home / bin_dir / "uv")
    r = run(root, "plan", HOME=str(home))
    assert r.returncode == 0, r.stderr
    assert "sync" in log.read_text()
    assert "engine ran: plan" in r.stdout


def test_home_uv_is_ignored_when_not_executable(tmp_path):
    root = make_plugin(tmp_path, venv=False)
    home = tmp_path / "home"
    (home / ".local/bin").mkdir(parents=True)
    (home / ".local/bin/uv").write_text("not a program\n")
    r = run(root, "doctor", HOME=str(home))
    assert r.returncode == 127 and "uv is not installed" in r.stderr
