import os
import subprocess
import sys
import types
import wave
from dataclasses import dataclass

import pytest
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.doctor import extra_command
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import IngestBundle, MediaInfo, Route, SourceInfo, Transcript
from skipwatch.providers import transcribe_faster, transcribe_mlx
from skipwatch.providers.registry import transcription_backends
from skipwatch.providers.transcribe_faster import FasterWhisperBackend
from skipwatch.providers.transcribe_mlx import MlxWhisperBackend
from skipwatch.transcribe import select_backend
from skipwatch.workdir import WorkDir, read_model, write_model


@dataclass
class W:
    start: float
    end: float
    word: str
    probability: float = 0.9


@dataclass
class S:
    start: float
    end: float
    text: str
    words: list


@dataclass
class Info:
    language: str
    duration: float


def write_silent_wav(path, seconds: float = 1.0):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\x00\x00" * int(16000 * seconds))


def bundle(media: bool = True) -> IngestBundle:
    return IngestBundle(
        source=SourceInfo(kind="file", platform="local", path="/x/clip.mp4", duration_s=60.0),
        media=MediaInfo(path="media/clip.mp4", has_audio=True) if media else None,
        route=Route(context="local", media="local"),
    )


class FakeArray:
    """Stands in for the float32 array, so unit tests need neither numpy nor the extras."""

    def __init__(self, path):
        self.path = path


@pytest.fixture(autouse=True)
def fake_wav_loader(monkeypatch):
    for module in (transcribe_faster, transcribe_mlx):
        monkeypatch.setattr(module, "load_wav_float32", FakeArray)


@pytest.fixture
def work_with_audio(tmp_path):
    """ingest.json plus a 1 s silent audio-16k.wav newer than the (dummy) media file."""
    w = WorkDir(tmp_path / "w")
    w.ensure()
    (w.path / "media").mkdir()
    clip = w.path / "media" / "clip.mp4"
    clip.write_bytes(b"not decoded: the wav is newer, so extract_audio reuses it")
    os.utime(clip, ns=(1_000_000_000, 1_000_000_000))
    write_silent_wav(w.path / "media" / "audio-16k.wav")
    write_model(w.file("ingest.json"), bundle())
    return w


def fake_faster(monkeypatch, segments, calls):
    class FakeModel:
        def __init__(self, name, device, compute_type):
            calls["init"] = (name, device, compute_type)

        def transcribe(self, audio, word_timestamps, vad_filter):
            calls["audio"] = audio
            calls["word_timestamps"] = word_timestamps
            calls["vad_filter"] = vad_filter
            return iter(segments), Info("en", 60.0)

    monkeypatch.setitem(
        sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel)
    )


def test_faster_maps_word_timestamps(work_with_audio, monkeypatch):
    calls = {}
    segs = [S(1.0, 2.5, " paste this", [W(1.0, 1.4, " paste"), W(1.5, 2.5, " this")])]
    fake_faster(monkeypatch, segs, calls)
    t = FasterWhisperBackend().transcribe(work_with_audio, None)
    assert calls["init"] == ("small", "auto", "int8") and calls["word_timestamps"] is True
    # The engine's WAV as an array, not a path: faster-whisper 1.2.1 decodes paths with an
    # av.open keyword that av 18 removed.
    assert isinstance(calls["audio"], FakeArray)
    assert calls["audio"].path == work_with_audio.path / "media" / "audio-16k.wav"
    assert t.origin == "faster-whisper" and t.language == "en" and t.model == "small"
    assert t.segments[0].text == "paste this"
    assert [(w.w, w.s, w.e) for w in t.segments[0].words or []] == [
        ("paste", 1.0, 1.4),
        ("this", 1.5, 2.5),
    ]


def test_faster_thorough_model_is_passed_through(work_with_audio, monkeypatch):
    calls = {}
    fake_faster(monkeypatch, [S(0.0, 1.0, "hi", [W(0.0, 1.0, "hi")])], calls)
    t = FasterWhisperBackend().transcribe(work_with_audio, "large-v3-turbo")
    assert calls["init"][0] == "large-v3-turbo" and t.model == "large-v3-turbo"


def fake_mlx(monkeypatch, result, calls):
    def transcribe(audio, *, path_or_hf_repo, word_timestamps, **kw):
        calls["audio"] = audio
        calls["repo"] = path_or_hf_repo
        calls["word_timestamps"] = word_timestamps
        return result

    monkeypatch.setitem(sys.modules, "mlx_whisper", types.SimpleNamespace(transcribe=transcribe))


MLX_RESULT = {
    "text": " Next, paste this.",
    "language": "en",
    "segments": [
        {
            "start": 24.0,
            "end": 26.0,
            "text": " Next, paste this.",
            "words": [
                {"word": " Next,", "start": 24.0, "end": 24.5, "probability": 0.9},
                {"word": " paste", "start": 24.6, "end": 25.1, "probability": 0.9},
                {"word": " this.", "start": 25.2, "end": 26.0, "probability": 0.9},
            ],
        }
    ],
}


