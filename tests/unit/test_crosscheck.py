import json
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch import transcribe as transcribe_module
from skipwatch.cli import app
from skipwatch.crosscheck import LOW_SIMILARITY, attach, disagreement, overlap, similarity
from skipwatch.models import (
    CrossCheck,
    IngestBundle,
    IngestContext,
    MediaInfo,
    Route,
    Segment,
    SourceInfo,
    Transcript,
    TranscriptHint,
    TranscriptOrigin,
)
from skipwatch.transcribe import run_transcribe
from skipwatch.workdir import WorkDir, read_model, write_model

TREG = Path(__file__).parent.parent / "fixtures" / "recorded" / "treg"


def recorded(name: str) -> dict:
    return json.loads((TREG / name).read_text(encoding="utf-8"))["output"]["data"]


YOUTUBE = recorded("anyapi.youtube.video_transcript_full.json")
TWEET = recorded("anyapi.twitter.tweet_transcript.json")


def youtube_timed() -> Transcript:
    """The recorded timed segments, as a captions transcript would carry them."""
    return Transcript(
        origin="captions",
        segments=[
            Segment(start=s["startSeconds"], end=s["endSeconds"], text=s["text"])
            for s in YOUTUBE["segments"]
        ],
    )


def timed(text: str, origin: TranscriptOrigin = "captions") -> Transcript:
    return Transcript(origin=origin, segments=[Segment(start=0, end=30, text=text)])


# ---- similarity ----


def test_identical_text_is_1():
    assert similarity("Hello there, world.", "Hello there, world.") == 1.0


def test_disjoint_text_below_0_2():
    assert similarity("alpha beta gamma delta", "one two three four five") < 0.2


def test_normalization_ignores_case_punctuation_width_and_nbsp():
    # NFKC folds the full-width letters and the no-break space; casefold folds the case.
    assert similarity("Let’s GO,\xa0now!", "let’s go now") == 1.0
    assert similarity("ＪＳＯＮ wins", "json wins") == 1.0


def test_similarity_is_deterministic_and_rounded():
    a, b = "the cat sat on the mat", "the cat sat on a hat"
    assert similarity(a, b) == similarity(a, b) == round(similarity(a, b), 2)
    assert 0 < similarity(a, b) < 1


def test_empty_side_is_0():
    assert similarity("", "some words") == 0.0
    assert similarity("...", "some words") == 0.0


def test_recorded_youtube_transcript_agrees_with_its_segments():
    s = similarity(" ".join(s.text for s in youtube_timed().segments), YOUTUBE["transcript"])
    assert s >= 0.95


def test_recorded_tweet_transcript_disagrees_with_youtube_segments():
    s = similarity(" ".join(s.text for s in youtube_timed().segments), TWEET["transcript"])
    assert s < LOW_SIMILARITY


def test_single_word_uses_unigrams():
    assert similarity("hello", "Hello!") == 1.0
    assert similarity("hello world", "hello") == 0.67  # 2 * 1 / 3, rounded to 2 places


def test_reordered_words_score_low():
    assert similarity("a b c d", "d c b a") < 0.2


def test_similarity_is_cheap_on_hour_long_disjoint_text():
    # An hour of speech (~9k words) against unrelated text drawn from the same small vocabulary.
    vocab = [f"w{i}" for i in range(40)]
    a = " ".join(vocab[(i * 7) % 40] for i in range(9000))
    b = " ".join(vocab[(i * 13 + 5) % 40] for i in range(9000))
    start = time.perf_counter()
    similarity(a, b)
    assert time.perf_counter() - start < 2.0


# ---- attach ----


def test_attach_sets_cross_check_from_hint():
    hint = TranscriptHint(origin="treg:anyapi.youtube.video_transcript", text=YOUTUBE["transcript"])
    t = attach(youtube_timed(), hint)
    assert t.cross_check is not None
    assert t.cross_check.origin == "treg:anyapi.youtube.video_transcript"
    assert t.cross_check.text == YOUTUBE["transcript"]
    assert t.cross_check.similarity is not None and t.cross_check.similarity >= 0.95


