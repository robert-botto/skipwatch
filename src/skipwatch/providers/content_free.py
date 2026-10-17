"""The free route: the only module that imports yt_dlp (R-ARCH-1).

A library the adapters call, not a content provider: providers/registry skips it.
yt-dlp errors leave this module as FreeRouteError, so adapters never import yt_dlp.

- js_runtime (R-ING-5, plan issue 2): yt-dlp enables deno when js_runtimes is absent, so one
  runtime is always passed explicitly: node 22+, else deno 2.3+, else none ({}).
- remote_components is never set, so no challenge script is fetched at run time.
- Cookies only from the explicit --cookies-from-browser flag (R-ING-5).
- select_format (R-ING-4, plan issue 3): "720p" means the short side, so vertical video works.
- A caption track that turns out to be an HLS playlist (X lists WebVTT that way) is resolved
  here: its segments come through links.get_vetted (public addresses only, pinned, no cookies,
  a generic User-Agent), within a size cap and a deadline, and are merged by captions_hls.
"""

import math
import re
import shutil
import subprocess
import time
from collections import OrderedDict
from collections.abc import Callable
from http.cookiejar import Cookie
from pathlib import Path
from typing import Any, Literal, TypeVar

import requests
import urllib3.exceptions
import yt_dlp
from yt_dlp.utils import DownloadError

from skipwatch import captions_hls, media
from skipwatch.adapters.base import IngestOptions
from skipwatch.adapters.localfile import media_info
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import MediaInfo, ProviderCall
from skipwatch.output import progress
from skipwatch.providers import links
from skipwatch.workdir import WorkDir, write_bytes_atomic

NODE_MIN = (22, 0, 0)  # yt-dlp's own minimum for node
DENO_MIN = (2, 3, 0)  # and for deno
MIN_SHORT_SIDE = 720
CAPTION_EXTS = ("json3", "vtt", "srt")  # the formats skipwatch.captions parses, best first
SOCKET_TIMEOUT_S = 30
MAX_CAPTION_BYTES = 10_000_000  # every segment of one HLS caption playlist together
CAPTION_SEGMENTS_DEADLINE_S = 120.0

CaptionKind = Literal["manual", "auto"]
T = TypeVar("T")

RETRY_DELAY_S = 2.0
# Failures YouTube's CDN produces intermittently and an immediate retry clears (1 in 5 G1 runs).
_TRANSIENT = (
    (re.compile(r"HTTP Error 403"), "403"),
    (re.compile(r"HTTP Error 429"), "429"),
    (re.compile(r"connection reset|ConnectionResetError", re.IGNORECASE), "connection reset"),
)

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


def transient_label(exc: FreeRouteError) -> str | None:
    """ "403", "429" or "connection reset" for a retryable failure. Login, private and bot-check
    errors classify as PRIVATE_CONTENT and are never retried."""
    if exc.code != ExitCode.DOWNLOAD_FAILED:
        return None
    return next((label for pattern, label in _TRANSIENT if pattern.search(exc.message)), None)


def _retry_once(op: str, attempt: Callable[[], T], failed: list[ProviderCall] | None) -> T:
    """Run attempt; after one transient failure, log it to failed, pause, and run it again."""
    started = time.monotonic()
    try:
        return attempt()
    except FreeRouteError as exc:
        label = transient_label(exc)
        if label is None:
            raise
        if failed is not None:
            failed.append(call_log(f"yt-dlp.{op}", False, started, exc.first_line))
        progress(f"retrying after a transient {label}")
        time.sleep(RETRY_DELAY_S)
        return attempt()


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


def _rank(fmt: dict[str, Any], duration: float | None) -> tuple[float, float, int, str]:
    """Smaller is cheaper. Without a duration or sizes (Instagram) every _size is inf, so the
    bitrate decides (renditions share one duration), then the short side, then format_id
    (identical mirrors, as on TikTok); never list order."""
    tbr = fmt.get("tbr")
    size = _size(fmt, duration)
    return size, float(tbr) if tbr else math.inf, _short_side(fmt) or 0, str(fmt["format_id"])


