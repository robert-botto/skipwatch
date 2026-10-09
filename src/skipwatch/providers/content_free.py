"""The free route: the only module that imports yt_dlp (R-ARCH-1).

A library the adapters call, not a content provider: providers/registry skips it.
yt-dlp errors leave this module as FreeRouteError, so adapters never import yt_dlp.

- js_runtime (R-ING-5, plan issue 2): yt-dlp enables deno when js_runtimes is absent, so one
  runtime is always passed explicitly: node 22+, else deno 2.3+, else none ({}).
- remote_components is never set, so no challenge script is fetched at run time.
- Cookies only from the explicit --cookies-from-browser flag (R-ING-5).
- select_format (R-ING-4, plan issue 3): "720p" means the short side, so vertical video works.
"""

import math
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Literal

import yt_dlp
from yt_dlp.networking import Request
from yt_dlp.networking.exceptions import RequestError
from yt_dlp.utils import DownloadError

from skipwatch import media
from skipwatch.adapters.base import IngestOptions
from skipwatch.adapters.localfile import media_info
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import MediaInfo, ProviderCall
from skipwatch.workdir import WorkDir

NODE_MIN = (22, 0, 0)  # yt-dlp's own minimum for node
DENO_MIN = (2, 3, 0)  # and for deno
MIN_SHORT_SIDE = 720
CAPTION_EXTS = ("json3", "vtt", "srt")  # the formats skipwatch.captions parses, best first
SOCKET_TIMEOUT_S = 30

CaptionKind = Literal["manual", "auto"]

_VERSION_RE = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")
_PRIVATE_MARKERS = (
    "private video",
    "this video is private",
    "protected tweet",
    "requires authentication",
    "log in to access",
    "login required",
)
_NO_CONTENT_MARKERS = ("no video could be found", "there's no video in this")


class FreeRouteError(Exception):
    """A yt-dlp failure, classified (R-ING-6). first_line drops yt-dlp's `ERROR: ` prefix."""

    def __init__(self, op: str, message: str):
        super().__init__(message)
        self.op = op
        self.message = message
        self.code = classify_error(message)
        lines = message.strip().splitlines() or [""]
        self.first_line = lines[0].removeprefix("ERROR: ").strip()


class _Quiet:
    """yt-dlp logger that prints nothing: errors still arrive as DownloadError."""

    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        pass

    def error(self, msg: str) -> None:
        pass


def _version_of(path: str) -> str | None:
    try:
        out = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() or None


def _at_least(version: str | None, minimum: tuple[int, int, int]) -> bool:
    match = _VERSION_RE.search(version or "")
    if match is None:
        return False
    parts = tuple(int(g or 0) for g in match.groups())
    return parts >= minimum


def js_runtime() -> dict[str, dict[str, str]]:
    node = shutil.which("node")
    if node and _at_least(_version_of(node), NODE_MIN):
        return {"node": {"path": node}}
    deno = shutil.which("deno")
    if deno and _at_least(_version_of(deno), DENO_MIN):
        return {"deno": {"path": deno}}
    return {}


def ydl_params(work: Path | None, opts: IngestOptions, *, download: bool) -> dict[str, Any]:
    params: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": SOCKET_TIMEOUT_S,
        "retries": 3,
        "js_runtimes": js_runtime(),
        "logger": _Quiet(),
    }
    if opts.cookies_from_browser:
        params["cookiesfrombrowser"] = (opts.cookies_from_browser,)
    if download:
        assert work is not None, "a download needs a work folder"
        params.update(
            paths={"home": str(work / "media")},
            outtmpl="video.%(ext)s",
            merge_output_format="mp4",
            ffmpeg_location=str(media.ffmpeg_paths()[0].parent),
            overwrites=True,
        )
    else:
        params["skip_download"] = True
        params["extract_flat"] = "in_playlist"  # a playlist or channel URL lists, never resolves
    return params


