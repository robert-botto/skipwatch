"""Synthetic media for frame tests: lavfi sources and Pillow stills, no drawtext."""

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

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


CODE_LINE = "result = compute_total(items, tax=0.0825)"  # 41 chars, about one editor line


def editor_frame(
    lines: int, extra_chars: int = 0, size=(1280, 720), cursor: bool = False
) -> Image.Image:
    """A dark code editor showing `lines` full lines, then `extra_chars` of the next one.

    `cursor` draws a 12x26 block where the next character would go.
    """
    img = Image.new("RGB", size, (30, 30, 36))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=26)
    draw.rectangle((0, 0, size[0], 36), fill=(50, 50, 60))  # title bar
    for k in range(lines + 1):
        text = CODE_LINE if k < lines else CODE_LINE[:extra_chars]
        draw.text((40, 60 + k * 44), text, fill=(220, 220, 220), font=font)
    if cursor:
        x = 40 + draw.textlength(CODE_LINE[:extra_chars], font=font)
        y = 60 + lines * 44
        draw.rectangle((x, y, x + 12, y + 26), fill=(220, 220, 220))
    return img


def _stills_to_video(stills: list[Image.Image], path: Path) -> Path:
    """One still per second, encoded at 10 fps."""
    folder = path.parent / f"{path.stem}-stills"
    folder.mkdir()
    for n, still in enumerate(stills):
        still.save(folder / f"img-{n:04d}.png")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-nostdin", "-framerate", "1", "-i", "img-%04d.png",
         "-r", "10", "-pix_fmt", "yuv420p", str(path.resolve())],
        check=True, cwd=folder,
    )  # fmt: skip
    return path


def make_blinking_cursor_video(path: Path) -> Path:
    """20 s: empty editor 0-2 s; a prompt line from 2 s and a second line from 12 s, with a
    cursor block toggling every second, so mpdecimate keeps every 1 s frame."""
    stills = []
    for second in range(20):
        lines = 0 if second < 2 else 1 if second < 12 else 2
        stills.append(editor_frame(lines, cursor=lines > 0 and second % 2 == 1))
    return _stills_to_video(stills, path)


def make_typed_code_video(path: Path, lines: int = 10, seconds_per_line: int = 2) -> Path:
    """A new 40-char line appears every `seconds_per_line` s; Pillow frames joined by ffmpeg."""
    stills = [editor_frame(k + 1) for k in range(lines) for _ in range(seconds_per_line)]
    return _stills_to_video(stills, path)
