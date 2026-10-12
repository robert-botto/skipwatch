from datetime import UTC, datetime
from pathlib import Path

from skipwatch import installs
from skipwatch.models import InstallRecord, InstallResult, InstallsFile
from skipwatch.workdir import write_model

NOW = datetime(2026, 10, 11, 9, 30, 0, tzinfo=UTC)


def result(path: Path, name: str = "deploy-astro", scope="user") -> InstallResult:
    return InstallResult(name=name, path=str(path), scope=scope)


def test_load_missing_is_empty(sw_home):
    assert installs.load() == InstallsFile()


def test_load_invalid_is_empty_with_one_warning(sw_home, capsys):
    sw_home.mkdir(parents=True)
    (sw_home / installs.INSTALLS).write_text("{not json", encoding="utf-8")
    assert installs.load() == InstallsFile()
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and installs.INSTALLS in err


def test_record_appends_and_writes_atomically(sw_home, tmp_path):
    first, second = tmp_path / "a" / "one", tmp_path / "b" / "two"
    installs.record(result(first, "one"), "run", now=NOW)
    installs.record(result(second, "two", scope="dir"), "pack", now=NOW)
    data = installs.load().installs
    assert [(r.name, Path(r.path), r.scope, r.origin) for r in data] == [
        ("one", first.resolve(), "user", "run"),
        ("two", second.resolve(), "dir", "pack"),
    ]
    assert data[0].installed_at == "2026-10-11T09:30:00Z"
    assert sorted(p.name for p in sw_home.iterdir()) == [installs.INSTALLS]


def test_record_replaces_same_resolved_path(sw_home, tmp_path):
    target = tmp_path / "skills" / "one"
    target.mkdir(parents=True)
    installs.record(result(target, "one"), "run", now=NOW)
    later = datetime(2026, 10, 12, tzinfo=UTC)
    installs.record(result(target / ".." / "one", "one"), "pack", now=later)
    data = installs.load().installs
    assert len(data) == 1
    assert data[0].origin == "pack" and data[0].installed_at == "2026-10-12T00:00:00Z"


def test_record_keeps_other_records(sw_home, tmp_path):
    sw_home.mkdir(parents=True)
    old = InstallRecord(
        name="old", path=str(tmp_path / "old"), scope="user", installed_at="2026-01-01T00:00:00Z"
    )
    write_model(sw_home / installs.INSTALLS, InstallsFile(installs=[old]))
    installs.record(result(tmp_path / "new", "new"), "run", now=NOW)
    assert [r.name for r in installs.load().installs] == ["old", "new"]
