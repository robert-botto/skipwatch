import json
import sys

import pytest
from typer.testing import CliRunner

from skipwatch import cli
from skipwatch.cli import app
from skipwatch.errors import ExitCode
from skipwatch.models import Batch, BatchesFile, FrameNote, NotesFile
from skipwatch.workdir import WorkDir, read_model, write_model


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
    for stage in ("ingest", "frames", "check"):
        assert mark_main(monkeypatch, w, stage, "done") == ExitCode.USAGE, stage
        assert state(w, stage)["status"] == "pending"
    assert mark_main(monkeypatch, w, "read", "pending") == ExitCode.USAGE
    assert mark_main(monkeypatch, w, "read", "done") == 0


def test_mark_install_done(tmp_path):
    # the install command takes a staging folder, not --work, so it cannot mark itself;
    # resume needs install done to see a finished run
    w = work(tmp_path)
    assert mark(w, "install", "done").exit_code == 0
    assert state(w, "install")["status"] == "done"


def test_mark_needs_an_existing_work_folder(tmp_path):
    r = CliRunner().invoke(
        app,
        ["mark", "--work", str(tmp_path / "nope"), "--stage", "read", "--status", "done"],
    )
    assert r.exit_code == 64 and "has no readable stages.json" in r.output
    assert not (tmp_path / "nope").exists()  # never creates a work folder


# ---- merge-notes: fold a missing-frames retry into the batch's notes file ----


def notes_work(tmp_path, ids):
    w = tmp_path / "w"
    WorkDir(w).ensure()  # directly in tmp_path, the test home's work/ (conftest)
    (w / "notes").mkdir(parents=True)
    batch = Batch(id=2, frame_ids=ids, notes_path="notes/batch-02.json")
    write_model(w / "batches.json", BatchesFile(batches=[batch]))
    return w


def notes(w, name, ids, batch=2, note=""):
    frames = [FrameNote(id=i, t=float(n), shows="terminal", note=note) for n, i in enumerate(ids)]
    write_model(w / "notes" / name, NotesFile(batch=batch, frames=frames))


def merge(w, batch="2"):
    return CliRunner().invoke(app, ["merge-notes", "--work", str(w), "--batch", batch])


def test_merge_notes_adds_missing_frames_in_batch_order(tmp_path):
    w = notes_work(tmp_path, ["f1", "f2", "f3", "f4"])
    notes(w, "batch-02.json", ["f1", "f2", "f4"], note="first")
    notes(w, "batch-02.retry.json", ["f3", "f1"], note="retry")
    r = merge(w)
    assert r.exit_code == 0, r.output
    merged = read_model(w / "notes/batch-02.json", NotesFile)
    assert [f.id for f in merged.frames] == ["f1", "f2", "f3", "f4"]
    # the first reader's entries win; the retry only fills the gap
    assert [f.note for f in merged.frames] == ["first", "first", "retry", "first"]
    assert not (w / "notes/batch-02.retry.json").exists()
    v = CliRunner().invoke(app, ["validate-notes", "--work", str(w)])
    assert v.exit_code == 0, v.output


def test_merge_notes_drops_frames_outside_the_batch(tmp_path):
    w = notes_work(tmp_path, ["f1", "f2"])
    notes(w, "batch-02.json", ["f1"])
    notes(w, "batch-02.retry.json", ["f2", "f9"])
    assert merge(w).exit_code == 0
    merged = read_model(w / "notes/batch-02.json", NotesFile)
    assert [f.id for f in merged.frames] == ["f1", "f2"]


def test_merge_notes_reports_frames_still_missing(tmp_path):
    w = notes_work(tmp_path, ["f1", "f2", "f3"])
    notes(w, "batch-02.json", ["f1"])
    notes(w, "batch-02.retry.json", ["f2"])
    r = merge(w)
    assert r.exit_code == 0
    assert "still missing f3" in r.output


def test_merge_notes_needs_both_valid_files(tmp_path):
    w = notes_work(tmp_path, ["f1", "f2"])
    notes(w, "batch-02.json", ["f1"])
    r = merge(w)  # no retry file
    assert r.exit_code == 7 and "batch-02.retry.json" in r.output
    notes(w, "batch-02.retry.json", ["f2"], batch=3)  # retry for the wrong batch
    assert merge(w).exit_code == 7
    assert [f.id for f in read_model(w / "notes/batch-02.json", NotesFile).frames] == ["f1"]
    (w / "notes/batch-02.json").unlink()  # nothing to merge into: re-dispatch the batch
    notes(w, "batch-02.retry.json", ["f2"])
    assert merge(w).exit_code == 7
    assert merge(w, "5").exit_code == 7  # no such batch
    (w / "batches.json").unlink()
    assert merge(w).exit_code == 7  # no plan yet
