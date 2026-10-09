"""Local media files: ffprobe metadata plus an optional captions sidecar (8.3, plan issue 4).

The user's original is never copied, moved or deleted: media.path points at it.
"""

import shutil
from pathlib import Path
from typing import Any

from skipwatch import media
from skipwatch.adapters.base import IngestOptions
from skipwatch.captions import language_from_name
from skipwatch.detect import Detected
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import IngestBundle, IngestContext, MediaInfo, Route, SourceInfo
from skipwatch.workdir import WorkDir

CAPTION_EXTENSIONS = (".vtt", ".srt")


def _sidecar_rank(candidate: Path, stem: str) -> tuple[int, int, str] | None:
    """Lower sorts first: English `<stem>.<lang>.*`, then `<stem>.*`, then other languages."""
    suffix = candidate.suffix.lower()
    if suffix not in CAPTION_EXTENSIONS or not candidate.is_file():
        return None
    middle = candidate.name[: -len(suffix)]
    if middle == stem:
        tier = 1
    else:
        lang = language_from_name(candidate.name, stem)
        if lang is None:
            return None
        tier = 0 if lang.lower().startswith("en") else 2
    return tier, CAPTION_EXTENSIONS.index(suffix), candidate.name


def find_sidecar(media_path: Path) -> Path | None:
    stem = media_path.stem
    ranked = []
    for candidate in media_path.parent.iterdir():
        rank = _sidecar_rank(candidate, stem)
        if rank is not None:
            ranked.append((rank, candidate))
    return min(ranked)[1] if ranked else None


def _fps(rate: str | None) -> float | None:
    if not rate or "/" not in rate:
        return None
    num, den = rate.split("/", 1)
    try:
        value = float(num) / float(den)
    except (ValueError, ZeroDivisionError):
        return None
    return round(value, 3) if value > 0 else None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _video_stream(probed: dict[str, Any]) -> dict[str, Any] | None:
    # Cover art in audio files is a one-frame "video" stream flagged attached_pic.
    return next(
        (
            s
            for s in probed.get("streams", [])
            if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
        ),
        None,
    )


def media_info(path: Path, probed: dict[str, Any]) -> MediaInfo:
    streams = probed.get("streams", [])
    video = _video_stream(probed)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    if video is None and not has_audio:
        raise SkipwatchError(ExitCode.NO_CONTENT, f"no audio or video stream in {path.name}")
    return MediaInfo(
        path=str(path),
        width=video.get("width") if video else None,
        height=video.get("height") if video else None,
        fps=_fps(video.get("r_frame_rate")) if video else None,
        has_audio=has_audio,
    )


class LocalFileAdapter:
    def build(self, detected: Detected, work: WorkDir, opts: IngestOptions) -> IngestBundle:
        path = Path(detected.value)
        probed = media.probe(path)
        info = media_info(path, probed)
        context = IngestContext()
        sidecar = find_sidecar(path)
        if sidecar is not None:
            captions_dir = work.file("captions")
            captions_dir.mkdir(exist_ok=True)
            shutil.copyfile(sidecar, captions_dir / sidecar.name)
            context = IngestContext(
                captions_available=True, captions_path=f"captions/{sidecar.name}"
            )
        return IngestBundle(
            source=SourceInfo(
                # Spec 7.1: a local file with no picture is an audio source; path stays set.
                kind="file" if _video_stream(probed) is not None else "audio",
                platform="local",
                path=str(path),
                title=path.stem,
                duration_s=_float(probed.get("format", {}).get("duration")),
            ),
            context=context,
            media=info,
            route=Route(context="local", media="local"),
        )