def test_r_tr_1_untimed_text_only_in_cross_check():
    base = youtube_timed()
    t = attach(base, TranscriptHint(origin="treg:anyapi.twitter.tweet_transcript", text="x y z"))
    assert t.segments == base.segments  # a hint never creates, replaces or edits segments
    assert t.origin == "captions"


def test_attach_without_hint_text_has_no_cross_check():
    assert attach(timed("a b c"), TranscriptHint()).cross_check is None
    assert attach(timed("a b c"), TranscriptHint(origin="treg", text="  ")).cross_check is None


def test_attach_replaces_a_stale_cross_check():
    stale = timed("a b c").model_copy(
        update={"cross_check": CrossCheck(origin="old", text="q", similarity=0.0)}
    )
    assert attach(stale, TranscriptHint()).cross_check is None
    fresh = attach(stale, TranscriptHint(origin="new", text="a b c"))
    assert fresh.cross_check == CrossCheck(origin="new", text="a b c", similarity=1.0)


def with_check(similarity_value: float) -> Transcript:
    check = CrossCheck(origin="treg", text="one two three", similarity=similarity_value)
    return timed("alpha beta gamma").model_copy(update={"cross_check": check})


def test_disagreement_threshold_is_0_6():
    assert disagreement(with_check(0.59)) == "transcript sources disagree: 0.59"
    assert disagreement(with_check(0.60)) is None


def test_excerpt_of_the_transcript_does_not_warn():
    # A provider caption that quotes 5 words of a 1000-word talk: Dice is tiny, overlap is 1.
    words = [f"w{i}" for i in range(1000)]
    t = attach(timed(" ".join(words)), TranscriptHint(origin="treg", text=" ".join(words[40:45])))
    assert t.cross_check is not None and t.cross_check.similarity == 0.01  # Dice is kept
    assert overlap(" ".join(words), " ".join(words[40:45])) == 1.0
    assert disagreement(t) is None


def test_unrelated_short_text_still_warns():
    words = [f"w{i}" for i in range(1000)]
    t = attach(
        timed(" ".join(words)), TranscriptHint(origin="treg", text="nothing alike here at all")
    )
    assert disagreement(t) == "transcript sources disagree: 0.00"


def test_overlap_is_shared_over_the_smaller_side():
    assert overlap("a b c d e", "c d e") == 1.0  # 2 shared bigrams of min(4, 2)
    assert overlap("a b c d e", "c d x") == 0.5
    assert overlap("", "a b") == 0.0


def test_disagreement_message_under_threshold_only():
    low = attach(timed("alpha beta"), TranscriptHint(origin="treg", text="one two three"))
    assert disagreement(low) == "transcript sources disagree: 0.00"
    assert disagreement(attach(timed("a b c"), TranscriptHint(origin="treg", text="a b c"))) is None
    assert disagreement(timed("a b c")) is None


# ---- transcribe hook ----

SPOKEN = "WEBVTT\n\n" + "".join(
    f"00:00:{i * 5:02d}.000 --> 00:00:{i * 5 + 4:02d}.000\n"
    "this sentence has exactly seven words here\n\n"
    for i in range(12)
)


def captions_work(tmp_path, hint: TranscriptHint, name="w") -> WorkDir:
    w = WorkDir(tmp_path / name)
    w.ensure()
    (w.path / "captions").mkdir()
    (w.path / "captions" / "demo.en.vtt").write_text(SPOKEN, encoding="utf-8")
    write_model(
        w.file("ingest.json"),
        IngestBundle(
            source=SourceInfo(kind="file", platform="local", path="/x/demo.mp4", duration_s=60),
            context=IngestContext(captions_available=True, captions_path="captions/demo.en.vtt"),
            route=Route(context="local", media="local"),
            transcript_hint=hint,
        ),
    )
    return w


