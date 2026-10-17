"""The adapter seam: every source becomes the same IngestBundle (8.3)."""

from dataclasses import dataclass
from typing import Protocol

from skipwatch.detect import Detected
from skipwatch.models import IngestBundle
from skipwatch.workdir import WorkDir


@dataclass(frozen=True)
class IngestOptions:
    provider: str = "auto"
    max_height: int = 1080
    cookies_from_browser: str | None = None


class Adapter(Protocol):
    """Adapters register by defining PLATFORMS and ADAPTER at module level (adapters/registry).

    A login or private-content error raises SkipwatchError(PRIVATE_CONTENT) directly (R-ING-6).
    """

    def build(self, detected: Detected, work: WorkDir, opts: IngestOptions) -> IngestBundle: ...


class NoMediaError(Exception):
    """The URL resolved but has no video or audio. ingest may retry it as a text source."""

    def __init__(self, url: str, reason: str):
        super().__init__(f"{url}: {reason}")
        self.url = url
        self.reason = reason


class DownloadFailed(Exception):
    """Every free route failed for media. attempts are 'route.op: reason' strings.

    bundle carries whatever metadata the adapter did get, so a provider's fetch_media can work
    from it; without it ingest builds a minimal one from the detected input.
    """

    def __init__(self, attempts: list[str], bundle: IngestBundle | None = None):
        super().__init__("; ".join(attempts))
        self.attempts = attempts
        self.bundle = bundle
