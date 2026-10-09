import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "scrub_fixture.py"


def run(tmp_path, data):
    p = tmp_path / "in.json"
    p.write_text(json.dumps(data))
    out = tmp_path / "out.json"
    subprocess.run([sys.executable, str(SCRIPT), str(p), "-o", str(out)], check=True)
    return json.loads(out.read_text())


def test_scrub_removes_cookies_headers_and_signed_queries(tmp_path):
    data = {
        "http_headers": {"Cookie": "a=b"},
        "cookies": "x",
        "uploader": "@creator",
        "formats": [
            {
                "format_id": "18",
                "url": "https://rr1.googlevideo.com/videoplayback?sig=SECRET&ip=1.2.3.4",
                "height": 360,
                "width": 640,
                "filesize": 10,
            }
        ],
        "thumbnail": "https://i.ytimg.com/vi/x/hq.jpg?sqp=SIGNED",
    }
    out = run(tmp_path, data)
    text = json.dumps(out)
    assert "SECRET" not in text and "1.2.3.4" not in text and "SIGNED" not in text
    assert "Cookie" not in text and "cookies" not in out
    assert out["formats"][0]["url"] == "https://rr1.googlevideo.com/videoplayback?SCRUBBED"
    assert out["uploader"] == "@creator"  # attribution data stays


def test_scrub_drops_token_session_and_signed_subtitle_keys(tmp_path):
    data = {
        "_cookies": "c",
        "__x_forwarded_for_ip": "9.9.9.9",
        "requested_subtitles": {"en": {"url": "https://x.example/s?sig=1"}},
        "nested": {"access_token": "t", "SessionId": "s", "keep": "k"},
        "description": "from 10.0.0.1 with love",
    }
    out = run(tmp_path, data)
    assert out == {"description": "from 0.0.0.0 with love", "nested": {"keep": "k"}}


def test_scrub_is_idempotent(tmp_path):
    data = {"formats": [{"url": "https://a.example/v?x=1"}]}
    once = run(tmp_path, data)
    assert run(tmp_path, once) == once
