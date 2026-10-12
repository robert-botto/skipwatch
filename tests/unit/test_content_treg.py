"""treg content provider on the M3 spike's recorded responses (tests/fixtures/recorded/treg).

No treg process ever runs: a fake runner stands in for subprocess.run and serves each recorded
response by endpoint (argv[2]), with the stderr charge line the CLI prints.
"""

import json
import subprocess
from pathlib import Path

import pytest

from skipwatch.providers import content_treg
from skipwatch.providers.content_treg import CATALOG_PRICES, TregClient

REC = Path(__file__).resolve().parents[1] / "fixtures" / "recorded" / "treg"
G2_URL = "https://x.com/i/status/1505892984658743300"
G2_ID = "1505892984658743300"
CALL_ID = "0123456789abcdef0123456789abcdef"
DOT = "·"


def recorded(endpoint: str) -> dict:
    return json.loads((REC / f"{endpoint}.json").read_text(encoding="utf-8"))


def charge_line(endpoint: str, n: int) -> str:
    cost = recorded(endpoint).get("costUsd") or 0.00045
    return f"treg: charged ${cost:g} {DOT} call id {CALL_ID[:-2]}{n:02d}\n"


class FakeRunner:
    """subprocess.run stand-in: `treg call <endpoint>` answers from the recorded fixtures (or
    an override), `treg review` and `treg balance` succeed. Every argv is kept."""

    def __init__(self, overrides: dict | None = None):
        self.argvs: list[list[str]] = []
        self.overrides = overrides or {}

    def __call__(self, argv, **kwargs):
        self.argvs.append(list(argv))
        if argv[1] == "review":
            return subprocess.CompletedProcess(argv, 0, stdout="received\n", stderr="")
        if argv[1] == "balance":
            return subprocess.CompletedProcess(argv, 0, stdout='{"balance_micro": 1}', stderr="")
        endpoint = argv[2]
        n = sum(1 for a in self.argvs if a[1] == "call")
        if endpoint in self.overrides:
            override = self.overrides[endpoint]
            if callable(override):
                return override(argv, n)
            return override
        stdout = json.dumps(recorded(endpoint))
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr=charge_line(endpoint, n))

    def calls(self) -> list[list[str]]:
        return [a for a in self.argvs if a[1] == "call"]

    def reviews(self) -> list[list[str]]:
        return [a for a in self.argvs if a[1] == "review"]


@pytest.fixture
def fake_runner():
    return FakeRunner()


def client(runner, cap: float = 0.05) -> TregClient:
    return TregClient(cap, runner=runner, exe="treg")


# ---- the client: call log, cost, cap, review (Task M4-A1) ----


def test_call_logs_cost_and_call_id_from_stderr(fake_runner):
    c = client(fake_runner)
    data = c.call("anyapi.twitter.thread", body={"url": G2_URL})
    assert data is not None and data["threadLength"] == 3  # output.data, not the envelope
    assert fake_runner.calls()[0] == [
        "treg",
        "call",
        "anyapi.twitter.thread",
        "--method",
        "POST",
        "--data",
        json.dumps({"url": G2_URL}),
    ]
    [call] = c.calls
    assert call.provider == "treg" and call.ok and call.endpoint == "anyapi.twitter.thread"
    assert call.cost_usd == pytest.approx(0.00375)
    assert call.call_id == f"{CALL_ID[:-2]}01"
    assert c.spent == pytest.approx(0.00375)


def test_routed_call_returns_output_and_sends_the_max_cost_header(fake_runner):
    c = client(fake_runner)
    data = c.call(
        "treg.x.post.comments",
        body={"tweet_id": G2_ID},
        headers={"X-Treg-Route-Max-Cost": "0.01"},
    )
    assert data is not None and len(data["comments"]) == 22  # routed: `output` itself
    argv = fake_runner.calls()[0]
    assert argv[argv.index("--header") + 1] == "X-Treg-Route-Max-Cost: 0.01"
    assert c.calls[0].cost_usd == pytest.approx(0.00045)


