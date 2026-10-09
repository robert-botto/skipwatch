"""Cloud transcription backends (M2-D): request shapes, mapping, chunk offsets, errors, R-TR-2.

Responses come from hand-made fixtures in tests/fixtures/recorded/cloud/ (doc-derived, no paid
call was ever made). requests.post is replaced in the module, and conftest blocks sockets.
"""

import json
from pathlib import Path

import pytest
import requests
from typer.testing import CliRunner

from skipwatch import transcribe as transcribe_module
from skipwatch.cli import app
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import IngestBundle, IngestContext, MediaInfo, Route, SourceInfo, Transcript
from skipwatch.providers import transcribe_cloud
from skipwatch.providers.registry import transcription_backends
from skipwatch.providers.transcribe_cloud import DeepgramBackend, GroqBackend, OpenAIBackend
from skipwatch.workdir import WorkDir, read_model, write_model

RECORDED = Path(__file__).resolve().parents[1] / "fixtures" / "recorded" / "cloud"
FAKE_KEY = "sk-test-not-real"
KEY_ENVS = ("OPENAI_API_KEY", "GROQ_API_KEY", "DEEPGRAM_API_KEY")
KEY_BACKENDS = ("openai", "groq", "deepgram")


def recorded(name: str) -> dict:
    return json.loads((RECORDED / name).read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(self, status_code: int, body: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._body = body
        self.text = text or (json.dumps(body) if body is not None else "")

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class FakePost:
    """Records every call; answers with the queued responses in order."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url, **kw):
        body = kw.get("data")
        if hasattr(body, "read"):
            kw["_body_bytes"] = body.read()
        files = kw.get("files")
        if files:
            name, fh, mime = files["file"]
            kw["_file"] = (name, fh.read(), mime)
        self.calls.append((url, kw))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture(autouse=True)
def _no_keys(monkeypatch):
    for env in KEY_ENVS:
        monkeypatch.delenv(env, raising=False)


@pytest.fixture
def work(tmp_path):
    """A work folder with ingest.json (no captions) and a media file."""
    w = WorkDir(tmp_path / "w")
    w.ensure()
    (w.path / "media").mkdir()
    (w.path / "media" / "video.mp4").write_bytes(b"not really a video")
    write_model(
        w.file("ingest.json"),
        IngestBundle(
            source=SourceInfo(kind="video", platform="youtube", url="https://youtu.be/x"),
            context=IngestContext(),
            route=Route(context="free", media="free"),
            media=MediaInfo(path="media/video.mp4", has_audio=True),
        ),
    )
    return w


@pytest.fixture
def chunks(monkeypatch, tmp_path):
    """Stand in for audio extraction: returns the given (path, offset) chunks."""

    def install(offsets: list[float]) -> list[tuple[Path, float]]:
        made = []
        for i, offset in enumerate(offsets):
            p = tmp_path / f"chunk-{i:03d}.mp3"
            p.write_bytes(f"mp3 bytes {i}".encode())
            made.append((p, offset))
        monkeypatch.setattr(transcribe_cloud, "audio_chunks", lambda work: made)
        return made

    return install


def fake_post(monkeypatch, *responses) -> FakePost:
    fake = FakePost(*responses)
    monkeypatch.setattr(transcribe_cloud.requests, "post", fake)
    return fake


# ---- registration and R-TR-2 ----


def test_three_cloud_backends_register_explicit_only():
    backends = transcription_backends()
    for name in ("openai", "groq", "deepgram"):
        assert backends[name].cloud is True and backends[name].auto_rank is None


@pytest.mark.parametrize(
    ("backend", "env"),
    [(OpenAIBackend(), "OPENAI_API_KEY"), (GroqBackend(), "GROQ_API_KEY"),
     (DeepgramBackend(), "DEEPGRAM_API_KEY")],
)  # fmt: skip
def test_available_only_with_the_env_key(monkeypatch, work, backend, env):
    bundle = read_model(work.file("ingest.json"), IngestBundle)
    assert backend.available(bundle) is False
    assert backend.missing_hint() == f"set {env}"
    monkeypatch.setenv(env, "")
    assert backend.available(bundle) is False
    monkeypatch.setenv(env, FAKE_KEY)
    assert backend.available(bundle) is True


def test_r_tr_2_cloud_needs_explicit_backend(work, monkeypatch, chunks):
    for env in KEY_ENVS:
        monkeypatch.setenv(env, FAKE_KEY)
    registered = transcription_backends()
    only_captions_and_cloud = {
        k: v for k, v in registered.items() if k in ("captions", "openai", "groq", "deepgram")
    }
    assert set(only_captions_and_cloud) == {"captions", "openai", "groq", "deepgram"}
    monkeypatch.setattr(
        transcribe_module, "transcription_backends", lambda: only_captions_and_cloud
    )
    chunks([0.0])
    fake = fake_post(monkeypatch, FakeResponse(200, recorded("openai_verbose.json")))
    r = CliRunner().invoke(app, ["transcribe", "--work", str(work.path)])
    assert r.exit_code == 8  # auto never chooses cloud, even with every key present
    assert not work.file("transcript.json").exists() and fake.calls == []
    r = CliRunner().invoke(app, ["transcribe", "--work", str(work.path), "--backend", "openai"])
    assert r.exit_code == 0, r.output  # named explicitly, it runs
    assert len(fake.calls) == 1


# ---- OpenAI and Groq ----


def test_openai_request_shape_and_mapping(work, monkeypatch, chunks):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    chunks([0.0])
    fake = fake_post(monkeypatch, FakeResponse(200, recorded("openai_verbose.json")))
    t = OpenAIBackend().transcribe(work, None)
    url, kw = fake.calls[0]
    assert url == "https://api.openai.com/v1/audio/transcriptions"
    assert kw["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"
    data = kw["data"]
    assert ("model", "whisper-1") in data and ("response_format", "verbose_json") in data
    assert ("timestamp_granularities[]", "word") in data
    assert ("timestamp_granularities[]", "segment") in data
    assert kw["_file"] == ("chunk-000.mp3", b"mp3 bytes 0", "audio/mpeg")
    assert kw["timeout"] > 0
    assert t.origin == "openai" and t.model == "whisper-1" and t.language == "en"
    assert [(s.start, s.end, s.text) for s in t.segments] == [
        (1.0, 4.2, "First type this command."),
        (5.0, 9.0, "Then paste the prompt."),
    ]
    first, second = t.segments
    assert [w.w for w in first.words or []] == ["First", "type", "this", "command", "okay"]
    assert [w.w for w in second.words or []] == ["Then", "paste", "the", "prompt", "now"]
    assert (second.words or [])[0].s == 5.0 and (second.words or [])[0].e == 5.4


def test_openai_word_in_a_gap_goes_to_the_segment_before(work, monkeypatch, chunks):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    chunks([0.0])
    body = recorded("openai_verbose.json")
    body["words"].insert(5, {"word": "um", "start": 4.5, "end": 4.8})  # between 4.2 and 5.0
    fake_post(monkeypatch, FakeResponse(200, body))
    t = OpenAIBackend().transcribe(work, None)
    assert [w.w for w in t.segments[0].words or []][-1] == "um"
    assert [w.w for w in t.segments[1].words or []][0] == "Then"


def test_openai_rejects_a_model_without_timestamps(work, monkeypatch, chunks):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    chunks([0.0])
    fake = fake_post(monkeypatch)
    with pytest.raises(SkipwatchError) as e:
        OpenAIBackend().transcribe(work, "gpt-4o-transcribe")
    assert e.value.code == ExitCode.USAGE and "whisper-1" in e.value.message
    assert fake.calls == []


def test_groq_request_shape(work, monkeypatch, chunks):
    monkeypatch.setenv("GROQ_API_KEY", FAKE_KEY)
    chunks([0.0])
    fake = fake_post(monkeypatch, FakeResponse(200, recorded("groq_verbose.json")))
    t = GroqBackend().transcribe(work, None)
    url, kw = fake.calls[0]
    assert url == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert kw["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"
    assert ("model", "whisper-large-v3-turbo") in kw["data"]
    assert ("timestamp_granularities[]", "word") in kw["data"]
    assert t.origin == "groq" and t.model == "whisper-large-v3-turbo" and t.language == "en"
    assert len(t.segments) == 2 and all(s.words for s in t.segments)


def test_groq_model_override(work, monkeypatch, chunks):
    monkeypatch.setenv("GROQ_API_KEY", FAKE_KEY)
    chunks([0.0])
    fake = fake_post(monkeypatch, FakeResponse(200, recorded("groq_verbose.json")))
    t = GroqBackend().transcribe(work, "whisper-large-v3")
    assert ("model", "whisper-large-v3") in fake.calls[0][1]["data"]
    assert t.model == "whisper-large-v3"


def test_chunk_offsets_are_added(work, monkeypatch, chunks):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    chunks([0.0, 3000.0])
    body = recorded("openai_verbose.json")
    fake = fake_post(monkeypatch, FakeResponse(200, body), FakeResponse(200, body))
    t = OpenAIBackend().transcribe(work, None)
    assert len(fake.calls) == 2
    assert fake.calls[1][1]["_file"][1] == b"mp3 bytes 1"
    assert [s.start for s in t.segments] == [1.0, 5.0, 3001.0, 3005.0]
    third = t.segments[2]
    assert third.end == pytest.approx(3004.2)
    assert [(w.s, w.e) for w in third.words or []][0] == (3001.0, 3001.5)


# ---- Deepgram ----


def test_deepgram_uses_token_auth_and_octet_stream(work, monkeypatch, chunks):
    monkeypatch.setenv("DEEPGRAM_API_KEY", FAKE_KEY)
    chunks([0.0, 3000.0])
    body = recorded("deepgram_listen.json")
    fake = fake_post(monkeypatch, FakeResponse(200, body), FakeResponse(200, body))
    t = DeepgramBackend().transcribe(work, None)
    url, kw = fake.calls[0]
    assert url == "https://api.deepgram.com/v1/listen"
    assert kw["headers"]["Authorization"] == f"Token {FAKE_KEY}"
    assert kw["headers"]["Content-Type"] == "application/octet-stream"
    assert kw["params"]["model"] == "nova-3"
    for flag in ("smart_format", "punctuate", "utterances", "detect_language"):
        assert kw["params"][flag] == "true"
    assert kw["_body_bytes"] == b"mp3 bytes 0"
    assert t.origin == "deepgram" and t.model == "nova-3" and t.language == "en"
    assert [(s.start, s.text) for s in t.segments] == [
        (1.0, "First type this command."),
        (5.0, "Then paste the prompt."),
        (3001.0, "First type this command."),
        (3005.0, "Then paste the prompt."),
    ]
    # punctuated_word when present, else word
    assert [w.w for w in t.segments[0].words or []] == ["First", "type", "this", "command."]
    assert (t.segments[1].words or [])[0].w == "then"
    assert (t.segments[3].words or [])[0].s == 3005.0


# ---- errors and key hygiene ----


@pytest.mark.parametrize(
    ("response", "code", "needle"),
    [
        (FakeResponse(401, {"error": {"message": f"Incorrect API key provided: {FAKE_KEY}"}}),
         ExitCode.MISSING_DEPENDENCY, "rejected the key in OPENAI_API_KEY"),
        (FakeResponse(403, {}), ExitCode.MISSING_DEPENDENCY, "rejected the key in OPENAI_API_KEY"),
        (FakeResponse(413, {}), ExitCode.INTERNAL_ERROR, "chunk contract"),
        (FakeResponse(429, {}), ExitCode.DOWNLOAD_FAILED, "429"),
        (FakeResponse(503, text="upstream down"), ExitCode.DOWNLOAD_FAILED, "503"),
        (FakeResponse(400, {"error": {"message": f"bad file for key {FAKE_KEY}"}}),
         ExitCode.DOWNLOAD_FAILED, "bad file"),
        (FakeResponse(200, text="<html>not json</html>"), ExitCode.DOWNLOAD_FAILED,
         "unreadable"),
        (requests.Timeout("read timed out"), ExitCode.DOWNLOAD_FAILED, "timed out"),
        (requests.ConnectionError("dns"), ExitCode.DOWNLOAD_FAILED, "could not reach"),
    ],
)  # fmt: skip
def test_http_errors_are_clear_and_never_show_the_key(
    work, monkeypatch, chunks, response, code, needle
):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    chunks([0.0])
    fake_post(monkeypatch, response)
    with pytest.raises(SkipwatchError) as e:
        OpenAIBackend().transcribe(work, None)
    assert e.value.code == code and needle in e.value.message
    assert e.value.message.startswith("openai ")
    assert FAKE_KEY not in e.value.message


def test_429_and_5xx_say_to_retry_later(work, monkeypatch, chunks):
    monkeypatch.setenv("GROQ_API_KEY", FAKE_KEY)
    chunks([0.0])
    fake_post(monkeypatch, FakeResponse(429, {}))
    with pytest.raises(SkipwatchError) as e:
        GroqBackend().transcribe(work, None)
    assert "retry later" in e.value.message and "rate limit" in e.value.message


def test_key_never_written_or_printed(work, monkeypatch, chunks):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    chunks([0.0])
    body = {"error": {"message": f"Incorrect API key provided: {FAKE_KEY}"}}
    fake_post(monkeypatch, FakeResponse(401, body))
    r = CliRunner().invoke(app, ["transcribe", "--work", str(work.path), "--backend", "openai"])
    assert r.exit_code == 8 and "OPENAI_API_KEY" in r.stderr
    assert FAKE_KEY not in r.output
    for path in work.path.rglob("*"):
        if path.is_file():
            assert FAKE_KEY.encode() not in path.read_bytes(), path


def test_success_writes_transcript_without_the_key(work, monkeypatch, chunks):
    monkeypatch.setenv("DEEPGRAM_API_KEY", FAKE_KEY)
    chunks([0.0])
    fake_post(monkeypatch, FakeResponse(200, recorded("deepgram_listen.json")))
    r = CliRunner().invoke(app, ["transcribe", "--work", str(work.path), "--backend", "deepgram"])
    assert r.exit_code == 0, r.output
    t = read_model(work.file("transcript.json"), Transcript)
    assert t.origin == "deepgram" and len(t.segments) == 2
    for path in work.path.rglob("*"):
        if path.is_file():
            assert FAKE_KEY.encode() not in path.read_bytes(), path


def test_word_in_a_blank_segment_joins_the_nearest_kept_segment(work, monkeypatch, chunks):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    chunks([0.0])
    body = recorded("openai_verbose.json")
    blank = {"id": 9, "seek": 0, "start": 9.5, "end": 10.0, "text": "  "}
    body["segments"].append(blank)
    body["words"].append({"word": "um", "start": 9.6, "end": 9.9})
    first_blank = {"id": 8, "seek": 0, "start": 0.0, "end": 0.9, "text": " "}
    body["segments"].insert(0, first_blank)
    body["words"].insert(0, {"word": "so", "start": 0.2, "end": 0.5})
    fake_post(monkeypatch, FakeResponse(200, body))
    t = OpenAIBackend().transcribe(work, None)
    assert len(t.segments) == 2  # blank segments are dropped
    assert [w.w for w in t.segments[0].words or []][0] == "so"
    assert [w.w for w in t.segments[1].words or []][-1] == "um"


@pytest.mark.parametrize(
    ("backend", "env", "name", "body"),
    [
        (OpenAIBackend(), "OPENAI_API_KEY", "openai",
         {"segments": [{"end": 1.0, "text": "no start"}], "words": []}),
        (GroqBackend(), "GROQ_API_KEY", "groq", {"segments": "not a list"}),
        (OpenAIBackend(), "OPENAI_API_KEY", "openai",
         {"segments": [{"start": 0.0, "end": 1.0, "text": "a"}], "words": [{"word": "a"}]}),
        (DeepgramBackend(), "DEEPGRAM_API_KEY", "deepgram",
         {"results": {"utterances": [{"transcript": "hi", "end": 1.0}]}}),
        (DeepgramBackend(), "DEEPGRAM_API_KEY", "deepgram",
         {"results": ["not", "a", "dict"]}),
    ],
)  # fmt: skip
def test_malformed_200_body_is_exit_3_unreadable(
    work, monkeypatch, chunks, backend, env, name, body
):
    monkeypatch.setenv(env, FAKE_KEY)
    chunks([0.0])
    fake_post(monkeypatch, FakeResponse(200, body))
    with pytest.raises(SkipwatchError) as e:
        backend.transcribe(work, None)
    assert e.value.code == ExitCode.DOWNLOAD_FAILED
    assert f"unreadable response from {name}" in e.value.message


@pytest.mark.parametrize("cloud", ["openai", "groq", "deepgram"])
@pytest.mark.parametrize("args", [(), ("--backend", "auto")])
def test_r_tr_2_config_backend_never_routes_to_cloud(
    work, monkeypatch, chunks, sw_home, cloud, args
):
    sw_home.mkdir(parents=True, exist_ok=True)
    (sw_home / "config.toml").write_text(f'[transcribe]\nbackend = "{cloud}"\n', encoding="utf-8")
    for env in KEY_ENVS:
        monkeypatch.setenv(env, FAKE_KEY)
    monkeypatch.setattr(transcribe_module, "is_apple_silicon", lambda: False)
    registered = transcription_backends()
    monkeypatch.setattr(
        transcribe_module,
        "transcription_backends",
        lambda: {k: v for k, v in registered.items() if k in ("captions", *KEY_BACKENDS)},
    )
    chunks([0.0])
    fake = fake_post(monkeypatch)
    r = CliRunner().invoke(app, ["transcribe", "--work", str(work.path), *args])
    assert r.exit_code == 8, r.output
    assert fake.calls == [] and not work.file("transcript.json").exists()


def test_language_names_become_codes():
    assert transcribe_cloud.language_code("english") == "en"
    assert transcribe_cloud.language_code("English") == "en"
    assert transcribe_cloud.language_code("portuguese") == "pt"
    assert transcribe_cloud.language_code("de") == "de"
    assert transcribe_cloud.language_code("klingon") == "klingon"
    assert transcribe_cloud.language_code(None) is None


# ---- wiring to skipwatch.audio (M2-C) ----


def test_audio_chunks_uses_extract_audio_and_mp3_chunks(work, monkeypatch):
    audio = pytest.importorskip("skipwatch.audio")
    seen = {}

    def fake_extract(w, bundle):
        seen["extract"] = (w, bundle.media.path if bundle.media else None)
        return w.path / "media" / "audio-16k.wav"

    def fake_encode(wav, out_dir, chunk_s=3000, kbps=32):
        seen["encode"] = (wav, out_dir, chunk_s, kbps)
        return [(out_dir / "c0.mp3", 0.0)]

    monkeypatch.setattr(audio, "extract_audio", fake_extract)
    monkeypatch.setattr(audio, "encode_mp3_chunks", fake_encode)
    result = transcribe_cloud.audio_chunks(work)
    assert seen["extract"] == (work, "media/video.mp4")
    assert seen["encode"] == (
        work.path / "media" / "audio-16k.wav",
        work.path / "media" / "chunks",
        3000,
        32,
    )
    assert result == [(work.path / "media" / "chunks" / "c0.mp3", 0.0)]
