"""TikTok, Instagram and Facebook adapters on the free route (Task M3-C1)."""

import pytest

from skipwatch.detect import detect


@pytest.mark.parametrize(
    ("url", "platform"),
    [
        ("https://www.instagram.com/reel/Dd-rJlkE_Z5/", "instagram"),
        ("https://www.instagram.com/p/Dd-rJlkE_Z5/", "instagram"),
        ("https://www.instagram.com/tv/Dd-rJlkE_Z5/", "instagram"),
        ("https://www.tiktok.com/@github/video/7624273546776153377", "tiktok"),
        ("https://vm.tiktok.com/ZMabc123/", "tiktok"),
        ("https://vt.tiktok.com/ZSabc123/", "tiktok"),
        ("https://www.facebook.com/watch/?v=10154383743583686", "facebook"),
        ("https://www.facebook.com/reel/1234567890", "facebook"),
        ("https://www.facebook.com/gov.sg/videos/10154383743583686/", "facebook"),
        ("https://fb.watch/abcDEF123/", "facebook"),
        ("https://m.facebook.com/watch/?v=1", "facebook"),
    ],
)
def test_detect_maps_social_url_shapes(url, platform):
    assert detect(url).platform == platform
