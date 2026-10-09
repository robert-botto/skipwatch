from skipwatch.adapters.ytdlp_common import choose_caption_track


def test_caption_choice_prefers_manual_then_orig():
    info = {
        "language": "de",
        "subtitles": {"live_chat": [{}], "de": [{"ext": "vtt"}]},
        "automatic_captions": {"en": [{}], "de-orig": [{}], "ab": [{}]},
    }
    assert choose_caption_track(info) == ("de", "manual")
    info["subtitles"] = {}
    assert choose_caption_track(info) == ("de-orig", "auto")
    assert (
        choose_caption_track(
            {"language": None, "subtitles": {}, "automatic_captions": {"ab": [{}]}}
        )
        is None
    )


def test_caption_choice_manual_english_region_beats_original_language():
    info = {"language": "de", "subtitles": {"de": [{}], "en-US": [{}]}, "automatic_captions": {}}
    assert choose_caption_track(info) == ("en-US", "manual")


def test_caption_choice_manual_other_language_as_last_manual_resort():
    info = {"language": None, "subtitles": {"fr": [{}], "es": [{}]}, "automatic_captions": {}}
    assert choose_caption_track(info) == ("fr", "manual")


def test_caption_choice_live_chat_alone_is_not_a_caption_track():
    info = {
        "language": "en",
        "subtitles": {"live_chat": [{}]},
        "automatic_captions": {"en-orig": [{}]},
    }
    assert choose_caption_track(info) == ("en-orig", "auto")


def test_caption_choice_auto_english_source_without_orig_uses_english():
    info = {"language": "en", "subtitles": {}, "automatic_captions": {"en": [{}], "de": [{}]}}
    assert choose_caption_track(info) == ("en", "auto")


def test_caption_choice_never_takes_a_machine_translation():
    info = {"language": "ja", "subtitles": {}, "automatic_captions": {"en": [{}], "de": [{}]}}
    assert choose_caption_track(info) is None
