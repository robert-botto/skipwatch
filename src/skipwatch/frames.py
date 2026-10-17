"""Frame sampling (spec 8.5): scene frames, dedup, cue frames and the frame budget.

Scene frames come from one ffmpeg run at 1 fps through mpdecimate, so a still screen yields
one frame at the moment it appeared and then nothing until it changes. Dedup keeps the last
frame of each run of near-duplicates (finished code, not half-typed), and also the first frame
of any run lasting HELD_SECONDS or more: that frame is the appearance of held text, and the
last frame of its run can be far later (Review Focus 3). Run length is measured from the
run's first to last frame, so it holds both when mpdecimate dropped the still frames and when
a blinking cursor kept every 1 s frame.

Two frames are duplicates when under DUP_FRACTION of their pixels changed by more than
PIXEL_DELTA on a 320x180 grayscale thumbnail. A 64-bit dHash cannot see a new line of code
(measured distance 0 to 7 for real changes), so it is kept only as the frames.json field.
Measured fractions: noise 0.00014, a few typed characters 0.0004 to 0.00056, a new line of
code 0.0059 to 0.0072, command output 0.0031.
"""

import math
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from PIL import Image, ImageChops

from skipwatch.config import load_config
from skipwatch.dhash import dhash
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.media import ffmpeg_paths, probe
from skipwatch.models import Frame, FramesFile, IngestBundle, Sampling, Transcript
from skipwatch.workdir import WorkDir, read_model, run_stage, write_model

HELD_SECONDS = 3.0
COVERAGE_WINDOW_S = 90.0
DUP_FRACTION = 0.001
PIXEL_DELTA = 32
THUMB_SIZE = (320, 180)
DENSE_PER_MINUTE = 6
DEFAULT_CUE_TERMS = ["paste", "prompt", "settings", "click", "type", "run", "copy"]
CUE_LEAD_S = 2.0
CUE_TAIL_S = 3.0  # spoken cues come about 1 s before the text shows, so look 3 s ahead
CUE_STEP_S = 0.5

_PTS_RE = re.compile(r"pts_time:\s*(-?[\d.]+)")


@dataclass
class Candidate:
    t: float
    path: Path
    reason: Literal["scene", "cue", "spread"]
    dhash: str
    thumb: Image.Image | None = field(default=None, repr=False, compare=False)


def thumbnail(source: Path | Image.Image) -> Image.Image:
    """Grayscale 320x180 BOX downscale used for duplicate detection."""
    if isinstance(source, Image.Image):
        return source.convert("L").resize(THUMB_SIZE, Image.Resampling.BOX)
    with Image.open(source) as img:
        return img.convert("L").resize(THUMB_SIZE, Image.Resampling.BOX)


def changed_fraction(a: Image.Image, b: Image.Image) -> float:
    """Fraction of pixels whose gray level differs by more than PIXEL_DELTA."""
    histogram = ImageChops.difference(a, b).histogram()
    return sum(histogram[PIXEL_DELTA + 1 :]) / (a.width * a.height)


def _thumb(cand: Candidate) -> Image.Image:
    return cand.thumb if cand.thumb is not None else thumbnail(cand.path)


def _changed_flags(cands: list[Candidate]) -> list[bool]:
    """flags[i]: candidate i differs from candidate i + 1. Two thumbnails in memory at a time."""
    flags: list[bool] = []
    current = _thumb(cands[0]) if cands else None
    for nxt in cands[1:]:
        following = _thumb(nxt)
        assert current is not None
        flags.append(changed_fraction(current, following) >= DUP_FRACTION)
        current = following
    return flags


def frame_id(t: float) -> str:
    """Deciseconds since the start (plan issue 13): t=123.0 gives f001230."""
    return f"f{round(t * 10):06d}"


def budget(duration_s: float, per_minute: int, max_frames: int) -> int:
    return min(max_frames, max(1, math.ceil(per_minute * duration_s / 60)))