def test_mlx_receives_an_array_not_a_path(work_with_audio, monkeypatch):
    calls = {}
    fake_mlx(monkeypatch, MLX_RESULT, calls)
    t = MlxWhisperBackend().transcribe(work_with_audio, None)
    assert isinstance(calls["audio"], FakeArray)  # plan issue 13: never a path
    assert calls["audio"].path == work_with_audio.path / "media" / "audio-16k.wav"
    assert calls["repo"] == "mlx-community/whisper-large-v3-turbo"
    assert calls["word_timestamps"] is True
    assert t.origin == "mlx-whisper" and t.model == "large-v3-turbo" and t.language == "en"
    assert t.segments[0].text == "Next, paste this."
    assert [w.w for w in t.segments[0].words or []] == ["Next,", "paste", "this."]


@pytest.mark.parametrize(
    ("model", "repo"),
    [
        ("large-v3-turbo", "mlx-community/whisper-large-v3-turbo"),
        ("turbo", "mlx-community/whisper-large-v3-turbo"),
        ("small", "mlx-community/whisper-small-mlx"),
        ("someone/custom-whisper", "someone/custom-whisper"),
    ],
)
def test_mlx_model_names_map_to_repos(work_with_audio, monkeypatch, model, repo):
    calls = {}
    fake_mlx(monkeypatch, MLX_RESULT, calls)
    MlxWhisperBackend().transcribe(work_with_audio, model)
    assert calls["repo"] == repo


def test_no_speech_gives_one_empty_timed_segment_and_silent(work_with_audio, monkeypatch):
    """VAD on a silent track yields no segments; the run must still end silent, not exit 7."""
    fake_faster(monkeypatch, [], {})
    installed(monkeypatch, mlx=False, faster=True)
    r = CliRunner().invoke(
        app, ["transcribe", "--work", str(work_with_audio.path), "--backend", "faster"]
    )
    assert r.exit_code == 0, r.output
    t = read_model(work_with_audio.file("transcript.json"), Transcript)
    assert t.silent is True
    assert [(s.start, s.end, s.text) for s in t.segments] == [(0.0, 1.0, "")]


def test_words_with_blank_text_are_dropped(work_with_audio, monkeypatch):
    segs = [S(0.0, 1.0, " a", [W(0.0, 0.1, " "), W(0.2, 1.0, " a")])]
    fake_faster(monkeypatch, segs, {})
    t = FasterWhisperBackend().transcribe(work_with_audio, None)
    assert [w.w for w in t.segments[0].words or []] == ["a"]


def test_whisper_backends_registered_local_with_ranks():
    backends = transcription_backends()
    assert (backends["mlx"].auto_rank, backends["mlx"].cloud) == (1, False)
    assert (backends["faster"].auto_rank, backends["faster"].cloud) == (2, False)


def test_backend_modules_do_not_import_the_libraries():
    """A missing extra must never break registry import: the heavy imports are lazy."""
    code = (
        "import sys, skipwatch.providers.transcribe_faster, skipwatch.providers.transcribe_mlx;"
        "print('faster_whisper' in sys.modules, 'mlx_whisper' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.split() == ["False", "False"]


def installed(monkeypatch, *, mlx: bool, faster: bool, apple: bool = True):
    monkeypatch.setattr(transcribe_mlx, "_installed", lambda: mlx)
    monkeypatch.setattr(transcribe_mlx, "is_apple_silicon", lambda: apple)
    monkeypatch.setattr(transcribe_faster, "_installed", lambda: faster)


def test_auto_prefers_mlx_on_apple_silicon_then_faster(monkeypatch):
    installed(monkeypatch, mlx=True, faster=True)
    assert select_backend("auto", bundle()).name == "mlx"
    installed(monkeypatch, mlx=True, faster=True, apple=False)
    assert select_backend("auto", bundle()).name == "faster"
    installed(monkeypatch, mlx=False, faster=True)
    assert select_backend("auto", bundle()).name == "faster"


def test_whisper_needs_media(monkeypatch):
    installed(monkeypatch, mlx=True, faster=True)
    assert not MlxWhisperBackend().available(bundle(media=False))
    assert not FasterWhisperBackend().available(bundle(media=False))


def test_whisper_missing_is_exit_8_with_extra_command(monkeypatch):
    installed(monkeypatch, mlx=False, faster=False)
    with pytest.raises(SkipwatchError) as e:
        select_backend("auto", bundle())
    assert e.value.code == ExitCode.MISSING_DEPENDENCY
    with pytest.raises(SkipwatchError) as e:
        select_backend("faster", bundle())
    assert e.value.message.endswith(extra_command(None, "whisper"))
    with pytest.raises(SkipwatchError) as e:
        select_backend("mlx", bundle())
    assert e.value.message.endswith(extra_command(None, "mlx"))


def test_mlx_off_apple_silicon_points_at_faster(monkeypatch):
    installed(monkeypatch, mlx=False, faster=False, apple=False)
    hint = MlxWhisperBackend().missing_hint()
    assert "Apple Silicon" in hint and "--backend faster" in hint
