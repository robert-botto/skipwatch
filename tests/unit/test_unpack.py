import json
import os
import shutil
import sys
import warnings
import zipfile
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from skipwatch import pack as pack_mod
from skipwatch.checks.runner import run_all
from skipwatch.cli import app
from skipwatch.commands import unpack as unpack_cmd
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.install import install
from skipwatch.manifest import pack_refusal
from skipwatch.models import IngestBundle, Manifest, Transcript, UnpackResult
from skipwatch.pack import pack_skill, read_pack, transcript_from_markdown, unpack
from skipwatch.workdir import write_model
from tests.unit._skills import NAME, installed_skill

NOW = datetime(2026, 10, 11, 9, 30, 0)


def make_zip(path: Path, entries: list[tuple[zipfile.ZipInfo | str, bytes]], deflate=False) -> Path:
    """A zip holding exactly these entries, names written as given (never sanitised)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # duplicate names are the point of some tests
        with zipfile.ZipFile(path, "w") as z:
            for entry, data in entries:
                if isinstance(entry, str):
                    info = zipfile.ZipInfo(entry, date_time=pack_mod.ZIP_DATE)
                    info.filename = info.orig_filename = entry  # keep "\\" on Windows too
                    info.external_attr = 0o100644 << 16
                    info.compress_type = zipfile.ZIP_DEFLATED if deflate else zipfile.ZIP_STORED
                else:
                    info = entry
                z.writestr(info, data)
    return path


def set_encrypted(path: Path, name: str) -> Path:
    """Set the encryption flag on one entry's local and central headers (zipfile cannot)."""
    data = bytearray(path.read_bytes())
    target = name.encode()
    for signature, flag_at, len_at, name_at in (
        (b"PK\x03\x04", 6, 26, 30),
        (b"PK\x01\x02", 8, 28, 46),
    ):
        pos = data.find(signature)
        while pos != -1:
            size = int.from_bytes(data[pos + len_at : pos + len_at + 2], "little")
            if bytes(data[pos + name_at : pos + name_at + size]) == target:
                data[pos + flag_at] |= 0x1
            pos = data.find(signature, pos + 4)
    path.write_bytes(bytes(data))
    return path


def good_pack(tmp_path: Path) -> Path:
    skill = installed_skill(tmp_path / "author")
    return Path(pack_skill(skill, tmp_path / f"{NAME}.skillpack.zip").path)


def entries_of(pack: Path) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(pack) as z:
        return [(name, z.read(name)) for name in z.namelist()]


def manifest_of(pack: Path) -> Manifest:
    return Manifest.model_validate_json(dict(entries_of(pack))[f"{NAME}/skipwatch.json"])


def with_manifest(entries: list[tuple[str, bytes]], manifest: Manifest) -> list[tuple[str, bytes]]:
    data = manifest.model_dump_json(by_alias=True, indent=2).encode()
    return [(n, data if n == f"{NAME}/skipwatch.json" else d) for n, d in entries]


def refused(pack: Path, home: Path) -> SkipwatchError:
    with pytest.raises(SkipwatchError) as err:
        unpack(pack, None, now=NOW)
    assert err.value.code == ExitCode.PACK_INTEGRITY, err.value.message
    assert not (home / "packs").exists()  # nothing written anywhere
    return err.value


@pytest.mark.parametrize(
    "name",
    [
        "../evil/SKILL.md",
        "/abs/SKILL.md",
        "run-x\\SKILL.md",
        "C:run-x/SKILL.md",
        "run-x/../SKILL.md",
        "run-x/./SKILL.md",
        "run-x//SKILL.md",
        "run-x/reférences.md",  # not NFC
        "run-x/a\x00.md",
        "run-x/CON.md",  # Windows device names, characters and endings
        "run-x/references/lpt1",
        "run-x/what?.md",
        "run-x/a<b>.md",
        "run-x/trailing.",
        "run-x/trailing ",
        "run-x/CON .md",  # Windows ignores spaces before the dot
        "run-x/conin$",
        "run-x/CONOUT$.txt",
        "run-x/COM\u00b9.md",  # superscript digits are device names too
        "run-x/lpt\u00b2",
        "run-x/references/LPT\u00b3.txt",
    ],
)
def test_unpack_rejects_unsafe_entries(tmp_path, sw_home, name):
    entries = [*entries_of(good_pack(tmp_path)), (name, b"evil\n")]
    err = refused(make_zip(tmp_path / "evil.skillpack.zip", entries), sw_home)
    assert err.message.startswith("pack integrity: ")
    assert "not in manifest" not in err.message  # refused for its name, before any hash


