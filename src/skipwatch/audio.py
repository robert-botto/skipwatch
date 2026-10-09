"""Audio for transcription: 16 kHz mono WAV from the media, and MP3 chunks for cloud uploads.

Whisper backends get the decoded WAV (mlx as a float32 array, plan issue 13), so mlx-whisper
never shells out to an `ffmpeg` on PATH that a static-ffmpeg machine may not have.
"""

import math
import subprocess
import wave
from pathlib import Path
from typing import TYPE_CHECKING

from skipwatch import media
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import IngestBundle
from skipwatch.workdir import WorkDir

if TYPE_CHECKING:
    import numpy

AUDIO_NAME = "audio-16k.wav"
SAMPLE_RATE = 16000


def media_path(work: WorkDir, bundle: IngestBundle) -> Path:
    """Absolute for local files, work-relative for downloads."""
    if bundle.media is None:
        raise SkipwatchError(ExitCode.NO_CONTENT, "ingest found no media to transcribe")
    path = Path(bundle.media.path)
    return path if path.is_absolute() else work.path / path


def _ffmpeg(args: list[str]) -> None:
    ffmpeg, _ = media.ffmpeg_paths()
    out = subprocess.run(
        [str(ffmpeg), "-v", "error", "-y", *args], capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        raise SkipwatchError(
            ExitCode.NO_CONTENT, f"ffmpeg could not extract audio: {out.stderr.strip()[-300:]}"
        )


def extract_audio(work: WorkDir, bundle: IngestBundle) -> Path:
    """Write media/audio-16k.wav (16 kHz mono PCM s16le); reuse it when newer than the media."""
    source = media_path(work, bundle)
    out = work.file("media") / AUDIO_NAME
    if out.exists() and out.stat().st_mtime_ns >= source.stat().st_mtime_ns:
        return out
    streams = media.probe(source).get("streams", [])
    if not any(s.get("codec_type") == "audio" for s in streams):
        raise SkipwatchError(ExitCode.NO_CONTENT, "the video has no audio track")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".tmp.wav")
    _ffmpeg(["-i", str(source), "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
             "-c:a", "pcm_s16le", str(tmp)])  # fmt: skip
    tmp.replace(out)
    return out


def audio_duration(wav: Path) -> float:
    with wave.open(str(wav)) as f:
        return f.getnframes() / f.getframerate()


def load_wav_float32(path: Path) -> "numpy.ndarray":
    import numpy as np

    with wave.open(str(path)) as f:
        frames = f.readframes(f.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0


def encode_mp3_chunks(
    wav: Path, out_dir: Path, chunk_s: int = 3000, kbps: int = 32
) -> list[tuple[Path, float]]:
    """MP3 pieces of at most chunk_s seconds, each with its start offset in seconds."""
    out_dir.mkdir(parents=True, exist_ok=True)
    count = max(1, math.ceil(audio_duration(wav) / chunk_s))
    chunks = []
    for n in range(count):
        start = float(n * chunk_s)
        path = out_dir / f"chunk-{n:03d}.mp3"
        _ffmpeg(["-ss", str(start), "-t", str(chunk_s), "-i", str(wav), "-ac", "1",
                 "-ar", str(SAMPLE_RATE), "-b:a", f"{kbps}k", str(path)])  # fmt: skip
        chunks.append((path, start))
    return chunks
