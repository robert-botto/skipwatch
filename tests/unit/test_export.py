import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch import export
from skipwatch.cli import app
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import Config, ExportItem, ExportLog, ExportResult
from skipwatch.workdir import read_model
from tests.unit._skills import installed_skill

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


class FakeProvider:
    def __init__(self, name: str, fail: SkipwatchError | None = None):
        self.name, self.fail, self.calls = name, fail, 0

    def enabled(self, cfg: Config) -> bool:
        return getattr(cfg.exports, self.name).enabled

    def export(self, skill_dir, manifest, cfg) -> ExportItem:
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        return ExportItem(provider=self.name, ok=True, location=f"{self.name}:{manifest.name}")


@pytest.fixture
def fakes(monkeypatch):
    found = {"mem0": FakeProvider("mem0"), "notes": FakeProvider("notes")}
    monkeypatch.setattr(export, "export_providers", lambda: dict(found))
    return found


@pytest.fixture
def skill(tmp_path, monkeypatch, sw_home) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.chdir(tmp_path)
    return installed_skill(home / ".claude")


def cfg(mem0: bool = False, notes: bool = False) -> Config:
    return Config.model_validate(
        {"exports": {"mem0": {"enabled": mem0}, "notes": {"enabled": notes}}}
    )


def log(sw_home: Path) -> ExportLog:
    return read_model(sw_home / "exports.json", ExportLog)


def test_export_runs_enabled_only_and_explicit_overrides(skill, fakes, sw_home):
    result = export.run_exports(skill, None, cfg(notes=True), NOW)
    assert result.name == "run-x"
    assert [(i.provider, i.ok, i.location) for i in result.results] == [
        ("notes", True, "notes:run-x")
    ]
    assert (fakes["mem0"].calls, fakes["notes"].calls) == (0, 1)

    result = export.run_exports(skill, "mem0", cfg(notes=True), NOW)  # disabled, but asked
    assert [i.provider for i in result.results] == ["mem0"]
    assert (fakes["mem0"].calls, fakes["notes"].calls) == (1, 1)

    assert export.run_exports(skill, None, cfg(), NOW).results == []
    with pytest.raises(SkipwatchError) as e:
        export.run_exports(skill, "obsidian", cfg(), NOW)
    assert e.value.code == ExitCode.USAGE


def test_export_cli_none_enabled(skill, fakes):
    r = CliRunner().invoke(app, ["export", "run-x"])
    assert r.exit_code == 0, r.stderr
    assert r.stderr.strip() == "no exports enabled"
    assert fakes["mem0"].calls == fakes["notes"].calls == 0


def test_export_unchanged_skill_is_skipped(skill, fakes, sw_home):
    both = cfg(mem0=True, notes=True)
    export.run_exports(skill, None, both, NOW)
    entries = log(sw_home).entries
    assert [(e.provider, e.name, e.ref) for e in entries] == [
        ("mem0", "run-x", "mem0:run-x"),
        ("notes", "run-x", "notes:run-x"),
    ]
    assert all(e.manifest_sha256.startswith("sha256:") for e in entries)
    assert entries[0].exported_at == "2026-10-13T12:00:00Z"

    again = export.run_exports(skill, None, both, NOW)
    assert [(i.provider, i.ok, i.skipped, i.detail) for i in again.results] == [
        ("mem0", True, True, "unchanged since last export"),
        ("notes", True, True, "unchanged since last export"),
    ]
    assert (fakes["mem0"].calls, fakes["notes"].calls) == (1, 1)

    manifest = skill / "skipwatch.json"
    manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    changed = export.run_exports(skill, "notes", both, NOW)
    assert [(i.provider, i.skipped) for i in changed.results] == [("notes", False)]
    entries = log(sw_home).entries
    assert len(entries) == 2  # the notes entry is replaced, not duplicated
    assert fakes["notes"].calls == 2


def test_export_failure_keeps_earlier_successes_logged(skill, fakes, sw_home):
    fakes["notes"].fail = SkipwatchError(ExitCode.MISSING_DEPENDENCY, "no folder")
    with pytest.raises(SkipwatchError) as e:
        export.run_exports(skill, None, cfg(mem0=True, notes=True), NOW)
    assert e.value.code == ExitCode.MISSING_DEPENDENCY
    assert [en.provider for en in log(sw_home).entries] == ["mem0"]


def test_export_without_manifest_is_exit_2(tmp_path, fakes):
    with pytest.raises(SkipwatchError) as e:
        export.run_exports(tmp_path, None, cfg(notes=True), NOW)
    assert e.value.code == ExitCode.UNSUPPORTED_SOURCE


def test_export_broken_log_reads_as_empty(skill, fakes, sw_home):
    sw_home.mkdir(parents=True, exist_ok=True)
    (sw_home / "exports.json").write_text("{not json", encoding="utf-8")
    result = export.run_exports(skill, None, cfg(notes=True), NOW)
    assert [i.skipped for i in result.results] == [False]
    assert [e.provider for e in log(sw_home).entries] == ["notes"]


def test_export_json_validates(skill, fakes, sw_home):
    sw_home.mkdir(parents=True, exist_ok=True)
    (sw_home / "config.toml").write_text("[exports.notes]\nenabled = true\n", encoding="utf-8")
    r = CliRunner().invoke(app, ["export", "run-x", "--json"])
    assert r.exit_code == 0, r.stderr
    result = ExportResult.model_validate_json(r.stdout)
    assert result.name == "run-x"
    assert [(i.provider, i.location) for i in result.results] == [("notes", "notes:run-x")]
    assert json.loads(r.stdout)["schema"] == "skipwatch/export/1"
    assert "notes: notes:run-x" in r.stderr

    r = CliRunner().invoke(app, ["export", "run-x", "--provider", "nope"])
    assert r.exit_code == ExitCode.USAGE


def test_export_unknown_skill_is_exit_2(skill, fakes):
    r = CliRunner().invoke(app, ["export", "nope"])
    assert r.exit_code == ExitCode.UNSUPPORTED_SOURCE
    assert "no installed SkipWatch skill named nope" in r.stderr