def dedup_runs(cands: list[Candidate]) -> list[Candidate]:
    """Collapse runs of near-duplicate scene frames; cue frames pass through untouched.

    A run is consecutive scene frames each a duplicate of the previous one (under DUP_FRACTION
    changed). Each run keeps its last frame, and its first frame too when the run lasts
    HELD_SECONDS or more (first to last frame).
    """
    ordered = sorted(cands, key=lambda c: c.t)
    scenes = [c for c in ordered if c.reason != "cue"]
    changed = _changed_flags(scenes)
    keep: set[int] = set()
    run_start = 0
    for i in range(len(scenes)):
        if i + 1 == len(scenes) or changed[i]:  # i ends a run
            keep.add(i)
            if scenes[i].t - scenes[run_start].t >= HELD_SECONDS:
                keep.add(run_start)  # held on screen: the appearance of static text
            run_start = i + 1
    kept_ids = {id(scenes[i]) for i in keep}
    return [c for c in ordered if c.reason == "cue" or id(c) in kept_ids]


def _term_pattern(terms: list[str]) -> re.Pattern[str] | None:
    if not terms:
        return None
    alternatives = "|".join(re.escape(t) for t in terms)
    return re.compile(rf"\b(?:{alternatives})\b", re.IGNORECASE)


def cue_times(transcript: Transcript, terms: list[str]) -> list[float]:
    """Times of spoken cue terms: word timestamps when present, else the segment start."""
    pattern = _term_pattern(terms)
    if pattern is None:
        return []
    times: set[float] = set()
    for seg in transcript.segments:
        if seg.words:
            times.update(w.s for w in seg.words if pattern.search(w.w))
        elif pattern.search(seg.text):
            times.add(seg.start)
    return sorted(times)


