"""Live cloud transcription (paid). Runs only with SKIPWATCH_LIVE=1 and the provider's key.

Not run by builders; the orchestrator runs it only when Robert provides a key:
    SKIPWATCH_LIVE=1 OPENAI_API_KEY=... uv run pytest tests/live/test_live_cloud.py -m live -v
"""

import json
import os
import shutil
from pathlib import Path

import pytest

from skipwatch.models import IngestBundle, IngestContext, MediaInfo, Route, SourceInfo
from skipwatch.providers.transcribe_cloud import DeepgramBackend, GroqBackend, OpenAIBackend
from skipwatch.workdir import WorkDir, write_model

pytestmark = pytest.mark.live

FIX = Path(__file__).resolve().parents[1] / "fixtures"
TOLERANCE_S = 1.0


@pytest.fixture
def narration_work(tmp_path):
    pytest.importorskip("skipwatch.audio")
    if shutil.which("ffmpeg") is None:
        pytest.skip("needs ffmpeg")
    media = tmp_path / "narration.wav"
    shutil.copy(FIX / "narration.wav", media)
    w = WorkDir(tmp_path / "w")
    w.ensure()
    write_model(
        w.file("ingest.json"),
        IngestBundle(
            source=SourceInfo(kind="file", platform="local", path=str(media), duration_s=60.0),
            context=IngestContext(),
            route=Route(context="local", media="local"),
            media=MediaInfo(path=str(media), has_audio=True),
        ),
    )
    return w


@pytest.mark.parametrize(
    "backend",
    [OpenAIBackend(), GroqBackend(), DeepgramBackend()],
    ids=lambda b: b.name,
)
def test_live_cloud_sentence_starts(narration_work, backend):
    if not os.environ.get(backend.env, "").strip():
        pytest.skip(f"set {backend.env} to run the {backend.name} live test")
    transcript = backend.transcribe(narration_work, None)
    assert transcript.origin == backend.name and transcript.segments
    assert all(s.words for s in transcript.segments)
    script = json.loads((FIX / "tutorial-60s.script.json").read_text(encoding="utf-8"))
    starts = [s.start for s in transcript.segments]
    for sentence in script["sentences"]:
        nearest = min(abs(start - sentence["start"]) for start in starts)
        assert nearest <= TOLERANCE_S, (sentence["text"], starts)
