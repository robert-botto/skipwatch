from pathlib import Path

import pytest

from skipwatch.config import load_config, skipwatch_home
from skipwatch.errors import ExitCode


def test_exit_codes_are_the_section_6_table():
    assert [c.value for c in ExitCode] == [*range(10), 64, 70]
    assert ExitCode.USAGE == 64


def test_home_defaults_to_dot_skipwatch(monkeypatch):
    monkeypatch.delenv("SKIPWATCH_HOME", raising=False)
    assert skipwatch_home() == Path.home() / ".skipwatch"


def test_home_respects_env(sw_home):
    assert skipwatch_home() == sw_home


def test_defaults_match_section_3_4(tmp_path):
    cfg = load_config(tmp_path / "missing.toml")
    assert cfg.install.scope == "user"
    assert (cfg.frames.per_minute, cfg.frames.max) == (3, 60)
    assert cfg.transcribe.backend == "auto"
    assert cfg.providers.treg.enabled == "auto"
    assert cfg.style.forbid == ["em-dash"]
    assert cfg.exports.mem0.enabled is False and cfg.exports.notes.enabled is False


def test_config_file_overrides(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[frames]\nper_minute = 5\nmax = 150\n[style]\nforbid = []\n", encoding="utf-8")
    cfg = load_config(p)
    assert (cfg.frames.per_minute, cfg.frames.max) == (5, 150)
    assert cfg.style.forbid == []


def test_unknown_config_key_rejected(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[frames]\nper_minuet = 5\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(p)


def test_relative_home_resolved_to_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SKIPWATCH_HOME", "rel-home")
    home = skipwatch_home()
    assert home.is_absolute()
    assert home == Path.cwd() / "rel-home"


def test_config_types_are_strict(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[frames]\nper_minute = "5"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(p)


def test_install_scope_agents_allowed(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[install]\nscope = "agents"\n', encoding="utf-8")
    assert load_config(p).install.scope == "agents"
