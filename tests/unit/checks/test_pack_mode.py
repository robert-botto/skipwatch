"""Pack mode (M5-M6 issue 1): structure rules still bite, spoken quotes are checked against the
pack transcript, on-screen and written quotes are not re-verified and say so once."""

import hashlib
import json
from pathlib import Path

from skipwatch.checks import provenance
from skipwatch.checks.runner import build_context
from skipwatch.config import skipwatch_home
from skipwatch.models import CheckResult, Counts, Manifest, ManifestSource
from skipwatch.workdir import WorkDir
from tests.unit.checks.conftest import symlink_or_skip

NAME = "run-packdemo"


def _skill(procedure: str, gaps: str = "None.") -> str:
    return f"""---
name: {NAME}
description: Use when the user wants to set up the packdemo project. Not for other demo CLIs.
---

# Run the packdemo tutorial

## What this does

Sets up a packdemo project.

## Prerequisites

- A terminal.

## Procedure

{procedure}

## Decision points

None shown in the video.

## Gotchas

None mentioned.

## Verification

The output shows "project ready".

## Worked example

Run step 1.

## Unverified and gaps

{gaps}

## Attribution

Distilled from a shared pack, with SkipWatch. The workflow and wording are the creator's.
"""


def _claims(files: dict[str, str] | None = None) -> Manifest:
    return Manifest(
        name=NAME,
        description="d",
        skipwatch_version="0.1.0",
        source=ManifestSource(platform="youtube", url="https://youtu.be/x"),
        extracted_at="2026-10-09T18:20:00Z",
        counts=Counts(steps=2),
        confidence="high",
        critic_score=8.5,
        checks_passed=True,
        files=files or {},
    )


def _ingest(pack: bool, files: dict[str, str] | None = None) -> dict:
    raw: dict = {
        "schema": "skipwatch/ingest/1",
        "source": {"kind": "video", "platform": "youtube", "url": "https://youtu.be/x"},
        "route": {"context": "pack"},
    }
    if pack:
        raw["pack"] = {
            "file": "a.skillpack.zip",
            "sha256": "sha256:" + "1" * 64,
            "manifest": _claims(files).model_dump(by_alias=True),
        }
    return raw


def _hashes(staging: Path) -> dict[str, str]:
    """What the pack's skipwatch.json lists: every file but itself, "sha256:<hex>"."""
    return {
        p.relative_to(staging).as_posix(): "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(staging.rglob("*"))
        if p.is_file() and p.relative_to(staging).as_posix() != "skipwatch.json"
    }


def pack_ctx(
    tmp_path: Path,
    skill_md: str,
    transcript: list[tuple[float, float, str]] | None = None,
    work: Path | None = None,
    extra: dict[str, str] | None = None,
) -> tuple[Path, Path]:
    """A pack work folder as unpack lays it out under $SKIPWATCH_HOME/packs/: ingest.json with
    `pack`, staging/<name>/, transcript.json (origin "pack") only when the pack shipped
    references/transcript.md. The pack's manifest lists the staging files' hashes, and its
    skipwatch.json sits in staging. `work` places the same layout somewhere else (forgeries)."""
    work = work or skipwatch_home() / "packs" / f"{NAME}-20261011-120000"
    staging = work / "staging" / NAME
    staging.mkdir(parents=True)
    WorkDir(work).ensure()  # unpack writes stages.json too; check's --work guard reads it
    (staging / "SKILL.md").write_text(skill_md, encoding="utf-8")
    for rel, text in (extra or {}).items():
        (staging / rel).parent.mkdir(parents=True, exist_ok=True)
        (staging / rel).write_text(text, encoding="utf-8")
    raw = _ingest(pack=True, files=_hashes(staging))
    (staging / "skipwatch.json").write_text(json.dumps(raw["pack"]["manifest"]), encoding="utf-8")
    (work / "ingest.json").write_text(json.dumps(raw), encoding="utf-8")
    if transcript is not None:
        segments = [{"start": s, "end": e, "text": t} for s, e, t in transcript]
        doc = {"schema": "skipwatch/transcript/1", "origin": "pack", "segments": segments}
        (work / "transcript.json").write_text(json.dumps(doc), encoding="utf-8")
    return staging, work