def _usable(fmt: dict[str, Any]) -> bool:
    return not fmt.get("has_drm") and fmt.get("format_id") is not None


def _pick_video(videos: list[dict[str, Any]], cap: int, duration: float | None) -> dict[str, Any]:
    low = min(MIN_SHORT_SIDE, cap)
    window = [f for f in videos if low <= (_short_side(f) or 0) <= cap]
    if window:
        return min(window, key=lambda f: _rank(f, duration))
    below = [f for f in videos if (_short_side(f) or 0) < low]
    if below:
        return min(below, key=lambda f: (-(_short_side(f) or 0), *_rank(f, duration)))
    return min(videos, key=lambda f: (_short_side(f) or 0, *_rank(f, duration)))


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
    return min(original or audios, key=lambda f: _rank(f, duration))


def select_format(info: dict[str, Any], max_short_side: int = 1080) -> str:
    """A yt-dlp format spec: the smallest rendition whose short side is in [720, cap]."""
    duration = info.get("duration")
    formats = [f for f in info.get("formats") or [] if _usable(f)]
    videos = [f for f in formats if not _is_none(f.get("vcodec")) and _short_side(f)]
    # vcodec "none" marks audio-only; X leaves acodec out entirely, which still means audio.
    audios = [f for f in formats if _is_none(f.get("vcodec")) and not _is_none(f.get("acodec"))]
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

# Session continuity, for every platform (not only X): some sites hand the extract step
# session cookies (X: guest_id and friends from its guest-token flow) and refuse the media
# without them, so a fresh YoutubeDL for the download gets 404. The extract step's cookies are
# kept here, in memory only, keyed by the page URL, and copied into every download's jar.
# Without --cookies-from-browser they are only the site's own guest session. With it, the jar
# also holds the user's browser cookies for that site, which the download's YoutubeDL would
# load from the browser anyway. Either way they stay in memory: never written anywhere, and
# fetched_with_cookies follows the flag.
MAX_SESSIONS = 8
_SESSIONS: OrderedDict[str, list[Cookie]] = OrderedDict()


def _session_key(info: dict[str, Any]) -> str | None:
    return info.get("webpage_url") or info.get("original_url")


def _keep_session(info: dict[str, Any], ydl: Any) -> None:
    key = _session_key(info)
    jar = getattr(ydl, "cookiejar", None)
    if key is None or jar is None:
        return
    _SESSIONS[key] = list(jar)
    _SESSIONS.move_to_end(key)
    while len(_SESSIONS) > MAX_SESSIONS:
        _SESSIONS.popitem(last=False)


def _resume_session(info: dict[str, Any], ydl: Any) -> None:
    key = _session_key(info)
    for cookie in _SESSIONS.get(key, []) if key else []:
        ydl.cookiejar.set_cookie(cookie)


def extract(url: str, opts: IngestOptions) -> dict[str, Any]:
    """Metadata only, sanitized to plain JSON types. Never downloads."""
    try:
        with yt_dlp.YoutubeDL(ydl_params(None, opts, download=False)) as ydl:  # pyright: ignore[reportArgumentType]
            info = ydl.extract_info(url, download=False)
            info = ydl.sanitize_info(info)
            _keep_session(info, ydl)  # pyright: ignore[reportArgumentType]
            return info  # pyright: ignore[reportReturnType]
    except DownloadError as exc:
        raise FreeRouteError("metadata", str(exc)) from exc


def has_video(info: dict[str, Any]) -> bool:
    """False only when every format says it has no video codec (an audio source)."""
    formats = info.get("formats") or []
    return not formats or any(f.get("vcodec") != "none" for f in formats)


