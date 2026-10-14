import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch.cli import app
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import Config, Manifest
from skipwatch.providers import export_notes
from skipwatch.workdir import read_model
from tests.unit._skills import installed_skill

NOTE = """# run-x

Runs x. Use when you want x run.

- Source: [Run x](https://youtu.be/x) by [[someone]] on [[youtube]]
- Installed: 2026-10-09
- Path: `~/.claude/skills/run-x`
- Confidence: high

Part of [[SkipWatch skills]].
"""


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


@pytest.fixture
def skill(home) -> Path:
    return installed_skill(home / ".claude")


def manifest(skill: Path) -> Manifest:
    return read_model(skill / "skipwatch.json", Manifest)


def cfg(folder: str | None, enabled: bool = True) -> Config:
    notes: dict = {"enabled": enabled}
    if folder is not None:
        notes["folder"] = folder
    return Config.model_validate({"exports": {"notes": notes}})


def test_notes_writes_wiki_links_and_is_idempotent(skill, home):
    vault = home / "vault"
    vault.mkdir()
    item = export_notes.PROVIDER.export(skill, manifest(skill), cfg("~/vault"))
    note = vault / "run-x.md"
    assert item.provider == "notes" and item.ok and item.location == str(note)
    assert note.read_text(encoding="utf-8") == NOTE
    first = note.read_bytes()
    export_notes.PROVIDER.export(skill, manifest(skill), cfg(str(vault)))
    assert note.read_bytes() == first  # R-CLI-1: same manifest, same note
    assert [p.name for p in vault.iterdir()] == ["run-x.md"]  # no temp file left behind


def test_notes_without_author_or_url_still_reads(skill, home):
    vault = home / "vault"
    vault.mkdir()
    m = manifest(skill)
    m = m.model_copy(
        update={"source": m.source.model_copy(update={"author": None, "url": None, "title": None})}
    )
    export_notes.PROVIDER.export(skill, m, cfg(str(vault)))
    text = (vault / "run-x.md").read_text(encoding="utf-8")
    assert "- Source: untitled on [[youtube]]\n" in text


def test_notes_enabled_follows_config():
    assert export_notes.PROVIDER.name == "notes"
    assert export_notes.PROVIDER.enabled(cfg("x")) is True
    assert export_notes.PROVIDER.enabled(Config()) is False


def test_notes_folder_missing_is_exit_8(skill, home, sw_home):
    fix = "set [exports.notes] folder in config.toml to an existing folder"
    for folder in (None, "", "   ", "~/no-such-folder"):
        with pytest.raises(SkipwatchError) as e:
            export_notes.PROVIDER.export(skill, manifest(skill), cfg(folder))
        assert e.value.code == ExitCode.MISSING_DEPENDENCY and fix in e.value.message
    (home / "a-file").write_text("x", encoding="utf-8")
    with pytest.raises(SkipwatchError) as e:
        export_notes.PROVIDER.export(skill, manifest(skill), cfg(str(home / "a-file")))
    assert e.value.code == ExitCode.MISSING_DEPENDENCY
    r = CliRunner().invoke(app, ["export", str(skill), "--provider", "notes"])
    assert r.exit_code == 8 and fix in r.stderr


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs POSIX permissions")
def test_notes_read_only_folder_is_exit_8(skill, home):
    vault = home / "vault"
    vault.mkdir()
    vault.chmod(0o500)
    try:
        with pytest.raises(SkipwatchError) as e:
            export_notes.PROVIDER.export(skill, manifest(skill), cfg(str(vault)))
    finally:
        vault.chmod(0o700)
    assert e.value.code == ExitCode.MISSING_DEPENDENCY
    assert f"cannot write a note to {vault}" in e.value.message


@pytest.mark.parametrize("name", ["../escape", "a/b", ".", ".."])
def test_notes_refuse_a_name_that_is_not_a_file_name(skill, home, name):
    vault = home / "vault"
    vault.mkdir()
    m = manifest(skill).model_copy(update={"name": name})
    with pytest.raises(SkipwatchError) as e:
        export_notes.PROVIDER.export(skill, m, cfg(str(vault)))
    assert e.value.code == ExitCode.UNSUPPORTED_SOURCE
    assert list(vault.iterdir()) == []


def test_notes_write_is_atomic(skill, home, monkeypatch):
    # review M1: a half-written note must never replace a good one
    vault = home / "vault"
    vault.mkdir()
    writes: list[tuple] = []
    real = export_notes.write_bytes_atomic

    def spy(path, data):
        writes.append((path, data))
        real(path, data)

    monkeypatch.setattr(export_notes, "write_bytes_atomic", spy)
    export_notes.PROVIDER.export(skill, manifest(skill), cfg(str(vault)))
    assert writes == [(vault / "run-x.md", NOTE.encode("utf-8"))]
