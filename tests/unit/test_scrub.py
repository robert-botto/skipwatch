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
                "url": "https://rr1.googlevideo.com/videoplayback?sig=SECRET&ip=203.0.113.7",
                "height": 360,
                "width": 640,
                "filesize": 10,
            }
        ],
        "thumbnail": "https://i.ytimg.com/vi/x/hq.jpg?sqp=SIGNED",
    }
    out = run(tmp_path, data)
    text = json.dumps(out)
    assert "SECRET" not in text and "203.0.113.7" not in text and "SIGNED" not in text
    assert "Cookie" not in text and "cookies" not in out
    assert out["formats"][0]["url"] == "https://rr1.googlevideo.com"  # host only (plan)
    assert out["uploader"] == "@creator"  # attribution data stays


def test_scrub_drops_token_session_and_signed_subtitle_keys(tmp_path):
    data = {
        "_cookies": "c",
        "__x_forwarded_for_ip": "198.51.100.23",
        "requested_subtitles": {"en": {"url": "https://x.example/s?sig=1"}},
        "nested": {"access_token": "t", "SessionId": "s", "keep": "k"},
        "description": "from 192.0.2.10 with love",
    }
    out = run(tmp_path, data)
    assert out == {"description": "from 0.0.0.0 with love", "nested": {"keep": "k"}}


def test_scrub_is_idempotent(tmp_path):
    data = {"formats": [{"url": "https://a.example/v?x=1"}]}
    once = run(tmp_path, data)
    assert run(tmp_path, once) == once


def test_scrub_adversarial_nested_mixed_case(tmp_path):
    secrets = [
        "BEARERSECRET", "APIKEYSECRET", "PASSSECRET", "AUTHSECRET", "SIGSECRET", "CSRFSECRET",
        "ACCTSECRET", "USERSECRET", "HDRSECRET", "COOKIESECRET", "SETCOOKIESECRET", "JARSECRET",
        "operator@example.com", "2001:db8::42", "10.1.2.3", "MIDQUERY", "UPPERQUERY", "FRAGSIG",
        "PATHSIG1", "PATHSIG2", "MANIFESTPATH", "FRAGPATH", "10.9.8.7", "XKEYSECRET", "APIKEY2",
        "SESSSECRET", "XSRFSECRET", "TOKSECRET",
    ]  # fmt: skip
    data = {
        "Info": {
            "headers": {"Authorization": "Bearer BEARERSECRET"},
            "HTTP_HEADERS": {"X": "HDRSECRET"},
            "Http_Headers": {"X": "HDRSECRET"},
            "X-Api-Key": "XKEYSECRET",
            "api_key": "APIKEYSECRET",
            "apiKey": "APIKEY2",
            "Password": "PASSSECRET",
            "auth": "AUTHSECRET",
            "signature": "SIGSECRET",
            "csrf": "CSRFSECRET",
            "X-XSRF-Token": "XSRFSECRET",
            "sessionId": "SESSSECRET",
            "access_token": "TOKSECRET",
            "account_id": "ACCTSECRET",
            "userId": "USERSECRET",
            "COOKIE": "COOKIESECRET",
            "set-cookie": "SETCOOKIESECRET",
            "cookie_jar": ["JARSECRET"],
            "10.9.8.7": "KEYIP",
        },
        "description": (
            "mail operator@example.com from 10.1.2.3 or 2001:db8::42, see "
            "https://example.com/page?q=MIDQUERY and HTTPS://EXAMPLE.COM/x?Q=UPPERQUERY "
            "or https://example.com/y#sig=FRAGSIG"
        ),
        "webpage_url": "https://rr3.googlevideo.com/videoplayback/signature/PATHSIG1/id/1",
        "other": "https://cdn.example/v/sig/PATHSIG2/file.mp4",
        "manifest_url": "https://manifest.googlevideo.com/api/manifest/MANIFESTPATH",
        "requested_formats": [{"fragment_base_url": "https://a.example/FRAGPATH/"}],
        "fragments": [{"url": "https://a.example/FRAGPATH/seg1"}],
        "uploader": "@creator",
        "author": "Creator Name",
        "extractor_key": "Youtube",
        "uploader_url": "https://www.youtube.com/@creator",
        "timestamp_text": "00:01:02",
    }
    out = run(tmp_path, data)
    text = json.dumps(out)
    leaked = [s for s in secrets if s.lower() in text.lower()]
    assert leaked == []
    assert out["uploader"] == "@creator" and out["author"] == "Creator Name"
    assert out["extractor_key"] == "Youtube"
    assert out["uploader_url"] == "https://www.youtube.com/@creator"
    assert out["timestamp_text"] == "00:01:02"
    assert out["manifest_url"] == "https://manifest.googlevideo.com"
    assert out["fragments"][0]["url"] == "https://a.example"
    assert "https://example.com/page?SCRUBBED" in out["description"]
    assert run(tmp_path, out) == out  # idempotent on the adversarial case too