def test_unpack_rejects_symlink_dir_encrypted_and_two_tops(tmp_path, sw_home):
    good = entries_of(good_pack(tmp_path))
    link = zipfile.ZipInfo(f"{NAME}/references/link.md", date_time=pack_mod.ZIP_DATE)
    link.external_attr = 0o120777 << 16
    err = refused(make_zip(tmp_path / "a.zip", [*good, (link, b"/etc/passwd")]), sw_home)
    assert "references/link.md" in err.message and "not a regular file" in err.message

    folder = zipfile.ZipInfo(f"{NAME}/extra/", date_time=pack_mod.ZIP_DATE)
    err = refused(make_zip(tmp_path / "b.zip", [*good, (folder, b"")]), sw_home)
    assert "directory entry" in err.message

    secret = make_zip(tmp_path / "c.zip", [*good, (f"{NAME}/secret.md", b"xx")])
    err = refused(set_encrypted(secret, f"{NAME}/secret.md"), sw_home)
    assert "encrypted" in err.message

    err = refused(make_zip(tmp_path / "d.zip", [*good, ("other/x.md", b"x")]), sw_home)
    assert "one top folder" in err.message

    bad_top = [(n.replace(f"{NAME}/", "Run_X/"), d) for n, d in good]
    err = refused(make_zip(tmp_path / "e.zip", bad_top), sw_home)
    assert "Run_X" in err.message

    bzip = zipfile.ZipInfo(f"{NAME}/z.md", date_time=pack_mod.ZIP_DATE)
    bzip.compress_type = zipfile.ZIP_BZIP2
    err = refused(make_zip(tmp_path / "f.zip", [*good, (bzip, b"z" * 50)]), sw_home)
    assert "compression" in err.message


def test_unpack_rejects_duplicate_and_casefold_collisions(tmp_path, sw_home):
    good = entries_of(good_pack(tmp_path))
    err = refused(make_zip(tmp_path / "a.zip", [*good, (f"{NAME}/SKILL.md", b"x")]), sw_home)
    assert "duplicate" in err.message and "SKILL.md" in err.message
    err = refused(make_zip(tmp_path / "b.zip", [*good, (f"{NAME}/skill.md", b"x")]), sw_home)
    assert "duplicate" in err.message and "skill.md" in err.message


@pytest.mark.parametrize("file_first", [True, False])
@pytest.mark.parametrize("clash", ["references", "REFERENCES", "assets/frames"])
def test_unpack_rejects_a_file_and_folder_with_one_name(tmp_path, sw_home, file_first, clash):
    good = entries_of(good_pack(tmp_path))
    extra = (f"{NAME}/{clash}", b"a file where a folder goes")
    entries = [extra, *good] if file_first else [*good, extra]
    err = refused(make_zip(tmp_path / "a.zip", entries), sw_home)
    assert err.message == f"pack integrity: {clash}: a file and a folder share this name"


def test_unpack_extra_missing_or_changed_file_is_9(tmp_path, sw_home):
    good = entries_of(good_pack(tmp_path))
    err = refused(make_zip(tmp_path / "a.zip", [*good, (f"{NAME}/extra.md", b"x")]), sw_home)
    assert err.message == "pack integrity: extra.md: not in manifest"

    missing = [(n, d) for n, d in good if not n.endswith("references/source.md")]
    err = refused(make_zip(tmp_path / "b.zip", missing), sw_home)
    assert err.message == "pack integrity: references/source.md: missing"

    changed = [(n, d + b" " if n.endswith("SKILL.md") else d) for n, d in good]
    err = refused(make_zip(tmp_path / "c.zip", changed), sw_home)
    assert err.message == "pack integrity: SKILL.md: hash mismatch"

    no_manifest = [(n, d) for n, d in good if not n.endswith("skipwatch.json")]
    err = refused(make_zip(tmp_path / "d.zip", no_manifest), sw_home)
    assert "skipwatch.json" in err.message

    broken = [(n, b"{}" if n.endswith("skipwatch.json") else d) for n, d in good]
    err = refused(make_zip(tmp_path / "e.zip", broken), sw_home)
    assert "skipwatch.json" in err.message


def test_unpack_manifest_name_must_match_folder(tmp_path, sw_home):
    pack = good_pack(tmp_path)
    renamed = with_manifest(
        entries_of(pack), manifest_of(pack).model_copy(update={"name": "run-y"})
    )
    err = refused(make_zip(tmp_path / "a.zip", renamed), sw_home)
    assert "run-y" in err.message and NAME in err.message


