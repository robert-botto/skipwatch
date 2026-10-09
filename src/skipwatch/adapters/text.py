"""Text sources (8.2, 8.3): a URL that resolved but has no video or audio.

ingest calls this adapter when another one raises NoMediaError. An X post needs a content
provider that can read post text (treg, M4, through `build_text_x`); on the free route it
exits 7 (plan issue 8). Any other page is fetched once as text (R-ING-1) and becomes a `text`
bundle when it holds at least 200 words, else exit 7.
"""

from skipwatch import ingest
from skipwatch.adapters.base import IngestOptions
from skipwatch.config import load_config
from skipwatch.detect import Detected
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import IngestBundle, IngestContext, ProviderCall, Route, SourceInfo
from skipwatch.providers import links
from skipwatch.workdir import WorkDir

MIN_WORDS = 200
NO_X_TEXT = "This post has no video. Enable treg (Tier 3) to read text posts."


def _x_text(detected: Detected, work: WorkDir, opts: IngestOptions) -> IngestBundle:
    for provider in ingest.enabled_providers(opts, load_config()):
        build_text_x = getattr(provider, "build_text_x", None)
        if build_text_x is None:
            continue
        bundle = build_text_x(detected, work, opts)
        if bundle is not None:
            return bundle
    raise SkipwatchError(ExitCode.NO_CONTENT, NO_X_TEXT)


class TextAdapter:
    def build(self, detected: Detected, work: WorkDir, opts: IngestOptions) -> IngestBundle:
        if detected.platform == "x":
            return _x_text(detected, work, opts)
        url = detected.value
        calls: list[ProviderCall] = []
        budget = links.Budget()  # the page and its links share one post budget
        page = links.fetch_link(url, calls, budget)
        if page is None or len(page.text.split()) < MIN_WORDS:
            raise SkipwatchError(
                ExitCode.NO_CONTENT, f"no video and under {MIN_WORDS} words of text at {url}"
            )
        return IngestBundle(
            source=SourceInfo(kind="text", platform=detected.platform, url=url, title=page.title),
            context=IngestContext(
                post_text=page.text, links=links.fetch_all(page.text, calls, budget)
            ),
            media=None,
            provider_calls=calls,
            route=Route(context="free", media=None),
        )


PLATFORMS = ("text",)
ADAPTER = TextAdapter()
