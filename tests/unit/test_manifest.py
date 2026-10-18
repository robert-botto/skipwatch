import hashlib
import json
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
from skipwatch.models import (
    CheckReport,
    CheckResult,
    Counts,
    Critique,
    Manifest,
    ManifestSource,
    SafetyFlag,
)
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
    assert m.skipwatch_version == "0.1.1"
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


def _claims() -> Manifest:
    return Manifest(
        name="claimed-name",
        description="claimed description",
        skipwatch_version="0.0.9",
        source=ManifestSource(platform="youtube", url="https://youtu.be/x", title="Pack title"),
        extracted_at="2026-09-01T10:00:00Z",
        fetched_with_cookies=False,
        counts=Counts(steps=99),
        confidence="high",
        critic_score=8.5,
        checks_passed=True,
        safety_flags=[],
        files={"SKILL.md": "sha256:" + "0" * 64},
    )


def _write_pack_field(work, cookies_in_ingest=False, files=None):
    raw = json.loads((work / "ingest.json").read_text(encoding="utf-8"))
    raw["fetched_with_cookies"] = cookies_in_ingest
    raw["pack"] = {
        "file": "a.skillpack.zip",
        "sha256": "sha256:" + "1" * 64,
        "manifest": _claims().model_copy(update={"files": files or {}}).model_dump(by_alias=True),
    }
    (work / "ingest.json").write_text(json.dumps(raw), encoding="utf-8")


def _pack_copy(home):
    """A pack work folder as unpack lays it out: $SKIPWATCH_HOME/packs/<name>-<stamp>/ with
    staging/<name>/, ingest.json carrying `pack`, and no frame notes or run transcript."""
    work = home / "packs" / "run-skipdemo-tutorial-20261011-120000"
    work.mkdir(parents=True)
    shutil.copy(FIX / "work/ingest.json", work / "ingest.json")
    staging = work / "staging" / "run-skipdemo-tutorial"
    shutil.copytree(FIX / "good/run-skipdemo-tutorial", staging)
    _write_pack_field(work, files=file_hashes(staging))
    return staging, work


def test_manifest_pack_mode_keeps_claims_and_recomputes_counts(sw_home):
    staging, work = _pack_copy(sw_home)
    flag = SafetyFlag(step=2, kind="sudo", text="sudo x", severity="medium")
    report = CheckReport(
        skill="run-skipdemo-tutorial",
        passed=False,
        results=[CheckResult(check="safety", ok=False, flags=[flag])],
        counts=Counts(steps=4, on_screen=3, spoken=1),
    )
    m = build(staging, work, report)
    claims = _claims()
    assert m.counts == Counts(steps=4, on_screen=3, spoken=1)
    assert m.safety_flags == [flag] and m.checks_passed is False
    assert m.confidence == "high" and m.critic_score == 8.5
    assert m.source == claims.source and m.extracted_at == claims.extracted_at
    assert m.skipwatch_version == "0.0.9" and m.fetched_with_cookies is False
    # name and description come from the shipped SKILL.md frontmatter, as in a run.
    assert m.name == "run-skipdemo-tutorial"
    assert m.description.startswith("Use when the user wants")


def test_manifest_pack_mode_keeps_claimed_cookie_flag(sw_home):
    staging, work = _pack_copy(sw_home)
    raw = json.loads((work / "ingest.json").read_text(encoding="utf-8"))
    raw["pack"]["manifest"]["fetched_with_cookies"] = True
    (work / "ingest.json").write_text(json.dumps(raw), encoding="utf-8")
    assert build(staging, work, _report()).fetched_with_cookies is True


def test_manifest_pack_mode_ignores_critique_json(sw_home):
    staging, work = _pack_copy(sw_home)
    scores = dict.fromkeys(
        ["completeness", "verifiability", "actionability", "trigger_quality", "safety_hygiene"],
        2.0,
    )
    write_model(work / "critique.json", Critique(scores=scores, score=2.0))  # pyright: ignore[reportArgumentType]
    m = build(staging, work, _report())
    assert m.critic_score == 8.5 and m.confidence == "high"


def test_manifest_forged_pack_in_run_folder_builds_as_a_run(sw_home, tmp_path):
    # A run that needed cookies gains a forged `pack` field: the claims (cookies false, another
    # source, confidence high) must not replace what the run recorded.
    staging, work = _copy(tmp_path)
    _write_pack_field(work, cookies_in_ingest=True)
    m = build(staging, work, _report())
    assert m.fetched_with_cookies is True
    assert m.source.title == "tutorial-60s" and m.source.platform == "local"
    assert m.confidence == "medium" and m.critic_score is None
    assert m.skipwatch_version == "0.1.1"


def test_manifest_pack_mode_cookies_from_ingest_are_never_dropped(sw_home):
    staging, work = _pack_copy(sw_home)
    _write_pack_field(work, cookies_in_ingest=True, files=file_hashes(staging))
    assert build(staging, work, _report()).fetched_with_cookies is True


def test_manifest_run_mode_unchanged_by_pack_helpers(tmp_path):
    staging, work = _copy(tmp_path)
    m = build(staging, work, _report())
    assert m.skipwatch_version == "0.1.1" and m.confidence == "medium"
    assert m.source.title == "tutorial-60s"


def test_pack_confidence_never_high():
    assert pack_confidence(Counts(steps=10)) == "medium"
    assert pack_confidence(Counts(steps=10, gaps=2)) == "low"


def test_manifest_pack_folder_with_edited_skill_md_builds_as_a_run(sw_home):
    staging, work = _pack_copy(sw_home)
    skill_md = staging / "SKILL.md"
    skill_md.write_text(skill_md.read_text(encoding="utf-8") + "\nEdited.\n", encoding="utf-8")
    m = build(staging, work, _report())
    assert m.confidence == "medium" and m.critic_score is None
    assert m.skipwatch_version == "0.1.1" and m.source.title == "tutorial-60s"
