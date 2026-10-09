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
    def build(self, detected: Detected, work: WorkDir, opts: IngestOptions) -> IngestBundle: ...
