import json
import sys

import pytest
from typer.testing import CliRunner

from skipwatch import cli
from skipwatch.cli import app
from skipwatch.errors import ExitCode
from skipwatch.workdir import WorkDir


def work(tmp_path):
    w = WorkDir(tmp_path / "w")
    w.ensure()
    return w


def mark(w, stage, status):
    return CliRunner().invoke(
        app, ["mark", "--work", str(w.path), "--stage", stage, "--status", status]
    )


def state(w, stage):
    return json.loads((w.path / "stages.json").read_text())["stages"][stage]


def test_mark_records_running_then_done_with_timings(tmp_path):
    w = work(tmp_path)
    assert mark(w, "read", "running").exit_code == 0
    s = state(w, "read")
    assert s["status"] == "running" and s["started_at"] and s["finished_at"] is None
    assert mark(w, "read", "done").exit_code == 0
    s = state(w, "read")
    assert s["status"] == "done" and s["started_at"] and s["finished_at"]


def test_mark_failed_and_other_claude_stages(tmp_path):
    w = work(tmp_path)
    for stage in ("distill", "critique", "review"):
        assert mark(w, stage, "running").exit_code == 0
    assert mark(w, "review", "failed").exit_code == 0
    assert state(w, "review")["status"] == "failed"
    assert state(w, "distill")["status"] == "running"


def mark_main(monkeypatch, w, stage, status):
    """Through cli.main, where usage errors exit 64 (CliRunner reports click's 2)."""
    argv = ["skipwatch", "mark", "--work", str(w.path), "--stage", stage, "--status", status]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    return exc.value.code


def test_mark_refuses_engine_stages_and_bad_status(tmp_path, monkeypatch):
    # engine stages mark themselves; a hand mark could hide a stage that never ran
    w = work(tmp_path)
    for stage in ("ingest", "frames", "check", "install"):
        assert mark_main(monkeypatch, w, stage, "done") == ExitCode.USAGE, stage
        assert state(w, stage)["status"] == "pending"
    assert mark_main(monkeypatch, w, "read", "pending") == ExitCode.USAGE
    assert mark_main(monkeypatch, w, "read", "done") == 0


def test_mark_needs_an_existing_work_folder(tmp_path):
    r = CliRunner().invoke(
        app,
        ["mark", "--work", str(tmp_path / "nope"), "--stage", "read", "--status", "done"],
    )
    assert r.exit_code == 2 and "not a SkipWatch work folder" in r.output
    assert not (tmp_path / "nope").exists()  # never creates a work folder