def test_same_request_twice_is_served_from_the_run_log(fake_runner):
    c = client(fake_runner)
    first = c.call("anyapi.twitter.thread", body={"url": G2_URL})
    second = c.call("anyapi.twitter.thread", body={"url": G2_URL})
    assert first == second
    assert len(fake_runner.calls()) == 1 and len(c.calls) == 1  # billed once


def test_treg_not_found_and_bad_json_fall_through():
    not_found = subprocess.CompletedProcess(
        [], 0, stdout='{"output": {"found": false, "data": null}, "costUsd": 0}', stderr=""
    )
    oops = subprocess.CompletedProcess([], 0, stdout="oops", stderr="")
    failed = subprocess.CompletedProcess(
        [], 1, stdout="", stderr="treg: HTTP 502 bad gateway at https://h/x?token=secret\nmore\n"
    )
    runner = FakeRunner(
        {
            "anyapi.twitter.thread": not_found,
            "anyapi.twitter.tweet_transcript": oops,
            "anyapi.tiktok.video_download": failed,
        }
    )
    c = client(runner)
    assert c.call("anyapi.twitter.thread", body={"url": G2_URL}) is None
    assert c.call("anyapi.twitter.tweet_transcript", body={"url": G2_URL}) is None
    assert c.call("anyapi.tiktok.video_download", body={"url": "https://t/v"}) is None
    assert [call.ok for call in c.calls] == [False, False, False]
    assert c.calls[0].error == "not found"
    assert c.calls[1].error == "not JSON"
    assert c.calls[2].error == "treg: HTTP 502 bad gateway at https://h/x?"  # first line, cut
    assert "secret" not in json.dumps([call.model_dump() for call in c.calls])


def test_timeout_counts_the_estimate_against_the_cap():
    def slow(argv, n):
        raise subprocess.TimeoutExpired(argv, 60)

    c = client(FakeRunner({"anyapi.twitter.thread": slow}))
    assert c.call("anyapi.twitter.thread", body={"url": G2_URL}) is None
    assert c.calls[0].error == "timeout" and not c.calls[0].ok
    assert c.spent == pytest.approx(CATALOG_PRICES["anyapi.twitter.thread"])


def test_treg_cost_cap_stops_calls(fake_runner):
    c = client(fake_runner, cap=0.004)
    assert c.call("anyapi.twitter.thread", body={"url": G2_URL}) is not None  # 0.00375
    refused = c.call(
        "treg.x.post.comments", body={"tweet_id": G2_ID}, headers={"X-Treg-Route-Max-Cost": "0.01"}
    )
    assert refused is None
    assert [a[2] for a in fake_runner.calls()] == ["anyapi.twitter.thread"]  # never ran
    assert c.calls[-1].error == "cost cap" and not c.calls[-1].ok
    assert sum(call.cost_usd for call in c.calls) <= 0.004
    assert c.capped


def test_unknown_endpoint_is_never_called(fake_runner):
    with pytest.raises(ValueError, match="no catalog price"):
        client(fake_runner).call("anyapi.anything.else", body={})
    assert fake_runner.calls() == []


def test_r_ing_3_every_used_call_is_reviewed(fake_runner):
    c = client(fake_runner)
    c.call("anyapi.twitter.thread", body={"url": G2_URL})
    c.call("anyapi.twitter.tweet_transcript", body={"url": G2_URL})
    c.use("anyapi.twitter.thread")
    c.review_all()
    reviews = fake_runner.reviews()
    assert [r[2] for r in reviews] == [call.call_id for call in c.calls]  # one per logged id
    assert [r[3] for r in reviews] == ["useful", "not_sure"]  # unused gets not_sure
    for argv in reviews:
        reason = argv[argv.index("--reason") + 1]
        assert 0 < len(reason) < 200
    assert [call.review for call in c.calls] == ["useful", "not_sure"]
    c.review_all()  # a second pass reviews nothing again
    assert len(fake_runner.reviews()) == 2


