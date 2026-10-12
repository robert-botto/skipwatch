from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.models import (
    Batch,
    BatchesFile,
    FrameNote,
    NotesError,
    NotesFile,
    ValidateNotesResult,
)
from skipwatch.workdir import write_model


def make_work(tmp_path, batches: dict[int, list[str]]):
    w = tmp_path / "w"
    (w / "notes").mkdir(parents=True)
    write_model(
        w / "batches.json",
        BatchesFile(
            batches=[
                Batch(id=i, frame_ids=ids, notes_path=f"notes/batch-{i:02d}.json")
                for i, ids in batches.items()
            ]
        ),
    )
    return w


def write_notes(w, batch: int, ids: list[str]):
    frames = [FrameNote(id=i, t=float(n), shows="terminal") for n, i in enumerate(ids)]
    write_model(w / f"notes/batch-{batch:02d}.json", NotesFile(batch=batch, frames=frames))


def run(w):
    return CliRunner().invoke(app, ["validate-notes", "--work", str(w)])


def test_validate_notes_fails_on_missing_file(tmp_path):
    w = make_work(tmp_path, {1: ["f000100"], 2: ["f000200"]})
    write_notes(w, 1, ["f000100"])
    r = run(w)
    assert r.exit_code == 1
    assert "batch 2: missing notes/batch-02.json" in r.output
    assert "batch 1" not in r.output


def test_validate_notes_fails_on_malformed_json(tmp_path):
    w = make_work(tmp_path, {1: ["f000100"]})
    (w / "notes/batch-01.json").write_text('{"schema": "skipwatch/notes/1", "batch": 1')
    r = run(w)
    assert r.exit_code == 1 and "batch 1: invalid" in r.output


def test_validate_notes_fails_on_wrong_schema_shape(tmp_path):
    w = make_work(tmp_path, {1: ["f000100"]})
    (w / "notes/batch-01.json").write_text(
        '{"schema": "skipwatch/notes/1", "batch": 1, "frames": [{"id": "f000100"}]}'
    )
    r = run(w)
    assert r.exit_code == 1 and "batch 1: invalid" in r.output


def test_validate_notes_fails_on_wrong_batch_id(tmp_path):
    w = make_work(tmp_path, {1: ["f000100"], 2: ["f000200"]})
    write_notes(w, 1, ["f000100"])
    write_model(
        w / "notes/batch-02.json",
        NotesFile(batch=1, frames=[FrameNote(id="f000200", t=20.0, shows="other")]),
    )
    r = run(w)
    assert r.exit_code == 1 and "batch 2: batch id is 1, expected 2" in r.output


def test_validate_notes_fails_on_wrong_frames(tmp_path):
    w = make_work(tmp_path, {1: ["f000100", "f000110"]})
    write_notes(w, 1, ["f000100", "f000999"])  # a reader that read the wrong batch
    r = run(w)
    assert r.exit_code == 1
    assert "batch 1: frames missing f000110; unexpected f000999" in r.output


def test_validate_notes_exit_7_without_batches(tmp_path):
    w = tmp_path / "w"
    w.mkdir()
    r = run(w)
    assert r.exit_code == 7 and "batches.json" in r.output


def test_validate_notes_passes(tmp_path):
    w = make_work(tmp_path, {1: ["f000100", "f000110"], 2: ["f000200"]})
    write_notes(w, 1, ["f000110", "f000100"])  # order does not matter
    write_notes(w, 2, ["f000200"])
    r = run(w)
    assert r.exit_code == 0, r.output
    assert "2 notes files valid" in r.output


def test_validate_notes_passes_with_zero_batches(tmp_path):
    w = make_work(tmp_path, {})
    assert run(w).exit_code == 0


def run_json(w):
    r = CliRunner().invoke(app, ["validate-notes", "--work", str(w), "--json"])
    return r, ValidateNotesResult.model_validate_json(r.stdout)


def test_validate_notes_json_reports_every_bad_batch(tmp_path):
    w = make_work(tmp_path, {1: ["f000100"], 2: ["f000200"], 3: ["f000300", "f000310"]})
    write_model(
        w / "notes/batch-02.json",
        NotesFile(batch=4, frames=[FrameNote(id="f000200", t=20.0, shows="other")]),
    )
    write_notes(w, 3, ["f000300", "f000999"])
    r, result = run_json(w)
    assert r.exit_code == 1
    assert result.ok is False and result.batches == 3
    assert result.errors == [
        NotesError(batch=1, message="missing notes/batch-01.json"),
        NotesError(batch=2, field="batch", message="batch id is 4, expected 2"),
        NotesError(batch=3, frame="f000310", message="missing"),
        NotesError(batch=3, frame="f000999", message="unexpected"),
    ]


def test_validate_notes_json_keeps_the_validation_error_location(tmp_path):
    w = make_work(tmp_path, {1: ["f000100"]})
    (w / "notes/batch-01.json").write_text(
        '{"schema": "skipwatch/notes/1", "batch": 1,'
        ' "frames": [{"id": "f000100", "t": "soon", "shows": "terminal"}]}'
    )
    r, result = run_json(w)
    assert r.exit_code == 1
    [error] = result.errors
    assert error.batch == 1 and error.field == "frames.0.t"
    assert error.message.startswith("invalid notes/batch-01.json")


def test_validate_notes_json_malformed_json_has_no_field(tmp_path):
    w = make_work(tmp_path, {1: ["f000100"]})
    (w / "notes/batch-01.json").write_text('{"schema": "skipwatch/notes/1", "batch": 1')
    r, result = run_json(w)
    assert r.exit_code == 1
    [error] = result.errors
    assert error.field is None and error.message.startswith("invalid notes/batch-01.json")


def test_validate_notes_json_passes(tmp_path):
    w = make_work(tmp_path, {1: ["f000100"], 2: ["f000200"]})
    write_notes(w, 1, ["f000100"])
    write_notes(w, 2, ["f000200"])
    r, result = run_json(w)
    assert r.exit_code == 0, r.output
    assert result == ValidateNotesResult(ok=True, batches=2)
