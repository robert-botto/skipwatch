"""`skipwatch --home <dir> <command>` (skill audit 2 fix 16): the home for one invocation,
resolved exactly as SKIPWATCH_HOME is, so the skill needs no env-var prefix."""

import json
from pathlib import Path

from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.config import skipwatch_home


def _new_work(*root_opts: str) -> Path:
    r = CliRunner().invoke(app, [*root_opts, "new-work", "--slug", "demo", "--json"])
    assert r.exit_code == 0, r.output
    return Path(json.loads(r.stdout.splitlines()[-1])["work"])


def test_home_option_wins_over_the_env_var(tmp_path, sw_home):
    home = tmp_path / "project" / ".skipwatch"
    work = _new_work("--home", str(home))
    assert work.parent == home / "work"
    assert not (sw_home / "work").exists()


def test_home_option_resolves_like_the_env_var(tmp_path, sw_home, monkeypatch):
    monkeypatch.chdir(tmp_path)
    work = _new_work("--home", "rel/.skipwatch")
    assert work.parent == (tmp_path / "rel" / ".skipwatch" / "work").absolute()
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    work = _new_work("--home", "~/.skipwatch")
    assert work.parent == tmp_path / "user" / ".skipwatch" / "work"


def test_home_option_does_not_leak_into_later_calls(tmp_path, sw_home):
    _new_work("--home", str(tmp_path / "once" / ".skipwatch"))
    assert skipwatch_home() == sw_home
    assert _new_work().parent == sw_home / "work"


def test_home_option_works_with_log_in_either_order(tmp_path, sw_home):
    home = tmp_path / "h" / ".skipwatch"
    work = _new_work("--home", str(home))
    log = work / "logs" / "note.log"
    note = ["note", "--work", str(work), "--degradation"]
    for value, root_opts in (
        ("home first", ("--home", str(home), "--log", str(log))),
        ("log first", ("--log", str(log), "--home", str(home))),
    ):
        r = CliRunner().invoke(app, [*root_opts, *note, value])
        assert r.exit_code == 0, r.output
        assert f"Noted: {value}" in log.read_text(encoding="utf-8")


# ---- --home must name a .skipwatch folder (skill audit 5 fix 5 follow-up) ----


def test_home_option_refuses_any_other_folder_before_running(tmp_path, sw_home, monkeypatch):
    monkeypatch.chdir(tmp_path)
    real = tmp_path / "real" / ".skipwatch"
    real.mkdir(parents=True)
    targets = [
        str(tmp_path / "anything"),
        str(tmp_path),
        str(tmp_path / ".skipwatch" / ".."),
        str(tmp_path / ".skipwatch" / "work"),
        str(tmp_path / ".skipwatchx"),
        "rel-home",
        "~",
    ]
    try:
        (tmp_path / "link").mkdir()
        (tmp_path / "link" / ".skipwatch").symlink_to(real, target_is_directory=True)
        targets.append(str(tmp_path / "link" / ".skipwatch"))
    except OSError:
        pass
    for home in targets:
        r = CliRunner().invoke(app, ["--home", home, "new-work", "--slug", "demo", "--json"])
        assert r.exit_code == 64, home
        assert "--home" in r.stderr and r.stdout == "", home
    assert not any(tmp_path.rglob("work"))
    assert not (sw_home / "work").exists()


def test_skipwatch_home_env_var_is_not_restricted(tmp_path, monkeypatch):
    monkeypatch.setenv("SKIPWATCH_HOME", str(tmp_path / "any-name"))
    assert _new_work().parent == tmp_path / "any-name" / "work"
