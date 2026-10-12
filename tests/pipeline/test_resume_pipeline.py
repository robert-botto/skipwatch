"""A run killed mid-frames, then resumed (R-WORK-1, R-CLI-1; plan edge case 3, task M2-H1).

Runs the real `skipwatch` CLI as subprocesses on tests/fixtures/tutorial-60s.mp4 in a temporary
SKIPWATCH_HOME. `frames` is SIGKILLed while its stage is `running`: an ffmpeg wrapper on PATH
runs the real ffmpeg once, leaves a marker and then blocks, so the kill always lands inside the
stage instead of racing a sub-second run. POSIX only (SIGKILL, process groups, a shell
wrapper); the pipeline job runs on ubuntu and macOS.
"""

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from skipwatch.media import ffmpeg_paths, find_system_ffmpeg, static_ffmpeg_fetched
from skipwatch.workdir import STAGE_ORDER

pytestmark = [
    pytest.mark.pipeline,
    pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL and a shell wrapper: POSIX only"),
]

FIX = Path(__file__).resolve().parents[1] / "fixtures"
TIMEOUT_S = 300
KILL_WAIT_S = 60
# Runs the real ffmpeg, then marks that frames is mid-stage and blocks until killed.
WRAPPER = """#!/bin/sh
"{real}" "$@" || exit $?
: > "{marker}"
exec sleep 600
"""


def _engine() -> str:
    found = shutil.which("skipwatch", path=str(Path(sys.executable).parent))
    assert found, f"no skipwatch entry point next to {sys.executable}; run uv sync --dev"
    return found


@pytest.fixture
def home(tmp_path: Path) -> Path:
    if find_system_ffmpeg() is None and not static_ffmpeg_fetched():
        pytest.fail("pipeline tests need ffmpeg and ffprobe on PATH (no static-ffmpeg download)")
    return tmp_path / "swhome"


def _env(home: Path, path: str | None = None) -> dict[str, str]:
    env = {**os.environ, "SKIPWATCH_HOME": str(home)}
    if path is not None:
        env["PATH"] = path
    return env


def sw(home: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [_engine(), *args],
        env=_env(home),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        check=False,
    )
    assert result.returncode == 0, (args, result.returncode, result.stderr)
    return result


def stage(work: Path, name: str) -> str:
    return json.loads((work / "stages.json").read_text(encoding="utf-8"))["stages"][name]["status"]


def resume_json(home: Path, *args: str) -> dict:
    return json.loads(sw(home, "resume", *args, "--json").stdout)


def _run_json(work: Path) -> None:
    """run.json as the orchestrator writes it; resume only offers folders that have one."""
    run = {
        "schema": "skipwatch/run/1",
        "input": "tutorial-60s.mp4",
        "started_at": "2026-10-09T12:00:00Z",
    }
    (work / "run.json").write_text(json.dumps(run), encoding="utf-8")


def ingested(home: Path, work: Path) -> Path:
    sw(home, "ingest", str(FIX / "tutorial-60s.mp4"), "--work", str(work))
    _run_json(work)
    sw(home, "transcribe", "--work", str(work))
    return work


def kill_frames_mid_stage(home: Path, work: Path, tmp_path: Path) -> None:
    ffmpeg, ffprobe = ffmpeg_paths(allow_fetch=False)  # system or already-fetched static
    bin_dir = tmp_path / "wrapped-bin"
    bin_dir.mkdir()
    marker = tmp_path / "ffmpeg-ran"
    wrapper = bin_dir / "ffmpeg"
    wrapper.write_text(WRAPPER.format(real=ffmpeg, marker=marker), encoding="utf-8")
    wrapper.chmod(0o755)
    (bin_dir / "ffprobe").symlink_to(ffprobe)
    path = os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")])

    proc = subprocess.Popen(
        [_engine(), "frames", "--work", str(work)],
        env=_env(home, path),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # its own group, so the kill takes the blocked wrapper too
    )
    try:
        deadline = time.monotonic() + KILL_WAIT_S
        while not marker.exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists(), f"frames never reached ffmpeg (exit {proc.poll()})"
        assert stage(work, "frames") == "running"
    finally:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=30)
    assert proc.returncode == -signal.SIGKILL


def frame_files(work: Path) -> dict[str, str]:
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((work / "frames").iterdir())
    }


def test_resume_after_killed_frames_completes(home: Path, tmp_path: Path):
    work = ingested(home, home / "work" / "tutorial-60s-20261009-120000")
    kill_frames_mid_stage(home, work, tmp_path)
    assert stage(work, "frames") == "running"  # killed, so never marked failed or done
    assert not (work / "frames.json").exists()
    # What a kill during the copy into frames/ leaves behind; the rerun must not keep it.
    (work / "frames" / "f999999.jpg").write_bytes(b"partial")

    resumed = resume_json(home, str(work))
    assert resumed["next_stage"] == "frames"
    assert resumed["completed"] == ["detect", "ingest", "transcribe"]
    assert resumed["media_present"] is True

    sw(home, "frames", "--work", str(work))
    assert stage(work, "frames") == "done"
    assert resume_json(home, str(work))["next_stage"] == "plan"
    sw(home, "plan", "--work", str(work))
    assert stage(work, "plan") == "done"
    assert resume_json(home, str(work))["next_stage"] == "read"  # the orchestrator's stages next

    # Same frames as a run that was never interrupted, and no partial frame survives.
    clean = ingested(home, tmp_path / "uninterrupted")
    sw(home, "frames", "--work", str(clean))
    resumed_frames = json.loads((work / "frames.json").read_text(encoding="utf-8"))
    assert resumed_frames == json.loads((clean / "frames.json").read_text(encoding="utf-8"))
    assert frame_files(work) == frame_files(clean)
    assert sorted(frame_files(work)) == sorted(f"{f['id']}.jpg" for f in resumed_frames["frames"])


def _decoy(work: Path, done_through: str) -> None:
    """A run folder holding only stages.json, every stage up to `done_through` done."""
    work.mkdir(parents=True)
    done = STAGE_ORDER[: STAGE_ORDER.index(done_through) + 1]
    stages = {name: {"status": "done" if name in done else "pending"} for name in STAGE_ORDER}
    payload = {"schema": "skipwatch/stages/1", "stages": stages}
    (work / "stages.json").write_text(json.dumps(payload), encoding="utf-8")
    _run_json(work)


def test_resume_without_folder_picks_newest_incomplete_run(home: Path, tmp_path: Path):
    runs = home / "work"
    killed = ingested(home, runs / "tutorial-60s-20261009-120000")
    kill_frames_mid_stage(home, killed, tmp_path)
    _decoy(runs / "older-20261009-110000", "ingest")  # unfinished, but older
    _decoy(runs / "reviewed-20261009-130000", "review")  # newer, but reviewed already
    _decoy(runs / "finished-20261009-140000", "export")  # newer, but every stage done

    resumed = resume_json(home)
    assert Path(resumed["work"]) == killed
    assert resumed["next_stage"] == "frames"
