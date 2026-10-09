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


def test_wrapper_is_executable_in_repo():
    assert WRAPPER.is_file() and os.access(WRAPPER, os.X_OK)


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
    assert "sync" in calls and "--locked" in calls and str(root) in calls
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
    assert "could not refresh the environment" in r.stderr
    assert "engine ran: frames" in r.stdout


def test_sync_failure_without_venv_names_the_fix(tmp_path):
    root = make_plugin(tmp_path, venv=False)
    bin_dir, _ = fake_uv(tmp_path, ok=False)
    r = run(root, "doctor", path=f"{bin_dir}:{SYSTEM_PATH}")
    assert r.returncode == 1
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
