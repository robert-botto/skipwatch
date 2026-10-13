"""HLS subtitle playlists: read the segment list and merge the WebVTT segments (R-TR-1).

Some platforms (X) list their captions as an HLS media playlist (#EXTM3U) of WebVTT segments
instead of a WebVTT file. This module is pure: content_free fetches the playlist and the
segments, this module says which URLs to fetch and joins what came back into one WebVTT text
that captions.parse_vtt reads.

X-TIMESTAMP-MAP (RFC 8216 3.5) ties a segment's cue times (LOCAL) to the stream clock (MPEGTS,
90 kHz). Each segment is shifted by its own mapping relative to the first segment's, so the
first mapping is the timeline's origin, as it is for the video. A segment with no mapping keeps
its cue times as they are.
"""

import re
from urllib.parse import urljoin

MAX_SEGMENTS = 2000  # 6 s segments for over three hours of video
MPEGTS_HZ = 90_000

_MAP_RE = re.compile(r"^X-TIMESTAMP-MAP=(?P<fields>.*)$", re.MULTILINE)
_TIMING_RE = re.compile(
    r"^(?P<lead>[ \t]*)(?P<start>(?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})(?P<arrow>[ \t]*-->[ \t]*)"
    r"(?P<end>(?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})",
    re.MULTILINE,
)
_REFUSED_TAGS = {
    "#EXT-X-STREAM-INF": "a master playlist, not subtitle segments",
    "#EXT-X-MEDIA:": "a master playlist, not subtitle segments",
    "#EXT-X-MAP:": "segments with an init section, not WebVTT",
}


class HlsError(Exception):
    """A playlist SkipWatch will not turn into captions."""


def is_playlist(body: bytes) -> bool:
    return body.lstrip(b"\xef\xbb\xbf").lstrip().startswith(b"#EXTM3U")


def segment_urls(playlist: str, base_url: str) -> list[str]:
    """The segment URLs, in order, resolved against the playlist's own URL."""
    urls: list[str] = []
    for raw in playlist.lstrip("﻿").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            reason = next((r for tag, r in _REFUSED_TAGS.items() if line.startswith(tag)), None)
            if reason is not None:
                raise HlsError(reason)
            if line.startswith("#EXT-X-KEY:") and "METHOD=NONE" not in line.upper():
                raise HlsError("encrypted segments")
            continue
        urls.append(urljoin(base_url, line))
        if len(urls) > MAX_SEGMENTS:
            raise HlsError(f"more than {MAX_SEGMENTS} segments")
    if not urls:
        raise HlsError("a playlist with no segments")
    return urls


def _seconds(stamp: str) -> float:
    parts = stamp.replace(",", ".").split(":")
    hours = int(parts[-3]) if len(parts) == 3 else 0
    return hours * 3600 + int(parts[-2]) * 60 + float(parts[-1])


def _stamp(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    return f"{hours:02d}:{minutes:02d}:{rest // 1000:02d}.{rest % 1000:03d}"


def _offset(segment: str) -> float | None:
    """MPEGTS/90000 - LOCAL in seconds, or None when the segment has no usable mapping."""
    found = _MAP_RE.search(segment.replace("\r\n", "\n").replace("\r", "\n"))
    if found is None:
        return None
    fields = dict(part.split(":", 1) for part in found["fields"].strip().split(",") if ":" in part)
    try:
        mpegts = int(fields.get("MPEGTS", "0"))
        local = _seconds(fields.get("LOCAL", "00:00.000"))
    except ValueError:
        return None
    return mpegts / MPEGTS_HZ - local


def _shifted(segment: str, shift: float) -> str:
    if not shift:
        return segment

    def move(m: re.Match[str]) -> str:
        start = _stamp(_seconds(m["start"]) + shift)
        return f"{m['lead']}{start}{m['arrow']}{_stamp(_seconds(m['end']) + shift)}"

    return _TIMING_RE.sub(move, segment)


def merge_webvtt(segments: list[str]) -> str:
    """One WebVTT text from the segments, each shifted by its X-TIMESTAMP-MAP."""
    origin: float | None = None
    bodies: list[str] = []
    for segment in segments:
        offset = _offset(segment)
        if offset is not None and origin is None:
            origin = offset
        shift = offset - origin if offset is not None and origin is not None else 0.0
        bodies.append(_shifted(segment.lstrip("﻿"), shift))
    # Each segment's own WEBVTT header and mapping become header-only blocks, which the parser
    # skips; a blank line keeps the last cue of one segment from running into the next.
    return "WEBVTT\n\n" + "\n\n".join(bodies)
