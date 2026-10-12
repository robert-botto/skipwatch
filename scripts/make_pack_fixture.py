"""Generate the pack fixtures in tests/fixtures/packs/ (spec S4, M5-G1).

In a scratch SKIPWATCH_HOME, builds the M1 reference work folder exactly as
tests/pipeline/test_fixture_pipeline.py does (ingest the fixture video, transcribe, frames,
plan, copy tests/fixtures/pipeline/notes, redact the reference draft into staging, scale the
linked frames to 960 wide), then runs `check`, `install --to <scratch>` and `pack`:

- run-skipdemo-tutorial.skillpack.zip: the pack as `pack` wrote it.
- run-skipdemo-tutorial-tampered.skillpack.zip: the same pack with one byte of step 2's
  quoted prompt changed inside run-skipdemo-tutorial/SKILL.md, the manifest untouched.

Packs are stored zips with fixed entry dates, so both files are byte-stable for the same
inputs: the manifest's extracted_at (the mtime of ingest.json) is pinned to EXTRACTED_AT.
Needs ffmpeg and ffprobe on PATH.

    uv run python scripts/make_pack_fixture.py
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
REF = FIX / "pipeline"
OUT = FIX / "packs"
NAME = "run-skipdemo-tutorial"
GOOD = OUT / f"{NAME}.skillpack.zip"
TAMPERED = OUT / f"{NAME}-tampered.skillpack.zip"
PROMPT = b"Write a four line poem about rivers"
TAMPERED_PROMPT = b"Write a four line poem about rovers"  # one byte: i -> o
SKILL_FRAME_WIDTH = 960
FRAME_LINK = re.compile(r"assets/frames/(f\d{6})\.jpg")
EXTRACTED_AT = datetime(2026, 10, 11, tzinfo=UTC).timestamp()


def engine_binary() -> str:
    local = Path(sys.executable).parent / "skipwatch"
    return str(local) if local.exists() else (shutil.which("skipwatch") or "skipwatch")


def engine(env: dict[str, str], *args: str, stdin=None, stdout=None) -> None:
    result = subprocess.run(
        [engine_binary(), *args],
        env=env,
        stdin=stdin if stdin is not None else subprocess.DEVNULL,
        stdout=stdout if stdout is not None else subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"skipwatch {' '.join(args)} exited {result.returncode}: {result.stderr}")


def reference_run(env: dict[str, str], work: Path) -> Path:
    """The M1 reference run up to a checked staging folder; returns the staging folder."""
    engine(env, "ingest", str(FIX / "tutorial-60s.mp4"), "--work", str(work))
    for stage in ("transcribe", "frames", "plan"):
        engine(env, stage, "--work", str(work))
    shutil.copytree(REF / "notes", work / "notes")
    draft = REF / "draft" / NAME
    staging = work / "staging" / NAME
    for src in sorted(p for p in draft.rglob("*") if p.is_file()):
        dst = staging / src.relative_to(draft)
        dst.parent.mkdir(parents=True, exist_ok=True)
        with src.open("rb") as fin, dst.open("wb") as fout:
            engine(env, "redact", "--stdin", stdin=fin, stdout=fout)
    for fid in sorted(set(FRAME_LINK.findall((staging / "SKILL.md").read_text(encoding="utf-8")))):
        with Image.open(work / "frames" / f"{fid}.jpg") as img:
            height = round(img.height * SKILL_FRAME_WIDTH / img.width)
            dst = staging / "assets" / "frames" / f"{fid}.jpg"
            dst.parent.mkdir(parents=True, exist_ok=True)
            img.convert("RGB").resize((SKILL_FRAME_WIDTH, height)).save(dst, "JPEG")
    os.utime(work / "ingest.json", (EXTRACTED_AT, EXTRACTED_AT))
    engine(env, "check", str(staging), "--work", str(work))
    return staging


def tamper(good: Path, out: Path) -> None:
    """Copy every entry with its ZipInfo; change one byte of step 2's prompt in SKILL.md."""
    tmp = out.with_name(out.name + ".tmp")
    with zipfile.ZipFile(good) as zin, zipfile.ZipFile(tmp, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info)
            if info.filename == f"{NAME}/SKILL.md":
                if data.count(PROMPT) != 1:
                    raise SystemExit("step 2's prompt must appear exactly once in SKILL.md")
                data = data.replace(PROMPT, TAMPERED_PROMPT)
            zout.writestr(info, data, compress_type=zipfile.ZIP_STORED)
    os.replace(tmp, out)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="skipwatch-pack-fixture-") as tmp:
        scratch = Path(tmp).resolve()
        env = {**os.environ, "SKIPWATCH_HOME": str(scratch / "home")}
        env["SKIPWATCH_TREG_DISABLED"] = "1"
        staging = reference_run(env, scratch / "work")
        engine(env, "install", str(staging), "--to", str(scratch / "installed"))
        engine(env, "pack", str(scratch / "installed" / NAME), "-o", str(GOOD))
    tamper(GOOD, TAMPERED)
    for path in (GOOD, TAMPERED):
        print(f"Wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
