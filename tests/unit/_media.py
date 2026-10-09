"""Synthetic media for frame tests: system ffmpeg lavfi sources only (no drawtext)."""

import shutil
import subprocess
from pathlib import Path

import pytest

from skipwatch.models import IngestBundle, MediaInfo, Route, SourceInfo
from skipwatch.workdir import WorkDir, write_model

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="system ffmpeg required",
)


def make_video(path: Path, seconds: float, pattern: str = "testsrc2") -> Path:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", f"{pattern}=size=640x360:rate=10:duration={seconds}",
         "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )  # fmt: skip
    return path


def make_held_video(path: Path) -> Path:
    """20 s: testsrc2 0-5 s, the 5 s frame held still until 15 s (held text), testsrc2 15-20 s.

    Built by concatenating three trims of one testsrc2 run; the middle trim is one frame
    cloned for 10 s with tpad. The `select` recipe in the plan was not used.
    """
    graph = (
        "[0:v]split=3[a][b][c];"
        "[a]trim=0:5,setpts=PTS-STARTPTS[a1];"
        "[b]trim=start=5:end=5.1,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=9.9[b1];"
        "[c]trim=15:20,setpts=PTS-STARTPTS[c1];"
        "[a1][b1][c1]concat=n=3:v=1:a=0[v]"
    )
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", "testsrc2=size=640x360:rate=10:duration=20",
         "-filter_complex", graph, "-map", "[v]", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )  # fmt: skip
    return path


def make_local_work(tmp_path: Path, video: Path, duration: float | None = None) -> Path:
    """A work folder whose ingest.json points at `video` (a local file, M1 localfile shape)."""
    w = tmp_path / "work"
    (w / "media").mkdir(parents=True)
    target = w / "media" / video.name
    shutil.copyfile(video, target)
    WorkDir(w).ensure()
    bundle = IngestBundle(
        source=SourceInfo(kind="file", platform="local", path=str(video), duration_s=duration),
        media=MediaInfo(path=f"media/{video.name}", width=640, height=360, fps=10.0),
        route=Route(context="local", media="local"),
    )
    write_model(w / "ingest.json", bundle)
    return w