def test_unpack_size_limits(tmp_path, sw_home, monkeypatch):
    pack = good_pack(tmp_path)
    huge = tmp_path / "huge.skillpack.zip"
    with huge.open("wb") as f:
        f.truncate(30 * 1024 * 1024)  # sparse: refused on size before any byte is read
    assert "26 MiB" in refused(huge, sw_home).message

    bomb = make_zip(tmp_path / "bomb.zip", [(f"{NAME}/SKILL.md", b"\0" * 200_000)], deflate=True)
    assert "compression ratio" in refused(bomb, sw_home).message

    not_zip = tmp_path / "not.skillpack.zip"
    not_zip.write_bytes(b"PK\x03\x04 but not really a zip")
    assert "not a zip" in refused(not_zip, sw_home).message

    for limit, value, words in [
        ("MAX_PACK_BYTES", 1000, "pack is over"),
        ("MAX_FILES", 3, "more than 3 files"),
        ("MAX_FILE_BYTES", 100, "file limit"),
        ("MAX_TOTAL_BYTES", 1000, "total limit"),
    ]:
        with monkeypatch.context() as m:
            m.setattr(pack_mod, limit, value)
            assert words in refused(pack, sw_home).message


def test_unpack_cookie_claim_is_exit_4(tmp_path, sw_home):
    pack = good_pack(tmp_path)
    cookie = with_manifest(
        entries_of(pack), manifest_of(pack).model_copy(update={"fetched_with_cookies": True})
    )
    with pytest.raises(SkipwatchError) as err:
        unpack(make_zip(tmp_path / "a.zip", cookie), None, now=NOW)
    assert err.value.code == ExitCode.PRIVATE_CONTENT
    assert not (sw_home / "packs").exists()


def test_read_pack_returns_files_without_manifest(tmp_path):
    name, files, manifest = read_pack(good_pack(tmp_path))
    assert name == NAME and manifest.name == NAME
    assert sorted(files) == sorted(manifest.files)
    assert files["SKILL.md"] == (tmp_path / "author" / "skills" / NAME / "SKILL.md").read_bytes()


def test_unpack_lays_out_pack_work_folder(tmp_path, sw_home):
    pack = good_pack(tmp_path)
    source = tmp_path / "author" / "skills" / NAME
    result = unpack(pack, None, now=NOW)
    work = Path(result.work)
    assert work == sw_home / "packs" / f"{NAME}-20261011-093000"
    staging = Path(result.staging)
    assert staging == work / "staging" / NAME
    for path in source.rglob("*"):
        if path.is_file():
            rel = path.relative_to(source)
            assert (staging / rel).read_bytes() == path.read_bytes(), rel
    assert sorted(p.relative_to(staging) for p in staging.rglob("*") if p.is_file()) == sorted(
        p.relative_to(source) for p in source.rglob("*") if p.is_file()
    )
    ingest = IngestBundle.model_validate_json((work / "ingest.json").read_bytes())
    assert ingest.route.context == "pack" and ingest.fetched_with_cookies is False
    assert ingest.pack is not None and ingest.pack.sha256 == result.pack_sha256
    assert ingest.pack.file == pack.name and ingest.pack.manifest == manifest_of(pack)
    assert ingest.source.kind == "video" and ingest.source.platform == "youtube"
    assert ingest.source.url == "https://youtu.be/x" and ingest.source.title == "Run x"
    transcript = Transcript.model_validate_json((work / "transcript.json").read_bytes())
    assert transcript.origin == "pack" and transcript.segments[0].text == "initialise the project"
    assert (work / "stages.json").is_file()
    assert result.transcript is True and result.files == 5
    assert result.claimed_confidence == "high" and result.claimed_critic_score == 8.5
    assert result.pack_sha256 == pack_skill(source, tmp_path / "again.zip").sha256

    second = unpack(pack, None, now=NOW, fetched_from="https://example.com/run-x.skillpack.zip")
    assert Path(second.work) == sw_home / "packs" / f"{NAME}-20261011-093000-1"
    assert second.fetched_from == "https://example.com/run-x.skillpack.zip"
    ingest = IngestBundle.model_validate_json((Path(second.work) / "ingest.json").read_bytes())
    assert ingest.pack is not None and ingest.pack.file == second.fetched_from


