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

_URL = re.compile(r"https?://\S+")
# twitter-text v3: code points in these ranges weigh 1, every other code point weighs 2
_LIGHT = ((0x0000, 0x10FF), (0x2000, 0x200D), (0x2010, 0x201F), (0x2032, 0x2037))


def _char_weight(ch: str) -> int:
    cp = ord(ch)
    return 1 if any(lo <= cp <= hi for lo, hi in _LIGHT) else 2


def weighted_length(text: str) -> int:
    """Length as X counts it: each http(s) URL is 23, wide characters are 2, the rest 1."""
    total = 0
    last = 0
    for match in _URL.finditer(text):
        total += sum(_char_weight(ch) for ch in text[last : match.start()]) + URL_WEIGHT
        last = match.end()
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
    for keep in range(len(value) - 1, -1, -1):
        cut = value[:keep].rstrip() + ELLIPSIS
        if weighted_length(render(cut)) <= LIMIT:
            return cut
    return None


def share_text(manifest: Manifest) -> ShareResult:
    """Copy-ready thank-you post. Raises UNSUPPORTED_SOURCE for a local-file skill."""
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
