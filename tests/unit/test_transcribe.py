import json

import pytest
from typer.testing import CliRunner

from skipwatch import runcache
from skipwatch import transcribe as transcribe_module
from skipwatch.cli import app
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import (
    IngestBundle,
    IngestContext,
    MediaInfo,
    Route,
    Segment,
    SourceInfo,
    Transcript,
)
from skipwatch.providers.transcribe_captions import CaptionsBackend
from skipwatch.review import read_degradations
from skipwatch.transcribe import mark_silence, select_backend
from skipwatch.workdir import WorkDir, read_model, write_model


def work_with(tmp_path, vtt: str | None, duration=60.0, name="demo.en.vtt", path="/x/demo.mp4"):
    w = WorkDir(tmp_path / "w")
    w.ensure()
    ctx = IngestContext()
    if vtt is not None:
        (w.path / "captions").mkdir()
        (w.path / "captions" / name).write_text(vtt, encoding="utf-8")
        ctx = IngestContext(captions_available=True, captions_path=f"captions/{name}")
    write_model(
        w.file("ingest.json"),
        IngestBundle(
            source=SourceInfo(kind="file", platform="local", path=path, duration_s=duration),
            context=ctx,
            route=Route(context="local", media="local"),
        ),
    )
    return w


SPOKEN = "WEBVTT\n\n" + "".join(
    f"00:00:{i * 5:02d}.000 --> 00:00:{i * 5 + 4:02d}.000\n"
    "this sentence has exactly seven words here\n\n"
    for i in range(12)
)


def transcribe(w: WorkDir, *args: str):
    return CliRunner().invoke(app, ["transcribe", "--work", str(w.path), *args])


def test_r_tr_1_captions_produce_timed_segments(tmp_path):
    w = work_with(tmp_path, SPOKEN)
    r = transcribe(w, "--json")
    assert r.exit_code == 0, r.output
    assert Transcript.model_validate_json(r.stdout).origin == "captions"  # R-CLI-2
    t = read_model(w.file("transcript.json"), Transcript)
    assert t.origin == "captions" and t.language == "en" and t.model is None
    assert len(t.segments) == 12  # repeats separated by pauses are real speech, not rolling
    assert all(s.end >= s.start for s in t.segments) and t.silent is False
    stages = json.loads(w.file("stages.json").read_text())["stages"]
    assert stages["transcribe"]["status"] == "done"


def test_distinct_cues_are_kept_in_order(tmp_path):
    vtt = "WEBVTT\n\n" + "".join(
        f"00:00:{i:02d}.000 --> 00:00:{i:02d}.900\nline {i}\n\n" for i in range(3)
    )
    w = work_with(tmp_path, vtt)
    assert transcribe(w).exit_code == 0
    t = read_model(w.file("transcript.json"), Transcript)
    assert [s.text for s in t.segments] == ["line 0", "line 1", "line 2"]


def test_plain_sidecar_has_no_language(tmp_path):
    w = work_with(
        tmp_path,
        SPOKEN,
        name="Screen Recording at 14.02.11.vtt",
        path="/a/Screen Recording at 14.02.11.mov",
    )
    assert transcribe(w).exit_code == 0
    assert read_model(w.file("transcript.json"), Transcript).language is None


def test_srt_sidecar_language(tmp_path):
    srt = "1\n00:00:00,000 --> 00:00:30,000\n" + "word " * 40 + "\n"
    w = work_with(tmp_path, srt, name="demo.de.srt")
    assert transcribe(w).exit_code == 0
    t = read_model(w.file("transcript.json"), Transcript)
    assert t.language == "de" and t.silent is False


def test_silence_detection_under_20_wpm(tmp_path):
    w = work_with(tmp_path, "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhello there\n", duration=60.0)
    transcribe(w)
    assert read_model(w.file("transcript.json"), Transcript).silent is True


def test_mark_silence_threshold_is_20_wpm():
    def t(words: int) -> Transcript:
        return Transcript(origin="captions", segments=[Segment(start=0, end=1, text="w " * words)])

    assert mark_silence(t(19), 60.0).silent is True
    assert mark_silence(t(20), 60.0).silent is False
    assert mark_silence(t(10), 30.0).silent is False  # 20 wpm over half a minute


def test_mark_silence_falls_back_to_last_segment_end():
    t = Transcript(
        origin="captions",
        segments=[Segment(start=0, end=10, text="a b c"), Segment(start=50, end=60, text="d")],
    )
    assert mark_silence(t, None).silent is True  # 4 words over 60 s
    assert mark_silence(t.model_copy(update={"segments": []}), None).silent is True


def test_no_captions_no_whisper_is_exit_8_with_command(tmp_path, monkeypatch):
    monkeypatch.setattr(transcribe_module, "is_apple_silicon", lambda: False)
    w = work_with(tmp_path, None)
    r = transcribe(w)
    assert r.exit_code == 8 and "--extra whisper" in r.stderr
    assert not w.file("transcript.json").exists()  # R-TR-1: nothing untimed is written


