"""An uncaught exception exits 70 (INTERNAL_ERROR) with one redacted line, never a traceback."""

import sys

import pytest
import typer

from skipwatch import cli
from skipwatch.errors import ExitCode
from skipwatch.output import progress
from tests.unit.test_stagelog import _fake_app, _run, logs  # noqa: F401 (fixture)

FAKE_KEY = "sk-proj-" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0"


def _crashing_app(message: str = "engine bug") -> typer.Typer:
    app = _fake_app()

    @app.command("crash")
    def _crash():
        progress("about to crash")
        raise RuntimeError(message)

    @app.command("abort")
    def _abort():
        raise typer.Abort()

    return app


@pytest.fixture(autouse=True)
def _no_debug(monkeypatch):
    monkeypatch.delenv("SKIPWATCH_DEBUG", raising=False)


def test_uncaught_exception_exits_70_with_one_line(monkeypatch, capsys):
    assert _run(monkeypatch, ["crash"], _crashing_app()) == ExitCode.INTERNAL_ERROR
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert err.splitlines() == [
        "about to crash",
        "skipwatch: internal error: RuntimeError: engine bug",
    ]


def test_debug_env_prints_the_traceback_before_the_line(monkeypatch, capsys):
    monkeypatch.setenv("SKIPWATCH_DEBUG", "1")
    assert _run(monkeypatch, ["crash"], _crashing_app()) == ExitCode.INTERNAL_ERROR
    err = capsys.readouterr().err
    assert "Traceback (most recent call last)" in err and "raise RuntimeError(message)" in err
    assert err.splitlines()[-1] == "skipwatch: internal error: RuntimeError: engine bug"


def test_log_gets_the_traceback_and_stderr_points_to_it(monkeypatch, capsys, logs):  # noqa: F811
    log = logs / "crash.log"
    code = _run(monkeypatch, ["--log", str(log), "crash"], _crashing_app())
    assert code == ExitCode.INTERNAL_ERROR
    text = log.read_text(encoding="utf-8")
    assert "about to crash" in text and "Traceback (most recent call last)" in text
    assert text.splitlines()[-1] == "skipwatch: internal error: RuntimeError: engine bug"
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert err.splitlines()[0] == "rc=70 elapsed=0s"
    assert err.splitlines()[-1] == (
        f"skipwatch: internal error: RuntimeError: engine bug (traceback in {log})"
    )


def test_message_never_echoes_secrets(monkeypatch, capsys, logs):  # noqa: F811
    monkeypatch.setenv("SKIPWATCH_DEBUG", "1")
    monkeypatch.setenv("MEM0_API_KEY", "m0-plainvalue-without-pattern-123")
    message = f"bad key {FAKE_KEY} and m0-plainvalue-without-pattern-123"
    log = logs / "secret.log"
    _run(monkeypatch, ["--log", str(log), "crash"], _crashing_app(message))
    _run(monkeypatch, ["crash"], _crashing_app(message))
    seen = capsys.readouterr().err + log.read_text(encoding="utf-8")
    assert "internal error: RuntimeError: bad key" in seen
    assert FAKE_KEY not in seen and "m0-plainvalue-without-pattern-123" not in seen


def test_multiline_message_stays_one_line(monkeypatch, capsys):
    _run(monkeypatch, ["crash"], _crashing_app("first\nsecond"))
    last = capsys.readouterr().err.splitlines()[-1]
    assert last == "skipwatch: internal error: RuntimeError: first"


def test_abort_still_exits_1(monkeypatch, capsys):
    assert _run(monkeypatch, ["abort"], _crashing_app()) == 1
    assert "Aborted!" in capsys.readouterr().err


def test_ctrl_c_still_reraises(monkeypatch):
    # click turns Ctrl-C inside a command into Abort (exit 1); one that reaches main re-raises
    def interrupted() -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_dispatch", interrupted)
    monkeypatch.setattr(sys, "argv", ["skipwatch", "ok"])
    with pytest.raises(KeyboardInterrupt):
        cli.main()