def _has_audio(info: dict[str, Any]) -> bool:
    """True when some format names an audio codec, or is audio-only (vcodec "none", as X's
    HLS audio with no acodec field). A video format that merely leaves acodec out says
    nothing, so a silent source is not mistaken for one with sound."""
    return any(
        f.get("acodec") not in (None, "none")
        or (_is_none(f.get("vcodec")) and f.get("acodec") is None)
        for f in info.get("formats") or []
    )


def _existing_download(work: WorkDir, info: dict[str, Any]) -> MediaInfo | None:
    """R-CLI-1: a finished download whose length matches is not fetched again.

    Only the final file counts: `video.<ext>`, never yt-dlp's per-format intermediates
    (`video.f398.mp4`, `video.f251.webm`) or partial files, and it must carry a picture when
    the source has video. Without a duration to compare (Instagram), the file must instead carry
    audio whenever the source has audio, so a half-merged video-only file is fetched again.
    """
    duration = info.get("duration")
    needs_audio = not duration and _has_audio(info)
    for path in sorted((work.path / "media").glob("video.*")):
        if path.name.count(".") != 1 or path.suffix in (".part", ".ytdl") or not path.is_file():
            continue
        probed = media.probe(path)
        length = float(probed.get("format", {}).get("duration") or 0)
        if duration and abs(length - float(duration)) > 1:
            continue
        try:
            found = media_info(path, probed)
        except SkipwatchError:
            continue
        if (has_video(info) and found.width is None) or (needs_audio and not found.has_audio):
            continue
        return found.model_copy(update={"path": f"media/{path.name}"})
    return None


def download(
    info: dict[str, Any],
    work: WorkDir,
    opts: IngestOptions,
    failed: list[ProviderCall] | None = None,
) -> MediaInfo:
    """Download the chosen format. A transient failure is retried once and logged to failed;
    the caller logs the final attempt."""
    existing = _existing_download(work, info)
    if existing is not None:
        return existing
    spec = select_format(info, opts.max_height)
    params = ydl_params(work.path, opts, download=True) | {"format": spec}

    def attempt() -> dict[str, Any]:
        try:
            with yt_dlp.YoutubeDL(params) as ydl:  # pyright: ignore[reportArgumentType]
                _resume_session(info, ydl)
                return ydl.process_ie_result(dict(info), download=True)  # pyright: ignore[reportArgumentType, reportReturnType]
        except DownloadError as exc:
            raise FreeRouteError("download", str(exc)) from exc

    result = _retry_once("download", attempt, failed)
    downloads = (result or {}).get("requested_downloads") or []
    if not downloads or not downloads[0].get("filepath"):
        raise FreeRouteError("download", "yt-dlp reported no downloaded file")
    path = Path(downloads[0]["filepath"])
    probed = media.probe(path)
    return media_info(path, probed).model_copy(update={"path": f"media/{path.name}"})


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_") or "captions"


def _caption_error(message: str) -> FreeRouteError:
    return FreeRouteError("captions", f"caption playlist: {message}")


def _read_vetted(
    url: str, deadline: float, room: int, error: Callable[[str], FreeRouteError], status: str
) -> tuple[bytes, str]:
    """(body, URL of the last hop) through the vetted transport: every redirect hop checked
    and pinned to its vetted address, at most `room` bytes, never past deadline."""
    try:
        response = links.get_vetted(url, deadline)
    except links.Refused as exc:
        raise error(str(exc)) from exc
    except requests.RequestException as exc:
        raise error(type(exc).__name__) from exc
    try:
        if response.status_code != 200:
            raise error(status.format(code=response.status_code))
        body = bytearray()
        while True:
            if time.monotonic() >= deadline:
                raise error(f"over the {CAPTION_SEGMENTS_DEADLINE_S:g} s deadline")
            chunk = response.raw.read1(links.CHUNK, decode_content=True)
            if not chunk:
                return bytes(body), str(getattr(response, "url", None) or url)
            body.extend(chunk)
            if len(body) > room:
                raise error(f"over the {MAX_CAPTION_BYTES:,} byte cap")
    except (requests.RequestException, urllib3.exceptions.HTTPError) as exc:
        # read1 raises urllib3's own errors (a short body, a read timeout, bad gzip)
        raise error(type(exc).__name__) from exc
    finally:
        links.close_vetted(response)


