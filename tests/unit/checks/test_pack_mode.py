"""Pack mode (M5-M6 issue 1): structure rules still bite, spoken quotes are checked against the
pack transcript, on-screen and written quotes are not re-verified and say so once."""

import json
from pathlib import Path

from skipwatch.checks import provenance
from skipwatch.checks.runner import build_context
from skipwatch.models import CheckResult, Counts, Manifest, ManifestSource

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


def _claims() -> Manifest:
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
    )


def _ingest(pack: bool) -> dict:
    raw: dict = {
        "schema": "skipwatch/ingest/1",
        "source": {"kind": "video", "platform": "youtube", "url": "https://youtu.be/x"},
        "route": {"context": "pack"},
    }
    if pack:
        raw["pack"] = {
            "file": "a.skillpack.zip",
            "sha256": "sha256:" + "1" * 64,
            "manifest": _claims().model_dump(by_alias=True),
        }
    return raw


def pack_ctx(
    tmp_path: Path, skill_md: str, transcript: list[tuple[float, float, str]] | None = None
) -> tuple[Path, Path]:
    """A pack work folder as unpack lays it out: ingest.json with `pack`, staging/<name>/,
    transcript.json (origin "pack") only when the pack shipped references/transcript.md."""
    work = tmp_path / "packwork"
    staging = work / "staging" / NAME
    staging.mkdir(parents=True)
    (staging / "SKILL.md").write_text(skill_md, encoding="utf-8")
    (work / "ingest.json").write_text(json.dumps(_ingest(pack=True)), encoding="utf-8")
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
    assert ctx.pack is not None and ctx.pack.manifest == _claims()
