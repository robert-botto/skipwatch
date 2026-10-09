"""Live: the real free route on TikTok (G3), Instagram (G4) and Facebook (Task M3-C1).

Runs only with SKIPWATCH_LIVE=1 (tests/conftest.py). Each case probes, ingests without
cookies and extracts frames, then deletes the work folder so no media is kept. Instagram may
demand a login logged out; then ingest must exit 4 naming --cookies-from-browser.
"""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.errors import ExitCode
from skipwatch.models import FramesFile, IngestBundle, ProbeResult

pytestmark = pytest.mark.live

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "golden.json"
# Fallbacks: the URLs the M3 spike recorded its fixtures from.
DEFAULTS = {
    "G3": "https://www.tiktok.com/@github/video/7624273546776153377",
    "G4": "https://www.instagram.com/reel/Dd-rJlkE_Z5/",
}
# gov.sg, "What to do during the haze?" (65 s), the spike's public Facebook post.
FACEBOOK_URL = "https://www.facebook.com/gov.sg/videos/10154383743583686/"


def golden_url(slot: str) -> str:
    try:
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        videos = golden.get("videos", []) if isinstance(golden, dict) else []
        row = next((v for v in videos if v.get("id") == slot), None)
        return (row or {}).get("url") or DEFAULTS[slot]
    except (OSError, ValueError, AttributeError):
        return DEFAULTS[slot]


def run(*args: str):
    return CliRunner().invoke(app, list(args))


CASES = [
    pytest.param("tiktok", lambda: golden_url("G3"), id="G3-tiktok"),
    pytest.param("instagram", lambda: golden_url("G4"), id="G4-instagram"),
    pytest.param("facebook", lambda: FACEBOOK_URL, id="facebook"),
]


@pytest.mark.parametrize(("platform", "url_of"), CASES)
def test_live_social_probe_ingest_frames(tmp_path, sw_home, platform, url_of):
    url = url_of()
    work = tmp_path / "w"
    try:
        r = run("probe", url, "--json")
        if platform == "instagram" and r.exit_code == ExitCode.PRIVATE_CONTENT:
            assert "--cookies-from-browser" in r.output
            print(f"\nlive instagram: login wall, exit 4 names the cookie flag: {r.output!r}")
            return
        assert r.exit_code == 0, r.output
        probed = ProbeResult.model_validate_json(r.stdout)
        assert probed.platform == platform and probed.kind == "video"

        r = run("ingest", url, "--work", str(work), "--provider", "free", "--json")
        if platform == "instagram" and r.exit_code == ExitCode.PRIVATE_CONTENT:
            assert "--cookies-from-browser" in r.output
            print(f"\nlive instagram: login wall, exit 4 names the cookie flag: {r.output!r}")
            return
        assert r.exit_code == 0, r.output
        bundle = IngestBundle.model_validate_json(r.stdout)
        assert bundle.source.platform == platform and bundle.source.kind == "video"
        assert bundle.source.author and bundle.context.post_text
        assert bundle.media is not None and bundle.media.width and bundle.media.height
        assert bundle.media.has_audio  # transcribe exits 7 on a silent download
        assert 720 <= min(bundle.media.width, bundle.media.height) <= 1080
        assert (work / bundle.media.path).is_file()
        assert bundle.fetched_with_cookies is False

        r = run("frames", "--work", str(work), "--json")
        assert r.exit_code == 0, r.output
        frames = FramesFile.model_validate_json(r.stdout)
        assert len(frames.frames) >= 1
        print(
            f"\nlive {platform}: {probed.title!r} probe duration {probed.duration_s}, author "
            f"{bundle.source.author}, media {bundle.media.width}x{bundle.media.height} "
            f"{bundle.media.path}, {len(frames.frames)} frames, "
            f"calls {[(c.op, c.ms) for c in bundle.provider_calls]}"
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)  # never keep downloaded media or its frames