def test_unpack_records_the_url_without_query_or_fragment(tmp_path, sw_home):
    url = "https://example.com/x/run-x.skillpack.zip"
    result = unpack(good_pack(tmp_path), None, now=NOW, fetched_from=url + "?token=s3cret#part")
    assert result.fetched_from == url
    ingest = IngestBundle.model_validate_json((Path(result.work) / "ingest.json").read_bytes())
    assert ingest.pack is not None and ingest.pack.file == url
    assert "s3cret" not in (Path(result.work) / "ingest.json").read_text(encoding="utf-8")


def test_unpack_without_transcript_and_local_source(tmp_path, sw_home):
    skill = installed_skill(tmp_path / "author")
    (skill / "references" / "transcript.md").unlink()
    manifest = Manifest.model_validate_json((skill / "skipwatch.json").read_bytes())
    files = {k: v for k, v in manifest.files.items() if k != "references/transcript.md"}
    source = manifest.source.model_copy(update={"platform": "local", "url": None})
    write_model(
        skill / "skipwatch.json", manifest.model_copy(update={"files": files, "source": source})
    )
    pack = Path(pack_skill(skill, tmp_path / "p.skillpack.zip").path)
    result = unpack(pack, None, now=NOW)
    assert result.transcript is False and not (Path(result.work) / "transcript.json").exists()
    ingest = IngestBundle.model_validate_json((Path(result.work) / "ingest.json").read_bytes())
    assert ingest.source.kind == "file" and ingest.source.platform == "local"


def test_unpack_work_must_be_a_new_folder_directly_under_packs(tmp_path, sw_home):
    pack = good_pack(tmp_path)
    packs = sw_home / "packs"
    elsewhere = tmp_path / "elsewhere"
    nested = packs / "a" / "b"
    taken = packs / "taken"
    taken.mkdir(parents=True)
    for work in (elsewhere, nested, taken, packs, packs / "x" / ".."):
        with pytest.raises(SkipwatchError) as err:
            unpack(pack, work, now=NOW)
        assert err.value.code == ExitCode.USAGE, work
        assert "--work must be a new folder directly under $SKIPWATCH_HOME/packs/" in (
            err.value.message
        )
    assert not elsewhere.exists() and not nested.exists() and list(taken.iterdir()) == []
    result = unpack(pack, packs / "mine", now=NOW)
    assert Path(result.work) == (packs / "mine").resolve()
    assert Path(result.work).parent == packs.resolve()


