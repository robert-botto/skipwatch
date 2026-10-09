import os

import pytest

from skipwatch.checks import structure
from tests.unit.checks.conftest import (
    context_for,
    hardlink_or_skip,
    make_case,
    symlink_or_skip,
    write_jpeg,
    write_manifest,
)

ATTRIBUTION = (
    "## Attribution\n\nDistilled from the local recording tutorial-60s, "
    "with SkipWatch. The workflow and wording are the creator's.\n"
)


def _case(tmp_path, edit=None):
    staging, work = make_case(tmp_path, edit=edit)
    write_manifest(staging, work)
    return staging, work


def _msgs(result):
    return [i.msg for i in result.items]


def test_structure_fails_on_missing_attribution(tmp_path):
    staging, work = _case(tmp_path, lambda s: s.replace(ATTRIBUTION, ""))
    r = structure.run(context_for(staging, work))
    assert not r.ok and any("Attribution" in m for m in _msgs(r))


def test_structure_fails_on_attribution_without_creator_line(tmp_path):
    staging, work = _case(
        tmp_path, lambda s: s.replace("The workflow and wording are the creator's.", "")
    )
    r = structure.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == [
        'Attribution must say "The workflow and wording are the creator\'s"'
    ]


def test_structure_fails_on_sections_out_of_order(tmp_path):
    staging, work = _case(
        tmp_path,
        lambda s: (
            s.replace("## Decision points", "## TMP")
            .replace("## Gotchas", "## Decision points")
            .replace("## TMP", "## Gotchas")
        ),
    )
    r = structure.run(context_for(staging, work))
    assert not r.ok and any("sections out of order" in m for m in _msgs(r))


def test_structure_fails_on_missing_h1(tmp_path):
    staging, work = _case(tmp_path, lambda s: s.replace("# Run the skipdemo tutorial\n", ""))
    r = structure.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == ["missing H1 title"]


def test_structure_fails_on_501_lines(tmp_path):
    staging, work = _case(tmp_path, lambda s: s + "filler line\n" * (501 - len(s.splitlines())))
    r = structure.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == ["SKILL.md has 501 lines; it must stay under 500"]


def test_structure_fails_on_missing_referenced_file(tmp_path):
    staging, work = _case(tmp_path)
    (staging / "assets/frames/f000250.jpg").unlink()
    r = structure.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == ["referenced file missing: assets/frames/f000250.jpg"]


def test_structure_fails_on_missing_backticked_reference(tmp_path):
    staging, work = _case(
        tmp_path,
        lambda s: s.replace("None mentioned.", "See `references/gotchas.md`."),
    )
    r = structure.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == ["referenced file missing: references/gotchas.md"]


def test_structure_fails_on_invalid_manifest(tmp_path):
    staging, work = _case(tmp_path)
    (staging / "skipwatch.json").write_text("{}", encoding="utf-8")
    r = structure.run(context_for(staging, work))
    assert not r.ok and any("skipwatch.json is not valid" in m for m in _msgs(r))


def test_structure_fails_on_missing_manifest(tmp_path):
    staging, work = make_case(tmp_path)
    r = structure.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == ["skipwatch.json is missing"]


def test_structure_fails_on_nine_frames(tmp_path):
    staging, work = _case(tmp_path)
    for i in range(8):
        write_jpeg(staging / f"assets/frames/f00020{i}.jpg")
    r = structure.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == ["9 frames in assets/frames; the cap is 8"]


def test_structure_passes(tmp_path):
    staging, work = _case(tmp_path)
    r = structure.run(context_for(staging, work))
    assert r.ok and r.items == [] and r.check == "structure"


def test_structure_passes_at_499_lines_and_eight_frames(tmp_path):
    staging, work = _case(tmp_path, lambda s: s + "filler line\n" * (499 - len(s.splitlines())))
    for i in range(7):
        write_jpeg(staging / f"assets/frames/f00020{i}.jpg")
    r = structure.run(context_for(staging, work))
    assert r.ok, _msgs(r)


def test_structure_ignores_external_links_and_anchors(tmp_path):
    staging, work = _case(
        tmp_path,
        lambda s: s.replace(
            "None mentioned.", "See [docs](https://example.com/x) and [above](#procedure)."
        ),
    )
    r = structure.run(context_for(staging, work))
    assert r.ok, _msgs(r)


