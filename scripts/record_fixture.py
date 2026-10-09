"""Record a scrubbed yt-dlp metadata fixture (and optionally its caption track) for unit tests.

Live: touches the real network, so it refuses to run unless SKIPWATCH_LIVE=1. Metadata and
captions only, never media; never cookies. The output is passed through scrub_fixture.scrub and
cut down to the keys adapters read. Caption track URLs are cut to scheme and host before the
scrub: YouTube's HLS timedtext URLs carry the caller's IP percent-encoded inside the path
(`ip%3D198.51.100.23`), which the scrubber's word-boundary IP pattern does not see. As a last check
the percent-decoded output must hold no IPv4 literal other than 0.0.0.0. Text is written as
ASCII JSON (json3 captions are re-serialised the same way) so no em dash character lands in a
file; a vtt or srt track has it replaced by a hyphen. Caption text is scrubbed too. A human
still reads every recorded file before commit.

Usage:
  SKIPWATCH_LIVE=1 uv run python scripts/record_fixture.py <url> --name <slug> \
      --platform <dir> [--captions]
Writes tests/fixtures/recorded/<platform>/<slug>.info.json and, with --captions,
<slug>.<lang>.<ext> (json3 when offered, else vtt or srt).
"""

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import yt_dlp

from skipwatch.adapters.base import IngestOptions
from skipwatch.adapters.ytdlp_common import choose_caption_track
from skipwatch.providers import content_free
from skipwatch.workdir import WorkDir

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scrub_fixture import scrub  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "recorded"

TOP_KEYS = (
    "id", "title", "uploader", "uploader_id", "channel", "upload_date", "timestamp", "duration",
    "webpage_url", "extractor_key", "description", "language", "is_live", "availability",
    "age_limit",
)  # fmt: skip
FORMAT_KEYS = (
    "format_id", "ext", "width", "height", "filesize", "filesize_approx", "tbr", "vcodec",
    "acodec", "url",
)  # fmt: skip
IPV4_RE = re.compile(r"(?<![0-9A-Za-z.])\d{1,3}(?:\.\d{1,3}){3}(?![0-9.])")
EM_DASH = "\u2014"
# YouTube CDN node names (rr5---sn-abcd1234.googlevideo.com) map to the caller's ISP edge.
CDN_NODE_RE = re.compile(r"---sn-[a-z0-9-]+\.")


def _host(url: str | None) -> str | None:
    if not url:
        return url
    parts = urlsplit(url)
    if not (parts.scheme and parts.hostname):
        return None
    return f"{parts.scheme}://{CDN_NODE_RE.sub('---sn-SCRUBBED.', parts.hostname)}"


def _tracks(tracks: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    return {
        lang: [{"ext": e.get("ext"), "url": _host(e.get("url"))} for e in entries]
        for lang, entries in (tracks or {}).items()
    }


def leaked_ips(text: str) -> set[str]:
    return {ip for ip in IPV4_RE.findall(unquote(unquote(text))) if ip != "0.0.0.0"}


def caption_text(raw: bytes, ext: str) -> str:
    """Caption files go through the same scrub as metadata (emails, URLs, IPs in the text)."""
    text = raw.decode("utf-8")
    if ext == ".json3":
        return json.dumps(scrub(json.loads(text)), indent=1) + "\n"
    return scrub({"text": text})["text"].replace(EM_DASH, "-")


def trim(info: dict[str, Any]) -> dict[str, Any]:
    """Only the keys adapters read (plan Task M2-B1)."""
    out = {k: info.get(k) for k in TOP_KEYS}
    out["formats"] = [
        {k: _host(f.get(k)) if k == "url" else f.get(k) for k in FORMAT_KEYS}
        for f in info.get("formats") or []
    ]
    out["subtitles"] = _tracks(info.get("subtitles"))
    out["automatic_captions"] = _tracks(info.get("automatic_captions"))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--name", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--captions", action="store_true")
    args = parser.parse_args()
    if os.environ.get("SKIPWATCH_LIVE") != "1":
        print("record_fixture touches the network: set SKIPWATCH_LIVE=1", file=sys.stderr)
        return 2
    opts = IngestOptions()  # never cookies
    params = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "js_runtimes": content_free.js_runtime(),
    }
    with yt_dlp.YoutubeDL(params) as ydl:  # pyright: ignore[reportArgumentType]
        raw = ydl.sanitize_info(ydl.extract_info(args.url, download=False))
    folder = OUT / args.platform
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{args.name}.info.json"
    text = json.dumps(scrub(trim(raw)), indent=2, sort_keys=True) + "\n"
    if leaked := leaked_ips(text):
        print(f"refusing to write: IP literals survived the scrub: {leaked}", file=sys.stderr)
        return 1
    target.write_text(text, "utf-8")
    print(f"wrote {target.relative_to(ROOT)}")
    if args.captions:
        track = choose_caption_track(raw)
        if track is None:
            print("no caption track to record", file=sys.stderr)
            return 1
        with tempfile.TemporaryDirectory() as tmp:
            got = content_free.download_captions(raw, WorkDir(Path(tmp)), opts, track)
            if got is None:
                print(f"track {track} has no json3, vtt or srt", file=sys.stderr)
                return 1
            src = Path(tmp) / got[0]
            dest = folder / f"{args.name}.{got[1]}{src.suffix}"
            body = caption_text(src.read_bytes(), src.suffix)
            if leaked := leaked_ips(body):
                print(f"refusing to write captions: IP literals {leaked}", file=sys.stderr)
                return 1
            dest.write_text(body, "utf-8")
        print(f"wrote {dest.relative_to(ROOT)} ({got[2]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
