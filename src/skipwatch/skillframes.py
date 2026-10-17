"""Copy chosen frames into a skill at 960 wide (spec 3.4, M5-M6 issue 7).

Runs while drafting, before check, so the manifest hashes cover the final bytes and `pack`
never has to change a file. Output is plain RGB JPEG with no EXIF or ICC data, and the same
frame always gives the same bytes (R-CLI-1).
"""

import io
from pathlib import Path

from PIL import Image

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.manifest import read_work_file
from skipwatch.models import FramesFile
from skipwatch.workdir import write_bytes_atomic

SKILL_FRAME_WIDTH = 960
MAX_SKILL_FRAMES = 8  # spec 10: a skill carries at most 8 frames
JPEG_QUALITY = 85


def _scaled(source: Path) -> bytes:
    with Image.open(source) as img:
        rgb = img.convert("RGB")
    if rgb.width > SKILL_FRAME_WIDTH:
        height = max(1, round(rgb.height * SKILL_FRAME_WIDTH / rgb.width))
        rgb = rgb.resize((SKILL_FRAME_WIDTH, height), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    # no exif or icc_profile argument: Pillow writes neither unless asked (test pins this)
    rgb.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def _resolve(path: Path) -> Path | None:
    """path resolved, or None when it cannot be (a NUL byte or other invalid path). NUL is
    checked here: resolve() raises for it on POSIX, but not on Windows from Python 3.13."""
    if "\x00" in str(path):
        return None
    try:
        return path.resolve()
    except ValueError:
        return None


def copy_frames(work: Path, dest: Path, ids: list[str]) -> list[Path]:
    frames_path = work / "frames.json"
    if not frames_path.is_file():
        raise SkipwatchError(ExitCode.NO_CONTENT, f"{frames_path} not found; run frames first")
    by_id = {f.id: f for f in read_work_file(frames_path, FramesFile).frames}
    wanted = list(dict.fromkeys(ids))
    unknown = [i for i in wanted if i not in by_id]
    if unknown:
        raise SkipwatchError(ExitCode.USAGE, f"not in frames.json: {', '.join(unknown)}")
    existing = {p.name for p in dest.glob("*.jpg")} if dest.is_dir() else set()
    total = len(existing | {f"{i}.jpg" for i in wanted})
    if total > MAX_SKILL_FRAMES:
        raise SkipwatchError(
            ExitCode.USAGE,
            f"a skill holds at most {MAX_SKILL_FRAMES} frames; {dest} would hold {total}",
        )
    frames_dir = (work / "frames").resolve()
    resolved = {i: _resolve(work / by_id[i].path) for i in wanted}
    unusable = [i for i, s in resolved.items() if s is None]
    if unusable:
        raise SkipwatchError(
            ExitCode.USAGE, f"frames.json has an unusable path for {', '.join(unusable)}"
        )
    sources = [s for s in resolved.values() if s is not None]
    outside = [i for i, s in zip(wanted, sources, strict=True) if not s.is_relative_to(frames_dir)]
    if outside:
        raise SkipwatchError(
            ExitCode.USAGE, f"frames.json points outside the frames folder for {', '.join(outside)}"
        )
    missing = [str(s) for s in sources if not s.is_file()]
    if missing:
        raise SkipwatchError(ExitCode.NO_CONTENT, f"frame file missing: {', '.join(missing)}")

    encoded = [_scaled(s) for s in sources]  # decode everything before writing anything
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for fid, data in zip(wanted, encoded, strict=True):
        target = dest / f"{fid}.jpg"
        write_bytes_atomic(target, data)
        out.append(target)
    return out
