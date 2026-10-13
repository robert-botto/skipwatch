"""Whisper end to end on the committed fixture (11.2) and the silent path (8.4).

Unit tests block sockets, so these run offline against models already in the Hugging Face
cache; a backend whose model is not cached is skipped with the command that fetches it.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.models import FramesFile, IngestBundle, MediaInfo, Route, SourceInfo, Transcript
from skipwatch.providers.registry import transcription_backends
from skipwatch.workdir import WorkDir, read_model, write_model

pytestmark = [pytest.mark.pipeline, pytest.mark.whisper]

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
REPOS = {"faster": "Systran/faster-whisper-small", "mlx": "mlx-community/whisper-large-v3-turbo"}
MAX_START_ERROR_S = 0.75  # tighter than the 1.0 s of 11.2: both backends measure under 0.5
ANY_MEDIA = IngestBundle(
    source=SourceInfo(kind="file", platform="local", path="/x.mp4"),
    media=MediaInfo(path="/x.mp4", has_audio=True),
    route=Route(context="local", media="local"),
)


def _cached(repo: str) -> bool:
    from huggingface_hub import scan_cache_dir

    try:
        return any(r.repo_id == repo for r in scan_cache_dir().repos)
    except Exception:
        return False


def ready_backends() -> list[str]:
    if shutil.which("ffmpeg") is None:
        return []
    backends = transcription_backends()
    return [n for n in ("mlx", "faster") if backends[n].available(ANY_MEDIA)]


def require(backend: str, monkeypatch) -> None:
    if backend not in ready_backends():
        pytest.skip(f"{backend} backend not importable here")
    try:
        cached = _cached(REPOS[backend])
    except ImportError:
        cached = False
    if not cached:
        pytest.skip(f"model {REPOS[backend]} not downloaded; run it once with network")
    from huggingface_hub import constants

    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setattr(constants, "HF_HUB_OFFLINE", True)  # read at import, so set it too


def run(*args: str):
    r = CliRunner().invoke(app, list(args))
    assert r.exit_code == 0, (r.output, r.exception)
    return r


def new_work(slug: str) -> Path:
    """A work folder made by the engine's own new-work, so it sits where the --work guard
    expects it (directly under the home's work/, with a stages.json), as in a real run."""
    return Path(
        json.loads(run("new-work", "--slug", slug, "--json").stdout.splitlines()[-1])["work"]
    )


@pytest.mark.parametrize("backend", ["mlx", "faster"])
def test_whisper_transcript_matches_script(tmp_path, sw_home, monkeypatch, backend):
    require(backend, monkeypatch)
    video = tmp_path / "tutorial-60s.mp4"  # copied alone: no .vtt sidecar beside it
    shutil.copyfile(FIXTURES / "tutorial-60s.mp4", video)
    work = new_work("tutorial-60s")
    run("ingest", str(video), "--work", str(work))
    assert read_model(work / "ingest.json", IngestBundle).context.captions_available is False

    run("transcribe", "--work", str(work), "--backend", backend)
    t = read_model(work / "transcript.json", Transcript)
    assert t.origin == {"mlx": "mlx-whisper", "faster": "faster-whisper"}[backend]
    assert t.silent is False and t.language == "en"
    assert t.segments and all(s.words for s in t.segments)
    starts = [s.start for s in t.segments]
    script = json.loads((FIXTURES / "tutorial-60s.script.json").read_text())
    for sentence in script["sentences"]:
        nearest = min(abs(sentence["start"] - s) for s in starts)
        assert nearest <= MAX_START_ERROR_S, (
            f"{sentence['text']!r} at {sentence['start']}: off by {nearest:.2f}"
        )
    # Speech starts at 1.0 s. Starts are clamped at 0, so a transcript pinned to 0.0 would
    # still pass a 1.0 s window; this proves the leading silence was really accounted for.
    assert starts[0] > 0.5, f"first segment starts at {starts[0]:.2f}"


def test_auto_picks_a_whisper_backend(tmp_path, sw_home, monkeypatch):
    ready = ready_backends()
    if not ready:
        pytest.skip("no Whisper backend importable here")
    require(ready[0], monkeypatch)
    w = WorkDir(new_work("narration"))
    write_model(
        w.file("ingest.json"),
        IngestBundle(
            source=SourceInfo(kind="audio", platform="local", path=str(FIXTURES / "narration.wav")),
            media=MediaInfo(path=str(FIXTURES / "narration.wav"), has_audio=True),
            route=Route(context="local", media="local"),
        ),
    )
    run("transcribe", "--work", str(w.path))
    t = read_model(w.file("transcript.json"), Transcript)
    assert t.origin in {"mlx-whisper", "faster-whisper"}
    assert t.origin == {"mlx": "mlx-whisper", "faster": "faster-whisper"}[ready[0]]


@pytest.mark.parametrize("backend", ["mlx", "faster"])
def test_silent_video_sets_silent_and_dense_frames(tmp_path, sw_home, monkeypatch, backend):
    require(backend, monkeypatch)
    video = tmp_path / "quiet.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=10:duration=30",
         "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=44100",
         "-shortest", "-pix_fmt", "yuv420p", str(video)],
        check=True,
    )  # fmt: skip
    work = new_work("quiet")
    run("ingest", str(video), "--work", str(work))
    run("transcribe", "--work", str(work), "--backend", backend)
    assert read_model(work / "transcript.json", Transcript).silent is True
    run("frames", "--work", str(work))
    assert read_model(work / "frames.json", FramesFile).sampling.per_minute == 6
