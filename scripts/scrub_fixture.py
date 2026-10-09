"""Scrub a recorded yt-dlp or provider fixture before it is committed.

Recording fixtures: this script is a safety net, not a review. A human must read every
recorded fixture before it is committed. Known residuals it does not catch: JSON stringified
inside a string value, opaque bare tokens under innocent keys, YouTube `visitor_data`, and
`client_id` values.

Keys: compared casefolded and split into words (snake, kebab and camel case). A key is dropped
when any word is sensitive (cookie, header, auth, key, secret, password, token, session,
signature, sig, csrf, xsrf, email, ip, bearer, jwt, credential, otp, ...), the key names an
account or user id, or it is a session cookie name (`sid`, `*sid`, `*sessid`). Creator
attribution (`author`, `uploader`) and `extractor_key` stay: adapters need them.

Strings, in values and in keys: every URL loses its query and fragment (`?SCRUBBED`) and any
path-style signature (`/signature/X/`, `/sig/X/`), protocol-relative URLs (`//host/...`)
included; `Bearer <token>` and JWT-shaped strings, emails, IPv4 and IPv6 literals are replaced.
Media URLs (formats, fragments, manifests) are cut to scheme and host.
Usage: scrub_fixture.py IN -o OUT. scripts/record_fixture.py imports `scrub` directly.
"""

import argparse
import ipaddress
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SENSITIVE_WORDS = {
    "cookie", "header", "auth", "authorization", "authentication", "key", "apikey", "secret",
    "password", "passwd", "token", "session", "sessionid", "signature", "sig", "csrf", "xsrf",
    "email", "ip", "bearer", "jwt", "credential", "passcode", "pwd", "otp", "authuser",
}  # fmt: skip
# Joined spellings that word splitting cannot see ("setcookie", "sessiontoken").
SENSITIVE_PARTS = (
    "cookie", "header", "password", "passwd", "secret", "token", "session", "signature",
    "csrf", "xsrf", "apikey", "accountid", "userid", "email", "authorization",
)  # fmt: skip
SENSITIVE_PAIRS = {("account", "id"), ("user", "id")}
KEPT_KEYS = {"extractor_key", "ie_key"}
DROPPED_KEYS = {"requested_subtitles"}  # holds signed subtitle URLs under ordinary names

# Lists whose dicts describe one media rendition; their `url` is cut to scheme and host.
MEDIA_LISTS = {"formats", "requested_formats", "requested_downloads", "fragments"}
HOST_ONLY_KEYS = {"manifest_url", "fragment_base_url"}

URL_RE = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s\"'<>]+", re.IGNORECASE)
PROTOCOL_RELATIVE_RE = re.compile(r"(?<![:\w])//[A-Za-z0-9.-]+\.[A-Za-z]{2,}/[^\s\"'<>]*")
BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[^\s\"'<>]+")
PATH_SIG_RE = re.compile(
    r"/(signature|sig|lsig|sparams|key|token|expire|ip|ei)/[^/?#\s]+", re.IGNORECASE
)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
IPV4_RE = re.compile(r"\b\d{1,3}(\.\d{1,3}){3}\b")
IPV6_CANDIDATE_RE = re.compile(r"(?<![0-9A-Za-z:])[0-9A-Fa-f:]*:[0-9A-Fa-f:]*(?![0-9A-Za-z:])")
EMAIL_PLACEHOLDER = "redacted@example.invalid"


def _words(key: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", key)
    words = [w.casefold() for w in re.split(r"[^A-Za-z0-9]+", spaced) if w]
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words]


def _dropped(key: str) -> bool:
    folded = key.casefold()
    if folded in KEPT_KEYS:
        return False
    if folded in DROPPED_KEYS or folded.endswith(("sid", "sessid")):
        return True  # session cookies: PHPSESSID, SAPISID, __Secure-3PSID, HSID, dsid
    words = _words(key)
    if any(w in SENSITIVE_WORDS for w in words):
        return True
    if any(pair in SENSITIVE_PAIRS for pair in zip(words, words[1:], strict=False)):
        return True
    joined = "".join(words)
    return any(part in joined for part in SENSITIVE_PARTS)


def _scrub_url(url: str) -> str:
    cut = min((i for i in (url.find("?"), url.find("#")) if i >= 0), default=-1)
    if cut >= 0:
        url = url[:cut] + "?SCRUBBED"
    return PATH_SIG_RE.sub(lambda m: f"/{m.group(1)}/SCRUBBED", url)


def _host_only(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return _scrub_string(url)
    if not parts.scheme or not parts.hostname:
        return _scrub_string(url)
    return _scrub_string(f"{parts.scheme}://{parts.hostname}")


def _ipv6(match: re.Match[str]) -> str:
    text = match.group(0)
    if text.count(":") < 2:
        return text
    try:
        ipaddress.IPv6Address(text)
    except ValueError:
        return text
    return "::"


def _scrub_string(value: str) -> str:
    value = BEARER_RE.sub("SCRUBBED", value)
    value = JWT_RE.sub("SCRUBBED", value)
    value = URL_RE.sub(lambda m: _scrub_url(m.group(0)), value)
    value = PROTOCOL_RELATIVE_RE.sub(lambda m: _scrub_url(m.group(0)), value)
    value = EMAIL_RE.sub(EMAIL_PLACEHOLDER, value)
    value = IPV4_RE.sub("0.0.0.0", value)
    return IPV6_CANDIDATE_RE.sub(_ipv6, value)


def _scrub_dict(obj: dict[Any, Any], media: bool) -> dict[Any, Any]:
    media = media or "format_id" in obj
    out: dict[Any, Any] = {}
    for key, value in obj.items():
        name = str(key)
        if _dropped(name):
            continue
        folded = name.casefold()
        if isinstance(value, str) and (folded in HOST_ONLY_KEYS or (media and folded == "url")):
            scrubbed: Any = _host_only(value)
        else:
            scrubbed = _scrub(value, media=folded in MEDIA_LISTS)
        out[_scrub_string(key) if isinstance(key, str) else key] = scrubbed
    return out


def _scrub(obj: Any, media: bool = False) -> Any:
    if isinstance(obj, dict):
        return _scrub_dict(obj, media)
    if isinstance(obj, list):
        return [_scrub(item, media) for item in obj]
    if isinstance(obj, str):
        return _scrub_string(obj)
    return obj


def scrub(obj: Any) -> Any:
    return _scrub(obj)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    text = json.dumps(scrub(data), indent=2, sort_keys=True) + "\n"
    Path(args.output).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
