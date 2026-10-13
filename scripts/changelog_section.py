"""Print the CHANGELOG.md section for a release tag, for the GitHub release notes (spec 13).

Usage: changelog_section.py v0.1.0 [--changelog PATH]. Prints the body under `## [0.1.0]`
up to the next `## ` heading and exits 0; exits 1 when the section is missing or empty.
Standard library only: the release workflow runs it with `uv run --no-project`.
"""

import argparse
import re
import sys
from pathlib import Path

DEFAULT_CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"


def section(text: str, version: str) -> str | None:
    heading = re.compile(rf"^## \[{re.escape(version)}\][^\n]*$", re.MULTILINE)
    match = heading.search(text)
    if match is None:
        return None
    rest = text[match.end() :]
    following = re.search(r"^## ", rest, re.MULTILINE)
    body = rest[: following.start()] if following else rest
    return body.strip("\n") + "\n" if body.strip() else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag", help="release tag, for example v0.1.0")
    parser.add_argument("--changelog", default=str(DEFAULT_CHANGELOG))
    args = parser.parse_args()
    version = args.tag.removeprefix("v")
    path = Path(args.changelog)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    body = section(text, version)
    if body is None:
        print(f"no ## [{version}] section in {path}", file=sys.stderr)
        return 1
    sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
