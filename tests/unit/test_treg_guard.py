"""No non-live test ever reaches a real treg, in this process or in a subprocess (pipeline tests
run the real CLI with os.environ). tests/conftest.py sets SKIPWATCH_TREG_DISABLED=1 and puts a
failing stub `treg` first on PATH; content_treg honours the variable."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from skipwatch.providers import content_treg

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the fake treg is a sh script")


def _engine() -> str:
    found = shutil.which("skipwatch", path=str(Path(sys.executable).parent))
    assert found, "no skipwatch entry point next to the interpreter; run uv sync --dev"
    return found


def test_env_guard_hides_treg(monkeypatch):
    monkeypatch.setattr(content_treg.shutil, "which", lambda name: "/opt/bin/treg")
    monkeypatch.setenv(content_treg.DISABLE_ENV, "1")
    assert content_treg._treg_path() is None
    monkeypatch.delenv(content_treg.DISABLE_ENV)
    assert content_treg._treg_path() == "/opt/bin/treg"


def test_conftest_puts_a_failing_stub_treg_first_on_path():
    assert os.environ.get(content_treg.DISABLE_ENV) == "1"
    stub = shutil.which("treg")
    assert stub is not None
    result = subprocess.run([stub, "balance", "--json"], capture_output=True, check=False)
    assert result.returncode != 0


def test_cli_subprocesses_never_run_treg(tmp_path):
    """Doctor and an ingest under --provider auto, as the pipeline tests run them, with a
    logging fake treg first on PATH: it is never invoked."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "treg.log"
    fake = bin_dir / "treg"
    fake.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\necho "{{}}"\n', encoding="utf-8")
    fake.chmod(0o755)
    env = {
        **os.environ,
        "SKIPWATCH_HOME": str(tmp_path / "home"),
        "PATH": os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")]),
    }
    for args in (
        ["doctor", "--json"],
        ["ingest", "http://127.0.0.1:9/nothing", "--work", str(tmp_path / "w"), "--json"],
    ):
        subprocess.run(
            [_engine(), *args],
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=120,
            check=False,
        )
    assert not log.exists(), log.read_text(encoding="utf-8")
