import hashlib
import os
import shutil
from pathlib import Path

from skipwatch.manifest import (
    build,
    confidence,
    file_hashes,
    finalize_manifest,
    pack_confidence,
)
from skipwatch.models import CheckReport, CheckResult, Counts, Critique, Manifest, SafetyFlag
from skipwatch.workdir import read_model, write_model

FIX = Path(__file__).resolve().parents[1] / "fixtures/skills"


def _copy(tmp_path):
    work = tmp_path / "work"
    shutil.copytree(FIX / "work", work)
    staging = work / "staging" / "run-skipdemo-tutorial"
    shutil.copytree(FIX / "good/run-skipdemo-tutorial", staging)
    return staging, work


def _report(passed=True, flags=()):
    return CheckReport(
        skill="run-skipdemo-tutorial",
        passed=passed,
        results=[CheckResult(check="safety", ok=True, flags=list(flags))],
        counts=Counts(steps=5, on_screen=4, spoken=1),
    )


def test_confidence_high_impossible_without_critic():
    assert confidence(Counts(steps=5, on_screen=4, spoken=1), None) == "medium"


def test_confidence_high_with_critic_score():
    assert confidence(Counts(steps=10, spoken=9, inferred=1), 8.0) == "high"


def test_confidence_high_needs_zero_gaps():
    assert confidence(Counts(steps=10, spoken=10, gaps=1), 9.0) == "medium"


def test_confidence_high_needs_inferred_under_15_percent():
    assert confidence(Counts(steps=20, spoken=17, inferred=3), 9.0) == "medium"


def test_confidence_low_on_two_gaps():
    assert confidence(Counts(steps=10, spoken=10, gaps=2), 9.0) == "low"


def test_confidence_low_on_inferred_30_percent():
    assert confidence(Counts(steps=10, spoken=7, inferred=3), 9.0) == "low"


def test_confidence_low_on_zero_steps():
    assert confidence(Counts(), 9.0) == "low"


def test_build_reads_source_and_frontmatter(tmp_path):
    staging, work = _copy(tmp_path)
    flag = SafetyFlag(step=1, kind="sudo", text="sudo x", severity="medium")
    m = build(staging, work, _report(flags=[flag]))
    assert m.name == "run-skipdemo-tutorial"
    assert m.description.startswith("Use when the user wants")
    assert m.source.title == "tutorial-60s" and m.source.platform == "local"
    assert m.skipwatch_version == "0.1.0"
    assert m.confidence == "medium" and m.critic_score is None
    assert m.checks_passed is True and m.safety_flags == [flag]
    assert m.files == {}


def test_build_extracted_at_from_ingest_mtime(tmp_path):
    staging, work = _copy(tmp_path)
    os.utime(work / "ingest.json", (1_791_570_000, 1_791_570_000))
    assert build(staging, work, _report()).extracted_at == "2026-10-09T18:20:00Z"


def test_build_uses_critic_score(tmp_path):
    staging, work = _copy(tmp_path)
    scores = dict.fromkeys(
        ["completeness", "verifiability", "actionability", "trigger_quality", "safety_hygiene"],
        9.0,
    )
    write_model(work / "critique.json", Critique(scores=scores, score=9.0))  # pyright: ignore[reportArgumentType]
    m = build(staging, work, _report())
    assert m.critic_score == 9.0 and m.confidence == "high"


def test_file_hashes_excludes_manifest_and_is_stable(tmp_path):
    staging, _ = _copy(tmp_path)
    (staging / "skipwatch.json").write_text("{}", encoding="utf-8")
    first = file_hashes(staging)
    assert "skipwatch.json" not in first
    assert list(first) == sorted(first)
    assert "references/source.md" in first
    want = hashlib.sha256((staging / "SKILL.md").read_bytes()).hexdigest()
    assert first["SKILL.md"] == f"sha256:{want}"
    assert file_hashes(staging) == first


def test_finalize_manifest_sets_files_and_checks_passed(tmp_path):
    staging, work = _copy(tmp_path)
    write_model(staging / "skipwatch.json", build(staging, work, _report(passed=False)))
    m = finalize_manifest(staging, checks_passed=True)
    on_disk = read_model(staging / "skipwatch.json", Manifest)
    assert m == on_disk and on_disk.checks_passed is True
    assert on_disk.files == file_hashes(staging)


def test_pack_confidence_never_high():
    assert pack_confidence(Counts(steps=10)) == "medium"
    assert pack_confidence(Counts(steps=10, gaps=2)) == "low"
