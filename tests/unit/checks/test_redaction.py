import gzip
import os
from pathlib import Path

import pytest

from skipwatch.checks import redaction
from tests.unit.checks.conftest import (
    KEY,
    context_for,
    hardlink_or_skip,
    make_case,
    symlink_or_skip,
    write_jpeg,
)

SECRET_FRAME_LINE = "![Settings panel](assets/frames/f000400.jpg)"


def _plant_key(staging):
    source = staging / "references" / "source.md"
    source.write_text(
        source.read_text(encoding="utf-8") + f"\nThe key shown was {KEY}\n", encoding="utf-8"
    )
    return source


def test_redaction_fails_on_raw_key_in_source_md(tmp_path):
    staging, work = make_case(tmp_path)
    source = _plant_key(staging)
    assert KEY in source.read_text(encoding="utf-8")  # the input is dirty before the check
    r = redaction.run(context_for(staging, work))
    text = source.read_text(encoding="utf-8")
    assert KEY not in text and "<OPENAI_API_KEY>" in text
    assert [i.msg for i in r.items] == [
        "replaced 1 openai with <OPENAI_API_KEY> in references/source.md"
    ]


def test_redaction_fails_on_raw_key_in_skill_md(tmp_path):
    staging, work = make_case(
        tmp_path,
        edit=lambda s: s.replace("OPENAI_API_KEY=<OPENAI_API_KEY>", f"OPENAI_API_KEY={KEY}"),
    )
    redaction.run(context_for(staging, work))
    assert KEY not in (staging / "SKILL.md").read_text(encoding="utf-8")


def test_redaction_removes_frame_that_showed_a_secret(tmp_path):
    staging, work = make_case(
        tmp_path,
        edit=lambda s: s.replace(
            "## Decision points", SECRET_FRAME_LINE + "\n\n## Decision points"
        ),
    )
    frame = staging / "assets" / "frames" / "f000400.jpg"
    write_jpeg(frame)
    r = redaction.run(context_for(staging, work))
    assert not frame.exists()
    assert "f000400" not in (staging / "SKILL.md").read_text(encoding="utf-8")
    assert (staging / "assets" / "frames" / "f000250.jpg").exists()
    assert "removed frame f000400 (showed a secret)" in [i.msg for i in r.items]


def test_redaction_passes(tmp_path):
    staging, work = make_case(tmp_path)
    before = {p: p.read_bytes() for p in staging.rglob("*") if p.is_file()}
    r = redaction.run(context_for(staging, work))
    assert r.ok and r.items == [] and r.check == "redaction"
    assert {p: p.read_bytes() for p in staging.rglob("*") if p.is_file()} == before


def test_redaction_is_ok_even_when_it_replaces(tmp_path):
    staging, work = make_case(tmp_path)
    _plant_key(staging)
    assert redaction.run(context_for(staging, work)).ok


def test_redaction_report_never_contains_value(tmp_path):
    staging, work = make_case(tmp_path)
    _plant_key(staging)
    r = redaction.run(context_for(staging, work))
    assert KEY not in r.model_dump_json()


def test_redaction_check_skips_manifest(tmp_path):
    staging, work = make_case(tmp_path)
    manifest = staging / "skipwatch.json"
    raw = '{"files": {"SKILL.md": "sha256:' + "a3f1" * 16 + '"}, "note": "' + KEY + '"}\n'
    manifest.write_text(raw, encoding="utf-8")
    redaction.run(context_for(staging, work))
    assert manifest.read_text(encoding="utf-8") == raw


def test_redaction_leaves_hashes_in_references(tmp_path):
    staging, work = make_case(tmp_path)
    source = staging / "references" / "source.md"
    text = source.read_text(encoding="utf-8") + "\nsha256:" + "9f2c4e1b" * 8 + "\n"
    source.write_text(text, encoding="utf-8")
    r = redaction.run(context_for(staging, work))
    assert source.read_text(encoding="utf-8") == text and r.items == []


# ---- adversarial review (m1d-review) ----