def test_cross_check_written_by_transcribe(tmp_path):
    w = captions_work(
        tmp_path, TranscriptHint(origin="treg:anyapi.twitter.tweet_transcript", text=SPOKEN[8:60])
    )
    r = CliRunner().invoke(app, ["transcribe", "--work", str(w.path)])
    assert r.exit_code == 0, r.output
    t = read_model(w.file("transcript.json"), Transcript)
    assert t.origin == "captions" and len(t.segments) == 12  # R-ING-2: never primary
    assert t.cross_check is not None
    assert t.cross_check.origin == "treg:anyapi.twitter.tweet_transcript"
    assert t.cross_check.similarity is not None and t.cross_check.similarity > 0


def test_transcribe_without_hint_writes_no_cross_check(tmp_path):
    w = captions_work(tmp_path, TranscriptHint())
    assert CliRunner().invoke(app, ["transcribe", "--work", str(w.path)]).exit_code == 0
    assert read_model(w.file("transcript.json"), Transcript).cross_check is None


def test_low_similarity_warns_in_transcribe_log(tmp_path, capsys):
    w = captions_work(tmp_path, TranscriptHint(origin="treg", text=TWEET["transcript"]))
    run_transcribe(w, "auto", None)
    err = capsys.readouterr().err
    assert "Transcribe: warning: transcript sources disagree: " in err
    t = read_model(w.file("transcript.json"), Transcript)
    assert t.cross_check is not None and t.cross_check.similarity is not None
    assert t.cross_check.similarity < LOW_SIMILARITY


def test_close_text_does_not_warn(tmp_path, capsys):
    hint_text = " ".join(["this sentence has exactly seven words here"] * 12)
    w = captions_work(tmp_path, TranscriptHint(origin="treg", text=hint_text))
    run_transcribe(w, "auto", None)
    assert "disagree" not in capsys.readouterr().err


class OneBackend:
    cloud = False
    name, origin, auto_rank = "faster", "faster-whisper", 2

    def __init__(self):
        self.calls = 0

    def available(self, bundle):
        return True

    def transcribe(self, work, model):
        self.calls += 1
        return timed(" ".join(["word"] * 40), origin=self.origin)

    def missing_hint(self):
        return ""


def url_work(tmp_path, name, hint: TranscriptHint) -> WorkDir:
    w = WorkDir(tmp_path / name)
    w.ensure()
    url = "https://vimeo.com/1"
    write_model(
        w.file("ingest.json"),
        IngestBundle(
            source=SourceInfo(
                kind="video", platform="generic", url=url, canonical_url=url, duration_s=60
            ),
            media=MediaInfo(path="media/video.mp4", has_audio=True),
            route=Route(context="free", media="free"),
            transcript_hint=hint,
        ),
    )
    return w


@pytest.fixture
def one_backend(monkeypatch, sw_home):
    backend = OneBackend()
    monkeypatch.setattr(transcribe_module, "transcription_backends", lambda: {"faster": backend})
    return backend


def test_cached_transcript_keeps_cross_check(tmp_path, one_backend):
    hint = TranscriptHint(origin="treg", text="word word word")
    first = run_transcribe(url_work(tmp_path, "w1", hint), "auto", None)
    w2 = url_work(tmp_path, "w2", hint)
    second = run_transcribe(w2, "auto", None)
    assert one_backend.calls == 1  # served from the cache
    assert first.cross_check is not None
    assert second.cross_check == first.cross_check
    assert read_model(w2.file("transcript.json"), Transcript).cross_check == first.cross_check


def test_cached_transcript_cross_check_follows_this_runs_hint(tmp_path, one_backend, capsys):
    run_transcribe(url_work(tmp_path, "w1", TranscriptHint()), "auto", None)
    hint = TranscriptHint(origin="treg", text="nothing alike at all")
    w2 = url_work(tmp_path, "w2", hint)
    second = run_transcribe(w2, "auto", None)
    assert one_backend.calls == 1
    assert second.cross_check is not None and second.cross_check.origin == "treg"
    assert read_model(w2.file("transcript.json"), Transcript).cross_check == second.cross_check
    assert "transcript sources disagree" in capsys.readouterr().err
    # and a later run with no hint drops the cached cross_check instead of showing a stale one
    third = run_transcribe(url_work(tmp_path, "w3", TranscriptHint()), "auto", None)
    assert third.cross_check is None
