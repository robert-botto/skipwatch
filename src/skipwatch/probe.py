"""probe: metadata only, before ingest, so the orchestrator can warn about long videos
(plan issue 4, 3.4 and 15). Writes nothing; errors map like ingest (exit 2, 3, 4, 7)."""

import importlib.util
import os
from pathlib import Path

from skipwatch import media
from skipwatch.adapters.base import DownloadFailed, IngestOptions, NoMediaError
from skipwatch.adapters.localfile import find_sidecar
from skipwatch.adapters.registry import adapter_for
from skipwatch.adapters.ytdlp_common import author_of, choose_caption_track, fetch_info, has_video
from skipwatch.detect import Detected, detect
from skipwatch.doctor import CLOUD_KEYS
from skipwatch.errors import VIDEO_ONLY, ExitCode, SkipwatchError
from skipwatch.models import ProbeResult

LONG_VIDEO_S = 3600
BASE_RUN_S = 30
# Seconds of work per second of media, by transcription route.
FACTOR_CAPTIONS = 0.05
FACTOR_MLX = 0.25
FACTOR_FASTER = 0.6
FACTOR_CLOUD = 0.1


def _installed(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _factor(captions: bool) -> float | None:
    if captions:
        return FACTOR_CAPTIONS
    if _installed("mlx_whisper"):
        return FACTOR_MLX
    if _installed("faster_whisper"):
        return FACTOR_FASTER
    if any(os.environ.get(key) for key in CLOUD_KEYS):
        return FACTOR_CLOUD
    return None


def _result(value: str, duration: float | None, captions: bool, **fields) -> ProbeResult:
    factor = _factor(captions)
    estimate = round(BASE_RUN_S + duration * factor) if duration and factor else None
    return ProbeResult(
        value=value,
        duration_s=duration,
        captions_available=captions,
        long_video=bool(duration and duration > LONG_VIDEO_S),
        estimated_run_s=estimate,
        **fields,
    )


def _probe_local(value: str, detected: Detected) -> ProbeResult:
    path = Path(detected.value)
    probed = media.probe(path)
    streams = probed.get("streams", [])
    if not streams:
        raise SkipwatchError(ExitCode.NO_CONTENT, f"no audio or video stream in {path.name}")
    picture = any(
        s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
        for s in streams
    )
    duration = probed.get("format", {}).get("duration")
    return _result(
        value,
        float(duration) if duration else None,
        find_sidecar(path) is not None,
        kind="file" if picture else "audio",
        platform="local",
        title=path.stem,
    )


def probe(value: str, opts: IngestOptions) -> ProbeResult:
    detected = detect(value)
    if detected.platform == "local":
        return _probe_local(value, detected)
    if adapter_for(detected.platform) is None:
        raise SkipwatchError(ExitCode.UNSUPPORTED_SOURCE, f"no adapter for {detected.platform}")
    try:
        info, _ = fetch_info(detected, opts, detected.platform)
    except NoMediaError as exc:
        raise SkipwatchError(ExitCode.NO_CONTENT, VIDEO_ONLY) from exc
    except DownloadFailed as exc:
        raise SkipwatchError(
            ExitCode.DOWNLOAD_FAILED, f"could not read {value}: {'; '.join(exc.attempts)}"
        ) from exc
    return _result(
        value,
        info.get("duration"),
        choose_caption_track(info) is not None,
        kind="video" if has_video(info) else "audio",
        platform=detected.platform,
        title=info.get("title"),
        author=author_of(info, detected.platform),
    )
