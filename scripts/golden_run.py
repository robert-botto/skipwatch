"""Run the golden set through SkipWatch and diff each staged draft against its expected ranges.

Usage:
  uv run python scripts/golden_run.py [--only G1,G5] [--out DIR] [--plugin-dir .]
  uv run python scripts/golden_run.py --engine-only --only G1 --out DIR

The full run calls `claude -p` once per video (paid, run by hand). Each video gets its own
SKIPWATCH_HOME under <out>/<id>/home. Judging reads that home's newest check-report.json and
staged SKILL.md, installed or not (M2-M4 issue 16). `--engine-only` runs just the stages that
need no Claude (ingest, transcribe, frames, plan) and judges nothing.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skipwatch.skillmd import _split_frontmatter, fenced_lines

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLDEN = ROOT / "tests" / "golden" / "golden.json"
CLAUDE_TIMEOUT_S = 30 * 60
STAGE_TIMEOUT_S = 30 * 60
ENGINE_STAGES = ("ingest", "transcribe", "frames", "plan")
COOKIE_ENV = "SKIPWATCH_GOLDEN_COOKIES"
COOKIE_BROWSERS = {"chrome"}

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass
class VideoResult:
    id: str
    ok: bool
    line: str


def illegible_in_quotes(skill_md: str) -> int:
    """`[illegible` markers inside quotes: blockquote lines and closed fenced blocks (S3)."""
    _, body, _, _ = _split_frontmatter(skill_md)
    lines = body.splitlines()
    fenced = fenced_lines(lines)
    return sum(
        line.count("[illegible")
        for i, line in enumerate(lines)
        if i in fenced or line.lstrip().startswith(">")
    )


def metrics(report: dict[str, Any], skill_md: str) -> dict[str, Any]:
    counts = report.get("counts", {})
    steps = int(counts.get("steps", 0))
    inferred = int(counts.get("inferred", 0))
    return {
        "steps": steps,
        "inferred": inferred / steps if steps else 0.0,
        "gaps": int(counts.get("gaps", 0)),
        "flags": sum(len(result.get("flags", [])) for result in report.get("results", [])),
        "illegible_in_quotes": illegible_in_quotes(skill_md),
    }


def judge(report: dict[str, Any], skill_md: str, expected: dict[str, Any]) -> list[str]:
    """Each out-of-range value as `name=value (want range)`; empty when all are in range."""
    m = metrics(report, skill_md)
    low, high = expected["steps"]
    problems = []
    if not low <= m["steps"] <= high:
        problems.append(f"steps={m['steps']} (want {low}..{high})")
    if m["inferred"] > expected["inferred_ratio_max"]:
        problems.append(
            f"inferred={m['inferred']:.2f} (want <={expected['inferred_ratio_max']:.2f})"
        )
    for key, limit in (
        ("gaps", "gaps_max"),
        ("flags", "safety_flags_max"),
        ("illegible_in_quotes", "illegible_in_quotes_max"),
    ):
        if m[key] > expected[limit]:
            problems.append(f"{key}={m[key]} (want <={expected[limit]})")
    return problems


def result_line(video_id: str, m: dict[str, Any], problems: list[str], installed: bool) -> str:
    tail = f"installed={'yes' if installed else 'no'}"
    if problems:
        return f"{video_id} FAIL {' '.join(problems)} {tail}"
    return (
        f"{video_id} PASS steps={m['steps']} inferred={m['inferred']:.2f} gaps={m['gaps']} "
        f"flags={m['flags']} illegible_in_quotes={m['illegible_in_quotes']} {tail}"
    )


def cookies_from_env(env: Mapping[str, str]) -> str | None:
    value = env.get(COOKIE_ENV, "")
    return value if value in COOKIE_BROWSERS else None


def skill_name(entry: dict[str, Any]) -> str:
    return f"{entry['id'].lower()}-skill"


def claude_command(
    entry: dict[str, Any], out: Path, plugin_dir: Path, cookies: str | None
) -> list[str]:
    prompt = (
        f"/skipwatch:skipwatch {entry['url']} --yes --to {out / entry['id'] / 'skills'} "
        f"--name {skill_name(entry)}"
    )
    if entry.get("needs_cookies") and cookies:
        prompt += f" --cookies-from-browser {cookies}"
    return [
        "claude",
        "-p",
        "--plugin-dir",
        str(plugin_dir),
        "--allowedTools",
        "Bash,Read,Write,Agent",
        prompt,
    ]


def _newest(paths: list[Path]) -> Path | None:
    return max(paths, key=lambda p: p.stat().st_mtime) if paths else None


def run_video(
    entry: dict[str, Any],
    out: Path,
    plugin_dir: Path,
    runner: Runner = subprocess.run,
    base_env: Mapping[str, str] | None = None,
) -> VideoResult:
    base = dict(os.environ if base_env is None else base_env)
    home = out / entry["id"] / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {**base, "SKIPWATCH_HOME": str(home)}
    cmd = claude_command(entry, out, plugin_dir, cookies_from_env(base))
    vid = entry["id"]
    try:
        runner(cmd, env=env, timeout=CLAUDE_TIMEOUT_S, stdin=subprocess.DEVNULL, text=True)
    except subprocess.TimeoutExpired:
        return VideoResult(vid, False, f"{vid} FAIL timed out after {CLAUDE_TIMEOUT_S} s")
    report_path = _newest(list(home.glob("work/*/check-report.json")))
    if report_path is None:
        return VideoResult(vid, False, f"{vid} FAIL no check-report.json under {home / 'work'}")
    skill_path = report_path.parent / "staging" / skill_name(entry) / "SKILL.md"
    if not skill_path.exists():
        return VideoResult(vid, False, f"{vid} FAIL no staged draft at {skill_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    skill_md = skill_path.read_text(encoding="utf-8")
    problems = judge(report, skill_md, entry["expected"])
    installed = (out / vid / "skills" / skill_name(entry) / "SKILL.md").exists()
    line = result_line(vid, metrics(report, skill_md), problems, installed)
    return VideoResult(vid, not problems, line)


def engine_binary() -> str:
    """The `skipwatch` entry point of this interpreter's environment (cli.py has no __main__)."""
    local = Path(sys.executable).parent / "skipwatch"
    return str(local) if local.exists() else (shutil.which("skipwatch") or "skipwatch")


