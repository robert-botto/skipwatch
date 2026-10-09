"""YouTube (youtube.com, youtu.be, youtube-nocookie.com) on the free route (8.3)."""

from skipwatch.adapters.base import IngestOptions
from skipwatch.adapters.ytdlp_common import build_video_bundle
from skipwatch.detect import Detected
from skipwatch.models import IngestBundle
from skipwatch.workdir import WorkDir


class YoutubeAdapter:
    def build(self, detected: Detected, work: WorkDir, opts: IngestOptions) -> IngestBundle:
        return build_video_bundle(detected, work, opts, "youtube")


PLATFORMS = ("youtube",)
ADAPTER = YoutubeAdapter()
