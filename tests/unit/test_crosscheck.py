import json
import time
from pathlib import Path

from skipwatch.crosscheck import LOW_SIMILARITY, attach, disagreement, similarity
from skipwatch.models import (
    CrossCheck,
    Segment,
    Transcript,
    TranscriptHint,
    TranscriptOrigin,
)

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


def test_disagreement_message_under_threshold_only():
    low = attach(timed("alpha beta"), TranscriptHint(origin="treg", text="one two three"))
    assert disagreement(low) == "transcript sources disagree: 0.00"
    assert disagreement(attach(timed("a b c"), TranscriptHint(origin="treg", text="a b c"))) is None
    assert disagreement(timed("a b c")) is None
