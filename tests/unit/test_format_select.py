import json
from pathlib import Path

import pytest

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.providers.content_free import select_format


def f(fid, w, h, size, v="avc1", a="none", tbr=None):
    return {
        "format_id": fid,
        "width": w,
        "height": h,
        "filesize": size,
        "vcodec": v,
        "acodec": a,
        "tbr": tbr,
    }


AUDIO = [
    {"format_id": "140", "vcodec": "none", "acodec": "mp4a", "filesize": 3_000_000},
    {"format_id": "251", "vcodec": "none", "acodec": "opus", "filesize": 2_500_000},
]


def test_r_ing_4_smallest_at_or_above_720_capped_at_1080():
    info = {
        "duration": 600,
        "formats": [
            f("160", 256, 144, 1e6),
            f("136", 1280, 720, 40e6),
            f("398", 1280, 720, 30e6),
            f("137", 1920, 1080, 90e6),
            f("401", 3840, 2160, 400e6),
        ]
        + AUDIO,
    }
    assert select_format(info) == "398+251"


def test_r_ing_4_vertical_uses_short_side():
    info = {
        "duration": 30,
        "formats": [
            f("a", 576, 1024, 4e6),
            f("b", 720, 1280, 6e6),
            f("c", 1080, 1920, 9e6),
            f("d", 2160, 3840, 40e6),
        ]
        + AUDIO,
    }
    assert select_format(info).startswith("b+")


def test_r_ing_4_below_720_takes_the_largest_available():
    info = {
        "duration": 30,
        "formats": [f("s", 320, 240, 1e6, a="mp4a"), f("m", 640, 480, 2e6, a="mp4a")],
    }
    assert select_format(info) == "m"


def test_unknown_sizes_fall_back_to_bitrate_times_duration():
    info = {
        "duration": 100,
        "formats": [
            f("x", 1280, 720, None, a="mp4a", tbr=3000),
            f("y", 1920, 1080, None, a="mp4a", tbr=1500),
        ],
    }
    assert select_format(info) == "y"


def test_only_above_cap_takes_the_smallest_resolution():
    info = {
        "duration": 10,
        "formats": [f("k4", 3840, 2160, 9e6, a="mp4a"), f("k2", 2560, 1440, 5e6, a="mp4a")],
    }
    assert select_format(info) == "k2"


def test_lower_max_height_moves_the_window():
    info = {
        "duration": 10,
        "formats": [f("p4", 640, 480, 2e6, a="mp4a"), f("p7", 1280, 720, 4e6, a="mp4a")],
    }
    assert select_format(info, max_short_side=480) == "p4"


def test_storyboards_and_drm_formats_are_ignored():
    story = {
        "format_id": "sb0",
        "vcodec": "none",
        "acodec": "none",
        "width": 1280,
        "height": 720,
        "filesize": 1,
    }
    drm = dict(f("drm", 1280, 720, 1, a="mp4a"), has_drm=True)
    info = {"duration": 10, "formats": [story, drm, f("ok", 1280, 720, 5e6, a="mp4a")]}
    assert select_format(info) == "ok"


def test_audio_only_source_takes_the_smallest_audio():
    assert select_format({"duration": 10, "formats": AUDIO}) == "251"


def test_video_without_any_audio_only_format_is_alone():
    assert select_format({"duration": 10, "formats": [f("v", 1280, 720, 5e6)]}) == "v"


def test_formats_with_unknown_codecs_use_best():
    info = {
        "duration": 10,
        "formats": [{"format_id": "0", "url": "https://example.com/a.mp4", "ext": "mp4"}],
    }
    assert select_format(info) == "best"


def test_no_formats_is_no_content():
    with pytest.raises(SkipwatchError) as e:
        select_format({"duration": 10, "formats": []})
    assert e.value.code == ExitCode.NO_CONTENT


REC = Path(__file__).resolve().parents[1] / "fixtures" / "recorded" / "youtube"


def test_recorded_youtube_formats_pick_the_smallest_720p_and_smallest_audio():
    info = json.loads((REC / "manual-captions.info.json").read_text())
    assert select_format(info) == "398+139"  # av01 720p (24.8 MB), m4a 48 kbps (5.29 MB)


def test_recorded_vertical_fixture_picks_720x1280():
    info = json.loads((REC / "vertical-short.info.json").read_text())
    assert select_format(info) == "b+251"


def test_audio_matching_the_video_language_beats_a_smaller_dub():
    info = json.loads((REC / "dubbed-audio.info.json").read_text())
    assert select_format(info) == "398+139"  # 139 is the English original, 139-es a smaller dub


def test_audio_marked_original_wins_when_the_language_is_unknown():
    info = json.loads((REC / "dubbed-audio.info.json").read_text())
    info["language"] = None
    assert select_format(info).endswith("+139")


def test_without_language_hints_the_smallest_audio_wins():
    audio = [
        {"format_id": "big", "vcodec": "none", "acodec": "opus", "filesize": 9, "language": "de"},
        {"format_id": "small", "vcodec": "none", "acodec": "opus", "filesize": 1, "language": "fr"},
    ]
    assert select_format({"duration": 1, "language": None, "formats": audio}) == "small"
