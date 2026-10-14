"""Map a user input to (kind, platform) with pure string logic (8.2, R-DET-1).

URLs return kind "url": deciding between video and text needs metadata, which the M2/M3
adapters fetch. Local paths must exist and carry a known media extension.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import SourceKind

VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"})
AUDIO_EXTENSIONS = frozenset({".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg", ".opus"})
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

# t.co stays generic on purpose: it is a redirect, and resolving it needs the network (M2).
# Checked in order; a host matches a domain when equal to it or a subdomain of it.
PLATFORM_DOMAINS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("x", ("x.com", "twitter.com")),
    ("youtube", ("youtube.com", "youtu.be", "youtube-nocookie.com")),
    ("tiktok", ("tiktok.com",)),
    ("instagram", ("instagram.com", "instagr.am")),
    ("facebook", ("facebook.com", "fb.watch", "fb.com")),
)


# A bare host such as "www.youtube.com": dotted labels ending in a letters-only TLD.
_HOST_RE = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")


@dataclass(frozen=True)
class Detected:
    kind: SourceKind | Literal["url"]
    platform: str
    value: str


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def platform_for_host(host: str) -> str:
    host = host.lower().rstrip(".")
    for platform, domains in PLATFORM_DOMAINS:
        if any(_host_matches(host, d) for d in domains):
            return platform
    return "generic"


def _as_url(value: str) -> tuple[str, str] | None:
    """(normalised url, host) when value is an http(s) URL, else None."""
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return None
    return value.strip(), parts.hostname


def _looks_like_scheme_less_url(value: str) -> bool:
    """True for "youtube.com/watch?v=1", "youtube.com" or "example.com/post"; false for a file
    name such as "clip.mov" or "notes.md" (ruling FU-R1). A host with nothing after it but a
    query is a URL only when it is a known platform host, so a missing notes.md never turns into
    a request to https://notes.md."""
    value = value.strip()
    first = re.split(r"[/?#]", value, maxsplit=1)[0]
    if not _HOST_RE.match(first) or Path(first).suffix.lower() in MEDIA_EXTENSIONS:
        return False
    return platform_for_host(first) != "generic" or value[len(first) :].startswith("/")


def detect(value: str, cwd: Path | None = None) -> Detected:
    url = _as_url(value)
    if url is not None:
        return Detected(kind="url", platform=platform_for_host(url[1]), value=url[0])

    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (cwd or Path.cwd()) / path
    if not path.exists() and _looks_like_scheme_less_url(value):
        return detect("https://" + value.strip(), cwd)
    if not path.is_file():
        raise SkipwatchError(ExitCode.UNSUPPORTED_SOURCE, f"not a URL and no such file: {value}")
    if path.suffix.lower() not in MEDIA_EXTENSIONS:
        known = " ".join(sorted(MEDIA_EXTENSIONS))
        raise SkipwatchError(
            ExitCode.UNSUPPORTED_SOURCE,
            f"unsupported file type {path.suffix or '(none)'}; supported: {known}",
        )
    return Detected(kind="file", platform="local", value=str(path.resolve()))