@pytest.mark.parametrize("breaks", ["write_model", "transcript_from_markdown"])
def test_unpack_failure_leaves_no_work_folder(tmp_path, sw_home, monkeypatch, breaks):
    pack = good_pack(tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(pack_mod, breaks, boom)
    with pytest.raises(RuntimeError):
        unpack(pack, None, now=NOW)
    assert list((sw_home / "packs").iterdir()) == []
    with pytest.raises(RuntimeError):
        unpack(pack, sw_home / "packs" / "mine", now=NOW)
    assert not (sw_home / "packs" / "mine").exists()


@pytest.mark.skipif(
    sys.platform == "win32" or getattr(os, "geteuid", lambda: 1)() == 0,
    reason="chmod does not make a folder read-only here",
)
def test_unpack_read_only_packs_folder_is_a_clean_exit_7(tmp_path, sw_home):
    pack = good_pack(tmp_path)
    packs = sw_home / "packs"
    packs.mkdir(parents=True)
    packs.chmod(0o555)
    try:
        for work in (None, packs / "mine"):
            with pytest.raises(SkipwatchError) as err:
                unpack(pack, work, now=NOW)
            assert err.value.code == ExitCode.NO_CONTENT
            assert err.value.message.startswith("cannot write the pack work folder ")
            assert str(packs.resolve()) in err.value.message
        result = CliRunner().invoke(app, ["unpack", str(pack)])
        assert result.exit_code == ExitCode.NO_CONTENT and "Traceback" not in result.output
        assert "cannot write the pack work folder" in result.stderr
    finally:
        packs.chmod(0o755)
    assert list(packs.iterdir()) == []


def test_unpack_write_error_is_exit_7_and_cleans_up(tmp_path, sw_home, monkeypatch):
    pack = good_pack(tmp_path)

    def full(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(pack_mod, "write_model", full)
    with pytest.raises(SkipwatchError) as err:
        unpack(pack, None, now=NOW)
    assert err.value.code == ExitCode.NO_CONTENT
    folder = (sw_home / "packs").resolve() / f"{NAME}-20261011-093000"
    assert (
        err.value.message == f"cannot write the pack work folder {folder}: No space left on device"
    )
    assert list((sw_home / "packs").iterdir()) == []


def test_transcript_from_markdown_parses_and_rejects():
    got = transcript_from_markdown(
        "# Transcript\n\n[00:05] first line\n[01:10] second\nnot a line\n[1:02:03] third\n"
    )
    assert got is not None and got.origin == "pack"
    assert [(s.start, s.end, s.text) for s in got.segments] == [
        (5.0, 70.0, "first line"),
        (70.0, 3723.0, "second"),
        (3723.0, 3738.0, "third"),
    ]
    assert transcript_from_markdown("# Transcript\n\nno timestamps here\n[00:61] bad\n") is None
    assert transcript_from_markdown("") is None


def test_unpack_cli_exit_codes(tmp_path, sw_home, monkeypatch):
    runner = CliRunner()
    not_zip = tmp_path / "bad.skillpack.zip"
    not_zip.write_bytes(b"nope")
    assert runner.invoke(app, ["unpack", str(not_zip)]).exit_code == ExitCode.PACK_INTEGRITY
    result = runner.invoke(app, ["unpack", "http://example.com/a.skillpack.zip"])
    assert result.exit_code == ExitCode.UNSUPPORTED_SOURCE and "https" in result.stderr
    missing = runner.invoke(app, ["unpack", str(tmp_path / "missing.skillpack.zip")])
    assert missing.exit_code == ExitCode.UNSUPPORTED_SOURCE
    pack = good_pack(tmp_path)
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "x").write_text("x", encoding="utf-8")
    result = runner.invoke(app, ["unpack", str(pack), "--work", str(busy)])
    assert result.exit_code == ExitCode.USAGE
    result = runner.invoke(app, ["unpack", str(pack), "--json"])
    assert result.exit_code == 0, result.output
    parsed = UnpackResult.model_validate(json.loads(result.stdout))
    assert f"Pack verified: {NAME}, 5 files, sha256 {parsed.pack_sha256[7:19]}" in result.stderr
    assert f"Unpacked to {parsed.staging}" in result.stderr


def test_unpack_cli_https_fetches_into_a_temp_folder(tmp_path, sw_home, monkeypatch):
    pack = good_pack(tmp_path)
    seen: dict[str, Path] = {}

    def fetch(url: str, dest_dir: Path) -> Path:
        seen["dir"] = dest_dir
        target = dest_dir / "run-x.skillpack.zip"
        target.write_bytes(pack.read_bytes())
        return target

    monkeypatch.setattr(unpack_cmd, "fetch_pack", fetch)
    url = "https://example.com/run-x.skillpack.zip"
    result = CliRunner().invoke(app, ["unpack", url, "--json"])
    assert result.exit_code == 0, result.output
    parsed = UnpackResult.model_validate(json.loads(result.stdout))
    assert parsed.fetched_from == url
    assert not seen["dir"].exists()  # the download is deleted afterwards


def test_run_install_pack_unpack_check_round_trip(tmp_path, sw_home):
    """A skill that passed check as a run, installed, packed and unpacked, passes check again
    under M5-B's pack guard, and its skipwatch.json comes back byte-identical."""
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "skills"
    skill_name = "run-skipdemo-tutorial"
    work = tmp_path / "work"
    shutil.copytree(fixtures / "work", work)
    staging = work / "staging" / skill_name
    shutil.copytree(fixtures / "good" / skill_name, staging)
    frame = staging / "assets" / "frames" / "f000250.jpg"
    frame.parent.mkdir(parents=True)
    Image.new("RGB", (960, 540), (30, 30, 30)).save(frame, "JPEG")
    assert run_all(staging, work).passed
    installed = install(staging, None, tmp_path / "skills", False)
    packed = pack_skill(Path(installed.path), tmp_path / "p.skillpack.zip")

    result = unpack(Path(packed.path), None, now=NOW)
    unpacked = Path(result.staging)
    report = run_all(unpacked, Path(result.work))
    assert report.passed, [(r.check, [i.msg for i in r.items]) for r in report.results]
    ingest = IngestBundle.model_validate_json((Path(result.work) / "ingest.json").read_bytes())
    assert ingest.pack is not None
    assert pack_refusal(unpacked, Path(result.work), ingest.pack) is None  # pack mode honoured
    repacked = install(unpacked, None, tmp_path / "again", False)
    again = Path(repacked.path) / "skipwatch.json"
    assert again.read_bytes() == (Path(installed.path) / "skipwatch.json").read_bytes()
