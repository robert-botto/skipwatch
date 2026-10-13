"""Parse WebVTT and SRT captions into timed segments (R-TR-1); json3 is in captions_json3."""

import html
import re
from pathlib import Path

from skipwatch.captions_json3 import parse_json3
from skipwatch.models import Segment

_TIMING_RE = re.compile(
    r"^\s*(?P<start>(?:\d{1,4}:)?\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*"
    r"(?P<end>(?:\d{1,4}:)?\d{1,2}:\d{2}[.,]\d{1,3})"
)
# Only caption markup is stripped, so spoken text such as "x < y and z > w" survives. Covers
# WebVTT class variants (<c.colorE5E5E5>, <v.loud Name>), <lang en>, inline timestamps
# (<00:00:01.000>), the <font ...> tag common in SRT files and X's per-word timing tag
# (<X-word-ms ms=... index=...>).
_TAG_RE = re.compile(
    r"</?(?:c|v|b|i|u|ruby|rt|lang|font|x-word-ms)(?:[.\s][^<>]*)?>"
    r"|<(?:\d+:)?\d{1,2}:\d{2}[.,]\d{3}>",
    re.IGNORECASE,
)
MIN_CUE_S = 0.05  # YouTube auto-captions put 10 ms transition cues between real ones
_SPACE_RE = re.compile(r"\s+")
_LANG_RE = re.compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*$")


def _seconds(stamp: str) -> float:
    parts = stamp.replace(",", ".").split(":")
    seconds = float(parts[-1])
    minutes = int(parts[-2])
    hours = int(parts[-3]) if len(parts) == 3 else 0
    return round(hours * 3600 + minutes * 60 + seconds, 3)


def _clean_line(line: str) -> str:
    return _SPACE_RE.sub(" ", html.unescape(_TAG_RE.sub("", line))).strip()


def _blocks(text: str) -> list[list[str]]:
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    # Split on truly empty lines only: YouTube auto-captions hold a single-space line inside
    # each cue, and splitting there would cut the timing line off from the cue text.
    return [block.split("\n") for block in re.split(r"\n{2,}", text) if block.strip()]


def _parse(text: str) -> list[Segment]:
    segments: list[Segment] = []
    last_line: str | None = None
    for block in _blocks(text):
        timing_at = next((i for i, line in enumerate(block) if _TIMING_RE.match(line)), None)
        if timing_at is None:
            continue  # header, NOTE, STYLE, REGION, or a stray SRT index
        match = _TIMING_RE.match(block[timing_at])
        assert match is not None
        start = _seconds(match["start"])
        end = max(start, _seconds(match["end"]))
        if round(end - start, 3) < MIN_CUE_S:
            continue
        lines = [cleaned for line in block[timing_at + 1 :] if (cleaned := _clean_line(line))]
        # Rolling captions repeat the previous cue's last line at the top of the next cue. A cue
        # that is only a repeat is left whole for the merge rule below.
        while len(lines) > 1 and lines[0] == last_line:
            lines.pop(0)
        if not lines:
            continue
        last_line = lines[-1]
        cue = " ".join(lines)
        previous = segments[-1] if segments else None
        if previous is not None and previous.text == cue and start <= previous.end:
            # A cue repeated back to back is extended instead of duplicated. The same words
            # after a pause are spoken again and stay a separate segment.
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
    if path.suffix.lower() == ".json3":
        return parse_json3(text)
    return parse_vtt(text)


def language_from_name(sidecar_name: str, media_stem: str) -> str | None:
    """The `<lang>` in `<stem>.<lang>.vtt` (yt-dlp naming), or None for `<stem>.vtt`."""
    middle = Path(sidecar_name).stem
    if not middle.startswith(media_stem + "."):
        return None
    lang = middle[len(media_stem) + 1 :]
    return lang if _LANG_RE.match(lang) else None
