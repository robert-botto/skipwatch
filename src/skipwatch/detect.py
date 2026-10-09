"""Map a user input to (kind, platform) with pure string logic (8.2, R-DET-1).

URLs return kind "url": deciding between video and text needs metadata, which the M2/M3
adapters fetch. Local paths must exist and carry a known media extension.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import SourceKind

VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"})
AUDIO_EXTENSIONS = frozenset({".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg", ".opus"})
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

# Checked in order; a host matches a domain when equal to it or a subdomain of it.
PLATFORM_DOMAINS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("x", ("x.com", "twitter.com")),
    ("youtube", ("youtube.com", "youtu.be")),
    ("tiktok", ("tiktok.com",)),
    ("instagram", ("instagram.com",)),
    ("facebook", ("facebook.com", "fb.watch", "fb.com")),
)


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


def detect(value: str, cwd: Path | None = None) -> Detected:
    url = _as_url(value)
    if url is not None:
        return Detected(kind="url", platform=platform_for_host(url[1]), value=url[0])

    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (cwd or Path.cwd()) / path
    if not path.is_file():
        raise SkipwatchError(ExitCode.UNSUPPORTED_SOURCE, f"not a URL and no such file: {value}")
    if path.suffix.lower() not in MEDIA_EXTENSIONS:
        known = " ".join(sorted(MEDIA_EXTENSIONS))
        raise SkipwatchError(
            ExitCode.UNSUPPORTED_SOURCE,
            f"unsupported file type {path.suffix or '(none)'}; supported: {known}",
        )
    return Detected(kind="file", platform="local", value=str(path.resolve()))
