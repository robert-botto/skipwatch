"""`skipwatch --log <file> <command>` (skill audit fix 18): the engine logs and times each stage,
so the skill never assembles `T0=$(date +%s); ...; rc=$?` one-liners by hand."""

import json
import sys

import pytest
import typer

from skipwatch import cli, stagelog
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.output import progress


def _fake_app() -> typer.Typer:
    """The real root callback (where --log lives) with fake commands under it."""
    app = typer.Typer()
    app.callback(invoke_without_command=True)(cli._root)

    @app.command("ok")
    def _ok(json_out: bool = typer.Option(False, "--json")):
        def body() -> int:
            for n in range(1, 6):
                progress(f"step {n}")
            if json_out:
                sys.stdout.write(json.dumps({"ok": True}) + "\n")
            return 0

        cli.run_command(body)

    @app.command("boom")
    def _boom():
        def body() -> int:
            progress("starting")
            raise SkipwatchError(ExitCode.INTERNAL_ERROR, "a content provider lost the bundle")

        cli.run_command(body)

    @app.command("needs-arg")
    def _needs_arg(name: str):
        progress(name)

    return app


@pytest.fixture
def logs(sw_home):
    """The logs/ folder of a work folder under the test home: where --log may write."""
    from skipwatch.workdir import WorkDir

    work = sw_home / "work" / "logged-20261012-120000"
    WorkDir(work).ensure()
    return work / "logs"


def _run(monkeypatch, args, app=None):
    if app is not None:
        monkeypatch.setattr(cli, "app", app)
    monkeypatch.setattr(sys, "argv", ["skipwatch", *args])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    return exc.value.code


def test_success_logs_progress_and_prints_rc_elapsed_and_last_3_lines(monkeypatch, capsys, logs):
    log = logs / "ingest.log"
    assert _run(monkeypatch, ["--log", str(log), "ok"], _fake_app()) == 0
    err = capsys.readouterr().err.splitlines()
    assert err == ["rc=0 elapsed=0s", "step 3", "step 4", "step 5"]
    assert log.read_text(encoding="utf-8").splitlines() == [f"step {n}" for n in range(1, 6)]


def test_engine_error_keeps_its_exit_code_and_its_message_is_in_the_tail(monkeypatch, capsys, logs):
    log = logs / "boom.log"
    code = _run(monkeypatch, ["--log", str(log), "boom"], _fake_app())
    assert code == ExitCode.INTERNAL_ERROR == 70
    assert capsys.readouterr().err.splitlines() == [
        "rc=70 elapsed=0s",
        "starting",
        "a content provider lost the bundle",
    ]


def test_json_stdout_is_untouched(monkeypatch, capsys, logs):
    log = logs / "ok.log"
    assert _run(monkeypatch, ["--log", str(log), "ok", "--json"], _fake_app()) == 0
    out = capsys.readouterr()
    assert json.loads(out.out) == {"ok": True}
    assert "step" not in out.out and "rc=" not in out.out


def test_nested_missing_log_folder_is_created_and_the_log_overwritten(monkeypatch, capsys, logs):
    log = logs / "a" / "b" / "c" / "run.log"
    assert not log.parent.exists()
    assert _run(monkeypatch, ["--log", str(log), "ok"], _fake_app()) == 0
    assert _run(monkeypatch, ["--log", str(log), "ok"], _fake_app()) == 0
    assert log.read_text(encoding="utf-8").count("step 1") == 1  # overwritten, not appended


def test_usage_error_after_the_command_starts_exits_64_with_the_summary(monkeypatch, capsys, logs):
    log = logs / "usage.log"
    assert _run(monkeypatch, ["--log", str(log), "needs-arg"], _fake_app()) == ExitCode.USAGE
    err = capsys.readouterr().err
    assert "Missing argument" in err and "rc=64 elapsed=0s" in err
    assert log.exists()


def test_real_command_through_the_real_app(monkeypatch, capsys, logs):
    log = logs / "check.log"
    code = _run(monkeypatch, ["--log", str(log), "check", str(logs.parent / "nope")])
    assert code == ExitCode.USAGE
    err = capsys.readouterr().err.splitlines()
    assert err[0] == "rc=64 elapsed=0s"
    assert err[1:] == log.read_text(encoding="utf-8").splitlines()[-3:]
    assert "has no SKILL.md" in err[-1]


def test_elapsed_is_whole_seconds(monkeypatch, capsys, logs):
    clock = iter([100.0, 107.6])
    monkeypatch.setattr(stagelog.time, "monotonic", lambda: next(clock))
    assert _run(monkeypatch, ["--log", str(logs / "t.log"), "ok"], _fake_app()) == 0
    assert capsys.readouterr().err.splitlines()[0] == "rc=0 elapsed=8s"


def test_without_log_nothing_changes(monkeypatch, capsys):
    assert _run(monkeypatch, ["ok"], _fake_app()) == 0
    err = capsys.readouterr().err
    assert err.splitlines() == [f"step {n}" for n in range(1, 6)] and "rc=" not in err