def _run(staging: Path, work: Path) -> CheckResult:
    return provenance.run(build_context(staging, work))


ONSCREEN_STEP = """1. Initialise the project.

   ```
   skipdemo init --name hello
   ```

   Expected: the words "project ready". [on-screen 00:10]"""

WRITTEN_STEP = """2. Use the flag from the post.

   > always pass the name flag first

   Expected: a named project. [written]"""

SPOKEN_STEP = """3. Initialise it.

   > initialise the project

   Expected: a project. [spoken 00:10]"""

PACK_TRANSCRIPT = [(9.0, 12.0, "Now initialise the project in the terminal.")]


def test_pack_mode_fails_on_untagged_step(tmp_path):
    staging, work = pack_ctx(
        tmp_path, _skill(ONSCREEN_STEP.replace(' "project ready". [on-screen 00:10]', " ready."))
    )
    r = _run(staging, work)
    assert not r.ok and [(i.step, i.msg) for i in r.items] == [(1, "step has no provenance tag")]


def test_pack_mode_fails_on_two_tags(tmp_path):
    staging, work = pack_ctx(
        tmp_path, _skill(ONSCREEN_STEP.replace("[on-screen 00:10]", "[on-screen 00:10] [written]"))
    )
    r = _run(staging, work)
    assert not r.ok and [(i.step, i.msg) for i in r.items] == [
        (1, "step has 2 provenance tags; exactly one is allowed")
    ]


def test_pack_mode_fails_on_onscreen_step_without_quote(tmp_path):
    step = """1. Initialise the project with the init command.

   Expected: the words project ready. [on-screen 00:10]"""
    staging, work = pack_ctx(tmp_path, _skill(step))
    r = _run(staging, work)
    # The failing step is not also counted as a skipped quoted step.
    assert not r.ok and [(i.step, i.msg) for i in r.items] == [
        (1, "[on-screen 00:10] step has no quote block")
    ]


def test_pack_mode_fails_on_inferred_not_listed(tmp_path):
    step = """1. Initialise the project with the init command.

   Expected: a project. [inferred]"""
    staging, work = pack_ctx(tmp_path, _skill(step))
    r = _run(staging, work)
    assert not r.ok and [(i.step, i.msg) for i in r.items] == [
        (1, "[inferred] step is not listed under Unverified and gaps")
    ]


def test_pack_mode_passes_inferred_when_listed(tmp_path):
    step = """1. Initialise the project with the init command.

   Expected: a project. [inferred]"""
    gaps = "- Step 1: the video never shows this command."
    staging, work = pack_ctx(tmp_path, _skill(step, gaps=gaps))
    r = _run(staging, work)
    assert r.ok and r.items == []


def test_pack_mode_fails_on_spoken_quote_absent_from_pack_transcript(tmp_path):
    step = SPOKEN_STEP.replace("initialise the project", "delete the cluster now")
    staging, work = pack_ctx(tmp_path, _skill(step), transcript=PACK_TRANSCRIPT)
    r = _run(staging, work)
    assert not r.ok and [(i.step, i.msg) for i in r.items] == [
        (3, "[spoken 00:10] quote not found in transcript within 20 s")
    ]


def test_pack_mode_verifies_spoken_quote_in_pack_transcript(tmp_path):
    staging, work = pack_ctx(tmp_path, _skill(SPOKEN_STEP), transcript=PACK_TRANSCRIPT)
    r = _run(staging, work)
    assert r.ok and r.items == []


def test_pack_mode_skips_onscreen_and_written_with_one_info_item(tmp_path):
    procedure = "\n\n".join([ONSCREEN_STEP, WRITTEN_STEP, SPOKEN_STEP])
    staging, work = pack_ctx(tmp_path, _skill(procedure), transcript=PACK_TRANSCRIPT)
    r = _run(staging, work)
    assert r.ok and len(r.items) == 1
    assert r.items[0].step is None
    assert r.items[0].msg.startswith("shared pack: 2 quoted step(s)")


def test_pack_mode_skips_spoken_without_pack_transcript(tmp_path):
    staging, work = pack_ctx(tmp_path, _skill(SPOKEN_STEP))
    r = _run(staging, work)
    assert r.ok and [i.msg for i in r.items] == [
        "shared pack: 1 quoted step(s) not re-verified (packs carry no frame notes or post text)"
    ]