def run_engine_only(
    entry: dict[str, Any],
    out: Path,
    runner: Runner = subprocess.run,
    base_env: Mapping[str, str] | None = None,
) -> VideoResult:
    """ingest, transcribe, frames, plan in an isolated home; no Claude, no judging."""
    base = dict(os.environ if base_env is None else base_env)
    vid = entry["id"]
    home = out / vid / "home"
    work = home / "work" / vid.lower()
    work.parent.mkdir(parents=True, exist_ok=True)
    env = {**base, "SKIPWATCH_HOME": str(home)}
    engine = [engine_binary()]
    done = []
    for stage in ENGINE_STAGES:
        cmd = [*engine, stage]
        if stage == "ingest":
            cmd += [entry["url"]]
        cmd += ["--work", str(work)]
        try:
            proc = runner(cmd, env=env, timeout=STAGE_TIMEOUT_S, capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            return VideoResult(vid, False, f"{vid} ENGINE-FAIL {stage} timed out")
        if proc.returncode != 0:
            last = (proc.stderr or "").strip().splitlines()
            reason = last[-1] if last else ""
            line = f"{vid} ENGINE-FAIL {stage} exit={proc.returncode} {reason}".rstrip()
            return VideoResult(vid, False, line)
        done.append(stage)
    return VideoResult(vid, True, f"{vid} ENGINE-OK {' '.join(done)}")


def select(videos: list[dict[str, Any]], only: str | None) -> list[dict[str, Any]]:
    if not only:
        return videos
    wanted = [part.strip().upper() for part in only.split(",") if part.strip()]
    known = {video["id"] for video in videos}
    unknown = [vid for vid in wanted if vid not in known]
    if unknown:
        raise SystemExit(f"unknown golden id: {', '.join(unknown)}")
    return [video for video in videos if video["id"] in wanted]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="comma-separated ids, for example G1,G5")
    parser.add_argument("--out", type=Path, default=Path("/tmp/sw-golden"))
    parser.add_argument("--plugin-dir", type=Path, default=ROOT)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument(
        "--engine-only", action="store_true", help="run ingest to plan only (no Claude)"
    )
    args = parser.parse_args(argv)
    videos = select(json.loads(args.golden.read_text(encoding="utf-8"))["videos"], args.only)
    out = args.out.resolve()
    all_ok = True
    for entry in videos:
        if args.engine_only:
            result = run_engine_only(entry, out)
        else:
            result = run_video(entry, out, args.plugin_dir.resolve(), subprocess.run, None)
        all_ok = all_ok and result.ok
        print(result.line, flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
