"""Check that every golden video still resolves: metadata only, no download, no cookies.

Usage: uv run python scripts/golden_check.py [--only G1,G5] [--golden tests/golden/golden.json]

Prints one line per video, `G1 OK youtube 10:12 captions=manual formats>=720p=yes` or
`G1 FAIL <reason>`, and exits 0 only when every selected video passes. Live network.
"""

import argparse
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLDEN = ROOT / "tests" / "golden" / "golden.json"


def _english(tracks: dict[str, Any] | None) -> bool:
    return any(lang == "en" or lang.startswith("en-") for lang in tracks or {})


def caption_kind(info: dict[str, Any]) -> str:
    """ "manual" when an English manual track exists, else "auto" for English auto, else "none"."""
    if _english(info.get("subtitles")):
        return "manual"
    if _english(info.get("automatic_captions")):
        return "auto"
    return "none"


def has_720p(info: dict[str, Any]) -> bool:
    """Any video format whose short side is at least 720 (M2-M4 issue 3)."""
    for fmt in info.get("formats") or []:
        width, height = fmt.get("width"), fmt.get("height")
        if width and height and min(width, height) >= 720:
            return True
    return False


def _clock(seconds: float | None) -> str:
    if seconds is None:
        return "?:??"
    total = round(seconds)
    return f"{total // 60}:{total % 60:02d}"


TASK_KEYS = ("s2", "s3")  # fresh-session tasks: G1's worked example (S2), G2's workflow (S3)
TASK_FIELDS = {"task", "verify", "setup_files"}


def safe_relative(name: str) -> bool:
    """A setup file path that stays inside the scratch dir on every OS."""
    path = PurePosixPath(name)
    return (
        bool(name)
        and "\\" not in name
        and ":" not in name
        and not path.is_absolute()
        and (".." not in path.parts)
    )


def task_problems(entry: dict[str, Any]) -> list[str]:
    """Shape of s2/s3: non-empty task and verify, optional setup_files of safe paths to text."""
    problems = []
    for key in TASK_KEYS:
        spec = entry.get(key)
        if spec is None:
            continue
        unknown = sorted(set(spec) - TASK_FIELDS)
        if unknown:
            problems.append(f"{key} has unknown keys: {', '.join(unknown)}")
        for field in ("task", "verify"):
            value = spec.get(field)
            if not isinstance(value, str) or not value.strip():
                problems.append(f"{key}.{field} is empty")
        for name, text in (spec.get("setup_files") or {}).items():
            if not safe_relative(name):
                problems.append(f"{key}.setup_files path {name} escapes the scratch dir")
            elif not isinstance(text, str):
                problems.append(f"{key}.setup_files {name} not text")
    return problems


def check_entry(entry: dict[str, Any], info: dict[str, Any]) -> tuple[bool, str]:
    captions = caption_kind(info)
    hd = has_720p(info)
    summary = (
        f"{entry['platform']} {_clock(info.get('duration'))} "
        f"captions={captions} formats>=720p={'yes' if hd else 'no'}"
    )
    problems = task_problems(entry)
    if entry["captions"] == "manual" and captions != "manual":
        problems.append("manual captions missing")
    if entry["captions"] == "auto" and captions == "none":
        problems.append("captions missing")
    if not hd:
        problems.append("no format at or above 720p")
    if problems:
        return False, f"{entry['id']} FAIL {'; '.join(problems)}: {summary}"
    return True, f"{entry['id']} OK {summary}"


def _js_runtimes() -> dict[str, dict[str, str]]:
    """Exactly one runtime, node 22+ before deno, as the engine does (M2-M4 issue 2)."""
    node = shutil.which("node")
    if node:
        out = subprocess.run([node, "--version"], capture_output=True, text=True).stdout
        try:
            if int(out.strip().lstrip("v").split(".")[0]) >= 22:
                return {"node": {"path": node}}
        except ValueError:
            pass
    deno = shutil.which("deno")
    return {"deno": {"path": deno}} if deno else {}


def fetch_info(url: str) -> dict[str, Any]:
    import yt_dlp

    params = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "js_runtimes": _js_runtimes(),
    }
    with yt_dlp.YoutubeDL(params) as ydl:  # pyright: ignore[reportArgumentType]
        info = ydl.extract_info(url, download=False)
    return dict(info or {})


def select(videos: list[dict[str, Any]], only: str | None) -> list[dict[str, Any]]:
    if not only:
        return videos
    wanted = [part.strip().upper() for part in only.split(",") if part.strip()]
    known = {video["id"] for video in videos}
    unknown = [vid for vid in wanted if vid not in known]
    if unknown:
        raise SystemExit(f"unknown golden id: {', '.join(unknown)}")
    return [video for video in videos if video["id"] in wanted]


def main(argv: list[str] | None = None, fetch: Callable[[str], dict[str, Any]] = fetch_info) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="comma-separated ids, for example G1,G5")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    args = parser.parse_args(argv)
    videos = select(json.loads(args.golden.read_text(encoding="utf-8"))["videos"], args.only)
    all_ok = True
    for entry in videos:
        try:
            ok, line = check_entry(entry, fetch(entry["url"]))
        except Exception as exc:  # yt-dlp raises many types; each is one FAIL line
            ok, line = False, f"{entry['id']} FAIL {str(exc).splitlines()[0]}"
        all_ok = all_ok and ok
        print(line, flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
