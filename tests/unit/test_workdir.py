from datetime import datetime

import pytest

from skipwatch.models import SourceFile
from skipwatch.workdir import (
    STAGE_ORDER,
    WorkDir,
    new_work_path,
    read_model,
    run_stage,
    write_model,
)


def test_new_work_path_layout(sw_home):
    p = new_work_path("demo", datetime(2026, 10, 9, 18, 20, 0))
    assert p == sw_home / "work" / "demo-20261009-182000"


def test_ensure_creates_pending_stages(tmp_path):
    w = WorkDir(tmp_path / "w")
    w.ensure()
    assert all(s.status == "pending" for s in w.stages().stages.values())
    assert list(w.stages().stages) == list(STAGE_ORDER)


def test_r_work_1_done_only_after_output(tmp_path):
    w = WorkDir(tmp_path / "w")
    w.ensure()
    seen = {}

    def stage():
        seen["status_during"] = w.stages().stages["ingest"].status
        write_model(w.file("source.json"), SourceFile(kind="file", platform="local", path="/x.mp4"))
        return 1

    run_stage(w, "ingest", stage)
    assert seen["status_during"] == "running"
    assert w.file("source.json").exists()
    assert w.stages().stages["ingest"].status == "done"


def test_r_work_1_failure_marks_failed_and_resume_points_there(tmp_path):
    w = WorkDir(tmp_path / "w")
    w.ensure()
    w.mark("detect", "done")
    with pytest.raises(RuntimeError):
        run_stage(w, "ingest", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    st = w.stages().stages["ingest"]
    assert st.status == "failed" and st.error == "boom"
    assert w.first_incomplete() == "ingest"


def test_write_model_is_deterministic(tmp_path):
    p = tmp_path / "s.json"
    m = SourceFile(kind="file", platform="local", path="/x.mp4")
    write_model(p, m)
    a = p.read_bytes()
    write_model(p, m)
    assert p.read_bytes() == a
    assert read_model(p, SourceFile) == m
