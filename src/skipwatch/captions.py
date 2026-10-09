"""Parse WebVTT and SRT captions into timed segments (R-TR-1)."""

import html
import re
from pathlib import Path

from skipwatch.models import Segment

_TIMING_RE = re.compile(
    r"^\s*(?P<start>(?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*"
    r"(?P<end>(?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})"
)
_TAG_RE = re.compile(r"<[^>]*>")
_SPACE_RE = re.compile(r"\s+")
_LANG_RE = re.compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*$")


def _seconds(stamp: str) -> float:
    parts = stamp.replace(",", ".").split(":")
    seconds = float(parts[-1])
    minutes = int(parts[-2])
    hours = int(parts[-3]) if len(parts) == 3 else 0
    return round(hours * 3600 + minutes * 60 + seconds, 3)


def _clean(lines: list[str]) -> str:
    text = " ".join(_TAG_RE.sub("", line) for line in lines)
    return _SPACE_RE.sub(" ", html.unescape(text)).strip()


def _blocks(text: str) -> list[list[str]]:
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    return [block.split("\n") for block in re.split(r"\n\s*\n", text) if block.strip()]


def _parse(text: str) -> list[Segment]:
    segments: list[Segment] = []
    for block in _blocks(text):
        timing_at = next((i for i, line in enumerate(block) if _TIMING_RE.match(line)), None)
        if timing_at is None:
            continue  # header, NOTE, STYLE, REGION, or a stray SRT index
        match = _TIMING_RE.match(block[timing_at])
        assert match is not None
        start = _seconds(match["start"])
        end = max(start, _seconds(match["end"]))
        cue = _clean(block[timing_at + 1 :])
        if not cue:
            continue
        previous = segments[-1] if segments else None
        if previous is not None and previous.text == cue and start <= previous.end:
            # YouTube rolling captions repeat a cue back to back; extend instead of duplicating.
            # The same words after a pause are spoken again and stay a separate segment.
            previous.end = max(previous.end, end)
            continue
        segments.append(Segment(start=start, end=end, text=cue))
    return segments


def parse_vtt(text: str) -> list[Segment]:
    return _parse(text)


def parse_srt(text: str) -> list[Segment]:
    return _parse(text)


def parse_file(path: Path) -> list[Segment]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if path.suffix.lower() == ".srt":
        return parse_srt(text)
    return parse_vtt(text)


def language_from_name(sidecar_name: str, media_stem: str) -> str | None:
    """The `<lang>` in `<stem>.<lang>.vtt` (yt-dlp naming), or None for `<stem>.vtt`."""
    middle = Path(sidecar_name).stem
    if not middle.startswith(media_stem + "."):
        return None
    lang = middle[len(media_stem) + 1 :]
    return lang if _LANG_RE.match(lang) else None
