"""X (x.com, twitter.com) posts on the free route (8.3; plan decisions after the M3 spike).

- yt-dlp's `id` is the media id, so the post id comes from the status path of `webpage_url`
  and the canonical URL is `https://x.com/i/status/<post id>` (decision 1).
- `description` is the full post text (R-ING-1); t.co links in it are resolved with one HEAD
  each. A link to the post's own media is dropped, other x.com links are never fetched as
  pages (they are a JavaScript shell), and up to 5 other pages are fetched for context.
- A post with no media of its own that links another post gets that post's video from yt-dlp
  with no error, under the requesting post's metadata. When the first linked post's video has
  the same length, the bundle credits the linked post: source describes it, the requested
  post's text goes into context.thread with its URL, context.links records the linked post,
  and route.fallbacks carries "video came from a linked post: <url>" (decision 2).
- A post with no video raises NoMediaError; ingest hands it to the text adapter (issue 8).
"""

import re
import time
from urllib.parse import urlsplit

from skipwatch.adapters.base import IngestOptions
from skipwatch.adapters.ytdlp_common import (
    _posted_at,
    author_name_of,
    author_of,
    build_video_bundle,
)
from skipwatch.detect import Detected, platform_for_host
from skipwatch.models import IngestBundle, LinkContext, ProviderCall
from skipwatch.providers import content_free, links
from skipwatch.providers.content_free import FreeRouteError
from skipwatch.workdir import WorkDir

SHORT_LINK_HOSTS = frozenset({"t.co"})
SAME_VIDEO_TOLERANCE_S = 1.0
_STATUS = re.compile(
    r"^https?://(?:[\w-]+\.)?(?:x|twitter)\.com/(?:i/(?:web/)?|\w+/)status(?:es)?/(\d+)",
    re.IGNORECASE,
)


def post_id(url: str | None) -> str | None:
    match = _STATUS.match(url or "")
    return match.group(1) if match else None


def canonical(post: str) -> str:
    return f"https://x.com/i/status/{post}"


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _expand(urls: list[str], calls: list[ProviderCall]) -> list[str]:
    """Short links resolved (unresolvable ones dropped); everything else as it is."""
    expanded = []
    for url in urls:
        target = links.resolve(url, calls) if _host(url) in SHORT_LINK_HOSTS else url
        if target:
            expanded.append(target)
    return expanded


def _same_video(info: dict, duration_s: float | None) -> bool:
    length = info.get("duration")
    if not isinstance(length, int | float) or duration_s is None:
        return False
    return abs(float(length) - duration_s) <= SAME_VIDEO_TOLERANCE_S


def _credit_linked_post(
    bundle: IngestBundle, linked: str, opts: IngestOptions, calls: list[ProviderCall]
) -> IngestBundle | None:
    """The bundle re-attributed to the linked post, or None when its video is not this one."""
    url = canonical(linked)
    started = time.monotonic()
    try:
        info = content_free.extract(url, opts)
    except FreeRouteError as exc:
        calls.append(content_free.call_log("yt-dlp.metadata", False, started, exc.first_line))
        return None
    calls.append(content_free.call_log("yt-dlp.metadata", True, started))
    if not _same_video(info, bundle.source.duration_s):
        return None
    requested = bundle.source.canonical_url or bundle.source.url
    source = bundle.source.model_copy(
        update={
            "url": url,
            "canonical_url": url,
            "author": author_of(info, "x"),
            "author_name": author_name_of(info, "x"),
            "title": info.get("title"),
            "posted_at": _posted_at(info),
        }
    )
    text = info.get("description") or ""
    record = LinkContext(url=url, title=info.get("title"), text=text[: links.MAX_CHARS])
    context = bundle.context.model_copy(
        update={
            "post_text": text or None,
            "thread": [f"Requested post {requested}: {bundle.context.post_text or ''}"],
            "links": [record, *bundle.context.links],
        }
    )
    note = f"video came from a linked post: {url}"
    route = bundle.route.model_copy(update={"fallbacks": [*bundle.route.fallbacks, note]})
    return bundle.model_copy(update={"source": source, "context": context, "route": route})


class XAdapter:
    def build(self, detected: Detected, work: WorkDir, opts: IngestOptions) -> IngestBundle:
        bundle = build_video_bundle(detected, work, opts, "x")
        calls = list(bundle.provider_calls)
        own = post_id(bundle.source.canonical_url) or post_id(detected.value)
        urls = _expand(links.extract_urls(bundle.context.post_text or ""), calls)
        statuses = [post_id(u) for u in urls]
        has_own_media = own is not None and own in statuses
        others = [s for s in statuses if s is not None and s != own]
        pages = [u for u in urls if platform_for_host(_host(u)) != "x"]
        source = bundle.source
        if own is not None:
            source = source.model_copy(update={"canonical_url": canonical(own)})
        context = bundle.context.model_copy(update={"links": links.fetch_urls(pages, calls)})
        bundle = bundle.model_copy(
            update={"source": source, "context": context, "provider_calls": calls}
        )
        if others and not has_own_media:
            credited = _credit_linked_post(bundle, others[0], opts, calls)
            if credited is not None:
                return credited.model_copy(update={"provider_calls": calls})
        return bundle.model_copy(update={"provider_calls": calls})


PLATFORMS = ("x",)
ADAPTER = XAdapter()
