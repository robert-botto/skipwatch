import json

import pytest
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import (
    IngestBundle,
    MediaInfo,
    ResumeResult,
    Route,
    RunFile,
    SourceInfo,
)
from skipwatch.resume import newest_incomplete, resume_info
from skipwatch.workdir import WorkDir, write_model


def work_at(path, done=(), running=None, run_json=False):
    w = WorkDir(path)
    w.ensure()
    if run_json:
        run = RunFile(input="https://youtu.be/x", started_at="2026-10-09T12:00:00Z")
        write_model(w.file("run.json"), run)
    for s in done:
        w.mark(s, "done")
    if running:
        w.mark(running, "running")
    return w


def resume(*args):
    return CliRunner().invoke(app, ["resume", *args])


def test_running_stage_counts_as_incomplete(tmp_path):
    w = WorkDir(tmp_path / "w")
    w.ensure()
    for s in ("detect", "ingest", "transcribe"):
        w.mark(s, "done")
    w.mark("frames", "running")  # process was killed here
    r = resume_info(w.path)
    assert r.next_stage == "frames" and r.completed == ["detect", "ingest", "transcribe"]


def test_failed_stage_is_next_and_later_done_stages_are_listed(tmp_path):
    w = work_at(tmp_path / "w", done=("detect", "ingest", "frames"))
    w.mark("transcribe", "failed", error="boom")
    r = resume_info(w.path)
    assert r.next_stage == "transcribe" and r.completed == ["detect", "ingest", "frames"]


def test_newest_incomplete_skips_reviewed_runs(sw_home):
    older = work_at(
        sw_home / "work" / "demo-20261001-090000", run_json=True, done=("detect", "ingest")
    )
    newer = work_at(
        sw_home / "work" / "demo-20261005-090000",
        done=("detect", "ingest", "transcribe", "frames", "plan", "read", "distill"),
        run_json=True,
    )
    newer.mark("critique", "done")
    newer.mark("check", "done")
    newer.mark("review", "done")  # reviewed: install was declined, nothing to resume
    assert newest_incomplete(sw_home) == older.path
    newer.mark("review", "pending")
    assert newest_incomplete(sw_home) == newer.path


def test_newest_incomplete_orders_by_timestamp_suffix_not_name(sw_home):
    a = work_at(sw_home / "work" / "zeta-20261001-090000", run_json=True, done=("detect",))
    b = work_at(sw_home / "work" / "alpha-20261002-090000", run_json=True, done=("detect",))
    work_at(sw_home / "work" / "not-a-run", run_json=True)  # no timestamp suffix: ignored
    (sw_home / "work" / "loose-20261009-000000").mkdir()  # no stages.json: ignored
    assert newest_incomplete(sw_home) == b.path
    b.mark("review", "done")
    assert newest_incomplete(sw_home) == a.path


def test_newest_incomplete_none_when_everything_is_complete(sw_home):
    assert newest_incomplete(sw_home) is None  # no work folder at all
    w = work_at(sw_home / "work" / "demo-20261001-090000", run_json=True)
    for s in w.stages().stages:
        w.mark(s, "done")
    assert newest_incomplete(sw_home) is None


def test_resume_reads_run_json(tmp_path):
    w = work_at(tmp_path / "w", done=("detect",))
    run = RunFile(
        input="https://youtu.be/x", flags=["--thorough"], started_at="2026-10-09T12:00:00Z"
    )
    write_model(w.file("run.json"), run)
    r = resume_info(w.path)
    assert r.run is not None and r.run.flags == ["--thorough"] and r.run.input == run.input
    assert r.next_stage == "ingest"


def test_resume_without_or_with_broken_run_json_has_no_run(tmp_path):
    w = work_at(tmp_path / "w", done=("detect",))
    assert resume_info(w.path).run is None
    w.file("run.json").write_text("{not json")
    assert resume_info(w.path).run is None


def test_media_present_follows_ingest_media_path(tmp_path):
    w = work_at(tmp_path / "w", done=("detect", "ingest"))
    bundle = IngestBundle(
        source=SourceInfo(kind="video", platform="youtube", url="https://youtu.be/x"),
        media=MediaInfo(path="media/video.mp4", has_audio=True),
        route=Route(context="free", media="free"),
    )
    write_model(w.file("ingest.json"), bundle)
    assert resume_info(w.path).media_present is False  # media/ was deleted after install
    (w.path / "media").mkdir()
    (w.path / "media" / "video.mp4").write_bytes(b"x")
    assert resume_info(w.path).media_present is True
    local = tmp_path / "clip.mp4"  # a local source points at the user's own file
    write_model(
        w.file("ingest.json"),
        bundle.model_copy(update={"media": MediaInfo(path=str(local), has_audio=True)}),
    )
    assert resume_info(w.path).media_present is False
    local.write_bytes(b"x")
    assert resume_info(w.path).media_present is True


def test_non_work_folder_raises_exit_2(tmp_path):
    for target in (tmp_path / "missing", tmp_path):
        with pytest.raises(SkipwatchError) as e:
            resume_info(target)
        assert e.value.code == ExitCode.UNSUPPORTED_SOURCE
        assert "not a SkipWatch work folder" in e.value.message
    (tmp_path / "empty").mkdir()  # a folder with no stages.json
    with pytest.raises(SkipwatchError) as e:
        resume_info(tmp_path / "empty")
    assert e.value.code == ExitCode.UNSUPPORTED_SOURCE