def _read_segment(url: str, deadline: float, room: int) -> bytes:
    """One segment of an HLS caption playlist."""
    return _read_vetted(url, deadline, room, _caption_error, "HTTP {code} for a segment")[0]


def _track_error(message: str) -> FreeRouteError:
    return FreeRouteError("captions", f"caption track: {message}")


def fetch_track(url: str) -> tuple[bytes, str]:
    """(body, final URL) of one caption track. The URL comes from the page yt-dlp read (on a
    generic site, a page-controlled <track src>), so it goes through the vetted transport
    like any link (R-ING-1): no localhost, LAN or metadata host on any redirect hop, and no
    second DNS answer."""
    deadline = time.monotonic() + CAPTION_SEGMENTS_DEADLINE_S
    # "HTTP Error 403" and "429" read as transient, so _retry_once tries them once more
    return _read_vetted(url, deadline, MAX_CAPTION_BYTES, _track_error, "HTTP Error {code}")


def _resolve_playlist(playlist: bytes, playlist_url: str) -> bytes:
    """The WebVTT text an HLS caption playlist stands for (segments merged)."""
    try:
        urls = captions_hls.segment_urls(playlist.decode("utf-8", "replace"), playlist_url)
    except captions_hls.HlsError as exc:
        raise _caption_error(str(exc)) from exc
    deadline = time.monotonic() + CAPTION_SEGMENTS_DEADLINE_S
    segments: list[str] = []
    total = 0
    for url in urls:
        body = _read_segment(url, deadline, MAX_CAPTION_BYTES - total)
        total += len(body)
        segments.append(body.decode("utf-8-sig", "replace"))
    try:
        return captions_hls.merge_webvtt(segments).encode("utf-8")
    except Exception as exc:  # hostile segment text: a caption failure never ends ingest
        raise _caption_error(f"could not merge the segments ({type(exc).__name__})") from exc


def download_captions(
    info: dict[str, Any],
    work: WorkDir,
    opts: IngestOptions,
    track: tuple[str, CaptionKind],
    failed: list[ProviderCall] | None = None,
) -> tuple[str, str, CaptionKind] | None:
    """Fetch one caption track (json3, else vtt, else srt) into captions/. None when the track
    has no format SkipWatch parses. A transient failure is retried once and logged to failed.
    An HLS playlist in place of the file (X) is resolved into one WebVTT file."""
    lang, kind = track
    tracks = info.get("subtitles" if kind == "manual" else "automatic_captions") or {}
    entries = [e for e in tracks.get(lang) or [] if e.get("url")]
    by_ext = {e.get("ext"): e for e in entries}
    ext = next((x for x in CAPTION_EXTS if x in by_ext), None)
    if ext is None:
        return None
    entry = by_ext[ext]
    body, fetched_from = _retry_once("captions", lambda: fetch_track(str(entry["url"])), failed)
    if captions_hls.is_playlist(body):
        body, ext = _resolve_playlist(body, fetched_from), "vtt"
    folder = work.path / "captions"
    # the language code comes from the platform: sanitised like the id, never a path
    name = f"{_safe_name(str(info.get('id') or 'captions'))}.{_safe_name(lang)}.{ext}"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(folder / name, body)  # a planted symlink is replaced, never followed
    except OSError as exc:  # a folder planted at the file's path, or a file at the folder's
        message = f"could not write captions/{name}: {exc.strerror or type(exc).__name__}"
        raise FreeRouteError("captions", message) from exc
    return f"captions/{name}", lang, kind
