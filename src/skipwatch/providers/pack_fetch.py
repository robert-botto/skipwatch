"""Download a shared pack from an https URL (spec 14.1 pack loop).

The transport is links.get_vetted: no cookies, no environment credentials or proxies, every
hop (at most 3 redirects) resolved, refused unless every address is public, and pinned to the
vetted address. On top of that a pack must stay on https, and at most MAX_PACK_BYTES are read,
within a wall-clock deadline. The file lands only in dest_dir, under a sanitised name.
"""

import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
import urllib3

from skipwatch import pack
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.project import PACK_SUFFIX
from skipwatch.providers import links

DEADLINE_S = 120.0  # wall clock for the whole download, redirects included
DEFAULT_NAME = "download" + PACK_SUFFIX
_GITHUB_BLOB = re.compile(r"^/([^/]+)/([^/]+)/blob/(.+)$")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _failed(message: str) -> SkipwatchError:
    return SkipwatchError(ExitCode.DOWNLOAD_FAILED, f"cannot fetch the pack: {message}")


def _too_large() -> SkipwatchError:
    return SkipwatchError(ExitCode.PACK_INTEGRITY, "pack integrity: pack too large")


def raw_url(url: str) -> str:
    """A github.com blob page becomes its raw.githubusercontent.com file; else url."""
    parts = urlsplit(url)
    if (parts.hostname or "").lower() in ("github.com", "www.github.com"):
        blob = _GITHUB_BLOB.match(parts.path)
        if blob:
            owner, repo, rest = blob.groups()
            return f"https://raw.githubusercontent.com/{owner}/{repo}/{rest}"
    return url


def file_name(url: str) -> str:
    segment = urlsplit(url).path.rsplit("/", 1)[-1]
    if segment.endswith(PACK_SUFFIX) and _SAFE_NAME.match(segment):
        return segment
    return DEFAULT_NAME


def _stream(response: requests.Response, part: Path, deadline: float) -> None:
    size = 0
    with part.open("xb") as out:
        while True:
            if time.monotonic() >= deadline:
                raise _failed(f"over the {DEADLINE_S:g} s download deadline")
            chunk = response.raw.read1(links.CHUNK, decode_content=True)
            if not chunk:
                return
            size += len(chunk)
            if size > pack.MAX_PACK_BYTES:
                raise _too_large()
            out.write(chunk)


def fetch_pack(url: str, dest_dir: Path) -> Path:
    """GET an https pack URL into dest_dir. Raises SkipwatchError: UNSUPPORTED_SOURCE for a
    non-https URL, DOWNLOAD_FAILED for a refused host, an HTTP error or a broken transfer,
    PACK_INTEGRITY for a body over the pack size limit. No partial file is left behind."""
    if urlsplit(url).scheme.lower() != "https":
        raise SkipwatchError(ExitCode.UNSUPPORTED_SOURCE, "pack URLs must be https")
    deadline = time.monotonic() + DEADLINE_S
    try:
        response = links.get_vetted(raw_url(url), deadline)
    except links.Refused as exc:
        raise _failed(str(exc)) from exc
    except requests.RequestException as exc:
        raise _failed(type(exc).__name__) from exc
    dest = dest_dir / file_name(url)
    part = dest.with_name(dest.name + ".part")
    try:
        if urlsplit(str(response.url)).scheme.lower() != "https":
            raise _failed("redirected off https")
        if not 200 <= response.status_code < 300:
            raise _failed(f"HTTP {response.status_code}")
        length = response.headers.get("Content-Length")
        if length and length.isdigit() and int(length) > pack.MAX_PACK_BYTES:
            raise _too_large()
        try:
            _stream(response, part, deadline)
        except (urllib3.exceptions.HTTPError, requests.RequestException, OSError) as exc:
            raise _failed(type(exc).__name__) from exc
        os.replace(part, dest)
    finally:
        links.close_vetted(response)
        part.unlink(missing_ok=True)
    return dest
