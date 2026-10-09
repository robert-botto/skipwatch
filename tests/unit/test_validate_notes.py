from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.models import Batch, BatchesFile, FrameNote, NotesFile
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
