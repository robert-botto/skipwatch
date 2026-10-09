"""Locate ffmpeg and ffprobe, and thin wrappers around them.

A system ffmpeg on PATH is preferred. Otherwise the static-ffmpeg package supplies one, but its
wheel carries no binary: the first `get_or_fetch_platform_executables_else_raise()` downloads
about 70 MB from GitHub. That one-time dependency bootstrap is the only network access allowed
outside providers/ (plan issue 8, R-ARCH-1). It runs only from stage commands (ingest, frames)
through `ffmpeg_paths(allow_fetch=True)`, never from doctor (R-DOC-1).
"""

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from skipwatch.errors import ExitCode, SkipwatchError

_EXE = ".exe" if sys.platform == "win32" else ""
_VERSION_RE = re.compile(r"ffmpeg version (\S+)")


def find_system_ffmpeg() -> tuple[Path, Path] | None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg and ffprobe:
        return Path(ffmpeg), Path(ffprobe)
    return None


def _static_bin_dir() -> Path:
    spec = importlib.util.find_spec("static_ffmpeg")
    if spec is None or spec.origin is None:
        return Path("/nonexistent-static-ffmpeg")
    return Path(spec.origin).parent / "bin"


def _static_paths_on_disk() -> tuple[Path, Path] | None:
    d = _static_bin_dir()
    if not d.exists():
        return None
    for ffmpeg in d.rglob(f"ffmpeg{_EXE}"):
        ffprobe = ffmpeg.with_name(f"ffprobe{_EXE}")
        if ffprobe.exists():
            return ffmpeg, ffprobe
    return None


def static_ffmpeg_fetched() -> bool:
    """True when the static binaries are already on disk. Never downloads."""
    d = _static_bin_dir()
    return any(p.is_file() for p in d.rglob(f"ffmpeg{_EXE}")) if d.exists() else False


def _fetch_static() -> tuple[Path, Path]:
    # One-time dependency bootstrap: downloads about 70 MB (plan issue 8). Never called by doctor.
    from static_ffmpeg import run

    ffmpeg, ffprobe = run.get_or_fetch_platform_executables_else_raise()
    return Path(ffmpeg), Path(ffprobe)


def ffmpeg_paths(allow_fetch: bool = True) -> tuple[Path, Path]:
    system = find_system_ffmpeg()
    if system:
        return system
    if static_ffmpeg_fetched():
        on_disk = _static_paths_on_disk()
        if on_disk:
            return on_disk
    if allow_fetch:
        return _fetch_static()
    raise SkipwatchError(
        ExitCode.MISSING_DEPENDENCY,
        'ffmpeg not found; run: uv sync --project "<plugin root>" (or install ffmpeg on PATH)',
    )


def parse_ffmpeg_version(first_line: str) -> str | None:
    match = _VERSION_RE.search(first_line)
    return match.group(1) if match else None


def ffmpeg_version(ffmpeg: Path) -> str | None:
    try:
        out = subprocess.run(
            [str(ffmpeg), "-version"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = out.stdout.splitlines()
    return parse_ffmpeg_version(lines[0]) if lines else None


def probe(path: Path) -> dict[str, Any]:
    _, ffprobe = ffmpeg_paths()
    out = subprocess.run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        raise SkipwatchError(ExitCode.UNSUPPORTED_SOURCE, f"ffprobe could not read {path}")
    return json.loads(out.stdout)


def has_filter(ffmpeg: Path, name: str) -> bool:
    out = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-filters"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return any(line.split()[1:2] == [name] for line in out.stdout.splitlines())
