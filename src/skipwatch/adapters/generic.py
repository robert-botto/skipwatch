"""Any other URL yt-dlp supports (8.3). A page yt-dlp does not support, or one with no video
or audio, raises NoMediaError so ingest can hand it to the text adapter (M3)."""

from skipwatch.adapters.base import IngestOptions
from skipwatch.adapters.ytdlp_common import build_video_bundle
from skipwatch.detect import Detected
from skipwatch.models import IngestBundle
from skipwatch.workdir import WorkDir


class GenericAdapter:
    def build(self, detected: Detected, work: WorkDir, opts: IngestOptions) -> IngestBundle:
        return build_video_bundle(detected, work, opts, "generic")


PLATFORMS = ("generic",)
ADAPTER = GenericAdapter()
