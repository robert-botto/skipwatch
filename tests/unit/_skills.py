"""An installed skill folder (what `install` leaves behind), for the pack and unpack tests."""

import io
from pathlib import Path

from PIL import Image

from skipwatch.manifest import file_hashes
from skipwatch.models import Counts, Manifest, ManifestSource
from skipwatch.workdir import write_model

NAME = "run-x"
SKILL_MD = """---
name: run-x
description: Runs x. Use when you want x run.
---

# Run x

## Procedure

1. Initialise the project. [spoken]
   > "initialise the project" (00:05)
"""
TRANSCRIPT_MD = """# Transcript

[00:05] initialise the project
[00:12] then build it
[1:02:03] and ship it
"""


def jpeg_bytes() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 40, 40)).save(out, format="JPEG")
    return out.getvalue()


def installed_skill(root: Path, **manifest_updates) -> Path:
    """<root>/skills/run-x with SKILL.md, two references, one frame and a skipwatch.json
    whose `files` hashes match, as `install` writes it."""
    skill = root / "skills" / NAME
    (skill / "references").mkdir(parents=True)
    (skill / "assets" / "frames").mkdir(parents=True)
    (skill / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    (skill / "references" / "source.md").write_text("# Source\n\nstep 1: 00:05\n", encoding="utf-8")
    (skill / "references" / "transcript.md").write_text(TRANSCRIPT_MD, encoding="utf-8")
    (skill / "assets" / "frames" / "f000250.jpg").write_bytes(jpeg_bytes())
    manifest = Manifest(
        name=NAME,
        description="Runs x. Use when you want x run.",
        skipwatch_version="0.1.0",
        source=ManifestSource(
            platform="youtube", url="https://youtu.be/x", author="someone", title="Run x"
        ),
        extracted_at="2026-10-09T18:20:00Z",
        counts=Counts(steps=1, spoken=1),
        confidence="high",
        critic_score=8.5,
        checks_passed=True,
        files=file_hashes(skill),
    )
    write_model(skill / "skipwatch.json", manifest.model_copy(update=manifest_updates))
    return skill
