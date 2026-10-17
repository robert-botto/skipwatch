import time
from pathlib import Path

import pytest

from skipwatch.captions import parse_vtt
from skipwatch.captions_hls import HlsError, is_playlist, merge_webvtt, segment_urls

REC = Path(__file__).parents[1] / "fixtures" / "recorded" / "x"
PLAYLIST_URL = "https://video.twimg.com/amplify_video/2100714561389129730/pl/s0/DMUX4.m3u8"


def test_a_recorded_x_caption_playlist_is_recognised():
    assert is_playlist((REC / "captions-hls.m3u8").read_bytes())
    assert is_playlist(b"\xef\xbb\xbf\n#EXTM3U\n")
    assert not is_playlist((REC / "captions-hls.segment.vtt").read_bytes())
    assert not is_playlist(b'{"events": []}')


def test_segment_urls_resolve_against_the_playlist_url():
    text = (REC / "captions-hls.m3u8").read_text()
    assert segment_urls(text, PLAYLIST_URL) == [
        "https://video.twimg.com/subtitles/amplify_video/2100714561389129730/0/JWjpF_z1GMS3dPwx.vtt"
    ]


def test_relative_segment_urls_resolve_next_to_the_playlist():
    text = "#EXTM3U\n#EXTINF:6.0,\nseg0.vtt\n#EXTINF:6.0,\nhttps://other.example/seg1.vtt\n"
    assert segment_urls(text, "https://cdn.example/a/b/subs.m3u8") == [
        "https://cdn.example/a/b/seg0.vtt",
        "https://other.example/seg1.vtt",
    ]


@pytest.mark.parametrize(
    "text",
    [
        "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nvideo.m3u8\n",
        '#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="k"\n#EXTINF:6,\na.vtt\n',
        "#EXTM3U\n#EXT-X-ENDLIST\n",
    ],
    ids=["master", "encrypted", "empty"],
)
def test_playlists_that_are_not_plain_subtitle_segments_are_refused(text):
    with pytest.raises(HlsError):
        segment_urls(text, PLAYLIST_URL)


def test_too_many_segments_are_refused(monkeypatch):
    import skipwatch.captions_hls as hls

    monkeypatch.setattr(hls, "MAX_SEGMENTS", 2)
    text = "#EXTM3U\n" + "".join(f"#EXTINF:1,\n{n}.vtt\n" for n in range(3))
    with pytest.raises(HlsError, match="more than 2 segments"):
        segment_urls(text, PLAYLIST_URL)


def test_one_recorded_x_segment_merges_into_parseable_webvtt():
    merged = merge_webvtt([(REC / "captions-hls.segment.vtt").read_text()])
    segs = parse_vtt(merged)
    assert len(segs) == 6
    assert (segs[0].start, segs[0].end, segs[0].text) == (0.12, 1.12, "Yesterday")
    assert segs[2].text == "released that's 20 to 200 times faster"


SEG = "WEBVTT\nX-TIMESTAMP-MAP=MPEGTS:{mpegts},LOCAL:00:00:00.000\n\n{cue}\n{text}\n"


def test_timestamp_maps_shift_each_segment_relative_to_the_first():
    # Segment cues start at local zero; MPEGTS says where each segment sits (90 kHz clock).
    # The first map is the timeline's origin, as for the video (base PTS 10 s here).
    first = SEG.format(mpegts=900000, cue="00:00:01.000 --> 00:00:02.000", text="one")
    second = SEG.format(mpegts=900000 + 6 * 90000, cue="00:00:01.500 --> 00:00:03.000", text="two")
    segs = parse_vtt(merge_webvtt([first, second]))
    assert [(s.start, s.end, s.text) for s in segs] == [(1.0, 2.0, "one"), (7.5, 9.0, "two")]


def test_a_local_anchor_in_the_map_is_subtracted():
    seg = (
        "WEBVTT\nX-TIMESTAMP-MAP=LOCAL:00:00:10.000,MPEGTS:0\n\n00:00:12.000 --> 00:00:13.000\nhi\n"
    )
    base = SEG.format(mpegts=0, cue="00:00:00.000 --> 00:00:01.000", text="start")
    segs = parse_vtt(merge_webvtt([base, seg]))
    assert [(s.start, s.end) for s in segs] == [(0.0, 1.0), (2.0, 3.0)]


def test_segments_without_a_map_keep_their_own_times():
    a = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\na\n"
    b = "WEBVTT\n\n01:00:05.250 --> 01:00:06.000\nb\n"
    segs = parse_vtt(merge_webvtt([a, b]))
    assert [(s.start, s.end, s.text) for s in segs] == [(1.0, 2.0, "a"), (3605.25, 3606.0, "b")]


def test_a_whitespace_flood_is_linear_when_shifted():
    # A hostile segment of blank and space-only lines must not make the shift quadratic.
    first = SEG.format(mpegts=0, cue="00:00:00.000 --> 00:00:01.000", text="a")
    flood = "WEBVTT\nX-TIMESTAMP-MAP=MPEGTS:900000,LOCAL:00:00:00.000\n" + "\n \n" * 25_000
    started = time.monotonic()
    merge_webvtt([first, flood])
    assert time.monotonic() - started < 1.0


@pytest.mark.parametrize(
    "mapping",
    [
        "MPEGTS:" + "9" * 4000 + ",LOCAL:00:00.000",
        "MPEGTS:900000,LOCAL:5",
        "MPEGTS:900000,LOCAL:0:inf",
        "MPEGTS:900000,LOCAL:0:nan",
        "MPEGTS:0,LOCAL:" + "9" * 400 + ":00:00.000",
        "MPEGTS:-5,LOCAL:00:00.000",
        "MPEGTS:1e9,LOCAL:00:00.000",
    ],
    ids=["huge-mpegts", "local-no-colon", "local-inf", "local-nan", "huge-hours", "neg", "exp"],
)
def test_a_malformed_timestamp_map_is_ignored(mapping):
    # p1.py: these crashed with OverflowError, IndexError or ValueError
    first = SEG.format(mpegts=0, cue="00:00:00.000 --> 00:00:01.000", text="a")
    second = f"WEBVTT\nX-TIMESTAMP-MAP={mapping}\n\n00:00:05.000 --> 00:00:06.000\nb\n"
    segs = parse_vtt(merge_webvtt([first, second]))
    assert [(s.start, s.text) for s in segs] == [(0.0, "a"), (5.0, "b")]


def test_a_cue_with_absurd_hours_is_left_alone():
    first = SEG.format(mpegts=0, cue="00:00:00.000 --> 00:00:01.000", text="a")
    huge = "9" * 400 + ":00:00.000 --> 00:01.000"
    second = SEG.format(mpegts=900000, cue=huge, text="x")
    merged = merge_webvtt([first, second])  # no OverflowError
    assert huge in merged  # not a timing line SkipWatch shifts


def test_mpegts_is_at_most_ten_digits():
    # MPEGTS is a 33-bit clock (2**33 - 1 = 8589934591, ten digits); eleven digits is malformed.
    first = SEG.format(mpegts=0, cue="00:00:00.000 --> 00:00:01.000", text="a")
    widest = SEG.format(mpegts=2**33 - 1, cue="00:00:00.000 --> 00:00:01.000", text="b")
    too_wide = SEG.format(mpegts="1" + "0" * 10, cue="00:00:05.000 --> 00:00:06.000", text="c")
    segs = parse_vtt(merge_webvtt([first, widest, too_wide]))
    assert [(s.start, s.text) for s in segs] == [(0.0, "a"), (95443.718, "b"), (5.0, "c")]
