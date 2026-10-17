"""The run slug for `new-work --from` (run-engine.md stage 2), so the skill never builds it.

A URL gives its host without `www.` plus the video id (`v=`) or the last path segment; any
other input gives its file stem. Then: lowercase, every character outside [a-z0-9-] to `-`,
repeated hyphens collapsed, hyphens trimmed, cut to 40 (URL) or 80 (file) characters with a
hyphen the cut leaves at the end trimmed, and `video` when nothing is left.
"""

import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from skipwatch.detect import _as_url, _looks_like_scheme_less_url

URL_MAX = 40
FILE_MAX = 80
FALLBACK = "video"


def _url_base(url: str) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").rstrip(".")
    if host.startswith("www."):
        host = host[len("www.") :]
    video_id = parse_qs(parts.query).get("v", [""])[0]
    segments = [s for s in parts.path.split("/") if s]
    tail = video_id or (segments[-1] if segments else "")
    return f"{host}-{tail}" if tail else host


def _clean(text: str, limit: int) -> str:
    text = re.sub(r"[^a-z0-9-]", "-", text.lower())
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:limit].rstrip("-") or FALLBACK


def slug_for(value: str, cwd: Path | None = None) -> str:
    url = _as_url(value)
    if url is None:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = (cwd or Path.cwd()) / path
        if not path.exists() and _looks_like_scheme_less_url(value):
            url = _as_url("https://" + value.strip())
    if url is not None:
        return _clean(_url_base(url[0]), URL_MAX)
    return _clean(Path(value.strip()).stem, FILE_MAX)
