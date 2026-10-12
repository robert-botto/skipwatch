"""Fixture pipeline, the engine half of spec 11.2 (plan issue 5, package M1-G).

Runs the real `skipwatch` CLI as subprocesses on tests/fixtures/tutorial-60s.mp4 in a temporary
SKIPWATCH_HOME: doctor, ingest, transcribe, frames, plan. Then it plays the orchestrator's
part with committed reference files: notes for the planned batch (validate-notes), a draft
skill redacted file to file with `redact --stdin` into staging, `check`, and `install`.
The Claude half (the agent-directed text never reaches an executed command) is eval
`local-fixture`.

Needs ffmpeg and ffprobe on PATH (or already fetched by static-ffmpeg): the engine would
otherwise download static ffmpeg, and this suite must not depend on the network.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from skipwatch.frames import DUP_FRACTION, changed_fraction, thumbnail
from skipwatch.media import ffmpeg_paths, find_system_ffmpeg, static_ffmpeg_fetched
from skipwatch.skillmd import fence_spans, parse

pytestmark = pytest.mark.pipeline

FIX = Path(__file__).resolve().parents[1] / "fixtures"
REF = FIX / "pipeline"
NAME = "run-skipdemo-tutorial"
SCRIPT = json.loads((FIX / "tutorial-60s.script.json").read_text(encoding="utf-8"))
CUES = {cue["kind"]: cue for cue in SCRIPT["cues"]}
KEY = CUES["setting"]["text"].split("=", 1)[1]  # the fake sk-proj-FIXTURE0NLY... key
AGENT_TEXT = CUES["agent"]["text"]
FRAME_LINK = re.compile(r"assets/frames/(f\d{6})\.jpg")
SKILL_FRAME_WIDTH = 960
TIMEOUT_S = 300


def _engine() -> list[str]:
    """The installed console script next to this interpreter: the CLI exactly as users run it."""
    found = shutil.which("skipwatch", path=str(Path(sys.executable).parent))
    assert found, f"no skipwatch entry point next to {sys.executable}; run uv sync --dev"
    return [found]


class Engine:
    def __init__(self, home: Path):
        self.env = {**os.environ, "SKIPWATCH_HOME": str(home)}

    def run(self, *args: str, stdin=None, stdout=None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [*_engine(), *args],
            env=self.env,
            stdin=stdin if stdin is not None else subprocess.DEVNULL,
            stdout=stdout if stdout is not None else subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=stdout is None,
            timeout=TIMEOUT_S,
            check=False,
        )

    def ok(self, *args: str) -> subprocess.CompletedProcess:
        result = self.run(*args)
        assert result.returncode == 0, (args, result.returncode, result.stderr)
        return result


@pytest.fixture(scope="module")
def root(tmp_path_factory) -> Path:
    if find_system_ffmpeg() is None and not static_ffmpeg_fetched():
        pytest.fail("pipeline tests need ffmpeg and ffprobe on PATH (no static-ffmpeg download)")
    return tmp_path_factory.mktemp("pipeline")


@pytest.fixture(scope="module")
def engine(root: Path) -> Engine:
    return Engine(root / "swhome")


@pytest.fixture(scope="module")
def work(root: Path, engine: Engine) -> Path:
    """doctor, ingest, transcribe, frames and plan, exactly as the orchestrator runs them."""
    w = root / "work"
    engine.ok("doctor")
    engine.ok("ingest", str(FIX / "tutorial-60s.mp4"), "--work", str(w))
    engine.ok("transcribe", "--work", str(w))
    engine.ok("frames", "--work", str(w))
    engine.ok("plan", "--work", str(w))
    return w


@pytest.fixture(scope="module")
def staged(work: Path, engine: Engine) -> dict[str, str]:
    """The orchestrator's drafting step: every draft file goes through `redact --stdin`.

    Returns the staged text files as `redact` wrote them, before `check` (which redacts again)
    can touch them, so (d) proves `redact --stdin` alone.
    """
    shutil.copytree(REF / "notes", work / "notes")
    draft = REF / "draft" / NAME
    out = work / "staging" / NAME
    for src in sorted(p for p in draft.rglob("*") if p.is_file()):
        dst = out / src.relative_to(draft)
        dst.parent.mkdir(parents=True, exist_ok=True)
        with src.open("rb") as fin, dst.open("wb") as fout:
            result = engine.run("redact", "--stdin", stdin=fin, stdout=fout)
        assert result.returncode == 0, (src, result.stderr)
    # Skill frames: the linked work frames, scaled to 960 wide JPEG.
    for fid in sorted(set(FRAME_LINK.findall((out / "SKILL.md").read_text(encoding="utf-8")))):
        with Image.open(work / "frames" / f"{fid}.jpg") as img:
            height = round(img.height * SKILL_FRAME_WIDTH / img.width)
            dst = out / "assets" / "frames" / f"{fid}.jpg"
            dst.parent.mkdir(parents=True, exist_ok=True)
            img.convert("RGB").resize((SKILL_FRAME_WIDTH, height)).save(dst, "JPEG")
    return {
        p.relative_to(out).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(out.rglob("*.md"))
    }


@pytest.fixture(scope="module")
def staging(staged: dict[str, str], work: Path) -> Path:
    return work / "staging" / NAME


@pytest.fixture(scope="module")
def checked(staging: Path, work: Path, engine: Engine) -> subprocess.CompletedProcess:
    return engine.run("check", str(staging), "--work", str(work), "--json")


# (a) ------------------------------------------------------------------------------------------


def _speech_onsets(wav: Path) -> list[float]:
    ffmpeg, _ = ffmpeg_paths(allow_fetch=False)
    err = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-nostdin", "-i", str(wav),
         "-af", "silencedetect=n=-35dB:d=0.4", "-f", "null", "-"],
        capture_output=True, text=True, timeout=60, check=False,
    ).stderr  # fmt: skip
    return [float(m) for m in re.findall(r"silence_end: ([\d.]+)", err)]


def test_a_transcript_matches_narration_within_1s(work: Path):
    segments = json.loads((work / "transcript.json").read_text(encoding="utf-8"))["segments"]
    sentences = SCRIPT["sentences"]
    assert len(segments) == len(sentences)
    onsets = _speech_onsets(FIX / "narration.wav")
    for seg, sentence in zip(segments, sentences, strict=True):
        assert seg["text"] == sentence["text"]
        assert abs(seg["start"] - sentence["start"]) <= 1.0, (seg, sentence)
        # The narration itself, not only the script: speech starts where the segment does.
        # The first sentence opens the file after 1 s of silence, so it has an onset too.
        assert min(abs(seg["start"] - t) for t in onsets) <= 1.0, (seg, onsets)


# (b) ------------------------------------------------------------------------------------------


def _frame_at(t: float, out: Path) -> Path:
    ffmpeg, _ = ffmpeg_paths(allow_fetch=False)
    subprocess.run(
        [str(ffmpeg), "-hide_banner", "-nostdin", "-y", "-ss", f"{t:.3f}",
         "-i", str(FIX / "tutorial-60s.mp4"), "-frames:v", "1", "-vf", "scale=1280:-2", str(out)],
        capture_output=True, timeout=60, check=True,
    )  # fmt: skip
    return out


@pytest.mark.parametrize("kind", ["command", "prompt", "setting", "agent"])
def test_b_r_fr_1_kept_frame_within_1s_after_each_cue(work: Path, tmp_path: Path, kind: str):
    cue = CUES[kind]["start"]
    frames = json.loads((work / "frames.json").read_text(encoding="utf-8"))["frames"]
    near = [f for f in frames if cue - 0.01 <= f["t"] <= cue + 1.0]
    assert near, (cue, [f["t"] for f in frames])
    before = thumbnail(_frame_at(cue - 1.0, tmp_path / "before.jpg"))
    fractions = [changed_fraction(before, thumbnail(work / f["path"])) for f in near]
    assert max(fractions) >= DUP_FRACTION, (cue, fractions)


# (c) ------------------------------------------------------------------------------------------


def test_c_validate_notes_accepts_reference_notes(staging: Path, work: Path, engine: Engine):
    batches = json.loads((work / "batches.json").read_text(encoding="utf-8"))["batches"]
    notes = json.loads((work / "notes" / "batch-01.json").read_text(encoding="utf-8"))
    assert [b["frame_ids"] for b in batches] == [[f["id"] for f in notes["frames"]]]
    result = engine.run("validate-notes", "--work", str(work))
    assert result.returncode == 0, result.stderr
    # Every cue's text reached the notes verbatim (the key still raw: notes are evidence).
    verbatim = {v["text"] for f in notes["frames"] for v in f["verbatim"]}
    assert {c["text"] for c in SCRIPT["cues"]} <= verbatim


# (d) ------------------------------------------------------------------------------------------


def test_d_redact_stdin_replaces_the_key_in_every_staged_file(staged: dict[str, str]):
    draft = REF / "draft" / NAME
    drafted = sorted(p.relative_to(draft).as_posix() for p in draft.rglob("*") if p.is_file())
    assert sorted(staged) == drafted
    with_key = [rel for rel in drafted if KEY in (draft / rel).read_text(encoding="utf-8")]
    assert len(with_key) >= 2, "the reference draft must carry the raw key in several files"
    for rel, text in staged.items():
        assert KEY not in text, rel
        assert "FIXTURE0NLY" not in text, rel
    assert "OPENAI_API_KEY=<OPENAI_API_KEY>" in staged["SKILL.md"]


# (e) ------------------------------------------------------------------------------------------


def test_e_check_passes_and_writes_report_and_manifest(
    checked: subprocess.CompletedProcess, staging: Path, work: Path
):
    assert checked.returncode == 0, checked.stderr
    report = json.loads((work / "check-report.json").read_text(encoding="utf-8"))
    assert report["passed"] is True and report["skill"] == NAME
    assert json.loads(checked.stdout) == report
    manifest = json.loads((staging / "skipwatch.json").read_text(encoding="utf-8"))
    front = parse((staging / "SKILL.md").read_text(encoding="utf-8")).frontmatter
    assert manifest["name"] == NAME == front["name"]
    assert manifest["description"] == front["description"]
    assert manifest["description"].startswith("Use when")


# (f) ------------------------------------------------------------------------------------------


def _sha256_files(skill_dir: Path) -> dict[str, str]:
    return {
        p.relative_to(skill_dir).as_posix(): "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(skill_dir.rglob("*"))
        if p.is_file() and p.name != "skipwatch.json"
    }


def test_f_install_writes_matching_hashes_and_refuses_a_second_time(
    checked: subprocess.CompletedProcess, staging: Path, root: Path, engine: Engine
):
    assert checked.returncode == 0, checked.stderr
    to = root / "installed"
    first = engine.run("install", str(staging), "--to", str(to), "--json")
    assert first.returncode == 0, first.stderr
    installed = to / NAME
    manifest = json.loads((installed / "skipwatch.json").read_text(encoding="utf-8"))
    assert manifest["checks_passed"] is True
    assert manifest["files"] == _sha256_files(installed)
    assert "SKILL.md" in manifest["files"]
    second = engine.run("install", str(staging), "--to", str(to), "--json")
    assert second.returncode == 6, (second.returncode, second.stderr)


# (g) ------------------------------------------------------------------------------------------


def test_g_agent_text_only_quoted_under_gotchas(checked: subprocess.CompletedProcess, staging):
    assert checked.returncode == 0, checked.stderr
    doc = parse((staging / "SKILL.md").read_text(encoding="utf-8"))
    assert doc.steps, "the staged skill has no Procedure steps"
    for step in doc.steps:
        assert AGENT_TEXT not in step.text, step.number
    assert AGENT_TEXT not in doc.section_text("Procedure")
    gotchas = doc.section_text("Gotchas").splitlines()
    fenced = {i for a, b in fence_spans(gotchas) for i in range(a + 1, b)}
    quoted = [i for i, line in enumerate(gotchas) if AGENT_TEXT in line]
    assert quoted and all(i in fenced for i in quoted), quoted
    assert doc.body.count(AGENT_TEXT) == len(quoted), "agent text appears outside Gotchas"


def test_treg_guard_is_in_the_environment_engine_snapshots():
    """Engine copies os.environ at module scope: the treg guard must already be there."""
    assert os.environ.get("SKIPWATCH_TREG_DISABLED") == "1"
