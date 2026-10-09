"""Shared by every adapter that goes through yt-dlp (youtube, generic; x, tiktok and others in M3).

content_free does the network work; this module turns its info dict into an IngestBundle and
maps its errors onto the ingest contract (R-ING-6): a login wall exits 4 naming the cookie
flag, a URL with no video raises NoMediaError, anything else raises DownloadFailed.
"""

from typing import Any

from skipwatch.providers.content_free import CaptionKind

NOT_CAPTIONS = {"live_chat", "rechat"}


def _primary(lang: str) -> str:
    return lang.split("-")[0].casefold()


def _first(keys: list[str], match) -> str | None:
    return next((k for k in keys if match(k)), None)


def choose_caption_track(
    info: dict[str, Any], prefer: str = "en"
) -> tuple[str, CaptionKind] | None:
    """Manual first, then the original-language auto track; never a machine translation.

    Manual: a `prefer` language (en, en-US, ...), else the video's language, else the first.
    Auto: `<language>-orig`, then `prefer` only when the video is in that language (or its
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
    if language is None or _primary(language) == prefer:
        candidates += [f"{prefer}-orig", prefer]
    if language:
        candidates += [language, _primary(language)]
    pick = next((c for c in candidates if c in auto), None)
    return (pick, "auto") if pick else None