# ---- adversarial review (m1d-review) ----

ATTR = "## Attribution"


def _with_line(line):
    return lambda s: s.replace(ATTR, line + "\n\n" + ATTR, 1)


def test_structure_fails_on_symlinked_file(tmp_path):
    staging, work = _case(tmp_path)
    symlink_or_skip(staging / "references" / "hosts.md", tmp_path / "work" / "ingest.json")
    r = structure.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == ["symlink not allowed in a skill: references/hosts.md"]


def test_structure_fails_on_symlinked_directory(tmp_path):
    staging, work = _case(tmp_path)
    symlink_or_skip(staging / "references" / "etc", tmp_path, is_dir=True)
    r = structure.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == ["symlink not allowed in a skill: references/etc"]


def test_structure_fails_on_parent_traversal_link(tmp_path):
    staging, work = _case(tmp_path, _with_line("See [x](../../ingest.json)."))
    r = structure.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == ["reference escapes the skill folder: ../../ingest.json"]


def test_structure_fails_on_absolute_path_link(tmp_path):
    staging, work = _case(tmp_path, _with_line("See [x](/etc/passwd)."))
    r = structure.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == ["reference escapes the skill folder: /etc/passwd"]


def test_structure_fails_on_file_url(tmp_path):
    staging, work = _case(tmp_path, _with_line("See [x](file:///etc/passwd)."))
    r = structure.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == ["reference escapes the skill folder: file:///etc/passwd"]


def test_structure_fails_on_backtick_traversal(tmp_path):
    staging, work = _case(tmp_path, _with_line("Run `scripts/../../../../etc/hosts`."))
    r = structure.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == [
        "reference escapes the skill folder: scripts/../../../../etc/hosts"
    ]


# ---- adversarial round 2 (m1d-r2) ----


def test_structure_fails_on_hardlinked_file(tmp_path):
    staging, work = _case(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("x\n", encoding="utf-8")
    hardlink_or_skip(staging / "references" / "hard.md", outside)
    r = structure.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == ["hardlink not allowed in a skill: references/hard.md"]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs on this OS")
def test_structure_fails_on_fifo(tmp_path):
    staging, work = _case(tmp_path)
    os.mkfifo(staging / "references" / "pipe.md")
    r = structure.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == ["special file not allowed in a skill: references/pipe.md"]


@pytest.mark.parametrize(
    ("line", "target"),
    [
        ("See [x][r].\n\n[r]: ../../ingest.json", "../../ingest.json"),
        ('<img src="../../ingest.json">', "../../ingest.json"),
        ("See [x](<../../ingest.json>).", "../../ingest.json"),
        ("See [x](%2e%2e/%2e%2e/ingest.json).", "%2e%2e/%2e%2e/ingest.json"),
        ("See [x](references\\..\\..\\..\\ingest.json).", "references\\..\\..\\..\\ingest.json"),
        ("See [x](~/.ssh/id_rsa).", "~/.ssh/id_rsa"),
    ],
    ids=["ref-def", "img", "angle", "pct", "backslash", "tilde"],
)
def test_structure_fails_on_escaping_reference_forms(tmp_path, line, target):
    staging, work = _case(tmp_path, _with_line(line))
    r = structure.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == [f"reference escapes the skill folder: {target}"]


def test_structure_fails_on_missing_ref_def_and_img(tmp_path):
    staging, work = _case(
        tmp_path, _with_line('[r]: references/nope.md\n\n<img src="assets/frames/nope.jpg">')
    )
    r = structure.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == [
        "referenced file missing: references/nope.md",
        "referenced file missing: assets/frames/nope.jpg",
    ]


def test_structure_fails_on_case_mismatched_reference(tmp_path):
    staging, work = _case(tmp_path, _with_line("See [x](References/Source.md)."))
    r = structure.run(context_for(staging, work))
    assert not r.ok and _msgs(r) == ["referenced file missing: References/Source.md"]


def test_structure_passes_existing_ref_def_and_img(tmp_path):
    staging, work = _case(
        tmp_path,
        _with_line('[r]: references/source.md\n\n<img src="assets/frames/f000250.jpg">'),
    )
    r = structure.run(context_for(staging, work))
    assert r.ok, _msgs(r)