def test_stderr_is_restored_after_a_logged_run(monkeypatch, capsys, logs):
    before = sys.stderr
    _run(monkeypatch, ["--log", str(logs / "r.log"), "boom"], _fake_app())
    assert sys.stderr is before
    progress("after")
    assert capsys.readouterr().err.splitlines()[-1] == "after"


def test_an_unexpected_crash_still_reports_rc_1_and_reraises(monkeypatch, capsys, logs):
    app = _fake_app()

    @app.command("crash")
    def _crash():
        progress("about to crash")
        raise RuntimeError("engine bug")

    monkeypatch.setattr(cli, "app", app)
    monkeypatch.setattr(sys, "argv", ["skipwatch", "--log", str(logs / "c.log"), "crash"])
    with pytest.raises(RuntimeError):
        cli.main()
    assert capsys.readouterr().err.splitlines() == ["rc=1 elapsed=0s", "about to crash"]


def test_cli_runner_without_main_still_restores_stderr(logs):
    """Click closes the root context on the way out, so stderr never stays on the log file."""
    from typer.testing import CliRunner

    before = sys.stderr
    r = CliRunner().invoke(_fake_app(), ["--log", str(logs / "r.log"), "ok"])
    assert r.exit_code == 0 and sys.stderr is before
    assert (logs / "r.log").read_text(encoding="utf-8").splitlines()[-1] == "step 5"
    stagelog.report(0)  # clear the module state the runner left for main


# ---- --log is confined to a work folder's logs/ (skill audit 5 fix 5 follow-up) ----


def _work(home, area: str = "work"):
    from skipwatch.workdir import WorkDir

    path = home / area / "demo-20261012-120000"
    WorkDir(path).ensure()
    return path


@pytest.mark.parametrize("area", ["work", "packs"])
def test_log_inside_a_work_folders_logs_runs(monkeypatch, capsys, sw_home, area):
    log = _work(sw_home, area) / "logs" / "deep" / "ok.log"
    assert _run(monkeypatch, ["--log", str(log), "ok"], _fake_app()) == 0
    assert log.read_text(encoding="utf-8").splitlines()[-1] == "step 5"


def test_log_follows_home_in_either_order(monkeypatch, capsys, tmp_path, sw_home):
    home = tmp_path / "project" / ".skipwatch"
    log = _work(home) / "logs" / "ok.log"
    assert _run(monkeypatch, ["--home", str(home), "--log", str(log), "ok"], _fake_app()) == 0
    assert _run(monkeypatch, ["--log", str(log), "--home", str(home), "ok"], _fake_app()) == 0
    assert log.is_file()


def test_log_outside_a_work_folders_logs_is_refused_before_anything(
    monkeypatch, capsys, tmp_path, sw_home
):
    work = _work(sw_home)
    victim = tmp_path / "victim.rc"
    victim.write_text("keep\n", encoding="utf-8")
    elsewhere = _work(tmp_path / "elsewhere")
    nested = _work(sw_home / "work" / "a")
    bad = sw_home / "work" / "bad-20261012-120000"
    bad.mkdir(parents=True)
    (bad / "stages.json").write_text("{", encoding="utf-8")
    targets = [
        victim,
        tmp_path / "new.log",
        work / "stages.json",
        work / "run.log",
        work / "logs",
        work / "logs" / ".." / ".." / ".." / "escape.log",
        sw_home / "work" / "logs" / "x.log",
        elsewhere / "logs" / "x.log",
        nested / "logs" / "x.log",
        bad / "logs" / "x.log",
    ]
    (work / "logs").mkdir(exist_ok=True)
    try:
        (work / "logs" / "link.log").symlink_to(victim)
        (work / "logs" / "dir").symlink_to(tmp_path, target_is_directory=True)
        linked = sw_home / "work" / "linked-20261012-120000"
        linked.symlink_to(elsewhere, target_is_directory=True)
        targets += [work / "logs" / "link.log", work / "logs" / "dir" / "x.log"]
        targets.append(linked / "logs" / "x.log")
    except OSError:
        pass
    ran = []
    app = _fake_app()

    @app.command("mark-ran")
    def _mark():
        ran.append(True)

    for log in targets:
        assert _run(monkeypatch, ["--log", str(log), "mark-ran"], app) == ExitCode.USAGE, log
        err = capsys.readouterr().err
        assert "--log" in err and "rc=" not in err, log
    assert ran == []
    assert victim.read_text(encoding="utf-8") == "keep\n"
    assert not (tmp_path / "new.log").exists() and not (tmp_path / "x.log").exists()
    assert not (sw_home / "escape.log").exists() and not (tmp_path / "escape.log").exists()
    assert not (elsewhere / "logs" / "x.log").exists()
    assert not (bad / "logs").exists() and not (work / "run.log").exists()
