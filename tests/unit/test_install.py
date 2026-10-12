import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skipwatch import install as install_mod
from skipwatch import installs
from skipwatch.cli import app
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.install import install, target_dir
from skipwatch.models import (
    CheckReport,
    Counts,
    IngestBundle,
    InstallResult,
    Manifest,
    ManifestSource,
    PackOrigin,
    Route,
    SourceInfo,
)
from skipwatch.workdir import write_model

NAME = "deploy-astro"


@pytest.fixture
def roots(tmp_path, monkeypatch, sw_home):
    """Fake HOME and cwd so nothing touches the real ~/.claude or the repo."""
    home = tmp_path / "home"
    cwd = tmp_path / "project dir é"
    home.mkdir()
    cwd.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.chdir(cwd)
    return home, cwd


def make_staging(root: Path, name: str = NAME, passed: bool = True, skill: str | None = None):
    """A work folder holding staging/<name>/ and the check-report.json `skipwatch check` writes."""
    work = root / "work" / "run-20261009-120000"
    staging = work / "staging" / name
    (staging / "references").mkdir(parents=True)
    (staging / "SKILL.md").write_text(f"---\nname: {name}\n---\n\nnew body\n", encoding="utf-8")
    (staging / "references" / "source.md").write_text("source\n", encoding="utf-8")
    manifest = Manifest(
        name=name,
        description="Deploys an Astro site.",
        skipwatch_version="0.1.0",
        source=ManifestSource(platform="local"),
        extracted_at="2026-10-09T12:00:00Z",
        counts=Counts(steps=1, spoken=1),
        confidence="medium",
        checks_passed=False,
    )
    write_model(staging / "skipwatch.json", manifest)
    report = CheckReport(skill=skill or name, passed=passed, results=[], counts=Counts())
    write_model(work / "check-report.json", report)
    return staging


def existing_skill(target: Path, body: str = "old body\n") -> None:
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text(body, encoding="utf-8")


def run_cli(*args: str):
    return CliRunner().invoke(app, ["install", *args])


# ---- target_dir ----


def test_install_scopes(tmp_path):
    home, cwd = tmp_path / "h", tmp_path / "c"
    assert target_dir("user", None, NAME, cwd, home) == (home / ".claude/skills" / NAME, "user")
    assert target_dir("project", None, NAME, cwd, home) == (
        cwd / ".claude/skills" / NAME,
        "project",
    )
    assert target_dir("agents", None, NAME, cwd, home) == (
        cwd / ".agents/skills" / NAME,
        "agents",
    )
    assert target_dir(None, tmp_path / "d", NAME, cwd, home) == (tmp_path / "d" / NAME, "dir")


def test_to_wins_over_scope(tmp_path):
    assert target_dir("project", tmp_path / "d", NAME, tmp_path, tmp_path) == (
        tmp_path / "d" / NAME,
        "dir",
    )


def test_install_default_scope_is_user_under_home(roots, tmp_path):
    home, _ = roots
    staging = make_staging(tmp_path)
    result = install(staging, None, None, force=False)
    assert result.scope == "user"
    assert Path(result.path) == home / ".claude" / "skills" / NAME
    assert (
        (home / ".claude/skills" / NAME / "SKILL.md")
        .read_text(encoding="utf-8")
        .endswith("new body\n")
    )


def test_install_default_scope_comes_from_config(roots, tmp_path, sw_home):
    _, cwd = roots
    sw_home.mkdir(parents=True, exist_ok=True)
    (sw_home / "config.toml").write_text('[install]\nscope = "agents"\n', encoding="utf-8")
    result = install(make_staging(tmp_path), None, None, force=False)
    assert result.scope == "agents"
    assert (cwd / ".agents/skills" / NAME / "SKILL.md").exists()


def test_install_cli_project_scope_and_to(roots, tmp_path):
    _, cwd = roots
    staging = make_staging(tmp_path)
    r = run_cli(str(staging), "--scope", "project")
    assert r.exit_code == 0, r.stderr
    assert (cwd / ".claude/skills" / NAME / "SKILL.md").exists()
    dest = tmp_path / "out dir"
    r = run_cli(str(staging), "--scope", "agents", "--to", str(dest))
    assert r.exit_code == 0, r.stderr
    assert (dest / NAME / "SKILL.md").exists()
    assert not (cwd / ".agents").exists()


# ---- R-SK-1: refuse unchecked drafts ----


def test_install_refuses_unchecked_draft(roots, tmp_path):
    home, _ = roots
    staging = make_staging(tmp_path)
    (staging.parent.parent / "check-report.json").unlink()
    r = run_cli(str(staging))
    assert r.exit_code == ExitCode.CHECK_FAILED
    assert "run skipwatch check first" in r.stderr
    assert not (home / ".claude").exists()