def classify_error(message: str) -> ExitCode:
    folded = message.casefold()
    if "--cookies" in folded or any(m in folded for m in _PRIVATE_MARKERS):
        return ExitCode.PRIVATE_CONTENT
    if any(m in folded for m in _NO_CONTENT_MARKERS):
        return ExitCode.NO_CONTENT
    return ExitCode.DOWNLOAD_FAILED


def call_log(op: str, ok: bool, started: float, error: str | None = None) -> ProviderCall:
    ms = max(0, int((time.monotonic() - started) * 1000))
    return ProviderCall(provider="free", op=op, ok=ok, cost_usd=0, ms=ms, error=error)


# ---- format choice (R-ING-4) ----


def _is_none(codec: Any) -> bool:
    return codec == "none"


def _short_side(fmt: dict[str, Any]) -> int | None:
    sides = [s for s in (fmt.get("width"), fmt.get("height")) if isinstance(s, int | float)]
    return int(min(sides)) if sides else None


def _size(fmt: dict[str, Any], duration: float | None) -> float:
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    if size:
        return float(size)
    tbr = fmt.get("tbr")
    if tbr and duration:
        return float(tbr) * 1000 / 8 * float(duration)
    return math.inf


def _usable(fmt: dict[str, Any]) -> bool:
    return not fmt.get("has_drm") and fmt.get("format_id") is not None


def _pick_video(videos: list[dict[str, Any]], cap: int, duration: float | None) -> dict[str, Any]:
    low = min(MIN_SHORT_SIDE, cap)
    window = [f for f in videos if low <= (_short_side(f) or 0) <= cap]
    if window:
        return min(window, key=lambda f: _size(f, duration))
    below = [f for f in videos if (_short_side(f) or 0) < low]
    if below:
        return max(below, key=lambda f: (_short_side(f) or 0, -_size(f, duration)))
    return min(videos, key=lambda f: (_short_side(f) or 0, _size(f, duration)))


def _primary_lang(value: Any) -> str | None:
    return str(value).split("-")[0].casefold() if value else None


def _pick_audio(
    audios: list[dict[str, Any]], language: str | None, duration: float | None
) -> dict[str, Any] | None:
    """The smallest audio in the video's own language (or marked original), so a multi-audio
    video never gets a dubbed track; the smallest of all when nothing says which is original."""
    if not audios:
        return None
    lang = _primary_lang(language)
    original = [
        f
        for f in audios
        if (lang and _primary_lang(f.get("language")) == lang)
        or "original" in str(f.get("format_note") or "").casefold()
    ]
    return min(original or audios, key=lambda f: _size(f, duration))


def select_format(info: dict[str, Any], max_short_side: int = 1080) -> str:
    """A yt-dlp format spec: the smallest rendition whose short side is in [720, cap]."""
    duration = info.get("duration")
    formats = [f for f in info.get("formats") or [] if _usable(f)]
    videos = [f for f in formats if not _is_none(f.get("vcodec")) and _short_side(f)]
    audios = [f for f in formats if _is_none(f.get("vcodec")) and not _is_none(f.get("acodec"))]
    audios = [f for f in audios if f.get("acodec") is not None]
    best_audio = _pick_audio(audios, info.get("language"), duration)
    if videos:
        video = _pick_video(videos, max_short_side, duration)
        progressive = not _is_none(video.get("acodec")) and video.get("acodec") is not None
        if progressive or best_audio is None:
            return str(video["format_id"])
        return f"{video['format_id']}+{best_audio['format_id']}"
    if best_audio is not None:
        return str(best_audio["format_id"])
    # Generic direct links often carry no codec or size fields; let yt-dlp choose.
    if any(not _is_none(f.get("vcodec")) and not _is_none(f.get("acodec")) for f in formats):
        return "best"
    raise SkipwatchError(ExitCode.NO_CONTENT, "the source lists no video or audio formats")


# ---- yt-dlp calls ----


