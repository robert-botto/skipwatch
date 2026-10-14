from pathlib import Path

import pytest
import requests
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import Config, Manifest
from skipwatch.providers import export_mem0
from skipwatch.workdir import read_model
from tests.unit._skills import installed_skill

KEY = "m0-test-key-do-not-echo-1234567890"
URL = "https://api.mem0.ai/v3/memories/add/"


class FakeResponse:
    def __init__(self, status: int, body: object = None):
        self.status_code = status
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no JSON")
        return self._body


class FakePost:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def fake_post(monkeypatch, *outcomes) -> FakePost:
    fake = FakePost(*outcomes)
    monkeypatch.setattr(export_mem0.requests, "post", fake)
    return fake


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


@pytest.fixture
def skill(home) -> Path:
    return installed_skill(home / ".claude")


def manifest(skill: Path) -> Manifest:
    return read_model(skill / "skipwatch.json", Manifest)


def cfg(user_id: str = "", enabled: bool = True) -> Config:
    return Config.model_validate({"exports": {"mem0": {"enabled": enabled, "user_id": user_id}}})


def accepted() -> FakeResponse:
    return FakeResponse(200, {"event_id": "ev-123", "status": "PENDING"})


def test_mem0_body_is_a_pointer_not_the_procedure(skill, home, monkeypatch):
    monkeypatch.setenv("MEM0_API_KEY", KEY)
    fake = fake_post(monkeypatch, accepted(), accepted())

    item = export_mem0.PROVIDER.export(skill, manifest(skill), cfg())
    assert item.provider == "mem0" and item.ok and item.location == "mem0 event ev-123"

    call = fake.calls[0]
    assert call["url"] == URL
    assert call["headers"] == {"Authorization": f"Token {KEY}", "Accept": "application/json"}
    assert call["timeout"] == 20
    body = call["json"]
    content = body["messages"][0]["content"]
    assert body["messages"] == [{"role": "user", "content": content}]
    assert content == (
        "SkipWatch skill run-x installed 2026-10-09 at ~/.claude/skills/run-x."
        " Purpose: Runs x. Use when you want x run."
        ' Source: "Run x" by someone (https://youtu.be/x).'
    )
    # never the procedure: no step text, no quoted evidence, no transcript
    for text in ("Initialise the project", "initialise the project", "(00:05)", "then build"):
        assert text not in content
    assert str(home) not in str(body)
    assert body["metadata"] == {
        "project": "skipwatch",
        "skill": "run-x",
        "source_url": "https://youtu.be/x",
    }
    assert body["infer"] is False
    assert body["agent_id"] == "skipwatch" and "user_id" not in body

    export_mem0.PROVIDER.export(skill, manifest(skill), cfg(user_id="someone-id"))
    body = fake.calls[1]["json"]
    assert body["user_id"] == "someone-id" and "agent_id" not in body


def test_mem0_prefers_canonical_url_and_uses_install_date(skill, monkeypatch, sw_home):
    from datetime import UTC, datetime

    from skipwatch import installs
    from skipwatch.models import InstallResult

    monkeypatch.setenv("MEM0_API_KEY", KEY)
    installs.record(
        InstallResult(name="run-x", path=str(skill), scope="user"),
        "run",
        now=datetime(2026, 10, 12, 9, 30, tzinfo=UTC),
    )
    m = manifest(skill)
    m = m.model_copy(
        update={
            "source": m.source.model_copy(
                update={"canonical_url": "https://youtube.com/c", "posted_at": "2026-09-01"}
            )
        }
    )
    fake = fake_post(monkeypatch, accepted())
    export_mem0.PROVIDER.export(skill, m, cfg())
    body = fake.calls[0]["json"]
    assert body["metadata"]["source_url"] == "https://youtube.com/c"
    content = body["messages"][0]["content"]
    assert "installed 2026-10-12 at" in content
    assert content.endswith(
        'Source: "Run x" by someone (https://youtube.com/c), posted 2026-09-01.'
    )


def test_mem0_enabled_follows_config():
    assert export_mem0.PROVIDER.name == "mem0"
    assert export_mem0.PROVIDER.enabled(cfg(enabled=True)) is True
    assert export_mem0.PROVIDER.enabled(Config()) is False


@pytest.mark.parametrize(
    ("outcome", "code", "detail"),
    [
        (FakeResponse(401), ExitCode.MISSING_DEPENDENCY, "Mem0 rejected the key in MEM0_API_KEY"),
        (FakeResponse(403), ExitCode.MISSING_DEPENDENCY, "Mem0 rejected the key in MEM0_API_KEY"),
        (FakeResponse(500), ExitCode.DOWNLOAD_FAILED, "Mem0 export failed: HTTP 500"),
        (
            requests.Timeout(f"read timed out, Authorization: Token {KEY}"),
            ExitCode.DOWNLOAD_FAILED,
            "Mem0 export failed: Timeout",
        ),
        (
            requests.ConnectionError(f"refused, Token {KEY}"),
            ExitCode.DOWNLOAD_FAILED,
            "Mem0 export failed: ConnectionError",
        ),
    ],
)
def test_mem0_http_errors_never_echo_the_key(skill, monkeypatch, capsys, outcome, code, detail):
    monkeypatch.setenv("MEM0_API_KEY", KEY)
    fake_post(monkeypatch, outcome)
    with pytest.raises(SkipwatchError) as e:
        export_mem0.PROVIDER.export(skill, manifest(skill), cfg())
    assert e.value.code == code and e.value.message == detail
    assert KEY not in e.value.message and KEY not in str(e.value)
    # no chained exception whose text could hold the key
    assert e.value.__cause__ is None
    assert e.value.__context__ is None or e.value.__suppress_context__
    out = capsys.readouterr()
    assert KEY not in out.out and KEY not in out.err


def test_mem0_cli_exit_codes_never_echo_the_key(skill, monkeypatch, sw_home):
    monkeypatch.setenv("MEM0_API_KEY", KEY)
    for outcome, code in ((FakeResponse(401), 8), (FakeResponse(500), 3)):
        fake_post(monkeypatch, outcome)
        r = CliRunner().invoke(app, ["export", str(skill), "--provider", "mem0"])
        assert r.exit_code == code, r.stderr
        assert KEY not in r.stdout and KEY not in r.stderr
    fake_post(monkeypatch, requests.Timeout(KEY))
    r = CliRunner().invoke(app, ["export", str(skill), "--provider", "mem0"])
    assert r.exit_code == 3 and KEY not in r.stderr


def test_mem0_missing_key_is_exit_8(skill, monkeypatch, sw_home):
    monkeypatch.delenv("MEM0_API_KEY", raising=False)
    fake = fake_post(monkeypatch)
    with pytest.raises(SkipwatchError) as e:
        export_mem0.PROVIDER.export(skill, manifest(skill), cfg())
    assert e.value.code == ExitCode.MISSING_DEPENDENCY
    assert e.value.message == "set MEM0_API_KEY to export to Mem0"
    monkeypatch.setenv("MEM0_API_KEY", "  ")
    with pytest.raises(SkipwatchError) as e:
        export_mem0.PROVIDER.export(skill, manifest(skill), cfg())
    assert e.value.code == ExitCode.MISSING_DEPENDENCY
    assert fake.calls == []
    monkeypatch.delenv("MEM0_API_KEY")
    r = CliRunner().invoke(app, ["export", str(skill), "--provider", "mem0"])
    assert r.exit_code == 8 and "set MEM0_API_KEY to export to Mem0" in r.stderr
