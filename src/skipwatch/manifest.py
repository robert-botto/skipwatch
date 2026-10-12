"""skipwatch.json: built by `check` (plan issue 1), finalised by `install` (R-MAN-1 hashes)."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel, ValidationError

from skipwatch import __version__
from skipwatch.errors import ExitCode, SkipwatchError
from skipwatch.models import (
    CheckReport,
    Counts,
    Critique,
    IngestBundle,
    Manifest,
    ManifestSource,
)
from skipwatch.skillmd import parse
from skipwatch.workdir import read_model, write_model

MANIFEST_NAME = "skipwatch.json"
M = TypeVar("M", bound=BaseModel)


def read_work_file(path: Path, cls: type[M]) -> M:
    """Read a work-folder JSON file; a bad one is exit 7 with the file name, never a crash."""
    try:
        return cls.model_validate_json(path.read_bytes())
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or "root"
        raise SkipwatchError(
            ExitCode.NO_CONTENT, f"{path.name} is not valid: {where}: {first['msg']}"
        ) from exc


def confidence(counts: Counts, critic_score: float | None) -> Literal["high", "medium", "low"]:
    """Section 4.3. Without a critic score (M1, plan issue 12) the best is `medium`."""
    if counts.steps == 0:
        return "low"
    inferred = counts.inferred / counts.steps
    if counts.gaps == 0 and inferred < 0.15 and critic_score is not None and critic_score >= 8:
        return "high"
    if counts.gaps <= 1 and inferred < 0.30:
        return "medium"
    return "low"


def pack_confidence(counts: Counts) -> Literal["high", "medium", "low"]:
    """The 4.3 rule for a shared pack: the critic did not run here, so at most `medium`."""
    return confidence(counts, None)


def _mtime_utc(path: Path) -> str:
    stamp = datetime.fromtimestamp(int(path.stat().st_mtime), UTC)
    return stamp.isoformat(timespec="seconds").replace("+00:00", "Z")


def build(staging: Path, work: Path, report: CheckReport) -> Manifest:
    ingest_path = work / "ingest.json"
    ingest = read_work_file(ingest_path, IngestBundle)
    skill_md = staging / "SKILL.md"
    text = skill_md.read_bytes().decode("utf-8", errors="replace") if skill_md.exists() else ""
    front = parse(text).frontmatter
    name = front.get("name")
    name = name if isinstance(name, str) else staging.name
    description = front.get("description")
    description = description if isinstance(description, str) else ""
    flags = [f for r in report.results if r.check == "safety" for f in r.flags]
    if ingest.pack is not None:
        # A shared pack keeps its claims so a round trip is byte-identical (M5-M6 issue 4);
        # counts, flags and checks are recomputed here, and critique.json is never read.
        claims = ingest.pack.manifest
        return Manifest(
            name=name,
            description=description,
            skipwatch_version=claims.skipwatch_version,
            source=claims.source,
            extracted_at=claims.extracted_at,
            fetched_with_cookies=claims.fetched_with_cookies,
            counts=report.counts,
            confidence=claims.confidence,
            critic_score=claims.critic_score,
            checks_passed=report.passed,
            safety_flags=flags,
        )
    critique_path = work / "critique.json"
    critic_score = read_work_file(critique_path, Critique).score if critique_path.exists() else None
    src = ingest.source
    return Manifest(
        name=name,
        description=description,
        skipwatch_version=__version__,
        source=ManifestSource(
            url=src.url,
            canonical_url=src.canonical_url,
            platform=src.platform,
            author=src.author,
            title=src.title,
            posted_at=src.posted_at,
        ),
        extracted_at=_mtime_utc(ingest_path),
        fetched_with_cookies=ingest.fetched_with_cookies,
        counts=report.counts,
        confidence=confidence(report.counts, critic_score),
        critic_score=critic_score,
        checks_passed=report.passed,
        safety_flags=flags,
    )


def file_hashes(skill_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in skill_dir.rglob("*"):
        rel = path.relative_to(skill_dir).as_posix()
        if path.is_file() and rel != MANIFEST_NAME:
            hashes[rel] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(sorted(hashes.items()))


def finalize_manifest(skill_dir: Path, checks_passed: bool) -> Manifest:
    path = skill_dir / MANIFEST_NAME
    manifest = read_model(path, Manifest).model_copy(
        update={"files": file_hashes(skill_dir), "checks_passed": checks_passed}
    )
    write_model(path, manifest)
    return manifest
