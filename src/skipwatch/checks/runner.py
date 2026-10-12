"""Run the six checks over a staging skill and write check-report.json and skipwatch.json."""

import importlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from skipwatch.checks import CHECK_ORDER
from skipwatch.config import load_config
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.manifest import (
    MANIFEST_NAME,
    build,
    pack_confidence,
    pack_refusal,
    read_work_file,
)
from skipwatch.models import (
    BatchesFile,
    CheckReport,
    Config,
    Counts,
    IngestBundle,
    NotesFile,
    PackOrigin,
    Transcript,
)
from skipwatch.skillmd import SkillDoc, parse
from skipwatch.workdir import WorkDir, run_stage, write_model

GAP_LINE = re.compile(r"^\s*(?:[-*]\s+|\d+\.\s+)?GAP\b")


def skill_entries(staging: Path) -> tuple[list[Path], list[Path], list[Path]]:
    """(regular files, symlinks, special files) under staging, sorted. lstat only, never follows."""
    files: list[Path] = []
    links: list[Path] = []
    specials: list[Path] = []
    for root, dirs, names in os.walk(staging, followlinks=False):
        base = Path(root)
        for name in dirs + names:
            path = base / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                links.append(path)
            elif stat.S_ISREG(mode):
                files.append(path)
            elif not stat.S_ISDIR(mode):
                specials.append(path)
    return sorted(files), sorted(links), sorted(specials)


def skill_files(staging: Path) -> list[Path]:
    return skill_entries(staging)[0]


def write_atomic(path: Path, data: bytes) -> None:
    """Write via a temp file in the same folder and os.replace: never through a hardlink."""
    tmp = path.with_name(f".{path.name}.skipwatch-tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


@dataclass
class CheckContext:
    staging: Path
    work: Path
    doc: SkillDoc
    transcript: Transcript | None
    notes: list[NotesFile]
    ingest: IngestBundle
    config: Config
    pack: PackOrigin | None = None  # from ingest.pack only: the one switch for pack mode


def _notes_paths(work: Path) -> list[Path]:
    batches = work / "batches.json"
    if batches.exists():
        listed = [work / b.notes_path for b in read_work_file(batches, BatchesFile).batches]
        return [p for p in listed if p.exists()]
    return sorted((work / "notes").glob("*.json"))


def build_context(staging: Path, work: Path) -> CheckContext:
    skill_md = staging / "SKILL.md"
    text = skill_md.read_bytes().decode("utf-8", errors="replace") if skill_md.exists() else ""
    transcript_path = work / "transcript.json"
    try:
        config = load_config()
    except ValueError as exc:
        raise SkipwatchError(ExitCode.USAGE, str(exc)) from exc
    ingest = read_work_file(work / "ingest.json", IngestBundle)
    return CheckContext(
        staging=staging,
        work=work,
        doc=parse(text),
        transcript=(
            read_work_file(transcript_path, Transcript) if transcript_path.exists() else None
        ),
        notes=[read_work_file(p, NotesFile) for p in _notes_paths(work)],
        ingest=ingest,
        config=config,
        pack=ingest.pack,
    )


def _gap_count(doc: SkillDoc) -> int:
    """GAP lines under "Unverified and gaps", plus `GAP:` lines anywhere, each line once."""
    gaps_section = set(doc.section_text("Unverified and gaps").splitlines())
    return sum(
        1
        for line in doc.body_lines
        if "GAP:" in line or (line in gaps_section and GAP_LINE.match(line))
    )


def counts_for(doc: SkillDoc) -> Counts:
    tags = [tag.kind for step in doc.steps for tag in step.tags]
    return Counts(
        steps=len(doc.steps),
        spoken=tags.count("spoken"),
        on_screen=tags.count("on-screen"),
        written=tags.count("written"),
        inferred=tags.count("inferred"),
        gaps=_gap_count(doc),
        illegible=doc.body.count("[illegible at"),
    )


def _check_modules() -> dict[str, ModuleType]:
    return {name: importlib.import_module(f"skipwatch.checks.{name}") for name in CHECK_ORDER}


def _is_pack(ctx: CheckContext) -> bool:
    """Pack mode as build sees it: a `pack` field honoured in this folder (pack_refusal)."""
    return ctx.pack is not None and pack_refusal(ctx.staging, ctx.work, ctx.pack) is None


def _run_checks(staging: Path, work: Path) -> CheckReport:
    modules = _check_modules()
    # Redaction first so every later check, and the manifest, see cleaned text (R-CHK-2).
    results = {"redaction": modules["redaction"].run(build_context(staging, work))}
    ctx = build_context(staging, work)
    counts = counts_for(ctx.doc)
    # check writes skipwatch.json before structure validates it (plan issue 1).
    draft = CheckReport(
        skill=staging.name, passed=False, results=list(results.values()), counts=counts
    )
    write_model(staging / MANIFEST_NAME, build(staging, work, draft))
    for name in CHECK_ORDER:
        if name not in results:
            results[name] = modules[name].run(ctx)
    ordered = [results[name] for name in CHECK_ORDER]
    report = CheckReport(
        skill=staging.name,
        passed=all(r.ok for r in ordered if r.check != "safety"),
        results=ordered,
        counts=counts,
        pack_confidence=pack_confidence(counts) if _is_pack(ctx) else None,
    )
    write_model(staging / MANIFEST_NAME, build(staging, work, report))
    write_model(work / "check-report.json", report)
    return report


def run_all(staging: Path, work: Path) -> CheckReport:
    workdir = WorkDir(work)
    workdir.ensure()
    return run_stage(workdir, "check", lambda: _run_checks(staging, work))
