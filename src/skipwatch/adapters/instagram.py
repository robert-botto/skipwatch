"""Instagram (reels, posts and IGTV under instagram.com and instagr.am) on the free route (8.3).

Post text is the caption in `description`, never treg (plan decision 3). Logged out,
`duration` is null and older posts hit a login wall, which exits 4 naming
--cookies-from-browser (R-ING-6).
"""

from skipwatch.adapters.base import IngestOptions
from skipwatch.adapters.ytdlp_common import build_video_bundle
from skipwatch.detect import Detected
from skipwatch.models import IngestBundle
from skipwatch.workdir import WorkDir


class InstagramAdapter:
    def build(self, detected: Detected, work: WorkDir, opts: IngestOptions) -> IngestBundle:
        return build_video_bundle(detected, work, opts, "instagram")


PLATFORMS = ("instagram",)
ADAPTER = InstagramAdapter()
