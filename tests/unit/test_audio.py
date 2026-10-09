import os
import subprocess
import wave
from pathlib import Path

import pytest

from skipwatch.audio import audio_duration, encode_mp3_chunks, extract_audio, load_wav_float32
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import IngestBundle, MediaInfo, Route, SourceInfo
from tests.unit._media import needs_ffmpeg


def make_av(path: Path, seconds: float, audio: bool = True) -> Path:
    inputs = ["-f", "lavfi", "-i", f"testsrc=size=160x120:rate=5:duration={seconds}"]
    if audio:
        inputs += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=44100:duration={seconds}"]
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *inputs, "-pix_fmt", "yuv420p", "-shortest", str(path)],
        check=True,
    )
    return path


def work_for(tmp_path: Path, media_path: str, has_audio: bool = True):
    from skipwatch.workdir import WorkDir

    w = WorkDir(tmp_path / "w")
    w.ensure()
    (w.path / "media").mkdir(exist_ok=True)
    bundle = IngestBundle(
        source=SourceInfo(kind="file", platform="local", path=media_path),
        media=MediaInfo(path=media_path, has_audio=has_audio),
        route=Route(context="local", media="local"),
    )
    return w, bundle


@needs_ffmpeg
def test_extract_audio_16k_mono(tmp_path):
    video = make_av(tmp_path / "a.mp4", 2)
    w, bundle = work_for(tmp_path, str(video))
    wav = extract_audio(w, bundle)
    assert wav == w.path / "media" / "audio-16k.wav"
    with wave.open(str(wav)) as f:
        assert f.getnchannels() == 1 and f.getframerate() == 16000 and f.getsampwidth() == 2
        assert abs(f.getnframes() - 32000) < 1600
    assert abs(audio_duration(wav) - 2.0) < 0.1


@needs_ffmpeg
def test_extract_audio_work_relative_media_path(tmp_path):
    w, bundle = work_for(tmp_path, "media/clip.mp4")
    make_av(w.path / "media" / "clip.mp4", 1)
    assert extract_audio(w, bundle).exists()


@needs_ffmpeg
def test_extract_audio_is_reused(tmp_path):
    video = make_av(tmp_path / "a.mp4", 1)
    w, bundle = work_for(tmp_path, str(video))
    wav = extract_audio(w, bundle)
    before = wav.stat().st_mtime_ns
    assert extract_audio(w, bundle) == wav
    assert wav.stat().st_mtime_ns == before


@needs_ffmpeg
def test_extract_audio_redone_when_media_is_newer(tmp_path):
    video = make_av(tmp_path / "a.mp4", 1)
    w, bundle = work_for(tmp_path, str(video))
    wav = extract_audio(w, bundle)
    old = wav.stat().st_mtime_ns - 10_000_000_000
    os.utime(wav, ns=(old, old))
    extract_audio(w, bundle)
    assert wav.stat().st_mtime_ns > old


@needs_ffmpeg
def test_no_audio_track_is_exit_7(tmp_path):
    video = make_av(tmp_path / "mute.mp4", 1, audio=False)
    w, bundle = work_for(tmp_path, str(video))
    with pytest.raises(SkipwatchError) as e:
        extract_audio(w, bundle)
    assert e.value.code == ExitCode.NO_CONTENT and "no audio track" in e.value.message
    assert not (w.path / "media" / "audio-16k.wav").exists()


def test_no_media_is_exit_7(tmp_path):
    w, bundle = work_for(tmp_path, "media/x.mp4")
    with pytest.raises(SkipwatchError) as e:
        extract_audio(w, bundle.model_copy(update={"media": None}))
    assert e.value.code == ExitCode.NO_CONTENT


def test_load_wav_float32_scales_int16(tmp_path):
    wav = tmp_path / "s.wav"
    with wave.open(str(wav), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes((16384).to_bytes(2, "little", signed=True) * 3)
        f.writeframes((-32768).to_bytes(2, "little", signed=True))
    arr = load_wav_float32(wav)
    assert str(arr.dtype) == "float32"
    assert arr.tolist() == [0.5, 0.5, 0.5, -1.0]


@needs_ffmpeg
def test_mp3_chunks_offsets(tmp_path):
    wav = tmp_path / "long.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
         "sine=frequency=300:sample_rate=16000:duration=130", "-ac", "1", str(wav)],
        check=True,
    )  # fmt: skip
    chunks = encode_mp3_chunks(wav, tmp_path / "chunks", chunk_s=60)
    assert [offset for _, offset in chunks] == [0.0, 60.0, 120.0]
    assert all(p.suffix == ".mp3" and p.stat().st_size > 0 for p, _ in chunks)
    from skipwatch import media

    last = media.probe(chunks[-1][0])
    assert abs(float(last["format"]["duration"]) - 10.0) < 0.5
