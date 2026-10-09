"""Live: the real free route on one public, captioned YouTube CLI tutorial (Task M2-B4).

Runs only with SKIPWATCH_LIVE=1 (tests/conftest.py). Uses the G1 URL from
tests/golden/golden.json when that file names one, else the video the YouTube fixtures were
recorded from. Downloads about 30 MB of media into a temp work folder and deletes the folder after.
"""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.models import FramesFile, IngestBundle, ProbeResult, Transcript

pytestmark = pytest.mark.live

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "golden.json"
# GitHub's "Beginner Git commands you need to know", 14:28, manual English captions.
DEFAULT_URL = "https://www.youtube.com/watch?v=rE2zRhZdjFU"
GENERIC_URL = "https://commons.wikimedia.org/wiki/File:Wikipedia_Edit_2014.webm"


def g1_url() -> str:
    try:
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        videos = golden.get("videos", []) if isinstance(golden, dict) else []
        g1 = next((v for v in videos if v.get("id") == "G1"), None)
        return (g1 or {}).get("url") or DEFAULT_URL
    except (OSError, ValueError, AttributeError):
        return DEFAULT_URL


def run(*args: str):
    return CliRunner().invoke(app, list(args))


def test_live_youtube_probe_ingest_transcribe_frames(tmp_path, sw_home):
    url = g1_url()
    work = tmp_path / "w"
    try:
        r = run("probe", url, "--json")
        assert r.exit_code == 0, r.output
        probed = ProbeResult.model_validate_json(r.stdout)
        assert probed.platform == "youtube" and probed.captions_available

        r = run("ingest", url, "--work", str(work), "--provider", "free", "--json")
        assert r.exit_code == 0, r.output
        bundle = IngestBundle.model_validate_json(r.stdout)
        assert bundle.context.captions_kind in {"manual", "auto"}
        assert bundle.media is not None and bundle.media.width and bundle.media.height
        assert 720 <= min(bundle.media.width, bundle.media.height) <= 1080
        assert (work / bundle.media.path).is_file()
        assert [c.op for c in bundle.provider_calls] == [
            "yt-dlp.metadata",
            "yt-dlp.captions",
            "yt-dlp.download",
        ]
        assert bundle.fetched_with_cookies is False

        r = run("transcribe", "--work", str(work), "--backend", "captions", "--json")
        assert r.exit_code == 0, r.output
        transcript = Transcript.model_validate_json(r.stdout)
        assert transcript.origin == "captions" and len(transcript.segments) >= 20

        r = run("frames", "--work", str(work), "--json")
        assert r.exit_code == 0, r.output
        frames = FramesFile.model_validate_json(r.stdout)
        assert len(frames.frames) >= 5
        print(
            f"\nlive: {probed.title!r} {probed.duration_s}s, media "
            f"{bundle.media.width}x{bundle.media.height} {bundle.media.path}, captions "
            f"{bundle.context.captions_kind}/{bundle.context.captions_lang}, "
            f"{len(transcript.segments)} segments, {len(frames.frames)} frames, "
            f"calls {[(c.op, c.ms) for c in bundle.provider_calls]}"
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)  # never keep downloaded media or its frames


def test_live_generic_probe_reads_metadata_only(tmp_path, sw_home):
    r = run("probe", GENERIC_URL, "--json")
    assert r.exit_code == 0, r.output
    probed = ProbeResult.model_validate_json(r.stdout)
    assert probed.platform == "generic" and probed.kind == "video"
    assert probed.captions_available and probed.duration_s and probed.duration_s > 100
