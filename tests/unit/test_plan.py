import json

from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.models import BatchesFile, Frame, FramesFile, Sampling
from skipwatch.plan import make_batches
from skipwatch.workdir import WorkDir, read_model, write_model


def ff(n):
    return FramesFile(
        sampling=Sampling(per_minute=3, max=60),
        frames=[
            Frame(
                id=f"f{i * 10:06d}",
                t=float(i),
                path=f"frames/f{i * 10:06d}.jpg",
                reason="scene",
                dhash="0" * 16,
            )
            for i in range(n)
        ],
    )


def test_batches_of_20():
    b = make_batches(ff(45))
    assert [len(x.frame_ids) for x in b.batches] == [20, 20, 5]
    assert b.batches[2].notes_path == "notes/batch-03.json"
    assert [x.id for x in b.batches] == [1, 2, 3]


def test_empty_frames_give_no_batches():
    assert make_batches(ff(0)).batches == []


def test_batches_follow_time_order_and_cover_every_frame_once():
    frames = ff(25)
    frames.frames.reverse()
    b = make_batches(frames, size=10)
    ids = [i for x in b.batches for i in x.frame_ids]
    assert ids == sorted(f.id for f in frames.frames)


def _work(tmp_path, n):
    w = tmp_path / "work dir é"
    WorkDir(w).ensure()
    write_model(w / "frames.json", ff(n))
    return w


def test_plan_command_writes_batches_and_marks_stage(tmp_path):
    w = _work(tmp_path, 21)
    r = CliRunner().invoke(app, ["plan", "--work", str(w), "--batch-size", "7", "--json"])
    assert r.exit_code == 0, r.output
    on_disk = read_model(w / "batches.json", BatchesFile)
    assert [len(b.frame_ids) for b in on_disk.batches] == [7, 7, 7]
    assert BatchesFile.model_validate_json(r.stdout) == on_disk  # R-CLI-2
    assert WorkDir(w).stages().stages["plan"].status == "done"


def test_plan_command_is_idempotent(tmp_path):
    w = _work(tmp_path, 45)
    r1 = CliRunner().invoke(app, ["plan", "--work", str(w)])
    a = (w / "batches.json").read_bytes()
    r2 = CliRunner().invoke(app, ["plan", "--work", str(w)])
    assert r1.exit_code == r2.exit_code == 0 and a == (w / "batches.json").read_bytes()
    assert r1.stdout == ""  # machine output only with --json
    assert len(json.loads(a)["batches"]) == 3


def test_plan_without_frames_exits_7(tmp_path):
    w = tmp_path / "w"
    WorkDir(w).ensure()
    r = CliRunner().invoke(app, ["plan", "--work", str(w)])
    assert r.exit_code == 7
    assert WorkDir(w).stages().stages["plan"].status == "failed"


def test_plan_rejects_bad_batch_size(tmp_path):
    w = _work(tmp_path, 3)
    r = CliRunner().invoke(app, ["plan", "--work", str(w), "--batch-size", "0"])
    assert r.exit_code != 0 and not (w / "batches.json").exists()
