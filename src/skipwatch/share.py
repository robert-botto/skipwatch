"""A copy-ready thank-you post for a skill's creator (spec 4.2, 14.1 creator loop).

The text fits one X post: X counts every URL as 23 characters and characters outside its Latin
and punctuation ranges (emoji, CJK) as 2. A title that would not fit is shortened with "...".
"""

import re
from collections.abc import Callable

from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import Manifest, ShareResult
from skipwatch.project import REPO_URL

URL_WEIGHT = 23  # X counts every URL as 23 characters
LIMIT = 280
ELLIPSIS = "..."

# A scheme URL, or a bare domain (x.ai, github.com/foo) that X also links: a dotted name whose
# last label is two or more letters. Trailing punctuation is stripped before counting, as X does.
_LINK = re.compile(r"https?://\S+|[\w-]+(?:\.[\w-]+)*\.[^\W\d_]{2,}(?:/\S*)?")
_TRAILING = ".,;:!?\"')"
TITLE_CAP = 500  # longer titles are cut before shortening, so shortening stays cheap
# twitter-text v3: code points in these ranges weigh 1, every other code point weighs 2
_LIGHT = ((0x0000, 0x10FF), (0x2000, 0x200D), (0x2010, 0x201F), (0x2032, 0x2037))


def _char_weight(ch: str) -> int:
    cp = ord(ch)
    return 1 if any(lo <= cp <= hi for lo, hi in _LIGHT) else 2


def weighted_length(text: str) -> int:
    """Length as X counts it, rounded up where unsure: each http(s) URL is 23, a bare domain is
    23 or its own length when longer (X may not link it), wide characters are 2, the rest 1."""
    total = 0
    last = 0
    for match in _LINK.finditer(text):
        link = match.group().rstrip(_TRAILING)
        if not link:
            continue
        start = match.start()
        total += sum(_char_weight(ch) for ch in text[last:start])
        raw = sum(_char_weight(ch) for ch in link)
        total += URL_WEIGHT if link.startswith(("http://", "https://")) else max(URL_WEIGHT, raw)
        last = start + len(link)
    return total + sum(_char_weight(ch) for ch in text[last:])


def _clean(value: str | None) -> str | None:
    """One line, single spaces; empty is missing."""
    if value is None:
        return None
    return " ".join(value.split()) or None


def _render(author: str | None, title: str | None, steps: int, url: str) -> str:
    subject = f'"{title}"' if title is not None else "this video"
    opening = (
        f"Thanks {author} for {subject}." if author else f"Thanks to the creator of {subject}."
    )
    noun = "step" if steps == 1 else "steps"
    return (
        f"{opening} I turned it into a Claude Code skill with SkipWatch: {steps} {noun},"
        " each traced to a moment in your video.\n"
        "\n"
        f"Try it: /skipwatch {url}\n"
        f"{REPO_URL}"
    )


def _shorten(value: str, render: Callable[[str], str]) -> str | None:
    """value, or its longest prefix plus "..." whose rendering fits; None when nothing fits."""
    if weighted_length(render(value)) <= LIMIT:
        return value
    value = value[:TITLE_CAP]  # never fits whole: every character weighs at least 1
    for keep in range(len(value) - 1, -1, -1):
        cut = value[:keep].rstrip() + ELLIPSIS
        if weighted_length(render(cut)) <= LIMIT:
            return cut
    return None


def share_text(manifest: Manifest) -> ShareResult:
    """Copy-ready thank-you post. Raises PRIVATE_CONTENT for a skill fetched with cookies
    (spec 10) and UNSUPPORTED_SOURCE for a local-file skill."""
    if manifest.fetched_with_cookies:
        raise SkipwatchError(
            ExitCode.PRIVATE_CONTENT,
            f"{manifest.name} was made from content fetched with your browser cookies,"
            " so it cannot be shared",
        )
    src = manifest.source
    url = src.canonical_url or src.url
    if src.platform == "local" or not url:
        raise SkipwatchError(
            ExitCode.UNSUPPORTED_SOURCE,
            f"{manifest.name} was made from a local file; there is no public video to credit",
        )
    steps = manifest.counts.steps
    author, title = _clean(src.author), _clean(src.title)

    if title is not None:
        title = _shorten(title, lambda t: _render(author, t, steps, url)) or ELLIPSIS
    if author is not None:
        # only a very long author name gets here shortened; titles are cut first
        author = _shorten(author, lambda a: _render(a, title, steps, url)) or ELLIPSIS
    text = _render(author, title, steps, url)
    return ShareResult(
        name=manifest.name,
        text=text,
        weighted_length=weighted_length(text),
        install_line=f"/skipwatch {url}",
    )
