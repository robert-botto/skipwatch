"""Live: X on the free route, no cookies (Task M3-B2).

Runs only with SKIPWATCH_LIVE=1 (tests/conftest.py). G2 from tests/golden/golden.json (a public
video post with no captions, so transcription needs Whisper), and the G2 author's public reply
that links an earlier video post (plan decision 2). Downloads a few MB of media into temp work
folders and deletes them after.
"""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.models import FramesFile, IngestBundle, ProbeResult, Transcript
from skipwatch.providers.registry import transcription_backends

pytestmark = pytest.mark.live

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "golden.json"
DEFAULT_G2 = "https://x.com/mattpocockuk/status/1505892984658743300"
LINKING_REPLY = "https://x.com/mattpocockuk/status/1505898799335628805"
TEXT_ONLY_REPLY = "https://x.com/mattpocockuk/status/1506032263359864843"


def g2_url() -> str:
    try:
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        g2 = next((v for v in golden.get("videos", []) if v.get("id") == "G2"), None)
        return (g2 or {}).get("url") or DEFAULT_G2
    except (OSError, ValueError, AttributeError):
        return DEFAULT_G2


def run(*args: str):
    return CliRunner().invoke(app, list(args))


def whisper_backend() -> str | None:
    """A local Whisper backend importable here, or None (then transcription is skipped)."""
    for name in ("mlx", "faster"):
        backend = transcription_backends().get(name)
        if backend is None:
            continue
        try:
            __import__({"mlx": "mlx_whisper", "faster": "faster_whisper"}[name])
        except ImportError:
            continue
        return name
    return None


def test_live_x_g2_ingest_transcribe_frames(tmp_path, sw_home):
    url = g2_url()
    work = tmp_path / "g2"
    try:
        r = run("probe", url, "--json")
        assert r.exit_code == 0, r.output
        probed = ProbeResult.model_validate_json(r.stdout)
        assert probed.platform == "x" and probed.duration_s and probed.duration_s > 100

        r = run("ingest", url, "--work", str(work), "--provider", "free", "--json")
        assert r.exit_code == 0, r.output
        bundle = IngestBundle.model_validate_json(r.stdout)
        assert bundle.source.platform == "x" and bundle.source.kind == "video"
        assert bundle.media is not None and bundle.media.has_audio
        post = url.rstrip("/").rsplit("/", 1)[-1]
        assert bundle.source.canonical_url == f"https://x.com/i/status/{post}"
        assert (bundle.source.author or "").startswith("@")
        assert bundle.context.post_text and "TypeScript" in bundle.context.post_text
        assert not bundle.context.captions_available  # X has no captions: Whisper or nothing
        assert bundle.media is not None and bundle.media.width and bundle.media.height
        assert min(bundle.media.width, bundle.media.height) <= 1080
        assert (work / bundle.media.path).is_file()
        assert bundle.route.fallbacks == [] and bundle.fetched_with_cookies is False
        ops = [c.op for c in bundle.provider_calls]
        assert ops[0] == "yt-dlp.metadata" and "yt-dlp.download" in ops
        assert "link.resolve" in ops  # the post's own t.co media link

        backend = whisper_backend()
        segments = None
        if backend is not None:
            r = run("transcribe", "--work", str(work), "--backend", backend, "--json")
            assert r.exit_code == 0, r.output
            transcript = Transcript.model_validate_json(r.stdout)
            assert transcript.origin != "captions" and len(transcript.segments) >= 5
            segments = len(transcript.segments)

        r = run("frames", "--work", str(work), "--json")
        assert r.exit_code == 0, r.output
        frames = FramesFile.model_validate_json(r.stdout)
        assert len(frames.frames) >= 3
        print(
            f"\nlive G2: {bundle.source.author} {bundle.source.duration_s}s, media "
            f"{bundle.media.width}x{bundle.media.height} audio {bundle.media.has_audio}, "
            f"backend {backend}, "
            f"{segments} segments, {len(frames.frames)} frames, "
            f"calls {[(c.op, c.ok, c.ms) for c in bundle.provider_calls]}"
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)  # never keep downloaded media or its frames


def test_live_x_reply_linking_a_video_credits_the_linked_post(tmp_path, sw_home):
    work = tmp_path / "linked"
    try:
        r = run("ingest", LINKING_REPLY, "--work", str(work), "--provider", "free", "--json")
        assert r.exit_code == 0, r.output
        bundle = IngestBundle.model_validate_json(r.stdout)
        reply_id = LINKING_REPLY.rsplit("/", 1)[-1]
        assert bundle.source.canonical_url != f"https://x.com/i/status/{reply_id}"
        assert bundle.notes == [f"video came from a linked post: {bundle.source.canonical_url}"]
        assert bundle.route.fallbacks == []
        assert bundle.context.thread and reply_id in bundle.context.thread[0]
        assert bundle.context.links[0].url == bundle.source.canonical_url
        assert bundle.media is not None and bundle.media.has_audio
        print(f"\nlive linked: {bundle.source.canonical_url} {bundle.source.author}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_live_x_text_only_post_is_exit_7_on_the_free_route(tmp_path, sw_home):
    work = tmp_path / "text"
    try:
        r = run("ingest", TEXT_ONLY_REPLY, "--work", str(work), "--provider", "free")
        assert r.exit_code == 7, r.output
        assert "SkipWatch 0.1.0 reads videos only." in r.output  # R-SCOPE-1
    finally:
        shutil.rmtree(work, ignore_errors=True)
