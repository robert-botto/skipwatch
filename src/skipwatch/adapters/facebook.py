"""Facebook (watch, reels, page videos and fb.watch links) on the free route (8.3).

Reels resolve through yt-dlp's FacebookReel extractor. Media comes from the free route only:
treg exposes no Facebook media URL (plan decision 4). A login wall exits 4 naming
--cookies-from-browser (R-ING-6).
"""

from skipwatch.adapters.base import IngestOptions
from skipwatch.adapters.ytdlp_common import build_video_bundle
from skipwatch.detect import Detected
from skipwatch.models import IngestBundle
from skipwatch.workdir import WorkDir


class FacebookAdapter:
    def build(self, detected: Detected, work: WorkDir, opts: IngestOptions) -> IngestBundle:
        return build_video_bundle(detected, work, opts, "facebook")


PLATFORMS = ("facebook",)
ADAPTER = FacebookAdapter()
