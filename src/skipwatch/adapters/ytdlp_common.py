"""Shared by every adapter that goes through yt-dlp (youtube, generic; x, tiktok and others in M3).

content_free does the network work; this module turns its info dict into an IngestBundle and
maps its errors onto the ingest contract (R-ING-6): a login wall exits 4 naming the cookie
flag, a URL with no video raises NoMediaError, anything else raises DownloadFailed.
"""

import time
from datetime import UTC, datetime
from typing import Any, NamedTuple, NoReturn
from urllib.parse import urlsplit

from skipwatch import media
from skipwatch.adapters.base import DownloadFailed, IngestOptions, NoMediaError
from skipwatch.detect import Detected
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import (
    IngestBundle,
    IngestContext,
    MediaInfo,
    ProviderCall,
    Route,
    SourceInfo,
)
from skipwatch.providers import content_free
from skipwatch.providers.content_free import CaptionKind, FreeRouteError, has_video
from skipwatch.workdir import WorkDir

NOT_CAPTIONS = {"live_chat", "rechat"}
PLATFORM_NAMES = {
    "youtube": "YouTube",
    "tiktok": "TikTok",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "x": "X",
}


class AuthorFields(NamedTuple):
    """Which info fields hold a platform's handle and display name (platforms.md)."""

    handle: str
    name: str | None  # None where the handle is already the display name
    at: bool = True  # prefix the handle with "@"; False where it is a page name, not a handle


# The single place a platform names its author fields. Platforms not listed (youtube, generic)
# keep the default: uploader_id as the handle, uploader or channel as the name.
AUTHOR_FIELDS: dict[str, AuthorFields] = {
    "tiktok": AuthorFields("uploader", "channel"),  # uploader_id is numeric
    "instagram": AuthorFields("channel", "uploader"),  # uploader_id is numeric
    "facebook": AuthorFields("uploader", None, at=False),  # the page name, shown once
    "x": AuthorFields("uploader_id", "uploader"),  # never the display name as a handle
}


def _primary(lang: str) -> str:
    return lang.split("-")[0].casefold()


def _first(keys: list[str], match) -> str | None:
    return next((k for k in keys if match(k)), None)


def choose_caption_track(
    info: dict[str, Any], prefer: str = "en"
) -> tuple[str, CaptionKind] | None:
    """Manual first, then the original-language auto track; never a machine translation.

    Manual: a `prefer` language (en, en-US, ...), else the video's language, else the first.
    Auto: `<language>-orig` (or, when the language is unknown, the only `*-orig` track), then
    `prefer` only when the video is in that language (or its
    language is unknown), then the video's own language.
    """
    language = info.get("language")
    manual = [k for k in (info.get("subtitles") or {}) if k not in NOT_CAPTIONS]
    pick = (
        _first(manual, lambda k: _primary(k) == prefer)
        or (language and _first(manual, lambda k: k == language))
        or (language and _first(manual, lambda k: _primary(k) == _primary(language)))
        or (manual[0] if manual else None)
    )
    if pick:
        return pick, "manual"
    auto = list(info.get("automatic_captions") or {})
    candidates = []
    if language:
        candidates += [f"{language}-orig", f"{_primary(language)}-orig"]
    else:
        # Unknown language: a single original track is the spoken language, so it beats an
        # English track that may be a machine translation.
        originals = [k for k in auto if k.endswith("-orig")]
        if len(originals) == 1:
            candidates.append(originals[0])
    if language is None or _primary(language) == prefer:
        candidates += [f"{prefer}-orig", prefer]
    if language:
        candidates += [language, _primary(language)]
    pick = next((c for c in candidates if c in auto), None)
    return (pick, "auto") if pick else None


# ---- bundle building ----


def _site(platform: str, url: str) -> str:
    return PLATFORM_NAMES.get(platform) or urlsplit(url).hostname or platform


def login_error(platform: str, url: str, opts: IngestOptions, reason: str = "") -> SkipwatchError:
    """R-ING-6: exit 4, naming the cookie flag."""
    site = _site(platform, url)
    if "not a bot" in reason.casefold():
        message = (
            f'{site} stopped this with a bot check ("Sign in to confirm you\'re not a bot"). '
            "Re-run with --cookies-from-browser <browser> using a browser signed in to "
            f"{site}, or run from a home connection: VPN and data-centre addresses trigger it."
        )
    elif opts.cookies_from_browser:
        message = (
            f"{site} says this needs a login, and the cookies from "
            f"--cookies-from-browser {opts.cookies_from_browser} did not get access. Sign in "
            "there and retry, or the content is private."
        )
    else:
        message = (
            f"{site} says this needs a login. Re-run with --cookies-from-browser <browser> "
            "if you can see it in that browser."
        )
    return SkipwatchError(ExitCode.PRIVATE_CONTENT, message)


def _raise_mapped(
    exc: FreeRouteError,
    detected: Detected,
    platform: str,
    opts: IngestOptions,
    partial: IngestBundle | None = None,
) -> NoReturn:
    if exc.code == ExitCode.PRIVATE_CONTENT:
        raise login_error(platform, detected.value, opts, exc.message) from exc
    if exc.code == ExitCode.NO_CONTENT or "unsupported url" in exc.message.casefold():
        raise NoMediaError(detected.value, exc.first_line) from exc
    raise DownloadFailed([f"free.yt-dlp.{exc.op}: {exc.first_line}"], partial) from exc