def test_scrub_more_credential_keys_and_sid_cookies(tmp_path):
    keys = [
        "bearer", "jwt", "credential", "Credentials", "passcode", "pwd", "otp", "authuser",
        "x-goog-authuser", "sid", "PHPSESSID", "SAPISID", "__Secure-3PSID", "HSID", "SSID",
        "APISID", "dsid",
    ]  # fmt: skip
    data = {"nested": {k: f"LEAK{i}X" for i, k in enumerate(keys)}, "keep": "ok"}
    out = run(tmp_path, data)
    assert out == {"keep": "ok", "nested": {}}


def test_scrub_protocol_relative_urls(tmp_path):
    data = {
        "a": "//cdn.example.com/v.mp4?sig=PRQUERY#PRFRAG",
        "b": '<img src=//img.example.com/sig/PRPATH/x.jpg> and <a src="//c.example.org/p?t=PRQ2">',
        "ratio": "16//9 and a//b",
    }
    out = run(tmp_path, data)
    text = json.dumps(out)
    for leak in ("PRQUERY", "PRFRAG", "PRPATH", "PRQ2"):
        assert leak not in text
    assert out["a"] == "//cdn.example.com/v.mp4?SCRUBBED"
    assert out["ratio"] == "16//9 and a//b"


def test_scrub_bearer_and_jwt_values_without_telltale_keys(tmp_path):
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.SIGNATUREPART"
    data = {"note": f"call with Bearer BEARERVALUE then {jwt} done", "list": [jwt]}
    out = run(tmp_path, data)
    text = json.dumps(out)
    assert "BEARERVALUE" not in text and "eyJ" not in text and "SIGNATUREPART" not in text
    assert out["note"] == "call with SCRUBBED then SCRUBBED done"
    assert run(tmp_path, out) == out


def test_scrub_percent_encoded_ip_inside_a_url_path(tmp_path):
    hls = (
        "https://manifest.example.com/api/timedtext/tts_params/"
        "caps%3Dasr%26ip%3D203.0.113.7%26ipbits%3D0/playlist/index.m3u8"
    )
    data = {"tracks": [{"ext": "vtt", "url": hls}], "note": f"see {hls} and ip%253D198.51.100.23"}
    out = run(tmp_path, data)
    text = json.dumps(out)
    assert "203.0.113.7" not in text and "198.51.100.23" not in text
    assert "203%2E0" not in text
    assert run(tmp_path, out) == out


def test_scrub_ip_parameter_in_a_path_is_scrubbed_even_when_not_an_address(tmp_path):
    out = run(tmp_path, {"u": "https://h.example.com/a/ip=203.0.113.7/b", "v": "x?y&ip=abcd&z"})
    assert "203.0.113.7" not in json.dumps(out)
    assert "ip=SCRUBBED" in out["u"] and "abcd" not in out["v"]


def test_scrub_percent_encoded_email(tmp_path):
    out = run(tmp_path, {"d": "contact a.person%40example.com or b%2540example.org"})
    text = json.dumps(out)
    assert "a.person" not in text and "b%40" not in text and "b@" not in text