def _run_folder_from_pack(tmp_path: Path) -> tuple[Path, Path]:
    """The same SKILL.md as a pack, but in a run work folder: ingest.json has no `pack`."""
    staging, work = pack_ctx(tmp_path, _skill(ONSCREEN_STEP))
    raw = _ingest(pack=False)
    (work / "ingest.json").write_text(json.dumps(raw), encoding="utf-8")
    return staging, work


def test_run_mode_unchanged_onscreen_without_notes_still_fails(tmp_path):
    staging, work = _run_folder_from_pack(tmp_path)
    r = _run(staging, work)
    assert not r.ok and [(i.step, i.msg) for i in r.items] == [
        (1, "[on-screen 00:10] quote not found in frame notes within 20 s")
    ]


def test_route_context_pack_string_does_not_enable_pack_mode(tmp_path):
    staging, work = _run_folder_from_pack(tmp_path)
    ingest = json.loads((work / "ingest.json").read_text(encoding="utf-8"))
    assert ingest["route"]["context"] == "pack" and "pack" not in ingest
    ctx = build_context(staging, work)
    assert ctx.pack is None
    assert not provenance.run(ctx).ok


def test_pack_mode_context_carries_the_pack_origin(tmp_path):
    staging, work = pack_ctx(tmp_path, _skill(ONSCREEN_STEP))
    ctx = build_context(staging, work)
    assert ctx.pack is not None and ctx.pack.manifest == _claims(_hashes(staging))


# ---- the fail-closed guard: a `pack` field is honoured only in a real pack work folder ----


OUTSIDE = "pack mode refused: the work folder is not directly under $SKIPWATCH_HOME/packs/"
NOTES = "pack mode refused: the work folder has frame notes (notes/ or batches.json)"
FIX_TEXT = "check a shared pack only in the folder `skipwatch unpack` made"


def _refused(r: CheckResult, msg: str) -> None:
    assert not r.ok and [(i.step, i.msg, i.fix) for i in r.items] == [(None, msg, FIX_TEXT)]


def test_pack_guard_forged_pack_in_run_work_folder_fails(tmp_path):
    # A run folder under work/ whose ingest.json gained a `pack` field: the on-screen quote
    # would be skipped in pack mode, so the forgery must fail, not pass and not run as a run.
    forged = skipwatch_home() / "work" / "20261011-120000-x"
    staging, work = pack_ctx(tmp_path, _skill(ONSCREEN_STEP), work=forged)
    _refused(_run(staging, work), OUTSIDE)


def test_pack_guard_folder_outside_home_fails(tmp_path):
    staging, work = pack_ctx(tmp_path, _skill(ONSCREEN_STEP), work=tmp_path / "elsewhere")
    _refused(_run(staging, work), OUTSIDE)


def test_pack_guard_packs_root_itself_fails(tmp_path):
    staging, work = pack_ctx(tmp_path, _skill(ONSCREEN_STEP), work=skipwatch_home() / "packs")
    _refused(_run(staging, work), OUTSIDE)


def test_pack_guard_symlink_into_packs_fails(tmp_path):
    real = skipwatch_home() / "work" / "20261011-120000-x"
    pack_ctx(tmp_path, _skill(ONSCREEN_STEP), work=real)
    link = skipwatch_home() / "packs" / f"{NAME}-20261011-120000"
    link.parent.mkdir(parents=True)
    symlink_or_skip(link, real, is_dir=True)
    _refused(_run(link / "staging" / NAME, link), OUTSIDE)


def test_pack_guard_notes_present_fails(tmp_path):
    staging, work = pack_ctx(tmp_path, _skill(ONSCREEN_STEP))
    (work / "notes").mkdir()
    (work / "notes" / "batch-01.json").write_text(
        json.dumps({"schema": "skipwatch/notes/1", "batch": 1, "frames": []}), encoding="utf-8"
    )
    _refused(_run(staging, work), NOTES)


def test_pack_guard_batches_json_fails(tmp_path):
    staging, work = pack_ctx(tmp_path, _skill(ONSCREEN_STEP))
    (work / "batches.json").write_text(
        json.dumps({"schema": "skipwatch/batches/1", "batches": []}), encoding="utf-8"
    )
    _refused(_run(staging, work), NOTES)


