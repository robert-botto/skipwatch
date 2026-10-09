"""TikTok (tiktok.com, vm.tiktok.com and vt.tiktok.com share links) on the free route (8.3).

Share links resolve through yt-dlp's TikTokVM extractor; the canonical URL is the resolved
`webpage_url`. The caption (`description`) is the post text. 720p and 1080p are h265 only,
which ffmpeg decodes, so the format rule needs nothing special (plan decision 6).
"""

from skipwatch.adapters.base import IngestOptions
from skipwatch.adapters.ytdlp_common import build_video_bundle
from skipwatch.detect import Detected
from skipwatch.models import IngestBundle
from skipwatch.providers import links
from skipwatch.workdir import WorkDir


class TiktokAdapter:
    def build(self, detected: Detected, work: WorkDir, opts: IngestOptions) -> IngestBundle:
        return links.with_post_links(build_video_bundle(detected, work, opts, "tiktok"))


PLATFORMS = ("tiktok",)
ADAPTER = TiktokAdapter()
