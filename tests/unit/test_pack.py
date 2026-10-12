import json
import os
import zipfile

import pytest
from typer.testing import CliRunner

from skipwatch import pack as pack_mod
from skipwatch.cli import app
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import PackResult
from skipwatch.pack import pack_skill, skill_tree
from tests.unit._skills import NAME, installed_skill


def test_pack_is_deterministic_and_stored(tmp_path):
    skill = installed_skill(tmp_path)
    a = pack_skill(skill, tmp_path / "a.skillpack.zip")
    os.utime(skill / "SKILL.md", (1, 1))  # mtimes never reach the zip
    b = pack_skill(skill, tmp_path / "b.skillpack.zip")
    assert (tmp_path / "a.skillpack.zip").read_bytes() == (
        tmp_path / "b.skillpack.zip"
    ).read_bytes()
    with zipfile.ZipFile(tmp_path / "a.skillpack.zip") as z:
        names = z.namelist()
        assert names == sorted(names) and all(n.startswith(f"{NAME}/") for n in names)
        assert f"{NAME}/skipwatch.json" in names
        assert not any(n.endswith("/") for n in names)  # no directory entries
        for info in z.infolist():
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.create_system == 3 and info.external_attr == 0o100644 << 16
        manifest_bytes = z.read(f"{NAME}/skipwatch.json")
    assert manifest_bytes == (skill / "skipwatch.json").read_bytes()  # as installed, not rewritten
    assert a.sha256 == b.sha256 and a.sha256.startswith("sha256:") and len(a.sha256) == 71
    assert a.files == 5 and a.bytes == (tmp_path / "a.skillpack.zip").stat().st_size
    assert not (tmp_path / "a.skillpack.zip.tmp").exists()


