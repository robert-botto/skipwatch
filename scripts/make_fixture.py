"""Generate the 60 s fixture (narration.wav, tutorial-60s.mp4, tutorial-60s.en.vtt).

Everything is built from tests/fixtures/tutorial-60s.script.json. macOS only: narration is
recorded with `say`. Always uses the static ffmpeg, because Homebrew ffmpeg has no `drawtext`
(plan issue 9). The outputs are committed, so CI never runs this script.

    uv run python scripts/make_fixture.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
SCRIPT = FIX / "tutorial-60s.script.json"
FONT = "/System/Library/Fonts/Menlo.ttc"
VOICE = "Samantha"
SAMPLE_RATE = 16000


def static_ffmpeg() -> tuple[str, str]:
    from static_ffmpeg import run

    ffmpeg, ffprobe = run.get_or_fetch_platform_executables_else_raise()
    return str(ffmpeg), str(ffprobe)


def has_filter(ffmpeg: str, name: str) -> bool:
    out = subprocess.run([ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True)
    return any(line.split()[1:2] == [name] for line in out.stdout.splitlines())


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def duration(ffprobe: str, path: Path) -> float:
    out = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(out.stdout.strip())


def record_sentences(ffmpeg: str, sentences: list[dict], tmp: Path) -> list[Path]:
    clips = []
    for i, s in enumerate(sentences):
        aiff = tmp / f"s{i}.aiff"
        wav = tmp / f"s{i}.wav"
        run(["say", "-v", VOICE, "-r", "170", "-o", str(aiff), s["text"]])
        run([ffmpeg, "-y", "-i", str(aiff), "-ar", str(SAMPLE_RATE), "-ac", "1", str(wav)])
        clips.append(wav)
    return clips


def check_clips_fit(sentences: list[dict], lengths: list[float], total: float) -> None:
    for i, (s, length) in enumerate(zip(sentences, lengths, strict=True)):
        limit = sentences[i + 1]["start"] if i + 1 < len(sentences) else total
        if s["start"] + length >= limit:
            sys.exit(f"sentence {i} ends at {s['start'] + length:.2f}s, after {limit:.2f}s")


def mix_narration(ffmpeg: str, clips: list[Path], sentences: list[dict], total: float) -> None:
    inputs = ["-f", "lavfi", "-t", str(total), "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono"]
    filters = []
    for i, (clip, s) in enumerate(zip(clips, sentences, strict=True)):
        inputs += ["-i", str(clip)]
        ms = round(s["start"] * 1000)
        filters.append(f"[{i + 1}:a]adelay={ms}|{ms}[d{i}]")
    labels = "[0:a]" + "".join(f"[d{i}]" for i in range(len(clips)))
    filters.append(f"{labels}amix=inputs={len(clips) + 1}:normalize=0:duration=first[out]")
    run(
        [ffmpeg, "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[out]"]
        + ["-t", str(total), "-ar", "8000", "-ac", "1", "-c:a", "pcm_u8"]
        + [str(FIX / "narration.wav")]
    )


def drawtext(textfile: Path, size: int, y: int, enable: str | None) -> str:
    parts = [
        f"fontfile={FONT}",
        f"textfile={textfile}",
        "expansion=none",
        f"fontsize={size}",
        "fontcolor=white",
        "x=60",
        f"y={y}",
    ]
    if enable:
        parts.append(f"enable='{enable}'")
    return "drawtext=" + ":".join(parts)


def render_video(ffmpeg: str, cues: list[dict], total: float, tmp: Path) -> None:
    title = tmp / "title.txt"
    title.write_text("skipdemo tutorial", encoding="utf-8")
    chain = [drawtext(title, 28, 40, None)]
    for i, cue in enumerate(cues):
        textfile = tmp / f"cue{i}.txt"
        textfile.write_text(cue["text"], encoding="utf-8")
        size = 40 if len(cue["text"]) <= 50 else 30
        chain.append(drawtext(textfile, size, 320, f"between(t,{cue['start']},{cue['end']})"))
    run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c=0x1e1e1e:s=1280x720:d={total}:r=10"]
        + ["-i", str(FIX / "narration.wav"), "-vf", ",".join(chain)]
        + ["-c:v", "libx264", "-crf", "30", "-preset", "veryslow", "-pix_fmt", "yuv420p"]
        + ["-c:a", "aac", "-b:a", "48k", "-t", str(total), "-movflags", "+faststart"]
        + [str(FIX / "tutorial-60s.mp4")]
    )


def vtt_time(t: float) -> str:
    ms = round(t * 1000)
    h, rest = divmod(ms, 3_600_000)
    m, rest = divmod(rest, 60_000)
    s, ms = divmod(rest, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def write_vtt(sentences: list[dict], lengths: list[float], total: float) -> None:
    lines = ["WEBVTT", ""]
    for i, (s, length) in enumerate(zip(sentences, lengths, strict=True)):
        limit = sentences[i + 1]["start"] - 0.1 if i + 1 < len(sentences) else total
        end = min(s["start"] + length, limit)
        lines += [f"{vtt_time(s['start'])} --> {vtt_time(end)}", s["text"], ""]
    (FIX / "tutorial-60s.en.vtt").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    if sys.platform != "darwin":
        sys.exit("make_fixture.py needs macOS `say`")
    script = json.loads(SCRIPT.read_text(encoding="utf-8"))
    total = float(script["duration_s"])
    sentences, cues = script["sentences"], script["cues"]
    ffmpeg, ffprobe = static_ffmpeg()
    if not has_filter(ffmpeg, "drawtext"):
        sys.exit(f"{ffmpeg} has no drawtext filter")
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        clips = record_sentences(ffmpeg, sentences, tmp)
        lengths = [duration(ffprobe, c) for c in clips]
        check_clips_fit(sentences, lengths, total)
        mix_narration(ffmpeg, clips, sentences, total)
        render_video(ffmpeg, cues, total, tmp)
        write_vtt(sentences, lengths, total)
    for name in ("narration.wav", "tutorial-60s.mp4", "tutorial-60s.en.vtt"):
        print(f"{name}: {(FIX / name).stat().st_size} bytes", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
