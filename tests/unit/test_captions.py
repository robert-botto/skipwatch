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
        "\ufeffWEBVTT\r\n\r\nNOTE this is a comment\r\nspanning lines\r\n\r\n"
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
    segs = parse_srt("\ufeff1\r\n00:00:00,000 --> 00:00:01,000\r\n<i>hi</i>")
    assert [s.text for s in segs] == ["hi"]


def test_numeric_cue_text_is_kept():
    segs = parse_srt("1\n00:00:00,000 --> 00:00:01,000\n42\n")
    assert [s.text for s in segs] == ["42"]


def test_end_before_start_is_dropped_as_zero_length():
    segs = parse_srt(
        "1\n00:00:05,000 --> 00:00:04,000\nback\n\n2\n00:00:06,000 --> 00:00:07,000\nok\n"
    )
    assert [(s.start, s.end, s.text) for s in segs] == [(6.0, 7.0, "ok")]


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


def test_repeated_text_after_a_gap_is_not_merged():
    # Rolling duplicates touch or overlap; a sentence said again after a pause is real speech.
    vtt = (
        "WEBVTT\n\n00:00:00.000 --> 00:00:04.000\nsay it again\n\n"
        "00:00:05.000 --> 00:00:09.000\nsay it again\n"
    )
    assert [(s.start, s.end) for s in parse_vtt(vtt)] == [(0.0, 4.0), (5.0, 9.0)]


# YouTube auto-captions: each cue carries a line holding a single space, rolling two-line cues
# repeat the previous line, and 10 ms transition cues sit between them.
YOUTUBE_AUTO = (
    "WEBVTT\nKind: captions\nLanguage: en\n\n"
    "00:00:00.160 --> 00:00:02.270 align:start position:0%\n"
    " \n"
    "first<00:00:00.480><c> line</c><00:00:00.800><c> here</c>\n\n"
    "00:00:02.270 --> 00:00:02.280 align:start position:0%\n"
    "first line here\n"
    " \n\n"
    "00:00:02.280 --> 00:00:04.990 align:start position:0%\n"
    "first line here\n"
    "second<00:00:02.600><c> part</c><00:00:03.000><c> now</c>\n\n"
    "00:00:04.990 --> 00:00:05.000 align:start position:0%\n"
    "second part now\n"
    " \n\n"
    "00:00:05.000 --> 00:00:07.000 align:start position:0%\n"
    "second part now\n"
    "third<00:00:05.500><c.colorE5E5E5> bit</c>\n"
)


def test_youtube_auto_captions_keep_first_cue_and_drop_rolling_repeats():
    segs = parse_vtt(YOUTUBE_AUTO)
    assert [(s.start, s.end, s.text) for s in segs] == [
        (0.16, 2.27, "first line here"),
        (2.28, 4.99, "second part now"),
        (5.0, 7.0, "third bit"),
    ]
    assert sum(len(s.text.split()) for s in segs) == 8


def test_cues_shorter_than_50ms_are_dropped():
    srt = "1\n00:00:01,000 --> 00:00:01,040\nblink\n\n2\n00:00:02,000 --> 00:00:02,050\nkept\n"
    assert [s.text for s in parse_srt(srt)] == ["kept"]


def test_angle_brackets_in_spoken_text_survive():
    vtt = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nif x < y and z > w then <b>stop</b>\n"
    assert parse_vtt(vtt)[0].text == "if x < y and z > w then stop"


def test_known_caption_tags_are_stripped():
    vtt = (
        "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n"
        "<v.loud Narrator><c.yellow.bg_blue>a</c> <i>b</i> <U>c</U> <ruby>d<rt>e</rt></ruby>"
        " <lang en-GB>f</lang> <00:00:00.500>g</v>\n"
    )
    assert parse_vtt(vtt)[0].text == "a b c de f g"


def test_vtt_strips_x_word_timing_tags():
    # X (Twitter) wraps every cue in a custom <X-word-ms ...> tag with per-word timings.
    text = (
        "WEBVTT\n\n00:00:00.120 --> 00:00:01.120\n"
        "<X-word-ms ms=1000 index=1 character_ranges=0-8>Yesterday</X-word-ms>\n\n"
        "00:00:03.001 --> 00:00:06.102\n"
        "<X-word-ms ms=419,260 index=3 character_ranges=0-7,8-14>released that's</X-word-ms>\n"
    )
    assert [s.text for s in parse_vtt(text)] == ["Yesterday", "released that's"]


def test_a_cue_with_absurd_hours_is_skipped_not_an_overflow():
    huge = "9" * 400 + ":00:00.000 --> 00:01.000"
    text = f"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\na\n\n{huge}\nx\n"
    assert [s.text for s in parse_vtt(text)] == ["a"]