def test_pack_defaults_to_name_in_cwd(tmp_path, monkeypatch):
    skill = installed_skill(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = pack_skill(skill, None)
    assert result.path == str(tmp_path / f"{NAME}.skillpack.zip")
    assert (tmp_path / f"{NAME}.skillpack.zip").is_file()


def test_pack_refuses_cookie_skill_exit_4(tmp_path):
    skill = installed_skill(tmp_path, fetched_with_cookies=True)
    with pytest.raises(SkipwatchError) as err:
        pack_skill(skill, tmp_path / "a.skillpack.zip")
    assert err.value.code == ExitCode.PRIVATE_CONTENT
    assert "cannot be packed" in err.value.message
    assert not (tmp_path / "a.skillpack.zip").exists()


def test_pack_refuses_failed_checks_exit_1(tmp_path):
    skill = installed_skill(tmp_path, checks_passed=False)
    with pytest.raises(SkipwatchError) as err:
        pack_skill(skill, tmp_path / "a.skillpack.zip")
    assert err.value.code == ExitCode.CHECK_FAILED


def test_pack_refuses_missing_or_invalid_manifest_exit_9(tmp_path):
    skill = installed_skill(tmp_path)
    (skill / "skipwatch.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SkipwatchError) as err:
        pack_skill(skill, tmp_path / "a.skillpack.zip")
    assert err.value.code == ExitCode.PACK_INTEGRITY and "reinstall" in err.value.message
    (skill / "skipwatch.json").unlink()
    with pytest.raises(SkipwatchError) as err:
        pack_skill(skill, tmp_path / "a.skillpack.zip")
    assert err.value.code == ExitCode.PACK_INTEGRITY


def test_pack_refuses_a_bad_name_exit_9(tmp_path):
    skill = installed_skill(tmp_path, name="Run_X")
    with pytest.raises(SkipwatchError) as err:
        pack_skill(skill, tmp_path / "a.skillpack.zip")
    assert err.value.code == ExitCode.PACK_INTEGRITY and "Run_X" in err.value.message


def test_pack_ignores_finder_junk_and_refuses_edited_files(tmp_path):
    skill = installed_skill(tmp_path)
    (skill / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
    (skill / "references" / "Thumbs.db").write_bytes(b"junk")
    result = pack_skill(skill, tmp_path / "a.skillpack.zip")
    assert result.ignored == [".DS_Store", "references/Thumbs.db"]
    with zipfile.ZipFile(tmp_path / "a.skillpack.zip") as z:
        assert not any("DS_Store" in n or "Thumbs" in n for n in z.namelist())
    (skill / "SKILL.md").write_text("edited\n", encoding="utf-8")
    with pytest.raises(SkipwatchError) as err:
        pack_skill(skill, tmp_path / "b.skillpack.zip")
    assert err.value.code == ExitCode.PACK_INTEGRITY
    assert "SKILL.md: hash mismatch" in err.value.message


def test_pack_names_extra_and_missing_files(tmp_path):
    skill = installed_skill(tmp_path)
    (skill / "references" / "source.md").unlink()
    (skill / "notes.txt").write_text("added\n", encoding="utf-8")
    with pytest.raises(SkipwatchError) as err:
        pack_skill(skill, tmp_path / "a.skillpack.zip")
    assert "notes.txt: not in manifest" in err.value.message
    assert "references/source.md: missing" in err.value.message


def test_pack_refuses_symlink_exit_9(tmp_path):
    skill = installed_skill(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("private\n", encoding="utf-8")
    try:
        (skill / "references" / "link.md").symlink_to(secret)
    except OSError:
        pytest.skip("symlinks need privileges on this platform")
    with pytest.raises(SkipwatchError) as err:
        skill_tree(skill)
    assert err.value.code == ExitCode.PACK_INTEGRITY and "references/link.md" in err.value.message
    with pytest.raises(SkipwatchError) as err:
        pack_skill(skill, tmp_path / "a.skillpack.zip")
    assert err.value.code == ExitCode.PACK_INTEGRITY


def test_pack_refuses_a_symlinked_folder_exit_9(tmp_path):
    skill = installed_skill(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.md").write_text("x\n", encoding="utf-8")
    try:
        (skill / "more").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks need privileges on this platform")
    with pytest.raises(SkipwatchError) as err:
        skill_tree(skill)
    assert err.value.code == ExitCode.PACK_INTEGRITY and "more" in err.value.message


def test_pack_refuses_what_unpack_would_refuse(tmp_path, monkeypatch):
    skill = installed_skill(tmp_path)
    monkeypatch.setattr(pack_mod, "MAX_FILES", 4)  # five entries with skipwatch.json
    with pytest.raises(SkipwatchError) as err:
        pack_skill(skill, tmp_path / "a.skillpack.zip")
    assert err.value.code == ExitCode.PACK_INTEGRITY and "files" in err.value.message
    monkeypatch.setattr(pack_mod, "MAX_FILES", 200)
    monkeypatch.setattr(pack_mod, "MAX_FILE_BYTES", 100)  # SKILL.md is bigger
    with pytest.raises(SkipwatchError) as err:
        pack_skill(skill, tmp_path / "a.skillpack.zip")
    assert err.value.message.startswith("SKILL.md: over the") and "file limit" in err.value.message
    monkeypatch.setattr(pack_mod, "MAX_FILE_BYTES", 10 * 1024 * 1024)
    monkeypatch.setattr(pack_mod, "MAX_TOTAL_BYTES", 300)
    with pytest.raises(SkipwatchError) as err:
        pack_skill(skill, tmp_path / "a.skillpack.zip")
    assert "total" in err.value.message
    assert not (tmp_path / "a.skillpack.zip").exists()


def test_pack_cli_json_validates(tmp_path):
    skill = installed_skill(tmp_path)
    out = tmp_path / "out.skillpack.zip"
    result = CliRunner().invoke(app, ["pack", str(skill), "-o", str(out), "--json"])
    assert result.exit_code == 0, result.output
    parsed = PackResult.model_validate(json.loads(result.stdout))
    assert parsed.name == NAME and parsed.path == str(out) and out.is_file()
    assert f"Packed {NAME}: 5 files" in result.stderr
    assert f"sha256 {parsed.sha256[7:19]}" in result.stderr


def test_pack_cli_refusal_exit_codes(tmp_path):
    skill = installed_skill(tmp_path, fetched_with_cookies=True)
    result = CliRunner().invoke(app, ["pack", str(skill), "-o", str(tmp_path / "o.skillpack.zip")])
    assert result.exit_code == ExitCode.PRIVATE_CONTENT
    empty = tmp_path / "empty"
    empty.mkdir()
    result = CliRunner().invoke(app, ["pack", str(empty)])
    assert result.exit_code == ExitCode.UNSUPPORTED_SOURCE


def test_pack_cli_resolves_an_installed_name(tmp_path, monkeypatch):
    pytest.importorskip("skipwatch.listing")
    home = tmp_path / "home"
    skill = installed_skill(home / ".claude")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.chdir(tmp_path)
    assert skill.parent == home / ".claude" / "skills"
    result = CliRunner().invoke(app, ["pack", NAME, "--json"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / f"{NAME}.skillpack.zip").is_file()