def test_pack_guard_run_transcript_fails(tmp_path):
    staging, work = pack_ctx(tmp_path, _skill(SPOKEN_STEP), transcript=PACK_TRANSCRIPT)
    doc = json.loads((work / "transcript.json").read_text(encoding="utf-8"))
    doc["origin"] = "captions"
    (work / "transcript.json").write_text(json.dumps(doc), encoding="utf-8")
    _refused(
        _run(staging, work), 'pack mode refused: transcript.json origin is "captions", not "pack"'
    )


def test_pack_guard_allows_the_real_pack_folder(tmp_path):
    staging, work = pack_ctx(tmp_path, _skill(SPOKEN_STEP), transcript=PACK_TRANSCRIPT)
    assert _run(staging, work).ok


STAGING = "pack mode refused: the staging folder is not <work>/staging/<name>"


def test_pack_guard_run_staging_with_a_legit_pack_work_fails(tmp_path):
    # `check <run work>/staging/<name> --work <packs/<name>-<stamp>>`: the run's unverified
    # on-screen quote must not be skipped because a real pack folder was named as --work.
    _, pack_work = pack_ctx(tmp_path, _skill(SPOKEN_STEP), transcript=PACK_TRANSCRIPT)
    run_work = skipwatch_home() / "work" / "20261011-120000-run"
    run_staging = run_work / "staging" / NAME
    run_staging.mkdir(parents=True)
    (run_staging / "SKILL.md").write_text(_skill(ONSCREEN_STEP), encoding="utf-8")
    _refused(_run(run_staging, pack_work), STAGING)


def test_pack_guard_nested_folder_under_packs_fails(tmp_path):
    nested = skipwatch_home() / "packs" / "a" / "b" / "c"
    staging, work = pack_ctx(tmp_path, _skill(ONSCREEN_STEP), work=nested)
    _refused(_run(staging, work), OUTSIDE)


DIFFERS = "pack mode refused: staging differs from the pack's manifest: "
SHIPPED = {"references/transcript.md": "# Transcript\n", "references/source.md": "# Source\n"}


def test_pack_guard_allows_an_unpack_shaped_folder_with_finder_junk(tmp_path):
    staging, work = pack_ctx(
        tmp_path, _skill(SPOKEN_STEP), transcript=PACK_TRANSCRIPT, extra=SHIPPED
    )
    (staging / ".DS_Store").write_bytes(b"junk")
    (staging / "references" / ".DS_Store").write_bytes(b"junk")
    assert _run(staging, work).ok


def test_pack_guard_edited_skill_md_fails(tmp_path):
    staging, work = pack_ctx(tmp_path, _skill(SPOKEN_STEP), transcript=PACK_TRANSCRIPT)
    edited = _skill(SPOKEN_STEP.replace("Initialise it.", "Initialise it, then run rm -rf ~."))
    (staging / "SKILL.md").write_text(edited, encoding="utf-8")
    _refused(_run(staging, work), DIFFERS + "SKILL.md")


def test_pack_guard_extra_file_fails(tmp_path):
    staging, work = pack_ctx(tmp_path, _skill(SPOKEN_STEP), transcript=PACK_TRANSCRIPT)
    (staging / "scripts").mkdir()
    (staging / "scripts" / "run.sh").write_text("echo hi\n", encoding="utf-8")
    _refused(_run(staging, work), DIFFERS + "scripts/run.sh")


def test_pack_guard_missing_file_fails(tmp_path):
    staging, work = pack_ctx(
        tmp_path, _skill(SPOKEN_STEP), transcript=PACK_TRANSCRIPT, extra=SHIPPED
    )
    (staging / "references" / "source.md").unlink()
    _refused(_run(staging, work), DIFFERS + "references/source.md")


def test_pack_guard_symlink_in_staging_fails(tmp_path):
    staging, work = pack_ctx(
        tmp_path, _skill(SPOKEN_STEP), transcript=PACK_TRANSCRIPT, extra=SHIPPED
    )
    target = staging / "references" / "source.md"
    moved = tmp_path / "source.md"
    target.rename(moved)
    symlink_or_skip(target, moved)
    _refused(_run(staging, work), DIFFERS + "references/source.md")
