"""`doctor --max-age-hours`: the stage 1 cache test, in the engine (skill audit 4 fix 1)."""

import os
import sys
import time

import pytest
from typer.testing import CliRunner

from skipwatch import cli, doctor
from skipwatch.cli import app
from skipwatch.errors import ExitCode
from skipwatch.models import DoctorReport
from skipwatch.workdir import write_model

CACHED = DoctorReport(tier="none", components=[], missing=[], warnings=["from the cache"])


def cache_doctor(home, age_hours: float = 0) -> None:
    home.mkdir(parents=True, exist_ok=True)
    path = home / "doctor.json"
    write_model(path, CACHED)
    then = time.time() - age_hours * 3600
    os.utime(path, (then, then))


def no_probe():
    raise AssertionError("doctor probed the machine for a fresh doctor.json")


def test_fresh_doctor_json_is_reused_without_probing(monkeypatch, sw_home):
    cache_doctor(sw_home, age_hours=1)
    monkeypatch.setattr(doctor, "probe_machine", no_probe)
    r = CliRunner().invoke(app, ["doctor", "--json", "--max-age-hours", "24"])
    assert r.exit_code == 0, r.output
    assert DoctorReport.model_validate_json(r.stdout) == CACHED
    assert r.stderr.startswith("Tier none")


def test_reuse_without_json_keeps_stdout_empty(monkeypatch, sw_home):
    cache_doctor(sw_home, age_hours=1)
    monkeypatch.setattr(doctor, "probe_machine", no_probe)
    r = CliRunner().invoke(app, ["doctor", "--max-age-hours", "24"])
    assert r.exit_code == 0 and r.stdout == ""
    assert r.stderr.startswith("Tier none")


def test_old_doctor_json_is_rebuilt(sw_home):
    cache_doctor(sw_home, age_hours=25)
    r = CliRunner().invoke(app, ["doctor", "--json", "--max-age-hours", "24"])
    assert r.exit_code == 0, r.output
    assert "from the cache" not in DoctorReport.model_validate_json(r.stdout).warnings
    rebuilt = DoctorReport.model_validate_json((sw_home / "doctor.json").read_text())
    assert "from the cache" not in rebuilt.warnings


def test_invalid_doctor_json_is_rebuilt(sw_home):
    sw_home.mkdir(parents=True)
    (sw_home / "doctor.json").write_text("{not json", encoding="utf-8")
    r = CliRunner().invoke(app, ["doctor", "--json", "--max-age-hours", "24"])
    assert r.exit_code == 0, r.output
    DoctorReport.model_validate_json(r.stdout)
    DoctorReport.model_validate_json((sw_home / "doctor.json").read_text())


def test_missing_doctor_json_is_built(sw_home):
    r = CliRunner().invoke(app, ["doctor", "--json", "--max-age-hours", "24"])
    assert r.exit_code == 0, r.output
    assert (sw_home / "doctor.json").is_file()


def test_without_max_age_doctor_always_rebuilds(sw_home):
    cache_doctor(sw_home, age_hours=0)
    r = CliRunner().invoke(app, ["doctor", "--json"])
    assert "from the cache" not in DoctorReport.model_validate_json(r.stdout).warnings


def test_home_option_picks_the_cached_doctor_json(monkeypatch, tmp_path, sw_home):
    project_home = tmp_path / "project" / ".skipwatch"
    cache_doctor(project_home, age_hours=1)
    monkeypatch.setattr(doctor, "probe_machine", no_probe)
    r = CliRunner().invoke(
        app, ["--home", str(project_home), "doctor", "--json", "--max-age-hours", "24"]
    )
    assert r.exit_code == 0, r.output
    assert DoctorReport.model_validate_json(r.stdout) == CACHED


@pytest.mark.parametrize("value", ["-1", "soon", "nan", "inf", "-inf", "1e400"])
def test_bad_max_age_is_a_usage_error(value, monkeypatch, sw_home):
    monkeypatch.setattr(sys, "argv", ["skipwatch", "doctor", "--max-age-hours", value])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == ExitCode.USAGE


def test_a_doctor_json_from_the_future_is_rebuilt(sw_home):
    cache_doctor(sw_home, age_hours=-48)  # clock skew or a copied file: never trust it
    r = CliRunner().invoke(app, ["doctor", "--json", "--max-age-hours", "24"])
    assert r.exit_code == 0, r.output
    assert "from the cache" not in DoctorReport.model_validate_json(r.stdout).warnings
