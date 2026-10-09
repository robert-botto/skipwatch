import pytest

from skipwatch.captions import language_from_name, parse_file, parse_srt, parse_vtt

VTT = """WEBVTT
Kind: captions

00:00:09.000 --> 00:00:12.500 align:start position:0%
First, <c>type</c> this command

00:00:12.500 --> 00:00:14.000
First, type this command

01:02.000 --> 01:03.000
<v Narrator>short form timing</v>
"""


def test_vtt_parses_strips_tags_and_merges_rolling_duplicates():
    segs = parse_vtt(VTT)
    assert [(s.start, s.end, s.text) for s in segs] == [
        (9.0, 14.0, "First, type this command"),
        (62.0, 63.0, "short form timing"),
    ]


def test_srt_parses_comma_millis():
    segs = parse_srt("1\n00:00:01,500 --> 00:00:03,000\nhello\nworld\n\n")
    assert [(s.start, s.end, s.text) for s in segs] == [(1.5, 3.0, "hello world")]


def test_vtt_inline_timestamps_notes_ids_and_empty_cues():
    text = (
        "﻿WEBVTT\r\n\r\nNOTE this is a comment\r\nspanning lines\r\n\r\n"
        "cue-1\r\n01:00:00.250 --> 01:00:01.000\r\n"
        "<00:00:00.250><c>one</c><00:00:00.500><c> two</c>\r\n\r\n"
        "00:00:02.000 --> 00:00:03.000\r\n<c> </c>\r\n\r\n"
        "STYLE\r\n::cue { color: red }\r\n"
    )
    segs = parse_vtt(text)
    assert [(s.start, s.end, s.text) for s in segs] == [(3600.25, 3601.0, "one two")]


def test_vtt_decodes_entities():
    segs = parse_vtt("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nA &amp; B &lt;x&gt;\n")
    assert segs[0].text == "A & B <x>"


def test_srt_without_trailing_blank_line_and_with_bom():
    segs = parse_srt("﻿1\r\n00:00:00,000 --> 00:00:01,000\r\n<i>hi</i>")
    assert [s.text for s in segs] == ["hi"]


def test_numeric_cue_text_is_kept():
    segs = parse_srt("1\n00:00:00,000 --> 00:00:01,000\n42\n")
    assert [s.text for s in segs] == ["42"]


def test_end_before_start_is_clamped():
    segs = parse_srt("1\n00:00:05,000 --> 00:00:04,000\nback\n")
    assert segs[0].start == 5.0 and segs[0].end == 5.0


def test_parse_file_by_extension_case_insensitive(tmp_path):
    p = tmp_path / "Demo.EN.VTT"
    p.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello\n", encoding="utf-8")
    assert [s.text for s in parse_file(p)] == ["hello"]
    q = tmp_path / "demo.SRT"
    q.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    assert [s.text for s in parse_file(q)] == ["hi"]


REC = "Screen Recording 2026-10-09 at 14.02.11"


@pytest.mark.parametrize(
    "name,stem,lang",
    [
        ("demo.en.vtt", "demo", "en"),
        ("demo.en-US.srt", "demo", "en-US"),
        ("demo.vtt", "demo", None),
        (f"{REC}.vtt", REC, None),
        (f"{REC}.de.srt", REC, "de"),
    ],
)
def test_language_from_name(name, stem, lang):
    assert language_from_name(name, stem) == lang