@pytest.mark.parametrize("content", ["{}", "{not json", '{"schema": "skipwatch/stages/1"}'])
def test_invalid_stages_json_is_exit_7(tmp_path, content):
    (tmp_path / "stages.json").write_text(content)
    with pytest.raises(SkipwatchError) as e:
        resume_info(tmp_path)
    assert e.value.code == ExitCode.NO_CONTENT
    assert e.value.message.startswith("stages.json is unreadable: ")
    r = resume(str(tmp_path), "--json")
    assert r.exit_code == 7 and r.stdout == ""


def test_resume_json_validates_and_exit_codes(sw_home, tmp_path):
    w = work_at(tmp_path / "w", done=("detect", "ingest"), running="transcribe")
    r = resume(str(w.path), "--json")
    assert r.exit_code == 0, r.output
    out = ResumeResult.model_validate_json(r.stdout)  # R-CLI-2: requires the schema tag
    assert out.next_stage == "transcribe" and out.completed == ["detect", "ingest"]
    assert out.work == str(w.path)
    assert f"Resume: {w.path} at transcribe (2 stages done)" in r.stderr
    again = resume(str(w.path), "--json")  # R-CLI-1: read-only, so the same answer twice
    assert again.exit_code == 0 and again.stdout == r.stdout

    bad = resume(str(tmp_path), "--json")
    assert bad.exit_code == 2 and bad.stdout == ""
    assert "not a SkipWatch work folder" in bad.stderr


def test_resume_without_folder_picks_newest_incomplete(sw_home):
    w = work_at(sw_home / "work" / "demo-20261001-090000", done=("detect",), run_json=True)
    r = resume("--json")
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout)["work"] == str(w.path)
    assert json.loads(r.stdout)["next_stage"] == "ingest"


def test_nothing_to_resume_is_exit_0_with_null_stage(sw_home):
    r = resume("--json")
    assert r.exit_code == 0, r.output
    out = ResumeResult.model_validate_json(r.stdout)
    assert out.next_stage is None and out.work == ""
    assert "Resume: nothing to resume" in r.stderr
    plain = resume()
    assert plain.exit_code == 0 and plain.stdout == ""


def test_resume_of_a_complete_folder_says_so(tmp_path):
    w = work_at(tmp_path / "w")
    for s in w.stages().stages:
        w.mark(s, "done")
    r = resume(str(w.path), "--json")
    assert r.exit_code == 0 and json.loads(r.stdout)["next_stage"] is None
    assert f"Resume: {w.path} is complete (12 stages done)" in r.stderr


FINISHED = (
    "detect",
    "ingest",
    "transcribe",
    "frames",
    "plan",
    "read",
    "distill",
    "critique",
    "check",
    "review",
    "install",
)


def test_finished_run_is_complete_without_the_export_feature(tmp_path, sw_home):
    # export never runs before M6, so a run whose install is done has nothing left
    w = work_at(tmp_path / "w", done=FINISHED)
    r = resume_info(w.path)
    assert r.next_stage is None and r.completed[-1] == "install"
    out = resume(str(w.path), "--json")
    assert out.exit_code == 0 and json.loads(out.stdout)["next_stage"] is None


def test_install_not_done_is_still_next(tmp_path, sw_home):
    w = work_at(tmp_path / "w", done=FINISHED[:-1])
    assert resume_info(w.path).next_stage == "install"


def test_export_is_next_only_when_the_feature_exists_and_is_enabled(tmp_path, sw_home, monkeypatch):
    import skipwatch.resume as resume_mod

    w = work_at(tmp_path / "w", done=FINISHED)
    sw_home.mkdir(parents=True, exist_ok=True)
    (sw_home / "config.toml").write_text("[exports.notes]\nenabled = true\n")
    assert resume_info(w.path).next_stage is None  # enabled, but no export command yet
    monkeypatch.setattr(resume_mod, "_export_command_exists", lambda: True)
    assert resume_info(w.path).next_stage == "export"  # the M6 seam
    (sw_home / "config.toml").write_text("[exports.notes]\nenabled = false\n")
    assert resume_info(w.path).next_stage is None


def test_newest_incomplete_skips_a_finished_run(sw_home):
    older = work_at(sw_home / "work" / "demo-20261001-090000", run_json=True, done=("detect",))
    newer = work_at(sw_home / "work" / "demo-20261005-090000", run_json=True, done=FINISHED)
    newer.mark("review", "running")  # even with review re-opened, install done ends it
    newer.mark("review", "done")
    assert newest_incomplete(sw_home) == older.path


def test_newest_incomplete_skips_a_folder_without_run_json(sw_home):
    # an abandoned folder (new-work ran, then the Write probe failed) must not win
    real = work_at(sw_home / "work" / "demo-20261001-090000", done=("detect",), run_json=True)
    work_at(sw_home / "work" / "demo-20261005-090000")  # newer orphan, no run.json
    assert newest_incomplete(sw_home) == real.path
