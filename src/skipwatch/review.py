"""The review screen (review-screen.md), built from the run's files so the skill prints it
exactly instead of assembling about fifteen lines by hand (skill audit 3 fix 6).

The prompt line and the transcription offers stay with the skill: they depend on the
install target and on the user's answers, which the engine never sees.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from skipwatch.crosscheck import disagreement
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.manifest import MANIFEST_NAME, read_work_file
from skipwatch.models import CheckReport, IngestBundle, Manifest, PackOrigin, Transcript
from skipwatch.providers.transcribe_cloud import DeepgramBackend, GroqBackend, OpenAIBackend
from skipwatch.skillmd import SkillDoc, parse

M = TypeVar("M", bound=BaseModel)

CRITIC_FAILED = "critic failed twice"
LINKED_POST = "video came from a linked post: "
COOKIES_LINE = "Fetched with your browser cookies: this skill cannot be packed for sharing."
CACHED_TRANSCRIPT = "Transcribe: reused cached transcript ("
CLOUD_KEYS = {b.name: b.env for b in (OpenAIBackend, GroqBackend, DeepgramBackend)}
PACK_SKIPPED = re.compile(r"^shared pack: (\d+) quoted step")
INFERRED_REASON = r"(?im)^\s*(?:[-*]\s+|\d+\.\s+)?step\s+{n}\s*[:\-]\s*(.+?)\s*$"


@dataclass
class ReviewInputs:
    """What the skill recorded during the run and passes on the command line."""

    degradations: list[str] = field(default_factory=list)
    unread: list[str] = field(default_factory=list)
    test_run: str | None = None


@dataclass
class _Run:
    work: Path
    skill: Path
    report: CheckReport
    manifest: Manifest
    ingest: IngestBundle
    doc: SkillDoc
    transcript: Transcript | None
    inputs: ReviewInputs

    @property
    def pack(self) -> PackOrigin | None:
        """Pack mode exactly when check graded it as a pack (pack_confidence set)."""
        return self.ingest.pack if self.report.pack_confidence is not None else None


def _required(path: Path, cls: type[M]) -> M:
    if not path.is_file():
        raise SkipwatchError(ExitCode.NO_CONTENT, f"missing {path}")
    return read_work_file(path, cls)


def _load(work: Path, skill: Path, inputs: ReviewInputs) -> _Run:
    report = _required(work / "check-report.json", CheckReport)
    if report.provider_calls_line is None:
        raise SkipwatchError(
            ExitCode.NO_CONTENT,
            "check-report.json has no provider_calls_line (an older check): run check again",
        )
    manifest = _required(skill / MANIFEST_NAME, Manifest)
    ingest = _required(work / "ingest.json", IngestBundle)
    skill_md = skill / "SKILL.md"
    if not skill_md.is_file():
        raise SkipwatchError(ExitCode.NO_CONTENT, f"missing {skill_md}")
    transcript_path = work / "transcript.json"
    transcript = read_work_file(transcript_path, Transcript) if transcript_path.is_file() else None
    return _Run(
        work=work,
        skill=skill,
        report=report,
        manifest=manifest,
        ingest=ingest,
        doc=parse(skill_md.read_bytes().decode("utf-8", errors="replace")),
        transcript=transcript,
        inputs=inputs,
    )


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item.strip()))


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _triggers(run: _Run) -> str:
    phrasings = re.findall(r'"([^"]+)"', run.manifest.description)[:3]
    return ", ".join(f'"{p}"' for p in phrasings) or "none"


def _steps(run: _Run) -> str:
    c = run.report.counts
    return (
        f"{c.steps} ({c.spoken} spoken, {c.on_screen} on-screen, {c.written} written, "
        f"{c.inferred} inferred), {_plural(c.gaps, 'gap')}"
    )


def _inferred(run: _Run) -> list[str]:
    gaps = run.doc.section_text("Unverified and gaps")
    items = []
    for step in run.doc.steps:
        if not any(tag.kind == "inferred" for tag in step.tags):
            continue
        found = re.search(INFERRED_REASON.format(n=step.number), gaps)
        reason = found.group(1).removesuffix(".") if found else "inferred"
        items.append(f"step {step.number} ({reason})")
    return items


def _pack_skipped(run: _Run) -> list[str]:
    for result in run.report.results:
        if result.check != "provenance":
            continue
        for item in result.items:
            found = PACK_SKIPPED.match(item.msg)
            if found:
                return [f"{found.group(1)} quoted steps not re-verified (shared pack)"]
    return []


def _unverified(run: _Run) -> str:
    items = _inferred(run)
    if run.pack is not None:
        items += _pack_skipped(run)
    items += run.inputs.degradations
    return "; ".join(_unique(items)) or "none"


def _unread(run: _Run) -> list[str]:
    return [] if run.pack is not None else _unique(run.inputs.unread)


def _safety(run: _Run) -> str:
    flags = [f for r in run.report.results if r.check == "safety" for f in r.flags]
    parts = [
        f"{f.kind} ({f.severity})" + (f" at step {f.step}" if f.step is not None else "")
        for f in flags
    ]
    return ", ".join(parts) or "none"


def _other_reasons(run: _Run) -> list[str]:
    reasons = []
    if run.report.counts.gaps:
        reasons.append(_plural(run.report.counts.gaps, "gap"))
    if run.transcript is None:
        reasons.append("no transcript")
    if _unread(run):
        reasons.append("frames unread")
    return reasons


def _confidence(run: _Run) -> str:
    pack = run.pack
    if pack is not None:
        claims = pack.manifest
        critic = f"{claims.critic_score:.1f}" if claims.critic_score is not None else "none"
        reasons = [
            "shared pack: critic not re-run here; "
            f"the pack claims {claims.confidence}, critic {critic}"
        ]
        return f"{run.report.pack_confidence} ({'; '.join(reasons + _other_reasons(run))})"
    grade = run.manifest.confidence
    if grade == "high":
        return grade  # the spec template: reasons only when not high
    score = run.manifest.critic_score
    reasons = []
    if CRITIC_FAILED in run.inputs.degradations:
        reasons.append(CRITIC_FAILED)
    elif score is None:
        reasons.append("critic not run")
    elif score < 8:
        reasons.append(f"critic score {score:.1f}")
    reasons += _other_reasons(run)
    return f"{grade} ({'; '.join(reasons)})" if reasons else grade


def _source(run: _Run) -> str:
    src = run.ingest.source
    title = src.title or "untitled"
    if src.author:
        author = src.author
    elif src.platform == "local":
        author = "local file"
    else:
        author = "unknown author"
    date = src.posted_at[:10] if src.posted_at else "undated"
    line = f'"{title}" by {author}, {date}'
    pack = run.pack
    if pack is not None:
        digest = pack.sha256.removeprefix("sha256:")[:12]
        line += f" (from pack {pack.file}, sha256 {digest})"
    return line


def _cached_transcript(run: _Run) -> bool:
    log = run.work / "logs" / "transcribe.log"
    if not log.is_file():
        return False
    text = log.read_text(encoding="utf-8", errors="replace")
    return any(line.startswith(CACHED_TRANSCRIPT) for line in text.splitlines())


def _provider_calls(run: _Run) -> str:
    line = run.report.provider_calls_line or ""
    transcript = run.transcript
    if run.pack is not None or transcript is None:
        return line
    if _cached_transcript(run):
        line += f"; transcript cached ({transcript.origin})"
    elif transcript.origin in CLOUD_KEYS:
        env = CLOUD_KEYS[transcript.origin]
        line += f"; {transcript.origin} transcription (billed to your {env} key)"
    return line


def _linked_post(run: _Run) -> str | None:
    for source in (run.ingest.notes, run.ingest.route.fallbacks):
        for note in source:
            if note.startswith(LINKED_POST):
                return note
    return None


def _extra_lines(run: _Run) -> list[str]:
    lines = []
    linked = _linked_post(run)
    if linked is not None:
        lines.append(linked)
    if run.ingest.fetched_with_cookies:
        lines.append(COOKIES_LINE)
    transcript = run.transcript
    if transcript is not None and transcript.cross_check is not None:
        check = transcript.cross_check
        if check.similarity is not None:
            lines.append(f"Cross-check: {check.similarity:.2f} against {check.origin}")
        warning = disagreement(transcript)
        if warning is not None:
            lines.append(warning)
    return lines


def screen(work: Path, skill: Path, inputs: ReviewInputs) -> str:
    run = _load(work, skill, inputs)
    unread = _unread(run)
    lines = [
        f"Triggers: {_triggers(run)}",
        f"Steps: {_steps(run)}",
        f"Unverified: {_unverified(run)}",
        f"Unread frames: {', '.join(unread) or 'none'}",
        f"Safety flags: {_safety(run)}",
        f"Confidence: {_confidence(run)}",
    ]
    if inputs.test_run is not None:
        lines.append(inputs.test_run)
    lines += [
        f"Source: {_source(run)}",
        f"Provider calls: {_provider_calls(run)}",
        f"Draft: {skill.absolute()}{os.sep}",
    ]
    lines += _extra_lines(run)
    head = f"Skill ready for review: {run.manifest.name}"
    return "\n".join([head, *(f"  {line}" for line in lines)]) + "\n"