def test_review_is_skipped_without_call_id_and_failure_leaves_review_unset():
    no_id = subprocess.CompletedProcess([], 0, stdout=json.dumps(recorded("anyapi.twitter.thread")))
    runner = FakeRunner({"anyapi.twitter.thread": no_id})
    c = client(runner)
    c.call("anyapi.twitter.thread", body={"url": G2_URL})
    c.review_all()
    assert runner.reviews() == []
    assert c.calls[0].review is None


def test_failed_call_with_an_id_is_reviewed_not_useful():
    stdout = '{"output": {"found": false, "data": null}}'
    stderr = f"treg: charged $0 {DOT} call id {CALL_ID}\n"
    runner = FakeRunner(
        {"anyapi.twitter.thread": subprocess.CompletedProcess([], 0, stdout, stderr)}
    )
    c = client(runner)
    c.call("anyapi.twitter.thread", body={"url": G2_URL})
    c.review_all()
    assert runner.reviews()[0][2:4] == [CALL_ID, "not_useful"]


def test_no_personal_data_in_argv(fake_runner):
    c = client(fake_runner)
    c.call("anyapi.twitter.thread", body={"url": G2_URL})
    c.call(
        "treg.x.post.comments", body={"tweet_id": G2_ID}, headers={"X-Treg-Route-Max-Cost": "0.01"}
    )
    c.use("anyapi.twitter.thread")
    c.review_all()
    allowed = {
        "treg",
        "call",
        "review",
        "--method",
        "POST",
        "--data",
        "--header",
        "--reason",
        "X-Treg-Route-Max-Cost: 0.01",
        "useful",
        "not_sure",
        json.dumps({"url": G2_URL}),
        json.dumps({"tweet_id": G2_ID}),
        *CATALOG_PRICES,
        *(call.call_id for call in c.calls),
        *content_treg.REVIEW_REASONS.values(),
    }
    for argv in fake_runner.argvs:
        assert set(argv) <= allowed, argv


# ---- login and availability ----


def test_logged_in_false_without_binary(monkeypatch, fake_runner):
    monkeypatch.setattr(content_treg, "_treg_path", lambda: None)
    assert content_treg.logged_in(fake_runner) is False
    assert content_treg.TregProvider(runner=fake_runner).available() is False
    assert fake_runner.argvs == []


def test_logged_in_runs_the_free_balance_command(monkeypatch, fake_runner):
    monkeypatch.setattr(content_treg, "_treg_path", lambda: "/bin/treg")
    assert content_treg.logged_in(fake_runner) is True
    assert fake_runner.argvs == [["/bin/treg", "balance", "--json", "--limit", "1"]]


@pytest.mark.parametrize(
    "result",
    [
        subprocess.CompletedProcess([], 1, stdout="", stderr="not logged in"),
        subprocess.CompletedProcess([], 0, stdout="Balance: $3", stderr=""),
        OSError("gone"),
        subprocess.TimeoutExpired([], 10),
    ],
)
def test_logged_in_false_on_any_failure(monkeypatch, result):
    monkeypatch.setattr(content_treg, "_treg_path", lambda: "/bin/treg")

    def runner(argv, **kwargs):
        if isinstance(result, BaseException):
            raise result
        return result

    assert content_treg.logged_in(runner) is False


def test_provider_is_registered_under_its_name():
    from skipwatch.providers.registry import content_providers

    assert [p.name for p in content_providers()] == ["treg"]
    assert content_treg.PROVIDER.name == "treg"


def test_unit_tests_never_reach_a_real_treg():
    """tests/conftest.py hides the treg binary from every non-live test."""
    assert content_treg._treg_path() is None
    assert content_treg.PROVIDER.available() is False