def extract(url: str, opts: IngestOptions) -> dict[str, Any]:
    """Metadata only, sanitized to plain JSON types. Never downloads."""
    try:
        with yt_dlp.YoutubeDL(ydl_params(None, opts, download=False)) as ydl:  # pyright: ignore[reportArgumentType]
            info = ydl.extract_info(url, download=False)
            return ydl.sanitize_info(info)  # pyright: ignore[reportReturnType]
    except DownloadError as exc:
        raise FreeRouteError("metadata", str(exc)) from exc


def has_video(info: dict[str, Any]) -> bool:
    """False only when every format says it has no video codec (an audio source)."""
    formats = info.get("formats") or []
    return not formats or any(f.get("vcodec") != "none" for f in formats)


def _existing_download(work: WorkDir, info: dict[str, Any]) -> MediaInfo | None:
    """R-CLI-1: a finished download whose length matches is not fetched again.

    Only the final file counts: `video.<ext>`, never yt-dlp's per-format intermediates
    (`video.f398.mp4`, `video.f251.webm`) or partial files, and it must carry a picture when
    the source has video.
    """
    duration = info.get("duration")
    if not duration:
        return None
    for path in sorted((work.path / "media").glob("video.*")):
        if path.name.count(".") != 1 or path.suffix in (".part", ".ytdl") or not path.is_file():
            continue
        probed = media.probe(path)
        length = float(probed.get("format", {}).get("duration") or 0)
        if abs(length - float(duration)) > 1:
            continue
        try:
            found = media_info(path, probed)
        except SkipwatchError:
            continue
        if has_video(info) and found.width is None:
            continue
        return found.model_copy(update={"path": f"media/{path.name}"})
    return None


def download(info: dict[str, Any], work: WorkDir, opts: IngestOptions) -> MediaInfo:
    existing = _existing_download(work, info)
    if existing is not None:
        return existing
    spec = select_format(info, opts.max_height)
    params = ydl_params(work.path, opts, download=True) | {"format": spec}
    try:
        with yt_dlp.YoutubeDL(params) as ydl:  # pyright: ignore[reportArgumentType]
            result = ydl.process_ie_result(dict(info), download=True)  # pyright: ignore[reportArgumentType]
    except DownloadError as exc:
        raise FreeRouteError("download", str(exc)) from exc
    downloads = (result or {}).get("requested_downloads") or []
    if not downloads or not downloads[0].get("filepath"):
        raise FreeRouteError("download", "yt-dlp reported no downloaded file")
    path = Path(downloads[0]["filepath"])
    probed = media.probe(path)
    return media_info(path, probed).model_copy(update={"path": f"media/{path.name}"})


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_") or "captions"


def download_captions(
    info: dict[str, Any], work: WorkDir, opts: IngestOptions, track: tuple[str, CaptionKind]
) -> tuple[str, str, CaptionKind] | None:
    """Fetch one caption track (json3, else vtt, else srt) into captions/. None when the track
    has no format SkipWatch parses."""
    lang, kind = track
    tracks = info.get("subtitles" if kind == "manual" else "automatic_captions") or {}
    entries = [e for e in tracks.get(lang) or [] if e.get("url")]
    by_ext = {e.get("ext"): e for e in entries}
    ext = next((x for x in CAPTION_EXTS if x in by_ext), None)
    if ext is None:
        return None
    entry = by_ext[ext]
    try:
        with yt_dlp.YoutubeDL(ydl_params(None, opts, download=False)) as ydl:  # pyright: ignore[reportArgumentType]
            request = Request(entry["url"], headers=entry.get("http_headers"))
            body = ydl.urlopen(request).read()  # pyright: ignore[reportArgumentType]
    except (DownloadError, RequestError) as exc:
        raise FreeRouteError("captions", str(exc)) from exc
    folder = work.path / "captions"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{_safe_name(str(info.get('id') or 'captions'))}.{lang}.{ext}"
    (folder / name).write_bytes(body)
    return f"captions/{name}", lang, kind
