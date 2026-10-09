"""Live tests run only with SKIPWATCH_LIVE=1, whatever -m expression is given."""

from pathlib import Path

import pytest

CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"
DUMMY = """
import socket

import pytest


@pytest.mark.live
def test_reaches_the_network():
    assert socket.socket.connect.__name__ != "guard"  # live tests may open sockets


def test_offline():
    pass
"""


@pytest.fixture
def suite(pytester):
    pytester.makeconftest(CONFTEST.read_text(encoding="utf-8"))
    pytester.makeini("[pytest]\nmarkers =\n    live: real network\n    pipeline: ffmpeg\n")
    pytester.makepyfile(test_dummy=DUMMY)
    return pytester


@pytest.mark.parametrize("args", [(), ("-m", "not pipeline"), ("-m", "live")])
def test_live_skipped_without_opt_in(suite, monkeypatch, args):
    monkeypatch.delenv("SKIPWATCH_LIVE", raising=False)
    result = suite.runpytest("-rs", *args)
    outcomes = result.parseoutcomes()
    assert outcomes.get("skipped") == 1 and "failed" not in outcomes
    assert "SKIPWATCH_LIVE=1" in result.stdout.str()


def test_live_runs_with_opt_in(suite, monkeypatch):
    monkeypatch.setenv("SKIPWATCH_LIVE", "1")
    result = suite.runpytest_subprocess("-m", "live")  # outside this test's socket guard
    result.assert_outcomes(passed=1, deselected=1)