@pytest.mark.parametrize("kwargs", [{"passed": False}, {"skill": "other-skill"}])
def test_install_refuses_failed_or_foreign_report(roots, tmp_path, kwargs):
    staging = make_staging(tmp_path, **kwargs)
    with pytest.raises(SkipwatchError) as exc:
        install(staging, None, None, force=False)
    assert exc.value.code == ExitCode.CHECK_FAILED
    assert not (roots[0] / ".claude").exists()


def test_install_refuses_unreadable_report(roots, tmp_path):
    staging = make_staging(tmp_path)
    (staging.parent.parent / "check-report.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SkipwatchError) as exc:
        install(staging, None, None, force=False)
    assert exc.value.code == ExitCode.CHECK_FAILED


def test_install_missing_staging_is_usage_error(roots, tmp_path):
    r = run_cli(str(tmp_path / "nope" / "staging" / NAME))
    assert r.exit_code == ExitCode.USAGE
    assert "not a folder" in r.stderr


# ---- collisions and backups ----


def test_install_exit_6_when_target_exists(roots, tmp_path, sw_home):
    home, _ = roots
    target = home / ".claude/skills" / NAME
    existing_skill(target)
    r = run_cli(str(make_staging(tmp_path)))
    assert r.exit_code == ExitCode.TARGET_EXISTS
    assert "pass --force to replace" in r.stderr
    assert (target / "SKILL.md").read_text(encoding="utf-8") == "old body\n"
    assert sorted(p.name for p in target.iterdir()) == ["SKILL.md"]
    assert not (sw_home / "backups").exists()


def test_r_rev_2_force_backs_up_first(roots, tmp_path, sw_home, monkeypatch):
    home, _ = roots
    target = home / ".claude/skills" / NAME
    existing_skill(target)
    seen = {}

    def spy(src, dst, *args, **kwargs):
        # At copy time the old skill must already sit in the backup, not at the target.
        # copytree recurses through this name, so record only the top-level call.
        seen.setdefault("target_free", not target.exists())
        seen.setdefault("backups", list((sw_home / "backups").iterdir()))
        return real_copytree(src, dst, *args, **kwargs)

    real_copytree = install_mod.shutil.copytree
    monkeypatch.setattr(install_mod.shutil, "copytree", spy)
    result = install(make_staging(tmp_path), None, None, force=True)

    assert seen["target_free"] and len(seen["backups"]) == 1
    backup = Path(result.backup or "")
    assert backup.parent == sw_home / "backups"
    assert backup.name.startswith(f"{NAME}-")
    assert (backup / "SKILL.md").read_text(encoding="utf-8") == "old body\n"
    assert (target / "SKILL.md").read_text(encoding="utf-8").endswith("new body\n")


def test_force_backup_name_has_timestamp_and_never_collides(roots, tmp_path, sw_home):
    home, _ = roots
    target = home / ".claude/skills" / NAME
    now = datetime(2026, 10, 9, 14, 2, 11)
    staging = make_staging(tmp_path)
    existing_skill(target, "first\n")
    first = install(staging, None, None, force=True, now=now)
    second = install(staging, None, None, force=True, now=now)
    assert Path(first.backup or "").name == f"{NAME}-20261009-140211"
    assert second.backup != first.backup
    assert (Path(first.backup or "") / "SKILL.md").read_text(encoding="utf-8") == "first\n"
    assert (Path(second.backup or "") / "SKILL.md").exists()


def test_force_without_existing_target_makes_no_backup(roots, tmp_path, sw_home):
    result = install(make_staging(tmp_path), None, None, force=True)
    assert result.backup is None
    assert not (sw_home / "backups").exists()


def test_failed_copy_restores_previous_skill(roots, tmp_path, sw_home, monkeypatch):
    home, _ = roots
    target = home / ".claude/skills" / NAME
    existing_skill(target)

    def broken(skill_dir, checks_passed):
        raise OSError("disk full")

    monkeypatch.setattr(install_mod, "finalize_manifest", broken)
    with pytest.raises(OSError):
        install(make_staging(tmp_path), None, None, force=True)
    assert (target / "SKILL.md").read_text(encoding="utf-8") == "old body\n"
    assert list((sw_home / "backups").iterdir()) == []


def test_install_never_touches_the_work_folder(roots, tmp_path):
    staging = make_staging(tmp_path)
    work = staging.parent.parent
    before = sorted(str(p.relative_to(work)) for p in work.rglob("*"))
    install(staging, None, None, force=False)
    assert sorted(str(p.relative_to(work)) for p in work.rglob("*")) == before


def test_install_accepts_trailing_dot_staging_path(roots, tmp_path, monkeypatch):
    home, _ = roots
    staging = make_staging(tmp_path)
    monkeypatch.chdir(staging)
    result = install(Path("."), "user", None, force=False)
    assert result.name == NAME
    assert (home / ".claude/skills" / NAME / "SKILL.md").exists()


# ---- R-CLI-2 and R-MAN-1 ----


def test_install_json_validates(roots, tmp_path):
    home, _ = roots
    r = run_cli(str(make_staging(tmp_path)), "--json")
    assert r.exit_code == 0, r.stderr
    result = InstallResult.model_validate_json(r.stdout)
    assert result.name == NAME and result.scope == "user" and result.backup is None
    assert Path(result.path) == home / ".claude/skills" / NAME
    assert json.loads(r.stdout)["schema"] == "skipwatch/install/1"


def test_install_without_json_prints_nothing_on_stdout(roots, tmp_path):
    r = run_cli(str(make_staging(tmp_path)))
    assert r.exit_code == 0 and r.stdout == ""
    assert "Installed" in r.stderr


def test_install_writes_file_hashes(roots, tmp_path):
    home, _ = roots
    install(make_staging(tmp_path), None, None, force=False)
    target = home / ".claude/skills" / NAME
    manifest = Manifest.model_validate_json((target / "skipwatch.json").read_text(encoding="utf-8"))
    expected = hashlib.sha256((target / "SKILL.md").read_bytes()).hexdigest()
    assert manifest.files["SKILL.md"] == f"sha256:{expected}"
    assert "references/source.md" in manifest.files
    assert manifest.checks_passed is True


# ---- review fixes ----


def _touch_after_report(staging: Path, path: Path) -> None:
    """Give path an mtime 10 s after the check report (no reliance on clock resolution)."""
    later = (staging.parent.parent / "check-report.json").stat().st_mtime + 10
    os.utime(path, (later, later))


def test_install_refuses_staging_edited_after_check(roots, tmp_path):
    staging = make_staging(tmp_path)
    (staging / "SKILL.md").write_text("edited after check\n", encoding="utf-8")
    _touch_after_report(staging, staging / "SKILL.md")
    r = run_cli(str(staging))
    assert r.exit_code == ExitCode.CHECK_FAILED
    assert "staging changed since check; run skipwatch check again" in r.stderr
    assert not (roots[0] / ".claude").exists()


def test_install_refuses_file_added_after_check(roots, tmp_path):
    staging = make_staging(tmp_path)
    added = staging / "references" / "extra.md"
    added.write_text("new\n", encoding="utf-8")
    _touch_after_report(staging, added)
    with pytest.raises(SkipwatchError) as exc:
        install(staging, None, None, force=False)
    assert exc.value.code == ExitCode.CHECK_FAILED
    assert "staging changed since check" in exc.value.message


def test_install_relative_to_gives_absolute_path(roots, tmp_path):
    _, cwd = roots
    result = install(make_staging(tmp_path), None, Path("out"), force=False)
    assert Path(result.path).is_absolute()
    assert Path(result.path) == (cwd / "out" / NAME).resolve()
    assert (cwd / "out" / NAME / "SKILL.md").exists()


# ---- install log (M5-M6 issue 10) ----


def _write_ingest(staging: Path, pack: bool) -> None:
    manifest = Manifest.model_validate_json((staging / "skipwatch.json").read_text("utf-8"))
    bundle = IngestBundle(
        source=SourceInfo(kind="video", platform="youtube"),
        route=Route(context="pack"),
        pack=PackOrigin(file="x.skillpack.zip", sha256="sha256:00", manifest=manifest)
        if pack
        else None,
    )
    write_model(staging.parent.parent / "ingest.json", bundle)


def test_install_records_run_and_pack_origin(roots, tmp_path, sw_home):
    _, cwd = roots
    run_staging = make_staging(tmp_path / "run")
    _write_ingest(run_staging, pack=False)
    pack_staging = make_staging(tmp_path / "pack")
    _write_ingest(pack_staging, pack=True)
    first = install(run_staging, None, None, force=False)
    second = install(pack_staging, None, tmp_path / "elsewhere", force=False)
    records = installs.load().installs
    assert [(Path(r.path), r.scope, r.origin) for r in records] == [
        (Path(first.path).resolve(), "user", "run"),
        (Path(second.path).resolve(), "dir", "pack"),
    ]


def test_install_without_ingest_records_run(roots, tmp_path, sw_home):
    install(make_staging(tmp_path), None, None, force=False)
    assert [r.origin for r in installs.load().installs] == ["run"]


def test_install_still_succeeds_when_log_unwritable(roots, tmp_path, monkeypatch):
    home, _ = roots

    def broken(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(installs, "record", broken)
    r = run_cli(str(make_staging(tmp_path)))
    assert r.exit_code == 0, r.stderr
    assert "could not record the install: read-only file system" in r.stderr
    assert (home / ".claude/skills" / NAME / "SKILL.md").exists()