def _posted_at(info: dict[str, Any]) -> str | None:
    if isinstance(info.get("timestamp"), int | float):
        stamp = datetime.fromtimestamp(info["timestamp"], UTC)
        return stamp.isoformat(timespec="seconds").replace("+00:00", "Z")
    day = info.get("upload_date")
    if isinstance(day, str) and len(day) == 8 and day.isdigit():
        return f"{day[:4]}-{day[4:6]}-{day[6:]}"
    return None


def author_of(info: dict[str, Any], platform: str | None = None) -> str | None:
    fields = AUTHOR_FIELDS.get(platform or "")
    if fields is not None:
        handle = info.get(fields.handle)
        if not handle or not fields.at:
            return handle or None
        return handle if str(handle).startswith("@") else f"@{handle}"
    handle = info.get("uploader_id")
    if handle:
        return handle if str(handle).startswith("@") else f"@{handle}"
    return info.get("uploader")


def author_name_of(info: dict[str, Any], platform: str | None = None) -> str | None:
    fields = AUTHOR_FIELDS.get(platform or "")
    if fields is not None:
        return (info.get(fields.name) or None) if fields.name else None
    return info.get("uploader") or info.get("channel")


def fetch_info(
    detected: Detected, opts: IngestOptions, platform: str
) -> tuple[dict[str, Any], ProviderCall]:
    """Metadata through the free route, with errors mapped onto the ingest contract."""
    started = time.monotonic()
    try:
        info = content_free.extract(detected.value, opts)
    except FreeRouteError as exc:
        _raise_mapped(exc, detected, platform, opts)
    if info.get("_type") in ("playlist", "multi_video"):
        raise SkipwatchError(
            ExitCode.UNSUPPORTED_SOURCE,
            f"{detected.value} is a playlist or channel; pass the URL of one video",
        )
    if info.get("is_live"):
        raise SkipwatchError(
            ExitCode.UNSUPPORTED_SOURCE,
            f"{detected.value} is a live stream; run SkipWatch on it after it ends",
        )
    if not info.get("formats") and not info.get("url"):
        raise NoMediaError(detected.value, "no video or audio formats")
    return info, content_free.call_log("yt-dlp.metadata", True, started)


def _captions(
    info: dict[str, Any], work: WorkDir, opts: IngestOptions, calls: list[ProviderCall]
) -> IngestContext:
    context = IngestContext(post_text=info.get("description"))
    track = choose_caption_track(info)
    if track is None:
        return context
    started = time.monotonic()
    try:
        got = content_free.download_captions(info, work, opts, track, calls)
    except FreeRouteError as exc:
        calls.append(content_free.call_log("yt-dlp.captions", False, started, exc.first_line))
        return context  # Whisper can still transcribe; a caption failure never ends ingest
    calls.append(content_free.call_log("yt-dlp.captions", got is not None, started))
    if got is None:
        return context
    path, lang, kind = got
    return context.model_copy(
        update={
            "captions_available": True,
            "captions_path": path,
            "captions_lang": lang.removesuffix("-orig"),
            "captions_kind": kind,
        }
    )


def _media_duration(work: WorkDir, downloaded: MediaInfo) -> float | None:
    try:
        probed = media.probe(work.path / downloaded.path)
    except SkipwatchError:
        return None
    duration = probed.get("format", {}).get("duration")
    return float(duration) if duration else None


def build_video_bundle(
    detected: Detected, work: WorkDir, opts: IngestOptions, platform: str
) -> IngestBundle:
    info, metadata_call = fetch_info(detected, opts, platform)
    calls = [metadata_call]
    context = _captions(info, work, opts, calls)
    source = SourceInfo(
        kind="video" if has_video(info) else "audio",
        platform=platform,
        url=detected.value,
        canonical_url=info.get("webpage_url") or detected.value,
        author=author_of(info, platform),
        author_name=author_name_of(info, platform),
        title=info.get("title"),
        posted_at=_posted_at(info),
        duration_s=info.get("duration"),
    )
    partial = IngestBundle(
        source=source,
        context=context,
        provider_calls=calls,
        route=Route(context="free"),
        fetched_with_cookies=opts.cookies_from_browser is not None,
    )
    started = time.monotonic()
    try:
        downloaded = content_free.download(info, work, opts, calls)
    except FreeRouteError as exc:
        calls.append(content_free.call_log("yt-dlp.download", False, started, exc.first_line))
        _raise_mapped(
            exc, detected, platform, opts, partial.model_copy(update={"provider_calls": calls})
        )
    calls.append(content_free.call_log("yt-dlp.download", True, started))
    if source.duration_s is None:  # Instagram logged out: read it from the file instead
        source = source.model_copy(update={"duration_s": _media_duration(work, downloaded)})
    return partial.model_copy(
        update={
            "source": source,
            "media": downloaded,
            "provider_calls": calls,
            "route": Route(context="free", media="free"),
        }
    )
