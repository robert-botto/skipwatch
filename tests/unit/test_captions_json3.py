from pathlib import Path

from skipwatch.captions import parse_file
from skipwatch.captions_json3 import parse_json3

REC = Path(__file__).resolve().parents[1] / "fixtures" / "recorded" / "youtube"

JSON3 = """{"events": [
 {"tStartMs": 0, "dDurationMs": 4000, "segs": [{"utf8": "first"}, {"utf8": " type", "tOffsetMs": 600}, {"utf8": " this", "tOffsetMs": 1100}]},
 {"tStartMs": 2000, "dDurationMs": 10, "aAppend": 1, "segs": [{"utf8": "\\n"}]},
 {"tStartMs": 4000, "dDurationMs": 2000, "segs": [{"utf8": "run it"}]}]}"""  # noqa: E501


def test_json3_segments_and_word_timings():
    segs = parse_json3(JSON3)
    assert [(s.start, s.end, s.text) for s in segs] == [
        (0.0, 4.0, "first type this"),
        (4.0, 6.0, "run it"),
    ]
    assert [(w.w, w.s) for w in segs[0].words] == [("first", 0.0), ("type", 0.6), ("this", 1.1)]
    assert segs[1].words is None


def test_json3_word_ends_are_the_next_start_then_the_segment_end():
    segs = parse_json3(JSON3)
    assert [w.e for w in segs[0].words] == [0.6, 1.1, 4.0]


def test_json3_overlapping_events_are_clipped_to_the_next_start():
    text = """{"events": [
     {"tStartMs": 0, "dDurationMs": 5000, "segs": [{"utf8": "one"}]},
     {"tStartMs": 3000, "dDurationMs": 4000, "segs": [{"utf8": "two"}]}]}"""
    assert [(s.start, s.end) for s in parse_json3(text)] == [(0.0, 3.0), (3.0, 7.0)]


def test_json3_repeated_cue_back_to_back_is_merged():
    text = """{"events": [
     {"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "same"}]},
     {"tStartMs": 1000, "dDurationMs": 1000, "segs": [{"utf8": "same"}]},
     {"tStartMs": 5000, "dDurationMs": 1000, "segs": [{"utf8": "same"}]}]}"""
    assert [(s.start, s.end) for s in parse_json3(text)] == [(0.0, 2.0), (5.0, 6.0)]


def test_json3_newlines_inside_a_cue_become_spaces_and_events_without_segs_are_skipped():
    text = """{"events": [{"tStartMs": 0, "dDurationMs": 100},
     {"tStartMs": 0, "dDurationMs": 2000, "segs": [{"utf8": "line one\\nline  two"}]}]}"""
    assert [s.text for s in parse_json3(text)] == ["line one line two"]


def test_parse_file_dispatches_json3(tmp_path):
    path = tmp_path / "a.en.json3"
    path.write_text(JSON3, encoding="utf-8")
    assert [s.text for s in parse_file(path)] == ["first type this", "run it"]


def test_recorded_manual_json3_parses_into_ordered_segments():
    segs = parse_file(REC / "manual-captions.en-US.json3")
    assert len(segs) >= 100
    assert any("git config" in s.text for s in segs)
    assert all(a.end <= b.start + 1e-9 for a, b in zip(segs, segs[1:], strict=False))


def test_recorded_auto_json3_has_word_timings():
    segs = parse_file(REC / "auto-only-nonenglish.de-orig.json3")
    assert len(segs) >= 50
    worded = [s for s in segs if s.words]
    assert len(worded) > len(segs) // 2
    assert all(w.s <= w.e for s in worded for w in s.words or [])
    assert all(a.end <= b.start + 1e-9 for a, b in zip(segs, segs[1:], strict=False))


def test_json3_word_starts_are_clipped_to_the_clipped_cue_end():
    text = """{"events": [
     {"tStartMs": 0, "dDurationMs": 5000,
      "segs": [{"utf8": "a"}, {"utf8": " b", "tOffsetMs": 4000}]},
     {"tStartMs": 2000, "dDurationMs": 1000, "segs": [{"utf8": "c"}]}]}"""
    first = parse_json3(text)[0]
    assert first.end == 2.0
    assert [(w.w, w.s, w.e) for w in first.words or []] == [("a", 0.0, 2.0), ("b", 2.0, 2.0)]


def test_json3_events_with_the_same_start_become_one_cue():
    text = """{"events": [
     {"tStartMs": 1000, "dDurationMs": 2000, "segs": [{"utf8": "top line"}]},
     {"tStartMs": 1000, "dDurationMs": 3000, "segs": [{"utf8": "bottom line"}]},
     {"tStartMs": 5000, "dDurationMs": 1000, "segs": [{"utf8": "next"}]}]}"""
    segs = parse_json3(text)
    assert [(s.start, s.end, s.text) for s in segs] == [
        (1.0, 4.0, "top line bottom line"),
        (5.0, 6.0, "next"),
    ]
