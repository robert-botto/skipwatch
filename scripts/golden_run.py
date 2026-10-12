"""Run the golden set through SkipWatch and diff each staged draft against its expected ranges.

Usage:
  uv run python scripts/golden_run.py [--only G1,G5] [--out DIR] [--plugin-dir .]
  uv run python scripts/golden_run.py --engine-only --only G1 --out DIR

The full run calls `claude -p` once per video (paid, run by hand). Each video gets its own
SKIPWATCH_HOME under <out>/<id>/home. Judging reads that home's newest check-report.json and
staged SKILL.md, installed or not (M2-M4 issue 16). Downloaded media and frames are
deleted after each video unless `--keep-media` is given. `--engine-only` runs just the stages that
need no Claude (probe, ingest, transcribe, frames, plan) on the free provider and judges
nothing; `--stages` picks a subset.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from skipwatch.skillmd import _split_frontmatter, fenced_lines

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLDEN = ROOT / "tests" / "golden" / "golden.json"
CLAUDE_TIMEOUT_S = 30 * 60
STAGE_TIMEOUT_S = 30 * 60
ENGINE_STAGES = ("probe", "ingest", "transcribe", "frames", "plan")
COOKIE_ENV = "SKIPWATCH_GOLDEN_COOKIES"
# Below this many steps the inferred ratio ceiling is replaced by an absolute count.
SMALL_SKILL_STEPS = 6
SMALL_SKILL_INFERRED_MAX = 1
COOKIE_BROWSERS = {"chrome"}

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass
class VideoResult:
    id: str
    ok: bool
    line: str


def illegible_total(skill_md: str) -> int:
    """Every `[illegible at` marker in the body, counted as checks/runner.counts_for does."""
    _, body, _, _ = _split_frontmatter(skill_md)
    return body.count("[illegible at")


def illegible_in_quotes(skill_md: str) -> int:
    """`[illegible` markers inside quotes: blockquote lines and closed fenced blocks (S3).

    This reimplements quote detection on purpose: the engine's counts.illegible counts every
    marker in the body, prose and "Unverified and gaps" included, while S3 only forbids
    markers inside quoted source text. judge() cross-checks the total against counts.illegible
    so the two readings of the draft cannot drift apart unnoticed.
    """
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
        "inferred_steps": inferred,
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
    if m["steps"] < SMALL_SKILL_STEPS:
        # One honest [inferred] step in a 3-step skill is already 0.33: ratios are noise here.
        if m["inferred_steps"] > SMALL_SKILL_INFERRED_MAX:
            problems.append(
                f"inferred={m['inferred_steps']} steps "
                f"(want <={SMALL_SKILL_INFERRED_MAX} below {SMALL_SKILL_STEPS} steps)"
            )
    elif m["inferred"] > expected["inferred_ratio_max"]:
        problems.append(
            f"inferred={m['inferred']:.2f} (want <={expected['inferred_ratio_max']:.2f})"
        )
    reported = report.get("counts", {}).get("illegible")
    if reported is not None and illegible_total(skill_md) != reported:
        problems.append(
            f"illegible_total={illegible_total(skill_md)} (report counts.illegible={reported})"
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
    # Prompt right after -p: --allowedTools is variadic and would swallow a later prompt.
    return [
        "claude",
        "-p",
        prompt,
        "--plugin-dir",
        str(plugin_dir),
        "--allowedTools",
        "Bash,Read,Write,Agent",
    ]


def _newest(paths: list[Path]) -> Path | None:
    return max(paths, key=lambda p: p.stat().st_mtime) if paths else None


def remove_media(home: Path) -> None:
    """Delete fetched video and extracted frames under home/work/*; judging inputs stay."""
    for folder in [*home.glob("work/*/media"), *home.glob("work/*/frames")]:
        if folder.is_dir():
            shutil.rmtree(folder)


def run_video(
    entry: dict[str, Any],
    out: Path,
    plugin_dir: Path,
    runner: Runner = subprocess.run,
    base_env: Mapping[str, str] | None = None,
    keep_media: bool = False,
) -> VideoResult:
    """One full Claude run, judged; media and frames are deleted afterwards unless kept."""
    try:
        return _run_video(entry, out, plugin_dir, runner, base_env)
    finally:
        if not keep_media:
            remove_media(out / entry["id"] / "home")


def _run_video(
    entry: dict[str, Any],
    out: Path,
    plugin_dir: Path,
    runner: Runner,
    base_env: Mapping[str, str] | None,
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


def _engine_summary(work: Path, probe: dict[str, Any]) -> str:
    """What the stages produced, read back from the work folder; absent files are skipped."""

    def load(name: str) -> dict[str, Any] | None:
        path = work / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    parts = []
    if probe:
        duration = probe.get("duration_s")
        parts.append(f"duration={round(duration)}s" if duration else "duration=?")
        parts.append(f"long_video={'yes' if probe.get('long_video') else 'no'}")
    transcript = load("transcript.json")
    if transcript:
        silent = " silent" if transcript.get("silent") else ""
        parts.append(f"origin={transcript['origin']}{silent}")
        parts.append(f"segments={len(transcript['segments'])}")
    frames = load("frames.json")
    if frames:
        parts.append(f"frames={len(frames['frames'])}")
    batches = load("batches.json")
    if batches:
        parts.append(f"batches={len(batches['batches'])}")
    return " ".join(parts)


def run_engine_only(
    entry: dict[str, Any],
    out: Path,
    runner: Runner = subprocess.run,
    base_env: Mapping[str, str] | None = None,
    stages: list[str] | None = None,
    keep_media: bool = False,
) -> VideoResult:
    """probe, ingest, transcribe, frames, plan in an isolated home on the free provider.

    No Claude, no cookies, no judging. `stages` runs a subset in order (for example
    probe, ingest and frames for a video no transcription backend can handle yet).
    Media and frames are deleted afterwards unless kept.
    """
    try:
        return _run_engine_only(entry, out, runner, base_env, stages)
    finally:
        if not keep_media:
            remove_media(out / entry["id"] / "home")


def _run_engine_only(
    entry: dict[str, Any],
    out: Path,
    runner: Runner,
    base_env: Mapping[str, str] | None,
    stages: list[str] | None,
) -> VideoResult:
    base = dict(os.environ if base_env is None else base_env)
    vid = entry["id"]
    home = out / vid / "home"
    work = home / "work" / vid.lower()
    work.parent.mkdir(parents=True, exist_ok=True)
    env = {**base, "SKIPWATCH_HOME": str(home)}
    timings: list[str] = []
    probe: dict[str, Any] = {}
    for stage in [s for s in ENGINE_STAGES if stages is None or s in stages]:
        cmd = [engine_binary(), stage]
        if stage == "probe":
            cmd += [entry["url"], "--json"]
        elif stage == "ingest":
            cmd += [entry["url"], "--work", str(work), "--provider", "free"]
        else:
            cmd += ["--work", str(work)]
        started = time.monotonic()
        try:
            proc = runner(cmd, env=env, timeout=STAGE_TIMEOUT_S, capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            return VideoResult(vid, False, f"{vid} ENGINE-FAIL {stage} timed out")
        timings.append(f"{stage}={proc.returncode}/{time.monotonic() - started:.1f}s")
        if proc.returncode != 0:
            last = (proc.stderr or "").strip().splitlines()
            reason = last[-1] if last else ""
            line = f"{vid} ENGINE-FAIL {stage} exit={proc.returncode} {' '.join(timings)} {reason}"
            return VideoResult(vid, False, line.rstrip())
        if stage == "probe":
            probe = json.loads(proc.stdout or "{}")
    summary = _engine_summary(work, probe)
    return VideoResult(vid, True, f"{vid} ENGINE-OK {' '.join(timings)} {summary}".rstrip())


def write_setup_files(spec: dict[str, Any], directory: Path) -> None:
    """Write a task's setup_files (s2 or s3) into the scratch dir before the fresh session."""
    for name, text in (spec.get("setup_files") or {}).items():
        parts = PurePosixPath(name).parts
        if not name or PurePosixPath(name).is_absolute() or ".." in parts or "\\" in name:
            raise ValueError(f"setup file {name!r} escapes {directory}")
        target = directory.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def prepare(entry: dict[str, Any], directory: Path) -> str:
    """Write the entry's fresh-session setup files and return its task text."""
    spec = entry.get("s2") or entry.get("s3")
    if spec is None:
        raise SystemExit(f"{entry['id']} has no s2 or s3 task")
    directory.mkdir(parents=True, exist_ok=True)
    write_setup_files(spec, directory)
    return spec["task"]


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
        "--engine-only", action="store_true", help="run probe to plan only (no Claude)"
    )
    parser.add_argument(
        "--keep-media",
        action="store_true",
        help="keep downloaded media and frames under <out>/<id>/home/work (default: delete)",
    )
    parser.add_argument(
        "--stages", help="with --engine-only: comma-separated subset, for example probe,ingest"
    )
    parser.add_argument(
        "--prepare",
        metavar="ID",
        help="write that entry's s2/s3 setup files into --dir and print its task",
    )
    parser.add_argument("--dir", type=Path, help="scratch dir for --prepare")
    args = parser.parse_args(argv)
    if args.prepare:
        if args.dir is None:
            parser.error("--prepare needs --dir")
        (entry,) = select(
            json.loads(args.golden.read_text(encoding="utf-8"))["videos"], args.prepare
        )
        print(prepare(entry, args.dir))
        return 0
    videos = select(json.loads(args.golden.read_text(encoding="utf-8"))["videos"], args.only)
    out = args.out.resolve()
    all_ok = True
    for entry in videos:
        if args.engine_only:
            stages = args.stages.split(",") if args.stages else None
            if stages and set(stages) - set(ENGINE_STAGES):
                raise SystemExit(f"--stages takes {','.join(ENGINE_STAGES)}")
            result = run_engine_only(entry, out, stages=stages, keep_media=args.keep_media)
        else:
            result = run_video(
                entry,
                out,
                args.plugin_dir.resolve(),
                subprocess.run,
                None,
                keep_media=args.keep_media,
            )
        all_ok = all_ok and result.ok
        print(result.line, flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