def test_redaction_never_writes_through_a_symlink(tmp_path):
    staging, work = make_case(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text(f"outside file {KEY}\n", encoding="utf-8")
    symlink_or_skip(staging / "references" / "link.md", outside)
    redaction.run(context_for(staging, work))
    assert outside.read_text(encoding="utf-8") == f"outside file {KEY}\n"
    assert (staging / "references" / "link.md").is_symlink()


def test_redaction_never_follows_a_symlinked_directory(tmp_path):
    staging, work = make_case(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "a.md").write_text(f"k {KEY}\n", encoding="utf-8")
    symlink_or_skip(staging / "references" / "dir", outside, is_dir=True)
    redaction.run(context_for(staging, work))
    assert (outside / "a.md").read_text(encoding="utf-8") == f"k {KEY}\n"


def test_redaction_reencodes_non_utf8_text_and_redacts(tmp_path):
    staging, work = make_case(tmp_path)
    notes = staging / "assets" / "notes.txt"
    notes.write_bytes(b"\xff bad byte then key " + KEY.encode())
    r = redaction.run(context_for(staging, work))
    text = notes.read_bytes().decode("utf-8")  # valid UTF-8 now
    assert KEY not in text and "<OPENAI_API_KEY>" in text and "�" in text
    assert "re-encoded assets/notes.txt" in [i.msg for i in r.items]


def test_redaction_fails_on_secret_in_binary_file(tmp_path):
    staging, work = make_case(tmp_path)
    (staging / "assets" / "shot.png").write_bytes(b"\x89PNG\x00\x01 " + KEY.encode())
    r = redaction.run(context_for(staging, work))
    assert not r.ok
    assert [i.msg for i in r.items] == [
        "assets/shot.png is binary and contains a secret; remove the file"
    ]
    assert KEY not in r.model_dump_json()


def test_redaction_flags_secret_in_file_name(tmp_path):
    staging, work = make_case(tmp_path)
    (staging / "assets" / f"{KEY}.md").write_text("x\n", encoding="utf-8")
    r = redaction.run(context_for(staging, work))
    assert not r.ok
    assert "file name contains a secret: assets/<OPENAI_API_KEY>.md" in [i.msg for i in r.items]
    assert (staging / "assets" / f"{KEY}.md").exists()  # flagged, never renamed
    assert KEY not in r.model_dump_json()


# ---- adversarial round 2 (m1d-r2) ----


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be", "utf-32"])
def test_redaction_reencodes_utf16_and_utf32_and_redacts(tmp_path, encoding):
    staging, work = make_case(tmp_path)
    notes = staging / "references" / "notes.md"
    notes.write_bytes(f"key {KEY}\nline two\n".encode(encoding))
    r = redaction.run(context_for(staging, work))
    text = notes.read_bytes().decode("utf-8")
    assert text == "key <OPENAI_API_KEY>\nline two\n"
    assert any(i.msg.startswith("re-encoded references/notes.md") for i in r.items)
    assert r.ok


def test_redaction_fails_on_unknown_binary_file(tmp_path):
    staging, work = make_case(tmp_path)
    (staging / "assets" / "blob.bin").write_bytes(b"\x00\x01\x02 no key here \x00")
    r = redaction.run(context_for(staging, work))
    assert not r.ok and [i.msg for i in r.items] == [
        "assets/blob.bin is binary; only images and media may be binary in a skill"
    ]


@pytest.mark.parametrize("name", ["k.gz", "k.zip", "k.tgz", "k.tar", "k.7z", "k.bz2", "k.xz"])
def test_redaction_fails_on_archives(tmp_path, name):
    staging, work = make_case(tmp_path)
    (staging / "assets" / name).write_bytes(gzip.compress(KEY.encode()))
    r = redaction.run(context_for(staging, work))
    assert not r.ok and [i.msg for i in r.items] == [
        f"assets/{name}: archives are not allowed in skills"
    ]


def test_redaction_never_writes_through_a_hardlink(tmp_path):
    staging, work = make_case(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text(f"outside {KEY}\n", encoding="utf-8")
    inside = staging / "references" / "hard.md"
    hardlink_or_skip(inside, outside)
    r = redaction.run(context_for(staging, work))
    assert outside.read_text(encoding="utf-8") == f"outside {KEY}\n"
    assert not r.ok and [i.msg for i in r.items] == [
        "references/hard.md is a hardlink; not redacted"
    ]


def test_redaction_writes_atomically_via_replace(tmp_path, monkeypatch):
    staging, work = make_case(tmp_path)
    _plant_key(staging)
    calls = []
    real_replace = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: (calls.append((a, b)), real_replace(a, b)))
    redaction.run(context_for(staging, work))
    assert [Path(b).name for _, b in calls] == ["source.md"]
    assert not list(staging.rglob("*.tmp"))


def test_redaction_fails_on_key_split_over_three_lines(tmp_path):
    staging, work = make_case(tmp_path)
    source = staging / "references" / "source.md"
    source.write_text("use sk-proj-Ab3dEf\n6hIj9kLm2nOp\n5qRs8tUv1wXy4z\n", encoding="utf-8")
    r = redaction.run(context_for(staging, work))
    assert not r.ok and [i.msg for i in r.items] == [
        "references/source.md: a key may be split across lines; join it and run check again"
    ]


# ---- final round (m1d-final) ----


def test_redaction_fails_on_pdf_without_rewriting_it(tmp_path):
    staging, work = make_case(tmp_path)
    pdf = staging / "assets" / "guide.pdf"
    data = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj << /Type /Catalog >> endobj\n"
    pdf.write_bytes(data)
    r = redaction.run(context_for(staging, work))
    assert not r.ok and [i.msg for i in r.items] == [
        "assets/guide.pdf is binary; only images and media may be binary in a skill"
    ]
    assert pdf.read_bytes() == data


def test_redaction_fails_on_non_utf8_unknown_suffix_without_rewriting(tmp_path):
    staging, work = make_case(tmp_path)
    blob = staging / "assets" / "model.weights"
    data = b"\xff\xfe\xfd not text but no NUL bytes"
    blob.write_bytes(data)
    r = redaction.run(context_for(staging, work))
    assert not r.ok and blob.read_bytes() == data


@pytest.mark.parametrize("name", ["notes.txt", "Makefile", "run.sh", "data.csv"])
def test_redaction_reencodes_known_text_types(tmp_path, name):
    staging, work = make_case(tmp_path)
    path = staging / "assets" / name
    path.write_bytes(b"caf\xe9 " + KEY.encode())
    r = redaction.run(context_for(staging, work))
    assert r.ok and KEY not in path.read_bytes().decode("utf-8")


def test_redaction_redacts_valid_utf8_with_unknown_suffix(tmp_path):
    staging, work = make_case(tmp_path)
    path = staging / "assets" / "main.go"
    path.write_text(f'const key = "{KEY}"\n', encoding="utf-8")
    r = redaction.run(context_for(staging, work))
    assert r.ok and KEY not in path.read_text(encoding="utf-8")
