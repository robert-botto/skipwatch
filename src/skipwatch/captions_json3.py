"""Parse YouTube json3 captions into timed segments with word timings (R-TR-1).

Each event with `segs` is one cue: start tStartMs, end tStartMs + dDurationMs, clipped to the
next cue's start (auto captions keep a line on screen while the next one is spoken, so raw
events overlap). Events sharing a start (two rows shown together) are merged first. Word
timings come from `tOffsetMs` when a cue has more than one seg, clipped to the cue's end.
Events that hold only a newline ("aAppend" line breaks) are dropped, and a cue repeated back
to back is extended instead of duplicated, as in parse_vtt.
"""

import json
import re
from typing import Any

from skipwatch.models import Segment, Word

_SPACE_RE = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _SPACE_RE.sub(" ", text).strip()


def _words(event: dict[str, Any], start_ms: int, end: float) -> list[Word] | None:
    segs = event.get("segs") or []
    if len(segs) < 2:
        return None
    timed = [
        (min((start_ms + int(seg.get("tOffsetMs", 0))) / 1000, end), _clean(seg.get("utf8", "")))
        for seg in segs
    ]
    timed = [(s, w) for s, w in timed if w]
    words = []
    for i, (s, w) in enumerate(timed):
        e = timed[i + 1][0] if i + 1 < len(timed) else end
        words.append(Word(w=w, s=round(s, 3), e=round(max(s, min(e, end)), 3)))
    return words or None


def _merge_same_start(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Two rows shown at the same moment are one cue: texts joined, the longer duration."""
    merged: list[dict[str, Any]] = []
    for event in events:
        last = merged[-1] if merged else None
        if last is not None and int(last.get("tStartMs", 0)) == int(event.get("tStartMs", 0)):
            last["dDurationMs"] = max(
                int(last.get("dDurationMs", 0)), int(event.get("dDurationMs", 0))
            )
            last["segs"] = [*last["segs"], {"utf8": " "}, *event["segs"]]
        else:
            merged.append(dict(event))
    return merged


def parse_json3(text: str) -> list[Segment]:
    events = [
        e
        for e in json.loads(text).get("events", [])
        if e.get("segs") and _clean("".join(s.get("utf8", "") for s in e["segs"]))
    ]
    events.sort(key=lambda e: int(e.get("tStartMs", 0)))
    events = _merge_same_start(events)
    segments: list[Segment] = []
    for i, event in enumerate(events):
        start_ms = int(event.get("tStartMs", 0))
        start = start_ms / 1000
        end = (start_ms + int(event.get("dDurationMs", 0))) / 1000
        if i + 1 < len(events):
            next_start = int(events[i + 1].get("tStartMs", 0)) / 1000
            if start < next_start < end:
                end = next_start
        cue = _clean("".join(seg.get("utf8", "") for seg in event["segs"]))
        previous = segments[-1] if segments else None
        if previous is not None and previous.text == cue and start <= previous.end:
            previous.end = max(previous.end, end)
            continue
        segments.append(
            Segment(
                start=round(start, 3),
                end=round(end, 3),
                text=cue,
                words=_words(event, start_ms, end),
            )
        )
    return segments
