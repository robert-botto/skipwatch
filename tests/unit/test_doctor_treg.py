"""Doctor's treg login detection (Task M4-A3, plan issue 11): Tier 3 needs treg logged in, and
the only network-capable call doctor makes is the free `treg balance --json`."""

import subprocess

from typer.testing import CliRunner

from skipwatch import doctor
from skipwatch.cli import app
from skipwatch.providers import content_treg
from tests.unit.test_doctor import TODAY, P


def test_tier_3_needs_treg_logged_in():
    on_path = P(whisper_faster=True, treg_on_path=True, treg_logged_in=False)
    assert doctor.compute_tier(on_path) == "1"
    assert (
        doctor.compute_tier(P(whisper_faster=True, treg_on_path=True, treg_logged_in=True)) == "3"
    )
    assert doctor.compute_tier(P(treg_on_path=True, treg_logged_in=True)) == "0"  # no whisper


def test_treg_lines_say_logged_in_or_how_to_log_in():
    for logged_in, expected in (
        (True, "treg: logged in"),
        (False, "treg: on PATH, not logged in: run treg login"),
    ):
        p = P(whisper_faster=True, treg_on_path=True, treg_logged_in=logged_in)
        report = doctor.build_report(p, TODAY, "/plug")
        lines = doctor.render_table(report)
        assert expected in lines
        assert sum(line.startswith("treg: ") for line in lines) == 1
        treg = next(c for c in report.components if c.name == "treg")
        assert treg.found is logged_in and treg.detail == expected.removeprefix("treg: ")
    absent = doctor.render_table(doctor.build_report(P(), TODAY, "/plug"))
    assert not any(line.startswith("treg: ") for line in absent)


def test_probe_checks_login_only_when_treg_is_on_path(monkeypatch):
    asked = []
    monkeypatch.setattr(content_treg, "logged_in", lambda: asked.append(1) or True)
    monkeypatch.setattr(doctor, "_treg_on_path", lambda: False)
    assert doctor.probe_machine().treg_logged_in is None and asked == []
    monkeypatch.setattr(doctor, "_treg_on_path", lambda: True)
    probe = doctor.probe_machine()
    assert probe.treg_on_path and probe.treg_logged_in is True and asked == [1]


def test_r_doc_1_doctor_still_never_installs(monkeypatch, sw_home):
    """The M0 spy, with treg on PATH: every command is a version probe except exactly one
    `treg balance --json`, the free login check."""
    calls = []
    real_run = subprocess.run

    def spy(cmd, *a, **k):
        calls.append([str(part) for part in cmd])
        if "balance" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")
        return real_run(cmd, *a, **k)

    monkeypatch.setattr(subprocess, "run", spy)
    monkeypatch.setattr(content_treg, "_treg_path", lambda: "/fake/bin/treg")
    monkeypatch.setattr(doctor, "_treg_on_path", lambda: True)
    monkeypatch.setattr(
        doctor.media, "_fetch_static", lambda: (_ for _ in ()).throw(AssertionError)
    )
    r = CliRunner().invoke(app, ["doctor"])
    assert r.exit_code == 0, r.output
    treg = [cmd for cmd in calls if cmd[0].endswith("treg")]
    assert treg == [["/fake/bin/treg", "balance", "--json", "--limit", "1"]]
    for cmd in calls:
        if cmd not in treg:
            assert cmd[-1] in ("--version", "-version"), cmd  # ffmpeg uses one dash
    assert "treg: logged in" in r.stderr