def test_captions_requested_without_captions_is_exit_7(tmp_path):
    w = work_with(tmp_path, None)
    assert transcribe(w, "--backend", "captions").exit_code == 7
    assert not w.file("transcript.json").exists()


EMPTY_CAPTIONS = "#EXTM3U\n#EXTINF:6.0,\n/subtitles/0/seg.vtt\n#EXT-X-ENDLIST\n"  # X, unresolved


def test_captions_with_no_cues_and_no_whisper_is_exit_7_with_a_noted_degradation(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(transcribe_module, "is_apple_silicon", lambda: False)
    w = work_with(tmp_path, EMPTY_CAPTIONS)
    r = transcribe(w)
    assert r.exit_code == 7
    assert "captions produced no timed segments" in r.stderr
    assert "--extra whisper" in r.stderr  # how to get the fallback next time
    assert not w.file("transcript.json").exists()
    # the review screen shows it even when the orchestrator notes nothing itself
    noted = read_degradations(w.path).degradations
    assert len(noted) == 1 and noted[0].startswith("no transcript: captions produced no timed")


class _Whisper:
    name, cloud, auto_rank = "faster", False, 2

    def __init__(self, available=True):
        self._available = available
        self.calls = 0

    def available(self, bundle):
        return self._available

    def missing_hint(self):
        return "install whisper"

    def transcribe(self, work, model):
        self.calls += 1
        segments = [
            Segment(start=i * 5.0, end=i * 5.0 + 4, text="seven words " * 4) for i in range(12)
        ]
        return Transcript(origin="faster-whisper", model=model or "small", segments=segments)


def _with_whisper(monkeypatch, whisper):
    registered = transcribe_module.transcription_backends()
    monkeypatch.setattr(
        transcribe_module,
        "transcription_backends",
        lambda: {"captions": registered["captions"], "faster": whisper},
    )


def test_captions_with_no_cues_fall_back_to_whisper_under_auto(tmp_path, monkeypatch):
    whisper = _Whisper()
    _with_whisper(monkeypatch, whisper)
    w = work_with(tmp_path, EMPTY_CAPTIONS)
    r = transcribe(w)
    assert r.exit_code == 0, r.output
    assert whisper.calls == 1
    t = read_model(w.file("transcript.json"), Transcript)
    assert t.origin == "faster-whisper" and len(t.segments) == 12
    assert "falling back to faster" in r.stderr
    assert read_degradations(w.path).degradations == [
        "captions produced no timed segments; transcribed with faster instead"
    ]


def test_an_unavailable_whisper_is_no_fallback(tmp_path, monkeypatch):
    whisper = _Whisper(available=False)
    _with_whisper(monkeypatch, whisper)
    w = work_with(tmp_path, EMPTY_CAPTIONS)
    assert transcribe(w).exit_code == 7
    assert whisper.calls == 0


def test_empty_captions_on_a_silent_video_say_so(tmp_path, monkeypatch):
    whisper = _Whisper(available=False)  # Whisper is never available without an audio track
    _with_whisper(monkeypatch, whisper)
    w = work_with(tmp_path, EMPTY_CAPTIONS)
    bundle = read_model(w.file("ingest.json"), IngestBundle)
    silent = MediaInfo(path="media/video.mp4", width=1280, height=720, has_audio=False)
    write_model(w.file("ingest.json"), bundle.model_copy(update={"media": silent}))
    r = transcribe(w)
    assert r.exit_code == 7
    assert "no audio track" in r.stderr and "install" not in r.stderr


def test_captions_named_explicitly_never_fall_back(tmp_path, monkeypatch):
    whisper = _Whisper()
    _with_whisper(monkeypatch, whisper)
    w = work_with(tmp_path, EMPTY_CAPTIONS)
    r = transcribe(w, "--backend", "captions")
    assert r.exit_code == 7 and whisper.calls == 0
    assert not w.file("transcript.json").exists()


def test_captions_with_cues_never_reach_whisper(tmp_path, monkeypatch):
    whisper = _Whisper()
    _with_whisper(monkeypatch, whisper)
    w = work_with(tmp_path, SPOKEN)
    assert transcribe(w).exit_code == 0
    assert whisper.calls == 0
    assert read_degradations(w.path).degradations == []


class _KeylessCloud:
    name, cloud, auto_rank = "openai", True, None

    def available(self, bundle):
        return False

    def missing_hint(self):
        return "set OPENAI_API_KEY"


def test_cloud_backend_without_key_is_exit_8(tmp_path, monkeypatch):
    registered = transcribe_module.transcription_backends()
    monkeypatch.setattr(
        transcribe_module,
        "transcription_backends",
        lambda: {**registered, "openai": _KeylessCloud()},
    )
    w = work_with(tmp_path, SPOKEN)
    r = transcribe(w, "--backend", "openai")
    assert r.exit_code == 8 and "OPENAI_API_KEY" in r.stderr
    assert not w.file("transcript.json").exists()


@pytest.mark.parametrize("backend", ["openai", "groq", "deepgram", "mlx", "faster"])
def test_unregistered_backend_named_explicitly_is_exit_8(tmp_path, monkeypatch, backend):
    registered = transcribe_module.transcription_backends()
    monkeypatch.setattr(
        transcribe_module,
        "transcription_backends",
        lambda: {k: v for k, v in registered.items() if k != backend},
    )
    w = work_with(tmp_path, SPOKEN)
    r = transcribe(w, "--backend", backend)
    assert r.exit_code == 8 and backend in r.stderr
    assert not w.file("transcript.json").exists()


def test_select_backend_auto_prefers_captions(tmp_path):
    w = work_with(tmp_path, SPOKEN)
    bundle = read_model(w.file("ingest.json"), IngestBundle)
    assert select_backend("auto", bundle).name == "captions"


def test_select_backend_cloud_never_under_auto(tmp_path):
    w = work_with(tmp_path, None)
    bundle = read_model(w.file("ingest.json"), IngestBundle)
    with pytest.raises(SkipwatchError) as e:
        select_backend("auto", bundle)
    assert e.value.code == ExitCode.MISSING_DEPENDENCY


def test_captions_backend_available_reflects_bundle(tmp_path):
    with_caps = read_model(work_with(tmp_path / "a", SPOKEN).file("ingest.json"), IngestBundle)
    without = read_model(work_with(tmp_path / "b", None).file("ingest.json"), IngestBundle)
    assert CaptionsBackend().available(with_caps) is True
    assert CaptionsBackend().available(without) is False


def test_missing_ingest_is_exit_7(tmp_path):
    w = WorkDir(tmp_path / "w")
    w.ensure()
    r = transcribe(w)
    assert r.exit_code == 7 and "ingest" in r.stderr and "Traceback" not in r.output


def test_r_cli_1_transcribe_idempotent(tmp_path):
    w = work_with(tmp_path, SPOKEN)
    assert transcribe(w).exit_code == 0
    first = w.file("transcript.json").read_bytes()
    assert transcribe(w).exit_code == 0
    assert w.file("transcript.json").read_bytes() == first


def test_unicode_caption_text_round_trips(tmp_path):
    w = work_with(tmp_path, "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\ncafé → naïve\n")
    assert transcribe(w).exit_code == 0
    assert read_model(w.file("transcript.json"), Transcript).segments[0].text == "café → naïve"


def test_select_backend_unknown_name_is_usage(tmp_path):
    bundle = read_model(work_with(tmp_path, SPOKEN).file("ingest.json"), IngestBundle)
    with pytest.raises(SkipwatchError) as e:
        select_backend("whisper-xl", bundle)
    assert e.value.code == ExitCode.USAGE


def test_captions_lang_from_ingest_wins_over_file_name(tmp_path):
    w = work_with(tmp_path, SPOKEN, name="abc.vtt", path=None)
    bundle = read_model(w.file("ingest.json"), IngestBundle)
    ctx = bundle.context.model_copy(update={"captions_lang": "pt", "captions_kind": "auto"})
    write_model(w.file("ingest.json"), bundle.model_copy(update={"context": ctx}))
    assert transcribe(w).exit_code == 0
    assert read_model(w.file("transcript.json"), Transcript).language == "pt"


def _seed_cached_transcript(tmp_path, bundle: IngestBundle) -> None:
    seed = tmp_path / "seed.json"
    write_model(seed, Transcript(origin="captions", segments=[Segment(start=0, end=5, text="hi")]))
    runcache.remember_transcript(bundle, seed)
    assert runcache.cached_transcript(bundle, "auto", None) is not None  # the seed is a hit


@pytest.mark.parametrize(
    ("kind", "media"),
    [
        ("text", None),
        ("video", MediaInfo(path="media/video.mp4", has_audio=False)),
    ],
    ids=["text-source", "no-audio"],
)
def test_nothing_to_transcribe_is_exit_7_even_with_a_cached_transcript(
    tmp_path, sw_home, kind, media
):
    url = "https://example.com/post/1"
    bundle = IngestBundle(
        source=SourceInfo(kind=kind, platform="generic", url=url, canonical_url=url),
        media=media,
        route=Route(context="free", media="free" if media else None),
    )
    _seed_cached_transcript(tmp_path, bundle)
    w = WorkDir(sw_home / "work" / "w")
    w.ensure()
    write_model(w.file("ingest.json"), bundle)
    r = transcribe(w)
    assert r.exit_code == ExitCode.NO_CONTENT == 7, r.output
    assert not w.file("transcript.json").exists()
