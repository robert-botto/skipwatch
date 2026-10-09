"""Scrub a recorded yt-dlp or provider fixture before it is committed.

Drops cookies, request headers, tokens and sessions; cuts signed query strings from URLs to
`?SCRUBBED`; replaces IPv4 literals with 0.0.0.0. Creator handles stay (attribution data).
Usage: scrub_fixture.py IN -o OUT. scripts/record_fixture.py imports `scrub` directly.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

DROPPED_KEYS = {
    "http_headers",
    "cookies",
    "_cookies",
    "__x_forwarded_for_ip",
    "requested_subtitles",  # holds signed subtitle URLs
}
DROPPED_KEY_PARTS = ("token", "session")
IPV4 = re.compile(r"\b\d{1,3}(\.\d{1,3}){3}\b")


def _dropped(key: str) -> bool:
    lowered = key.lower()
    return key in DROPPED_KEYS or any(part in lowered for part in DROPPED_KEY_PARTS)


def _scrub_string(value: str) -> str:
    if value.startswith("http") and "?" in value:
        value = value[: value.index("?")] + "?SCRUBBED"
    return IPV4.sub("0.0.0.0", value)


def scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {key: scrub(value) for key, value in obj.items() if not _dropped(str(key))}
    if isinstance(obj, list):
        return [scrub(item) for item in obj]
    if isinstance(obj, str):
        return _scrub_string(obj)
    return obj


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    text = json.dumps(scrub(data), indent=2, sort_keys=True) + "\n"
    Path(args.output).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