def _even_subset(items: list[Candidate], k: int) -> list[Candidate]:
    """k items evenly spaced through items (which are sorted by time)."""
    m = len(items)
    if k >= m:
        return list(items)
    if k <= 0:
        return []
    if k == 1:
        return [items[m // 2]]
    step = (m - 1) / (k - 1)  # > 1 because m > k, so rounded indices never repeat
    return [items[round(i * step)] for i in range(k)]


def _windows(cands: list[Candidate], count: int, duration: float) -> list[list[Candidate]]:
    """Split time-sorted candidates into `count` equal time windows over [0, duration]."""
    width = duration / count
    out: list[list[Candidate]] = [[] for _ in range(count)]
    for cand in cands:
        out[min(count - 1, int(cand.t // width))].append(cand)
    return out


def _most_different(cands: list[Candidate], ref: Image.Image) -> Candidate:
    return max(cands, key=lambda c: changed_fraction(ref, _thumb(c)))


def _distinct_cues(cues: list[Candidate], k: int, duration: float) -> list[Candidate]:
    """k cue frames spread over time: one per equal time slot, the one that differs most from
    the previous pick (a new slide or new text, not the same screen again), then an even top-up
    from the rest when some slots hold no cue."""
    if k >= len(cues):
        return list(cues)
    if k <= 0:
        return []
    picks: list[Candidate] = []
    previous = None
    for slot in _windows(cues, k, duration):
        if not slot:
            continue
        best = slot[0] if previous is None else _most_different(slot, previous)
        picks.append(best)
        previous = _thumb(best)
    chosen = {id(c) for c in picks}
    rest = [c for c in cues if id(c) not in chosen]
    return sorted(picks + _even_subset(rest, k - len(picks)), key=lambda c: c.t)


def select(
    cands: list[Candidate], n: int, max_frames: int | None = None, duration: float | None = None
) -> list[Candidate]:
    """Pick at most max_frames frames (R-FR-2): coverage first, then cues, then scenes.

    - Cue frames bypass the per-minute budget n (spec 3.4), but fill at most half of
      max_frames while scene frames can use the other half: common words ("run", "type") in a
      long talk must not crowd out the slides. Over that share they are cut to a temporal
      subset that prefers frames differing most from the previous pick.
    - Temporal coverage: the video is split into equal windows (one per COVERAGE_WINDOW_S,
      at most max_frames / 2), and every window with a candidate keeps one frame, a scene
      frame when it has one, else a cue frame.
    - Scene frames then fill what n leaves after the cues, never fewer than a floor of
      ceil(n / 3) in total, evenly spread.
    max_frames defaults to n; duration defaults to the last candidate's time.
    """
    cap = n if max_frames is None else max_frames
    by_id: dict[str, Candidate] = {}
    for cand in sorted(cands, key=lambda c: (c.t, c.reason != "cue")):
        by_id.setdefault(frame_id(cand.t), cand)  # one frame per id; a cue wins a tie
    unique = list(by_id.values())
    if not unique or cap <= 0:
        return []
    span = max(duration or 0.0, unique[-1].t + 1e-6)
    cues = [c for c in unique if c.reason == "cue"]
    others = [c for c in unique if c.reason != "cue"]

    cue_limit = max(cap // 2, cap - len(others))
    kept_cues = _distinct_cues(cues, cue_limit, span)
    kept_ids = {id(c) for c in kept_cues}

    n_windows = max(1, min(math.ceil(span / COVERAGE_WINDOW_S), cap // 2))
    coverage: list[Candidate] = []
    for window in _windows(unique, n_windows, span):
        scenes_here = [c for c in window if c.reason != "cue"]
        if scenes_here:
            coverage.append(scenes_here[len(scenes_here) // 2])
        elif window and not any(id(c) in kept_ids for c in window):
            coverage.append(window[len(window) // 2])  # a cue frame the share cap had cut
    coverage = coverage[: max(0, cap - len(kept_cues))]
    taken = kept_ids | {id(c) for c in coverage}

    floor = min(math.ceil(n / 3), len(others))
    covered_scenes = sum(1 for c in coverage if c.reason != "cue")
    room = cap - len(kept_cues) - len(coverage)
    want = max(n - len(kept_cues), floor) - covered_scenes
    rest = [c for c in others if id(c) not in taken]
    extra = _even_subset(rest, max(0, min(room, want)))
    return sorted(kept_cues + coverage + extra, key=lambda c: c.t)


def _run_ffmpeg(cmd: list[str], cwd: Path, video: Path) -> str:
    # cwd is the output folder so the image2 pattern never contains a user path (a "%" in a
    # folder name would be read as a pattern). -nostdin: no command reads stdin (R-CLI-3).
    out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if out.returncode != 0:
        tail = out.stderr.strip().splitlines()[-1:] or ["no output"]
        raise SkipwatchError(
            ExitCode.NO_CONTENT, f"ffmpeg could not read frames from {video}: {tail[0]}"
        )
    return out.stderr


def _hash_file(path: Path) -> str:
    with Image.open(path) as img:
        return dhash(img)


def sample_scene(ffmpeg: Path, video: Path, out_dir: Path) -> list[Candidate]:
    """1 fps through mpdecimate, scaled to 1280 wide; timestamps from showinfo on stderr."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stderr = _run_ffmpeg(
        [str(ffmpeg), "-hide_banner", "-nostdin", "-i", str(video.resolve()),
         "-vf", "fps=1,mpdecimate,scale=1280:-2,showinfo", "-fps_mode", "vfr",
         "-q:v", "3", "raw-%06d.jpg"],
        out_dir, video,
    )  # fmt: skip
    times = [
        float(m.group(1))
        for line in stderr.splitlines()
        if "showinfo" in line and (m := _PTS_RE.search(line))
    ]
    files = sorted(out_dir.glob("raw-*.jpg"))
    if len(times) != len(files):
        raise SkipwatchError(
            ExitCode.NO_CONTENT,
            f"ffmpeg wrote {len(files)} frames but logged {len(times)} timestamps for {video}",
        )
    return [
        Candidate(t=round(t, 3), path=f, reason="scene", dhash=_hash_file(f))
        for t, f in zip(times, files, strict=True)
    ]


def sample_cues(
    ffmpeg: Path, video: Path, out_dir: Path, times: list[float], duration: float
) -> list[Candidate]:
    """2 fps from 2 s before to 3 s after each cue, keeping one frame per on-screen change.

    Within a window a frame is kept when it differs from the frame before it (the moment new
    text shows). A window with no change keeps the frame nearest the cue. Overlapping windows
    never repeat a frame id.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    cands: list[Candidate] = []
    for i, cue in enumerate(times):
        start = max(0.0, cue - CUE_LEAD_S)
        span = min(cue + CUE_TAIL_S, duration) - start
        if span <= 0:
            continue
        prefix = f"cue-{i:04d}-"
        _run_ffmpeg(
            [str(ffmpeg), "-hide_banner", "-nostdin", "-ss", f"{start:.3f}",
             "-i", str(video.resolve()), "-t", f"{span:.3f}",
             "-vf", "fps=2,scale=1280:-2", "-q:v", "3", f"{prefix}%03d.jpg"],
            out_dir, video,
        )  # fmt: skip
        window = [
            Candidate(t=round(start + k * CUE_STEP_S, 3), path=path, reason="cue", dhash="")
            for k, path in enumerate(sorted(out_dir.glob(f"{prefix}*.jpg")))
        ]
        window = [c for c in window if c.t <= duration]
        if not window:
            continue
        changed = _changed_flags(window)
        kept = [c for c, flag in zip(window[1:], changed, strict=True) if flag]
        if not kept:
            kept = [min(window, key=lambda c: (abs(c.t - cue), c.t))]
        for cand in kept:
            fid = frame_id(cand.t)
            if fid in seen:
                continue
            seen.add(fid)
            cand.dhash = _hash_file(cand.path)
            cands.append(cand)
    return sorted(cands, key=lambda c: c.t)


def transcript_window(transcript: Transcript, t: float, half: float = 6.0) -> str:
    """Text of every segment overlapping [t - half, t + half], joined by spaces."""
    lo, hi = t - half, t + half
    parts = [s.text.strip() for s in transcript.segments if s.end >= lo and s.start <= hi]
    return " ".join(p for p in parts if p)


def _duration(ingest: IngestBundle, video: Path) -> float:
    if ingest.source.duration_s:
        return ingest.source.duration_s
    value = probe(video).get("format", {}).get("duration")
    if value is None:
        raise SkipwatchError(ExitCode.NO_CONTENT, f"could not read the duration of {video}")
    return float(value)


def run_frames(
    work: WorkDir, per_minute: int | None, max_frames: int | None, dense: bool
) -> FramesFile:
    """Sample, dedup and budget frames; write frames/<id>.jpg and frames.json (R-CLI-1)."""

    def stage() -> FramesFile:
        ingest_path = work.file("ingest.json")
        if not ingest_path.exists():
            raise SkipwatchError(ExitCode.NO_CONTENT, f"no ingest.json in {work.path}")
        ingest = read_model(ingest_path, IngestBundle)
        transcript_path = work.file("transcript.json")
        transcript = read_model(transcript_path, Transcript) if transcript_path.exists() else None
        cfg = load_config().frames
        silent = transcript.silent if transcript else False
        if per_minute is not None:
            pm = per_minute
        elif dense or silent:
            pm = DENSE_PER_MINUTE
        else:
            pm = cfg.per_minute
        terms = list(DEFAULT_CUE_TERMS)
        sampling = Sampling(per_minute=pm, max=max_frames or cfg.max, dense=dense, cue_terms=terms)
        frames_dir = work.file("frames")
        shutil.rmtree(frames_dir, ignore_errors=True)  # stale frames never survive a rerun
        frames_dir.mkdir(parents=True)
        frames: list[Frame] = []
        # No video stream (no media, an audio source, or a local .wav ingested as kind "file"
        # with no width): nothing to sample, so frames.json is written empty.
        media = ingest.media
        if media is not None and media.width is not None and ingest.source.kind != "audio":
            video = Path(media.path)
            video = video if video.is_absolute() else work.path / video
            ffmpeg, _ = ffmpeg_paths(allow_fetch=True)
            duration = _duration(ingest, video)
            times = cue_times(transcript, terms) if transcript else []
            with tempfile.TemporaryDirectory(prefix="skipwatch-frames-") as raw:
                cues = sample_cues(ffmpeg, video, Path(raw) / "cue", times, duration)
                cue_ids = {frame_id(c.t) for c in cues}
                scenes = [
                    c
                    for c in sample_scene(ffmpeg, video, Path(raw) / "scene")
                    if frame_id(c.t) not in cue_ids
                ]
                chosen = select(
                    dedup_runs(scenes + cues),
                    budget(duration, pm, sampling.max),
                    sampling.max,
                    duration,
                )
                for cand in chosen:
                    fid = frame_id(cand.t)
                    shutil.copyfile(cand.path, frames_dir / f"{fid}.jpg")
                    window = transcript_window(transcript, cand.t) if transcript else ""
                    frames.append(
                        Frame(
                            id=fid,
                            t=cand.t,
                            path=f"frames/{fid}.jpg",
                            reason=cand.reason,
                            transcript_window=window,
                            dhash=cand.dhash,
                        )
                    )
        result = FramesFile(sampling=sampling, frames=frames)
        write_model(work.file("frames.json"), result)
        return result

    return run_stage(work, "frames", stage)
