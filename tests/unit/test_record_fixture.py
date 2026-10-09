import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import record_fixture as rf  # noqa: E402

EM_DASH = "\u2014"


def test_percent_encoded_ip_in_a_path_is_caught():
    url = "https://m.googlevideo.com/api/x/tts_params/caps%3Dasr%26ip%3D203.0.113.7%26v%3D1"
    assert rf.leaked_ips(url) == {"203.0.113.7"}


def test_codec_strings_and_placeholder_ip_are_not_leaks():
    assert rf.leaked_ips('"vcodec": "vp09.00.21.08", "ip": "0.0.0.0"') == set()


def test_trim_cuts_track_and_format_urls_to_a_scrubbed_host():
    info = {
        "id": "x",
        "cookies": "SID=1",
        "formats": [{"format_id": "1", "url": "https://rr5---sn-abcd1234.googlevideo.com/v?a=1",
                     "http_headers": {"Cookie": "a"}}],
        "automatic_captions": {"en": [{"ext": "vtt", "url": "https://m.g.com/ip/198.51.100.23/x"}]},
    }  # fmt: skip
    out = rf.trim(info)
    assert "cookies" not in out and "http_headers" not in out["formats"][0]
    assert out["formats"][0]["url"] == "https://rr5---sn-SCRUBBED.googlevideo.com"
    assert out["automatic_captions"] == {"en": [{"ext": "vtt", "url": "https://m.g.com"}]}


def test_caption_text_is_scrubbed_and_free_of_em_dashes():
    raw = json.dumps({"events": [{"segs": [{"utf8": f"mail a@b.com {EM_DASH} ok"}]}]})
    body = rf.caption_text(raw.encode(), ".json3")
    assert "a@b.com" not in body and EM_DASH not in body
    vtt = rf.caption_text(
        f"WEBVTT\n\n00:00.000 --> 00:01.000\nx {EM_DASH} y a@b.com\n".encode(), ".vtt"
    )
    assert EM_DASH not in vtt and "a@b.com" not in vtt


def test_recorder_refuses_to_run_without_the_live_opt_in(monkeypatch):
    monkeypatch.delenv("SKIPWATCH_LIVE", raising=False)
    monkeypatch.setattr(
        sys, "argv", ["record_fixture.py", "https://x", "--name", "n", "--platform", "p"]
    )
    assert rf.main() == 2


def test_committed_recordings_hold_no_ip_email_or_em_dash():
    root = Path(__file__).resolve().parents[1] / "fixtures" / "recorded"
    files = [p for p in root.rglob("*") if p.is_file()]
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert rf.leaked_ips(text) == set(), path
        assert EM_DASH not in text, path
        assert "---sn-" not in text.replace("---sn-scrubbed", ""), path
