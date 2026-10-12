"""Live: the treg provider on G2 and doctor's login check (Task M4-A3). PAID.

Runs only with SKIPWATCH_LIVE=1 (tests/conftest.py) and treg on PATH and logged in. The G2
ingest makes three treg calls (thread, comments, transcript; about $0.006 at the M3 spike's
prices) under a per-run cap of $0.03 set in an isolated config. The media download is the free
route's. Nothing about the operator is sent: treg only sees the public post URL and id.
"""

import json

import pytest
from typer.testing import CliRunner

from skipwatch import doctor
from skipwatch.cli import app
from skipwatch.models import IngestBundle
from skipwatch.providers import content_treg
from tests.live.test_live_x import g2_url

pytestmark = pytest.mark.live

LIVE_CAP_USD = 0.03


@pytest.fixture
def treg_logged_in():
    if not content_treg.logged_in():
        pytest.skip("treg is not on PATH or not logged in")


def test_live_doctor_sees_treg_logged_in(treg_logged_in):
    probe = doctor.probe_machine()
    assert probe.treg_on_path and probe.treg_logged_in is True
    if probe.whisper_mlx or probe.whisper_faster:
        assert doctor.compute_tier(probe) == "3"


def test_live_treg_g2_thread_replies_and_reviews(treg_logged_in, tmp_path, sw_home):
    sw_home.mkdir(parents=True, exist_ok=True)
    (sw_home / "config.toml").write_text(
        f"[providers.treg]\nenabled = true\nmax_cost_usd = {LIVE_CAP_USD}\n", encoding="utf-8"
    )
    work = tmp_path / "g2"
    r = CliRunner().invoke(
        app, ["ingest", g2_url(), "--work", str(work), "--provider", "treg", "--json"]
    )
    assert r.exit_code == 0, r.output
    bundle = IngestBundle.model_validate_json((work / "ingest.json").read_text(encoding="utf-8"))
    calls = [c for c in bundle.provider_calls if c.provider == "treg"]
    print(json.dumps([c.model_dump(exclude={"call_id"}) for c in calls], indent=1))
    assert sum(c.cost_usd for c in calls) <= LIVE_CAP_USD
    assert len(bundle.context.thread) >= 2
    assert bundle.transcript_hint.origin == "treg:anyapi.twitter.tweet_transcript"
    assert all(c.review is not None for c in calls if c.call_id), "R-ING-3: every call reviewed"
    calls_file = json.loads((work / "calls.json").read_text(encoding="utf-8"))
    assert len([c for c in calls_file["calls"] if c["provider"] == "treg"]) == len(calls)
